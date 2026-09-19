import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_market_cap_stock_portfolio_qc_runtime as reviewed_input,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_market_cap_stock_portfolio_tilt as tilt,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_order_level_core as orders,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_order_level_input_runtime as input_runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as evaluator,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_qc_runtime as runtime,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_preliminary_qc_runtime as preliminary_fixtures,
)


class _Sid:
    def __init__(self, value):
        self.value = value
        self.market = "usa"

    def __str__(self):
        return self.value


class _Symbol:
    def __init__(self, sid, value="STOCK"):
        self.id = _Sid(sid)
        self.value = value
        self.security_type = "Equity"


class _Security:
    def __init__(self, symbol, price="100", end_time=None):
        self.symbol = symbol
        self.price = Decimal(price)
        self.last_data = SimpleNamespace(
            end_time=end_time or datetime.fromisoformat("2026-01-02T16:00:00")
        )
        self.models = []

    def get_last_data(self):
        return self.last_data

    def set_data_normalization_mode(self, value):
        self.models.append(("normalization", value))

    def set_fee_model(self, value):
        self.models.append(("fee", value))

    def set_slippage_model(self, value):
        self.models.append(("slippage", value))


class _Portfolio:
    def __init__(self):
        self.total_portfolio_value = Decimal("1000000")
        self.cash = Decimal("1000000")
        self.total_holdings_value = Decimal(0)
        self.quantities = {}

    def __getitem__(self, symbol):
        return SimpleNamespace(quantity=self.quantities.get(str(symbol.id), 0))


class _Resolution:
    def __init__(self, by_security):
        self.by_security = dict(by_security)
        self.by_sid = {str(value.id): key for key, value in by_security.items()}
        self.resolved = tuple(
            {
                "security_id": security_id,
                "qc_security_id": str(symbol.id),
            }
            for security_id, symbol in sorted(by_security.items())
        )
        self.named_refusal_count = 0
        self.resolution_id = "resolution-fixture"
        self.resolution_sha256 = "a" * 64

    def symbol_for_security(self, security_id):
        return self.by_security.get(security_id)

    def security_for_qc_sid(self, sid):
        if sid not in self.by_sid:
            raise ValueError("unknown")
        return self.by_sid[sid]


class _Algorithm:
    def __init__(self, session="2026-01-02"):
        self.live_mode = False
        self.portfolio = _Portfolio()
        self.time = datetime.fromisoformat(session + "T16:00:00")
        self.securities = {}
        self.orders = []
        self.summary_statistics = {}

    def add_security(self, symbol, *_args):
        value = _Security(symbol, end_time=self.time)
        self.securities[symbol] = value
        return value

    def market_on_open_order(self, symbol, quantity, *, tag):
        self.orders.append((symbol.value, quantity, tag))
        return SimpleNamespace(order_id=len(self.orders))

    def set_summary_statistic(self, key, value):
        self.summary_statistics[key] = value


def _runtime(algorithm=None, profile_id=runtime.PROFILE_2026_ID):
    algorithm = algorithm or _Algorithm()
    return runtime.AcceptedRiskQqqOrderLevelQcRuntime(
        algorithm,
        activation_manifest_key="arv2/x/transport-manifest.json",
        activation_manifest_sha256="a" * 64,
        activation_manifest_byte_count=1,
        profile_id=profile_id,
        authority_benchmark_symbol=_Symbol("SPY-SID", "SPY"),
        qqq_benchmark_symbol=_Symbol("QQQ-SID", "QQQ"),
        qqq_constituent_universe=SimpleNamespace(symbol=_Symbol("QQQU-SID")),
        minute_resolution="Minute",
        raw_normalization="Raw",
        trade_bar_type="TradeBar",
        daily_resolution="Daily",
        total_return_normalization="TotalReturn",
        fee_model_factory=lambda: "ten-bps",
        slippage_model_factory=lambda: "zero",
    )


def _coverage_record(session="2026-01-02"):
    return {
        "session": session,
        "positive_weight_member_count": 100,
        "resolved_positive_weight_member_count": 100,
        "resolved_member_count_ratio": "1",
        "resolved_constituent_weight_ratio": "1",
        "positive_constituent_weight_total": "1",
        "constituent_snapshot_age_sessions": 1,
        "pit_constituent_weight_map_sha256": "f" * 64,
    }


def _lifecycle_record(**updates):
    value = {
        "modeled_fee_amount": "10",
        "actual_engine_fee_amount": "10",
        "fee_mismatch": False,
        "total_filled_notional": "10000",
        "filled_order_count": 1,
        "canceled_order_count": 0,
        "invalid_order_count": 0,
        "orders_with_any_fill_count": 1,
        "target_weight_l1_error": "0.01",
    }
    value.update(updates)
    return value


def _order_fee(amount, currency="USD"):
    return SimpleNamespace(
        value=SimpleNamespace(amount=Decimal(amount), currency=currency)
    )


def _outcome(function, *args):
    try:
        return ("value", function(*args))
    except ValueError as exc:
        return ("refusal", str(exc))


def test_fixed_profiles_are_exact_backtest_only_and_transport_is_bounded():
    assert runtime.PROFILE_IDS == (
        "arv2-qqq-order-level-tilt-2025-cutoff-v4",
        "arv2-qqq-order-level-tilt-2026-cutoff-v4",
    )
    expected_starts = {
        runtime.PROFILE_2025_ID: "2025-01-02",
        runtime.PROFILE_2026_ID: "2026-01-02",
    }
    expected_digests = {
        runtime.PROFILE_2025_ID: (
            "43ea09abd2b6eb9aef23cfb05ec7cb0c19c50451fb41ac78c3aeeac8bd60e518"
        ),
        runtime.PROFILE_2026_ID: (
            "190637eb9145c4b3a9e844cb42eb84d24bb5b318afc56957f98bf9d413d8a3b6"
        ),
    }
    for profile_id in runtime.PROFILE_IDS:
        profile = runtime.require_qqq_order_level_profile(profile_id)
        assert profile["evaluation_start_session"] == expected_starts[profile_id]
        assert profile["profile_sha256"] == expected_digests[profile_id]
        assert profile["decision_cutoff_session"] == "2026-09-16"
        assert profile["final_execution_session"] == "2026-09-17"
        assert profile["price_normalization"] == "RAW"
        assert profile["benchmark_price_normalization"] == "TOTAL_RETURN"
        assert profile["benchmark_observation"] == (
            "EXECUTION_MATCHED_FIRST_MOO_OPEN_THEN_SESSION_CLOSE"
        )
        assert profile["benchmark_target_gross_exposure"] == "0.98"
        assert profile["benchmark_entry_fee_bps_per_side"] == 10
        assert profile["calendar_benchmark_observation"] == (
            "SESSION_CLOSE_CONTEXT_ONLY"
        )
        assert profile["minimum_resolved_constituent_weight_ratio"] == "0.95"
        assert profile["target_weight_basis"] == runtime.TARGET_WEIGHT_BASIS
        assert profile["minimum_positive_constituent_weight_total"] == "0.95"
        assert profile["maximum_positive_constituent_weight_total"] == "1.05"
        assert profile["exact_constituent_snapshot_age_sessions"] == 1
        assert profile["constituent_source_session_rule"] == (
            "QC_daily_Series_collection_EndTime_minus_one_calendar_day"
        )
        assert profile["score_source_view_id"] == evaluator.SOURCE_VIEW_IDS[1]
        assert profile["fee_bps_per_side"] == 10
        assert profile["backtest_only"] is True
        assert profile["live_orders"] is False
        assert runtime.expected_custom_summary_statistic_names(profile_id) == (
            runtime.AGGREGATES_STATISTIC_NAME,
            runtime.META_STATISTIC_NAME,
        )


