"""Pure market-cap portfolio arithmetic over the unchanged R055 score."""

import dataclasses
import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext

try:
    import accepted_risk_preliminary_rating_evaluator as _base
    import accepted_risk_market_cap_stock_portfolio_tilt as _tilt
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_rating_evaluator as _base,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_market_cap_stock_portfolio_tilt as _tilt,
    )


class MarketCapStockPortfolioEvaluationError(
    _base.PreliminaryRatingEvaluationError
):
    """The market-cap profile, point-in-time input, or arithmetic is invalid."""


PROFILE_SCHEMA = "arv2-market-cap-stock-portfolio-profile-v1"
CONTRACT_ID = "arv2-market-cap-stock-portfolio-v1"
SUMMARY_SCHEMA = "arv2-market-cap-stock-portfolio-summary-v1"
PORTFOLIO_CELL_SCHEMA = "arv2-market-cap-stock-portfolio-cell-v1"
PRIMARY_SOURCE_VIEW_ID = _base.SOURCE_VIEW_IDS[1]
PRIMARY_SCORE_ARM = "firm_specific"
MAXIMUM_HOLDINGS = 50
TARGET_GROSS_EXPOSURE = _tilt.TARGET_GROSS_EXPOSURE
PORTFOLIO_WEIGHT_QUANTUM = _tilt.PORTFOLIO_WEIGHT_QUANTUM
PRIMARY_COST_BPS = 10
COST_BPS_SCENARIOS = (0, 5, PRIMARY_COST_BPS, 20)
ANNUALIZATION_SESSIONS = Decimal("252")
MINIMUM_INVESTED_RETURN_SESSIONS = 50
MAXIMUM_MARKET_CAP_TEXT_LENGTH = 64
MINIMUM_TILT_RANKED_NAME_COUNT = _tilt.MINIMUM_TILT_RANKED_NAME_COUNT
MINIMUM_TILT_POSITIVE_SCORE_COUNT = _tilt.MINIMUM_TILT_POSITIVE_SCORE_COUNT
MINIMUM_TILT_NEGATIVE_SCORE_COUNT = _tilt.MINIMUM_TILT_NEGATIVE_SCORE_COUNT
MAXIMUM_RELATIVE_TILT = _tilt.MAXIMUM_RELATIVE_TILT
MAXIMUM_ABSOLUTE_OVERWEIGHT = _tilt.MAXIMUM_ABSOLUTE_OVERWEIGHT
MAXIMUM_ONE_WAY_ACTIVE_SHARE = _tilt.MAXIMUM_ONE_WAY_ACTIVE_SHARE
MAXIMUM_HHI_MULTIPLE = _tilt.MAXIMUM_HHI_MULTIPLE
TILT_ENABLED = _tilt.TILT_ENABLED
TILT_UNDERFILLED = _tilt.TILT_UNDERFILLED
TILT_AGGREGATES_SCHEMA = _tilt.TILT_AGGREGATES_SCHEMA
BENCHMARK_LOGICAL_ID = "SPY"
META_STATISTIC_NAME = "ARV2_STOCK_PORTFOLIO_META"
SELECTED_AGGREGATES_STATISTIC_NAME = (
    "ARV2_STOCK_PORTFOLIO_SELECTED_AGGREGATES"
)
MATCHED_AGGREGATES_STATISTIC_NAME = (
    "ARV2_STOCK_PORTFOLIO_MATCHED_AGGREGATES"
)
TILT_AGGREGATES_STATISTIC_NAME = (
    "ARV2_STOCK_PORTFOLIO_TILT_AGGREGATES"
)

QQQ_2021_2025_PROFILE_ID = "arv2-market-cap-stock-qqq-2021-2025-v1"
SPY_2021_2025_PROFILE_ID = "arv2-market-cap-stock-spy-2021-2025-v1"
QQQ_2019_2023_PROFILE_ID = "arv2-market-cap-stock-qqq-2019-2023-v1"
SPY_2019_2023_PROFILE_ID = "arv2-market-cap-stock-spy-2019-2023-v1"
QQQ_2023_2025_PROFILE_ID = "arv2-market-cap-stock-qqq-2023-2025-v1"
SPY_2023_2025_PROFILE_ID = "arv2-market-cap-stock-spy-2023-2025-v1"
QQQ_2021_2025_V2_PROFILE_ID = "arv2-market-cap-stock-qqq-2021-2025-v2"
SPY_2021_2025_V2_PROFILE_ID = "arv2-market-cap-stock-spy-2021-2025-v2"
QQQ_2019_2023_V2_PROFILE_ID = "arv2-market-cap-stock-qqq-2019-2023-v2"
SPY_2019_2023_V2_PROFILE_ID = "arv2-market-cap-stock-spy-2019-2023-v2"
QQQ_2023_2025_V2_PROFILE_ID = "arv2-market-cap-stock-qqq-2023-2025-v2"
SPY_2023_2025_V2_PROFILE_ID = "arv2-market-cap-stock-spy-2023-2025-v2"
QQQ_2021_2025_V3_PROFILE_ID = "arv2-market-cap-stock-qqq-2021-2025-v3"
SPY_2021_2025_V3_PROFILE_ID = "arv2-market-cap-stock-spy-2021-2025-v3"
OUT_OF_WINDOW_COLLECTION_POLICY = (
    "ignore_only_after_validating_collection_shape_identity_and_time_"
    "and_before_traversing_rows"
)

