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


def test_close_summary_preserves_the_first_failed_guard_context(native):
    n = native();n.at(8, 9, 30)
    n.algo.on_data(n.algo.current_slice)
    first = n.algo._report.get("first_failure_stage", n.algo._report["status"])
    n.state.callback()
    assert n.algo._report.get("first_failure_stage", n.algo._report["status"]) == first


def test_current_epoch_distinguishes_no_callback_from_failed_callback_and_disabled_skips(native):
    untouched = native();untouched.state.callback();untouched.algo.on_end_of_algorithm()
    no_entry = untouched.algo._report
    assert no_entry["schema"] == "tpr-native-parent-cache-observations-v4"
    assert no_entry["on_data_entries"] == no_entry["on_data_disabled_skips"] == 0
    assert no_entry["first_failure_stage"] == "close_without_bootstrap"
    assert no_entry["first_failure_code"] == "bootstrap_incomplete"
    assert no_entry["first_failure_category"] == "state"
    assert no_entry["terminal_summary"] == "incomplete_cache_observations"
    failed = native();failed.state.lock = False;failed.algo.on_data(failed.algo.current_slice)
    report = failed.algo._report
    assert report["on_data_entries"] == 1 and report["on_data_disabled_skips"] == 0
    assert failed.algo._slices == 0
    assert report["first_failure_stage"] == "waiting_custody"
    assert report["first_failure_code"] == "custody_locked"
    assert report["first_failure_category"] == "guard"
    first = {k: report[k] for k in ("first_failure_stage", "first_failure_code", "first_failure_category", "last_completed_stage")}
    failed.state.lock = True
    failed.algo.on_data(failed.algo.current_slice);failed.state.callback();failed.algo.on_end_of_algorithm()
    assert report["on_data_entries"] == 2 and report["on_data_disabled_skips"] == 1
    assert {k: report[k] for k in first} == first
    assert report["terminal_custody_passed"] is True
    assert not failed.state.contains and not failed.state.reads


@pytest.mark.parametrize("fault,stage,code", [
    ("late", "waiting_clock", "stage_failed"),
    ("slice_argument", "waiting_slice", "stage_failed"),
    ("foreign_control", "waiting_control", "stage_failed"),
    ("cache", "preopen_bar", "stage_failed"),
    ("configs", "preopen_configs", "stage_failed"),
    ("current_slice", "waiting_custody", "custody_current_slice")])
def test_earliest_guard_phase_is_preserved_without_private_error_payload(native, fault, stage, code):
    n = native();data = n.algo.current_slice
    if fault == "late": n.at(8, 9, 30);data = n.algo.current_slice
    elif fault == "slice_argument": data = n.Slice(dict(data.bars))
    elif fault == "foreign_control": data.bars = {object(): next(iter(data.bars.values()))}
    elif fault == "cache": next(iter(data.bars.values())).period = timedelta(days=1)
    elif fault == "configs":
        class PrivateError(AttributeError):
            def __str__(self): raise AssertionError("private exception string consumed")
        n.state.config_hook = lambda rows: (_ for _ in ()).throw(PrivateError("PRIVATE KEY/BODY"))
    elif fault == "current_slice": n.algo.current_slice = None
    n.algo.on_data(data)
    report = n.algo._report
    assert (report["first_failure_stage"], report["first_failure_code"]) == (stage, code)
    assert report["first_failure_category"] in p.FAILURE_CATEGORIES
    assert not n.state.contains and not n.state.reads
    n.state.callback();n.algo.on_end_of_algorithm()
    assert report["first_failure_stage"] == stage
    assert "PRIVATE" not in n.state.logs[-1] and "PrivateError" not in n.state.logs[-1]


