"""Synthetic native-final-fill boundary proofs; no cloud/provider/operator I/O.

The executed v1 runtime and tests stay immutable. These tests exercise the
successor's narrowly scoped legacy-scalar compatibility exception, not a
general non-RAW feed exception or a delisting outcome-acceptance rule.
"""
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import hashlib
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
    api.SplitType = NS(SPLIT_OCCURRED=object())
    api.OrderStatus = NS(FILLED=object(), PARTIALLY_FILLED=object(), INVALID=object(), CANCELED=object())
    api.OrderType = NS(MARKET=object(), MARKET_ON_OPEN=object())
    api.Universe = NS(UNCHANGED=object())
    api.Resolution = NS(MINUTE="minute", DAILY="daily", HOUR="hour")
    api.TickType = NS(TRADE="trade", QUOTE="quote")
    api.DataNormalizationMode = NS(RAW=0, ADJUSTED=1)
    api.Currencies = NS(NullCurrency="QCC")
    api.SecurityType = NS(EQUITY="equity", BASE="base")
    api.TradeBar = type("TradeBar", (), {})
    api.Order = type("Order", (), {})
    api.MarketOrder = type("MarketOrder", (api.Order,), {})
    for name in ("OrderEvent", "Delisting", "Slice"):
        setattr(api, name, type(name, (), {}))
    api.DelistingType = NS(WARNING=object(), DELISTED=object())
    monkeypatch.setitem(sys.modules, "AlgorithmImports", api)
    monkeypatch.setitem(sys.modules, "cap_tilt", cap_tilt)
    monkeypatch.setitem(sys.modules, "cap_observer", cap_observer)
    core = ModuleType("proxy_core")
    exec(compile((LANE / "cloud_algorithm_v2.py").read_bytes(), "proxy_core.py", "exec"), core.__dict__)
    monkeypatch.setitem(sys.modules, "proxy_core", core)
    module = ModuleType("cap_runtime_v2")
    exec(compile((LANE / "cap_tilt_algorithm_v2.py").read_bytes(), "main.py", "exec"), module.__dict__)
    return module


class Symbol:
    def __init__(self, sid):
        self.id = self.value = sid


