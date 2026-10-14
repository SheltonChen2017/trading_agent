"""Synthetic runtime boundary proofs, never cloud/provider/operator reads."""
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest
from research.target_price_revisions_qc import cap_observer, cap_tilt

LANE = Path(__file__).resolve().parents[2] / "research/target_price_revisions_qc"


@pytest.fixture
def runtime(monkeypatch):
    api = ModuleType("AlgorithmImports")
    api.FeeModel = type("FeeModel", (), {})
    api.QCAlgorithm = type("QCAlgorithm", (), {})
    api.SplitType = NS(SPLIT_OCCURRED="occurred")
    api.OrderStatus = NS(INVALID="invalid", CANCELED="canceled")
    api.Universe = NS(UNCHANGED="unchanged")
    api.Resolution = NS(MINUTE="minute", DAILY="daily", HOUR="hour")
    api.TickType = NS(TRADE="trade", QUOTE="quote")
    api.DataNormalizationMode = NS(RAW=0, ADJUSTED=1)
    api.SecurityType = NS(EQUITY="equity", BASE="base")
    api.TradeBar = type("TradeBar", (), {})
    for name in ("Order", "OrderEvent", "Delisting"):
        setattr(api, name, type(name, (), {}))
    api.DelistingType = NS(WARNING=object(), DELISTED=object())
    monkeypatch.setitem(sys.modules, "AlgorithmImports", api)
    monkeypatch.setitem(sys.modules, "cap_tilt", cap_tilt)
    monkeypatch.setitem(sys.modules, "cap_observer", cap_observer)
    core = ModuleType("proxy_core")
    exec(compile((LANE / "cloud_algorithm_v2.py").read_bytes(), "proxy_core.py", "exec"), core.__dict__)
    monkeypatch.setitem(sys.modules, "proxy_core", core)
    module = ModuleType("cap_runtime")
    exec(compile((LANE / "cap_tilt_algorithm.py").read_bytes(), "main.py", "exec"), module.__dict__)
    return module


class Symbol:
    def __init__(self, sid):
        self.id = self.value = sid


def setup(runtime, arm="tpr_on"):
    algo = runtime.TargetPriceCapTiltAlgorithm()
    algo._config = {"arm": arm, "cost": "baseline", "candidate_id": "synthetic", "slippage": "0.001"}
    algo.utc_time = datetime(2025, 1, 2, 14, 20)
    cutoff = runtime.core._clock(runtime.CUTOFFS[0])
    symbols = {sid: Symbol(sid) for sid in ("A", "B", "C", "D")}
    members = [{"symbol": symbol, "ticker": sid, "weight": None} for sid, symbol in symbols.items()]
    algo._snapshots = {etf: [{"members": members, "effective": cutoff-timedelta(days=8),
                              "received": cutoff-timedelta(days=1)}] for etf in runtime.ETFS}
    algo._cap_snapshots = [{"effective": cutoff.replace(hour=5), "asof": cutoff.replace(hour=5)-timedelta(days=1),
                            "received": cutoff.replace(hour=6),
                            "caps": {sid: {"state": "available", "value": str(100-i)}
                                     for i, sid in enumerate(symbols)}}]
    algo._identities = {sid: {"ticker": sid, "eligible": True} for sid in symbols}
    algo._frames = {runtime.DECISIONS[0]: {"states": [
        {"security_id": sid, "state": "scored", "score": str(i-2)}
        for i, sid in enumerate(symbols)]}}
    algo._decision_coverage, algo._targets, algo._symbols = {}, {}, symbols
    algo._target_weights, algo._ever_targeted_ids, algo._delisted_ids = {}, set(), set()
    algo._reasons = {}
    algo._reason = lambda key: algo._reasons.__setitem__(key, algo._reasons.get(key, 0)+1)
    return algo


def test_selection_same_with_signs_missing_and_disabled(runtime):
    algo = setup(runtime)
    algo._prepare_targets(runtime.DECISIONS[0])
    import json
    assert len("MATCHED_COVERAGE " + json.dumps(algo._decision_coverage[runtime.DECISIONS[0]], sort_keys=True, separators=(",", ":"))) <= 16384
    selected = set(algo._targets)
    hashes = {etf: row["selected_ids_hash"] for etf, row in algo._decision_coverage[runtime.DECISIONS[0]]["sleeves"].items()}
    for row in algo._frames[runtime.DECISIONS[0]]["states"]:
        row["state"], row["score"] = "unknown_input", None
    algo._prepare_targets(runtime.DECISIONS[0])
    assert set(algo._targets) == selected
    assert all(row["score_state_counts"]["unknown"] == 4 for row in algo._decision_coverage[runtime.DECISIONS[0]]["sleeves"].values())
    assert hashes == {etf: row["selected_ids_hash"] for etf, row in algo._decision_coverage[runtime.DECISIONS[0]]["sleeves"].items()}
    class Forbidden(dict):
        def items(self):
            raise AssertionError("OFF read signal")
        def __getitem__(self, key):
            raise AssertionError("OFF read frame")
    algo._config["arm"] = "tpr_off"
    algo._identities, algo._frames = Forbidden(), Forbidden()
    algo._prepare_targets(runtime.DECISIONS[0])
    assert set(algo._targets) == selected
    assert all(row["score_state_counts"] == {"not_used": 4} for row in algo._decision_coverage[runtime.DECISIONS[0]]["sleeves"].values())


