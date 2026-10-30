"""Synthetic fixed-minute Tick observation; no private/native/provider IO."""
import ast
from copy import deepcopy
from datetime import datetime,timedelta
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import sys

import pytest

from research.target_price_revisions_qc import comparison_20261029_mark_tick_probe as p
from tests.target_price_revisions_qc import test_qc_comparison_20261028_mark_probe_post_gap as old
from tests.target_price_revisions_qc import test_qc_comparison_20261028_mark_probe as base

PREFIX=Path('research/target_price_revisions_qc')
FILES=dict(native_post_gap_source='comparison_20261028_mark_probe_post_gap_native.py',
    post_gap_source='comparison_20261028_mark_probe_post_gap.py',
    control_source='comparison_20261028_mark_probe_control.py',base_probe_source='comparison_20261028_mark_probe.py',
    helper_source='comparison_20261028_mark_read.py',producer_source='comparison_20261028_algorithm.py')


@pytest.fixture
def sources():return {name:(PREFIX/file).read_bytes() for name,file in FILES.items()}


def build(sources,**changes):
    args=dict(sources,operation_id='TPR-CMP28-MARK-PROBE-TICK-SYNTHETIC-007',git_head='a'*40)
    args.update(changes);return p.build_mark_tick_probe(**args)


class Tick:
    def __init__(self,symbol,stamp,kind='trade',price='50',quantity='10'):
        self.symbol=symbol;self.time=stamp;self.end_time=stamp;self.tick_type=kind
        self.is_fill_forward=False;self.suspicious=False;self._price=price;self._quantity=quantity
    @property
    def last_price(self):
        if self.tick_type=='quote':raise AssertionError('PRIVATE-QUOTE-PRICE-READ')
        return self._price
    @property
    def quantity(self):
        if self.tick_type=='quote':raise AssertionError('PRIVATE-QUOTE-QUANTITY-READ')
        return self._quantity


@pytest.fixture
def native(sources,monkeypatch):
    def render(values,**changes):
        return build(dict(values,native_post_gap_source=sources['native_post_gap_source'],
            post_gap_source=sources['post_gap_source']),**changes)
    monkeypatch.setattr(old,'build',render)
    case=old.native.__wrapped__({name:value for name,value in sources.items()
        if name not in ('native_post_gap_source','post_gap_source')},monkeypatch)
    case.module.Tick=Tick;sys.modules['AlgorithmImports'].Tick=Tick
    case.module.Resolution.TICK='tick';case.control.tick_history=[];case.control.tick_yielded=0
    case.control.tick_hook=lambda *_:None;case.control.tick_rows={};case.control.iterator_hook=lambda *_:None
    class History:
        def __getitem__(self,kind):
            assert kind is Tick
            def request(symbol,start,end,resolution,**options):
                label='control_ticks' if symbol.id==case.algo._clock.id else 'target_ticks'
                assert type(start) is datetime and start==datetime(2021,2,10,15,59)
                assert type(end) is datetime and end==datetime(2021,2,10,16,0)
                assert resolution=='tick' and options==dict(fill_forward=False,extended_market_hours=False,data_normalization_mode='raw')
                case.control.events.append(label);case.control.tick_history.append((label,symbol,start,end,options))
                case.control.tick_hook(label)
                class Rows:
                    def __iter__(self):
                        case.control.iterator_hook(label)
                        def rows():
                            for row in case.control.tick_rows[label]:
                                case.control.tick_yielded+=1;case.control.tick_hook('next_'+label);yield row
                        return rows()
                return Rows()
            return request
    case.algo.history=History();initialize=case.initialize
    def setup():
        initialize()
        target=base.Symbol(base.SID(case.body['security_id']),'PRIVATE.SID')
        case.target=target
        case.control.tick_rows={label:[Tick(symbol,datetime(2021,2,10,15,59),'quote'),
            Tick(symbol,datetime(2021,2,10,15,59,30)),Tick(symbol,datetime(2021,2,10,16,0))]
            for label,symbol in (('control_ticks',case.algo._clock),('target_ticks',target))}
    case.initialize=setup
    return case


def result(case):
    out=old.result(case)
    raw=case.logs[-1]
    assert not any(secret in raw for secret in ('PRIVATE-QUOTE','PRIVATE-TICK-ERROR','X123ABC','"last_price"','"quantity"'))
    return out


