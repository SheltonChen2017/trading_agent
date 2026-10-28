"""Synthetic four-arm composition; no native packet, private input or QC effect."""
from copy import deepcopy
from datetime import date, datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS

import pytest

from tests.target_price_revisions_qc import test_qc_comparison_20261028_algorithm as prior
from research.target_price_revisions_qc import comparison_20261028 as comparison
from research.target_price_revisions_qc import comparison_20261028_events as events

PUBLIC=Path("research/target_price_revisions_qc")


@pytest.fixture(autouse=True)
def forbid_actual_effects(monkeypatch):
    import http.client
    from research.target_price_revisions_qc import extended_operations as operations
    def denied(*_args, **_kwargs): raise AssertionError("actual private/provider/QC/operator effect forbidden")
    monkeypatch.setattr(operations,"credential",denied)
    monkeypatch.setattr(operations,"read_private",denied)
    monkeypatch.setattr(operations.Operations,"__init__",denied)
    monkeypatch.setattr(http.client,"HTTPSConnection",denied)


@pytest.fixture
def driver(monkeypatch):
    old=prior.driver.__wrapped__(monkeypatch)
    monkeypatch.setitem(sys.modules,"comparison_20261028_algorithm",old)
    provider=ModuleType("comparison_20261028_signal_native")
    provider.prepare_native_signals=lambda *_args,**_kwargs: NS(scores_for=lambda *_:None)
    monkeypatch.setitem(sys.modules,provider.__name__,provider)
    module=ModuleType("synthetic_multi_native")
    exec(compile((PUBLIC/"comparison_20261028_multi_algorithm.py").read_bytes(),"<public-multi>","exec"),module.__dict__)
    module.previous=old
    return module


def config(module,arm="cap_tilt_200",**changes):
    body={"schema":"tpr-cmp28-multi-native-config-v1","study_id":module.STUDY,
        "candidate_id":module.CANDIDATES.get(arm,"INVALID"),"arm":arm,
        "operation_id":"TPR-CMP28-MULTI-SYNTHETIC-001","attempt":4,"project_id":37650453,
        "policy_sha256":hashlib.sha256(comparison.policy_bytes()).hexdigest(),
        "calendar_sha256":module.calendar_sha256(),"source_template_closure_sha256":"a"*64,
        "prior_attempts_looks_sha256":"b"*64,"signal_packet":{"key":"tpr-cmp28/inputs/synthetic/packet.json",
            "sha256":"c"*64,"bytes":16,"encoding":"utf-8-json",
            "source_inventory_sha256":"e"*64},"source_inputs_admitted":False,"canonical_admission":False}
    body.update(changes)
    raw=json.dumps(body,sort_keys=True,separators=(",",":"))
    return body,raw,hashlib.sha256(raw.encode()).hexdigest()


class Provider:
    def __init__(self,values=None):self.values=values or {};self.calls=[]
    def drain_private_binding_receipts(self,maximum=200):return []
    def scores_for(self,day,cutoff,current):
        self.calls.append((day,cutoff,dict(current)))
        return {"scores_by_sid":{sid:self.values.get(sid,{"state":"available","value":"1"}) for sid in current},
            "states":[],"census":{"synthetic":True},"binding_census":{"synthetic":True},"source_inputs_admitted":False}


def minimal(module,arm="cap_tilt_200"):
    original=prior.minimal(module.previous)
    algo=module.ComparisonMultiAlgorithm();algo.__dict__.update(original.__dict__)
    algo._config,_,_=config(module,arm)
    algo.project_id=algo._config["project_id"]
    algo._signal_provider=Provider()
    return algo


def supplied(module,algo):
    return prior.supplied_inputs(module.previous,algo)


@pytest.mark.parametrize("arm",["cap_tilt_50","cap_tilt_100","cap_tilt_200","pure_tpr"])
def test_closed_multi_config_accepts_exact_declared_four_arms(driver,arm):
    body,raw,digest=config(driver,arm)
    assert driver.validate_config(raw,digest)==body


