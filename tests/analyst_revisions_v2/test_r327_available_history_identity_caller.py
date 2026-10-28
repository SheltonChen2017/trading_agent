"""Synthetic caller/guard integration; no retained DATA or genuine source read."""
import copy
import inspect
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import inspect_arv2_r327_available_history_identity as m
assert 'assistant.dispatch_fence' not in sys.modules


def args():return NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def fail(code,call):
    with pytest.raises(m.Refused) as error:call()
    assert m.finite(error.value)==code


def input_binding():return {'synthetic_input_sha256':'a'*64}


def private_raw():return m.canonical({'schema':'synthetic-private','rows':[{'ordinal':0}]})


def summary():return {'schema':'synthetic-summary','private_payload_pin':m.pin(private_raw()),'all_originals_checked':True}


def receipt():
    return {'schema':m.guard_module.SCHEMA+'-receipt',
      'profile_sha256':m.sha(m.canonical(m.guard_module.profile_record(m.DATA_PLAN))),
      'files':{role:{**row,'current_metadata_sha256':'d'*64,'current_security_sha256':'e'*64}
        for role,row in m.DATA_PLAN.items()},'fresh_current_security_authenticated':True,
      'fixed_bytes_authenticated':True,'requires_normal_return_before_use':True,
      'historical_continuity_proven':False,'continuous_integrity_proven':False}


def prepared():
    return {'identity_summary':summary(),'genuine_input_binding':input_binding(),'source_receipt':receipt(),
      'all_four_DATA_guard_normal_return':True,'genuine_input_checks_complete':True}


def result():
    return {'schema':m.SCHEMA,**prepared(),'private_pin':summary()['private_payload_pin'],
      'source_context_sha256':m.sha(m.canonical(m.source_context())),'H_fact_sha256':m.H_FACT_SHA256,
      'post_checks_complete':True,**m.FALSE_FLAGS}


@pytest.fixture
def scope(monkeypatch,tmp_path):
    root=tmp_path/'root';root.mkdir(mode=0o755);root.chmod(0o755)
    for name in ('artifacts','artifacts/analyst_revisions_v2','artifacts/analyst_revisions_v2/source','.pytest_cache'):
        (root/name).mkdir(mode=0o700)
    plan={};raws={};paths={}
    for role in ('hierarchy','catalog','stocks_metadata','funds_metadata'):
        raw=m.canonical({'synthetic_source':role});path=root/'artifacts/analyst_revisions_v2/source'/role
        path.write_bytes(raw);path.chmod(0o600);raws[role]=raw;paths[role]=path
        plan[role]={'relative_path':path.relative_to(root).as_posix(),**m.pin(raw)}
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m.guard_module,'ROOT',root);monkeypatch.chdir(root)
    monkeypatch.setattr(m,'CONTROL',root/'output'/'I');monkeypatch.setattr(m,'DATA_PLAN',plan)
    monkeypatch.setattr(m,'source_context',lambda:{'input_binding':input_binding(),'synthetic':True})
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    monkeypatch.setattr(m.previous.ar,'_credential_free',lambda:None)
    monkeypatch.setattr(m,'preflight',lambda *args:None)
    monkeypatch.setattr(m,'MIN_FREE_DISK',0)
    monkeypatch.setattr(m.diagnosis,'validate_summary',lambda value:value)
    monkeypatch.setattr(m.diagnosis,'validate_private_record',lambda value,**kwargs:value)
    class Private:
        _raw=private_raw();byte_count=len(_raw);sha256=m.sha(_raw);summary_sha256=m.sha(m.canonical(summary()))
        def private_record(self):return m.parse(self._raw)
    monkeypatch.setattr(m.diagnosis,'PrivateIdentityDemand',Private)
    seen=[]
    def prepare(*raws,**kwargs):
        seen.append(('prepare',raws,kwargs));return summary(),Private()
    monkeypatch.setattr(m.diagnosis,'prepare',prepare)
    selected={'evaluator_manifest':[{'synthetic_manifest':True}],'session_axis':['synthetic'],
      'memberships':[{'synthetic_membership':True}],'runtime_symbol_bindings':[{'synthetic_binding':True}]}
    record={'synthetic_record':True};initial={'synthetic_fingerprint':True}
    class Plain:
        def to_record(self):return copy.deepcopy(record)
    plain=Plain();axis=tuple('synthetic-session-'+str(i) for i in range(3466));catalog=[{'ordinal':i} for i in range(6151)]
    def load(deadline):seen.append(('load',));return plain
    monkeypatch.setattr(m.worker,'_load_plain',load)
    monkeypatch.setattr(m.membership,'_authenticated',lambda value,deadline:(initial,record,selected,catalog,input_binding(),axis,()))
    monkeypatch.setattr(m.transport,'require_plain_transport',lambda value:value)
    monkeypatch.setattr(m.transport,'_fingerprint',lambda value:copy.deepcopy(initial))
    monkeypatch.setattr(m.membership,'_streams',lambda *args:copy.deepcopy(selected))
    monkeypatch.setattr(m.period,'FULL_AXIS_SHA256',m.sha(m.canonical(list(axis))))
    monkeypatch.setattr(m.period,'make_period',lambda value:{'synthetic_period':True})
    def walk(path):
        chain=tuple((os.stat(Path(*path.parts[:i+1])).st_dev,os.stat(Path(*path.parts[:i+1])).st_ino) for i in range(1,len(path.parts)))
        return os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW),chain
    monkeypatch.setattr(m.admitted,'_storage_module',lambda:NS(_walk=walk))
    return NS(root=root,plan=plan,raws=raws,paths=paths,seen=seen,plain=plain,initial=initial,record=record,
      selected=selected,axis=axis,catalog=catalog,Private=Private)


