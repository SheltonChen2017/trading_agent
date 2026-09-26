import dataclasses
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_order_level_forced_exit as forced,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_qc_runtime as base,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_bridge_qc_runtime as bridge,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_tilt_qc_runtime as subject,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_tilt_targets as tilt,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_targets as targets,
)


def test_tilt_profile_binds_bridge_matched_role_and_unlevered_gates():
    baseline = bridge.require_bridge_profile(targets.ROLE_MATCHED)
    assert baseline["profile_sha256"] == (
        subject.BASELINE_MATCHED_PROFILE_SHA256
    )
    profile = subject.require_tilt_profile()
    digest = profile.pop("profile_sha256")
    assert hashlib.sha256(base._canonical(profile)).hexdigest() == digest
    assert profile["schema"] == subject.TILT_PROFILE_SCHEMA
    assert profile["role"] == tilt.TILT_ROLE
    assert profile["matched_baseline_profile_sha256"] == (
        baseline["profile_sha256"]
    )
    assert profile["gate_profile_sha256"] == baseline["gate_profile_sha256"]
    assert profile["evaluation_profile_sha256"] == (
        baseline["evaluation_profile_sha256"]
    )
    assert profile["target_path_schema"] == tilt.TARGET_PATH_SCHEMA
    assert profile["decision_target_schema"] == tilt.DECISION_TARGET_SCHEMA
    assert profile["tilt_rank_rule_id"] == tilt.TILT_RANK_RULE_ID
    assert profile["maximum_stock_weight_change_fraction"] == "0.20"
    assert profile["admission_leverage"] == "2"
    assert profile["target_gross_exposure"] == "0.98"
    assert profile["realized_borrowing_allowed"] is False
    assert profile["maximum_mean_target_weight_l1_error"] == "0.02"
    assert profile["maximum_single_target_weight_l1_error"] == "0.05"
    assert profile["backtest_only"] is True
    assert profile["live_orders"] is False
    assert profile["paper_orders"] is False
    assert profile["funded_orders"] is False
    assert profile["trading"] is False
    assert subject.expected_tilt_custom_statistic_names() == (
        subject.AGGREGATES_STATISTIC_NAME,
        subject.META_STATISTIC_NAME,
    )
    assert bridge.require_bridge_profile(targets.ROLE_MATCHED) == baseline


@pytest.mark.parametrize(
    ("role", "variant"),
    (
        (targets.ROLE_MATCHED, subject.TILT_VARIANT),
        (tilt.TILT_ROLE, base.CAP90_VARIANT),
        (tilt.TILT_ROLE, "r177"),
        (True, subject.TILT_VARIANT),
    ),
)
def test_tilt_driver_rejects_other_roles_and_variants_before_qc_access(
    role, variant
):
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderTiltQcRuntimeError,
        match="role or variant is not frozen",
    ):
        subject.AcceptedRiskSixUniverseOrderTiltQcDriver(
            None, role=role, variant=variant
        )