def test_decision_axis_is_weekly_plus_exact_cutoff_and_next_open():
    axis = (
        "2026-01-02",
        "2026-01-05",
        "2026-01-06",
        "2026-09-14",
        "2026-09-16",
        "2026-09-17",
    )
    decisions, start, cutoff, final = runtime.AcceptedRiskQqqOrderLevelQcRuntime._decision_axis(
        axis, "2026-01-02"
    )
    assert decisions == (
        "2026-01-02",
        "2026-01-05",
        "2026-09-14",
        "2026-09-16",
    )
    assert (start, cutoff, final) == (0, 4, 5)


def test_known_performance_path_reports_drawdown_volatility_and_sharpe():
    values = (
        ("a", Decimal("100")),
        ("b", Decimal("110")),
        ("c", Decimal("99")),
    )
    result = runtime._path_metrics(values)
    assert result["total_return"] == Decimal("-0.01")
    assert result["maximum_drawdown"] == Decimal("-0.1")
    assert result["annualized_arithmetic_return"] == 0
    assert result["zero_rate_sharpe"] == 0
    assert result["annualized_volatility"] > 0


def test_qqq_hurdle_uses_first_executable_open_gross_and_entry_cost():
    sessions = ("2026-01-02", "2026-01-05", "2026-01-06")
    closes = tuple(
        (session, close)
        for session, close in zip(
            sessions,
            (Decimal("100"), Decimal("110"), Decimal("120")),
        )
    )
    first_path, first_binding = runtime._execution_matched_qqq_path(
        close_observations=closes,
        open_observations={
            sessions[0]: Decimal("100"),
            sessions[1]: Decimal("100"),
            sessions[2]: Decimal("120"),
        },
        expected_sessions=sessions,
        first_execution_session=sessions[1],
    )
    second_path, second_binding = runtime._execution_matched_qqq_path(
        close_observations=closes,
        open_observations={
            sessions[0]: Decimal("100"),
            sessions[1]: Decimal("105"),
            sessions[2]: Decimal("120"),
        },
        expected_sessions=sessions,
        first_execution_session=sessions[1],
    )

    with localcontext() as context:
        context.prec = 96
        first_expected = (
            Decimal("0.02")
            + Decimal("0.98") * Decimal("120") / Decimal("100")
            - Decimal("0.98") * Decimal("0.001")
            - 1
        )
        second_expected = (
            Decimal("0.02")
            + Decimal("0.98") * Decimal("120") / Decimal("105")
            - Decimal("0.98") * Decimal("0.001")
            - 1
        )
    assert first_path[-1][1] - 1 == first_expected
    assert second_path[-1][1] - 1 == second_expected
    assert first_path[0][1] == second_path[0][1] == Decimal(1)
    assert first_binding["target_gross_exposure"] == "0.98"
    assert first_binding["entry_fee_bps_per_side"] == 10
    assert first_binding["raw_observation_sha256"] != second_binding[
        "raw_observation_sha256"
    ]
    assert first_binding["return_path_sha256"] != second_binding[
        "return_path_sha256"
    ]


def test_aggregate_binds_execution_matched_and_calendar_qqq_paths():
    sessions = ("2026-01-02", "2026-01-05", "2026-09-17")
    algorithm = _Algorithm()
    algorithm.portfolio.total_portfolio_value = Decimal("990000")
    value = _runtime(algorithm)
    value._package = SimpleNamespace(
        evaluator_input=SimpleNamespace(session_axis=sessions)
    )
    value._resolution = SimpleNamespace(named_refusal_count=0)
    value._decision_count = 2
    value._decision_sessions = sessions[:2]
    value._submitted_order_count = 2
    value._lifecycle_records = [
        _lifecycle_record(),
        _lifecycle_record(target_weight_l1_error="0.03"),
    ]
    value._pit_coverage_records = [
        _coverage_record(),
        {
            **_coverage_record(sessions[1]),
            "resolved_positive_weight_member_count": 99,
            "resolved_member_count_ratio": "0.99",
            "resolved_constituent_weight_ratio": "0.99",
            "pit_constituent_weight_map_sha256": "e" * 64,
        },
    ]
    value._strategy_equity_observations = {
        sessions[0]: Decimal("1000000"),
        sessions[1]: Decimal("1100000"),
        sessions[2]: Decimal("990000"),
    }
    value._gross_exposure_observations = {
        session: Decimal("0.98") for session in sessions
    }
    value._cash_weight_observations = {
        session: Decimal("0.02") for session in sessions
    }
    qqq = (
        (sessions[0], Decimal("100")),
        (sessions[1], Decimal("105")),
        (sessions[2], Decimal("110")),
    )
    value._load_qqq_total_return_observations = (
        lambda expected: qqq if expected == sessions else ()
    )
    value._benchmark_open_observations = {
        sessions[0]: Decimal("100"),
        sessions[1]: Decimal("105"),
        sessions[2]: Decimal("110"),
    }

    result = value._aggregate_record()

    assert result["strategy_total_return"] == "-0.01"
    assert result["score_source_view_id"] == evaluator.SOURCE_VIEW_IDS[1]
    assert result["strategy_maximum_drawdown"] == "-0.1"
    assert Decimal(result["strategy_annualized_volatility"]) > 0
    assert result["strategy_zero_rate_sharpe"] == "0"
    assert result["mean_gross_exposure"] == "0.98"
    assert result["mean_cash_weight"] == "0.02"
    with localcontext() as context:
        context.prec = 96
        expected_qqq_return = (
            Decimal("0.02")
            + Decimal("0.98") * Decimal("110") / Decimal("105")
            - Decimal("0.98") * Decimal("0.001")
            - 1
        )
    assert abs(
        Decimal(result["QQQ_total_return"]) - expected_qqq_return
    ) < Decimal("1e-26")
    assert Decimal(result["QQQ_maximum_drawdown"]) == Decimal("-0.00098")
    assert result["QQQ_normalization_mode"] == "TOTAL_RETURN"
    assert result["QQQ_observation"] == (
        "start_cash_then_first_execution_session_adjusted_open_entry_"
        "and_session_close_marks"
    )
    assert result["QQQ_first_execution_session"] == sessions[1]
    assert result["QQQ_target_gross_exposure"] == "0.98"
    assert result["QQQ_entry_fee_bps_per_side"] == 10
    assert result["QQQ_observation_count"] == 3
    assert result["QQQ_calendar_close_total_return"] == "0.1"
    assert result["QQQ_calendar_close_observation_count"] == 3
    assert result["filled_order_count_sum"] == 2
    assert result["canceled_order_count_sum"] == 0
    assert result["invalid_order_count_sum"] == 0
    assert result["orders_with_any_fill_count_sum"] == 2
    assert result["mean_reference_mark_target_weight_l1_error"] == "0.02"
    assert result["maximum_reference_mark_target_weight_l1_error"] == "0.03"
    assert result["execution_failure"] is False
    assert result["actual_engine_fee_amount"] == "20"
    assert result["actual_engine_fee_effective_bps_per_side"] == "10"
    assert result["modeled_minus_actual_fee_amount"] == "0"
    assert result["fee_mismatch"] is False
    assert result["run_valid"] is True
    assert result["coverage_decision_count"] == 2
    assert result["positive_weight_member_count_sum"] == 200
    assert result["target_weight_basis"] == runtime.TARGET_WEIGHT_BASIS
    assert result["mean_resolved_constituent_weight_ratio"] == "0.995"
    assert result["mean_positive_constituent_weight_total"] == "1"
    assert result["minimum_positive_constituent_weight_total"] == "1"
    assert result["maximum_positive_constituent_weight_total"] == "1"
    assert result["minimum_resolved_constituent_weight_ratio"] == "0.99"
    assert result["maximum_constituent_snapshot_age_sessions"] == 1
    assert len(result["pit_coverage_path_sha256"]) == 64
    assert len(result["pit_target_weight_path_sha256"]) == 64
    original_path_digest = result["pit_target_weight_path_sha256"]
    value._pit_coverage_records[1]["pit_constituent_weight_map_sha256"] = (
        "d" * 64
    )
    changed_weight_path = value._aggregate_record()
    assert changed_weight_path["pit_target_weight_path_sha256"] != (
        original_path_digest
    )
    value._pit_coverage_records[1]["pit_constituent_weight_map_sha256"] = (
        "e" * 64
    )
    assert len(runtime._canonical(result)) <= runtime.MAXIMUM_STATISTIC_BYTES

    value._lifecycle_records[0] = {
        **value._lifecycle_records[0],
        "fee_mismatch": True,
    }
    offsetting_mismatch = value._aggregate_record()
    assert offsetting_mismatch["actual_engine_fee_amount"] == "20"
    assert offsetting_mismatch["modeled_minus_actual_fee_amount"] == "0"
    assert offsetting_mismatch["fee_mismatch"] is True
    assert offsetting_mismatch["execution_failure"] is True
    assert offsetting_mismatch["run_valid"] is False

    value._lifecycle_records[0] = {
        **value._lifecycle_records[0],
        "actual_engine_fee_amount": "11",
    }
    mismatched = value._aggregate_record()
    assert mismatched["actual_engine_fee_amount"] == "21"
    assert mismatched["modeled_minus_actual_fee_amount"] == "-1"
    assert mismatched["fee_mismatch"] is True
    assert mismatched["execution_failure"] is True
    assert mismatched["run_valid"] is False


