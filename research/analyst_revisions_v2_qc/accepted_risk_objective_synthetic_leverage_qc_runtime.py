"""Compact QC wrapper for the objective synthetic-leverage diagnostic.

All package, FIGI, point-in-time membership/market-cap, adjusted-open history,
and work-slice bounds are inherited unchanged from the market-cap QC driver.
Only the profile mapping, evaluator class, and aggregate-only result metadata
are specialized here.
"""

try:
    import accepted_risk_market_cap_stock_portfolio_evaluator as market_cap_evaluator
    import accepted_risk_market_cap_stock_portfolio_qc_runtime as market_cap_runtime
    import accepted_risk_objective_synthetic_leverage_evaluator as leverage_evaluator
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_market_cap_stock_portfolio_evaluator as market_cap_evaluator,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_market_cap_stock_portfolio_qc_runtime as market_cap_runtime,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_objective_synthetic_leverage_evaluator as leverage_evaluator,
    )


class AcceptedRiskObjectiveSyntheticLeverageQcRuntimeError(
    market_cap_runtime.AcceptedRiskMarketCapStockPortfolioQcRuntimeError
):
    """The objective leverage profile or aggregate transport is invalid."""


RUNTIME_META_STATISTIC = market_cap_runtime.RUNTIME_META_STATISTIC
RUNTIME_META_SCHEMA = (
    "arv2-accepted-risk-objective-synthetic-leverage-qc-runtime-meta-v1"
)
RUNTIME_COMPLETED_STATUS = (
    "PRELIMINARY_OBJECTIVE_SYNTHETIC_LEVERAGE_COMPLETED"
)
PROFILE_IDS = leverage_evaluator.PROFILE_IDS
TRAIN_WORK_UNITS_PER_SLICE = market_cap_runtime.TRAIN_WORK_UNITS_PER_SLICE
TRAIN_SLICE_SOFT_SECONDS = market_cap_runtime.TRAIN_SLICE_SOFT_SECONDS
MAX_TRAIN_SLICE_COUNT = market_cap_runtime.MAX_TRAIN_SLICE_COUNT

_BASE_PROFILE_BY_LEVERAGE = {
    leverage_evaluator.QQQ_2021_2025_V2_PROFILE_ID: (
        market_cap_evaluator.QQQ_2021_2025_V2_PROFILE_ID
    ),
    leverage_evaluator.SPY_2021_2025_V2_PROFILE_ID: (
        market_cap_evaluator.SPY_2021_2025_V2_PROFILE_ID
    ),
}


def _error(message):
    raise AcceptedRiskObjectiveSyntheticLeverageQcRuntimeError(message)


def base_market_cap_profile_id_for_profile(evaluation_profile_id):
    if (
        leverage_evaluator.PROFILE_IDS != PROFILE_IDS
        or set(_BASE_PROFILE_BY_LEVERAGE) != set(PROFILE_IDS)
    ):
        _error("objective leverage profile inventory binding changed")
    profile = leverage_evaluator.require_profile(evaluation_profile_id)
    expected = _BASE_PROFILE_BY_LEVERAGE[evaluation_profile_id]
    if profile["base_profile_id"] != expected:
        _error("objective leverage base-profile mapping changed")
    base_profile = market_cap_evaluator.require_profile(expected)
    if base_profile["profile_sha256"] != profile["base_profile_sha256"]:
        _error("objective leverage base-profile identity changed")
    return expected


def constituent_etf_tickers_for_profile(evaluation_profile_id):
    return market_cap_evaluator.constituent_etf_tickers_for_profile(
        base_market_cap_profile_id_for_profile(evaluation_profile_id)
    )


def expected_custom_summary_statistic_names(evaluation_profile_id):
    names = leverage_evaluator.expected_custom_summary_statistic_names(
        evaluation_profile_id
    )
    return tuple(sorted((*names, RUNTIME_META_STATISTIC)))


