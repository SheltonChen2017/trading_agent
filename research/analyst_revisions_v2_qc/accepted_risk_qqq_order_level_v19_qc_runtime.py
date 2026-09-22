"""V19 successor: context-independent boundary and complete drift census.

V18 remains byte-identical.  V19 preserves every inherited universe, score,
tilt, execution, fee, terminal-account and skip-path economic rule.  It makes
four prospective evidence corrections only:

* the terminal residual magnitude uses ``Decimal.copy_abs()``, whose result
  is independent of mutable ambient Decimal precision and rounding;
* a nonzero holding outside the frozen plan's tracked names is treated as the
  same counted, no-order overnight-drift skip as a tracked holding change;
* the first executed decision is derived from plans actually submitted at the
  preopen, not from the broader PIT-coverage census; and
* a window in which every decision is skipped refuses explicitly because the
  inherited aggregate cannot truthfully fabricate executed coverage.

The engine's total portfolio value remains authoritative.  V19 also declares
and requires a 16,384-byte custom-statistic transport for its exact profile
family, resolving V18's measured 190-byte prospective review margin without
trimming evidence.
"""

from decimal import (
    MAX_EMAX,
    MIN_EMIN,
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DecimalException,
    localcontext,
)

try:
    import accepted_risk_qqq_order_level_v18_qc_runtime as _v18
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_qqq_order_level_v18_qc_runtime as _v18,
    )


_v17 = _v18._v17
_v15 = _v18._v15
_v14 = _v17._v14
_v13 = _v18._v13
_base = _v18._base
AcceptedRiskQqqOrderLevelQcRuntimeError = (
    _v18.AcceptedRiskQqqOrderLevelQcRuntimeError
)
_Refusal = AcceptedRiskQqqOrderLevelQcRuntimeError


SUCCESSOR_PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v19"
SUCCESSOR_SUMMARY_SCHEMA = "arv2-qqq-order-level-tilt-summary-v14"
SUCCESSOR_PROFILE_IDS = tuple(
    "arv2-qqq-order-level-tilt-" + str(year) + "-cutoff-v19"
    for year in (2025, 2026)
)
(
    SUCCESSOR_PROFILE_2025_ID,
    SUCCESSOR_PROFILE_2026_ID,
) = SUCCESSOR_PROFILE_IDS

RESIDUAL_MAGNITUDE_POLICY = (
    "compare_terminal_composition_residual_with_decimal_copy_abs_independent_"
    "of_ambient_decimal_context"
)
COMPLETE_CENSUS_DRIFT_POLICY = (
    "skip_without_orders_and_count_overnight_drift_when_any_nonzero_holding_"
    "differs_from_the_complete_frozen_preopen_census"
)
EXECUTED_DECISION_SESSION_POLICY = (
    "derive_executed_decision_sessions_only_from_frozen_plans_actually_"
    "submitted_at_the_authenticated_preopen"
)
ALL_SKIPPED_TERMINAL_POLICY = (
    "refuse_terminal_aggregate_when_no_scheduled_decision_executed_without_"
    "fabricating_PIT_coverage"
)
MAXIMUM_STATISTIC_BYTES = 16_384

TERMINAL_COMPOSITION_POLICY = _v18.TERMINAL_COMPOSITION_POLICY
TERMINAL_COMPOSITION_TOLERANCE = _v18.TERMINAL_COMPOSITION_TOLERANCE
MAXIMUM_BOUNDARY_OBSERVABLE_EQUITY = (
    _v18.MAXIMUM_BOUNDARY_OBSERVABLE_EQUITY
)
STARTING_CASH = _v18.STARTING_CASH
META_STATISTIC_NAME = _v18.META_STATISTIC_NAME
AGGREGATES_STATISTIC_NAME = _v18.AGGREGATES_STATISTIC_NAME

