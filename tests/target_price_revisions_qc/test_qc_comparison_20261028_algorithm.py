"""New OFF driver runs only on LEAN stubs and in-memory own-job stores."""
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest

from research.target_price_revisions_qc import comparison_20261028 as comparison
from research.target_price_revisions_qc import extended_compressed_store as storage
from tests.target_price_revisions_qc import test_qc_extended_runtime as old_runtime

PUBLIC=Path("research/target_price_revisions_qc")


@pytest.fixture(autouse=True)
def no_actual_effects(monkeypatch):
    import http.client
    from research.target_price_revisions_qc import extended_operations as operations
    def denied(*_args, **_kwargs):
        raise AssertionError("actual QC/private/operator/provider/credential operation forbidden")
    monkeypatch.setattr(operations, "credential", denied)
    monkeypatch.setattr(operations, "read_private", denied)
    monkeypatch.setattr(operations.Operations, "__init__", denied)
    monkeypatch.setattr(operations.subprocess, "run", denied)
    monkeypatch.setattr(http.client, "HTTPSConnection", denied)


class Sid(str):
    def __new__(cls,value,market="usa"):
        item=super().__new__(cls,value);item.market=market;return item


class Symbol:
    def __init__(self, sid, ticker=None):
        self.id=Sid(sid); self.value=ticker or sid
        self.security_type=sys.modules["AlgorithmImports"].SecurityType.EQUITY
    def __hash__(self):return hash(self.id)
    def __eq__(self, other):return isinstance(other, Symbol) and self.id==other.id


class Constituent:
    def __init__(self, symbol, end):self.symbol=symbol; self.end_time=end
    def data_time_zone(self):return NS(id="UTC")
    @property
    def weight(self):raise AssertionError("membership weight/units must never be accessed")


class Fundamental:
    pass


class SupportedExchangeHours:
    """Only documented LEAN GetNextMarketClose(localDateTime,extendedHours)."""
    __slots__=("close","calls")
    def __init__(self,close):self.close=close;self.calls=[]
    def get_next_market_close(self,local_datetime,extended_market_hours):
        self.calls.append((local_datetime,extended_market_hours))
        assert extended_market_hours is False
        return self.close if local_datetime<self.close else self.close+timedelta(days=1)


class NativeStore:
    def __init__(self):self.values={}; self.calls=[]
    def contains_key(self,key):self.calls.append(("contains",key)); return key in self.values
    def save_bytes(self,key,value):
        assert key not in self.values
        self.calls.append(("save",key)); self.values[key]=bytes(value); return True
    def read_bytes(self,key):self.calls.append(("read",key)); return self.values[key]


def canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"))


def config(module, **changes):
    body={"schema":"tpr-cmp28-off-native-config-v1", "study_id":module.STUDY,
        "candidate_id":module.CANDIDATE,"arm":"cap_off", "operation_id":"TPR-CMP28-OFF-SYNTHETIC-001",
        "attempt":4,"project_id":module.PROJECT,"policy_sha256":hashlib.sha256(comparison.policy_bytes()).hexdigest(),
        "calendar_sha256":module.calendar_sha256(),"source_template_closure_sha256":"a"*64,
        "prior_attempts_looks_sha256":"b"*64,"source_inputs_admitted":False,"canonical_admission":False}
    body.update(changes)
    raw=canonical(body)
    return body, raw, hashlib.sha256(raw.encode()).hexdigest()


@pytest.fixture
def driver(monkeypatch):
    old=old_runtime.runtime.__wrapped__(monkeypatch)
    api=sys.modules["AlgorithmImports"]
    api.Market=NS(USA="usa")
    api.ETFConstituentUniverse=Constituent
    api.Fundamental=Fundamental
    deferred=ModuleType("extended_runtime_successor")
    exec(compile((PUBLIC/"extended_runtime_successor.py").read_bytes(), "<public-deferred>","exec"),deferred.__dict__)
    monkeypatch.setitem(sys.modules,"extended_runtime_successor",deferred)
    monkeypatch.setitem(sys.modules,"extended_compressed_store",storage)
    predecessor=ModuleType("extended_algorithm_successor")
    predecessor.__dict__["__ATTEMPT_NUMBER__"]=3
    monkeypatch.setitem(sys.modules,predecessor.__name__,predecessor)
    exec(compile((PUBLIC/"extended_algorithm_successor.py").read_bytes(),"<public-predecessor>","exec"),predecessor.__dict__)
    monkeypatch.setitem(sys.modules,"comparison_20261028",comparison)
    module=ModuleType("synthetic_cmp28_main")
    exec(compile((PUBLIC/"comparison_20261028_algorithm.py").read_bytes(),"<synthetic-cmp28>","exec"),module.__dict__)
    module.predecessor=predecessor
    module.fixture=old
    return module


def minimal(driver):
    algo=driver.ComparisonOffAlgorithm()
    algo._config,_,_=config(driver)
    algo.project_id,algo.algorithm_id=driver.PROJECT,"synthetic-native-job"
    algo.get_locked=lambda:True
    algo.utc_time=datetime(2021,1,4,14,20,tzinfo=timezone.utc)
    algo.time=datetime(2021,1,4,9,20)
    algo.is_warming_up=False
    algo._snapshots={sleeve:[] for sleeve in driver.SLEEVES}
    algo._cap_snapshots=[];algo._cap_callback_count=0
    algo._membership_coverage_by_day={};algo._cap_snapshot_coverage_by_day={}
    algo._decision_coverage={};algo._targets={};algo._target_weights={};algo._symbols={}
    algo._warning_ids=set();algo._delisted_ids=set();algo._ever_targeted_ids=set();algo._reasons={}
    algo._records=[];algo._log_audit=lambda kind,payload:algo._records.append((kind,payload))
    return algo


