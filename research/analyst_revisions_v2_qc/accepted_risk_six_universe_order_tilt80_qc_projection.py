"""Pinned R186 80% revision-weight projection of the exact R185 order source.

The R185 16-file source is authenticated before counted substitutions in only
the target builder, runtime, and entry point. Stock identities, ETF fallbacks,
six sleeve budgets, 98% gross target, caps, and order-admission bridge remain.
"""

import dataclasses
import hashlib
import json

from . import accepted_risk_six_universe_order_qc_projection as _base
from . import accepted_risk_six_universe_order_tilt40_qc_projection as _r185


class SixUniverseTilt80QcProjectionError(ValueError):
    """A source, profile, package, or R186 identity changed from its pin."""


TILT80_ROLE = "matched_revision_tilt80"
TILT80_VARIANT = "cap90_matched_revision_tilt80_admission_bridge_v1"
TILT80_PROFILE_SCHEMA = "arv2-six-universe-order-tilt80-bridge-profile-v1"
TILT80_PROFILE_ID = "arv2-six-universe-order-matched-revision-tilt80-bridge-v1"
TILT80_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt80-bridge-summary-v1"
TILT80_DECISION_TARGET_SCHEMA = "arv2-six-universe-order-tilt80-decision-target-v1"
TILT80_TARGET_PATH_SCHEMA = "arv2-six-universe-order-tilt80-target-path-v1"
TILT80_RANK_RULE_ID = _r185.TILT40_RANK_RULE_ID
PROJECTION_SCHEMA = "arv2-six-universe-order-qc-projection-tilt80-bridge-v1"

_R185_PROJECTION_SHA256 = (
    "2a9f9a2175e2765c1136d4aca3d86d617bbee970769eecae6dcab2e0f1127c7d"
)
_R185_PROFILE_SHA256 = (
    "a76cead2de5fef1176803f77b2a7efd3cc11fa24734dcdcf91a047f4ae552539"
)
_R185_TOTAL_SOURCE_BYTES = 422_758
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

# Every replacement is counted against an exact, SHA-pinned R185 cloud file.
# The runtime fraction appears in both the profile and summary aggregates.
_TRANSFORMS = {
    "accepted_risk_six_universe_order_tilt_targets.py": (
        ('TILT_ROLE = "matched_revision_tilt40"',
         'TILT_ROLE = "matched_revision_tilt80"', 1),
        ('MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION = Decimal("0.40")',
         'MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION = Decimal("0.80")', 1),
        ('DECISION_TARGET_SCHEMA = "arv2-six-universe-order-tilt40-decision-target-v1"',
         'DECISION_TARGET_SCHEMA = "arv2-six-universe-order-tilt80-decision-target-v1"', 1),
        ('TARGET_PATH_SCHEMA = "arv2-six-universe-order-tilt40-target-path-v1"',
         'TARGET_PATH_SCHEMA = "arv2-six-universe-order-tilt80-target-path-v1"', 1),
        ('bounded by 40% of its own post-cap',
         'bounded by 80% of its own post-cap', 1),
        ('"maximum_stock_weight_change_fraction": "0.40"',
         '"maximum_stock_weight_change_fraction": "0.80"', 1),
        ('"arv2-six-universe-order-tilt40-target-path-"',
         '"arv2-six-universe-order-tilt80-target-path-"', 1),
    ),
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": (
        ('TILT_VARIANT = "cap90_matched_revision_tilt40_admission_bridge_v1"',
         'TILT_VARIANT = "cap90_matched_revision_tilt80_admission_bridge_v1"', 1),
        ('TILT_PROFILE_SCHEMA = "arv2-six-universe-order-tilt40-bridge-profile-v1"',
         'TILT_PROFILE_SCHEMA = "arv2-six-universe-order-tilt80-bridge-profile-v1"', 1),
        ('TILT_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt40-bridge-summary-v1"',
         'TILT_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt80-bridge-summary-v1"', 1),
        ('"profile_id": "arv2-six-universe-order-matched-revision-tilt40-bridge-v1"',
         '"profile_id": "arv2-six-universe-order-matched-revision-tilt80-bridge-v1"', 1),
        ('"maximum_stock_weight_change_fraction": "0.40"',
         '"maximum_stock_weight_change_fraction": "0.80"', 2),
    ),
    "main.py": (
        ('class ARV2SixUniverseOrderTilt40Algorithm(QCAlgorithm):',
         'class ARV2SixUniverseOrderTilt80Algorithm(QCAlgorithm):', 1),
        ("role='matched_revision_tilt40',", "role='matched_revision_tilt80',", 1),
        ("variant='cap90_matched_revision_tilt40_admission_bridge_v1',",
         "variant='cap90_matched_revision_tilt80_admission_bridge_v1',", 1),
    ),
}