@pytest.mark.parametrize("field,value",[("arm","cap_off"),("arm","other"),("candidate_id","OFF"),("project_id",1),
    ("project_id",True),("attempt",True),("attempt",0),("schema","old"),("source_inputs_admitted",True),
    ("canonical_admission",True),("policy_sha256","a"*64),("calendar_sha256","a"*64),
    ("source_template_closure_sha256","0"*64),("prior_attempts_looks_sha256","0"*64),("operation_id","foreign")])
def test_multi_config_rejects_wrong_identity_and_authority(driver,field,value):
    _,raw,digest=config(driver,**{field:value})
    with pytest.raises(ValueError):driver.validate_config(raw,digest)


@pytest.mark.parametrize("field,value",[("key","../private.json"),("key","tpr-cmp28/inputs/a/../x"),("key","tpr-cmp28/inputs//x"),
    ("sha256","0"*64),("bytes",True),("bytes",0),("bytes",512*1024**2+1),
    ("encoding","gzip"),("plain_bytes",32),("source_inventory_sha256","bad"),("extra",True)])
def test_packet_descriptor_is_explicit_closed_bounded_and_never_defaulted(driver,field,value):
    body,_,_=config(driver);body["signal_packet"][field]=value
    _,raw,digest=config(driver,signal_packet=body["signal_packet"])
    with pytest.raises(ValueError):driver.validate_config(raw,digest)


def test_fixed_native_session_axis_matches_the_event_producer_hash(driver):
    axis=driver.session_axis()
    assert len(axis)==1534
    assert hashlib.sha256(events.canonical(axis)).hexdigest()==events.SESSION_AXIS_SHA256


@pytest.mark.parametrize("arm",["cap_tilt_50","cap_tilt_100","cap_tilt_200"])
def test_tilt_selects_cap_only_and_filters_unusable_before_one_signal_call(driver,arm):
    algo=minimal(driver,arm);day=supplied(driver,algo)
    # An eleventh cap rank cannot enter via a huge score or a missing score.
    snapshot=algo._snapshots["SPY"][0]
    snapshot["members"]=[{"symbol":prior.Symbol(f"SID-S{n:02}"),"ticker":f"S{n:02}"} for n in range(11)]
    algo._cap_snapshots[0]["caps"].update({f"SID-S{n:02}":{"state":"available","value":str(100-n)} for n in range(11)})
    algo._warning_ids={"SID-S00"}
    algo._prepare_targets(day)
    requested=algo._signal_provider.calls[0][2]
    assert len(algo._signal_provider.calls)==1
    assert "SID-S00" not in requested and "SID-S10" not in requested
    assert all(f"SID-S{n:02}" in requested for n in range(1,10))
    assert "SID-S10" not in algo._targets and "SID-S00" not in algo._targets
    assert algo._decision_coverage[day]["caps_used"] is True


def test_pure_uses_all_members_signed_scores_without_any_caps_mapping(driver):
    algo=minimal(driver,"pure_tpr");day=supplied(driver,algo)
    del algo._cap_snapshots[0]["caps"]
    rows=algo._snapshots["SPY"][0]["members"]
    rows.extend({"symbol":prior.Symbol(f"S{n:02}"),"ticker":f"S{n:02}"} for n in range(11))
    algo._signal_provider=Provider({**{f"S{n:02}":{"state":"available","value":str(n-5)} for n in range(11)},
        "SID-SPY":{"state":"unknown","value":None}})
    algo._prepare_targets(day)
    assert len(algo._signal_provider.calls[0][2])==17
    assert "S00" not in algo._targets and "S01" in algo._targets and "S10" in algo._targets
    assert "SID-SPY" not in algo._targets
    assert algo._decision_coverage[day]["caps_used"] is False
    assert algo._cap_snapshot_coverage_by_day[day] is None
    assert not any(kind=="CAPS" for kind,_ in algo._records)