def _tilt_driver(execution_valid=True):
    profile = subject.require_tilt_profile()
    decisions = []
    baseline_decisions = []
    for index in range(base.EXPECTED_DECISION_COUNT):
        session = f"decision-{index:03d}"
        baseline_sha = hashlib.sha256(session.encode("ascii")).hexdigest()
        draft = tilt.TiltDecisionTarget(
            session=session,
            role=tilt.TILT_ROLE,
            construction_id="synthetic-construction",
            construction_sha256="c" * 64,
            baseline_target_sha256=baseline_sha,
            target_weights=(),
            sleeves=(),
            target_sha256="",
        )
        decisions.append(dataclasses.replace(
            draft, target_sha256=tilt._sha(draft._semantic())
        ))
        baseline_decisions.append(SimpleNamespace(
            session=session, target_sha256=baseline_sha
        ))
    baseline_path = SimpleNamespace(
        gate_profile_id=profile["gate_profile_id"],
        gate_profile_sha256=profile["gate_profile_sha256"],
        evaluation_profile_id=profile["evaluation_profile_id"],
        evaluation_profile_sha256=profile["evaluation_profile_sha256"],
        construction_path_sha256="c" * 64,
        target_path_sha256="b" * 64,
        decisions=tuple(baseline_decisions),
    )
    matched_builder = SimpleNamespace(
        completed=True,
        complete_path=lambda: baseline_path,
    )
    builder = object.__new__(tilt.MatchedRevisionTiltTargetBuilder)
    builder._matched = matched_builder
    builder._decisions = decisions
    builder._failed = False

    sessions = tuple(
        (datetime(2021, 1, 4) + timedelta(days=index)).date().isoformat()
        for index in range(base.EXPECTED_SESSION_COUNT - 1)
    ) + (base.EVALUATION_END_SESSION,)
    emitted = {}
    driver = object.__new__(subject.AcceptedRiskSixUniverseOrderTiltQcDriver)
    driver._initialized = True
    driver._completed = False
    driver._tilt_initialized = True
    driver._bridge_initialized = True
    driver._variant = base.CAP90_VARIANT
    driver._role = tilt.TILT_ROLE
    driver._bridge_role = tilt.TILT_ROLE
    driver._profile = profile
    driver._target_builder = builder
    driver._tilt_profile = profile
    driver._tilt_builder = builder
    driver._bridge_profile = profile
    driver._bridge_builder = builder
    driver._executor = SimpleNamespace(terminal_aggregate=lambda: {
        "run_valid": execution_valid,
        "decision_count": base.EXPECTED_DECISION_COUNT,
        "invalid_order_count": 0 if execution_valid else 22,
        "mean_target_weight_l1_error": "0.01",
        "maximum_target_weight_l1_error": "0.03",
        "target_weight_l1_error_mark_basis": (
            "prior_close_reference_prices_not_realized_open_prices"
        ),
    })
    driver._evaluation_sessions = sessions
    driver._account_observations = {
        session: Decimal("1000000") for session in sessions
    }
    driver._gross_exposure_observations = {
        session: Decimal("0.98") for session in sessions
    }
    driver._bridge_cash_observations = {
        session: Decimal("20000") for session in sessions
    }
    driver._bridge_event_cash_count = 1
    driver._bridge_event_cash_minimum = Decimal("10000")
    driver._decision_target_sha256s = [
        decision.target_sha256 for decision in decisions
    ]
    driver._fallback_counts = {
        "FULL_STOCK_SLOTS": (
            base.EXPECTED_DECISION_COUNT * len(base._gate.UNIVERSE_IDS)
        )
    }
    driver._sleeve_diagnostics = base._empty_sleeve_diagnostics()
    for record in driver._sleeve_diagnostics.values():
        record["decision_count"] = base.EXPECTED_DECISION_COUNT
    driver._forced_ledger = forced.empty_forced_delisting_ledger()
    driver._reference_history_call_count = base.EXPECTED_DECISION_COUNT
    driver._source_row_count = 0
    driver._active_dynamic_sids = set()
    driver._maximum_active_dynamic_security_count = 0
    driver._removed_dynamic_security_count = 0
    driver._fundamental_snapshot_unavailable_sessions = []
    driver._decision_set = frozenset(
        decision.session for decision in decisions
    )
    driver._constituent_collection_unavailable_path = []
    driver._package = SimpleNamespace(
        package_id="synthetic-package",
        package_sha256="p" * 64,
        activation_manifest_sha256="m" * 64,
    )
    driver._resolution = SimpleNamespace(
        resolution_id="synthetic-resolution",
        resolution_sha256="r" * 64,
    )
    driver._algorithm = SimpleNamespace(
        time=datetime(2026, 1, 1, 0, 0),
        live_mode=False,
        set_summary_statistic=lambda name, value: emitted.setdefault(name, value),
    )
    return driver, emitted


@pytest.mark.parametrize("execution_valid", (True, False))
def test_tilt_aggregate_emits_exact_two_digest_bound_statistics(
    execution_valid
):
    driver, emitted = _tilt_driver(execution_valid)
    aggregate = driver.on_end_of_algorithm()
    assert aggregate["run_valid"] is execution_valid
    assert aggregate["execution"]["invalid_order_count"] == (
        0 if execution_valid else 22
    )
    assert aggregate["schema"] == subject.TILT_SUMMARY_SCHEMA
    assert aggregate["role"] == tilt.TILT_ROLE
    assert aggregate["matched_baseline_profile_sha256"] == (
        subject.BASELINE_MATCHED_PROFILE_SHA256
    )
    assert aggregate["matched_baseline_target_path_sha256"] == "b" * 64
    assert aggregate["tilt_rank_rule_id"] == tilt.TILT_RANK_RULE_ID
    assert aggregate["daily_cash_nonnegative"] is True
    assert aggregate["order_event_cash_nonnegative"] is True
    assert aggregate["end_day_gross_at_most_one"] is True
    assert aggregate["target_tracking_valid"] is True
    assert tuple(sorted(emitted)) == (
        subject.expected_tilt_custom_statistic_names()
    )
    assert all(
        len(value.encode("ascii")) <= subject.MAXIMUM_STATISTIC_BYTES
        for value in emitted.values()
    )
    meta = json.loads(emitted[subject.META_STATISTIC_NAME])
    assert meta["schema"] == subject.TILT_META_SCHEMA
    assert meta["role"] == tilt.TILT_ROLE
    assert meta["aggregate_sha256"] == hashlib.sha256(
        emitted[subject.AGGREGATES_STATISTIC_NAME].encode("ascii")
    ).hexdigest()
    assert json.loads(emitted[subject.AGGREGATES_STATISTIC_NAME]) == aggregate
    assert driver.completed is True


