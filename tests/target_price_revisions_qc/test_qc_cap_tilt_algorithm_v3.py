"""Synthetic lossless runtime transport proofs; no empirical/cloud/operator I/O."""
import ast
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS

import pytest

from tests.target_price_revisions_qc import test_qc_cap_tilt_algorithm_v2 as v2
from tests.target_price_revisions_qc import test_qc_cap_tilt_algorithm as v1
from tests.target_price_revisions_qc.test_qc_cap_tilt_audit import fixture

LANE = v2.LANE


@pytest.fixture
def runtime(monkeypatch):
    previous = v2.runtime.__wrapped__(monkeypatch)
    module = ModuleType("cap_runtime_v3")
    module.__dict__["__CAP_LOG_TRANSPORT_SOURCE_LITERAL__"] = (LANE / "cap_log_transport.py").read_text()
    exec(compile((LANE / "cap_tilt_algorithm_v3.py").read_bytes(), "main.py", "exec"), module.__dict__)
    module.previous = previous
    return module


def logging(algo):
    algo._audit_log_wire_chars = algo._audit_log_record_count = 0
    algo.logs = []
    algo.log = algo.logs.append
    return algo


def decode(runtime, lines):
    response = {"success": True, "logs": list(lines), "length": len(lines)}
    before = deepcopy(response)
    restored = runtime._cap_transport.decode_logs(response)
    assert response == before
    return restored["logs"]


def synthetic_records():
    """Complete bounded 14-decision, 60-NAV, one-summary aggregate fixture."""
    lines = fixture()[1]["logs"]
    records = []
    for line in lines:
        marker, raw = line.split(" ", 1)
        kind = marker.removeprefix("MATCHED_")
        record = json.loads(raw)
        if kind == "SUMMARY":
            record["native_final_delisting_compatibility_exceptions"] = 0
        records.append((kind, record))
    return records


def test_full_realistic_75_record_stream_is_lossless_below_reserved_wire_budget(runtime):
    algo = logging(runtime.TargetPriceCapTiltAlgorithm())
    records = synthetic_records()
    assert len(records) == 75
    assert sum(kind == "NAV" for kind, _ in records) == 60
    assert sum(kind == "COVERAGE" for kind, _ in records) == 14
    plain = ["MATCHED_" + kind + " " + json.dumps(payload, sort_keys=True)
             for kind, payload in records]
    assert sum(map(len, plain)) > 100000  # The uncompressed control cannot fit the observed native quota.
    kept, consumed = [], 0
    for line in plain:
        if consumed + len(line) > 75000:
            break
        kept.append(line)
        consumed += len(line)
    assert not any(line.startswith("MATCHED_SUMMARY ") for line in kept)
    assert len(kept) < 75
    for kind, payload in records:
        algo._log_audit(kind, payload)
    assert algo._audit_log_record_count == 75
    assert algo._audit_log_wire_chars == sum(map(len, algo.logs))
    assert algo._audit_log_wire_chars <= 75000
    assert runtime._cap_transport.MAX_RUN_WIRE_CHARS == 75000
    restored = decode(runtime, algo.logs)
    assert [(line.split(" ", 1)[0].removeprefix("MATCHED_"), json.loads(line.split(" ", 1)[1]))
            for line in restored] == records


def test_oversized_single_record_refuses_before_counters_or_logging(runtime):
    algo = logging(runtime.TargetPriceCapTiltAlgorithm())
    with pytest.raises(ValueError):
        algo._log_audit("NAV", {"session": "2025-01-02", "oversized": "x" * 20000})
    assert algo.logs == [] and algo._audit_log_wire_chars == algo._audit_log_record_count == 0


def test_run_budget_exhaustion_refuses_without_silent_drop_or_counter_change(runtime):
    algo = logging(runtime.TargetPriceCapTiltAlgorithm())
    payload = {"session": "2025-01-02", "nav": "100000"}
    wire = runtime._cap_transport.encode_record("NAV", payload)
    algo._audit_log_wire_chars = 75000 - len(wire)
    algo._log_audit("NAV", payload)
    assert algo._audit_log_wire_chars == 75000 and algo._audit_log_record_count == 1
    before = list(algo.logs)
    with pytest.raises(ValueError, match="wire budget"):
        algo._log_audit("NAV", payload)
    assert algo.logs == before and algo._audit_log_wire_chars == 75000
    assert algo._audit_log_record_count == 1


