"""Public synthetic source-load regression, never native compatibility proof."""
import ast
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest

from research.target_price_revisions_qc import comparison_20261107_sid_cash_single_base_bundle as p
from tests.target_price_revisions_qc import test_qc_comparison_20261107_sid_cash_bundle as v1_tests

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def deny_effects(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("native/private/provider effect denied")
    monkeypatch.setattr(p.bundle.projects.ops, "credential", denied)
    monkeypatch.setattr(p.bundle.projects.ops, "read_private", denied)
    monkeypatch.setattr(p.bundle.projects.http.client, "HTTPSConnection", denied)
    monkeypatch.setattr(p.bundle.projects.subprocess, "run", denied)


@pytest.fixture
def sources():
    return {name: (ROOT / name).read_bytes() for name in p.REQUIRED_SOURCES}


def arguments(sources, arm="cap_off", attempt=2):
    raw = p._wire(v1_tests.registry())
    return {"public_sources": sources, "project_bindings_raw": raw,
        "expected_project_bindings_sha256": p._sha(raw), "arm": arm,
        "operation_id": ("TPR-CMP28-OFF-" if arm == "cap_off" else "TPR-CMP28-")
            + "SID-CASH-20261107-FULL-A" + str(attempt),
        "attempt": attempt, "prior_attempts_looks_sha256": p._sha(b"attempt1 runtime failure and all earlier history retained"),
        "latest_owner_instruction_sha256": p.OWNER_SHA256}


def build(sources, arm="cap_off", **changes):
    args = arguments(sources, arm)
    args.update(changes)
    return p.build_cash_candidate(**args)


def previous(sources, arm="cap_off", **changes):
    args = arguments({name: sources[name] for name in p.predecessor.REQUIRED_SOURCES}, arm)
    args.update(changes)
    return p.predecessor.build_cash_candidate(**args)


def classes(raw):
    return {node.name: node for node in ast.parse(raw).body if isinstance(node, ast.ClassDef)}


@pytest.mark.parametrize("arm", p.ARMS)
def test_all_five_single_base_outputs_preserve_v1_economics_and_history(sources, arm):
    files, report_raw = build(sources, arm)
    again, repeat = build(sources, arm)
    old, old_raw = previous(sources, arm)
    report, before = json.loads(report_raw), json.loads(old_raw)
    config = p.preflight._config(files["comparison_20261028_config.py"])
    old_config = p.preflight._config(old["comparison_20261028_config.py"])
    assert files == again and report_raw == repeat
    assert report["schema"] == "tpr-cmp1107-sid-cash-single-base-project-bundle-v2"
    assert report["source_epoch"] == p.SOURCE_EPOCH != before["source_epoch"]
    assert report["study_id"] == config["study_id"] == before["study_id"] == p.STUDY_ID
    assert report["predecessor_source_epoch"] == before["source_epoch"]
    assert report["predecessor_builder_source_sha256"] == p.PREDECESSOR_SHA256
    assert report["predecessor_same_lineage_render_report_sha256"] == p._sha(old_raw)
    assert config["attempt"] == report["attempt"] == 2
    assert report["prior_attempts_looks_sha256"] == before["prior_attempts_looks_sha256"]
    assert report["earlier_attempts_preserved_not_reset"] is True
    for key in ("policy_sha256", "calendar_sha256", "source_calendar_sha256", "candidate_id",
                "parent_signal_packet_descriptor", "execution_mask_policy"):
        assert report[key] == before[key]
    expected = dict(old_config)
    expected["source_template_closure_sha256"] = config["source_template_closure_sha256"]
    assert config == expected
    assert config["source_template_closure_sha256"] != old_config["source_template_closure_sha256"]
    assert report["config_sha256"] == p._sha(p._wire(config)) != before["config_sha256"]
    driver = report["single_base_class_shape"]["candidate_module"] + ".py"
    assert {name for name in files if files[name] != old[name]} == {"main.py", driver, "comparison_20261028_config.py"}
    for name in files:
        if name not in ("main.py", driver, "comparison_20261028_config.py"):
            assert files[name] == old[name]
    assert p.bundle._functions(files[driver]) == p.bundle._functions(old[driver])
    assert report["cloud_source_hashes"] == {name: p._sha(raw) for name, raw in files.items()}
    assert report["rendered_source_closure_sha256"] == p._sha(p._wire(report["cloud_source_hashes"]))
    assert report["template_source_hashes"] == {name: p._sha(raw) for name, raw in sources.items()}
    assert report["additional_strategy_economics_changed_vs_v1"] is False
    assert report["strategy_economics_changed"] is True  # Original study exclusion remains disclosed.
    assert report["new_policy_or_calendar"] is False
    assert report["native_single_base_compatibility_verified"] is report["native_accounting_accepted"] is False
    assert report["source_inputs_admitted"] is report["canonical_admission"] is report["strategy_accepted"] is False
    assert report["new_attempts"] == report["new_observed_looks"] == report["backtests_launched"] == 0
    assert report["financial_metrics"] is report["accepted_performance"] is None


@pytest.mark.parametrize("arm", p.ARMS)
def test_static_chain_preserves_every_method_and_global_statement(sources, arm):
    files, _ = build(sources, arm)
    old, _ = previous(sources, arm)
    before, after = classes(old["main.py"]), classes(files["main.py"])
    assert "CashExclusionMixin" not in after and "ResourceRecoveryMixin" not in after
    for left, right in (("CashExclusionMixin", "Main"), ("ResourceRecoveryMixin", "_ResourceRecoveryLayer")):
        assert p._dump(before[left].body) == p._dump(after[right].body)
        assert [ast.get_source_segment(old["main.py"].decode(), node) for node in before[left].body
                if isinstance(node, ast.FunctionDef)] == [
            ast.get_source_segment(files["main.py"].decode(), node) for node in after[right].body
                if isinstance(node, ast.FunctionDef)]
    assert p._dump(after["Main"].bases) == p._dump([ast.Name(id="_ResourceRecoveryLayer", ctx=ast.Load())])
    assert len(after["_ResourceRecoveryLayer"].bases) == 1
    tree = ast.parse(files["main.py"])
    position = tree.body.index(p._classes(tree)["_ResourceRecoveryLayer"])
    assert isinstance(tree.body[position - 1], ast.Import)
    assert tree.body[position - 1].names[0].asname == "candidate"
    assert isinstance(tree.body[-1], ast.Delete)
    assert tree.body[-1].targets[0].id == "_ResourceRecoveryLayer"
    assert 0 < len(files["main.py"]) <= 60000
    forbidden = {"exec", "eval", "__import__"}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in forbidden for node in ast.walk(tree))


