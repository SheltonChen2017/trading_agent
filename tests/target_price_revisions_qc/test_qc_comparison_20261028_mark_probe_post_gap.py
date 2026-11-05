"""Synthetic five-session identity/coverage diagnostic; no private/native IO."""
import ast
from copy import deepcopy
from datetime import datetime,timedelta
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace as NS

import pytest
from research.target_price_revisions_qc import comparison_20261028_mark_probe_post_gap as p
from research.target_price_revisions_qc import comparison_20261028_mark_read as reader
from tests.target_price_revisions_qc import test_qc_comparison_20261028_mark_probe_control as control
from tests.target_price_revisions_qc import test_qc_comparison_20261028_mark_probe as old

PREFIX=Path('research/target_price_revisions_qc')


@pytest.fixture
def sources():
    return {'control_source':(PREFIX/'comparison_20261028_mark_probe_control.py').read_bytes(),
        **{name:(PREFIX/file).read_bytes() for name,file in (
            ('base_probe_source','comparison_20261028_mark_probe.py'),('helper_source','comparison_20261028_mark_read.py'),
            ('producer_source','comparison_20261028_algorithm.py'))}}


def build(sources,**changes):
    args=dict(sources,operation_id='TPR-CMP28-MARK-PROBE-POST-GAP-SYNTHETIC-001',git_head='a'*40)
    args.update(changes);return p.build_mark_probe_post_gap(**args)


def literal(raw,name):
    node=next(node for node in ast.parse(raw).body if isinstance(node,ast.Assign) and len(node.targets)==1
        and isinstance(node.targets[0],ast.Name) and node.targets[0].id==name)
    return ast.literal_eval(node.value)