def supplied_inputs(driver,algo,classification="noninsurance"):
    day="2021-01-04"
    cutoff=driver.core._clock(driver.core.CUTOFF_BY_DAY[day])
    effective=cutoff-timedelta(days=8)
    caps={}; insurance={}
    for sleeve in driver.SLEEVES:
        symbol=Symbol("SID-"+sleeve)
        algo._symbols[symbol.id]=symbol
        algo._snapshots[sleeve]=[{"effective":effective,"received":effective,
            "members":[{"symbol":symbol,"ticker":symbol.value}], "native_member_coverage":{
                "source_rows":1,"us_equity_members":1,"other_market_excluded":0,"other_security_type_excluded":0}}]
        caps[str(symbol.id)]={"state":"available","value":"1000"}
        insurance[str(symbol.id)]=classification
    algo._cap_snapshots=[{"effective":cutoff-timedelta(hours=8),"received":cutoff-timedelta(hours=7),
        "asof":cutoff-timedelta(hours=12),"caps":caps,"insurance":insurance}]
    return day


def test_driver_keeps_mature_money_action_raw_methods_without_old_initialization(driver):
    for name in ("_rebalance","_prior_mark","_native_factor_basis","_cancel_day_orders","on_data", "on_order_event",
                 "_raw_security_configs","_assert_raw_subscriptions","_native_final_fill_symbol"):
        assert getattr(driver.ComparisonOffAlgorithm,name) is getattr(driver.predecessor.TargetPriceExtendedAlgorithm,name)
    assert driver.ComparisonOffAlgorithm.initialize is not driver.predecessor.TargetPriceExtendedAlgorithm.initialize
    assert driver.ComparisonOffAlgorithm._prepare_targets is not driver.predecessor.TargetPriceExtendedAlgorithm._prepare_targets
    assert len(driver.core.DECISIONS)==301 and len(driver.core.VALUATIONS)==1449
    assert driver.SLEEVES==("SPY","XLE","REMX","KIE","XLF","IWM")


@pytest.mark.parametrize("field,value", [("arm","pure_tpr"),("arm","cap_tilt_50"),("arm","cap_tilt_100"),("arm","cap_tilt_200"),
    ("study_id","old"),("candidate_id","old"),("project_id",1),("project_id",True),("attempt",True),("attempt",0),
    ("source_inputs_admitted",True),("canonical_admission",True),("policy_sha256","a"*64),
    ("calendar_sha256","a"*64),("operation_id","foreign"),("source_template_closure_sha256","0"*64)])
def test_config_accepts_only_exact_new_off_and_false_admission(driver,field,value):
    _,raw,digest=config(driver,**{field:value})
    with pytest.raises(ValueError,match="CMP28 OFF native candidate refused"):
        driver.validate_config(raw,digest)


def test_config_hash_and_unknown_duplicate_fields_refuse(driver):
    body,raw,digest=config(driver)
    assert driver.validate_config(raw,digest)==body
    for changed in (raw+" ",raw[:-1]+',"secret":1}',raw[:-1]+',"arm":"cap_off"}'):
        with pytest.raises(ValueError):driver.validate_config(changed,hashlib.sha256(changed.encode()).hexdigest() if changed!=raw+" " else digest)


def test_native_identity_membership_never_reads_weight_or_filters_unknown_weight(driver):
    algo=minimal(driver)
    rows=[Constituent(Symbol("SID-A"),algo.utc_time-timedelta(days=8)),
          Constituent(Symbol("SID-B"),algo.utc_time-timedelta(days=8))]
    assert algo._constituents_for("KIE",rows)==[row.symbol for row in rows]
    assert set(algo._snapshots["KIE"][0]["members"][0])=={"symbol","ticker"}
    assert algo._snapshots["KIE"][0]["received"]==algo.utc_time


@pytest.mark.parametrize("mode",["future","mixed","duplicate","untyped","oversize"])
def test_membership_refuses_future_ambiguous_and_untyped_rows(driver,mode):
    algo=minimal(driver)
    row=Constituent(Symbol("SID-A"),algo.utc_time-timedelta(days=8))
    rows=[row]
    if mode=="future":row.end_time=algo.utc_time+timedelta(seconds=1)
    elif mode=="mixed":rows.append(Constituent(Symbol("SID-B"),row.end_time-timedelta(days=1)))
    elif mode=="duplicate":rows.append(row)
    elif mode=="untyped":rows=[NS(symbol=row.symbol,end_time=row.end_time)]
    else:rows=[row]*(comparison.MAX_IDENTITIES+1)
    with pytest.raises(ValueError):algo._constituents_for("KIE",rows)
    assert algo._snapshots["KIE"]==[]


def test_actual_new_constructor_uses_new_labels_excludes_finance_insurance_and_is_score_free(driver):
    algo=minimal(driver); day=supplied_inputs(driver,algo)
    algo._cap_snapshots[0]["insurance"]["SID-XLF"]="insurance"
    algo._prepare_targets(day)
    assert set(algo._target_weights)=={"SID-"+s for s in driver.SLEEVES if s!="XLF"}
    assert algo._target_weights==dict.fromkeys(algo._target_weights,Fraction(1,60))
    report=algo._decision_coverage[day]
    assert set(report["sleeves"])==set(driver.SLEEVES)
    assert report["construction"]["finance_classification"]["insurance_excluded"]==1
    assert report["source_inputs_admitted"] is report["native_source_units_accepted"] is False
    assert all(row["membership_weights_used"] is False for row in report["sleeves"].values())
    with pytest.raises(ValueError):algo._selected_scores({},day)


@pytest.mark.parametrize("mode",["finance_unknown","finance_missing","future_caps","stale_membership","missing_membership"])
def test_unavailable_native_inputs_refuse_the_decision_without_fallback(driver,mode):
    algo=minimal(driver);day=supplied_inputs(driver,algo)
    if mode=="finance_unknown":algo._cap_snapshots[0]["insurance"]["SID-XLF"]=None
    elif mode=="finance_missing":algo._cap_snapshots[0]["insurance"].clear()
    elif mode=="future_caps":algo._cap_snapshots[0]["received"]=algo.utc_time
    elif mode=="stale_membership":algo._snapshots["KIE"][0]["effective"]-=timedelta(days=30)
    else:algo._snapshots["IWM"]=[]
    algo._prepare_targets(day)
    assert algo._decision_coverage[day] is None and not algo._target_weights
    assert not any(kind=="ORDER" for kind,_ in algo._records)


