"""Pinned R185 40% revision-weight projection of the R184 order source.

The R184 source is authenticated before exact, counted token substitutions.
Only its target builder, runtime, and entry point change in this separate
backtest project. The R182 selected stocks, 98% gross target, caps, score
ranking, and 2x order-admission bridge remain in the source closure.
"""

import dataclasses
import hashlib
import json

from . import accepted_risk_six_universe_order_qc_projection as _base
from . import accepted_risk_six_universe_order_tilt_qc_projection as _r184
from . import accepted_risk_six_universe_order_tilt_qc_runtime as _r184_runtime
from . import accepted_risk_six_universe_order_tilt_targets as _r184_targets


class SixUniverseTilt40QcProjectionError(ValueError):
    """A source, profile, package, or R185 identity changed from its pin."""


TILT40_ROLE = "matched_revision_tilt40"
TILT40_VARIANT = "cap90_matched_revision_tilt40_admission_bridge_v1"
TILT40_PROFILE_SCHEMA = "arv2-six-universe-order-tilt40-bridge-profile-v1"
TILT40_PROFILE_ID = "arv2-six-universe-order-matched-revision-tilt40-bridge-v1"
TILT40_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt40-bridge-summary-v1"
TILT40_DECISION_TARGET_SCHEMA = "arv2-six-universe-order-tilt40-decision-target-v1"
TILT40_TARGET_PATH_SCHEMA = "arv2-six-universe-order-tilt40-target-path-v1"
TILT40_RANK_RULE_ID = _r184_targets.TILT_RANK_RULE_ID
PROJECTION_SCHEMA = "arv2-six-universe-order-qc-projection-tilt40-bridge-v1"

_R184_PROJECTION_SHA256 = (
    "8fdb1e051c1e9620c1a126dd9d2bd09c1eb298d9dd8ae1d4e7d07ada61af9afc"
)
_R184_PROFILE_SHA256 = (
    "e0c77820c37b394a88ab7cfc95370b1ce6218c0860ee264fc52bad9b93ada9b2"
)
_R184_TOTAL_SOURCE_BYTES = 422_728
_R184_SOURCE_SHA256S = {
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": (
        "d6cd9f963e4754e134d1a6116ee300711ad7e28bc0e4b95f15e241d7e22f1489"
    ),
    "accepted_risk_six_universe_order_tilt_targets.py": (
        "b063c5bca9e4aa13e2deff66726cc4b6c12c405845921c1ee39bbe653f266506"
    ),
    "main.py": (
        "5d03dcc26a8e86288cf78a9bdab0718a94bb7b7f3be52300ae0c37b40cd24e0f"
    ),
}
_R184_SOURCE_BYTE_COUNTS = {
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": 7698,
    "accepted_risk_six_universe_order_tilt_targets.py": 20733,
    "main.py": 6573,
}

# Every replacement is tied to one exact source line or sentence. The two
# runtime fraction occurrences bind both the profile and the aggregate.
_TRANSFORMS = {
    "accepted_risk_six_universe_order_tilt_targets.py": (
        ('TILT_ROLE = "matched_revision_tilt"',
         'TILT_ROLE = "matched_revision_tilt40"', 1),
        ('MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION = Decimal("0.20")',
         'MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION = Decimal("0.40")', 1),
        ('DECISION_TARGET_SCHEMA = "arv2-six-universe-order-tilt-decision-target-v4"',
         'DECISION_TARGET_SCHEMA = "arv2-six-universe-order-tilt40-decision-target-v1"', 1),
        ('TARGET_PATH_SCHEMA = "arv2-six-universe-order-tilt-target-path-v4"',
         'TARGET_PATH_SCHEMA = "arv2-six-universe-order-tilt40-target-path-v1"', 1),
        ('bounded by 20% of its own post-cap',
         'bounded by 40% of its own post-cap', 1),
        ('"maximum_stock_weight_change_fraction": "0.20"',
         '"maximum_stock_weight_change_fraction": "0.40"', 1),
        ('"arv2-six-universe-order-tilt-target-path-"',
         '"arv2-six-universe-order-tilt40-target-path-"', 1),
        ('A later v4\norder runtime', 'A projected\norder runtime', 1),
        ('The v4 caller must', 'The projected caller must', 1),
    ),
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": (
        ('TILT_VARIANT = "cap90_matched_revision_tilt_admission_bridge_v1"',
         'TILT_VARIANT = "cap90_matched_revision_tilt40_admission_bridge_v1"', 1),
        ('TILT_PROFILE_SCHEMA = "arv2-six-universe-order-tilt-bridge-profile-v1"',
         'TILT_PROFILE_SCHEMA = "arv2-six-universe-order-tilt40-bridge-profile-v1"', 1),
        ('TILT_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt-bridge-summary-v1"',
         'TILT_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt40-bridge-summary-v1"', 1),
        ('"profile_id": "arv2-six-universe-order-matched-revision-tilt-bridge-v1"',
         '"profile_id": "arv2-six-universe-order-matched-revision-tilt40-bridge-v1"', 1),
        ('"maximum_stock_weight_change_fraction": "0.20"',
         '"maximum_stock_weight_change_fraction": "0.40"', 2),
    ),
    "main.py": (
        ('class ARV2SixUniverseOrderTiltAlgorithm(QCAlgorithm):',
         'class ARV2SixUniverseOrderTilt40Algorithm(QCAlgorithm):', 1),
        ("role='matched_revision_tilt',", "role='matched_revision_tilt40',", 1),
        ("variant='cap90_matched_revision_tilt_admission_bridge_v1',",
         "variant='cap90_matched_revision_tilt40_admission_bridge_v1',", 1),
    ),
}