def test_fixed_four_DATA_plan_and_H_source_proof():
    assert set(m.DATA_PLAN)=={'hierarchy','catalog','stocks_metadata','funds_metadata'}
    assert sum(row['byte_count'] for row in m.DATA_PLAN.values())==5507602
    assert m.DATA_PLAN['hierarchy']['sha256']=='b85c3d37acbe4f72192d4d42d6470654a2e727f0c6a23bed06a3539e2ec3aacd'
    assert m.H_FACT_SHA256=='e72ff5029df04609c1f7eb4d6fc2f2a552c4dfa0065764d2c4dc00f0601beab4'
    assert m.source_context()==m.diagnosis.source_context()


def test_own_profile_is_inert_closed_pinned_metadata():
    profile=m.profile_record()
    assert profile['data_total_bytes']==5507602 and len(profile['source_pins'])>=221
    assert profile['all_five_transport_role_byte_inventories_checked'] is True
    assert profile['parsed_role_semantics']==['evaluator_manifest','session_axis','memberships','runtime_symbol_bindings']
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    assert profile['maximum_private_output_bytes']==16*1024*1024


def test_source_fact_cannot_be_changed_to_failure(monkeypatch):
    fact=m.h_anchor.observed_fact();fact['producer']['actual_exit']=2
    monkeypatch.setattr(m.h_anchor,'observed_fact',lambda:fact)
    fail('source_binding',m.source_context)


@pytest.mark.parametrize('role',['hierarchy','catalog','stocks_metadata','funds_metadata'])
def test_all_four_external_pins_precede_genuine_loader(scope,role):
    raw=bytearray(scope.raws[role]);raw[-2]^=1;scope.paths[role].write_bytes(raw)
    with pytest.raises(m.guard_module.Refused):m.construct(time.monotonic()+30)
    assert scope.seen==[]


def test_construct_passes_exact_all_sources_and_fresh_streams(scope):
    observed,raw=m.construct(time.monotonic()+30)
    assert raw==private_raw() and observed['all_four_DATA_guard_normal_return'] is True
    assert scope.seen[0]==('load',) and scope.seen[1][0]=='prepare'
    _,raws,kwargs=scope.seen[1]
    assert raws==tuple(scope.raws[role] for role in ('hierarchy','catalog','stocks_metadata','funds_metadata'))
    assert kwargs['full_axis']==scope.axis and kwargs['binding_rows']==tuple(scope.catalog)
    assert kwargs['membership_rows']==tuple(scope.selected['memberships'])
    assert kwargs['evaluator_manifest']==scope.selected['evaluator_manifest'][0]
    assert kwargs['input_binding']==input_binding()
    m.guard_module.validate_receipt(observed['source_receipt'],m.DATA_PLAN)


def test_genuine_fingerprint_change_refuses_no_publication(scope,monkeypatch):
    monkeypatch.setattr(m.transport,'_fingerprint',lambda value:{'changed':True})
    fail('genuine_changed',lambda:m.construct(time.monotonic()+30))
    assert not m.CONTROL.exists()


def test_genuine_record_change_refuses(scope,monkeypatch):
    monkeypatch.setattr(scope.plain,'to_record',lambda:{'changed':True})
    fail('genuine_changed',lambda:m.construct(time.monotonic()+30))


