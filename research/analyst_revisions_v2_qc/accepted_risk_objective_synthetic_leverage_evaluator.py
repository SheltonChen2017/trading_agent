"""Objective synthetic leverage diagnostic over the frozen cap-weighted book.

The two profiles in this module inherit the exact R055 signal, point-in-time
QQQ/SPY membership, market-cap weights, weekly cadence, and selected/matched
portfolio paths from the reviewed market-cap evaluator.  No security is added
or removed here.  The only transformation is deterministic portfolio-level,
daily-reset 2x or 3x leverage over the already costed underlying daily return
stream, followed by a disclosed flat financing debit on each session that
began invested.

This is a synthetic diagnostic.  It does not model margin calls, borrow
availability, security-level financing, taxes, market impact, or broker
liquidation, and it has no provider, network, object-store, order, deployment,
or trading capability.
"""

import dataclasses
import hashlib
import json
from decimal import Decimal, localcontext

try:
    import accepted_risk_market_cap_stock_portfolio_evaluator as _market
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_market_cap_stock_portfolio_evaluator as _market,
    )


class ObjectiveSyntheticLeverageEvaluationError(
    _market.MarketCapStockPortfolioEvaluationError
):
    """The frozen leverage profile or its exact arithmetic is invalid."""


PROFILE_SCHEMA = "arv2-objective-synthetic-leverage-profile-v1"
CONTRACT_ID = "arv2-objective-synthetic-leverage-v1"
SUMMARY_SCHEMA = "arv2-objective-synthetic-leverage-summary-v1"
CELL_SCHEMA = "arv2-objective-synthetic-leverage-cell-v1"
BASE_EVALUATOR_SOURCE_SHA256 = (
    "52d46cf0e8f89a02b5630d70ef7e5e9aa4cabc5a8fdc80b4cd7d6ba1da4f55d9"
)
V2_BASE_EVALUATOR_SOURCE_SHA256 = (
    "0f320134b96e651593bfb98d29a1b8da3987d6192eb83f5a6025a21bdecb5905"
)
V1_BASE_EVALUATOR_SOURCE_SHA256 = (
    "8edb2b55955567a2b809124106bab8bdcb84b610d9fc0c8635fdd92d1a21e831"
)

QQQ_2021_2025_PROFILE_ID = (
    "arv2-objective-synthetic-leverage-qqq-2021-2025-v1"
)
SPY_2021_2025_PROFILE_ID = (
    "arv2-objective-synthetic-leverage-spy-2021-2025-v1"
)
QQQ_2021_2025_V2_PROFILE_ID = (
    "arv2-objective-synthetic-leverage-qqq-2021-2025-v2"
)
SPY_2021_2025_V2_PROFILE_ID = (
    "arv2-objective-synthetic-leverage-spy-2021-2025-v2"
)
QQQ_2021_2025_V3_PROFILE_ID = (
    "arv2-objective-synthetic-leverage-qqq-2021-2025-v3"
)
SPY_2021_2025_V3_PROFILE_ID = (
    "arv2-objective-synthetic-leverage-spy-2021-2025-v3"
)
V1_PROFILE_IDS = (QQQ_2021_2025_PROFILE_ID, SPY_2021_2025_PROFILE_ID)
V2_PROFILE_IDS = (QQQ_2021_2025_V2_PROFILE_ID, SPY_2021_2025_V2_PROFILE_ID)
PROFILE_IDS = (QQQ_2021_2025_V3_PROFILE_ID, SPY_2021_2025_V3_PROFILE_ID)
ALL_PROFILE_IDS = V1_PROFILE_IDS + V2_PROFILE_IDS + PROFILE_IDS
LEVERAGE_FACTORS = (2, 3)
PRIMARY_SCENARIO_ID = "primary-6pct-financing-10bps"
ADVERSE_SCENARIO_ID = "adverse-10pct-financing-20bps"
SCENARIOS = (
    (PRIMARY_SCENARIO_ID, Decimal("0.06"), 10, True),
    (ADVERSE_SCENARIO_ID, Decimal("0.10"), 20, False),
)
ANNUALIZATION_SESSIONS = Decimal(252)
META_STATISTIC_NAME = "ARV2_LEVERAGE_META"
SELECTED_BASE_AGGREGATES_STATISTIC_NAME = (
    "ARV2_LEVERAGE_SELECTED_BASE_AGGREGATES"
)
MATCHED_BASE_AGGREGATES_STATISTIC_NAME = (
    "ARV2_LEVERAGE_MATCHED_BASE_AGGREGATES"
)

