"""Typed synthetic initialized-map probe; no native/private/account I/O."""
import ast
from copy import deepcopy
from datetime import datetime,timedelta
from enum import IntEnum
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace as NS

import pytest

from research.target_price_revisions_qc import comparison_20261029_project_map_probe as p
from research.target_price_revisions_qc import comparison_20261029_projects as registry
from tests.target_price_revisions_qc import test_qc_comparison_20261029_project_probe as project
from tests.target_price_revisions_qc import test_qc_comparison_20261029_extended_mark_probe as extended
from tests.target_price_revisions_qc import test_qc_comparison_20261028_mark_probe as base

sha=project.sha

@pytest.fixture
def sources():return {name:Path(name).read_bytes() for name in p.SOURCE_PATHS}

@pytest.fixture
def bindings():return project.bindings.__wrapped__()

def build(sources,bindings,**changes):
    raw=registry._canonical(bindings)
    args=dict(public_sources=sources,project_bindings_raw=raw,expected_project_bindings_sha256=sha(raw),
        operation_id='TPR-CMP28-MARK-PROBE-ISOLATED-MAP-SYNTHETIC-010',git_head='a'*40)
    args.update(changes);return p.build_project_map_probe(**args)

def test_plain_bounded_main_closes_ten_sources_and_preserves_actual_guards(sources,bindings):
    raw,report_raw=build(sources,bindings);report=json.loads(report_raw)
    cfg=json.loads(project.literal(raw,'PROBE_CONFIG_JSON'));tree=ast.parse(raw)
    compile(tree,'main.py','exec')
    assert len(raw)==report['main_bytes']<=60000 and sha(raw)==report['main_sha256']
    assert sha(project.literal(raw,'PROBE_CONFIG_JSON').encode())==report['config_sha256']
    assert cfg['public_source_sha256']==p.PINS and report['public_source_sha256']==p.PINS
    assert cfg['schema']=='tpr-cmp28-native-project-map-probe-config-v1'
    assert cfg['child_project_id']==project.PROJECT and cfg['binding']['project_id']==37650980
    assert cfg['max_history_calls']==4 and cfg['max_total_history_rows']==3844
    assert cfg['max_map_rows']==64 and cfg['max_map_rows_encountered']==65
    assert cfg['max_mapped_symbol_calls']==cfg['max_has_data_calls']==5
    assert cfg['map_trace_sessions']==['2021-02-'+f'{day:02}' for day in range(8,13)]
    assert b'private_target_identity_label' not in raw
    before,_=p.prior.build_project_probe(public_sources={k:v for k,v in sources.items() if k!=p.PROJECT_PROBE},
        project_bindings_raw=registry._canonical(bindings),expected_project_bindings_sha256=sha(registry._canonical(bindings)),
        operation_id='TPR-CMP28-MARK-PROBE-ISOLATED-MAP-SYNTHETIC-010',git_head='a'*40)
    a,b=project.methods(before),project.methods(raw)
    for name in ('_bound','_tick_config_bound','_effect','_history','_register_parent','_regular_window','_record_error','on_data','on_end_of_algorithm'):
        assert ast.dump(a[name])==ast.dump(b[name]),name
    funcs={node.name for node in tree.body if isinstance(node,ast.FunctionDef)}
    assert 'validate_pointer_v2' in funcs and 'project_witness_v2' in funcs
    assert 'validate_pointer' not in funcs and 'project_witness' not in funcs
    helper_bytes=raw[:raw.index(b'PROBE_CONFIG_JSON = ')]
    assert sha(helper_bytes)==report['rendered_helper_definition_sha256']
    assert len(helper_bytes)==report['rendered_helper_definition_bytes']
    assert report['original_helper_source_sha256']==p.PINS[p.PREFIX+'comparison_20261028_mark_read.py']
    assert report['full_original_helper_bytes_preserved'] is False
    original={n.name:n for n in ast.parse(sources[p.PREFIX+'comparison_20261028_mark_read.py']).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    projected={n.name:n for n in ast.parse(helper_bytes).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    assert set(original)-set(projected)=={'project_witness','validate_pointer','_binding'}
    assert all(ast.dump(original[name])==ast.dump(node) for name,node in projected.items())
    attributes={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    assert not attributes&{'Initialize','set_market_price','set_holdings','save_bytes','download','market_order'}
    assert report['provider_initializations']==report['provider_constructions']==0
    for key in ('financial_recovery_proven','native_routing_fix_proven','provider_hole_excluded','independent_native_origin_attested'):
        assert report[key] is False
    assert all(sha(Path(name).read_bytes())==digest for name,digest in p.PINS.items())

@pytest.mark.parametrize('name',p.SOURCE_PATHS)
def test_every_independent_source_pin_refuses_drift(sources,bindings,name):
    sources[name]+=b'\n'
    with pytest.raises(p.ProjectMapProbeRefusal):build(sources,bindings)

@pytest.mark.parametrize('changes',[{'operation_id':'foreign'},{'git_head':'0'*40},
    {'expected_project_bindings_sha256':'0'*64},{'public_sources':{}},{'public_sources':None}])
def test_open_or_mismatched_scope_refuses_before_render(sources,bindings,changes):
    with pytest.raises(p.ProjectMapProbeRefusal):build(sources,bindings,**changes)

@pytest.fixture
def native(sources,bindings,monkeypatch):
    def render(_values,**changes):return build(sources,bindings,**changes)
    monkeypatch.setattr(extended,'build',render)
    ext_sources={key:sources[p.PREFIX+name] for key,name in extended.FILES.items()}
    case=extended.native.__wrapped__(ext_sources,monkeypatch)
    case.algo.project_id=project.PROJECT
    class Mode(IntEnum):OPEN_INTEREST=0;LAST_TRADING_DAY=1
    class Row:
        def __init__(self,day,alias='PRIVATE_ALIAS',mode=None):self.Date=day;self.MappedSymbol=alias;self.DataMappingMode=mode
    class Map:
        def __init__(self):
            self.rows=[Row(datetime(2000,1,1)),Row(datetime(2030,1,1))]
            self.FirstTicker='PRIVATE.SID';self.FirstDate=datetime(2000,1,1)
        def __iter__(self):
            state.calls.append('rows_iter');state.hook('rows_iter')
            for row in self.rows:
                state.calls.append('row_next');state.hook('row_next');yield row
        def GetMappedSymbol(self,day,default,mode):
            assert default=='' and mode is Mode.OPEN_INTEREST
            state.calls.append(('mapped',day));state.hook('mapped')
            return state.alias_result if state.alias_result is not None else next((r.MappedSymbol for r in self.rows if r.Date>=day and r.DataMappingMode in (None,mode)),default)
        def HasData(self,day):state.calls.append(('has',day));state.hook('has');return state.has_data
    class Resolver:
        def ResolveMapFile(self,symbol,date):
            assert symbol=='PRIVATE.SID' and date==datetime(2000,1,1)
            state.calls.append('resolve');state.hook('resolve');return state.mapping
    class Provider:
        def Get(self,key):
            assert key is equity;state.calls.append('get');state.hook('get');return state.resolver
    class Parts:
        def __getitem__(self,kind):
            assert kind is Provider
            def get():
                state.calls.append('getparts');state.hook('getparts')
                def rows():
                    for provider in state.providers:
                        state.provider_yields+=1;state.hook('provider_next');yield provider
                return rows()
            return get
    state=NS(mapping=Map(),resolver=Resolver(),providers=[Provider()],calls=[],hook=lambda *_:None,
        has_data=True,alias_result=None,provider_yields=0)
    equity=object();qc=ModuleType('QuantConnect');qc.DataMappingMode=Mode
    interfaces=ModuleType('QuantConnect.Interfaces');interfaces.IMapFileProvider=Provider
    util=ModuleType('QuantConnect.Util');util.Composer=NS(Instance=NS(GetParts=Parts()))
    auxiliary=ModuleType('QuantConnect.Data.Auxiliary')
    auxiliary.AuxiliaryDataKey=NS(EquityUsa=equity);auxiliary.MapFileResolver=Resolver
    auxiliary.MapFile=Map;auxiliary.MapFileRow=Row
    for mod in (qc,interfaces,util,auxiliary):monkeypatch.setitem(sys.modules,mod.__name__,mod)
    monkeypatch.setattr(base.SID,'Symbol',property(lambda self:self.symbol),raising=False)
    monkeypatch.setattr(base.SID,'Date',property(lambda self:datetime(2000,1,1)),raising=False)
    before=case.control.on_configs
    def configs():
        before()
        for row in case.control.configs:
            if not hasattr(row,'data_mapping_mode'):
                row.data_mapping_mode=Mode.OPEN_INTEREST;row.MappedSymbol='PRIVATE_ALIAS'
                row.data_time_zone=NS(Id='America/New_York');row.exchange_time_zone.Id='America/New_York'
    case.control.on_configs=configs;case.map=state;case.Mode=Mode;case.MapRow=Row
    return case

def result(case):
    out=extended.result(case);raw=case.logs[-1]
    assert not any(secret in raw for secret in ('PRIVATE_ALIAS','PRIVATE.SID','PRIVATE-MAP-PATH','PRIVATE-MAP-ERROR'))
    # TPR-CR33-005: an unsalted digest of a short ticker is the ticker; none may leave the job.
    assert not any(sha(alias.encode()) in raw for alias in ('PRIVATE_ALIAS','PRIVATE_OLD_ALIAS'))
    assert out['alias_exported'] is False
    return out

def test_post_history_initialized_exact_sid_map_observations_are_bounded_private_and_not_a_fix(native):
    native.initialize();assert not native.algo.object_store.calls and not native.map.calls
    native.algo._probe();out=result(native);cell=out['map_trace']
    assert out['history_calls']==4 and len(native.control.extended_history)==4
    assert out['status']=='completed_bounded_extended_observations'
    assert cell['status']=='bounded_initialized_map_observations' and cell['complete'] is True
    assert cell['config_reads']==2 and cell['config_rows_encountered']==2
    assert cell['configuration_unchanged'] is cell['sid_first_identity_matches'] is True
    assert cell['config_before_sha256']==cell['config_after_sha256']
    assert cell['provider_rows_encountered']==cell['provider_get_calls']==cell['resolve_calls']==1
    assert cell['map_rows_encountered']==2 and cell['mapped_symbol_calls']==cell['has_data_calls']==5
    assert set(cell['sessions'])=={'2021-02-'+f'{day:02}' for day in range(8,13)}
    for row in cell['sessions'].values():
        assert row['has_data'] is row['mapped_present'] is row['mapped_matches_explicit_row'] is row['mapped_equals_current_config'] is True
        assert 'mapped_alias_sha256' not in row
    assert native.control.events[-2:]==['configs','configs']
    assert all(cell[name] is False for name in ('provider_initialized','provider_constructed','fallback_used','alias_exported',
        'raw_map_rows_exported','native_origin_authenticated','historical_pit_authenticated','financial_recovery_proven'))
    before=(list(native.map.calls),list(native.control.events));native.algo._probe();assert before==(native.map.calls,native.control.events)

@pytest.mark.parametrize('mode,code',[('zero','map_provider_count_unproved'),('two','map_provider_count_unproved'),
    ('untyped','map_provider_type_unproved'),('resolver','map_resolver_type_unproved'),('map','map_file_type_unproved'),
    ('empty','map_row_bound_or_empty'),('too_many','map_row_bound_or_empty'),('row','map_row_type_unproved'),
    ('alias','map_row_metadata_unproved'),('mode','map_row_metadata_unproved'),('date','map_row_metadata_unproved'),
    ('order','map_row_order_or_conflict_unproved'),('duplicate','map_row_order_or_conflict_unproved'),
    ('alias_result','map_alias_result_unproved'),('has_data','map_has_data_result_unproved')])
def test_unproved_maps_report_closed_unknown_without_demoting_history_or_inventing_absence(native,mode,code):
    native.initialize();state=native.map
    if mode=='zero':state.providers=[]
    elif mode=='two':state.providers*=20
    elif mode=='untyped':state.providers=[NS()]
    elif mode=='resolver':state.resolver=NS()
    elif mode=='map':state.mapping=NS()
    elif mode=='empty':state.mapping.rows=[]
    elif mode=='too_many':state.mapping.rows=[native.MapRow(datetime(2000,1,1)+timedelta(days=i)) for i in range(100)]
    elif mode=='row':state.mapping.rows[0]=NS()
    elif mode=='alias':state.mapping.rows[0].MappedSymbol='PRIVATE-MAP-PATH/invalid'
    elif mode=='mode':state.mapping.rows[0].DataMappingMode=0
    elif mode=='date':state.mapping.rows[0].Date=datetime(2000,1,1,1)
    elif mode=='order':state.mapping.rows.reverse()
    elif mode=='duplicate':state.mapping.rows=[state.mapping.rows[0]]*2
    elif mode=='alias_result':state.alias_result='PRIVATE-MAP-PATH/invalid'
    else:state.has_data=None
    native.algo._probe();out=result(native);cell=out['map_trace']
    assert cell['status']==code and cell['complete'] is False and cell['configuration_unchanged'] is True
    assert out['history_calls']==4 and out['status']=='completed_bounded_extended_observations'
    if mode=='two':assert state.provider_yields==2
    if mode=='too_many':assert cell['map_rows_encountered']==65
    assert out['financial_recovery_proven'] is out['provider_hole_excluded'] is False

def test_empty_or_disagreeing_map_results_and_first_identity_are_observations_not_routing_acceptance(native):
    native.initialize();native.map.mapping.FirstTicker='OTHER';native.map.alias_result=''
    native.algo._probe();cell=result(native)['map_trace']
    assert cell['status']=='bounded_initialized_map_observations' and cell['sid_first_identity_matches'] is False
    assert all(row['has_data'] is True and row['mapped_present'] is False and row['mapped_matches_explicit_row'] is False for row in cell['sessions'].values())
    assert cell['financial_recovery_proven'] is False

def test_native_row_end_dates_and_nullable_actual_modes_are_compared_without_export_or_mapping_change(native):
    native.initialize();mode=native.Mode.OPEN_INTEREST
    native.map.mapping.rows=[native.MapRow(datetime(2021,2,9),'PRIVATE_OLD_ALIAS',mode),
        native.MapRow(datetime(2030,1,1),'PRIVATE_ALIAS',None)]
    native.algo._probe();out=result(native);cells=out['map_trace']['sessions']
    assert all(row['mapped_matches_explicit_row'] is True for row in cells.values())
    assert cells['2021-02-10']['mapped_equals_current_config'] is True
    assert cells['2021-02-09']['mapped_equals_current_config'] is False
    assert 'PRIVATE_OLD_ALIAS' not in native.logs[-1]

@pytest.mark.parametrize('mutation',['mapped','mode','type','sid','raw','ff','zone','new_object'])
def test_actual_config_before_after_drift_is_reported_and_never_repaired(native,mutation):
    native.initialize();count=0
    def hook(phase):
        nonlocal count
        if phase!='has':return
        count+=1
        if count!=5:return
        row=native.control.configs[0]
        if mutation=='mapped':row.MappedSymbol='CHANGED'
        elif mutation=='mode':row.data_mapping_mode=native.Mode.LAST_TRADING_DAY
        elif mutation=='type':row.type.FullName='QuantConnect.Data.Market.QuoteBar'
        elif mutation=='sid':row.symbol=base.Symbol(base.SID('FOREIGN X123ABC'),'FOREIGN')
        elif mutation=='raw':row.data_normalization_mode='adjusted'
        elif mutation=='ff':row.fill_data_forward=True
        elif mutation=='zone':row.data_time_zone.Id='UTC'
        else:native.control.configs[0]=deepcopy(row)
    native.map.hook=hook;native.algo._probe();out=result(native)
    assert out['map_trace']['status'] in ('map_configuration_changed','map_configuration_unproved')
    assert out['map_trace']['complete'] is False and out['history_calls']==4

@pytest.mark.parametrize('phase',['getparts','provider_next','get','resolve','rows_iter','row_next','mapped','has'])
def test_every_map_effect_preserves_actual_child_custody_before_and_after(native,phase):
    native.initialize()
    native.map.hook=lambda at:setattr(native.algo,'algorithm_id','d'*32) if at==phase else None
    native.algo._probe();out=result(native)
    assert out['status']=='runtime_custody_changed' and out['history_calls']==4
    assert out['map_trace']['complete'] is False and out['end_runtime_custody'] is False

@pytest.mark.parametrize('phase',['getparts','resolve','mapped','has'])
@pytest.mark.parametrize('kind',['ordinary','cancel','fatal'])
def test_private_error_bodies_stay_private_and_nonordinary_priority_is_preserved(native,phase,kind):
    native.initialize()
    class Fatal(BaseException):pass
    def hook(at):
        if at==phase:raise {'ordinary':RuntimeError,'cancel':KeyboardInterrupt,'fatal':Fatal}[kind]('PRIVATE-MAP-ERROR')
    native.map.hook=hook
    if kind=='ordinary':native.algo._probe()
    else:
        with pytest.raises(KeyboardInterrupt if kind=='cancel' else native.module.ProbeStopped) as error:native.algo._probe()
        assert 'PRIVATE-MAP-ERROR' not in str(error.value)
    out=result(native)
    if kind=='ordinary':assert out['map_trace']['status']=='initialized_map_api_unproved' and out['map_trace']['config_reads']==2
    else:assert out['map_trace']['config_reads']==1
    assert out['history_calls']==4

@pytest.mark.parametrize('phase',['before','getparts','mapped'])
def test_config_drift_never_allows_a_later_map_effect(native,phase):
    native.initialize()
    if phase=='before':native.module.PROBE_CONFIG['binding']['key']='foreign/unreserved'
    else:
        native.map.hook=lambda at:native.module.PROBE_CONFIG['binding'].__setitem__('key','foreign/unreserved') if at==phase else None
    native.algo._probe();out=result(native)
    assert out['status']=='config_digest'
    if phase=='before':assert not native.algo.object_store.calls and not native.map.calls
    else:assert out['history_calls']==4 and out['map_trace']['complete'] is False

@pytest.mark.parametrize('phase',['map_cfg_before_read','map_parts','map_alias'])
def test_config_mutating_native_getter_is_caught_before_requested_effect(native,phase):
    native.initialize();original=native.algo.get_locked
    def get_locked():
        if native.algo._phase==phase:native.module.PROBE_CONFIG['binding']['key']='foreign/unreserved'
        return original()
    native.algo.get_locked=get_locked;native.algo._probe();out=result(native)
    assert out['status']=='config_digest' and out['history_calls']==4
    if phase=='map_cfg_before_read':assert out['map_trace']['config_reads']==0
    elif phase=='map_parts':assert 'getparts' not in native.map.calls
    else:assert not any(isinstance(row,tuple) and row[0]=='mapped' for row in native.map.calls)

@pytest.mark.parametrize('fault',['wrong_clock','wrong_project','unlocked','parent_job'])
def test_no_private_or_history_or_map_before_genuine_child_binding(native,fault):
    native.initialize()
    if fault=='wrong_clock':native.algo.time+=timedelta(minutes=1)
    elif fault=='wrong_project':native.algo.project_id=37650980
    elif fault=='unlocked':native.algo.get_locked=lambda:False
    else:native.algo.algorithm_id=native.module.PROBE_CONFIG['binding']['job_id']
    native.algo._probe();out=result(native)
    assert not native.algo.object_store.calls and not native.map.calls and out['history_calls']==0
