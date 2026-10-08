"""Synthetic successor proofs; executed v1 remains an immutable red control."""
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
import ast
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
LANE = ROOT / "research/target_price_revisions_qc"
V1_SHA = "3fa48df5b7d52d40bae38d0ce6e52a7b4a485550b136470a5e91628f422a4d0f"


@pytest.fixture
def modules(monkeypatch):
    api = ModuleType("AlgorithmImports")
    api.FeeModel = type("FeeModel", (), {})
    api.QCAlgorithm = type("QCAlgorithm", (), {})
    api.SplitType = SimpleNamespace(SPLIT_OCCURRED="occurred")
    api.OrderStatus = SimpleNamespace(INVALID="invalid", CANCELED="canceled")
    api.Universe = SimpleNamespace(UNCHANGED="unchanged")
    api.Resolution = SimpleNamespace(MINUTE="minute", DAILY="daily")
    api.TickType = SimpleNamespace(TRADE="trade", QUOTE="quote")
    api.DataNormalizationMode = SimpleNamespace(RAW=0, ADJUSTED=1)
    api.TradeBar = type("TradeBar", (), {})
    monkeypatch.setitem(sys.modules, "AlgorithmImports", api)
    result = []
    for filename in ("cloud_algorithm.py", "cloud_algorithm_v2.py"):
        module = ModuleType(filename.removesuffix(".py"))
        path = LANE / filename
        exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
        result.append(module)
    return result


class Symbol:
    def __init__(self, identifier="synthetic-id", value="SYNTH"):
        self.id, self.value = identifier, value


def config(mode=0, internal=False, resolution="minute", tick="trade"):
    return SimpleNamespace(data_normalization_mode=mode, is_internal_feed=internal,
                           resolution=resolution, tick_type=tick)


class Security:
    def __init__(self, symbol, subscriptions=None):
        self.symbol = symbol
        self.subscriptions = [config()] if subscriptions is None else subscriptions
        self.has_data = True

    @property
    def data_normalization_mode(self):
        return self.subscriptions[0].data_normalization_mode if self.subscriptions else 1

    def set_data_normalization_mode(self, mode):
        for subscription in self.subscriptions:
            subscription.data_normalization_mode = mode

    def get_last_data(self):
        return SimpleNamespace(price="20")


def algorithm(module):
    algo = module.TargetPriceSixUniverseAlgorithm()
    algo.live_mode, algo.is_warming_up = False, False
    algo.time, algo.utc_time = datetime(2025, 1, 2, 9, 20), datetime(2025, 1, 2, 14, 20)
    algo._frames = {"2025-01-02": {"cutoff_utc": "2024-12-31T23:00:00+00:00"}}
    algo._config = {"candidate_id": "TPR-QC6-SPY-v1"}
    algo._attempted_days, algo._reasons = set(), {}
    algo._decision_count = algo._refused_count = 0
    algo._targets, algo._symbols, algo._snapshots, algo._decision_coverage = {}, {}, [], {}
    algo._manual_symbols, algo._valuation_days = set(), set()
    algo._cash_ledger, algo._quantity_ledger, algo._dividend_keys = Fraction(100000), {}, set()
    algo._prior_close_nav, algo._prior_close_day = Fraction(100000), None
    algo._fees, algo._fill_events, algo._submitted = Fraction(0), 0, 0
    algo._requested_shares = algo._submitted_shares = algo._filled_shares = 0
    algo._max_cash_residual = algo._max_nav_residual = Fraction(0)
    algo._position_ledger_mismatches = 0
    algo._split_factors, algo._tickets, algo.securities = {}, [], {}
    algo.subscription_manager = SimpleNamespace(subscription_data_config_service=SimpleNamespace(
        get_subscription_data_configs=lambda symbol, include_internal: list(algo.securities[symbol].subscriptions)))
    algo.portfolio = SimpleNamespace(cash="100000", total_portfolio_value="100000",
                                    total_holdings_value="0", values=lambda: [])
    algo.logs, algo.orders, algo.add_calls = [], [], []
    algo.log = algo.logs.append
    algo.market_on_open_order = lambda symbol, quantity, **kwargs: algo.orders.append((symbol, quantity)) or "ticket"
    def add_security(symbol, resolution, **kwargs):
        algo.add_calls.append((symbol, resolution, kwargs))
        security = algo.securities.get(symbol)
        if security is None:
            security = Security(symbol)
            algo.securities[symbol] = security
        elif not security.subscriptions:
            security.subscriptions.append(config())
        return security
    algo.add_security = add_security
    class History:
        def __getitem__(self, kind):
            def history(symbol, count, resolution):
                assert algo.securities[symbol].data_normalization_mode == 0
                return [SimpleNamespace(time=datetime(2024, 12, 31, 9, 30),
                    end_time=datetime(2024, 12, 31, 16), close="100", volume="100000")]
            return history
    algo.history = History()
    return algo


