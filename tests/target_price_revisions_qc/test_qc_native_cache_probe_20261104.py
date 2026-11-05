"""Synthetic native-cache canary only; no private identity or native effects."""
import ast
from datetime import datetime, timedelta
import hashlib
import inspect
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest

from research.target_price_revisions_qc import native_cache_probe_20261104 as p

OPERATION = "TPR-CACHE-20261104-SYNTHETIC-001"
HEAD = "a" * 40


def render():
    return p._build_fixture(operation_id=OPERATION, git_head=HEAD)


def test_builder_is_deterministic_fixed_and_never_a_dispatcher():
    raw, report = render()
    assert (raw, report) == render()
    metadata = json.loads(report)
    assert metadata["main_bytes"] == len(raw) <= p.MAX_SOURCE_BYTES
    assert metadata["main_sha256"] == hashlib.sha256(raw).hexdigest()
    assert metadata["sessions"] == [f"2021-02-{day:02d}" for day in range(8, 13)]
    assert metadata["max_securities"] == 2 and metadata["native_requests_dispatched"] == 0
    assert all(metadata[key] is False for key in p.FLAGS)
    assert metadata["input_canary_only"] is True
    compile(ast.parse(raw), "main.py", "exec")
    signature = inspect.signature(p.build_cache_probe)
    assert set(signature.parameters) == {"target_sid_text", "operation_id", "git_head"}
    tree = ast.parse(raw)
    names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not names & {"history", "object_store", "download", "market_order", "limit_order",
        "set_holdings", "liquidate", "remove_security", "set_market_price", "save", "price", "volume",
        "close", "cash", "total_portfolio_value", "maximum_data_points_per_chart_series"}
    own_tree = ast.parse(Path(p.__file__).read_bytes())
    imports = {node.name for item in ast.walk(own_tree) if isinstance(item, ast.Import) for node in item.names}
    assert imports <= {"ast", "hashlib", "json", "re"}


@pytest.mark.parametrize("target", [None, 1, b"SYNTHETIC.CACHE 1", "", "SYNTHETIC.CACHE 1",
    "OTHER 1", "SPY", "bad\nSID 1", "bad|SID 1", "bad 9999999999999", "bad \u2603"])
def test_production_rejects_unbound_identity_without_echo(target):
    with pytest.raises(p.CacheProbeRefusal, match="^fixed prospective cache diagnostic refused$"):
        p.build_cache_probe(target_sid_text=target, operation_id=OPERATION, git_head=HEAD)


@pytest.mark.parametrize("changes", [{"operation_id": "foreign"}, {"operation_id": OPERATION + "_"},
    {"git_head": "0" * 40}, {"git_head": "A" * 40}, {"git_head": None}])
def test_fixture_does_not_relax_operation_or_head_framing(changes):
    args = {"operation_id": OPERATION, "git_head": HEAD, **changes}
    with pytest.raises(p.CacheProbeRefusal):
        p._build_fixture(**args)