def test_aggregate_marks_canceled_or_incomplete_execution_invalid():
    sessions = ("2026-01-02", "2026-09-17")
    value = _runtime(_Algorithm())
    value._package = SimpleNamespace(
        evaluator_input=SimpleNamespace(session_axis=sessions)
    )
    value._resolution = SimpleNamespace(named_refusal_count=0)
    value._decision_count = 1
    value._decision_sessions = sessions[:1]
    value._submitted_order_count = 1
    value._lifecycle_records = [
        _lifecycle_record(
            filled_order_count=0,
            canceled_order_count=1,
            orders_with_any_fill_count=0,
            modeled_fee_amount="0",
            actual_engine_fee_amount="0",
            total_filled_notional="0",
            target_weight_l1_error="0.98",
        )
    ]
    value._pit_coverage_records = [_coverage_record()]
    value._strategy_equity_observations = {
        session: Decimal("1000000") for session in sessions
    }
    value._gross_exposure_observations = {
        session: Decimal(0) for session in sessions
    }
    value._cash_weight_observations = {
        session: Decimal(1) for session in sessions
    }
    qqq = tuple((session, Decimal("100")) for session in sessions)
    value._load_qqq_total_return_observations = lambda _expected: qqq
    value._benchmark_open_observations = {
        session: Decimal("100") for session in sessions
    }

    result = value._aggregate_record()

    assert result["filled_order_count_sum"] == 0
    assert result["canceled_order_count_sum"] == 1
    assert result["invalid_order_count_sum"] == 0
    assert result["execution_failure"] is True
    assert result["run_valid"] is False
    assert result[
        "maximum_reference_mark_target_weight_l1_error"
    ] == "0.98"


def test_end_callback_emits_exact_bounded_meta_and_aggregate_statistics():
    sessions = ("2026-01-02", "2026-01-05", "2026-09-17")
    algorithm = _Algorithm("2026-09-17")
    algorithm.portfolio.total_portfolio_value = Decimal("990000")
    value = _runtime(algorithm)
    value._initialized = True
    value._decision_sessions = sessions[:2]
    value._decision_count = 2
    value._submitted_order_count = 2
    value._package = SimpleNamespace(
        evaluator_input=SimpleNamespace(session_axis=sessions),
        package_id="package-fixture",
        package_sha256="b" * 64,
        activation_manifest_sha256="c" * 64,
    )
    value._resolution = SimpleNamespace(
        named_refusal_count=0,
        resolution_id="resolution-fixture",
        resolution_sha256="a" * 64,
    )
    value._lifecycle_records = [_lifecycle_record(), _lifecycle_record()]
    value._pit_coverage_records = [
        _coverage_record(sessions[0]),
        _coverage_record(sessions[1]),
    ]
    value._strategy_equity_observations = {
        sessions[0]: Decimal("1000000"),
        sessions[1]: Decimal("1100000"),
        sessions[2]: Decimal("990000"),
    }
    value._gross_exposure_observations = {
        session: Decimal("0.98") for session in sessions
    }
    value._cash_weight_observations = {
        session: Decimal("0.02") for session in sessions
    }
    qqq = (
        (sessions[0], Decimal("100")),
        (sessions[1], Decimal("105")),
        (sessions[2], Decimal("110")),
    )
    value._load_qqq_total_return_observations = (
        lambda expected: qqq if expected == sessions else ()
    )
    value._benchmark_open_observations = {
        sessions[0]: Decimal("100"),
        sessions[1]: Decimal("105"),
        sessions[2]: Decimal("110"),
    }

    value.on_end_of_algorithm()

    assert tuple(sorted(algorithm.summary_statistics)) == (
        runtime.AGGREGATES_STATISTIC_NAME,
        runtime.META_STATISTIC_NAME,
    )
    assert all(
        len(item.encode("ascii")) <= runtime.MAXIMUM_STATISTIC_BYTES
        for item in algorithm.summary_statistics.values()
    )
    aggregates = json.loads(
        algorithm.summary_statistics[runtime.AGGREGATES_STATISTIC_NAME]
    )
    meta = json.loads(algorithm.summary_statistics[runtime.META_STATISTIC_NAME])
    assert aggregates["strategy_total_return"] == "-0.01"
    assert aggregates["QQQ_calendar_close_total_return"] == "0.1"
    assert aggregates["run_valid"] is True
    assert meta["aggregates_sha256"] == runtime._sha(aggregates)
    assert meta["result_transport"] == (
        "aggregate_only_custom_summary_statistics"
    )
    assert value._completed is True