def test_tilt_refuses_live_mode_and_wrong_profile_before_emission():
    driver, emitted = _tilt_driver()
    driver._algorithm.live_mode = True
    with pytest.raises(
        bridge.AcceptedRiskSixUniverseOrderBridgeQcRuntimeError,
        match="backtest-only",
    ):
        driver.on_end_of_algorithm()
    assert emitted == {}
    driver._algorithm.live_mode = False
    driver._profile["role"] = targets.ROLE_MATCHED
    with pytest.raises(
        bridge.AcceptedRiskSixUniverseOrderBridgeQcRuntimeError,
        match="authority changed",
    ):
        driver.on_end_of_algorithm()
    assert emitted == {}


def test_tilt_refuses_truncated_transport_before_emission(monkeypatch):
    driver, emitted = _tilt_driver()
    monkeypatch.setattr(bridge, "MAXIMUM_STATISTIC_BYTES", 100)
    with pytest.raises(
        bridge.AcceptedRiskSixUniverseOrderBridgeQcRuntimeError,
        match="transport bound",
    ):
        driver.on_end_of_algorithm()
    assert emitted == {}


def test_tilt_callback_accepts_unchanged_authority_before_preopen():
    driver, _emitted = _tilt_driver()
    calls = []
    driver._executor.on_preopen = lambda clock: calls.append(clock) or True
    assert driver.on_before_open() is True
    assert calls == [driver._algorithm.time]


def test_tilt_inherits_effective_two_x_check_before_order(monkeypatch):
    driver, _emitted = _tilt_driver()
    symbol = object()
    security = SimpleNamespace(
        leverage=Decimal(1),
    )
    security.buying_power_model = SimpleNamespace(
        get_leverage=lambda observed: observed.leverage
    )
    driver._algorithm.securities = {symbol: security}
    submissions = []
    monkeypatch.setattr(
        base.AcceptedRiskSixUniverseOrderQcDriver,
        "_submit_market_on_open",
        lambda _self, *_args: submissions.append("submitted"),
    )
    with pytest.raises(
        bridge.AcceptedRiskSixUniverseOrderBridgeQcRuntimeError,
        match="effective security leverage is not two",
    ):
        driver._submit_market_on_open(symbol, 1, "tilt")
    assert submissions == []
    security.leverage = Decimal(2)
    driver._submit_market_on_open(symbol, 1, "tilt")
    assert submissions == ["submitted"]


@pytest.mark.parametrize(
    "mutation",
    ("role", "variant", "profile_content", "profile_identity", "builder"),
)
def test_tilt_callback_refuses_changed_authority_before_preopen(mutation):
    driver, _emitted = _tilt_driver()
    calls = []
    driver._executor.on_preopen = lambda clock: calls.append(clock) or True
    if mutation == "role":
        driver._role = targets.ROLE_MATCHED
    elif mutation == "variant":
        driver._variant = "r177"
    elif mutation == "profile_content":
        driver._profile["role"] = targets.ROLE_MATCHED
    elif mutation == "profile_identity":
        driver._profile = dict(driver._profile)
    else:
        driver._target_builder = object.__new__(
            tilt.MatchedRevisionTiltTargetBuilder
        )
    with pytest.raises(
        bridge.AcceptedRiskSixUniverseOrderBridgeQcRuntimeError,
        match="authority changed",
    ):
        driver.on_before_open()
    assert calls == []


@pytest.mark.parametrize(
    ("mutation", "valid"),
    (("cash", False), ("gross", False), ("tracking", False),
     ("unchanged", True)),
)
def test_tilt_inherits_bridge_account_and_tracking_gates(mutation, valid):
    driver, _emitted = _tilt_driver()
    if mutation == "cash":
        session = driver._evaluation_sessions[-1]
        driver._bridge_cash_observations[session] = Decimal("-1")
        with pytest.raises(
            bridge.AcceptedRiskSixUniverseOrderBridgeQcRuntimeError,
            match="daily cash path",
        ):
            driver.on_end_of_algorithm()
        return
    if mutation == "gross":
        session = driver._evaluation_sessions[-1]
        driver._gross_exposure_observations[session] = Decimal("1.001")
    if mutation == "tracking":
        driver._executor.terminal_aggregate = lambda: {
            "run_valid": True,
            "decision_count": base.EXPECTED_DECISION_COUNT,
            "invalid_order_count": 0,
            "mean_target_weight_l1_error": "0.021",
            "maximum_target_weight_l1_error": "0.03",
            "target_weight_l1_error_mark_basis": (
                "prior_close_reference_prices_not_realized_open_prices"
            ),
        }
    aggregate = driver.on_end_of_algorithm()
    assert aggregate["run_valid"] is valid
    assert aggregate["target_tracking_valid"] is (mutation != "tracking")


def test_tilt_runtime_source_is_qc_prelude_safe():
    source = open(subject.__file__, encoding="utf-8").read()
    assert "from __future__" not in source
    compile("from AlgorithmImports import *\n" + source, subject.__file__, "exec")
