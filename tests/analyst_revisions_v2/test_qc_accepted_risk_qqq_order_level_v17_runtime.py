import hashlib
import json
from datetime import datetime
from decimal import Decimal
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
    accepted_risk_qqq_order_level_v14_qc_runtime as v14,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v16_qc_runtime as v16,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v17_qc_runtime as runtime,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_qqq_order_level_runtime as fixtures,
)


V16_SOURCE_SHA256 = (
    "998cb19bfe7d48c37ec1dfb901399080ef206831df62a42cb339a464a638877e"
)
PRIOR, DECISION, EXECUTION = "2026-01-02", "2026-01-05", "2026-01-06"
AXIS = ("2025-12-31", PRIOR, DECISION, EXECUTION)
REFUSAL = runtime.AcceptedRiskQqqOrderLevelQcRuntimeError


def _runtime(algorithm=None, profile_id=runtime.SKIP_PROFILE_2026_ID):
    algorithm = algorithm or fixtures._Algorithm()
    return runtime.AcceptedRiskQqqOrderLevelV17QcRuntime(
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


def _rows(weights):
    return tuple(
        SimpleNamespace(symbol=fixtures._Symbol(sid), weight=Decimal(text))
        for sid, text in weights.items()
    )


def _ready_decision(*, snapshot_session=PRIOR, weights=None, inventory=None):
    """One weekly decision session with a real inherited decision path."""

    algorithm = fixtures._Algorithm(DECISION)
    a = fixtures._Symbol("A-SID", "A")
    value = _runtime(algorithm)
    value._initialized = True
    value._decision_sessions = (DECISION,)
    value._decision_set = frozenset({DECISION})
    value._session_axis = AXIS
    value._session_positions = {s: i for i, s in enumerate(AXIS)}
    value._resolution = fixtures._Resolution({"a": a})
    scored = []

    def score(position):
        scored.append(position)
        return SimpleNamespace(
            memberships=(evaluator.SecurityMembership(
                "a", 0, 2, "sector", Decimal(1), "a" * 64,
            ),),
            primary_view_firm_specific_scores={"a": Decimal(1)},
        )

    value._score_runtime = SimpleNamespace(score=score)
    history_calls = []
    if inventory is None:
        inventory = {
            datetime.fromisoformat(snapshot_session + "T00:00:00"): _rows(
                weights or {"A-SID": "0.86", "B-SID": "0.14"}
            ),
        }

    def history(_universe, start, end, _name):
        history_calls.append((start, end))
        return inventory

    value._history_inventory = history
    return algorithm, value, scored, history_calls


def test_v17_profiles_are_exact_v16_extensions_and_v16_is_immutable():
    expected_sha256s = {
        runtime.SKIP_PROFILE_2025_ID: (
            "60af112e42e4bbdfe8949c360359399138cc94a6b24968db59026d9c874fb6b6"
        ),
        runtime.SKIP_PROFILE_2026_ID: (
            "def21cb138fdec25af88398c9e0d2e5f7f43da6a3eff64d1bf6c74653fb5e68a"
        ),
    }
    for profile_id, predecessor_id in zip(
        runtime.SKIP_PROFILE_IDS, v16.EXPOSURE_PROFILE_IDS,
    ):
        profile = runtime.require_qqq_order_level_profile(profile_id)
        predecessor = v16.require_qqq_order_level_profile(predecessor_id)
        assert profile["schema"] == runtime.SKIP_PROFILE_SCHEMA
        assert profile["decision_skip_policy"] == runtime.DECISION_SKIP_POLICY
        assert profile["maximum_retained_skipped_decisions"] == 4
        assert profile["exact_constituent_snapshot_age_sessions"] == 1
        assert profile["profile_sha256"] == expected_sha256s[profile_id]
        for record in (profile, predecessor):
            record.pop("profile_sha256")
            record.pop("schema")
            record.pop("profile_id")
        profile.pop("decision_skip_policy")
        profile.pop("maximum_retained_skipped_decisions")
        assert profile == predecessor
    assert hashlib.sha256(Path(v16.__file__).read_bytes()).hexdigest() == (
        V16_SOURCE_SHA256
    )
    own_callables = {
        name for name, member in
        runtime.AcceptedRiskQqqOrderLevelV17QcRuntime.__dict__.items()
        if callable(member)
    }
    assert own_callables == {
        "__init__", "_aggregate_record", "_pit_benchmark_measures",
        "_pit_verdict", "_record_skipped_decision",
        "_skipped_decision_evidence", "on_after_close", "on_before_open",
        "on_end_of_algorithm",
    }
    with pytest.raises(REFUSAL, match="V17 profile is not an exact fixed"):
        runtime.require_qqq_order_level_profile(v16.EXPOSURE_PROFILE_2026_ID)
    with pytest.raises(REFUSAL, match="V17 profile is not an exact fixed"):
        _runtime(profile_id=v16.EXPOSURE_PROFILE_2026_ID)


def test_exact_age_one_snapshot_runs_the_inherited_decision_once():
    algorithm, value, scored, history_calls = _ready_decision()

    assert value.on_after_close() is True

    assert len(history_calls) == 1
    assert value._decision_count == 1
    assert [row["session"] for row in value._pit_coverage_records] == [
        DECISION
    ]
    assert value._pending_preopen[0] == EXECUTION
    assert value._pending_preopen[1].rebalance_id == (
        "arv2-qqq-order-" + DECISION
    )
    assert scored == [2]
    assert value._skipped_decision_records == []
    assert value._prefetched_benchmark_measures is None
    assert algorithm.orders == []
    assert DECISION in value._strategy_equity_observations


def test_stale_snapshot_skips_the_decision_without_orders_or_aging():
    algorithm, value, scored, history_calls = _ready_decision(
        snapshot_session="2025-12-31",
    )

    assert value.on_after_close() is False

    assert len(history_calls) == 1
    assert value._decision_count == 0
    assert value._pit_coverage_records == []
    assert value._pending_preopen is None
    assert algorithm.orders == []
    assert scored == [2]
    assert DECISION in value._strategy_equity_observations
    assert value._stale_snapshot_skipped_decision_count == 1
    assert value._weight_total_skipped_decision_count == 0
    assert value._overnight_drift_skipped_execution_count == 0
    assert value._skipped_decision_records == [{
        "decision_session": DECISION,
        "reason": runtime.STALE_SNAPSHOT_SKIP_REASON,
        "expected_snapshot_session": PRIOR,
        "served_snapshot_session": "2025-12-31",
        "served_snapshot_age_sessions": 2,
    }]
    # The skipped session's account observation is not duplicated later.
    with pytest.raises(REFUSAL, match="account session is duplicated"):
        value.on_after_close()


def test_percent_scaled_weights_skip_the_decision_without_rescaling():
    algorithm, value, _scored, _calls = _ready_decision(
        weights={"A-SID": "0.0086", "B-SID": "0.0014"},
    )

    assert value.on_after_close() is False

    assert value._decision_count == 0
    assert value._pit_coverage_records == []
    assert value._pending_preopen is None
    assert algorithm.orders == []
    assert value._weight_total_skipped_decision_count == 1
    record, = value._skipped_decision_records
    assert record["reason"] == runtime.WEIGHT_TOTAL_SKIP_REASON
    assert record["decision_session"] == DECISION
    assert record["served_snapshot_session"] == PRIOR
    assert record["positive_weight_member_count"] == 2
    assert Decimal(record["positive_constituent_weight_total"]) == Decimal(
        "0.01"
    )


@pytest.mark.parametrize(
    ("total", "executes"),
    (
        ("0.9499", False),
        ("0.95", True),
        ("1.05", True),
        ("1.0501", False),
    ),
)
def test_weight_total_band_is_closed_and_shared_with_the_inherited_core(
    total, executes,
):
    _algorithm, value, _scored, _calls = _ready_decision(
        weights={"A-SID": total},
    )

    assert value.on_after_close() is executes

    assert value._decision_count == (1 if executes else 0)
    assert value._weight_total_skipped_decision_count == (
        0 if executes else 1
    )


def test_other_inherited_pit_refusals_still_end_the_run():
    _algorithm, value, _scored, _calls = _ready_decision(
        weights={"A-SID": "0.5", "B-SID": "0.5"},
    )
    with pytest.raises(REFUSAL, match="coverage is below"):
        value.on_after_close()
    assert value._skipped_decision_records == []
    assert value._decision_count == 0

    _algorithm, value, _scored, _calls = _ready_decision(inventory={
        datetime.fromisoformat(EXECUTION + "T00:00:00"): _rows(
            {"A-SID": "1"}
        ),
    })
    with pytest.raises(REFUSAL, match="has no strictly prior collection"):
        value.on_after_close()
    assert value._skipped_decision_records == []


def test_pit_measures_are_never_served_outside_the_decision_callback():
    _algorithm, value, _scored, history_calls = _ready_decision()
    with pytest.raises(
        REFUSAL, match="requested outside the decision callback",
    ):
        value._pit_benchmark_measures(DECISION)
    assert history_calls == []
    value._prefetched_benchmark_measures = (PRIOR, {"a": Decimal(1)})
    with pytest.raises(
        REFUSAL, match="requested outside the decision callback",
    ):
        value._pit_benchmark_measures(DECISION)
    assert value._prefetched_benchmark_measures is None


def test_non_decision_session_and_callback_gates_are_inherited():
    algorithm, value, _scored, history_calls = _ready_decision()
    algorithm.time = datetime.fromisoformat(EXECUTION + "T16:00:00")
    assert value.on_after_close() is False
    assert history_calls == []
    assert EXECUTION in value._strategy_equity_observations
    value._pending_preopen = (EXECUTION, None)
    with pytest.raises(REFUSAL, match="preopen callback was missed"):
        value.on_after_close()
    value._completed = True
    with pytest.raises(REFUSAL, match="escaped runtime state"):
        value.on_after_close()


def _ready_preopen(clock="09:20"):
    algorithm, value, scored, history_calls = _ready_decision()
    assert value.on_after_close() is True
    algorithm.time = datetime.fromisoformat(EXECUTION + "T" + clock + ":00")
    return algorithm, value


def test_overnight_holdings_drift_skips_the_frozen_execution():
    algorithm, value = _ready_preopen()
    frozen = value._pending_preopen[1]
    algorithm.portfolio.quantities["A-SID"] = 1

    assert value.on_before_open() is False

    assert algorithm.orders == []
    assert value._pending_preopen is None
    assert value._open_plan is None
    assert EXECUTION not in value._submitted_preopen_sessions
    assert value._overnight_drift_skipped_execution_count == 1
    digest = v14._redacted_security_id_sha256("a")
    assert value._skipped_decision_records == [{
        "decision_session": DECISION,
        "reason": runtime.OVERNIGHT_DRIFT_SKIP_REASON,
        "execution_session": EXECUTION,
        "drifted_security_count": 1,
        "drifted_security_path_sha256": legacy._sha({
            "schema": runtime.DRIFTED_SECURITY_PATH_SCHEMA,
            "security_sha256s": [digest],
        }),
    }]
    assert frozen.rebalance_id == "arv2-qqq-order-" + DECISION
    # Nothing is pending, so the next callback is an ordinary no-op rather
    # than a duplicate-submission refusal.
    assert value.on_before_open() is False
    assert value._overnight_drift_skipped_execution_count == 1


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("late_clock", "missed its exact next session"),
        ("cash_down", "overnight cash decreased or is invalid"),
        ("live", "backtest-only"),
        ("duplicate", "preopen submission was duplicated"),
    ),
)
def test_drift_skip_never_weakens_the_inherited_preopen_refusals(
    mutation, message,
):
    algorithm, value = _ready_preopen("09:28" if mutation == "late_clock" else "09:20")
    algorithm.portfolio.quantities["A-SID"] = 1
    if mutation == "cash_down":
        algorithm.portfolio.cash -= Decimal(1)
    elif mutation == "live":
        algorithm.live_mode = True
    elif mutation == "duplicate":
        value._submitted_preopen_sessions.add(EXECUTION)
    with pytest.raises(ValueError, match=message):
        value.on_before_open()
    assert algorithm.orders == []
    assert value._pending_preopen is not None
    assert value._skipped_decision_records == []