_PROFILE_ROWS = (
    (
        QQQ_2021_2025_PROFILE_ID,
        _market.QQQ_2021_2025_PROFILE_ID,
        "3025fff20f0742b60b5e75af22bc71230608fcc7a3af9b043c0c8865dfe0548e",
        V1_BASE_EVALUATOR_SOURCE_SHA256,
    ),
    (
        SPY_2021_2025_PROFILE_ID,
        _market.SPY_2021_2025_PROFILE_ID,
        "6dcb9a08790a40407622d5a6ec34e5cd8fab5978d8e4cdc0f1ba16fb984063d7",
        V1_BASE_EVALUATOR_SOURCE_SHA256,
    ),
    (
        QQQ_2021_2025_V2_PROFILE_ID,
        _market.QQQ_2021_2025_V2_PROFILE_ID,
        "71fe35e9a200e61c9c908fe839e244d97bcef89664a921ddaa3dfd09b8a09178",
        V2_BASE_EVALUATOR_SOURCE_SHA256,
    ),
    (
        SPY_2021_2025_V2_PROFILE_ID,
        _market.SPY_2021_2025_V2_PROFILE_ID,
        "0b6587206c68452b7468aff42432cb3b587a0f96cc078fbf57a6473f86feb59d",
        V2_BASE_EVALUATOR_SOURCE_SHA256,
    ),
    (
        QQQ_2021_2025_V3_PROFILE_ID,
        _market.QQQ_2021_2025_V2_PROFILE_ID,
        "71fe35e9a200e61c9c908fe839e244d97bcef89664a921ddaa3dfd09b8a09178",
        BASE_EVALUATOR_SOURCE_SHA256,
    ),
    (
        SPY_2021_2025_V3_PROFILE_ID,
        _market.SPY_2021_2025_V2_PROFILE_ID,
        "0b6587206c68452b7468aff42432cb3b587a0f96cc078fbf57a6473f86feb59d",
        BASE_EVALUATOR_SOURCE_SHA256,
    ),
)


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decimal_text(value):
    if type(value) is not Decimal or not value.is_finite():
        raise ObjectiveSyntheticLeverageEvaluationError(
            "synthetic leverage metric is not an exact finite Decimal"
        )
    return "0" if value == 0 else format(value, "f")