def native_final(runtime):
    """Native-shaped closed positive control, with real inherited accounting."""
    algo = runtime.TargetPriceCapTiltAlgorithm()
    symbol = Symbol("A")
    algo.time = datetime(2025, 2, 4, 19)
    algo.utc_time = datetime(2025, 2, 5)
    algo.live_mode = algo.is_warming_up = False
    algo._context_symbols = set()
    algo._symbols = {"A": symbol}
    algo._custody_since = {"A": datetime(2025, 1, 1, tzinfo=timezone.utc)}
    algo._event_zones = {"A": "America/New_York"}
    algo._native_final_fill_authority = None
    algo._native_final_delisting_compatibility_exceptions = 0
    algo._benchmark_internal_config_max = 0
    algo._ever_filled_ids, algo._ever_targeted_ids, algo._delisted_ids = set(), set(), set()
    algo._fill_history_unknown = False
    algo._delisting_audit = cap_observer.empty_audit()
    algo._targets, algo._target_weights = {}, {}
    algo._reasons, algo._dividend_keys, algo._split_factors = {}, set(), {}
    algo._reason = lambda key: algo._reasons.__setitem__(key, algo._reasons.get(key, 0) + 1)
    algo._quantity_ledger, algo._cash_ledger = {"A": Fraction(3)}, Fraction(100)
    algo._fees, algo._fill_events, algo._filled_shares = Fraction(0), 0, 0
    security = NS(symbol=symbol, is_delisted=True, is_tradable=False,
                  subscriptions=[], data_normalization_mode=runtime.DataNormalizationMode.ADJUSTED)
    algo.securities = {symbol: security}
    config = NS(symbol=symbol, is_internal_feed=False, resolution=runtime.Resolution.MINUTE,
        tick_type=runtime.TickType.TRADE, data_normalization_mode=runtime.DataNormalizationMode.RAW,
        type=NS(FullName="QuantConnect.Data.Market.TradeBar"), is_custom_data=False,
        fill_data_forward=True, exchange_time_zone=NS(id="America/New_York"))
    registry = [config]
    algo.subscription_manager = NS(subscription_data_config_service=NS(
        get_subscription_data_configs=lambda *args: list(registry)))
    algo.portfolio = {symbol: NS(symbol=symbol, quantity=0, invested=False)}
    order = runtime.MarketOrder()
    order.id, order.symbol, order.quantity = 7, symbol, "-3"
    order.type, order.status = runtime.OrderType.MARKET, runtime.OrderStatus.FILLED
    order.price_adjustment_mode, order.tag = runtime.DataNormalizationMode.RAW, "Liquidate from delisting"
    algo.transactions = NS(get_order_by_id=lambda identifier: order,
        get_orders=lambda: [order], get_open_orders=lambda: [])
    final = runtime.Delisting()
    final.symbol, final.type = symbol, runtime.DelistingType.DELISTED
    final.time, final.ticket = datetime(2025, 2, 5), None
    current = runtime.Slice()
    current.delistings, current.bars, current.splits, current.dividends = {symbol: final}, {}, {}, {}
    algo.current_slice = current
    event = runtime.OrderEvent()
    event.order_id, event.symbol = 7, symbol
    event.status, event.is_assignment = runtime.OrderStatus.FILLED, False
    event.utc_time, event.message = algo.utc_time, "Liquidate from delisting"
    event.fill_quantity, event.fill_price = "-3", "7.5"
    event.order_fee = NS(value=NS(amount="0", currency=runtime.Currencies.NullCurrency))
    return algo, symbol, security, config, registry, order, final, event


def test_executed_v1_runtime_and_test_harness_stay_immutable():
    assert hashlib.sha256((LANE / "cap_tilt_algorithm.py").read_bytes()).hexdigest() == "c8804b43b9a25b5fe1ce3f8b5fac424c129c9e7b39a4ad0480b3fbd98e98ab37"
    test_path = Path(__file__).with_name("test_qc_cap_tilt_algorithm.py")
    assert hashlib.sha256(test_path.read_bytes()).hexdigest() == "7bf1815f163bf5ff273adf4d02669a0ed0b8e3862ea8a86ddc3bd48651a10dad"


def test_native_final_full_liquidation_runs_unchanged_parent_accounting(runtime):
    algo, symbol, security, config, _, _, _, event = native_final(runtime)
    algo.on_order_event(event)
    assert algo._quantity_ledger == {"A": Fraction(0)}
    assert algo._cash_ledger == Fraction(245, 2)
    assert algo._fees == 0 and algo._fill_events == 1 and algo._filled_shares == 3
    assert algo._ever_filled_ids == {"A"} and not algo._fill_history_unknown
    assert algo._native_final_delisting_compatibility_exceptions == 1
    assert algo._native_final_fill_authority is None
    assert security.data_normalization_mode == runtime.DataNormalizationMode.ADJUSTED
    assert security.subscriptions == [] and config.data_normalization_mode == runtime.DataNormalizationMode.RAW
    assert config.resolution == runtime.Resolution.MINUTE


REFUSALS = (
    "untyped_event", "status_partial", "status_string", "assignment", "assignment_unknown",
    "stale_event", "message_missing", "message_substring", "context", "missing_security",
    "security_identity", "not_delisted", "delisted_unknown", "tradable", "tradable_unknown",
    "attached_config", "attached_unknown", "scalar_other", "fill_zero", "fill_positive",
    "fill_partial", "fill_fractional", "fill_nonfinite", "ledger_zero", "ledger_short",
    "ledger_fractional", "native_not_flat", "native_quantity_unknown", "price_zero", "price_unknown",
    "fee_nonzero", "fee_currency", "fee_usd", "fee_unknown", "custody_missing", "custody_naive", "custody_future",
    "history_missing", "history_untyped", "history_not_market", "history_id", "history_symbol",
    "history_status", "history_nonraw", "history_tag", "history_quantity", "history_failure",
    "slice_untyped", "slice_missing", "final_missing", "final_untyped", "final_warning",
    "final_symbol", "final_duplicate", "final_collection_unknown",
)


