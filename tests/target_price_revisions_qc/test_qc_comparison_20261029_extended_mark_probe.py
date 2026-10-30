"""Synthetic extended-day typed history; no market/native/private I/O."""
import ast
from copy import deepcopy
from datetime import datetime,timedelta
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from research.target_price_revisions_qc import comparison_20261029_extended_mark_probe as p
from tests.target_price_revisions_qc import test_qc_comparison_20261029_mark_tick_probe as tick
from tests.target_price_revisions_qc import test_qc_comparison_20261028_mark_probe_post_gap as old
from tests.target_price_revisions_qc import test_qc_comparison_20261028_mark_probe as base

PREFIX=Path('research/target_price_revisions_qc')
FILES={'tick_source':'comparison_20261029_mark_tick_probe.py',**tick.FILES}


@pytest.fixture
def sources():return {name:(PREFIX/file).read_bytes() for name,file in FILES.items()}


def build(sources,**changes):
    args=dict(sources,operation_id='TPR-CMP28-MARK-PROBE-EXTENDED-SYNTHETIC-008',git_head='a'*40)
    args.update(changes);return p.build_extended_mark_probe(**args)


class MinuteBar:
    def __init__(self,symbol,stamp):
        self.symbol=symbol;self.time=stamp;self.period=timedelta(minutes=1)
        self.end_time=stamp+self.period;self.is_fill_forward=False
    @property
    def close(self):raise AssertionError('PRIVATE-OHLC-READ')
    @property
    def value(self):raise AssertionError('PRIVATE-QUOTE-VALUE-READ')
    @property
    def volume(self):raise AssertionError('PRIVATE-VOLUME-READ')


class TradeBar(MinuteBar):pass
class QuoteBar(MinuteBar):pass


@pytest.fixture
def native(sources,monkeypatch):
    def render(values,**changes):return build(dict(sources,**values),**changes)
    monkeypatch.setattr(old,'build',render)
    case=old.native.__wrapped__({name:value for name,value in sources.items()
        if name not in ('tick_source','native_post_gap_source','post_gap_source')},monkeypatch)
    case.module.TradeBar=TradeBar;case.module.QuoteBar=QuoteBar
    sys.modules['AlgorithmImports'].TradeBar=TradeBar;sys.modules['AlgorithmImports'].QuoteBar=QuoteBar
    state=case.control;state.extended_history=[];state.extended_rows={};state.extended_yielded=0
    state.extended_hook=lambda *_:None;state.iterator_hook=lambda *_:None
    class History:
        def __getitem__(self,kind):
            assert kind in (TradeBar,QuoteBar)
            def request(symbol,start,end,resolution,**options):
                origin='control' if symbol.id==case.algo._clock.id else 'target'
                label=origin+('_trade' if kind is TradeBar else '_quote')
                assert type(start) is datetime and start==datetime(2021,2,10,4)
                assert type(end) is datetime and end==datetime(2021,2,10,20)
                assert resolution=='minute' and options==dict(fill_forward=False,extended_market_hours=True,data_normalization_mode='raw')
                state.events.append(label);state.extended_history.append((label,kind,symbol,start,end,options))
                state.extended_hook(label)
                class Rows:
                    def __iter__(self):
                        state.iterator_hook(label)
                        def rows():
                            for row in state.extended_rows[label]:
                                state.extended_yielded+=1;state.extended_hook('next_'+label);yield row
                        return rows()
                return Rows()
            return request
    case.algo.history=History();initialize=case.initialize
    def setup():
        initialize();case.target=base.Symbol(base.SID(case.body['security_id']),'PRIVATE.SID')
        # Covers both sides of regular-open/close and the exact 20:00 end.
        stamps=[datetime(2021,2,10,h,m) for h,m in ((4,0),(9,29),(9,30),(15,59),(16,0),(19,59))]
        state.extended_rows={label:[kind(symbol,stamp) for stamp in stamps] for label,kind,symbol in (
            ('control_trade',TradeBar,case.algo._clock),('control_quote',QuoteBar,case.algo._clock),
            ('target_trade',TradeBar,case.target),('target_quote',QuoteBar,case.target))}
    case.initialize=setup
    return case


def result(case):
    out=old.result(case);raw=case.logs[-1]
    assert not any(secret in raw for secret in ('PRIVATE.SID','X123ABC','PRIVATE-ERROR','PRIVATE-OHLC',
        'PRIVATE-QUOTE','PRIVATE-VOLUME','"price"','"volume"','2021-02-10T','2021-02-12T'))
    return out