def test_observability_counters_are_capped_and_cannot_trigger_a_private_retry(native):
    n = native();n.algo._report["on_data_entries"] = p.ON_DATA_ENTRY_MAX
    n.algo.on_data(n.algo.current_slice)
    report = n.algo._report
    assert report["on_data_entries"] == p.ON_DATA_ENTRY_MAX and report["on_data_entry_cap_reached"] is True
    assert report["on_data_disabled_skips"] == 1
    assert report["first_failure_code"] == "entry_budget_exceeded"
    report["on_data_disabled_skips"] = p.ON_DATA_ENTRY_MAX
    first = report["first_failure_stage"]
    n.algo.on_data(n.algo.current_slice)
    assert report["on_data_disabled_skips"] == p.ON_DATA_ENTRY_MAX
    assert report["on_data_disabled_skip_cap_reached"] is True and report["first_failure_stage"] == first
    assert not n.state.contains and not n.state.reads


def test_bound_ast_split_preserves_original_predicates_prelude_and_assignment():
    original = next(n for c in ast.parse(p.base.RUNTIME).body if isinstance(c, ast.ClassDef)
        for n in c.body if isinstance(n, ast.FunctionDef) and n.name == "_bound")
    rewritten = next(n for c in ast.parse(p._base_source()).body if isinstance(c, ast.ClassDef)
        for n in c.body if isinstance(n, ast.FunctionDef) and n.name == "_bound")
    dump = lambda n: ast.dump(n, include_attributes=False)
    assert [dump(n) for n in original.body[:2]] == [dump(n) for n in rewritten.body[:2]]
    assert dump(original.body[-1]) == dump(rewritten.body[-1])
    assert [dump(n) for n in original.body[2].test.values] == [dump(n.test) for n in rewritten.body[2:-1]]


@pytest.mark.parametrize("fault", ["valid_none", "valid_same", "algorithm", "live", "warmup", "slice",
    "project_type", "project", "locked", "job_type", "job_format", "job_changed"])
def test_bound_differential_trace_preserves_lazy_evaluation_and_native_call_counts(native, fault):
    n = native();original_node = next(m for c in ast.parse(p.base.RUNTIME).body if isinstance(c, ast.ClassDef)
        for m in c.body if isinstance(m, ast.FunctionDef) and m.name == "_bound")
    scopes = dict(n.namespace)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[original_node], type_ignores=[])), "original_bound.py", "exec"), scopes)
    original, rewritten = scopes["_bound"], n.namespace["CacheProbeBase"]._bound
    active = []
    original_match = scopes["re"].fullmatch
    def regex(*a, **k): active.append("regex_call");return original_match(*a, **k)
    scopes["re"] = n.namespace["re"] = NS(fullmatch=regex)
    parent = object if fault == "algorithm" else n.namespace["QCAlgorithm"]
    class Probe(parent):
        def __getattribute__(self, name):
            if name in ("_configuration", "algorithm_id", "live_mode", "is_warming_up", "current_slice",
                    "project_id", "get_locked", "_job"):
                active.append(name)
            return object.__getattribute__(self, name)
        def __setattr__(self, name, value):
            if name == "_job": active.append("assign_job")
            object.__setattr__(self, name, value)
        def _configuration(self): active.append("configuration_call")
        def get_locked(self): active.append("locked_call");return self._locked
    def execute(method):
        active.clear();obj = object.__new__(Probe)
        obj.__dict__.update(algorithm_id="b"*32, live_mode=False, is_warming_up=False,
            current_slice=n.Slice(), project_id=p.PROJECT_ID, _locked=True, _job=None)
        key, value = {"valid_same": ("_job", "b"*32), "live": ("live_mode", True),
            "warmup": ("is_warming_up", True), "slice": ("current_slice", None),
            "project_type": ("project_id", str(p.PROJECT_ID)), "project": ("project_id", p.PROJECT_ID+1),
            "locked": ("_locked", False), "job_type": ("algorithm_id", 1),
            "job_format": ("algorithm_id", "invalid"), "job_changed": ("_job", "c"*32)}.get(fault, ("unused", None))
        obj.__dict__[key] = value
        refused = False
        try: method(obj)
        except ValueError: refused = True
        return refused, list(active), obj.__dict__["_job"]
    assert execute(original) == execute(rewritten)