_V18_PROFILE_BY_V19 = {
    SUCCESSOR_PROFILE_2025_ID: _v18.BOUNDARY_PROFILE_2025_ID,
    SUCCESSOR_PROFILE_2026_ID: _v18.BOUNDARY_PROFILE_2026_ID,
}


def _v19_profile(profile_id):
    v18_id = _V18_PROFILE_BY_V19.get(profile_id)
    if v18_id is None:
        raise _Refusal(
            "QQQ order-level V19 profile is not an exact fixed profile"
        )
    record = _v18.require_qqq_order_level_profile(v18_id)
    record.pop("profile_sha256")
    record.update({
        "schema": SUCCESSOR_PROFILE_SCHEMA,
        "profile_id": profile_id,
        "residual_magnitude_policy": RESIDUAL_MAGNITUDE_POLICY,
        "complete_census_drift_policy": COMPLETE_CENSUS_DRIFT_POLICY,
        "executed_decision_session_policy": (
            EXECUTED_DECISION_SESSION_POLICY
        ),
        "all_skipped_terminal_policy": ALL_SKIPPED_TERMINAL_POLICY,
        "maximum_custom_statistic_bytes_each": MAXIMUM_STATISTIC_BYTES,
    })
    return {**record, "profile_sha256": _base._sha(record)}


_PROFILES = {
    profile_id: _v19_profile(profile_id)
    for profile_id in SUCCESSOR_PROFILE_IDS
}


def require_qqq_order_level_profile(profile_id):
    if type(profile_id) is not str or profile_id not in _PROFILES:
        raise _Refusal(
            "QQQ order-level V19 profile is not an exact fixed profile"
        )
    return _base.json.loads(
        _base._canonical(_PROFILES[profile_id]).decode("ascii")
    )


def expected_custom_summary_statistic_names(profile_id):
    require_qqq_order_level_profile(profile_id)
    return tuple(sorted((META_STATISTIC_NAME, AGGREGATES_STATISTIC_NAME)))