def with_selected(algo, symbol):
    algo._symbols = {"A": symbol}
    algo._targets = {"A": symbol}
    algo._decision_coverage["2025-01-02"] = {"synthetic": True}
    algo._prepare_targets = lambda day: None


def summary(algo):
    algo.on_end_of_algorithm()
    return json.loads(algo.logs[-1].split(" ", 1)[1])


def complete_evidence(algo, module):
    algo._attempted_days = set(module.DECISIONS)
    algo._decision_count, algo._fill_events = 14, 1
    start = date(2025, 1, 2)
    holidays = {"2025-01-09", "2025-01-20", "2025-02-17"}
    algo._valuation_days = {(start + timedelta(days=offset)).isoformat() for offset in range(89)
        if (start + timedelta(days=offset)).weekday() < 5
        and (start + timedelta(days=offset)).isoformat() not in holidays}
    assert len(algo._valuation_days) == 60
    algo._prior_close_day = date(2025, 3, 31)
    algo.time, algo.utc_time = datetime(2025, 4, 1), datetime(2025, 4, 1, 4)


def test_executed_v1_bytes_remain_frozen(modules):
    assert hashlib.sha256((LANE / "cloud_algorithm.py").read_bytes()).hexdigest() == V1_SHA


def test_pure_signals_ranking_economics_and_prior_mark_rule_are_unchanged(modules):
    names = {"validate_inputs", "select_snapshot", "rank_members", "plan_orders",
             "_prior_mark", "_prepare_targets", "_initialize_security", "get_order_fee"}
    trees = [ast.parse((LANE / filename).read_text()) for filename in
             ("cloud_algorithm.py", "cloud_algorithm_v2.py")]
    bodies = [{node.name: ast.dump(node) for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef) and node.name in names} for tree in trees]
    assert bodies[0] == bodies[1] and set(bodies[0]) == names
    for constant in ("CASES", "DECISIONS", "CUTOFFS", "EXPECTED_FREEZE_SHA256", "FROZEN_SOURCE_HASHES"):
        assert getattr(modules[0], constant) == getattr(modules[1], constant)


def test_live_guard_runs_before_input_or_any_api_access(modules):
    for module in modules:
        algo = module.TargetPriceSixUniverseAlgorithm()
        algo.live_mode = True
        with pytest.raises(ValueError, match="live mode refused"):
            algo.initialize()


def test_midnight_callback_then_preopen_missing_security_red_green(modules):
    symbol = Symbol()
    for index, module in enumerate(modules):
        algo = algorithm(module)
        algo.time, algo.utc_time = datetime(2025, 1, 1, 19), datetime(2025, 1, 2)
        algo._identities = {"A": {"security_id": "A", "ticker": "SYNTH", "eligible": True}}
        algo._frames["2025-01-02"]["states"] = [{"security_id": "A", "state": "scored", "score": "1"}]
        old = datetime(2024, 12, 24, tzinfo=timezone.utc)
        algo._snapshots = [{"effective": old, "received": old,
                           "members": [{"ticker": "SYNTH", "weight": "1", "symbol": symbol}]}]
        rows = [SimpleNamespace(symbol=symbol, weight="1", end_time=datetime(2025, 1, 2))]
        # UTC Jan2 callback sees NY Jan1; no Jan2 trade subscription yet.
        assert algo._constituents(rows) == []
        algo.time, algo.utc_time = datetime(2025, 1, 2, 9, 20), datetime(2025, 1, 2, 14, 20)
        algo._rebalance()
        assert algo._targets == {"A": symbol}
        if index == 0:
            assert not algo.orders
            assert algo._reasons == {"missing_security_subscription": 1, "missing_mark": 1}
        else:
            assert algo.orders == [(symbol, 100)]
            assert algo.add_calls[0][0] is symbol
            assert algo.add_calls[0][2]["data_normalization_mode"] == 0
            assert algo._manual_symbols == {"synthetic-id"}
            assert not algo._reasons.get("missing_mark", 0)


