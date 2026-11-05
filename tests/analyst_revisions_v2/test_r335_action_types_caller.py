"""J synthetic caller checks; no real DATA, USB, Keychain, provider or QC."""
import ast
import copy
from contextlib import ExitStack
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS
import pytest
from scripts import run_arv2_r335_action_types as m
from scripts import arv2_r335_action_types as observer
from tests.analyst_revisions_v2 import test_r335_action_types as observer_tests


def args():return NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def refuse(code,call):
    with pytest.raises(m.Refused) as error:call()
    assert m.finite(error.value)==code


class Security:
    @staticmethod
    def snapshot(fd):return {'acl_empty':True,'xattrs':{}}


def fixture_control(tmp_path,monkeypatch):
    root=tmp_path/'root';root.mkdir(mode=0o755);root.chmod(0o755)
    artifacts=root/'artifacts';artifacts.mkdir(mode=0o700)
    lane=artifacts/'analyst_revisions_v2';lane.mkdir(mode=0o700)
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'CONTROL',lane/'firstrate/R335-J')
    return lane


def worker_observation(*,good=True,code='provider_header'):
    return {'spawn_observed':True,'actual_exit':0 if good else 2,'stdout_pin':{'byte_count':100,'sha256':'a'*64},
        'stderr_byte_count':0,'stderr_sha256':m.sha(b''),'marker_created':True,'marker_authenticated':True,
        'output_authenticated':True,'failure_code':None if good else code,'descriptor_validation_normal_return':good}


@pytest.fixture
def launched(tmp_path,monkeypatch):
    fixture_control(tmp_path,monkeypatch)
    transport=observer_tests.transport.__wrapped__(monkeypatch)
    state=NS(transport=transport,key_calls=[],workers=[],credential_fail=False,worker_fail=None)
    def load_key(provider,*,timeout_seconds):
        state.key_calls.append((provider,timeout_seconds));assert (m.CONTROL/'claim.json').exists()
        if state.credential_fail:raise ValueError(observer_tests.KEY)
        return observer_tests.KEY
    modules={'security':Security,'observer':observer,'keychain':NS(load_key=load_key)}
    monkeypatch.setattr(m,'preflight',lambda *a:None);monkeypatch.setattr(m,'safe_runtime',lambda:None)
    monkeypatch.setattr(m,'bootstrap',lambda *a:modules);monkeypatch.setattr(m,'OBSERVER_MODULE',observer)
    monkeypatch.setattr(m,'CLAIM_STATE','unallocated')
    def capture(value_args,store,deadline,obs):
        store.verify();assert m.STATE['session_closed_before_worker'] is m.STATE['key_local_reference_cleared_before_worker'] is True
        assert transport.responses[0].closed;state.workers.append('dictionary')
        try:
            if state.worker_fail:raise m.Refused(state.worker_fail)
            captured=m.STATE['capture_receipt'];raw=os.pread(m._held_fd(store,'response-00.csv'),m.MAX_PRIVATE+1,0)
            validated=observer.validate_capture(observer.plan_record(),captured,raw)
            result={'dictionary_receipt':validated,'response_pin':m.pin(raw),'capture_receipt_sha256':m.sha(m.canonical(captured)),
                'descriptor_validation_normal_return':True,'credential_access':False,'network_access':False,'old_control_access':False}
            observed=worker_observation();observed['stdout_pin']=m.pin(m.canonical({'schema':m.SCHEMA+'-worker','binding':m.binding(value_args),'result':result})+b'\n');m.validate_worker_result(result,observer,captured)
        except BaseException as error:result=None;observed=worker_observation(good=False,code=m.finite(error))
        m.STATE['worker_observation']=observed;store.write('dictionary-observed.json',m.canonical(observed))
        return result,observed
    monkeypatch.setattr(m,'capture_worker',capture)
    state.run=lambda:m.launch(args(),time.monotonic()+149)
    return state


