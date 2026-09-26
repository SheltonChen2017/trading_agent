import hashlib
import json
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, localcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as evaluator,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_qc_runtime as legacy,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v18_qc_runtime as v18,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v19_qc_runtime as runtime,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_qqq_order_level_runtime as fixtures,
)


V18_SOURCE_SHA256 = (
    "40d3832163db238a0a716277b93500fb38214d46b1c54b2611337426331c3bc1"
)
REFUSAL = runtime.AcceptedRiskQqqOrderLevelQcRuntimeError
FINAL = legacy.FINAL_EXECUTION_SESSION
START = "2026-01-02"
PRIOR, DECISION, EXECUTION = "2026-01-02", "2026-01-05", "2026-01-06"
AXIS = ("2025-12-31", PRIOR, DECISION, EXECUTION)


def _runtime(algorithm=None, profile_id=runtime.SUCCESSOR_PROFILE_2026_ID):
    algorithm = algorithm or fixtures._Algorithm()
    return runtime.AcceptedRiskQqqOrderLevelV19QcRuntime(
        algorithm,
        activation_manifest_key="arv2/x/transport-manifest.json",
        activation_manifest_sha256="a" * 64,
        activation_manifest_byte_count=1,
        profile_id=profile_id,
        authority_benchmark_symbol=fixtures._Symbol("SPY-SID", "SPY"),
        qqq_benchmark_symbol=fixtures._Symbol("QQQ-SID", "QQQ"),
        qqq_constituent_universe=SimpleNamespace(
            symbol=fixtures._Symbol("QQQU-SID")
        ),
        minute_resolution="Minute",
        raw_normalization="Raw",
        trade_bar_type="TradeBar",
        daily_resolution="Daily",
        total_return_normalization="TotalReturn",
        fee_model_factory=lambda: "ten-bps",
        slippage_model_factory=lambda: "zero",
        order_status_enum=fixtures._OpaqueOrderStatus,
    )


def _terminal_ready(runtime_factory, *, residual_text):
    holdings = Decimal("1381054.2127016393")
    cash = Decimal("12345.678901234567")
    equity = holdings + cash - Decimal(residual_text)
    algorithm = fixtures._Algorithm()
    algorithm.portfolio.total_holdings_value = holdings
    algorithm.portfolio.cash = cash
    algorithm.portfolio.total_portfolio_value = equity
    value = runtime_factory(algorithm)
    value._strategy_equity_observations = {
        START: Decimal("1000000"), FINAL: Decimal("1168510.983845"),
    }
    value._gross_exposure_observations = {FINAL: Decimal("0.9")}
    value._cash_weight_observations = {FINAL: Decimal("0.1")}
    return value


def test_v19_profiles_extend_immutable_v18_and_declare_transport():
    expected_sha256s = {
        runtime.SUCCESSOR_PROFILE_2025_ID: (
            "a27018fbf8e0df77240988890a43702a19d561a7d90e24a840b5c0c220f1fb2f"
        ),
        runtime.SUCCESSOR_PROFILE_2026_ID: (
            "4c32ec5f90c7c5abe6f23c909a2ea3c2745dd3377b1650991c9559aef1e44195"
        ),
    }
    extension_fields = {
        "residual_magnitude_policy",
        "complete_census_drift_policy",
        "executed_decision_session_policy",
        "all_skipped_terminal_policy",
        "maximum_custom_statistic_bytes_each",
    }
    for profile_id, predecessor_id in zip(
        runtime.SUCCESSOR_PROFILE_IDS, v18.BOUNDARY_PROFILE_IDS,
    ):
        profile = runtime.require_qqq_order_level_profile(profile_id)
        predecessor = v18.require_qqq_order_level_profile(predecessor_id)
        assert profile["schema"] == runtime.SUCCESSOR_PROFILE_SCHEMA
        assert profile["maximum_custom_statistic_bytes_each"] == 16_384
        assert profile["profile_sha256"] == expected_sha256s[profile_id]
        for record in (profile, predecessor):
            record.pop("profile_sha256")
            record.pop("schema")
            record.pop("profile_id")
        for field in extension_fields:
            profile.pop(field)
        assert profile == predecessor
    assert hashlib.sha256(Path(v18.__file__).read_bytes()).hexdigest() == (
        V18_SOURCE_SHA256
    )
    own_callables = {
        name for name, member in
        runtime.AcceptedRiskQqqOrderLevelV19QcRuntime.__dict__.items()
        if callable(member)
    }
    assert own_callables == {
        "__init__", "_aggregate_record", "_complete_preopen_quantity_census",
        "_record_overnight_drift_skip",
        "_replace_terminal_account_observation", "on_before_open",
        "on_end_of_algorithm",
    }