def test_real_rebalance_composes_construct_off_and_prior_close_moo_order_planner(driver):
    algo=minimal(driver);day=supplied_inputs(driver,algo)
    algo._attempted_days=set();algo._decision_count=algo._refused_count=0
    algo._assert_clock_subscription=lambda:None
    algo._evidence=NS(require_binding=lambda:None)
    algo.portfolio=NS(cash="100000",values=lambda:[])
    algo._prior_close_nav=Fraction(100000);algo._prior_close_day=None
    algo._prior_mark=lambda symbol:(Fraction(100),Fraction(10000))
    algo._assert_raw_subscriptions=lambda symbol:None
    algo._requested_shares=algo._submitted_shares=algo._submitted=0;algo._tickets=[]
    actual=[]
    def moo(symbol,quantity,tag):
        actual.append((symbol.id,quantity,tag));return NS(order_id=len(actual))
    algo.market_on_open_order=moo
    algo._rebalance()
    assert actual and len(actual)==6 and all(quantity==16 for _,quantity,_ in actual)
    assert algo._attempted_days=={day} and algo._decision_count==1 and algo._refused_count==0
    before=list(actual);algo._rebalance();assert actual==before
    assert algo._submitted==6 and algo._requested_shares==algo._submitted_shares==96
    assert any(kind=="ORDER" and "settled_cash" in payload for kind,payload in algo._records)


def test_inherited_exact_planner_does_not_recycle_sale_proceeds_and_caps_volume(driver):
    planner=driver.predecessor.plan_weighted_orders
    result=planner({"B":Fraction(1,10)},{"A":100},{"A":(10,10000),"B":(10,10000)},10000,0,Fraction(1,1000))
    assert [(row["security_id"],row["submitted"]) for row in result]==[("A",-100),("B",0)]
    result=planner({"A":Fraction(1,10)},{},{"A":(10,1000)},10000,10000,Fraction(1,1000))
    assert result[0]["submitted"]==10 and result[0]["reason"]=="volume_cap"


def test_journal_stays_private_job_bound_plain_and_index_last(driver):
    body,_,digest=config(driver)
    state=NS(project=driver.PROJECT,job="",locked=False)
    journal=driver.ComparisonJournal(body,digest,lambda:(state.project,state.job,state.locked))
    journal.append("NAV",{"nav":Fraction(100000),"synthetic":True})
    store=NativeStore()
    with pytest.raises(ValueError):journal.export(store)
    assert store.calls==[]
    state.job,state.locked="synthetic-job-4",True
    pointer=journal.export(store)
    saves=[key for method,key in store.calls if method=="save"]
    assert saves[-1].endswith("/index.json") and len(saves)==2
    assert all("/37650980/synthetic-job-4/" in key and "/attempt-4/" in key for key in saves)
    raw=store.values[pointer["index_key"]];index=json.loads(raw)
    assert hashlib.sha256(raw).hexdigest()==pointer["index_sha256"]
    assert index["records"]==1 and index["config"]==body
    chunk=index["chunks"][0]
    chunk_raw=store.values[chunk["key"]]
    assert json.loads(chunk_raw)["kind"]=="NAV"
    assert chunk["bytes"]==len(chunk_raw) and chunk["sha256"]==hashlib.sha256(chunk_raw).hexdigest()
    assert set(chunk)=={"key","bytes","sha256"} and chunk["key"].endswith(".jsonl")
    assert pointer["index_bytes"]==len(raw) and pointer["encoding"]==index["encoding"]=="utf-8-jsonl"
    assert pointer["schema"]=="tpr-cmp28-private-journal-pointer-v2-plain"
    assert index["schema"]=="tpr-cmp28-private-journal-index-v2-plain"
    assert "gzip" not in raw.decode() and not any("gzip" in key for key in pointer)
    assert index["strategy_accepted"] is index["source_inputs_admitted"] is False
    with pytest.raises(ValueError):journal.export(store)


@pytest.mark.parametrize("mode",["project","job","unlock","missing_job"])
def test_journal_rejects_native_identity_drift_before_any_effect(driver,mode):
    body,_,digest=config(driver)
    state=NS(project=driver.PROJECT,job="synthetic",locked=True)
    journal=driver.ComparisonJournal(body,digest,lambda:(state.project,state.job,state.locked))
    journal.append("SUMMARY",{})
    if mode=="project":state.project=1
    elif mode=="job":state.job="foreign"
    elif mode=="unlock":state.locked=False
    else:state.job=""
    store=NativeStore()
    with pytest.raises(ValueError):journal.export(store)
    assert store.calls==[]


def test_uncertain_store_effect_closes_against_retry_and_cannot_publish_index(driver):
    body,_,digest=config(driver)
    journal=driver.ComparisonJournal(body,digest,lambda:(driver.PROJECT,"synthetic",True))
    journal.append("SUMMARY",{})
    store=NativeStore()
    def uncertain(key,raw):
        store.calls.append(("uncertain",key));raise TimeoutError("synthetic transport")
    store.save_bytes=uncertain
    with pytest.raises(TimeoutError):journal.export(store)
    before=list(store.calls)
    with pytest.raises(ValueError):journal.export(store)
    assert store.calls==before and not any(key.endswith("index.json") and method=="uncertain" for method,key in before)


def test_daily_audit_clock_is_exact_and_reuses_existing_stale_future_mark_checks(driver):
    algo=minimal(driver);algo.time=datetime(2021,1,4,16,0)
    with pytest.raises(ValueError):algo._daily_audit()


def test_native_candidate_source_is_bounded_and_compiles_in_memory(driver):
    raw=(PUBLIC/"comparison_20261028_algorithm.py").read_bytes()
    assert len(raw)<=60000
    compile(raw,"<new-off-source>","exec")
    assert "signal_packet" not in raw.decode() and "compressed_packet" not in raw.decode()


def test_new_calendar_identity_preserves_301_1449_dates_without_old_study_identity(driver):
    calendar=driver.comparison_calendar()
    assert calendar["study_id"]==comparison.STUDY_ID
    assert calendar["source_calendar_sha256"]==driver.core.CALENDAR_SHA256
    assert driver.calendar_sha256()!=driver.core.CALENDAR_SHA256
    assert calendar["decisions"]==driver.core.CALENDAR["decisions"]
    assert calendar["valuation_sessions"]==list(driver.core.VALUATIONS)
    calendar["decisions"].clear()
    assert len(driver.comparison_calendar()["decisions"])==301