def test_early_preopen_callback_leaves_the_frozen_plan_pending():
    algorithm, value = _ready_preopen()
    algorithm.time = datetime.fromisoformat(DECISION + "T09:20:00")
    algorithm.portfolio.quantities["A-SID"] = 1
    assert value.on_before_open() is False
    assert value._pending_preopen is not None
    assert value._skipped_decision_records == []


@pytest.mark.parametrize("cash_delta", ("0", "100000"))
def test_unchanged_holdings_execute_through_the_inherited_preopen_path(
    cash_delta,
):
    algorithm, value = _ready_preopen()
    frozen = value._pending_preopen[1]
    algorithm.portfolio.cash += Decimal(cash_delta)

    assert value.on_before_open() is True

    assert algorithm.orders
    assert value._pending_preopen is None
    assert EXECUTION in value._submitted_preopen_sessions
    assert value._skipped_decision_records == []
    assert value._open_plan.starting_cash == frozen.starting_cash + Decimal(
        cash_delta
    )
    with pytest.raises(REFUSAL, match="preopen submission was duplicated"):
        value.on_before_open()


def test_frozen_plan_identity_must_name_a_scheduled_decision():
    decisions = frozenset({DECISION})
    plan = SimpleNamespace(rebalance_id="arv2-qqq-order-" + DECISION)
    assert runtime._decision_session_of(plan, decisions) == DECISION
    for bad in (
        SimpleNamespace(rebalance_id="arv2-qqq-order-" + EXECUTION),
        SimpleNamespace(rebalance_id="split-adjusted-" + DECISION),
        SimpleNamespace(rebalance_id=None),
    ):
        with pytest.raises(REFUSAL, match="frozen plan identity changed"):
            runtime._decision_session_of(bad, decisions)
    with pytest.raises(REFUSAL, match="frozen plan identity is unreadable"):
        runtime._decision_session_of(object(), decisions)


