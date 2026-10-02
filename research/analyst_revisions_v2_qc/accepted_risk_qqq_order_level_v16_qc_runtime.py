"""V16 successor for exact mean exposure complement reporting.

V15 remains byte-identical.  V16 preserves its universe, score, tilt,
execution, fee, forced-exit, delisted-target retirement, and terminal-account
policies.  It changes only the aggregate representation of mean cash weight:
the already-emitted mean gross exposure is authoritative and mean cash weight
is its exact unit complement under the same bounded local Decimal discipline
used by V14's proxy complements.  This removes a producer/consumer mismatch
caused by independently rounded means without changing an order or path.
"""

from decimal import Decimal, DecimalException

try:
    import accepted_risk_qqq_order_level_v15_qc_runtime as _v15
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_qqq_order_level_v15_qc_runtime as _v15,
    )


_v14 = _v15._v14
_v13 = _v15._v13
_base = _v15._base
AcceptedRiskQqqOrderLevelQcRuntimeError = (
    _v15.AcceptedRiskQqqOrderLevelQcRuntimeError
)
_Refusal = AcceptedRiskQqqOrderLevelQcRuntimeError


EXPOSURE_PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v16"
EXPOSURE_SUMMARY_SCHEMA = "arv2-qqq-order-level-tilt-summary-v11"
EXPOSURE_PROFILE_IDS = tuple(
    "arv2-qqq-order-level-tilt-" + str(year) + "-cutoff-v16"
    for year in (2025, 2026)
)
(
    EXPOSURE_PROFILE_2025_ID,
    EXPOSURE_PROFILE_2026_ID,
) = EXPOSURE_PROFILE_IDS

MEAN_EXPOSURE_COMPLEMENT_POLICY = (
    "emitted_mean_cash_weight_is_exact_local_32768_digit_unit_complement_"
    "of_emitted_mean_gross_exposure"
)

STARTING_CASH = _v15.STARTING_CASH
META_STATISTIC_NAME = _v15.META_STATISTIC_NAME
AGGREGATES_STATISTIC_NAME = _v15.AGGREGATES_STATISTIC_NAME

_V15_PROFILE_BY_V16 = {
    EXPOSURE_PROFILE_2025_ID: _v15.ACCOUNT_PROFILE_2025_ID,
    EXPOSURE_PROFILE_2026_ID: _v15.ACCOUNT_PROFILE_2026_ID,
}


def _v16_profile(profile_id):
    v15_id = _V15_PROFILE_BY_V16.get(profile_id)
    if v15_id is None:
        raise _Refusal(
            "QQQ order-level V16 profile is not an exact fixed profile"
        )
    record = _v15.require_qqq_order_level_profile(v15_id)
    record.pop("profile_sha256")
    record.update({
        "schema": EXPOSURE_PROFILE_SCHEMA,
        "profile_id": profile_id,
        "mean_exposure_complement_policy": (
            MEAN_EXPOSURE_COMPLEMENT_POLICY
        ),
    })
    return {**record, "profile_sha256": _base._sha(record)}


_PROFILES = {
    profile_id: _v16_profile(profile_id)
    for profile_id in EXPOSURE_PROFILE_IDS
}


def require_qqq_order_level_profile(profile_id):
    if type(profile_id) is not str or profile_id not in _PROFILES:
        raise _Refusal(
            "QQQ order-level V16 profile is not an exact fixed profile"
        )
    return _base.json.loads(
        _base._canonical(_PROFILES[profile_id]).decode("ascii")
    )


def expected_custom_summary_statistic_names(profile_id):
    require_qqq_order_level_profile(profile_id)
    return tuple(sorted((META_STATISTIC_NAME, AGGREGATES_STATISTIC_NAME)))


def _exact_mean_cash_complement(summary):
    """Replace only the predecessor's independently rounded cash mean."""

    if type(summary) is not dict:
        raise _Refusal("order-level V16 aggregate is not an exact dict")
    if summary.get("schema") != _v15.ACCOUNT_SUMMARY_SCHEMA:
        raise _Refusal("order-level V16 predecessor schema changed")
    gross_text = summary.get("mean_gross_exposure")
    prior_cash_text = summary.get("mean_cash_weight")
    if type(gross_text) is not str or type(prior_cash_text) is not str:
        raise _Refusal(
            "order-level V16 mean exposure source is not exact decimal text"
        )
    try:
        gross = Decimal(gross_text)
        prior_cash = Decimal(prior_cash_text)
    except (DecimalException, ValueError) as exc:
        raise _Refusal(
            "order-level V16 mean exposure source is not exact decimal text"
        ) from exc
    if (
        not gross.is_finite()
        or not prior_cash.is_finite()
        or gross < 0
        or gross > 1
        or prior_cash < 0
        or prior_cash > 1
    ):
        raise _Refusal(
            "order-level V16 mean exposure source is outside zero and one"
        )
    result = dict(summary)
    result.update({
        "schema": EXPOSURE_SUMMARY_SCHEMA,
        "mean_cash_weight": _v14._exact_unit_complement_text(gross_text),
    })
    return result


