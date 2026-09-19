"""Backtest-only QQQ bounded-tilt runtime with simulated QC orders.

The runtime consumes the authenticated accepted-risk input package, advances
the unchanged R055 score only through simulated time, constructs the frozen
sector-neutral QQQ benchmark tilt, and submits whole-share market-on-open
orders in a QuantConnect *backtest*.  It has no live, paper, deployment,
broker-credential, or funded-account mode.

This file intentionally has no ``__future__`` import: QuantConnect injects a
source prelude, so a future import here would no longer be first and would
make the cloud project fail to compile.
"""

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

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
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_market_cap_stock_portfolio_tilt as _tilt,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_order_level_core as _orders,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_order_level_input_runtime as _input,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_qc_figi as _figi,
    )
    from research.analyst_revisions_v2_qc import (
        accepted_risk_sequential_r055_score as _score,
    )


class AcceptedRiskQqqOrderLevelQcRuntimeError(ValueError):
    """The fixed order profile or simulated QC boundary was refused."""


PROFILE_SCHEMA = "arv2-qqq-order-level-tilt-profile-v1"
PROFILE_2025_ID = "arv2-qqq-order-level-tilt-2025-cutoff-v1"
PROFILE_2026_ID = "arv2-qqq-order-level-tilt-2026-cutoff-v1"
PROFILE_IDS = (PROFILE_2025_ID, PROFILE_2026_ID)
DECISION_CUTOFF_SESSION = "2026-09-16"
FINAL_EXECUTION_SESSION = "2026-09-17"
STARTING_CASH = Decimal("1000000")
META_STATISTIC_NAME = "ARV2_ORDER_LEVEL_META"
AGGREGATES_STATISTIC_NAME = "ARV2_ORDER_LEVEL_AGGREGATES"
MAXIMUM_STATISTIC_BYTES = 4096
SUMMARY_SCHEMA = "arv2-qqq-order-level-tilt-summary-v3"
QQQ_TICKER = "QQQ"
PIT_LOOKBACK_CALENDAR_DAYS = 45
MINIMUM_CAP_COVERED_CONSTITUENT_WEIGHT_RATIO = Decimal("0.99")
MINIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL = Decimal("0.95")
MAXIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL = Decimal("1.05")
MAXIMUM_FUNDAMENTAL_SNAPSHOT_AGE_SESSIONS = 1
EXACT_CONSTITUENT_SNAPSHOT_AGE_SESSIONS = 1
IGNORED_ORDER_STATUSES = frozenset(
    {"New", "Submitted", "UpdateSubmitted", "CancelPending", "None"}
)