def methods(raw):
    main=next(n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name=='Main')
    return {n.name:n for n in main.body if isinstance(n,ast.FunctionDef)}


def test_plain_main_exact_seven_source_closure_closed_scopes_and_no_authority(sources):
    raw,report_raw=build(sources);report=json.loads(report_raw);tree=ast.parse(raw);compile(tree,'main.py','exec')
    assert raw.startswith(sources['helper_source']+b'\n') and len(raw)==report['main_bytes']<60000
    assert hashlib.sha256(raw).hexdigest()==report['main_sha256'] and report['public_source_sha256']==p.PINS
    cfg_raw=old.literal(raw,'PROBE_CONFIG_JSON').encode('ascii');cfg=json.loads(cfg_raw)
    assert hashlib.sha256(cfg_raw).hexdigest()==old.literal(raw,'PROBE_CONFIG_SHA256')==report['config_sha256']
    assert cfg['schema']=='tpr-cmp28-native-extended-mark-probe-config-v1'
    assert cfg['diagnostic_definition']==p.DEFINITION and cfg['public_source_sha256']==p.PINS
    assert cfg['failure_session']=='2021-02-10' and cfg['configured_session']==cfg['diagnostic_session']=='2021-02-12'
    assert cfg['history_start_local']=='2021-02-10T04:00:00' and cfg['history_end_local']=='2021-02-10T20:00:00'
    assert cfg['history_resolution']=='minute' and cfg['history_types']==['TradeBar','QuoteBar']
    assert cfg['extended_market_hours'] is True and cfg['fill_forward'] is False and cfg['data_normalization_mode']=='RAW'
    assert report['max_history_calls']==4 and report['max_bar_rows_per_call']==961 and report['max_total_history_rows']==3844
    assert report['max_native_market_hours_calls']==4 and report['max_contains']==report['max_reads']==1
    assert report['max_clock_bars']==1440
    for key in ('native_permission','native_clock_class_attested','native_origin_authenticated','rights_verified',
            'point_in_time_verified','source_inputs_admitted','financial_recovery_proven','cache_updated','derived_bar_created',
            'sdk_hard_timeout_proven','sdk_preallocation_byte_bound_proven','external_manifest_attested',
            'one_of_five_economic_arms','canonical_admission','regular_session_no_trade_proven','provider_hole_excluded',
            'native_routing_fix_proven','prices_consumed','volume_consumed','quotes_used_as_trades'):
        assert report[key] is False
    attrs={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    assert not attrs&{'save_bytes','set_market_price','set_holdings','market_order','market_on_open_order','liquidate','download'}
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('exec','eval','HistoryRequest') for n in ast.walk(tree))
    assert not any(isinstance(n,ast.keyword) and n.arg=='tick_type' for n in ast.walk(tree))
    assert not any(isinstance(n,ast.Import) and any(a.name in ('gzip','zlib','codecs') for a in n.names) for n in ast.walk(tree))


def test_reviewed_native_effect_config_registration_and_lifecycle_guards_are_unchanged(sources):
    raw,_=build(sources)
    predecessor,_=p.prior.build_mark_tick_probe(**{name:value for name,value in sources.items() if name!='tick_source'},
        operation_id='TPR-CMP28-MARK-PROBE-EXTENDED-SYNTHETIC-008',git_head='a'*40)
    before,after=methods(predecessor),methods(raw)
    for name in ('_bound','_tick_config_bound','_effect','_register_parent','_record_error','on_data','on_end_of_algorithm'):
        assert ast.dump(before[name])==ast.dump(after[name]),name
    assert ast.unparse(after['_bound'].body[0])==ast.unparse(after['_bound'].body[-1])=='self._tick_config_bound()'
    for name,value in sources.items():assert hashlib.sha256(value).hexdigest()==p.PINS[name]


@pytest.mark.parametrize('name',list(FILES))
def test_independent_pin_rejects_any_predecessor_byte_change(sources,name):
    sources[name]+=b'\n'
    with pytest.raises(p.ExtendedMarkProbeBuildRefusal):build(sources)


@pytest.mark.parametrize('changes',[{'operation_id':'foreign'},{'git_head':'0'*40},{'git_head':False}])
def test_operation_or_head_cannot_be_relabelled(sources,changes):
    with pytest.raises(p.ExtendedMarkProbeBuildRefusal):build(sources,**changes)


