"""Exact cloud projection for matched stocks plus revision weight tilt.

The R182 bridge matched source is authenticated first. The tilt adds only
its target builder, runtime, and role-bound entry point; all three use the
same 2x buying-power admission policy and unlevered validity gates.
"""

import dataclasses
import hashlib
from pathlib import Path

from . import accepted_risk_six_universe_order_qc_projection as _base
from . import accepted_risk_six_universe_order_bridge_qc_projection as _bridge_projection
from . import accepted_risk_six_universe_order_bridge_qc_runtime as _bridge_runtime
from . import accepted_risk_six_universe_order_targets as _targets
from . import accepted_risk_six_universe_order_tilt_qc_runtime as _tilt_runtime
from . import accepted_risk_six_universe_order_tilt_targets as _tilt_targets


class SixUniverseTiltQcProjectionError(ValueError):
    """A tilt source, bridge profile, package, or capability changed."""


PROJECTION_SCHEMA = "arv2-six-universe-order-qc-projection-tilt-bridge-v1"
PINNED_BASE_MATCHED_PROJECTION_SHA256 = (
    "186cb2bb3dbd2a37358c9c0b2dbfa86e1e685203dba33795eb192f74faa9feeb"
)
PINNED_BASE_MATCHED_PROFILE_SHA256 = (
    "b419d3f2b149a1509ef09bd0a5bf607bea8c25a3363cbc8a9dc04a40910f9c0c"
)
PINNED_TILT_PROFILE_SHA256 = (
    "e0c77820c37b394a88ab7cfc95370b1ce6218c0860ee264fc52bad9b93ada9b2"
)
_TILT_SOURCE_SHA256S = {
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": (
        "d6cd9f963e4754e134d1a6116ee300711ad7e28bc0e4b95f15e241d7e22f1489"
    ),
    "accepted_risk_six_universe_order_tilt_targets.py": (
        "b063c5bca9e4aa13e2deff66726cc4b6c12c405845921c1ee39bbe653f266506"
    ),
}


def _error(message):
    raise SixUniverseTiltQcProjectionError(message)


def _read_exact_tilt_source(project_path):
    if project_path not in _TILT_SOURCE_SHA256S:
        _error("tilt source path is outside the frozen bridge closure")
    try:
        source = (Path(__file__).resolve().parent / project_path).read_bytes()
    except OSError as exc:
        raise SixUniverseTiltQcProjectionError(
            "tilt projected source is unavailable"
        ) from exc
    if hashlib.sha256(source).hexdigest() != _TILT_SOURCE_SHA256S[project_path]:
        _error("tilt source bytes changed from the v4 pin")
    return source


def _tilt_main_source(activation, profile):
    if (
        profile.get("role") != _tilt_targets.TILT_ROLE
        or profile.get("profile_sha256") != PINNED_TILT_PROFILE_SHA256
    ):
        _error("tilt main profile changed")
    original = _base._main_source(
        activation=activation,
        profile=profile,
        variant=_tilt_runtime.TILT_VARIANT,
    ).decode("ascii")
    substitutions = (
        (
            "from accepted_risk_six_universe_order_qc_runtime import (\n"
            "    AcceptedRiskSixUniverseOrderQcDriver,\n"
            "    STARTING_CASH,\n"
            ")\n",
            "from accepted_risk_six_universe_order_qc_runtime import STARTING_CASH\n"
            "from accepted_risk_six_universe_order_tilt_qc_runtime import (\n"
            "    AcceptedRiskSixUniverseOrderTiltQcDriver,\n"
            ")\n",
        ),
        (
            "class ARV2SixUniverseOrderAlgorithm(QCAlgorithm):",
            "class ARV2SixUniverseOrderTiltAlgorithm(QCAlgorithm):",
        ),
        (
            "self._arv2_driver = AcceptedRiskSixUniverseOrderQcDriver(",
            "self._arv2_driver = AcceptedRiskSixUniverseOrderTiltQcDriver(",
        ),
        (
            "self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW\n",
            "self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW\n"
            "        self.universe_settings.leverage = 2\n",
        ),
        ("                leverage=1,\n", "                leverage=2,\n"),
    )
    for old, new in substitutions:
        if original.count(old) != 1:
            _error("tilt main source no longer has its exact insertion point")
        original = original.replace(old, new, 1)
    if (
        original.count("self.universe_settings.leverage = 2") != 1
        or original.count("                leverage=2,\n") != 1
        or "                leverage=1,\n" in original
    ):
        _error("tilt main admission leverage changed")
    return original.encode("ascii")