def test_claim_then_one_key_one_GET_one_native_parse_and_exact_receipts(launched):
    packet=launched.run();state=packet['result']
    assert state['complete'] is state['accepted'] is True and state['failure_code'] is None
    assert launched.workers==['dictionary'] and len(launched.key_calls)==len(launched.transport.calls)==1
    assert launched.key_calls[0][0]=='sharadar' and 0<launched.key_calls[0][1]<=20
    assert state['keychain_lookup_attempts']==state['keychain_lookup_completed']==1
    assert state['capture_receipt']['CSV_validation_complete'] is False
    assert state['dictionary_receipt']['CSV_validation_complete'] is True
    assert state['dictionary_receipt']['row_count']==1 and state['provider_request_count'] is None
    raw=m.canonical(packet)+b'\n';assert m.validate_output(raw,0,args(),observer)['accepted'] is True
    assert not any(value in raw for value in (observer_tests.KEY.encode(),b'Synthetic definition',b'synthetic_event'))
    assert all(state[name] is False for name in m.FALSE_FLAGS)
    assert (m.CONTROL/'response-00.csv').read_bytes()==launched.transport.raw
    assert (m.CONTROL/'transport-00.json').exists();refuse('claim_spent',launched.run)


@pytest.mark.parametrize('status',[201,301,401,403,429,500,599])
def test_non200_status_retained_before_no_body_read_and_no_native_parse(launched,status):
    launched.transport.status=status;packet=launched.run();state=packet['result']
    assert state['accepted'] is False and state['failure_code']=='provider_http_status'
    assert launched.workers==[] and launched.transport.read==[] and state['response_pin'] is None
    assert state['http_events'][-2]['http_status']==status and state['http_events'][-1]['terminal_state']=='refused'
    assert m.validate_output(m.canonical(packet)+b'\n',2,args(),observer)['accepted'] is False
    refuse('output',lambda:m.validate_output(m.canonical(packet)+b'\n',0,args(),observer))


def test_bad_status200_header_retained_then_native_finite_failure(launched):
    launched.transport.raw=b'bad,header\n';packet=launched.run();state=packet['result']
    assert launched.workers==['dictionary'] and state['failure_code']=='provider_header'
    assert state['capture_receipt']['CSV_validation_complete'] is False and state['dictionary_receipt'] is None
    assert state['worker_observation']['actual_exit']==2 and state['worker_observation']['output_authenticated'] is True
    assert (m.CONTROL/'response-00.csv').read_bytes()==b'bad,header\n'
    assert m.validate_output(m.canonical(packet)+b'\n',2,args(),observer)['accepted'] is False


def test_response_close_failure_preserves_body_and_original_finite_cause(launched):
    launched.transport.fail_close=True;packet=launched.run();state=packet['result']
    assert state['failure_code']=='provider_response_close' and state['response_pin']==m.pin(launched.transport.raw)
    assert (m.CONTROL/'response-00.csv').exists() and launched.workers==[]
    assert state['accepted'] is False and state['capture_receipt'] is None


def test_credential_failure_consumes_claim_without_GET_or_worker(launched):
    launched.credential_fail=True;state=launched.run()['result']
    assert state['failure_code']=='unknown' and state['claim_state']=='consumed'
    assert state['keychain_lookup_attempts']==1 and state['keychain_lookup_completed']==0
    assert not launched.transport.calls and not launched.workers


@pytest.mark.parametrize('code',['provider_csv','provider_header','worker_deadline','worker_output','changed'])
def test_actual_child_failure_reason_is_preserved_and_never_success(launched,code):
    launched.worker_fail=code;packet=launched.run();state=packet['result']
    assert state['failure_code']==code and state['worker_observation']['failure_code']==code
    assert state['worker_observation']['actual_exit']==2 and state['accepted'] is False
    assert m.validate_output(m.canonical(packet)+b'\n',2,args(),observer)['result']['failure_code']==code


