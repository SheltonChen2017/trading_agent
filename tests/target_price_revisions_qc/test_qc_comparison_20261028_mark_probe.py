"""Pure public-source rendering + synthetic native wrappers, never actual QC."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import ast
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace as NS

import pytest
from research.target_price_revisions_qc import comparison_20261028_mark_probe as p
from research.target_price_revisions_qc import comparison_20261028_mark_read as r

PREFIX=Path('research/target_price_revisions_qc')


@pytest.fixture
def sources():return dict(helper_source=(PREFIX/'comparison_20261028_mark_read.py').read_bytes(),producer_source=(PREFIX/'comparison_20261028_algorithm.py').read_bytes())


def build(sources,**changes):
    args=dict(sources,operation_id='TPR-CMP28-MARK-PROBE-SYNTHETIC-001',git_head='a'*40,failure_session='2021-02-10')
    args.update(changes);return p.build_mark_probe(**args)


def test_single_plain_main_preserves_exact_reviewed_helper_and_fixed_parent_scope(sources):
    raw,report=build(sources);report=json.loads(report)
    assert raw.startswith(sources['helper_source']+b'\n') and len(raw)<=60000
    assert report['main_sha256']==hashlib.sha256(raw).hexdigest() and report['main_bytes']==len(raw)
    tree=ast.parse(raw);compile(tree,'<probe>','exec')
    main=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Main')
    assert ast.unparse(main.bases[0])=='QCAlgorithm'
    names={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
    assert not names & {'set_holdings','market_order','market_on_open_order','liquidate','save_bytes','download'}
    assert report['max_history_calls']==2 and report['max_minute_rows']==1000 and report['max_daily_rows']==2
    assert report['initialize_private_effects'] is report['one_of_five_economic_arms'] is report['native_permission'] is False
    assert report['new_jobs']==report['new_economic_looks']==0 and report['accepted_performance'] is None


@pytest.mark.parametrize('name',['helper_source','producer_source'])
def test_public_source_drift_refuses_independent_pins(sources,name):
    sources[name]+=b'\n'
    with pytest.raises(p.MarkProbeBuildRefusal):build(sources)


@pytest.mark.parametrize('changes',[{'operation_id':'foreign'},{'git_head':'0'*40},{'failure_session':'2020-12-31'},
    {'failure_session':'2026-10-10'},{'failure_session':'2021-2-10'},{'failure_session':True}])
def test_builder_refuses_open_or_malformed_scope(sources,changes):
    with pytest.raises(p.MarkProbeBuildRefusal):build(sources,**changes)


class SID:
    security_type='equity';market='usa'
    def __init__(self,text):self.text=text;self.symbol=text.split(' ')[0]
    def __str__(self):return self.text
    def __eq__(self,other):return isinstance(other,SID) and self.text==other.text
    @staticmethod
    def parse(text):return SID(text)


class Symbol:
    def __init__(self,sid,value):self.id=sid;self.value=value
    def __eq__(self,other):return isinstance(other,Symbol) and self.id==other.id


class Bar:
    def __init__(self,symbol,end,price='50',ff=False):
        self.symbol=symbol;self.end_time=end;self.close=price;self.is_fill_forward=ff


class Store:
    def __init__(self,raw):self.raw=raw;self.present=True;self.calls=[];self.hook=lambda *_:None
    def contains_key(self,key):self.calls.append(('contains',key));self.hook('contains');return self.present
    def read_bytes(self,key):self.calls.append(('read',key));self.hook('read');return self.raw


def synthetic_body():
    expected=datetime(2021,2,10,21,tzinfo=timezone.utc);algorithm=expected+timedelta(minutes=1);observed=expected-timedelta(days=1)
    body=dict(schema='tpr-cmp28-private-mark-refusal-v2',study_id=r.STUDY,candidate_id=r.STUDY+'-OFF',arm='cap_off',
        operation_id=p.PARENT_OPERATION,attempt=4,config_sha256=p.PARENT_CONFIG,source_template_closure_sha256=p.PARENT_TEMPLATE,
        policy_sha256=p.PARENT_POLICY,calendar_sha256=p.PARENT_CALENDAR,project_id=r.PROJECT,job_id=p.PARENT_JOB,
        security_id='PRIVATE.SID X123ABC',data_type='trade_bar',algorithm_utc=algorithm.isoformat(),algorithm_local=algorithm.astimezone(r.NY).isoformat(),
        expected_close_utc=expected.isoformat(),expected_close_local=expected.astimezone(r.NY).isoformat(),
        observed_end_utc=observed.isoformat(),observed_end_local=observed.astimezone(r.NY).isoformat(),
        predicates=dict(observed_equals_expected=False,expected_date_equals_algorithm=True,observed_date_equals_session=False,observed_relation='before'),
        valuation_verification_mode=r.V2_MODE,verification_policy_extended=True,source_inputs_admitted=False,strategy_accepted=False,canonical_admission=False)
    return body


@pytest.fixture
def native(sources,monkeypatch):
    raw,_=build(sources)
    api=ModuleType('AlgorithmImports');api.QCAlgorithm=type('QCAlgorithm',(),{})
    api.TradeBar=Bar;api.Symbol=Symbol;api.SecurityIdentifier=SID;api.SecurityType=NS(EQUITY='equity');api.Market=NS(USA='usa')
    api.Resolution=NS(MINUTE='minute',DAILY='daily');api.DataNormalizationMode=NS(RAW='raw')
    monkeypatch.setitem(sys.modules,api.__name__,api)
    module=ModuleType('synthetic_probe');exec(compile(raw,'<synthetic-probe>','exec'),module.__dict__)
    body=synthetic_body();private=r._canonical(body)
    config=deepcopy(module.PROBE_CONFIG);binding=config['binding']
    arguments={name:binding[name] for name in r.BINDING_ARGUMENTS}
    arguments.update(expected_sha256=hashlib.sha256(private).hexdigest(),expected_bytes=len(private))
    config['binding']=r.prepare_binding_v2(**arguments)
    config['pointer'].update(bytes=len(private),expected_sha256=arguments['expected_sha256'],verified_sha256=arguments['expected_sha256'])
    module.PROBE_CONFIG=config;module.PROBE_CONFIG_JSON=r._canonical(config).decode();module.PROBE_CONFIG_SHA256=hashlib.sha256(module.PROBE_CONFIG_JSON.encode()).hexdigest()
    algo=module.Main();algo.live_mode=False;algo.project_id=r.PROJECT;algo.algorithm_id='';state=NS(locked=False,history=[],yielded=0)
    algo.get_locked=lambda:state.locked
    meta=[];schedule=[]
    for name in ('set_time_zone','set_start_date','set_end_date','set_benchmark'):
        setattr(algo,name,lambda *args,_name=name:meta.append((_name,args)))
    algo.add_equity=lambda *args,**kwargs:(meta.append(('add_equity',(args,kwargs))) or NS(symbol=Symbol(SID('SPY X123ABC'),'SPY')))
    algo.schedule=NS(on=lambda *args:schedule.append(args));algo.date_rules=NS(every_day=lambda _:None);algo.time_rules=NS(at=lambda *_:None)
    algo.object_store=Store(private);algo.settings=NS(daily_precise_end_time=True)
    algo.time=datetime(2021,2,10,16,1);algo.utc_time=datetime(2021,2,10,21,1,tzinfo=timezone.utc)
    symbol=Symbol(SID(body['security_id']),'PRIVATE.SID')
    state.rows={'minute':[Bar(symbol,datetime(2021,2,10,15,59)),Bar(symbol,datetime(2021,2,10,16))],
        'daily':[Bar(symbol,datetime(2021,2,10,16))]}
    state.history_hook=lambda *_:None;state.yield_hook=lambda:None
    class History:
        def __getitem__(self,kind):
            assert kind is Bar
            def request(exact,start,end,resolution,**options):
                state.history.append((exact,start,end,resolution,options));state.history_hook(resolution)
                assert exact.id==symbol.id and start==datetime(2021,2,10) and end==datetime(2021,2,10,16,1)
                assert options==dict(fill_forward=False,extended_market_hours=False,data_normalization_mode='raw')
                def rows():
                    for bar in state.rows[resolution]:state.yield_hook();state.yielded+=1;yield bar
                return rows()
            return request
    algo.history=History();logs=[];algo.log=logs.append;algo.quit=lambda _:meta.append(('quit',()))
    def runtime():algo.algorithm_id='c'*32;state.locked=True
    return NS(module=module,algo=algo,state=state,body=body,private=private,meta=meta,schedule=schedule,logs=logs,runtime=runtime)


def result(case):
    case.algo.on_end_of_algorithm()
    raw=case.logs[-1];assert raw.startswith('CMP28_MARK_PROBE_RESULT ')
    assert 'PRIVATE.SID' not in raw and '2021-02-10T' not in raw
    assert '"close"' not in raw and '"price"' not in raw
    return json.loads(raw.split(' ',1)[1])


def test_initialize_works_with_empty_native_job_and_performs_zero_private_effects(native):
    native.algo.initialize()
    assert not native.algo.object_store.calls and not native.state.history
    assert len(native.schedule)==1
    equity=next(row for row in native.meta if row[0]=='add_equity')
    assert equity[1][0]==('SPY','minute') and equity[1][1]==dict(extended_market_hours=True,data_normalization_mode='raw')
    native.runtime();out=result(native)
    assert out['status']=='scheduled_callback_not_fired' and out['actual_child_job_id']=='c'*32


def test_actual_locked_job_reads_exact_parent_then_two_bounded_exact_sid_histories_and_only_safe_result(native):
    native.algo.initialize();native.runtime();native.algo._probe();out=result(native)
    assert [method for method,_ in native.algo.object_store.calls]==['contains','read']
    assert all(key==native.module.PROBE_CONFIG['binding']['key'] for _,key in native.algo.object_store.calls)
    assert out['status']=='completed_bounded_diagnostic' and out['parent_hash_verified'] is out['parent_schema_verified'] is True
    assert out['native_identity_roundtrip'] is True and out['minute']['rows']==2 and out['daily']['rows']==1
    assert out['minute']['end_equals_parent_close_rows']==out['daily']['end_equals_parent_close_rows']==1
    assert out['minute_daily_close_price_parity'] is True and out['history_calls']==2
    assert out['source_inputs_admitted'] is out['strategy_accepted'] is out['backend_durability_proven'] is False
    before=(list(native.algo.object_store.calls),list(native.state.history));native.algo._probe()
    assert before==(native.algo.object_store.calls,native.state.history)


@pytest.mark.parametrize('mode',['missing','unknown','wrong_hash','read_error','schema'])
def test_missing_unproved_or_invalid_parent_never_dispatches_history(native,mode):
    native.algo.initialize();native.runtime()
    if mode=='missing':native.algo.object_store.present=False
    elif mode=='unknown':native.algo.object_store.present=None
    elif mode=='wrong_hash':native.algo.object_store.raw+=b' '
    elif mode=='read_error':
        def failure(_):raise RuntimeError('PRIVATE-NATIVE-ERROR-BODY')
        native.algo.object_store.read_bytes=failure
    else:
        body=deepcopy(native.body);body['extra']='PRIVATE-SCHEMA-SENTINEL';raw=r._canonical(body)
        args={name:native.module.PROBE_CONFIG['binding'][name] for name in r.BINDING_ARGUMENTS}
        args.update(expected_sha256=hashlib.sha256(raw).hexdigest(),expected_bytes=len(raw))
        native.module.PROBE_CONFIG['binding']=r.prepare_binding_v2(**args)
        native.module.PROBE_CONFIG['pointer'].update(bytes=len(raw),expected_sha256=args['expected_sha256'],verified_sha256=args['expected_sha256'])
        native.algo.object_store.raw=raw
    native.algo._probe();out=result(native)
    assert not native.state.history and out['history_calls']==0 and out['status']!='completed_bounded_diagnostic'
    assert 'PRIVATE-NATIVE-ERROR-BODY' not in native.logs[-1] and 'PRIVATE-SCHEMA-SENTINEL' not in native.logs[-1]
    if mode=='missing':assert native.algo.object_store.calls[0][0]=='contains' and len(native.algo.object_store.calls)==1


@pytest.mark.parametrize('mode',['no_job','parent_job','wrong_project','unlocked'])
def test_runtime_custody_refuses_before_every_private_effect(native,mode):
    native.algo.initialize();native.runtime()
    if mode=='no_job':native.algo.algorithm_id=''
    elif mode=='parent_job':native.algo.algorithm_id=p.PARENT_JOB
    elif mode=='wrong_project':native.algo.project_id=1
    else:native.state.locked=False
    native.algo._probe();out=result(native)
    assert out['status']=='runtime_custody_unproved' and not native.algo.object_store.calls and not native.state.history


@pytest.mark.parametrize('phase',['contains','read'])
def test_post_private_read_custody_drift_stops_without_history(native,phase):
    native.algo.initialize();native.runtime()
    native.algo.object_store.hook=lambda stage:setattr(native.algo,'algorithm_id','d'*32) if stage==phase else None
    native.algo._probe();out=result(native)
    assert out['status']=='runtime_custody_changed' and not native.state.history


def test_history_custody_drift_is_safe_and_does_not_query_second_resolution(native):
    native.algo.initialize();native.runtime();native.state.history_hook=lambda _:setattr(native.algo,'algorithm_id','d'*32)
    native.algo._probe();out=result(native)
    assert out['status']=='runtime_custody_changed' and len(native.state.history)==1


@pytest.mark.parametrize('mode',['wrong_sid','fill_forward','future','untyped'])
def test_invalid_native_history_rows_refuse_without_data_leak_or_fallback(native,mode):
    native.algo.initialize();native.runtime();bar=native.state.rows['minute'][0]
    if mode=='wrong_sid':bar.symbol=Symbol(SID('OTHER X123ABC'),'OTHER')
    elif mode=='fill_forward':bar.is_fill_forward=True
    elif mode=='future':bar.end_time=datetime(2021,2,11,16)
    else:native.state.rows['minute']=[NS(**vars(bar))]
    native.algo._probe();out=result(native)
    assert out['status'] in ('history_row_type_identity_or_fillforward','history_row_outside_request')
    assert len(native.state.history)==1


def test_empty_histories_are_honest_null_price_parity(native):
    native.algo.initialize();native.runtime();native.state.rows={'minute':[],'daily':[]}
    native.algo._probe();out=result(native)
    assert out['status']=='completed_bounded_diagnostic' and out['minute']['rows']==out['daily']['rows']==0
    assert out['minute_daily_close_price_parity'] is None and out['minute']['all_exact_sid'] is None


def test_history_enumeration_never_reads_beyond_the_minute1000_daily2_limits(native):
    native.algo.initialize();native.runtime()
    native.state.rows={'minute':[native.state.rows['minute'][0]]*1001,'daily':[native.state.rows['daily'][0]]*3}
    native.algo._probe();out=result(native)
    assert out['minute']['rows']==1000 and out['daily']['rows']==2 and native.state.yielded==1002
    assert out['minute']['row_bound_reached_result_may_be_incomplete'] is True
    assert out['minute_daily_close_price_parity'] is None


@pytest.mark.parametrize('kind',['cancel','fatal'])
def test_nonordinary_stops_stay_body_free_and_are_not_reported_as_completed(native,kind):
    native.algo.initialize();native.runtime()
    class Fatal(BaseException):pass
    def stop(_):raise (KeyboardInterrupt if kind=='cancel' else Fatal)('PRIVATE-STOP-BODY')
    native.algo.object_store.hook=stop
    with pytest.raises(KeyboardInterrupt if kind=='cancel' else native.module.ProbeStopped) as error:native.algo._probe()
    assert 'PRIVATE-STOP-BODY' not in str(error.value) and not native.state.history and not native.logs


def test_unavailable_failure_session_is_frozen_jan4_and_never_dispatches_history(sources,native):
    raw,report=build(sources,failure_session=None);assert json.loads(report)["configured_failure_session"] is None
    assert b'2021-01-04' in raw
    native.module.PROBE_CONFIG["failure_session"]=None
    native.module.PROBE_CONFIG_JSON=r._canonical(native.module.PROBE_CONFIG).decode()
    native.module.PROBE_CONFIG_SHA256=hashlib.sha256(native.module.PROBE_CONFIG_JSON.encode()).hexdigest()
    native.algo.initialize();native.runtime();native.algo._probe();out=result(native)
    assert out["status"]=="failure_session_unavailable_no_history" and not native.state.history


def test_private_parent_session_must_match_frozen_runtime_failure_session(native):
    native.module.PROBE_CONFIG["failure_session"]="2021-02-11"
    native.module.PROBE_CONFIG_JSON=r._canonical(native.module.PROBE_CONFIG).decode()
    native.module.PROBE_CONFIG_SHA256=hashlib.sha256(native.module.PROBE_CONFIG_JSON.encode()).hexdigest()
    native.algo.initialize();native.runtime();native.algo._probe();out=result(native)
    assert out["status"]=="parent_session_or_valuation_clock_mismatch" and not native.state.history


def test_private_parent_clock_after_actual_child_now_prevents_future_history(native):
    native.algo.initialize();native.runtime();native.algo.utc_time-=timedelta(minutes=2)
    native.algo._probe();out=result(native)
    assert out["status"]=="parent_session_or_valuation_clock_mismatch" and not native.state.history


def test_native_sid_api_failure_is_honest_safe_and_has_no_history_fallback(native,monkeypatch):
    native.algo.initialize();native.runtime()
    def unsupported(_):raise AttributeError("PRIVATE-SID-API-ERROR")
    monkeypatch.setattr(SID,"parse",unsupported)
    native.algo._probe();out=result(native)
    assert out["status"]=="ordinary_native_or_schema_failure" and out["phase"]=="identity_roundtrip" and not native.state.history
    assert "PRIVATE-SID-API-ERROR" not in native.logs[-1]


def test_native_job_drift_during_history_enumeration_stops_before_reading_rows_or_second_request(native):
    native.algo.initialize();native.runtime();native.state.yield_hook=lambda:setattr(native.algo,"algorithm_id","d"*32)
    native.algo._probe();out=result(native)
    assert out["status"]=="runtime_custody_changed" and len(native.state.history)==1


def test_untrusted_reason_body_cannot_escape_fixed_public_probe_enum(native):
    native.algo.initialize();native.runtime();native.algo._record_error(native.module.ProbeRefusal("PRIVATE-REASON-BODY"))
    out=result(native);assert out["status"]=="ordinary_native_or_schema_failure"
    assert "PRIVATE-REASON-BODY" not in native.logs[-1]


def test_end_custody_cannot_overwrite_the_initial_bound_job_after_runtime_drift(native):
    native.algo.initialize();native.runtime();native.algo._probe()
    assert native.algo._child_job=="c"*32
    before=(list(native.algo.object_store.calls),list(native.state.history))
    native.algo.algorithm_id="d"*32
    out=result(native)
    assert out["end_runtime_custody"] is False and out["actual_child_job_id"]=="c"*32
    assert before==(native.algo.object_store.calls,native.state.history)