def test_retired_security_is_reactivated_even_if_manager_key_exists(modules):
    algo = algorithm(modules[1])
    symbol = Symbol()
    retired = Security(symbol, [])
    algo.securities[symbol] = retired
    with_selected(algo, symbol)
    assert retired.data_normalization_mode == 1
    algo._rebalance()
    assert algo.orders == [(symbol, 100)]
    assert algo.add_calls[0][0] is symbol
    assert retired.data_normalization_mode == 0


@pytest.mark.parametrize("subscriptions", [
    [], [config(internal=True)], [config(resolution="daily")],
    [config(tick="quote")], [config(mode=1)], [config(), config(mode=1, internal=True)],
])
def test_current_config_guard_refuses_missing_or_nonraw_configs(modules, subscriptions):
    algo, symbol = algorithm(modules[1]), Symbol()
    algo.securities[symbol] = Security(symbol, subscriptions)
    with pytest.raises(ValueError, match="RAW minute"):
        algo._assert_raw_subscriptions(symbol)
    algo.securities[symbol] = Security(symbol)
    assert algo._assert_raw_subscriptions(symbol) is algo.securities[symbol]


def test_failed_reactivation_cannot_be_hidden_by_empty_initializer_setter(modules):
    algo, symbol = algorithm(modules[1]), Symbol()
    algo.securities[symbol] = Security(symbol, [])
    algo.add_security = lambda *args, **kwargs: algo.securities[symbol]
    with pytest.raises(ValueError, match="RAW minute"):
        algo._ensure_raw_subscription(symbol)
    assert not algo._manual_symbols


def test_stale_security_bag_cannot_hide_missing_current_registry(modules):
    algo, symbol = algorithm(modules[1]), Symbol()
    algo.securities[symbol] = Security(symbol)
    algo.subscription_manager.subscription_data_config_service.get_subscription_data_configs = lambda *args: []
    with pytest.raises(ValueError, match="RAW minute"):
        algo._assert_raw_subscriptions(symbol)


def test_current_internal_adjusted_config_cannot_be_hidden_from_guard(modules):
    algo, symbol = algorithm(modules[1]), Symbol()
    algo.securities[symbol] = Security(symbol)
    def registered(queried_symbol, include_internal):
        assert queried_symbol is symbol and include_internal is True
        return [config(), config(mode=1, internal=True)]
    algo.subscription_manager.subscription_data_config_service.get_subscription_data_configs = registered
    with pytest.raises(ValueError, match="RAW minute"):
        algo._assert_raw_subscriptions(symbol)


def test_typed_subscription_refuses_remapped_identity_and_maximum_excess(modules):
    algo, symbol = algorithm(modules[1]), Symbol()
    algo.add_security = lambda *args, **kwargs: Security(Symbol("wrong-id", "SYNTH"))
    with pytest.raises(ValueError, match="identity"):
        algo._ensure_raw_subscription(symbol)
    algo = algorithm(modules[1])
    algo._manual_symbols = {str(number) for number in range(140)}
    with pytest.raises(ValueError, match="bound"):
        algo._ensure_raw_subscription(symbol)
    assert not algo.add_calls
    existing = Symbol("0")
    algo._ensure_raw_subscription(existing)
    assert len(algo._manual_symbols) == 140