def _build_profile(row):
    (
        profile_id,
        base_profile_id,
        expected_base_profile_sha256,
        base_evaluator_source_sha256,
    ) = row
    base_profile = _market.require_profile(base_profile_id)
    if base_profile["profile_sha256"] != expected_base_profile_sha256:
        raise ObjectiveSyntheticLeverageEvaluationError(
            "synthetic leverage base profile identity changed"
        )
    record = {
        "schema": PROFILE_SCHEMA,
        "profile_id": profile_id,
        "contract_id": CONTRACT_ID,
        "base_contract_id": _market.CONTRACT_ID,
        "base_profile_id": base_profile_id,
        "base_profile_sha256": expected_base_profile_sha256,
        "base_evaluator_source_sha256": base_evaluator_source_sha256,
        "universe_proxy_ticker": base_profile["universe_proxy_ticker"],
        "evaluation_start_session": base_profile[
            "evaluation_start_session"
        ],
        "evaluation_end_session": base_profile["evaluation_end_session"],
        "expected_return_session_count": base_profile[
            "expected_return_session_count"
        ],
        "signal_and_selection": (
            "exact_unchanged_base_R055_top_decile_capped_at_50_without_"
            "hindsight_or_security_override"
        ),
        "selected_and_matched_paths": (
            "exact_base_market_cap_weighted_daily_return_streams"
        ),
        "daily_reset_formula": (
            "L_times_corresponding_already_costed_base_daily_return_minus_"
            "L_minus_1_times_annual_financing_rate_divided_by_252_on_each_"
            "session_that_began_invested"
        ),
        "cash_and_initial_session_rule": (
            "no_financing_debit_when_the_corresponding_base_portfolio_"
            "began_the_session_with_zero_invested_weight_including_initial_"
            "entry_session"
        ),
        "financing_notional_rule": (
            "one_full_base_portfolio_unit_when_the_session_began_invested_"
            "without_netting_cash_or_underfill"
        ),
        "underlying_cost_rule": (
            "use_corresponding_base_cost_accumulator_then_multiply_its_net_"
            "daily_return_by_leverage_without_a_second_cost_deduction"
        ),
        "leverage_factors": list(LEVERAGE_FACTORS),
        "scenarios": [
            {
                "scenario_id": scenario_id,
                "annual_financing_rate": _decimal_text(financing_rate),
                "underlying_cost_bps_per_side": cost_bps,
                "primary": primary,
            }
            for scenario_id, financing_rate, cost_bps, primary in SCENARIOS
        ],
        "matched_comparator_rule": (
            "identical_leverage_financing_and_cost_scenario_applied_to_"
            "the_base_matched_eligible_stock_path"
        ),
        "spy_context_rule": (
            "same_daily_reset_leverage_and_financing_applied_to_base_SPY_"
            "buy_and_hold_context_without_transaction_cost"
        ),
        "daily_wipeout_rule": (
            "refuse_any_pre_or_post_financing_daily_return_less_than_or_"
            "equal_to_negative_one"
        ),
        "synthetic_only": True,
        "margin_calls_modeled": False,
        "borrow_availability_modeled": False,
        "broker_liquidation_modeled": False,
        "orders": False,
        "deployment": False,
        "trading": False,
    }
    return {**record, "profile_sha256": _sha(record)}


_PROFILE_CANONICAL = {
    row[0]: _canonical(_build_profile(row)) for row in _PROFILE_ROWS
}


def require_profile(profile_id):
    if type(profile_id) is not str or profile_id not in _PROFILE_CANONICAL:
        raise ObjectiveSyntheticLeverageEvaluationError(
            "synthetic leverage profile is not an exact fixed profile"
        )
    return json.loads(_PROFILE_CANONICAL[profile_id].decode("ascii"))


def expected_custom_summary_statistic_names(profile_id):
    require_profile(profile_id)
    return tuple(
        sorted(
            (
                META_STATISTIC_NAME,
                SELECTED_BASE_AGGREGATES_STATISTIC_NAME,
                MATCHED_BASE_AGGREGATES_STATISTIC_NAME,
                "ARV2_LEVERAGE_L2_PRIMARY",
                "ARV2_LEVERAGE_L2_ADVERSE",
                "ARV2_LEVERAGE_L3_PRIMARY",
                "ARV2_LEVERAGE_L3_ADVERSE",
            )
        )
    )


@dataclasses.dataclass(frozen=True)
class _LeveragedPath:
    returns: tuple
    cumulative_return: Decimal
    cumulative_return_before_financing: Decimal
    cumulative_financing_drag: Decimal
    arithmetic_financing_debit: Decimal
    annualized_arithmetic_return: Decimal
    annualized_volatility: Decimal | None
    zero_rate_sharpe: Decimal | None
    zero_rate_sortino: Decimal | None
    maximum_drawdown: Decimal
    financing_session_count: int


