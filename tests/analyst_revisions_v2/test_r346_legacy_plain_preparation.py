"""Synthetic guard/publication/deadline tests; no operational DATA read."""
import ast
import copy
import io
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import prepare_arv2_r346_legacy_plain as m


def refused(code, operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    assert caught.value.args == (code,)


def args():
    return NS(expected_head='a'*40,caller_sha256='b'*64,plan_sha256='c'*64)


def public_root():
    return Path(__file__).resolve().parents[2]


def test_plan_preserves_all_old_pins_exactly_and_adds_only_bridge_and_A3_fact():
    root=public_root()
    raw=(root/'scripts/arv2_r346_legacy_plain_plan.json').read_bytes()
    plan=m.loads(raw,m.MAX_PLAN)
    old_raw=(root/'scripts/arv2_r345_legacy_six_plan_v3.json').read_bytes()
    old=m.loads(old_raw,m.MAX_PLAN)
    assert m.pin(old_raw)==m.PARENT_PLAN_PIN==plan['parent_plan_pin']
    assert len(old['source_pins'])==168 and len(plan['source_pins'])==170
    assert plan['source_pins']=={**old['source_pins'],**m.ADDITIONAL_PINS}
    for key in ('private_pin','source_summary','preparation_binding'):
        assert plan[key]==old[key]
    for relative,expected in m.ADDITIONAL_PINS.items():
        assert m.pin((root/relative).read_bytes())==expected
    assert plan['private_pin']==m.DATA_PIN


def test_current_attempt_state_uses_actual_pinned_A3_fact_not_old_B_zero_counter():
    raw=(public_root()/m.A3_PATH).read_bytes()
    assert m.pin(raw)==m.ADDITIONAL_PINS[m.A3_PATH]
    state=m.validate_a3_fact(m.loads(raw,m.MAX_OUTPUT,lf=True))
    assert state['attempts_consumed']==state['maximum_attempts']==3
    assert state['A4_permitted'] is state['attempt_reset'] is False
    inventory=m.attempt_state(state)
    assert len(inventory['other_candidates'])==6
    assert all(row['attempts_consumed']==0 and row['status']=='uninvoked_no_submission_authority'
        for row in inventory['other_candidates'])
    assert inventory['new_candidate_created'] is inventory['attempt_budget_reset'] is False


@pytest.mark.parametrize('fault',['exit','bool_exit','claim','project','backtest','compile','binding','stage'])
def test_mutated_failure_proof_does_not_reset_or_reassign_attempts(fault):
    value=m.loads((public_root()/m.A3_PATH).read_bytes(),m.MAX_OUTPUT,lf=True)
    if fault=='exit':value['observation']['actual_exit']=0
    elif fault=='bool_exit':value['observation']['actual_exit']=True
    elif fault=='claim':value['failure']['claim_state']='unallocated'
    elif fault=='project':value['failure']['evidence']['allocated_identities']['project_id']=111
    elif fault=='backtest':value['failure']['evidence']['allocated_identities']['backtest_id']='unknown-job'
    elif fault=='compile':value['failure']['evidence']['allocated_identities']['compile_id']='unknown-compile'
    elif fault=='binding':value['binding']['caller_sha256']='d'*64
    else:value['failure']['stage']='launched'
    refused('plan',lambda:m.validate_a3_fact(value))


@pytest.mark.parametrize('fail', [None,'B_exit','source_exit','store_exit'])
def test_two_complete_computations_and_both_normal_returns_precede_publication(monkeypatch,fail):
    events,written,active=[],[],{'B':False,'source':False}
    objects=tuple((name,b'{"synthetic":true}\n') for name in m.OBJECT_NAMES)
    first=(objects,b'{"synthetic_source_proposal":true}',b'{"synthetic_summary":true}')
    class Store:
        def __init__(self,*args):pass
        def __enter__(self):events.append('exclusive-control');return self
        def __exit__(self,*args):
            events.append('store-close')
            if fail=='store_exit':raise m.Refused('close')
        def write(self,name,raw):
            if name!='claim.json':
                assert active=={'B':False,'source':False}
            events.append(name);written.append((name,bytes(raw)));return m.pin(raw)
        def verify(self):events.append('store-verify')
    class B:
        def __init__(self,**kwargs):assert kwargs['expected_pin']==m.DATA_PIN
        def __enter__(self):
            active['B']=True;events.append('B-enter');return NS(value='synthetic-immutable-submission')
        def __exit__(self,*args):
            active['B']=False;events.append('B-normal-return')
            if fail=='B_exit':raise m.Refused('data')
    class Sources:
        security=None
        consumer=NS(FreshSubmission=B,Refused=type('BRefused',(ValueError,),{}),FINITE=())
        bridge=NS(Refused=type('BridgeRefused',(ValueError,),{}))
        plan={'source_summary':{},'preparation_binding':{}}
        def __init__(self,*args):pass
        def __enter__(self):active['source']=True;events.append('sources-enter');return self
        def __exit__(self,*args):
            active['source']=False;events.append('sources-normal-return')
            if fail=='source_exit':raise m.Refused('source_changed')
        def verify(self):events.append('sources-verify')
    def compute(*args):
        assert active=={'B':True,'source':True};events.append('compute');return first
    monkeypatch.setattr(m,'preflight',lambda *args:{'synthetic_binding':True})
    monkeypatch.setattr(m,'Sources',Sources);monkeypatch.setattr(m,'Store',Store);monkeypatch.setattr(m,'compute',compute)
    if fail is None:
        output=m.run(args())
        assert output['report']['source_guard_returned'] is output['report']['B_DATA_guard_returned'] is True
        assert output['report_pin']==m.pin(written[-1][1])
    else:
        with pytest.raises(m.Refused):m.run(args())
    assert events.index('claim.json')<events.index('B-enter')
    assert events.count('compute')==2
    if fail in ('B_exit','source_exit'):
        assert [name for name,_ in written]==['claim.json']
    else:
        assert [name for name,_ in written]==['claim.json',*m.OBJECT_NAMES,'source-proposal.json','report.json']
        assert events.index('sources-normal-return')<events.index(m.OBJECT_NAMES[0])
        assert events.index('B-normal-return')<events.index(m.OBJECT_NAMES[0])


@pytest.mark.parametrize('changed',['payload','proposal','summary'])
def test_comparison_uses_every_detached_byte_not_just_reported_summaries(monkeypatch,changed):
    written,calls=[],[]
    objects=tuple((name,b'original') for name in m.OBJECT_NAMES)
    first=(objects,b'{"proposal":1}',b'{"summary":1}')
    if changed=='payload':second=(((objects[0][0],b'changed'),*objects[1:]),first[1],first[2])
    elif changed=='proposal':second=(first[0],b'{"proposal":2}',first[2])
    else:second=(first[0],first[1],b'{"summary":2}')
    class Context:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def verify(self):pass
        def write(self,name,raw):written.append(name);return m.pin(raw)
    class B(Context):
        value=None
    class Sources(Context):
        security=None;plan={'source_summary':{},'preparation_binding':{}}
        consumer=NS(FreshSubmission=B,Refused=type('BRefused',(ValueError,),{}),FINITE=())
        bridge=NS(Refused=type('BridgeRefused',(ValueError,),{}))
    def compute(*args):
        calls.append(True);return first if len(calls)==1 else second
    monkeypatch.setattr(m,'preflight',lambda *args:{})
    monkeypatch.setattr(m,'Sources',Sources);monkeypatch.setattr(m,'Store',Context);monkeypatch.setattr(m,'compute',compute)
    refused('agreement',lambda:m.run(args()))
    assert len(calls)==2 and written==['claim.json']


def test_top_level_actual_failure_exits_two_with_finite_output_even_after_complete_files():
    tree=ast.parse(Path(m.__file__).read_bytes())
    top=tree.body[-1]
    assert isinstance(top,ast.If)
    target=io.BytesIO()
    class Hostile(Exception):
        def __str__(self):raise AssertionError('never format raw exception')
    def late_failure():raise Hostile('PRIVATE-RAW-TEXT')
    namespace={'__name__':'__main__','main':late_failure,'canonical':m.canonical,'require':m.require,
        'MAX_OUTPUT':m.MAX_OUTPUT,'sys':NS(stdout=NS(buffer=target)),'SCHEMA':m.SCHEMA,
        'STAGE':'publication','CLAIM_STATE':'consumed','finite':m.finite,'DEPENDENCY_FAILURE':None,'FLAGS':m.FLAGS}
    with pytest.raises(SystemExit) as caught:
        exec(compile(ast.Module(body=[top],type_ignores=[]),'<synthetic-main>','exec'),namespace)
    assert caught.value.code==2
    value=m.loads(target.getvalue().rstrip(b'\n'),m.MAX_OUTPUT)
    assert value['failure_code']=='unknown' and value['stage']=='publication'
    assert 'PRIVATE-RAW-TEXT' not in target.getvalue().decode()


class Security:
    @staticmethod
    def snapshot(fd):return ('synthetic-native-empty',os.fstat(fd).st_uid)


@pytest.fixture
def location(tmp_path,monkeypatch):
    root=tmp_path/'synthetic-repository';root.mkdir(mode=0o755)
    (root/'artifacts').mkdir(mode=0o700)
    monkeypatch.setattr(m,'ROOT',root)
    monkeypatch.setattr(m,'CONTROL',root/'artifacts'/'plain-preparation'/'ONE')
    monkeypatch.setattr(m,'CLAIM_STATE','unallocated')
    return m.CONTROL


def test_real_store_exclusive_nine_files_original_FDs_private_modes_and_no_cleanup(location):
    with m.Store(Security) as store:
        for name in ('claim.json',*m.OBJECT_NAMES,'source-proposal.json','report.json'):
            store.write(name,b'{"synthetic":true}\n')
        assert m.CLAIM_STATE=='consumed' and len(store.leaves)==9
        store.verify()
        assert all(os.fstat(row[1]).st_mode&0o777==0o600 for row in store.leaves)
        assert len({row[1] for row in store.leaves})==9
    assert set(item.name for item in location.iterdir())==m.NORMAL_FILES
    refused('claim_spent',lambda:m.Store(Security).__enter__())
    assert len(list(location.iterdir()))==9


def test_store_rejects_tenth_file_or_named_data_swap_without_repair(location):
    store=m.Store(Security).__enter__()
    try:
        store.write('claim.json',b'{}')
        refused('output',lambda:store.write('failure.json',b'{}'))
        path=location/'claim.json';path.rename(location/'retained-synthetic-original')
        path.write_bytes(b'{}');path.chmod(0o600)
        refused('control',store.verify)
    finally:store.close()
    assert (location/'retained-synthetic-original').read_bytes()==b'{}'


def test_store_close_attempts_every_owned_descriptor_after_one_failure(location,monkeypatch):
    store=m.Store(Security).__enter__()
    store.write('claim.json',b'{}')
    store.write(m.OBJECT_NAMES[0],b'{}')
    owned=[row[1] for row in store.leaves]+[row[0] for row in reversed(store.chain)]
    failed_fd=owned[0];real_close=os.close;calls=[]
    def failing(fd):
        calls.append(fd)
        if fd==failed_fd:raise OSError('synthetic-close-refusal')
        real_close(fd)
    monkeypatch.setattr(m.os,'close',failing)
    try:
        refused('close',store.close)
        assert calls==owned and store.fd is None and store.leaves==store.chain==[]
        for fd in owned[1:]:
            with pytest.raises(OSError):os.fstat(fd)
    finally:
        # This fixture simulated a close failure without releasing its first
        # descriptor. Release only that test-owned descriptor, never evidence.
        real_close(failed_fd)


def test_native_policy_denies_network_credentials_USB_and_all_old_private_controls():
    value=m.native_profile()
    assert '(deny network*)' in value and 'remote tcp' not in value
    assert str(m.DATA) in value and 'R343-20261105-A' not in value
    assert '/Volumes' in value and '/Library/Keychains' in value
    assert '(deny process-exec (literal "/usr/bin/security"))' in value
    assert not any(name in m.safe_env() for name in ('QC_USER_ID','QC_API_TOKEN','HOME'))
    assert len(m.NORMAL_FILES)==9 and 'failure.json' not in m.NORMAL_FILES


@pytest.mark.parametrize('key',list(m.FLAGS))
def test_preparation_profile_never_claims_contact_admission_attempt_reset_or_trading(key):
    assert m.profile_record()[key] is False


@pytest.mark.parametrize('left',[0,-1,181,float('nan'),float('inf')])
def test_deadline_cannot_be_infinite_elapsed_or_extended(monkeypatch,left):
    monkeypatch.setattr(m.time,'monotonic',lambda:100.0)
    refused('deadline',lambda:m.budget(100.0+left))


@pytest.fixture
def original_output():
    root=public_root();plan=m.loads((root/'scripts/arv2_r346_legacy_plain_plan.json').read_bytes(),m.MAX_PLAN)
    binding=m.binding(args())
    parent_vector=m.canonical([{key:row[key] for key in ('candidate_id','ar_percent','profile_pin','sources')}
        for row in plan['source_summary']['cells']])
    proof='95405d1b569d4bfeeb6c6d87fdb430f2fd27b8b7a31d6dcde7f82276d9903cd1'
    activation={'schema':'arv2-newrule-plain-upload-object-v1','role':'activation_manifest','ordinal':0,
        'object_store_key':'arv2/newrule-plain-v1/'+proof[:24]+'/transport-manifest.json',
        'relative_path':'transport-manifest.json','byte_count':5901,
        'content_sha256':'ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b',
        'record_count':1,'compression':'identity','activation_manifest':True}
    objects=[{'relative_path':name,'byte_count':1,'sha256':'a'*64} for name in m.OBJECT_NAMES]
    objects[-1].update(byte_count=5901,sha256=activation['content_sha256'])
    bridge_flags=('operational_authority','fresh_private_input_authenticated','new_storage_admitted',
        'qc_source_policy_acceptance_proven','attempt_budget_reset','backtest_completed','point_in_time_proven',
        'formal_identity_admitted','formal_forward_ready','paper_or_live_ready')
    cells=[]
    for row in plan['source_summary']['cells']:
        files=copy.deepcopy(row['sources'])
        loader=next(item for item in files if item['project_path']=='accepted_risk_order_level_input_runtime.py')
        changed=['accepted_risk_order_level_input_runtime.py','main.py']
        cells.append({'schema':'arv2-r345-legacy-six-plain-buffer-bridge-v1',
            'candidate_id':row['candidate_id'],'ar_percent':row['ar_percent'],'prepared_only':True,
            'parent_vector_pin':m.pin(parent_vector),'unchanged_profile_pin':row['profile_pin'],
            'ancestral_source_package_sha256':'411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad',
            'source_lineage_sha256':'e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9',
            'actual_plain_package_sha256':'1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2',
            'actual_activation':{key:activation[key] for key in ('object_store_key','content_sha256','byte_count')},
            'parent_proof_sha256':proof,'changed_files':changed,
            'unchanged_files':[item['project_path'] for item in files if item['project_path'] not in changed],
            'input_exports_used':['collection_rows','load_accepted_risk_preliminary_package'],
            'source_mapping':{'accepted_risk_order_level_input_runtime.py':'newrule_plain_input_runtime.py'},
            'actual_loader_source_pin':{key:loader[key] for key in ('byte_count','sha256')},
            'selected_loader_source_pin':dict(m.ADDITIONAL_PINS[m.LOADER_PATH]),'source_files':files,
            'result_contract':'new_actual_plain_transport_META_plus_unchanged_ancestral_profile',
            **dict.fromkeys(bridge_flags,False)})
    a3=m.validate_a3_fact(m.loads((root/m.A3_PATH).read_bytes(),m.MAX_OUTPUT,lf=True))
    summary={'actual_plain_package_sha256':'1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2',
        'parent_proof_sha256':proof,'source_inventory_pin':{'byte_count':100,'sha256':'d'*64},
        'parent_source_vector_pin':m.pin(parent_vector),'actual_activation':activation,
        'object_files':objects,'cells':cells,'current_attempt_state':m.attempt_state(a3),**m.FLAGS}
    report={'schema':m.SCHEMA+'-result','binding':binding,'source_guard_returned':True,
        'B_DATA_guard_returned':True,'two_complete_buffers_equal':True,
        'qualification':'fresh_endpoint_buffers_only_not_formal_source_or_continuous_integrity_or_QC_acceptance',
        'source_proposal_pin':{'byte_count':1000,'sha256':'e'*64},'summary':summary,**m.FLAGS}
    return {'report':report,'report_pin':m.pin(m.canonical(report))},binding


def stdout_bytes(value):
    value['report_pin']=m.pin(m.canonical(value['report']))
    return m.canonical(value)+b'\n'


def test_original_stdout_and_observed_zero_exit_validate_metadata_only(original_output):
    value,binding=original_output
    answer=m.validate_original_stdout(stdout_bytes(value),actual_exit=0,expected_binding=binding)
    assert answer['original_stdout_validated'] is True and answer['report']==value['report']
    assert 'not_independent_private_file_authentication' in answer['qualification']


@pytest.mark.parametrize('change',['missing_LF','double_LF','trailing'])
def test_A3_fact_requires_exact_original_single_LF_format(change):
    raw=(public_root()/m.A3_PATH).read_bytes()
    assert raw.endswith(b'\n') and m.pin(raw)==m.ADDITIONAL_PINS[m.A3_PATH]
    if change=='missing_LF':raw=raw[:-1]
    elif change=='double_LF':raw+=b'\n'
    else:raw+=b'trailing'
    refused('plan',lambda:m.loads(raw,m.MAX_OUTPUT,lf=True))


@pytest.mark.parametrize('exit_code',[True,False,2,-1,None,'0'])
def test_report_alone_never_overrides_unknown_nonzero_or_bool_actual_exit(original_output,exit_code):
    value,binding=original_output
    refused('output',lambda:m.validate_original_stdout(stdout_bytes(value),actual_exit=exit_code,expected_binding=binding))


@pytest.mark.parametrize('key',list(m.FLAGS))
def test_rehashed_readiness_contact_or_attempt_reset_assertion_is_inadmissible(original_output,key):
    value,binding=original_output;value['report'][key]=True
    refused('output',lambda:m.validate_original_stdout(stdout_bytes(value),actual_exit=0,expected_binding=binding))


@pytest.mark.parametrize('fault',['binding','guard','proposal_bound','attempts','A4','objects','object_order',
    'activation','cells','cell_readiness','cell_mapping','extra','report_pin','trailing','duplicate','noncanonical'])
def test_original_output_closed_schema_and_attempt_metadata_refuse_forged_envelopes(original_output,fault):
    value,binding=original_output;report=value['report'];summary=report['summary']
    if fault=='binding':report['binding']['expected_head']='f'*40;binding={**binding,'expected_head':'a'*40}
    elif fault=='guard':report['B_DATA_guard_returned']=1
    elif fault=='proposal_bound':report['source_proposal_pin']['byte_count']=m.MAX_PROPOSAL+1
    elif fault=='attempts':summary['current_attempt_state']['R343-AR100']['attempts_consumed']=0
    elif fault=='A4':summary['current_attempt_state']['R343-AR100']['A4_permitted']=True
    elif fault=='objects':summary['object_files'].pop()
    elif fault=='object_order':summary['object_files'][0],summary['object_files'][1]=summary['object_files'][1],summary['object_files'][0]
    elif fault=='activation':summary['actual_activation']['compression']='gzip'
    elif fault=='cells':summary['cells'].pop()
    elif fault=='cell_readiness':summary['cells'][0]['attempt_budget_reset']=True
    elif fault=='cell_mapping':summary['cells'][0]['source_mapping']={'raw':'PRIVATE-TEXT'}
    elif fault=='extra':value['extra']=None
    raw=stdout_bytes(value)
    if fault=='report_pin':value['report_pin']['sha256']='0'*64;raw=m.canonical(value)+b'\n'
    elif fault=='trailing':raw+=b'\n'
    elif fault=='duplicate':raw=b'{"report":{},"report":{}}\n'
    elif fault=='noncanonical':raw=b' '+raw
    refused('output',lambda:m.validate_original_stdout(raw,actual_exit=0,expected_binding=binding))
