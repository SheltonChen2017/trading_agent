"""Aggregate-only direct-stock economics for the accepted-risk ARV2 signal.

The evaluator reuses the exact R055 score path and authenticated TOTAL_RETURN
adjusted-open matrix.  It is intentionally a preliminary arithmetic backtest,
not a broker simulation or a formal terminal-payoff result.
"""

import dataclasses
import hashlib
import json
from datetime import date
from decimal import Decimal, localcontext

try:
    import accepted_risk_preliminary_rating_evaluator as _base
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_rating_evaluator as _base,
    )


class AcceptedRiskStockPortfolioError(_base.PreliminaryRatingEvaluationError):
    """The stock portfolio profile or arithmetic result is inexact."""


PROFILE_SCHEMA = "arv2-accepted-risk-stock-portfolio-profile-v2"
PROFILE_ID = "arv2-stock-long-only-2021-2025-r065-v2"
SP500_PROFILE_ID = (
    "arv2-stock-long-only-spy-holdings-proxy-2021-2025-r066-v1"
)
NASDAQ100_PROFILE_ID = (
    "arv2-stock-long-only-qqq-holdings-proxy-2021-2025-r067-v1"
)
UNION_PROFILE_ID = (
    "arv2-stock-long-only-spy-qqq-union-2021-2025-r068-v1"
)
VARIANT_PROFILE_IDS = (
    SP500_PROFILE_ID,
    NASDAQ100_PROFILE_ID,
    UNION_PROFILE_ID,
)
UNIVERSE_PROFILE_IDS = VARIANT_PROFILE_IDS
ALL_PROFILE_IDS = (PROFILE_ID, *VARIANT_PROFILE_IDS)
PROFILE_IDS = ALL_PROFILE_IDS
CONTRACT_ID = "arv2-accepted-risk-stock-portfolio-v2"
SUMMARY_SCHEMA = "arv2-accepted-risk-stock-portfolio-summary-v4"
PORTFOLIO_CELL_SCHEMA = "arv2-accepted-risk-stock-portfolio-cell-v2"
DECISION_START_SESSION = "2021-01-04"
DECISION_END_SESSION = "2025-12-29"
MEASUREMENT_END_SESSION = "2025-12-31"
EXPECTED_DECISION_SESSION_COUNT = 261
EXPECTED_RETURN_SESSION_COUNT = 1254
PRIMARY_SOURCE_VIEW_ID = _base.SOURCE_VIEW_IDS[1]
PRIMARY_SCORE_ARM = "firm_specific"
MAXIMUM_HOLDINGS = 50
TARGET_GROSS_EXPOSURE = Decimal("0.98")
STOCK_WEIGHT_CAP = TARGET_GROSS_EXPOSURE / Decimal(MAXIMUM_HOLDINGS)
PRIMARY_COST_BPS = 10
COST_BPS_SCENARIOS = (0, 5, PRIMARY_COST_BPS, 20)
MINIMUM_INVESTED_RETURN_SESSIONS = 50
ANNUALIZATION_SESSIONS = Decimal("252")

_UNIVERSE_VARIANT_CONFIGS = (
    (
        SP500_PROFILE_ID,
        "spy_holdings_proxy_for_sp500",
        ("SPY",),
        (
            "SPY_holdings_proxy_not_official_SP500_index_membership"
        ),
        None,
    ),
    (
        NASDAQ100_PROFILE_ID,
        "qqq_holdings_proxy_for_nasdaq_100",
        ("QQQ",),
        (
            "QQQ_holdings_proxy_for_Nasdaq_100_not_all_Nasdaq_listed_stocks"
        ),
        None,
    ),
    (
        UNION_PROFILE_ID,
        "spy_qqq_holdings_security_id_union",
        ("SPY", "QQQ"),
        (
            "union_of_SPY_and_QQQ_holdings_proxies_not_official_SP500_or_all_"
            "Nasdaq_listed_membership"
        ),
        (
            "deduplicate_by_authenticated_security_id_union"
        ),
    ),
)


def _universe_variant_config(profile_id):
    for config in _UNIVERSE_VARIANT_CONFIGS:
        if config[0] == profile_id:
            return config
    return None


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
    if not value.is_finite():
        raise AcceptedRiskStockPortfolioError("portfolio metric is not finite")
    if value == 0:
        return "0"
    return format(value, "f")


