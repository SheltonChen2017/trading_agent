"""Synthetic private-result reader; no actual QC/private/provider effects."""
import ast
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace as NS

import pytest
from research.target_price_revisions_qc import comparison_20261028_native_result_reader as r
from tests.target_price_revisions_qc import test_qc_comparison_20261028_completion as pure
from tests.target_price_revisions_qc import test_qc_comparison_20261028_algorithm as off


@pytest.fixture
def sources():return {name:Path(name).read_bytes() for name in r.SOURCE_PATHS}


@pytest.fixture
def package():
    raw=Path('research/target_price_revisions_qc/extended_calendar.json').read_bytes()
    return pure.pack(raw,days=[])


def build(sources,package,**changes):
    args=dict(public_sources=sources,binding=package['binding'],summary_raw=package['raws'][0],
        config_raw=package['raws'][2],index_key=package['prefix']+'index.json',
        operation_id='TPR-CMP28-RESULT-READER-SYNTHETIC-001',git_head='a'*40)
    args.update(changes);return r.build_native_result_reader(**args)


def test_generated_main_is_plain_single_file_under_limit_with_no_effect_authority(sources,package):
    raw,report=build(sources,package);report=json.loads(report);tree=ast.parse(raw);compile(tree,'<reader>','exec')
    assert len(raw)==report['main_bytes']<=60000 and hashlib.sha256(raw).hexdigest()==report['main_sha256']
    assert report['main_only_cloud_edit'] is True and report['preserve_other_cloud_files']==23
    assert report['max_chunk_reads']==1024 and report['max_records']==300000 and report['max_claims']==1026
    calls={node.func.id for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)}
    assert not calls&{'exec','eval','__import__','open'}
    imports={node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)}
    imports|={item.name for node in ast.walk(tree) if isinstance(node,ast.Import) for item in node.names}
    assert not imports&{'gzip','zlib','codecs','comparison_20261028_completion','extended_evidence','extended_metrics'}
    assert all(report[key] is False for key in ('native_permission','strategy_accepted','canonical_admission',
        'native_origin_authenticated','backend_durability_proven','independent_reconciliation_proven','data_rights_authenticated'))


@pytest.mark.parametrize('path',tuple(r.PINS))
def test_each_public_dependency_rejects_one_byte_drift(sources,package,path):
    sources[path]+=b'\n'
    with pytest.raises(r.NativeReaderBuildRefusal):build(sources,package)


@pytest.mark.parametrize('change',[{'index_key':'private/other/index.json'},{'operation_id':'foreign'},
    {'git_head':'bad'},{'summary_raw':b'{}'},{'config_raw':b'{}'}])
def test_reader_parent_identity_and_supplied_own_aggregate_bounds_refuse(sources,package,change):
    with pytest.raises(r.NativeReaderBuildRefusal):build(sources,package,**change)


def make_native(sources,package,monkeypatch,before_initialize=None):
    off.driver.__wrapped__(monkeypatch)
    raw,_=build(sources,package);module=ModuleType('synthetic_native_result_reader');monkeypatch.setitem(sys.modules,module.__name__,module)
    exec(compile(raw,'<reader>','exec'),module.__dict__)
    algo=module.Main();algo.live_mode=False;algo.project_id=37650980;algo.algorithm_id='';state=NS(locked=False,hook=lambda *_:None,events=[])
    algo.get_locked=lambda:state.locked;logs=[];algo.log=logs.append
    for name in ('set_time_zone','set_start_date','set_end_date','set_benchmark'):setattr(algo,name,lambda *_:None)
    algo.add_equity=lambda *_args,**_kwargs:NS(symbol=off.Symbol('SPY'))
    algo.schedule=NS(on=lambda *_:None);algo.date_rules=NS(every_day=lambda *_:None);algo.time_rules=NS(at=lambda *_:None)
    class Store(off.NativeStore):
        def contains_key(self,key):state.events.append(('contains',key));state.hook('contains',key);return super().contains_key(key)
        def save_bytes(self,key,raw):state.events.append(('save',key));state.hook('save',key);return super().save_bytes(key,raw)
        def read_bytes(self,key):state.events.append(('read',key));state.hook('read',key);return super().read_bytes(key)
    store=Store();store.values[package['prefix']+'index.json']=package['raws'][1]
    for descriptor,chunk in zip(package['index']['chunks'],package['chunks']):store.values[descriptor['key']]=chunk
    algo.object_store=store
    if before_initialize is not None:before_initialize(module)
    algo.initialize();assert store.calls==[]
    state.locked=True;algo.algorithm_id='c'*32
    return NS(algo=algo,module=module,state=state,logs=logs,store=store,package=package)


