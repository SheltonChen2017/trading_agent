"""V18 successor: a bounded double-boundary tolerance for the terminal identity.

V17 remains byte-identical.  V18 preserves every inherited universe, score,
tilt, execution, fee, forced-exit, delisted-target retirement, decision-skip,
terminal-account and mean-exposure-complement policy.  It changes only how
V15's terminal account identity ``holdings + cash == equity`` is judged.

LEAN exposes its decimal account totals to Python as doubles, so each of the
runtime's decimal reads is the decimal rendering of a double.  Three
independently rounded doubles satisfy an exact sum identity only while the
values carry few enough significant digits; R-173's 2025-now terminal state
did not (its cash carried the sub-cent fractions of a split's fractional
share), and V15 refused on a residual far below any economic amount.  V18
keeps the engine's total portfolio value authoritative and keeps the
identity as the guard.  It replaces exact equality with a declared bound
derived from the double: below 2**24 dollars a double's unit in the last
place is 2**-29, each of the three reads carries at most one unit of
rounding, and three reads cannot differ from the exact identity by more
than 3 * 2**-29, which is below 1E-8 dollars.  Any larger residual still
refuses, equity at or above 2**24 dollars refuses because the derivation no
longer holds, and the observed residual is recorded and reported so a
boundary artifact is visible rather than hidden.  V18 never rebuilds equity
from its own components: a genuine composition break of even one cent still
ends the run.
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
    import accepted_risk_qqq_order_level_v17_qc_runtime as _v17
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_qqq_order_level_v17_qc_runtime as _v17,
    )


_v16 = _v17._v16
_v15 = _v17._v15
_v13 = _v17._v13
_base = _v17._base
AcceptedRiskQqqOrderLevelQcRuntimeError = (
    _v17.AcceptedRiskQqqOrderLevelQcRuntimeError
)
_Refusal = AcceptedRiskQqqOrderLevelQcRuntimeError


BOUNDARY_PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v18"
BOUNDARY_SUMMARY_SCHEMA = "arv2-qqq-order-level-tilt-summary-v13"
BOUNDARY_PROFILE_IDS = tuple(
    "arv2-qqq-order-level-tilt-" + str(year) + "-cutoff-v18"
    for year in (2025, 2026)
)
(
    BOUNDARY_PROFILE_2025_ID,
    BOUNDARY_PROFILE_2026_ID,
) = BOUNDARY_PROFILE_IDS

TERMINAL_COMPOSITION_POLICY = (
    "accept_terminal_holdings_plus_cash_minus_engine_equity_residual_only_"
    "within_1E-8_dollars_derived_from_three_double_boundary_roundings_below_"
    "2_pow_24_dollars_and_report_the_residual"
)
TERMINAL_COMPOSITION_TOLERANCE = Decimal("1E-8")
MAXIMUM_BOUNDARY_OBSERVABLE_EQUITY = Decimal(2 ** 24)

STARTING_CASH = _v17.STARTING_CASH
META_STATISTIC_NAME = _v17.META_STATISTIC_NAME
AGGREGATES_STATISTIC_NAME = _v17.AGGREGATES_STATISTIC_NAME

_V17_PROFILE_BY_V18 = {
    BOUNDARY_PROFILE_2025_ID: _v17.SKIP_PROFILE_2025_ID,
    BOUNDARY_PROFILE_2026_ID: _v17.SKIP_PROFILE_2026_ID,
}


def _v18_profile(profile_id):
    v17_id = _V17_PROFILE_BY_V18.get(profile_id)
    if v17_id is None:
        raise _Refusal(
            "QQQ order-level V18 profile is not an exact fixed profile"
        )
    record = _v17.require_qqq_order_level_profile(v17_id)
    record.pop("profile_sha256")
    record.update({
        "schema": BOUNDARY_PROFILE_SCHEMA,
        "profile_id": profile_id,
        "terminal_account_composition_policy": TERMINAL_COMPOSITION_POLICY,
        "terminal_account_composition_tolerance": _base._decimal_text(
            TERMINAL_COMPOSITION_TOLERANCE
        ),
        "maximum_boundary_observable_equity": _base._decimal_text(
            MAXIMUM_BOUNDARY_OBSERVABLE_EQUITY
        ),
    })
    return {**record, "profile_sha256": _base._sha(record)}


_PROFILES = {
    profile_id: _v18_profile(profile_id)
    for profile_id in BOUNDARY_PROFILE_IDS
}


def require_qqq_order_level_profile(profile_id):
    if type(profile_id) is not str or profile_id not in _PROFILES:
        raise _Refusal(
            "QQQ order-level V18 profile is not an exact fixed profile"
        )
    return _base.json.loads(
        _base._canonical(_PROFILES[profile_id]).decode("ascii")
    )


def expected_custom_summary_statistic_names(profile_id):
    require_qqq_order_level_profile(profile_id)
    return tuple(sorted((META_STATISTIC_NAME, AGGREGATES_STATISTIC_NAME)))


class AcceptedRiskQqqOrderLevelV18QcRuntime(
    _v17.AcceptedRiskQqqOrderLevelV17QcRuntime
):
    """Run V17 with a bounded, reported terminal composition residual."""

    def __init__(self, algorithm, *, profile_id, **kwargs):
        profile = require_qqq_order_level_profile(profile_id)
        super().__init__(
            algorithm,
            profile_id=_V17_PROFILE_BY_V18[profile_id],
            **kwargs,
        )
        self._profile = profile
        self._terminal_account_composition_residual = None

    def _replace_terminal_account_observation(self):
        # V15's terminal snapshot, repeated line for line except that the
        # exact composition equality becomes the bounded residual below.
        # Every refusal before the identity, and every observation written
        # after it, is unchanged.
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
        if abs(residual) > TERMINAL_COMPOSITION_TOLERANCE:
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

    def _aggregate_record(self):
        residual = self._terminal_account_composition_residual
        if type(residual) is not Decimal or not residual.is_finite():
            raise _Refusal(
                "order-level terminal account composition is unreconciled"
            )
        summary = super()._aggregate_record()
        if summary.get("schema") != _v17.SKIP_SUMMARY_SCHEMA:
            raise _Refusal("order-level V18 predecessor schema changed")
        summary.update({
            "schema": BOUNDARY_SUMMARY_SCHEMA,
            "terminal_account_composition_residual": _base._decimal_text(
                residual
            ),
            "terminal_account_composition_tolerance": _base._decimal_text(
                TERMINAL_COMPOSITION_TOLERANCE
            ),
        })
        return summary

    def on_end_of_algorithm(self):
        # V17's callback names V17's own profile family.  Repeat it with
        # V18's profile/name gate; every state transition and aggregate
        # operation remains inherited, and the terminal snapshot dispatches
        # to the bounded override above.
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
    "AcceptedRiskQqqOrderLevelV18QcRuntime",
    "BOUNDARY_PROFILE_2025_ID",
    "BOUNDARY_PROFILE_2026_ID",
    "BOUNDARY_PROFILE_IDS",
    "BOUNDARY_PROFILE_SCHEMA",
    "BOUNDARY_SUMMARY_SCHEMA",
    "MAXIMUM_BOUNDARY_OBSERVABLE_EQUITY",
    "META_STATISTIC_NAME",
    "STARTING_CASH",
    "TERMINAL_COMPOSITION_POLICY",
    "TERMINAL_COMPOSITION_TOLERANCE",
    "expected_custom_summary_statistic_names",
    "require_qqq_order_level_profile",
)