def test_hostile_ambient_context_red_green_proves_residual_fail_open_closed():
    residual = "1.00000001E-8"
    predecessor = _terminal_ready(
        lambda algorithm: v18.AcceptedRiskQqqOrderLevelV18QcRuntime(
            algorithm,
            activation_manifest_key="arv2/x/transport-manifest.json",
            activation_manifest_sha256="a" * 64,
            activation_manifest_byte_count=1,
            profile_id=v18.BOUNDARY_PROFILE_2026_ID,
            authority_benchmark_symbol=fixtures._Symbol("SPY-SID", "SPY"),
            qqq_benchmark_symbol=fixtures._Symbol("QQQ-SID", "QQQ"),
            qqq_constituent_universe=SimpleNamespace(
                symbol=fixtures._Symbol("QQQU-SID")
            ),
            minute_resolution="Minute",
            raw_normalization="Raw",
            trade_bar_type="TradeBar",
            daily_resolution="Daily",
            total_return_normalization="TotalReturn",
            fee_model_factory=lambda: "ten-bps",
            slippage_model_factory=lambda: "zero",
            order_status_enum=fixtures._OpaqueOrderStatus,
        ),
        residual_text=residual,
    )
    successor = _terminal_ready(_runtime, residual_text=residual)
    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_DOWN
        # Red evidence: V18 rounds abs(residual) to 1.00E-8 and accepts.
        predecessor._replace_terminal_account_observation()
        with pytest.raises(
            REFUSAL,
            match="^order-level terminal account composition changed$",
        ):
            successor._replace_terminal_account_observation()
    assert predecessor._terminal_account_composition_residual == Decimal(
        residual
    )
    assert successor._terminal_account_composition_residual is None


def _rows(weights):
    return tuple(
        SimpleNamespace(symbol=fixtures._Symbol(sid), weight=Decimal(text))
        for sid, text in weights.items()
    )


def _ready_preopen():
    algorithm = fixtures._Algorithm(DECISION)
    a = fixtures._Symbol("A-SID", "A")
    value = _runtime(algorithm)
    value._initialized = True
    value._decision_sessions = (DECISION,)
    value._decision_set = frozenset({DECISION})
    value._session_axis = AXIS
    value._session_positions = {session: i for i, session in enumerate(AXIS)}
    value._resolution = fixtures._Resolution({"a": a})
    value._score_runtime = SimpleNamespace(score=lambda _position: SimpleNamespace(
        memberships=(evaluator.SecurityMembership(
            "a", 0, 2, "sector", Decimal(1), "a" * 64,
        ),),
        primary_view_firm_specific_scores={"a": Decimal(1)},
    ))
    value._history_inventory = lambda *_args: {
        datetime.fromisoformat(PRIOR + "T00:00:00"): _rows({
            "A-SID": "0.86", "B-SID": "0.14",
        })
    }
    assert value.on_after_close() is True
    algorithm.time = datetime.fromisoformat(EXECUTION + "T09:20:00")
    return algorithm, value


@pytest.mark.parametrize("unexpected_quantity", (1, Decimal("0.5"), Decimal("-1")))
def test_complete_census_new_nonzero_holding_is_counted_no_order_drift_skip(
    unexpected_quantity,
):
    algorithm, value = _ready_preopen()
    algorithm.portfolio.quantities["SPINOFF-SID"] = unexpected_quantity

    assert value.on_before_open() is False

    assert algorithm.orders == []
    assert value._pending_preopen is None
    assert value._overnight_drift_skipped_execution_count == 1
    record, = value._skipped_decision_records
    assert record["decision_session"] == DECISION
    assert record["execution_session"] == EXECUTION
    assert record["reason"] == runtime._v17.OVERNIGHT_DRIFT_SKIP_REASON
    assert record["drifted_security_count"] == 1
    assert len(record["drifted_security_path_sha256"]) == 64
    assert value._executed_decision_sessions == []