@pytest.mark.parametrize("close_hour,last_hour", [(16,9),(16,17),(13,12)])
def test_same_day_stale_future_or_pre_halfday_closing_marks_refuse_before_accounting(driver,close_hour,last_hour):
    algo=minimal(driver);algo.time=datetime(2021,1,4,16,1)
    algo.utc_time=datetime(2021,1,4,21,1,tzinfo=timezone.utc)
    bar=driver.TradeBar()
    bar.end_time=datetime(2021,1,4,last_hour,0)
    symbol=Symbol("SID-HELD")
    security=NS(get_last_data=lambda:bar,
        exchange=NS(hours=SupportedExchangeHours(datetime(2021,1,4,close_hour,0))))
    algo.portfolio=NS(values=lambda:[NS(invested=True,symbol=symbol)])
    algo._assert_raw_subscriptions=lambda *_:security
    with pytest.raises(ValueError):algo._daily_audit()


def test_native_09_35_cancel_is_order_based_and_uses_existing_window(driver):
    algo=minimal(driver);algo.time=datetime(2021,1,4,9,35)
    cancelled=[]
    algo.transactions=NS(get_open_orders=lambda:[NS(id=17),NS(id=18)],
        cancel_order=lambda identity,tag:cancelled.append((identity,tag)))
    algo._cancel_day_orders()
    assert [identity for identity,_ in cancelled]==[17,18]


def test_real_initialization_registers_exact_new_universes_and_frozen_execution_schedule(driver,monkeypatch):
    algo=driver.ComparisonOffAlgorithm()
    body,raw,digest=config(driver)
    driver.EXPECTED_CONFIG_SHA256=digest
    settings=ModuleType("comparison_20261028_config");settings.CONFIG_JSON=raw
    monkeypatch.setitem(sys.modules,settings.__name__,settings)
    algo.live_mode=False;algo.project_id=driver.PROJECT;algo.algorithm_id=""
    algo.get_locked=lambda:False
    algo._initialized_factor_provider=lambda:object()
    settings_calls=[];equities=[];universes=[];events=[]
    for name in ("set_start_date","set_end_date","set_time_zone","set_account_currency","set_cash","set_warm_up","set_benchmark"):
        setattr(algo,name,lambda *args,_name=name:settings_calls.append((_name,args)))
    algo.add_chart=lambda *_:None
    algo.universe_settings=NS()
    algo.add_security_initializer=lambda callback:None
    def add_equity(label,*args,**kwargs):
        equities.append((label,args,kwargs));return NS(symbol=Symbol("ETF-"+label,label))
    algo.add_equity=add_equity
    algo.universe=NS(etf=lambda symbol,universe_filter_func:NS(symbol=Symbol("CTX-"+symbol.id),filter=universe_filter_func))
    def add_universe(value):
        if callable(value):value=NS(symbol=Symbol("CTX-FUNDAMENTAL"),filter=value)
        universes.append(value);return value
    algo.add_universe=add_universe
    algo.date_rules=NS(every_day=lambda symbol:("daily",symbol.id))
    algo.time_rules=NS(at=lambda hour,minute:(hour,minute))
    algo.schedule=NS(on=lambda *args:events.append(args))
    algo.initialize()
    assert [row[0] for row in equities]==list(comparison.SLEEVES)
    assert len(universes)==7
    assert ("set_start_date",(2021,1,4)) in settings_calls
    assert ("set_end_date",(2026,10,9)) in settings_calls
    assert ("set_cash",(100000,)) in settings_calls
    assert [row[1] for row in events]==[(9,20),(9,35),(16,1)]
    assert all(row[2]["data_normalization_mode"]==driver.DataNormalizationMode.RAW for row in equities)
    assert equities[0][2]["extended_market_hours"] is True
    assert algo._signal_store is None and algo._config==body
    assert algo._evidence.records==[]


def test_live_mode_refuses_before_configuration_or_any_initializer_effect(driver):
    algo=driver.ComparisonOffAlgorithm();algo.live_mode=True
    with pytest.raises(ValueError):algo.initialize()


class GroupFields(type):
    def __getattr__(cls,name):
        # Synthetic native static constants, distinct and deterministic.
        return 20000+sum(map(ord,name))


class Groups(metaclass=GroupFields):
    Insurance=10340
    Banks=10320


def fundamental(symbol,*,code=10320,cap="123456789",has=True):
    row=Fundamental();row.symbol=symbol
    row.time=datetime(2020,12,31,0);row.end_time=datetime(2020,12,31,0)
    row.market_cap=cap;row.has_fundamental_data=has
    row.asset_classification=NS(morningstar_industry_group_code=code)
    return row


def install_groups(monkeypatch):
    module=ModuleType("QuantConnect.Data.Fundamental");module.MorningstarIndustryGroupCode=Groups
    monkeypatch.setitem(sys.modules,module.__name__,module)


@pytest.mark.parametrize("code,expected",[(10340,"insurance"),(10320,"noninsurance"),(0,None),(99999,None),("10340.5",None)])
def test_insurance_classification_uses_native_complete_known_group_code_not_ticker_heuristics(driver,monkeypatch,code,expected):
    install_groups(monkeypatch)
    row=fundamental(Symbol("SID-INS"),code=code)
    assert driver.ComparisonOffAlgorithm._classify_insurance(row)==expected
    row.has_fundamental_data=False
    assert driver.ComparisonOffAlgorithm._classify_insurance(row) is None