def refuse(mode, runtime, values):
    algo, symbol, security, config, registry, order, final, event = values
    other = Symbol("OTHER")
    if mode == "untyped_event": event = NS(**vars(event))
    elif mode == "status_partial": event.status = runtime.OrderStatus.PARTIALLY_FILLED
    elif mode == "status_string": event.status = "Filled"
    elif mode == "assignment": event.is_assignment = True
    elif mode == "assignment_unknown": del event.is_assignment
    elif mode == "stale_event": event.utc_time -= timedelta(seconds=1)
    elif mode == "message_missing": del event.message
    elif mode == "message_substring": event.message = "prefix Liquidate from delisting"
    elif mode == "context": algo._context_symbols.add(symbol)
    elif mode == "missing_security": algo.securities.clear()
    elif mode == "security_identity": security.symbol = other
    elif mode == "not_delisted": security.is_delisted = False
    elif mode == "delisted_unknown": security.is_delisted = None
    elif mode == "tradable": security.is_tradable = True
    elif mode == "tradable_unknown": del security.is_tradable
    elif mode == "attached_config": security.subscriptions = [config]
    elif mode == "attached_unknown": del security.subscriptions
    elif mode == "scalar_other": security.data_normalization_mode = 77
    elif mode == "fill_zero": event.fill_quantity = "0"
    elif mode == "fill_positive": event.fill_quantity = "3"
    elif mode == "fill_partial": event.fill_quantity = order.quantity = "-2"
    elif mode == "fill_fractional": event.fill_quantity = "-2.5"
    elif mode == "fill_nonfinite": event.fill_quantity = "NaN"
    elif mode == "ledger_zero": algo._quantity_ledger["A"] = Fraction(0)
    elif mode == "ledger_short": algo._quantity_ledger["A"] = Fraction(-3)
    elif mode == "ledger_fractional": algo._quantity_ledger["A"] = Fraction(5, 2)
    elif mode == "native_not_flat": algo.portfolio[symbol].quantity = 1
    elif mode == "native_quantity_unknown": algo.portfolio[symbol].quantity = None
    elif mode == "price_zero": event.fill_price = "0"
    elif mode == "price_unknown": event.fill_price = "NaN"
    elif mode == "fee_nonzero": event.order_fee.value.amount = "0.01"
    elif mode == "fee_currency": event.order_fee.value.currency = "EUR"
    elif mode == "fee_usd": event.order_fee.value.currency = "USD"
    elif mode == "fee_unknown": del event.order_fee
    elif mode == "custody_missing": algo._custody_since.clear()
    elif mode == "custody_naive": algo._custody_since["A"] = datetime(2025, 1, 1)
    elif mode == "custody_future": algo._custody_since["A"] = datetime(2025, 2, 6, tzinfo=timezone.utc)
    elif mode == "history_missing": algo.transactions.get_order_by_id = lambda identifier: None
    elif mode == "history_untyped": algo.transactions.get_order_by_id = lambda identifier: NS(**vars(order))
    elif mode == "history_not_market": order.type = runtime.OrderType.MARKET_ON_OPEN
    elif mode == "history_id": order.id = 8
    elif mode == "history_symbol": order.symbol = other
    elif mode == "history_status": order.status = runtime.OrderStatus.PARTIALLY_FILLED
    elif mode == "history_nonraw": order.price_adjustment_mode = runtime.DataNormalizationMode.ADJUSTED
    elif mode == "history_tag": order.tag = "prefix Liquidate from delisting"
    elif mode == "history_quantity": order.quantity = "-2"
    elif mode == "history_failure":
        def fail(identifier): raise RuntimeError("unknown history")
        algo.transactions.get_order_by_id = fail
    elif mode == "slice_untyped": algo.current_slice = NS(delistings={symbol: final})
    elif mode == "slice_missing": del algo.current_slice
    elif mode == "final_missing": algo.current_slice.delistings.clear()
    elif mode == "final_untyped": algo.current_slice.delistings = {symbol: NS(**vars(final))}
    elif mode == "final_warning": final.type = runtime.DelistingType.WARNING
    elif mode == "final_symbol": final.symbol = other
    elif mode == "final_duplicate": algo.current_slice.delistings[other] = final
    elif mode == "final_collection_unknown": algo.current_slice.delistings = None
    else: raise AssertionError(mode)
    return event