def test_config_field_refusal_has_a_closed_program_code_instead_of_broad_stage_failure(native):
    n = native()
    n.algo._registered["control"].configs[0].data_normalization_mode = "adjusted"
    n.algo.on_data(n.algo.current_slice)
    assert n.algo._report["first_failure_stage"] == "preopen_configs"
    assert n.algo._report["first_failure_code"] == "cfg_normalization"
    assert not n.state.contains and not n.state.reads


@pytest.mark.parametrize("fault,code", [("rows", "cfg_no_rows"), ("extra_rows", "cfg_extra_rows"), ("row_type", "cfg_row_type"),
    ("symbol", "cfg_row_symbol"), ("resolution", "cfg_resolution"), ("ff", "cfg_fill_forward"),
    ("normalization", "cfg_normalization"), ("extended", "cfg_extended"), ("internal", "cfg_internal"),
    ("custom", "cfg_custom"), ("exchange_tz", "cfg_exchange_tz"), ("data_tz", "cfg_data_tz"),
    ("kind", "cfg_kind_tick"), ("tick", "cfg_kind_tick"), ("trade_count", "cfg_trade_count")])
def test_native_config_refusal_codes_are_closed_and_read_no_parent(native, fault, code):
    n = native();security = n.algo._registered["control"];row = security.configs[0]
    if fault == "rows": security.configs = []
    elif fault == "extra_rows": security.configs.append(row)
    elif fault == "row_type": security.configs[0] = NS()
    elif fault == "symbol": row.symbol = object()
    elif fault == "resolution": row.resolution = "daily"
    elif fault == "ff": row.fill_data_forward = True
    elif fault == "normalization": row.data_normalization_mode = "adjusted"
    elif fault == "extended": row.extended_market_hours = False
    elif fault == "internal": row.is_internal_feed = True
    elif fault == "custom": row.is_custom_data = True
    elif fault == "exchange_tz": row.exchange_time_zone.id = "UTC"
    elif fault == "data_tz": row.data_time_zone.id = "UTC"
    elif fault == "kind": row.type.FullName = "PRIVATE CONFIGURATION TYPE"
    elif fault == "tick": row.tick_type = "quote"
    elif fault == "trade_count": row.type.FullName = "QuantConnect.Data.Market.QuoteBar";row.tick_type = "quote"
    n.algo.on_data(n.algo.current_slice)
    report = n.algo._report
    assert report["first_failure_stage"] == "preopen_configs"
    assert report["first_failure_code"] == code and code in p.CONFIG_CODES
    assert report["first_failure_category"] == "guard"
    assert not n.state.contains and not n.state.reads
    n.state.callback();n.algo.on_end_of_algorithm()
    assert report["first_failure_code"] == code and "PRIVATE" not in n.state.logs[-1]


@pytest.mark.parametrize("fault,code", [("count", "cfg_sec_count"), ("type", "cfg_sec_type"),
    ("symbol", "cfg_sec_symbol"), ("reference", "cfg_sec_ref")])
def test_registered_security_component_guards_keep_their_exact_codes(native, fault, code):
    n = native();security = n.algo._registered["control"];symbol = security.symbol;provided = security
    if fault == "count": n.algo.securities[object()] = NS()
    elif fault == "type": provided = NS()
    elif fault == "symbol": security.symbol = object()
    elif fault == "reference": n.algo.securities[symbol] = NS()
    with pytest.raises(n.namespace["DiagnosticGuardRefusal"]) as captured:
        n.algo._bootstrap_configs("control", symbol, provided)
    assert captured.value.code == code
    assert not n.state.contains and not n.state.reads


