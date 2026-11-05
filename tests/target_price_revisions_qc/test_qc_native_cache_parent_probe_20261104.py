"""Fully synthetic native-only parent/bootstrap input checks; no private reads."""
import ast
from datetime import datetime, timedelta
import hashlib
import inspect
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest

from research.target_price_revisions_qc import native_cache_parent_probe_20261104 as p

HELPER = Path(p.reader.__file__).read_bytes()  # exact public source, never a witness
OP = "TPR-CACHE-20261104-PARENT-SYNTHETIC"
HEAD = "a" * 40


def render(case="valid"):
    return p._build_fixture(helper_source=HELPER, operation_id=OP, git_head=HEAD, case=case)


def test_pure_renderer_is_fixed_deterministic_and_never_accepts_local_sid():
    raw, report_raw = render()
    assert (raw, report_raw) == render()
    report = json.loads(report_raw)
    assert report["main_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["main_bytes"] == len(raw) <= p.MAX_SOURCE_BYTES
    assert report["initialize_private_effects"] is False and report["local_raw_sid_supplied"] is False
    assert report["parent_contains_max"] == report["parent_reads_max"] == 1
    assert report["raw_witness_export_authorized"] is False
    assert all(report[key] is False for key in p.FLAGS)
    assert set(inspect.signature(p.build_cache_probe).parameters) == {
        "parent_probe_config_json", "helper_source", "operation_id", "git_head"}
    own = ast.parse(Path(p.__file__).read_bytes())
    assert not {n.attr for n in ast.walk(own) if isinstance(n, ast.Attribute)} & {
        "read_bytes", "read_text", "open", "download", "execute_plan", "execute_action"}
    generated = ast.parse(raw)
    attrs = {n.attr for n in ast.walk(generated) if isinstance(n, ast.Attribute)}
    assert {"contains_key", "read_bytes"} <= attrs
    assert not attrs & {"history", "market_order", "limit_order", "set_holdings", "liquidate",
        "remove_security", "set_market_price", "save", "price", "volume", "close", "cash", "total_portfolio_value"}


@pytest.mark.parametrize("config", [None, b"{}", "", "{}", "PRIVATEKEY", "{\"binding\":{}}", "x" * 65537])
def test_production_refuses_any_unpinned_parent_configuration_without_echo(config):
    with pytest.raises(p.ParentCacheRefusal, match="^fixed native-parent cache diagnostic refused$"):
        p.build_cache_probe(parent_probe_config_json=config, helper_source=HELPER, operation_id=OP, git_head=HEAD)


@pytest.mark.parametrize("changes", [{"helper_source": b"arbitrary code"}, {"operation_id": "other"},
    {"git_head": "0" * 40}, {"git_head": "A" * 40}, {"case": "arbitrary"}])
def test_fixture_cannot_supply_arbitrary_code_or_metadata(changes):
    with pytest.raises(p.ParentCacheRefusal):
        p._build_fixture(**{"helper_source": HELPER, "operation_id": OP, "git_head": HEAD, **changes})


@pytest.fixture
def native(monkeypatch):
    def make(case="valid"):
        state = NS(lock=False, registrations=[], logs=[], contains=[], reads=[], config_hook=lambda rows: rows,
            cache_hook=lambda security: security.last, contains_hook=lambda: None, read_hook=lambda: None,
            add_hook=lambda: None, cached_gets=0, present=True, raw=p._fixture_parent(case)[1])
        class Identifier:
            def __init__(self, text):
                self.text, self.symbol, self.security_type, self.market = text, text.split()[0], "equity", "usa"
            @staticmethod
            def parse(text): return Identifier(text)
            def __str__(self): return self.text
            def __eq__(self, other): return type(other) is Identifier and self.text == other.text
            def __hash__(self): return hash(self.text)
        class Symbol:
            def __init__(self, identity, value): self.id = identity
            def __eq__(self, other): return type(other) is Symbol and self.id == other.id
            def __hash__(self): return hash(self.id)
        class Config: pass
        class TradeBar:
            def __init__(self, symbol, ended):
                self.symbol, self.end_time, self.time = symbol, ended, ended-timedelta(minutes=1)
                self.period, self.is_fill_forward = timedelta(minutes=1), False
            @property
            def price(self): raise AssertionError("private price consumed")
            @property
            def volume(self): raise AssertionError("private volume consumed")
        class Slice:
            def __init__(self, bars=None): self.bars = {} if bars is None else bars
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
                        type=NS(FullName="QuantConnect.Data.Market."+kind), tick_type=tick)
                    self.configs.append(row)
            def get_last_data(self):
                state.cached_gets += 1
                return state.cache_hook(self)
        class Store:
            def contains_key(self, key):
                state.contains.append(key);state.contains_hook();return state.present
            def read_bytes(self, key):
                state.reads.append(key);state.read_hook();return state.raw
        class Algorithm:
            def __init__(self):
                self.project_id, self.algorithm_id, self.live_mode = p.PROJECT_ID, "", False
                self.is_warming_up, self.current_slice = False, Slice()
                self.time, self.utc_time = datetime(2021, 2, 8), datetime(2021, 2, 8, 5)
                self.settings, self.securities, self.portfolio, self.object_store = NS(), {}, {}, Store()
                self.subscription_manager = NS(subscription_data_config_service=NS(
                    get_subscription_data_configs=lambda symbol, include: state.config_hook(self.securities[symbol].configs)))
                self.schedule = NS(on=lambda rule, at, call: setattr(state, "callback", call))
                self.date_rules, self.time_rules = NS(every_day=lambda symbol: symbol), NS(at=lambda h, m: (h, m))
            def get_locked(self): return state.lock
            def set_time_zone(self, zone): state.zone = zone
            def set_start_date(self, *parts): state.start = parts
            def set_end_date(self, *parts): state.end = parts
            def set_benchmark(self, symbol): state.benchmark = symbol
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
                answer = self._add(symbol, kwargs);state.add_hook();return answer
            def log(self, text): state.logs.append(text)
        imports = ModuleType("AlgorithmImports")
        imports.__dict__.update(QCAlgorithm=Algorithm, SecurityIdentifier=Identifier, Symbol=Symbol,
            SecurityType=NS(EQUITY="equity"), Market=NS(USA="usa"), Resolution=NS(MINUTE="minute"),
            DataNormalizationMode=NS(RAW="raw"), TickType=NS(TRADE="trade", QUOTE="quote"), TradeBar=TradeBar, Slice=Slice)
        data, securities, system = ModuleType("QuantConnect.Data"), ModuleType("QuantConnect.Securities"), ModuleType("System")
        data.SubscriptionDataConfig, securities.Security = Config, Security
        system.Object = NS(ReferenceEquals=lambda a, b: a is b)
        for name, module in (("AlgorithmImports", imports), ("QuantConnect", ModuleType("QuantConnect")),
                ("QuantConnect.Data", data), ("QuantConnect.Securities", securities), ("System", system)):
            monkeypatch.setitem(sys.modules, name, module)
        source, _ = render(case)
        namespace = {};exec(compile(source, "synthetic_parent_cache.py", "exec"), namespace)
        algo = namespace["Main"]();algo.initialize()
        assert len(state.registrations) == 1 and not algo._disabled
        assert not state.contains and not state.reads
        state.lock, algo.algorithm_id = True, "b" * 32
        def at(day=8, hour=4, minute=1, empty=False):
            algo.time, algo.utc_time = datetime(2021, 2, day, hour, minute), datetime(2021, 2, day, hour+5, minute)
            bars = {}
            for label, security in algo._registered.items():
                ended = algo.time if label == "control" or hour < 16 else algo.time.replace(minute=0)
                security.last = TradeBar(security.symbol, ended)
                bars[security.symbol] = security.last
            algo.current_slice = Slice({} if empty else bars)
            return algo.current_slice
        at()
        return NS(state=state, algo=algo, namespace=namespace, at=at, Slice=Slice, TradeBar=TradeBar)
    return make