def test_logger_does_not_coerce_or_silently_drop_unknown_record_kind(runtime):
    algo = logging(runtime.TargetPriceCapTiltAlgorithm())
    with pytest.raises(ValueError):
        algo._log_audit("OTHER", {"session": "2025-01-02"})
    assert algo.logs == [] and algo._audit_log_record_count == 0


def rebalance(runtime):
    algo = logging(v1.setup(runtime, "tpr_off"))
    algo.time, algo.is_warming_up = datetime(2025, 1, 2, 9, 20), False
    algo._attempted_days, algo._decision_count, algo._refused_count = set(), 0, 0
    algo._sleeve_selected_decisions = {etf: 0 for etf in runtime.ETFS}
    algo._prior_close_nav, algo._prior_close_day = Fraction(100000), None
    algo._requested_shares = algo._submitted_shares = algo._submitted = 0
    algo._tickets = []
    class Portfolio(dict):
        cash = 100000
    algo.portfolio = Portfolio({symbol: NS(symbol=symbol, invested=False, quantity=0)
                               for symbol in algo._symbols.values()})
    algo._prior_mark = lambda symbol: (Fraction(50), Fraction(100000))
    algo._assert_raw_subscriptions = lambda symbol: None
    algo.market_on_open_order = lambda *args, **kwargs: object()
    algo._rebalance()
    return algo


def test_actual_rebalance_coverage_payload_and_orders_match_v2_exactly(runtime):
    previous, current = rebalance(runtime.previous), rebalance(runtime)
    assert previous._submitted == current._submitted > 0
    assert previous._submitted_shares == current._submitted_shares
    assert len(previous.logs) == len(current.logs) == 1
    restored = decode(runtime, current.logs)
    assert restored[0].startswith("MATCHED_COVERAGE ")
    assert json.loads(restored[0].split(" ", 1)[1]) == json.loads(previous.logs[0].split(" ", 1)[1])


def daily(runtime):
    algo, _, _, _, _, _, _, _ = v2.native_final(runtime)
    logging(algo)
    algo._config = {"arm": "tpr_off"}
    algo.time = datetime(2025, 2, 4, 16)
    algo._valuation_days = set()
    algo._quantity_ledger, algo._cash_ledger = {}, Fraction(100000)
    algo._max_cash_residual = algo._max_nav_residual = Fraction(0)
    algo._position_ledger_mismatches = algo._risk_breaches = algo._name_soft_cap_breaches = 0
    algo._max_name_exposure = Fraction(0)
    class Portfolio(dict):
        cash = total_portfolio_value = 100000
        total_holdings_value = 0
    algo.portfolio = Portfolio()
    algo._daily_audit()
    return algo


def test_actual_daily_nav_payload_and_ledgers_match_v2_exactly(runtime):
    previous, current = daily(runtime.previous), daily(runtime)
    restored = decode(runtime, current.logs)
    assert restored[0].startswith("MATCHED_NAV ")
    assert json.loads(restored[0].split(" ", 1)[1]) == json.loads(previous.logs[0].split(" ", 1)[1])
    assert current._prior_close_nav == previous._prior_close_nav == 100000


def summary(runtime):
    algo, _, _, _, _, _, _, event = v2.native_final(runtime)
    logging(algo)
    algo.on_order_event(event)
    algo.on_data(algo.current_slice)
    algo._config = {"candidate_id": "synthetic", "arm": "tpr_off", "cost": "baseline"}
    algo._decision_coverage = {day: {"sleeves": {etf: {} for etf in runtime.ETFS}} for day in runtime.DECISIONS}
    algo._attempted_days = set(runtime.DECISIONS)
    algo._decision_count, algo._refused_count = 14, 0
    algo._warmup_finished_minute_validated = True
    algo._max_nav_residual = algo._max_cash_residual = Fraction(0)
    algo._position_ledger_mismatches = algo._risk_breaches = 0
    algo._valuation_days = {f"synthetic-{number}" for number in range(59)} | {"2025-03-31"}
    algo._prior_close_day = datetime(2025, 3, 31).date()
    algo._cap_callback_count, algo._cap_snapshots = 1, [{}]
    algo._submitted, algo._requested_shares, algo._submitted_shares = 1, 3, 3
    algo._manual_symbols = {"A"}
    algo._context_initializer_skips = algo._context_change_skips = 0
    algo._max_name_exposure, algo._name_soft_cap_breaches = Fraction(0), 0
    algo._sleeve_selected_decisions = {etf: 14 for etf in runtime.ETFS}
    algo.on_end_of_algorithm()
    return algo