class AcceptedRiskObjectiveSyntheticLeverageQcDriver(
    market_cap_runtime.AcceptedRiskMarketCapStockPortfolioQcDriver
):
    """Reuse the bounded PIT driver and substitute only leverage evaluation."""

    def __init__(
        self,
        algorithm,
        *,
        activation_manifest_key,
        activation_manifest_sha256,
        activation_manifest_byte_count,
        benchmark_symbol,
        trade_bar_type,
        daily_resolution,
        total_return_normalization,
        evaluation_profile_id,
        fundamental_universe,
        constituent_universes,
    ):
        leverage_profile = leverage_evaluator.require_profile(
            evaluation_profile_id
        )
        base_profile_id = base_market_cap_profile_id_for_profile(
            evaluation_profile_id
        )
        tickers = constituent_etf_tickers_for_profile(evaluation_profile_id)
        if (
            type(constituent_universes) is not dict
            or tuple(constituent_universes) != tickers
        ):
            _error("objective leverage ETF universe inventory changed")
        super().__init__(
            algorithm,
            activation_manifest_key=activation_manifest_key,
            activation_manifest_sha256=activation_manifest_sha256,
            activation_manifest_byte_count=activation_manifest_byte_count,
            benchmark_symbol=benchmark_symbol,
            trade_bar_type=trade_bar_type,
            daily_resolution=daily_resolution,
            total_return_normalization=total_return_normalization,
            evaluation_profile_id=base_profile_id,
            fundamental_universe=fundamental_universe,
            constituent_universes=constituent_universes,
        )
        self._leverage_profile_id = evaluation_profile_id
        self._leverage_profile_sha256 = leverage_profile["profile_sha256"]
        self._base_profile_id = base_profile_id
        self._base_profile_sha256 = leverage_profile["base_profile_sha256"]

    def _initialize_evaluator(self):
        maps = self._pit_loader.require_completed_market_caps()
        self._runtime = (
            leverage_evaluator.ObjectiveSyntheticLeverageEvaluationRuntime(
                self._package.evaluator_input,
                profile_id=self._leverage_profile_id,
                package_id=self._package.package_id,
                package_sha256=self._package.package_sha256,
                named_figi_resolution_refusals=self._named_refusals,
                eligibility_market_caps_by_decision_session=maps,
            )
        )

    def emit_completed_summary(self):
        if not self.completed:
            _error("objective leverage custom summary requested before completion")
        if self._emitted:
            return
        statistics = self._runtime.custom_summary_statistics()
        expected = leverage_evaluator.expected_custom_summary_statistic_names(
            self._leverage_profile_id
        )
        if type(statistics) is not dict or tuple(sorted(statistics)) != expected:
            _error("objective leverage evaluator custom summary inventory changed")
        meta = {
            "schema": RUNTIME_META_SCHEMA,
            "status": RUNTIME_COMPLETED_STATUS,
            "package_id": self._package.package_id,
            "package_sha256": self._package.package_sha256,
            "activation_manifest_sha256": (
                self._package.activation_manifest_sha256
            ),
            "symbol_resolution_id": self._resolution.resolution_id,
            "symbol_resolution_sha256": self._resolution.resolution_sha256,
            "resolved_security_count": self._resolution.resolved_count,
            "named_security_refusal_count": (
                self._resolution.named_refusal_count
            ),
            "evaluation_profile_id": self._leverage_profile_id,
            "evaluation_profile_sha256": self._leverage_profile_sha256,
            "base_market_cap_profile_id": self._base_profile_id,
            "base_market_cap_profile_sha256": self._base_profile_sha256,
            "runtime_slice_count": self._runtime_slice_count,
            "point_in_time_history_call_count": (
                self._pit_loader.history_call_count
            ),
            "point_in_time_fetched_source_row_count": (
                self._pit_loader.fetched_source_row_count
            ),
            "point_in_time_eligible_score_bearing_count": (
                self._pit_loader.eligible_score_bearing_count
            ),
            "point_in_time_market_cap_covered_count": (
                self._pit_loader.covered_count
            ),
            "point_in_time_market_cap_uncovered_count": (
                self._pit_loader.uncovered_count
            ),
            "leverage_factors": list(leverage_evaluator.LEVERAGE_FACTORS),
            "scenario_ids": [
                scenario[0] for scenario in leverage_evaluator.SCENARIOS
            ],
            "result_transport": "aggregate_only_custom_summary_statistics",
            "host_object_store_export_required": False,
            "preliminary": True,
            "point_in_time": True,
            "formal": False,
            "control_residualized": False,
            "economic_portfolio": True,
            "etf_or_leverage": True,
            "synthetic_leverage": True,
            "margin_calls_modeled": False,
            "borrow_availability_modeled": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        }
        statistics[RUNTIME_META_STATISTIC] = market_cap_runtime._canonical(
            meta
        ).decode("ascii")
        if (
            tuple(sorted(statistics))
            != expected_custom_summary_statistic_names(
                self._leverage_profile_id
            )
            or any(
                type(key) is not str
                or type(value) is not str
                or len(key) > 64
                or len(value) > 4096
                for key, value in statistics.items()
            )
        ):
            _error("objective leverage custom summary transport exceeded bound")
        try:
            for key, value in sorted(statistics.items()):
                self._algorithm.set_summary_statistic(key, value)
        except Exception as exc:
            raise AcceptedRiskObjectiveSyntheticLeverageQcRuntimeError(
                "objective leverage custom summary emission failed"
            ) from exc
        self._emitted = True

    def require_completed_at_end(self):
        if not self.completed or not self._emitted:
            if self._runtime is not None:
                self._runtime.abort()
            _error(
                "objective leverage QC backtest ended before aggregate completion"
            )
        return True


__all__ = (
    "AcceptedRiskObjectiveSyntheticLeverageQcDriver",
    "AcceptedRiskObjectiveSyntheticLeverageQcRuntimeError",
    "MAX_TRAIN_SLICE_COUNT",
    "PROFILE_IDS",
    "RUNTIME_COMPLETED_STATUS",
    "RUNTIME_META_SCHEMA",
    "RUNTIME_META_STATISTIC",
    "TRAIN_SLICE_SOFT_SECONDS",
    "TRAIN_WORK_UNITS_PER_SLICE",
    "base_market_cap_profile_id_for_profile",
    "constituent_etf_tickers_for_profile",
    "expected_custom_summary_statistic_names",
)