def test_held_and_selected_symbols_are_explicitly_subscribed_each_decision(modules):
    algo, selected, held = algorithm(modules[1]), Symbol("selected"), Symbol("held")
    with_selected(algo, selected)
    algo._symbols["H"] = held
    algo.portfolio.values = lambda: [SimpleNamespace(symbol=held, invested=True, quantity=10)]
    # First-session existing holdings are intentionally refused by the NAV rule,
    # but both subscriptions must be established before any price/order path.
    algo._rebalance()
    assert {str(call[0].id) for call in algo.add_calls} == {"selected", "held"}
    assert algo._reasons["missing_prior_close_nav"] == 1


def test_adjusted_dividend_cash_mismatch_red_then_current_raw_refusal(modules):
    symbol = Symbol()
    for index, module in enumerate(modules):
        algo = algorithm(module)
        algo._quantity_ledger[symbol.id] = Fraction(42)
        algo.securities[symbol] = Security(symbol, [config(mode=1)])
        data = SimpleNamespace(dividends={"d": SimpleNamespace(symbol=symbol, distribution=".75")}, splits={})
        if index == 0:
            algo.on_data(data)
            assert algo._cash_ledger - 100000 == Fraction("31.5")
        else:
            with pytest.raises(ValueError, match="RAW minute"):
                algo.on_data(data)
            assert algo._cash_ledger == 100000


def test_compound_raw_actions_and_cash_in_lieu_preserve_accounting(modules):
    algo, symbol = algorithm(modules[1]), Symbol()
    algo.securities[symbol] = Security(symbol)
    algo._quantity_ledger[symbol.id] = Fraction(3)
    dividend = SimpleNamespace(symbol=symbol, distribution=".2")
    split = SimpleNamespace(symbol=symbol, type="occurred", split_factor="2", reference_price="10")
    algo.on_data(SimpleNamespace(dividends={"d": dividend}, splits={"s": split}))
    assert algo._cash_ledger == Fraction("100010.6")
    assert algo._quantity_ledger[symbol.id] == 1


def test_nonraw_split_fill_and_daily_audit_refuse(modules):
    module, symbol = modules[1], Symbol()
    for operation in ("split", "fill", "audit"):
        algo = algorithm(module)
        algo.securities[symbol] = Security(symbol, [config(mode=1)])
        algo._quantity_ledger[symbol.id] = Fraction(2)
        algo.portfolio.values = lambda: [SimpleNamespace(symbol=symbol, invested=True, quantity=2)]
        with pytest.raises(ValueError, match="RAW minute"):
            if operation == "split":
                algo.on_data(SimpleNamespace(dividends={}, splits={"s": SimpleNamespace(
                    symbol=symbol, type="occurred", split_factor=".5")}))
            elif operation == "fill":
                algo.on_order_event(SimpleNamespace(fill_quantity=1, fill_price=100, symbol=symbol,
                    order_fee=SimpleNamespace(value=SimpleNamespace(amount=".01")), status="filled"))
            else:
                algo._daily_audit()
                pytest.fail("expected RAW refusal")
        if operation == "audit":
            assert not algo._valuation_days


def test_last_valuation_is_not_relabelled_april_first_red_green(modules):
    for index, module in enumerate(modules):
        algo = algorithm(module)
        complete_evidence(algo, module)
        result = summary(algo)
        nav_logs = [line for line in algo.logs if line.startswith("TPR_NAV ")]
        if index == 0:
            assert json.loads(nav_logs[-1].split(" ", 1)[1])["session"] == "2025-04-01"
        else:
            assert not nav_logs
            assert result["last_valuation_session"] == "2025-03-31"
            assert result["engine_end_utc"] == "2025-04-01T04:00:00+00:00"
            assert result["valuation_days"] == 60
            assert result["meaningful_execution"] is True


def test_daily_audits_deduplicate_and_refuse_outside_window(modules):
    algo = algorithm(modules[1])
    algo.time = datetime(2025, 1, 2, 16, 1)
    algo._daily_audit()
    algo._daily_audit()
    algo.time = datetime(2025, 4, 1, 16, 1)
    algo._daily_audit()
    assert algo._valuation_days == {"2025-01-02"}
    assert len(algo.logs) == 1


