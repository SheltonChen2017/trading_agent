"""Backtest-only ARV2 QQQ tilt runtime with simulated orders.

No ``__future__`` import: QC injects a source prelude.
"""

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal

try:
    import accepted_risk_order_level_benchmark as _benchmark
    import accepted_risk_market_cap_stock_portfolio_tilt as _tilt
    import accepted_risk_order_level_core as _orders
    import accepted_risk_order_level_input_runtime as _input
    import accepted_risk_preliminary_qc_figi as _figi
    import accepted_risk_sequential_r055_score as _score
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_order_level_benchmark as _benchmark,
        accepted_risk_market_cap_stock_portfolio_tilt as _tilt,
        accepted_risk_order_level_core as _orders,
        accepted_risk_order_level_input_runtime as _input,
        accepted_risk_preliminary_qc_figi as _figi,
        accepted_risk_sequential_r055_score as _score,
    )


class AcceptedRiskQqqOrderLevelQcRuntimeError(ValueError):
    """The fixed order profile or simulated QC boundary was refused."""


_Refusal = AcceptedRiskQqqOrderLevelQcRuntimeError


PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v4"
PROFILE_2025_ID = "arv2-qqq-order-level-tilt-2025-cutoff-v4"
PROFILE_2026_ID = "arv2-qqq-order-level-tilt-2026-cutoff-v4"
PROXY_PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v5"
PROXY_PROFILE_2025_ID = "arv2-qqq-order-level-tilt-2025-cutoff-v5"
PROXY_PROFILE_2026_ID = "arv2-qqq-order-level-tilt-2026-cutoff-v5"
PREOPEN_PROXY_PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v6"
PREOPEN_PROXY_PROFILE_2025_ID = "arv2-qqq-order-level-tilt-2025-cutoff-v6"
PREOPEN_PROXY_PROFILE_2026_ID = "arv2-qqq-order-level-tilt-2026-cutoff-v6"
NUMERIC_PREOPEN_PROXY_PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v7"
NUMERIC_PREOPEN_PROXY_PROFILE_2025_ID = "arv2-qqq-order-level-tilt-2025-cutoff-v7"
NUMERIC_PREOPEN_PROXY_PROFILE_2026_ID = "arv2-qqq-order-level-tilt-2026-cutoff-v7"
ENUM_PREOPEN_PROXY_PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v8"
ENUM_PREOPEN_PROXY_PROFILE_2025_ID = "arv2-qqq-order-level-tilt-2025-cutoff-v8"
ENUM_PREOPEN_PROXY_PROFILE_2026_ID = "arv2-qqq-order-level-tilt-2026-cutoff-v8"
CASH_PREOPEN_PROXY_PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v9"
CASH_PREOPEN_PROXY_PROFILE_2025_ID = "arv2-qqq-order-level-tilt-2025-cutoff-v9"
CASH_PREOPEN_PROXY_PROFILE_2026_ID = "arv2-qqq-order-level-tilt-2026-cutoff-v9"
CASH_PREOPEN_PROXY_PROFILE_IDS = (
    CASH_PREOPEN_PROXY_PROFILE_2025_ID, CASH_PREOPEN_PROXY_PROFILE_2026_ID,
)
ENUM_PREOPEN_PROXY_PROFILE_IDS = (
    ENUM_PREOPEN_PROXY_PROFILE_2025_ID, ENUM_PREOPEN_PROXY_PROFILE_2026_ID,
) + CASH_PREOPEN_PROXY_PROFILE_IDS
NUMERIC_PREOPEN_PROXY_PROFILE_IDS = (
    NUMERIC_PREOPEN_PROXY_PROFILE_2025_ID, NUMERIC_PREOPEN_PROXY_PROFILE_2026_ID,
)
PREOPEN_PROXY_PROFILE_IDS = (
    PREOPEN_PROXY_PROFILE_2025_ID, PREOPEN_PROXY_PROFILE_2026_ID,
) + NUMERIC_PREOPEN_PROXY_PROFILE_IDS + ENUM_PREOPEN_PROXY_PROFILE_IDS
PROXY_PROFILE_IDS = (
    PROXY_PROFILE_2025_ID, PROXY_PROFILE_2026_ID,
) + PREOPEN_PROXY_PROFILE_IDS
PROFILE_IDS = (PROFILE_2025_ID, PROFILE_2026_ID) + PROXY_PROFILE_IDS
DECISION_CUTOFF_SESSION = "2026-09-16"
FINAL_EXECUTION_SESSION = "2026-09-17"
STARTING_CASH = Decimal("1000000")
META_STATISTIC_NAME = "ARV2_ORDER_LEVEL_META"
AGGREGATES_STATISTIC_NAME = "ARV2_ORDER_LEVEL_AGGREGATES"
MAXIMUM_STATISTIC_BYTES = 4096
SUMMARY_SCHEMA = "arv2-qqq-order-level-tilt-summary-v6"
PROXY_SUMMARY_SCHEMA = "arv2-qqq-order-level-tilt-summary-v7"
QQQ_TICKER = "QQQ"
QQQ_PROXY_SECURITY_ID = "arv2-qqq-etf-unjoined-weight-proxy"
QQQ_PROXY_OVERLAP_DISCLOSURE = (
    "QQQ ETF proxy overlaps the resolved stock core; this is not exact QQQ replication"
)
PIT_LOOKBACK_CALENDAR_DAYS = 45
MINIMUM_RESOLVED_CONSTITUENT_WEIGHT_RATIO = Decimal("0.95")
MINIMUM_PROXY_RESOLVED_CONSTITUENT_WEIGHT_RATIO = Decimal("0.80")
MINIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL = Decimal("0.95")
MAXIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL = Decimal("1.05")
EXACT_CONSTITUENT_SNAPSHOT_AGE_SESSIONS = 1
TARGET_WEIGHT_BASIS = (
    "pit_qqq_reported_positive_holdings_weights_resolved_renormalized"
)
PROXY_TARGET_WEIGHT_BASIS = (
    "pit_qqq_reported_positive_holdings_weights_resolved_plus_unjoined_qqq_etf_proxy"
)
COVERAGE_PATH_SCHEMA = "arv2-order-level-pit-coverage-path-v2"
PROXY_COVERAGE_PATH_SCHEMA = "arv2-order-level-pit-coverage-path-v3"
TARGET_WEIGHT_MAP_SCHEMA = "arv2-order-level-pit-target-weight-map-v1"
PROXY_TARGET_WEIGHT_MAP_SCHEMA = "arv2-order-level-pit-target-weight-map-v2"
TARGET_WEIGHT_PATH_SCHEMA = "arv2-order-level-pit-target-weight-path-v1"
PROXY_TARGET_WEIGHT_PATH_SCHEMA = "arv2-order-level-pit-target-weight-path-v2"
IGNORED_ORDER_STATUSES = frozenset(
    {"New", "Submitted", "UpdateSubmitted", "CancelPending", "None"}
)
MAX_SYNCHRONOUS_ORDER_EVENTS = 64