def test_pure_does_not_require_cap_or_classification_snapshot_when_xlf_is_empty(driver):
    algo=minimal(driver,"pure_tpr");day=supplied(driver,algo)
    algo._snapshots["XLF"][0]["members"]=[]
    algo._cap_snapshots=[]
    algo._prepare_targets(day)
    assert len(algo._target_weights)==5 and algo._decision_coverage[day] is not None


def test_pure_native_classification_callback_never_reads_market_cap(driver,monkeypatch):
    prior.install_groups(monkeypatch)
    algo=minimal(driver,"pure_tpr");supplied(driver,algo)
    algo._cap_snapshots=[]
    algo._cap_context_symbol=prior.Symbol("CTX-FUNDAMENTAL")
    metadata=NS(symbol=algo._cap_context_symbol,is_internal_feed=True,resolution=driver.Resolution.DAILY,
        exchange_time_zone=NS(id="America/New_York"),type=NS(FullName="QuantConnect.Data.Fundamental.FundamentalUniverse"))
    algo.subscription_manager=NS(subscription_data_config_service=NS(get_subscription_data_configs=lambda *_:[metadata]))
    class ClassificationOnly(prior.Fundamental):
        @property
        def market_cap(self):raise AssertionError("pure arm read market cap")
    row=ClassificationOnly();row.symbol=prior.Symbol("SID-XLF")
    row.time=row.end_time=datetime(2020,12,31)
    row.has_fundamental_data=True;row.asset_classification=NS(morningstar_industry_group_code=10320)
    assert algo._capture_caps([row])==[]
    assert "caps" not in algo._cap_snapshots[-1]
    assert algo._cap_snapshots[-1]["insurance"]=={"SID-XLF":"noninsurance"}


def test_all_zero_selected_donor_remains_in_evidence_and_held_position_exits(driver):
    algo=minimal(driver);day=supplied(driver,algo)
    low,high=prior.Symbol("LOW"),prior.Symbol("HIGH")
    algo._snapshots["SPY"][0]["members"]=[{"symbol":low,"ticker":"LOW"},{"symbol":high,"ticker":"HIGH"}]
    algo._cap_snapshots[0]["caps"].update({"LOW":{"state":"available","value":"100"},"HIGH":{"state":"available","value":"90"}})
    algo._signal_provider=Provider({"LOW":{"state":"available","value":"-1"},"HIGH":{"state":"available","value":"1"}})
    algo._attempted_days=set();algo._decision_count=algo._refused_count=0
    algo._assert_clock_subscription=lambda:None;algo._evidence=NS(require_binding=lambda:None)
    algo.portfolio=NS(cash="99000",values=lambda:[NS(invested=True,symbol=low,quantity="10")])
    algo._prior_close_nav=Fraction(100000);algo._prior_close_day=date(2020,12,31)
    algo._prior_mark=lambda symbol:(Fraction(100),Fraction(10000))
    algo._assert_raw_subscriptions=lambda symbol:None
    algo._requested_shares=algo._submitted_shares=algo._submitted=0;algo._tickets=[]
    actual=[]
    algo.market_on_open_order=lambda symbol,quantity,tag:(actual.append((str(symbol.id),quantity)) or NS(order_id=len(actual)))
    algo._rebalance()
    assert algo._target_weights["LOW"]==0 and "LOW" in algo._targets
    assert ("LOW",-10) in actual
    assert algo._decision_coverage[day]["construction"]["per_sleeve"]["SPY"]["target_weights"]["LOW"]==0
    planned=next(payload for kind,payload in algo._records if kind=="ORDER" and "planned" in payload)
    assert planned["zero_weight_selected_count"]==1


@pytest.mark.parametrize("weights",[{"A":-1},{"A":Fraction(1,9)},{"A":1.0}])
def test_order_target_view_rejects_negative_excess_or_float_instead_of_clipping(driver,weights):
    with pytest.raises(ValueError):driver.positive_order_targets(weights)