@pytest.fixture
def native(sources,package,monkeypatch):return make_native(sources,package,monkeypatch)


def result(case):
    case.algo.on_end_of_algorithm();raw=case.logs[-1];assert raw.startswith('CMP28_PRIVATE_RESULT_READER_RESULT ')
    assert not any(value in raw for value in ('PRIVATE-SENTINEL','"security_id"','"raw_marks"','"holdings"','"ticker"'))
    return json.loads(raw.split(' ',1)[1])


def test_actual_child_reads_only_bound_index_chunks_after_claims_and_replays_without_acceptance(native):
    native.algo._audit();out=result(native)
    assert out['status']=='completed_supplied_journal_replay' and out['completed_read_replay'] is True
    assert out['private_reads']==2 and out['claims_same_node_verified']==3
    report=out['completion_report'];assert report['journal_framing_replayed'] is True
    assert report==pure.replay(native.package)
    assert report['daily_nav_observations']==0 and report['reported_nav_metrics'] is None
    assert report['native_origin_authenticated'] is report['independent_order_fill_action_cash_reconciliation'] is False
    events=native.state.events
    assert [method for method,_ in events]==['contains','save','read','read','contains','save','read','read','contains','save','read']
    claims=[json.loads(raw) for key,raw in native.store.values.items() if 'result-reader' in key]
    assert len(claims)==3 and all(claim['spent_before_effect'] and not claim['backend_durability_proven'] for claim in claims)
    before=list(events);native.algo._audit();assert events==before


@pytest.mark.parametrize('stage',['index','chunk','replay_parse'])
def test_private_hash_or_parse_refusal_never_exposes_body_and_never_retries(native,stage):
    if stage=='index':native.store.values[native.package['prefix']+'index.json']=b'PRIVATE-SENTINEL'
    elif stage=='chunk':native.store.values[native.package['index']['chunks'][0]['key']]=b'PRIVATE-SENTINEL'
    else:
        original=native.module.E_parse_json
        native.module.E_parse_json=lambda raw:(_ for _ in ()).throw(ValueError('PRIVATE-SENTINEL')) if b'ordinal' in raw else original(raw)
    native.algo._audit();out=result(native)
    assert out['status']=='private_read_or_replay_refused' and out['completed_read_replay'] is False
    before=list(native.state.events);native.algo._audit();assert native.state.events==before


@pytest.mark.parametrize('fault',['project','parent_job','empty_job','unlocked','live'])
def test_custody_refuses_before_any_private_effect(native,fault):
    if fault=='project':native.algo.project_id=1
    elif fault=='parent_job':native.algo.algorithm_id=native.package['binding']['job_id']
    elif fault=='empty_job':native.algo.algorithm_id=''
    elif fault=='unlocked':native.state.locked=False
    else:native.algo.live_mode=True
    native.algo._audit();out=result(native)
    assert native.store.calls==[] and out['completed_read_replay'] is False


