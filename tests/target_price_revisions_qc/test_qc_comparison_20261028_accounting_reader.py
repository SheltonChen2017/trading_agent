"""Generated reader software fixtures only; no actual native/private effects."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace as NS
import pytest
from research.target_price_revisions_qc import comparison_20261028_accounting_reader as r
from tests.target_price_revisions_qc import test_qc_comparison_20261028_accounting as fixture
from tests.target_price_revisions_qc import test_qc_comparison_20261028_algorithm as off

@pytest.fixture(scope='module')
def sources():return {name:Path(name).read_bytes() for name in r.SOURCE_PATHS}

@pytest.fixture(scope='module')
def original():return Path(r.PREFIX+'extended_calendar.json').read_bytes()

@pytest.fixture(scope='module')
def package(original):return fixture.package(original)

def compact(package,original):
    return r.accounting.normalize_api_observations(package['order_pages'],package['chart_raw'],package['api_binding'],
        binding=package['binding'],source_calendar_raw=original,normalizer_source_sha256=r.ACCOUNTING_SHA256)

def build(sources,package,original,**changes):
    raw=compact(package,original)
    args=dict(public_sources=sources,binding=package['binding'],summary_raw=package['raws'][0],config_raw=package['raws'][2],
        index_key=package['prefix']+'index.json',operation_id='TPR-CMP28-RESULT-READER-ACCOUNTING-SYNTHETIC-001',git_head='a'*40,
        compact_raw=raw,expected_compact_sha256=hashlib.sha256(raw).hexdigest(),expected_normalizer_source_sha256=r.ACCOUNTING_SHA256)
    args.update(changes);return r.build_native_accounting_reader(**args)

@pytest.mark.parametrize('arm',['cap_off','cap_tilt_50','cap_tilt_100','cap_tilt_200','pure_tpr'])
def test_all_five_parent_configs_plain_two_file_closure(sources,original,arm):
    files,raw=build(sources,fixture.package(original,arm=arm),original);report=json.loads(raw)
    assert set(files)=={'main.py',r.HELPER}
    for name,raw in files.items():
        assert len(raw)<=60000
        tree=ast.parse(raw);compile(tree,name,'exec')
        calls={n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
        attrs={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
        imports={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
        imports|={item.name for n in ast.walk(tree) if isinstance(n,ast.Import) for item in n.names}
        assert not calls&{'exec','eval','__import__','open'}
        assert not imports&{'gzip','zlib','base64','pickle','requests','http.client','extended_native','extended_operations'}
        assert not attrs&{'history','download','market_order','market_on_open_order','set_holdings','portfolio','transactions'}
    assert report['main_sha256']==hashlib.sha256(files['main.py']).hexdigest()
    assert report['helper_sha256']==hashlib.sha256(files[r.HELPER]).hexdigest()
    assert report['preserve_other_cloud_files']==23 and report['max_cloud_files_after_install']==25
    assert report['max_claims']==1027 and report['max_parse_calls']==900150 and report['private_processing_claims']==2
    assert all(report[key] is False for key in ('native_permission','native_origin_authenticated','backend_durability_proven',
        'independent_reconciliation_proven','data_rights_authenticated','historical_pit_authenticated','strategy_accepted',
        'canonical_admission','raw_api_pages_revalidated_in_child','exact_journal_to_event_id_mapping_proven',
        'original_strategy_intent_verified','moo_order_type_verified','cancellation_policy_verified','slippage_model_verified',
        'runtime_self_source_authentication_proven'))

@pytest.mark.parametrize('path',tuple(r.PINS))
def test_public_dependency_drift_refuses_before_emission(sources,package,original,path):
    with pytest.raises(r.AccountingReaderBuildRefusal):build({**sources,path:sources[path]+b'\n'},package,original)

@pytest.mark.parametrize('fault',['bytes','compact_hash','source_hash','parent_job','foreign_index'])
def test_compact_source_full_parent_identity_required(sources,package,original,fault):
    changes={}
    if fault=='bytes':changes['compact_raw']=b'{}'
    elif fault=='compact_hash':changes['expected_compact_sha256']='f'*64
    elif fault=='source_hash':changes['expected_normalizer_source_sha256']='f'*64
    elif fault=='foreign_index':changes['index_key']='foreign/index.json'
    else:
        parent=deepcopy(package['binding']);parent['job_id']='d'*32;changes['binding']=parent
    with pytest.raises(r.AccountingReaderBuildRefusal):build(sources,package,original,**changes)

def make_native(sources,package,original,monkeypatch,pre_initialize=None):
    off.driver.__wrapped__(monkeypatch);files,_=build(sources,package,original)
    helper=ModuleType('comparison_20261028_accounting_runtime');monkeypatch.setitem(sys.modules,helper.__name__,helper)
    exec(compile(files[r.HELPER],'<pure-accounting-runtime>','exec'),helper.__dict__)
    module=ModuleType('synthetic_accounting_reader');monkeypatch.setitem(sys.modules,module.__name__,module)
    exec(compile(files['main.py'],'<accounting-reader>','exec'),module.__dict__)
    algo=module.Main();algo.live_mode=False;algo.project_id=37650980;algo.algorithm_id=''
    state=NS(locked=False,hook=lambda *_:None,events=[]);algo.get_locked=lambda:state.locked;logs=[];algo.log=logs.append
    for name in ('set_time_zone','set_start_date','set_end_date','set_benchmark'):setattr(algo,name,lambda *_:None)
    algo.add_equity=lambda *_args,**_kwargs:NS(symbol=off.Symbol('SPY'))
    algo.schedule=NS(on=lambda *_:None);algo.date_rules=NS(every_day=lambda *_:None);algo.time_rules=NS(at=lambda *_:None)
    class Store(off.NativeStore):
        def contains_key(self,key):state.events.append(('contains',key));state.hook('contains',key);return super().contains_key(key)
        def save_bytes(self,key,raw):state.events.append(('save',key));state.hook('save',key);return super().save_bytes(key,raw)
        def read_bytes(self,key):state.events.append(('read',key));state.hook('read',key);return super().read_bytes(key)
    store=Store();store.values[package['prefix']+'index.json']=package['raws'][1]
    for desc,chunk in zip(package['index']['chunks'],package['chunks']):store.values[desc['key']]=chunk
    algo.object_store=store
    if pre_initialize:pre_initialize(module,helper)
    algo.initialize();assert store.calls==[]
    state.locked=True;algo.algorithm_id='c'*32
    return NS(algo=algo,module=module,helper=helper,state=state,store=store,logs=logs,package=package)

@pytest.fixture
def native(sources,package,original,monkeypatch):return make_native(sources,package,original,monkeypatch)

def result(case):
    case.algo.on_end_of_algorithm();raw=case.logs[-1]
    assert raw.startswith('CMP28_ACCOUNTING_READER_RESULT ')
    assert not any(x in raw for x in ('PRIVATE-SENTINEL','"security_id"','"raw_marks"','"holdings"','"ticker"'))
    return json.loads(raw.split(' ',1)[1])

def test_selected_compact_path_replays1449_rows_after_distinct_accounting_claim(native,original):
    native.algo._audit();out=result(native)
    assert out['status']=='completed_supplied_accounting_comparison'
    assert out['completed_read_replay'] is out['completed_accounting_processing'] is True
    raw=compact(native.package,original)
    expected=r.accounting.audit_compact(*native.package['raws'],binding=native.package['binding'],
        chunks=native.package['chunks'],compact_raw=raw,expected_compact_sha256=hashlib.sha256(raw).hexdigest(),
        expected_normalizer_source_sha256=r.ACCOUNTING_SHA256)
    assert out['accounting_report']==expected and expected['daily_nav_observations']==1449
    assert out['supplied_evidence_accounting_reconciled'] is expected['supplied_evidence_accounting_reconciled'] is True
    claims=[json.loads(value) for key,value in native.store.values.items() if '/accounting-result-reader/' in key]
    assert len(claims)==out['claims_same_node_verified']==len(native.package['chunks'])+3
    assert [row['kind'] for row in claims]==['index']+['chunk']*len(native.package['chunks'])+['replay','accounting']
    scope=claims[-1]['resource']
    assert scope['key']==native.package['prefix']+'index.json' and scope['bytes']==len(native.package['raws'][1])
    assert scope['journal_total_bytes']==sum(map(len,native.package['chunks']))
    assert scope['compact_sha256']==hashlib.sha256(raw).hexdigest() and scope['normalizer_source_sha256']==r.ACCOUNTING_SHA256
    assert all(not claim['backend_durability_proven'] and claim['spent_before_effect'] for claim in claims)
    assert out['private_reads']==1+len(native.package['chunks'])
    assert out['raw_api_pages_revalidated_in_child'] is out['strategy_accepted'] is out['native_origin_authenticated'] is False
    before=list(native.state.events);native.algo._audit();assert native.state.events==before

@pytest.mark.parametrize('fault',['project','parent_job','unlocked','live','compact','helper_hash','source_hash','helper_function','helper_data','callback'])
def test_custody_compact_helper_drift_stops_before_private_effect(native,fault):
    if fault=='project':native.algo.project_id=1
    elif fault=='parent_job':native.algo.algorithm_id=native.package['binding']['job_id']
    elif fault=='unlocked':native.state.locked=False
    elif fault=='live':native.algo.live_mode=True
    elif fault=='compact':native.module.READER_CONFIG['accounting']['compact_json']='{}'
    elif fault=='helper_hash':native.module.ACCOUNTING_RUNTIME_SHA256='f'*64
    elif fault=='source_hash':native.helper.SOURCE_SHA256='f'*64
    elif fault=='helper_function':native.helper.audit_compact=lambda *_a,**_kw:{}
    elif fault=='helper_data':native.helper.COMPACT_JSON='{}'
    else:native.module.ACCOUNTING_CALLBACKS['e.parse_json']=lambda _:None
    native.algo._audit();out=result(native)
    assert native.store.calls==[] and not out['completed_accounting_processing'] and not out['end_runtime_custody']

@pytest.mark.parametrize('phase',['getter','contains','save','read','parse','accounting'])
def test_drift_each_effect_boundary_cannot_complete_or_read_foreign(native,phase):
    def drift():native.module.READER_CONFIG['accounting']['helper_sha256']='f'*64
    if phase=='getter':
        def locked():drift();return True
        native.algo.get_locked=locked
    elif phase=='parse':
        original=native.module.E_parse_json
        def parse(raw):value=original(raw);drift();return value
        native.module.E_parse_json=parse
    elif phase=='accounting':
        original=native.algo._effect
        def effect(name,call):
            if name=='accounting':drift()
            return original(name,call)
        native.algo._effect=effect
    else:native.state.hook=lambda method,_key:drift() if method==phase else None
    native.algo._audit();out=result(native)
    assert not out['completed_accounting_processing'] and not out['end_runtime_custody']
    assert all('foreign' not in key for _,key in native.state.events)
    if phase=='getter':assert not native.state.events
    before=list(native.state.events);native.algo._audit();assert native.state.events==before

@pytest.mark.parametrize('kind',['cancel','fatal'])
def test_accounting_claim_stop_body_free_with_honest_status(native,kind):
    class Fatal(BaseException):pass
    target='access-'+str(len(native.package['chunks'])+2).zfill(4)+'.json'
    def stop(method,key):
        if key.endswith(target) and method=='save':raise (KeyboardInterrupt if kind=='cancel' else Fatal)('PRIVATE-SENTINEL')
    native.state.hook=stop
    with pytest.raises(KeyboardInterrupt if kind=='cancel' else native.module.ReaderStopped) as error:native.algo._audit()
    assert 'PRIVATE-SENTINEL' not in str(error.value)
    out=result(native)
    assert out['status']==('cancelled' if kind=='cancel' else 'fatal_or_uncertain')
    assert out['completed_read_replay'] is True and out['completed_accounting_processing'] is False

def test_claim_parse_ceilings_precede_effect_and_processing_never_retries(native):
    native.algo._bound();native.algo._claims=1027
    with pytest.raises(ValueError):native.algo._claim('accounting',{'key':'owned','bytes':1,'sha256':'a'*64})
    assert not native.state.events
    native.algo._parse_calls=900150
    with pytest.raises(ValueError):native.algo._effect('parse',lambda:None)
    assert native.algo._parse_calls==900151 and not native.state.events


@pytest.mark.parametrize('fault',['decoded','encoded','coordinated','helper_metadata'])
def test_preinitialize_drift_never_becomes_the_frozen_scope(sources,package,original,monkeypatch,fault):
    def mutate(module,helper):
        if fault=='decoded':module.READER_CONFIG['binding']['job_id']='d'*32
        elif fault=='encoded':module.READER_CONFIG_JSON='PRIVATE-SENTINEL'
        elif fault=='helper_metadata':helper.PARENT_SUMMARY_JSON='PRIVATE-SENTINEL'
        else:
            module.READER_CONFIG['binding']['job_id']='d'*32
            module.READER_CONFIG_JSON=json.dumps(module.READER_CONFIG,sort_keys=True,separators=(',',':'))
            module.READER_CONFIG_SHA256=hashlib.sha256(module.READER_CONFIG_JSON.encode()).hexdigest()
    case=make_native(sources,package,original,monkeypatch,mutate);case.algo._audit();out=result(case)
    assert not case.store.calls and out['status']=='setup_refused' and not out['completed_accounting_processing']
    assert out['parent_job_id']==package['binding']['job_id']


def test_pure_consumer_executable_ast_is_preserved_except_documentation(sources,package,original):
    old,_=r.base.build_native_result_reader(public_sources={name:sources[name] for name in r.base.PINS},
        binding=package['binding'],summary_raw=package['raws'][0],config_raw=package['raws'][2],
        index_key=package['prefix']+'index.json',operation_id='TPR-CMP28-RESULT-READER-ACCOUNTING-SYNTHETIC-001',git_head='a'*40)
    files,_=build(sources,package,original)
    def normalized(raw):
        tree=ast.parse(raw)
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.body:
                first=node.body[0]
                if isinstance(first,ast.Expr) and isinstance(first.value,ast.Constant) and isinstance(first.value.value,str):
                    node.body.pop(0)
                    if not node.body:node.body.append(ast.Pass())
        return {node.name:ast.dump(node,include_attributes=False) for node in tree.body
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name.startswith(('C_','E_','M_','R_'))}
    expected,actual=normalized(old),normalized(files['main.py'])
    assert expected and all(actual[name]==value for name,value in expected.items())


@pytest.mark.parametrize('arm',['cap_off','cap_tilt_50','cap_tilt_100','cap_tilt_200','pure_tpr'])
def test_real_public_renderer_full_source_config_closures_fit_and_bind(sources,original,arm):
    from research.target_price_revisions_qc import comparison_20261028_bundle as off_bundle
    from research.target_price_revisions_qc import comparison_20261028_multi_bundle as multi_bundle
    if arm=='cap_off':
        public={name:Path(name).read_bytes() for name in off_bundle.SOURCE_PATHS}
        financial,raw=off_bundle.build_off_candidate(public_sources=public,
            operation_id='TPR-CMP28-OFF-ACCOUNTING-READER-INTEROP-001',attempt=4,prior_attempts_looks_sha256='b'*64)
    else:
        public={name:Path(name).read_bytes() for name in multi_bundle.SOURCE_PATHS}
        descriptor={'key':'tpr-cmp28/inputs/synthetic/packet.json','sha256':'c'*64,'bytes':1234,
            'encoding':'utf-8-json','source_inventory_sha256':'d'*64}
        financial,raw=multi_bundle.build_multi_candidate(public_sources=public,arm=arm,
            operation_id='TPR-CMP28-ACCOUNTING-READER-INTEROP-001',attempt=4,prior_attempts_looks_sha256='b'*64,
            signal_packet=descriptor)
    parent_report=json.loads(raw)
    tree=ast.parse(financial['comparison_20261028_config.py'])
    literal=next(n.value for n in tree.body if isinstance(n,ast.Assign) and n.targets[0].id=='CONFIG_JSON')
    config_raw=ast.literal_eval(literal).encode('ascii');config=json.loads(config_raw)
    p=fixture.package(original,arm=arm);p['config']=config;p['calendar']=off_bundle._calendar(original,config['policy_sha256'])
    p['templates']=parent_report['template_source_hashes'];p['rendered']=parent_report['cloud_source_hashes']
    for key in ('study_id','candidate_id','arm','operation_id','attempt','project_id','policy_sha256','calendar_sha256','source_template_closure_sha256'):
        p['summary'][key]=config[key]
    p['summary']['config_sha256']=hashlib.sha256(config_raw).hexdigest()
    p['prefix']=(f"tpr-cmp28/evidence/{config['study_id']}/{config['operation_id']}/{p['summary']['config_sha256']}"
        f"/attempt-4/{config['project_id']}/{p['summary']['job_id']}/")
    if arm!='cap_off':p['summary']['signal_runtime_access']['claim_key']=p['prefix']+'signal-packet-access.json'
    fixture.fixture.rebuild(p);fixture.rebind_api(p)
    files,raw=build(sources,p,original);report=json.loads(raw)
    assert p['raws'][2]==config_raw
    assert p['binding']['rendered_source_closure_sha256']==parent_report['rendered_source_closure_sha256']
    assert max(map(len,files.values()))<=60000
    assert report['parent_binding_sha256']==hashlib.sha256(r._wire(p['binding'])).hexdigest()
    for name,body in files.items():compile(ast.parse(body),name,'exec')
    print('SYNTHETIC_RUNTIME_BYTES',arm,len(files['main.py']),len(files[r.HELPER]),report['generated_main_docstrings_removed'])