def test_unknown_skip_reason_is_refused_before_it_is_counted():
    value = _runtime()
    with pytest.raises(REFUSAL, match="skip reason changed"):
        value._record_skipped_decision({"reason": "other"})
    assert value._skipped_decision_records == []


def _stale_record(session, expected, served, age):
    return {
        "decision_session": session,
        "reason": runtime.STALE_SNAPSHOT_SKIP_REASON,
        "expected_snapshot_session": expected,
        "served_snapshot_session": served,
        "served_snapshot_age_sessions": age,
    }


def _aggregate_ready():
    """A V17 runtime whose inherited aggregate is real and valid."""

    sessions = ("2026-01-02", legacy.FINAL_EXECUTION_SESSION)
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
        sessions[0],
        {"A-SID": Decimal("1")},
        constituent_age_sessions=1,
    )
    value._decision_count = 1
    value._decision_sessions = sessions[:1]
    value._submitted_order_count = 1
    value._lifecycle_records = [fixtures._lifecycle_record()]
    value._strategy_equity_observations = {
        sessions[0]: Decimal("1000000"),
        sessions[1]: Decimal("1168510.983845"),
    }
    qqq = (
        (sessions[0], Decimal("100")),
        (sessions[1], Decimal("101")),
    )
    value._load_qqq_total_return_observations = (
        lambda expected: qqq if expected == sessions else ()
    )
    value._benchmark_open_observations = {
        sessions[0]: Decimal("100"),
        sessions[1]: Decimal("100"),
    }
    value._gross_exposure_observations = {
        sessions[0]: Decimal("0"),
        sessions[1]: Decimal("0.95"),
    }
    value._cash_weight_observations = {
        sessions[0]: Decimal("1"),
        sessions[1]: Decimal("0.05"),
    }
    value._replace_terminal_account_observation()
    return value