def test_complete_census_tracked_fraction_is_counted_no_order_drift_skip():
    algorithm, value = _ready_preopen()
    algorithm.portfolio.quantities["A-SID"] = Decimal("0.5")

    assert value.on_before_open() is False

    assert algorithm.orders == []
    assert value._pending_preopen is None
    assert value._overnight_drift_skipped_execution_count == 1
    record, = value._skipped_decision_records
    assert record["decision_session"] == DECISION
    assert record["reason"] == runtime._v17.OVERNIGHT_DRIFT_SKIP_REASON
    assert record["drifted_security_count"] == 1
    assert value._executed_decision_sessions == []


def test_successful_preopen_tracks_the_actual_decision_session():
    algorithm, value = _ready_preopen()

    assert value.on_before_open() is True

    assert algorithm.orders
    assert value._executed_decision_sessions == [DECISION]


def _aggregate_ready():
    sessions = (START, FINAL)
    algorithm = fixtures._Algorithm()
    algorithm.portfolio.total_portfolio_value = Decimal("1168243.410845")
    algorithm.portfolio.total_holdings_value = Decimal("1120000")
    algorithm.portfolio.cash = Decimal("48243.410845")
    value = _runtime(algorithm)
    value._package = SimpleNamespace(
        evaluator_input=SimpleNamespace(session_axis=sessions),
        package_id="package-fixture",
        package_sha256="b" * 64,
        activation_manifest_sha256="c" * 64,
    )
    value._resolution = fixtures._Resolution({
        "a": fixtures._Symbol("A-SID", "A")
    })
    value._resolved_qqq_weights(
        sessions[0], {"A-SID": Decimal("1")},
        constituent_age_sessions=1,
    )
    value._decision_count = 1
    value._decision_sessions = sessions[:1]
    value._decision_set = frozenset(value._decision_sessions)
    value._executed_decision_sessions = [sessions[0]]
    value._submitted_order_count = 1
    value._lifecycle_records = [fixtures._lifecycle_record()]
    value._strategy_equity_observations = {
        sessions[0]: Decimal("1000000"),
        sessions[1]: Decimal("1168510.983845"),
    }
    qqq = ((sessions[0], Decimal("100")), (sessions[1], Decimal("101")))
    value._load_qqq_total_return_observations = (
        lambda expected: qqq if expected == sessions else ()
    )
    value._benchmark_open_observations = {
        sessions[0]: Decimal("100"), sessions[1]: Decimal("100"),
    }
    value._gross_exposure_observations = {
        sessions[0]: Decimal("0"), sessions[1]: Decimal("0.95"),
    }
    value._cash_weight_observations = {
        sessions[0]: Decimal("1"), sessions[1]: Decimal("0.05"),
    }
    return value


def test_first_drifted_decision_reports_first_actually_submitted_plan():
    value = _aggregate_ready()
    second = FINAL
    value._resolved_qqq_weights(
        second, {"A-SID": Decimal("1")}, constituent_age_sessions=1,
    )
    value._decision_count = 2
    value._decision_sessions = (START, second)
    value._decision_set = frozenset(value._decision_sessions)
    value._executed_decision_sessions = [second]
    value._record_skipped_decision({
        "decision_session": START,
        "reason": runtime._v17.OVERNIGHT_DRIFT_SKIP_REASON,
        "execution_session": "2026-01-05",
        "drifted_security_count": 1,
        "drifted_security_path_sha256": "d" * 64,
    })
    value._replace_terminal_account_observation()

    summary = value._aggregate_record()

    assert summary["first_scheduled_decision_session"] == START
    assert summary["first_executed_decision_session"] == second
    assert summary["first_scheduled_decision_executed"] is False
    assert summary["executed_decision_count"] == 1
    assert len(summary["executed_decision_session_path_sha256"]) == 64


