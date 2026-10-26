"""Synthetic LEAN-shaped behavior only; no operational package/provider/QC."""

import ast
import dataclasses
import hashlib
import gzip
import json
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import IntEnum
from fractions import Fraction
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS

import pytest

from research.analyst_revisions_v2_qc import newrule_comparison_projection as projection
from research.analyst_revisions_v2_qc import newrule_comparison_qc_runtime as runtime
from research.analyst_revisions_v2_qc import newrule_comparison_targets as targets


D = Decimal


class Status(IntEnum):
    NEW = 0
    SUBMITTED = 1
    PARTIALLY_FILLED = 2
    FILLED = 3
    CANCELED = 5
    NONE = 6
    INVALID = 7
    CANCEL_PENDING = 8
    UPDATE_SUBMITTED = 9


@dataclasses.dataclass(frozen=True)
class Symbol:
    id: str
    value: str


def axis():
    # Deliberately synthetic weekday axis, not a replacement exchange calendar.
    start, end = date(2013, 1, 2), date(2026, 10, 13)
    return tuple((start + timedelta(days=index)).isoformat()
        for index in range((end - start).days + 1)
        if (start + timedelta(days=index)).weekday() < 5)


def profile(count=6, arm=0, pins=None):
    return runtime.make_profile(axis(), package_sha256="a" * 64, lineage_sha256="b" * 64,
        universe_count=count, ar_percent=arm, source_pins=pins or {"test.py": "c" * 64})


class Portfolio(dict):
    cash = D("1000000")

    def __missing__(self, symbol):
        self[symbol] = NS(quantity=D(0))
        return self[symbol]

    @property
    def total_portfolio_value(self):
        return self.cash + self.total_holdings_value

    @property
    def total_holdings_value(self):
        return sum((row.quantity * D(100) for row in self.values()), D(0))


class History:
    def __init__(self):
        self.values = []
        self.calls = []

    def __getitem__(self, kind):
        def call(*args, **kwargs):
            self.calls.append((kind, args, kwargs))
            return iter(self.values)
        return call


class Batch(dict):
    time = datetime(2026, 10, 12)


def driver():
    algorithm = NS(time=datetime(2026, 10, 12, 9, 31), live_mode=False,
        portfolio=Portfolio(), history=History(), securities={}, orders={}, submitted=[], fee_delta=D(0),
        status_override=None, fill_delta=D(0), summaries={})
    symbols = {name: Symbol("SID-" + name, name) for name in ("A", "B") + targets.UNIVERSES}
    def security(symbol):
        return NS(symbol=symbol, price=D(100), is_delisted=False,
            get_last_data=lambda: NS(end_time=algorithm.time, is_fill_forward=False),
            set_data_normalization_mode=lambda value: None,
            set_fee_model=lambda value: None, set_slippage_model=lambda value: None,
            set_leverage=lambda value: None)
    algorithm.securities = {s: security(s) for s in symbols.values()}
    algorithm.add_security = lambda symbol, *args: algorithm.securities[symbol]
    algorithm.remove_security = lambda symbol: True
    algorithm.transactions = NS(get_open_orders=lambda *args: (),
        get_order_by_id=lambda identity: algorithm.orders.get(identity))
    algorithm.set_summary_statistic = lambda name, value: algorithm.summaries.__setitem__(name, value)
    value = runtime.NewruleComparisonDriver(algorithm, profile=profile(),
        activation_manifest_key="synthetic/activation.json", activation_manifest_sha256="d" * 64,
        activation_manifest_byte_count=100, benchmark_symbol=symbols["SPY"],
        etf_symbols={name: symbols[name] for name in targets.UNIVERSES},
        fundamental_universe=object(), constituent_universes={name: object() for name in targets.UNIVERSES},
        trade_bar_type=object(), minute_resolution="minute", daily_resolution="daily",
        raw_normalization="raw", fee_model_factory=lambda: object(), slippage_model_factory=lambda: object(),
        order_status_enum=Status, order_status_to_int=int, split_occurred_type="occurred",
        split_warning_type="warning", split_data_type="Split")
    value._initialized = True
    value._security_by_sid = {symbols[name].id: name for name in ("A", "B")}
    value._label_by_sid = {symbols[name].id: name for name in ("A", "B")}
    value._symbol_by_security = {name: symbols[name] for name in ("A", "B")}
    value._security_by_etf_sid = {symbols[name].id: symbols[name].id for name in targets.UNIVERSES}
    value._symbol_by_security.update({symbols[name].id: symbols[name] for name in targets.UNIVERSES})
    value._session_axis = ("2026-10-09", "2026-10-12", "2026-10-13")
    value._session_positions = {s: i for i, s in enumerate(value._session_axis)}
    value._evaluation_sessions = ("2026-10-12", "2026-10-13")
    value._decision_sessions = ("2026-10-12",)
    value._decision_set = frozenset(value._decision_sessions)
    def market(symbol, quantity, *, asynchronous, tag):
        assert asynchronous is False
        identity = len(algorithm.orders) + 1
        algorithm.orders[identity] = NS(id=identity, quantity=quantity, tag=tag)
        algorithm.submitted.append((symbol.value, quantity))
        quote = algorithm.securities[symbol].price
        price = quote + algorithm.fill_delta
        fee = abs(quantity) * quote * D("0.001") + algorithm.fee_delta
        algorithm.portfolio[symbol].quantity += quantity
        algorithm.portfolio.cash -= quantity * price + fee
        status = algorithm.status_override or Status.FILLED
        event = NS(symbol=symbol, order_id=identity, id=1, status=status,
            fill_quantity=quantity, fill_price=price, order_fee=NS(value=NS(amount=fee, currency="USD")),
            utc_time=runtime.instant(algorithm.time).astimezone(timezone.utc))
        value.on_order_event(event)
        return NS(order_id=identity, status=status)
    algorithm.market_order = market
    return value, algorithm, symbols