def test_membership_stream_semantic_change_refuses(scope,monkeypatch):
    def streams(*args):
        value=copy.deepcopy(scope.selected);value['memberships'].append({'changed':True});return value
    monkeypatch.setattr(m.membership,'_streams',streams)
    fail('genuine_changed',lambda:m.construct(time.monotonic()+30))


def test_separate_checked_binding_catalog_mutation_refuses(scope,monkeypatch):
    def prepare(*raws,**kwargs):
        kwargs['binding_rows'][0]['mutated_copy']=True
        return summary(),scope.Private()
    monkeypatch.setattr(m.diagnosis,'prepare',prepare)
    fail('genuine_changed',lambda:m.construct(time.monotonic()+30))
    assert not m.CONTROL.exists()


def test_three_role_postcheck_cannot_stand_in_for_four(scope,monkeypatch):
    monkeypatch.setattr(m.membership,'_streams',lambda *args:{key:value for key,value in scope.selected.items() if key!='memberships'})
    fail('genuine_changed',lambda:m.construct(time.monotonic()+30))


def test_named_source_replacement_during_pure_analysis_refuses(scope,monkeypatch):
    def prepare(*raw,**kwargs):
        path=scope.paths['stocks_metadata'];path.rename(path.with_suffix('.old'));path.write_bytes(scope.raws['stocks_metadata']);path.chmod(0o600)
        return summary(),scope.Private()
    monkeypatch.setattr(m.diagnosis,'prepare',prepare)
    with pytest.raises(m.guard_module.Refused):m.construct(time.monotonic()+30)
    assert not m.CONTROL.exists()


def test_exact_private_class_required(scope,monkeypatch):
    monkeypatch.setattr(m.diagnosis,'prepare',lambda *args,**kwargs:(summary(),NS(_raw=private_raw(),
      byte_count=len(private_raw()),sha256=m.sha(private_raw()),summary_sha256=m.sha(m.canonical(summary())))))
    fail('private_binding',lambda:m.construct(time.monotonic()+30))


@pytest.mark.parametrize('attribute,value',[('sha256','0'*64),('summary_sha256','0'*64),('byte_count',1)])
def test_private_output_pin_and_summary_binding(scope,monkeypatch,attribute,value):
    monkeypatch.setattr(scope.Private,attribute,value)
    fail('private_binding',lambda:m.construct(time.monotonic()+30))


def test_claim_is_fsynced_before_any_DATA_or_genuine_read(scope,monkeypatch):
    original=m.construct
    def construct(deadline):
        assert (m.CONTROL/'claim.json').read_bytes()==m.canonical(m.binding(args()))
        assert list(m.CONTROL.iterdir())==[m.CONTROL/'claim.json']
        return original(deadline)
    monkeypatch.setattr(m,'construct',construct)
    outcome=m.run(args(),time.monotonic()+30)
    assert set(outcome)=={'result','report'} and (m.CONTROL/m.PRIVATE_NAME).read_bytes()==private_raw()
    m.validate_result(outcome['result'])


def test_guard_normal_return_precedes_private_publication(scope,monkeypatch):
    real=m.guard_module.FixedDataGuard;state={'returned':False}
    class Guard:
        def __init__(self,*args,**kwargs):self.inner=real(*args,**kwargs)
        def __enter__(self):return self.inner.__enter__()
        def __exit__(self,*args):
            assert not (m.CONTROL/m.PRIVATE_NAME).exists()
            result=self.inner.__exit__(*args);state['returned']=True;return result
    monkeypatch.setattr(m.guard_module,'FixedDataGuard',Guard)
    original=m.Store.write
    def write(store,name,raw,deadline):
        if name!= 'claim.json':assert state['returned'] is True
        return original(store,name,raw,deadline)
    monkeypatch.setattr(m.Store,'write',write)
    assert 'result' in m.run(args(),time.monotonic()+30)


def test_guard_close_failure_never_publishes_private(scope,monkeypatch):
    real=m.guard_module.FixedDataGuard
    class Guard:
        def __init__(self,*args,**kwargs):self.inner=real(*args,**kwargs)
        def __enter__(self):return self.inner.__enter__()
        def __exit__(self,*args):
            self.inner.__exit__(*args);raise m.guard_module.Refused('close')
    monkeypatch.setattr(m.guard_module,'FixedDataGuard',Guard)
    outcome=m.run(args(),time.monotonic()+30)
    assert outcome['failure']['failure_code']=='guard_close' and outcome['failure']['claim_state']=='consumed'
    assert not (m.CONTROL/m.PRIVATE_NAME).exists()


