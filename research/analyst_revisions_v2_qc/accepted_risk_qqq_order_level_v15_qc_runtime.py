"""V15 successor for exact delisted-target retirement and terminal marks.

V14 remains byte-identical.  V15 keeps its score, tilt, order, fee, timing,
proxy, forced-exit, and diagnostic policies.  It adds only two narrowly
bounded account mechanics:

* a target is transferred to the structural QQQ proxy only after V12 has
  authenticated LEAN's forced delisting exit for the exact, round-tripped
  security and the account still holds exactly zero shares; every held or
  unauthenticated missing price retains V14's whole-decision skip; and
* the final execution-session account observation is replaced once by QC's
  authoritative terminal account snapshot before performance is computed.

Neither rule admits a live order, changes a historical V14 profile, or turns
an unresolved held security into a tradable position.
"""

from decimal import (
    Context,
    Decimal,
    DecimalException,
    MAX_EMAX,
    MIN_EMIN,
    ROUND_HALF_EVEN,
    localcontext,
)

try:
    import accepted_risk_qqq_order_level_v14_qc_runtime as _v14
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_qqq_order_level_v14_qc_runtime as _v14,
    )


_v13 = _v14._v13
_v12 = _v14._v12
_base = _v14._base
_forced_exit = _v12._forced_exit
AcceptedRiskQqqOrderLevelQcRuntimeError = (
    _v14.AcceptedRiskQqqOrderLevelQcRuntimeError
)
_Refusal = AcceptedRiskQqqOrderLevelQcRuntimeError


ACCOUNT_PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v15"
ACCOUNT_SUMMARY_SCHEMA = "arv2-qqq-order-level-tilt-summary-v10"
ACCOUNT_PROFILE_IDS = tuple(
    "arv2-qqq-order-level-tilt-" + str(year) + "-cutoff-v15"
    for year in (2025, 2026)
)
(
    ACCOUNT_PROFILE_2025_ID,
    ACCOUNT_PROFILE_2026_ID,
) = ACCOUNT_PROFILE_IDS

DELISTED_ZERO_HOLDING_TARGET_POLICY = (
    "authenticated_forced_exit_exact_round_trip_LEAN_delisted_zero_holding_"
    "target_weight_transfers_to_structural_QQQ_proxy_else_refuse_or_skip"
)
TERMINAL_ACCOUNT_OBSERVATION_POLICY = (
    "replace_exact_final_execution_session_mark_once_with_QC_terminal_"
    "equity_holdings_and_cash_before_performance"
)
RETIRED_TARGET_PATH_SCHEMA = "arv2-order-level-retired-delisted-target-path-v1"
TERMINAL_ACCOUNT_RATIO_DECIMAL_PRECISION = 32_768

STARTING_CASH = _v14.STARTING_CASH
META_STATISTIC_NAME = _v14.META_STATISTIC_NAME
AGGREGATES_STATISTIC_NAME = _v14.AGGREGATES_STATISTIC_NAME

_V14_PROFILE_BY_V15 = {
    ACCOUNT_PROFILE_2025_ID: _v14.DIAGNOSTIC_PROFILE_2025_ID,
    ACCOUNT_PROFILE_2026_ID: _v14.DIAGNOSTIC_PROFILE_2026_ID,
}


def _v15_profile(profile_id):
    v14_id = _V14_PROFILE_BY_V15.get(profile_id)
    if v14_id is None:
        raise _Refusal(
            "QQQ order-level V15 profile is not an exact fixed profile"
        )
    record = _v14.require_qqq_order_level_profile(v14_id)
    record.pop("profile_sha256")
    record.update({
        "schema": ACCOUNT_PROFILE_SCHEMA,
        "profile_id": profile_id,
        "delisted_zero_holding_target_policy": (
            DELISTED_ZERO_HOLDING_TARGET_POLICY
        ),
        "terminal_account_observation_policy": (
            TERMINAL_ACCOUNT_OBSERVATION_POLICY
        ),
        "terminal_account_ratio_decimal_precision": (
            TERMINAL_ACCOUNT_RATIO_DECIMAL_PRECISION
        ),
    })
    return {**record, "profile_sha256": _base._sha(record)}


_PROFILES = {
    profile_id: _v15_profile(profile_id)
    for profile_id in ACCOUNT_PROFILE_IDS
}


def require_qqq_order_level_profile(profile_id):
    if type(profile_id) is not str or profile_id not in _PROFILES:
        raise _Refusal(
            "QQQ order-level V15 profile is not an exact fixed profile"
        )
    return _base.json.loads(
        _base._canonical(_PROFILES[profile_id]).decode("ascii")
    )