def test_locked_preopen_registration_then_five_close_checks_is_only_canary(native):
    n = native()
    n.algo.on_data(n.algo.current_slice)
    assert n.algo._target_ready and not n.algo._disabled and len(n.state.registrations) == 2
    assert len(n.state.contains) == len(n.state.reads) == 1
    assert n.state.contains[0] == n.state.reads[0]
    for day in range(8, 13):
        n.algo.on_data(n.at(day, 16, 1));n.state.callback()
    n.algo.on_end_of_algorithm()
    report = json.loads(n.state.logs[-1].split(" ", 1)[1])
    assert report["registration_before_open"] is True
    assert report["parent_hash_verified"] and report["parent_schema_verified"] and report["parent_sid_hash_verified"]
    assert report["close_checks"] == report["target_close_canary_days"] == 5
    assert report["object_store_calls"] == 2 and n.state.cached_gets == 30
    assert all(report[key] is False for key in p.FLAGS)
    assert "SYNTHETIC.CACHE" not in n.state.logs[-1] and n.state.reads[0] not in n.state.logs[-1]
    assert "security_id" not in n.state.logs[-1]


def test_quote_or_auxiliary_empty_slices_wait_with_zero_private_effects(native):
    n = native()
    for hour, minute in ((0, 1), (3, 59), (4, 1), (4, 2)):
        n.algo.on_data(n.at(8, hour, minute, empty=True))
        assert not n.algo._disabled and not n.state.contains and not n.state.reads
    n.algo.on_data(n.at(8, 4, 3))
    assert n.algo._target_ready and len(n.state.reads) == 1
    assert n.algo._report["preopen_empty_slices"] == 4