@pytest.mark.parametrize("mode", REFUSALS)
def test_native_final_authority_closed_evidence_refuses_unknowns(runtime, mode):
    values = native_final(runtime)
    algo = values[0]
    event = refuse(mode, runtime, values)
    assert algo._native_final_fill_symbol(event) is None
    assert algo._native_final_fill_authority is None
    assert algo._native_final_delisting_compatibility_exceptions == 0


@pytest.mark.parametrize("mode", ["message_substring", "history_untyped", "custody_missing", "final_warning", "fill_partial"])
def test_rejected_authority_does_not_bypass_original_scalar_refusal(runtime, mode):
    values = native_final(runtime)
    algo = values[0]
    event = refuse(mode, runtime, values)
    with pytest.raises(ValueError, match="RAW custody refused"):
        algo.on_order_event(event)
    assert algo._quantity_ledger == {"A": Fraction(3)} and algo._cash_ledger == 100
    assert algo._fill_events == 0 and algo._fees == 0
    assert algo._native_final_fill_authority is None


@pytest.mark.parametrize("mode", ["nonraw", "identity", "daily", "quote", "empty", "internal_only", "registry_failure"])
def test_native_final_never_weakens_global_raw_minute_registry(runtime, mode):
    algo, symbol, _, config, registry, _, _, event = native_final(runtime)
    if mode == "nonraw": config.data_normalization_mode = runtime.DataNormalizationMode.ADJUSTED
    elif mode == "identity": config.symbol = Symbol("OTHER")
    elif mode == "daily": config.resolution = runtime.Resolution.DAILY
    elif mode == "quote": config.tick_type = runtime.TickType.QUOTE
    elif mode == "empty": registry.clear()
    elif mode == "internal_only": config.is_internal_feed = True
    else:
        def fail(*args): raise RuntimeError("native registry unknown")
        algo.subscription_manager.subscription_data_config_service.get_subscription_data_configs = fail
    assert algo._native_final_fill_symbol(event) is symbol
    with pytest.raises((ValueError, RuntimeError)):
        algo.on_order_event(event)
    assert algo._quantity_ledger == {"A": Fraction(3)} and algo._cash_ledger == 100
    assert algo._fill_events == 0 and algo._native_final_fill_authority is None


def test_authority_exists_only_around_parent_and_clears_on_parent_failure(runtime, monkeypatch):
    algo, symbol, _, _, _, _, _, event = native_final(runtime)
    calls = []
    def fail(self, received):
        calls.append((received is event, self._native_final_fill_authority is symbol))
        raise RuntimeError("parent ledger failure")
    monkeypatch.setattr(runtime.core.TargetPriceSixUniverseAlgorithm, "on_order_event", fail)
    with pytest.raises(RuntimeError, match="parent ledger failure"):
        algo.on_order_event(event)
    assert calls == [(True, True)] and algo._native_final_fill_authority is None
    with pytest.raises(ValueError, match="RAW custody refused"):
        algo._assert_raw_subscriptions(symbol)