def test_total_return_history_includes_dividend_when_raw_prices_are_flat():
    qqq = _Symbol("QQQ-SID", "QQQ")

    class _Batch:
        def __init__(self, session, adjusted_open, adjusted_close):
            self.time = datetime.fromisoformat(session + "T16:00:00")
            self.bar = SimpleNamespace(
                symbol=qqq,
                time=datetime.fromisoformat(session + "T09:30:00"),
                open=Decimal(adjusted_open),
                close=Decimal(adjusted_close),
            )

        def items(self):
            return ((qqq, self.bar),)

    calls = []

    class _Typed:
        def __getitem__(self, item):
            assert item == "TradeBar"

            def load(*args, **kwargs):
                calls.append((args, kwargs))
                return (
                    _Batch("2026-01-02", "500", "99"),
                    _Batch("2026-01-05", "400", "100"),
                )

            return load

    algorithm = _Algorithm()
    algorithm.history = _Typed()
    value = _runtime(algorithm)
    value._qqq_benchmark_symbol = qqq
    observations = value._load_qqq_total_return_observations(
        ("2026-01-02", "2026-01-05")
    )

    raw_closes = (Decimal("100"), Decimal("100"))
    assert raw_closes[-1] / raw_closes[0] - 1 == 0
    # A distribution occurs between two unchanged raw closes.  The independent
    # explicitly TOTAL_RETURN request reinvests it, making its adjusted-close
    # path rise from 99 to 100.  The deliberately divergent adjusted opens
    # are retained separately for the execution-matched entry calculation.
    assert Decimal("100") / Decimal("99") - 1 == runtime._benchmark_total_return(
        observations
    )
    assert calls[0][1]["data_normalization_mode"] == "TotalReturn"
    assert observations == (
        ("2026-01-02", Decimal("99")),
        ("2026-01-05", Decimal("100")),
    )
    assert value._benchmark_open_observations == {
        "2026-01-02": Decimal("500"),
        "2026-01-05": Decimal("400"),
    }


def test_unscored_unmapped_qqq_member_remains_at_exact_benchmark_weight(monkeypatch):
    algorithm = _Algorithm("2026-01-02")
    value = _runtime(algorithm)
    value._initialized = True
    value._decision_set = frozenset({"2026-01-02"})
    value._session_positions = {"2026-01-02": 0}
    memberships = (
        evaluator.SecurityMembership("a", 0, 2, "sector", Decimal(1), "a" * 64),
        evaluator.SecurityMembership("b", 0, 2, "sector", Decimal(1), "b" * 64),
    )
    value._score_runtime = SimpleNamespace(
        score=lambda _position: SimpleNamespace(
            memberships=memberships,
            primary_view_firm_specific_scores={
                "a": Decimal("-1"),
                "b": Decimal("1"),
            },
            sector_by_security_id={"a": "sector", "b": "sector"},
        )
    )
    value._pit_benchmark_measures = lambda _session: {
        "a": Decimal("0.10"),
        "b": Decimal("0.20"),
        "unscored": Decimal("0.30"),
    }
    value._positive_price = (
        lambda _security_id, _session: Decimal("100")
    )
    value._build_plan = lambda _session, _weights: None
    captured = {}
    original = tilt.build_benchmark_tilt

    def build(caps, scores, sectors):
        captured["sectors"] = sectors
        captured["result"] = original(caps, scores, sectors)
        return captured["result"]

    monkeypatch.setattr(runtime._tilt, "build_benchmark_tilt", build)
    assert value.on_after_close() is True

    result = captured["result"]
    assert captured["sectors"]["unscored"] == (
        tilt.RESERVED_STRUCTURAL_ZERO_SECTOR_ID
    )
    assert "unscored" in result.selected_weights
    assert result.benchmark_weights["unscored"] == Decimal("0.49")
    assert result.selected_weights["unscored"] == result.benchmark_weights["unscored"]


def test_missing_price_skips_whole_rebalance_without_renormalizing_target(monkeypatch):
    algorithm = _Algorithm("2026-01-02")
    a = _Symbol("A-SID", "A")
    unpriced = _Symbol("UNPRICED-SID", "UNPRICED")
    value = _runtime(algorithm)
    value._initialized = True
    value._decision_set = frozenset({"2026-01-02"})
    value._session_positions = {"2026-01-02": 0}
    value._resolution = _Resolution({"a": a, "unpriced": unpriced})
    value._score_runtime = SimpleNamespace(
        score=lambda _position: SimpleNamespace(
            memberships=(
                evaluator.SecurityMembership(
                    "a", 0, 2, "sector", Decimal(1), "a" * 64
                ),
            ),
            primary_view_firm_specific_scores={"a": Decimal("1")},
            sector_by_security_id={"a": "sector"},
        )
    )
    value._pit_benchmark_measures = lambda _session: {
        "a": Decimal("0.10"),
        "unpriced": Decimal("0.30"),
    }
    value._positive_price = lambda security_id, _session: (
        None if security_id == "unpriced" else Decimal("100")
    )
    captured = {}
    original = tilt.build_benchmark_tilt

    def build(caps, scores, sectors):
        captured["caps"] = dict(caps)
        captured["result"] = original(caps, scores, sectors)
        return captured["result"]

    monkeypatch.setattr(runtime._tilt, "build_benchmark_tilt", build)
    assert value.on_after_close() is True

    assert captured["caps"] == {
        "a": Decimal("0.10"), "unpriced": Decimal("0.30")
    }
    assert captured["result"].selected_weights["unpriced"] == (
        captured["result"].benchmark_weights["unpriced"]
    )
    assert value._skipped_unpriced_decision_count == 1
    assert value._decision_count == 1
    assert algorithm.orders == []


def test_constituent_weight_resolution_keeps_95_percent_and_refuses_94_percent():
    a = _Symbol("A-SID", "A")
    accepted = _runtime()
    accepted._resolution = _Resolution({"a": a})
    result = accepted._resolved_qqq_weights(
        "2026-01-02",
        {"A-SID": Decimal("0.95"), "B-SID": Decimal("0.05")},
        constituent_age_sessions=1,
    )
    assert result == {"a": Decimal("0.95")}
    record = accepted._pit_coverage_records[0]
    assert record["positive_weight_member_count"] == 2
    assert record["resolved_positive_weight_member_count"] == 1
    assert record["resolved_member_count_ratio"] == "0.5"
    assert record["resolved_constituent_weight_ratio"] == "0.95"
    assert record["positive_constituent_weight_total"] == "1"
    assert record["constituent_snapshot_age_sessions"] == 1
    assert record["pit_constituent_weight_map_sha256"] == runtime._sha(
        {
            "schema": runtime.TARGET_WEIGHT_MAP_SCHEMA,
            "positive_weights_by_qc_sid": {"A-SID": "0.95", "B-SID": "0.05"},
            "resolved_weights_by_security_id": {"a": "0.95"},
        }
    )

    refused = _runtime()
    refused._resolution = _Resolution({"a": a})
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="resolved constituent-weight coverage is below 95 percent: 0.94",
    ):
        refused._resolved_qqq_weights(
            "2026-01-02",
            {"A-SID": Decimal("0.94"), "B-SID": Decimal("0.06")},
            constituent_age_sessions=1,
        )
    assert refused._pit_coverage_records == []

    truncated = _runtime()
    truncated._resolution = _Resolution({"a": a})
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="positive constituent weight total is outside 0.95 to 1.05",
    ):
        truncated._resolved_qqq_weights(
            "2026-01-02",
            {"A-SID": Decimal("0.10")},
            constituent_age_sessions=1,
        )
    assert truncated._pit_coverage_records == []


