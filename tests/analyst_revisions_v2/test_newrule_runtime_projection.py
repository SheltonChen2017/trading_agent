"""Synthetic LEAN-shaped behavior only; no operational package/provider/QC."""

import ast
import dataclasses
import hashlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import IntEnum
from pathlib import Path
from types import SimpleNamespace as NS

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
            get_last_data=lambda: NS(end_time=algorithm.time),
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
        order_status_enum=Status, order_status_to_int=int, split_occurred_type="occurred", split_data_type="Split")
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


@pytest.mark.parametrize("failure", ["fee", "partial", "clock", "holding", "live", "stale"])
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
    assert kind == "Split" and args[1] == datetime(2026, 10, 12)
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


@pytest.mark.parametrize("failure", ["future", "factor", "identity", "callback", "duplicate", "bound"])
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