def test_actual_native_final_summary_payload_and_false_gates_match_v2_exactly(runtime):
    previous, current = summary(runtime.previous), summary(runtime)
    assert previous._cash_ledger == current._cash_ledger == Fraction(245, 2)
    assert previous._quantity_ledger == current._quantity_ledger == {"A": Fraction(0)}
    restored = decode(runtime, current.logs)
    logical = json.loads(restored[0].split(" ", 1)[1])
    assert logical == json.loads(previous.logs[0].split(" ", 1)[1])
    assert logical["meaningful_execution"] is False and logical["development_execution_qualified"] is False
    assert logical["canonical_admission"] is False and logical["native_final_delisting_compatibility_exceptions"] == 1


def test_v3_only_changes_embedding_initialization_and_three_logging_calls():
    before = ast.parse((LANE / "cap_tilt_algorithm_v2.py").read_bytes())
    after = ast.parse((LANE / "cap_tilt_algorithm_v3.py").read_bytes())
    before.body.pop(0)
    after.body.pop(0)
    additions = []
    filtered = []
    for item in after.body:
        if (isinstance(item, ast.ImportFrom) and item.module == "types"
                or isinstance(item, ast.Assign) and any(isinstance(target, ast.Name)
                    and target.id in {"_CAP_LOG_TRANSPORT_SOURCE", "_cap_transport"} for target in item.targets)
                or isinstance(item, ast.Expr) and isinstance(item.value, ast.Call)
                    and isinstance(item.value.func, ast.Name) and item.value.func.id == "exec"):
            additions.append(item)
        else:
            filtered.append(item)
    assert len(additions) == 4
    after.body = filtered
    old_class = next(item for item in before.body if isinstance(item, ast.ClassDef) and item.name == "TargetPriceCapTiltAlgorithm")
    new_class = next(item for item in after.body if isinstance(item, ast.ClassDef) and item.name == "TargetPriceCapTiltAlgorithm")
    old_methods = {item.name: item for item in old_class.body if isinstance(item, ast.FunctionDef)}
    new_methods = {item.name: item for item in new_class.body if isinstance(item, ast.FunctionDef)}
    assert set(new_methods) == set(old_methods) | {"_log_audit"}
    new_class.body.remove(new_methods["_log_audit"])
    init = new_methods["initialize"]
    fields = {"_audit_log_wire_chars", "_audit_log_record_count"}
    new_fields = [item for item in init.body if isinstance(item, ast.Assign)
                  and {target.attr for target in item.targets if isinstance(target, ast.Attribute)} == fields]
    assert len(new_fields) == 1
    assert isinstance(new_fields[0].value, ast.Constant) and new_fields[0].value.value == 0
    init.body.remove(new_fields[0])
    for method, kind in (("_rebalance", "COVERAGE"), ("_daily_audit", "NAV"), ("on_end_of_algorithm", "SUMMARY")):
        new_call = next(node for node in ast.walk(new_methods[method]) if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute) and node.func.attr == "_log_audit")
        old_call = next(node for node in ast.walk(old_methods[method]) if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute) and node.func.attr == "log")
        assert len(new_call.args) == 2 and new_call.args[0].value == kind and new_call.keywords == []
        old_payload = old_call.args[0] if kind == "COVERAGE" else old_call.args[0].right.args[0]
        if kind == "COVERAGE":
            assert isinstance(old_payload, ast.Name) and old_payload.id == "coverage_log"
            assert isinstance(new_call.args[1], ast.Name) and new_call.args[1].id == "coverage"
        else:
            assert ast.dump(new_call.args[1]) == ast.dump(old_payload)
        new_call.func, new_call.args, new_call.keywords = deepcopy(old_call.func), deepcopy(old_call.args), deepcopy(old_call.keywords)
    assert ast.dump(after) == ast.dump(before)


def test_executed_v1_v2_runtime_sources_stay_immutable():
    expected = {"cap_tilt_algorithm.py": "c8804b43b9a25b5fe1ce3f8b5fac424c129c9e7b39a4ad0480b3fbd98e98ab37",
                "cap_tilt_algorithm_v2.py": "5fc7e2c95fea3fedebe66e627d0be700b2b67acab81d4f9e7cdee40c994ce871"}
    assert all(hashlib.sha256((LANE / name).read_bytes()).hexdigest() == digest for name, digest in expected.items())