@pytest.mark.parametrize("total_weight", (Decimal("0.95"), Decimal("1.05")))
def test_positive_constituent_weight_total_accepts_exact_boundaries(total_weight):
    a = _Symbol("A-SID", "A")
    value = _runtime()
    value._resolution = _Resolution({"a": a})
    assert value._resolved_qqq_weights(
        "2026-01-02",
        {"A-SID": total_weight},
        constituent_age_sessions=1,
    ) == {"a": total_weight}
    assert value._pit_coverage_records[0][
        "positive_constituent_weight_total"
    ] == str(total_weight)


def test_pit_weight_map_digest_binds_weights_without_emitting_raw_rows():
    a = _Symbol("A-SID", "A")
    b = _Symbol("B-SID", "B")
    first = _runtime()
    first._resolution = _Resolution({"a": a, "b": b})
    second = _runtime()
    second._resolution = _Resolution({"a": a, "b": b})
    first_measures = first._resolved_qqq_weights(
        "2026-01-02",
        {"A-SID": Decimal("0.80"), "B-SID": Decimal("0.20")},
        constituent_age_sessions=1,
    )
    second_measures = second._resolved_qqq_weights(
        "2026-01-02",
        {"A-SID": Decimal("0.20"), "B-SID": Decimal("0.80")},
        constituent_age_sessions=1,
    )
    assert first_measures == {"a": Decimal("0.80"), "b": Decimal("0.20")}
    assert second_measures == {"a": Decimal("0.20"), "b": Decimal("0.80")}
    assert first._pit_coverage_records[0][
        "pit_constituent_weight_map_sha256"
    ] != second._pit_coverage_records[0]["pit_constituent_weight_map_sha256"]
    assert "A-SID" not in json.dumps(first._pit_coverage_records)
    assert "0.80" not in json.dumps(first._pit_coverage_records)


def test_order_tilt_base_uses_pit_holdings_weights_not_opposite_cap_like_values(
    monkeypatch,
):
    algorithm = _Algorithm("2026-01-05")
    a = _Symbol("A-SID", "A")
    b = _Symbol("B-SID", "B")
    value = _runtime(algorithm)
    value._initialized = True
    value._decision_set = frozenset({"2026-01-05"})
    value._session_positions = {"2026-01-02": 0, "2026-01-05": 1}
    value._resolution = _Resolution({"a": a, "b": b})
    value._score_runtime = SimpleNamespace(
        score=lambda _position: SimpleNamespace(
            memberships=tuple(
                evaluator.SecurityMembership(
                    security_id, 0, 2, "sector", Decimal(1), security_id * 64
                )
                for security_id in ("a", "b")
            ),
            primary_view_firm_specific_scores={
                "a": Decimal("1"),
                "b": Decimal("-1"),
            },
        )
    )
    constituents = {
        datetime.fromisoformat("2026-01-02T00:00:00"): (
            SimpleNamespace(symbol=a, weight=Decimal("0.80")),
            SimpleNamespace(symbol=b, weight=Decimal("0.20")),
        )
    }
    history_universes = []

    def history(universe, *_args):
        history_universes.append(universe)
        return constituents

    value._history_inventory = history
    value._build_plan = lambda *_args: None
    captured = {}
    original = tilt.build_benchmark_tilt

    def build(measures, scores, sectors):
        captured["measures"] = dict(measures)
        captured["tilt"] = original(measures, scores, sectors)
        return captured["tilt"]

    monkeypatch.setattr(runtime._tilt, "build_benchmark_tilt", build)
    assert value.on_after_close() is True
    assert history_universes == [value._qqq_constituent_universe]
    assert captured["measures"] == {
        "a": Decimal("0.80"), "b": Decimal("0.20")
    }
    assert captured["tilt"].benchmark_weights == {
        "a": Decimal("0.784"), "b": Decimal("0.196")
    }
    # A cap-like 20/80 value pair would invert these weights; no such input
    # is fetched or admitted into the order runtime's target construction.
    assert captured["tilt"].benchmark_weights["a"] != Decimal("0.196")


def test_pit_weight_resolution_refuses_non_unique_security_identity():
    value = _runtime()
    value._resolution = SimpleNamespace(
        resolved=(
            {"qc_security_id": "A-SID", "security_id": "same"},
            {"qc_security_id": "B-SID", "security_id": "same"},
        )
    )
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="FIGI resolution is not one-to-one",
    ):
        value._resolved_qqq_weights(
            "2026-01-02",
            {"A-SID": Decimal("0.50"), "B-SID": Decimal("0.50")},
            constituent_age_sessions=1,
        )
    assert value._pit_coverage_records == []


def test_pit_weight_resolution_refuses_duplicate_qc_sid_binding():
    value = _runtime()
    value._resolution = SimpleNamespace(
        resolved=(
            {"qc_security_id": "A-SID", "security_id": "a"},
            {"qc_security_id": "A-SID", "security_id": "b"},
        )
    )
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="FIGI resolution duplicated a QC SID",
    ):
        value._resolved_qqq_weights(
            "2026-01-02",
            {"A-SID": Decimal("1")},
            constituent_age_sessions=1,
        )
    assert value._pit_coverage_records == []


def test_pit_snapshots_use_authenticated_session_age_across_weekend():
    a = _Symbol("A-SID", "A")
    value = _runtime(_Algorithm("2026-01-05"))
    value._resolution = _Resolution({"a": a})
    value._session_positions = {
        "2025-12-31": 0,
        "2026-01-02": 1,
        "2026-01-05": 2,
    }
    # QC daily universe data for Friday is keyed by its Saturday EndTime.
    constituents = {
        input_runtime.constituent_collection_time(
            datetime.fromisoformat("2026-01-03T00:00:00"),
            "fixture constituent EndTime",
        ): (
            SimpleNamespace(symbol=a, weight=Decimal("1")),
        )
    }
    value._history_inventory = lambda *_args: constituents

    assert value._pit_benchmark_measures("2026-01-05") == {
        "a": Decimal("1")
    }
    assert value._pit_coverage_records[0][
        "constituent_snapshot_age_sessions"
    ] == 1


def test_first_decision_uses_exact_prior_session_qqq_holdings_only():
    a = _Symbol("A-SID", "A")
    b = _Symbol("B-SID", "B")
    algorithm = _Algorithm("2026-01-02")
    value = _runtime(algorithm)
    value._resolution = _Resolution({"a": a, "b": b})
    value._session_positions = {
        "2025-12-30": 0,
        "2025-12-31": 1,
        "2026-01-02": 2,
    }
    universe = value._qqq_constituent_universe
    # QC Series keys are EndTime: Jan 1 represents the Dec 31 source
    # session, while Jan 3 represents the Jan 2 decision session itself.
    prior = (
        SimpleNamespace(symbol=a, weight=Decimal("0.80")),
        SimpleNamespace(symbol=b, weight=Decimal("0.20")),
    )
    same_day = (
        SimpleNamespace(symbol=a, weight=Decimal("0.20")),
        SimpleNamespace(symbol=b, weight=Decimal("0.80")),
    )
    history = {
        (universe.symbol, datetime.fromisoformat("2026-01-01T00:00:00")): prior,
        (universe.symbol, datetime.fromisoformat("2026-01-03T00:00:00")): (
            same_day
        ),
        (universe.symbol, datetime.fromisoformat("2026-01-06T00:00:00")): (
            same_day
        ),
    }
    calls = []

    def load_history(requested_universe, *_args, **_kwargs):
        calls.append(requested_universe)
        return history

    algorithm.history = load_history

    assert value._pit_benchmark_measures("2026-01-02") == {
        "a": Decimal("0.80"),
        "b": Decimal("0.20"),
    }
    assert calls == [universe]
    assert value._pit_history_call_count == 1
    assert value._pit_coverage_records[0][
        "constituent_snapshot_age_sessions"
    ] == 1

    # The same-day EndTime-normalized snapshot cannot start a first decision.
    no_prior = _runtime(_Algorithm("2026-01-02"))
    no_prior._resolution = _Resolution({"a": a, "b": b})
    no_prior._session_positions = dict(value._session_positions)
    same_day_only = {
        (no_prior._qqq_constituent_universe.symbol,
         datetime.fromisoformat("2026-01-03T00:00:00")): same_day,
    }
    no_prior._algorithm.history = lambda *_args, **_kwargs: same_day_only
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="has no strictly prior collection",
    ):
        no_prior._pit_benchmark_measures("2026-01-02")
    assert no_prior._pit_coverage_records == []