def _canonical(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AcceptedRiskQqqOrderLevelQcRuntimeError(
            "order-level value is not canonical ASCII JSON"
        ) from exc


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _decimal_text(value):
    if type(value) is not Decimal or not value.is_finite():
        raise AcceptedRiskQqqOrderLevelQcRuntimeError(
            "order-level aggregate is not an exact finite Decimal"
        )
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _decimal(value, name, *, positive=False, nonnegative=False):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AcceptedRiskQqqOrderLevelQcRuntimeError(
            name + " is not decimal"
        ) from exc
    if (
        not result.is_finite()
        or (positive and result <= 0)
        or (nonnegative and result < 0)
    ):
        raise AcceptedRiskQqqOrderLevelQcRuntimeError(
            name + " is outside its finite bound"
        )
    return result


def _symbol_sid(symbol, name):
    try:
        value = str(symbol.id)
    except Exception as exc:
        raise AcceptedRiskQqqOrderLevelQcRuntimeError(
            name + " symbol identity is unreadable"
        ) from exc
    if type(value) is not str or not value:
        raise AcceptedRiskQqqOrderLevelQcRuntimeError(
            name + " symbol identity changed"
        )
    return value


_benchmark_total_return = _benchmark.benchmark_total_return


_benchmark_close_binding = _benchmark.benchmark_close_binding


_execution_matched_qqq_path = _benchmark.execution_matched_qqq_path


_path_metrics = _benchmark.path_metrics


def _profile(profile_id, start_session):
    if (
        _benchmark.QQQ_TICKER != QQQ_TICKER
        or _benchmark.TARGET_GROSS_EXPOSURE
        != _tilt.TARGET_GROSS_EXPOSURE
        or _benchmark.ENTRY_FEE_RATE_PER_SIDE
        != _orders.MODELED_FEE_RATE_PER_SIDE
        or _benchmark.ENTRY_FEE_BPS_PER_SIDE
        != _orders.MODELED_FEE_BPS_PER_SIDE
    ):
        raise AcceptedRiskQqqOrderLevelQcRuntimeError(
            "execution-matched QQQ benchmark constants changed"
        )
    start = datetime.strptime(start_session, "%Y-%m-%d")
    record = {
        "schema": PROFILE_SCHEMA,
        "profile_id": profile_id,
        "universe_proxy_ticker": QQQ_TICKER,
        "evaluation_start_session": start_session,
        "start_year": start.year,
        "start_month": start.month,
        "start_day": start.day,
        "decision_cutoff_session": DECISION_CUTOFF_SESSION,
        "final_execution_session": FINAL_EXECUTION_SESSION,
        "decision_schedule": (
            "first_authenticated_session_of_each_ISO_week_plus_exact_cutoff"
        ),
        "decision_timing": "after_QQQ_market_close",
        "execution_timing": "next_authenticated_session_market_on_open",
        "starting_cash": _decimal_text(STARTING_CASH),
        "target_gross_exposure": _decimal_text(_tilt.TARGET_GROSS_EXPOSURE),
        "signal": "exact_unchanged_R055_primary_view_firm_specific",
        "score_source_view_id": _score.PRIMARY_SOURCE_VIEW_ID,
        "portfolio": "QQQ_market_cap_benchmark_plus_frozen_sector_neutral_tilt",
        "price_normalization": "RAW",
        "resolution": "MINUTE",
        "benchmark_price_normalization": "TOTAL_RETURN",
        "benchmark_observation": (
            "EXECUTION_MATCHED_FIRST_MOO_OPEN_THEN_SESSION_CLOSE"
        ),
        "benchmark_target_gross_exposure": _decimal_text(
            _tilt.TARGET_GROSS_EXPOSURE
        ),
        "benchmark_entry_fee_bps_per_side": (
            _orders.MODELED_FEE_BPS_PER_SIDE
        ),
        "calendar_benchmark_observation": "SESSION_CLOSE_CONTEXT_ONLY",
        "minimum_cap_covered_constituent_weight_ratio": _decimal_text(
            MINIMUM_CAP_COVERED_CONSTITUENT_WEIGHT_RATIO
        ),
        "minimum_positive_constituent_weight_total": _decimal_text(
            MINIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL
        ),
        "maximum_positive_constituent_weight_total": _decimal_text(
            MAXIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL
        ),
        "maximum_fundamental_snapshot_age_sessions": (
            MAXIMUM_FUNDAMENTAL_SNAPSHOT_AGE_SESSIONS
        ),
        "exact_constituent_snapshot_age_sessions": (
            EXACT_CONSTITUENT_SNAPSHOT_AGE_SESSIONS
        ),
        "constituent_source_session_rule": (
            "QC_daily_Series_collection_EndTime_minus_one_calendar_day"
        ),
        "reference_price_freshness": "exact_decision_session_last_data_end_time",
        "order_type": "MARKET_ON_OPEN",
        "fee_bps_per_side": _orders.MODELED_FEE_BPS_PER_SIDE,
        "lifecycle_modeled_fee_basis": (
            "actual_fill_price_times_filled_quantity"
        ),
        "engine_fee_model_basis": (
            "current_minute_trade_bar_open_times_full_order_quantity_at_fee_assessment"
        ),
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
    return {**record, "profile_sha256": _sha(record)}


_PROFILES = {
    PROFILE_2025_ID: _profile(PROFILE_2025_ID, "2025-01-02"),
    PROFILE_2026_ID: _profile(PROFILE_2026_ID, "2026-01-02"),
}


def require_qqq_order_level_profile(profile_id):
    if type(profile_id) is not str or profile_id not in _PROFILES:
        raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
        fundamental_universe,
        qqq_constituent_universe,
        minute_resolution,
        raw_normalization,
        trade_bar_type,
        daily_resolution,
        total_return_normalization,
        fee_model_factory,
        slippage_model_factory,
    ):
        self._algorithm = algorithm
        self._activation_manifest_key = activation_manifest_key
        self._activation_manifest_sha256 = activation_manifest_sha256
        self._activation_manifest_byte_count = activation_manifest_byte_count
        self._profile = require_qqq_order_level_profile(profile_id)
        self._authority_benchmark_symbol = authority_benchmark_symbol
        self._qqq_benchmark_symbol = qqq_benchmark_symbol
        self._fundamental_universe = fundamental_universe
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
        self._decision_sessions = ()
        self._decision_set = frozenset()
        self._configured_security_ids = set()
        self._open_plan = None
        self._open_plan_events = []
        self._open_order_ids = {}
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
        # The projection firewall permits this one read and no live-mode write.
        return self._algorithm.live_mode

    def _portfolio_equity(self):
        return _decimal(
            self._algorithm.portfolio.total_portfolio_value,
            "QC total portfolio value",
            positive=True,
        )

    def _portfolio_cash(self):
        return _decimal(
            self._algorithm.portfolio.cash,
            "QC portfolio cash",
            nonnegative=True,
        )

    def _observe_strategy_account(self, session):
        if session in self._strategy_equity_observations:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
        if (
            type(axis) is not tuple
            or tuple(sorted(set(axis))) != axis
            or any(type(item) is not str for item in axis)
        ):
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level authenticated session axis changed"
            )
        try:
            start = axis.index(start_session)
            cutoff = axis.index(DECISION_CUTOFF_SESSION)
            final = axis.index(FINAL_EXECUTION_SESSION)
        except ValueError as exc:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level profile escaped the authenticated session axis"
            ) from exc
        if not start < cutoff < final or final != cutoff + 1:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level cutoff lacks its exact next execution session"
            )
        decisions = []
        prior_week = None
        for session in axis[start : cutoff + 1]:
            parsed = datetime.strptime(session, "%Y-%m-%d")
            week = (parsed.isocalendar().year, parsed.isocalendar().week)
            if week != prior_week:
                decisions.append(session)
                prior_week = week
        if decisions[-1] != DECISION_CUTOFF_SESSION:
            decisions.append(DECISION_CUTOFF_SESSION)
        if tuple(sorted(set(decisions))) != tuple(decisions):
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level decision schedule changed"
            )
        return tuple(decisions), start, cutoff, final

    def initialize(self):
        if self._initialized:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level runtime initialized more than once"
            )
        _orders.validate_backtest_initialize(live_mode=self._backtest_flag())
        if (
            self._fundamental_universe is None
            or self._qqq_constituent_universe is None
            or self._authority_benchmark_symbol is None
            or self._qqq_benchmark_symbol is None
            or self._trade_bar_type is None
            or self._daily_resolution is None
            or self._total_return_normalization is None
            or not callable(self._fee_model_factory)
            or not callable(self._slippage_model_factory)
        ):
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level QC dependency inventory changed"
            )
        if self._portfolio_equity() != STARTING_CASH:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
        self._decision_sessions = decisions
        self._decision_set = frozenset(decisions)
        self._initialized = True

    def configure_security(self, security):
        if not self._initialized:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    "order-level QQQ constituent SID is duplicated"
                )
            accepted[sid] = symbol
        return [accepted[sid] for sid in sorted(accepted)]

    def _history_inventory(self, universe, start, end, name, *, fundamental):
        try:
            history = self._algorithm.history(
                universe, start, end, flatten=False
            )
        except Exception as exc:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                name + " history call failed"
            ) from exc
        self._pit_history_call_count += 1
        expected_sid = _input.universe_sid(universe, name)
        result = {}
        for item in _input.history_items(history, name):
            if type(item) is not tuple or len(item) != 2:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    name + " history item shape changed"
                )
            key, raw_rows = item
            if type(key) is not tuple or len(key) != 2:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    name + " history index shape changed"
                )
            universe_symbol, raw_time = key
            if _symbol_sid(universe_symbol, name) != expected_sid:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    name + " history universe identity changed"
                )
            observed = (
                _input.local_collection_time(raw_time, name + " collection")
                if fundamental
                else _input.constituent_collection_time(
                    raw_time, name + " collection"
                )
            )
            if not start <= observed < end:
                continue
            if observed in result:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    name + " duplicated a collection time"
                )
            rows = _input.collection_rows(raw_rows, name)
            result[observed] = rows
            self._pit_source_row_count += len(rows)
        return result

    @staticmethod
    def _latest(inventory, cutoff, name):
        prior = tuple(item for item in inventory if item < cutoff)
        if not prior:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                name + " has no strictly prior collection"
            )
        key = max(prior)
        return key, inventory[key]

    def _snapshot_age_sessions(
        self, observed, decision_session, name, *, permit_non_session=False
    ):
        if not isinstance(observed, datetime):
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                name + " collection time changed type"
            )
        observed_date = observed.date().isoformat()
        try:
            decision_position = self._session_positions[decision_session]
        except (KeyError, TypeError) as exc:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                name + " collection is outside the authenticated session axis"
            ) from exc
        observed_session = observed_date
        if observed_session not in self._session_positions:
            sessions = tuple(self._session_positions)
            if (
                permit_non_session is not True
                or not sessions
                or observed_date < sessions[0]
                or observed_date > sessions[-1]
            ):
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    name + " collection is outside the authenticated session axis"
                )
            observed_session = next(
                session for session in sessions if session >= observed_date
            )
        observed_position = self._session_positions[observed_session]
        age = decision_position - observed_position
        if age < 0:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                name + " collection is after its decision session"
            )
        return age

    @staticmethod
    def _positive_constituent_weights(rows):
        members = _input.collection_rows(
            rows, "order-level PIT QQQ constituent weights"
        )
        positive_sids = _input.positive_constituent_sids(members)
        result = {}
        for row in members:
            try:
                raw_weight = row.weight
            except AttributeError as exc:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    "order-level PIT QQQ constituent weight is unreadable"
                ) from exc
            if raw_weight is None:
                continue
            weight = _decimal(
                raw_weight,
                "order-level PIT QQQ constituent weight",
            )
            if weight <= 0:
                continue
            sid = _input.row_sid(row, "order-level PIT QQQ constituent")
            if sid not in positive_sids:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    "order-level PIT QQQ positive member identity changed"
                )
            result[sid] = weight
        if set(result) != set(positive_sids):
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level PIT QQQ constituent weights are unavailable"
            )
        return result

    def _covered_market_caps(
        self,
        session,
        constituent_weights,
        caps_by_sid,
        *,
        fundamental_age_sessions,
        constituent_age_sessions,
    ):
        if (
            type(constituent_weights) is not dict
            or not constituent_weights
            or any(
                type(sid) is not str
                or not sid
                or type(weight) is not Decimal
                or not weight.is_finite()
                or weight <= 0
                for sid, weight in constituent_weights.items()
            )
        ):
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level PIT QQQ constituent weights are unavailable"
            )
        security_by_sid = {
            row["qc_security_id"]: row["security_id"]
            for row in self._resolution.resolved
        }
        resolved_sids = set(constituent_weights) & set(security_by_sid)
        covered_sids = resolved_sids & set(caps_by_sid)
        total_weight = sum(constituent_weights.values(), Decimal(0))
        resolved_weight = sum(
            (constituent_weights[sid] for sid in resolved_sids), Decimal(0)
        )
        covered_weight = sum(
            (constituent_weights[sid] for sid in covered_sids), Decimal(0)
        )
        member_count = len(constituent_weights)
        resolved_count = len(resolved_sids)
        covered_count = len(covered_sids)
        if total_weight <= 0:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level PIT QQQ constituent weights are unavailable"
            )
        if not (
            MINIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL
            <= total_weight
            <= MAXIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL
        ):
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level PIT QQQ positive constituent weight total is outside 0.95 to 1.05"
            )
        resolved_weight_ratio = resolved_weight / total_weight
        covered_weight_ratio = covered_weight / total_weight
        record = {
            "session": session,
            "positive_weight_member_count": member_count,
            "resolved_positive_weight_member_count": resolved_count,
            "cap_covered_positive_weight_member_count": covered_count,
            "resolved_member_count_ratio": _decimal_text(
                Decimal(resolved_count) / Decimal(member_count)
            ),
            "cap_covered_member_count_ratio": _decimal_text(
                Decimal(covered_count) / Decimal(member_count)
            ),
            "resolved_constituent_weight_ratio": _decimal_text(
                resolved_weight_ratio
            ),
            "cap_covered_constituent_weight_ratio": _decimal_text(
                covered_weight_ratio
            ),
            "positive_constituent_weight_total": _decimal_text(total_weight),
            "fundamental_snapshot_age_sessions": fundamental_age_sessions,
            "constituent_snapshot_age_sessions": constituent_age_sessions,
        }
        if any(row["session"] == session for row in self._pit_coverage_records):
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level PIT coverage session is duplicated"
            )
        if (
            covered_weight_ratio
            < MINIMUM_CAP_COVERED_CONSTITUENT_WEIGHT_RATIO
        ):
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level PIT QQQ market-cap constituent-weight coverage is below 99 percent"
            )
        result = {}
        for sid in sorted(covered_sids):
            security_id = security_by_sid[sid]
            if security_id in result:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    "order-level PIT QQQ FIGI resolution is not one-to-one"
                )
            result[security_id] = caps_by_sid[sid]
        if not result:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level PIT QQQ market-cap coverage is empty"
            )
        self._pit_coverage_records.append(record)
        return result

    def _pit_market_caps(self, session):
        decision = datetime.strptime(session, "%Y-%m-%d")
        start = decision - timedelta(days=PIT_LOOKBACK_CALENDAR_DAYS)
        end = decision + timedelta(days=1)
        fundamentals = self._history_inventory(
            self._fundamental_universe,
            start,
            end,
            "order-level PIT fundamentals",
            fundamental=True,
        )
        constituents = self._history_inventory(
            self._qqq_constituent_universe,
            start,
            end,
            "order-level PIT QQQ constituents",
            fundamental=False,
        )
        fundamental_time, fundamental_rows = self._latest(
            fundamentals,
            decision.replace(hour=9, minute=30),
            "order-level PIT fundamentals",
        )
        constituent_time, constituent_rows = self._latest(
            constituents,
            decision,
            "order-level PIT QQQ constituents",
        )
        fundamental_age = self._snapshot_age_sessions(
            fundamental_time,
            session,
            "order-level PIT fundamentals",
            permit_non_session=True,
        )
        constituent_age = self._snapshot_age_sessions(
            constituent_time, session, "order-level PIT QQQ constituents"
        )
        if fundamental_age > MAXIMUM_FUNDAMENTAL_SNAPSHOT_AGE_SESSIONS:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level PIT fundamental snapshot exceeds one authenticated session"
            )
        if constituent_age != EXACT_CONSTITUENT_SNAPSHOT_AGE_SESSIONS:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level PIT QQQ constituent snapshot is not the immediately prior authenticated session"
            )
        caps_by_sid = _input.positive_market_caps(fundamental_rows)
        constituent_weights = self._positive_constituent_weights(
            constituent_rows
        )
        return self._covered_market_caps(
            session,
            constituent_weights,
            caps_by_sid,
            fundamental_age_sessions=fundamental_age,
            constituent_age_sessions=constituent_age,
        )

    def _security(self, security_id):
        symbol = self._resolution.symbol_for_security(security_id)
        if symbol is None:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
        try:
            last_data = security.get_last_data()
            observed = last_data.end_time
            if (
                not isinstance(observed, datetime)
                or observed.date().isoformat() != decision_session
            ):
                return None
            price = _decimal(
                security.price,
                "order-level RAW reference price",
                positive=True,
            )
        except (AttributeError, AcceptedRiskQqqOrderLevelQcRuntimeError):
            return None
        return price

    def _current_quantities(self, security_ids):
        quantities = {}
        for security_id in sorted(security_ids):
            symbol, _security = self._security(security_id)
            value = _decimal(
                self._algorithm.portfolio[symbol].quantity,
                "order-level holding quantity",
                nonnegative=True,
            )
            integral = value.to_integral_value()
            if value != integral:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    "order-level holding quantity is not a whole share"
                )
            if integral:
                quantities[security_id] = int(integral)
        return quantities

    def _close_open_plan(self):
        if self._open_plan is None:
            return
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
            symbol = self._resolution.symbol_for_security(intent.security_id)
            if symbol is None:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    "order-level intent lost its FIGI resolution"
                )
            quantity = (
                -intent.quantity
                if intent.side == "SELL"
                else intent.quantity
            )
            ticket = self._algorithm.market_on_open_order(
                symbol,
                quantity,
                tag=intent.client_order_id,
            )
            try:
                order_id = ticket.order_id
            except Exception as exc:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    "order-level MOO ticket is unreadable"
                ) from exc
            if type(order_id) is not int or order_id < 0 or order_id in self._open_order_ids:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    "order-level MOO ticket identity changed"
                )
            self._open_order_ids[order_id] = intent
            self._submitted_order_count += 1

    def on_after_close(self):
        if not self._initialized or self._completed:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level after-close callback escaped runtime state"
            )
        session = self._algorithm.time.date().isoformat()
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
        market_caps = self._pit_market_caps(session)
        scores = {
            security_id: score
            for security_id, score in (
                snapshot.primary_view_firm_specific_scores.items()
            )
            if security_id in market_caps
        }
        try:
            sectors = _tilt.sector_map_from_memberships(
                market_caps,
                snapshot.memberships,
                scores,
            )
        except _tilt.BoundedBenchmarkTiltError as exc:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(str(exc)) from exc
        tilt = _tilt.build_benchmark_tilt(market_caps, scores, sectors)
        if tilt.status == _tilt.TILT_ENABLED:
            self._tilt_enabled_count += 1
        elif tilt.status == _tilt.TILT_UNDERFILLED:
            self._tilt_underfilled_count += 1
        else:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level QQQ tilt status changed"
            )
        self._tilted_name_count_sum += tilt.tilted_name_count
        self._one_way_active_share_sum += tilt.one_way_active_share
        plan = self._build_plan(session, tilt.selected_weights)
        self._decision_count += 1
        if plan is not None:
            self._submit_plan(plan)
        return True

    def on_data(self, data):
        if not self._initialized or self._completed:
            return
        # Order decisions are scheduled after close; QQQ total return is read
        # independently with an explicit per-request normalization at the end.
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
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level QQQ TOTAL_RETURN history is unreadable"
            ) from exc
        for dictionary in dictionaries:
            try:
                dictionary_session = dictionary.time.date().isoformat()
                items = tuple(dictionary.items())
            except Exception as exc:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    "order-level QQQ TOTAL_RETURN batch is unreadable"
                ) from exc
            if dictionary_session not in expected_sessions or len(items) != 1:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    "order-level QQQ TOTAL_RETURN identity changed"
                )
            try:
                raw_open = bar.open
                raw_close = bar.close
            except AttributeError as exc:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level QQQ TOTAL_RETURN history is incomplete"
            )
        self._benchmark_observations = dict(result)
        if set(open_observations) != set(expected_sessions):
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level QQQ TOTAL_RETURN open history is incomplete"
            )
        self._benchmark_open_observations = open_observations
        return result

    @staticmethod
    def _status_text(value):
        text = str(value)
        return text.rsplit(".", 1)[-1]

    def on_order_event(self, event):
        if self._open_plan is None:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level event arrived without an open rebalance"
            )
        try:
            order_id = event.order_id
            event_id = event.id
            status = self._status_text(event.status)
        except Exception as exc:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level QC event is unreadable"
            ) from exc
        if status in IGNORED_ORDER_STATUSES:
            return
        intent = self._open_order_ids.get(order_id)
        if intent is None:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level event references an unknown QC order"
            )
        if status in _orders.FILL_STATUSES:
            quantity = event.fill_quantity
            if type(quantity) not in (int, float, Decimal):
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    "order-level fill quantity sign disagrees with order side"
                )
            absolute = _decimal(
                abs(signed_quantity),
                "order-level fill quantity",
                positive=True,
            )
            integral = absolute.to_integral_value()
            if absolute != integral:
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    "order-level QC fill fee is unreadable"
                ) from exc
            engine_fee_amount = _decimal(
                raw_fee_amount,
                "order-level QC fill fee amount",
                nonnegative=True,
            )
            if type(fee_currency) is not str or fee_currency != "USD":
                raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                    "order-level QC fill fee currency is not exact USD"
                )
        elif status in {_orders.CANCELED, _orders.INVALID}:
            fill_quantity = 0
            fill_price = None
            engine_fee_amount = None
            fee_currency = None
        else:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level QC event status is unsupported"
            )
        if type(event_id) not in (int, str) or str(event_id) == "":
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level QC event identity changed"
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
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level first QQQ execution session is unavailable"
            ) from exc
        qqq_path, binding = _execution_matched_qqq_path(
            close_observations=observations,
            open_observations=self._benchmark_open_observations,
            expected_sessions=expected_sessions,
            first_execution_session=first_execution_session,
        )
        if set(self._strategy_equity_observations) != set(expected_sessions):
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
        lifecycle_digest = _sha(
            {
                "schema": "arv2-order-level-lifecycle-census-v1",
                "records": self._lifecycle_records,
            }
        )
        fee = sum(
            (Decimal(row["modeled_fee_amount"]) for row in self._lifecycle_records),
            Decimal(0),
        )
        filled_notional = sum(
            (Decimal(row["total_filled_notional"]) for row in self._lifecycle_records),
            Decimal(0),
        )
        actual_engine_fee = sum(
            (
                Decimal(row["actual_engine_fee_amount"])
                for row in self._lifecycle_records
            ),
            Decimal(0),
        )
        if (
            self._decision_count <= 0
            or len(self._pit_coverage_records) != self._decision_count
        ):
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level PIT coverage path is incomplete"
            )
        filled_order_count = sum(
            row["filled_order_count"] for row in self._lifecycle_records
        )
        canceled_order_count = sum(
            row["canceled_order_count"] for row in self._lifecycle_records
        )
        invalid_order_count = sum(
            row["invalid_order_count"] for row in self._lifecycle_records
        )
        orders_with_any_fill_count = sum(
            row["orders_with_any_fill_count"]
            for row in self._lifecycle_records
        )
        target_errors = tuple(
            Decimal(row["target_weight_l1_error"])
            for row in self._lifecycle_records
        )
        mean_target_error = (
            Decimal(0)
            if not target_errors
            else sum(target_errors, Decimal(0)) / Decimal(len(target_errors))
        )
        maximum_target_error = max(target_errors, default=Decimal(0))
        execution_failure = (
            canceled_order_count != 0
            or invalid_order_count != 0
            or filled_order_count != self._submitted_order_count
            or any(row["fee_mismatch"] for row in self._lifecycle_records)
        )
        fee_mismatch = any(
            row["fee_mismatch"] for row in self._lifecycle_records
        )
        run_valid = (
            not execution_failure
            and self._skipped_unpriced_decision_count == 0
            and len(self._lifecycle_records) == self._decision_count
        )
        coverage_decimal_fields = (
            "resolved_member_count_ratio",
            "cap_covered_member_count_ratio",
            "resolved_constituent_weight_ratio",
            "cap_covered_constituent_weight_ratio",
            "positive_constituent_weight_total",
        )
        coverage_values = {
            name: tuple(
                Decimal(row[name]) for row in self._pit_coverage_records
            )
            for name in coverage_decimal_fields
        }
        coverage_count_fields = (
            "positive_weight_member_count",
            "resolved_positive_weight_member_count",
            "cap_covered_positive_weight_member_count",
        )
        return {
            "schema": SUMMARY_SCHEMA,
            "score_source_view_id": _score.PRIMARY_SOURCE_VIEW_ID,
            "decision_count": self._decision_count,
            "completed_rebalance_count": len(self._lifecycle_records),
            "submitted_order_count": self._submitted_order_count,
            "skipped_unpriced_decision_count": (
                self._skipped_unpriced_decision_count
            ),
            "tilt_enabled_count": self._tilt_enabled_count,
            "tilt_underfilled_count": self._tilt_underfilled_count,
            "mean_tilted_name_count": _decimal_text(
                Decimal(self._tilted_name_count_sum)
                / Decimal(self._decision_count)
            ),
            "mean_one_way_active_share": _decimal_text(
                self._one_way_active_share_sum / Decimal(self._decision_count)
            ),
            "pit_history_call_count": self._pit_history_call_count,
            "pit_source_row_count": self._pit_source_row_count,
            "named_figi_refusal_count": self._resolution.named_refusal_count,
            "modeled_fee_bps_per_side": _orders.MODELED_FEE_BPS_PER_SIDE,
            "modeled_fee_amount": _decimal_text(fee),
            "actual_engine_fee_amount": _decimal_text(actual_engine_fee),
            "actual_engine_fee_effective_bps_per_side": _decimal_text(
                Decimal(0)
                if filled_notional == 0
                else actual_engine_fee / filled_notional * Decimal(10_000)
            ),
            "modeled_minus_actual_fee_amount": _decimal_text(
                fee - actual_engine_fee
            ),
            "fee_mismatch": fee_mismatch,
            "lifecycle_modeled_fee_basis": (
                "actual_fill_price_times_filled_quantity"
            ),
            "engine_fee_model_basis": (
                "current_minute_trade_bar_open_times_full_order_quantity_at_fee_assessment"
            ),
            "total_filled_notional": _decimal_text(filled_notional),
            "filled_order_count_sum": filled_order_count,
            "canceled_order_count_sum": canceled_order_count,
            "invalid_order_count_sum": invalid_order_count,
            "orders_with_any_fill_count_sum": orders_with_any_fill_count,
            "mean_reference_mark_target_weight_l1_error": _decimal_text(
                mean_target_error
            ),
            "maximum_reference_mark_target_weight_l1_error": _decimal_text(
                maximum_target_error
            ),
            "execution_failure": execution_failure,
            "run_valid": run_valid,
            "coverage_decision_count": len(self._pit_coverage_records),
            **{
                name + "_sum": sum(
                    row[name] for row in self._pit_coverage_records
                )
                for name in coverage_count_fields
            },
            **{
                "mean_" + name: _decimal_text(
                    sum(coverage_values[name], Decimal(0))
                    / Decimal(len(coverage_values[name]))
                )
                for name in coverage_decimal_fields
            },
            **{
                "minimum_" + name: _decimal_text(
                    min(coverage_values[name])
                )
                for name in coverage_decimal_fields
            },
            "maximum_positive_constituent_weight_total": _decimal_text(
                max(coverage_values["positive_constituent_weight_total"])
            ),
            "minimum_required_positive_constituent_weight_total": (
                _decimal_text(MINIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL)
            ),
            "maximum_allowed_positive_constituent_weight_total": (
                _decimal_text(MAXIMUM_POSITIVE_CONSTITUENT_WEIGHT_TOTAL)
            ),
            "minimum_required_cap_covered_constituent_weight_ratio": (
                _decimal_text(
                    MINIMUM_CAP_COVERED_CONSTITUENT_WEIGHT_RATIO
                )
            ),
            "maximum_fundamental_snapshot_age_sessions": max(
                row["fundamental_snapshot_age_sessions"]
                for row in self._pit_coverage_records
            ),
            "maximum_constituent_snapshot_age_sessions": max(
                row["constituent_snapshot_age_sessions"]
                for row in self._pit_coverage_records
            ),
            "pit_coverage_path_sha256": _sha(
                {
                    "schema": "arv2-order-level-pit-coverage-path-v1",
                    "records": self._pit_coverage_records,
                }
            ),
            "starting_equity": _decimal_text(STARTING_CASH),
            "ending_equity": _decimal_text(self._portfolio_equity()),
            "strategy_total_return": _decimal_text(strategy_return),
            "strategy_maximum_drawdown": _decimal_text(
                strategy_metrics["maximum_drawdown"]
            ),
            "strategy_annualized_volatility": _decimal_text(
                strategy_metrics["annualized_volatility"]
            ),
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
            "QQQ_first_execution_session": binding[
                "first_execution_session"
            ],
            "QQQ_target_gross_exposure": binding[
                "target_gross_exposure"
            ],
            "QQQ_entry_fee_bps_per_side": binding[
                "entry_fee_bps_per_side"
            ],
            "QQQ_maximum_drawdown": _decimal_text(
                qqq_metrics["maximum_drawdown"]
            ),
            "QQQ_annualized_volatility": _decimal_text(
                qqq_metrics["annualized_volatility"]
            ),
            "QQQ_zero_rate_sharpe": (
                None
                if qqq_metrics["zero_rate_sharpe"] is None
                else _decimal_text(qqq_metrics["zero_rate_sharpe"])
            ),
            "strategy_minus_QQQ_total_return": _decimal_text(
                strategy_return - qqq_return
            ),
            "QQQ_observation_count": binding["observation_count"],
            "QQQ_return_interval_count": binding["return_interval_count"],
            "QQQ_raw_observation_sha256": binding[
                "raw_observation_sha256"
            ],
            "QQQ_return_path_sha256": binding["return_path_sha256"],
            "QQQ_calendar_close_total_return": _decimal_text(
                calendar_qqq_return
            ),
            "QQQ_calendar_close_observation_count": calendar_binding[
                "observation_count"
            ],
            "QQQ_calendar_close_raw_observation_sha256": calendar_binding[
                "raw_observation_sha256"
            ],
            "QQQ_calendar_close_return_path_sha256": calendar_binding[
                "return_path_sha256"
            ],
            "order_lifecycle_sha256": lifecycle_digest,
            "raw_order_rows_in_summary": False,
            "raw_security_rows_in_summary": False,
            "backtest_only": True,
            "simulated_orders": True,
            "live_orders": False,
            "trading": False,
        }

    def on_end_of_algorithm(self):
        if not self._initialized or self._completed:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level end callback escaped runtime state"
            )
        if self._algorithm.time.date().isoformat() != FINAL_EXECUTION_SESSION:
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
                "order-level backtest ended outside the exact final session"
            )
        self._close_open_plan()
        if self._decision_count != len(self._decision_sessions):
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
            raise AcceptedRiskQqqOrderLevelQcRuntimeError(
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
    "MINIMUM_CAP_COVERED_CONSTITUENT_WEIGHT_RATIO",
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