_V1_PROFILE_ROWS = (
    (
        QQQ_2021_2025_PROFILE_ID,
        "QQQ",
        "2021-01-04",
        "2025-12-31",
        1_255,
        261,
        "QQQ_holdings_proxy_for_Nasdaq_100_not_all_Nasdaq_listed_stocks",
    ),
    (
        SPY_2021_2025_PROFILE_ID,
        "SPY",
        "2021-01-04",
        "2025-12-31",
        1_255,
        261,
        "SPY_holdings_proxy_not_official_SP500_index_membership",
    ),
    (
        QQQ_2019_2023_PROFILE_ID,
        "QQQ",
        "2019-01-02",
        "2023-12-29",
        1_258,
        261,
        "QQQ_holdings_proxy_for_Nasdaq_100_not_all_Nasdaq_listed_stocks",
    ),
    (
        SPY_2019_2023_PROFILE_ID,
        "SPY",
        "2019-01-02",
        "2023-12-29",
        1_258,
        261,
        "SPY_holdings_proxy_not_official_SP500_index_membership",
    ),
    (
        QQQ_2023_2025_PROFILE_ID,
        "QQQ",
        "2023-01-03",
        "2025-12-31",
        752,
        157,
        "QQQ_holdings_proxy_for_Nasdaq_100_not_all_Nasdaq_listed_stocks",
    ),
    (
        SPY_2023_2025_PROFILE_ID,
        "SPY",
        "2023-01-03",
        "2025-12-31",
        752,
        157,
        "SPY_holdings_proxy_not_official_SP500_index_membership",
    ),
)
V1_PROFILE_IDS = tuple(row[0] for row in _V1_PROFILE_ROWS)
V2_PROFILE_IDS = (
    QQQ_2021_2025_V2_PROFILE_ID,
    SPY_2021_2025_V2_PROFILE_ID,
    QQQ_2019_2023_V2_PROFILE_ID,
    SPY_2019_2023_V2_PROFILE_ID,
    QQQ_2023_2025_V2_PROFILE_ID,
    SPY_2023_2025_V2_PROFILE_ID,
)
PROFILE_IDS = (
    QQQ_2021_2025_V3_PROFILE_ID,
    SPY_2021_2025_V3_PROFILE_ID,
)
_PROFILE_ROWS = tuple((*row, None) for row in _V1_PROFILE_ROWS) + tuple(
    (successor_id, *row[1:], OUT_OF_WINDOW_COLLECTION_POLICY)
    for successor_id, row in zip(
        V2_PROFILE_IDS, _V1_PROFILE_ROWS, strict=True
    )
) + tuple(
    (successor_id, *row[1:], OUT_OF_WINDOW_COLLECTION_POLICY)
    for successor_id, row in zip(
        PROFILE_IDS, _V1_PROFILE_ROWS[:2], strict=True
    )
)
ALL_PROFILE_IDS = V1_PROFILE_IDS + V2_PROFILE_IDS + PROFILE_IDS
QQQ_PROFILE_IDS = PROFILE_IDS[::2]
SPY_PROFILE_IDS = PROFILE_IDS[1::2]


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
        raise MarketCapStockPortfolioEvaluationError(
            "portfolio metric is not an exact finite Decimal"
        )
    return "0" if value == 0 else format(value, "f")


def _build_profile(row):
    (
        profile_id,
        proxy_ticker,
        start_session,
        end_session,
        expected_session_count,
        expected_decision_session_count,
        disclaimer,
        out_of_window_collection_policy,
    ) = row
    record = {
        "schema": PROFILE_SCHEMA,
        "profile_id": profile_id,
        "contract_id": CONTRACT_ID,
        "universe_proxy_ticker": proxy_ticker,
        "universe_scope_disclaimer": disclaimer,
        "evaluation_start_session": start_session,
        "evaluation_end_session": end_session,
        "expected_session_count": expected_session_count,
        "expected_return_session_count": expected_session_count - 1,
        "expected_decision_session_count": expected_decision_session_count,
        "score_source_view_id": PRIMARY_SOURCE_VIEW_ID,
        "score_arm": PRIMARY_SCORE_ARM,
        "r055_score_rule": "exact_unchanged_R055_cross_section",
        "rebalance_schedule": "first_authenticated_session_of_each_ISO_week",
        "execution_timing": "next_authenticated_session_open",
        "selection": (
            "top_decile_of_point_in_time_eligible_score_bearing_names_"
            "capped_at_50_ordered_by_score_then_security_id_without_"
            "absolute_score_gate"
        ),
        "maximum_holdings": MAXIMUM_HOLDINGS,
        "target_gross_exposure": _decimal_text(TARGET_GROSS_EXPOSURE),
        "signal_weighting": (
            "point_in_time_market_cap_proportional_across_selected_"
            "tradable_names_renormalized_to_target"
        ),
        "matched_comparator": (
            "same_point_in_time_eligible_score_bearing_universe_market_cap_"
            "weighted_and_renormalized_to_the_same_target"
        ),
        "division_residual": (
            "assigned_to_lexicographically_first_tradable_security"
        ),
        "point_in_time_market_cap_map_required": True,
        "market_cap_input_rule": "exact_strictly_positive_Decimal_only",
        "entry_price_missing_rule": (
            "exclude_unpriced_candidate_and_renormalize_remaining_tradable_"
            "market_caps_or_hold_cash_if_none"
        ),
        "within_eligibility_missing_price_rule": (
            "carry_last_observed_mark_and_defer_only_that_holding"
        ),
        "eligibility_exit_available_price_rule": (
            "liquidate_at_next_authenticated_open"
        ),
        "eligibility_exit_missing_price_rule": (
            "zero_recovery_conservative_sensitivity_applied_symmetrically"
        ),
        "cash_return": "0",
        "cost_bps_per_side": list(COST_BPS_SCENARIOS),
        "primary_cost_bps_per_side": PRIMARY_COST_BPS,
        "concentration_metric": (
            "invested_weight_HHI_and_inverse_HHI_excluding_cash"
        ),
        "history_normalization_mode": "TOTAL_RETURN",
        "history_value_field": "open",
        "leverage": False,
        "orders": False,
        "trading": False,
    }
    if out_of_window_collection_policy is not None:
        record["history_collection_window_policy"] = (
            out_of_window_collection_policy
        )
    if profile_id in PROFILE_IDS:
        record.update(_tilt.profile_fields())
    return {**record, "profile_sha256": _sha(record)}


_PROFILE_CANONICAL = {
    row[0]: _canonical(_build_profile(row)) for row in _PROFILE_ROWS
}


def require_market_cap_stock_portfolio_profile(profile_id):
    if type(profile_id) is not str or profile_id not in _PROFILE_CANONICAL:
        raise MarketCapStockPortfolioEvaluationError(
            "market-cap stock portfolio profile is not an exact fixed profile"
        )
    return json.loads(_PROFILE_CANONICAL[profile_id].decode("ascii"))


def require_profile(profile_id):
    """Return a detached copy of one exact market-cap profile."""

    return require_market_cap_stock_portfolio_profile(profile_id)


def constituent_etf_tickers_for_profile(profile_id):
    """Return the sole ETF holdings proxy named by the exact profile."""

    profile = require_market_cap_stock_portfolio_profile(profile_id)
    return (profile["universe_proxy_ticker"],)