class AcceptedRiskQqqOrderLevelV19QcRuntime(
    _v18.AcceptedRiskQqqOrderLevelV18QcRuntime
):
    """Run V18 with prospective evidence and transport corrections."""

    def __init__(self, algorithm, *, profile_id, **kwargs):
        profile = require_qqq_order_level_profile(profile_id)
        super().__init__(
            algorithm,
            profile_id=_V18_PROFILE_BY_V19[profile_id],
            **kwargs,
        )
        self._profile = profile
        self._executed_decision_sessions = []

    def _replace_terminal_account_observation(self):
        # V18 repeated exactly, except copy_abs replaces context-sensitive
        # ``abs`` at the single residual-magnitude comparison.
        session = _base.FINAL_EXECUTION_SESSION
        start_session = self._profile["evaluation_start_session"]
        if (
            self._terminal_account_observation_adjustment is not None
            or self._terminal_account_composition_residual is not None
            or start_session not in self._strategy_equity_observations
            or session not in self._strategy_equity_observations
            or session not in self._gross_exposure_observations
            or session not in self._cash_weight_observations
        ):
            raise _Refusal(
                "order-level terminal account observation is unavailable"
            )
        if self._strategy_equity_observations[start_session] != STARTING_CASH:
            raise _Refusal(
                "order-level starting account observation changed"
            )
        try:
            equity = self._portfolio_equity()
            holdings = _base._decimal(
                self._algorithm.portfolio.total_holdings_value,
                "QC terminal total holdings value",
                nonnegative=True,
            )
            cash = self._portfolio_cash()
            prior_equity = _base._decimal(
                self._strategy_equity_observations[session],
                "order-level terminal prior equity",
                positive=True,
            )
            ratio_context = Context(
                prec=_v15.TERMINAL_ACCOUNT_RATIO_DECIMAL_PRECISION,
                rounding=ROUND_HALF_EVEN,
                Emin=MIN_EMIN,
                Emax=MAX_EMAX,
                capitals=1,
                clamp=0,
            )
            ratio_context.clear_flags()
            with localcontext(ratio_context):
                composition = holdings + cash
                residual = composition - equity
                gross_exposure = holdings / equity
                cash_weight = Decimal(1) - gross_exposure
                adjustment = equity - prior_equity
        except DecimalException as exc:
            raise _Refusal(
                "order-level terminal account arithmetic changed"
            ) from exc
        if equity >= MAXIMUM_BOUNDARY_OBSERVABLE_EQUITY:
            raise _Refusal(
                "order-level terminal equity exceeds the double-boundary bound"
            )
        if residual.copy_abs() > TERMINAL_COMPOSITION_TOLERANCE:
            raise _Refusal(
                "order-level terminal account composition changed"
            )
        self._strategy_equity_observations[session] = equity
        self._gross_exposure_observations[session] = gross_exposure
        self._cash_weight_observations[session] = cash_weight
        self._terminal_account_observation_adjustment = adjustment
        self._terminal_account_observation_prior_equity = prior_equity
        self._terminal_account_observation_equity = equity
        self._terminal_account_composition_residual = residual

    def _complete_preopen_quantity_census(self, plan):
        """Return the exact frozen and live nonzero QC-SID quantities."""

        expected = {
            _base._symbol_sid(
                self._qqq_benchmark_symbol
                if security_id == _base._PROXY_ID else
                self._resolution.symbol_for_security(security_id),
                "order-level frozen holding",
            ): quantity
            for security_id, quantity in plan.starting_quantities
        }
        try:
            holdings = tuple(self._algorithm.portfolio.items())
        except Exception as exc:
            raise _Refusal(
                "order-level complete preopen holdings are unreadable"
            ) from exc
        observed = {}
        for item in holdings:
            try:
                symbol, holding = item
            except (TypeError, ValueError) as exc:
                raise _Refusal(
                    "order-level complete preopen holdings are unreadable"
                ) from exc
            try:
                sid = _base._symbol_sid(
                    symbol, "order-level preopen holding key"
                )
                if sid != _base._symbol_sid(
                    holding.symbol, "order-level preopen holding"
                ):
                    raise _Refusal(
                        "order-level preopen holding identity changed"
                    )
                quantity = _base._decimal(
                    holding.quantity,
                    "order-level preopen holding quantity",
                )
                if quantity:
                    if sid in observed:
                        raise _Refusal(
                            "order-level preopen holding SID is duplicated"
                        )
                    observed[sid] = quantity
            except AttributeError as exc:
                raise _Refusal(
                    "order-level complete preopen holdings are unreadable"
                ) from exc
        return expected, observed

    def _record_overnight_drift_skip(
        self, *, decision_session, execution_session, drifted_ids
    ):
        drifted = tuple(
            _v14._redacted_security_id_sha256(security_id)
            for security_id in sorted(drifted_ids)
        )
        self._pending_preopen = None
        self._record_skipped_decision({
            "decision_session": decision_session,
            "reason": _v17.OVERNIGHT_DRIFT_SKIP_REASON,
            "execution_session": execution_session,
            "drifted_security_count": len(drifted),
            "drifted_security_path_sha256": _base._sha({
                "schema": _v17.DRIFTED_SECURITY_PATH_SCHEMA,
                "security_sha256s": list(drifted),
            }),
        })
        return False

    def on_before_open(self):
        # Preserve every inherited state, clock, live-mode and cash gate.  The
        # complete finite-quantity census must precede V17's whole-share
        # partial read so a split-created fractional holding is classified as
        # the declared counted drift skip rather than a fatal format refusal.
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
        decision_session = _v17._decision_session_of(
            plan, self._decision_set
        )
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
        frozen_census, live_census = self._complete_preopen_quantity_census(
            plan
        )
        if frozen_census != live_census:
            drifted_ids = {
                security_id
                for security_id in set(frozen_census) | set(live_census)
                if frozen_census.get(security_id)
                != live_census.get(security_id)
            }
            return self._record_overnight_drift_skip(
                decision_session=decision_session,
                execution_session=expected,
                drifted_ids=drifted_ids,
            )
        planned_quantities = dict(plan.starting_quantities)
        observed_quantities = self._current_quantities(
            set(dict(plan.target_quantities))
        )
        if planned_quantities != observed_quantities:
            drifted_ids = {
                security_id
                for security_id in (
                    set(planned_quantities) | set(observed_quantities)
                )
                if planned_quantities.get(security_id)
                != observed_quantities.get(security_id)
            }
            return self._record_overnight_drift_skip(
                decision_session=decision_session,
                execution_session=expected,
                drifted_ids=drifted_ids,
            )
        submitted = super().on_before_open()
        if submitted is not True:
            raise _Refusal(
                "order-level V19 inherited preopen submission changed"
            )
        self._executed_decision_sessions.append(decision_session)
        return True

    def _aggregate_record(self):
        if not self._executed_decision_sessions:
            raise _Refusal(
                "order-level V19 all-skipped schedule has no executed decision"
            )
        summary = super()._aggregate_record()
        if summary.get("schema") != _v18.BOUNDARY_SUMMARY_SCHEMA:
            raise _Refusal("order-level V19 predecessor schema changed")
        executed = tuple(self._executed_decision_sessions)
        if (
            len(executed) != len(set(executed))
            or tuple(sorted(executed)) != executed
            or any(session not in self._decision_set for session in executed)
            or len(executed)
            + self._overnight_drift_skipped_execution_count
            + self._skipped_unpriced_decision_count
            + self._forced_exit_invalidated_pending_plan_count
            != self._decision_count
        ):
            raise _Refusal(
                "order-level V19 executed decision census changed"
            )
        first_scheduled = self._decision_sessions[0]
        first_executed = executed[0]
        summary.update({
            "schema": SUCCESSOR_SUMMARY_SCHEMA,
            "executed_decision_count": len(executed),
            "executed_decision_session_path_sha256": _base._sha({
                "schema": "arv2-order-level-executed-decision-path-v1",
                "sessions": list(executed),
            }),
            "first_executed_decision_session": first_executed,
            "first_scheduled_decision_executed": (
                first_executed == first_scheduled
            ),
        })
        return summary

    def on_end_of_algorithm(self):
        # V18's callback repeated with V19's exact profile and transport.
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
        if _base.MAXIMUM_STATISTIC_BYTES != MAXIMUM_STATISTIC_BYTES:
            raise _Refusal(
                "order-level V19 statistic transport binding changed"
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
        if not self._executed_decision_sessions:
            raise _Refusal(
                "order-level V19 all-skipped schedule has no executed decision"
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
                or len(value.encode("ascii")) > MAXIMUM_STATISTIC_BYTES
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
    "ALL_SKIPPED_TERMINAL_POLICY",
    "AcceptedRiskQqqOrderLevelQcRuntimeError",
    "AcceptedRiskQqqOrderLevelV19QcRuntime",
    "COMPLETE_CENSUS_DRIFT_POLICY",
    "EXECUTED_DECISION_SESSION_POLICY",
    "MAXIMUM_BOUNDARY_OBSERVABLE_EQUITY",
    "MAXIMUM_STATISTIC_BYTES",
    "META_STATISTIC_NAME",
    "RESIDUAL_MAGNITUDE_POLICY",
    "STARTING_CASH",
    "SUCCESSOR_PROFILE_2025_ID",
    "SUCCESSOR_PROFILE_2026_ID",
    "SUCCESSOR_PROFILE_IDS",
    "SUCCESSOR_PROFILE_SCHEMA",
    "SUCCESSOR_SUMMARY_SCHEMA",
    "TERMINAL_COMPOSITION_POLICY",
    "TERMINAL_COMPOSITION_TOLERANCE",
    "expected_custom_summary_statistic_names",
    "require_qqq_order_level_profile",
)