def test_order_target_view_removes_only_exact_zero_without_mutation(driver):
    weights={"A":Fraction(0),"B":Fraction(1,30)};before=deepcopy(weights)
    assert driver.positive_order_targets(weights)=={"B":Fraction(1,30)} and weights==before


@pytest.mark.parametrize("project",[37650980,37650453])
def test_multi_journal_binds_actual_configured_private_project_and_candidate(driver,project):
    body,_,digest=config(driver,"pure_tpr",project_id=project)
    state=NS(project=project,job="synthetic-job",locked=True)
    journal=driver.MultiJournal(body,digest,lambda:(state.project,state.job,state.locked))
    journal.append("SUMMARY",{"synthetic":True})
    store=prior.NativeStore();pointer=journal.export(store)
    index=json.loads(store.values[pointer["index_key"]])
    assert index["candidate_id"]==body["candidate_id"] and index["project_id"]==project
    assert index["config"]["arm"]=="pure_tpr"
    assert index["source_inputs_admitted"] is index["strategy_accepted"] is False
    saves=[key for method,key in store.calls if method=="save"]
    assert saves[-1].endswith("index.json")
    assert index["schema"]=="tpr-cmp28-private-journal-index-v2-plain" and index["encoding"]=="utf-8-jsonl"
    assert pointer["schema"]=="tpr-cmp28-private-journal-pointer-v2-plain"
    assert all("gzip" not in key for key in pointer)


def test_multi_journal_project_job_drift_refuses_without_store_effect(driver):
    body,_,digest=config(driver)
    state=NS(project=body["project_id"],job="first",locked=True)
    journal=driver.MultiJournal(body,digest,lambda:(state.project,state.job,state.locked));journal.append("SUMMARY",{})
    state.job="other";store=prior.NativeStore()
    with pytest.raises(ValueError):journal.export(store)
    assert store.calls==[]


def test_inherited_raw_money_action_paths_stay_identical(driver):
    for name in ("_prior_mark","_native_factor_basis","on_data","on_order_event","_daily_audit","_cancel_day_orders"):
        assert getattr(driver.ComparisonMultiAlgorithm,name) is getattr(driver.previous.ComparisonOffAlgorithm,name)
    assert driver.ComparisonMultiAlgorithm.initialize is not driver.previous.ComparisonOffAlgorithm.initialize


def test_real_multi_initialization_reads_one_exact_packet_and_registers_new_six(driver,monkeypatch):
    body,raw,digest=config(driver,"cap_tilt_50");driver.EXPECTED_CONFIG_SHA256=digest
    module=ModuleType("comparison_20261028_config");module.CONFIG_JSON=raw;monkeypatch.setitem(sys.modules,module.__name__,module)
    algo=driver.ComparisonMultiAlgorithm();algo.live_mode=False;algo.project_id=body["project_id"];algo.algorithm_id="";algo.get_locked=lambda:False
    algo._initialized_factor_provider=lambda:object()
    reads=[];packet=b"synthetic-packet";assert len(packet)==16
    algo.object_store=NS(read_bytes=lambda key:(reads.append(key) or packet))
    prepared=[];provider=Provider()
    driver.signal_native.prepare_native_signals=lambda raw,**kwargs:(prepared.append((raw,kwargs)) or provider)
    for name in ("set_start_date","set_end_date","set_time_zone","set_account_currency","set_cash","set_warm_up","set_benchmark"):
        setattr(algo,name,lambda *_:None)
    algo.add_chart=lambda *_:None;algo.universe_settings=NS();algo.add_security_initializer=lambda *_:None
    labels=[];universes=[]
    algo.add_equity=lambda label,*args,**kwargs:(labels.append(label) or NS(symbol=prior.Symbol("ETF-"+label,label)))
    algo.universe=NS(etf=lambda symbol,universe_filter_func:NS(symbol=prior.Symbol("CTX-"+symbol.id),filter=universe_filter_func))
    def add_universe(value):
        if callable(value):value=NS(symbol=prior.Symbol("CTX-FUNDAMENTAL"),filter=value)
        universes.append(value);return value
    algo.add_universe=add_universe;algo.date_rules=NS(every_day=lambda symbol:None);algo.time_rules=NS(at=lambda *_:None);algo.schedule=NS(on=lambda *_:None)
    algo.initialize()
    assert reads==[body["signal_packet"]["key"]]
    assert len(prepared)==1 and prepared[0][0]==packet
    kwargs=prepared[0][1]
    assert kwargs["expected_sha256"]==body["signal_packet"]["sha256"]
    assert kwargs["expected_bytes"]==body["signal_packet"]["bytes"]
    assert set(kwargs)=={"expected_sha256","expected_bytes","sessions","expected_source_inventory_sha256"}
    assert kwargs["expected_source_inventory_sha256"]==body["signal_packet"]["source_inventory_sha256"]
    assert algo._signal_provider is provider
    assert labels==list(driver.SLEEVES) and len(universes)==7