def build_accepted_risk_six_universe_order_tilt_qc_projection(delta_package):
    """Build the tilt source from exact R182 bridge matched source."""
    try:
        baseline = _bridge_projection.build_accepted_risk_six_universe_order_bridge_qc_projection(
            delta_package, role=_targets.ROLE_MATCHED,
        )
    except _bridge_projection.SixUniverseBridgeQcProjectionError as exc:
        raise SixUniverseTiltQcProjectionError(str(exc)) from exc
    if (
        baseline.projection_sha256
        != PINNED_BASE_MATCHED_PROJECTION_SHA256
        or baseline.profile_sha256 != PINNED_BASE_MATCHED_PROFILE_SHA256
        or baseline.variant != _bridge_runtime.BRIDGE_VARIANT
        or len(baseline.source_files) != 14
    ):
        _error("R182 bridge matched source projection changed from its pin")

    profile = _tilt_runtime.require_tilt_profile()
    if (
        profile["role"] != _tilt_targets.TILT_ROLE
        or profile["profile_sha256"] != PINNED_TILT_PROFILE_SHA256
        or profile["matched_baseline_profile_sha256"]
        != PINNED_BASE_MATCHED_PROFILE_SHA256
    ):
        _error("bridge revision tilt profile changed")
    activation = delta_package.package.upload_objects[-1]
    files = [
        item for item in baseline.source_files
        if item.project_path != _base.MAIN_PROJECT_PATH
    ]
    for project_path in _TILT_SOURCE_SHA256S:
        try:
            files.append(_base._source_file(
                project_path, _read_exact_tilt_source(project_path)
            ))
        except _base.AcceptedRiskSixUniverseOrderQcProjectionError as exc:
            raise SixUniverseTiltQcProjectionError(str(exc)) from exc
    try:
        files.append(_base._source_file(
            _base.MAIN_PROJECT_PATH,
            _tilt_main_source(activation, profile),
        ))
    except _base.AcceptedRiskSixUniverseOrderQcProjectionError as exc:
        raise SixUniverseTiltQcProjectionError(str(exc)) from exc
    files.sort(key=lambda item: item.project_path)
    if (
        len(files) != 16
        or len({item.project_path for item in files}) != len(files)
        or any(
            len(item.source_bytes.decode("ascii"))
            > _base.MAXIMUM_QC_SOURCE_CHARACTERS
            for item in files
        )
    ):
        _error("tilt bridge source closure or QC per-file bound changed")
    total = sum(item.byte_count for item in files)
    if total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES:
        _error("tilt bridge source set exceeded its reviewed total bound")

    semantic = {
        key: value for key, value in baseline.to_record().items()
        if key not in ("projection_id", "projection_sha256")
    }
    semantic.update({
        "schema": PROJECTION_SCHEMA,
        "role": _tilt_targets.TILT_ROLE,
        "variant": _tilt_runtime.TILT_VARIANT,
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "source_files": [item.to_record() for item in files],
        "total_source_byte_count": total,
    })
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    value = dataclasses.replace(
        baseline,
        schema=PROJECTION_SCHEMA,
        projection_id="arv2-six-universe-order-tilt-qc-projection-" + digest[:24],
        projection_sha256=digest,
        role=_tilt_targets.TILT_ROLE,
        variant=_tilt_runtime.TILT_VARIANT,
        profile_id=profile["profile_id"],
        profile_sha256=profile["profile_sha256"],
        source_files=tuple(files),
        total_source_byte_count=total,
    )
    if {
        key: item for key, item in value.to_record().items()
        if key not in ("projection_id", "projection_sha256")
    } != semantic:
        _error("tilt bridge projection did not self-authenticate")
    return value


__all__ = (
    "PINNED_BASE_MATCHED_PROFILE_SHA256",
    "PINNED_BASE_MATCHED_PROJECTION_SHA256",
    "PINNED_TILT_PROFILE_SHA256",
    "PROJECTION_SCHEMA",
    "SixUniverseTiltQcProjectionError",
    "build_accepted_risk_six_universe_order_tilt_qc_projection",
)