def test_four_typed_native_requests_separate_premarket_regular_postmarket_and_boundaries(native):
    native.initialize();assert native.algo.object_store.calls==[] and native.control.extended_history==[]
    native.algo._probe();out=result(native)
    assert out['status']=='completed_bounded_extended_observations' and out['history_calls']==4
    assert len(native.control.calendar)==out['native_market_hours_calls']==4
    assert out['bar_rows_encountered']==native.control.extended_yielded==24
    assert native.control.events==['contains','read','control_trade','control_quote','add_security','configs','target_trade','target_quote']
    for label in ('control_trade','control_quote','target_trade','target_quote'):
        cell=out[label];assert cell['complete'] is True and cell['rows_validated']==cell['rows_encountered']==6
        assert cell['pre_market_rows']==cell['regular_session_rows']==cell['post_market_rows']==2
        for key in ('end_equals_regular_open_rows','start_equals_regular_open_rows','end_equals_regular_close_rows','start_equals_regular_close_rows'):
            assert cell[key]==1
        assert cell['prices_consumed'] is cell['volume_consumed'] is cell['quotes_used_as_trades'] is False
    assert out['target_no_rows_observed_in_bound']=={'trade':False,'quote':False}
    for key in ('regular_session_no_trade_proven','provider_hole_excluded','native_routing_fix_proven',
            'native_origin_authenticated','point_in_time_verified','rights_verified','financial_recovery_proven',
            'cache_updated','derived_bar_created','source_inputs_admitted','canonical_admission','universal_absence_proven',
            'terminal_proven','target_data_gap_proven','cash_changes_made','one_of_five_economic_arms'):
        assert out[key] is False
    assert out['orders_submitted']==0
    before=list(native.control.events);native.algo._probe();assert native.control.events==before


@pytest.mark.parametrize('mode',['all_empty','target_empty','target_quote_only','control_trade_empty','after_hours_only'])
def test_empty_quote_only_or_after_hours_is_not_regular_no_trade_or_financial_recovery(native,mode):
    native.initialize();rows=native.control.extended_rows
    if mode=='all_empty':native.control.extended_rows={label:[] for label in rows}
    elif mode=='target_empty':rows['target_trade']=[];rows['target_quote']=[]
    elif mode=='target_quote_only':rows['target_trade']=[]
    elif mode=='control_trade_empty':rows['control_trade']=[]
    else:
        for label in ('target_trade','target_quote'):rows[label]=[row for row in rows[label] if row.time.hour<9 or row.time.hour>=16]
    native.algo._probe();out=result(native)
    assert out['history_calls']==4
    if mode in ('all_empty','control_trade_empty'):
        assert out['status']=='request_path_unproved' and out['target_no_rows_observed_in_bound']['trade'] is None
    else:assert out['status']=='completed_bounded_extended_observations'
    if mode in ('target_empty','target_quote_only'):assert out['target_no_rows_observed_in_bound']['trade'] is True
    assert out['regular_session_no_trade_proven'] is out['provider_hole_excluded'] is out['financial_recovery_proven'] is False


@pytest.mark.parametrize('fault',['type','quote_as_trade','sid','ff','unknown_ff','period','unknown_period','wrong_day',
    'before_start','after_end','end_mismatch','fractional_minute','descending'])