_R186_SOURCE_SHA256S = {
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": (
        "af48bcceef6c23769f4a4c803331a208be4afefcdb403eb48533e0fc44627a59"
    ),
    "accepted_risk_six_universe_order_tilt_targets.py": (
        "efecce41bd727558ac53768ffd68b0b750a27cb20b78386f1c0be5c600f47f2d"
    ),
    "main.py": (
        "4b42b34f40eb234782876276906aa3f087367f7ea2db99a149cc4f97151681dc"
    ),
}
_R186_SOURCE_BYTE_COUNTS = {
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": 7706,
    "accepted_risk_six_universe_order_tilt_targets.py": 20749,
    "main.py": 6579,
}
PINNED_TILT80_PROFILE_SHA256 = (
    "2fe851dd13421ea0d7d750d17ba509ee6f8407e25eb6a142725cf7c17f387036"
)
PINNED_TILT80_PROJECTION_SHA256 = (
    "16240a1ead1dd8466961556ffcfcfc58a6c974d763e87b72c27cfdce72699604"
)
PINNED_TILT80_TOTAL_SOURCE_BYTES = 422_758


def _error(message):
    raise SixUniverseTilt80QcProjectionError(message)


def _replace_exact(source_bytes, replacements):
    if type(source_bytes) is not bytes or type(replacements) is not tuple:
        _error("R186 source replacement contract changed")
    try:
        source = source_bytes.decode("ascii")
    except UnicodeError as exc:
        raise SixUniverseTilt80QcProjectionError(
            "R185 projected source is not ASCII"
        ) from exc
    for old, new, count in replacements:
        if (
            type(old) is not str or type(new) is not str
            or type(count) is not int or count < 1
            or old == new or source.count(old) != count
        ):
            _error("R186 projected source lost an exact replacement point")
        source = source.replace(old, new, count)
    return source.encode("ascii")


def _render_tilt80_profile():
    baseline = _r185.require_tilt40_profile()
    if (
        baseline["profile_sha256"] != _R185_PROFILE_SHA256
        or baseline["role"] != _r185.TILT40_ROLE
        or baseline["maximum_stock_weight_change_fraction"] != "0.40"
        or TILT80_RANK_RULE_ID != _r185.TILT40_RANK_RULE_ID
    ):
        _error("R185 tilt profile changed from its pin")
    seed = {
        key: value for key, value in baseline.items()
        if key != "profile_sha256"
    }
    seed.update({
        "schema": TILT80_PROFILE_SCHEMA,
        "profile_id": TILT80_PROFILE_ID,
        "role": TILT80_ROLE,
        "target_path_schema": TILT80_TARGET_PATH_SCHEMA,
        "decision_target_schema": TILT80_DECISION_TARGET_SCHEMA,
        "maximum_stock_weight_change_fraction": "0.80",
    })
    return json.loads(_base._canonical({
        **seed,
        "profile_sha256": hashlib.sha256(_base._canonical(seed)).hexdigest(),
    }).decode("ascii"))


def require_tilt80_profile():
    """Return the exact R186 profile derived from R182/R184/R185 lineage."""
    profile = _render_tilt80_profile()
    if profile["profile_sha256"] != PINNED_TILT80_PROFILE_SHA256:
        _error("R186 tilt80 profile changed from its pin")
    return profile