def test_latest_collection_excludes_same_day_even_when_it_is_newer():
    prior = datetime.fromisoformat("2025-12-31T00:00:00")
    same_day = datetime.fromisoformat("2026-01-02T00:00:00")
    cutoff = same_day
    inventory = {prior: "prior-80-20", same_day: "same-day-20-80"}
    assert runtime.AcceptedRiskQqqOrderLevelQcRuntime._latest(
        inventory, cutoff, "order-level PIT QQQ constituents"
    ) == (prior, "prior-80-20")
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="has no strictly prior collection",
    ):
        runtime.AcceptedRiskQqqOrderLevelQcRuntime._latest(
            {same_day: "same-day-20-80"},
            cutoff,
            "order-level PIT QQQ constituents",
        )


def test_non_session_constituent_source_date_still_refuses():
    a = _Symbol("A-SID", "A")
    value = _runtime(_Algorithm("2026-01-02"))
    value._resolution = _Resolution({"a": a})
    value._session_positions = {
        "2025-12-31": 0,
        "2026-01-02": 1,
    }
    constituents = {
        datetime.fromisoformat("2026-01-01T00:00:00"): (
            SimpleNamespace(symbol=a, weight=Decimal("1")),
        )
    }
    value._history_inventory = lambda *_args: constituents

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="constituents collection is outside the authenticated session axis",
    ):
        value._pit_benchmark_measures("2026-01-02")


def test_non_session_constituent_mapping_refuses_outside_or_after_axis():
    value = _runtime(_Algorithm("2026-01-02"))
    value._session_positions = {
        "2025-12-31": 0,
        "2026-01-02": 1,
        "2026-01-05": 2,
    }
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="outside the authenticated session axis",
    ):
        value._snapshot_age_sessions(
            datetime.fromisoformat("2025-12-30T08:00:00"),
            "2026-01-02",
            "order-level PIT QQQ constituents",
        )
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="outside the authenticated session axis",
    ):
        value._snapshot_age_sessions(
            datetime.fromisoformat("2026-01-03T08:00:00"),
            "2026-01-02",
            "order-level PIT QQQ constituents",
        )
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="collection is after its decision session",
    ):
        value._snapshot_age_sessions(
            datetime.fromisoformat("2026-01-05T00:00:00"),
            "2026-01-02",
            "order-level PIT QQQ constituents",
        )


def test_pit_snapshots_refuse_more_than_exact_authenticated_session_age():
    a = _Symbol("A-SID", "A")
    value = _runtime(_Algorithm("2026-01-05"))
    value._resolution = _Resolution({"a": a})
    value._session_positions = {
        "2025-12-31": 0,
        "2026-01-02": 1,
        "2026-01-05": 2,
    }
    stale_constituents = {
        datetime.fromisoformat("2025-12-31T00:00:00"): (
            SimpleNamespace(symbol=a, weight=Decimal("1")),
        )
    }
    value._history_inventory = lambda *_args: stale_constituents

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="not the immediately prior authenticated session",
    ):
        value._pit_benchmark_measures("2026-01-05")


def test_unresolved_reported_holdings_are_not_silently_renormalized_before_gate():
    a = _Symbol("A-SID", "A")
    value = _runtime(_Algorithm("2026-01-05"))
    value._resolution = _Resolution({"a": a})
    value._session_positions = {
        "2025-12-31": 0,
        "2026-01-02": 1,
        "2026-01-05": 2,
    }
    constituents = {
        datetime.fromisoformat("2026-01-02T00:00:00"): (
            SimpleNamespace(symbol=a, weight=Decimal("0.949")),
            SimpleNamespace(symbol=_Symbol("B-SID"), weight=Decimal("0.051")),
        )
    }
    value._history_inventory = lambda *_args: constituents

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="resolved constituent-weight coverage is below 95 percent: 0.949",
    ):
        value._pit_benchmark_measures("2026-01-05")


@pytest.mark.parametrize("last_data", ("stale", "missing"))
def test_reference_price_must_be_fresh_on_exact_decision_session(last_data):
    algorithm = _Algorithm("2026-01-05")
    a = _Symbol("A-SID", "A")
    value = _runtime(algorithm)
    value._initialized = True
    value._resolution = _Resolution({"a": a})
    fresh_plan = value._build_plan(
        "2026-01-05", {"a": Decimal("0.98")}
    )
    assert fresh_plan is not None
    security = algorithm.securities[a]
    security.last_data = (
        None
        if last_data == "missing"
        else SimpleNamespace(
            end_time=datetime.fromisoformat("2026-01-02T16:00:00")
        )
    )
    assert value._build_plan(
        "2026-01-05", {"a": Decimal("0.98")}
    ) is None
    assert value._skipped_unpriced_decision_count == 1


def test_runtime_submits_every_sell_before_buy_and_rechecks_live_mode():
    algorithm = _Algorithm()
    a = _Symbol("A-SID", "A")
    b = _Symbol("B-SID", "B")
    value = _runtime(algorithm)
    value._initialized = True
    value._resolution = _Resolution({"a": a, "b": b})
    plan = orders.plan_rebalance(
        rebalance_id="rebalance",
        starting_cash=Decimal("2000"),
        current_quantities={"a": 100},
        reference_prices={"a": Decimal("100"), "b": Decimal("50")},
        target_weights={"a": Decimal("0.49"), "b": Decimal("0.49")},
    )
    value._submit_plan(plan)
    assert [(ticker, quantity) for ticker, quantity, _tag in algorithm.orders] == [
        ("A", -42),
        ("B", 117),
    ]

    blocked_algorithm = _Algorithm()
    blocked_algorithm.live_mode = True
    blocked = _runtime(blocked_algorithm)
    blocked._initialized = True
    blocked._resolution = _Resolution({"a": a, "b": b})
    with pytest.raises(orders.OrderLevelBacktestError, match="backtest-only"):
        blocked._submit_plan(plan)
    assert blocked_algorithm.orders == []


