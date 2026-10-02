"""Separate matched-stock revision tilt under the same 2x QC admission bridge.

The bridge changes buying-power admission for simultaneous pre-open MOO
sells/buys. It does not change the 98% long-only target. This candidate
retains the bridge's cash, gross-exposure, order, and target-tracking gates.
"""

import json

try:
    import accepted_risk_six_universe_order_qc_runtime as _base
    import accepted_risk_six_universe_order_bridge_qc_runtime as _bridge
    import accepted_risk_six_universe_order_tilt_targets as _tilt
    import accepted_risk_six_universe_order_targets as _targets
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_order_qc_runtime as _base,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_order_bridge_qc_runtime as _bridge,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_order_tilt_targets as _tilt,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_order_targets as _targets,
    )


class AcceptedRiskSixUniverseOrderTiltQcRuntimeError(
    _bridge.AcceptedRiskSixUniverseOrderBridgeQcRuntimeError
):
    """The role, exact source lineage, or tilt target path was refused."""


TILT_VARIANT = "cap90_matched_revision_tilt_admission_bridge_v1"
TILT_PROFILE_SCHEMA = "arv2-six-universe-order-tilt-bridge-profile-v1"
TILT_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt-bridge-summary-v1"
TILT_META_SCHEMA = _base.META_SCHEMA
BASELINE_MATCHED_PROFILE_SHA256 = (
    "b419d3f2b149a1509ef09bd0a5bf607bea8c25a3363cbc8a9dc04a40910f9c0c"
)
META_STATISTIC_NAME = _bridge.META_STATISTIC_NAME
AGGREGATES_STATISTIC_NAME = _bridge.AGGREGATES_STATISTIC_NAME
MAXIMUM_STATISTIC_BYTES = _bridge.MAXIMUM_STATISTIC_BYTES


def _error(message):
    raise AcceptedRiskSixUniverseOrderTiltQcRuntimeError(message)


def require_tilt_profile():
    """Pin this role to the bridge matched economics and separate tilt rule."""
    baseline = _bridge.require_bridge_profile(_targets.ROLE_MATCHED)
    if baseline["profile_sha256"] != BASELINE_MATCHED_PROFILE_SHA256:
        _error("tilt bridge matched profile changed")
    seed = {
        key: value for key, value in baseline.items()
        if key != "profile_sha256"
    }
    seed.update({
        "schema": TILT_PROFILE_SCHEMA,
        "profile_id": "arv2-six-universe-order-matched-revision-tilt-bridge-v1",
        "role": _tilt.TILT_ROLE,
        "matched_baseline_profile_sha256": BASELINE_MATCHED_PROFILE_SHA256,
        "target_path_schema": _tilt.TARGET_PATH_SCHEMA,
        "decision_target_schema": _tilt.DECISION_TARGET_SCHEMA,
        "tilt_rank_rule_id": _tilt.TILT_RANK_RULE_ID,
        "maximum_stock_weight_change_fraction": "0.20",
        "weight_transfer_quantum": "0.000000000000000000000000000001",
    })
    return json.loads(_base._canonical({
        **seed,
        "profile_sha256": _base._sha(seed),
    }).decode("ascii"))


def expected_tilt_custom_statistic_names():
    require_tilt_profile()
    return _bridge.expected_bridge_custom_statistic_names(
        _targets.ROLE_MATCHED
    )