def _canonical(value):
    try:
        return _orders._canonical(value)
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise _Refusal(
            "order-level value is not canonical ASCII JSON"
        ) from exc


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decimal_text(value):
    if type(value) is not Decimal or not value.is_finite():
        raise _Refusal(
            "order-level aggregate is not an exact finite Decimal"
        )
    return _orders._decimal_text(value)


def _decimal(value, name, *, positive=False, nonnegative=False):
    return _orders.exact_decimal(
        value, name, _Refusal,
        positive=positive, nonnegative=nonnegative,
    )


def _symbol_sid(symbol, name):
    return _orders.symbol_sid(
        symbol, name, _Refusal
    )


_benchmark_total_return = _benchmark.benchmark_total_return


_benchmark_close_binding = _benchmark.benchmark_close_binding


_execution_matched_qqq_path = _benchmark.execution_matched_qqq_path


_path_metrics = _benchmark.path_metrics


def _profile(profile_id, start_session, *, proxy=False, preopen=False, numeric_status=False, enum_status=False, cash_replan=False):
    if (
        _benchmark.QQQ_TICKER != QQQ_TICKER
        or _benchmark.TARGET_GROSS_EXPOSURE
        != _tilt.TARGET_GROSS_EXPOSURE
        or _benchmark.ENTRY_FEE_RATE_PER_SIDE
        != _orders.MODELED_FEE_RATE_PER_SIDE
        or _benchmark.ENTRY_FEE_BPS_PER_SIDE
        != _orders.MODELED_FEE_BPS_PER_SIDE
    ):
        raise _Refusal(
            "execution-matched QQQ benchmark constants changed"
        )
    start = datetime.strptime(start_session, "%Y-%m-%d")
    record = {
        "schema": (
            CASH_PREOPEN_PROXY_PROFILE_SCHEMA if cash_replan else
            ENUM_PREOPEN_PROXY_PROFILE_SCHEMA if enum_status else
            NUMERIC_PREOPEN_PROXY_PROFILE_SCHEMA if numeric_status else
            PREOPEN_PROXY_PROFILE_SCHEMA if preopen else
            PROXY_PROFILE_SCHEMA if proxy else PROFILE_SCHEMA
        ),
        "profile_id": profile_id,
        "universe_proxy_ticker": QQQ_TICKER,
        "evaluation_start_session": start_session,
        "start_year": start.year,
        "start_month": start.month,
        "start_day": start.day,
        "decision_cutoff_session": DECISION_CUTOFF_SESSION,
        "final_execution_session": FINAL_EXECUTION_SESSION,
        "decision_schedule": "first_authenticated_session_of_each_ISO_week_plus_exact_cutoff",
        "decision_timing": "after_QQQ_market_close",
        "execution_timing": "next_authenticated_session_market_on_open",
        "starting_cash": _decimal_text(STARTING_CASH),
        "target_gross_exposure": _decimal_text(_tilt.TARGET_GROSS_EXPOSURE),
        "signal": "exact_unchanged_R055_primary_view_firm_specific",
        "score_source_view_id": _score.PRIMARY_SOURCE_VIEW_ID,
        "portfolio": (
            "QQQ_PIT_holdings_weight_stock_core_plus_unjoined_QQQ_ETF_proxy_plus_frozen_sector_neutral_tilt"
            if proxy else
            "QQQ_PIT_holdings_weight_benchmark_plus_frozen_sector_neutral_tilt"
        ),
        "target_weight_basis": PROXY_TARGET_WEIGHT_BASIS if proxy else TARGET_WEIGHT_BASIS,
        "price_normalization": "RAW",
        "resolution": "MINUTE",
        "benchmark_price_normalization": "TOTAL_RETURN",
        "benchmark_observation": "EXECUTION_MATCHED_FIRST_MOO_OPEN_THEN_SESSION_CLOSE",
        "benchmark_target_gross_exposure": _decimal_text(_tilt.TARGET_GROSS_EXPOSURE),
        "benchmark_entry_fee_bps_per_side": _orders.MODELED_FEE_BPS_PER_SIDE,
        "calendar_benchmark_observation": "SESSION_CLOSE_CONTEXT_ONLY",
        "minimum_resolved_constituent_weight_ratio": _decimal_text(
            MINIMUM_PROXY_RESOLVED_CONSTITUENT_WEIGHT_RATIO
            if proxy else MINIMUM_RESOLVED_CONSTITUENT_WEIGHT_RATIO
        ),
        "minimum_positive_constituent_weight_total": _decimal_text(MINIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL),
        "maximum_positive_constituent_weight_total": _decimal_text(MAXIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL),
        "exact_constituent_snapshot_age_sessions": EXACT_CONSTITUENT_SNAPSHOT_AGE_SESSIONS,
        "constituent_source_session_rule": "QC_daily_Series_collection_EndTime_minus_one_calendar_day",
        "reference_price_freshness": "exact_decision_session_last_data_end_time",
        "order_type": "MARKET_ON_OPEN",
        "fee_bps_per_side": _orders.MODELED_FEE_BPS_PER_SIDE,
        "lifecycle_modeled_fee_basis": "actual_fill_price_times_filled_quantity",
        "engine_fee_model_basis": "current_minute_trade_bar_open_times_full_order_quantity_at_fee_assessment",
        "slippage_model": "zero",
        "backtest_only": True,
        "simulated_order_submission": True,
        "live_orders": False,
        "paper_orders": False,
        "funded_orders": False,
        "deployment": False,
        "broker_credentials": False,
        "trading": False,
    }
    if proxy:
        record["qqq_proxy_security_id"] = QQQ_PROXY_SECURITY_ID
        record["qqq_proxy_overlap_disclosure"] = QQQ_PROXY_OVERLAP_DISCLOSURE
    if preopen:
        record["execution_submission_timing"] = "NEXT_AUTHENTICATED_SESSION_PREOPEN_10_MINUTES"
        record["preopen_timekeeper"] = "QQQ_extended_hours_minute_bars"
        record["latest_accepted_submission_clock"] = "09:27_New_York"
        record["synchronous_order_event_rule"] = "stage_until_exact_returned_ticket_then_replay_once"
    if numeric_status:
        record["qc_order_status_codec"] = "exact_LEAN_numeric_0_1_2_3_5_6_7_8_9"
    if enum_status:
        record["qc_order_status_codec"] = "direct_documented_LEAN_OrderStatus_enum_members"
    if cash_replan:
        record["overnight_cash_rule"] = (
            "increase_only_replan_frozen_prior_close_targets_and_RAW_prices"
        )
    return {**record, "profile_sha256": _sha(record)}