def plan(value, desired, holdings=None):
    value._plans["2026-10-12"] = {"sha256": "e" * 64, "quantities": desired,
        "holdings": holdings or {}, "split_records": {}}
    value._preopen_clock_confirmations["2026-10-12"] = "f" * 64


@pytest.mark.parametrize("count", [6, 8])
@pytest.mark.parametrize("arm", [0, 100, 200])
def test_profile_geometry_and_six_cell_identity(count, arm):
    value = profile(count, arm)
    assert value["candidate_id"] == f"arv2-newrule-{count}-ar{arm}-2026-v1"
    assert value["decision_sessions"][-1] == "2026-10-12"
    assert "2026-10-13" not in value["decision_sessions"]
    assert value["evaluation_sessions"][-1] == "2026-10-13"
    assert value["maximum_dynamic_subscriptions"] == 192
    assert value["formal_forward_ready"] is False


def test_market_orders_reenter_then_reconcile_sells_before_buys():
    value, algorithm, symbols = driver()
    algorithm.portfolio.cash = D(0)
    algorithm.portfolio[symbols["A"]].quantity = D(10)
    plan(value, {"A": 0, "B": 9}, {"A": 10})
    value.on_after_open()
    assert algorithm.submitted == [("A", -10), ("B", 9)]
    assert algorithm.portfolio.cash == D("98.1")
    assert value._intent is None and len(value._fills) == 2
    assert "2026-10-12" in value._executed


def test_buy_cash_capacity_uses_actual_cash_including_fees():
    value, algorithm, symbols = driver()
    algorithm.portfolio.cash = D("1000")
    plan(value, {"B": 10})
    value.on_after_open()
    assert algorithm.submitted == [("B", 9)]
    assert value._cash_underfill_count == 1 and algorithm.portfolio.cash == D("99.1")


def test_fill_price_and_fee_basis_are_distinct_but_actual_cash_is_reconciled():
    value, algorithm, symbols = driver()
    algorithm.fill_delta = D(1)
    plan(value, {"B": 1})
    value.on_after_open()
    assert value._fills[0]["price"] == "101"
    assert value._fills[0]["fee_basis_quote"] == "100"
    assert value._fills[0]["fee"] == "0.100"


@pytest.mark.parametrize("failure", ["fee", "partial", "clock", "holding", "live", "stale", "fillforward", "late_frontier"])
def test_order_inadmissible_states_refuse_without_retry(failure):
    value, algorithm, symbols = driver()
    plan(value, {"B": 1})
    if failure == "fee":
        algorithm.fee_delta = D("0.01")
    elif failure == "partial":
        algorithm.status_override = Status.PARTIALLY_FILLED
    elif failure == "clock":
        algorithm.time = datetime(2026, 10, 12, 9, 30)
    elif failure == "holding":
        algorithm.portfolio[symbols["A"]].quantity = D(1)
    elif failure == "live":
        algorithm.live_mode = True
    elif failure == "stale":
        algorithm.securities[symbols["B"]].get_last_data = lambda: NS(end_time=datetime(2026, 10, 9, 16))
    elif failure == "fillforward":
        algorithm.securities[symbols["B"]].get_last_data = lambda: NS(end_time=algorithm.time, is_fill_forward=True)
    elif failure == "late_frontier":
        value._preopen_clock_confirmations.clear()
    with pytest.raises(targets.NewruleError):
        value.on_after_open()
    assert len(algorithm.submitted) <= 1
    assert not value._executed


def test_duplicate_dispatch_refuses():
    value, algorithm, _ = driver()
    plan(value, {"B": 1})
    value.on_after_open()
    with pytest.raises(targets.NewruleError, match="execution_once"):
        value.on_after_open()
    assert len(algorithm.submitted) == 1


def test_same_session_callback_cutoff_and_source_age():
    value, algorithm, symbols = driver()
    algorithm.time = datetime(2026, 10, 12, 9, 19)
    row = NS(symbol=symbols["A"], market_cap=D(1000), end_time=datetime(2026, 10, 12))
    value.accept_fundamentals([row])
    cutoff = runtime.instant(datetime(2026, 10, 12, 9, 20))
    assert value._collection("FUNDAMENTALS", cutoff)[0] == (("SID-A", "A", "1000"),)
    algorithm.time = datetime(2026, 10, 12, 9, 20)
    value.accept_constituents("SPY", [NS(symbol=symbols["A"], weight=D(1), end_time=datetime(2026, 10, 12))])
    assert value._collection("SPY", cutoff) == ((), None)
    later = runtime.instant(datetime(2026, 10, 19, 9, 20))
    assert value._collection("FUNDAMENTALS", later)[0] == ()


