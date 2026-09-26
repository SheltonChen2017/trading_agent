"""V17 successor: fail-closed decision skips instead of stale-input trading.

V16 remains byte-identical.  V17 preserves its universe, score, tilt,
execution, fee, forced-exit, delisted-target retirement, terminal-account,
and mean-exposure-complement policies.  It changes only what happens when
one of three already-refused input conditions is met at a single decision:

1. the latest strictly-prior point-in-time QQQ constituent snapshot is not
   the immediately prior authenticated session (V16 refuses the whole run);
2. that snapshot's positive constituent weight total is outside the fixed
   0.95 to 1.05 acceptance band (V16 refuses the whole run); or
3. the frozen prior-close plan cannot execute at the next preopen because
   overnight holdings changed after the decision (V16 refuses the whole run).

V17 never trades on the affected input.  The decision (cases 1 and 2) or the
frozen execution (case 3) is skipped without orders, holdings are carried
unchanged, the skip is counted and recorded with its exact cause, the run
continues, and the aggregate's own ``run_valid`` flag is false whenever any
skip occurred.  This is the project's standing rule that stale, missing or
corrupt input is equivalent to no input: no snapshot is aged past its exact
policy, no weight is rescaled, and no plan is re-based from a rounded
corporate-action factor.  Every other V16 refusal is unchanged and still ends
the run, and the same session-age, band, SID-resolution and coverage checks
still run in their inherited order for every executed decision.

The skip conditions are detected by explicit pre-checks that reuse the
inherited helpers and the inherited constants, never by catching a refusal;
the inherited benchmark core and preopen guard therefore remain the
fail-closed verifiers behind every executed decision.
"""

from datetime import datetime, timedelta
from decimal import Decimal, localcontext

try:
    import accepted_risk_qqq_order_level_v16_qc_runtime as _v16
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_qqq_order_level_v16_qc_runtime as _v16,
    )


_v15 = _v16._v15
_v14 = _v16._v14
_v13 = _v16._v13
_base = _v16._base
AcceptedRiskQqqOrderLevelQcRuntimeError = (
    _v16.AcceptedRiskQqqOrderLevelQcRuntimeError
)
_Refusal = AcceptedRiskQqqOrderLevelQcRuntimeError


SKIP_PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v17"
SKIP_SUMMARY_SCHEMA = "arv2-qqq-order-level-tilt-summary-v12"
SKIP_PROFILE_IDS = tuple(
    "arv2-qqq-order-level-tilt-" + str(year) + "-cutoff-v17"
    for year in (2025, 2026)
)
(
    SKIP_PROFILE_2025_ID,
    SKIP_PROFILE_2026_ID,
) = SKIP_PROFILE_IDS

DECISION_SKIP_POLICY = (
    "skip_without_orders_and_carry_holdings_when_the_PIT_QQQ_constituent_"
    "snapshot_is_not_exact_age_1_or_its_positive_weight_total_is_outside_"
    "the_fixed_band_or_frozen_preopen_holdings_changed_overnight_then_count_"
    "and_record_every_skip_and_emit_run_valid_false"
)
STALE_SNAPSHOT_SKIP_REASON = (
    "pit_constituent_snapshot_not_immediately_prior_authenticated_session"
)
WEIGHT_TOTAL_SKIP_REASON = (
    "pit_positive_constituent_weight_total_outside_fixed_band"
)
OVERNIGHT_DRIFT_SKIP_REASON = "frozen_preopen_holdings_changed_after_decision"
SKIP_REASONS = (
    STALE_SNAPSHOT_SKIP_REASON,
    WEIGHT_TOTAL_SKIP_REASON,
    OVERNIGHT_DRIFT_SKIP_REASON,
)
SKIPPED_DECISION_EVIDENCE_SCHEMA = (
    "arv2-order-level-skipped-decision-evidence-v1"
)
SKIPPED_DECISION_PATH_SCHEMA = "arv2-order-level-skipped-decision-path-v1"
DRIFTED_SECURITY_PATH_SCHEMA = "arv2-order-level-drifted-security-path-v1"
MAXIMUM_RETAINED_SKIPPED_DECISIONS = 4
_REBALANCE_ID_PREFIX = "arv2-qqq-order-"