def test_complete_schedule_aggregate_stays_valid_and_extends_v16_only():
    value = _aggregate_ready()
    predecessor = v16.AcceptedRiskQqqOrderLevelV16QcRuntime._aggregate_record(
        value
    )
    summary = value._aggregate_record()

    assert predecessor["schema"] == v16.EXPOSURE_SUMMARY_SCHEMA
    assert predecessor["run_valid"] is True
    assert summary["schema"] == runtime.SKIP_SUMMARY_SCHEMA
    assert summary["run_valid"] is True
    assert summary["schedule_complete"] is True
    assert summary["scheduled_decision_count"] == 1
    assert summary["decision_count"] == 1
    assert summary["stale_snapshot_skipped_decision_count"] == 0
    assert summary["weight_total_skipped_decision_count"] == 0
    assert summary["overnight_drift_skipped_execution_count"] == 0
    assert summary["maximum_served_stale_snapshot_age_sessions"] == 0
    assert summary["first_scheduled_decision_session"] == "2026-01-02"
    assert summary["first_executed_decision_session"] == "2026-01-02"
    assert summary["first_scheduled_decision_executed"] is True
    evidence = summary["skipped_decision_evidence"]
    assert evidence == {
        "schema": runtime.SKIPPED_DECISION_EVIDENCE_SCHEMA,
        "skipped_count": 0,
        "retained_count": 0,
        "omitted_count": 0,
        "records": [],
        "path_sha256": legacy._sha({
            "schema": runtime.SKIPPED_DECISION_PATH_SCHEMA,
            "records": [],
        }),
    }
    added = {
        "schema", "scheduled_decision_count",
        "stale_snapshot_skipped_decision_count",
        "weight_total_skipped_decision_count",
        "overnight_drift_skipped_execution_count",
        "maximum_served_stale_snapshot_age_sessions",
        "first_scheduled_decision_session",
        "first_executed_decision_session",
        "first_scheduled_decision_executed", "schedule_complete",
        "run_valid", "skipped_decision_evidence",
    }
    assert {
        key: item for key, item in summary.items() if key not in added
    } == {
        key: item for key, item in predecessor.items() if key not in added
    }