def test_ordinary_order_parent_still_runs_without_final_authority(runtime, monkeypatch):
    algo, _, _, _, _, _, _, event = native_final(runtime)
    event.message = "ordinary"
    calls = []
    monkeypatch.setattr(runtime.core.TargetPriceSixUniverseAlgorithm, "on_order_event",
        lambda self, received: calls.append((received is event, self._native_final_fill_authority)))
    algo.on_order_event(event)
    assert calls == [(True, None)] and algo._native_final_fill_authority is None


def test_ordinary_raw_fill_still_uses_parent_ledger_without_exception(runtime):
    algo, symbol, security, _, _, order, _, event = native_final(runtime)
    security.data_normalization_mode = runtime.DataNormalizationMode.RAW
    security.is_delisted, security.is_tradable = False, True
    event.message, order.tag = "ordinary", "ordinary"
    algo.on_order_event(event)
    assert algo._quantity_ledger["A"] == 0 and algo._cash_ledger == Fraction(245, 2)
    assert algo._fill_events == 1 and algo._native_final_delisting_compatibility_exceptions == 0


def test_native_final_does_not_authorize_later_dividend_or_held_action(runtime):
    algo, symbol, _, _, _, _, _, event = native_final(runtime)
    algo.on_order_event(event)
    with pytest.raises(ValueError, match="RAW custody refused"):
        algo._assert_raw_subscriptions(symbol)
    algo._quantity_ledger["A"] = Fraction(1)
    dividend = NS(symbol=symbol, distribution="1")
    with pytest.raises(ValueError, match="RAW custody refused"):
        algo.on_data(NS(bars={}, splits={}, delistings={}, dividends={symbol: dividend}))
    assert algo._native_final_fill_authority is None and algo._cash_ledger == Fraction(245, 2)


def test_native_liquidation_is_nonambient_and_not_economic_qualification(runtime):
    algo, symbol, _, _, _, _, _, event = native_final(runtime)
    algo.on_order_event(event)
    algo.on_data(algo.current_slice)
    assert algo._reasons["delisting_event"] == 1
    assert algo._delisting_audit["ever_filled"] == 1 and algo._delisting_audit["ever_ordered"] == 1
    assert algo._delisting_audit["nonambient"] == 1 and algo._delisting_audit["ambient"] == 0
    assert not cap_observer.validate_audit(algo._delisting_audit, 1)
    assert algo._native_final_fill_authority is None


def test_native_exception_summary_never_closes_delisting_acceptance_gate(runtime):
    algo, _, _, _, _, _, _, event = native_final(runtime)
    algo.on_order_event(event)
    algo.on_data(algo.current_slice)
    algo._config = {"candidate_id": "synthetic", "arm": "tpr_off", "cost": "baseline"}
    algo._decision_coverage = {day: {"sleeves": {etf: {} for etf in runtime.ETFS}}
                               for day in runtime.DECISIONS}
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
    algo.logs = []
    algo.log = algo.logs.append
    algo.on_end_of_algorithm()
    import json
    summary = json.loads(algo.logs[-1].split("MATCHED_SUMMARY ", 1)[1])
    assert summary["native_final_delisting_compatibility_exceptions"] == 1
    assert summary["meaningful_execution"] is False
    assert summary["original_no_delisting_meaningful_execution"] is False
    assert summary["development_execution_qualified"] is False
    assert summary["canonical_admission"] is False
    assert summary["delisting_audit"]["nonambient"] == 1


def test_native_final_does_not_depend_on_ticket_or_local_delisted_bookkeeping(runtime):
    algo, symbol, _, _, _, _, final, event = native_final(runtime)
    final.ticket = object()
    assert algo._delisted_ids == set()
    assert algo._native_final_fill_symbol(event) is symbol
    algo.on_order_event(event)
    assert algo._quantity_ledger["A"] == 0