def test_every_invalid_bar_is_counted_before_refusal_no_quote_price_or_zero_substitution(native,fault):
    native.initialize();row=native.control.extended_rows['target_trade'][1]
    if fault=='type':native.control.extended_rows['target_trade'][1]=NS()
    elif fault=='quote_as_trade':native.control.extended_rows['target_trade'][1]=QuoteBar(native.target,row.time)
    elif fault=='sid':row.symbol=base.Symbol(base.SID('FOREIGN X123ABC'),'PRIVATE.SID')
    elif fault=='ff':row.is_fill_forward=True
    elif fault=='unknown_ff':row.is_fill_forward=None
    elif fault=='period':row.period=timedelta(minutes=2)
    elif fault=='unknown_period':row.period='one minute'
    elif fault=='wrong_day':row.time-=timedelta(days=1);row.end_time-=timedelta(days=1)
    elif fault=='before_start':row.time=datetime(2021,2,10,3,59);row.end_time=datetime(2021,2,10,4)
    elif fault=='after_end':row.time=datetime(2021,2,10,20);row.end_time=datetime(2021,2,10,20,1)
    elif fault=='end_mismatch':row.end_time+=timedelta(minutes=1)
    elif fault=='fractional_minute':row.time+=timedelta(seconds=1);row.end_time+=timedelta(seconds=1)
    else:row.time=datetime(2021,2,10,3,59);row.end_time=datetime(2021,2,10,4)
    if fault=='descending':
        row.time=datetime(2021,2,10,4);row.end_time=datetime(2021,2,10,4,1)
        native.control.extended_rows['target_trade'][0].time=datetime(2021,2,10,4,1)
        native.control.extended_rows['target_trade'][0].end_time=datetime(2021,2,10,4,2)
    native.algo._probe();out=result(native);cell=out['target_trade']
    assert out['status'] in p.CODES and cell['rows_encountered']==2 and cell['rows_validated']==1
    assert cell['invalid_rows']==1 and cell['complete'] is False and out['target_quote'] is None
    assert out['target_no_rows_observed_in_bound'] is None


@pytest.mark.parametrize('phase',['request','iterator','next'])
def test_permission_or_iteration_failure_is_unproved_and_never_retried(native,phase):
    native.initialize()
    def failure(label):
        if label==('control_trade' if phase!='next' else 'next_control_trade'):raise PermissionError('PRIVATE-ERROR')
    if phase=='iterator':native.control.iterator_hook=failure
    else:native.control.extended_hook=failure
    native.algo._probe();out=result(native)
    assert out['status']=='ordinary_native_or_schema_failure' and out['history_calls']==1
    assert out['control_trade']['complete'] is False and out['control_trade']['status']=='access_or_validation_unproved'
    assert out['control_quote'] is out['target_trade'] is out['target_quote'] is None
    before=list(native.control.events);native.algo._probe();assert native.control.events==before


@pytest.mark.parametrize('fault',['missing','unknown','hash','locked','clock','utc','project','live','decoded_config','json_rebase'])
def test_no_history_without_hashbound_parent_clock_native_custody_and_original_config(native,fault):
    native.initialize()
    if fault=='missing':native.algo.object_store.present=False
    elif fault=='unknown':native.algo.object_store.present=None
    elif fault=='hash':native.algo.object_store.raw+=b' '
    elif fault=='locked':native.algo.get_locked=lambda:False
    elif fault=='clock':native.algo.time-=timedelta(minutes=1);native.algo.utc_time-=timedelta(minutes=1)
    elif fault=='utc':native.algo.utc_time+=timedelta(minutes=1)
    elif fault=='project':native.algo.project_id+=1
    elif fault=='live':native.algo.live_mode=True
    else:
        native.module.PROBE_CONFIG['binding']['key']='foreign/unreserved'
        if fault=='json_rebase':
            native.module.PROBE_CONFIG_JSON=json.dumps(native.module.PROBE_CONFIG,sort_keys=True,separators=(',',':'))
            native.module.PROBE_CONFIG_SHA256=hashlib.sha256(native.module.PROBE_CONFIG_JSON.encode()).hexdigest()
    native.algo._probe();out=result(native)
    assert out['history_calls']==0 and native.control.extended_history==[] and native.control.calendar==[]
    if fault not in ('missing','unknown','hash'):assert native.algo.object_store.calls==[]