def test_single_plain_main_fixed_six_pins_scope_and_false_authority(sources):
    raw,report_raw=build(sources);report=json.loads(report_raw);compile(ast.parse(raw),'main.py','exec')
    assert raw.startswith(sources['helper_source']+b'\n') and len(raw)==report['main_bytes']<60000
    assert hashlib.sha256(raw).hexdigest()==report['main_sha256'] and report['public_source_sha256']==p.PINS
    cfg_raw=old.literal(raw,'PROBE_CONFIG_JSON').encode();cfg=json.loads(cfg_raw)
    assert hashlib.sha256(cfg_raw).hexdigest()==report['config_sha256']==old.literal(raw,'PROBE_CONFIG_SHA256')
    assert cfg['failure_session']=='2021-02-10' and cfg['diagnostic_session']==cfg['configured_session']=='2021-02-12'
    assert cfg['history_start_local']=='2021-02-10T15:59:00' and cfg['history_end_local']=='2021-02-10T16:00:00'
    assert cfg['public_source_sha256']==p.PINS and cfg['max_history_calls']==2
    assert report['max_tick_rows_per_symbol']==50000 and report['max_total_tick_rows']==100000
    assert report['max_contains']==report['max_reads']==1 and report['max_native_market_hours_calls']==0
    for name in ('native_permission','native_clock_class_attested','native_origin_authenticated','rights_verified',
            'point_in_time_verified','source_inputs_admitted','financial_recovery_proven','cache_updated','derived_bar_created',
            'sdk_hard_timeout_proven','sdk_preallocation_byte_bound_proven','external_manifest_attested',
            'one_of_five_economic_arms','canonical_admission'):
        assert report[name] is False
    attrs={node.attr for node in ast.walk(ast.parse(raw)) if isinstance(node,ast.Attribute)}
    assert not attrs&{'save_bytes','set_market_price','set_holdings','market_order','market_on_open_order','liquidate','download'}
    assert not any(isinstance(node,ast.keyword) and node.arg=='tick_type' for node in ast.walk(ast.parse(raw)))
    assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='HistoryRequest' for node in ast.walk(ast.parse(raw)))
    assert report['request_construction_correction_only'] is False


def test_reviewed_registration_effect_clock_and_end_custody_methods_are_ast_identical(sources):
    raw,_=build(sources)
    old_raw,_=p.prior.build_mark_probe_post_gap_native(**{name:value for name,value in sources.items()
        if name!='native_post_gap_source'},operation_id='TPR-CMP28-MARK-PROBE-TICK-SYNTHETIC-007',git_head='a'*40)
    def methods(source):
        main=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='Main')
        return {n.name:n for n in main.body if isinstance(n,ast.FunctionDef)}
    before,after=methods(old_raw),methods(raw)
    for name in ('_register_parent','_effect','_record_error','on_data','on_end_of_algorithm'):
        assert ast.dump(before[name])==ast.dump(after[name])
    bound=deepcopy(after['_bound']);first=bound.body.pop(0);last=bound.body.pop()
    assert ast.unparse(first)==ast.unparse(last)=='self._tick_config_bound()'
    assert 'config_digest' in ast.unparse(after['_tick_config_bound'])
    assert ast.dump(bound)==ast.dump(before['_bound'])
    assert '_session_windows' not in after
    for name,raw in sources.items():assert hashlib.sha256(raw).hexdigest()==p.PINS[name]


@pytest.mark.parametrize('name',list(FILES))
def test_each_independent_predecessor_pin_refuses_any_drift(sources,name):
    sources[name]+=b'\n'
    with pytest.raises(p.TickProbeBuildRefusal):build(sources)


@pytest.mark.parametrize('changes',[{'operation_id':'foreign'},{'git_head':'0'*40},{'git_head':False}])
def test_operation_head_and_fixed_public_window_cannot_be_relabelled(sources,changes):
    with pytest.raises(p.TickProbeBuildRefusal):build(sources,**changes)