@pytest.mark.parametrize("failure", ["duplicate", "future", "mixed", "revision"])
def test_callback_source_disagreements_refuse(failure):
    value, algorithm, symbols = driver()
    algorithm.time = datetime(2026, 10, 12, 9, 19)
    row = NS(symbol=symbols["A"], market_cap=D(1000), end_time=datetime(2026, 10, 12))
    if failure == "duplicate":
        rows = [row, row]
    elif failure == "future":
        row.end_time = datetime(2026, 10, 13)
        rows = [row]
    elif failure == "mixed":
        rows = [row, NS(symbol=symbols["B"], market_cap=D(2000), end_time=datetime(2026, 10, 11))]
    else:
        value.accept_fundamentals([row])
        row.market_cap = D(2000)
        rows = [row]
    with pytest.raises(targets.NewruleError):
        value.accept_fundamentals(rows)


def test_missing_weight_is_retained_and_refuses_whole_book():
    value, algorithm, symbols = driver()
    algorithm.time = datetime(2026, 10, 12, 9, 19)
    row = NS(symbol=symbols["A"], weight=None, end_time=datetime(2026, 10, 12))
    value.accept_constituents("SPY", [row])
    frozen, _ = value._collection("SPY", runtime.instant(datetime(2026, 10, 12, 9, 20)))
    assert frozen == (("SID-A", "A", None),)


def test_empty_split_history_is_qualified_and_exactly_one_bounded_batch_query():
    value, algorithm, _ = driver()
    algorithm.time = datetime(2026, 10, 12, 9, 20)
    factors, binding = value._split_factors(("A", "B"), value._now())
    assert factors == {"A": D(1), "B": D(1)} and len(binding) == 64
    assert len(algorithm.history.calls) == 1
    kind, args, kwargs = algorithm.history.calls[0]
    assert kind == "Split" and args[1] == datetime(2026, 10, 9)
    assert args[2] == datetime(2026, 10, 12, 9, 20)
    assert kwargs == {"fill_forward": False, "extended_market_hours": False}


def split_event(symbol, factor=D("0.1"), kind="occurred"):
    return NS(symbol=symbol, split_factor=factor, type=kind,
        time=datetime(2026, 10, 12), end_time=datetime(2026, 10, 12))


def test_split_history_matches_callback_and_warnings_never_adjust():
    value, algorithm, symbols = driver()
    event = split_event(symbols["A"])
    algorithm.time = datetime(2026, 10, 12, 8)
    value.on_splits({symbols["A"]: event})
    algorithm.time = datetime(2026, 10, 12, 9, 20)
    algorithm.history.values = [Batch({symbols["A"]: event, symbols["B"]: split_event(symbols["B"], kind="warning")})]
    factors, _ = value._split_factors(("A", "B"), value._now())
    assert factors == {"A": D("0.1"), "B": D(1)}


@pytest.mark.parametrize("failure", ["future", "factor", "identity", "callback", "duplicate", "bound", "unknown_kind"])
def test_split_history_ambiguity_refuses(failure):
    value, algorithm, symbols = driver()
    event = split_event(symbols["A"])
    algorithm.time = datetime(2026, 10, 12, 9, 20)
    algorithm.history.values = [Batch({symbols["A"]: event})]
    if failure == "future":
        event.end_time = datetime(2026, 10, 12, 9, 21)
    elif failure == "factor":
        event.split_factor = D(0)
    elif failure == "identity":
        event.symbol = symbols["B"]
    elif failure == "callback":
        value._split_records_by_session["2026-10-12"] = {"A": {"factor": "0.5"}}
    elif failure == "duplicate":
        algorithm.history.values *= 2
    elif failure == "unknown_kind":
        event.type = "unknown"
    else:
        algorithm.history.values *= 513
    with pytest.raises((targets.NewruleError, runtime.legacy.AcceptedRiskSixUniverseOrderQcRuntimeError)):
        value._split_factors(("A", "B"), value._now())


def test_late_split_callback_cannot_repair_frozen_plan():
    value, algorithm, symbols = driver()
    with pytest.raises(targets.NewruleError, match="split_not_predecision"):
        value.on_splits({symbols["A"]: split_event(symbols["A"])})


def test_terminal_does_not_submit_a_forced_oct13_rebalance():
    value, algorithm, _ = driver()
    algorithm.time = datetime(2026, 10, 13, 9, 20)
    assert value.on_before_open() is None
    algorithm.time = datetime(2026, 10, 13, 9, 31)
    assert value.on_after_open() is None
    assert algorithm.submitted == []
    with pytest.raises(targets.NewruleError, match="incomplete_terminal_geometry"):
        value.on_end_of_algorithm()


def test_complete_synthetic_terminal_emits_two_bounded_stats():
    value, algorithm, _ = driver()
    value._plans = {"2026-10-12": {"binding": {"context_sha256": "f" * 64}, "sha256": "e" * 64}}
    value._executed = {"2026-10-12"}
    value._account_observations = {"2026-10-12": D("1000000"), "2026-10-13": D("1010000")}
    value._gross_exposure_observations = {"2026-10-12": D(0), "2026-10-13": D(0)}
    value._account_safety = {s: "a" * 64 for s in value._evaluation_sessions}
    value._preopen_clock_confirmations = {"2026-10-12": "b" * 64}
    value._order_ids, value._fills = {1}, [{"synthetic": True, "fee": "1"}]
    value._reference_history_call_count = value._split_history_count = 1
    algorithm.time = datetime(2026, 10, 13, 16)
    meta, monthly = value.on_end_of_algorithm()
    assert meta["formal_identity_admitted"] is False
    assert monthly["months"] == [["2026-10-13", "0.010000000000", "1010000.000000"]]
    assert set(algorithm.summaries) == {runtime.META_STATISTIC, runtime.MONTHLY_STATISTIC}
    assert all(len(value) < 8192 for value in algorithm.summaries.values())
    assert not algorithm.submitted