def test_actual_native_fundamental_callback_keeps_cap_units_and_bound_classification_clocks(driver,monkeypatch):
    install_groups(monkeypatch)
    algo=minimal(driver)
    algo._cap_context_symbol=Symbol("CTX-FUNDAMENTAL")
    metadata=NS(symbol=algo._cap_context_symbol,is_internal_feed=True,resolution=driver.Resolution.DAILY,
        exchange_time_zone=NS(id="America/New_York"),type=NS(FullName="QuantConnect.Data.Fundamental.FundamentalUniverse"))
    algo.subscription_manager=NS(subscription_data_config_service=NS(get_subscription_data_configs=lambda *_:[metadata]))
    symbol=Symbol("SID-XLF");algo._symbols[symbol.id]=symbol
    row=fundamental(symbol,code=10340,cap="987654321.25")
    assert algo._capture_caps([row])==[]
    snapshot=algo._cap_snapshots[0]
    assert snapshot["caps"]=={symbol.id:{"state":"available","value":"987654321.25"}}
    assert snapshot["insurance"]=={symbol.id:"insurance"}
    assert snapshot["asof"]==snapshot["effective"]==datetime(2020,12,31,5,tzinfo=timezone.utc)
    assert snapshot["received"]==algo.utc_time
    row.end_time=datetime(2021,1,5)
    with pytest.raises(ValueError):algo._capture_caps([row])
    assert len(algo._cap_snapshots)==1


def test_raw_fill_dividend_split_ledger_and_native_close_audit_execute_without_rewriting_economics(driver):
    algo=minimal(driver)
    algo._evidence=NS(require_binding=lambda:None)
    algo._assert_raw_subscriptions=lambda *_:security
    algo._observe_raw_custody=lambda *_:None
    algo._ever_filled_ids=set();algo._fill_history_unknown=False
    algo._quantity_ledger={};algo._cash_ledger=Fraction(100000)
    algo._fees=Fraction(0);algo._fill_events=algo._filled_shares=0
    algo._split_factors={};algo._dividend_keys=set()
    symbol=Symbol("SID-A")
    security=NS()
    event=driver.OrderEvent()
    event.symbol=symbol;event.fill_quantity="16";event.fill_price="100"
    event.order_fee=NS(value=NS(amount="0.16",currency="USD"));event.status=driver.OrderStatus.FILLED
    event.is_assignment=False;event.utc_time=algo.utc_time;event.message="synthetic MOO";event.order_id=1
    algo.on_order_event(event)
    assert algo._quantity_ledger=={symbol.id:16} and algo._fees==Fraction(4,25)
    assert algo._cash_ledger==Fraction("98399.84")
    algo.time=datetime(2021,1,5,9,0);algo.utc_time=datetime(2021,1,5,14,0,tzinfo=timezone.utc)
    split=NS(symbol=symbol,type=driver.SplitType.SPLIT_OCCURRED,split_factor="0.5")
    dividend=NS(symbol=symbol,distribution="1")
    algo.on_data(NS(delistings={},bars={},splits={symbol:split},dividends={symbol:dividend}))
    assert algo._quantity_ledger=={symbol.id:32} and algo._cash_ledger==Fraction("98415.84")
    bar=driver.TradeBar();bar.end_time=datetime(2021,1,5,16,0);bar.price="50"
    security.get_last_data=lambda:bar;security.price="50"
    security.exchange=NS(hours=SupportedExchangeHours(datetime(2021,1,5,16,0)))
    held=NS(symbol=symbol,quantity="32",invested=True,holdings_value="1600")
    algo.portfolio=NS(cash="98415.84",total_portfolio_value="100015.84",total_holdings_value="1600",values=lambda:[held])
    algo.time=datetime(2021,1,5,16,1);algo.utc_time=datetime(2021,1,5,21,1,tzinfo=timezone.utc)
    algo._valuation_days=set();algo._position_ledger_mismatches=algo._risk_breaches=algo._name_soft_cap_breaches=0
    algo._max_cash_residual=algo._max_nav_residual=algo._max_name_exposure=Fraction(0)
    plots=[];algo.plot=lambda *args:plots.append(args)
    algo._daily_audit()
    assert algo._position_ledger_mismatches==0 and algo._max_cash_residual==algo._max_nav_residual==0
    assert algo._prior_close_nav==Fraction("100015.84") and algo._valuation_days=={"2021-01-05"}
    assert plots and any(kind=="FILL" for kind,_ in algo._records)
    assert len([1 for kind,_ in algo._records if kind=="ACTION"])==2
    assert any(kind=="NAV" for kind,_ in algo._records)


def test_terminal_partial_run_retains_new_study_private_index_without_inventing_acceptance(driver):
    algo=minimal(driver)
    body,_,digest=config(driver);driver.EXPECTED_CONFIG_SHA256=digest
    algo._evidence=driver.ComparisonJournal(body,digest,lambda:(algo.project_id,algo.algorithm_id,True))
    algo._log_audit=lambda kind,payload:algo._evidence.append(kind,payload)
    algo._decision_count=algo._refused_count=algo._submitted=algo._fill_events=0
    algo._requested_shares=algo._submitted_shares=algo._filled_shares=0
    algo._position_ledger_mismatches=algo._risk_breaches=algo._name_soft_cap_breaches=0
    algo._fees=algo._max_cash_residual=algo._max_nav_residual=algo._max_name_exposure=Fraction(0)
    algo._valuation_days=set();algo._attempted_days=set();algo._prior_close_nav=Fraction(100000)
    algo._clock_assertions=0;algo._delisting_audit=driver.cap_observer.empty_audit()
    algo._prior_close_day=None;algo._warmup_finished_minute_validated=False
    algo.object_store=NativeStore();logs=[];algo.log=logs.append
    algo.on_end_of_algorithm()
    summary=json.loads(logs[0].split(" ",1)[1]);pointer=json.loads(logs[1].split(" ",1)[1])
    assert summary["study_id"]==comparison.STUDY_ID and summary["arm"]=="cap_off"
    assert summary["coverage_complete"] is summary["calendar_complete"] is False
    assert summary["source_inputs_admitted"] is summary["strategy_accepted"] is False
    assert summary["accepted_performance"] is summary["final_nav"] is summary["last_observed_nav"] is None
    assert summary["internally_useful_order_run"] is False
    assert pointer["index_key"] in algo.object_store.values and algo._evidence.closed
    assert "SID-" not in logs[0] and "SID-" not in logs[1]