def decision_sessions_for_input(value, profile_id):
    profile = require_market_cap_stock_portfolio_profile(profile_id)
    try:
        axis = value.session_axis
    except AttributeError as exc:
        raise MarketCapStockPortfolioEvaluationError(
            "market-cap evaluator lacks its authenticated session axis"
        ) from exc
    if (
        type(axis) is not tuple
        or any(type(session) is not str for session in axis)
        or tuple(sorted(set(axis))) != axis
    ):
        raise MarketCapStockPortfolioEvaluationError(
            "market-cap evaluator authenticated session axis changed"
        )
    start_session = profile["evaluation_start_session"]
    end_session = profile["evaluation_end_session"]
    try:
        start = axis.index(start_session)
        end = axis.index(end_session)
    except ValueError as exc:
        raise MarketCapStockPortfolioEvaluationError(
            "market-cap profile escaped the authenticated session axis"
        ) from exc
    period = axis[start : end + 1]
    if len(period) != profile["expected_session_count"]:
        raise MarketCapStockPortfolioEvaluationError(
            "market-cap profile session geometry changed"
        )
    decisions = []
    prior_week = None
    try:
        for session in period:
            parsed = date.fromisoformat(session)
            week = (parsed.isocalendar().year, parsed.isocalendar().week)
            if week != prior_week:
                decisions.append(session)
                prior_week = week
    except ValueError as exc:
        raise MarketCapStockPortfolioEvaluationError(
            "market-cap evaluator authenticated session axis changed"
        ) from exc
    if len(decisions) != profile["expected_decision_session_count"]:
        raise MarketCapStockPortfolioEvaluationError(
            "market-cap decision schedule geometry changed"
        )
    if any(axis.index(session) + 1 > end for session in decisions):
        raise MarketCapStockPortfolioEvaluationError(
            "market-cap decision lacks next-open execution inside its profile"
        )
    return tuple(decisions)


def expected_custom_summary_statistic_names(profile_id):
    require_market_cap_stock_portfolio_profile(profile_id)
    tilt_names = (
        (TILT_AGGREGATES_STATISTIC_NAME,)
        if profile_id in PROFILE_IDS
        else ()
    )
    return tuple(
        sorted(
            (
                META_STATISTIC_NAME,
                SELECTED_AGGREGATES_STATISTIC_NAME,
                MATCHED_AGGREGATES_STATISTIC_NAME,
                *tilt_names,
                *(
                    "ARV2_STOCK_PORTFOLIO_COST_" + str(cost)
                    for cost in COST_BPS_SCENARIOS
                ),
            )
        )
    )


@dataclasses.dataclass(frozen=True)
class _Decision:
    selected: tuple
    eligible: tuple
    market_caps: dict
    selected_weights: dict | None = None
    benchmark_weights: dict | None = None
    sector_by_security_id: dict | None = None


def _build_benchmark_tilt(market_caps, arm_scores, memberships):
    try:
        sectors = _tilt.sector_map_from_memberships(market_caps, memberships)
        return _tilt.build_benchmark_tilt(market_caps, arm_scores, sectors), sectors
    except _tilt.BoundedBenchmarkTiltError as exc:
        raise MarketCapStockPortfolioEvaluationError(str(exc)) from exc


@dataclasses.dataclass
class _ReturnAccumulator:
    cost_bps: int
    wealth: Decimal = Decimal(1)
    peak: Decimal = Decimal(1)
    maximum_drawdown: Decimal = Decimal(0)
    returns: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class _Account:
    role: str
    weights: dict = dataclasses.field(default_factory=dict)
    marks: dict = dataclasses.field(default_factory=dict)
    accumulators: dict = dataclasses.field(
        default_factory=lambda: {
            cost: _ReturnAccumulator(cost) for cost in COST_BPS_SCENARIOS
        }
    )
    turnover_sum: Decimal = Decimal(0)
    cash_weight_sum: Decimal = Decimal(0)
    holding_count_sum: int = 0
    invested_return_session_count: int = 0
    rebalance_execution_count: int = 0
    full_target_execution_count: int = 0
    underfilled_target_execution_count: int = 0
    locked_exposure_over_target_count: int = 0
    locked_sector_over_target_count: int = 0
    sector_target_underfill_count: int = 0
    entry_price_refusal_count: int = 0
    stale_mark_session_count: int = 0
    partial_rebalance_decision_count: int = 0
    stale_position_deferral_count: int = 0
    selection_exit_deferral_count: int = 0
    eligibility_exit_liquidation_count: int = 0
    eligibility_exit_zero_recovery_count: int = 0
    executed_gross_observations: list = dataclasses.field(default_factory=list)
    maximum_weight_observations: list = dataclasses.field(default_factory=list)
    hhi_observations: list = dataclasses.field(default_factory=list)
    effective_holding_observations: list = dataclasses.field(default_factory=list)


def _risk_metrics(values):
    if not values:
        return (None, None, None, None)
    returns = tuple(values)
    with localcontext(_base._context()):
        mean = _base._mean(returns)
        annual_return = +(mean * ANNUALIZATION_SESSIONS)
        if len(returns) < 2:
            return (annual_return, None, None, None)
        variance = +(
            _base._stable_sum((value - mean) ** 2 for value in returns)
            / Decimal(len(returns) - 1)
        )
        annual_volatility = +(variance.sqrt() * ANNUALIZATION_SESSIONS.sqrt())
        sharpe = (
            None
            if annual_volatility == 0
            else +(annual_return / annual_volatility)
        )
        downside = tuple(min(value, Decimal(0)) for value in returns)
        downside_deviation = +(
            (
                _base._stable_sum(value * value for value in downside)
                / Decimal(len(downside))
            ).sqrt()
            * ANNUALIZATION_SESSIONS.sqrt()
        )
        sortino = (
            None
            if downside_deviation == 0
            else +(annual_return / downside_deviation)
        )
    return annual_return, annual_volatility, sharpe, sortino


def _mean_or_zero(values):
    return Decimal(0) if not values else _base._mean(tuple(values))


def _minimum_or_zero(values):
    return Decimal(0) if not values else min(values)


def _maximum_or_zero(values):
    return Decimal(0) if not values else max(values)