def test_executed_census_counts_forced_exit_invalidated_pending_plan():
    value = _aggregate_ready()
    second = FINAL
    value._resolved_qqq_weights(
        second, {"A-SID": Decimal("1")}, constituent_age_sessions=1,
    )
    value._decision_count = 2
    value._decision_sessions = (START, second)
    value._decision_set = frozenset(value._decision_sessions)
    value._executed_decision_sessions = [START]
    value._forced_exit_invalidated_pending_plan_count = 1
    value._replace_terminal_account_observation()

    summary = value._aggregate_record()

    assert summary["decision_count"] == 2
    assert summary["completed_rebalance_count"] == 1
    assert summary["forced_exit_invalidated_pending_rebalance_count"] == 1
    assert summary["executed_decision_count"] == 1


def test_all_skipped_terminal_refuses_before_observation_or_output(monkeypatch):
    value = _aggregate_ready()
    value._initialized = True
    value._algorithm.time = datetime.fromisoformat("2026-09-18T00:00:00")
    value._decision_count = 0
    value._decision_sessions = (START,)
    value._decision_set = frozenset(value._decision_sessions)
    value._executed_decision_sessions = []
    value._pit_coverage_records = []
    value._lifecycle_records = []
    value._record_skipped_decision({
        "decision_session": START,
        "reason": runtime._v17.STALE_SNAPSHOT_SKIP_REASON,
        "expected_snapshot_session": "2025-12-31",
        "served_snapshot_session": "2025-12-29",
        "served_snapshot_age_sessions": 2,
    })
    prior_terminal = value._strategy_equity_observations[FINAL]
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 16_384)

    with pytest.raises(
        REFUSAL, match="V19 all-skipped schedule has no executed decision",
    ):
        value.on_end_of_algorithm()

    assert value._terminal_account_composition_residual is None
    assert value._terminal_account_observation_adjustment is None
    assert value._strategy_equity_observations[FINAL] == prior_terminal
    assert value._algorithm.summary_statistics == {}


def test_end_callback_requires_and_uses_profile_bound_16384_transport(
    monkeypatch,
):
    value = _aggregate_ready()
    value._initialized = True
    value._algorithm.time = datetime.fromisoformat("2026-09-18T00:00:00")
    with pytest.raises(REFUSAL, match="statistic transport binding changed"):
        value.on_end_of_algorithm()
    assert value._algorithm.summary_statistics == {}

    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 16_384)
    value.on_end_of_algorithm()
    aggregate = json.loads(
        value._algorithm.summary_statistics[runtime.AGGREGATES_STATISTIC_NAME]
    )
    assert aggregate["schema"] == runtime.SUCCESSOR_SUMMARY_SCHEMA
    assert aggregate["executed_decision_count"] == 1
    assert value.completed is True


@pytest.mark.parametrize(
    ("aggregate_bytes", "accepted"),
    ((runtime.MAXIMUM_STATISTIC_BYTES, True),
     (runtime.MAXIMUM_STATISTIC_BYTES + 1, False)),
)
def test_end_callback_isolates_inclusive_statistic_byte_boundary(
    monkeypatch, aggregate_bytes, accepted,
):
    value = _aggregate_ready()
    value._initialized = True
    value._algorithm.time = datetime.fromisoformat("2026-09-18T00:00:00")
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 16_384)
    # Canonical ASCII for {"x":"..."} has exactly eight structural bytes.
    monkeypatch.setattr(
        value,
        "_aggregate_record",
        lambda: {"x": "a" * (aggregate_bytes - 8)},
    )

    if accepted:
        value.on_end_of_algorithm()
        stored = value._algorithm.summary_statistics[
            runtime.AGGREGATES_STATISTIC_NAME
        ]
        assert len(stored.encode("ascii")) == runtime.MAXIMUM_STATISTIC_BYTES
        assert value.completed is True
    else:
        with pytest.raises(
            REFUSAL,
            match="^order-level aggregate transport exceeded its exact bound$",
        ):
            value.on_end_of_algorithm()
        assert value._algorithm.summary_statistics == {}
        assert value.completed is False