def _profile_record(profile_id):
    if type(profile_id) is not str or profile_id not in ALL_PROFILE_IDS:
        raise AcceptedRiskStockPortfolioError(
            "stock portfolio profile is not the exact frozen profile"
        )
    record = {
        "schema": PROFILE_SCHEMA,
        "profile_id": profile_id,
        "contract_id": CONTRACT_ID,
        "decision_start_session": DECISION_START_SESSION,
        "decision_end_session": DECISION_END_SESSION,
        "measurement_end_session": MEASUREMENT_END_SESSION,
        "expected_decision_session_count": EXPECTED_DECISION_SESSION_COUNT,
        "expected_return_session_count": EXPECTED_RETURN_SESSION_COUNT,
        "source_view_id": PRIMARY_SOURCE_VIEW_ID,
        "score_arm": PRIMARY_SCORE_ARM,
        "rebalance_schedule": "first_authenticated_session_of_each_ISO_week",
        "execution_timing": "next_authenticated_session_open",
        "selection": (
            "top_decile_of_resolvable_score_bearing_universe_capped_at_50_"
            "ordered_by_score_then_security_id_without_absolute_score_gate"
        ),
        "maximum_holdings": MAXIMUM_HOLDINGS,
        "target_gross_exposure": _decimal_text(TARGET_GROSS_EXPOSURE),
        "stock_weight_cap": _decimal_text(STOCK_WEIGHT_CAP),
        "exposure_underfill_disposition": (
            "retain_residual_cash_and_label_every_result_cell"
        ),
        "cash_return": "0",
        "cost_bps_per_side": list(COST_BPS_SCENARIOS),
        "primary_cost_bps_per_side": PRIMARY_COST_BPS,
        "matched_benchmark": (
            "weekly_equal_weight_all_resolvable_score_bearing_members_at_"
            "decision_time_targeting_the_signal_sleeves_actual_executed_"
            "gross_exposure_with_failed_entries_left_cash_and_only_stale_"
            "positions_locked"
        ),
        "within_membership_missing_price": (
            "carry_last_observed_mark_and_weight_defer_only_the_locked_"
            "position_and_rebalance_tradable_holdings_within_remaining_gross"
        ),
        "account_wide_stale_rebalance_deferral": False,
        "stale_position_turnover": "excluded_until_current_price_is_available",
        "locked_position_gross_over_target": (
            "preserve_the_locked_weight_and_assign_zero_remaining_budget"
        ),
        "membership_end_missing_price": (
            "assume_zero_terminal_value_as_a_conservative_lower_bound"
        ),
        "membership_end_available_price": "liquidate_at_next_authenticated_open",
        "absolute_positive_score_gate": False,
        "named_figi_resolution_refusals_excluded_before_ranking": True,
        "liquidity_filter_applied": False,
        "terminal_payoff_applied": False,
        "leverage": False,
    }
    variant = _universe_variant_config(profile_id)
    if variant is not None:
        (
            _variant_profile_id,
            universe_id,
            constituent_etf_tickers,
            universe_scope_disclaimer,
            multi_etf_combination,
        ) = variant
        record.update(
            {
                "eligibility_universe": universe_id,
                "constituent_source": "QuantConnect_US_ETF_Constituents",
                "constituent_etf_tickers": list(constituent_etf_tickers),
                "constituent_snapshot_selection": (
                    "latest_collection_EndTime_strictly_before_decision_"
                    "midnight_America_New_York"
                ),
                "maximum_constituent_snapshot_age_calendar_days": 10,
                "constituent_last_update_required": True,
                "constituent_last_update_not_after_collection": True,
                "maximum_constituent_last_update_age_calendar_days": 10,
                "constituent_positive_weight_only": True,
                "minimum_constituent_total_positive_weight": "0.95",
                "maximum_constituent_total_positive_weight": "1.05",
                "constituent_mapping_key": (
                    "exact_QuantConnect_security_identifier"
                ),
                "minimum_mapped_positive_weight_fraction": "0.99",
                "multi_etf_combination": multi_etf_combination,
                "universe_scope_disclaimer": universe_scope_disclaimer,
                "eligibility_security_ids_by_decision_session_required": True,
                "eligibility_filter_application": (
                    "before_top_decile_ranking_and_matched_comparator"
                ),
            }
        )
    digest = _sha(record)
    return {**record, "profile_sha256": digest}


_PROFILE_CANONICAL_ROWS = tuple(
    (profile_id, _canonical(_profile_record(profile_id)))
    for profile_id in ALL_PROFILE_IDS
)
_PROFILE = json.loads(_PROFILE_CANONICAL_ROWS[0][1].decode("ascii"))


def require_stock_portfolio_profile(profile_id):
    if type(profile_id) is not str or profile_id not in ALL_PROFILE_IDS:
        raise AcceptedRiskStockPortfolioError(
            "stock portfolio profile is not the exact frozen profile"
        )
    for candidate_profile_id, profile_bytes in _PROFILE_CANONICAL_ROWS:
        if candidate_profile_id == profile_id:
            return json.loads(profile_bytes.decode("ascii"))
    raise AcceptedRiskStockPortfolioError(
        "stock portfolio profile is not the exact frozen profile"
    )


def constituent_etf_tickers_for_profile(profile_id):
    require_stock_portfolio_profile(profile_id)
    variant = _universe_variant_config(profile_id)
    return () if variant is None else tuple(variant[2])