def source_bytes():
    return {name: (projection.ROOT / name).read_bytes()
            for name in set(projection.OLD_PINS) | set(projection.NEW_SOURCE_NAMES)}


def test_pinned_projection_has_one_market_order_and_no_moo_capability():
    sources = source_bytes()
    pins = {name: hashlib.sha256(value).hexdigest() for name, value in sources.items()}
    activation = NS(object_store_key="synthetic/activation.json", content_sha256="d" * 64, byte_count=100)
    result = projection.render_projection(profile=profile(pins=pins), activation=activation, sources=sources)
    record = result.to_record()
    assert record["market_orders_only"] is True and record["market_on_open_orders_only"] is False
    assert sum(item.byte_count for item in result.source_files) < 448 * 1024
    assert all(item.byte_count <= 64000 for item in result.source_files)
    all_nodes = [node for item in result.source_files for node in ast.walk(ast.parse(item.source_bytes))]
    assert sum(isinstance(node, ast.Attribute) and node.attr == "market_order" for node in all_nodes) == 1
    assert not any(isinstance(node, ast.Attribute) and node.attr == "market_on_open_order" for node in all_nodes)
    primitive = next(item for item in result.source_files if item.project_path == "newrule_legacy_primitives.py")
    assert b"MAXIMUM_ACTIVE_DYNAMIC_SECURITY_COUNT = 192" in primitive.source_bytes
    assert b"MAXIMUM_REFERENCE_HISTORY_CALLS = 400" in primitive.source_bytes
    assert b"SimulatedMooExecutor" not in primitive.source_bytes


def test_old_source_pin_change_refuses_before_extraction():
    old = source_bytes()["accepted_risk_six_universe_order_qc_runtime.py"]
    with pytest.raises(targets.NewruleError, match="legacy_runtime_pin"):
        projection.legacy_primitives(old + b"\n")


@pytest.mark.parametrize("source", [b"import socket\n", b"x.market_on_open_order()\n", b"open('x')\n"])
def test_projected_forbidden_capability_refuses(source):
    with pytest.raises(targets.NewruleError):
        projection.audit("synthetic.py", source)


def test_public_projection_requires_authenticated_october_wrapper_not_rows():
    with pytest.raises(projection.october.OctoberOrderInputPackageError):
        projection.build_projection(NS(package=object()), expected_package_sha256="a" * 64,
            expected_lineage_sha256="b" * 64, expected_new_source_pins={}, universe_count=6, ar_percent=0)


def test_split_query_models_exclusive_lower_bound_and_prior_factor_initialization():
    value, algorithm, symbols = driver()
    algorithm.time = datetime(2026, 10, 12, 9, 20)
    event = split_event(symbols["A"])
    class ProviderHistory:
        def __getitem__(self, kind):
            assert kind == "Split"
            def call(census, start, end, resolution, **kwargs):
                # Models both LEAN's prior-date factor initialization and
                # TimeBasedFilter's strict EndTime > StartTimeLocal boundary.
                initialized = start <= datetime(2026, 10, 9)
                return [Batch({symbols["A"]: event})] if initialized and start < event.end_time <= end else []
            return call
    algorithm.history = ProviderHistory()
    factors, _ = value._split_factors(("A",), value._now())
    assert factors["A"] == D("0.1")


def test_prior_split_rows_are_authenticated_but_never_applied_to_current_units():
    value, algorithm, symbols = driver()
    algorithm.time = datetime(2026, 10, 12, 9, 20)
    event = split_event(symbols["A"])
    event.time = event.end_time = datetime(2026, 10, 9, 12)
    batch = Batch({symbols["A"]: event})
    batch.time = event.time
    algorithm.history.values = [batch]
    factors, _ = value._split_factors(("A",), value._now())
    assert factors["A"] == 1
    event.split_factor = D(0)
    with pytest.raises(runtime.legacy.AcceptedRiskSixUniverseOrderQcRuntimeError):
        value._split_factors(("A",), value._now())


def before_open_fixture(monkeypatch):
    value, algorithm, symbols = driver()
    algorithm.time = datetime(2026, 10, 12, 9, 20)
    books = tuple(targets.Book(name, symbols[name].id, (), "missing_or_stale_collection") for name in targets.UNIVERSES)
    monkeypatch.setattr(value, "_books", lambda session: (books, "a" * 64))
    monkeypatch.setattr(value, "_reference_prices", lambda previous, census: {sid: D(100) for sid in census})
    value._account_observations["2026-10-09"] = D(800000)
    return value, algorithm, symbols


def test_prior_close_nav_controls_sizing_not_mixed_premarket_engine_nav(monkeypatch):
    value, algorithm, symbols = before_open_fixture(monkeypatch)
    value.on_before_open()
    binding = value._plans["2026-10-12"]["binding"]
    assert binding["sizing_nav"] == "800000" and binding["sizing_nav_session"] == "2026-10-09"
    assert binding["actual_engine_nav_diagnostic"] == "1000000"
    assert value._plans["2026-10-12"]["quantities"][symbols["SPY"].id] == 1306
    assert not algorithm.submitted