class ManagedMeta(type):
    """Synthetic Python.NET restriction, not actual CLR/pythonnet evidence."""
    def __new__(meta, name, bases, namespace, **kwargs):
        if len(bases) > 1 and any(getattr(base, "_managed", False) for base in bases):
            raise TypeError("cannot use multiple inheritance with managed classes")
        return super().__new__(meta, name, bases, namespace, **kwargs)


def managed_fixture(monkeypatch, arm):
    class QCAlgorithm(metaclass=ManagedMeta):
        _managed = True

    class Sid:
        def __init__(self, value):
            self.value = value
        def __str__(self):
            return self.value
        def __eq__(self, other):
            return isinstance(other, Sid) and self.value == other.value
        def __hash__(self):
            return hash(self.value)
        @classmethod
        def parse(cls, value):
            return cls(value)

    class Symbol:
        def __init__(self, value):
            self.id = Sid(value)

    class Order:
        def __init__(self, symbol):
            self.symbol = symbol

    class OrderEvent:
        def __init__(self, symbol):
            self.symbol = symbol

    class Slice:
        def __init__(self, actions=False):
            self.splits = {"test": object()} if actions else {}
            self.dividends, self.delistings = {}, {}

    class Security:
        pass

    class Delisting:
        pass

    native = ModuleType("AlgorithmImports")
    for name, value in (("QCAlgorithm", QCAlgorithm), ("SecurityIdentifier", Sid), ("Symbol", Symbol),
            ("Order", Order), ("OrderEvent", OrderEvent), ("Slice", Slice), ("Security", Security), ("Delisting", Delisting)):
        setattr(native, name, value)
    monkeypatch.setitem(sys.modules, "AlgorithmImports", native)

    class Candidate(QCAlgorithm):
        def initialize(self):
            assert self._sid_cash_state["initializing"] is True
            assert self._subscription_recovery_state["peak_tracked"] == 0
            self.trace = [("candidate.initialize", "cash_then_resource_then_candidate")]
            self.live_mode, self.is_warming_up, self._locked = False, False, False
            self.project_id, self.algorithm_id = p.preflight.REGISTERED_PROJECTS[p.bundle.ARM_KEYS[arm]], "1" * 32
            self._config = {"study_id": p.STUDY_ID, "arm": arm, "project_id": self.project_id}
            self._quantity_ledger, self._ever_filled_ids, self._manual_symbols = {}, set(), set()
            self._fill_history_unknown = False
            self.portfolio = NS(values=lambda: [])
            self.orders, self.audit = [], []
            self.transactions = NS(get_open_orders=lambda: [], get_orders=lambda: self.orders)
            self.utc_time = datetime(2021, 1, 4, 15, tzinfo=timezone.utc)
            self.current_slice = None
            self._evidence = NS(require_binding=lambda: "test/" + str(self.project_id) + "/" + self.algorithm_id + "/")
            return "initialized"

        def get_locked(self):
            return self._locked

        def _ensure_raw_subscription(self, symbol):
            self.trace.append(("candidate.subscription", self._subscription_recovery_state["peak_tracked"]))
            self._manual_symbols.add(str(symbol.id))
            return symbol

        def _rebalance(self):
            self.trace.append(("candidate.rebalance", self._sid_cash_state["guard_calls"]))
            return "rebalance"

        def _daily_audit(self):
            self.trace.append(("candidate.valuation", self._sid_cash_state["guard_calls"]))
            return "valuation"

        def on_securities_changed(self, changes):
            self.trace.append(("candidate.securities", self._sid_cash_state["guard_calls"]))
            return changes

        def on_warmup_finished(self):
            self.trace.append(("candidate.warmup", self._sid_cash_state["guard_calls"]))
            return "warmup"

        def market_on_open_order(self, symbol, quantity, *args, **kwargs):
            self.trace.append(("candidate.submit", self._sid_cash_state["guard_calls"]))
            self.orders.append(Order(symbol))
            return NS(order_id=len(self.orders))

        def on_order_event(self, event):
            self.trace.append(("candidate.order_event", self._sid_cash_state["guard_calls"]))
            return event

        def on_data(self, data):
            self.trace.append(("candidate.data", self._sid_cash_state["guard_calls"]))
            self.current_slice = data
            if getattr(self, "raise_parent", False):
                raise RuntimeError("parent action failure")
            return data

        def _log_audit(self, kind, payload):
            self.audit.append((kind, payload))

    module_name = "comparison_20261028_algorithm" if arm == "cap_off" else "comparison_20261028_multi_algorithm"
    class_name = "ComparisonOffAlgorithm" if arm == "cap_off" else "ComparisonMultiAlgorithm"
    module = ModuleType(module_name)
    setattr(module, class_name, Candidate)
    monkeypatch.setitem(sys.modules, module_name, module)
    return native, Candidate