@pytest.fixture
def native(monkeypatch):
    state = NS(registrations=[], clock_reads=[], logs=[], config_hook=lambda rows: rows,
        cache_hook=lambda security: security.last, cached_gets=0, lock=False)
    class Identifier:
        def __init__(self, text):
            self.text, self.symbol, self.security_type, self.market = text, text.split()[0], "equity", "usa"
        @staticmethod
        def parse(text):
            return Identifier(text)
        def __str__(self):
            return self.text
        def __eq__(self, other):
            return type(other) is Identifier and self.text == other.text
        def __hash__(self):
            return hash(self.text)
    class Symbol:
        def __init__(self, identity, value):
            self.id = identity
        def __eq__(self, other):
            return type(other) is Symbol and self.id == other.id
        def __hash__(self):
            return hash(self.id)
    class Config:
        pass
    class TradeBar:
        def __init__(self, symbol, ended):
            self.symbol, self.end_time, self.time = symbol, ended, ended-timedelta(minutes=1)
            self.period, self.is_fill_forward = timedelta(minutes=1), False
        @property
        def price(self):
            raise AssertionError("price must never be consumed")
        @property
        def volume(self):
            raise AssertionError("volume must never be consumed")
    class Security:
        def __init__(self, symbol, extended):
            self.symbol, self.last = symbol, None
            self.exchange = NS(hours=NS(get_next_market_close=lambda day, ext: day.replace(hour=16)))
            self.configs = []
            for kind, tick in (("TradeBar", "trade"), ("QuoteBar", "quote")):
                row = Config()
                row.__dict__.update(symbol=symbol, resolution="minute", fill_data_forward=False,
                    data_normalization_mode="raw", extended_market_hours=extended,
                    is_internal_feed=False, is_custom_data=False,
                    exchange_time_zone=NS(id="America/New_York"), data_time_zone=NS(id="America/New_York"),
                    type=NS(FullName="QuantConnect.Data.Market." + kind), tick_type=tick)
                self.configs.append(row)
        def get_last_data(self):
            state.cached_gets += 1
            return state.cache_hook(self)
    class Slice:
        bars = []
    class Algorithm:
        def __init__(self):
            self.project_id, self.algorithm_id, self.live_mode = p.PROJECT_ID, "b" * 32, False
            self.is_warming_up, self.current_slice = False, Slice()
            self.settings, self.securities, self.portfolio = NS(), {}, {}
            self.subscription_manager = NS(subscription_data_config_service=NS(
                get_subscription_data_configs=lambda symbol, include: state.config_hook(self.securities[symbol].configs)))
            self.schedule = NS(on=lambda rule, at, call: setattr(state, "callback", call))
            self.date_rules, self.time_rules = NS(every_day=lambda symbol: symbol), NS(at=lambda h, m: (h, m))
        def get_locked(self):
            return state.lock
        def set_time_zone(self, zone):
            state.zone = zone
        def set_start_date(self, *parts):
            state.start = parts
        def set_end_date(self, *parts):
            state.end = parts
        def set_benchmark(self, symbol):
            state.benchmark = symbol
        def _add(self, symbol, kwargs):
            state.registrations.append((symbol, kwargs))
            security = Security(symbol, kwargs["extended_market_hours"])
            self.securities[symbol], self.portfolio[symbol] = security, NS(quantity=0.0)
            return security
        def add_equity(self, ticker, resolution, **kwargs):
            assert ticker == "SPY" and resolution == "minute"
            return self._add(Symbol(Identifier("SYNTHETIC.SPY 2"), "SPY"), kwargs)
        def add_security(self, symbol, **kwargs):
            assert kwargs["resolution"] == "minute"
            return self._add(symbol, kwargs)
        def log(self, wire):
            state.logs.append(wire)
    imports = ModuleType("AlgorithmImports")
    imports.__dict__.update(QCAlgorithm=Algorithm, SecurityIdentifier=Identifier, Symbol=Symbol,
        SecurityType=NS(EQUITY="equity"), Market=NS(USA="usa"), Resolution=NS(MINUTE="minute"),
        DataNormalizationMode=NS(RAW="raw"), TickType=NS(TRADE="trade", QUOTE="quote"),
        TradeBar=TradeBar, Slice=Slice)
    data, securities, system = ModuleType("QuantConnect.Data"), ModuleType("QuantConnect.Securities"), ModuleType("System")
    data.SubscriptionDataConfig, securities.Security = Config, Security
    system.Object = NS(ReferenceEquals=lambda a, b: a is b)
    for name, module in (("AlgorithmImports", imports), ("QuantConnect", ModuleType("QuantConnect")),
            ("QuantConnect.Data", data), ("QuantConnect.Securities", securities), ("System", system)):
        monkeypatch.setitem(sys.modules, name, module)
    source, _ = render()
    namespace = {}
    exec(compile(source, "synthetic_cache_main.py", "exec"), namespace)
    algo = namespace["Main"]()
    algo.initialize()
    assert len(state.registrations) == 2 and not algo._disabled
    state.lock = True
    def at(day=10):
        algo.time, algo.utc_time = datetime(2021, 2, day, 16, 1), datetime(2021, 2, day, 21, 1)
        for label, security in algo._registered.items():
            security.last = TradeBar(security.symbol, datetime(2021, 2, day, 16, 1 if label == "control" else 0))
    at()
    return NS(state=state, algo=algo, namespace=namespace, at=at, Slice=Slice, TradeBar=TradeBar)