def test_missing_exact_previous_close_refuses_instead_of_current_nav_fallback(monkeypatch):
    value, algorithm, _ = before_open_fixture(monkeypatch)
    value._account_observations = {"2026-10-08": D(800000)}
    with pytest.raises(targets.NewruleError, match="missing_prior_close_sizing_nav"):
        value.on_before_open()
    assert not algorithm.submitted


def clock_slice(symbol, stamp, *, filled=True):
    return NS(bars={symbol: NS(symbol=symbol, end_time=stamp, is_fill_forward=filled)})


def test_real_preopen_ondata_must_follow_frozen_plan_before_any_order(monkeypatch):
    value, algorithm, symbols = before_open_fixture(monkeypatch)
    with pytest.raises(targets.NewruleError, match="preopen_frontier_order"):
        value.on_data(clock_slice(symbols["SPY"], algorithm.time))
    value.on_before_open()
    value.on_data(clock_slice(symbols["SPY"], algorithm.time))
    assert set(value._preopen_clock_confirmations) == {"2026-10-12"}
    algorithm.time = datetime(2026, 10, 12, 9, 31)
    value.on_after_open()
    assert len(algorithm.submitted) == 6


def test_late_scheduled_replay_cannot_replace_genuine0920_ondata(monkeypatch):
    value, algorithm, symbols = before_open_fixture(monkeypatch)
    value.on_before_open()  # Emulates ScanPastEvents assigning nominal09:20.
    algorithm.time = datetime(2026, 10, 12, 9, 31)
    value.on_data(clock_slice(symbols["SPY"], algorithm.time))
    with pytest.raises(targets.NewruleError, match="missing_genuine_preopen_frontier"):
        value.on_after_open()
    assert not algorithm.submitted


@pytest.mark.parametrize("failure", ["missing", "wrong_end", "wrong_sid", "bad_ff"])
def test_clock_confirmation_refuses_unbound_slice(monkeypatch, failure):
    value, algorithm, symbols = before_open_fixture(monkeypatch)
    value.on_before_open()
    data = clock_slice(symbols["SPY"], algorithm.time)
    if failure == "missing":
        data.bars = {}
    elif failure == "wrong_end":
        data.bars[symbols["SPY"]].end_time = datetime(2026, 10, 12, 9, 19)
    elif failure == "wrong_sid":
        data.bars[symbols["SPY"]].symbol = symbols["A"]
    else:
        data.bars[symbols["SPY"]].is_fill_forward = 1
    with pytest.raises(targets.NewruleError):
        value.on_data(data)
    assert not value._preopen_clock_confirmations


def test_held_split_requires_predecision_callback_but_new_stock_does_not(monkeypatch):
    value, algorithm, symbols = before_open_fixture(monkeypatch)
    algorithm.portfolio[symbols["A"]].quantity = D(10)
    algorithm.history.values = [Batch({symbols["A"]: split_event(symbols["A"])})]
    with pytest.raises(targets.NewruleError, match="held_split_units_not_observed"):
        value.on_before_open()


@pytest.mark.parametrize("failure", ["cash", "fractional", "short", "unknown_sid"])
def test_close_checks_actual_cash_and_complete_whole_long_holdings(failure):
    value, algorithm, symbols = driver()
    algorithm.time = datetime(2026, 10, 13, 16)
    if failure == "cash":
        algorithm.portfolio.cash = D(-1)
    elif failure == "fractional":
        algorithm.portfolio[symbols["A"]].quantity = D("0.5")
    elif failure == "short":
        algorithm.portfolio[symbols["A"]].quantity = D(-1)
    else:
        algorithm.portfolio[Symbol("unknown", "Z")].quantity = D(1)
    with pytest.raises(runtime.legacy.AcceptedRiskSixUniverseOrderQcRuntimeError):
        value.on_after_close()
    assert not value._account_safety


def result_fixture():
    value, algorithm, _ = driver()
    value._profile = profile()
    value._decision_sessions = tuple(value._profile["decision_sessions"])
    value._evaluation_sessions = tuple(value._profile["evaluation_sessions"])
    value._plans = {s: {"binding": {"context_sha256": "a" * 64}, "sha256": "b" * 64} for s in value._decision_sessions}
    value._executed = set(value._decision_sessions)
    value._account_observations = {s: D("1000000.123456789") for s in value._evaluation_sessions}
    value._account_safety = {s: "c" * 64 for s in value._evaluation_sessions}
    value._preopen_clock_confirmations = {s: "d" * 64 for s in value._decision_sessions}
    value._order_ids, value._fills = {1}, [{"synthetic": True, "fee": "1"}]
    value._reference_history_call_count = value._split_history_count = len(value._decision_sessions)
    algorithm.time = datetime(2026, 10, 13, 16)
    value.on_end_of_algorithm()
    return algorithm.summaries, value._profile


def test_strict_result_validator_accepts_only_bound_finite_complete_aggregate():
    stats, expected = result_fixture()
    stats["Unrelated QC statistic"] = "unread"
    result = runtime.validate_result_statistics(stats, expected_profile=expected)
    assert result["meta"]["order_count"] == 1 and result["meta"]["complete_geometry"] is True
    assert len(result["monthly"]["months"]) == 70
    assert result["monthly"]["months"][-1][0] == "2026-10-13"
    result["meta"]["order_count"] = 99
    assert json.loads(stats[runtime.META_STATISTIC])["order_count"] == 1


