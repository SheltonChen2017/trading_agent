"""Separate QC source projection for the R181 A3 buying-power admission bridge.

The existing cap-90 source is authenticated first.  Only the entry point and
one bridge runtime are added; R181 A2 and the frozen R182 source remain
byte-identical.  This module performs no network or result access.
"""

import dataclasses
import hashlib
from pathlib import Path

from . import accepted_risk_six_universe_order_qc_projection as _base
from . import accepted_risk_six_universe_order_qc_runtime as _base_runtime
from . import accepted_risk_six_universe_order_targets as _targets
from . import accepted_risk_six_universe_order_bridge_qc_runtime as _bridge


class SixUniverseBridgeQcProjectionError(ValueError):
    """A bridge source, profile, package, or capability identity changed."""


PROJECTION_SCHEMA = "arv2-six-universe-order-qc-projection-bridge-v1"
PINNED_BASE_PROJECTION_SHA256S = {
    _targets.ROLE_SIGNAL: (
        "b68661ec2f90f98eb47e09242b8b9d4cd8ed21101667f355afba0a4a48461c29"
    ),
    _targets.ROLE_MATCHED: (
        "f72c05cc2168262f2c298ad934d87cc6e4005802d2ff0bdee7a472e18be7341f"
    ),
    _targets.ROLE_SIX_ETF_BASKET: (
        "3df9bfe2dd05c47c34b52de0b544aeaa68a3ee7f2ffec65437ac020d07ee41d7"
    ),
}
PINNED_BASE_PROFILE_SHA256S = {
    _targets.ROLE_SIGNAL: (
        "d27c558b71d20694e803a244e89f3feb79ba5084971c8d6d8eefa7cf8ecf09f0"
    ),
    _targets.ROLE_MATCHED: (
        "ab8e53adb828c5bb8cad23150d87f1ab87964887dc45e2e783a822cd754ce57a"
    ),
    _targets.ROLE_SIX_ETF_BASKET: (
        "8d6f58c2a4ac427c7f81487d5ad00c901b4822a530bb0b6e9d729160819b4c1c"
    ),
}
PINNED_BRIDGE_RUNTIME_SHA256 = (
    "60b0e300393c1356e21de310fdfce1ff029632d77e6bf62efd7bb053de55b5ab"
)
PINNED_BRIDGE_PROFILE_SHA256S = {
    _targets.ROLE_SIGNAL: (
        "9e1b93c3fc5fca0cd3154f8c8270fd10cdb2acc67742e9712aafb5682fbed031"
    ),
    _targets.ROLE_MATCHED: (
        "b419d3f2b149a1509ef09bd0a5bf607bea8c25a3363cbc8a9dc04a40910f9c0c"
    ),
    _targets.ROLE_SIX_ETF_BASKET: (
        "7e4a108e378f59f5927225c919b2a7e9bae4ed3de6cfd89a31a8a416e3a00349"
    ),
}
BRIDGE_RUNTIME_PATH = "accepted_risk_six_universe_order_bridge_qc_runtime.py"


def _error(message):
    raise SixUniverseBridgeQcProjectionError(message)


def _read_exact_bridge_runtime():
    if (
        type(PINNED_BRIDGE_RUNTIME_SHA256) is not str
        or len(PINNED_BRIDGE_RUNTIME_SHA256) != 64
    ):
        _error("bridge runtime source pin is unavailable")
    try:
        source = (Path(__file__).resolve().parent / BRIDGE_RUNTIME_PATH).read_bytes()
    except OSError as exc:
        raise SixUniverseBridgeQcProjectionError(
            "bridge projected runtime is unavailable"
        ) from exc
    if hashlib.sha256(source).hexdigest() != PINNED_BRIDGE_RUNTIME_SHA256:
        _error("bridge projected runtime changed from its exact pin")
    return source


