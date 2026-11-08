"""Synthetic J caller only; no retained evidence, credentials, provider or QC."""
import copy
import inspect
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import prepare_arv2_r327_eodhd_fmp_query_plan as m
assert 'assistant.dispatch_fence' not in sys.modules


def args():return NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def fail(code,call):
    with pytest.raises(m.Refused) as error:call()
    assert m.finite(error.value)==code


def private_raw():return m.canonical({'schema':'synthetic-query-plan','cases':[{'case_ordinal':i} for i in range(5)]})


def summary():return {'schema':'synthetic-query-summary','private_payload_pin':m.pin(private_raw()),'selected_case_count':5}


def receipt():
    return {'schema':m.guard_module.SCHEMA+'-receipt',
      'profile_sha256':m.sha(m.canonical(m.guard_module.profile_record(m.DATA_PLAN))),
      'files':{role:{**row,'current_metadata_sha256':'d'*64,'current_security_sha256':'e'*64}
        for role,row in m.DATA_PLAN.items()},'fresh_current_security_authenticated':True,
      'fixed_bytes_authenticated':True,'requires_normal_return_before_use':True,
      'historical_continuity_proven':False,'continuous_integrity_proven':False}


def result():
    return {'schema':m.SCHEMA,'query_summary':summary(),'source_receipt':receipt(),'source_guard_normal_return':True,
      'private_pin':summary()['private_payload_pin'],'source_context_sha256':m.sha(m.canonical(m.source_context())),
      'I_fact_sha256':m.I_FACT_SHA256,'post_checks_complete':True,**m.FALSE_FLAGS}


@pytest.fixture
def scope(monkeypatch,tmp_path):
    root=tmp_path/'root';root.mkdir(mode=0o755);root.chmod(0o755)
    for name in ('artifacts','artifacts/analyst_revisions_v2','artifacts/analyst_revisions_v2/source','.pytest_cache'):
        (root/name).mkdir(mode=0o700)
    plan={};raws={};paths={}
    for role in ('identity','crosswalk','seed','capture'):
        raw=m.canonical({'synthetic_source':role});path=root/'artifacts/analyst_revisions_v2/source'/role
        path.write_bytes(raw);path.chmod(0o600);raws[role]=raw;paths[role]=path
        plan[role]={'relative_path':path.relative_to(root).as_posix(),**m.pin(raw)}
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m.guard_module,'ROOT',root);monkeypatch.chdir(root)
    monkeypatch.setattr(m,'CONTROL',root/'output'/'J');monkeypatch.setattr(m,'DATA_PLAN',plan)
    monkeypatch.setattr(m,'source_context',lambda:{'I_fact_sha256':m.I_FACT_SHA256,'synthetic':True})
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    monkeypatch.setattr(m.ar,'_credential_free',lambda:None)
    monkeypatch.setattr(m,'preflight',lambda *args:None);monkeypatch.setattr(m,'MIN_FREE_DISK',0)
    monkeypatch.setattr(m.query,'validate_summary',lambda value:value)
    monkeypatch.setattr(m.query,'validate_private_record',lambda value,**kwargs:value)
    class Private:
        _raw=private_raw();byte_count=len(_raw);sha256=m.sha(_raw);summary_sha256=m.sha(m.canonical(summary()))
        def private_record(self):return m.parse(self._raw)
    monkeypatch.setattr(m.query,'PrivateFmpQueryPlan',Private)
    seen=[]
    def prepare(*raws,**kwargs):seen.append((raws,kwargs));return summary(),Private()
    monkeypatch.setattr(m.query,'prepare',prepare)
    def walk(path):
        chain=tuple((os.stat(Path(*path.parts[:i+1])).st_dev,os.stat(Path(*path.parts[:i+1])).st_ino) for i in range(1,len(path.parts)))
        return os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW),chain
    monkeypatch.setattr(m.admitted,'_storage_module',lambda:NS(_walk=walk))
    return NS(root=root,raws=raws,paths=paths,plan=plan,seen=seen,Private=Private)


def test_fixed_four_DATA_leaves_and_anchored_source_context():
    assert set(m.DATA_PLAN)=={'identity','crosswalk','seed','capture'}
    assert sum(row['byte_count'] for row in m.DATA_PLAN.values())==45891902
    assert m.DATA_PLAN['identity']['sha256']=='c85ae5ddf2e918d194f6aa2939ee1249229d0989f75c334ef92ea793b61b711d'
    assert m.I_FACT_SHA256=='8fd5f90a0990b82a08f18a5037a54ed772c9c8c033bd2430501bdfd88620874e'
    assert m.source_context()==m.query.source_context()