def test_qc_event_identity_includes_order_id_for_same_per_order_event_id():
    algorithm = _Algorithm()
    a = _Symbol("A-SID", "A")
    b = _Symbol("B-SID", "B")
    value = _runtime(algorithm)
    value._initialized = True
    value._resolution = _Resolution({"a": a, "b": b})
    plan = orders.plan_rebalance(
        rebalance_id="two-orders",
        starting_cash=Decimal("2000"),
        current_quantities={"a": 100},
        reference_prices={"a": Decimal("100"), "b": Decimal("50")},
        target_weights={"a": Decimal("0.49"), "b": Decimal("0.49")},
    )
    value._submit_plan(plan)
    value.on_order_event(
        SimpleNamespace(
            order_id=1, id=1, status="Filled", fill_quantity=-42,
            fill_price=Decimal("100"),
            order_fee=_order_fee("4.2"),
        )
    )
    value.on_order_event(
        SimpleNamespace(
            order_id=2, id=1, status="Filled", fill_quantity=117,
            fill_price=Decimal("50"),
            order_fee=_order_fee("5.85"),
        )
    )
    assert tuple(event.event_id for event in value._open_plan_events) == (
        "qc-event-1-1",
        "qc-event-2-1",
    )
    value._close_open_plan()
    assert value._lifecycle_records[0]["fill_event_count"] == 2


@pytest.mark.parametrize(
    ("order_id", "wrong_quantity"),
    ((1, 42), (2, -117)),
)
def test_fill_quantity_sign_must_match_sell_or_buy_side(
    order_id, wrong_quantity
):
    algorithm = _Algorithm()
    a = _Symbol("A-SID", "A")
    b = _Symbol("B-SID", "B")
    value = _runtime(algorithm)
    value._initialized = True
    value._resolution = _Resolution({"a": a, "b": b})
    plan = orders.plan_rebalance(
        rebalance_id="wrong-sign",
        starting_cash=Decimal("2000"),
        current_quantities={"a": 100},
        reference_prices={"a": Decimal("100"), "b": Decimal("50")},
        target_weights={"a": Decimal("0.49"), "b": Decimal("0.49")},
    )
    value._submit_plan(plan)
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="fill quantity sign disagrees with order side",
    ):
        value.on_order_event(
            SimpleNamespace(
                order_id=order_id,
                id=1,
                status="Filled",
                fill_quantity=wrong_quantity,
                fill_price=Decimal("100"),
            )
        )
    assert value._open_plan_events == []


@pytest.mark.parametrize(
    ("order_fee", "message"),
    (
        (SimpleNamespace(), "order-level QC fill fee is unreadable"),
        (
            SimpleNamespace(
                value=SimpleNamespace(amount="not-decimal", currency="USD")
            ),
            "order-level QC fill fee amount is not decimal",
        ),
        (
            _order_fee("9.8", "EUR"),
            "order-level QC fill fee currency is not exact USD",
        ),
    ),
)
def test_qc_fill_fee_must_be_readable_finite_and_exact_usd(
    order_fee, message
):
    algorithm = _Algorithm()
    a = _Symbol("A-SID", "A")
    value = _runtime(algorithm)
    value._initialized = True
    value._resolution = _Resolution({"a": a})
    plan = orders.plan_rebalance(
        rebalance_id="fee-shape",
        starting_cash=Decimal("10000"),
        current_quantities={},
        reference_prices={"a": Decimal("100")},
        target_weights={"a": Decimal("0.98")},
    )
    value._submit_plan(plan)
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match=message,
    ):
        value.on_order_event(
            SimpleNamespace(
                order_id=1,
                id=1,
                status="Filled",
                fill_quantity=98,
                fill_price=Decimal("100"),
                order_fee=order_fee,
            )
        )
    assert value._open_plan_events == []


def test_partial_fill_callbacks_preserve_arrival_order_across_9_and_10():
    algorithm = _Algorithm()
    a = _Symbol("A-SID", "A")
    value = _runtime(algorithm)
    value._initialized = True
    value._resolution = _Resolution({"a": a})
    plan = orders.plan_rebalance(
        rebalance_id="partial-sequence",
        starting_cash=Decimal("10000"),
        current_quantities={},
        reference_prices={"a": Decimal("100")},
        target_weights={"a": Decimal("0.98")},
    )
    value._submit_plan(plan)
    value.on_order_event(
        SimpleNamespace(
            order_id=1, id=9, status="PartiallyFilled", fill_quantity=40,
            fill_price=Decimal("100"),
            order_fee=_order_fee("4"),
        )
    )
    value.on_order_event(
        SimpleNamespace(
            order_id=1, id=10, status="Filled", fill_quantity=58,
            fill_price=Decimal("100"),
            order_fee=_order_fee("5.8"),
        )
    )
    assert tuple(event.event_id for event in value._open_plan_events) == (
        "qc-event-1-9",
        "qc-event-1-10",
    )
    value._close_open_plan()
    assert value._lifecycle_records[0]["filled_order_count"] == 1
    assert value._lifecycle_records[0]["actual_engine_fee_amount"] == "9.8"
    assert value._lifecycle_records[0]["fee_mismatch"] is False


def test_partial_fill_engine_full_order_fees_are_reported_as_mismatch():
    algorithm = _Algorithm()
    a = _Symbol("A-SID", "A")
    value = _runtime(algorithm)
    value._initialized = True
    value._resolution = _Resolution({"a": a})
    plan = orders.plan_rebalance(
        rebalance_id="partial-fee-mismatch",
        starting_cash=Decimal("10000"),
        current_quantities={},
        reference_prices={"a": Decimal("100")},
        target_weights={"a": Decimal("0.98")},
    )
    value._submit_plan(plan)
    value.on_order_event(
        SimpleNamespace(
            order_id=1,
            id=9,
            status="PartiallyFilled",
            fill_quantity=40,
            fill_price=Decimal("100"),
            order_fee=_order_fee("9.8"),
        )
    )
    value.on_order_event(
        SimpleNamespace(
            order_id=1,
            id=10,
            status="Filled",
            fill_quantity=58,
            fill_price=Decimal("100"),
            order_fee=_order_fee("9.8"),
        )
    )
    value._close_open_plan()

    record = value._lifecycle_records[0]
    assert record["modeled_fee_amount"] == "9.8"
    assert record["actual_engine_fee_amount"] == "19.6"
    assert record["actual_engine_fee_effective_bps_per_side"] == "20"
    assert record["modeled_minus_actual_fee_amount"] == "-9.8"
    assert record["fee_mismatch"] is True


def test_compact_input_loader_matches_reviewed_loader_on_valid_fixture(monkeypatch):
    values, key, activation, roles = preliminary_fixtures._transport_fixture()
    loaded_input = SimpleNamespace(marker="authenticated")
    monkeypatch.setattr(
        evaluator,
        "load_preliminary_rating_input",
        lambda *_items: loaded_input,
    )
    left_store = preliminary_fixtures._Store(dict(values))
    right_store = preliminary_fixtures._Store(dict(values))
    kwargs = {
        "activation_manifest_key": key,
        "activation_manifest_sha256": hashlib.sha256(activation).hexdigest(),
        "activation_manifest_byte_count": len(activation),
    }
    compact = input_runtime.load_accepted_risk_preliminary_package(
        SimpleNamespace(object_store=left_store), **kwargs
    )
    reviewed = reviewed_input.load_accepted_risk_preliminary_package(
        SimpleNamespace(object_store=right_store), **kwargs
    )
    assert (
        compact.package_id,
        compact.package_sha256,
        compact.activation_manifest_sha256,
        compact.evaluator_input,
        compact.runtime_symbol_bindings,
    ) == (
        reviewed.package_id,
        reviewed.package_sha256,
        reviewed.activation_manifest_sha256,
        reviewed.evaluator_input,
        reviewed.runtime_symbol_bindings,
    )
    assert compact.runtime_symbol_bindings == (roles["runtime_symbol_bindings"],)
    assert left_store.events == right_store.events