@pytest.mark.parametrize('field,value',[('expected_head','a'*39),('expected_head',True),('caller_sha256','x'*64),
    ('profile_sha256',None),('caller_sha256','b'*65)])
def test_binding_exact_types_hashes(field,value):
    selected=args();setattr(selected,field,value);refuse('arguments',lambda:m.binding(selected))


@pytest.mark.parametrize('raw',[b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}',b'not-json',b''])
def test_JSON_strict_duplicate_constant_shape(raw):refuse('input' if raw else 'bound',lambda:m.parse(raw,100))


@pytest.mark.parametrize('field,value',[('keychain_lookup_attempts',True),('keychain_lookup_completed',False),
    ('provider_request_count',0),('accepted',1),('complete',1),('session_closed_before_worker',1),
    ('key_local_reference_cleared_before_worker',1),('response_pin',{'byte_count':True,'sha256':'a'*64}),
    ('transport_pin',{'byte_count':True,'sha256':'a'*64}),('old_control_read',True),('identity_admitted',True),
    ('unknown',False)])
def test_state_rejects_bool_alias_false_flags_and_open_shapes(launched,field,value):
    state=copy.deepcopy(launched.run()['result']);state[field]=value
    with pytest.raises((m.Refused,observer.Refused)):m.validate_state(state,observer,m.binding(args()))


@pytest.mark.parametrize('which',['key0','completed0','claim','eventpin','receiptpin','receiptplan','dictionarypin',
    'dictionarycapture','workerfalse','markerfalse','child2','stderr','sessionfalse','keyfalse','missingdictionary'])
def test_source_capture_event_worker_dictionary_crossbindings(launched,which):
    state=copy.deepcopy(launched.run()['result'])
    if which=='key0':state['keychain_lookup_attempts']=0
    elif which=='completed0':state['keychain_lookup_completed']=0
    elif which=='claim':state['claim_state']='unallocated'
    elif which=='eventpin':state['http_events'][-1]['response_pin']['sha256']='d'*64
    elif which=='receiptpin':state['capture_receipt']['response_pin']['sha256']='d'*64
    elif which=='receiptplan':state['capture_receipt']['plan_sha256']='d'*64
    elif which=='dictionarypin':state['dictionary_receipt']['response_pin']['sha256']='d'*64
    elif which=='dictionarycapture':state['dictionary_receipt']['capture_receipt_sha256']='d'*64
    elif which=='workerfalse':state['worker_observation']['output_authenticated']=False
    elif which=='markerfalse':state['worker_observation']['marker_authenticated']=False
    elif which=='child2':state['worker_observation']['actual_exit']=2
    elif which=='stderr':state['worker_observation']['stderr_byte_count']=1
    elif which=='sessionfalse':state['session_closed_before_worker']=False
    elif which=='keyfalse':state['key_local_reference_cleared_before_worker']=False
    elif which=='missingdictionary':state['dictionary_receipt']=None
    with pytest.raises((m.Refused,observer.Refused)):m.validate_state(state,observer,m.binding(args()))


@pytest.mark.parametrize('which',['parent2','parentTrue','parentNone','reportpin','trailing','newline','wrongbinding'])
def test_external_actual_parent_exit_and_strict_envelope_are_mandatory(launched,which):
    packet=launched.run();actual=0
    if which=='parent2':actual=2
    elif which=='parentTrue':actual=True
    elif which=='parentNone':actual=None
    elif which=='reportpin':packet['report_pin']['sha256']='f'*64
    elif which=='wrongbinding':packet['binding']['expected_head']='f'*40
    raw=m.canonical(packet)+b'\n'
    if which=='trailing':raw+=b'noise'
    if which=='newline':raw+=b'\n'
    refuse('output',lambda:m.validate_output(raw,actual,args(),observer))


def test_late_parent_failure_forces_false_without_erasing_prior_finite_cause(launched,monkeypatch):
    launched.worker_fail='provider_header';packet=launched.run()
    monkeypatch.setattr(m,'ACTIVE_BINDING',m.binding(args()))
    m.STATE.update(accepted=False,complete=False)
    outer=m.failure_packet('source_changed')
    result=m.validate_output(m.canonical(outer)+b'\n',2,args(),observer)
    assert result['failure_code']=='source_changed' and result['result']['failure_code']=='provider_header'
    assert result['accepted'] is False and packet['result']['accepted'] is False


def test_dictionary_receipt_is_bound_to_exact_observed_worker_stdout_not_report_pin_only(launched):
    packet=launched.run();value=packet['result']['dictionary_receipt']
    value['empty_description_count']=1
    observer.validate_dictionary_receipt(value,observer.plan_record(),packet['result']['capture_receipt'])
    packet['report_pin']=m.pin(m.canonical({'binding':packet['binding'],'result':packet['result']}))
    refuse('output',lambda:m.validate_output(m.canonical(packet)+b'\n',0,args(),observer))


def test_held_file_original_descriptor_and_pin_reject_changed_and_symlink(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'synthetic');deadline=time.monotonic()+149
    with m.HeldFile(source,maximum=100,expected=m.pin(b'synthetic'),deadline=deadline) as held:assert held.read()==b'synthetic'
    with pytest.raises(m.Refused):
        with m.HeldFile(source,maximum=100,expected=m.pin(b'wrong'),deadline=deadline) as held:held.read()
    link=tmp_path/'link';link.symlink_to(source)
    with pytest.raises(OSError):
        with m.HeldFile(link,maximum=100,deadline=deadline):pass
    with pytest.raises(m.Refused):
        with m.HeldFile(source,maximum=100,deadline=deadline) as held:source.write_bytes(b'changed');held.verify()


def test_symlink_output_ancestor_refuses_before_claim(tmp_path,monkeypatch):
    lane=fixture_control(tmp_path,monkeypatch);other=tmp_path/'other';other.mkdir();(lane/'firstrate').symlink_to(other,target_is_directory=True)
    with pytest.raises((OSError,m.Refused)):m.Store(Security).__enter__()
    assert not (other/'R335-J').exists()


@pytest.mark.parametrize('mutation',['bytes','unexpected','mode','link','security'])
def test_own_output_is_never_silently_absorbed_or_repaired(tmp_path,monkeypatch,mutation):
    fixture_control(tmp_path,monkeypatch)
    class Changing(Security):
        changed=False
        @staticmethod
        def snapshot(fd):return {'synthetic_security_state':Changing.changed}
    with pytest.raises(m.Refused):
        with m.Store(Changing) as store:
            store.write('claim.json',b'{}')
            if mutation=='bytes':(m.CONTROL/'claim.json').write_bytes(b'changed')
            elif mutation=='unexpected':(m.CONTROL/'unexpected').write_bytes(b'synthetic')
            elif mutation=='mode':(m.CONTROL/'claim.json').chmod(0o644)
            elif mutation=='link':os.link(m.CONTROL/'claim.json',m.CONTROL/'duplicate')
            else:Changing.changed=True
            store.verify()


def test_public_profile_native_scope_and_exact_source_pin_closure():
    assert m.PROVIDER_CODES==observer.FINITE and 'header' in m.PROVIDER_CODES
    assert set(m.SOURCE_PINS)=={'scripts/arv2_relocation_security.py','scripts/arv2_keychain_connections.py','scripts/arv2_r335_action_types.py'}
    for name,expected in m.SOURCE_PINS.items():assert hashlib.sha256((m.ROOT/name).read_bytes()).hexdigest()==expected
    profile=m.profile_record();assert profile['maximum_seconds']==150 and profile['maximum_worker_seconds']==60
    assert profile['static_query']=={'endpoint':observer.ENDPOINT,**observer.QUERY}
    assert m.pin(observer.canonical(observer.profile_record()))==profile['observer_profile_pin']
    assert profile['worker_native_policy_sha256']==m.sha(m.worker_native_profile().encode())
    native=m.worker_native_profile()
    for literal in ('(deny network*)','/Volumes','/Library/Keychains','/usr/bin/security','[.]pyc$','response-00.csv','dictionary-started.json'):assert literal in native
    assert 'transport-00.json' not in native and 'R335-20261103-I' not in native


def test_no_old_DATA_or_price_QC_constructor_import_or_token_source():
    tree=ast.parse(m.SOURCE.read_bytes());imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports += [item.name for item in node.names]
        elif isinstance(node,ast.ImportFrom):imports.append(node.module or '')
    assert all(not name.startswith(('scripts.','research.','AlgorithmImports','QuantConnect')) for name in imports)
    assert 'fcntl' in imports and not hasattr(m,'DATA_PLAN')
    assert set(m.profile_record()['static_query'])=={'endpoint','tablename','format','limit','skip','sort'}
    assert 'old_private_DATA_read' in m.FALSE_FLAGS


def test_reused_held_source_and_Store_controls_match_frozen_G_except_allowed_names():
    old=ast.parse((m.ROOT/'scripts/run_arv2_r335_sharadar_actions.py').read_bytes());new=ast.parse(m.SOURCE.read_bytes())
    def selected(tree,name):
        value=next(node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name==name)
        value=copy.deepcopy(value)
        if isinstance(value,ast.ClassDef) and value.body and isinstance(value.body[0],ast.Expr) and isinstance(value.body[0].value,ast.Constant):value.body.pop(0)
        return ast.dump(value,include_attributes=False)
    for name in ('HeldFile','Store','meta','safe_env','_regular_fd','_held_fd'):assert selected(old,name)==selected(new,name),name


def test_CLI_bad_arguments_no_raw_value_or_traceback():
    result=subprocess.run([sys.executable,'-I','-B',str(m.SOURCE),'launch','--SYNTHETIC-SECRET'],cwd=m.ROOT,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    assert result.returncode==2 and not result.stderr and b'SYNTHETIC-SECRET' not in result.stdout
    assert m.parse(result.stdout,10000)['failure_code']=='arguments'


def capture_receipt(raw):
    return {'schema':observer.SCHEMA+'-capture','plan_sha256':m.sha(m.canonical(observer.plan_record())),
        'application_dispatch_attempts':1,'provider_request_count':None,'http_status':200,'response_pin':m.pin(raw),
        'CSV_validation_complete':False,**observer.FALSE_FLAGS}


def test_dictionary_worker_requires_own_claim_intent_readonlyFD_exclusive_marker_then_parse(tmp_path,monkeypatch):
    fixture_control(tmp_path,monkeypatch);raw=observer_tests.csv_bytes([observer_tests.row()]);receipt=capture_receipt(raw)
    monkeypatch.setattr(m,'preflight',lambda *a:None)
    monkeypatch.setattr(m,'bootstrap',lambda *a:{'security':Security,'observer':observer})
    selected=args();events=[];original=observer.validate_capture
    def parse_after_marker(*values):
        assert (m.CONTROL/'dictionary-started.json').exists();events.append('parse');return original(*values)
    monkeypatch.setattr(observer,'validate_capture',parse_after_marker)
    with m.Store(Security) as store:
        claim={'binding':m.binding(selected),'profile':m.profile_record()};store.write('claim.json',m.canonical(claim))
        store.write('response-00.csv',raw)
        intent={'binding':m.binding(selected),'phase':'dictionary','claim_pin':m.pin(m.canonical(claim)),
            'plan':observer.plan_record(),'capture_receipt':receipt,'response_pin':m.pin(raw)}
        store.write('dictionary-intent.json',m.canonical(intent))
        selected.control_fd=store.fd;selected.claim_fd=m._held_fd(store,'claim.json');selected.intent_fd=m._held_fd(store,'dictionary-intent.json')
        selected.response_fd=m._held_fd(store,'response-00.csv')
        refuse('worker_claim',lambda:m.dictionary_worker(selected,time.monotonic()+149));assert not events
        assert not (m.CONTROL/'dictionary-started.json').exists()
        response=os.open('response-00.csv',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=store.fd)
        try:
            selected.response_fd=response;packet=m.dictionary_worker(selected,time.monotonic()+149)
            marker=m.adopt_marker(store,'dictionary')
            assert marker==m.canonical({'binding':m.binding(selected),'phase':'dictionary','intent_pin':m.pin(m.canonical(intent))})
            assert packet['result']['dictionary_receipt']['row_count']==1 and events==['parse']
            m.validate_worker_result(packet['result'],observer,receipt)
            with pytest.raises(FileExistsError):m.dictionary_worker(selected,time.monotonic()+149)
            assert events==['parse']
        finally:os.close(response)


@pytest.mark.parametrize('mode',['success','failure','noise','stderr','timeout'])
def test_real_child_inherited_readonly_FD_finite_failure_noise_and_own_kill_reap(tmp_path,monkeypatch,mode):
    fixture_control(tmp_path,monkeypatch);raw=observer_tests.csv_bytes([observer_tests.row()]);receipt=capture_receipt(raw)
    monkeypatch.setattr(m,'STATE',m.new_state());m.STATE.update(capture_receipt=receipt,response_pin=m.pin(raw))
    monkeypatch.setattr(m,'safe_env',lambda:{'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    if mode=='timeout':monkeypatch.setattr(m,'WORKER_SECONDS',.2)
    actual=subprocess.Popen;children=[]
    def controlled(command,**kwargs):
        assert command[:2]==['/usr/bin/sandbox-exec','-p'] and '(deny network*)' in command[2]
        assert len(kwargs['pass_fds'])==4 and kwargs['close_fds'] is True
        directory,claimfd,responsefd,intentfd=kwargs['pass_fds'];intent_raw=os.pread(intentfd,16385,0)
        marker=m.canonical({'binding':m.binding(args()),'phase':'dictionary','intent_pin':m.pin(intent_raw)})
        if mode=='failure':packet={'schema':m.SCHEMA+'-worker','binding':m.binding(args()),'failure_code':'provider_header','attempt_reusable':False}
        else:
            result={'dictionary_receipt':observer.validate_capture(observer.plan_record(),receipt,raw),'response_pin':m.pin(raw),
                'capture_receipt_sha256':m.sha(m.canonical(receipt)),'descriptor_validation_normal_return':True,
                'credential_access':False,'network_access':False,'old_control_access':False}
            packet={'schema':m.SCHEMA+'-worker','binding':m.binding(args()),'result':result}
        output=m.canonical(packet)+b'\n'
        code='import os,sys,time,fcntl\n'
        code+='assert fcntl.fcntl('+str(responsefd)+',fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDONLY\n'
        code+='assert os.pread('+str(responsefd)+',524289,0)=='+repr(raw)+'\n'
        code+='assert os.fstat('+str(claimfd)+').st_size>0\n'
        code+='fd=os.open("dictionary-started.json",os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd='+str(directory)+')\n'
        code+='os.write(fd,'+repr(marker)+');os.fsync(fd);os.close(fd);os.fsync('+str(directory)+')\n'
        if mode=='timeout':code+='time.sleep(5)\n'
        if mode=='stderr':code+='os.write(2,b"synthetic-noise")\n'
        code+='os.write(1,'+repr(output+(b'noise\n' if mode=='noise' else b''))+')\n'
        code+='raise SystemExit('+('2' if mode=='failure' else '0')+')\n'
        # Darwin nested sandbox_apply is unavailable under this native-denied
        # harness; this real child inherits outer denial and tests FD/capture/
        # kill/reap mechanics, not a second application of the inner policy.
        child=actual([sys.executable,'-I','-B','-c',code],**kwargs);children.append(child);return child
    monkeypatch.setattr(m.subprocess,'Popen',controlled)
    with m.Store(Security) as store:
        store.write('claim.json',m.canonical({'binding':m.binding(args()),'profile':m.profile_record()}));store.write('response-00.csv',raw)
        result,observed=m.capture_worker(args(),store,time.monotonic()+149,observer)
        assert children[0].poll() is not None and children[0].stdout.closed and children[0].stderr.closed
        assert observed['spawn_observed'] is observed['marker_created'] is observed['marker_authenticated'] is True
        if mode=='success':assert result is not None and observed['actual_exit']==0 and observed['descriptor_validation_normal_return'] is True
        elif mode=='failure':assert result is None and observed['actual_exit']==2 and observed['output_authenticated'] is True and observed['failure_code']=='provider_header'
        elif mode=='timeout':assert result is None and observed['actual_exit']<0 and observed['failure_code']=='deadline'
        else:assert result is None and observed['actual_exit']==0 and observed['failure_code']==('worker_output' if mode=='noise' else 'worker_stderr')
        m.validate_worker_observation(observed);assert (m.CONTROL/'dictionary-observed.json').exists()


def test_bootstrap_executes_exact_held_selected_sources_without_repo_pyc_Keychain_or_old_caller():
    code="""from scripts import run_arv2_r335_action_types as m
from contextlib import ExitStack
import sys,time
with ExitStack() as held:
 modules=m.bootstrap('validate',held,time.monotonic()+149)
 assert set(modules)=={'security','observer'}
 assert modules['observer'].__spec__.loader is modules['security'].__spec__.loader is None
 assert getattr(modules['observer'],'__cached__',None) is None
 assert 'scripts.arv2_keychain_connections' not in sys.modules
 assert 'scripts.run_arv2_r335_sharadar_actions' not in sys.modules
 assert modules['observer'].profile_record()['maximum_observation_seconds']==150
"""
    result=subprocess.run([sys.executable,'-I','-B','-c','import sys;sys.path.insert(0,'+repr(str(m.ROOT))+');'+code],cwd=m.ROOT,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    assert result.returncode==0 and not result.stdout and not result.stderr


@pytest.mark.parametrize('change',['profile','head','source','platform','isolated','dirty'])
def test_preflight_exact_clean_host_HEAD_source_and_profile(tmp_path,monkeypatch,change):
    source=tmp_path/'scripts/caller.py';source.parent.mkdir();source.write_bytes(b'synthetic public source')
    monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'SOURCE',source);monkeypatch.setattr(m,'__file__',str(source))
    selected=args();selected.caller_sha256=m.sha(source.read_bytes());selected.profile_sha256=m.sha(m.canonical(m.profile_record()))
    monkeypatch.setattr(m,'sys',NS(platform='darwin',version_info=(3,13),executable=m.PYTHON,flags=NS(isolated=1),dont_write_bytecode=True))
    monkeypatch.setattr(m.Path,'cwd',classmethod(lambda cls:tmp_path));monkeypatch.setattr(m,'safe_env',lambda:{})
    def run(command,**kwargs):
        if command[1]=='cat-file':out=source.read_bytes() if change!='source' else b'changed'
        elif command[1]=='status':out=b'untracked' if change=='dirty' else b''
        elif command[1]=='branch':out=m.BRANCH.encode()
        elif command[-1]=='HEAD':out=('d'*40 if change=='head' else selected.expected_head).encode()
        else:out=str(tmp_path).encode()
        return NS(returncode=0,stderr=b'',stdout=out)
    monkeypatch.setattr(m.subprocess,'run',run)
    if change=='profile':selected.profile_sha256='d'*64
    if change=='platform':m.sys.platform='other'
    if change=='isolated':m.sys.flags.isolated=0
    refuse('host' if change in ('platform','isolated') else 'git_state' if change in ('head','dirty') else 'source_pin',
        lambda:m.preflight(selected,time.monotonic()+149))


def test_stdin_validation_mode_preflights_and_bootstraps_without_any_control_or_DATA_read():
    tree=ast.parse(m.SOURCE.read_bytes());main=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='main')
    branch=next(node for node in ast.walk(main) if isinstance(node,ast.If) and ast.unparse(node.test)=="args.mode == 'validate'")
    text=ast.unparse(branch)
    assert 'preflight(args, deadline)' in text and "bootstrap('validate', sources, deadline)" in text
    assert 'sys.stdin.buffer.read(MAX_OUTPUT + 1)' in text and 'Store(' not in text and 'CONTROL' not in text


@pytest.mark.parametrize('mode',['launch','dictionary','validate'])
def test_every_operational_entry_has_bounded_parent_worker_or_reader_alarm(monkeypatch,mode):
    selected=args();argv=[str(m.SOURCE),mode,'--expected-head',selected.expected_head,
        '--caller-sha256',selected.caller_sha256,'--profile-sha256',selected.profile_sha256]
    if mode=='dictionary':argv+=['--control-fd','3','--claim-fd','4','--response-fd','5','--intent-fd','6','--outer-deadline',repr(time.monotonic()+59)]
    if mode=='validate':argv+=['--actual-parent-exit','2']
    calls=[];monkeypatch.setattr(m.sys,'argv',argv);monkeypatch.setattr(m,'ENTRY_DEADLINE',time.monotonic()+149)
    monkeypatch.setattr(m.signal,'signal',lambda *a:None);monkeypatch.setattr(m.signal,'setitimer',lambda *a:calls.append(a))
    monkeypatch.setattr(m,'launch',lambda *a:{'synthetic':'launch'})
    monkeypatch.setattr(m,'dictionary_worker',lambda *a:{'synthetic':'dictionary'})
    monkeypatch.setattr(m,'preflight',lambda *a:None);monkeypatch.setattr(m,'bootstrap',lambda *a:{'observer':observer})
    monkeypatch.setattr(m.sys,'stdin',NS(buffer=io.BytesIO(b'finite synthetic stdin')))
    monkeypatch.setattr(m,'validate_output',lambda *a:{'synthetic':'validate'})
    assert m.main()=={'synthetic':mode} and len(calls)==1
    assert calls[0][0]==m.signal.ITIMER_REAL and 0<calls[0][1]<=(30 if mode=='validate' else 60 if mode=='dictionary' else 150)


def test_top_level_late_error_forces_failure_preserving_earlier_cause_without_traceback(monkeypatch):
    tree=ast.parse(m.SOURCE.read_bytes());entry=tree.body[-1];assert isinstance(entry,ast.If)
    code=compile(ast.Module(body=entry.body,type_ignores=[]),'<J-top-level-only>','exec')
    state=m.new_state();state.update(accepted=True,complete=True,failure_code='provider_header',claim_state='consumed')
    namespace=dict(m.__dict__);namespace['STATE']=state;namespace['CLAIM_STATE']='consumed';namespace['ACTIVE_BINDING']=m.binding(args())
    def late():raise m.Refused('source_changed')
    output=io.BytesIO();namespace['main']=late;namespace['sys']=NS(stdout=NS(buffer=output));namespace['failure_packet']=lambda code:{
        'binding':m.binding(args()),'failure_code':code,'attempt_reusable':False,'state':state}
    with pytest.raises(SystemExit) as finished:exec(code,namespace)
    assert finished.value.code==2 and state['complete'] is state['accepted'] is False
    assert state['failure_code']=='provider_header' and m.parse(output.getvalue(),m.MAX_OUTPUT)['failure_code']=='source_changed'
