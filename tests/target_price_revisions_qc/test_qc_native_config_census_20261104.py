"""Hermetic configuration-census fixtures; no private input or native access."""
import ast
from datetime import datetime, timedelta
from enum import IntEnum
import hashlib
import inspect
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest

from research.target_price_revisions_qc import native_config_census_20261104 as p

OP = "TPR-CONFIG-CENSUS-20261104-SYNTHETIC"
HEAD = "a" * 40


def render(): return p.build_config_census(operation_id=OP, git_head=HEAD)


def test_pure_fixed_builder_has_no_private_or_financial_input_or_effect_path():
    raw, report_raw = render();report = json.loads(report_raw)
    assert (raw, report_raw) == render()
    assert set(inspect.signature(p.build_config_census).parameters) == {"operation_id", "git_head"}
    assert report["project_id"] == 38609822 and report["main_bytes"] == len(raw) <= 60000
    assert report["main_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["max_config_queries"] == 1 and report["max_next_calls"] == 9
    assert report["max_rows"] == 8 and report["max_index_reads"] == 16
    assert all(report[key] is False for key in p.FLAGS)
    attrs = {n.attr for n in ast.walk(ast.parse(raw)) if isinstance(n, ast.Attribute)}
    assert not attrs & {"object_store", "history", "download", "market_order", "limit_order", "set_holdings",
        "liquidate", "set_market_price", "remove_security", "portfolio", "price", "volume", "close", "cash"}
    assert b"target_sid_text" not in raw and b"PARENT_" not in raw
    source_clock = next(n for n in ast.parse(p.base.RUNTIME).body if isinstance(n, ast.FunctionDef) and n.name == "clock")
    emitted_clock = next(n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == "clock")
    assert ast.dump(source_clock, include_attributes=False) == ast.dump(emitted_clock, include_attributes=False)


@pytest.mark.parametrize("changes", [{"operation_id": "foreign"}, {"operation_id": OP+"_"},
    {"git_head": "0"*40}, {"git_head": "A"*40}, {"git_head": None}])
def test_invalid_metadata_is_refused_without_input_echo(changes):
    with pytest.raises(p.CensusRefusal, match="^fixed native configuration census refused$"):
        p.build_config_census(**{"operation_id": OP, "git_head": HEAD, **changes})


@pytest.fixture
def native(monkeypatch):
    state = NS(lock=False, rows=[], logs=[], registrations=[], queries=0, next_calls=0, index_reads=0,
        count_reads=0, query_hook=lambda: None, next_hook=lambda: None, count_hook=lambda: None,
        index_hook=lambda: None, field_hook=lambda row, attr, count: None, fields={}, collection="indexed")
    class Resolution(IntEnum): MINUTE=0;SECOND=1;DAILY=4
    class Mode(IntEnum): RAW=0;ADJUSTED=1
    class Identifier:
        def __eq__(self, other): return type(other) is Identifier
    class Symbol:
        def __init__(self): self.id=Identifier()
        def __eq__(self, other): return self is other
        def __hash__(self): return id(self)
    fields = {"symbol", "type", "resolution", "data_normalization_mode", "is_internal_feed", "is_custom_data",
        "fill_data_forward", "extended_market_hours", "exchange_time_zone", "data_time_zone"}
    class Config:
        def __getattribute__(self, name):
            if name in fields:
                key=(id(self),name);state.fields[key]=state.fields.get(key,0)+1
                state.field_hook(self,name,state.fields[key])
            return object.__getattribute__(self,name)
    class TradeBar:
        def __init__(self,symbol,ended):
            self.symbol,self.time,self.end_time=symbol,ended-timedelta(minutes=1),ended
            self.period,self.is_fill_forward=timedelta(minutes=1),False
        @property
        def price(self): raise AssertionError("price consumed")
        @property
        def volume(self): raise AssertionError("volume consumed")
    class Slice:
        def __init__(self,bars=None): self.bars={} if bars is None else bars
    class Security:
        def __init__(self,symbol): self.symbol=symbol
    class Collection:
        @property
        def Count(self): state.count_reads+=1;state.count_hook();return len(state.rows)
        def __getitem__(self,index): state.index_reads+=1;state.index_hook();return state.rows[index]
        def __iter__(self):
            class Cursor:
                def __init__(self): self.index=0
                def __iter__(self): return self
                def __next__(self):
                    state.next_calls+=1;state.next_hook()
                    if self.index>=len(state.rows): raise StopIteration
                    row=state.rows[self.index];self.index+=1;return row
            return Cursor()
    class Algorithm:
        def __init__(self):
            self.project_id,self.algorithm_id,self.live_mode=38609822,"",False
            self.is_warming_up,self.current_slice=False,Slice()
            self.settings,self.securities=NS(),{}
            self.subscription_manager=NS(subscription_data_config_service=NS(get_subscription_data_configs=self.query))
        def query(self,symbol,include_internal):
            assert symbol is self._symbol and include_internal is True
            state.queries+=1;state.query_hook()
            return Collection() if state.collection=="indexed" else iter(state.rows)
        def get_locked(self): return state.lock
        def set_time_zone(self,zone): state.zone=zone
        def set_start_date(self,*parts): state.start=parts
        def set_end_date(self,*parts): state.end=parts
        def add_equity(self,ticker,resolution,**kw):
            assert ticker=="SPY" and resolution==Resolution.MINUTE
            assert kw=={"fill_forward":False,"extended_market_hours":True,"data_normalization_mode":Mode.RAW}
            symbol=Symbol();security=Security(symbol);self.securities[symbol]=security
            state.registrations.append(symbol);return security
        def set_benchmark(self,symbol): state.benchmark=symbol
        def log(self,text): state.logs.append(text)
    imports=ModuleType("AlgorithmImports")
    imports.__dict__.update(QCAlgorithm=Algorithm,Resolution=Resolution,DataNormalizationMode=Mode,
        Symbol=Symbol,TradeBar=TradeBar,Slice=Slice)
    data,securities,system=ModuleType("QuantConnect.Data"),ModuleType("QuantConnect.Securities"),ModuleType("System")
    data.SubscriptionDataConfig,securities.Security=Config,Security
    system.Object=NS(ReferenceEquals=lambda a,b:a is b)
    for name,module in (("AlgorithmImports",imports),("QuantConnect",ModuleType("QuantConnect")),
            ("QuantConnect.Data",data),("QuantConnect.Securities",securities),("System",system)):
        monkeypatch.setitem(sys.modules,name,module)
    namespace={};exec(compile(render()[0],"synthetic_census.py","exec"),namespace)
    algo=namespace["Main"]();algo.initialize()
    assert not algo._disabled and state.queries==0 and len(state.registrations)==1
    def row(kind="TradeBar",daily=False,internal=False):
        value=Config();value.__dict__.update(symbol=algo._symbol,type=NS(FullName="QuantConnect.Data.Market."+kind),
            resolution=Resolution.DAILY if daily else Resolution.MINUTE,data_normalization_mode=Mode.ADJUSTED if daily else Mode.RAW,
            is_internal_feed=internal,is_custom_data=False,fill_data_forward=daily,extended_market_hours=not daily,
            exchange_time_zone=NS(id="America/New_York"),data_time_zone=NS(id="America/New_York"))
        return value
    state.rows=[row(),row("QuoteBar"),row(daily=True,internal=True)]
    state.lock,algo.algorithm_id=True,"b"*32
    def at(day=8,hour=4,minute=1,empty=False):
        algo.time,algo.utc_time=datetime(2021,2,day,hour,minute),datetime(2021,2,day,hour+5,minute)
        algo.current_slice=Slice({} if empty else {algo._symbol:TradeBar(algo._symbol,algo.time)})
        return algo.current_slice
    at()
    return NS(state=state,algo=algo,at=at,row=row,Slice=Slice,TradeBar=TradeBar,namespace=namespace,Symbol=Symbol)


def test_three_configuration_rows_are_observed_without_parent_or_policy_admission(native):
    n=native;n.algo.on_data(n.algo.current_slice);report=n.algo._report
    assert report["complete"] and report["enumeration_complete"] and report["scope_stable"]
    assert report["rows_seen"]==len(report["rows"])==3
    assert report["rows"][0]["kind"]=="trade_bar" and report["rows"][1]["kind"]=="quote_bar"
    third=report["rows"][2]
    assert third["daily"] is True and third["minute"] is False and third["internal"] is True
    assert third["raw"] is False and third["adjusted"] is True
    assert n.state.queries==1 and n.state.next_calls==4 and n.state.count_reads==2 and n.state.index_reads==6
    for day in range(8,13): n.algo.on_data(n.at(day,16,1))
    n.algo.on_end_of_algorithm()
    assert n.state.queries==1 and report["post_query_skips"]==5
    assert state_benchmark(n) and all(report[key] is False for key in p.FLAGS)
    assert len(n.state.logs[-1].split(" ",1)[1])<=16384


def state_benchmark(n): return n.state.benchmark is n.algo._symbol


@pytest.mark.parametrize("count",[0,1,8,9,40])
def test_row_enumeration_and_endpoint_reads_are_bounded(native,count):
    n=native;n.state.rows=[n.row() for _ in range(count)]
    n.algo.on_data(n.algo.current_slice);r=n.algo._report
    assert n.state.queries==1 and n.state.next_calls==min(count+1,9)
    assert len(r["rows"])==min(count,8) and r["rows_seen"]==min(count,9)
    assert n.state.index_reads==2*min(count,8) and n.state.count_reads==2
    assert r["truncated"] is (count>8) and r["complete"] is (count<=8)
    if count>8: assert r["enumeration_complete"] is False


def test_unsupported_collection_never_claims_verified_endpoint(native):
    n=native;n.state.collection="iterator"
    n.algo.on_data(n.algo.current_slice);r=n.algo._report
    assert r["enumeration_complete"] and len(r["rows"])==3
    assert r["collection_endpoint_supported"] is False and r["complete"] is False
    assert r["retained_row_refs_unchanged"] is None and r["collection_count_unchanged"] is None
    assert r["collection_reason"]=="collection_endpoint_unsupported"


@pytest.mark.parametrize("fault",["unknown_kind","boolean","resolution","symbol","timezone","row_type","private_error"])
def test_unsupported_fields_remain_none_and_do_not_echo_unknown_data(native,fault):
    n=native;row=n.state.rows[0]
    if fault=="unknown_kind": row.type.FullName="SECRET PRIVATE CLASS"
    elif fault=="boolean": row.is_internal_feed=0
    elif fault=="resolution": row.resolution=object()
    elif fault=="symbol": row.symbol=object()
    elif fault=="timezone": row.data_time_zone=NS(id=None)
    elif fault=="row_type": n.state.rows[0]=NS()
    else:
        class PrivateError(ValueError):
            def __str__(self): raise AssertionError("exception text consumed")
        def hook(item,attr,count):
            if item is row and attr=="extended_market_hours": raise PrivateError("SECRET ERROR")
        n.state.field_hook=hook
    n.algo.on_data(n.algo.current_slice);r=n.algo._report;meta=r["rows"][0]
    key={"unknown_kind":"kind","boolean":"internal","resolution":"minute","symbol":"symbol_sid_matches",
        "timezone":"data_timezone_ny","private_error":"extended","row_type":"kind"}[fault]
    assert meta[key] is None and meta["unsupported"] and r["complete"] is False
    n.algo.on_end_of_algorithm()
    assert "SECRET" not in n.state.logs[-1] and "PrivateError" not in n.state.logs[-1]


@pytest.mark.parametrize("fault",["clock","lock","job","slice","security","bar"])
@pytest.mark.parametrize("stage",["query","iteration","metadata","endpoint"])
def test_scope_changes_never_produce_complete_census(native,fault,stage):
    n=native
    def mutate():
        if fault=="clock": n.algo.time+=timedelta(minutes=1);n.algo.utc_time+=timedelta(minutes=1)
        elif fault=="lock": n.state.lock=False
        elif fault=="job": n.algo.algorithm_id="c"*32
        elif fault=="slice": n.algo.current_slice=n.Slice(dict(n.algo.current_slice.bars))
        elif fault=="security": n.algo.securities[n.algo._symbol]=NS()
        elif fault=="bar": n.algo.current_slice.bars[n.algo._symbol].is_fill_forward=True
    if stage=="query": n.state.query_hook=mutate
    elif stage=="iteration": n.state.next_hook=mutate
    elif stage=="metadata": n.state.field_hook=lambda row,attr,count: mutate()
    else:
        def endpoint():
            if n.state.count_reads==2: mutate()
        n.state.count_hook=endpoint
    n.algo.on_data(n.algo.current_slice);r=n.algo._report
    assert not r["complete"] and r["first_failure_stage"] is not None
    n.algo.on_data(n.algo.current_slice)
    assert n.state.queries==1


def test_returned_collection_replacement_and_known_to_unknown_kind_are_detected(native):
    n=native;first=n.state.rows[0]
    def replace(row,attr,count):
        if row is first and attr=="type" and count==1: n.state.rows[0]=n.row()
    n.state.field_hook=replace
    n.algo.on_data(n.algo.current_slice);r=n.algo._report
    assert not r["complete"] and r["retained_row_refs_unchanged"] is False
    assert r["collection_reason"]=="collection_endpoint_changed"


def test_projected_kind_change_between_samples_is_not_silently_normalized(native):
    n=native;first=n.state.rows[0]
    def change(row,attr,count):
        if row is first and attr=="type" and count==2: row.__dict__["type"].FullName="SECRET NEW CLASS"
    n.state.field_hook=change
    n.algo.on_data(n.algo.current_slice);r=n.algo._report
    assert not r["complete"] and r["projected_metadata_unchanged"] is False
    n.algo.on_end_of_algorithm();assert "SECRET" not in n.state.logs[-1]


@pytest.mark.parametrize("fault",["late","day","unlocked","job","ff","future","pre4trade"])
def test_invalid_preopen_or_job_never_calls_configuration_service(native,fault):
    n=native
    if fault=="late": n.at(8,9,30)
    elif fault=="day": n.at(9)
    elif fault=="unlocked": n.state.lock=False
    elif fault=="job": n.algo.algorithm_id=""
    elif fault=="ff": n.algo.current_slice.bars[n.algo._symbol].is_fill_forward=True
    elif fault=="future": n.algo.current_slice.bars[n.algo._symbol].end_time+=timedelta(minutes=2)
    else: n.at(8,3,59)
    n.algo.on_data(n.algo.current_slice)
    assert n.state.queries==0 and not n.algo._report["complete"]


def test_auxiliary_wait_and_callback_cap_have_no_query_retry(native):
    n=native
    for hour,minute in ((0,1),(3,59),(4,1)): n.algo.on_data(n.at(8,hour,minute,empty=True))
    assert n.state.queries==0 and n.algo._report["preopen_empty_slices"]==3
    n.algo.on_data(n.at(8,4,2));assert n.state.queries==1
    n.algo._report["on_data_entries"]=6400;n.algo.on_data(n.algo.current_slice)
    assert n.algo._report["on_data_entries"]==6400 and n.algo._report["callback_cap_reached"]
    assert n.state.queries==1