def test_any_skip_invalidates_the_run_and_is_counted_and_bounded():
    # Eight scheduled decisions in the shape the 2025 window produced: five
    # stale snapshots, one out-of-band weight total, two executed decisions
    # of which the second lost its frozen execution to overnight drift.
    value = _aggregate_ready()
    schedule = (
        "2026-01-02", "2026-01-05", "2026-01-12", "2026-01-20",
        "2026-01-26", "2026-02-02", "2026-02-09", "2026-02-17",
    )
    value._decision_sessions = schedule
    value._resolved_qqq_weights(
        "2026-01-20", {"A-SID": Decimal("1")}, constituent_age_sessions=1,
    )
    value._decision_count = 2
    skips = (
        _stale_record("2026-01-05", "2026-01-02", "2025-12-31", 2),
        _stale_record("2026-01-12", "2026-01-09", "2026-01-07", 3),
        {
            "decision_session": "2026-01-20",
            "reason": runtime.OVERNIGHT_DRIFT_SKIP_REASON,
            "execution_session": "2026-01-21",
            "drifted_security_count": 1,
            "drifted_security_path_sha256": "d" * 64,
        },
        _stale_record("2026-01-26", "2026-01-23", "2026-01-16", 5),
        _stale_record("2026-02-02", "2026-01-30", "2026-01-16", 10),
        _stale_record("2026-02-09", "2026-02-06", "2026-01-16", 15),
        {
            "decision_session": "2026-02-17",
            "reason": runtime.WEIGHT_TOTAL_SKIP_REASON,
            "served_snapshot_session": "2026-02-13",
            "positive_weight_member_count": 103,
            "positive_constituent_weight_total": "0.010001",
        },
    )
    for record in skips:
        value._record_skipped_decision(dict(record))

    summary = value._aggregate_record()

    assert summary["run_valid"] is False
    assert summary["schedule_complete"] is False
    assert summary["scheduled_decision_count"] == 8
    assert summary["decision_count"] == 2
    assert summary["completed_rebalance_count"] == 1
    assert summary["stale_snapshot_skipped_decision_count"] == 5
    assert summary["weight_total_skipped_decision_count"] == 1
    assert summary["overnight_drift_skipped_execution_count"] == 1
    assert summary["maximum_served_stale_snapshot_age_sessions"] == 15
    assert summary["first_scheduled_decision_session"] == "2026-01-02"
    assert summary["first_executed_decision_session"] == "2026-01-02"
    assert summary["first_scheduled_decision_executed"] is True
    evidence = summary["skipped_decision_evidence"]
    assert evidence["skipped_count"] == 7
    assert evidence["retained_count"] == 4
    assert evidence["omitted_count"] == 3
    assert evidence["records"] == [dict(record) for record in skips[:4]]
    assert evidence["path_sha256"] == legacy._sha({
        "schema": runtime.SKIPPED_DECISION_PATH_SCHEMA,
        "records": [dict(record) for record in skips],
    })
    # The retained evidence never exceeds the 8,192-byte aggregate transport
    # by more than a bounded increment over the V16 aggregate.
    predecessor = v16.AcceptedRiskQqqOrderLevelV16QcRuntime._aggregate_record(
        value
    )
    increment = len(legacy._canonical(summary)) - len(
        legacy._canonical(predecessor)
    )
    assert 0 < increment <= 1_536