@pytest.mark.parametrize("field,bad", [
    ("candidate_id", "other"), ("package_sha256", "0" * 64), ("lineage_sha256", "0" * 64),
    ("profile_sha256", "0" * 64), ("decision_count", 1), ("evaluation_session_count", 1),
    ("order_count", 0), ("order_count", True), ("fill_count", 2),
    ("raw_reference_history_calls", 0), ("split_unit_history_calls", 0),
    ("common_source_path_sha256", "invalid"), ("point_in_time_proven", True),
    ("formal_forward_ready", 0), ("no_open_orders", False), ("actual_clock_confirmation_complete", False),
    ("actual_fill_cash_reconciled", False), ("configured_fee_checks_complete", False),
    ("whole_long_holdings_at_fills_closes_terminal", False), ("nonnegative_cash_at_fills_closes_terminal", False),
    ("coverage_fallback_counts", {"SPY:unknown": 1}),
    ("alternative_view_score_disagreements", -1), ("extra", 1),
])
def test_result_meta_tampering_refuses(field, bad):
    stats, expected = result_fixture()
    data = json.loads(stats[runtime.META_STATISTIC])
    data[field] = bad
    stats[runtime.META_STATISTIC] = targets.canonical(data).decode()
    with pytest.raises(targets.NewruleError):
        runtime.validate_result_statistics(stats, expected_profile=expected)


@pytest.mark.parametrize("failure", ["missing_month", "wrong_endpoint", "return", "nan", "negative_nav", "rounding", "realized_alt", "duplicate_key", "trailing", "oversized"])
def test_result_monthly_or_envelope_tampering_refuses(failure):
    stats, expected = result_fixture()
    data = json.loads(stats[runtime.MONTHLY_STATISTIC])
    if failure == "missing_month":
        data["months"].pop()
    elif failure == "wrong_endpoint":
        data["months"][-1][0] = "2026-10-12"
    elif failure == "return":
        data["months"][1][1] = "0.010000000000"
    elif failure == "nan":
        data["months"][1][1] = "NaN"
    elif failure == "negative_nav":
        data["months"][1][2] = "-1.000000"
    elif failure == "rounding":
        data["months"][1][1] = "0"
    elif failure == "realized_alt":
        data["alternative_view_realized_performance"] = True
    stats[runtime.MONTHLY_STATISTIC] = targets.canonical(data).decode()
    if failure == "duplicate_key":
        stats[runtime.MONTHLY_STATISTIC] = '{"schema":"duplicate",' + stats[runtime.MONTHLY_STATISTIC][1:]
    elif failure == "trailing":
        stats[runtime.MONTHLY_STATISTIC] += "\n"
    elif failure == "oversized":
        stats[runtime.MONTHLY_STATISTIC] = " " * 8193
    with pytest.raises(targets.NewruleError):
        runtime.validate_result_statistics(stats, expected_profile=expected)


def projected_modules(monkeypatch):
    sources = source_bytes()
    pins = {name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()}
    activation = NS(object_store_key="synthetic/activation.json", content_sha256="d" * 64, byte_count=100)
    rendered = projection.render_projection(profile=profile(pins=pins), activation=activation, sources=sources)
    payloads = {item.project_path[:-3]: item.source_bytes for item in rendered.source_files}
    order = ("accepted_risk_preliminary_rating_policy", "accepted_risk_preliminary_rating_evaluator",
        "accepted_risk_order_level_core", "accepted_risk_order_level_forced_exit",
        "accepted_risk_order_level_input_runtime", "accepted_risk_preliminary_qc_figi",
        "accepted_risk_preopen_rating_score", "newrule_comparison_targets", "newrule_legacy_primitives",
        "newrule_comparison_qc_runtime")
    result = {}
    for name in order:
        module = ModuleType(name)
        monkeypatch.setitem(sys.modules, name, module)
        exec(compile(payloads[name], "<synthetic-projected-" + name + ">", "exec"), module.__dict__)
        result[name] = module
    return result