def _bridge_main_source(activation, profile):
    if (
        type(profile) is not dict
        or profile.get("role") not in _targets.ROLES
        or profile.get("profile_sha256")
        != PINNED_BRIDGE_PROFILE_SHA256S[profile["role"]]
    ):
        _error("bridge main profile changed")
    original = _base._main_source(
        activation=activation,
        profile=profile,
        variant=_bridge.BRIDGE_VARIANT,
    ).decode("ascii")
    substitutions = (
        (
            "from accepted_risk_six_universe_order_qc_runtime import (\n"
            "    AcceptedRiskSixUniverseOrderQcDriver,\n"
            "    STARTING_CASH,\n"
            ")\n",
            "from accepted_risk_six_universe_order_qc_runtime import STARTING_CASH\n"
            "from accepted_risk_six_universe_order_bridge_qc_runtime import (\n"
            "    AcceptedRiskSixUniverseOrderBridgeQcDriver,\n"
            ")\n",
        ),
        (
            "class ARV2SixUniverseOrderAlgorithm(QCAlgorithm):",
            "class ARV2SixUniverseOrderBridgeAlgorithm(QCAlgorithm):",
        ),
        (
            "self._arv2_driver = AcceptedRiskSixUniverseOrderQcDriver(",
            "self._arv2_driver = AcceptedRiskSixUniverseOrderBridgeQcDriver(",
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
            _error("bridge main source lost its exact insertion point")
        original = original.replace(old, new, 1)
    if (
        original.count("self.universe_settings.leverage = 2") != 1
        or original.count("                leverage=2,\n") != 1
        or "                leverage=1,\n" in original
    ):
        _error("bridge main admission leverage changed")
    return original.encode("ascii")


def build_accepted_risk_six_universe_order_bridge_qc_projection(
    delta_package, *, role,
):
    """Build a role-bound, backtest-only A3/R182/R183 bridge source set."""
    if type(role) is not str or role not in _targets.ROLES:
        _error("bridge projection role is not frozen")
    try:
        baseline = _base.build_accepted_risk_six_universe_order_qc_projection(
            delta_package,
            role=role,
            variant=_base_runtime.CAP90_VARIANT,
        )
    except _base.AcceptedRiskSixUniverseOrderQcProjectionError as exc:
        raise SixUniverseBridgeQcProjectionError(str(exc)) from exc
    if (
        baseline.projection_sha256 != PINNED_BASE_PROJECTION_SHA256S[role]
        or baseline.profile_sha256 != PINNED_BASE_PROFILE_SHA256S[role]
        or baseline.role != role
        or baseline.variant != _base_runtime.CAP90_VARIANT
        or len(baseline.source_files) != 13
    ):
        _error("reviewed cap-90 source projection changed")
    try:
        profile = _bridge.require_bridge_profile(role)
    except _base_runtime.AcceptedRiskSixUniverseOrderQcRuntimeError as exc:
        raise SixUniverseBridgeQcProjectionError(str(exc)) from exc
    if (
        type(profile) is not dict
        or profile.get("role") != role
        or profile.get("schema") != _bridge.BRIDGE_PROFILE_SCHEMA
        or type(PINNED_BRIDGE_PROFILE_SHA256S[role]) is not str
        or len(PINNED_BRIDGE_PROFILE_SHA256S[role]) != 64
        or profile.get("profile_sha256")
        != PINNED_BRIDGE_PROFILE_SHA256S[role]
    ):
        _error("bridge role profile changed")
    activation = delta_package.package.upload_objects[-1]
    files = [
        item for item in baseline.source_files
        if item.project_path != _base.MAIN_PROJECT_PATH
    ]
    try:
        files.extend((
            _base._source_file(
                BRIDGE_RUNTIME_PATH,
                _read_exact_bridge_runtime(),
            ),
            _base._source_file(
                _base.MAIN_PROJECT_PATH,
                _bridge_main_source(activation, profile),
            ),
        ))
    except _base.AcceptedRiskSixUniverseOrderQcProjectionError as exc:
        raise SixUniverseBridgeQcProjectionError(str(exc)) from exc
    files.sort(key=lambda item: item.project_path)
    if (
        len(files) != 14
        or len({item.project_path for item in files}) != 14
        or any(
            len(item.source_bytes.decode("ascii"))
            > _base.MAXIMUM_QC_SOURCE_CHARACTERS
            for item in files
        )
    ):
        _error("bridge source closure or QC per-file bound changed")
    total = sum(item.byte_count for item in files)
    if total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES:
        _error("bridge source set exceeded its reviewed total bound")
    semantic = {
        key: value for key, value in baseline.to_record().items()
        if key not in ("projection_id", "projection_sha256")
    }
    semantic.update({
        "schema": PROJECTION_SCHEMA,
        "variant": _bridge.BRIDGE_VARIANT,
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "source_files": [item.to_record() for item in files],
        "total_source_byte_count": total,
    })
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    value = dataclasses.replace(
        baseline,
        schema=PROJECTION_SCHEMA,
        projection_id="arv2-six-universe-order-bridge-qc-projection-" + digest[:24],
        projection_sha256=digest,
        variant=_bridge.BRIDGE_VARIANT,
        profile_id=profile["profile_id"],
        profile_sha256=profile["profile_sha256"],
        source_files=tuple(files),
        total_source_byte_count=total,
    )
    if {
        key: item for key, item in value.to_record().items()
        if key not in ("projection_id", "projection_sha256")
    } != semantic:
        _error("bridge projection did not self-authenticate")
    return value


__all__ = (
    "BRIDGE_RUNTIME_PATH",
    "PINNED_BASE_PROFILE_SHA256S",
    "PINNED_BASE_PROJECTION_SHA256S",
    "PINNED_BRIDGE_PROFILE_SHA256S",
    "PINNED_BRIDGE_RUNTIME_SHA256",
    "PROJECTION_SCHEMA",
    "SixUniverseBridgeQcProjectionError",
    "build_accepted_risk_six_universe_order_bridge_qc_projection",
)