STARTING_CASH = _v16.STARTING_CASH
META_STATISTIC_NAME = _v16.META_STATISTIC_NAME
AGGREGATES_STATISTIC_NAME = _v16.AGGREGATES_STATISTIC_NAME

_V16_PROFILE_BY_V17 = {
    SKIP_PROFILE_2025_ID: _v16.EXPOSURE_PROFILE_2025_ID,
    SKIP_PROFILE_2026_ID: _v16.EXPOSURE_PROFILE_2026_ID,
}


def _v17_profile(profile_id):
    v16_id = _V16_PROFILE_BY_V17.get(profile_id)
    if v16_id is None:
        raise _Refusal(
            "QQQ order-level V17 profile is not an exact fixed profile"
        )
    record = _v16.require_qqq_order_level_profile(v16_id)
    record.pop("profile_sha256")
    record.update({
        "schema": SKIP_PROFILE_SCHEMA,
        "profile_id": profile_id,
        "decision_skip_policy": DECISION_SKIP_POLICY,
        "maximum_retained_skipped_decisions": (
            MAXIMUM_RETAINED_SKIPPED_DECISIONS
        ),
    })
    return {**record, "profile_sha256": _base._sha(record)}


_PROFILES = {
    profile_id: _v17_profile(profile_id)
    for profile_id in SKIP_PROFILE_IDS
}


def require_qqq_order_level_profile(profile_id):
    if type(profile_id) is not str or profile_id not in _PROFILES:
        raise _Refusal(
            "QQQ order-level V17 profile is not an exact fixed profile"
        )
    return _base.json.loads(
        _base._canonical(_PROFILES[profile_id]).decode("ascii")
    )


def expected_custom_summary_statistic_names(profile_id):
    require_qqq_order_level_profile(profile_id)
    return tuple(sorted((META_STATISTIC_NAME, AGGREGATES_STATISTIC_NAME)))


def _positive_weight_total(constituent_weights, proxy_mode):
    """Sum served positive weights exactly as the inherited benchmark core.

    This is a routing pre-check, not a second authority: the inherited core
    still applies the same band to the same map for every executed decision,
    so a disagreement between the two sums can only add a refusal.
    """

    with localcontext() as context:
        if proxy_mode:
            context.prec = 100
        return sum(
            (
                constituent_weights[sid]
                for sid in (
                    sorted(constituent_weights) if proxy_mode
                    else constituent_weights
                )
            ),
            Decimal(0),
        )


def _decision_session_of(plan, decision_set):
    """Recover the exact decision session a frozen plan was built for."""

    try:
        rebalance_id = plan.rebalance_id
    except AttributeError as exc:
        raise _Refusal("order-level V17 frozen plan identity is unreadable") from exc
    if (
        type(rebalance_id) is not str
        or not rebalance_id.startswith(_REBALANCE_ID_PREFIX)
        or rebalance_id[len(_REBALANCE_ID_PREFIX):] not in decision_set
    ):
        raise _Refusal("order-level V17 frozen plan identity changed")
    return rebalance_id[len(_REBALANCE_ID_PREFIX):]