@pytest.mark.parametrize('stage',['contains','save','read'])
def test_custody_drift_after_uncertain_native_effect_preserves_original_child_job_and_stops(native,stage):
    def drift(method,key):
        if method==stage:native.algo.algorithm_id='d'*32
    native.state.hook=drift;native.algo._audit();out=result(native)
    assert out['actual_child_job_id']=='c'*32 and out['end_runtime_custody'] is False and not out['completed_read_replay']
    assert len(native.store.calls)=={'contains':1,'save':2,'read':3}[stage]


@pytest.mark.parametrize('kind',['cancel','fatal'])
def test_native_nonordinary_cancellation_and_fatal_are_body_free(native,kind):
    class Fatal(BaseException):pass
    def stop(*_):raise (KeyboardInterrupt if kind=='cancel' else Fatal)('PRIVATE-SENTINEL')
    native.state.hook=stop
    with pytest.raises(KeyboardInterrupt if kind=='cancel' else native.module.ReaderStopped) as error:native.algo._audit()
    assert 'PRIVATE-SENTINEL' not in str(error.value)


def test_complete_daily_axis_produces_reported_nav_metrics_but_not_independent_money_acceptance(sources,monkeypatch):
    original=Path('research/target_price_revisions_qc/extended_calendar.json').read_bytes()
    package=pure.pack(original)
    for number,record in enumerate(package['records'][:-1]):record['payload']['nav']=str(100000+number)
    package['summary']['last_observed_nav']=pure.rat(101448);package['summary']['final_nav']=pure.rat(101448)
    package=pure.rebuild(package);case=make_native(sources,package,monkeypatch)
    case.algo._audit();out=result(case);report=out['completion_report']
    assert out['completed_read_replay'] is True and report['daily_nav_axis_complete'] is True
    assert report==pure.replay(package)
    assert report['daily_nav_observations']==1449 and report['reported_nav_metrics']['observations']==1449
    assert report['reported_nav_metrics']['last_nav_usd']==pure.rat(101448)
    assert report['reported_fees']==pure.rat('0.01')
    assert report['independent_order_fill_action_cash_reconciliation'] is False
    assert out['independent_reconciliation_proven'] is out['native_origin_authenticated'] is out['strategy_accepted'] is False


@pytest.mark.parametrize('mode',['exists','unknown','save_false','readback','oversize_chunk'])
def test_claim_uncertainty_no_overwrite_and_byte_bounds_stop_before_unclaimed_private_read(native,mode):
    if mode=='exists':native.store.contains_key=lambda key:True
    elif mode=='unknown':native.store.contains_key=lambda key:None
    elif mode=='save_false':native.store.save_bytes=lambda key,raw:False
    elif mode=='readback':
        original=native.store.read_bytes
        native.store.read_bytes=lambda key:b'PRIVATE-SENTINEL' if 'result-reader' in key else original(key)
    else:
        key=native.package['index']['chunks'][0]['key'];native.store.values[key]=b'x'*(512*1024+1)
    native.algo._audit();out=result(native)
    assert out['completed_read_replay'] is False and out['status']=='private_read_or_replay_refused'
    if mode!='oversize_chunk':assert out['private_reads']==0
    before=list(native.state.events);native.algo._audit();assert native.state.events==before


@pytest.mark.parametrize('stage',['parse','hash','replay'])
def test_custody_drift_during_private_hash_parse_or_replay_prevents_success(native,stage):
    if stage=='parse':
        original=native.module.E_parse_json
        def mutate(raw):
            value=original(raw);native.algo.algorithm_id='d'*32;return value
        native.module.E_parse_json=mutate
    elif stage=='hash':
        original=native.module.C__sha
        def mutate(raw):
            value=original(raw);native.algo.algorithm_id='d'*32;return value
        native.module.C__sha=mutate
    else:
        original=native.module.C_replay_chunks
        def mutate(*args,**kwargs):
            value=original(*args,**kwargs);native.algo.algorithm_id='d'*32;return value
        native.module.C_replay_chunks=mutate
    native.algo._audit();out=result(native)
    assert out['completed_read_replay'] is False and out['end_runtime_custody'] is False
    assert out['actual_child_job_id']=='c'*32