def _apply_daily_reset_leverage(
    underlying_returns,
    invested_at_session_start,
    *,
    leverage_factor,
    annual_financing_rate,
):
    if (
        type(underlying_returns) is not tuple
        or not underlying_returns
        or any(
            type(value) is not Decimal or not value.is_finite()
            for value in underlying_returns
        )
    ):
        raise ObjectiveSyntheticLeverageEvaluationError(
            "underlying leverage returns must be a nonempty exact Decimal tuple"
        )
    if (
        type(invested_at_session_start) is not tuple
        or len(invested_at_session_start) != len(underlying_returns)
        or any(type(value) is not bool for value in invested_at_session_start)
    ):
        raise ObjectiveSyntheticLeverageEvaluationError(
            "synthetic leverage invested-session flags changed"
        )
    if type(leverage_factor) is not int or leverage_factor not in LEVERAGE_FACTORS:
        raise ObjectiveSyntheticLeverageEvaluationError(
            "synthetic leverage factor is not exact"
        )
    if (
        type(annual_financing_rate) is not Decimal
        or not annual_financing_rate.is_finite()
        or annual_financing_rate < 0
    ):
        raise ObjectiveSyntheticLeverageEvaluationError(
            "synthetic leverage financing rate is invalid"
        )

    factor = Decimal(leverage_factor)
    wealth = Decimal(1)
    unfinanced_wealth = Decimal(1)
    peak = Decimal(1)
    maximum_drawdown = Decimal(0)
    financing_count = 0
    values = []
    with localcontext(_market._base._context()):
        daily_financing = +(
            (factor - Decimal(1))
            * annual_financing_rate
            / ANNUALIZATION_SESSIONS
        )
        for underlying, invested in zip(
            underlying_returns, invested_at_session_start, strict=True
        ):
            before_financing = +(factor * underlying)
            debit = daily_financing if invested else Decimal(0)
            after_financing = +(before_financing - debit)
            if before_financing <= -1 or after_financing <= -1:
                raise ObjectiveSyntheticLeverageEvaluationError(
                    "synthetic daily leveraged return is not survivable"
                )
            if invested:
                financing_count += 1
            values.append(after_financing)
            unfinanced_wealth = +(
                unfinanced_wealth * (Decimal(1) + before_financing)
            )
            wealth = +(wealth * (Decimal(1) + after_financing))
            peak = max(peak, wealth)
            maximum_drawdown = min(
                maximum_drawdown, +(wealth / peak - Decimal(1))
            )
        annual, volatility, sharpe, sortino = _market._risk_metrics(values)
        cumulative = +(wealth - Decimal(1))
        cumulative_before_financing = +(unfinanced_wealth - Decimal(1))
        cumulative_drag = +(cumulative_before_financing - cumulative)
        arithmetic_debit = +(daily_financing * Decimal(financing_count))
    if annual is None:
        raise ObjectiveSyntheticLeverageEvaluationError(
            "synthetic leverage annual return is unavailable"
        )
    return _LeveragedPath(
        tuple(values),
        cumulative,
        cumulative_before_financing,
        cumulative_drag,
        arithmetic_debit,
        annual,
        volatility,
        sharpe,
        sortino,
        maximum_drawdown,
        financing_count,
    )