def genuine_synthetic_transport(modules):
    loader = modules["accepted_risk_order_level_input_runtime"]
    evaluator = modules["accepted_risk_preliminary_rating_evaluator"]
    figi = modules["accepted_risk_preliminary_qc_figi"]
    sessions = projection.october._sessions()
    axis_rows = tuple({"schema": evaluator.SESSION_SCHEMA, "session_index": i, "session": s} for i, s in enumerate(sessions))
    lineage = {name: "c" * 64 for name in ("accepted_risk_input_pair_sha256", "security_master_admission_sha256",
        "firm_ontology_admission_sha256", "global_rating_map_sha256", "pre_normalized_contribution_source_sha256")}
    memberships, bindings, contributions = [], [], []
    for i in range(5):
        figi_value = "BBG00000000" + str(i)
        identity = "sharadar-composite-figi-" + figi_value
        memberships.append(evaluator.build_membership_record(security_id=identity,
            first_session_index=0, last_session_index_exclusive=len(sessions), sector_id="synthetic-sector"))
        bindings.append(figi.build_preliminary_qc_figi_binding(security_id=identity, issuer_id="issuer-" + str(i),
            composite_figi=figi_value, listing_id="listing-" + str(i), diagnostic_current_ticker="S" + str(i),
            diagnostic_exchange_mic="XNYS", candidate_first_session=sessions[0], candidate_last_session=sessions[-1],
            source_snapshot_available_at="2026-10-13T23:00:00.000000Z", source_row_sha256="d" * 64,
            identity_evidence_sha256="e" * 64, security_master_admission_sha256="c" * 64,
            admitted_mapping_inventory_sha256="f" * 64, admitted_mapping_count=5))
        for view in evaluator.SOURCE_VIEW_IDS:
            for when in ("2020-12-30", "2026-10-12"):
                contributions.append(evaluator.build_contribution_record(source_view_id=view, security_id=identity,
                    eligible_session_index=sessions.index(when), institution_id="firm-" + str(i),
                    common_event_id=view + "-" + identity + "-" + when, rating_action="upgrades",
                    firm_delta=Fraction(i + 1, 5), global_delta=Fraction(i + 1, 5), source_row_sha256="a" * 64))
    contributions.sort(key=lambda row: (evaluator.SOURCE_VIEW_IDS.index(row["source_view_id"]),
        row["eligible_session_index"], row["security_id"], row["institution_id"], row["contribution_id"]))
    manifest = evaluator.build_preliminary_rating_manifest(benchmark_security_id=loader.BENCHMARK_SECURITY_ID,
        session_axis_records=axis_rows, membership_records=tuple(memberships), contribution_records=tuple(contributions),
        source_lineage_sha256s=lineage)
    roles = {"evaluator_manifest": (manifest,), "session_axis": axis_rows, "memberships": tuple(memberships),
        "contributions": tuple(contributions), "runtime_symbol_bindings": tuple(bindings)}
    values, descriptors = {}, []
    for role, rows in roles.items():
        raw = b"".join(targets.canonical(row) + b"\n" for row in rows)
        compressed = role != "evaluator_manifest"
        payload = gzip.compress(raw, mtime=0) if compressed else raw
        name = role + ("-0000-jsonl.gz" if compressed else ".json")
        key = "arv2/synthetic-newrule/" + name
        values[key] = payload
        descriptors.append({"schema": loader.UPLOAD_OBJECT_SCHEMA, "role": role, "ordinal": 0,
            "object_store_key": key, "relative_path": name, "byte_count": len(payload),
            "content_sha256": hashlib.sha256(payload).hexdigest(), "record_count": len(rows),
            "compression": "gzip" if compressed else "identity", "activation_manifest": False})
    transport = {"schema": loader.TRANSPORT_MANIFEST_SCHEMA, "package_id": None, "package_sha256": None,
        "evaluator_manifest_id": manifest["manifest_id"], "evaluator_manifest_sha256": manifest["manifest_sha256"],
        "benchmark": {"security_id": loader.BENCHMARK_SECURITY_ID, "ticker": loader.BENCHMARK_TICKER,
                      "binding": "QC_US_equity_symbol_resolved_in_process"},
        "source_disposition_sha256": "b" * 64, "runtime_symbol_binding_count": 5,
        "runtime_symbol_bindings_sha256": loader._stream_hash(bindings), "contribution_census": {"accepted": len(contributions)},
        "objects": descriptors, "runtime": dict(loader._EXPECTED_RUNTIME), "claims": dict(loader._EXPECTED_CLAIMS)}
    package_hash = targets.digest(transport)
    transport["package_id"] = "arv2-preliminary-qc-package-" + package_hash[:24]
    transport["package_sha256"] = package_hash
    key = "arv2/synthetic-newrule/transport-manifest.json"
    payload = targets.canonical(transport) + b"\n"
    values[key] = payload
    return sessions, values, key, payload, package_hash


def projected_loaded_driver(monkeypatch):
    modules = projected_modules(monkeypatch)
    projected = modules["newrule_comparison_qc_runtime"]
    sessions, values, key, payload, package_hash = genuine_synthetic_transport(modules)
    _, algorithm, symbols = driver()
    class Sid(str):
        market = "usa"
    class EquitySymbol:
        security_type = "Equity"
        def __init__(self, sid, value):
            self.id, self.value = Sid(sid), value
    for ticker in targets.UNIVERSES:
        original = symbols[ticker]
        symbol = EquitySymbol(original.id, original.value)
        security = algorithm.securities.pop(original)
        security.symbol = symbol
        algorithm.securities[symbol] = security
        symbols[ticker] = symbol
    mapped = {"BBG00000000" + str(i): EquitySymbol("QC-stock-" + str(i), "S" + str(i)) for i in range(5)}
    inverse = {id(symbol): code for code, symbol in mapped.items()}
    algorithm.composite_figi = lambda item: mapped[item] if type(item) is str else inverse[id(item)]
    reads = []
    algorithm.object_store = NS(contains_key=lambda name: name in values,
        read_bytes=lambda name: (reads.append(name), values[name])[1])
    for symbol in mapped.values():
        algorithm.securities[symbol] = NS(symbol=symbol, price=D(100), is_delisted=False,
            get_last_data=lambda: NS(end_time=algorithm.time, is_fill_forward=False),
            set_data_normalization_mode=lambda value: None, set_fee_model=lambda value: None,
            set_slippage_model=lambda value: None, set_leverage=lambda value: None)
    expected = projected.make_profile(sessions, package_sha256=package_hash, lineage_sha256="b" * 64,
        universe_count=6, ar_percent=0, source_pins={"synthetic.py": "c" * 64})
    value = projected.NewruleComparisonDriver(algorithm, profile=expected,
        activation_manifest_key=key, activation_manifest_sha256=hashlib.sha256(payload).hexdigest(),
        activation_manifest_byte_count=len(payload), benchmark_symbol=symbols["SPY"],
        etf_symbols={name: symbols[name] for name in targets.UNIVERSES}, fundamental_universe=object(),
        constituent_universes={name: object() for name in targets.UNIVERSES}, trade_bar_type="TradeBar",
        minute_resolution="minute", daily_resolution="daily", raw_normalization="raw",
        fee_model_factory=lambda: object(), slippage_model_factory=lambda: object(), order_status_enum=Status,
        order_status_to_int=int, split_occurred_type="occurred", split_warning_type="warning", split_data_type="Split")
    value.initialize()
    return value, algorithm, symbols, tuple(mapped.values()), reads, values, modules