def test_config_ast_split_preserves_every_original_guard_predicate():
    original = next(n for c in ast.parse(p.base.RUNTIME).body if isinstance(c, ast.ClassDef)
        for n in c.body if isinstance(n, ast.FunctionDef) and n.name == "_configs")
    rewritten = next(n for c in ast.parse(p._base_source()).body if isinstance(c, ast.ClassDef)
        for n in c.body if isinstance(n, ast.FunctionDef) and n.name == "_configs")
    def old_message(body):
        if (len(body) == 1 and isinstance(body[0], ast.Raise) and isinstance(body[0].exc, ast.Call)
                and isinstance(body[0].exc.func, ast.Name) and body[0].exc.func.id == "ValueError"):
            return body[0].exc.args[0].value
    actual, count_checked = {}, False
    for node in ast.walk(rewritten):
        if (isinstance(node, ast.If) and len(node.body) == 1 and isinstance(node.body[0], ast.Raise)
                and isinstance(node.body[0].exc, ast.Call) and isinstance(node.body[0].exc.func, ast.Name)
                and node.body[0].exc.func.id == "DiagnosticGuardRefusal"):
            selected = node.body[0].exc.args[0]
            if isinstance(selected, ast.Constant):
                actual[selected.value] = ast.dump(node.test, include_attributes=False)
            else:
                assert isinstance(selected, ast.IfExp)
                assert (selected.body.value, selected.orelse.value) == ("cfg_no_rows", "cfg_extra_rows")
                assert ast.dump(selected.test, include_attributes=False) == ast.dump(
                    ast.parse("len(rows) == 0", mode="eval").body, include_attributes=False)
                original_count = next(item for item in ast.walk(original)
                    if isinstance(item, ast.If) and old_message(item.body) == "configuration count unproved")
                assert ast.dump(node.test, include_attributes=False) == ast.dump(original_count.test, include_attributes=False)
                count_checked = True
    for node in ast.walk(original):
        if isinstance(node, ast.If) and old_message(node.body) in p.CONFIG_SPLITS:
            for code, predicate in zip(p.CONFIG_SPLITS[old_message(node.body)], node.test.values):
                assert actual[code] == ast.dump(predicate, include_attributes=False)
    assert count_checked


def test_only_the_unused_base_terminal_method_is_newly_pruned(native):
    n = native();raw, _ = render()
    original = next(c for c in ast.parse(p.base.RUNTIME).body if isinstance(c, ast.ClassDef))
    rewritten = next(c for c in ast.parse(p._base_source()).body if isinstance(c, ast.ClassDef))
    source_main = next(c for c in ast.parse(p.RUNTIME).body if isinstance(c, ast.ClassDef) and c.name == "Main")
    rendered_main = next(c for c in ast.parse(raw).body if isinstance(c, ast.ClassDef) and c.name == "Main")
    old = {m.name: m for m in original.body if isinstance(m, ast.FunctionDef)}
    new = {m.name: m for m in rewritten.body if isinstance(m, ast.FunctionDef)}
    assert set(new) == set(old)-{"initialize", "_configuration", "on_end_of_algorithm"}|{"_bootstrap_configs"}
    for name in set(new)-{"_bound", "_configs", "_bootstrap_configs"}:
        assert ast.dump(new[name], include_attributes=False) == ast.dump(old[name], include_attributes=False)
    assert ast.dump(source_main, include_attributes=False) == ast.dump(rendered_main, include_attributes=False)
    assert "on_end_of_algorithm" in n.namespace["Main"].__dict__
    assert "on_end_of_algorithm" not in n.namespace["CacheProbeBase"].__dict__
    assert n.algo.on_end_of_algorithm.__func__ is n.namespace["Main"].__dict__["on_end_of_algorithm"]
    assert len(raw) <= 59900 < p.MAX_SOURCE_BYTES == 60000


@pytest.mark.parametrize("fault", ["valid", "security_count", "security_type", "security_symbol", "security_reference",
    "row_count", "row_excess", "row_type", "row_symbol", "resolution", "ff", "normalization", "extended", "internal", "custom",
    "exchange_tz", "data_tz", "kind", "tick", "trade_count"])