@pytest.mark.parametrize("fault", ["unlocked", "job", "live", "warmup", "project", "slice", "wrong_day",
    "post_open", "pre4_trade", "ff", "wrong_sid", "daily", "future", "stale", "nonraw", "foreign_trade"])
def test_invalid_first_trade_or_custody_never_reads_parent(native, fault):
    n = native();bar = next(iter(n.algo.current_slice.bars.values()))
    if fault == "unlocked": n.state.lock = False
    elif fault == "job": n.algo.algorithm_id = ""
    elif fault == "live": n.algo.live_mode = True
    elif fault == "warmup": n.algo.is_warming_up = True
    elif fault == "project": n.algo.project_id += 1
    elif fault == "slice": n.algo.current_slice = None
    elif fault == "wrong_day": n.at(9)
    elif fault == "post_open": n.at(8, 9, 30)
    elif fault == "pre4_trade": n.at(8, 3, 59)
    elif fault == "ff": bar.is_fill_forward = True
    elif fault == "wrong_sid": bar.symbol = object()
    elif fault == "daily": bar.period = timedelta(days=1)
    elif fault == "future": bar.time += timedelta(minutes=2);bar.end_time += timedelta(minutes=2)
    elif fault == "stale": bar.time -= timedelta(days=1);bar.end_time -= timedelta(days=1)
    elif fault == "nonraw": n.algo._registered["control"].configs[0].data_normalization_mode = "adjusted"
    elif fault == "foreign_trade": n.algo.current_slice.bars = {object(): bar}
    n.algo.on_data(n.algo.current_slice)
    assert n.algo._disabled and not n.state.contains and not n.state.reads
    assert len(n.state.registrations) == 1


@pytest.mark.parametrize("fault", ["absent", "unknown_present", "oversize", "hash", "read_exception", "contains_exception"])
def test_parent_failure_is_spent_once_and_never_exports_body(native, fault):
    n = native()
    if fault == "absent": n.state.present = False
    elif fault == "unknown_present": n.state.present = 1
    elif fault == "oversize": n.state.raw += b"x"
    elif fault == "hash": n.state.raw = b"x" * len(n.state.raw)
    elif fault == "read_exception": n.state.read_hook = lambda: (_ for _ in ()).throw(ValueError("PRIVATE BODY"))
    elif fault == "contains_exception": n.state.contains_hook = lambda: (_ for _ in ()).throw(ValueError("PRIVATE KEY"))
    n.algo.on_data(n.algo.current_slice)
    before = (len(n.state.contains), len(n.state.reads))
    n.algo.on_data(n.algo.current_slice)
    assert n.algo._disabled and before == (len(n.state.contains), len(n.state.reads))
    assert len(n.state.registrations) == 1 and len(n.state.contains) <= 1 and len(n.state.reads) <= 1
    n.algo.on_end_of_algorithm()
    assert "PRIVATE" not in n.state.logs[-1] and "SYNTHETIC.CACHE" not in n.state.logs[-1]


@pytest.mark.parametrize("case", ["wrong_schema", "wrong_sid", "wrong_clock"])
def test_hash_matched_but_invalid_parent_still_cannot_register(native, case):
    n = native(case);n.algo.on_data(n.algo.current_slice)
    assert n.algo._disabled and len(n.state.reads) == 1 and len(n.state.registrations) == 1
    assert n.algo._report["parent_hash_verified"] is True