def test_mixed_quotes_are_counted_without_price_read_and_boundary_trades_stay_separate(native):
    native.initialize();assert native.algo.object_store.calls==[] and native.control.tick_history==[]
    native.algo._probe();out=result(native)
    assert out['status']=='completed_bounded_tick_observations' and out['history_calls']==2
    assert out['tick_rows_encountered']==6 and native.control.tick_yielded==6
    assert native.control.calendar==[]
    assert native.control.events==['contains','read','control_ticks','add_security','configs','target_ticks']
    for label in ('control_ticks','target_ticks'):
        cell=out[label];assert cell['complete'] is True and cell['rows_encountered']==cell['rows_validated']==3
        assert cell['trade_rows']==2 and cell['quote_rows']==1
        assert cell['final_minute_trade_rows']==cell['close_boundary_trade_rows']==1
        assert cell['quote_price_consumed'] is cell['price_or_quantity_exported'] is False
    assert out['target_trade_ticks_observed'] is True and out['target_no_trade_ticks_observed_in_bound'] is False
    assert out['native_exact_subscription']['verified'] is True
    for key in ('native_origin_authenticated','backend_durability_proven','point_in_time_verified','rights_verified',
            'source_inputs_admitted','canonical_admission','financial_recovery_proven','cache_updated','derived_bar_created',
            'cash_changes_made','native_permission','one_of_five_economic_arms','external_manifest_attested'):
        assert out[key] is False
    assert out['orders_submitted']==0
    before=list(native.control.events);native.algo._probe();assert native.control.events==before


@pytest.mark.parametrize('mode',['both_empty','target_empty','quotes_only_control','quotes_only_target'])
def test_empty_or_quote_only_streams_remain_bounded_observations_not_gap_or_rights_proof(native,mode):
    native.initialize()
    if mode=='both_empty':native.control.tick_rows={label:[] for label in native.control.tick_rows}
    elif mode=='target_empty':native.control.tick_rows['target_ticks']=[]
    else:
        label='control_ticks' if mode=='quotes_only_control' else 'target_ticks'
        native.control.tick_rows[label]=[row for row in native.control.tick_rows[label] if row.tick_type=='quote']
    native.algo._probe();out=result(native)
    assert out['history_calls']==2 and out['target_data_gap_proven'] is out['universal_absence_proven'] is out['terminal_proven'] is False
    if mode in ('both_empty','quotes_only_control'):
        assert out['status']=='request_path_unproved' and out['target_no_trade_ticks_observed_in_bound'] is None
    else:assert out['target_no_trade_ticks_observed_in_bound'] is True


@pytest.mark.parametrize('fault',['type','sid','ff','wrong_day','before_start','after_end','end_mismatch','descending',
    'unknown_kind','unknown_flag','suspicious','nan_price','zero_price','negative_quantity','nan_quantity'])
def test_every_source_row_is_counted_before_typed_identity_clock_trade_or_flag_refusal(native,fault):
    native.initialize();row=native.control.tick_rows['target_ticks'][1]
    if fault=='type':native.control.tick_rows['target_ticks'][1]=NS()
    elif fault=='sid':row.symbol=base.Symbol(base.SID('FOREIGN X123ABC'),'PRIVATE.SID')
    elif fault=='ff':row.is_fill_forward=True
    elif fault=='wrong_day':row.time=row.end_time=datetime(2021,2,9,15,59,30)
    elif fault=='before_start':row.time=row.end_time=datetime(2021,2,10,15,58,59)
    elif fault=='after_end':row.time=row.end_time=datetime(2021,2,10,16,0,1)
    elif fault=='end_mismatch':row.end_time+=timedelta(seconds=1)
    elif fault=='descending':row.time=row.end_time=datetime(2021,2,10,15,59);native.control.tick_rows['target_ticks'][0].time=native.control.tick_rows['target_ticks'][0].end_time=datetime(2021,2,10,15,59,1)
    elif fault=='unknown_kind':row.tick_type='open_interest'
    elif fault=='unknown_flag':row.suspicious=None
    elif fault=='suspicious':row.suspicious=True
    elif fault=='nan_price':row._price='NaN'
    elif fault=='zero_price':row._price='0'
    elif fault=='negative_quantity':row._quantity='-1'
    else:row._quantity='Infinity'
    native.algo._probe();out=result(native);cell=out['target_ticks']
    assert out['status'] in p.CODES and cell['rows_encountered']==2 and cell['rows_validated']==1
    assert cell['complete'] is False and cell['status']=='access_or_validation_unproved'
    assert cell['unknown_type_rows']+cell['invalid_source_flag_rows']+cell['suspicious_rows']+cell['invalid_row_rows']==1
    assert out['target_trade_ticks_observed'] is None and out['target_no_trade_ticks_observed_in_bound'] is None