class ObjectiveSyntheticLeverageEvaluationRuntime(
    _market.MarketCapStockPortfolioEvaluationRuntime
):
    """Apply only the frozen leverage transformation to exact base paths."""

    def __init__(
        self,
        value,
        *,
        profile_id,
        package_id,
        package_sha256,
        named_figi_resolution_refusals,
        eligibility_market_caps_by_decision_session,
        scratch_directory=None,
    ):
        self._leverage_profile = require_profile(profile_id)
        self._starting_invested_flags = None
        super().__init__(
            value,
            profile_id=self._leverage_profile["base_profile_id"],
            package_id=package_id,
            package_sha256=package_sha256,
            named_figi_resolution_refusals=named_figi_resolution_refusals,
            eligibility_market_caps_by_decision_session=(
                eligibility_market_caps_by_decision_session
            ),
            scratch_directory=scratch_directory,
        )

    def _advance_account(self, account, position, decision, desired):
        if self._starting_invested_flags is None:
            raise ObjectiveSyntheticLeverageEvaluationError(
                "synthetic leverage simulation flags are unavailable"
            )
        if account.role not in self._starting_invested_flags:
            raise ObjectiveSyntheticLeverageEvaluationError(
                "synthetic leverage base account role changed"
            )
        starting_invested = _market._base._stable_sum(
            account.weights.values()
        )
        self._starting_invested_flags[account.role].append(
            starting_invested > 0
        )
        return super()._advance_account(account, position, decision, desired)

    def _benchmark_returns(self):
        sessions = self._input.session_axis
        start = sessions.index(self._profile["evaluation_start_session"])
        end = sessions.index(self._profile["evaluation_end_session"])
        first_execution = start + 1
        benchmark = self._input.benchmark_security_id
        prior = self._price(benchmark, first_execution)
        if prior is None:
            raise ObjectiveSyntheticLeverageEvaluationError(
                "SPY lacks the first synthetic leverage adjusted open"
            )
        returns = []
        for position in range(first_execution, end + 1):
            current = self._price(benchmark, position)
            if current is None:
                raise ObjectiveSyntheticLeverageEvaluationError(
                    "SPY lacks a synthetic leverage adjusted open"
                )
            with localcontext(_market._base._context()):
                value = (
                    Decimal(0)
                    if position == first_execution
                    else +(current / prior - Decimal(1))
                )
            returns.append(value)
            prior = current
        return tuple(returns)

    @staticmethod
    def _path_fields(prefix, path):
        return {
            prefix + "cumulative_return": _decimal_text(
                path.cumulative_return
            ),
            prefix + "cumulative_return_before_financing": _decimal_text(
                path.cumulative_return_before_financing
            ),
            prefix + "cumulative_financing_drag": _decimal_text(
                path.cumulative_financing_drag
            ),
            prefix + "arithmetic_financing_debit": _decimal_text(
                path.arithmetic_financing_debit
            ),
            prefix + "annualized_arithmetic_return": _decimal_text(
                path.annualized_arithmetic_return
            ),
            prefix + "annualized_volatility": (
                None
                if path.annualized_volatility is None
                else _decimal_text(path.annualized_volatility)
            ),
            prefix + "zero_rate_sharpe": (
                None
                if path.zero_rate_sharpe is None
                else _decimal_text(path.zero_rate_sharpe)
            ),
            prefix + "zero_rate_sortino": (
                None
                if path.zero_rate_sortino is None
                else _decimal_text(path.zero_rate_sortino)
            ),
            prefix + "maximum_drawdown": _decimal_text(
                path.maximum_drawdown
            ),
            prefix + "financing_session_count": (
                path.financing_session_count
            ),
        }

    def _cell(
        self,
        *,
        selected,
        matched,
        benchmark_returns,
        selected_flags,
        matched_flags,
        benchmark_flags,
        return_count,
        leverage_factor,
        scenario,
    ):
        scenario_id, financing_rate, cost_bps, primary = scenario
        selected_path = _apply_daily_reset_leverage(
            tuple(selected.accumulators[cost_bps].returns),
            selected_flags,
            leverage_factor=leverage_factor,
            annual_financing_rate=financing_rate,
        )
        matched_path = _apply_daily_reset_leverage(
            tuple(matched.accumulators[cost_bps].returns),
            matched_flags,
            leverage_factor=leverage_factor,
            annual_financing_rate=financing_rate,
        )
        benchmark_path = _apply_daily_reset_leverage(
            benchmark_returns,
            benchmark_flags,
            leverage_factor=leverage_factor,
            annual_financing_rate=financing_rate,
        )
        with localcontext(_market._base._context()):
            selected_minus_matched = +(
                selected_path.cumulative_return
                - matched_path.cumulative_return
            )
            selected_minus_spy = +(
                selected_path.cumulative_return
                - benchmark_path.cumulative_return
            )
        record = {
            "schema": CELL_SCHEMA,
            "profile_id": self._leverage_profile["profile_id"],
            "base_profile_id": self._profile["profile_id"],
            "scenario_id": scenario_id,
            "primary_scenario": primary,
            "leverage_factor": leverage_factor,
            "annual_financing_rate": _decimal_text(financing_rate),
            "underlying_cost_bps_per_side": cost_bps,
            "underlying_cost_is_already_in_base_return": True,
            "second_transaction_cost_deduction": False,
            "status": self._cell_status(selected, matched, return_count),
            "return_session_count": return_count,
            **self._path_fields("selected_", selected_path),
            **self._path_fields("matched_", matched_path),
            **self._path_fields("synthetic_spy_", benchmark_path),
            "selected_minus_matched_cumulative_return": _decimal_text(
                selected_minus_matched
            ),
            "selected_minus_synthetic_spy_cumulative_return": _decimal_text(
                selected_minus_spy
            ),
            "portfolio_level_daily_reset": True,
            "synthetic_only": True,
            "margin_calls_modeled": False,
            "borrow_availability_modeled": False,
            "security_level_financing_modeled": False,
            "broker_liquidation_modeled": False,
            "orders_submitted": 0,
            "formal_accept_reject_disposition": None,
        }
        return record

    def _build_summary(self):
        expected = tuple(
            self._input.session_axis[position]
            for position in sorted(self._decision_positions)
        )
        if tuple(sorted(self._decisions)) != expected:
            raise ObjectiveSyntheticLeverageEvaluationError(
                "synthetic leverage base decision census is not exhaustive"
            )
        self._starting_invested_flags = {"selected": [], "matched": []}
        benchmark_returns = self._benchmark_returns()
        (
            selected,
            matched,
            _benchmark_wealth,
            return_count,
            benchmark_binding,
        ) = self._simulate()
        selected_flags = tuple(self._starting_invested_flags["selected"])
        matched_flags = tuple(self._starting_invested_flags["matched"])
        self._starting_invested_flags = None
        if benchmark_binding is not None:
            raise ObjectiveSyntheticLeverageEvaluationError(
                "historical synthetic leverage base acquired a benchmark "
                "series binding"
            )
        if not (
            len(benchmark_returns)
            == len(selected_flags)
            == len(matched_flags)
            == return_count
        ):
            raise ObjectiveSyntheticLeverageEvaluationError(
                "synthetic leverage return-stream geometry changed"
            )
        benchmark_flags = (False,) + (True,) * (return_count - 1)
        cells = [
            self._cell(
                selected=selected,
                matched=matched,
                benchmark_returns=benchmark_returns,
                selected_flags=selected_flags,
                matched_flags=matched_flags,
                benchmark_flags=benchmark_flags,
                return_count=return_count,
                leverage_factor=leverage_factor,
                scenario=scenario,
            )
            for leverage_factor in LEVERAGE_FACTORS
            for scenario in SCENARIOS
        ]
        record = {
            "schema": SUMMARY_SCHEMA,
            "contract_id": CONTRACT_ID,
            "profile": dict(self._leverage_profile),
            "package_id": self._package_id,
            "package_sha256": self._package_sha256,
            "input_manifest_id": self._input.manifest_id,
            "input_manifest_sha256": self._input.manifest_sha256,
            "status": "PRELIMINARY_OBJECTIVE_SYNTHETIC_LEVERAGE",
            "base_contract_id": _market.CONTRACT_ID,
            "base_profile_id": self._profile["profile_id"],
            "base_profile_sha256": self._profile["profile_sha256"],
            "base_evaluator_source_sha256": self._leverage_profile[
                "base_evaluator_source_sha256"
            ],
            "decision_session_count": self._decision_session_count,
            "return_session_count": return_count,
            "selected_base_aggregates": _market._tilt.account_aggregates(
                selected, return_count, False
            ),
            "matched_base_aggregates": _market._tilt.account_aggregates(
                matched, return_count, False
            ),
            "r055_signal_rule_changed": False,
            "base_security_selection_changed": False,
            "point_in_time_membership_and_market_cap_weighting": True,
            "matched_comparator_levered_identically": True,
            "raw_security_ids_in_summary": False,
            "raw_price_rows_in_summary": False,
            "raw_provider_rows_in_summary": False,
            "synthetic_only": True,
            "formal_result": False,
            "alpha_claim_authorized": False,
            "evaluator_io": {
                "provider": False,
                "network": False,
                "object_store": False,
            },
            "margin_calls_modeled": False,
            "borrow_availability_modeled": False,
            "orders": False,
            "deployment": False,
            "trading": False,
            "cells": cells,
        }
        digest = _sha(record)
        return {
            **record,
            "summary_id": "arv2-objective-leverage-summary-" + digest[:24],
            "summary_sha256": digest,
        }

    def custom_summary_statistics(self):
        summary = self.aggregate_summary()
        cells = summary.pop("cells")
        profile = summary.pop("profile")
        selected_base_aggregates = summary.pop("selected_base_aggregates")
        matched_base_aggregates = summary.pop("matched_base_aggregates")
        if profile != require_profile(self._leverage_profile["profile_id"]):
            raise ObjectiveSyntheticLeverageEvaluationError(
                "synthetic leverage summary profile changed"
            )
        summary["profile_id"] = profile["profile_id"]
        summary["profile_sha256"] = profile["profile_sha256"]
        output = {
            META_STATISTIC_NAME: _canonical(summary).decode("ascii"),
            SELECTED_BASE_AGGREGATES_STATISTIC_NAME: _canonical(
                selected_base_aggregates
            ).decode("ascii"),
            MATCHED_BASE_AGGREGATES_STATISTIC_NAME: _canonical(
                matched_base_aggregates
            ).decode("ascii"),
        }
        for cell in cells:
            suffix = (
                "PRIMARY" if cell["primary_scenario"] else "ADVERSE"
            )
            key = (
                "ARV2_LEVERAGE_L"
                + str(cell["leverage_factor"])
                + "_"
                + suffix
            )
            output[key] = _canonical(cell).decode("ascii")
        if tuple(sorted(output)) != expected_custom_summary_statistic_names(
            self._leverage_profile["profile_id"]
        ):
            raise ObjectiveSyntheticLeverageEvaluationError(
                "synthetic leverage custom summary inventory changed"
            )
        fragments = (
            META_STATISTIC_NAME,
            SELECTED_BASE_AGGREGATES_STATISTIC_NAME,
            MATCHED_BASE_AGGREGATES_STATISTIC_NAME,
        )
        if (
            any(len(key) > 64 for key in output)
            or any(len(output[name]) > 3072 for name in fragments)
            or any(
                len(value) > 4096
                for name, value in output.items()
                if name not in fragments
            )
        ):
            raise ObjectiveSyntheticLeverageEvaluationError(
                "synthetic leverage custom summary exceeded compact bound"
            )
        return dict(sorted(output.items()))