@pytest.mark.parametrize("state", ["missing", "unknown", "invalid", "nonpositive"])
def test_unavailable_caps_explicit_and_cash_not_replaced(runtime, state):
    algo = setup(runtime)
    algo._cap_snapshots[0]["caps"]["A"] = {"state": state, "value": None}
    algo._prepare_targets(runtime.DECISIONS[0])
    assert "A" not in algo._targets
    row = algo._decision_coverage[runtime.DECISIONS[0]]["sleeves"]["SPY"]
    assert row["cap_state_counts"][state] == 1 and row["selected_count"] == 3
    assert row["unfilled_slots"] == 7 and row["etf_fallback"] is False
    assert Fraction(algo._decision_coverage[runtime.DECISIONS[0]]["target_gross"]) == Fraction(3, 10)


@pytest.mark.parametrize("change", ["today", "stale", "late_receipt", "future_effective"])
def test_cap_cutoff_refusal(runtime, change):
    algo = setup(runtime)
    row, cutoff = algo._cap_snapshots[0], runtime.core._clock(runtime.CUTOFFS[0])
    if change == "today":
        row["effective"] = cutoff+timedelta(days=2)
    elif change == "stale":
        row["effective"] -= timedelta(days=1)
    elif change == "late_receipt":
        row["received"] = cutoff+timedelta(seconds=1)
    else:
        row["effective"] = cutoff+timedelta(seconds=1)
    algo._prepare_targets(runtime.DECISIONS[0])
    assert algo._decision_coverage[runtime.DECISIONS[0]] is None
    assert algo._reasons == {"missing_prior_cap_snapshot": 1}


def cap_callback(runtime):
    algo = setup(runtime)
    algo._cap_context_symbol = Symbol("CAP-CONTEXT")
    config = NS(symbol=algo._cap_context_symbol, is_internal_feed=True, resolution="daily",
                exchange_time_zone=NS(id="America/New_York"),
                type=NS(FullName="QuantConnect.Data.Fundamental.FundamentalUniverse"))
    algo.subscription_manager = NS(subscription_data_config_service=NS(get_subscription_data_configs=lambda *a: [config]))
    algo._cap_snapshots, algo._cap_callback_count = [], 0
    algo.utc_time = datetime(2024, 12, 31, 6)
    row = NS(symbol=algo._symbols["A"], time=datetime(2024, 12, 30),
             end_time=datetime(2024, 12, 31), market_cap=123)
    return algo, row, config


def test_native_cap_clocks_known_zone_and_ignored_unrelated_rows(runtime):
    algo, row, _ = cap_callback(runtime)
    other = NS(symbol=Symbol("UNRELATED"), time=None, end_time=None, market_cap=None)
    assert algo._capture_caps([row, other]) == []
    snapshot = algo._cap_snapshots[0]
    assert snapshot["effective"] == datetime(2024, 12, 31, 5, tzinfo=timezone.utc)
    assert snapshot["asof"] == datetime(2024, 12, 30, 5, tzinfo=timezone.utc)
    assert snapshot["caps"] == {"A": {"state": "available", "value": "123"}}


@pytest.mark.parametrize("field,value", [("is_internal_feed", False), ("resolution", "minute"),
    ("exchange_time_zone", NS(id="UTC")), ("type", NS(FullName="Unknown"))])
def test_cap_context_is_exact_not_heuristic(runtime, field, value):
    algo, row, config = cap_callback(runtime)
    setattr(config, field, value)
    with pytest.raises(ValueError, match="context clock"):
        algo._capture_caps([row])
    assert not algo._cap_snapshots


@pytest.mark.parametrize("raw,state", [(None, "missing"), ("NaN", "invalid"), ("0", "nonpositive"),
                                      ("-1", "nonpositive"), ("10.25", "available")])
def test_cap_values_not_zero_coerced(runtime, raw, state):
    algo, row, _ = cap_callback(runtime)
    row.market_cap = raw
    algo._capture_caps([row])
    assert algo._cap_snapshots[0]["caps"]["A"]["state"] == state