def test_config_differential_trace_preserves_lazy_fields_and_sdk_call_counts(native, fault):
    n = native();original_node = next(m for c in ast.parse(p.base.RUNTIME).body if isinstance(c, ast.ClassDef)
        for m in c.body if isinstance(m, ast.FunctionDef) and m.name == "_configs")
    scopes = dict(n.namespace)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[original_node], type_ignores=[])), "original_configs.py", "exec"), scopes)
    original, rewritten = scopes["_configs"], n.namespace["CacheProbeBase"]._configs
    active = []
    def reference(a, b): active.append("reference_call");return a is b
    scopes["NetObject"] = n.namespace["NetObject"] = NS(ReferenceEquals=reference)
    class TraceSecurity(n.namespace["Security"]):
        def __getattribute__(self, name):
            if name == "symbol": active.append("security.symbol")
            return object.__getattribute__(self, name)
    class TraceConfig(n.namespace["SubscriptionDataConfig"]):
        def __getattribute__(self, name):
            if name in ("symbol", "resolution", "fill_data_forward", "data_normalization_mode", "extended_market_hours",
                    "is_internal_feed", "is_custom_data", "exchange_time_zone", "data_time_zone", "type", "tick_type"):
                active.append("row."+name)
            return object.__getattribute__(self, name)
    class TraceDict(dict):
        def __len__(self): active.append("security_count");return super().__len__()
        def __getitem__(self, key): active.append("security_lookup");return super().__getitem__(key)
    class Context:
        _config_values = n.namespace["CacheProbeBase"]._config_values
    def execute(method):
        source = n.algo._registered["control"];symbol = source.symbol
        security = object.__new__(TraceSecurity);security.__dict__.update(source.__dict__)
        rows = []
        for old in source.configs:
            row = object.__new__(TraceConfig);row.__dict__.update(old.__dict__)
            row.type = NS(FullName=old.type.FullName)
            row.exchange_time_zone, row.data_time_zone = NS(id=old.exchange_time_zone.id), NS(id=old.data_time_zone.id)
            rows.append(row)
        provided = security;ctx = Context();ctx.securities = TraceDict({symbol: security, object(): NS()})
        row = rows[0]
        if fault == "security_count": ctx.securities.pop(next(key for key in ctx.securities if key != symbol))
        elif fault == "security_type": provided = NS()
        elif fault == "security_symbol": security.symbol = object()
        elif fault == "security_reference": ctx.securities[symbol] = NS()
        elif fault == "row_count": rows = []
        elif fault == "row_excess": rows.append(rows[0])
        elif fault == "row_type": rows[0] = NS()
        elif fault == "row_symbol": row.symbol = object()
        elif fault == "resolution": row.resolution = "daily"
        elif fault == "ff": row.fill_data_forward = True
        elif fault == "normalization": row.data_normalization_mode = "adjusted"
        elif fault == "extended": row.extended_market_hours = False
        elif fault == "internal": row.is_internal_feed = True
        elif fault == "custom": row.is_custom_data = True
        elif fault == "exchange_tz": row.exchange_time_zone.id = "UTC"
        elif fault == "data_tz": row.data_time_zone.id = "UTC"
        elif fault == "kind": row.type.FullName = "Unknown"
        elif fault == "tick": row.tick_type = "quote"
        elif fault == "trade_count": row.type.FullName = "QuantConnect.Data.Market.QuoteBar";row.tick_type = "quote"
        class Stream:
            def __init__(self): self.iterator = iter(rows)
            def __iter__(self): active.append("stream_iter");return self
            def __next__(self): active.append("stream_next");return next(self.iterator)
        def query(*args): active.append("config_service");return Stream()
        ctx.subscription_manager = NS(subscription_data_config_service=NS(get_subscription_data_configs=query))
        active.clear();accepted, frames = True, None
        try:
            actual_rows, frames = method(ctx, "control", symbol, provided)
            assert len(actual_rows) == len(rows)
        except ValueError: accepted = False
        return accepted, list(active), frames
    assert execute(original) == execute(rewritten)