def decision_sessions_for_input(value):
    try:
        session_axis = value.session_axis
    except AttributeError as exc:
        raise AcceptedRiskStockPortfolioError(
            "stock portfolio input lacks its authenticated session axis"
        ) from exc
    if (
        type(session_axis) is not tuple
        or any(type(session) is not str for session in session_axis)
        or tuple(sorted(set(session_axis))) != session_axis
    ):
        raise AcceptedRiskStockPortfolioError(
            "stock portfolio authenticated session axis changed"
        )
    prior_week = None
    sessions = []
    try:
        for session in session_axis:
            if not (DECISION_START_SESSION <= session <= DECISION_END_SESSION):
                continue
            parsed = date.fromisoformat(session)
            week = (parsed.isocalendar().year, parsed.isocalendar().week)
            if week != prior_week:
                sessions.append(session)
                prior_week = week
    except ValueError as exc:
        raise AcceptedRiskStockPortfolioError(
            "stock portfolio authenticated session axis changed"
        ) from exc
    if len(sessions) != EXPECTED_DECISION_SESSION_COUNT:
        raise AcceptedRiskStockPortfolioError(
            "stock portfolio decision schedule geometry changed"
        )
    return tuple(sessions)


def expected_custom_summary_statistic_names(profile_id=PROFILE_ID):
    require_stock_portfolio_profile(profile_id)
    return tuple(
        sorted(
            (
                "ARV2_STOCK_PORTFOLIO_META",
                *(
                    "ARV2_STOCK_PORTFOLIO_COST_" + str(cost)
                    for cost in COST_BPS_SCENARIOS
                ),
            )
        )
    )


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
    selected_execution_count: int = 0
    rebalance_execution_count: int = 0
    full_target_execution_count: int = 0
    underfilled_target_execution_count: int = 0
    executed_target_gross_sum: Decimal = Decimal(0)
    entry_price_refusal_count: int = 0
    stale_mark_session_count: int = 0
    deferred_rebalance_count: int = 0
    partial_rebalance_decision_count: int = 0
    stale_position_deferral_count: int = 0
    locked_gross_sum_at_partial_decisions: Decimal = Decimal(0)
    locked_exposure_over_target_count: int = 0
    membership_end_liquidation_count: int = 0
    membership_end_zero_recovery_count: int = 0
    membership_end_entry_refusal_count: int = 0


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
            _base._stable_sum((value - mean) * (value - mean) for value in returns)
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