def test_compact_input_frozen_constants_match_reviewed_runtime():
    names = (
        "TRANSPORT_MANIFEST_SCHEMA",
        "UPLOAD_OBJECT_SCHEMA",
        "BENCHMARK_SECURITY_ID",
        "BENCHMARK_TICKER",
        "MAX_UPLOAD_OBJECT_BYTES",
        "MAX_TOTAL_UPLOAD_BYTES",
        "MAX_TRANSPORT_OBJECT_COUNT",
        "MAX_DECOMPRESSED_OBJECT_BYTES",
        "MAX_TOTAL_DECOMPRESSED_BYTES",
        "MAX_COLLECTIONS_PER_CALL",
        "MAX_COLLECTION_ROWS",
        "NEW_YORK",
        "_OBJECT_FIELDS",
        "_TRANSPORT_FIELDS",
        "_ROLE_ORDER",
        "_EXPECTED_RUNTIME",
        "_EXPECTED_CLAIMS",
    )
    assert {
        name: getattr(input_runtime, name) for name in names
    } == {
        name: getattr(reviewed_input, name) for name in names
    }
    assert input_runtime._HEX.pattern == reviewed_input._HEX.pattern
    assert input_runtime._SAFE.pattern == reviewed_input._SAFE.pattern
    assert input_runtime._KEY.pattern == reviewed_input._KEY.pattern


def test_compact_pit_helpers_match_reviewed_helpers_and_refusals():
    symbol = _Symbol("SID")
    fundamentals = (
        SimpleNamespace(symbol=symbol, market_cap=Decimal("100")),
        SimpleNamespace(symbol=symbol, market_cap=Decimal("100")),
        SimpleNamespace(symbol=_Symbol("NULL"), market_cap=None),
        SimpleNamespace(symbol=_Symbol("MISSING")),
        SimpleNamespace(symbol=_Symbol("ZERO"), market_cap=Decimal(0)),
        SimpleNamespace(symbol=_Symbol("INVALID"), market_cap="not-a-number"),
    )
    constituents = (
        SimpleNamespace(symbol=symbol, weight=Decimal("0.5")),
        SimpleNamespace(symbol=_Symbol("NULL"), weight=None),
        SimpleNamespace(symbol=_Symbol("ZERO"), weight=Decimal(0)),
        SimpleNamespace(symbol=_Symbol("NEGATIVE"), weight=Decimal("-1")),
    )
    assert input_runtime.positive_market_caps(fundamentals) == reviewed_input._positive_market_caps(fundamentals)
    assert input_runtime.positive_constituent_sids(constituents) == reviewed_input._positive_constituent_sids(constituents)
    assert input_runtime.local_collection_time(
        datetime(2026, 1, 2, 8), "fixture"
    ) == reviewed_input._local_collection_time(datetime(2026, 1, 2, 8), "fixture")
    assert reviewed_input._constituent_collection_time(
        datetime(2026, 1, 3), "fixture"
    ) == datetime(2026, 1, 3)
    assert input_runtime.constituent_collection_time(
        datetime(2026, 1, 3), "fixture"
    ) == datetime(2026, 1, 2)

    universe = SimpleNamespace(symbol=symbol)
    assert input_runtime.universe_sid(universe, "fixture") == reviewed_input._universe_sid(universe, "fixture")
    assert input_runtime.row_sid(universe, "fixture") == reviewed_input._row_sid(universe, "fixture")

    series = SimpleNamespace(items=lambda: iter((("key", "value"),)))
    assert input_runtime.history_items(series, "fixture") == reviewed_input._history_items(series, "fixture")
    assert input_runtime.collection_rows(iter((1, 2)), "fixture") == reviewed_input._collection_rows(iter((1, 2)), "fixture")

    for function in (
        input_runtime.local_collection_time,
        reviewed_input._local_collection_time,
    ):
        with pytest.raises(ValueError, match="not observed before open"):
            function(datetime(2026, 1, 2, 9, 30), "fixture")


@pytest.mark.parametrize(
    ("compact", "reviewed", "argument", "message"),
    (
        (
            input_runtime.constituent_collection_time,
            reviewed_input._constituent_collection_time,
            datetime(2026, 1, 2, tzinfo=timezone.utc),
            "timezone-aware",
        ),
        (
            input_runtime.constituent_collection_time,
            reviewed_input._constituent_collection_time,
            datetime(2026, 1, 2, 0, 0, 1),
            "not midnight",
        ),
        (
            lambda rows, _name: input_runtime.positive_market_caps(rows),
            lambda rows, _name: reviewed_input._positive_market_caps(rows),
            (
                SimpleNamespace(symbol=_Symbol("DUP"), market_cap=1),
                SimpleNamespace(symbol=_Symbol("DUP"), market_cap=2),
            ),
            "duplicate SID value or class conflicts",
        ),
        (
            lambda rows, _name: input_runtime.positive_constituent_sids(rows),
            lambda rows, _name: reviewed_input._positive_constituent_sids(rows),
            (
                SimpleNamespace(symbol=_Symbol("DUP"), weight=1),
                SimpleNamespace(symbol=_Symbol("DUP"), weight=1),
            ),
            "duplicated a positive SID",
        ),
    ),
)
def test_compact_pit_refusal_semantics_match_reviewed(
    compact, reviewed, argument, message
):
    assert _outcome(compact, argument, "fixture") == _outcome(
        reviewed, argument, "fixture"
    )
    assert message in _outcome(compact, argument, "fixture")[1]


def test_compact_collection_caps_match_reviewed_runtime():
    collection_at_cap = tuple(range(input_runtime.MAX_COLLECTION_ROWS))
    collection_over_cap = tuple(range(input_runtime.MAX_COLLECTION_ROWS + 1))
    history_at_cap = SimpleNamespace(
        items=lambda: iter(
            (index, index)
            for index in range(input_runtime.MAX_COLLECTIONS_PER_CALL)
        )
    )
    history_over_cap = SimpleNamespace(
        items=lambda: iter(
            (index, index)
            for index in range(input_runtime.MAX_COLLECTIONS_PER_CALL + 1)
        )
    )
    assert _outcome(
        input_runtime.collection_rows, collection_at_cap, "fixture"
    ) == _outcome(reviewed_input._collection_rows, collection_at_cap, "fixture")
    assert _outcome(
        input_runtime.collection_rows, collection_over_cap, "fixture"
    ) == _outcome(reviewed_input._collection_rows, collection_over_cap, "fixture")
    assert _outcome(
        input_runtime.history_items, history_at_cap, "fixture"
    ) == _outcome(reviewed_input._history_items, history_at_cap, "fixture")
    assert _outcome(
        input_runtime.history_items, history_over_cap, "fixture"
    ) == _outcome(reviewed_input._history_items, history_over_cap, "fixture")


def test_compact_transport_claim_refusal_matches_reviewed_loader():
    _values, key, activation, _roles = preliminary_fixtures._transport_fixture()
    candidate = json.loads(activation)
    candidate["claims"]["orders"] = True
    for function in (
        input_runtime._validate_transport,
        reviewed_input._validate_transport,
    ):
        with pytest.raises(ValueError, match="runtime or claims changed"):
            function(candidate, key)