@pytest.mark.parametrize("before,after,probe", [
    ('body["arm"] != "cap_off"', 'False', 'off_only'),
    ('if self._job is not None and (job != self._job or not locked):', 'if False:', 'job_custody'),
    ('sid = str(row.symbol.id)\n            if not sid or sid in seen:', 'sid = str(row.symbol.id)\n            unused_weight = row.weight\n            if not sid or sid in seen:', 'membership_weights'),
])
def test_in_memory_native_guard_mutants_fail_observable_contracts_and_restore(driver,monkeypatch,before,after,probe):
    raw=(PUBLIC/"comparison_20261028_algorithm.py").read_text()
    assert raw.count(before)==1
    mutant=ModuleType("synthetic_cmp28_guard_mutant")
    exec(compile(raw.replace(before,after),"<synthetic-native-guard-mutant>","exec"),mutant.__dict__)
    with pytest.raises((AssertionError,pytest.fail.Exception)):
        if probe=="off_only":test_config_accepts_only_exact_new_off_and_false_admission(mutant,"arm","cap_tilt_50")
        elif probe=="job_custody":test_journal_rejects_native_identity_drift_before_any_effect(mutant,"job")
        else:test_native_identity_membership_never_reads_weight_or_filters_unknown_weight(mutant)
    # The unmodified module must still prove the same dangerous direction.
    if probe=="off_only":test_config_accepts_only_exact_new_off_and_false_admission(driver,"arm","cap_tilt_50")
    elif probe=="job_custody":test_journal_rejects_native_identity_drift_before_any_effect(driver,"job")
    else:test_native_identity_membership_never_reads_weight_or_filters_unknown_weight(driver)


def test_native_membership_us_stock_scope_excludes_foreign_and_other_security_types_with_census(driver):
    algo=minimal(driver)
    end=algo.utc_time-timedelta(days=8)
    us=Symbol("SID-US");foreign=Symbol("SID-CAN");foreign.id=Sid("SID-CAN","canada")
    other=Symbol("SID-OPTION");other.security_type="option"
    rows=[Constituent(symbol,end) for symbol in (us,foreign,other)]
    assert algo._constituents_for("REMX",rows)==[us]
    census=algo._snapshots["REMX"][0]["native_member_coverage"]
    assert census=={"source_rows":3,"us_equity_members":1,"other_market_excluded":1,"other_security_type_excluded":1}
    assert algo._snapshots["REMX"][0]["members"]==[{"symbol":us,"ticker":us.value}]


def test_unknown_intrinsic_native_market_is_refused_not_misclassified_as_foreign(driver):
    algo=minimal(driver)
    symbol=Symbol("SID-UNKNOWN");symbol.id.market=None
    with pytest.raises(ValueError):
        algo._constituents_for("REMX",[Constituent(symbol,algo.utc_time-timedelta(days=8))])
    assert not algo._snapshots["REMX"]


def test_current_construction_domain_is_not_polluted_by_more_than_4096_old_fundamental_caps(driver):
    algo=minimal(driver);day=supplied_inputs(driver,algo)
    current={str(row["symbol"].id) for snapshots in algo._snapshots.values()
        for snapshot in snapshots for row in snapshot["members"]}
    expected=dict.fromkeys(current,Fraction(1,60))
    for index in range(comparison.MAX_IDENTITIES+1):
        sid="HISTORICAL-"+str(index)
        algo._symbols[sid]=Symbol(sid)
        algo._cap_snapshots[0]["caps"][sid]={"state":"available","value":"9999999999"}
    assert len(algo._cap_snapshots[0]["caps"])>comparison.MAX_IDENTITIES
    algo._prepare_targets(day)
    assert algo._target_weights==expected
    report=algo._decision_coverage[day]
    assert report["ignored_noncurrent_cap_cells"]==comparison.MAX_IDENTITIES+1
    assert report["current_member_cap_domain_count"]==len(current)
    caps_record=next(payload for kind,payload in algo._records if kind=="CAPS")
    assert set(caps_record["caps"])==current


def test_current_missing_cap_is_preserved_when_old_cells_are_narrowed(driver):
    algo=minimal(driver);day=supplied_inputs(driver,algo)
    del algo._cap_snapshots[0]["caps"]["SID-KIE"]
    for index in range(comparison.MAX_IDENTITIES+1):
        algo._cap_snapshots[0]["caps"]["OLD-"+str(index)]={"state":"available","value":"9999999999"}
    algo._prepare_targets(day)
    assert "SID-KIE" not in algo._target_weights
    row=algo._decision_coverage[day]["sleeves"]["KIE"]
    assert row["selection_coverage"]["cap_state_counts"]["missing"]==1
    assert row["unfilled_slots"]==10
    caps_record=next(payload for kind,payload in algo._records if kind=="CAPS")
    assert caps_record["caps"]["SID-KIE"]=={"state":"missing","value":None}


@pytest.mark.parametrize("value", [b"plain", bytearray(b"plain"), memoryview(b"plain")])
def test_native_bytes_preserves_plain_bounded_python_bytes(driver,value):
    assert driver.native_bytes(value,5)==b"plain"
    with pytest.raises(ValueError):driver.native_bytes(value,4)


@pytest.mark.parametrize("value", [None,"plain",[112,108,97,105,110],b"",True])
def test_native_bytes_rejects_arbitrary_coercions_and_empty_values(driver,value):
    with pytest.raises(ValueError):driver.native_bytes(value,64)


@pytest.mark.parametrize("session,close_hour",[("2021-01-04",16),("2021-11-26",13)])
def test_supported_next_close_is_queried_from_that_session_midnight_before_accounting(driver,monkeypatch,session,close_hour):
    day=date.fromisoformat(session)
    algo=minimal(driver);algo.time=datetime.combine(day,time(16,1))
    algo.utc_time=algo.time.replace(tzinfo=driver.NY).astimezone(timezone.utc)
    bar=driver.TradeBar();bar.end_time=datetime.combine(day,time(close_hour))
    hours=SupportedExchangeHours(bar.end_time)
    symbol=Symbol("SID-HELD")
    algo.portfolio=NS(values=lambda:[NS(invested=True,symbol=symbol)])
    algo._assert_raw_subscriptions=lambda *_:NS(get_last_data=lambda:bar,exchange=NS(hours=hours))
    calls=[]
    monkeypatch.setattr(driver.predecessor.TargetPriceExtendedAlgorithm,"_daily_audit",lambda self:calls.append("accounted"))
    assert not hasattr(hours,"get_previous_market_close")
    algo._daily_audit()
    assert hours.calls==[(datetime.combine(day,time()),False)]
    assert calls==["accounted"]