@pytest.mark.parametrize('phase',['request','iterator','next'])
def test_permission_or_stream_error_is_unproved_never_reported_as_zero_or_retried(native,phase):
    native.initialize()
    def failure(label):
        if label==('control_ticks' if phase in ('request','iterator') else 'next_control_ticks'):
            raise PermissionError('PRIVATE-TICK-ERROR')
    if phase=='iterator':native.control.iterator_hook=failure
    else:native.control.tick_hook=failure
    native.algo._probe();out=result(native)
    assert out['status']=='ordinary_native_or_schema_failure' and out['history_calls']==1
    assert out['control_ticks']['complete'] is False and out['target_ticks'] is None
    assert out['control_ticks']['status']=='access_or_validation_unproved'
    before=list(native.control.events);native.algo._probe();assert native.control.events==before


@pytest.mark.parametrize('fault',['missing','unknown','hash','locked','clock','utc','project','live','decoded_config','json_rebase'])
def test_no_history_without_exact_hashbound_parent_actual_custody_and_frozen_config(native,fault):
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
    assert out['history_calls']==0 and native.control.tick_history==[]
    if fault not in ('missing','unknown','hash'):assert native.algo.object_store.calls==[]


@pytest.mark.parametrize('phase',['read','request','iterate','inspect'])
def test_actual_job_drift_around_every_private_or_history_phase_stops_before_further_effects(native,monkeypatch,phase):
    native.initialize()
    def drift(_=None):native.algo.algorithm_id='d'*32
    if phase=='read':native.algo.object_store.hook=lambda stage:drift() if stage=='read' else None
    elif phase=='request':native.control.tick_hook=lambda stage:drift() if stage=='control_ticks' else None
    elif phase=='iterate':native.control.iterator_hook=drift
    else:
        row=native.control.tick_rows['control_ticks'][1]
        class NativeAmount:
            def ToString(self,_):drift();return '50'
        globalization=NS(CultureInfo=NS(InvariantCulture=object()))
        monkeypatch.setitem(sys.modules,'System.Globalization',globalization)
        row._price=NativeAmount()
    native.algo._probe();out=result(native)
    assert out['status']=='runtime_custody_changed' and len(native.control.tick_history)<=1
    assert out['native_exact_subscription']['add_security_calls']==0
    assert out['end_runtime_custody'] is False and out['actual_child_job_id']=='c'*32


@pytest.mark.parametrize('kind',['cancel','fatal'])
def test_native_nonordinary_errors_are_body_free_and_no_target_request_follows(native,kind):
    native.initialize()
    class Fatal(BaseException):pass
    def stop(label):raise (KeyboardInterrupt if kind=='cancel' else Fatal)('PRIVATE-TICK-ERROR')
    native.control.tick_hook=stop
    with pytest.raises(KeyboardInterrupt if kind=='cancel' else native.module.ProbeStopped) as caught:native.algo._probe()
    assert 'PRIVATE-TICK-ERROR' not in str(caught.value) and len(native.control.tick_history)==1


def test_hard_total_bound_counts_all_mixed_rows_without_peeking_and_third_call_refuses(native):
    native.initialize();native.algo._bound()
    # Only the mechanical 100000-row budget is isolated here; actual guard
    # behavior is separately exercised above and its inherited AST is pinned.
    native.algo._bound=lambda:None
    for label,symbol in (('control_ticks',native.algo._clock),('target_ticks',native.target)):
        row=Tick(symbol,datetime(2021,2,10,15,59,30),'quote')
        native.control.tick_rows[label]=[row]*50001
    native.algo._probe();out=result(native)
    assert out['status']=='tick_row_bound_incomplete' and out['history_calls']==2
    assert out['tick_rows_encountered']==native.control.tick_yielded==100000
    assert all(out[label]['rows_encountered']==50000 and out[label]['quote_rows']==50000
        and out[label]['complete'] is False for label in ('control_ticks','target_ticks'))
    with pytest.raises(native.module.ProbeRefusal):native.algo._history(native.target,datetime(2021,2,10,15,59),datetime(2021,2,10,16),'target_ticks')
    assert len(native.control.tick_history)==2