def test_partial_multi_terminal_has_own_candidate_private_index_and_null_final_nav(driver):
    algo=minimal(driver,"pure_tpr");body,_,digest=config(driver,"pure_tpr");driver.EXPECTED_CONFIG_SHA256=digest
    algo._evidence=driver.MultiJournal(body,digest,lambda:(algo.project_id,algo.algorithm_id,True))
    algo._log_audit=lambda kind,payload:algo._evidence.append(kind,payload)
    for name in ("_decision_count","_refused_count","_submitted","_fill_events","_requested_shares","_submitted_shares","_filled_shares",
        "_position_ledger_mismatches","_risk_breaches","_name_soft_cap_breaches","_clock_assertions"):
        setattr(algo,name,0)
    for name in ("_fees","_max_cash_residual","_max_nav_residual","_max_name_exposure"):
        setattr(algo,name,Fraction(0))
    algo._valuation_days=set();algo._attempted_days=set();algo._prior_close_nav=Fraction(100000);algo._prior_close_day=None
    algo._delisting_audit=driver.cap_observer.empty_audit();algo._warmup_finished_minute_validated=False
    algo.object_store=prior.NativeStore();logs=[];algo.log=logs.append
    algo.on_end_of_algorithm()
    summary=json.loads(logs[0].split(" ",1)[1])
    assert logs[0].startswith("CMP28_MULTI_SUMMARY ")
    assert summary["arm"]=="pure_tpr" and summary["candidate_id"]==body["candidate_id"]
    assert summary["accepted_performance"] is summary["final_nav"] is summary["last_observed_nav"] is None
    assert summary["source_inputs_admitted"] is summary["strategy_accepted"] is False


def test_large_pure_score_frame_is_hashed_whole_and_privately_chunked_without_dropping(driver):
    algo=minimal(driver,"pure_tpr");day=supplied(driver,algo)
    del algo._cap_snapshots[0]["caps"]
    ids=[f"N{n:04}-"+"X"*110 for n in range(4050)]
    algo._snapshots["IWM"][0]["members"]=[{"symbol":prior.Symbol(sid,f"T{n}"),"ticker":f"T{n}"} for n,sid in enumerate(ids)]
    values={sid:{"state":"available","value":"0."+"1"*60} for sid in ids}
    algo._signal_provider=Provider(values)
    algo._prepare_targets(day)
    frames=[payload for kind,payload in algo._records if kind=="COVERAGE" and payload.get("kind")=="signal_frame"]
    assert len(frames)==21 and [row["part"] for row in frames]==list(range(21))
    restored={sid:value for frame in frames for sid,value in frame["scores_by_sid"].items()}
    assert len(restored)==4055 and all(len(frame["scores_by_sid"])<=200 for frame in frames)
    assert all(len(driver._wire(frame))<driver.MAX_RECORD for frame in frames)
    with pytest.raises(ValueError):driver.core.exact_json(restored)
    assert driver.score_frame_sha256(restored)==frames[0]["score_frame_sha256"]
    assert algo._decision_coverage[day]["signal_scores_sha256"]==driver.score_frame_sha256(restored)