@pytest.mark.parametrize("stage", ["contains", "read", "add"])
@pytest.mark.parametrize("fault", ["clock", "job", "slice", "bar_fields", "bar_reference", "config"])
def test_native_boundaries_reject_clock_custody_bar_or_config_mutation(native, stage, fault):
    n = native();control = n.algo._registered["control"]
    def mutate():
        if fault == "clock": n.algo.utc_time += timedelta(minutes=1)
        elif fault == "job": n.algo.algorithm_id = "c" * 32
        elif fault == "slice": n.algo.current_slice = n.Slice(dict(n.algo.current_slice.bars))
        elif fault == "bar_fields": n.algo.current_slice.bars[control.symbol].is_fill_forward = True
        elif fault == "bar_reference":
            old = n.algo.current_slice.bars[control.symbol]
            n.algo.current_slice.bars[control.symbol] = n.TradeBar(control.symbol, old.end_time)
        elif fault == "config": control.configs[0].data_normalization_mode = "adjusted"
    setattr(n.state, {"contains": "contains_hook", "read": "read_hook", "add": "add_hook"}[stage], mutate)
    n.algo.on_data(n.algo.current_slice)
    assert n.algo._disabled and not n.algo._target_ready
    assert n.algo._report["registration_before_open"] is False
    assert len(n.state.contains) <= 1 and len(n.state.reads) <= 1


def test_no_trade_before_open_and_excess_empty_slices_are_bootstrap_unproved(native):
    n = native()
    n.algo.on_data(n.at(8, 4, 1, empty=True));n.algo.on_data(n.at(8, 9, 30, empty=True))
    assert n.algo._disabled and not n.state.reads
    n.algo.on_end_of_algorithm()
    assert n.algo._report["target_close_canary_days"] == 0
    n = native()
    for _ in range(401): n.algo.on_data(n.at(8, 4, 1, empty=True))
    assert n.algo._disabled and not n.state.reads


def test_missing_target_close_never_becomes_financial_acceptance(native):
    n = native();n.algo.on_data(n.algo.current_slice)
    for day in range(8, 13):
        n.at(day, 16, 1);n.algo._registered["target"].last = None;n.state.callback()
    n.algo.on_end_of_algorithm()
    assert n.algo._report["close_checks"] == 5 and n.algo._report["target_close_canary_days"] == 0
    assert all(n.algo._report[key] is False for key in p.FLAGS)


def test_runtime_configuration_refusal_does_not_echo_private_metadata(native):
    n = native();n.namespace["CONFIG"]["operation_id"] = "PRIVATE UNTRUSTED"
    n.algo.on_data(n.algo.current_slice)
    n.algo.on_end_of_algorithm()
    assert n.algo._disabled and not n.state.reads and "PRIVATE" not in n.state.logs[-1]


@pytest.mark.parametrize("boundary", ["before_contains", "before_read", "after_registration"])
@pytest.mark.parametrize("fault", ["clock", "lock", "job", "slice", "bar_fields", "bar_reference", "security_reference", "control_config"])
def test_final_configuration_query_cannot_cross_parent_effect_or_registration_endpoint(native, boundary, fault):
    n = native();control = n.algo._registered["control"];calls = 0
    trigger = {"before_contains": 1, "before_read": 2, "after_registration": 7}[boundary]
    def query(rows):
        nonlocal calls
        calls += 1
        if calls == trigger:
            if fault == "clock":
                n.algo.time, n.algo.utc_time = datetime(2021, 2, 8, 9, 30), datetime(2021, 2, 8, 14, 30)
            elif fault == "lock": n.state.lock = False
            elif fault == "job": n.algo.algorithm_id = "d" * 32
            elif fault == "slice": n.algo.current_slice = n.Slice(dict(n.algo.current_slice.bars))
            elif fault == "bar_fields": n.algo.current_slice.bars[control.symbol].is_fill_forward = True
            elif fault == "bar_reference":
                prior = n.algo.current_slice.bars[control.symbol]
                n.algo.current_slice.bars[control.symbol] = n.TradeBar(control.symbol, prior.end_time)
            elif fault == "security_reference": n.algo.securities[control.symbol] = NS()
            elif fault == "control_config": control.configs[0].data_normalization_mode = "adjusted"
        return rows
    n.state.config_hook = query
    n.algo.on_data(n.algo.current_slice)
    assert n.algo._disabled and not n.algo._target_ready
    assert n.algo._report["registration_before_open"] is False
    if boundary == "before_contains": assert not n.state.contains and not n.state.reads
    elif boundary == "before_read": assert len(n.state.contains) == 1 and not n.state.reads
    else: assert len(n.state.contains) == len(n.state.reads) == 1