def test_claim_leaf_cannot_be_reentered(scope):
    with m.Store() as store:store.write('claim.json',m.canonical(m.binding(args())),time.monotonic()+10)
    fail('claim_spent',lambda:m.Store())


@pytest.mark.parametrize('mode',['produce','validate'])
def test_native_isolation_and_exact_role_scope(mode):
    policy=m.native_profile(mode)
    assert '(deny network*)' in policy and '/usr/bin/security' in policy and '/Users/sheltonchen/Library/Keychains' in policy
    if mode=='validate':
        assert '(deny file-read* (subpath "'+str(m.ROOT/'artifacts')+'"))' in policy
    else:
        assert all(row['relative_path'] in policy for row in m.DATA_PLAN.values())
        assert str(m.worker.previous.PACKAGE) in policy and str(m.worker.previous.LINEAGE) in policy
        assert str(m.CONTROL.parent)+'"))' in policy


@pytest.mark.parametrize('exit',[2,1,-9,None,True])
def test_success_report_requires_exact_actual_zero(scope,exit):
    value=result();report=m.pin(m.canonical({**m.binding(args()),'result':value}))
    raw=m.canonical({'binding':m.binding(args()),'outcome':{'result':value,'report':report}})+b'\n'
    fail('output',lambda:m.validate_output(raw,exit,args()))


def test_success_result_and_report_are_joined(scope):
    value=result();report=m.pin(m.canonical({**m.binding(args()),'result':value}))
    raw=m.canonical({'binding':m.binding(args()),'outcome':{'result':value,'report':report}})+b'\n'
    assert m.validate_output(raw,0,args())['outcome']['result']==value
    report['sha256']='0'*64
    fail('output',lambda:m.validate_output(m.canonical({'binding':m.binding(args()),'outcome':{'result':value,'report':report}})+b'\n',0,args()))


@pytest.mark.parametrize('field',['all_four_DATA_guard_normal_return','genuine_input_checks_complete','post_checks_complete'])
def test_result_requires_every_normal_completion(scope,field):
    value=result();value[field]=False
    fail('output',lambda:m.validate_result(value))


def test_result_private_pin_and_original_inventory_must_match(scope):
    value=result();value['private_pin']['sha256']='0'*64
    fail('output',lambda:m.validate_result(value))
    value=result();value['genuine_input_binding']={'substituted':True}
    fail('output',lambda:m.validate_result(value))


def test_public_result_rejects_row_fields(scope):
    value=result();value['licensed_rows']=[{'synthetic':True}]
    fail('output',lambda:m.validate_result(value))


@pytest.mark.parametrize('claim_state',['unknown','consumed'])
def test_failure_is_authenticated_only_with_actual_two(scope,claim_state):
    value=m.failure(args(),m.Refused('deadline'),claim_state=claim_state);raw=m.canonical(value)+b'\n'
    assert m.validate_output(raw,2,args())['claim_state']==claim_state
    fail('output',lambda:m.validate_output(raw,0,args()))


def test_failure_unknown_predicate_never_discloses_exception_text():
    error=ValueError('DO-NOT-OUTPUT')
    value=m.failure(args(),error)
    assert value['failure_code']=='unknown' and b'DO-NOT-OUTPUT' not in m.canonical(value)


def test_known_diagnostic_predicate_is_retained_without_exception_text():
    error=m.diagnosis.Refused('byte_pin')
    value=m.failure(args(),error)
    assert value['failure_code']=='diagnosis_byte_pin' and value['failure_code'] in m.FINITE
    assert m.finite(m.diagnosis.Refused('deadline'))=='deadline'


def test_unknown_private_diagnostic_argument_is_never_printed():
    raw='SYNTHETIC-PRIVATE-VALUE-DO-NOT-OUTPUT'
    value=m.failure(args(),m.diagnosis.Refused(raw))
    assert value['failure_code']=='diagnosis_unknown'
    assert raw.encode('ascii') not in m.canonical(value)
    class Foreign(m.diagnosis.Refused):pass
    assert m.finite(Foreign(raw))=='unknown'


def test_public_helpers_do_not_import_or_invoke_old_operations():
    source=inspect.getsource(m)
    assert 'previous.run(' not in source and 'worker.prepare(' not in source and 'keychain' not in source.casefold().split('false_flags')[0]
    assert 'membership._authenticated(plain,deadline)' in source
    assert 'membership._streams(plain,record,deadline)' in source
    assert 'worker._catalog_unchanged(' not in source