def test_profile_retains_original_gates_and_owner_QC_hold():
    value=m.profile_record()
    assert len(value['source_pins'])==226 and value['data_total_bytes']==45891902
    assert value['all_four_external_byte_pins_before_any_DATA_JSON'] is True
    assert value['original_FIGI_AND_original_checksum_CUSIP9_gates_preserved'] is True
    assert value['QC_and_Safari_owner_hold_preserved'] is True
    assert value['maximum_owned_files']==4 and value['maximum_private_output_bytes']==16*1024*1024
    assert all(value[key] is False for key in m.FALSE_FLAGS)


def test_changed_helper_plan_refuses_before_read(monkeypatch):
    changed=copy.deepcopy(m.query.DATA_PLAN);changed['identity']['sha256']='0'*64
    monkeypatch.setattr(m.query,'DATA_PLAN',changed)
    fail('source_binding',m.source_context)


@pytest.mark.parametrize('role',['identity','crosswalk','seed','capture'])
def test_every_whole_pin_authenticates_before_pure_parse(scope,role):
    raw=bytearray(scope.raws[role]);raw[-2]^=1;scope.paths[role].write_bytes(raw)
    with pytest.raises(m.guard_module.Refused):m.construct(time.monotonic()+30)
    assert scope.seen==[] and not m.CONTROL.exists()


def test_pure_helper_receives_all_exact_four_sources(scope,monkeypatch):
    def no_genuine(*args,**kwargs):raise AssertionError('no genuine package reread')
    monkeypatch.setattr(m.previous.worker,'_load_plain',no_genuine)
    prepared,raw=m.construct(time.monotonic()+30)
    assert prepared['source_guard_normal_return'] is True and raw==private_raw()
    assert len(scope.seen)==1 and scope.seen[0][0]==tuple(scope.raws[role] for role in ('identity','crosswalk','seed','capture'))
    assert set(scope.seen[0][1])=={'deadline'}
    m.guard_module.validate_receipt(prepared['source_receipt'],m.DATA_PLAN)


def test_named_replacement_during_helper_refuses(scope,monkeypatch):
    def prepare(*raws,**kwargs):
        path=scope.paths['capture'];path.rename(path.with_suffix('.old'))
        path.write_bytes(scope.raws['capture']);path.chmod(0o600)
        return summary(),scope.Private()
    monkeypatch.setattr(m.query,'prepare',prepare)
    with pytest.raises(m.guard_module.Refused):m.construct(time.monotonic()+30)
    assert not m.CONTROL.exists()


def test_source_mode_change_during_helper_refuses(scope,monkeypatch):
    def prepare(*raws,**kwargs):
        scope.paths['seed'].chmod(0o640);return summary(),scope.Private()
    monkeypatch.setattr(m.query,'prepare',prepare)
    with pytest.raises(m.guard_module.Refused):m.construct(time.monotonic()+30)


def test_wrong_private_type_refuses(scope,monkeypatch):
    monkeypatch.setattr(m.query,'prepare',lambda *args,**kwargs:(summary(),NS(_raw=private_raw(),
      byte_count=len(private_raw()),sha256=m.sha(private_raw()),summary_sha256=m.sha(m.canonical(summary())))))
    fail('private_binding',lambda:m.construct(time.monotonic()+30))


@pytest.mark.parametrize('name,value',[('byte_count',1),('sha256','0'*64),('summary_sha256','0'*64)])
def test_private_object_and_summary_pins_are_exact(scope,monkeypatch,name,value):
    monkeypatch.setattr(scope.Private,name,value)
    fail('private_binding',lambda:m.construct(time.monotonic()+30))


def test_claim_precedes_DATA_and_is_reentry_spent(scope,monkeypatch):
    original=m.construct
    def construct(deadline):
        assert (m.CONTROL/'claim.json').read_bytes()==m.canonical(m.binding(args()))
        assert sorted(path.name for path in m.CONTROL.iterdir())==['claim.json']
        return original(deadline)
    monkeypatch.setattr(m,'construct',construct)
    outcome=m.run(args(),time.monotonic()+30)
    assert 'result' in outcome and (m.CONTROL/m.PRIVATE_NAME).read_bytes()==private_raw()
    m.validate_result(outcome['result'])
    fail('claim_spent',lambda:m.Store())