def expected_custom_summary_statistic_names(profile_id):
    require_qqq_order_level_profile(profile_id)
    return tuple(sorted((META_STATISTIC_NAME, AGGREGATES_STATISTIC_NAME)))


class AcceptedRiskQqqOrderLevelV15QcRuntime(
    _v14.AcceptedRiskQqqOrderLevelV14QcRuntime
):
    """Run V14 with exact zero-held delisting and terminal-mark policies."""

    def __init__(self, algorithm, *, profile_id, **kwargs):
        profile = require_qqq_order_level_profile(profile_id)
        super().__init__(
            algorithm,
            profile_id=_V14_PROFILE_BY_V15[profile_id],
            **kwargs,
        )
        self._profile = profile
        self._retired_delisted_target_records = []
        self._terminal_account_observation_adjustment = None
        self._terminal_account_observation_prior_equity = None
        self._terminal_account_observation_equity = None

    def _portfolio_equity(self):
        terminal = self._terminal_account_observation_equity
        return (
            terminal
            if terminal is not None
            else super()._portfolio_equity()
        )

    @staticmethod
    def _require_exact_target_weights(target_weights):
        """Apply the inherited order core's target boundary before retiring.

        Retirement necessarily transforms the target map before the inherited
        planner sees it.  Validate the original map first so a bad weight
        cannot disappear with a delisted target or be absorbed by QQQ.
        """

        if type(target_weights) is not dict or not target_weights:
            raise _Refusal(
                "order-level V15 target weights are not an exact dict"
            )
        if any(
            type(security_id) is not str
            or not security_id
            or security_id != security_id.strip()
            for security_id in target_weights
        ):
            raise _Refusal(
                "order-level V15 target security identity changed"
            )
        if any(
            type(weight) is not Decimal
            or not weight.is_finite()
            or weight <= 0
            for weight in target_weights.values()
        ):
            raise _Refusal("order-level V15 target weight changed")
        with localcontext() as context:
            context.prec = 80
            if (
                sum(target_weights.values(), Decimal(0))
                != _base._orders.TARGET_GROSS_EXPOSURE
            ):
                raise _Refusal("order-level V15 target gross changed")
        return target_weights

    def _is_exact_zero_held_delisted_target(self, security_id):
        if security_id == _base._PROXY_ID or self._proxy_weight_mode is not True:
            return False
        symbol, security = self._security(security_id)
        try:
            sid = _base._symbol_sid(
                symbol, "order-level retired delisted target"
            )
            canonical_id = self._resolution.security_for_qc_sid(sid)
            canonical_symbol = self._resolution.symbol_for_security(
                canonical_id
            )
            signed_forced_quantity = (
                _forced_exit.forced_delisting_signed_quantity(
                    self._forced_delisting_ledger, security_id
                )
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise _Refusal(
                "order-level retired delisted target authority is unreadable"
            ) from exc
        if signed_forced_quantity == 0:
            return False
        try:
            identities_match = (
                canonical_id == security_id
                and _base._symbol_sid(
                    canonical_symbol,
                    "order-level retired delisted target canonical",
                ) == sid
                and _base._symbol_sid(
                    security.symbol,
                    "order-level retired delisted target security",
                ) == sid
                and sid in self._configured_security_ids
                and security.is_delisted is True
            )
            quantity = _base._decimal(
                self._algorithm.portfolio[symbol].quantity,
                "order-level retired delisted target quantity",
                nonnegative=True,
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise _Refusal(
                "order-level retired delisted target authority is unreadable"
            ) from exc
        if signed_forced_quantity > 0 or not identities_match:
            raise _Refusal(
                "order-level retired delisted target authority changed"
            )
        if quantity != quantity.to_integral_value():
            raise _Refusal(
                "order-level retired delisted target quantity is not whole"
            )
        if quantity != 0:
            raise _Refusal(
                "order-level retired delisted target holding reappeared"
            )
        return True

    def _retire_exact_unpriced_delisted_targets(self, session, target_weights):
        self._require_exact_target_weights(target_weights)
        target_weights = dict(target_weights)
        retired = []
        for security_id in sorted(target_weights):
            if not self._is_exact_zero_held_delisted_target(security_id):
                continue
            retired.append(security_id)
        if not retired:
            return target_weights, None
        if _base._PROXY_ID not in target_weights:
            raise _Refusal(
                "order-level retired delisted target lacks structural proxy"
            )
        try:
            with localcontext(_v14._exact_complement_context()):
                absorbed = sum(
                    (target_weights.pop(security_id) for security_id in retired),
                    Decimal(0),
                )
                target_weights[_base._PROXY_ID] += absorbed
        except (DecimalException, KeyError, TypeError, ValueError) as exc:
            raise _Refusal(
                "order-level retired delisted target weight changed"
            ) from exc
        record = {
            "decision_session": session,
            "retired_security_sha256s": [
                _v14._redacted_security_id_sha256(security_id)
                for security_id in retired
            ],
            "retired_target_weight": _base._decimal_text(absorbed),
        }
        return target_weights, record

    def _build_plan(self, session, target_weights):
        transformed, record = self._retire_exact_unpriced_delisted_targets(
            session, target_weights
        )
        plan = super()._build_plan(session, transformed)
        if plan is not None and record is not None:
            self._retired_delisted_target_records.append(record)
        return plan

    def _replace_terminal_account_observation(self):
        session = _base.FINAL_EXECUTION_SESSION
        start_session = self._profile["evaluation_start_session"]
        if (
            self._terminal_account_observation_adjustment is not None
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
                prec=TERMINAL_ACCOUNT_RATIO_DECIMAL_PRECISION,
                rounding=ROUND_HALF_EVEN,
                Emin=MIN_EMIN,
                Emax=MAX_EMAX,
                capitals=1,
                clamp=0,
            )
            ratio_context.clear_flags()
            with localcontext(ratio_context):
                composition = holdings + cash
                gross_exposure = holdings / equity
                cash_weight = Decimal(1) - gross_exposure
                adjustment = equity - prior_equity
        except DecimalException as exc:
            raise _Refusal(
                "order-level terminal account arithmetic changed"
            ) from exc
        if composition != equity:
            raise _Refusal(
                "order-level terminal account composition changed"
            )
        self._strategy_equity_observations[session] = equity
        self._gross_exposure_observations[session] = gross_exposure
        self._cash_weight_observations[session] = cash_weight
        self._terminal_account_observation_adjustment = adjustment
        self._terminal_account_observation_prior_equity = prior_equity
        self._terminal_account_observation_equity = equity

    def _aggregate_record(self):
        if self._terminal_account_observation_adjustment is None:
            raise _Refusal(
                "order-level terminal account observation is unreconciled"
            )
        summary = super()._aggregate_record()
        records = tuple(self._retired_delisted_target_records)
        summary.update({
            "schema": ACCOUNT_SUMMARY_SCHEMA,
            "delisted_zero_holding_target_retirement_count": sum(
                len(record["retired_security_sha256s"])
                for record in records
            ),
            "delisted_zero_holding_target_retirement_decision_count": (
                len(records)
            ),
            "delisted_zero_holding_target_retired_weight_total": (
                _base._decimal_text(sum(
                    (
                        Decimal(record["retired_target_weight"])
                        for record in records
                    ),
                    Decimal(0),
                ))
            ),
            "delisted_zero_holding_target_path_sha256": _base._sha({
                "schema": RETIRED_TARGET_PATH_SCHEMA,
                "records": list(records),
            }),
            "terminal_account_observation_adjustment": _base._decimal_text(
                self._terminal_account_observation_adjustment
            ),
            "terminal_account_observation_prior_equity": _base._decimal_text(
                self._terminal_account_observation_prior_equity
            ),
            "terminal_account_observation_equity": _base._decimal_text(
                self._terminal_account_observation_equity
            ),
        })
        return summary

    def on_end_of_algorithm(self):
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
    "ACCOUNT_PROFILE_2025_ID",
    "ACCOUNT_PROFILE_2026_ID",
    "ACCOUNT_PROFILE_IDS",
    "ACCOUNT_PROFILE_SCHEMA",
    "ACCOUNT_SUMMARY_SCHEMA",
    "AGGREGATES_STATISTIC_NAME",
    "AcceptedRiskQqqOrderLevelQcRuntimeError",
    "AcceptedRiskQqqOrderLevelV15QcRuntime",
    "DELISTED_ZERO_HOLDING_TARGET_POLICY",
    "META_STATISTIC_NAME",
    "RETIRED_TARGET_PATH_SCHEMA",
    "STARTING_CASH",
    "TERMINAL_ACCOUNT_OBSERVATION_POLICY",
    "TERMINAL_ACCOUNT_RATIO_DECIMAL_PRECISION",
    "expected_custom_summary_statistic_names",
    "require_qqq_order_level_profile",
)