@pytest.mark.parametrize("offset",[-1,1])
def test_equal_last_bar_and_native_close_on_another_day_still_refuse(driver,monkeypatch,offset):
    algo=minimal(driver);algo.time=datetime(2021,1,4,16,1)
    algo.utc_time=datetime(2021,1,4,21,1,tzinfo=timezone.utc)
    class WrongDayHours:
        def get_next_market_close(self,local_datetime,extended_market_hours):
            assert local_datetime==datetime(2021,1,4)
            assert extended_market_hours is False
            return datetime(2021,1,4,16)+timedelta(days=offset)
    bar=driver.TradeBar();bar.end_time=datetime(2021,1,4,16)+timedelta(days=offset)
    symbol=Symbol("SID-HELD")
    algo.portfolio=NS(values=lambda:[NS(invested=True,symbol=symbol)])
    algo._assert_raw_subscriptions=lambda *_:NS(get_last_data=lambda:bar,exchange=NS(hours=WrongDayHours()))
    calls=[];monkeypatch.setattr(driver.predecessor.TargetPriceExtendedAlgorithm,"_daily_audit",lambda self:calls.append("accounted"))
    with pytest.raises(ValueError):algo._daily_audit()
    assert not calls


def mark_witness_case(driver,monkeypatch,*,session="2021-02-10",observed=None,expected=None):
    day=date.fromisoformat(session)
    algo=minimal(driver);algo.time=datetime.combine(day,time(16,1))
    algo.utc_time=algo.time.replace(tzinfo=driver.NY).astimezone(timezone.utc)
    expected=expected or datetime.combine(day,time(16))
    observed=observed or datetime.combine(day,time(15,59))
    bar=driver.TradeBar();bar.end_time=observed
    symbol=Symbol("PRIVATE-MARK-SID-SENTINEL")
    calls=[]
    def last_data():calls.append("last_data");return bar
    def next_close(start,extended):
        assert start==datetime.combine(day,time()) and extended is False
        calls.append("next_close");return expected
    algo.portfolio=NS(values=lambda:[NS(invested=True,symbol=symbol)])
    algo._assert_raw_subscriptions=lambda *_:NS(get_last_data=last_data,
        exchange=NS(hours=NS(get_next_market_close=next_close)))
    body,_,digest=config(driver)
    algo._evidence=driver.ComparisonJournal(body,digest,lambda:(algo.project_id,algo.algorithm_id,algo.get_locked()))
    algo.object_store=NativeStore();logs=[];algo.log=logs.append
    accounted=[]
    monkeypatch.setattr(driver.predecessor.TargetPriceExtendedAlgorithm,"_daily_audit",lambda self:accounted.append(True))
    return algo,bar,symbol,calls,logs,accounted


def mark_pointer(logs):
    assert len(logs)==1 and logs[0].startswith("CMP28_MARK_REFUSAL ")
    return json.loads(logs[0].split(" ",1)[1])


@pytest.mark.parametrize("session,close_hour",[("2021-02-10",16),("2021-11-26",13)])
def test_accepted_regular_or_halfday_close_has_no_witness_store_or_public_effect(driver,monkeypatch,session,close_hour):
    close=datetime.combine(date.fromisoformat(session),time(close_hour))
    algo,_,_,calls,logs,accounted=mark_witness_case(driver,monkeypatch,session=session,observed=close,expected=close)
    algo._daily_audit()
    assert calls==["last_data","next_close"] and accounted==[True]
    assert algo.object_store.calls==[] and not logs
    assert not getattr(algo,"_mark_refusal_witness_attempted",False)


@pytest.mark.parametrize("observed,expected",[(datetime(2021,2,10,15,59),datetime(2021,2,10,16)),
    (datetime(2021,2,10,16,1),datetime(2021,2,10,16)),
    (datetime(2021,2,9,16),datetime(2021,2,10,16)),
    (datetime(2021,2,11,16),datetime(2021,2,11,16))])
def test_failed_exact_close_retains_one_private_verified_snapshot_before_original_refusal(driver,monkeypatch,observed,expected):
    algo,bar,symbol,calls,logs,accounted=mark_witness_case(driver,monkeypatch,observed=observed,expected=expected)
    store=algo.object_store;save=store.save_bytes
    def saved_first(key,raw):
        assert algo._mark_refusal_witness_attempted is True
        # A later mutation must not change the captured mismatch inputs.
        bar.end_time=datetime(2030,1,1)
        return save(key,raw)
    store.save_bytes=saved_first
    with pytest.raises(ValueError,match="^CMP28 OFF native candidate refused$"):algo._daily_audit()
    pointer=mark_pointer(logs);key=pointer["key"];raw=store.values[key];body=json.loads(raw)
    assert pointer["status"]=="verified" and pointer["readback_verified"] is True
    assert 0<len(raw)==pointer["bytes"]<=4096
    assert pointer["verified_sha256"]==pointer["expected_sha256"]==hashlib.sha256(raw).hexdigest()
    assert key==algo._evidence.require_binding()+"mark-refusal.json"
    assert [method for method,_ in store.calls]==["contains","save","read"] and len(store.values)==1
    assert body["security_id"]==str(symbol.id) and body["project_id"]==driver.PROJECT
    assert body["job_id"]==algo.algorithm_id and body["guard_unchanged"] is True
    assert body["observed_end_local"]==observed.replace(tzinfo=driver.NY).isoformat()
    assert body["expected_close_local"]==expected.replace(tzinfo=driver.NY).isoformat()
    assert body["source_inputs_admitted"] is body["strategy_accepted"] is body["canonical_admission"] is False
    assert body["predicates"]==pointer["predicates"] and not accounted
    assert calls==["last_data","next_close"]
    assert str(symbol.id) not in logs[0] and observed.isoformat() not in logs[0] and expected.isoformat() not in logs[0]
    assert "price" not in raw.decode() and "quote" not in raw.decode()
    for field in ("algorithm_utc","algorithm_local","expected_close_utc","expected_close_local","observed_end_utc","observed_end_local"):
        assert body[field] not in logs[0]