_R185_SOURCE_SHA256S = {
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": (
        "ffee457b0ce283a097af0903ae529aa5c04fba05966f4641650b0690c061a035"
    ),
    "accepted_risk_six_universe_order_tilt_targets.py": (
        "ec794e09d62f6c071a0fc17969f2256a5ea37780ae8fba4251763721ea769630"
    ),
    "main.py": (
        "0afabfd5362d5103a78943a16f4e47015ca059d83446272485c2b171a4ab72ba"
    ),
}
_R185_SOURCE_BYTE_COUNTS = {
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": 7706,
    "accepted_risk_six_universe_order_tilt_targets.py": 20749,
    "main.py": 6579,
}
PINNED_TILT40_PROFILE_SHA256 = (
    "a76cead2de5fef1176803f77b2a7efd3cc11fa24734dcdcf91a047f4ae552539"
)
PINNED_TILT40_PROJECTION_SHA256 = (
    "2a9f9a2175e2765c1136d4aca3d86d617bbee970769eecae6dcab2e0f1127c7d"
)
PINNED_TILT40_TOTAL_SOURCE_BYTES = 422_758


def _error(message):
    raise SixUniverseTilt40QcProjectionError(message)


def _replace_exact(source_bytes, replacements):
    if type(source_bytes) is not bytes or type(replacements) is not tuple:
        _error("R185 source replacement contract changed")
    try:
        source = source_bytes.decode("ascii")
    except UnicodeError as exc:
        raise SixUniverseTilt40QcProjectionError(
            "R184 projected source is not ASCII"
        ) from exc
    for old, new, count in replacements:
        if (
            type(old) is not str or type(new) is not str
            or type(count) is not int or count < 1
            or old == new or source.count(old) != count
        ):
            _error("R185 projected source lost an exact replacement point")
        source = source.replace(old, new, count)
    return source.encode("ascii")


def _render_tilt40_profile():
    baseline = _r184_runtime.require_tilt_profile()
    if (
        baseline["profile_sha256"] != _R184_PROFILE_SHA256
        or baseline["role"] != _r184_targets.TILT_ROLE
        or baseline["maximum_stock_weight_change_fraction"] != "0.20"
        or TILT40_RANK_RULE_ID != _r184_targets.TILT_RANK_RULE_ID
    ):
        _error("R184 tilt profile changed from its pin")
    seed = {
        key: value for key, value in baseline.items()
        if key != "profile_sha256"
    }
    seed.update({
        "schema": TILT40_PROFILE_SCHEMA,
        "profile_id": TILT40_PROFILE_ID,
        "role": TILT40_ROLE,
        "target_path_schema": TILT40_TARGET_PATH_SCHEMA,
        "decision_target_schema": TILT40_DECISION_TARGET_SCHEMA,
        "maximum_stock_weight_change_fraction": "0.40",
    })
    return json.loads(_base._canonical({
        **seed,
        "profile_sha256": hashlib.sha256(_base._canonical(seed)).hexdigest(),
    }).decode("ascii"))


def require_tilt40_profile():
    """Return the exact R185 profile derived from R182/R184 lineage."""
    profile = _render_tilt40_profile()
    if profile["profile_sha256"] != PINNED_TILT40_PROFILE_SHA256:
        _error("R185 tilt40 profile changed from its pin")
    return profile