def test_five_prospective_close_checks_positive_is_only_an_input_canary(native):
    n = native
    assert n.state.start == (2021, 2, 8) and n.state.end == (2021, 2, 12)
    assert n.state.zone == "America/New_York"
    assert all(row[1]["fill_forward"] is False and row[1]["data_normalization_mode"] == "raw"
        for row in n.state.registrations)
    for day in range(8, 13):
        n.at(day)
        n.algo.on_data(n.Slice())
        n.state.callback()
    n.algo.on_end_of_algorithm()
    report = json.loads(n.state.logs[-1].split(" ", 1)[1])
    assert report["status"] == "complete_cache_observations"
    assert report["close_checks"] == report["target_close_canary_days"] == 5
    assert n.state.cached_gets == 30  # three reads x two securities x five fixed checks
    assert report["cache_reads_per_check_max"] == report["config_reads_per_check_max"] == 3
    assert report["native_close_reads_per_check_max"] == 2
    assert all(report[key] is False for key in p.FLAGS)
    assert all(row["target"]["now_minus_end_microseconds"] == 60000000 for row in report["sessions"].values())
    assert all(row["target"]["quantity_type"] == "python_float" for row in report["sessions"].values())
    assert "SYNTHETIC.CACHE" not in n.state.logs[-1] and "SYNTHETIC.SPY" not in n.state.logs[-1]


@pytest.mark.parametrize("fault", ["missing", "quote", "wrong_sid", "fill_forward", "daily", "future",
    "stale_day", "wrong_period", "cache_changed", "nonraw", "config_ff", "wrong_extended",
    "config_type", "too_many_configs", "security_changed", "unknown_quantity"])
def test_dangerous_cache_config_and_representation_cases_never_prove_freshness(native, fault):
    n = native
    security = n.algo._registered["target"]
    bar, row = security.last, security.configs[0]
    if fault == "missing": security.last = None
    elif fault == "quote": security.last = NS(secret="PRIVATE QUOTE VALUE")
    elif fault == "wrong_sid": bar.symbol = n.algo._symbols["control"]
    elif fault == "fill_forward": bar.is_fill_forward = True
    elif fault == "daily": bar.period = timedelta(days=1)
    elif fault == "future": bar.time += timedelta(minutes=2); bar.end_time += timedelta(minutes=2)
    elif fault == "stale_day": bar.time -= timedelta(days=1); bar.end_time -= timedelta(days=1)
    elif fault == "wrong_period": bar.time -= timedelta(seconds=1)
    elif fault == "cache_changed": n.state.cache_hook = lambda sec: n.TradeBar(sec.symbol, sec.last.end_time)
    elif fault == "nonraw": row.data_normalization_mode = "adjusted"
    elif fault == "config_ff": row.fill_data_forward = True
    elif fault == "wrong_extended": row.extended_market_hours = True
    elif fault == "config_type": row.type.FullName = "PRIVATE-TYPE"
    elif fault == "too_many_configs": security.configs.append(row)
    elif fault == "security_changed": n.algo.securities[security.symbol] = NS()
    elif fault == "unknown_quantity":
        class PrivateQuantity:
            def __str__(self): raise AssertionError("private quantity string consumed")
        n.algo.portfolio[security.symbol].quantity = PrivateQuantity()
    n.algo._check_close()
    cell = n.algo._report["sessions"]["2021-02-10"]["target"]
    assert cell["freshness_canary"] is (fault == "unknown_quantity")
    if fault == "unknown_quantity":
        assert cell["quantity_type"] == "unknown"
    n.algo.on_end_of_algorithm()
    assert "PRIVATE" not in n.state.logs[-1]
    assert all(n.algo._report[key] is False for key in p.FLAGS)


