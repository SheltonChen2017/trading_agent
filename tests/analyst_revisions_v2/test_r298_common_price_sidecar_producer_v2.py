"""Synthetic AR publication/policy/failure tests; no production DATA or API."""
import copy
import errno
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from scripts import prepare_arv2_r298_common_price_sidecar_v2 as m


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    for name in ('QC_USER_ID','QC_API_TOKEN','SHARADAR_API_KEY','MASSIVE_API_KEY','POLYGON_API_KEY','EODHD_API_TOKEN','FMP_API_KEY'):
        monkeypatch.delenv(name,raising=False)


@pytest.fixture
def store_scope(monkeypatch,tmp_path):
    monkeypatch.setattr(m,'CONTROL',tmp_path/'parent'/'AR')
    monkeypatch.setattr(m,'_security',lambda fd:('synthetic-security',))
    monkeypatch.setattr(m,'MONTH_COUNT',2)
    def walk(path):
        chain=tuple((os.stat(Path(*path.parts[:index+1])).st_dev,os.stat(Path(*path.parts[:index+1])).st_ino)
            for index in range(1,len(path.parts)))
        return os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW),chain
    monkeypatch.setattr(m.admitted,'_storage_module',lambda:NS(_walk=walk))
    return m.CONTROL


def fails(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def test_literal_source_pins_and_public_AP_actual_chain_are_closed():
    selected=m.pins();assert len(selected)==198
    for name,pin in selected.items():assert m.sha((m.ROOT/name).read_bytes())==pin
    context=m.source_context()
    assert set(context)=={'fact','source_summary','authentication_summary'}
    for name in ('source_actual','provider_actual','authentication_actual'):assert context['fact'][name]['actual_exit']==0
    assert context['authentication_summary']['observed_price_rows']==5541040
    assert context['authentication_summary']['absent_expected_cells']==2654048
    assert m.profile_record()['minimum_free_disk_bytes']==1536*1024*1024


@pytest.mark.parametrize('mode',('produce','validate'))
def test_entire_native_contract_denies_network_keychain_and_unscoped_artifacts(mode):
    policy=m.native_profile(mode)
    assert '(deny network*)' in policy and '(deny process-exec (literal "/usr/bin/security"))' in policy
    assert '/Users/sheltonchen/Library/Keychains' in policy and '/Library/Keychains' in policy
    assert 'remote tcp' not in policy
    for role in ('plan','corpus','dispatch','captures'):
        assert (m.anchor.data_plan()[role]['relative_path'] in policy) is (mode=='produce')
    assert (str(m.worker.previous.PACKAGE) in policy) is (mode=='produce')


def test_spools_remain_private_until_normal_return_then_rotate_and_manifest_last(store_scope):
    with m.Store() as store:
        store.write('claim.json','claim',b'{}');store.initialize_spools()
        store.append('provisional-000.jsonl',b'[0,0,"1"]\n')
        store.append('provisional-001.jsonl',b'[0,1,"2"]\n')
        fails('phase',lambda:store.read_spool(0,time.monotonic()+20))
        fails('phase',lambda:store.manifest(b'{}'))
        store.source_normal_return()
        store.write('catalog-private.json','catalog',b'{}')
        for month in range(2):
            raw=store.read_spool(month,time.monotonic()+20)
            assert raw
            stored=store.consume_into_final(month,raw)
            assert stored==m.pin(raw)
            assert store.files['provisional-'+str(month).zfill(3)+'.jsonl']['fd'] is None
            assert (store_scope/('provisional-'+str(month).zfill(3)+'.jsonl')).exists()
        store.manifest(b'{"synthetic":true}')
        receipt=store.receipt()
        assert receipt['original_spools_consumed']==2 and receipt['final_original_descriptors_held']
        assert receipt['final_byte_count']==receipt['provisional_byte_count']
        assert sum(row['kind'] in ('spool','month') and row['fd'] is not None for row in store.files.values())==2
        fails('phase',lambda:store.append('month-000.jsonl',b'extra'))


@pytest.mark.parametrize('which',('monthly','provisional','final'))
def test_budgets_refuse_before_extra_bytes_no_drop_or_expansion(store_scope,monkeypatch,which):
    with m.Store() as store:
        store.write('claim.json','claim',b'{}');store.initialize_spools()
        if which=='monthly':monkeypatch.setattr(m,'MAX_MONTH',2)
        elif which=='provisional':monkeypatch.setattr(m,'MAX_PROVISIONAL',2)
        else:
            store.source_normal_return();monkeypatch.setattr(m,'MAX_FINAL',2)
            fails('output_bound',lambda:store.consume_into_final(0,b'large'))
            assert store.files['month-000.jsonl']['metadata'][6]==0
            return
        fails('output_bound',lambda:store.append('provisional-000.jsonl',b'large'))
        assert store.files['provisional-000.jsonl']['metadata'][6]==0


def test_spool_bytes_authenticated_before_consumption_and_no_reopen(store_scope):
    with m.Store() as store:
        store.write('claim.json','claim',b'{}');store.initialize_spools()
        store.append('provisional-000.jsonl',b'original')
        store.source_normal_return()
        fd=store.files['provisional-000.jsonl']['fd']
        os.pwrite(fd,b'changed!',0)
        with pytest.raises(m.Refused):store.read_spool(0,time.monotonic()+20)
        assert store.files['provisional-000.jsonl']['fd']==fd


def test_final_byte_readback_detects_corrupt_write_before_consuming_original_spool(store_scope,monkeypatch):
    with m.Store() as store:
        store.write('claim.json','claim',b'{}');store.initialize_spools();store.source_normal_return()
        original=m._write
        def corrupt(fd,raw):original(fd,b'X'*len(raw))
        monkeypatch.setattr(m,'_write',corrupt)
        fails('output_write',lambda:store.consume_into_final(0,b'original'))
        assert store.files['provisional-000.jsonl']['fd'] is not None
        assert not store.files['provisional-000.jsonl']['consumed']


def test_nontarget_drift_cannot_pass_full_source_normal_return_barrier(store_scope):
    with m.Store() as store:
        store.write('claim.json','claim',b'{}');store.initialize_spools()
        store.append('provisional-000.jsonl',b'original')
        os.pwrite(store.files['provisional-000.jsonl']['fd'],b'changed!',0)
        # Bounded append checks its exact target; the full boundary still
        # refuses every other changed original before final publication.
        store.append('provisional-001.jsonl',b'other')
        fails('output_changed',store.source_normal_return)
        assert not store.source_returned and not any(row['kind']=='month' for row in store.files.values())


def test_second_claim_preserves_all_retained_evidence(store_scope):
    with m.Store() as store:store.write('claim.json','claim',b'{}')
    fails('claim_spent',lambda:m.Store())
    assert (store_scope/'claim.json').read_bytes()==b'{}'


@pytest.mark.parametrize('kind',('soft','occupied','disk'))
def test_fd_and_full_output_disk_reserve_are_checked_without_limit_changes(monkeypatch,kind):
    monkeypatch.setattr(m.resource,'getrlimit',lambda resource:(64 if kind=='soft' else 128,128))
    def fcntl(fd,command):
        if fd<(20 if kind=='occupied' else 3):return 0
        raise OSError(errno.EBADF,'synthetic')
    monkeypatch.setattr(m.fcntl,'fcntl',fcntl)
    monkeypatch.setattr(m.os,'statvfs',lambda root:NS(f_bavail=1 if kind=='disk' else m.FREE_DISK_BYTES,f_frsize=1))
    fails('disk_budget' if kind=='disk' else 'descriptor_budget',m.budgets)
    assert 'setrlimit' not in Path(m.__file__).read_text()


def manifest():
    months=[];left=5541040
    for value in m._public_months():
        count=5644*len(value['session_indexes']);valid=min(count,left);left-=valid
        months.append({**value,'row_count':count,'valid_count':valid,'absent_count':count-valid,
            'byte_count':100+value['month_ordinal'],'sha256':m.sha(('synthetic-'+value['month']).encode())})
    assert left==0
    return {'schema':m.fmt.SCHEMA+'-manifest','catalog_pin':m.pin(b'synthetic catalog'),
        'AP_fact_sha256':m.fmt.AP_FACT_SHA256,'AP_authentication_sha256':m.fmt.AP_AUTH_SHA256,
        'binding_stream_sha256':m.fmt.BINDING_SHA256,'full_axis_sha256':m.fmt.FULL_AXIS_SHA256,
        'assignment_count':6159,'vendor_slot_count':5644,'session_count':1452,'months':months,
        'row_count':8195088,'valid_count':5541040,'absent_count':2654048,
        'total_shard_bytes':sum(row['byte_count'] for row in months),**m.fmt.FALSE_FLAGS}


def test_stdout_descriptor_has_only_counts_pins_public_months_no_assignment_or_price_payload():
    record=manifest();m.fmt.validate_manifest(record)
    descriptor=m._manifest_descriptor(record)
    assert m._descriptor_manifest(descriptor)==record
    raw=m.canonical(descriptor)
    assert b'ticker' not in raw and b'security_id' not in raw and b'assignments' not in raw
    assert b'session_indexes' not in raw and len(descriptor['months'])==71


@pytest.mark.parametrize('change',('extra','month','count','pin','float'))
def test_stdout_descriptor_rejects_payload_smuggling_or_changed_output_pin(change):
    value=m._manifest_descriptor(manifest())
    if change=='extra':value['assignments']=[{'private':'not allowed'}]
    elif change=='month':value['months'][0]['month']='2021-01'
    elif change=='count':value['months'][0]['valid_count']-=1
    elif change=='float':value['assignment_count']=6159.0
    else:value['sha256']='e'*64
    with pytest.raises((m.Refused,m.fmt.Refused)):m._descriptor_manifest(value)


def result():
    context=m.source_context();record=manifest();descriptor=m._manifest_descriptor(record)
    receipt={'schema':m.source_guard.SCHEMA+'-receipt',
        'profile_sha256':m.sha(m.source_guard.canonical(m.source_guard.profile_record(context['fact']['data_plan']))),
        'file_pins':context['fact']['data_plan'],'whole_hashes_checked':4,'range_count':1256,
        'corpus_extent':179185028,'source_endpoint_sha256':'a'*64,'requires_normal_return_before_use':True,
        'continuous_or_historical_integrity_proven':False,'source_or_price_admission_granted':False}
    output={'schema':m.SCHEMA+'-output-receipt','catalog_pin':record['catalog_pin'],
        'manifest_pin':m.pin(m.canonical(record)),
        'month_pins':[{'byte_count':row['byte_count'],'sha256':row['sha256']} for row in record['months']],
        'provisional_byte_count':100,'final_byte_count':record['total_shard_bytes'],'original_spools_consumed':71,
        'provisional_pin_stream_sha256':'b'*64,'final_original_descriptors_held':True,
        'closed_spool_security_scope_ended_after_authenticated_consumption':True}
    complete={'schema':m.codec.SCHEMA+'-complete','manifest_pin':output['manifest_pin'],'catalog_pin':output['catalog_pin'],
        'month_count':71,**{key:record[key] for key in ('row_count','valid_count','absent_count','total_shard_bytes')},**m.fmt.FALSE_FLAGS}
    return {'schema':m.SCHEMA,'input_binding':context['source_summary']['input_binding'],'source_guard_receipt':receipt,
        'codec_summary':complete,'manifest_descriptor':descriptor,'output_receipt':output,
        'source_guards_normal_return':True,'genuine_input_unchanged':True,'AP_fact_sha256':m.fmt.AP_FACT_SHA256,
        'AP_source_sha256':m.fmt.AP_SOURCE_SHA256,'AP_authentication_sha256':m.fmt.AP_AUTH_SHA256,
        'post_checks_complete':True,**m.FALSE_FLAGS}


@pytest.fixture
def args():return NS(operation='produce',expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def envelope(value,args):
    outcome={'result':value,'report':m.pin(m.canonical({**m.binding(args),'result':value}))}
    return m.canonical({'binding':m.binding(args),'outcome':outcome})+b'\n'


def test_exact_closed_result_joins_source_and_output_metadata_and_actual_parent_exit(args):
    value=result();m.validate_result(value,args)
    raw=envelope(value,args);assert m.validate_output(raw,0,args)['outcome']['result']==value
    for exit_code in (None,True,2):fails('output',lambda:m.validate_output(raw,exit_code,args))


@pytest.mark.parametrize('field',('source','normal','catalog','month','manifest','private','flags'))
def test_closed_result_rejects_source_or_output_drift_even_if_report_pin_recomputed(args,field):
    value=result()
    if field=='source':value['source_guard_receipt']['file_pins']['corpus']['sha256']='e'*64
    elif field=='normal':value['source_guards_normal_return']=False
    elif field=='catalog':value['output_receipt']['catalog_pin']['sha256']='e'*64
    elif field=='month':value['output_receipt']['month_pins'][0]['sha256']='e'*64
    elif field=='manifest':value['output_receipt']['manifest_pin']['sha256']='e'*64
    elif field=='private':value['input_binding']['private_rows']=[{'not':'allowed'}]
    else:value['QC_transfer_granted']=True
    with pytest.raises((m.Refused,m.source_guard.Refused,m.fmt.Refused)):m.validate_output(envelope(value,args),0,args)


def test_original_full_binding_and_real_record_axis_bridge_before_corpus_semantics():
    rows=[{'security_id':'synthetic-'+str(i),'row_sha256':m.sha(str(i).encode())} for i in range(6151)]
    axis=m.worker.previous.october._sessions();evaluator=m.worker.previous.identity.evaluator
    selected={'session_axis':[{'schema':evaluator.SESSION_SCHEMA,'session_index':i,'session':day} for i,day in enumerate(axis)]}
    plan={'assignments':[{'binding_ordinal':i,'security_id':row['security_id'],
        'whole_binding_sha256':m.ap.prices.digest(row),'semantic_binding_sha256':row['row_sha256']} for i,row in enumerate(rows)]
        +[{} for _ in range(8)],'price_sessions':m.ap.prices._axis(axis)}
    raw=m.canonical(plan);public={'synthetic':True};context={'source_summary':{'plan_pin':m.pin(raw),'input_binding':public}}
    assert m._bind_original(raw,rows,public,selected,context)==plan
    plan['assignments'][42]['whole_binding_sha256']='e'*64;raw=m.canonical(plan);context['source_summary']['plan_pin']=m.pin(raw)
    fails('input',lambda:m._bind_original(raw,rows,public,selected,context))


def test_new_builder_never_calls_credential_or_provider_or_old_control_operations():
    code=Path(m.__file__).read_text()
    assert '.load_key(' not in code and '.fetch(' not in code and 'ap.run(' not in code
    assert 'read_all_once(' not in code and 'setrlimit(' not in code and 'os.unlink(' not in code
    assert 'source_guard.PriceCorpusGuard' in code and 'guard.authenticate_all()' in code
    assert code.index('guard.authenticate_all()')<code.index('guard.read_small(role)')


@pytest.mark.parametrize('failure',(None,'range','input_end','guard_return'))
def test_full_1256_stage_orchestration_cannot_finalize_before_all_source_guards_return(monkeypatch,failure):
    events=[];active={'source':False};plan_raw=b'{"synthetic":true}'
    context={'fact':{'data_plan':{'corpus':{'byte_count':1256}}},
        'source_summary':{'plan_pin':m.pin(plan_raw),'plan_summary':{'synthetic':True}}}
    monkeypatch.setattr(m,'MONTH_COUNT',2)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    monkeypatch.setattr(m.worker,'_load_plain',lambda deadline:events.append('genuine-load') or 'plain')
    monkeypatch.setattr(m.worker,'_catalog',lambda *args:('initial','original',{},[],{'synthetic-public':True}))
    def unchanged(*args):
        events.append('input-end')
        if failure=='input_end':raise m.Refused('input')
    monkeypatch.setattr(m.worker,'_catalog_unchanged',unchanged)
    monkeypatch.setattr(m,'_bind_original',lambda *args:events.append('all-bindings-and-axis') or {})
    monkeypatch.setattr(m.ap,'_request',lambda plan,pin,ordinal:NS(sha256=m.sha(str(ordinal).encode())))
    dispatches=[];captures=[]
    for index,ordinal in enumerate(m.ap.ORDER):
        row={'dispatch_ordinal':index,'plan_ordinal':ordinal,'request_sha256':m.sha(str(ordinal).encode())}
        dispatches.append(row)
        captures.append({**row,'offset':index,'body_pin':m.pin(b'X'),'HTTP_status':200})
    class Guard:
        def __init__(self,*args,**kwargs):self.authenticated=False;self.count=0
        def __enter__(self):active['source']=True;events.append('guard-enter');return self
        def authenticate_all(self):self.authenticated=True;events.append('all-four-whole-hashes')
        def read_small(self,role):
            assert self.authenticated
            return plan_raw if role=='plan' else b''.join(m.canonical(row)+b'\n' for row in (dispatches if role=='dispatch' else captures))
        def read_range(self,index,offset,length,expected):
            assert active['source'] and index==self.count and offset==index and length==1 and expected==m.sha(b'X')
            if failure=='range' and index==11:raise m.source_guard.Refused('byte_pin')
            self.count+=1;return b'X'
        def verify(self):assert self.count==1256
        def receipt(self):return {'synthetic-source-receipt':True}
        def __exit__(self,kind,*args):
            active['source']=False;events.append('guard-normal' if kind is None else 'guard-exception')
            if failure=='guard_return' and kind is None:raise m.source_guard.Refused('changed')
    monkeypatch.setattr(m.source_guard,'PriceCorpusGuard',Guard)
    class Layout:
        def catalog_raw(self):return b'{"synthetic-catalog":true}'
        def catalog_pin(self):return m.pin(self.catalog_raw())
        def catalog_record(self):return {'synthetic-catalog':True}
    layout=Layout()
    monkeypatch.setattr(m.codec,'make_layout',lambda *args,**kwargs:({},layout))
    seen=[]
    def split(layout,ordinal,raw,**kwargs):
        assert active['source'] and raw==b'X';seen.append(ordinal);return ((ordinal%2,b'fragment\n'),)
    monkeypatch.setattr(m.codec,'split_response',split)
    def final(layout,index,fragments,**kwargs):
        assert not active['source'] and len(seen)==1256
        events.append('final-'+str(index));raw=('synthetic-final-'+str(index)).encode()
        return {'month_ordinal':index,**m.pin(raw)},NS(bytes=lambda:raw)
    monkeypatch.setattr(m.codec,'finalize_month',final)
    manifest_raw=b'{"synthetic-manifest":true}'
    monkeypatch.setattr(m.codec,'finish_manifest',lambda *args,**kwargs:
        ({'manifest_pin':m.pin(manifest_raw)},NS(bytes=lambda:manifest_raw)))
    monkeypatch.setattr(m.fmt,'validate_catalog',lambda value:value)
    monkeypatch.setattr(m.fmt,'validate_manifest',lambda value:value)
    monkeypatch.setattr(m,'_manifest_descriptor',lambda value:{'synthetic-descriptor':True})
    class Store:
        def initialize_spools(self):assert active['source'];events.append('spools-created')
        def append(self,name,raw):assert active['source'] and raw==b'fragment\n'
        def source_normal_return(self):assert not active['source'];events.append('output-normal-boundary')
        def write(self,name,kind,raw):assert not active['source'];return m.pin(raw)
        def read_spool(self,index,deadline):assert not active['source'];return b'fragment\n'
        def consume_into_final(self,index,raw):assert not active['source'];return m.pin(raw)
        def manifest(self,raw):assert events[-2:]==['final-0','final-1'];events.append('manifest-last');return m.pin(raw)
        def receipt(self):return {'synthetic-output-receipt':True}
    if failure:
        with pytest.raises((m.Refused,m.source_guard.Refused)):m.construct(Store(),context,time.monotonic()+20)
        assert 'output-normal-boundary' not in events and not any(event.startswith('final-') for event in events)
    else:
        value=m.construct(Store(),context,time.monotonic()+20)
        assert seen==list(m.ap.ORDER) and len(seen)==1256
        assert events.index('all-four-whole-hashes')<events.index('all-bindings-and-axis')
        assert events.index('guard-normal')<events.index('output-normal-boundary')<events.index('final-0')
        assert events[-1]=='manifest-last' and value['source_guards_normal_return']


def test_budget_failure_occurs_before_claim_or_private_constructor(monkeypatch,args):
    called=[]
    monkeypatch.setattr(m,'budgets',lambda:(_ for _ in ()).throw(m.Refused('disk_budget')))
    monkeypatch.setattr(m,'Store',lambda:called.append('claim'))
    fails('disk_budget',lambda:m.run(args,time.monotonic()+20))
    assert called==[]


def test_outside_body_failure_uses_supplied_profile_hash_and_honest_unknown_allocation(monkeypatch,args):
    monkeypatch.setattr(m,'profile_record',lambda:(_ for _ in ()).throw(m.Refused('source_binding')))
    value=m.outside_body_failure(args,m.Refused('source_binding'));raw=m.canonical(value)+b'\n'
    assert m.validate_output(raw,2,args)['outside_body_failure']=={
        'operation':'produce','code':'source_binding','allocation_unknown':True}
    assert 'preflight_failure' not in value


def test_only_exact_parent_literal_is_added_to_producer_policy_and_never_sibling_subtree():
    from scripts import prepare_arv2_r298_common_price_sidecar as old
    addition=f'(require-not (literal "{m.CONTROL.parent}"))'
    value=m.native_profile('produce')
    assert value.count(addition)==2  # one write path, one exact artifact-read path
    assert f'(subpath "{m.CONTROL.parent}")' not in value
    assert value.replace(addition,'').replace('R326-20261027-AR','R326-20261027-AQ')==old.native_profile('produce')
    assert m.native_profile('validate')==old.native_profile('validate')
    assert '(deny network*)' in value and '(deny process-exec (literal "/usr/bin/security"))' in value
    assert '/Library/Keychains' in value and '/Users/sheltonchen/Library/Keychains' in value
    assert 'R326-20261027-AQ' not in value


def test_native_policy_contract_requires_independent_top_level_children_not_nested_outer():
    profile=m.profile_record()
    assert profile['outer_orchestration']=='ordinary_metadata_only_outer_separate_independent_native_producer_and_validator'
    assert profile['sole_file_permission_delta']=='write_exact_literal_CONTROL_parent_no_parent_subtree_read_or_write'
    # This is a static orchestration contract check. Root's independently
    # launched, no-DATA OS smoke is separate evidence; pytest's own sandbox is
    # never relaxed to make a nested different policy appear successful.
    assert 'subprocess' not in Path(m.__file__).read_text()


def test_frozen_AQ_failure_is_preserved_as_parent2_validator71_not_accepted_reader_or_data():
    value=m.failure_context()
    assert value['AQ_failure_fact_sha256']==m.AQ_FAILURE_FACT_SHA256
    assert value['producer_actual_exit']==2 and value['validator_actual_exit']==71
    assert value['attempt_spent'] is True
    assert all(value[key] is False for key in ('native_reader_accepted','allocation_and_private_read_stage_known',
        'old_control_read_granted','new_operation_granted','price_input_admitted'))
    assert m.NEW_PINS['scripts/prepare_arv2_r298_common_price_sidecar.py'].startswith('a454259')
    assert m.NEW_PINS['scripts/arv2_r298_aq_failure_binding.py'].startswith('923b0e')


@pytest.mark.parametrize('field',('parent_exit','validator_exit','reader','known_stage','spent','grant'))
def test_failed_history_cannot_be_upgraded_or_reused_even_with_recomputed_fact_digest(monkeypatch,field):
    fact=m.failure_anchor.observed_fact()
    if field=='parent_exit':fact['producer']['actual_exit']=0
    elif field=='validator_exit':fact['validator']['actual_exit']=0
    elif field=='reader':fact['finite_stdout_reconstruction']['native_reader_accepted']=True
    elif field=='known_stage':fact['allocation_and_private_read_stage_known']=True
    elif field=='spent':fact['attempt_spent']=False
    else:fact['new_operation_granted']=True
    monkeypatch.setattr(m.failure_anchor,'observed_fact',lambda:fact)
    monkeypatch.setattr(m,'AQ_FAILURE_FACT_SHA256',m.fmt.digest(fact))
    fails('source_binding',m.failure_context)


@pytest.mark.parametrize('change',('exit','operation','code','allocation','extra'))
def test_safe_outside_body_failure_is_closed_and_never_success(args,change):
    value=m.outside_body_failure(args,PermissionError(errno.EPERM,'synthetic private text'))
    assert 'synthetic private text' not in m.canonical(value).decode()
    exit_code=2
    if change=='exit':exit_code=0
    elif change=='operation':value['outside_body_failure']['operation']='validate'
    elif change=='code':value['outside_body_failure']['code']='raw exception not allowed'
    elif change=='allocation':value['outside_body_failure']['allocation_unknown']=False
    else:value['outside_body_failure']['stage']='not established'
    fails('output',lambda:m.validate_output(m.canonical(value)+b'\n',exit_code,args))


def test_old_misleading_AQ_preflight_only_shape_not_accepted_by_new_AR_validator(args):
    raw=m.canonical({'binding':m.binding(args),'preflight_failure':'os_error'})+b'\n'
    fails('output',lambda:m.validate_output(raw,2,args))


def test_outermost_exception_boundary_calls_safe_failure_constructor_without_old_stage_claim():
    import ast
    tree=ast.parse(Path(m.__file__).read_bytes())
    main=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='main')
    calls=[node for node in ast.walk(main) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
        and node.func.id=='outside_body_failure']
    assert len(calls)==1
    assert not any(isinstance(node,ast.Constant) and node.value=='preflight_failure' for node in ast.walk(main))


def test_AR_allocation_constructor_creates_only_its_own_new_family_and_leaf_under_test_root(store_scope):
    assert not store_scope.parent.exists()
    with m.Store() as store:
        store.write('claim.json','claim',b'{}')
        assert store_scope.parent.is_dir() and store_scope.is_dir()
        assert sorted(path.name for path in store_scope.iterdir())==['claim.json']
    # The native production-policy permission proof is Root's separate tiny
    # top-level smoke, not this fixture under pytest's independent native fence.


def test_AR_operational_bodies_unchanged_except_declared_scope_policy_and_error_boundary():
    import ast
    old_path=m.ROOT/'scripts/prepare_arv2_r298_common_price_sidecar.py'
    assert m.sha(old_path.read_bytes())=='a454259816eb5ad97aa3d4143d65abc8c96f7c77331071c864f696f396c8c056'
    original=ast.parse(old_path.read_bytes());current=ast.parse(Path(m.__file__).read_bytes())
    before={node.name:node for node in original.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
    after={node.name:node for node in current.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
    assert set(after)==set(before)|{'failure_context','outside_body_failure'}
    class Normalize(ast.NodeTransformer):
        def visit_Expr(self,node):
            if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='failure_context':return None
            return self.generic_visit(node)
    for name,node in before.items():
        if name in ('profile_record','native_profile','validate_output','main'):continue
        assert ast.dump(Normalize().visit(copy.deepcopy(after[name])),include_attributes=False)==ast.dump(node,include_attributes=False),name
    assert m.SCHEMA=='arv2-r298-offline-common-price-sidecar-ar-v2'
    assert m.CONTROL.name=='R326-20261027-AR'
    assert m.source_context()['fact']['binding']['caller_sha256']==m.AP_SHA256