@pytest.mark.parametrize('changes',[{'start':datetime(2020,2,10,15,59)},{'end':datetime(2022,2,10,16)},
    {'end':datetime(2021,2,10,16,1)},{'label':'foreign'}])
def test_closed_tick_window_cannot_widen_or_change_year_type_or_label(native,changes):
    native.initialize()
    args=dict(symbol=native.algo._clock,start=datetime(2021,2,10,15,59),end=datetime(2021,2,10,16),label='control_ticks')
    args.update(changes)
    with pytest.raises(native.module.ProbeRefusal):native.algo._history(**args)
    assert native.control.tick_history==[]


@pytest.mark.parametrize('phase',['contains','read','request','iterator'])
def test_config_drift_after_an_uncertain_effect_prevents_all_following_reads_or_queries(native,phase):
    native.initialize()
    def drift(_=None):native.module.PROBE_CONFIG['binding']['key']='foreign/unreserved'
    if phase in ('contains','read'):
        native.algo.object_store.hook=lambda stage:drift() if stage==phase else None
    elif phase=='request':native.control.tick_hook=lambda label:drift() if label=='control_ticks' else None
    else:native.control.iterator_hook=drift
    native.algo._probe();out=result(native)
    assert out['status']=='config_digest' and len(native.control.tick_history)<=1
    assert all('foreign' not in key for _,key in native.algo.object_store.calls)
    if phase=='contains':assert [name for name,_ in native.algo.object_store.calls]==['contains']
    assert out['native_exact_subscription']['add_security_calls']==0


def test_native_decimal_to_string_uses_invariant_culture_before_positive_trade_validation(native,monkeypatch):
    native.initialize();sentinel=object();calls=[]
    class NativeAmount:
        def ToString(self,culture):
            assert culture is sentinel;calls.append(culture);return '50.000000000000000001'
    monkeypatch.setitem(sys.modules,'System.Globalization',NS(CultureInfo=NS(InvariantCulture=sentinel)))
    for rows in native.control.tick_rows.values():
        for row in rows:
            if row.tick_type=='trade':row._price=row._quantity=NativeAmount()
    native.algo._probe();out=result(native)
    assert out['status']=='completed_bounded_tick_observations' and len(calls)==8
    assert out['derived_bar_created'] is out['cache_updated'] is False


@pytest.mark.parametrize('phase',['contains_parent','read_parent','history_control_ticks_request'])
def test_native_getter_config_drift_denies_the_effect_it_precedes(native,phase):
    native.initialize();original_locked=native.algo.get_locked
    def getter():
        if native.algo._phase==phase:
            native.module.PROBE_CONFIG['binding']['key']='foreign/unreserved'
        return original_locked()
    native.algo.get_locked=getter
    native.algo._probe();out=result(native)
    assert out['status']=='config_digest'
    assert all('foreign' not in key for _,key in native.algo.object_store.calls)
    if phase=='contains_parent':assert native.algo.object_store.calls==[]
    else:assert [method for method,_ in native.algo.object_store.calls]==(['contains'] if phase=='read_parent' else ['contains','read'])
    assert native.control.tick_history==[]


@pytest.mark.parametrize('kind',['cancel','fatal'])
def test_config_drift_during_native_nonordinary_failure_preserves_original_priority(native,kind):
    native.initialize()
    class Fatal(BaseException):pass
    def stop(label):
        native.module.PROBE_CONFIG['binding']['key']='foreign/unreserved'
        raise (KeyboardInterrupt if kind=='cancel' else Fatal)('PRIVATE-TICK-ERROR')
    native.control.tick_hook=stop
    with pytest.raises(KeyboardInterrupt if kind=='cancel' else native.module.ProbeStopped) as caught:native.algo._probe()
    assert 'PRIVATE-TICK-ERROR' not in str(caught.value) and len(native.control.tick_history)==1
    assert all('foreign' not in key for _,key in native.algo.object_store.calls)