def load_main(raw, name, monkeypatch):
    module = ModuleType(name)
    monkeypatch.setitem(sys.modules, name, module)
    exec(compile(raw, name + ".py", "exec"), module.__dict__)
    return module


@pytest.mark.parametrize("arm", p.ARMS)
def test_managed_metaclass_old_multiple_base_fails_new_static_chain_loads_only_main(sources, arm, monkeypatch):
    native, candidate = managed_fixture(monkeypatch, arm)
    old, _ = previous(sources, arm)
    files, _ = build(sources, arm)
    with pytest.raises(TypeError, match="cannot use multiple inheritance with managed classes"):
        load_main(old["main.py"], "synthetic_old_main", monkeypatch)
    module = load_main(files["main.py"], "synthetic_new_main", monkeypatch)
    discovered = {name: cls for name, cls in vars(module).items() if isinstance(cls, type)
        and cls is not native.QCAlgorithm and issubclass(cls, native.QCAlgorithm)}
    assert set(discovered) == {"Main"}
    assert "_ResourceRecoveryLayer" not in vars(module)
    assert module.Main.__bases__[0].__name__ == "_ResourceRecoveryLayer"
    assert module.Main.__bases__[0].__bases__ == (candidate,)
    assert len(module.Main.__bases__) == len(module.Main.__bases__[0].__bases__) == 1
    algo = module.Main()
    assert algo.initialize() == "initialized"
    assert algo._sid_cash_state["initializing"] is False
    assert algo._sid_cash_state["guard_calls"] == 1
    assert algo.trace == [("candidate.initialize", "cash_then_resource_then_candidate")]