def test_first_scheduled_decision_skip_is_disclosed_against_the_comparator():
    # The inherited QQQ comparator still enters after the first scheduled
    # decision; when that decision was skipped the aggregate says so.
    value = _aggregate_ready()
    value._pit_coverage_records[0]["session"] = legacy.FINAL_EXECUTION_SESSION
    value._decision_sessions = ("2026-01-02", legacy.FINAL_EXECUTION_SESSION)
    value._record_skipped_decision(
        _stale_record("2026-01-02", "2025-12-31", "2025-12-29", 2)
    )

    summary = value._aggregate_record()

    assert summary["QQQ_first_execution_session"] == (
        legacy.FINAL_EXECUTION_SESSION
    )
    assert summary["first_scheduled_decision_session"] == "2026-01-02"
    assert summary["first_executed_decision_session"] == (
        legacy.FINAL_EXECUTION_SESSION
    )
    assert summary["first_scheduled_decision_executed"] is False
    assert summary["run_valid"] is False


def test_aggregate_refuses_census_or_evidence_drift_before_output():
    value = _aggregate_ready()
    value._decision_sessions = ("2026-01-02", "2026-01-05", "2026-01-12")
    value._record_skipped_decision(
        _stale_record("2026-01-05", "2026-01-02", "2025-12-31", 2)
    )
    with pytest.raises(REFUSAL, match="scheduled decision census changed"):
        value._aggregate_record()
    value._decision_sessions = ("2026-01-02", "2026-01-05")
    assert value._aggregate_record()["run_valid"] is False
    value._stale_snapshot_skipped_decision_count = 0
    value._weight_total_skipped_decision_count = 1
    with pytest.raises(REFUSAL, match="evidence count changed"):
        value._aggregate_record()