class AcceptedRiskSixUniverseOrderTiltQcDriver(
    _bridge.AcceptedRiskSixUniverseOrderBridgeQcDriver
):
    """Run the exact cap-selected stock identities with bounded weight tilt."""

    def __init__(self, algorithm, *, role, variant=TILT_VARIANT, **kwargs):
        if (
            type(role) is not str
            or role != _tilt.TILT_ROLE
            or type(variant) is not str
            or variant != TILT_VARIANT
        ):
            _error("tilt runtime role or variant is not frozen")
        super().__init__(
            algorithm,
            role=_targets.ROLE_MATCHED,
            variant=_bridge.BRIDGE_VARIANT,
            **kwargs,
        )
        self._tilt_initialized = False
        self._tilt_builder = None

    def _bridge_expected_profile(self):
        return require_tilt_profile()

    def _bridge_expected_builder_type(self):
        return _tilt.MatchedRevisionTiltTargetBuilder

    def _bridge_summary_schema(self):
        return TILT_SUMMARY_SCHEMA

    def _bridge_expected_statistic_names(self):
        return expected_tilt_custom_statistic_names()

    def initialize(self):
        if self._tilt_initialized:
            _error("tilt runtime initialized more than once")
        # Base setup needs the matched builder while it authenticates the
        # immutable input. The bridge configures every ETF with 2x during
        # that setup; switch to the tilt builder before any decision callback.
        _base.AcceptedRiskSixUniverseOrderQcDriver.initialize(self)
        try:
            builder = _tilt.MatchedRevisionTiltTargetBuilder(
                self._package.evaluator_input
            )
            if type(builder) is not _tilt.MatchedRevisionTiltTargetBuilder:
                _error("tilt target builder type changed")
        except Exception:
            self._initialized = False
            self._completed = True
            raise
        profile = require_tilt_profile()
        self._target_builder = builder
        self._tilt_builder = builder
        self._role = _tilt.TILT_ROLE
        self._profile = profile
        self._bridge_role = _tilt.TILT_ROLE
        self._bridge_profile = profile
        self._bridge_builder = builder
        self._bridge_cash_observations = {}
        self._bridge_event_cash_minimum = None
        self._bridge_event_cash_count = 0
        self._bridge_initialized = True
        self._tilt_initialized = True
        self._bridge_authority()
        return True

    def _require_initialized(self):
        super()._require_initialized()
        if self._tilt_initialized is not True:
            _error("tilt runtime did not finish initialization")

    def _aggregate(self):
        self._require_initialized()
        path = self._target_builder.complete_path()
        if type(path) is not _tilt.TiltTargetPath:
            _error("tilt target path type changed")
        path.to_record()
        if (
            path.role != _tilt.TILT_ROLE
            or type(path.baseline_target_path_sha256) is not str
            or len(path.baseline_target_path_sha256) != 64
            or path.gate_profile_sha256 != self._profile["gate_profile_sha256"]
            or path.evaluation_profile_sha256
            != self._profile["evaluation_profile_sha256"]
        ):
            _error("tilt path or matched baseline identity changed")
        aggregate = super()._aggregate()
        if (
            aggregate["schema"] != TILT_SUMMARY_SCHEMA
            or aggregate["role"] != _tilt.TILT_ROLE
            or aggregate["profile_sha256"] != self._profile["profile_sha256"]
            or aggregate["target_path_sha256"] != path.target_path_sha256
        ):
            _error("tilt bridge aggregate identity changed")
        aggregate.update({
            "matched_baseline_profile_sha256": BASELINE_MATCHED_PROFILE_SHA256,
            "matched_baseline_target_path_sha256": (
                path.baseline_target_path_sha256
            ),
            "tilt_rank_rule_id": _tilt.TILT_RANK_RULE_ID,
            "maximum_stock_weight_change_fraction": "0.20",
        })
        return aggregate


__all__ = (
    "AGGREGATES_STATISTIC_NAME",
    "AcceptedRiskSixUniverseOrderTiltQcDriver",
    "AcceptedRiskSixUniverseOrderTiltQcRuntimeError",
    "BASELINE_MATCHED_PROFILE_SHA256",
    "MAXIMUM_STATISTIC_BYTES",
    "META_STATISTIC_NAME",
    "TILT_META_SCHEMA",
    "TILT_PROFILE_SCHEMA",
    "TILT_SUMMARY_SCHEMA",
    "TILT_VARIANT",
    "expected_tilt_custom_statistic_names",
    "require_tilt_profile",
)