def _build_projection(delta_package):
    try:
        baseline = _r184.build_accepted_risk_six_universe_order_tilt_qc_projection(
            delta_package
        )
    except _r184.SixUniverseTiltQcProjectionError as exc:
        raise SixUniverseTilt40QcProjectionError(str(exc)) from exc
    if (
        baseline.projection_sha256 != _R184_PROJECTION_SHA256
        or baseline.profile_sha256 != _R184_PROFILE_SHA256
        or baseline.total_source_byte_count != _R184_TOTAL_SOURCE_BYTES
        or len(baseline.source_files) != 16
        or baseline.variant != _r184_runtime.TILT_VARIANT
    ):
        _error("R184 projected source changed from its pin")
    profile = _render_tilt40_profile()
    files = []
    for item in baseline.source_files:
        path = item.project_path
        if (
            item.byte_count != len(item.source_bytes)
            or item.content_sha256 != hashlib.sha256(item.source_bytes).hexdigest()
        ):
            _error("R184 projected file identity changed")
        if path in _TRANSFORMS:
            if (
                item.content_sha256 != _R184_SOURCE_SHA256S[path]
                or item.byte_count != _R184_SOURCE_BYTE_COUNTS[path]
            ):
                _error("R184 transformed source changed from its exact pin")
            try:
                files.append(_base._source_file(
                    path,
                    _replace_exact(item.source_bytes, _TRANSFORMS[path]),
                ))
            except _base.AcceptedRiskSixUniverseOrderQcProjectionError as exc:
                raise SixUniverseTilt40QcProjectionError(str(exc)) from exc
        else:
            files.append(item)
    files.sort(key=lambda item: item.project_path)
    if (
        len(files) != 16
        or len({item.project_path for item in files}) != 16
        or set(_TRANSFORMS) != set(_R184_SOURCE_SHA256S)
        or any(
            len(item.source_bytes.decode("ascii"))
            > _base.MAXIMUM_QC_SOURCE_CHARACTERS
            for item in files
        )
    ):
        _error("R185 projected source closure or QC file bound changed")
    for item in files:
        compile(
            "from AlgorithmImports import *\n" + item.source_bytes.decode("ascii"),
            item.project_path,
            "exec",
        )
    total = sum(item.byte_count for item in files)
    if total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES:
        _error("R185 projected source exceeded the reviewed total bound")
    semantic = {
        key: value for key, value in baseline.to_record().items()
        if key not in ("projection_id", "projection_sha256")
    }
    semantic.update({
        "schema": PROJECTION_SCHEMA,
        "role": TILT40_ROLE,
        "variant": TILT40_VARIANT,
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "source_files": [item.to_record() for item in files],
        "total_source_byte_count": total,
    })
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    value = dataclasses.replace(
        baseline,
        schema=PROJECTION_SCHEMA,
        projection_id="arv2-six-universe-order-tilt40-qc-projection-" + digest[:24],
        projection_sha256=digest,
        role=TILT40_ROLE,
        variant=TILT40_VARIANT,
        profile_id=profile["profile_id"],
        profile_sha256=profile["profile_sha256"],
        source_files=tuple(files),
        total_source_byte_count=total,
    )
    if {
        key: item for key, item in value.to_record().items()
        if key not in ("projection_id", "projection_sha256")
    } != semantic:
        _error("R185 projection did not self-authenticate")
    return value


def build_accepted_risk_six_universe_order_tilt40_qc_projection(delta_package):
    """Build the exact, backtest-only, 16-file R185 order source."""
    value = _build_projection(delta_package)
    if (
        value.profile_sha256 != PINNED_TILT40_PROFILE_SHA256
        or value.projection_sha256 != PINNED_TILT40_PROJECTION_SHA256
        or value.total_source_byte_count != PINNED_TILT40_TOTAL_SOURCE_BYTES
        or any(
            item.content_sha256 != _R185_SOURCE_SHA256S[item.project_path]
            or item.byte_count != _R185_SOURCE_BYTE_COUNTS[item.project_path]
            for item in value.source_files
            if item.project_path in _R185_SOURCE_SHA256S
        )
    ):
        _error("R185 projected profile, manifest, or source changed from its pin")
    return value


__all__ = (
    "PINNED_TILT40_PROFILE_SHA256",
    "PINNED_TILT40_PROJECTION_SHA256",
    "PINNED_TILT40_TOTAL_SOURCE_BYTES",
    "PROJECTION_SCHEMA",
    "SixUniverseTilt40QcProjectionError",
    "TILT40_PROFILE_ID",
    "TILT40_PROFILE_SCHEMA",
    "TILT40_RANK_RULE_ID",
    "TILT40_ROLE",
    "TILT40_SUMMARY_SCHEMA",
    "TILT40_VARIANT",
    "build_accepted_risk_six_universe_order_tilt40_qc_projection",
    "require_tilt40_profile",
)