@pytest.mark.parametrize("fault", ["project", "job", "unlocked", "live", "late", "utc", "duplicate", "slice", "warmup"])
def test_custody_clock_and_duplicate_callbacks_fail_closed(native, fault):
    n = native
    if fault == "project": n.algo.project_id += 1
    elif fault == "job": n.algo.algorithm_id = "not-native"
    elif fault == "unlocked": n.state.lock = False
    elif fault == "live": n.algo.live_mode = True
    elif fault == "late": n.algo.time += timedelta(minutes=1); n.algo.utc_time += timedelta(minutes=1)
    elif fault == "utc": n.algo.utc_time += timedelta(minutes=1)
    elif fault == "duplicate": n.algo._check_close()
    elif fault == "slice": n.algo.current_slice = None
    elif fault == "warmup": n.algo.is_warming_up = True
    prior = len(n.algo._report["sessions"])
    n.algo._check_close()
    assert n.algo._disabled and len(n.algo._report["sessions"]) == prior
    assert n.algo._report["status"] == "native_scope_unproved"


def test_complete_observations_can_have_no_positive_target_cache(native):
    n = native
    for day in range(8, 13):
        n.at(day)
        n.algo._registered["target"].last = None
        n.algo._check_close()
    n.algo.on_end_of_algorithm()
    assert n.algo._report["status"] == "complete_cache_observations"
    assert n.algo._report["target_close_canary_days"] == 0
    assert all(n.algo._report[key] is False for key in p.FLAGS)


def test_corrupt_runtime_configuration_never_echoes_changed_private_metadata(native):
    n = native
    n.namespace["CONFIG"]["operation_id"] = "PRIVATE-UNVALIDATED-METADATA"
    algo = n.namespace["Main"]()
    n.state.lock = False
    algo.initialize()
    assert algo._disabled and algo._report["operation_id"] is None
    n.state.lock = True
    algo.on_end_of_algorithm()
    assert "PRIVATE" not in n.state.logs[-1]


@pytest.mark.parametrize("fault", ["fill_forward", "previous_day", "period"])
def test_same_cache_object_mutation_on_second_getter_never_proves_freshness(native, fault):
    n = native
    target = n.algo._registered["target"]
    original, target_reads = target.last, 0
    def mutate(security):
        nonlocal target_reads
        if security is target:
            target_reads += 1
            if target_reads == 2:
                if fault == "fill_forward": security.last.is_fill_forward = True
                elif fault == "previous_day":
                    security.last.time -= timedelta(days=1)
                    security.last.end_time -= timedelta(days=1)
                else: security.last.period = timedelta(days=1)
        return security.last
    n.state.cache_hook = mutate
    n.algo._check_close()
    cell = n.algo._report["sessions"]["2021-02-10"]["target"]
    assert target_reads == 3 and target.last is original
    assert cell["cache_reference_unchanged"] is True
    assert cell["freshness_canary"] is False
    assert cell["cache_values_unchanged"] is False


def test_same_config_objects_valid_trade_quote_role_swap_is_not_unchanged(native):
    n = native
    target = n.algo._registered["target"]
    original, reads = tuple(target.configs), 0
    def mutate(rows):
        nonlocal reads
        if rows is target.configs:
            reads += 1
            if reads == 2:
                a, b = rows
                a.type.FullName, b.type.FullName = b.type.FullName, a.type.FullName
                a.tick_type, b.tick_type = b.tick_type, a.tick_type
        return rows
    n.state.config_hook = mutate
    n.algo._check_close()
    cell = n.algo._report["sessions"]["2021-02-10"]["target"]
    assert reads == 3 and all(a is b for a, b in zip(original, target.configs))
    assert cell["status"] == "bounded_cache_observation"  # both inventories satisfy field predicates
    assert cell["configuration_unchanged"] is False
    assert cell["freshness_canary"] is False