def observer_setup(runtime, monkeypatch):
    algo = setup(runtime)
    algo.utc_time = datetime(2025, 1, 2, 5)
    algo.is_warming_up = False
    algo._ever_filled_ids, algo._fill_history_unknown = set(), False
    algo._event_zones = {"A": "America/New_York"}
    algo._delisting_audit = cap_observer.empty_audit()
    symbol = algo._symbols["A"]
    algo.portfolio = {symbol: NS(quantity=0)}
    algo.transactions = NS(get_orders=lambda: [], get_open_orders=lambda: [])
    event = runtime.Delisting()
    event.symbol, event.type, event.time, event.ticket = symbol, runtime.DelistingType.WARNING, datetime(2025, 1, 2), None
    data = NS(bars={}, splits={}, dividends={}, delistings={"A": event})
    calls = []
    monkeypatch.setattr(runtime.core.TargetPriceSixUniverseAlgorithm, "on_data", lambda self, data: calls.append("parent"))
    return algo, event, data, calls


def test_new_ambient_qualifier_retains_original_parent_and_diagnostic(runtime, monkeypatch):
    algo, event, data, calls = observer_setup(runtime, monkeypatch)
    algo.on_data(data)
    assert calls == ["parent"] and algo._reasons["delisting_event"] == 1
    assert algo._delisting_audit["ambient"] == 1
    assert cap_observer.validate_audit(algo._delisting_audit, 1)


@pytest.mark.parametrize("mode", ["unknown_zone", "bad_type", "native_ticket", "held_before",
    "held_after", "historical_order", "new_parent_order", "parent_ticket", "target_history", "filled_history",
    "history_failure", "receipt_inside", "event_inside", "fill_unknown"])
def test_observer_refuses_unknown_and_nonambient(runtime, monkeypatch, mode):
    algo, event, data, calls = observer_setup(runtime, monkeypatch)
    if mode == "unknown_zone":
        algo._event_zones = {}
    elif mode == "bad_type":
        event.type = "warning"
    elif mode == "native_ticket":
        event.ticket = object()
    elif mode == "parent_ticket":
        monkeypatch.setattr(runtime.core.TargetPriceSixUniverseAlgorithm, "on_data",
            lambda self, data: setattr(event, "ticket", object()))
    elif mode == "held_before":
        algo.portfolio[event.symbol].quantity = 1
    elif mode == "held_after":
        monkeypatch.setattr(runtime.core.TargetPriceSixUniverseAlgorithm, "on_data",
            lambda self, data: setattr(self.portfolio[event.symbol], "quantity", 1))
    elif mode in ("historical_order", "new_parent_order"):
        order = runtime.Order()
        order.symbol = event.symbol
        if mode == "historical_order":
            algo.transactions.get_orders = lambda: [order]
        else:
            monkeypatch.setattr(runtime.core.TargetPriceSixUniverseAlgorithm, "on_data",
                lambda self, data: setattr(self.transactions, "get_orders", lambda: [order]))
    elif mode == "target_history":
        algo._ever_targeted_ids.add("A")
    elif mode == "filled_history":
        algo._ever_filled_ids.add("A")
    elif mode == "history_failure":
        def fail():
            raise RuntimeError("synthetic")
        algo.transactions.get_orders = fail
    elif mode == "receipt_inside":
        algo.utc_time = datetime(2025, 1, 2, 14, 20)
    elif mode == "event_inside":
        event.time = datetime(2025, 1, 2, 9, 35)
    else:
        algo._fill_history_unknown = True
    algo.on_data(data)
    assert not cap_observer.validate_audit(algo._delisting_audit, 1)


def test_parent_failure_not_swallowed(runtime, monkeypatch):
    algo, event, data, _ = observer_setup(runtime, monkeypatch)
    def fail(self, data):
        raise RuntimeError("parent")
    monkeypatch.setattr(runtime.core.TargetPriceSixUniverseAlgorithm, "on_data", fail)
    with pytest.raises(RuntimeError, match="parent"):
        algo.on_data(data)


def test_partial_fill_and_unknown_do_not_skip_original_handler(runtime, monkeypatch):
    algo, _, _, calls = observer_setup(runtime, monkeypatch)
    monkeypatch.setattr(runtime.core.TargetPriceSixUniverseAlgorithm, "on_order_event",
                        lambda self, event: calls.append("order-parent"))
    event = runtime.OrderEvent()
    event.symbol, event.fill_quantity, event.status = algo._symbols["A"], "1", "partially_filled"
    algo.on_order_event(event)
    assert algo._ever_filled_ids == {"A"} and not algo._fill_history_unknown
    event.fill_quantity = "NaN"
    algo.on_order_event(event)
    assert algo._fill_history_unknown and calls == ["order-parent", "order-parent"]