def test_plain_main_separates_parent_failure_child_day_and_fixed_five_session_scope(sources):
    raw,report=build(sources);report=json.loads(report);tree=ast.parse(raw);compile(tree,'<post-gap>','exec')
    assert raw.startswith(sources['helper_source']+b'\n') and len(raw)==report['main_bytes']<60000
    assert hashlib.sha256(raw).hexdigest()==report['main_sha256']
    cfg=json.loads(literal(raw,'PROBE_CONFIG_JSON'))
    assert cfg['failure_session']=='2021-02-10' and cfg['configured_session']==cfg['diagnostic_session']=='2021-02-12'
    assert cfg['history_start_session']=='2021-02-08' and cfg['history_end_local']=='2021-02-12T16:01:00'
    assert cfg['allowed_failure_date_offsets']==[-2,-1,0,1,2]
    assert report['max_history_calls']==4 and report['max_total_history_rows']==4810
    assert report['max_minute_rows_per_symbol']==2400 and report['max_daily_rows_per_symbol']==5
    assert all(report[name] is False for name in ('universal_absence_proven','terminal_proven','financial_recovery_proven',
        'target_data_gap_proven','one_of_five_economic_arms','native_permission'))
    calls={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
    assert not calls&{'set_holdings','market_order','market_on_open_order','liquidate','save_bytes','set_market_price','download'}


@pytest.mark.parametrize('name',['control_source','base_probe_source','helper_source','producer_source'])
def test_each_independent_public_source_pin_rejects_one_byte_drift(sources,name):
    sources[name]+=b'\n'
    with pytest.raises(p.PostGapProbeRefusal):build(sources)


@pytest.fixture
def native(sources,monkeypatch):
    original=control.native.__wrapped__({name:value for name,value in sources.items() if name!='control_source'},monkeypatch)
    raw,_=build(sources);module=ModuleType('synthetic_post_gap');exec(compile(raw,'<post-gap>','exec'),module.__dict__)
    cfg=deepcopy(module.PROBE_CONFIG);cfg['binding']=original.module.PROBE_CONFIG['binding'];cfg['pointer']=original.module.PROBE_CONFIG['pointer']
    module.PROBE_CONFIG=cfg;module.PROBE_CONFIG_JSON=reader._canonical(cfg).decode();module.PROBE_CONFIG_SHA256=hashlib.sha256(module.PROBE_CONFIG_JSON.encode()).hexdigest()
    algo=module.Main();algo.__dict__.update(original.algo.__dict__);original.algo=algo;original.module=module
    state=original.control;state.registry={};state.calendar=[];state.calendar_hook=lambda *_:None
    security_type=sys.modules['QuantConnect.Securities'].Security
    class Hours:
        def __init__(self,label):self.time_zone=NS(Id='America/New_York');self.label=label
        def get_next_market_open(self,midnight,extended):
            assert midnight.time()==datetime.min.time() and extended is False
            state.calendar.append((self.label,'open',midnight.day));state.calendar_hook(self.label,'open')
            return midnight.replace(hour=9,minute=30)
        def get_next_market_close(self,midnight,extended):
            assert midnight.time()==datetime.min.time() and extended is False
            state.calendar.append((self.label,'close',midnight.day));state.calendar_hook(self.label,'close')
            return midnight.replace(hour=16)
    sys.modules['QuantConnect.Securities'].SecurityExchangeHours=Hours
    class Registry:
        def __getitem__(self,symbol):return state.registry[str(symbol.id)]
    algo.securities=Registry()
    original_add=algo.add_security
    def add_security(symbol,**kwargs):
        security=original_add(symbol,**kwargs);security.exchange=NS(hours=Hours('target'))
        state.registry[str(symbol.id)]=security;return security
    algo.add_security=add_security
    class History:
        def __getitem__(self,kind):
            assert kind is old.Bar
            def request(symbol,start,end,resolution,**options):
                label=('control_' if symbol.id==algo._clock.id else '')+resolution
                state.events.append(label);state.history.append((label,symbol,options));state.hook(label)
                assert start==datetime(2021,2,8) and end==datetime(2021,2,12,16,1)
                assert options==dict(fill_forward=False,extended_market_hours=False,data_normalization_mode='raw')
                def rows():
                    for row in state.rows.get(label,[]):state.yielded+=1;yield row
                return rows()
            return request
    algo.history=History()
    def initialize():
        algo.time=datetime(2021,2,12,16,1);algo.utc_time=datetime(2021,2,12,21,1)
        algo.initialize()
        security=security_type(algo._clock);security.exchange=NS(hours=Hours('control'))
        state.registry[str(algo._clock.id)]=security
        target=old.Symbol(old.SID(original.body['security_id']),'PRIVATE.SID')
        def bar(symbol,day,volume='100'):
            row=old.Bar(symbol,datetime(2021,2,day,16),'50');row.volume=volume;return row
        state.rows={label:[bar(symbol,day) for day in range(8,13)] for label,symbol in (
            ('control_minute',algo._clock),('control_daily',algo._clock),('minute',target),('daily',target))}
        algo.algorithm_id='c'*32;original.state.locked=True
    original.initialize=initialize;original.Hours=Hours
    return original


def result(case):
    case.algo.on_end_of_algorithm();raw=case.logs[-1];assert raw.startswith('CMP28_MARK_PROBE_RESULT ')
    assert not any(secret in raw for secret in ('PRIVATE.SID','2021-02-10T','2021-02-12T','PRIVATE-ERROR','"price"','"volume"'))
    return json.loads(raw.split(' ',1)[1])


def test_parent_feb10_is_preserved_child_feb12_observes_each_native_session_and_retains_offset_counts(native):
    native.initialize();assert native.algo.object_store.calls==[]
    native.control.rows['minute']=[row for row in native.control.rows['minute'] if row.end_time.day!=10]
    native.control.rows['daily']=[row for row in native.control.rows['daily'] if row.end_time.day!=10]
    native.algo._probe();out=result(native)
    assert out['status']=='completed_post_gap_observations' and out['history_calls']==4
    assert out['control_request_path_status']=='positive_five_session_controls_observed'
    assert out['parent_session_matches_config'] is True and native.body['algorithm_local'].startswith('2021-02-10')
    assert out['target_post_failure_rows_observed']=={'minute':True,'daily':True}
    assert len(native.control.calendar)==20 and out['native_regular_calendars']['target']['verified'] is True
    for label in ('minute','daily'):
        assert out[label]['by_failure_date_offset']['0']['rows']==0
        assert out[label]['by_failure_date_offset']['1']['rows']==out[label]['by_failure_date_offset']['2']['rows']==1
    assert all(out[name] is False for name in ('target_data_gap_proven','universal_absence_proven','terminal_proven','strategy_accepted'))
    assert native.control.events==['contains','read','control_minute','control_daily','add_security','configs','minute','daily']
    before=list(native.control.events);native.algo._probe();assert native.control.events==before


@pytest.mark.parametrize('mode',['all_empty','no_after','zero_daily','negative_minute','missing_spy_day'])
def test_absence_or_incomplete_controls_never_prove_universal_absence_terminal_or_data_gap(native,mode):
    native.initialize()
    if mode=='all_empty':native.control.rows={name:[] for name in native.control.rows}
    elif mode=='no_after':
        for name in ('minute','daily'):native.control.rows[name]=[row for row in native.control.rows[name] if row.end_time.day<=10]
    elif mode=='zero_daily':native.control.rows['control_daily'][-1].volume='0'
    elif mode=='negative_minute':native.control.rows['control_minute'][0].volume='-1'
    else:native.control.rows['control_daily'].pop(2)
    native.algo._probe();out=result(native)
    if mode!='no_after':assert out['status']=='request_path_unproved'
    if mode in ('all_empty','no_after'):assert out['target_post_failure_rows_observed']=={'minute':False,'daily':False}
    assert out['universal_absence_proven'] is out['terminal_proven'] is out['target_data_gap_proven'] is False


@pytest.mark.parametrize('fault',['wrong_sid','fillforward','future','before_window','extended','daily_wrong_close','bad_volume'])
def test_exact_rows_must_be_typed_native_identity_noff_within_own_regular_session(native,fault):
    native.initialize();label='daily' if fault=='daily_wrong_close' else 'minute';row=native.control.rows[label][0]
    if fault=='wrong_sid':row.symbol=old.Symbol(old.SID('FOREIGN X123ABC'),'PRIVATE.SID')
    elif fault=='fillforward':row.is_fill_forward=True
    elif fault=='future':row.end_time=datetime(2021,2,15,16)
    elif fault=='before_window':row.end_time=datetime(2021,2,5,16)
    elif fault=='extended':row.end_time=datetime(2021,2,8,9)
    elif fault=='daily_wrong_close':row.end_time=datetime(2021,2,8,15,59)
    else:row.volume='nan'
    native.algo._probe();out=result(native)
    assert out['status'] in ('history_row_type_identity_or_fillforward','history_row_outside_request',
        'native_regular_history_endpoint_unproved','native_volume_representation')
    assert out['control_minute']['rows']==5 and out['control_daily']['rows']==5
    assert out['target_data_gap_proven'] is False


@pytest.mark.parametrize('fault',['utc_mismatch','wrong_day','wrong_time','job_drift'])
def test_actual_child_clock_and_custody_are_required_before_private_effects(native,fault):
    native.initialize()
    if fault=='utc_mismatch':native.algo.utc_time+=timedelta(minutes=1)
    elif fault=='wrong_day':native.algo.time-=timedelta(days=1);native.algo.utc_time-=timedelta(days=1)
    elif fault=='wrong_time':native.algo.time-=timedelta(minutes=1);native.algo.utc_time-=timedelta(minutes=1)
    else:native.algo.get_locked=lambda:False
    native.algo._probe();out=result(native)
    assert not native.algo.object_store.calls and out['history_calls']==0
    assert out['status'] in ('post_gap_runtime_clock_unproved','runtime_custody_unproved')


@pytest.mark.parametrize('fault',['wrong_day','wrong_zone','wrong_type','calendar_custody'])
def test_native_calendar_proof_refuses_before_history_if_calendar_or_custody_unproved(native,fault):
    native.initialize();security=native.control.registry[str(native.algo._clock.id)]
    if fault=='wrong_day':security.exchange.hours.get_next_market_close=lambda day,_:day+timedelta(days=1,hours=16)
    elif fault=='wrong_zone':security.exchange.hours.time_zone.Id='UTC'
    elif fault=='wrong_type':security.exchange.hours=NS(time_zone=NS(Id='America/New_York'))
    else:native.control.calendar_hook=lambda *_:setattr(native.algo,'algorithm_id','d'*32)
    native.algo._probe();out=result(native)
    assert out['history_calls']==0 and out['native_regular_calendars']['control'] is None
    assert out['status'] in ('native_regular_calendar_unproved','runtime_custody_changed')
    if fault=='calendar_custody':assert len(native.control.calendar)==1


@pytest.mark.parametrize('kind',['cancel','fatal'])
def test_nonordinary_stops_preserve_body_free_semantics_during_native_calendar(native,kind):
    native.initialize()
    class Fatal(BaseException):pass
    def stop(*_):raise (KeyboardInterrupt if kind=='cancel' else Fatal)('PRIVATE-ERROR')
    native.control.calendar_hook=stop
    with pytest.raises(KeyboardInterrupt if kind=='cancel' else native.module.ProbeStopped) as error:native.algo._probe()
    assert 'PRIVATE-ERROR' not in str(error.value) and not native.control.history


def test_per_symbol_history_bounds_are_hard_and_no_extra_row_is_peeked(native):
    native.initialize()
    for label in ('control_minute','minute'):native.control.rows[label]*=500
    for label in ('control_daily','daily'):native.control.rows[label]*=2
    native.algo._probe();out=result(native)
    assert out['history_calls']==4 and native.control.yielded==4810
    assert all(out[label]['row_bound_reached_result_may_be_incomplete'] for label in ('control_minute','control_daily','minute','daily'))


@pytest.mark.parametrize('change',[{'start':datetime(2021,2,9)},{'end':datetime(2021,2,12,16,2)},
    {'maximum':2401},{'maximum':None,'resolution':'unsupported'},{'label':'daily'},{'windows':{}}])
def test_private_history_helper_cannot_broaden_closed_range_type_label_or_row_budget(native,change):
    native.initialize();windows=native.algo._session_windows(native.algo._clock,'control')
    args=dict(symbol=native.algo._clock,start=datetime(2021,2,8),end=datetime(2021,2,12,16,1),
        resolution=native.module.Resolution.MINUTE,maximum=2400,windows=windows,label='control_minute')
    args.update(change)
    with pytest.raises(native.module.ProbeRefusal):native.algo._history(**args)
    assert not native.control.history