def test_actual_projected_loader_figi_scorer_and_priorclose_predecision_work_together(monkeypatch):
    value, algorithm, etfs, stocks, reads, _, _ = projected_loaded_driver(monkeypatch)
    assert len(reads) == 6 and reads[0].endswith("transport-manifest.json")
    assert len(value._session_axis) == 3466 and len(value._security_by_sid) == 5
    algorithm.time = datetime(2026, 10, 12, 9, 19)
    value.accept_fundamentals([NS(symbol=symbol, market_cap=D(1000 + i), end_time=datetime(2026, 10, 12))
                              for i, symbol in enumerate(stocks)])
    for ticker in targets.UNIVERSES:
        value.accept_constituents(ticker, [NS(symbol=symbol, weight=D("0.2"), end_time=datetime(2026, 10, 12))
                                          for symbol in stocks])
    value._account_observations["2026-10-09"] = D(900000)
    class ActualTypedHistory:
        calls = []
        def __getitem__(self, kind):
            def call(census, *args, **kwargs):
                self.calls.append((kind, census, args, kwargs))
                if kind == "Split":
                    return []
                batch = Batch({symbol: NS(symbol=symbol, open=D(100), high=D(101), low=D(99), close=D(100),
                    end_time=datetime(2026, 10, 9, 16), time=datetime(2026, 10, 9, 9, 30),
                    period=timedelta(hours=6, minutes=30), is_fill_forward=False) for symbol in census})
                batch.time = datetime(2026, 10, 9, 16)
                return [batch]
            return call
    algorithm.history = ActualTypedHistory()
    algorithm.time = datetime(2026, 10, 12, 9, 20)
    value.on_before_open()
    binding = value._plans["2026-10-12"]["binding"]
    assert binding["sizing_nav"] == "900000" and binding["raw_reference_session"] == "2026-10-09"
    assert set(kind for kind, *_ in algorithm.history.calls) == {"TradeBar", "Split"}
    value.on_data(clock_slice(etfs["SPY"], algorithm.time))
    assert set(value._preopen_clock_confirmations) == {"2026-10-12"}
    assert not algorithm.submitted  # No order path or operational package invoked.


@pytest.mark.parametrize("which", ["cash", "initial_stock"])
def test_projected_first_decision_rejects_noninitial_capital(monkeypatch, which):
    value, algorithm, _, stocks, _, _, modules = projected_loaded_driver(monkeypatch)
    algorithm.time = datetime(2021, 1, 4, 9, 20)
    monkeypatch.setattr(value, "_reference_prices", lambda previous, census: {sid: D(100) for sid in census})
    if which == "cash":
        algorithm.portfolio.cash -= 1
    else:
        algorithm.portfolio[stocks[0]].quantity = D(1)
    with pytest.raises(modules["newrule_comparison_targets"].NewruleError, match="first_decision_cash_only"):
        value.on_before_open()


def test_account_aggregates_use_daily_not_monthly_drawdown_and_actual_date_cagr():
    sessions = ("2021-01-04", "2021-01-05", "2026-10-13")
    result = runtime.account_aggregates(dict(zip(sessions, (D(1000000), D(500000), D(1100000)))), sessions,
        [{"fee": "10.01"}, {"fee": "20.02"}], {"actual_engine_fee_amount": "1.03"})
    assert result["net_total_return"] == "0.100000000000"
    assert result["daily_close_max_drawdown"] == "-0.500000000000"
    assert result["total_engine_fees"] == "31.06"
    assert result["elapsed_calendar_days"] == (date(2026, 10, 13) - date(2021, 1, 4)).days
    expected = (1.1 ** (365.25 / result["elapsed_calendar_days"])) - 1
    assert abs(float(result["cagr"]) - expected) < 1e-12


@pytest.mark.parametrize("field,bad", [("terminal_nav", "1.000000"), ("net_total_return", "1.000000000000"),
    ("cagr", "1.000000000000"), ("daily_close_max_drawdown", "0.100000000000"),
    ("elapsed_calendar_days", 1), ("observed_close_count", 1), ("total_engine_fees", "2"),
    ("daily_drawdown_not_independently_reconstructed_from_monthly", False)])
def test_bound_account_aggregate_tampering_refuses(field, bad):
    stats, expected = result_fixture()
    meta = json.loads(stats[runtime.META_STATISTIC])
    meta["account_aggregates"][field] = bad
    stats[runtime.META_STATISTIC] = targets.canonical(meta).decode()
    with pytest.raises(targets.NewruleError):
        runtime.validate_result_statistics(stats, expected_profile=expected)