def test_live_refused_before_any_config_or_api(runtime):
    algo = runtime.TargetPriceCapTiltAlgorithm()
    algo.live_mode = True
    with pytest.raises(ValueError, match="live refused"):
        algo.initialize()


def test_off_initialization_never_reads_packet_registers_seven_contexts(runtime, monkeypatch):
    algo = runtime.TargetPriceCapTiltAlgorithm()
    algo.live_mode = False
    import hashlib, json
    config = {"schema": "tpr-qc-cap-tilt-config-v1", "study_id": runtime.STUDY,
              "freeze_sha256": "a"*64, "candidate_id": "TPR-CAP-TILT-OFF-BASE-v1",
              "arm": "tpr_off", "cost": "baseline", "slippage": "0.001"}
    raw = json.dumps(config)
    runtime.EXPECTED_MATCHED_CONFIG_SHA256 = hashlib.sha256(raw.encode()).hexdigest()
    runtime.EXPECTED_MATCHED_FREEZE_SHA256 = "a"*64
    module = ModuleType("matched_config")
    module.CONFIG_JSON = raw
    monkeypatch.setitem(sys.modules, "matched_config", module)
    monkeypatch.delitem(sys.modules, "signal_packet", raising=False)
    def forbidden(*a, **kw):
        raise AssertionError("OFF touched original signal initializer or packet")
    monkeypatch.setattr(runtime.core.TargetPriceSixUniverseAlgorithm, "initialize", forbidden)
    algo.object_store = NS(contains_key=forbidden, read=forbidden)
    for name in ("set_start_date", "set_end_date", "set_time_zone", "set_account_currency",
                 "set_cash", "add_security_initializer", "set_benchmark", "set_warm_up"):
        setattr(algo, name, lambda *a, **kw: None)
    algo.universe_settings = NS()
    algo.universe = NS(etf=lambda symbol, **kw: NS(symbol=Symbol("CONTEXT-"+symbol.id)))
    algo.add_equity = lambda etf, resolution, **kw: NS(symbol=Symbol(etf))
    registered = []
    def add_universe(universe):
        if callable(universe):
            result = NS(symbol=Symbol("CAP-CONTEXT"))
        else:
            assert universe.symbol in algo._context_symbols
            result = universe
        registered.append(result.symbol)
        return result
    algo.add_universe = add_universe
    algo.schedule, algo.date_rules, algo.time_rules = NS(on=lambda *a: None), NS(every_day=lambda *a: None), NS(at=lambda *a: None)
    algo.initialize()
    assert len(registered) == len(algo._context_symbols) == 7
    assert set(registered) == algo._context_symbols
    assert algo._identities == algo._frames == {}
    assert algo._cap_context_symbol in algo._context_symbols


def test_known_delisted_name_not_replaced_or_renormalized(runtime):
    algo = setup(runtime, "tpr_off")
    algo._delisted_ids = {"A"}
    algo._prepare_targets(runtime.DECISIONS[0])
    assert "A" not in algo._targets and algo._reasons["delisting_target_refused"] == 1
    assert sum(algo._target_weights.values()) == Fraction(3, 10)


def test_rebalance_captures_common_selected_mark_hash_and_prices_matter(runtime):
    import json
    def run(arm, price):
        algo = setup(runtime, arm)
        algo.time, algo.is_warming_up = datetime(2025, 1, 2, 9, 20), False
        algo._attempted_days, algo._decision_count, algo._refused_count = set(), 0, 0
        algo._sleeve_selected_decisions = {etf: 0 for etf in runtime.ETFS}
        algo._prior_close_nav, algo._prior_close_day = Fraction(100000), None
        algo._requested_shares = algo._submitted_shares = algo._submitted = 0
        algo._tickets, algo.logs = [], []
        class Portfolio(dict):
            cash = 100000
        algo.portfolio = Portfolio({symbol: NS(symbol=symbol, invested=False, quantity=0)
                                    for symbol in algo._symbols.values()})
        algo._prior_mark = lambda symbol: (Fraction(price), Fraction(100000))
        algo._assert_raw_subscriptions = lambda symbol: None
        algo.market_on_open_order = lambda *a, **kw: object()
        algo.log = algo.logs.append
        algo._rebalance()
        assert algo._refused_count == 0 and algo._submitted > 0
        assert len(algo.logs) == 1 and len(algo.logs[0]) <= 16384
        return json.loads(algo.logs[0].split("MATCHED_COVERAGE ", 1)[1])
    first, control, altered = run("tpr_on", 50), run("tpr_off", 50), run("tpr_off", 51)
    assert first["prior_mark_session"] == "2024-12-31"
    assert first["prior_mark_inputs_sha256"] == control["prior_mark_inputs_sha256"]
    assert first["prior_mark_inputs_sha256"] != altered["prior_mark_inputs_sha256"]