def test_aggregate_refuses_a_changed_predecessor(monkeypatch):
    value = _aggregate_ready()
    monkeypatch.setattr(
        v16.AcceptedRiskQqqOrderLevelV16QcRuntime,
        "_aggregate_record",
        lambda _self: {"schema": "other", "run_valid": True},
    )
    with pytest.raises(REFUSAL, match="predecessor schema changed"):
        value._aggregate_record()
    monkeypatch.setattr(
        v16.AcceptedRiskQqqOrderLevelV16QcRuntime,
        "_aggregate_record",
        lambda _self: {"schema": v16.EXPOSURE_SUMMARY_SCHEMA, "run_valid": 1},
    )
    with pytest.raises(REFUSAL, match="predecessor validity changed"):
        value._aggregate_record()


def _end_ready():
    value = _aggregate_ready()
    value._initialized = True
    value._algorithm.time = datetime.fromisoformat("2026-09-18T00:00:00")
    value._strategy_equity_observations[legacy.FINAL_EXECUTION_SESSION] = (
        Decimal("1168510.983845")
    )
    value._terminal_account_observation_adjustment = None
    value._terminal_account_observation_prior_equity = None
    value._terminal_account_observation_equity = None
    return value


def test_end_callback_binds_v17_profile_and_counts_skips_toward_schedule(
    monkeypatch,
):
    value = _end_ready()
    value._decision_sessions = ("2026-01-02", "2026-01-05")
    value._record_skipped_decision(
        _stale_record("2026-01-05", "2026-01-02", "2025-12-31", 2)
    )
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 8_192)

    value.on_end_of_algorithm()

    stored = value._algorithm.summary_statistics
    assert sorted(stored) == sorted(
        (runtime.META_STATISTIC_NAME, runtime.AGGREGATES_STATISTIC_NAME)
    )
    aggregate = json.loads(stored[runtime.AGGREGATES_STATISTIC_NAME])
    meta = json.loads(stored[runtime.META_STATISTIC_NAME])
    assert value.completed is True
    assert aggregate["schema"] == runtime.SKIP_SUMMARY_SCHEMA
    assert aggregate["run_valid"] is False
    assert aggregate["scheduled_decision_count"] == 2
    assert aggregate["stale_snapshot_skipped_decision_count"] == 1
    assert meta["profile_id"] == runtime.SKIP_PROFILE_2026_ID
    assert meta["profile_sha256"] == value._profile["profile_sha256"]
    assert meta["aggregates_sha256"] == legacy._sha(aggregate)
    assert meta["schema"] == "arv2-qqq-order-level-tilt-runtime-meta-v3"
    assert meta["live_orders"] is False
    assert meta["trading"] is False


def test_end_callback_refuses_incomplete_schedule_before_output(monkeypatch):
    value = _end_ready()
    value._decision_sessions = ("2026-01-02", "2026-01-05")
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 8_192)
    with pytest.raises(REFUSAL, match="decision schedule did not complete"):
        value.on_end_of_algorithm()
    assert value.completed is False
    assert value._algorithm.summary_statistics == {}


def test_end_callback_transport_refusal_emits_nothing(monkeypatch):
    value = _end_ready()
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 1)
    with pytest.raises(
        REFUSAL, match="^order-level aggregate transport exceeded its exact bound$",
    ):
        value.on_end_of_algorithm()
    assert value.completed is False
    assert value._algorithm.summary_statistics == {}


@pytest.mark.parametrize(
    "state",
    ("pending", "completed", "clock"),
)
def test_end_callback_inherited_state_gates_remain(state, monkeypatch):
    value = _end_ready()
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 8_192)
    if state == "pending":
        value._pending_preopen = ("2026-09-17", None)
        message = "pending preopen submission remained at end"
    elif state == "completed":
        value._completed = True
        message = "end callback escaped runtime state"
    else:
        value._algorithm.time = datetime.fromisoformat("2026-09-18T00:00:01")
        message = "ended outside the exact final clock"
    with pytest.raises(REFUSAL, match=message):
        value.on_end_of_algorithm()
    assert value._algorithm.summary_statistics == {}