def test_runtime_has_no_history_orders_marks_or_broker_api(sources,package):
    raw,_=build(sources,package);tree=ast.parse(raw)
    names={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
    assert not names&{'history','market_order','market_on_open_order','set_holdings','liquidate','set_market_price','download','portfolio','transactions'}


def test_metadata_claim_and_chunk_maxima_are_checked_without_oversized_effect(native):
    native.algo._bound()
    with pytest.raises(ValueError):native.algo._read('chunk',{'key':native.package['prefix']+'chunk-0000.jsonl','bytes':512*1024+1,'sha256':'a'*64},512*1024)
    assert not native.store.calls
    native.algo._claims=1026
    with pytest.raises(ValueError):native.algo._claim('chunk',{'key':'fixed','bytes':1,'sha256':'b'*64})
    assert not native.store.calls


def test_conservative_twentyfour_hash_metadata_size_envelope_stays_plain_and_bounded(sources,package):
    from research.target_price_revisions_qc import comparison_20261028_multi_bundle as bundle
    # Size-only synthetic envelope. Actual multi parent rendered closure has
    #15active files; the separate preserved24-file census must not replace it.
    templates=dict(bundle.PINS)
    package['templates']=templates
    closure=pure.sha(pure.wire({'schema':'tpr-cmp28-public-template-closure-v1','source_hashes':templates}))
    package['config']['source_template_closure_sha256']=closure;package['summary']['source_template_closure_sha256']=closure
    names=['extended_core.py','cap_tilt.py','cap_observer.py','extended_construction.py','extended_loader.py',
        'extended_runtime_successor.py','extended_algorithm_successor.py','comparison_20261028.py',
        'comparison_20261028_algorithm.py','comparison_20261028_config.py','main.py','raw_revision.py',
        'comparison_20261028_events.py','comparison_20261028_signal_native.py','comparison_20261028_multi_algorithm.py']
    names+=[f'retained_legacy_source_{number:02d}.py' for number in range(9)]
    package['rendered']={name:pure.sha(name.encode()) for name in names}
    config_hash=pure.sha(pure.wire(package['config']));package['summary']['config_sha256']=config_hash
    package['prefix']=f"tpr-cmp28/evidence/{r.completion.STUDY}/{package['config']['operation_id']}/{config_hash}/attempt-1/37650980/{package['summary']['job_id']}/"
    package=pure.rebuild(package);raw,report=build(sources,package);report=json.loads(report)
    assert len(templates)==16 and len(names)==24 and report['main_bytes']==len(raw)<=60000


@pytest.mark.parametrize('mode',['prefix','index_key','parent_project','parent_job','parent_config','json','hash','coordinated_rebase'])
def test_frozen_reader_configuration_drift_refuses_before_any_claim_or_private_read(native,mode):
    cfg=native.module.READER_CONFIG
    if mode=='prefix':cfg['parent_prefix']='foreign/private/'
    elif mode=='index_key':cfg['index_key']='foreign/private/index.json'
    elif mode=='parent_project':cfg['binding']['project_id']=37650453
    elif mode=='parent_job':cfg['binding']['job_id']='d'*32
    elif mode=='parent_config':cfg['binding']['config_sha256']='f'*64
    elif mode=='json':native.module.READER_CONFIG_JSON+=' '
    elif mode=='hash':native.module.READER_CONFIG_SHA256='f'*64
    else:
        cfg['parent_prefix']='foreign/private/';cfg['index_key']='foreign/private/index.json'
        native.module.READER_CONFIG_JSON=json.dumps(cfg,sort_keys=True,separators=(',',':'))
        native.module.READER_CONFIG_SHA256=hashlib.sha256(native.module.READER_CONFIG_JSON.encode()).hexdigest()
    native.store.values['foreign/private/index.json']=b'PRIVATE-SENTINEL'
    native.algo._audit();out=result(native)
    assert native.state.events==[] and native.store.calls==[] and out['private_reads']==0
    assert out['completed_read_replay'] is False and out['end_runtime_custody'] is False
    assert out['parent_job_id']==native.package['binding']['job_id']


@pytest.mark.parametrize('phase',['contains','save','claim_readback','index_read','chunk_read','hash','parse','replay'])
def test_config_drift_during_every_guarded_phase_stops_without_foreign_or_further_effect(native,phase):
    def mutate():
        native.module.READER_CONFIG['parent_prefix']='foreign/private/'
        native.module.READER_CONFIG['index_key']='foreign/private/index.json'
    if phase in ('hash','parse','replay'):
        name={'hash':'C__sha','parse':'E_parse_json','replay':'C_replay_chunks'}[phase]
        original=getattr(native.module,name)
        def wrapped(*args,**kwargs):
            value=original(*args,**kwargs);mutate();return value
        setattr(native.module,name,wrapped)
    else:
        def change(method,key):
            if (method==phase or phase=='claim_readback' and method=='read' and 'result-reader' in key
                    or phase=='index_read' and method=='read' and key==native.package['prefix']+'index.json'
                    or phase=='chunk_read' and method=='read' and key.endswith('chunk-0000.jsonl')):mutate()
        native.state.hook=change
    native.algo._audit();out=result(native)
    assert out['completed_read_replay'] is False and out['end_runtime_custody'] is False
    assert out['actual_child_job_id']=='c'*32
    assert all('foreign/private' not in key for _,key in native.state.events)
    before=list(native.state.events);native.algo._audit();assert native.state.events==before


def test_native_getter_cannot_mutate_decoded_scope_between_guard_and_effect(native):
    def locked():
        native.module.READER_CONFIG['parent_prefix']='foreign/private/'
        return True
    native.algo.get_locked=locked
    native.algo._audit();out=result(native)
    assert not native.state.events and out['completed_read_replay'] is False


def test_replay_processing_claim_keeps_exact_index_descriptor_and_separate_journal_bytes(native):
    native.algo._audit();out=result(native);assert out['completed_read_replay'] is True
    claims=[json.loads(raw) for key,raw in native.store.values.items() if 'result-reader' in key]
    replay=next(claim for claim in claims if claim['kind']=='replay')['resource']
    assert replay['key']==native.package['prefix']+'index.json'
    assert replay['sha256']==native.package['binding']['envelopes']['index']['sha256']
    assert replay['bytes']==len(native.package['raws'][1])
    assert replay['journal_total_bytes']==sum(map(len,native.package['chunks']))
    assert replay['maximum_records']==300000 and replay['maximum_chunks']==1024


def test_decoded_scope_drift_before_initialize_keeps_original_frozen_parent_metadata(sources,package,monkeypatch):
    def change(module):
        module.READER_CONFIG['binding']['job_id']='d'*32
        module.READER_CONFIG['operation_id']='PRIVATE-SENTINEL'
    case=make_native(sources,package,monkeypatch,before_initialize=change)
    case.algo._audit();out=result(case)
    assert not case.store.calls and out['status']=='setup_refused'
    assert out['parent_job_id']==package['binding']['job_id']
    assert out['operation_id']=='TPR-CMP28-RESULT-READER-SYNTHETIC-001'


@pytest.mark.parametrize('kind',['cancel','fatal'])
def test_config_drift_does_not_demote_first_native_nonordinary_stop(native,kind):
    class Fatal(BaseException):pass
    def stop(*_):
        native.module.READER_CONFIG['parent_prefix']='foreign/private/'
        raise (KeyboardInterrupt if kind=='cancel' else Fatal)('PRIVATE-SENTINEL')
    native.state.hook=stop
    with pytest.raises(KeyboardInterrupt if kind=='cancel' else native.module.ReaderStopped) as error:native.algo._audit()
    assert 'PRIVATE-SENTINEL' not in str(error.value)
    assert len(native.state.events)==1 and native.algo._reads==0