__all__ = (
    "ADVERSE_SCENARIO_ID",
    "ALL_PROFILE_IDS",
    "ANNUALIZATION_SESSIONS",
    "BASE_EVALUATOR_SOURCE_SHA256",
    "CELL_SCHEMA",
    "CONTRACT_ID",
    "LEVERAGE_FACTORS",
    "MATCHED_BASE_AGGREGATES_STATISTIC_NAME",
    "META_STATISTIC_NAME",
    "ObjectiveSyntheticLeverageEvaluationError",
    "ObjectiveSyntheticLeverageEvaluationRuntime",
    "PRIMARY_SCENARIO_ID",
    "PROFILE_IDS",
    "PROFILE_SCHEMA",
    "QQQ_2021_2025_PROFILE_ID",
    "QQQ_2021_2025_V2_PROFILE_ID",
    "QQQ_2021_2025_V3_PROFILE_ID",
    "SCENARIOS",
    "SPY_2021_2025_PROFILE_ID",
    "SPY_2021_2025_V2_PROFILE_ID",
    "SPY_2021_2025_V3_PROFILE_ID",
    "SELECTED_BASE_AGGREGATES_STATISTIC_NAME",
    "SUMMARY_SCHEMA",
    "V1_BASE_EVALUATOR_SOURCE_SHA256",
    "V1_PROFILE_IDS",
    "V2_BASE_EVALUATOR_SOURCE_SHA256",
    "V2_PROFILE_IDS",
    "expected_custom_summary_statistic_names",
    "require_profile",
)