_PROFILES = {
    profile_id: _profile(
        profile_id,
        "2025-01-02" if "2025-cutoff" in profile_id else "2026-01-02",
        proxy=profile_id in PROXY_PROFILE_IDS,
        preopen=profile_id in PREOPEN_PROXY_PROFILE_IDS,
        numeric_status=profile_id in NUMERIC_PREOPEN_PROXY_PROFILE_IDS,
        enum_status=profile_id in ENUM_PREOPEN_PROXY_PROFILE_IDS,
        cash_replan=profile_id in CASH_PREOPEN_PROXY_PROFILE_IDS,
    )
    for profile_id in PROFILE_IDS
}


def require_qqq_order_level_profile(profile_id):
    if type(profile_id) is not str or profile_id not in _PROFILES:
        raise _Refusal(
            "QQQ order-level profile is not an exact fixed profile"
        )
    return json.loads(_canonical(_PROFILES[profile_id]).decode("ascii"))


def expected_custom_summary_statistic_names(profile_id):
    require_qqq_order_level_profile(profile_id)
    return tuple(sorted((META_STATISTIC_NAME, AGGREGATES_STATISTIC_NAME)))


class AcceptedRiskQqqOrderLevelQcRuntime:
    """Coordinate one fixed QQQ simulated-order backtest profile."""

    def __init__(
        self,
        algorithm,
        *,
        activation_manifest_key,
        activation_manifest_sha256,
        activation_manifest_byte_count,
        profile_id,
        authority_benchmark_symbol,
        qqq_benchmark_symbol,
        qqq_constituent_universe,
        minute_resolution,
        raw_normalization,
        trade_bar_type,
        daily_resolution,
        total_return_normalization,
        fee_model_factory,
        slippage_model_factory,
        order_status_enum=None,
    ):
        self._algorithm = algorithm
        self._activation_manifest_key = activation_manifest_key
        self._activation_manifest_sha256 = activation_manifest_sha256
        self._activation_manifest_byte_count = activation_manifest_byte_count
        self._profile = require_qqq_order_level_profile(profile_id)
        self._proxy_weight_mode = profile_id in PROXY_PROFILE_IDS
        self._preopen_mode = profile_id in PREOPEN_PROXY_PROFILE_IDS
        self._numeric_order_status_mode = profile_id in NUMERIC_PREOPEN_PROXY_PROFILE_IDS
        self._enum_order_status_mode = profile_id in ENUM_PREOPEN_PROXY_PROFILE_IDS
        self._cash_replan_mode = profile_id in CASH_PREOPEN_PROXY_PROFILE_IDS
        try:
            self._order_status_enum_members = (
                _orders.require_qc_order_status_enum_members(order_status_enum)
                if self._enum_order_status_mode else None
            )
        except _orders.OrderLevelBacktestError as exc:
            raise _Refusal(str(exc)) from exc
        self._authority_benchmark_symbol = authority_benchmark_symbol
        self._qqq_benchmark_symbol = qqq_benchmark_symbol
        self._qqq_constituent_universe = qqq_constituent_universe
        self._minute_resolution = minute_resolution
        self._raw_normalization = raw_normalization
        self._trade_bar_type = trade_bar_type
        self._daily_resolution = daily_resolution
        self._total_return_normalization = total_return_normalization
        self._fee_model_factory = fee_model_factory
        self._slippage_model_factory = slippage_model_factory
        self._initialized = False
        self._completed = False
        self._package = None
        self._resolution = None
        self._score_runtime = None
        self._session_positions = None
        self._session_axis = None
        self._decision_sessions = ()
        self._decision_set = frozenset()
        self._configured_security_ids = set()
        self._open_plan = None
        self._open_plan_events = []
        self._open_order_ids = {}
        self._pending_preopen = None
        self._submitted_preopen_sessions = set()
        self._pending_submission_events = None
        self._pending_submission_event_keys = None
        self._lifecycle_records = []
        self._benchmark_observations = {}
        self._benchmark_open_observations = {}
        self._strategy_equity_observations = {}
        self._gross_exposure_observations = {}
        self._cash_weight_observations = {}
        self._decision_count = 0
        self._submitted_order_count = 0
        self._skipped_unpriced_decision_count = 0
        self._pit_history_call_count = 0
        self._pit_source_row_count = 0
        self._tilt_enabled_count = 0
        self._tilt_underfilled_count = 0
        self._tilted_name_count_sum = 0
        self._one_way_active_share_sum = Decimal(0)
        self._pit_coverage_records = []

    @property
    def completed(self):
        return self._completed

    def _backtest_flag(self):
        return self._algorithm.live_mode

    def _order_status_text(self, value):
        if self._enum_order_status_mode:
            return _orders.qc_order_status_enum_text(
                value, self._order_status_enum_members
            )
        return _orders.qc_order_status_text(
            value, numeric=self._numeric_order_status_mode
        )

    def _portfolio_equity(self):
        return _decimal(
            self._algorithm.portfolio.total_portfolio_value, "QC total portfolio value",
            positive=True,
        )

    def _portfolio_cash(self):
        return _decimal(
            self._algorithm.portfolio.cash, "QC portfolio cash", nonnegative=True,
        )

    def _observe_strategy_account(self, session):
        if session in self._strategy_equity_observations:
            raise _Refusal(
                "order-level strategy account session is duplicated"
            )
        equity = self._portfolio_equity()
        holdings = _decimal(
            self._algorithm.portfolio.total_holdings_value,
            "QC total holdings value",
            nonnegative=True,
        )
        cash = self._portfolio_cash()
        self._strategy_equity_observations[session] = equity
        self._gross_exposure_observations[session] = holdings / equity
        self._cash_weight_observations[session] = cash / equity

    @staticmethod
    def _decision_axis(axis, start_session):
        return _orders.weekly_decision_axis(
            axis, start_session, DECISION_CUTOFF_SESSION, FINAL_EXECUTION_SESSION,
            _Refusal,
        )

    def initialize(self):
        if self._initialized:
            raise _Refusal(
                "order-level runtime initialized more than once"
            )
        _orders.validate_backtest_initialize(live_mode=self._backtest_flag())
        if (
            self._qqq_constituent_universe is None
            or self._authority_benchmark_symbol is None
            or self._qqq_benchmark_symbol is None
            or self._trade_bar_type is None
            or self._daily_resolution is None
            or self._total_return_normalization is None
            or not callable(self._fee_model_factory)
            or not callable(self._slippage_model_factory)
        ):
            raise _Refusal(
                "order-level QC dependency inventory changed"
            )
        if self._portfolio_equity() != STARTING_CASH:
            raise _Refusal(
                "order-level starting equity is not exact one million dollars"
            )
        package = _input.load_accepted_risk_preliminary_package(
            self._algorithm,
            activation_manifest_key=self._activation_manifest_key,
            activation_manifest_sha256=self._activation_manifest_sha256,
            activation_manifest_byte_count=self._activation_manifest_byte_count,
        )
        try:
            lineage = dict(package.evaluator_input.source_lineage_sha256s)
            resolution = _figi.resolve_preliminary_qc_figis(
                package.runtime_symbol_bindings,
                expected_security_master_admission_sha256=(
                    lineage["security_master_admission_sha256"]
                ),
                composite_figi=self._algorithm.composite_figi,
                benchmark_symbol=self._authority_benchmark_symbol,
            )
        except Exception as exc:
            raise _Refusal(
                "order-level composite-FIGI inventory did not resolve"
            ) from exc
        decisions, start, _cutoff, _final = self._decision_axis(
            package.evaluator_input.session_axis,
            self._profile["evaluation_start_session"],
        )
        self._package = package
        self._resolution = resolution
        self._score_runtime = _score.SequentialR055ScoreRuntime(
            package.evaluator_input,
            start_position=start,
        )
        self._session_positions = {
            session: position
            for position, session in enumerate(
                package.evaluator_input.session_axis
            )
        }
        self._session_axis = tuple(package.evaluator_input.session_axis)
        self._decision_sessions = decisions
        self._decision_set = frozenset(decisions)
        self._initialized = True
        if self._proxy_weight_mode:
            # The ETF position is executable, unlike the legacy contextual
            # QQQ benchmark. Explicit history requests still use TOTAL_RETURN.
            try:
                qqq_security = self._algorithm.securities[self._qqq_benchmark_symbol]
            except KeyError as exc:
                raise _Refusal(
                    "order-level QQQ ETF proxy security is unavailable"
                ) from exc
            self.configure_security(qqq_security)

    def configure_security(self, security):
        if not self._initialized:
            raise _Refusal(
                "order-level security arrived before initialization"
            )
        sid = _symbol_sid(security.symbol, "order-level configured")
        security.set_data_normalization_mode(self._raw_normalization)
        security.set_fee_model(self._fee_model_factory())
        security.set_slippage_model(self._slippage_model_factory())
        self._configured_security_ids.add(sid)
        return security

    def on_securities_changed(self, changes):
        try:
            added = tuple(changes.added_securities)
        except Exception as exc:
            raise _Refusal(
                "order-level security changes are unreadable"
            ) from exc
        for security in added:
            sid = _symbol_sid(security.symbol, "order-level added")
            if sid == _symbol_sid(
                self._qqq_benchmark_symbol, "order-level QQQ benchmark"
            ) or sid == _symbol_sid(
                self._authority_benchmark_symbol,
                "order-level authority benchmark",
            ):
                continue
            self.configure_security(security)

    def accept_qqq_constituents(self, constituents):
        if not self._initialized:
            raise _Refusal(
                "QQQ constituents arrived before initialization"
            )
        rows = _input.collection_rows(constituents, "order-level QQQ constituents")
        accepted = {}
        for row in rows:
            try:
                weight = _decimal(
                    row.weight,
                    "order-level QQQ constituent weight",
                )
                symbol = row.symbol
            except AttributeError as exc:
                raise _Refusal(
                    "order-level QQQ constituent row is unreadable"
                ) from exc
            if weight <= 0:
                continue
            sid = _symbol_sid(symbol, "order-level QQQ constituent")
            try:
                self._resolution.security_for_qc_sid(sid)
            except Exception:
                continue
            if sid in accepted:
                raise _Refusal(
                    "order-level QQQ constituent SID is duplicated"
                )
            accepted[sid] = symbol
        return [accepted[sid] for sid in sorted(accepted)]

    def _history_inventory(self, universe, start, end, name):
        try:
            history = self._algorithm.history(
                universe, start, end, flatten=False
            )
        except Exception as exc:
            raise _Refusal(
                name + " history call failed"
            ) from exc
        self._pit_history_call_count += 1
        result, row_count = _input.indexed_constituent_history(
            history, universe, start, end, name, _symbol_sid,
            _Refusal,
        )
        self._pit_source_row_count += row_count
        return result

    @staticmethod
    def _latest(inventory, cutoff, name):
        return _orders.strictly_prior_collection(
            inventory, cutoff, name, _Refusal
        )

    def _snapshot_age_sessions(self, observed, decision_session, name):
        return _orders.authenticated_session_age(
            self._session_positions, observed, decision_session, name,
            _Refusal,
        )

    def _resolved_qqq_weights(
        self,
        session,
        constituent_weights,
        *,
        constituent_age_sessions,
    ):
        result, record = _benchmark.resolved_qqq_holdings_weight_core(
            constituent_weights,
            self._resolution.resolved,
            session=session,
            constituent_age_sessions=constituent_age_sessions,
            minimum_total=MINIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL,
            maximum_total=MAXIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL,
            minimum_resolved_ratio=(
                MINIMUM_PROXY_RESOLVED_CONSTITUENT_WEIGHT_RATIO
                if self._proxy_weight_mode
                else MINIMUM_RESOLVED_CONSTITUENT_WEIGHT_RATIO
            ),
            weight_map_schema=(
                PROXY_TARGET_WEIGHT_MAP_SCHEMA if self._proxy_weight_mode
                else TARGET_WEIGHT_MAP_SCHEMA
            ),
            error_type=_Refusal,
            proxy_security_id=(
                QQQ_PROXY_SECURITY_ID if self._proxy_weight_mode else None
            ),
            qqq_sid=(
                _symbol_sid(self._qqq_benchmark_symbol, "order-level QQQ ETF proxy")
                if self._proxy_weight_mode else None
            ),
        )
        if any(row["session"] == session for row in self._pit_coverage_records):
            raise _Refusal(
                "order-level PIT coverage session is duplicated"
            )
        self._pit_coverage_records.append(record)
        return result

    def _pit_benchmark_measures(self, session):
        decision = datetime.strptime(session, "%Y-%m-%d")
        start = decision - timedelta(days=PIT_LOOKBACK_CALENDAR_DAYS)
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
        if constituent_age != EXACT_CONSTITUENT_SNAPSHOT_AGE_SESSIONS:
            raise _Refusal(
                "order-level PIT QQQ constituent snapshot is not the immediately prior authenticated session"
            )
        constituent_weights = _input.positive_constituent_weights(
            constituent_rows, _decimal, _Refusal
        )
        return self._resolved_qqq_weights(
            session,
            constituent_weights,
            constituent_age_sessions=constituent_age,
        )

    def _security(self, security_id):
        if security_id == QQQ_PROXY_SECURITY_ID and self._proxy_weight_mode:
            symbol = self._qqq_benchmark_symbol
        else:
            symbol = self._resolution.symbol_for_security(security_id)
        if symbol is None:
            raise _Refusal(
                "order-level target lacks an exact FIGI resolution"
            )
        try:
            security = self._algorithm.securities[symbol]
        except KeyError:
            security = self._algorithm.add_security(
                symbol,
                self._minute_resolution,
                False,
                1,
                False,
            )
        sid = _symbol_sid(symbol, "order-level target")
        if sid not in self._configured_security_ids:
            self.configure_security(security)
        return symbol, security

    def _positive_price(self, security_id, decision_session):
        _symbol, security = self._security(security_id)
        return _input.same_session_positive_raw_price(
            security, decision_session, _decimal,
            _Refusal,
        )

    def _current_quantities(self, security_ids):
        return _input.current_whole_share_quantities(
            security_ids, self._security, self._algorithm.portfolio,
            _decimal, _Refusal,
        )

    def _verify_preopen_holding_census(self, plan):
        expected = {
            _symbol_sid(
                self._qqq_benchmark_symbol
                if security_id == QQQ_PROXY_SECURITY_ID else
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
                sid = _symbol_sid(symbol, "order-level preopen holding key")
                if sid != _symbol_sid(
                    holding.symbol, "order-level preopen holding"
                ):
                    raise _Refusal(
                        "order-level preopen holding identity changed"
                    )
                quantity = _decimal(
                    holding.quantity, "order-level preopen holding quantity",
                    nonnegative=True,
                )
                if quantity != quantity.to_integral_value():
                    raise _Refusal(
                        "order-level preopen holding is not a whole share"
                    )
                if quantity:
                    if sid in observed:
                        raise _Refusal(
                            "order-level preopen holding SID is duplicated"
                        )
                    observed[sid] = int(quantity)
            except AttributeError as exc:
                raise _Refusal(
                    "order-level complete preopen holdings are unreadable"
                ) from exc
        if observed != expected:
            raise _Refusal(
                "order-level complete overnight holdings changed"
            )

    def _close_open_plan(self):
        if self._open_plan is None:
            return
        if self._pending_submission_events is not None:
            raise _Refusal(
                "order-level rebalance closed during MOO submission"
            )
        ordered = tuple(self._open_plan_events)
        summary = _orders.summarize_order_lifecycle(
            self._open_plan,
            ordered,
            require_all_terminal=True,
        )
        self._lifecycle_records.append(summary.to_record())
        self._open_plan = None
        self._open_plan_events = []
        self._open_order_ids = {}

    def _build_plan(self, session, target_weights):
        target_ids = set(target_weights)
        tracked = set(target_ids)
        if self._proxy_weight_mode:
            tracked.add(QQQ_PROXY_SECURITY_ID)
        for row in self._resolution.resolved:
            sid = row["qc_security_id"]
            if sid in self._configured_security_ids:
                tracked.add(row["security_id"])
        quantities = self._current_quantities(tracked)
        census = target_ids | set(quantities)
        prices = {
            security_id: self._positive_price(security_id, session)
            for security_id in sorted(census)
        }
        if any(value is None for value in prices.values()):
            self._skipped_unpriced_decision_count += 1
            return None
        return _orders.plan_rebalance(
            rebalance_id="arv2-qqq-order-" + session,
            starting_cash=self._portfolio_cash(),
            current_quantities=quantities,
            reference_prices=prices,
            target_weights=target_weights,
        )

    def _submit_plan(self, plan):
        registered = _orders.register_idempotent_rebalance(plan)
        self._open_plan = registered
        self._open_plan_events = []
        self._open_order_ids = {}
        if not registered.intents:
            self._close_open_plan()
            return
        for intent in registered.intents:
            _orders.validate_backtest_pre_submit(
                live_mode=self._backtest_flag(),
                candidate_plan=plan,
                registered_plan=registered,
            )
            symbol = (
                self._qqq_benchmark_symbol
                if self._proxy_weight_mode
                and intent.security_id == QQQ_PROXY_SECURITY_ID
                else self._resolution.symbol_for_security(intent.security_id)
            )
            if symbol is None:
                raise _Refusal(
                    "order-level intent lost its FIGI resolution"
                )
            quantity = (
                -intent.quantity
                if intent.side == "SELL"
                else intent.quantity
            )
            if self._pending_submission_events is not None:
                raise _Refusal(
                    "order-level nested MOO submission is unsupported"
                )
            # Authenticate synchronous events against the returned ticket.
            self._pending_submission_events = []
            self._pending_submission_event_keys = set()
            try:
                ticket = self._algorithm.market_on_open_order(
                    symbol,
                    quantity,
                    tag=intent.client_order_id,
                )
                staged = tuple(self._pending_submission_events)
            finally:
                self._pending_submission_events = None
                self._pending_submission_event_keys = None
            try:
                order_id = ticket.order_id
            except Exception as exc:
                raise _Refusal(
                    "order-level MOO ticket is unreadable"
                ) from exc
            if type(order_id) is not int or order_id < 0 or order_id in self._open_order_ids:
                raise _Refusal(
                    "order-level MOO ticket identity changed"
                )
            if any(item[0] != order_id for item in staged):
                raise _Refusal(
                    "synchronous QC event does not match returned MOO ticket"
                )
            self._open_order_ids[order_id] = intent
            self._submitted_order_count += 1
            for staged_id, staged_event_id, staged_status, event in staged:
                if (
                    event.order_id != staged_id
                    or str(event.id) != staged_event_id
                    or self._order_status_text(event.status) != staged_status
                ):
                    raise _Refusal(
                        "synchronous QC event changed before replay"
                    )
                self.on_order_event(event)

    def on_after_close(self):
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
        if (
            self._profile["evaluation_start_session"]
            <= session
            <= FINAL_EXECUTION_SESSION
        ):
            self._observe_strategy_account(session)
        if session not in self._decision_set:
            return False
        self._close_open_plan()
        snapshot = self._score_runtime.score(
            self._session_positions[session]
        )
        benchmark_measures = self._pit_benchmark_measures(session)
        if self._proxy_weight_mode:
            stock_measures = {
                security_id: weight
                for security_id, weight in benchmark_measures.items()
                if security_id != QQQ_PROXY_SECURITY_ID
            }
        else:
            stock_measures = benchmark_measures
        scores = {
            security_id: score
            for security_id, score in (
                snapshot.primary_view_firm_specific_scores.items()
            )
            if security_id in stock_measures
        }
        try:
            sectors = _tilt.sector_map_from_memberships(
                stock_measures,
                snapshot.memberships,
                scores,
            )
            if self._proxy_weight_mode and QQQ_PROXY_SECURITY_ID in benchmark_measures:
                sectors[QQQ_PROXY_SECURITY_ID] = (
                    _tilt.RESERVED_STRUCTURAL_ZERO_SECTOR_ID
                )
        except _tilt.BoundedBenchmarkTiltError as exc:
            raise _Refusal(str(exc)) from exc
        tilt = _tilt.build_benchmark_tilt(
            benchmark_measures, scores, sectors
        )
        if tilt.status == _tilt.TILT_ENABLED:
            self._tilt_enabled_count += 1
        elif tilt.status == _tilt.TILT_UNDERFILLED:
            self._tilt_underfilled_count += 1
        else:
            raise _Refusal(
                "order-level QQQ tilt status changed"
            )
        self._tilted_name_count_sum += tilt.tilted_name_count
        self._one_way_active_share_sum += tilt.one_way_active_share
        plan = self._build_plan(session, tilt.selected_weights)
        self._decision_count += 1
        if plan is not None:
            if self._preopen_mode:
                next_position = self._session_positions[session] + 1
                if (
                    self._pending_preopen is not None
                    or next_position >= len(self._session_axis)
                    or self._session_axis[next_position] > FINAL_EXECUTION_SESSION
                ):
                    raise _Refusal(
                        "order-level next authenticated execution is unavailable"
                    )
                self._pending_preopen = (self._session_axis[next_position], plan)
            else:
                self._submit_plan(plan)
        return True

    def on_before_open(self):
        if not self._preopen_mode or not self._initialized or self._completed:
            raise _Refusal(
                "order-level preopen callback escaped its V6 runtime state"
            )
        _orders.validate_backtest_initialize(live_mode=self._backtest_flag())
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
        observed_cash = self._portfolio_cash()
        observed_quantities = self._current_quantities(
            set(dict(plan.target_quantities))
        )
        replan = _orders.require_next_session_preopen(
            expected=expected,
            actual_time=self._algorithm.time,
            planned_cash=plan.starting_cash,
            observed_cash=observed_cash,
            planned_quantities=dict(plan.starting_quantities),
            observed_quantities=observed_quantities,
            error_type=_Refusal,
            cash_increase_replan=self._cash_replan_mode,
        )
        if self._cash_replan_mode:
            self._verify_preopen_holding_census(plan)
        if replan:
            plan = _orders.plan_rebalance(
                rebalance_id=plan.rebalance_id,
                starting_cash=observed_cash,
                current_quantities=observed_quantities,
                reference_prices=dict(plan.reference_prices),
                target_weights=dict(plan.target_weights),
            )
        self._pending_preopen = None
        self._submitted_preopen_sessions.add(session)
        self._submit_plan(plan)
        return True

    def on_data(self, data):
        return None

    def _load_qqq_total_return_observations(self, expected_sessions):
        try:
            typed_history = self._algorithm.history[self._trade_bar_type]
            history = typed_history(
                [self._qqq_benchmark_symbol],
                datetime.strptime(expected_sessions[0], "%Y-%m-%d"),
                datetime.strptime(expected_sessions[-1], "%Y-%m-%d")
                + timedelta(days=1),
                self._daily_resolution,
                fill_forward=False,
                extended_market_hours=False,
                data_normalization_mode=self._total_return_normalization,
            )
        except Exception as exc:
            raise _Refusal(
                "order-level QQQ TOTAL_RETURN history call failed"
            ) from exc
        observations = {}
        open_observations = {}
        expected_sid = _symbol_sid(
            self._qqq_benchmark_symbol, "order-level QQQ benchmark"
        )
        try:
            dictionaries = tuple(history)
        except Exception as exc:
            raise _Refusal(
                "order-level QQQ TOTAL_RETURN history is unreadable"
            ) from exc
        for dictionary in dictionaries:
            try:
                dictionary_session = dictionary.time.date().isoformat()
                items = tuple(dictionary.items())
            except Exception as exc:
                raise _Refusal(
                    "order-level QQQ TOTAL_RETURN batch is unreadable"
                ) from exc
            if dictionary_session not in expected_sessions or len(items) != 1:
                raise _Refusal(
                    "order-level QQQ TOTAL_RETURN batch shape changed"
                )
            symbol, bar = items[0]
            if (
                _symbol_sid(symbol, "order-level QQQ history key")
                != expected_sid
                or _symbol_sid(bar.symbol, "order-level QQQ history bar")
                != expected_sid
                or bar.time.date().isoformat() != dictionary_session
                or dictionary_session in observations
            ):
                raise _Refusal(
                    "order-level QQQ TOTAL_RETURN identity changed"
                )
            try:
                raw_open = bar.open
                raw_close = bar.close
            except AttributeError as exc:
                raise _Refusal(
                    "order-level QQQ TOTAL_RETURN bar lacks exact OHLC input"
                ) from exc
            open_observations[dictionary_session] = _decimal(
                raw_open,
                "order-level QQQ TOTAL_RETURN adjusted open",
                positive=True,
            )
            observations[dictionary_session] = _decimal(
                raw_close,
                "order-level QQQ TOTAL_RETURN adjusted close",
                positive=True,
            )
        result = tuple(
            (session, observations[session])
            for session in expected_sessions
            if session in observations
        )
        if len(result) != len(expected_sessions):
            raise _Refusal(
                "order-level QQQ TOTAL_RETURN history is incomplete"
            )
        self._benchmark_observations = dict(result)
        if set(open_observations) != set(expected_sessions):
            raise _Refusal(
                "order-level QQQ TOTAL_RETURN open history is incomplete"
            )
        self._benchmark_open_observations = open_observations
        return result

    def on_order_event(self, event):
        if self._open_plan is None:
            raise _Refusal(
                "order-level event arrived without an open rebalance"
            )
        try:
            order_id = event.order_id
            event_id = event.id
            status = self._order_status_text(event.status)
        except Exception as exc:
            raise _Refusal(
                "order-level QC event is unreadable"
            ) from exc
        if type(order_id) is not int or order_id < 0:
            raise _Refusal(
                "order-level QC event order identity changed"
            )
        if type(event_id) not in (int, str) or str(event_id) == "":
            raise _Refusal(
                "order-level QC event identity changed"
            )
        event_key = (order_id, str(event_id))
        if self._pending_submission_events is not None:
            if event_key in self._pending_submission_event_keys:
                raise _Refusal(
                    "duplicate synchronous QC event"
                )
            if len(self._pending_submission_events) >= MAX_SYNCHRONOUS_ORDER_EVENTS:
                raise _Refusal(
                    "synchronous QC event buffer exceeded"
                )
            self._pending_submission_event_keys.add(event_key)
            self._pending_submission_events.append(
                (order_id, str(event_id), status, event)
            )
            return
        intent = self._open_order_ids.get(order_id)
        if intent is None:
            raise _Refusal(
                "order-level event references an unknown QC order"
            )
        if status in IGNORED_ORDER_STATUSES:
            return
        if status in _orders.FILL_STATUSES:
            quantity = event.fill_quantity
            if type(quantity) not in (int, float, Decimal):
                raise _Refusal(
                    "order-level fill quantity changed type"
                )
            signed_quantity = _decimal(
                quantity,
                "order-level signed fill quantity",
            )
            if (
                (intent.side == "SELL" and signed_quantity >= 0)
                or (intent.side == "BUY" and signed_quantity <= 0)
            ):
                raise _Refusal(
                    "order-level fill quantity sign disagrees with order side"
                )
            absolute = _decimal(
                abs(signed_quantity),
                "order-level fill quantity",
                positive=True,
            )
            integral = absolute.to_integral_value()
            if absolute != integral:
                raise _Refusal(
                    "order-level fill quantity is not a whole share"
                )
            fill_quantity = int(integral)
            fill_price = _decimal(
                event.fill_price,
                "order-level fill price",
                positive=True,
            )
            try:
                fee_value = event.order_fee.value
                raw_fee_amount = fee_value.amount
                fee_currency = fee_value.currency
            except AttributeError as exc:
                raise _Refusal(
                    "order-level QC fill fee is unreadable"
                ) from exc
            engine_fee_amount = _decimal(
                raw_fee_amount,
                "order-level QC fill fee amount",
                nonnegative=True,
            )
            if type(fee_currency) is not str or fee_currency != "USD":
                raise _Refusal(
                    "order-level QC fill fee currency is not exact USD"
                )
        elif status in {_orders.CANCELED, _orders.INVALID}:
            fill_quantity = 0
            fill_price = None
            engine_fee_amount = None
            fee_currency = None
        else:
            raise _Refusal(
                "order-level QC event status is unsupported"
                + (
                    _orders.qc_order_status_enum_diagnostic(
                        event.status
                    ) if self._enum_order_status_mode else ""
                )
            )
        core_event = _orders.FillEvent(
            event_id="qc-event-" + str(order_id) + "-" + str(event_id),
            rebalance_id=self._open_plan.rebalance_id,
            client_order_id=intent.client_order_id,
            status=status,
            fill_quantity=fill_quantity,
            fill_price=fill_price,
            engine_fee_amount=engine_fee_amount,
            engine_fee_currency=fee_currency,
        )
        self._open_plan_events.append(core_event)

    def _aggregate_record(self):
        expected_sessions = tuple(
            session
            for session in self._package.evaluator_input.session_axis
            if self._profile["evaluation_start_session"]
            <= session
            <= FINAL_EXECUTION_SESSION
        )
        observations = self._load_qqq_total_return_observations(
            expected_sessions
        )
        calendar_binding = _benchmark_close_binding(
            observations, expected_sessions
        )
        first_decision_session = self._decision_sessions[0]
        try:
            first_execution_session = expected_sessions[
                expected_sessions.index(first_decision_session) + 1
            ]
        except (IndexError, ValueError) as exc:
            raise _Refusal(
                "order-level first QQQ execution session is unavailable"
            ) from exc
        qqq_path, binding = _execution_matched_qqq_path(
            close_observations=observations,
            open_observations=self._benchmark_open_observations,
            expected_sessions=expected_sessions,
            first_execution_session=first_execution_session,
        )
        if set(self._strategy_equity_observations) != set(expected_sessions):
            raise _Refusal(
                "order-level strategy equity path is incomplete"
            )
        strategy_observations = tuple(
            (session, self._strategy_equity_observations[session])
            for session in expected_sessions
        )
        strategy_metrics = _path_metrics(strategy_observations)
        qqq_metrics = _path_metrics(qqq_path)
        qqq_return = qqq_metrics["total_return"]
        calendar_qqq_return = _benchmark_total_return(observations)
        strategy_return = strategy_metrics["total_return"]
        mean_gross = sum(
            self._gross_exposure_observations.values(), Decimal(0)
        ) / Decimal(len(expected_sessions))
        mean_cash = sum(
            self._cash_weight_observations.values(), Decimal(0)
        ) / Decimal(len(expected_sessions))
        lifecycle = _orders.aggregate_lifecycle_records(
            tuple(self._lifecycle_records), self._submitted_order_count
        )
        lifecycle_digest = lifecycle["digest"]
        fee = lifecycle["fee"]
        filled_notional = lifecycle["filled_notional"]
        actual_engine_fee = lifecycle["actual_fee"]
        if (
            self._decision_count <= 0
            or len(self._pit_coverage_records) != self._decision_count
        ):
            raise _Refusal(
                "order-level PIT coverage path is incomplete"
            )
        filled_order_count = lifecycle["filled"]
        canceled_order_count = lifecycle["canceled"]
        invalid_order_count = lifecycle["invalid"]
        orders_with_any_fill_count = lifecycle["orders_with_any_fill"]
        mean_target_error = lifecycle["mean_target_error"]
        maximum_target_error = lifecycle["maximum_target_error"]
        execution_failure = lifecycle["execution_failure"]
        fee_mismatch = lifecycle["fee_mismatch"]
        run_valid = (
            not execution_failure
            and self._skipped_unpriced_decision_count == 0
            and len(self._lifecycle_records) == self._decision_count
        )
        coverage_values, coverage_stats = _orders.coverage_statistics(
            self._pit_coverage_records, self._proxy_weight_mode,
        )
        summary = {
            "schema": PROXY_SUMMARY_SCHEMA if self._proxy_weight_mode else SUMMARY_SCHEMA,
            "score_source_view_id": _score.PRIMARY_SOURCE_VIEW_ID,
            "target_weight_basis": PROXY_TARGET_WEIGHT_BASIS if self._proxy_weight_mode else TARGET_WEIGHT_BASIS,
            "decision_count": self._decision_count,
            "completed_rebalance_count": len(self._lifecycle_records),
            "submitted_order_count": self._submitted_order_count,
            "skipped_unpriced_decision_count": self._skipped_unpriced_decision_count,
            "tilt_enabled_count": self._tilt_enabled_count,
            "tilt_underfilled_count": self._tilt_underfilled_count,
            "mean_tilted_name_count": _decimal_text(
                Decimal(self._tilted_name_count_sum) / Decimal(self._decision_count)
            ),
            "mean_one_way_active_share": _decimal_text(self._one_way_active_share_sum / Decimal(self._decision_count)),
            "pit_history_call_count": self._pit_history_call_count,
            "pit_source_row_count": self._pit_source_row_count,
            "named_figi_refusal_count": self._resolution.named_refusal_count,
            "modeled_fee_bps_per_side": _orders.MODELED_FEE_BPS_PER_SIDE,
            "modeled_fee_amount": _decimal_text(fee),
            "actual_engine_fee_amount": _decimal_text(actual_engine_fee),
            "actual_engine_fee_effective_bps_per_side": _decimal_text(
                Decimal(0) if filled_notional == 0 else actual_engine_fee / filled_notional * Decimal(10_000)
            ),
            "modeled_minus_actual_fee_amount": _decimal_text(fee - actual_engine_fee),
            "fee_mismatch": fee_mismatch,
            "lifecycle_modeled_fee_basis": "actual_fill_price_times_filled_quantity",
            "engine_fee_model_basis": "current_minute_trade_bar_open_times_full_order_quantity_at_fee_assessment",
            "total_filled_notional": _decimal_text(filled_notional),
            "filled_order_count_sum": filled_order_count,
            "canceled_order_count_sum": canceled_order_count,
            "invalid_order_count_sum": invalid_order_count,
            "orders_with_any_fill_count_sum": orders_with_any_fill_count,
            "mean_reference_mark_target_weight_l1_error": _decimal_text(mean_target_error),
            "maximum_reference_mark_target_weight_l1_error": _decimal_text(maximum_target_error),
            "execution_failure": execution_failure,
            "run_valid": run_valid,
            **coverage_stats,
            "maximum_positive_constituent_weight_total": _decimal_text(
                max(coverage_values["positive_constituent_weight_total"])
            ),
            "minimum_required_positive_constituent_weight_total": _decimal_text(
                MINIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL
            ),
            "maximum_allowed_positive_constituent_weight_total": _decimal_text(
                MAXIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL
            ),
            "minimum_required_resolved_constituent_weight_ratio": _decimal_text(
                MINIMUM_PROXY_RESOLVED_CONSTITUENT_WEIGHT_RATIO if self._proxy_weight_mode
                else MINIMUM_RESOLVED_CONSTITUENT_WEIGHT_RATIO
            ),
            "maximum_constituent_snapshot_age_sessions": max(
                row["constituent_snapshot_age_sessions"]
                for row in self._pit_coverage_records
            ),
            "pit_coverage_path_sha256": _sha(
                {
                    "schema": PROXY_COVERAGE_PATH_SCHEMA if self._proxy_weight_mode else COVERAGE_PATH_SCHEMA,
                    "records": self._pit_coverage_records,
                }
            ),
            "pit_target_weight_path_sha256": _sha(
                {
                    "schema": PROXY_TARGET_WEIGHT_PATH_SCHEMA if self._proxy_weight_mode else TARGET_WEIGHT_PATH_SCHEMA,
                    "records": [
                        {
                            "session": row["session"],
                            "pit_constituent_weight_map_sha256": row["pit_constituent_weight_map_sha256"],
                        }
                        for row in self._pit_coverage_records
                    ],
                }
            ),
            "starting_equity": _decimal_text(STARTING_CASH),
            "ending_equity": _decimal_text(self._portfolio_equity()),
            "strategy_total_return": _decimal_text(strategy_return),
            "strategy_maximum_drawdown": _decimal_text(strategy_metrics["maximum_drawdown"]),
            "strategy_annualized_volatility": _decimal_text(strategy_metrics["annualized_volatility"]),
            "strategy_zero_rate_sharpe": (
                None
                if strategy_metrics["zero_rate_sharpe"] is None
                else _decimal_text(strategy_metrics["zero_rate_sharpe"])
            ),
            "mean_gross_exposure": _decimal_text(mean_gross),
            "mean_cash_weight": _decimal_text(mean_cash),
            "strategy_equity_path_sha256": _sha(
                {
                    "schema": "arv2-order-level-equity-path-v1",
                    "observations": [
                        [session, _decimal_text(value)]
                        for session, value in strategy_observations
                    ],
                }
            ),
            "QQQ_total_return": _decimal_text(qqq_return),
            "QQQ_normalization_mode": binding["normalization_mode"],
            "QQQ_observation": binding["observation"],
            "QQQ_first_execution_session": binding["first_execution_session"],
            "QQQ_target_gross_exposure": binding["target_gross_exposure"],
            "QQQ_entry_fee_bps_per_side": binding["entry_fee_bps_per_side"],
            "QQQ_maximum_drawdown": _decimal_text(qqq_metrics["maximum_drawdown"]),
            "QQQ_annualized_volatility": _decimal_text(qqq_metrics["annualized_volatility"]),
            "QQQ_zero_rate_sharpe": (
                None
                if qqq_metrics["zero_rate_sharpe"] is None
                else _decimal_text(qqq_metrics["zero_rate_sharpe"])
            ),
            "strategy_minus_QQQ_total_return": _decimal_text(strategy_return - qqq_return),
            "QQQ_observation_count": binding["observation_count"],
            "QQQ_return_interval_count": binding["return_interval_count"],
            "QQQ_raw_observation_sha256": binding["raw_observation_sha256"],
            "QQQ_return_path_sha256": binding["return_path_sha256"],
            "QQQ_calendar_close_total_return": _decimal_text(calendar_qqq_return),
            "QQQ_calendar_close_observation_count": calendar_binding["observation_count"],
            "QQQ_calendar_close_raw_observation_sha256": calendar_binding["raw_observation_sha256"],
            "QQQ_calendar_close_return_path_sha256": calendar_binding["return_path_sha256"],
            "order_lifecycle_sha256": lifecycle_digest,
            "raw_order_rows_in_summary": False,
            "raw_security_rows_in_summary": False,
            "backtest_only": True,
            "simulated_orders": True,
            "live_orders": False,
            "trading": False,
        }
        if self._proxy_weight_mode:
            summary.update({
                "qqq_proxy_overlap_disclosure": QQQ_PROXY_OVERLAP_DISCLOSURE,
                "mean_qqq_proxy_constituent_weight_ratio": _decimal_text(
                    Decimal(1) - Decimal(summary["mean_resolved_constituent_weight_ratio"])
                ),
                "minimum_qqq_proxy_constituent_weight_ratio": _decimal_text(
                    Decimal(1) - max(coverage_values["resolved_constituent_weight_ratio"])
                ),
                "maximum_qqq_proxy_constituent_weight_ratio": _decimal_text(
                    Decimal(1) - Decimal(summary["minimum_resolved_constituent_weight_ratio"])
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
        if self._algorithm.time.date().isoformat() != FINAL_EXECUTION_SESSION:
            raise _Refusal(
                "order-level backtest ended outside the exact final session"
            )
        self._close_open_plan()
        if self._decision_count != len(self._decision_sessions):
            raise _Refusal(
                "order-level decision schedule did not complete"
            )
        aggregates = self._aggregate_record()
        aggregates_sha256 = _sha(aggregates)
        meta = {
            "schema": "arv2-qqq-order-level-tilt-runtime-meta-v1",
            "profile_id": self._profile["profile_id"],
            "profile_sha256": self._profile["profile_sha256"],
            "package_id": self._package.package_id,
            "package_sha256": self._package.package_sha256,
            "activation_manifest_sha256": (
                self._package.activation_manifest_sha256
            ),
            "symbol_resolution_id": self._resolution.resolution_id,
            "symbol_resolution_sha256": self._resolution.resolution_sha256,
            "score_source_view_id": _score.PRIMARY_SOURCE_VIEW_ID,
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
            META_STATISTIC_NAME: _canonical(meta).decode("ascii"),
            AGGREGATES_STATISTIC_NAME: _canonical(aggregates).decode("ascii"),
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
    "AcceptedRiskQqqOrderLevelQcRuntime",
    "AcceptedRiskQqqOrderLevelQcRuntimeError",
    "DECISION_CUTOFF_SESSION",
    "FINAL_EXECUTION_SESSION",
    "MINIMUM_RESOLVED_CONSTITUENT_WEIGHT_RATIO",
    "MINIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL",
    "MAXIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL",
    "META_STATISTIC_NAME",
    "PROFILE_2025_ID",
    "PROFILE_2026_ID",
    "PROFILE_IDS",
    "STARTING_CASH",
    "expected_custom_summary_statistic_names",
    "require_qqq_order_level_profile",
)