@pytest.mark.parametrize("fault", ["cache_fields", "config_fields"])
def test_in_place_mutation_during_final_native_close_query_is_also_detected(native, fault):
    n = native
    target, calls = n.algo._registered["target"], 0
    def close(day, extended):
        nonlocal calls
        calls += 1
        if calls == 2:
            if fault == "cache_fields": target.last.is_fill_forward = True
            else:
                a, b = target.configs
                a.type.FullName, b.type.FullName = b.type.FullName, a.type.FullName
                a.tick_type, b.tick_type = b.tick_type, a.tick_type
        return day.replace(hour=16)
    target.exchange.hours.get_next_market_close = close
    n.algo._check_close()
    cell = n.algo._report["sessions"]["2021-02-10"]["target"]
    assert calls == 2 and cell["native_close_unchanged"] is True
    assert cell["freshness_canary"] is False
    assert cell["cache_values_unchanged" if fault == "cache_fields" else "configuration_unchanged"] is False


@pytest.mark.parametrize("fault", ["algorithm_utc", "native_close"])
def test_endpoint_clock_changes_do_not_admit_the_initial_fresh_cache(native, fault):
    n = native
    target, calls = n.algo._registered["target"], 0
    if fault == "algorithm_utc":
        def cache(security):
            nonlocal calls
            if security is target:
                calls += 1
                if calls == 2: n.algo.utc_time += timedelta(minutes=1)
            return security.last
        n.state.cache_hook = cache
    else:
        def close(day, extended):
            nonlocal calls
            calls += 1
            return day.replace(hour=16, minute=1 if calls == 2 else 0)
        target.exchange.hours.get_next_market_close = close
    cell = n.algo._observe("target", n.namespace["clock"](n.algo.utc_time, "UTC"), n.algo.time.date())
    assert calls == (3 if fault == "algorithm_utc" else 2) and cell["end_equals_close"] is True
    assert cell["freshness_canary"] is False


@pytest.mark.parametrize("fault", ["replacement_stale", "replacement_ff", "quote_tick_unknown"])
def test_final_close_cache_replacement_and_unknown_quote_tick_cannot_escape(native, fault):
    n = native
    target, calls = n.algo._registered["target"], 0
    original = target.last
    def close(day, extended):
        nonlocal calls
        calls += 1
        if calls == 2:
            if fault == "quote_tick_unknown": target.configs[1].tick_type = "unknown"
            else:
                target.last = n.TradeBar(target.symbol, original.end_time)
                if fault == "replacement_stale":
                    target.last.time -= timedelta(days=1)
                    target.last.end_time -= timedelta(days=1)
                else: target.last.is_fill_forward = True
        return day.replace(hour=16)
    target.exchange.hours.get_next_market_close = close
    n.algo._check_close()
    cell = n.algo._report["sessions"]["2021-02-10"]["target"]
    assert calls == 2 and cell["end_equals_close"] is True
    assert cell["freshness_canary"] is False
    if fault != "quote_tick_unknown":
        assert target.last is not original and cell["cache_reference_unchanged"] is False


@pytest.mark.parametrize("fault", ["cache_at_endpoint_config", "quote_at_endpoint_cache", "registration_at_endpoint_cache"])
def test_declared_endpoint_rechecks_current_cache_config_fields_and_registered_identity(native, fault):
    n = native
    target, cache_reads, config_reads = n.algo._registered["target"], 0, 0
    def configs(rows):
        nonlocal config_reads
        if rows is target.configs:
            config_reads += 1
            if config_reads == 3 and fault == "cache_at_endpoint_config":
                target.last = n.TradeBar(target.symbol, target.last.end_time-timedelta(days=1))
        return rows
    def cache(security):
        nonlocal cache_reads
        if security is target:
            cache_reads += 1
            if cache_reads == 3:
                if fault == "quote_at_endpoint_cache": target.configs[1].tick_type = "unknown"
                elif fault == "registration_at_endpoint_cache": n.algo.securities[target.symbol] = NS()
        return security.last
    n.state.config_hook, n.state.cache_hook = configs, cache
    n.algo._check_close()
    cell = n.algo._report["sessions"]["2021-02-10"]["target"]
    assert config_reads == cache_reads == 3 and cell["status"] == "bounded_cache_observation"
    assert cell["freshness_canary"] is False
    if fault == "quote_at_endpoint_cache": assert cell["configuration_unchanged"] is False
    if fault == "registration_at_endpoint_cache": assert cell["registered_security_unchanged"] is False