@pytest.mark.parametrize('fault',['security_type','security_sid','symbol_type','symbol_market','hours_type','hours_zone','open_day','open_time','close_day','close_time','getter_config','job_drift'])
def test_native_calendar_identity_zone_date_or_custody_must_be_proven_before_history(native,fault):
    native.initialize();security=native.control.registry[str(native.algo._clock.id)];hours=security.exchange.hours
    if fault=='security_type':native.control.registry[str(native.algo._clock.id)]=NS(symbol=native.algo._clock,exchange=security.exchange)
    elif fault=='security_sid':security.symbol=base.Symbol(base.SID('FOREIGN X123ABC'),'PRIVATE.SID')
    elif fault=='symbol_type':native.algo._clock.id.security_type='option'
    elif fault=='symbol_market':native.algo._clock.id.market='foreign'
    elif fault=='hours_type':security.exchange.hours=NS(time_zone=NS(Id='America/New_York'))
    elif fault=='hours_zone':hours.time_zone.Id='UTC'
    elif fault=='open_day':hours.get_next_market_open=lambda day,_:day+timedelta(days=1,hours=9,minutes=30)
    elif fault=='open_time':hours.get_next_market_open=lambda day,_:day.replace(hour=9,minute=31)
    elif fault=='close_day':hours.get_next_market_close=lambda day,_:day+timedelta(days=1,hours=16)
    elif fault=='close_time':hours.get_next_market_close=lambda day,_:day.replace(hour=15,minute=59)
    elif fault=='getter_config':native.control.calendar_hook=lambda *_:native.module.PROBE_CONFIG['binding'].update(key='foreign/unreserved')
    else:native.control.calendar_hook=lambda *_:setattr(native.algo,'algorithm_id','d'*32)
    native.algo._probe();out=result(native)
    assert out['history_calls']==0 and out['native_regular_calendars']['control'] is None
    assert out['status'] in ('extended_native_calendar_unproved','config_digest','runtime_custody_changed')


@pytest.mark.parametrize('phase',['contains_parent','read_parent','extended_calendar_control_inspect','history_control_trade_request'])
def test_native_getter_config_mutation_denies_the_exact_effect_it_precedes(native,phase):
    native.initialize();original=native.algo.get_locked
    def getter():
        if native.algo._phase==phase:native.module.PROBE_CONFIG['binding']['key']='foreign/unreserved'
        return original()
    native.algo.get_locked=getter;native.algo._probe();out=result(native)
    assert out['status']=='config_digest' and native.control.extended_history==[]
    if phase=='contains_parent':assert native.algo.object_store.calls==[]
    elif phase=='read_parent':assert [name for name,_ in native.algo.object_store.calls]==['contains']
    if phase=='extended_calendar_control_inspect':assert native.control.calendar==[]
    assert all('foreign' not in key for _,key in native.algo.object_store.calls)


@pytest.mark.parametrize('phase',['read','request','iterate','inspect'])
def test_job_drift_around_native_effects_stops_before_any_following_query(native,phase):
    native.initialize()
    def drift(_=None):native.algo.algorithm_id='d'*32
    if phase=='read':native.algo.object_store.hook=lambda stage:drift() if stage=='read' else None
    elif phase=='request':native.control.extended_hook=lambda stage:drift() if stage=='control_trade' else None
    elif phase=='iterate':native.control.iterator_hook=drift
    else:
        class DriftingBar(TradeBar):
            @property
            def period(self):
                if native.algo._phase=='history_control_trade_inspect':drift()
                return timedelta(minutes=1)
            @period.setter
            def period(self,value):pass
        native.control.extended_rows['control_trade'][0]=DriftingBar(native.algo._clock,datetime(2021,2,10,4))
    native.algo._probe();out=result(native)
    assert out['status']=='runtime_custody_changed' and len(native.control.extended_history)<=1
    assert out['native_exact_subscription']['add_security_calls']==0
    assert out['actual_child_job_id']=='c'*32 and out['end_runtime_custody'] is False


@pytest.mark.parametrize('kind',['cancel','fatal'])
@pytest.mark.parametrize('phase',['calendar','history','iterate'])
def test_nonordinary_priority_is_body_free_even_with_simultaneous_config_drift(native,kind,phase):
    native.initialize()
    class Fatal(BaseException):pass
    def stop(*_):
        native.module.PROBE_CONFIG['binding']['key']='foreign/unreserved'
        raise (KeyboardInterrupt if kind=='cancel' else Fatal)('PRIVATE-ERROR')
    if phase=='calendar':native.control.calendar_hook=stop
    elif phase=='history':native.control.extended_hook=stop
    else:native.control.iterator_hook=stop
    with pytest.raises(KeyboardInterrupt if kind=='cancel' else native.module.ProbeStopped) as caught:native.algo._probe()
    assert 'PRIVATE-ERROR' not in str(caught.value) and len(native.control.extended_history)<=1