@pytest.mark.parametrize("reason", ["missing_mark", "missing_security_subscription", "unpriced_held_nav"])
def test_any_missing_selected_execution_input_blocks_meaningful_label(modules, reason):
    algo = algorithm(modules[1])
    complete_evidence(algo, modules[1])
    assert summary(algo)["meaningful_execution"] is True
    algo._reasons[reason] = 1
    assert summary(algo)["meaningful_execution"] is False


@pytest.mark.parametrize("fault", ["cash", "nav", "positions", "decision_dates", "valuation_dates", "last_valuation", "fills"])
def test_other_incomplete_evidence_cannot_claim_success(modules, fault):
    algo = algorithm(modules[1])
    complete_evidence(algo, modules[1])
    if fault == "cash":
        algo._max_cash_residual = Fraction("0.02")
    elif fault == "nav":
        algo._max_nav_residual = Fraction("0.02")
    elif fault == "positions":
        algo._position_ledger_mismatches = 1
    elif fault == "decision_dates":
        algo._attempted_days.remove(modules[1].DECISIONS[0])
        algo._attempted_days.add("2025-01-03")
    elif fault == "valuation_dates":
        algo._valuation_days.remove("2025-03-31")
    elif fault == "last_valuation":
        algo._prior_close_day = date(2025, 3, 28)
    else:
        algo._fill_events = 0
    assert summary(algo)["meaningful_execution"] is False


def test_signal_cutoff_at_or_after_the_decision_clock_is_refused_before_membership(modules, monkeypatch):
    """TPR-CR21-005: behavioural proof of the look-ahead guard. A frame
    whose cutoff equals or follows the 09:20 engine clock must refuse before any
    membership is read; one second earlier reaches membership selection and,
    with no snapshot, records missing coverage without issuing an order."""
    for module in modules:
        algo = algorithm(module)
        membership_reads = []
        original_select = module.select_snapshot
        def observed_selection(snapshots, cutoff, original=original_select):
            membership_reads.append((snapshots, cutoff))
            return original(snapshots, cutoff)
        monkeypatch.setattr(module, "select_snapshot", observed_selection)
        for cutoff in ("2025-01-02T14:20:00+00:00", "2025-01-02T14:20:01+00:00"):
            algo._frames["2025-01-02"]["cutoff_utc"] = cutoff
            with pytest.raises(ValueError, match="not yet available"):
                algo._prepare_targets("2025-01-02")
            assert membership_reads == [] and algo._decision_coverage == {}
        algo._frames["2025-01-02"]["cutoff_utc"] = "2025-01-02T14:19:59+00:00"
        algo._prepare_targets("2025-01-02")
        assert membership_reads == [(algo._snapshots, datetime(2025, 1, 2, 14, 19, 59, tzinfo=timezone.utc))]
        assert algo._decision_coverage["2025-01-02"] is None and algo.orders == []


def test_plan_orders_lists_every_sell_before_any_buy_regardless_of_identity_order(modules):
    """TPR-CR21-005: sells precede buys even when the buy identity sorts first."""
    for module in modules:
        orders = module.plan_orders({"A"}, {"Z": 10}, {"A": ("50", "100000"), "Z": ("100", "100000")}, "100000", "1000")
        submitted = [(row["security_id"], row["submitted"]) for row in orders if row["submitted"]]
        assert submitted == [("Z", -10), ("A", 19)]


def test_meaningful_execution_requires_exactly_sixty_valuation_days(modules):
    """TPR-CR21-005: a missing mid-window valuation day, with 2025-03-31 still
    present, cannot be labelled a complete run."""
    algo = algorithm(modules[1])
    complete_evidence(algo, modules[1])
    assert summary(algo)["meaningful_execution"] is True
    algo._valuation_days.remove("2025-02-03")
    assert summary(algo)["meaningful_execution"] is False
    algo._valuation_days.update({"2025-02-03", "2025-01-09"})
    assert summary(algo)["meaningful_execution"] is False