class AcceptedRiskQqqOrderLevelV17QcRuntime(
    _v16.AcceptedRiskQqqOrderLevelV16QcRuntime
):
    """Run V16 with fail-closed, counted decision and execution skips."""

    def __init__(self, algorithm, *, profile_id, **kwargs):
        profile = require_qqq_order_level_profile(profile_id)
        super().__init__(
            algorithm,
            profile_id=_V16_PROFILE_BY_V17[profile_id],
            **kwargs,
        )
        self._profile = profile
        self._skipped_decision_records = []
        self._stale_snapshot_skipped_decision_count = 0
        self._weight_total_skipped_decision_count = 0
        self._overnight_drift_skipped_execution_count = 0
        self._prefetched_benchmark_measures = None

    def _record_skipped_decision(self, record):
        reason = record["reason"]
        if reason == STALE_SNAPSHOT_SKIP_REASON:
            self._stale_snapshot_skipped_decision_count += 1
        elif reason == WEIGHT_TOTAL_SKIP_REASON:
            self._weight_total_skipped_decision_count += 1
        elif reason == OVERNIGHT_DRIFT_SKIP_REASON:
            self._overnight_drift_skipped_execution_count += 1
        else:
            raise _Refusal("order-level V17 skip reason changed")
        self._skipped_decision_records.append(record)

    def _pit_verdict(self, session):
        """Return ``(skip_record, None)`` or ``(None, benchmark_measures)``.

        The inherited helpers, constants and coverage recording are reused in
        the inherited order; only the two named refusals become skip records,
        and they are detected before, never instead of, the inherited checks.
        """

        decision = datetime.strptime(session, "%Y-%m-%d")
        start = decision - timedelta(days=_base.PIT_LOOKBACK_CALENDAR_DAYS)
        end = decision + timedelta(days=1)
        constituents = self._history_inventory(
            self._qqq_constituent_universe,
            start,
            end,
            "order-level PIT QQQ constituents",
        )
        constituent_time, constituent_rows = self._latest(
            constituents,
            decision,
            "order-level PIT QQQ constituents",
        )
        constituent_age = self._snapshot_age_sessions(
            constituent_time, session, "order-level PIT QQQ constituents"
        )
        served_session = constituent_time.date().isoformat()
        if constituent_age != _base.EXACT_CONSTITUENT_SNAPSHOT_AGE_SESSIONS:
            expected_position = (
                self._session_positions[session]
                - _base.EXACT_CONSTITUENT_SNAPSHOT_AGE_SESSIONS
            )
            if expected_position < 0:
                raise _Refusal(
                    "order-level V17 expected snapshot escaped the session axis"
                )
            return {
                "decision_session": session,
                "reason": STALE_SNAPSHOT_SKIP_REASON,
                "expected_snapshot_session": (
                    self._session_axis[expected_position]
                ),
                "served_snapshot_session": served_session,
                "served_snapshot_age_sessions": constituent_age,
            }, None
        constituent_weights = _base._input.positive_constituent_weights(
            constituent_rows, _base._decimal, _Refusal
        )
        total = _positive_weight_total(
            constituent_weights, self._proxy_weight_mode
        )
        if not (
            _base.MINIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL
            <= total
            <= _base.MAXIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL
        ):
            return {
                "decision_session": session,
                "reason": WEIGHT_TOTAL_SKIP_REASON,
                "served_snapshot_session": served_session,
                "positive_weight_member_count": len(constituent_weights),
                "positive_constituent_weight_total": _base._decimal_text(
                    total
                ),
            }, None
        return None, self._resolved_qqq_weights(
            session,
            constituent_weights,
            constituent_age_sessions=constituent_age,
        )

    def _pit_benchmark_measures(self, session):
        # The inherited decision path asks for the measures once, after this
        # class has already verified and recorded them for the same session.
        # Any other request is a state defect, not a reason to re-read.
        prefetched = self._prefetched_benchmark_measures
        self._prefetched_benchmark_measures = None
        if prefetched is None or prefetched[0] != session:
            raise _Refusal(
                "order-level V17 PIT measures were requested outside the decision callback"
            )
        return prefetched[1]

    def on_after_close(self):
        # Repeat the inherited callback gates exactly; a non-decision session
        # and every executed decision run the unchanged inherited path.
        if not self._initialized or self._completed:
            raise _Refusal(
                "order-level after-close callback escaped runtime state"
            )
        session = self._algorithm.time.date().isoformat()
        if (
            self._pending_preopen is not None
            and self._pending_preopen[0] <= session
        ):
            raise _Refusal(
                "order-level next-session preopen callback was missed"
            )
        if session not in self._decision_set:
            return super().on_after_close()
        record, measures = self._pit_verdict(session)
        if record is None:
            self._prefetched_benchmark_measures = (session, measures)
            try:
                return super().on_after_close()
            finally:
                self._prefetched_benchmark_measures = None
        # Fail-closed skip: repeat the inherited pre-decision transitions
        # (account observation, prior-plan closure, monotone score advance)
        # so the carried path and the sequential score state are identical
        # to an executed decision's, then record without any order.
        if (
            self._profile["evaluation_start_session"]
            <= session
            <= _base.FINAL_EXECUTION_SESSION
        ):
            self._observe_strategy_account(session)
        self._close_open_plan()
        self._score_runtime.score(self._session_positions[session])
        self._record_skipped_decision(record)
        return False

    def on_before_open(self):
        # Repeat the inherited preopen gates exactly, in the inherited order,
        # up to the single holdings comparison; a clock, live-mode, duplicate
        # or cash refusal is unchanged and still ends the run.
        if not self._preopen_mode or not self._initialized or self._completed:
            raise _Refusal(
                "order-level preopen callback escaped its V6 runtime state"
            )
        _base._orders.validate_backtest_initialize(
            live_mode=self._backtest_flag()
        )
        session = self._algorithm.time.date().isoformat()
        if session in self._submitted_preopen_sessions:
            raise _Refusal(
                "order-level preopen submission was duplicated"
            )
        if self._pending_preopen is None:
            return False
        expected, plan = self._pending_preopen
        if session < expected:
            return False
        actual_time = self._algorithm.time
        if (
            actual_time.date().isoformat() != expected
            or actual_time.hour != 9
            or not 20 <= actual_time.minute <= 27
        ):
            raise _Refusal(
                "order-level preopen callback missed its exact next session"
            )
        decision_session = _decision_session_of(plan, self._decision_set)
        observed_cash = self._portfolio_cash()
        planned_cash = plan.starting_cash
        if (
            type(planned_cash) is not Decimal
            or not planned_cash.is_finite()
            or planned_cash < 0
            or type(observed_cash) is not Decimal
            or not observed_cash.is_finite()
            or observed_cash < planned_cash
        ):
            raise _Refusal(
                "order-level overnight cash decreased or is invalid"
            )
        planned_quantities = dict(plan.starting_quantities)
        observed_quantities = self._current_quantities(
            set(dict(plan.target_quantities))
        )
        if planned_quantities == observed_quantities:
            return super().on_before_open()
        drifted = tuple(
            _v14._redacted_security_id_sha256(security_id)
            for security_id in sorted(
                set(planned_quantities) | set(observed_quantities)
            )
            if planned_quantities.get(security_id)
            != observed_quantities.get(security_id)
        )
        self._pending_preopen = None
        self._record_skipped_decision({
            "decision_session": decision_session,
            "reason": OVERNIGHT_DRIFT_SKIP_REASON,
            "execution_session": expected,
            "drifted_security_count": len(drifted),
            "drifted_security_path_sha256": _base._sha({
                "schema": DRIFTED_SECURITY_PATH_SCHEMA,
                "security_sha256s": list(drifted),
            }),
        })
        return False

    def _skipped_decision_evidence(self):
        records = [dict(record) for record in self._skipped_decision_records]
        retained = records[:MAXIMUM_RETAINED_SKIPPED_DECISIONS]
        return {
            "schema": SKIPPED_DECISION_EVIDENCE_SCHEMA,
            "skipped_count": len(records),
            "retained_count": len(retained),
            "omitted_count": len(records) - len(retained),
            "records": retained,
            "path_sha256": _base._sha({
                "schema": SKIPPED_DECISION_PATH_SCHEMA,
                "records": records,
            }),
        }

    def _aggregate_record(self):
        summary = super()._aggregate_record()
        if summary.get("schema") != _v16.EXPOSURE_SUMMARY_SCHEMA:
            raise _Refusal("order-level V17 predecessor schema changed")
        records = tuple(self._skipped_decision_records)
        counted = {
            reason: sum(1 for record in records if record["reason"] == reason)
            for reason in SKIP_REASONS
        }
        stale = self._stale_snapshot_skipped_decision_count
        weight = self._weight_total_skipped_decision_count
        drift = self._overnight_drift_skipped_execution_count
        if (
            counted[STALE_SNAPSHOT_SKIP_REASON] != stale
            or counted[WEIGHT_TOTAL_SKIP_REASON] != weight
            or counted[OVERNIGHT_DRIFT_SKIP_REASON] != drift
            or sum(counted.values()) != len(records)
        ):
            raise _Refusal(
                "order-level V17 skipped decision evidence count changed"
            )
        scheduled = self._decision_count + stale + weight
        if scheduled != len(self._decision_sessions):
            raise _Refusal(
                "order-level V17 scheduled decision census changed"
            )
        predecessor_run_valid = summary.get("run_valid")
        if type(predecessor_run_valid) is not bool or not self._pit_coverage_records:
            raise _Refusal("order-level V17 predecessor validity changed")
        first_scheduled = self._decision_sessions[0]
        first_executed = self._pit_coverage_records[0]["session"]
        schedule_complete = stale == 0 and weight == 0 and drift == 0
        # The skip policy text is bound by the profile digest carried in the
        # emitted meta; the aggregate stays within the 8,192-byte transport.
        summary.update({
            "schema": SKIP_SUMMARY_SCHEMA,
            "scheduled_decision_count": scheduled,
            "stale_snapshot_skipped_decision_count": stale,
            "weight_total_skipped_decision_count": weight,
            "overnight_drift_skipped_execution_count": drift,
            "maximum_served_stale_snapshot_age_sessions": max(
                (
                    record["served_snapshot_age_sessions"]
                    for record in records
                    if record["reason"] == STALE_SNAPSHOT_SKIP_REASON
                ),
                default=0,
            ),
            "first_scheduled_decision_session": first_scheduled,
            "first_executed_decision_session": first_executed,
            "first_scheduled_decision_executed": (
                first_executed == first_scheduled
            ),
            "schedule_complete": schedule_complete,
            "run_valid": predecessor_run_valid and schedule_complete,
            "skipped_decision_evidence": self._skipped_decision_evidence(),
        })
        return summary

    def on_end_of_algorithm(self):
        # V16's callback names its own exact profile family and requires the
        # executed decision count to equal the schedule.  Repeat it with V17's
        # profile/name gate and with skipped decisions counted toward the
        # schedule; every state transition and aggregate operation remains
        # inherited.
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
        if (
            self._decision_count
            + self._stale_snapshot_skipped_decision_count
            + self._weight_total_skipped_decision_count
            != len(self._decision_sessions)
        ):
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
    "AcceptedRiskQqqOrderLevelV17QcRuntime",
    "DECISION_SKIP_POLICY",
    "DRIFTED_SECURITY_PATH_SCHEMA",
    "MAXIMUM_RETAINED_SKIPPED_DECISIONS",
    "META_STATISTIC_NAME",
    "OVERNIGHT_DRIFT_SKIP_REASON",
    "SKIPPED_DECISION_EVIDENCE_SCHEMA",
    "SKIPPED_DECISION_PATH_SCHEMA",
    "SKIP_PROFILE_2025_ID",
    "SKIP_PROFILE_2026_ID",
    "SKIP_PROFILE_IDS",
    "SKIP_PROFILE_SCHEMA",
    "SKIP_REASONS",
    "SKIP_SUMMARY_SCHEMA",
    "STALE_SNAPSHOT_SKIP_REASON",
    "STARTING_CASH",
    "WEIGHT_TOTAL_SKIP_REASON",
    "expected_custom_summary_statistic_names",
    "require_qqq_order_level_profile",
)