def test_normal_guard_return_precedes_all_plan_publication(scope,monkeypatch):
    real=m.guard_module.FixedDataGuard;state={'returned':False}
    class Guard:
        def __init__(self,*args,**kwargs):self.inner=real(*args,**kwargs)
        def __enter__(self):return self.inner.__enter__()
        def __exit__(self,*args):
            assert not (m.CONTROL/m.PRIVATE_NAME).exists()
            value=self.inner.__exit__(*args);state['returned']=True;return value
    monkeypatch.setattr(m.guard_module,'FixedDataGuard',Guard);original=m.Store.write
    def write(store,name,raw,deadline):
        if name!='claim.json':assert state['returned'] is True
        return original(store,name,raw,deadline)
    monkeypatch.setattr(m.Store,'write',write)
    assert 'result' in m.run(args(),time.monotonic()+30)


def test_guard_close_error_retains_failure_without_private_plan(scope,monkeypatch):
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


@pytest.mark.parametrize('mode',['produce','validate'])
def test_native_source_and_credential_scopes(mode):
    policy=m.native_profile(mode)
    assert '(deny network*)' in policy and '/usr/bin/security' in policy and '/Users/sheltonchen/Library/Keychains' in policy
    assert str(m.previous.worker.previous.PACKAGE) not in policy
    if mode=='produce':assert all(row['relative_path'] in policy for row in m.DATA_PLAN.values())
    else:assert '(deny file-read* (subpath "'+str(m.ROOT/'artifacts')+'"))' in policy


@pytest.mark.parametrize('exit',[2,1,-9,None,True])
def test_success_requires_observed_actual_zero(scope,exit):
    value=result();report=m.pin(m.canonical({**m.binding(args()),'result':value}))
    raw=m.canonical({'binding':m.binding(args()),'outcome':{'result':value,'report':report}})+b'\n'
    fail('output',lambda:m.validate_output(raw,exit,args()))


def test_success_report_pin_matches_exact_result(scope):
    value=result();report=m.pin(m.canonical({**m.binding(args()),'result':value}))
    raw=m.canonical({'binding':m.binding(args()),'outcome':{'result':value,'report':report}})+b'\n'
    assert m.validate_output(raw,0,args())['outcome']['result']==value
    report['sha256']='0'*64
    fail('output',lambda:m.validate_output(m.canonical({'binding':m.binding(args()),'outcome':{'result':value,'report':report}})+b'\n',0,args()))


@pytest.mark.parametrize('field',['source_guard_normal_return','post_checks_complete'])
def test_result_normal_completion_is_required(scope,field):
    value=result();value[field]=False;fail('output',lambda:m.validate_result(value))


def test_unknown_public_rows_and_private_pin_mismatch_refuse(scope):
    value=result();value['query_rows']=[{'secret':'not public'}]
    fail('output',lambda:m.validate_result(value))
    value=result();value['private_pin']['sha256']='0'*64
    fail('output',lambda:m.validate_result(value))


@pytest.mark.parametrize('claim_state',['unknown','consumed'])
def test_failure_actual_two_only(scope,claim_state):
    value=m.failure(args(),m.Refused('deadline'),claim_state=claim_state)
    raw=m.canonical(value)+b'\n';assert m.validate_output(raw,2,args())['claim_state']==claim_state
    fail('output',lambda:m.validate_output(raw,0,args()))


def test_whitelisted_query_failure_retained_and_raw_text_suppressed():
    assert 'byte_pin' in m.query.FINITE
    assert m.failure(args(),m.query.Refused('byte_pin'))['failure_code']=='query_byte_pin'
    assert m.finite(m.query.Refused('deadline'))=='deadline'
    raw='SYNTHETIC-PRIVATE-ISIN-DO-NOT-OUTPUT'
    value=m.failure(args(),m.query.Refused(raw))
    assert value['failure_code']=='query_unknown' and raw.encode() not in m.canonical(value)
    class Foreign(m.query.Refused):pass
    assert m.finite(Foreign(raw))=='unknown'


def test_no_old_operations_genuine_reread_or_provider_calls_in_source():
    source=inspect.getsource(m)
    assert 'previous.run(' not in source and '_load_plain(' not in source
    assert 'load_key(' not in source and 'requests.' not in source and 'get_browser' not in source
    assert 'query.prepare(' in source and 'guard_module.FixedDataGuard(DATA_PLAN' in source