@pytest.mark.parametrize("arm", p.ARMS)
def test_callbacks_keep_cash_resource_candidate_cooperative_super_order(sources, arm, monkeypatch):
    native, _ = managed_fixture(monkeypatch, arm)
    files, _ = build(sources, arm)
    module = load_main(files["main.py"], "synthetic_super_main", monkeypatch)
    algo = module.Main()
    algo.initialize()
    algo._locked = True
    symbol = native.Symbol("SYNTHETIC-OTHER")
    assert algo._ensure_raw_subscription(symbol) is symbol
    assert algo._subscription_recovery_state["seen"] == {"SYNTHETIC-OTHER"}
    assert algo._subscription_recovery_state["peak_tracked"] == 1
    assert algo._rebalance() == "rebalance"
    assert algo._daily_audit() == "valuation"
    changes = object()
    assert algo.on_securities_changed(changes) is changes
    assert algo.on_warmup_finished() == "warmup"
    assert algo.market_on_open_order(symbol, 1).order_id == 1
    event = native.OrderEvent(symbol)
    assert algo.on_order_event(event) is event
    data = native.Slice(actions=True)
    assert algo.on_data(data) is data
    assert algo._sid_cash_state["guard_calls"] == 15
    assert algo.trace == [
        ("candidate.initialize", "cash_then_resource_then_candidate"),
        ("candidate.subscription", 0), ("candidate.rebalance", 2), ("candidate.valuation", 4),
        ("candidate.securities", 6), ("candidate.warmup", 8), ("candidate.submit", 10),
        ("candidate.order_event", 12), ("candidate.data", 14)]
    assert algo._subscription_recovery_state["unknown"] == 0
    algo.raise_parent = True
    with pytest.raises(RuntimeError, match="parent action failure"):
        algo.on_data(data)
    assert algo.trace[-1] == ("candidate.data", 16)
    assert algo._sid_cash_state["guard_calls"] == 16  # No false after-parent success.


@pytest.mark.parametrize("path", sorted(p.PINS))
def test_every_predecessor_and_template_byte_is_fixed_before_render(sources, path):
    changed = dict(sources)
    changed[path] += b"\n"
    with pytest.raises(p.CashBundleRefusal):
        build(changed)


@pytest.mark.parametrize("fault", ("missing", "extra", "text"))
def test_closed_source_set_cannot_accept_caller_code_or_fragment(sources, fault):
    changed = dict(sources)
    if fault == "missing":
        changed.pop(p.PREDECESSOR_MODULE)
    elif fault == "extra":
        changed["arbitrary.py"] = b"raise RuntimeError"
    else:
        changed[p.PREDECESSOR_MODULE] = changed[p.PREDECESSOR_MODULE].decode()
    with pytest.raises(p.CashBundleRefusal):
        build(changed)


@pytest.mark.parametrize("fault", ("header", "suffix", "extra_base", "candidate_import"))
def test_static_main_transform_refuses_unreviewed_source_shape(sources, fault):
    old, _ = previous(sources)
    raw = old["main.py"]
    if fault == "header":
        raw = raw.replace(b"class CashExclusionMixin:", b"class OtherMixin:", 1)
    elif fault == "suffix":
        raw += b"\n"
    elif fault == "extra_base":
        raw = raw.replace(b"class ResourceRecoveryMixin:", b"class ResourceRecoveryMixin(object):", 1)
    else:
        raw = raw.replace(b" as candidate", b" as different", 1)
    with pytest.raises(p.CashBundleRefusal):
        p._single_base_main(raw, arm="cap_off")


def test_off_attempt_two_remains_same_candidate_not_reset_or_pooled(sources):
    args = arguments(sources)
    second, second_raw = p.build_cash_candidate(**args)
    first_args = arguments(sources, attempt=1)
    first, first_raw = p.build_cash_candidate(**first_args)
    a, b_report = json.loads(first_raw), json.loads(second_raw)
    assert a["candidate_id"] == b_report["candidate_id"]
    assert a["study_id"] == b_report["study_id"] == p.STUDY_ID
    assert a["source_template_closure_sha256"] == b_report["source_template_closure_sha256"]
    assert a["prior_attempts_looks_sha256"] == b_report["prior_attempts_looks_sha256"]
    assert a["attempt"] == 1 and b_report["attempt"] == 2
    assert a["config_sha256"] != b_report["config_sha256"]
    assert first["main.py"] == second["main.py"]
    assert b_report["earlier_attempts_preserved_not_reset"] is True
    assert b_report["historical_attempts_looks_pooled"] is False
    assert b_report["new_attempts"] == b_report["new_observed_looks"] == 0