class StockPortfolioEvaluationRuntime(_base.PreliminaryRatingEvaluationRuntime):
    """Reuse R055 scoring, then evaluate one fixed weekly long-only portfolio."""

    def __init__(
        self,
        value,
        *,
        profile_id,
        package_id,
        package_sha256,
        named_figi_resolution_refusals,
        eligible_security_ids_by_decision_session=None,
        scratch_directory=None,
    ):
        self._profile = require_stock_portfolio_profile(profile_id)
        if type(package_id) is not str or not package_id:
            raise AcceptedRiskStockPortfolioError("stock package id changed")
        if (
            type(package_sha256) is not str
            or len(package_sha256) != 64
            or any(character not in "0123456789abcdef" for character in package_sha256)
        ):
            raise AcceptedRiskStockPortfolioError("stock package hash changed")
        self._package_id = package_id
        self._package_sha256 = package_sha256
        if (
            type(named_figi_resolution_refusals) is not tuple
            or any(
                type(item) is not str
                for item in named_figi_resolution_refusals
            )
            or named_figi_resolution_refusals
            != tuple(sorted(set(named_figi_resolution_refusals)))
        ):
            raise AcceptedRiskStockPortfolioError(
                "named FIGI resolution refusals must be a sorted unique tuple"
            )
        self._decisions = {}
        self._decision_session_count = 0
        self._signal_selected_decision_count = 0
        self._sector_refused_decision_count = 0
        self._eligible_score_count_sum = 0
        self._selected_name_count_sum = 0
        super().__init__(value, scratch_directory=scratch_directory)
        input_security_ids = {
            item.security_id for item in self._input.memberships
        }
        if not set(named_figi_resolution_refusals).issubset(
            input_security_ids
        ):
            raise AcceptedRiskStockPortfolioError(
                "named FIGI resolution refusal escaped input securities"
            )
        self._named_figi_resolution_refusals = frozenset(
            named_figi_resolution_refusals
        )
        expected_decision_sessions = decision_sessions_for_input(value)
        if profile_id == PROFILE_ID:
            if eligible_security_ids_by_decision_session is not None:
                raise AcceptedRiskStockPortfolioError(
                    "R065 does not accept a constituent-universe eligibility map"
                )
            self._eligible_security_ids_by_decision_session = None
        else:
            mapping = eligible_security_ids_by_decision_session
            if type(mapping) is not dict:
                raise AcceptedRiskStockPortfolioError(
                    "universe-variant eligibility map must be an exact dict"
                )
            if (
                any(type(session) is not str for session in mapping)
                or set(mapping) != set(expected_decision_sessions)
                or len(mapping) != EXPECTED_DECISION_SESSION_COUNT
            ):
                raise AcceptedRiskStockPortfolioError(
                    "universe-variant eligibility sessions are not exhaustive"
                )
            normalized = {}
            for session in expected_decision_sessions:
                security_ids = mapping[session]
                if (
                    type(security_ids) is not tuple
                    or not security_ids
                    or any(
                        type(security_id) is not str or not security_id
                        for security_id in security_ids
                    )
                    or tuple(sorted(set(security_ids))) != security_ids
                ):
                    raise AcceptedRiskStockPortfolioError(
                        "universe-variant eligibility values must be sorted "
                        "unique nonempty tuples"
                    )
                if not set(security_ids).issubset(input_security_ids):
                    raise AcceptedRiskStockPortfolioError(
                        "universe-variant eligibility escaped input securities"
                    )
                normalized[session] = frozenset(security_ids)
            self._eligible_security_ids_by_decision_session = normalized
        intervals = {}
        for membership in value.memberships:
            if membership.security_id in intervals:
                raise AcceptedRiskStockPortfolioError(
                    "stock portfolio membership security is duplicated"
                )
            intervals[membership.security_id] = (
                membership.first_session_index,
                membership.last_session_index_exclusive,
            )
        self._membership_intervals = intervals
        self._decision_positions = frozenset(self._weekly_decision_positions())

    def _weekly_decision_positions(self):
        sessions = frozenset(decision_sessions_for_input(self._input))
        return tuple(
            position
            for position, session in enumerate(self._input.session_axis)
            if session in sessions
        )

    def _after_score_cross_section(
        self, position, memberships, scores, sector_refused
    ):
        if position not in self._decision_positions:
            return
        session = self._input.session_axis[position]
        axis = (PRIMARY_SOURCE_VIEW_ID, PRIMARY_SCORE_ARM)
        universe_eligible = self._eligible_security_ids_by_decision_session
        eligible_security_ids = (
            None if universe_eligible is None else universe_eligible[session]
        )
        arm_scores = {
            security_id: score
            for security_id, score in scores[axis].items()
            if security_id not in self._named_figi_resolution_refusals
            and (
                eligible_security_ids is None
                or security_id in eligible_security_ids
            )
        }
        refused = sector_refused[axis]
        self._decision_session_count += 1
        if refused:
            self._sector_refused_decision_count += 1
        ranked = tuple(
            sorted(
                arm_scores.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )
        top_decile_count = min(
            MAXIMUM_HOLDINGS,
            (len(arm_scores) + 9) // 10,
        )
        selected = tuple(
            security_id for security_id, _score in ranked[:top_decile_count]
        )
        matched = tuple(sorted(arm_scores))
        self._eligible_score_count_sum += len(ranked)
        self._selected_name_count_sum += len(selected)
        if selected:
            self._signal_selected_decision_count += 1
        self._decisions[session] = (selected, matched)

    def _price(self, security_id, position):
        security_position = self._history_security_positions.get(security_id)
        session = self._input.session_axis[position]
        history_position = self._history_session_positions.get(session)
        if security_position is None or history_position is None:
            return None
        value = self._history_prices[history_position][security_position]
        if value is None:
            return None
        return _base._decimal(value, "stock portfolio adjusted open", positive=True)

    def _membership_ended(self, security_id, position):
        interval = self._membership_intervals.get(security_id)
        if interval is None:
            raise AcceptedRiskStockPortfolioError(
                "held stock escaped authenticated membership"
            )
        return position >= interval[1]

    def _targets(
        self,
        account,
        desired,
        position,
        *,
        target_gross=None,
        locked_weights=None,
    ):
        if type(locked_weights) not in (type(None), dict):
            raise AcceptedRiskStockPortfolioError(
                "locked stock-portfolio weights changed"
            )
        locked = {} if locked_weights is None else dict(locked_weights)
        if any(
                type(security_id) is not str
                or type(weight) is not Decimal
                or not weight.is_finite()
                or weight <= 0
                for security_id, weight in locked.items()
        ):
            raise AcceptedRiskStockPortfolioError(
                "locked stock-portfolio weights changed"
            )
        requested_target_gross = (
            TARGET_GROSS_EXPOSURE
            if account.role == "signal" or target_gross is None
            else target_gross
        )
        if (
            type(requested_target_gross) is not Decimal
            or not requested_target_gross.is_finite()
            or not Decimal(0)
            <= requested_target_gross
            <= Decimal(1)
        ):
            raise AcceptedRiskStockPortfolioError(
                "stock-portfolio target gross exposure escaped unlevered bounds"
            )
        with localcontext(_base._context()):
            locked_gross = +_base._stable_sum(locked.values())
            remaining_gross = +max(
                Decimal(0), requested_target_gross - locked_gross
            )
        tradable = []
        for security_id in desired:
            if security_id in locked:
                continue
            if self._membership_ended(security_id, position):
                account.membership_end_entry_refusal_count += 1
                continue
            if self._price(security_id, position) is None:
                account.entry_price_refusal_count += 1
                continue
            tradable.append(security_id)
        targets = dict(locked)
        if account.role == "signal":
            if len(locked) > MAXIMUM_HOLDINGS:
                raise AcceptedRiskStockPortfolioError(
                    "locked signal holdings exceed the frozen holdings cap"
                )
            tradable = tradable[: MAXIMUM_HOLDINGS - len(locked)]
            with localcontext(_base._context()):
                for security_id in tradable:
                    weight = +min(STOCK_WEIGHT_CAP, remaining_gross)
                    if weight == 0:
                        break
                    targets[security_id] = weight
                    remaining_gross = +(remaining_gross - weight)
            return targets
        if account.role != "matched":
            raise AcceptedRiskStockPortfolioError(
                "stock-portfolio account role changed"
            )
        unlocked_desired_count = sum(
            security_id not in locked for security_id in desired
        )
        if unlocked_desired_count == 0 or remaining_gross == 0:
            return targets
        with localcontext(_base._context()):
            weight = +(
                remaining_gross / Decimal(unlocked_desired_count)
            )
            targets.update(
                {security_id: weight for security_id in tradable if weight}
            )
            if len(tradable) == unlocked_desired_count and tradable:
                residual = +(
                    requested_target_gross
                    - _base._stable_sum(targets.values())
                )
                if residual:
                    first = min(tradable)
                    targets[first] = +(targets[first] + residual)
        return targets

    def _advance_account(
        self,
        account,
        position,
        desired,
        *,
        target_gross=None,
    ):
        starting_invested = _base._stable_sum(account.weights.values())
        ratios = {}
        stale = set()
        ended = set()
        for security_id in tuple(sorted(account.weights)):
            prior = account.marks.get(security_id)
            if prior is None:
                raise AcceptedRiskStockPortfolioError(
                    "held stock lacks its prior observed mark"
                )
            current = self._price(security_id, position)
            if self._membership_ended(security_id, position):
                ended.add(security_id)
                account.membership_end_liquidation_count += 1
                if current is None:
                    ratios[security_id] = Decimal(0)
                    account.membership_end_zero_recovery_count += 1
                else:
                    with localcontext(_base._context()):
                        ratios[security_id] = +(current / prior)
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
            gross_return = _base._stable_sum(
                weight * (ratios[security_id] - Decimal(1))
                for security_id, weight in account.weights.items()
            )
            gross_multiplier = +(Decimal(1) + gross_return)
            if gross_multiplier <= 0:
                raise AcceptedRiskStockPortfolioError(
                    "stock portfolio gross return is not survivable"
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
                if security_id not in ended
            }
        for security_id in ended:
            account.marks.pop(security_id, None)
        turnover = _base._stable_sum(
            pretrade[security_id] for security_id in sorted(ended)
        )
        if desired is not None:
            requested_target_gross = (
                TARGET_GROSS_EXPOSURE
                if account.role == "signal" or target_gross is None
                else target_gross
            )
            locked = {
                security_id: drifted[security_id]
                for security_id in sorted(stale)
            }
            target = self._targets(
                account,
                desired,
                position,
                target_gross=target_gross,
                locked_weights=locked,
            )
            with localcontext(_base._context()):
                locked_gross = +_base._stable_sum(locked.values())
                turnover = _base._stable_sum(
                    abs(
                        target.get(security_id, Decimal(0))
                        - pretrade.get(security_id, Decimal(0))
                    )
                    for security_id in sorted(set(target) | set(pretrade))
                    if security_id not in stale
                )
                executed_target_gross = +(
                    _base._stable_sum(target.values())
                )
                account.executed_target_gross_sum = +(
                    account.executed_target_gross_sum
                    + executed_target_gross
                )
                if stale:
                    account.locked_gross_sum_at_partial_decisions = +(
                        account.locked_gross_sum_at_partial_decisions
                        + locked_gross
                    )
            if stale:
                account.partial_rebalance_decision_count += 1
                account.stale_position_deferral_count += len(stale)
            account.rebalance_execution_count += 1
            if executed_target_gross == requested_target_gross:
                account.full_target_execution_count += 1
            elif executed_target_gross < requested_target_gross:
                account.underfilled_target_execution_count += 1
            else:
                account.locked_exposure_over_target_count += 1
            account.weights = target
            account.marks = {
                **{
                    security_id: account.marks[security_id]
                    for security_id in locked
                },
                **{
                    security_id: self._price(security_id, position)
                    for security_id in target
                    if security_id not in locked
                },
            }
            if target:
                account.selected_execution_count += 1
        if desired is None:
            account.weights = drifted
        with localcontext(_base._context()):
            account.turnover_sum = +(account.turnover_sum + turnover)
            end_invested = _base._stable_sum(account.weights.values())
            cash_weight = +(Decimal(1) - end_invested)
            if cash_weight < Decimal("-1e-18"):
                raise AcceptedRiskStockPortfolioError(
                    "stock portfolio target exceeds one hundred percent"
                )
            if cash_weight < 0:
                cash_weight = Decimal(0)
            account.cash_weight_sum = +(account.cash_weight_sum + cash_weight)
            for cost, accumulator in account.accumulators.items():
                net = +(
                    gross_return
                    - Decimal(cost) / Decimal(10000) * turnover
                )
                if net <= -1:
                    raise AcceptedRiskStockPortfolioError(
                        "stock portfolio net return is not survivable"
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
        return (
            executed_target_gross
            if desired is not None
            else None
        )

    def _simulate(self):
        signal = _Account("signal")
        matched = _Account("matched")
        sessions = self._input.session_axis
        start = sessions.index(DECISION_START_SESSION)
        end = sessions.index(MEASUREMENT_END_SESSION)
        benchmark = self._input.benchmark_security_id
        benchmark_wealth = Decimal(1)
        first_execution = start + 1
        prior_benchmark = self._price(benchmark, first_execution)
        if prior_benchmark is None:
            raise AcceptedRiskStockPortfolioError(
                "SPY lacks the first-execution stock-portfolio adjusted open"
            )
        for position in range(first_execution, end + 1):
            current_benchmark = self._price(benchmark, position)
            if current_benchmark is None:
                raise AcceptedRiskStockPortfolioError(
                    "SPY lacks a stock-portfolio adjusted open"
                )
            if position != first_execution:
                with localcontext(_base._context()):
                    benchmark_wealth = +(
                        benchmark_wealth * current_benchmark / prior_benchmark
                    )
            prior_benchmark = current_benchmark
            prior_session = sessions[position - 1]
            decision = self._decisions.get(prior_session)
            signal_target_gross = self._advance_account(
                signal,
                position,
                None if decision is None else decision[0],
            )
            self._advance_account(
                matched,
                position,
                None if decision is None else decision[1],
                target_gross=signal_target_gross,
            )
        return_count = end - start
        if return_count != EXPECTED_RETURN_SESSION_COUNT:
            raise AcceptedRiskStockPortfolioError(
                "stock portfolio return-session geometry changed"
            )
        return signal, matched, benchmark_wealth, return_count

    @staticmethod
    def _cell_status(signal, matched, return_count):
        if (
            return_count < 252
            or signal.invested_return_session_count
            < MINIMUM_INVESTED_RETURN_SESSIONS
        ):
            return "INCONCLUSIVE_UNDERFILLED"
        if (
            signal.membership_end_zero_recovery_count
            or matched.membership_end_zero_recovery_count
        ):
            return (
                "PRELIMINARY_DESCRIPTIVE_LOWER_BOUND_WITH_ZERO_RECOVERY"
            )
        if any(
            value
            for value in (
                signal.stale_mark_session_count,
                matched.stale_mark_session_count,
            )
        ):
            return (
                "PRELIMINARY_DESCRIPTIVE_AVAILABLE_WITH_STALE_MARK_PROXY"
            )
        if (
            signal.underfilled_target_execution_count
            or matched.underfilled_target_execution_count
        ):
            return (
                "PRELIMINARY_DESCRIPTIVE_AVAILABLE_WITH_EXPOSURE_UNDERFILL"
            )
        return "PRELIMINARY_DESCRIPTIVE_AVAILABLE"

    @staticmethod
    def _metric_conditioning(signal, matched):
        if (
            signal.membership_end_zero_recovery_count
            or matched.membership_end_zero_recovery_count
        ):
            return (
                "conditioned_on_zero_recovery_lower_bound_and_possible_"
                "stale_mark_path"
            )
        if signal.stale_mark_session_count or matched.stale_mark_session_count:
            return "conditioned_on_stale_mark_path"
        return "no_price_proxy"

    def _cell(self, cost, signal, matched, benchmark_wealth, return_count):
        signal_accumulator = signal.accumulators[cost]
        matched_accumulator = matched.accumulators[cost]
        annual, volatility, sharpe, sortino = _risk_metrics(
            signal_accumulator.returns
        )
        m_annual, m_volatility, m_sharpe, m_sortino = _risk_metrics(
            matched_accumulator.returns
        )
        with localcontext(_base._context()):
            signal_return = +(signal_accumulator.wealth - Decimal(1))
            matched_return = +(matched_accumulator.wealth - Decimal(1))
            spy_return = +(benchmark_wealth - Decimal(1))
            signal_minus_matched = +(signal_return - matched_return)
            signal_minus_spy = +(signal_return - spy_return)
            average_turnover = +(signal.turnover_sum / Decimal(return_count))
            average_cash = +(signal.cash_weight_sum / Decimal(return_count))
            matched_turnover = +(matched.turnover_sum / Decimal(return_count))
            matched_cash = +(matched.cash_weight_sum / Decimal(return_count))
        return {
            "schema": PORTFOLIO_CELL_SCHEMA,
            "profile_id": self._profile["profile_id"],
            "cost_bps_per_side": cost,
            "primary_cost_scenario": cost == PRIMARY_COST_BPS,
            "status": self._cell_status(signal, matched, return_count),
            "return_metric_conditioning": self._metric_conditioning(
                signal, matched
            ),
            "risk_metrics_are_price_proxy_conditioned": bool(
                signal.stale_mark_session_count
                or signal.membership_end_zero_recovery_count
                or matched.stale_mark_session_count
                or matched.membership_end_zero_recovery_count
            ),
            "exposure_underfill_present": bool(
                signal.underfilled_target_execution_count
                or matched.underfilled_target_execution_count
            ),
            "return_session_count": return_count,
            "invested_return_session_count": signal.invested_return_session_count,
            "cumulative_return": _decimal_text(signal_return),
            "matched_eligible_stock_cumulative_return": _decimal_text(
                matched_return
            ),
            "spy_cumulative_return": _decimal_text(spy_return),
            "cumulative_return_minus_matched": _decimal_text(
                signal_minus_matched
            ),
            "cumulative_return_minus_spy": _decimal_text(
                signal_minus_spy
            ),
            "annualized_arithmetic_return": _decimal_text(annual),
            "annualized_volatility": _decimal_text(volatility),
            "zero_rate_sharpe": None if sharpe is None else _decimal_text(sharpe),
            "zero_rate_sortino": None if sortino is None else _decimal_text(sortino),
            "maximum_drawdown": _decimal_text(
                signal_accumulator.maximum_drawdown
            ),
            "average_daily_two_sided_turnover": _decimal_text(
                average_turnover
            ),
            "average_cash_weight": _decimal_text(average_cash),
            "matched_annualized_arithmetic_return": _decimal_text(m_annual),
            "matched_annualized_volatility": _decimal_text(m_volatility),
            "matched_zero_rate_sharpe": (
                None if m_sharpe is None else _decimal_text(m_sharpe)
            ),
            "matched_zero_rate_sortino": (
                None if m_sortino is None else _decimal_text(m_sortino)
            ),
            "matched_maximum_drawdown": _decimal_text(
                matched_accumulator.maximum_drawdown
            ),
            "matched_average_daily_two_sided_turnover": _decimal_text(
                matched_turnover
            ),
            "matched_average_cash_weight": _decimal_text(matched_cash),
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
            raise AcceptedRiskStockPortfolioError(
                "stock portfolio decision-score census is not exhaustive"
            )
        signal, matched, benchmark_wealth, return_count = self._simulate()
        cells = [
            self._cell(
                cost, signal, matched, benchmark_wealth, return_count
            )
            for cost in COST_BPS_SCENARIOS
        ]
        with localcontext(_base._context()):
            mean_eligible = +(
                Decimal(self._eligible_score_count_sum)
                / Decimal(self._decision_session_count)
            )
            mean_selected = +(
                Decimal(self._selected_name_count_sum)
                / Decimal(self._decision_session_count)
            )
            average_holdings = +(
                Decimal(signal.holding_count_sum) / Decimal(return_count)
            )
            mean_target_gross = (
                Decimal(0)
                if signal.rebalance_execution_count == 0
                else +(
                    signal.executed_target_gross_sum
                    / Decimal(signal.rebalance_execution_count)
                )
            )
            matched_mean_target_gross = (
                Decimal(0)
                if matched.rebalance_execution_count == 0
                else +(
                    matched.executed_target_gross_sum
                    / Decimal(matched.rebalance_execution_count)
                )
            )
            mean_locked_gross = (
                Decimal(0)
                if signal.partial_rebalance_decision_count == 0
                else +(
                    signal.locked_gross_sum_at_partial_decisions
                    / Decimal(signal.partial_rebalance_decision_count)
                )
            )
            matched_mean_locked_gross = (
                Decimal(0)
                if matched.partial_rebalance_decision_count == 0
                else +(
                    matched.locked_gross_sum_at_partial_decisions
                    / Decimal(matched.partial_rebalance_decision_count)
                )
            )
        record = {
            "schema": SUMMARY_SCHEMA,
            "contract_id": CONTRACT_ID,
            "profile": dict(self._profile),
            "package_id": self._package_id,
            "package_sha256": self._package_sha256,
            "input_manifest_id": self._input.manifest_id,
            "input_manifest_sha256": self._input.manifest_sha256,
            "status": "PRELIMINARY_ACCEPTED_RISK_STOCK_PORTFOLIO",
            "decision_session_count": self._decision_session_count,
            "portfolio_return_session_count": return_count,
            "invested_return_session_count": (
                signal.invested_return_session_count
            ),
            "signal_selected_decision_count": (
                self._signal_selected_decision_count
            ),
            "selected_execution_count": signal.selected_execution_count,
            "rebalance_execution_count": signal.rebalance_execution_count,
            "full_target_execution_count": (
                signal.full_target_execution_count
            ),
            "underfilled_target_execution_count": (
                signal.underfilled_target_execution_count
            ),
            "matched_rebalance_execution_count": (
                matched.rebalance_execution_count
            ),
            "matched_target_met_execution_count": (
                matched.full_target_execution_count
            ),
            "matched_underfilled_target_execution_count": (
                matched.underfilled_target_execution_count
            ),
            "sector_refused_decision_count": (
                self._sector_refused_decision_count
            ),
            "mean_eligible_score_count": _decimal_text(mean_eligible),
            "mean_selected_name_count": _decimal_text(mean_selected),
            "mean_executed_target_gross_exposure": _decimal_text(
                mean_target_gross
            ),
            "matched_mean_executed_target_gross_exposure": _decimal_text(
                matched_mean_target_gross
            ),
            "average_holding_count": _decimal_text(average_holdings),
            "entry_price_refusal_count": signal.entry_price_refusal_count,
            "stale_mark_session_count": signal.stale_mark_session_count,
            "deferred_rebalance_count": signal.deferred_rebalance_count,
            "partial_rebalance_decision_count": (
                signal.partial_rebalance_decision_count
            ),
            "stale_position_deferral_count": (
                signal.stale_position_deferral_count
            ),
            "mean_locked_gross_at_partial_decisions": _decimal_text(
                mean_locked_gross
            ),
            "locked_exposure_over_target_count": (
                signal.locked_exposure_over_target_count
            ),
            "membership_end_liquidation_count": (
                signal.membership_end_liquidation_count
            ),
            "membership_end_zero_recovery_count": (
                signal.membership_end_zero_recovery_count
            ),
            "membership_end_entry_refusal_count": (
                signal.membership_end_entry_refusal_count
            ),
            "matched_entry_price_refusal_count": (
                matched.entry_price_refusal_count
            ),
            "matched_stale_mark_session_count": (
                matched.stale_mark_session_count
            ),
            "matched_deferred_rebalance_count": (
                matched.deferred_rebalance_count
            ),
            "matched_partial_rebalance_decision_count": (
                matched.partial_rebalance_decision_count
            ),
            "matched_stale_position_deferral_count": (
                matched.stale_position_deferral_count
            ),
            "matched_mean_locked_gross_at_partial_decisions": _decimal_text(
                matched_mean_locked_gross
            ),
            "matched_locked_exposure_over_target_count": (
                matched.locked_exposure_over_target_count
            ),
            "matched_membership_end_liquidation_count": (
                matched.membership_end_liquidation_count
            ),
            "matched_membership_end_zero_recovery_count": (
                matched.membership_end_zero_recovery_count
            ),
            "matched_membership_end_entry_refusal_count": (
                matched.membership_end_entry_refusal_count
            ),
            "named_figi_resolution_refusal_count": len(
                self._named_figi_resolution_refusals
            ),
            "history_normalization_mode": "TOTAL_RETURN",
            "history_value_field": "open",
            "r055_signal_rule_changed": False,
            "liquidity_filter_applied": False,
            "terminal_payoff_applied": False,
            "membership_end_liquidation_is_terminal_payoff": False,
            "membership_end_missing_price_policy": (
                "zero_recovery_conservative_lower_bound"
            ),
            "matched_exposure_targeted_to_signal_executed_gross": True,
            "current_vintage_non_pristine_pit_input": True,
            "raw_provider_rows_in_summary": False,
            "raw_security_outcome_rows_in_summary": False,
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
        digest = _sha(record)
        return {
            **record,
            "summary_id": "arv2-stock-portfolio-summary-" + digest[:24],
            "summary_sha256": digest,
        }

    def custom_summary_statistics(self):
        summary = self.aggregate_summary()
        cells = summary.pop("portfolio_cells")
        profile = summary.pop("profile")
        expected_profile = require_stock_portfolio_profile(
            self._profile["profile_id"]
        )
        if profile != expected_profile:
            raise AcceptedRiskStockPortfolioError(
                "stock portfolio summary profile changed"
            )
        # The complete profile is authenticated independently by the QC
        # projection and remains part of the summary digest.  Repeating its
        # 1.6 KiB canonical body inside the metadata statistic left the R062
        # fixture only six bytes below QC's 4 KiB per-statistic ceiling and
        # caused the real run to refuse after computation.  Carry the exact
        # identity here; the result validator rehydrates the pinned profile
        # before checking the digest.
        summary["profile_id"] = profile["profile_id"]
        summary["profile_sha256"] = profile["profile_sha256"]
        output = {
            "ARV2_STOCK_PORTFOLIO_META": _canonical(summary).decode("ascii")
        }
        for cell in cells:
            output[
                "ARV2_STOCK_PORTFOLIO_COST_" + str(cell["cost_bps_per_side"])
            ] = _canonical(cell).decode("ascii")
        if tuple(sorted(output)) != expected_custom_summary_statistic_names(
            self._profile["profile_id"]
        ):
            raise AcceptedRiskStockPortfolioError(
                "stock portfolio custom summary inventory changed"
            )
        if any(len(key) > 64 or len(value) > 4096 for key, value in output.items()):
            raise AcceptedRiskStockPortfolioError(
                "stock portfolio custom summary exceeded compact bound"
            )
        return dict(sorted(output.items()))


__all__ = (
    "AcceptedRiskStockPortfolioError",
    "ALL_PROFILE_IDS",
    "CONTRACT_ID",
    "COST_BPS_SCENARIOS",
    "DECISION_END_SESSION",
    "DECISION_START_SESSION",
    "EXPECTED_DECISION_SESSION_COUNT",
    "EXPECTED_RETURN_SESSION_COUNT",
    "MAXIMUM_HOLDINGS",
    "MEASUREMENT_END_SESSION",
    "MINIMUM_INVESTED_RETURN_SESSIONS",
    "NASDAQ100_PROFILE_ID",
    "PORTFOLIO_CELL_SCHEMA",
    "PRIMARY_COST_BPS",
    "PROFILE_ID",
    "PROFILE_IDS",
    "PROFILE_SCHEMA",
    "SP500_PROFILE_ID",
    "STOCK_WEIGHT_CAP",
    "SUMMARY_SCHEMA",
    "TARGET_GROSS_EXPOSURE",
    "UNION_PROFILE_ID",
    "UNIVERSE_PROFILE_IDS",
    "VARIANT_PROFILE_IDS",
    "StockPortfolioEvaluationRuntime",
    "constituent_etf_tickers_for_profile",
    "decision_sessions_for_input",
    "expected_custom_summary_statistic_names",
    "require_stock_portfolio_profile",
)