class MarketCapStockPortfolioEvaluationRuntime(
    _base.PreliminaryRatingEvaluationRuntime
):
    """Capture exact R055 scores and run one deterministic cap-weighted book."""

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
        self._profile = require_market_cap_stock_portfolio_profile(profile_id)
        if type(package_id) is not str or not package_id:
            raise MarketCapStockPortfolioEvaluationError(
                "market-cap stock package id changed"
            )
        if (
            type(package_sha256) is not str
            or len(package_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in package_sha256
            )
        ):
            raise MarketCapStockPortfolioEvaluationError(
                "market-cap stock package hash changed"
            )
        if (
            type(named_figi_resolution_refusals) is not tuple
            or any(
                type(item) is not str or not item
                for item in named_figi_resolution_refusals
            )
            or named_figi_resolution_refusals
            != tuple(sorted(set(named_figi_resolution_refusals)))
        ):
            raise MarketCapStockPortfolioEvaluationError(
                "named FIGI resolution refusals must be a sorted unique tuple"
            )
        self._package_id = package_id
        self._package_sha256 = package_sha256
        self._named_figi_resolution_refusals = frozenset(
            named_figi_resolution_refusals
        )
        self._decisions = {}
        self._decision_session_count = 0
        self._sector_refused_decision_count = 0
        self._point_in_time_eligible_count_sum = 0
        self._eligible_score_count_sum = 0
        self._selected_name_count_sum = 0
        self._eligible_without_score_count = 0
        self._tilt_census = _tilt.TiltCensus()
        super().__init__(value, scratch_directory=scratch_directory)

        input_security_ids = {
            item.security_id for item in self._input.memberships
        }
        if not self._named_figi_resolution_refusals.issubset(
            input_security_ids
        ):
            raise MarketCapStockPortfolioEvaluationError(
                "named FIGI resolution refusal escaped input securities"
            )
        expected_decisions = decision_sessions_for_input(value, profile_id)
        self._market_caps = self._validate_market_cap_maps(
            eligibility_market_caps_by_decision_session,
            expected_decisions,
            input_security_ids,
        )
        self._decision_positions = frozenset(
            self._input.session_axis.index(session)
            for session in expected_decisions
        )
        self._configure_fixed_window(input_security_ids)

    def _validate_market_cap_maps(self, value, decisions, input_security_ids):
        if type(value) is not dict:
            raise MarketCapStockPortfolioEvaluationError(
                "point-in-time eligibility and market-cap maps must be an exact dict"
            )
        if (
            any(type(session) is not str for session in value)
            or set(value) != set(decisions)
            or len(value) != len(decisions)
        ):
            raise MarketCapStockPortfolioEvaluationError(
                "point-in-time market-cap decision sessions are not exhaustive"
            )
        normalized = {}
        for session in decisions:
            row = value[session]
            if type(row) is not dict or not row:
                raise MarketCapStockPortfolioEvaluationError(
                    "each point-in-time market-cap row must be a nonempty exact dict"
                )
            if any(
                type(security_id) is not str or not security_id
                for security_id in row
            ):
                raise MarketCapStockPortfolioEvaluationError(
                    "point-in-time market-cap security id changed"
                )
            if not set(row).issubset(input_security_ids):
                raise MarketCapStockPortfolioEvaluationError(
                    "point-in-time market-cap row escaped input securities"
                )
            copied = {}
            for security_id in sorted(row):
                market_cap = row[security_id]
                if (
                    type(market_cap) is not Decimal
                    or not market_cap.is_finite()
                    or market_cap <= 0
                    or (
                        len(market_cap.as_tuple().digits)
                        + abs(market_cap.as_tuple().exponent)
                        + 2
                        > MAXIMUM_MARKET_CAP_TEXT_LENGTH
                    )
                ):
                    raise MarketCapStockPortfolioEvaluationError(
                        "point-in-time market cap must be an exact positive finite Decimal"
                    )
                copied[security_id] = market_cap
            normalized[session] = copied
        return normalized

    def _configure_fixed_window(self, input_security_ids):
        sessions = self._input.session_axis
        start = sessions.index(self._profile["evaluation_start_session"])
        end = sessions.index(self._profile["evaluation_end_session"])
        history_end = end + max(_base.HORIZONS)
        if history_end >= len(sessions):
            raise MarketCapStockPortfolioEvaluationError(
                "market-cap profile lacks complete R055 H60 score maturity"
            )
        self._evaluation_positions = tuple(range(start, end + 1))
        self._prestart_indices = tuple(
            index
            for index, row in enumerate(self._input.contributions)
            if row.eligible_session_index < start
        )
        pending = defaultdict(list)
        for index, row in enumerate(self._input.contributions):
            if row.eligible_session_index >= start:
                pending[row.eligible_session_index].append(index)
        self._live_contribution_indices = {
            position: tuple(indices)
            for position, indices in pending.items()
        }
        history_ids = (
            self._input.benchmark_security_id,
            *tuple(
                sorted(
                    input_security_ids
                    - self._named_figi_resolution_refusals
                )
            ),
        )
        batch_size = self._input.history_batch_security_count
        self._history_batches = tuple(
            tuple(history_ids[index : index + batch_size])
            for index in range(0, len(history_ids), batch_size)
        )
        self._history_sessions = sessions[start : history_end + 1]
        slot_count = len(history_ids) * len(self._history_sessions)
        if (
            slot_count > _base.MAX_HISTORY_OBSERVATION_COUNT
            or slot_count > _base.MAX_HISTORY_MATRIX_SLOT_COUNT
        ):
            raise MarketCapStockPortfolioEvaluationError(
                "market-cap history observation geometry exceeds reviewed bound"
            )
        self._history_security_ids = history_ids
        self._history_security_positions = {
            security_id: index
            for index, security_id in enumerate(history_ids)
        }
        self._history_session_positions = {
            session: index
            for index, session in enumerate(self._history_sessions)
        }
        self._history_prices = [
            [None] * len(history_ids) for _session in self._history_sessions
        ]
        self._maximum_callback_count = (
            len(self._history_batches)
            + max(
                1,
                (
                    len(self._prestart_indices)
                    + self._input.signal_seed_contributions_per_callback
                    - 1
                )
                // self._input.signal_seed_contributions_per_callback,
            )
            + (
                len(self._evaluation_positions)
                + self._input.scoring_sessions_per_callback
                - 1
            )
            // self._input.scoring_sessions_per_callback
        )

    def _history_request(self, index):
        securities = self._history_batches[index]
        sessions = self._input.session_axis
        end_position = (
            sessions.index(self._profile["evaluation_end_session"])
            + max(_base.HORIZONS)
        )
        seed = {
            "schema": _base.HISTORY_REQUEST_SCHEMA,
            "request_index": index,
            "security_ids": list(securities),
            "start_session": self._profile["evaluation_start_session"],
            "end_session": sessions[end_position],
            "normalization_mode": "total_return",
            "observation": "session_open",
        }
        return _base.TotalReturnHistoryRequest(
            _base.HISTORY_REQUEST_SCHEMA,
            index,
            securities,
            seed["start_session"],
            seed["end_session"],
            "total_return",
            "session_open",
            _base._sha256(seed),
        )

    def _after_score_cross_section(
        self, position, memberships, scores, sector_refused
    ):
        if position not in self._decision_positions:
            return
        session = self._input.session_axis[position]
        axis = (PRIMARY_SOURCE_VIEW_ID, PRIMARY_SCORE_ARM)
        arm_scores = scores[axis]
        caps = self._market_caps[session]
        if self._profile["profile_id"] in PROFILE_IDS:
            eligible = tuple(
                sorted(
                    security_id
                    for security_id in caps
                    if security_id
                    not in self._named_figi_resolution_refusals
                )
            )
            eligible_caps = {
                security_id: caps[security_id] for security_id in eligible
            }
            tilt, sectors = _build_benchmark_tilt(
                eligible_caps, arm_scores, memberships
            )
            selected = eligible
            decision = _Decision(
                selected=selected,
                eligible=eligible,
                market_caps=eligible_caps,
                selected_weights=tilt.selected_weights,
                benchmark_weights=tilt.benchmark_weights,
                sector_by_security_id=sectors,
            )
            try:
                self._tilt_census.observe(tilt)
            except _tilt.BoundedBenchmarkTiltError as exc:
                raise MarketCapStockPortfolioEvaluationError(str(exc)) from exc
        else:
            eligible = tuple(
                sorted(
                    security_id
                    for security_id in caps
                    if security_id in arm_scores
                    and security_id
                    not in self._named_figi_resolution_refusals
                )
            )
            ranked = tuple(
                sorted(
                    (
                        (security_id, arm_scores[security_id])
                        for security_id in eligible
                    ),
                    key=lambda item: (-item[1], item[0]),
                )
            )
            selected_count = min(
                MAXIMUM_HOLDINGS,
                (len(ranked) + 9) // 10,
            )
            selected = tuple(
                security_id
                for security_id, _score in ranked[:selected_count]
            )
            decision = _Decision(
                selected=selected,
                eligible=eligible,
                market_caps={
                    security_id: caps[security_id]
                    for security_id in eligible
                },
            )
        self._decision_session_count += 1
        if sector_refused[axis]:
            self._sector_refused_decision_count += 1
        self._point_in_time_eligible_count_sum += len(caps)
        self._eligible_score_count_sum += sum(
            security_id in arm_scores for security_id in eligible
        )
        self._selected_name_count_sum += len(selected)
        if self._profile["profile_id"] in PROFILE_IDS:
            self._eligible_without_score_count += sum(
                security_id not in arm_scores
                for security_id in caps
                if security_id not in self._named_figi_resolution_refusals
            )
        else:
            self._eligible_without_score_count += len(
                set(caps) - set(eligible)
            )
        self._decisions[session] = decision

    def _price(self, security_id, position):
        security_position = self._history_security_positions.get(security_id)
        if security_position is None:
            return None
        session = self._input.session_axis[position]
        history_position = self._history_session_positions.get(session)
        if history_position is None:
            return None
        value = self._history_prices[history_position][security_position]
        if value is None:
            return None
        return _base._decimal(
            value, "market-cap stock adjusted open", positive=True
        )

    def _targets(self, account, decision, desired, position, locked):
        if decision.sector_by_security_id is not None:
            frozen_weights = (
                decision.selected_weights
                if account.role == "selected"
                else decision.benchmark_weights
            )
            if frozen_weights is None or account.role not in (
                "selected", "matched"
            ):
                raise MarketCapStockPortfolioEvaluationError(
                    "sector-neutral frozen target changed"
                )
            tradable = []
            for security_id in sorted(desired):
                if security_id in locked:
                    continue
                if self._price(security_id, position) is None:
                    account.entry_price_refusal_count += 1
                    continue
                tradable.append(security_id)
            try:
                target = _tilt.executable_selected_target(
                    frozen_weights,
                    decision.sector_by_security_id,
                    desired,
                    tuple(tradable),
                    locked,
                )
            except _tilt.BoundedBenchmarkTiltError as exc:
                raise MarketCapStockPortfolioEvaluationError(str(exc)) from exc
            account.locked_sector_over_target_count += (
                target.locked_sector_over_target_count
            )
            account.sector_target_underfill_count += (
                target.sector_target_underfill_count
            )
            return target.weights
        with localcontext(_base._context()):
            locked_gross = +_base._stable_sum(locked.values())
            remaining = +max(
                Decimal(0), TARGET_GROSS_EXPOSURE - locked_gross
            )
        tradable = []
        for security_id in desired:
            if security_id in locked:
                continue
            if self._price(security_id, position) is None:
                account.entry_price_refusal_count += 1
                continue
            tradable.append(security_id)
        if account.role == "selected":
            if len(locked) > MAXIMUM_HOLDINGS:
                raise MarketCapStockPortfolioEvaluationError(
                    "stale selected holdings exceed the exact holdings cap"
                )
            tradable = tradable[: MAXIMUM_HOLDINGS - len(locked)]
        elif account.role != "matched":
            raise MarketCapStockPortfolioEvaluationError(
                "market-cap account role changed"
            )
        targets = dict(locked)
        if not tradable or remaining == 0:
            return targets
        with localcontext(_base._context()):
            cap_total = +_base._stable_sum(
                decision.market_caps[security_id]
                for security_id in tradable
            )
            allocated = Decimal(0)
            for security_id in sorted(tradable)[:-1]:
                weight = +(
                    remaining
                    * decision.market_caps[security_id]
                    / cap_total
                )
                targets[security_id] = weight
                allocated = +(allocated + weight)
            last = sorted(tradable)[-1]
            targets[last] = +(remaining - allocated)
        return targets

    @staticmethod
    def _observe_target(account):
        with localcontext(_base._context()):
            gross = +_base._stable_sum(account.weights.values())
            account.executed_gross_observations.append(gross)
            if gross == 0:
                return
            maximum_weight = max(account.weights.values())
            hhi = +_base._stable_sum(
                (weight / gross) ** 2
                for weight in account.weights.values()
            )
            effective = +(Decimal(1) / hhi)
        account.maximum_weight_observations.append(maximum_weight)
        account.hhi_observations.append(hhi)
        account.effective_holding_observations.append(effective)

    def _advance_account(self, account, position, decision, desired):
        starting_invested = _base._stable_sum(account.weights.values())
        eligible = None if decision is None else frozenset(decision.eligible)
        ratios = {}
        stale = set()
        eligibility_exits = set()
        for security_id in tuple(sorted(account.weights)):
            prior = account.marks.get(security_id)
            if prior is None:
                raise MarketCapStockPortfolioEvaluationError(
                    "held market-cap stock lacks its prior observed mark"
                )
            current = self._price(security_id, position)
            exits = eligible is not None and security_id not in eligible
            if exits:
                eligibility_exits.add(security_id)
                if current is None:
                    ratios[security_id] = Decimal(0)
                    account.eligibility_exit_zero_recovery_count += 1
                else:
                    with localcontext(_base._context()):
                        ratios[security_id] = +(current / prior)
                    account.eligibility_exit_liquidation_count += 1
                continue
            if current is None:
                stale.add(security_id)
                ratios[security_id] = Decimal(1)
                continue
            with localcontext(_base._context()):
                ratios[security_id] = +(current / prior)
            account.marks[security_id] = current
        if stale:
            account.stale_mark_session_count += 1
        with localcontext(_base._context()):
            gross_return = +_base._stable_sum(
                weight * (ratios[security_id] - Decimal(1))
                for security_id, weight in account.weights.items()
            )
            gross_multiplier = +(Decimal(1) + gross_return)
            if gross_multiplier <= 0:
                raise MarketCapStockPortfolioEvaluationError(
                    "market-cap stock portfolio gross return is not survivable"
                )
            pretrade = {
                security_id: +(
                    weight * ratios[security_id] / gross_multiplier
                )
                for security_id, weight in account.weights.items()
            }
            drifted = {
                security_id: weight
                for security_id, weight in pretrade.items()
                if security_id not in eligibility_exits
            }
        for security_id in eligibility_exits:
            account.marks.pop(security_id, None)

        turnover = Decimal(0)
        if desired is not None:
            locked = {
                security_id: drifted[security_id]
                for security_id in sorted(stale)
            }
            if account.role == "selected":
                account.selection_exit_deferral_count += sum(
                    security_id not in desired for security_id in stale
                )
            targets = self._targets(
                account, decision, desired, position, locked
            )
            with localcontext(_base._context()):
                turnover = +_base._stable_sum(
                    abs(
                        targets.get(security_id, Decimal(0))
                        - pretrade.get(security_id, Decimal(0))
                    )
                    for security_id in sorted(set(targets) | set(pretrade))
                    if security_id not in stale
                )
                gross = +_base._stable_sum(targets.values())
            account.rebalance_execution_count += 1
            if stale:
                account.partial_rebalance_decision_count += 1
                account.stale_position_deferral_count += len(stale)
            if gross == TARGET_GROSS_EXPOSURE:
                account.full_target_execution_count += 1
            elif gross < TARGET_GROSS_EXPOSURE:
                account.underfilled_target_execution_count += 1
            else:
                account.locked_exposure_over_target_count += 1
            account.weights = targets
            account.marks = {
                **{
                    security_id: account.marks[security_id]
                    for security_id in locked
                },
                **{
                    security_id: self._price(security_id, position)
                    for security_id in targets
                    if security_id not in locked
                },
            }
            self._observe_target(account)
        else:
            account.weights = drifted

        with localcontext(_base._context()):
            account.turnover_sum = +(account.turnover_sum + turnover)
            invested = +_base._stable_sum(account.weights.values())
            cash_weight = +(Decimal(1) - invested)
            if cash_weight < Decimal("-1e-18"):
                raise MarketCapStockPortfolioEvaluationError(
                    "market-cap stock portfolio exceeds one hundred percent"
                )
            account.cash_weight_sum = +(
                account.cash_weight_sum + max(Decimal(0), cash_weight)
            )
            for cost, accumulator in account.accumulators.items():
                net = +(
                    gross_return
                    - Decimal(cost) / Decimal(10000) * turnover
                )
                if net <= -1:
                    raise MarketCapStockPortfolioEvaluationError(
                        "market-cap stock portfolio net return is not survivable"
                    )
                accumulator.returns.append(net)
                accumulator.wealth = +(
                    accumulator.wealth * (Decimal(1) + net)
                )
                accumulator.peak = max(accumulator.peak, accumulator.wealth)
                drawdown = +(
                    accumulator.wealth / accumulator.peak - Decimal(1)
                )
                accumulator.maximum_drawdown = min(
                    accumulator.maximum_drawdown, drawdown
                )
        account.holding_count_sum += len(account.weights)
        if starting_invested > 0:
            account.invested_return_session_count += 1

    def _simulate(self):
        selected = _Account("selected")
        matched = _Account("matched")
        sessions = self._input.session_axis
        start = sessions.index(self._profile["evaluation_start_session"])
        end = sessions.index(self._profile["evaluation_end_session"])
        first_execution = start + 1
        benchmark = self._input.benchmark_security_id
        prior_benchmark = self._price(benchmark, first_execution)
        if prior_benchmark is None:
            raise MarketCapStockPortfolioEvaluationError(
                "SPY lacks the first market-cap execution adjusted open"
            )
        benchmark_wealth = Decimal(1)
        benchmark_observations = []
        for position in range(first_execution, end + 1):
            current_benchmark = self._price(benchmark, position)
            if current_benchmark is None:
                raise MarketCapStockPortfolioEvaluationError(
                    "SPY lacks a market-cap portfolio adjusted open"
                )
            if self._profile["profile_id"] in PROFILE_IDS:
                benchmark_observations.append(
                    (sessions[position], current_benchmark)
                )
            if position != first_execution:
                with localcontext(_base._context()):
                    benchmark_wealth = +(
                        benchmark_wealth
                        * current_benchmark
                        / prior_benchmark
                    )
            prior_benchmark = current_benchmark
            decision = self._decisions.get(sessions[position - 1])
            self._advance_account(
                selected,
                position,
                decision,
                None if decision is None else decision.selected,
            )
            self._advance_account(
                matched,
                position,
                decision,
                None if decision is None else decision.eligible,
            )
        return_count = end - start
        if return_count != self._profile["expected_return_session_count"]:
            raise MarketCapStockPortfolioEvaluationError(
                "market-cap return-session geometry changed"
            )
        benchmark_binding = None
        if self._profile["profile_id"] in PROFILE_IDS:
            try:
                benchmark_binding = _tilt.build_benchmark_series_binding(
                    tuple(benchmark_observations),
                    sessions[first_execution : end + 1],
                    logical_benchmark_id=BENCHMARK_LOGICAL_ID,
                )
            except _tilt.BoundedBenchmarkTiltError as exc:
                raise MarketCapStockPortfolioEvaluationError(str(exc)) from exc
            if (
                benchmark_binding.observation_count != return_count
                or benchmark_binding.return_interval_count
                != return_count - 1
            ):
                raise MarketCapStockPortfolioEvaluationError(
                    "benchmark used-series geometry changed"
                )
        return (
            selected,
            matched,
            benchmark_wealth,
            return_count,
            benchmark_binding,
        )

    def _tilt_aggregates(self):
        try:
            value = self._tilt_census.aggregates()
        except _tilt.BoundedBenchmarkTiltError as exc:
            raise MarketCapStockPortfolioEvaluationError(str(exc)) from exc
        if value["decision_session_count"] != self._decision_session_count:
            raise MarketCapStockPortfolioEvaluationError(
                "benchmark tilt decision census changed"
            )
        return value

    @staticmethod
    def _cell_status(selected, matched, return_count):
        if (
            return_count < 252
            or selected.invested_return_session_count
            < MINIMUM_INVESTED_RETURN_SESSIONS
        ):
            return "INCONCLUSIVE_UNDERFILLED"
        if (
            selected.eligibility_exit_zero_recovery_count
            or matched.eligibility_exit_zero_recovery_count
        ):
            return "PRELIMINARY_DESCRIPTIVE_ZERO_RECOVERY_SENSITIVITY"
        if selected.stale_mark_session_count or matched.stale_mark_session_count:
            return "PRELIMINARY_DESCRIPTIVE_STALE_MARK_SENSITIVITY"
        if (
            selected.underfilled_target_execution_count
            or matched.underfilled_target_execution_count
        ):
            return "PRELIMINARY_DESCRIPTIVE_EXPOSURE_UNDERFILL"
        return "PRELIMINARY_DESCRIPTIVE_AVAILABLE"

    def _cell(self, cost, selected, matched, benchmark_wealth, return_count):
        selected_accumulator = selected.accumulators[cost]
        matched_accumulator = matched.accumulators[cost]
        annual, volatility, sharpe, sortino = _risk_metrics(
            selected_accumulator.returns
        )
        matched_annual, matched_volatility, matched_sharpe, matched_sortino = (
            _risk_metrics(matched_accumulator.returns)
        )
        with localcontext(_base._context()):
            selected_return = +(selected_accumulator.wealth - Decimal(1))
            matched_return = +(matched_accumulator.wealth - Decimal(1))
            spy_return = +(benchmark_wealth - Decimal(1))
            selected_minus_matched = +(selected_return - matched_return)
            selected_minus_spy = +(selected_return - spy_return)
            average_turnover = +(
                selected.turnover_sum / Decimal(return_count)
            )
            average_cash = +(
                selected.cash_weight_sum / Decimal(return_count)
            )
            matched_average_turnover = +(
                matched.turnover_sum / Decimal(return_count)
            )
            matched_average_cash = +(
                matched.cash_weight_sum / Decimal(return_count)
            )
        return {
            "schema": PORTFOLIO_CELL_SCHEMA,
            "profile_id": self._profile["profile_id"],
            "cost_bps_per_side": cost,
            "primary_cost_scenario": cost == PRIMARY_COST_BPS,
            "status": self._cell_status(selected, matched, return_count),
            "return_session_count": return_count,
            "invested_return_session_count": (
                selected.invested_return_session_count
            ),
            "return_metric_conditioning": (
                "zero_recovery_for_missing_eligibility_exits_and_stale_mark_"
                "carry_with_trade_deferral_within_eligibility"
            ),
            "risk_metrics_are_price_proxy_conditioned": bool(
                selected.eligibility_exit_zero_recovery_count
                or matched.eligibility_exit_zero_recovery_count
                or selected.stale_mark_session_count
                or matched.stale_mark_session_count
            ),
            "exposure_underfill_present": bool(
                selected.underfilled_target_execution_count
                or matched.underfilled_target_execution_count
            ),
            "cumulative_return": _decimal_text(selected_return),
            "matched_eligible_stock_cumulative_return": _decimal_text(
                matched_return
            ),
            "spy_cumulative_return": _decimal_text(spy_return),
            "cumulative_return_minus_matched": _decimal_text(
                selected_minus_matched
            ),
            "cumulative_return_minus_spy": _decimal_text(
                selected_minus_spy
            ),
            "annualized_arithmetic_return": _decimal_text(annual),
            "annualized_volatility": _decimal_text(volatility),
            "zero_rate_sharpe": None if sharpe is None else _decimal_text(sharpe),
            "zero_rate_sortino": None if sortino is None else _decimal_text(sortino),
            "maximum_drawdown": _decimal_text(
                selected_accumulator.maximum_drawdown
            ),
            "average_daily_two_sided_turnover": _decimal_text(
                average_turnover
            ),
            "average_cash_weight": _decimal_text(
                average_cash
            ),
            "matched_annualized_arithmetic_return": _decimal_text(
                matched_annual
            ),
            "matched_annualized_volatility": _decimal_text(
                matched_volatility
            ),
            "matched_zero_rate_sharpe": (
                None
                if matched_sharpe is None
                else _decimal_text(matched_sharpe)
            ),
            "matched_zero_rate_sortino": (
                None
                if matched_sortino is None
                else _decimal_text(matched_sortino)
            ),
            "matched_maximum_drawdown": _decimal_text(
                matched_accumulator.maximum_drawdown
            ),
            "matched_average_daily_two_sided_turnover": _decimal_text(
                matched_average_turnover
            ),
            "matched_average_cash_weight": _decimal_text(
                matched_average_cash
            ),
            "leverage": False,
            "orders_submitted": 0,
            "formal_accept_reject_disposition": None,
        }

    def _build_summary(self):
        expected = tuple(
            self._input.session_axis[position]
            for position in sorted(self._decision_positions)
        )
        if tuple(sorted(self._decisions)) != expected:
            raise MarketCapStockPortfolioEvaluationError(
                "market-cap R055 decision-score census is not exhaustive"
            )
        (
            selected,
            matched,
            benchmark_wealth,
            return_count,
            benchmark_binding,
        ) = self._simulate()
        cells = [
            self._cell(
                cost, selected, matched, benchmark_wealth, return_count
            )
            for cost in COST_BPS_SCENARIOS
        ]
        with localcontext(_base._context()):
            decision_count = Decimal(self._decision_session_count)
            mean_input_eligible = +(
                Decimal(self._point_in_time_eligible_count_sum)
                / decision_count
            )
            mean_score_eligible = +(
                Decimal(self._eligible_score_count_sum) / decision_count
            )
            mean_selected = +(
                Decimal(self._selected_name_count_sum) / decision_count
            )
        record = {
            "schema": SUMMARY_SCHEMA,
            "contract_id": CONTRACT_ID,
            "profile": dict(self._profile),
            "package_id": self._package_id,
            "package_sha256": self._package_sha256,
            "input_manifest_id": self._input.manifest_id,
            "input_manifest_sha256": self._input.manifest_sha256,
            "status": "PRELIMINARY_ACCEPTED_RISK_MARKET_CAP_STOCK_PORTFOLIO",
            "decision_session_count": self._decision_session_count,
            "portfolio_return_session_count": return_count,
            "mean_point_in_time_eligible_count": _decimal_text(
                mean_input_eligible
            ),
            "mean_eligible_score_count": _decimal_text(
                mean_score_eligible
            ),
            "mean_selected_name_count": _decimal_text(mean_selected),
            "eligible_without_R055_score_count": (
                self._eligible_without_score_count
            ),
            "sector_refused_decision_count": (
                self._sector_refused_decision_count
            ),
            "named_figi_resolution_refusal_count": len(
                self._named_figi_resolution_refusals
            ),
            "selected_aggregates": _tilt.account_aggregates(
                selected,
                return_count,
                self._profile["profile_id"] in PROFILE_IDS,
            ),
            "matched_aggregates": _tilt.account_aggregates(
                matched,
                return_count,
                self._profile["profile_id"] in PROFILE_IDS,
            ),
            "r055_signal_rule_changed": False,
            "point_in_time_market_cap_weighting": True,
            "selected_and_matched_target_same_gross": True,
            "market_cap_values_in_summary": False,
            "raw_security_ids_in_summary": False,
            "raw_price_rows_in_summary": False,
            "formal_result": False,
            "alpha_claim_authorized": False,
            "economic_portfolio_evaluation": True,
            "leverage": False,
            "deployment": False,
            "orders": False,
            "trading": False,
            "portfolio_cells": cells,
        }
        if self._profile["profile_id"] in PROFILE_IDS:
            if type(benchmark_binding) is not _tilt.BenchmarkSeriesBinding:
                raise MarketCapStockPortfolioEvaluationError(
                    "prospective benchmark series binding changed"
                )
            record["analyst_revisions_role"] = (
                "bounded_helper_overlay_not_an_admission_gate"
            )
            record["tilt_aggregates"] = self._tilt_aggregates()
            record.update(benchmark_binding.summary_fields())
        elif benchmark_binding is not None:
            raise MarketCapStockPortfolioEvaluationError(
                "historical summary acquired a benchmark series binding"
            )
        digest = _sha(record)
        return {
            **record,
            "summary_id": "arv2-market-cap-stock-summary-" + digest[:24],
            "summary_sha256": digest,
        }

    def custom_summary_statistics(self):
        summary = self.aggregate_summary()
        cells = summary.pop("portfolio_cells")
        profile = summary.pop("profile")
        selected_aggregates = summary.pop("selected_aggregates")
        matched_aggregates = summary.pop("matched_aggregates")
        tilt_aggregates = summary.pop("tilt_aggregates", None)
        expected_profile = require_market_cap_stock_portfolio_profile(
            self._profile["profile_id"]
        )
        if profile != expected_profile:
            raise MarketCapStockPortfolioEvaluationError(
                "market-cap stock summary profile changed"
            )
        summary["profile_id"] = profile["profile_id"]
        summary["profile_sha256"] = profile["profile_sha256"]
        output = {
            META_STATISTIC_NAME: _canonical(summary).decode("ascii"),
            SELECTED_AGGREGATES_STATISTIC_NAME: _canonical(
                selected_aggregates
            ).decode("ascii"),
            MATCHED_AGGREGATES_STATISTIC_NAME: _canonical(
                matched_aggregates
            ).decode("ascii"),
        }
        if self._profile["profile_id"] in PROFILE_IDS:
            if type(tilt_aggregates) is not dict:
                raise MarketCapStockPortfolioEvaluationError(
                    "benchmark tilt aggregate fragment changed"
                )
            output[TILT_AGGREGATES_STATISTIC_NAME] = _canonical(
                tilt_aggregates
            ).decode("ascii")
        elif tilt_aggregates is not None:
            raise MarketCapStockPortfolioEvaluationError(
                "historical market-cap summary acquired tilt fields"
            )
        for cell in cells:
            output[
                "ARV2_STOCK_PORTFOLIO_COST_"
                + str(cell["cost_bps_per_side"])
            ] = _canonical(cell).decode("ascii")
        if tuple(sorted(output)) != expected_custom_summary_statistic_names(
            self._profile["profile_id"]
        ):
            raise MarketCapStockPortfolioEvaluationError(
                "market-cap stock custom summary inventory changed"
            )
        if any(
            len(key) > 64 or len(value) > 4096
            for key, value in output.items()
        ):
            raise MarketCapStockPortfolioEvaluationError(
                "market-cap stock custom summary exceeded compact bound"
            )
        return dict(sorted(output.items()))


