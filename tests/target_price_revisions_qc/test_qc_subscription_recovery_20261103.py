"""Synthetic-only recovery planner/adapter checks; no QC or private evidence."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from types import ModuleType, SimpleNamespace
import sys

import pytest

from research.target_price_revisions_qc import subscription_recovery_20261103 as recovery


def proof(sid="SYNTHETIC-SID"):
    return {"security_id": sid, **{key: True for key in recovery.PROOF_FIELDS}}


def test_supplied_plans_never_issue_native_or_economic_authority():
    row = proof()
    before = deepcopy(row)
    plan = recovery.plan_reconciliation(["SYNTHETIC-SID"], [row])
    assert plan["candidate_release_ids"] == ["SYNTHETIC-SID"]
    assert plan["tracked_manual_ids_before"] == 1 and plan["tracked_manual_ids_after"] == 0
    assert row == before
    for key in ("supplied_rows_are_native_authority", "native_capacity_proven",
                "native_full_window_verified", "source_inputs_admitted", "economics_accepted"):
        assert plan[key] is False
    assert plan["fixed_active_id_limit"] == 4096


@pytest.mark.parametrize("field", recovery.PROOF_FIELDS)
@pytest.mark.parametrize("unknown", (False, None))
def test_every_absent_or_unknown_proof_retains_slot(field, unknown):
    row = proof()
    row[field] = unknown
    plan = recovery.plan_reconciliation(["SYNTHETIC-SID"], [row])
    assert plan["candidate_release_ids"] == []
    assert plan["refusals"][field] == 1


@pytest.mark.parametrize("mutate", (
    lambda row: row.update({"unreviewed_override": True}),
    lambda row: row.pop("native_zero_quantity"),
    lambda row: row.update({"native_zero_quantity": 1}),
    lambda row: row.update({"security_id": ""}),
))
def test_planning_schema_refuses_ambiguity(mutate):
    row = proof()
    mutate(row)
    with pytest.raises(recovery.ResourceRecoveryRefusal):
        recovery.plan_reconciliation(["SYNTHETIC-SID"], [row])


def test_duplicate_or_excessive_domains_refuse_and_fixed_limit_cannot_be_raised():
    with pytest.raises(recovery.ResourceRecoveryRefusal):
        recovery.plan_reconciliation(["SYNTHETIC-SID"] * 2, [])
    with pytest.raises(recovery.ResourceRecoveryRefusal):
        recovery.plan_reconciliation([str(i) for i in range(4097)], [])
    with pytest.raises(recovery.ResourceRecoveryRefusal):
        recovery.plan_reconciliation(["SYNTHETIC-SID"], [proof(), proof()])


@pytest.fixture
def engine(monkeypatch):
    native = ModuleType("AlgorithmImports")

    class QCAlgorithm:
        pass

    class Symbol:
        def __init__(self, sid="SYNTHETIC-SID"):
            self.id, self.security_type = sid, "EQUITY"

    class Security:
        def __init__(self, symbol):
            self.symbol = symbol
            self.subscriptions = []
            self.is_delisted, self.is_tradable = True, False

    class Order:
        def __init__(self, symbol):
            self.symbol = symbol

    class Delisting:
        def __init__(self, symbol, kind="DELISTED"):
            self.symbol, self.type = symbol, kind

    class Slice:
        def __init__(self, event):
            self.delistings = {"event": event}

    for name, value in locals().copy().items():
        if name in ("QCAlgorithm", "Symbol", "Security", "Order", "Delisting", "Slice"):
            setattr(native, name, value)
    native.DelistingType = SimpleNamespace(DELISTED="DELISTED", WARNING="WARNING")
    native.SecurityType = SimpleNamespace(EQUITY="EQUITY")
    monkeypatch.setitem(sys.modules, "AlgorithmImports", native)

    class Parent(QCAlgorithm):
        def initialize(self):
            self.parent_initialized = True

        def _ensure_raw_subscription(self, symbol):
            if symbol.id not in self._manual_symbols and len(self._manual_symbols) >= 4096:
                raise ValueError("original fixed subscription bound")
            self._manual_symbols.add(symbol.id)
            return "original-guard-result"

        def on_data(self, data):
            self.parent_calls += 1
            if self.parent_error is not None:
                raise self.parent_error
            return "parent-result"

        def on_end_of_algorithm(self):
            self.parent_ended = True
            return "original-end-result"

    class Algorithm(recovery.ResourceRecoveryMixin, Parent):
        pass

    algo = Algorithm()
    algo.initialize()
    symbol = Symbol()
    event = Delisting(symbol)
    data = Slice(event)
    security = Security(symbol)
    algo.live_mode, algo.is_warming_up = False, False
    algo.project_id, algo.algorithm_id = 123, "SYNTHETIC-BACKTEST"
    algo._config = {"project_id": 123}
    algo.utc_time = datetime(2026, 1, 5, 15, tzinfo=timezone.utc)
    algo.current_slice = data
    algo.get_locked = lambda: True
    algo._evidence = SimpleNamespace(require_binding=lambda: "synthetic-binding")
    algo._context_symbols = set()
    algo._symbols = {symbol.id: symbol}
    algo._manual_symbols = {symbol.id}
    algo._delisted_ids = {symbol.id}
    algo._warning_ids = {symbol.id}
    algo._custody_since = {symbol.id: datetime(2025, 1, 1, tzinfo=timezone.utc)}
    algo._split_factors = {(symbol.id, "2025-02-01"): Fraction(2)}
    algo._ever_filled_ids, algo._ever_targeted_ids = {symbol.id}, {symbol.id}
    algo._targets = {}
    algo._quantity_ledger = {symbol.id: Fraction(0)}
    algo._cash_ledger = Fraction(100000)
    algo._fees, algo._fill_events = Fraction(1), 2
    algo._fill_history_unknown = False
    algo.securities = {symbol: security}
    algo.portfolio = {symbol: SimpleNamespace(quantity=Fraction(0))}
    algo.manager_configs = []
    algo.subscription_manager = SimpleNamespace(subscription_data_config_service=SimpleNamespace(
        get_subscription_data_configs=lambda *args: list(algo.manager_configs)))
    algo.history, algo.opened = [Order(symbol)], []
    algo.transactions = SimpleNamespace(get_orders=lambda: list(algo.history),
                                        get_open_orders=lambda: list(algo.opened))
    algo.audit = []
    algo._log_audit = lambda kind, payload: algo.audit.append((kind, deepcopy(payload)))
    algo.parent_calls, algo.parent_error = 0, None
    return algo, symbol, event, data, native


def test_only_manual_bookkeeping_changes_after_parent_actions(engine):
    algo, symbol, event, data, native = engine
    names = ("_symbols", "_custody_since", "_split_factors", "_warning_ids", "_delisted_ids",
             "_ever_filled_ids", "_ever_targeted_ids", "_targets", "_quantity_ledger",
             "_cash_ledger", "_fees", "_fill_events")
    refs = {name: getattr(algo, name) for name in names}
    values = {name: deepcopy(getattr(algo, name)) for name in names if name != "_symbols"}
    assert algo.on_data(data) == "parent-result"
    assert algo.parent_calls == 1 and algo._manual_symbols == set()
    assert algo.resource_recovery_census()["proved_final_bookkeeping_releases"] == 1
    for name in names:
        assert getattr(algo, name) is refs[name]
    for name, value in values.items():
        assert getattr(algo, name) == value
    assert algo.securities[symbol].subscriptions == []
    assert algo.history and algo.audit[0][0] == "SUBSCRIPTION"
    assert not hasattr(algo, "remove_security")


@pytest.mark.parametrize("fault", (
    "warning", "no_final", "duplicate_final", "not_registered", "context",
    "not_delisted", "tradable", "held", "ledger_nonzero", "ledger_missing",
    "security_config", "manager_config", "open_order", "untyped_history",
    "unknown_history", "live", "warmup", "job_mismatch", "unlocked", "missing_type",
))
def test_native_unknown_or_incomplete_final_proof_retains_everything(engine, fault, monkeypatch):
    algo, symbol, event, data, native = engine
    if fault == "warning": event.type = native.DelistingType.WARNING
    elif fault == "no_final": data.delistings = {}
    elif fault == "duplicate_final": data.delistings["second"] = native.Delisting(symbol)
    elif fault == "not_registered": algo._symbols = {}
    elif fault == "context": algo._context_symbols.add(symbol)
    elif fault == "not_delisted": algo.securities[symbol].is_delisted = False
    elif fault == "tradable": algo.securities[symbol].is_tradable = True
    elif fault == "held": algo.portfolio[symbol].quantity = Fraction(1)
    elif fault == "ledger_nonzero": algo._quantity_ledger[symbol.id] = Fraction(1)
    elif fault == "ledger_missing": algo._quantity_ledger = {}
    elif fault == "security_config": algo.securities[symbol].subscriptions = [object()]
    elif fault == "manager_config": algo.manager_configs = [object()]
    elif fault == "open_order": algo.opened = [native.Order(symbol)]
    elif fault == "untyped_history": algo.history = [object()]
    elif fault == "unknown_history": algo._fill_history_unknown = True
    elif fault == "live": algo.live_mode = True
    elif fault == "warmup": algo.is_warming_up = True
    elif fault == "job_mismatch": algo._config = {"project_id": 999}
    elif fault == "unlocked": algo.get_locked = lambda: False
    elif fault == "missing_type": monkeypatch.delattr(native, "Security")
    assert algo.on_data(data) == "parent-result"
    assert algo.parent_calls == 1 and algo._manual_symbols == {symbol.id}
    assert algo.resource_recovery_census()["proved_final_bookkeeping_releases"] == 0


@pytest.mark.parametrize("fault", ("audit_failure", "clock_drift", "config_drift", "quantity_drift"))
def test_evidence_and_reobservation_boundaries_precede_mutation(engine, fault):
    algo, symbol, event, data, native = engine

    def audit(kind, payload):
        if fault == "audit_failure":
            raise ValueError("synthetic audit failure")
        if fault == "clock_drift":
            algo.utc_time += timedelta(seconds=1)
        elif fault == "config_drift":
            algo.manager_configs = [object()]
        elif fault == "quantity_drift":
            algo.portfolio[symbol].quantity = Fraction(1)

    algo._log_audit = audit
    algo.on_data(data)
    assert algo._manual_symbols == {symbol.id}
    assert algo.resource_recovery_census()["proved_final_bookkeeping_releases"] == 0


@pytest.mark.parametrize("failure", (ValueError("parent-error"), KeyboardInterrupt()))
def test_parent_failures_propagate_without_recovery(engine, failure):
    algo, symbol, event, data, native = engine
    algo.parent_error = failure
    with pytest.raises(type(failure)):
        algo.on_data(data)
    assert algo._manual_symbols == {symbol.id}
    assert algo.audit == []


def test_fixed_original_guard_and_bounded_cumulative_census(engine, monkeypatch):
    algo, symbol, event, data, native = engine
    algo._manual_symbols = {str(i) for i in range(4096)}
    with pytest.raises(ValueError, match="original fixed"):
        algo._ensure_raw_subscription(native.Symbol("EXCESS"))
    algo._manual_symbols = set()
    monkeypatch.setattr(recovery, "MAX_CENSUS_IDS", 2)
    for i in range(3):
        assert algo._ensure_raw_subscription(native.Symbol("SYNTHETIC-" + str(i))) == "original-guard-result"
    census = algo.resource_recovery_census()
    assert census["tracked_manual_id_count"] == 3
    assert census["cumulative_observed_id_count"] is None
    assert census["cumulative_observed_id_lower_bound"] == 2
    assert census["census_complete"] is False
    assert census["native_capacity_proven"] is False
    assert census["actual_native_active_configuration_count"] is None


def test_census_is_logged_before_original_export(engine):
    algo, symbol, event, data, native = engine
    assert algo.on_end_of_algorithm() == "original-end-result"
    assert algo.parent_ended is True
    assert algo.audit[-1][1]["kind"] == "resource_recovery_census"
    assert algo.audit[-1][1]["native_full_window_verified"] is False