class AcceptedRiskQqqOrderLevelV16QcRuntime(
    _v15.AcceptedRiskQqqOrderLevelV15QcRuntime
):
    """Run V15 with an exact emitted mean exposure complement."""

    def __init__(self, algorithm, *, profile_id, **kwargs):
        profile = require_qqq_order_level_profile(profile_id)
        super().__init__(
            algorithm,
            profile_id=_V15_PROFILE_BY_V16[profile_id],
            **kwargs,
        )
        self._profile = profile

    def _aggregate_record(self):
        return _exact_mean_cash_complement(super()._aggregate_record())

    def on_end_of_algorithm(self):
        # V15's callback names its own exact profile family.  Repeat that
        # callback with V16's profile/name gate; every state transition and
        # aggregate operation remains inherited.
        if not self._initialized or self._completed:
            raise _Refusal(
                "order-level end callback escaped runtime state"
            )
        if self._pending_preopen is not None:
            raise _Refusal(
                "order-level pending preopen submission remained at end"
            )
        if not _v13._end_callback_clock_is_allowed(self._algorithm.time):
            raise _Refusal(
                "order-level backtest ended outside the exact final clock"
            )
        self._close_open_plan()
        if self._decision_count != len(self._decision_sessions):
            raise _Refusal(
                "order-level decision schedule did not complete"
            )
        self._replace_terminal_account_observation()
        aggregates = self._aggregate_record()
        aggregates_sha256 = _base._sha(aggregates)
        meta = {
            "schema": "arv2-qqq-order-level-tilt-runtime-meta-v3",
            "profile_id": self._profile["profile_id"],
            "profile_sha256": self._profile["profile_sha256"],
            "package_id": self._package.package_id,
            "package_sha256": self._package.package_sha256,
            "activation_manifest_sha256": (
                self._package.activation_manifest_sha256
            ),
            "symbol_resolution_id": self._resolution.resolution_id,
            "symbol_resolution_sha256": self._resolution.resolution_sha256,
            "score_source_view_id": _base._score.PRIMARY_SOURCE_VIEW_ID,
            "aggregates_sha256": aggregates_sha256,
            "result_transport": "aggregate_only_custom_summary_statistics",
            "backtest_only": True,
            "simulated_order_submission": True,
            "live_orders": False,
            "paper_orders": False,
            "funded_orders": False,
            "deployment": False,
            "trading": False,
        }
        statistics = {
            META_STATISTIC_NAME: _base._canonical(meta).decode("ascii"),
            AGGREGATES_STATISTIC_NAME: (
                _base._canonical(aggregates).decode("ascii")
            ),
        }
        if (
            tuple(sorted(statistics))
            != expected_custom_summary_statistic_names(
                self._profile["profile_id"]
            )
            or any(
                len(key) > 64
                or len(value.encode("ascii"))
                > _base.MAXIMUM_STATISTIC_BYTES
                for key, value in statistics.items()
            )
        ):
            raise _Refusal(
                "order-level aggregate transport exceeded its exact bound"
            )
        for key, value in sorted(statistics.items()):
            self._algorithm.set_summary_statistic(key, value)
        self._completed = True


__all__ = (
    "AGGREGATES_STATISTIC_NAME",
    "AcceptedRiskQqqOrderLevelQcRuntimeError",
    "AcceptedRiskQqqOrderLevelV16QcRuntime",
    "EXPOSURE_PROFILE_2025_ID",
    "EXPOSURE_PROFILE_2026_ID",
    "EXPOSURE_PROFILE_IDS",
    "EXPOSURE_PROFILE_SCHEMA",
    "EXPOSURE_SUMMARY_SCHEMA",
    "MEAN_EXPOSURE_COMPLEMENT_POLICY",
    "META_STATISTIC_NAME",
    "STARTING_CASH",
    "expected_custom_summary_statistic_names",
    "require_qqq_order_level_profile",
)