def test_961_encountered_rows_each_are_incomplete_without_peeking_or_fifth_query(native):
    native.initialize()
    for label,rows in native.control.extended_rows.items():native.control.extended_rows[label]=[rows[0]]*962
    native.algo._probe();out=result(native)
    assert out['history_calls']==4 and out['bar_rows_encountered']==native.control.extended_yielded==3844
    assert out['status']=='extended_row_bound_incomplete' and out['target_no_rows_observed_in_bound']=={'trade':None,'quote':None}
    for label in ('control_trade','control_quote','target_trade','target_quote'):
        assert out[label]['rows_encountered']==961 and out[label]['duplicate_end_rows']==960
        assert out[label]['complete'] is False and out[label]['row_bound_reached_result_may_be_incomplete'] is True
    with pytest.raises(native.module.ProbeRefusal):native.algo._history(native.target,datetime(2021,2,10,4),datetime(2021,2,10,20),TradeBar,'target_trade')
    assert len(native.control.extended_history)==4


def test_960_unique_minute_bars_can_end_naturally_under_the_961_budget(native):
    native.initialize()
    for label,rows in native.control.extended_rows.items():
        first=rows[0];native.control.extended_rows[label]=[type(first)(first.symbol,datetime(2021,2,10,4)+timedelta(minutes=n)) for n in range(960)]
    native.algo._probe();out=result(native)
    assert out['status']=='completed_bounded_extended_observations' and out['bar_rows_encountered']==3840
    for label in ('control_trade','control_quote','target_trade','target_quote'):
        assert out[label]['complete'] is True and out[label]['rows_validated']==960


@pytest.mark.parametrize('changes',[{'start':datetime(2020,2,10,4)},{'end':datetime(2022,2,10,20)},
    {'end':datetime(2021,2,10,20,1)},{'kind':QuoteBar},{'label':'foreign'}])
def test_exact_history_type_label_and_public_year_bounds_cannot_widen(native,changes):
    native.initialize();args=dict(symbol=native.algo._clock,start=datetime(2021,2,10,4),end=datetime(2021,2,10,20),kind=TradeBar,label='control_trade')
    args.update(changes)
    with pytest.raises(native.module.ProbeRefusal):native.algo._history(**args)
    assert native.control.extended_history==[]


def test_no_history_before_exact_parent_validation_or_native_calendar(native):
    native.initialize()
    with pytest.raises(native.module.ProbeRefusal):native.algo._history(native.algo._clock,datetime(2021,2,10,4),datetime(2021,2,10,20),TradeBar,'control_trade')
    assert native.control.extended_history==[] and native.algo.object_store.calls==[]


@pytest.mark.parametrize('mutation',['regular_hours_only','quote_routed_as_trade','foreign_sid_accepted'])
def test_behavioral_negatives_kill_three_in_memory_history_mutants(native,sources,mutation):
    """Mutations live only in the synthetic module; all source files stay exact."""
    raw,_=build(sources);node=deepcopy(methods(raw)['_history']);changed=False
    for item in ast.walk(node):
        if mutation=='regular_hours_only' and isinstance(item,ast.keyword) and item.arg=='extended_market_hours':
            assert ast.literal_eval(item.value) is True;item.value=ast.Constant(False);changed=True
        elif (mutation=='quote_routed_as_trade' and isinstance(item,ast.Subscript)
                and isinstance(item.value,ast.Attribute) and item.value.attr=='history'):
            assert ast.unparse(item.slice)=='kind';item.slice=ast.Name(id='TradeBar',ctx=ast.Load());changed=True
        elif (mutation=='foreign_sid_accepted' and isinstance(item,ast.Compare)
                and ast.unparse(item)=='row.symbol.id != symbol.id'):
            item.left=ast.Constant(False);item.comparators=[ast.Constant(True)];item.ops=[ast.Is()];changed=True
    assert changed
    module=ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[]))
    exec(compile(module,'<synthetic-history-mutant>','exec'),native.module.__dict__)
    native.module.Main._history=native.module.__dict__['_history']
    native.initialize()
    if mutation=='foreign_sid_accepted':
        native.control.extended_rows['target_trade'][1].symbol=base.Symbol(base.SID('FOREIGN X123ABC'),'PRIVATE.SID')
    native.algo._probe();out=result(native)
    if mutation=='foreign_sid_accepted':
        # The real foreign-SID regression requires refusal; this mutant wrongly
        # completes, proving that expected-refusal assertion would kill it.
        assert out['status']=='completed_bounded_extended_observations'
    else:
        # The real successful four-request test requires completion; options or
        # type dispatch mutation breaks it instead of passing unnoticed.
        assert out['status']!='completed_bounded_extended_observations'
    for name,value in sources.items():assert hashlib.sha256(value).hexdigest()==p.PINS[name]