def _build_projection(delta_package):
    try:
        baseline = _r185.build_accepted_risk_six_universe_order_tilt40_qc_projection(
            delta_package
        )
    except _r185.SixUniverseTilt40QcProjectionError as exc:
        raise SixUniverseTilt80QcProjectionError(str(exc)) from exc
    if (
        baseline.projection_sha256 != _R185_PROJECTION_SHA256
        or baseline.profile_sha256 != _R185_PROFILE_SHA256
        or baseline.total_source_byte_count != _R185_TOTAL_SOURCE_BYTES
        or len(baseline.source_files) != 16
        or baseline.variant != _r185.TILT40_VARIANT
    ):
        _error("R185 projected source changed from its pin")
    profile = _render_tilt80_profile()
    files = []
    for item in baseline.source_files:
        path = item.project_path
        if (
            item.byte_count != len(item.source_bytes)
            or item.content_sha256 != hashlib.sha256(item.source_bytes).hexdigest()
        ):
            _error("R185 projected file identity changed")
        if path in _TRANSFORMS:
            if (
                item.content_sha256 != _R185_SOURCE_SHA256S[path]
                or item.byte_count != _R185_SOURCE_BYTE_COUNTS[path]
            ):
                _error("R185 transformed source changed from its exact pin")
            try:
                files.append(_base._source_file(
                    path,
                    _replace_exact(item.source_bytes, _TRANSFORMS[path]),
                ))
            except _base.AcceptedRiskSixUniverseOrderQcProjectionError as exc:
                raise SixUniverseTilt80QcProjectionError(str(exc)) from exc
        else:
            files.append(item)
    files.sort(key=lambda item: item.project_path)
    if (
        len(files) != 16
        or len({item.project_path for item in files}) != 16
        or set(_TRANSFORMS) != set(_R185_SOURCE_SHA256S)
        or any(
            len(item.source_bytes.decode("ascii"))
            > _base.MAXIMUM_QC_SOURCE_CHARACTERS
            for item in files
        )
    ):
        _error("R186 projected source closure or QC file bound changed")
    for item in files:
        compile(
            "from AlgorithmImports import *\n" + item.source_bytes.decode("ascii"),
            item.project_path,
            "exec",
        )
    total = sum(item.byte_count for item in files)
    if total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES:
        _error("R186 projected source exceeded the reviewed total bound")
    semantic = {
        key: value for key, value in baseline.to_record().items()
        if key not in ("projection_id", "projection_sha256")
    }
    semantic.update({
        "schema": PROJECTION_SCHEMA,
        "role": TILT80_ROLE,
        "variant": TILT80_VARIANT,
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "source_files": [item.to_record() for item in files],
        "total_source_byte_count": total,
    })
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    value = dataclasses.replace(
        baseline,
        schema=PROJECTION_SCHEMA,
        projection_id="arv2-six-universe-order-tilt80-qc-projection-" + digest[:24],
        projection_sha256=digest,
        role=TILT80_ROLE,
        variant=TILT80_VARIANT,
        profile_id=profile["profile_id"],
        profile_sha256=profile["profile_sha256"],
        source_files=tuple(files),
        total_source_byte_count=total,
    )
    if {
        key: item for key, item in value.to_record().items()
        if key not in ("projection_id", "projection_sha256")
    } != semantic:
        _error("R186 projection did not self-authenticate")
    return value


def build_accepted_risk_six_universe_order_tilt80_qc_projection(delta_package):
    """Build the exact, backtest-only, 16-file R186 order source."""
    value = _build_projection(delta_package)
    if (
        value.profile_sha256 != PINNED_TILT80_PROFILE_SHA256
        or value.projection_sha256 != PINNED_TILT80_PROJECTION_SHA256
        or value.total_source_byte_count != PINNED_TILT80_TOTAL_SOURCE_BYTES
        or any(
            item.content_sha256 != _R186_SOURCE_SHA256S[item.project_path]
            or item.byte_count != _R186_SOURCE_BYTE_COUNTS[item.project_path]
            for item in value.source_files
            if item.project_path in _R186_SOURCE_SHA256S
        )
    ):
        _error("R186 projected profile, manifest, or source changed from its pin")
    return value


__all__ = (
    "PINNED_TILT80_PROFILE_SHA256",
    "PINNED_TILT80_PROJECTION_SHA256",
    "PINNED_TILT80_TOTAL_SOURCE_BYTES",
    "PROJECTION_SCHEMA",
    "SixUniverseTilt80QcProjectionError",
    "TILT80_PROFILE_ID",
    "TILT80_PROFILE_SCHEMA",
    "TILT80_RANK_RULE_ID",
    "TILT80_ROLE",
    "TILT80_SUMMARY_SCHEMA",
    "TILT80_VARIANT",
    "build_accepted_risk_six_universe_order_tilt80_qc_projection",
    "require_tilt80_profile",
)