def test_witness_does_not_reopen_or_overwrite_existing_key_and_never_retries(driver,monkeypatch):
    algo,_,_,_,logs,_=mark_witness_case(driver,monkeypatch)
    key=algo._evidence.require_binding()+"mark-refusal.json"
    algo.object_store.values[key]=b"PRIVATE-EXISTING-WITNESS"
    with pytest.raises(ValueError):algo._daily_audit()
    first=mark_pointer(logs)
    assert first["status"]=="existing_or_unknown_key_refused" and not first["readback_verified"]
    assert first["verified_sha256"] is None and algo.object_store.values[key]==b"PRIVATE-EXISTING-WITNESS"
    assert algo.object_store.calls==[("contains",key)]
    before=list(algo.object_store.calls);logs.clear()
    with pytest.raises(ValueError):algo._daily_audit()
    assert algo.object_store.calls==before and mark_pointer(logs)["status"]=="already_attempted"


@pytest.mark.parametrize("phase",["contains","save","read"])
def test_witness_observes_native_job_drift_after_every_store_interaction(driver,monkeypatch,phase):
    algo,_,_,_,logs,_=mark_witness_case(driver,monkeypatch)
    store=algo.object_store
    name={"contains":"contains_key","save":"save_bytes","read":"read_bytes"}[phase]
    original=getattr(store,name)
    def drift(*args):
        value=original(*args);algo.algorithm_id="foreign-job";return value
    setattr(store,name,drift)
    with pytest.raises(ValueError,match="^CMP28 OFF native candidate refused$"):algo._daily_audit()
    pointer=mark_pointer(logs)
    assert pointer["status"]=="publication_failed" and not pointer["readback_verified"] and pointer["verified_sha256"] is None
    assert [method for method,_ in store.calls]==["contains","save","read"][:{"contains":1,"save":2,"read":3}[phase]]


def test_witness_wrong_native_project_refuses_before_any_private_effect(driver,monkeypatch):
    algo,_,_,_,logs,_=mark_witness_case(driver,monkeypatch);algo.project_id=1
    with pytest.raises(ValueError,match="^CMP28 OFF native candidate refused$"):algo._daily_audit()
    assert algo.object_store.calls==[] and mark_pointer(logs)["status"]=="publication_failed"


@pytest.mark.parametrize("mode",["bytes","length","save_false","contains_unknown","ordinary_error"])
def test_witness_uncertain_publication_preserves_original_refusal_and_honest_safe_status(driver,monkeypatch,mode):
    algo,_,_,_,logs,_=mark_witness_case(driver,monkeypatch);store=algo.object_store
    if mode in ("bytes","length"):
        original=store.read_bytes
        def corrupt(key):
            raw=original(key)
            return b"!"+raw[1:] if mode=="bytes" else raw+b" "
        store.read_bytes=corrupt
    elif mode=="save_false":store.save_bytes=lambda *_:False
    elif mode=="contains_unknown":store.contains_key=lambda *_:None
    else:
        def uncertain(key):raise TimeoutError("PRIVATE-TRANSPORT-BODY-SENTINEL")
        store.contains_key=uncertain
    with pytest.raises(ValueError,match="^CMP28 OFF native candidate refused$"):algo._daily_audit()
    pointer=mark_pointer(logs)
    assert pointer["status"]=={"bytes":"readback_mismatch","length":"readback_mismatch","save_false":"save_unconfirmed",
        "contains_unknown":"existing_or_unknown_key_refused","ordinary_error":"publication_failed"}[mode]
    assert pointer["verified_sha256"] is None and pointer["readback_verified"] is False
    assert "PRIVATE-TRANSPORT-BODY-SENTINEL" not in logs[0]
    before=list(store.calls);logs.clear()
    with pytest.raises(ValueError):algo._daily_audit()
    assert store.calls==before and mark_pointer(logs)["status"]=="already_attempted"


@pytest.mark.parametrize("kind",["cancel","fatal"])
def test_witness_cancellation_and_nonordinary_fatal_are_body_free_and_never_demoted(driver,monkeypatch,kind):
    algo,_,_,_,logs,_=mark_witness_case(driver,monkeypatch)
    class Fatal(BaseException):pass
    def stop(key):raise (KeyboardInterrupt if kind=="cancel" else Fatal)("PRIVATE-STOP-BODY-SENTINEL")
    algo.object_store.contains_key=stop
    wanted=KeyboardInterrupt if kind=="cancel" else driver.MarkWitnessStopped
    with pytest.raises(wanted) as error:algo._daily_audit()
    assert "PRIVATE-STOP-BODY-SENTINEL" not in str(error.value) and not logs
    assert algo._mark_refusal_witness_attempted is True


def test_witness_after_error_custody_check_cannot_demote_cancellation(driver,monkeypatch):
    algo,_,_,_,logs,_=mark_witness_case(driver,monkeypatch)
    stopped=[False]
    def locked():
        if stopped[0]:raise SystemExit("PRIVATE-SECOND-STOP")
        return True
    algo.get_locked=locked
    def stop(key):stopped[0]=True;raise KeyboardInterrupt("PRIVATE-FIRST-CANCEL")
    algo.object_store.contains_key=stop
    with pytest.raises(KeyboardInterrupt) as error:algo._daily_audit()
    assert str(error.value)=="CMP28 mark witness cancelled" and not logs


def test_witness_oversize_body_refuses_without_truncation_or_any_store_effect(driver,monkeypatch):
    algo,_,_,_,logs,_=mark_witness_case(driver,monkeypatch)
    config_body=json.loads(algo._evidence._config_raw);config_body["candidate_id"]="X"*4096
    algo._evidence._config_raw=driver._wire(config_body)
    with pytest.raises(ValueError,match="^CMP28 OFF native candidate refused$"):algo._daily_audit()
    assert algo.object_store.calls==[] and mark_pointer(logs)["status"]=="publication_failed"


def test_witness_notice_failure_cannot_replace_the_original_mark_refusal(driver,monkeypatch):
    algo,_,_,_,_,_=mark_witness_case(driver,monkeypatch)
    def log_failed(_):raise RuntimeError("PRIVATE-LOGGER-SENTINEL")
    algo.log=log_failed
    with pytest.raises(ValueError,match="^CMP28 OFF native candidate refused$"):algo._daily_audit()
    assert len(algo.object_store.values)==1