__all__ = (
    "ALL_PROFILE_IDS",
    "ANNUALIZATION_SESSIONS",
    "CONTRACT_ID",
    "COST_BPS_SCENARIOS",
    "MAXIMUM_HOLDINGS",
    "MAXIMUM_ABSOLUTE_OVERWEIGHT",
    "MAXIMUM_HHI_MULTIPLE",
    "MAXIMUM_ONE_WAY_ACTIVE_SHARE",
    "MAXIMUM_RELATIVE_TILT",
    "MATCHED_AGGREGATES_STATISTIC_NAME",
    "META_STATISTIC_NAME",
    "MINIMUM_TILT_NEGATIVE_SCORE_COUNT",
    "MINIMUM_TILT_POSITIVE_SCORE_COUNT",
    "MINIMUM_TILT_RANKED_NAME_COUNT",
    "MarketCapStockPortfolioEvaluationError",
    "MarketCapStockPortfolioEvaluationRuntime",
    "PORTFOLIO_CELL_SCHEMA",
    "PORTFOLIO_WEIGHT_QUANTUM",
    "PRIMARY_COST_BPS",
    "PRIMARY_SCORE_ARM",
    "PRIMARY_SOURCE_VIEW_ID",
    "PROFILE_IDS",
    "PROFILE_SCHEMA",
    "OUT_OF_WINDOW_COLLECTION_POLICY",
    "QQQ_PROFILE_IDS",
    "QQQ_2019_2023_PROFILE_ID",
    "QQQ_2019_2023_V2_PROFILE_ID",
    "QQQ_2021_2025_PROFILE_ID",
    "QQQ_2021_2025_V2_PROFILE_ID",
    "QQQ_2021_2025_V3_PROFILE_ID",
    "QQQ_2023_2025_PROFILE_ID",
    "QQQ_2023_2025_V2_PROFILE_ID",
    "SPY_2019_2023_PROFILE_ID",
    "SPY_2019_2023_V2_PROFILE_ID",
    "SPY_2021_2025_PROFILE_ID",
    "SPY_2021_2025_V2_PROFILE_ID",
    "SPY_2021_2025_V3_PROFILE_ID",
    "SPY_2023_2025_PROFILE_ID",
    "SPY_2023_2025_V2_PROFILE_ID",
    "SPY_PROFILE_IDS",
    "SELECTED_AGGREGATES_STATISTIC_NAME",
    "SUMMARY_SCHEMA",
    "TARGET_GROSS_EXPOSURE",
    "TILT_AGGREGATES_SCHEMA",
    "TILT_AGGREGATES_STATISTIC_NAME",
    "TILT_ENABLED",
    "TILT_UNDERFILLED",
    "V1_PROFILE_IDS",
    "V2_PROFILE_IDS",
    "constituent_etf_tickers_for_profile",
    "decision_sessions_for_input",
    "expected_custom_summary_statistic_names",
    "require_profile",
    "require_market_cap_stock_portfolio_profile",
)
