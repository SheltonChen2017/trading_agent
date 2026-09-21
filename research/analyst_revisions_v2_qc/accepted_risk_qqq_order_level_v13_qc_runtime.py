"""V13-only wrapper for the exact QuantConnect end-callback clock rollover.

V12 remains byte-identical.  This module maps each V13 profile to its V12
execution behavior and changes only the end-callback clock acceptance: the
callback may arrive on the final execution session, as before, or at exact
midnight on the immediately following calendar day.
"""

from datetime import date, timedelta

try:
    import accepted_risk_qqq_order_level_v12_qc_runtime as _v12
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_qqq_order_level_v12_qc_runtime as _v12,
    )


_base = _v12._base
AcceptedRiskQqqOrderLevelQcRuntimeError = (
    _v12.AcceptedRiskQqqOrderLevelQcRuntimeError
)
_Refusal = AcceptedRiskQqqOrderLevelQcRuntimeError


ROLLOVER_PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v13"
ROLLOVER_PROFILE_IDS = tuple(
    "arv2-qqq-order-level-tilt-" + str(year) + "-cutoff-v13"
    for year in (2025, 2026)
)
(
    ROLLOVER_PROFILE_2025_ID,
    ROLLOVER_PROFILE_2026_ID,
) = ROLLOVER_PROFILE_IDS

STARTING_CASH = _v12.STARTING_CASH
META_STATISTIC_NAME = _v12.META_STATISTIC_NAME
AGGREGATES_STATISTIC_NAME = _v12.AGGREGATES_STATISTIC_NAME

_V12_PROFILE_BY_V13 = {
    ROLLOVER_PROFILE_2025_ID: _v12.FORCED_EXIT_PROFILE_2025_ID,
    ROLLOVER_PROFILE_2026_ID: _v12.FORCED_EXIT_PROFILE_2026_ID,
}
_NEXT_CALENDAR_DAY = (
    date.fromisoformat(_base.FINAL_EXECUTION_SESSION) + timedelta(days=1)
).isoformat()


def _v13_profile(profile_id):
    v12_id = _V12_PROFILE_BY_V13.get(profile_id)
    if v12_id is None:
        raise _Refusal(
            "QQQ order-level V13 profile is not an exact fixed profile"
        )
    record = _v12.require_qqq_order_level_profile(v12_id)
    record.pop("profile_sha256")
    record.update({
        "schema": ROLLOVER_PROFILE_SCHEMA,
        "profile_id": profile_id,
        "qc_end_callback_clock_policy": (
            "final_execution_session_or_exact_next_calendar_day_midnight"
        ),
    })
    return {**record, "profile_sha256": _base._sha(record)}


_PROFILES = {
    profile_id: _v13_profile(profile_id)
    for profile_id in ROLLOVER_PROFILE_IDS
}


def require_qqq_order_level_profile(profile_id):
    if type(profile_id) is not str or profile_id not in _PROFILES:
        raise _Refusal(
            "QQQ order-level V13 profile is not an exact fixed profile"
        )
    return _base.json.loads(
        _base._canonical(_PROFILES[profile_id]).decode("ascii")
    )


def expected_custom_summary_statistic_names(profile_id):
    require_qqq_order_level_profile(profile_id)
    return tuple(sorted((META_STATISTIC_NAME, AGGREGATES_STATISTIC_NAME)))


def _end_callback_clock_is_allowed(value):
    try:
        callback_date = value.date().isoformat()
    except (AttributeError, TypeError, ValueError):
        return False
    if callback_date == _base.FINAL_EXECUTION_SESSION:
        return True
    if callback_date != _NEXT_CALENDAR_DAY:
        return False
    try:
        return (
            value.hour == 0
            and value.minute == 0
            and value.second == 0
            and value.microsecond == 0
        )
    except (AttributeError, TypeError, ValueError):
        return False


class AcceptedRiskQqqOrderLevelV13QcRuntime(
    _v12.AcceptedRiskQqqOrderLevelV12QcRuntime
):
    """Run V12 behavior with one exact end-callback rollover allowance."""

    def __init__(self, algorithm, *, profile_id, **kwargs):
        profile = require_qqq_order_level_profile(profile_id)
        super().__init__(
            algorithm,
            profile_id=_V12_PROFILE_BY_V13[profile_id],
            **kwargs,
        )
        self._profile = profile

    def on_end_of_algorithm(self):
        if not self._initialized or self._completed:
            raise _Refusal(
                "order-level end callback escaped runtime state"
            )
        if self._pending_preopen is not None:
            raise _Refusal(
                "order-level pending preopen submission remained at end"
            )
        if not _end_callback_clock_is_allowed(self._algorithm.time):
            raise _Refusal(
                "order-level backtest ended outside the exact final clock"
            )
        self._close_open_plan()
        if self._decision_count != len(self._decision_sessions):
            raise _Refusal(
                "order-level decision schedule did not complete"
            )
        aggregates = self._aggregate_record()
        aggregates_sha256 = _base._sha(aggregates)
        meta = {
            "schema": "arv2-qqq-order-level-tilt-runtime-meta-v2",
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
    "AcceptedRiskQqqOrderLevelV13QcRuntime",
    "META_STATISTIC_NAME",
    "ROLLOVER_PROFILE_2025_ID",
    "ROLLOVER_PROFILE_2026_ID",
    "ROLLOVER_PROFILE_IDS",
    "ROLLOVER_PROFILE_SCHEMA",
    "STARTING_CASH",
    "expected_custom_summary_statistic_names",
    "require_qqq_order_level_profile",
)
