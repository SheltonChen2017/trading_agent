"""Synthetic ACTIONS caller; real DATA/USB/Keychain/network access denied."""
import ast
import copy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS
import pytest
from scripts import run_arv2_r335_sharadar_actions as m
from scripts import arv2_r335_sharadar_actions as observer
from tests.analyst_revisions_v2 import test_r335_sharadar_actions as observer_tests


def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64, profile_sha256='c' * 64)


def refuse(code, call):
    with pytest.raises(m.Refused) as caught:
        call()
    assert m.finite(caught.value) == code


class Security:
    @staticmethod
    def snapshot(fd): return {'acl_empty': True, 'xattrs': {}}


def fixture_control(tmp_path, monkeypatch):
    root = tmp_path / 'root'; root.mkdir(mode=0o755); root.chmod(0o755)
    artifacts = root / 'artifacts'; artifacts.mkdir(mode=0o700)
    lane = artifacts / 'analyst_revisions_v2'; lane.mkdir(mode=0o700)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'CONTROL', lane / 'firstrate/R335-A')
    return lane


def test_symlink_output_ancestor_refuses_before_any_own_claim(tmp_path, monkeypatch):
    lane = fixture_control(tmp_path, monkeypatch)
    other = tmp_path / 'other'; other.mkdir()
    (lane / 'firstrate').symlink_to(other, target_is_directory=True)
    with pytest.raises((OSError, m.Refused)): m.Store(Security).__enter__()
    assert not (other / 'R335-A').exists()


def test_late_output_mutation_is_refused_and_evidence_retained(tmp_path, monkeypatch):
    fixture_control(tmp_path, monkeypatch)
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json', b'{}')
            (m.CONTROL / 'claim.json').write_bytes(b'changed')
            store.verify()
    assert (m.CONTROL / 'claim.json').read_bytes() == b'changed'


def test_unexpected_owned_control_leaf_is_not_absorbed_by_later_own_write(tmp_path, monkeypatch):
    fixture_control(tmp_path, monkeypatch)
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json', b'{}')
            (m.CONTROL / 'unexpected').write_bytes(b'synthetic')
            refuse('control', lambda: store.write('report.json', b'{}'))
    assert (m.CONTROL / 'unexpected').read_bytes() == b'synthetic'
    assert not (m.CONTROL / 'report.json').exists()