@pytest.mark.parametrize("mode",["missing","extra","malformed"])
def test_signal_provider_does_not_silently_drop_invent_or_mislabel_requested_names(driver,mode):
    algo=minimal(driver);day=supplied(driver,algo)
    def scores(*_):
        body={"scores_by_sid":{sid:{"state":"available","value":"1"} for sid in ("SID-"+s for s in driver.SLEEVES)}}
        if mode=="missing":body["scores_by_sid"].pop("SID-SPY")
        elif mode=="extra":body["scores_by_sid"]["FOREIGN"]={"state":"available","value":"1"}
        else:body["scores_by_sid"]["SID-SPY"]={"state":"available","value":1.0}
        return body
    algo._signal_provider=NS(scores_for=scores,drain_private_binding_receipts=lambda **_:[])
    with pytest.raises(ValueError):algo._prepare_targets(day)


@pytest.mark.parametrize("mode",["foreign_project","wrong_candidate","off_arm"])
def test_standalone_multi_journal_rejects_unowned_or_wrong_arm_binding(driver,mode):
    body,_,digest=config(driver)
    if mode=="foreign_project":body["project_id"]=1
    elif mode=="wrong_candidate":body["candidate_id"]="old"
    else:body["arm"]="cap_off"
    with pytest.raises(ValueError):driver.MultiJournal(body,digest,lambda:(body["project_id"],"job",True))


def test_multi_source_uses_shared_config_and_readable_data_only():
    raw=(PUBLIC/"comparison_20261028_multi_algorithm.py").read_text()
    assert "from comparison_20261028_config import CONFIG_JSON" in raw
    assert "comparison_20261028_multi_config" not in raw
    assert "gzip" not in raw and "extended_compressed_store" not in raw
    compile(raw,"<plain-multi>","exec")


def test_native_binding_receipts_are_retained_only_in_bounded_private_journal_parts(driver):
    algo=minimal(driver);day=supplied(driver,algo)
    remaining=[{"synthetic_private_binding":n} for n in range(401)]
    calls=[]
    def drain(maximum):
        calls.append(maximum);rows=remaining[:maximum];del remaining[:maximum];return rows
    algo._signal_provider.drain_private_binding_receipts=drain
    algo._prepare_targets(day)
    rows=[payload for kind,payload in algo._records if kind=="COVERAGE" and payload.get("kind")=="native_binding_receipts"]
    assert calls==[200]*4 and [len(row["receipts"]) for row in rows]==[200,200,1]
    assert [row["part"] for row in rows]==[0,1,2] and not remaining
    assert all(row["source_inputs_admitted"] is row["historical_identity_proven"] is False for row in rows)


@pytest.mark.parametrize("rows",[[{}]*201,None,["not-a-receipt"]])
def test_invalid_provider_receipt_batch_refuses_instead_of_losing_private_evidence(driver,rows):
    algo=minimal(driver);day=supplied(driver,algo)
    algo._signal_provider.drain_private_binding_receipts=lambda **_:rows
    with pytest.raises(ValueError):algo._prepare_targets(day)


def test_all_four_signal_arms_inherit_the_same_native_close_corroboration_and_safe_refusal(driver):
    assert driver.ComparisonMultiAlgorithm._corroborate_raw_daily_close is driver.previous.ComparisonOffAlgorithm._corroborate_raw_daily_close
    assert driver.ComparisonMultiAlgorithm._daily_audit is driver.previous.ComparisonOffAlgorithm._daily_audit
    assert driver.ComparisonMultiAlgorithm._reject_mark is driver.previous.ComparisonOffAlgorithm._reject_mark
    for arm in driver.CANDIDATES:
        algo=minimal(driver,arm)
        summary=algo._mark_verification_summary()
        assert summary["mode"]=="strict_minute_or_raw_daily_equal_close_v1"
        assert summary["daily_requests"]==summary["daily_corroborated_marks"]==summary["refused_marks"]==0