def test_cli_unknown_argument_never_echoes_supplied_value():
    result = subprocess.run([sys.executable, '-I', '-B', str(m.SOURCE), 'launch', '--SYNTHETIC-SECRET-ARG'],
        cwd=m.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
        env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
    assert result.returncode == 2 and not result.stderr
    assert b'SYNTHETIC-SECRET' not in result.stdout
    assert json.loads(result.stdout)['failure_code'] == 'arguments'


def test_dynamic_output_security_mismatch_is_not_ignored(tmp_path,monkeypatch):
    fixture_control(tmp_path,monkeypatch)
    class Changing(Security):
        changed=False
        @staticmethod
        def snapshot(fd):return {'synthetic_security_state':Changing.changed}
    with pytest.raises(m.Refused):
        with m.Store(Changing) as store:
            store.write('claim.json',b'{}');Changing.changed=True;store.verify()


def test_original_held_named_file_rejects_byte_pin_symlink_and_late_replacement(tmp_path):
    source = tmp_path / 'source'; source.write_bytes(b'synthetic')
    deadline = time.monotonic() + 299
    with m.HeldFile(source, maximum=100, expected=m.pin(b'synthetic'), deadline=deadline) as held:
        assert held.read() == b'synthetic'
    with pytest.raises(m.Refused):
        with m.HeldFile(source, maximum=100, expected=m.pin(b'other'), deadline=deadline) as held: held.read()
    link = tmp_path / 'link'; link.symlink_to(source)
    with pytest.raises(OSError):
        with m.HeldFile(link, maximum=100, deadline=deadline): pass
    with pytest.raises(m.Refused):
        with m.HeldFile(source, maximum=100, deadline=deadline) as held:
            source.write_bytes(b'changed!'); held.verify()


@pytest.mark.parametrize('field,value', [('expected_head', 'a' * 39), ('expected_head', True),
    ('caller_sha256', 'x' * 64), ('profile_sha256', None), ('caller_sha256', 'b' * 65)])
def test_arguments_refuse_malformed_bindings(field, value):
    value_args = args(); setattr(value_args, field, value)
    refuse('arguments', lambda: m.binding(value_args))


def test_binding_accepts_exact_source_run_pins_only():
    assert m.binding(args()) == {'schema': m.SCHEMA, 'expected_head': 'a' * 40,
        'caller_sha256': 'b' * 64, 'profile_sha256': 'c' * 64}


@pytest.mark.parametrize('raw', [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'not-json', b''])
def test_json_refuses_duplicates_constants_and_malformed(raw):
    with pytest.raises(m.Refused): m.parse(raw, 100)


def plan():
    return {'schema':observer.PLAN_SCHEMA,'F_DATA_pin':dict(observer.F_DATA_PIN),'I_DATA_pin':dict(observer.I_DATA_PIN),
        'explicit_tokens':['SYN0','SYN1'],'binding_lineage_sha256':'a'*64}


def worker_observation(phase, *, good=True):
    value={'phase':phase,'spawn_observed':True,'actual_exit':0 if good else 2,'stdout_pin':{'byte_count':100,'sha256':'b'*64},
        'stderr_byte_count':0,'stderr_sha256':m.sha(b''),'marker_created':True,'marker_authenticated':True,
        'output_authenticated':True,'failure_code':None if good else 'input','F_guard_normal_return':good,
        'source_receipt_sha256':'c'*64 if good else None,'plan_sha256':m.sha(m.canonical(plan())) if good else None}
    return value


@pytest.fixture
def launched(tmp_path,monkeypatch):
    fixture_control(tmp_path,monkeypatch)
    transport=observer_tests.transport.__wrapped__(monkeypatch)
    state=NS(transport=transport,key_calls=[],workers=[],source_fail=False,reauth_fail=False,reauth_changed=False,credential_fail=False)
    def load_key(provider,*,timeout_seconds):
        state.key_calls.append((provider,timeout_seconds))
        assert (m.CONTROL/'claim.json').exists()
        if state.credential_fail:raise ValueError('SYNTHETIC-PRIVATE-KEY')
        return observer_tests.KEY
    modules={'security':Security,'observer':observer,'keychain':NS(load_key=load_key)}
    monkeypatch.setattr(m,'preflight',lambda *args:None)
    monkeypatch.setattr(m,'safe_runtime',lambda:None)
    monkeypatch.setattr(m,'bootstrap',lambda *args:modules)
    monkeypatch.setattr(m,'OBSERVER_MODULE',observer)
    def capture(value_args,store,phase,deadline,obs):
        store.verify();state.workers.append(phase)
        good=not(state.source_fail if phase=='source' else state.reauth_fail)
        observed=worker_observation(phase,good=good)
        store.write(phase+'-observed.json',m.canonical(observed))
        if not good:return None,observed
        selected=plan()
        if phase=='reauth' and state.reauth_changed:selected['binding_lineage_sha256']='d'*64
        return {'plan':selected,'plan_sha256':m.sha(m.canonical(selected)),
            'source_receipt_sha256':'c'*64,'F_DATA_guard_normal_return':True,'credential_access':False,
            'network_access':False,'USB_access':False},observed
    monkeypatch.setattr(m,'capture_worker',capture)
    def run():return m.launch(args(),time.monotonic()+299)
    state.run=run
    return state


def test_exact_two_guards_one_keychain_lookup_and_owned_receipt_no_raw_return(launched):
    packet=launched.run();state=packet['result']
    assert state['accepted'] is state['complete'] is True and state['failure_code'] is None
    assert launched.workers==['source','reauth'] and len(launched.key_calls)==1
    assert launched.key_calls[0][0]=='sharadar' and 0<launched.key_calls[0][1]<=20
    assert state['keychain_lookup_attempts']==state['keychain_lookup_completed']==1
    assert len(state['retained_bodies'])==3 and len(state['http_events'])==9
    assert state['observer_receipt']['application_dispatch_attempts']==3 and state['provider_request_count'] is None
    raw=m.canonical(packet)+b'\n'
    checked=m.validate_output(raw,0,args(),observer)
    assert checked['accepted'] is True
    assert not any(value in raw for value in (observer_tests.KEY.encode(),b'SYN0',b'Synthetic issuer',b'query_token'))
    assert all(state[key] is False for key in m.FALSE_FLAGS)
    assert (m.CONTROL/'response-00.csv').read_bytes()==launched.transport.retained[0][1] if launched.transport.retained else True
    assert (m.CONTROL/'transport-00.json').exists()
    refuse('claim_spent',launched.run)


@pytest.mark.parametrize('status',[401,403,429,500])
def test_failed_status_retains_previous_bodies_and_numeric_status_without_failed_body(launched,status):
    launched.transport.statuses[1]=status
    packet=launched.run();state=packet['result']
    assert state['accepted'] is False and state['failure_code']=='provider_http_status'
    assert launched.workers==['source'] and len(launched.key_calls)==1
    assert launched.transport.read==[0] and len(state['retained_bodies'])==1
    assert (m.CONTROL/'response-00.csv').exists() and not (m.CONTROL/'response-01.csv').exists()
    assert state['http_events'][-2]['http_status']==status and state['http_events'][-1]['terminal_state']=='refused'
    assert m.validate_output(m.canonical(packet)+b'\n',2,args(),observer)['accepted'] is False
    refuse('output',lambda:m.validate_output(m.canonical(packet)+b'\n',0,args(),observer))


def test_bad_status200_CSV_retained_before_parse_and_close_failure_retains_body(launched):
    launched.transport.payloads[1]=b'not-a-csv'
    packet=launched.run();state=packet['result']
    assert state['failure_code']=='provider_csv' and state['accepted'] is False
    assert len(state['retained_bodies'])==2 and (m.CONTROL/'response-01.csv').read_bytes()==b'not-a-csv'
    assert state['http_events'][-1]['response_pin']==m.pin(b'not-a-csv')
    assert m.validate_output(m.canonical(packet)+b'\n',2,args(),observer)['accepted'] is False


def test_response_close_failure_retains_authenticated_complete_body(launched):
    launched.transport.fail_close=0
    packet=launched.run();state=packet['result']
    assert state['failure_code']=='provider_response_close' and state['accepted'] is False
    assert len(state['retained_bodies'])==1 and (m.CONTROL/'response-00.csv').exists()


def test_credential_or_pre_source_failure_never_dispatches(launched):
    launched.source_fail=True
    packet=launched.run();state=packet['result']
    assert state['failure_code']=='input' and state['accepted'] is False
    assert launched.key_calls==[] and launched.transport.calls==[] and launched.workers==['source']
    assert state['plan_pin'] is None and state['keychain_lookup_attempts']==0


def test_reauthentication_failure_after_provider_is_failure_not_success_or_retry(launched):
    launched.reauth_fail=True
    packet=launched.run();state=packet['result']
    assert state['accepted'] is False and state['failure_code']=='input'
    assert launched.workers==['source','reauth'] and len(launched.key_calls)==1
    assert len(launched.transport.calls)==3 and len(state['retained_bodies'])==3
    assert m.validate_output(m.canonical(packet)+b'\n',2,args(),observer)['accepted'] is False


def test_reauthentication_plan_change_refuses_without_silent_refresh(launched):
    launched.reauth_changed=True
    packet=launched.run();assert packet['result']['failure_code']=='changed'
    assert packet['result']['accepted'] is False and len(launched.transport.calls)==3


@pytest.mark.parametrize('change',['terminal_pin','terminal_rows','body_pin','source_guard','actual_alias','key_count','secret','project_pin','event_count'])
def test_public_result_and_actual_exit_cannot_forge_success_or_disclose_data(launched,change):
    packet=launched.run();state=packet['result']
    if change=='terminal_pin':state['http_events'][2]['response_pin']['sha256']='0'*64
    elif change=='terminal_rows':state['http_events'][2]['row_count']+=1
    elif change=='body_pin':state['retained_bodies'][0]['body_pin']['sha256']='0'*64
    elif change=='source_guard':state['source_workers'][1]['F_guard_normal_return']=False
    elif change=='actual_alias':state['source_workers'][1]['actual_exit']=False
    elif change=='key_count':state['keychain_lookup_attempts']=2
    elif change=='secret':state['api_key']='SECRET'
    elif change=='project_pin':state['plan_pin']['sha256']='0'*64
    else:state['http_events'].pop()
    packet['report_pin']=m.pin(m.canonical({'binding':m.binding(args()),'result':state}))
    with pytest.raises((m.Refused,observer.Refused)):m.validate_output(m.canonical(packet)+b'\n',0,args(),observer)


def test_nonzero_unknown_and_bool_actual_exits_never_admit_matching_report(launched):
    packet=launched.run();raw=m.canonical(packet)+b'\n'
    for actual in (None,True,-9,2):refuse('output',lambda:m.validate_output(raw,actual,args(),observer))
    packet['report_pin']['sha256']='0'*64
    refuse('output',lambda:m.validate_output(m.canonical(packet)+b'\n',0,args(),observer))


def F_metadata(monkeypatch):
    cases=[];wholes=[]
    for ordinal in range(5):
        original={'ticker':'SYN'+str(ordinal),'relatedtickers':'DO-NOT-PARSE OTHER','name':'Synthetic café'}
        original.update({'field'+str(index):'' for index in range(28-len(original))})
        raw=(json.dumps(original,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()
        binding={'diagnostic_current_ticker':'SYN'+str(ordinal),'source_row_sha256':m.sha(raw)}
        whole=m.sha(m.canonical(binding));wholes.append(whole)
        current={key:'' for key in m.META_FIELDS};current['ticker']='ALT'+str(ordinal)
        leads=[('binding.diagnostic_current_ticker',None,binding['diagnostic_current_ticker']),('original_row.ticker',None,original['ticker']),
            ('current_candidate_rows.ticker',0,current['ticker'])]
        rows=[{'field_origin':origin,'current_row_ordinal':index,'token':token,'token_supported':True,
            'listing_matches':[],'metadata_only_not_identity_or_price_coverage':True} for origin,index,token in leads]
        cases.append({'case_ordinal':ordinal,'whole_binding_sha256':whole,'binding':binding,'original_row':original,
            'current_candidate_rows':[current],'metadata_leads':rows,'optional_relatedtickers_raw':original['relatedtickers'],
            'relatedtickers_parse_state':'retained_unparsed','required_sessions':[],'potential_reference_sessions':[],
            'candidates':[],'no_candidate_gap':{},'source_assignment_changed':False,'original_metadata_hash_rechecked':True})
    monkeypatch.setattr(m,'EXPECTED_WHOLES',tuple(wholes))
    return {'schema':m.F_SCHEMA,'input_DATA_pins':{'identity':{'relative_path':'inherited-only',**m.I_DATA_PIN}},
        'retained_E_observation':{},'cases':cases,**m.F_FLAGS}


def test_source_plan_derives_all_explicit_supported_fields_not_related_or_name(monkeypatch):
    value=F_metadata(monkeypatch)
    selected=m.derive_plan(value,observer)
    assert selected['explicit_tokens']==['ALT0','ALT1','ALT2','ALT3','ALT4','SYN0','SYN1','SYN2','SYN3','SYN4']
    assert 'DO-NOT-PARSE' not in m.canonical(selected).decode()
    assert selected['F_DATA_pin']==observer.F_DATA_PIN and selected['I_DATA_pin']==observer.I_DATA_PIN
    value['cases'].reverse()
    assert m.derive_plan(value,observer)==selected


@pytest.mark.parametrize('change',['ordinal','whole','original_hash','related_parse','lead_origin','lead_token','lead_bool','current_bool','extra','flag'])
def test_plan_source_validation_rejects_lineage_or_lead_substitution(monkeypatch,change):
    value=F_metadata(monkeypatch);row=value['cases'][0]
    if change=='ordinal':row['case_ordinal']=False
    elif change=='whole':row['whole_binding_sha256']='0'*64
    elif change=='original_hash':row['original_row']['name']='changed'
    elif change=='related_parse':row['relatedtickers_parse_state']='split_into_aliases'
    elif change=='lead_origin':row['metadata_leads'][0]['field_origin']='relatedtickers'
    elif change=='lead_token':row['metadata_leads'][0]['token']='OTHER'
    elif change=='lead_bool':row['metadata_leads'][0]['token_supported']=1
    elif change=='current_bool':row['current_candidate_rows'][0]['ticker']=True
    elif change=='extra':value['api_key']='SECRET'
    else:value['identity_admitted']=True
    with pytest.raises(m.Refused):m.derive_plan(value,observer)


def test_unexpected_control_names_and_duplicate_claim_never_write(tmp_path,monkeypatch):
    fixture_control(tmp_path,monkeypatch)
    for name in ('../response-00.csv','response-17.csv','transport-00.csv','response-00.json','unknown','source-started.json'):
        assert m.allowed_name(name) is False
    with m.Store(Security) as store:
        store.write('claim.json',b'{}')
        store.write('response-00.csv',b'synthetic')
        assert all(item[0] in ('claim.json','response-00.csv') for item in store.held)
    refuse('claim_spent',lambda:m.Store(Security).__enter__())


def test_selected_pins_and_native_F_only_worker_scope():
    assert all(m.sha((m.ROOT/name).read_bytes())==digest for name,digest in m.SOURCE_PINS.items())
    assert len(m.DATA_PLAN)==1 and m.DATA_PLAN['metadata']['byte_count']==87170
    assert m.CONTROL.name=='R335-20261103-G'
    for phase in ('source','reauth'):
        policy=m.worker_native_profile(phase)
        assert '(deny network*)' in policy and '(subpath "/Volumes")' in policy
        assert '/Users/sheltonchen/Library/Keychains' in policy and '/Library/Keychains' in policy
        assert '/usr/bin/security' in policy and '[.]pyc$' in policy
        assert 'R335-20261103-F/private-diagnosis.json' in policy
        assert 'identity-demand-private.json' not in policy and 'R335-20261103-E' not in policy
        assert 'R335-20261103-G/'+phase+'-started.json' in policy
        assert 'plan-private.json' not in policy and 'response-00.csv' not in policy
    profile=m.profile_record()
    assert profile['retained_F_observation']['actual_parent_exit']==0
    assert profile['window']==['2023-11-01','2026-10-13']
    assert all(profile[key] is False for key in m.FALSE_FLAGS)


def test_source_worker_requires_inherited_claim_intent_then_exclusive_marker_before_F_read(tmp_path,monkeypatch):
    fixture_control(tmp_path,monkeypatch);value=F_metadata(monkeypatch);events=[]
    class Guard:
        def __init__(self,plan,**kwargs):assert plan==m.DATA_PLAN
        def __enter__(self):
            assert (m.CONTROL/'source-started.json').exists();events.append('enter_F');return self
        def read_all_once(self):events.append('read_F');return {'metadata':m.canonical(value)}
        def verify(self):events.append('verify_F')
        def receipt(self):return {'synthetic':True}
        def __exit__(self,*args):events.append('normal_F_return')
    modules={'security':Security,'observer':observer,'guard':NS(FixedDataGuard=Guard)}
    monkeypatch.setattr(m,'bootstrap',lambda *args:modules);monkeypatch.setattr(m,'preflight',lambda *args:None)
    selected=args();selected.mode='source'
    with m.Store(Security) as store:
        claim={'binding':m.binding(selected),'profile':m.profile_record()}
        store.write('claim.json',m.canonical(claim))
        intent={'binding':m.binding(selected),'phase':'source','claim_pin':m.pin(m.canonical(claim))}
        store.write('source-intent.json',m.canonical(intent))
        selected.control_fd=store.fd;selected.claim_fd=m._held_fd(store,'claim.json');selected.intent_fd=m._held_fd(store,'source-intent.json')
        result=m.worker(selected,time.monotonic()+299)
        marker=m.adopt_marker(store,'source')
        assert marker==m.canonical({'binding':m.binding(selected),'phase':'source','intent_pin':m.pin(m.canonical(intent))})
        assert result['result']['F_DATA_guard_normal_return'] is True and result['result']['credential_access'] is False
        assert events==['enter_F','read_F','verify_F','normal_F_return']
        assert result['result']['plan']['explicit_tokens']==['ALT0','ALT1','ALT2','ALT3','ALT4','SYN0','SYN1','SYN2','SYN3','SYN4']
        with pytest.raises(FileExistsError):m.worker(selected,time.monotonic()+299)
        assert events.count('read_F')==1


def test_unexpected_leaf_cannot_be_absorbed_during_child_marker_adoption(tmp_path,monkeypatch):
    fixture_control(tmp_path,monkeypatch)
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json',b'{}')
            (m.CONTROL/'source-started.json').write_bytes(b'{}');(m.CONTROL/'unowned').write_bytes(b'{}')
            refuse('worker_marker',lambda:m.adopt_marker(store,'source'))
    assert (m.CONTROL/'unowned').exists()


def test_partial_child_marker_is_retained_but_never_authenticated_as_success(tmp_path,monkeypatch):
    fixture_control(tmp_path,monkeypatch)
    with m.Store(Security) as store:
        store.write('claim.json',b'{}')
        path=m.CONTROL/'source-started.json';path.write_bytes(b'{');path.chmod(0o600)
        assert m.adopt_marker(store,'source')==b'{'
        store.verify()
        assert any(item[0]=='source-started.json' for item in store.held)


def test_bootstrap_compiles_held_selected_sources_without_repo_bytecode_or_old_caller_execution():
    root=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
    code="""from scripts import run_arv2_r335_sharadar_actions as m
from contextlib import ExitStack
import sys,time
with ExitStack() as held:
 modules=m.bootstrap('validate',held,time.monotonic()+299)
 assert set(modules)=={'security','observer'}
 assert modules['observer'].__spec__.loader is None
 assert modules['security'].__spec__.loader is None
 assert getattr(modules['observer'],'__cached__',None) is None
 assert 'scripts.arv2_keychain_connections' not in sys.modules
 assert 'scripts.inspect_arv2_r335_firstrate_gap_metadata' not in sys.modules
 assert modules['observer'].profile_record()['maximum_observation_seconds']==300
"""
    # This child has no operational modes, credentials, private DATA or network.
    result=subprocess.run([sys.executable,'-I','-B','-c',"import sys;sys.path.insert(0,"+repr(str(root))+");"+code],
        cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,
        env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    assert result.returncode==0 and not result.stdout and not result.stderr


def test_reused_FD_store_preflight_compilation_guards_remain_exact_frozen_F_except_output_names():
    path=m.ROOT/'scripts/inspect_arv2_r335_firstrate_gap_metadata.py'
    raw=path.read_bytes();assert m.sha(raw)=='fd41a4d434503edc15d71d25775b520e98728a0e0d2e455c5bc03c69dabbbfa0'
    before,after=ast.parse(raw),ast.parse(m.SOURCE.read_bytes())
    for name in ('HeldFile','preflight','binding','safe_env','meta','budget','parse'):
        get=lambda tree:next(node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name==name)
        assert ast.dump(get(before),include_attributes=False)==ast.dump(get(after),include_attributes=False)


@pytest.mark.parametrize('change',['no_key_lookup','key_not_completed','claim_unallocated','stderr_empty_hash','empty_source_stdout'])
def test_failure_evidence_cannot_claim_HTTP_without_consumed_claim_source_guard_and_key(launched,change):
    launched.transport.statuses[0]=403
    packet=launched.run();state=packet['result']
    if change=='no_key_lookup':state['keychain_lookup_attempts']=state['keychain_lookup_completed']=0
    elif change=='key_not_completed':state['keychain_lookup_completed']=0
    elif change=='claim_unallocated':state['claim_state']='unallocated'
    elif change=='stderr_empty_hash':state['source_workers'][0]['stderr_sha256']='0'*64
    else:state['source_workers'][0]['stdout_pin']=m.pin(b'')
    packet['report_pin']=m.pin(m.canonical({'binding':m.binding(args()),'result':state}))
    refuse('output',lambda:m.validate_output(m.canonical(packet)+b'\n',2,args(),observer))


@pytest.mark.parametrize('mode',['success','failure','noise','stderr','timeout'])
def test_real_tiny_child_capture_inherited_FDs_finite_failure_noise_and_kill_reap(tmp_path,monkeypatch,mode):
    fixture_control(tmp_path,monkeypatch)
    monkeypatch.setattr(m,'STATE',m.new_state())
    monkeypatch.setattr(m,'safe_env',lambda:{'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    if mode=='timeout':monkeypatch.setattr(m,'WORKER_SECONDS',0.2)
    real=subprocess.Popen;children=[]
    def controlled(command,**kwargs):
        assert command[:2]==['/usr/bin/sandbox-exec','-p'] and '(deny network*)' in command[2]
        assert len(kwargs['pass_fds'])==3 and kwargs['close_fds'] is True
        directory,claimfd,intentfd=kwargs['pass_fds']
        chosen=plan();intent_raw=os.pread(intentfd,8193,0)
        marker=m.canonical({'binding':m.binding(args()),'phase':'source','intent_pin':m.pin(intent_raw)})
        if mode=='failure':
            packet={'schema':m.SCHEMA+'-worker','binding':m.binding(args()),'phase':'source','failure_code':'input','attempt_reusable':False}
        else:
            packet={'schema':m.SCHEMA+'-worker','binding':m.binding(args()),'phase':'source','result':{'plan':chosen,
                'plan_sha256':m.sha(m.canonical(chosen)),'source_receipt_sha256':'a'*64,'F_DATA_guard_normal_return':True,
                'credential_access':False,'network_access':False,'USB_access':False}}
        raw=m.canonical(packet)+b'\n'
        code='import os,sys,time\n'
        code+='assert os.fstat('+str(claimfd)+').st_size>0\n'
        code+='fd=os.open("source-started.json",os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd='+str(directory)+')\n'
        code+='os.write(fd,'+repr(marker)+');os.fsync(fd);os.close(fd);os.fsync('+str(directory)+')\n'
        if mode=='timeout':code+='time.sleep(5)\n'
        if mode=='stderr':code+='os.write(2,b"synthetic-noise")\n'
        code+='os.write(1,'+repr(raw+(b'noise\n' if mode=='noise' else b''))+')\n'
        code+='raise SystemExit('+('2' if mode=='failure' else '0')+')\n'
        # Darwin refuses nested sandbox_apply from this already native-denied
        # test harness (observed exit71). Capture mechanics use a real child
        # inheriting that outer denial; this does not test inner policy application.
        child=real([sys.executable,'-I','-B','-c',code],**kwargs);children.append(child);return child
    monkeypatch.setattr(m.subprocess,'Popen',controlled)
    with m.Store(Security) as store:
        store.write('claim.json',m.canonical({'binding':m.binding(args()),'profile':m.profile_record()}))
        result,observed=m.capture_worker(args(),store,'source',time.monotonic()+299,observer)
        assert children[0].poll() is not None and children[0].stdout.closed and children[0].stderr.closed
        assert observed['spawn_observed'] is observed['marker_created'] is observed['marker_authenticated'] is True
        if mode=='success':
            assert result['plan']==plan() and observed['actual_exit']==0 and observed['F_guard_normal_return'] is True
        elif mode=='failure':
            assert result is None and observed['actual_exit']==2 and observed['output_authenticated'] is True
            assert observed['failure_code']=='input'
        elif mode=='timeout':
            assert result is None and observed['actual_exit']<0 and observed['failure_code']=='deadline'
        else:
            assert result is None and observed['actual_exit']==0
            assert observed['failure_code']==('worker_output' if mode=='noise' else 'worker_stderr')
        assert m.validate_worker_observation(observed)==observed
        assert (m.CONTROL/'source-observed.json').exists()
