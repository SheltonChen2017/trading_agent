"""Synthetic N orchestration; actual DATA/USB/credentials/provider/QC denied."""
import ast
import copy
from contextlib import ExitStack
import io
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS
import pytest
from scripts import inspect_arv2_r336_action_semantics as m


def args():return NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def refuse(code,call):
    with pytest.raises(m.Refused) as error:call()
    assert m.finite(error.value)==code


class Security:
    @staticmethod
    def snapshot(fd):return {'acl_empty':True,'xattrs':{}}


class Pure:
    class Refused(ValueError):pass
    @staticmethod
    def finite(error):return 'input'
    @staticmethod
    def validate_summary(value):
        m.require(type(value) is dict and set(value)=={'schema','selected_case_count','classes'}
            and value['schema']=='synthetic_semantics' and type(value['selected_case_count']) is int
            and value['selected_case_count']==5 and value['classes']=={'unit_change_lead':1,'rename_lead':2},'output')
        return value


def summary():return {'schema':'synthetic_semantics','selected_case_count':5,'classes':{'unit_change_lead':1,'rename_lead':2}}


def result():
    return {'schema':m.SCHEMA,'complete':True,'summary':summary(),'private_pin':m.pin(b'PRIVATE-PROTECTED-ENRICHMENT'),
        'all_three_DATA_authenticated':True,'source_guard_normal_return':True,
        'worker_marker_pin':m.pin(m.canonical({'binding':m.binding(args()),'phase':'semantics'})),
        'source_receipt_sha256':'a'*64,**m.FALSE_FLAGS}


def worker_packet():
    value={'binding':m.binding(args()),'result':result()}
    return {**value,'report_pin':m.pin(m.canonical(value))}


def parent_packet():
    value=worker_packet()
    return {'binding':m.binding(args()),'output_authenticated':True,'observation':{'actual_child_exit':0,
        'child_stdout_pin':m.pin(m.canonical(value)+b'\n'),'child_stderr_byte_count':0,'child_stderr_sha256':m.sha(b''),
        'failure_code':None},'outcome':value}


@pytest.fixture(autouse=True)
def pure(monkeypatch):monkeypatch.setattr(m,'PURE_MODULE',Pure)


def fixture_root(tmp_path,monkeypatch):
    root=tmp_path/'root';root.mkdir(mode=0o755);root.chmod(0o755)
    artifacts=root/'artifacts';artifacts.mkdir(mode=0o700);lane=artifacts/'analyst_revisions_v2';lane.mkdir(mode=0o700)
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'CONTROL',lane/'identity_recovery/R336-N')


@pytest.fixture
def worker_setup(tmp_path,monkeypatch):
    fixture_root(tmp_path,monkeypatch);order=[]
    raw={'events':m.canonical({'raw':'PRIVATE-EVENT-TICKER-NAME-DATE-VALUE'}),
        'ownership':m.canonical({'raw':'PRIVATE-OWNERSHIP-FIGI-CUSIP-PERMA'}),'dictionary':b'PRIVATE-NORMATIVE-PROSE'}
    monkeypatch.setattr(m,'DATA_PLAN',{name:{'relative_path':'artifacts/analyst_revisions_v2/synthetic/'+name,**m.pin(value)} for name,value in raw.items()})
    state=NS(raw=raw,order=order,guard_fail=False,source_fail=False,semantics_fail=False,late_fail=False)
    class SourceClose:
        def __enter__(self):return self
        def __exit__(self,*a):
            order.append('source_normal_return' if not state.source_fail else 'source_close_refusal')
            if state.source_fail:raise m.Refused('source_changed')
    class Guard:
        def __init__(self,plan,*,deadline):assert plan==m.DATA_PLAN
        def __enter__(self):
            assert (m.CONTROL/'claim.json').exists() and (m.CONTROL/'worker-started.json').exists();order.append('data_enter');return self
        def read_all_once(self):order.append('data_read');return raw
        def verify(self):order.append('data_verify')
        def receipt(self):return {'synthetic_receipt':True}
        def __exit__(self,*a):
            order.append('data_normal_return' if not state.guard_fail else 'data_close_refusal')
            if state.guard_fail:raise m.Refused('changed')
    class Semantics(Pure):
        @staticmethod
        def analyze(i_value,m_value,j_raw,*,deadline):
            assert i_value=={'raw':'PRIVATE-EVENT-TICKER-NAME-DATE-VALUE'}
            assert m_value=={'raw':'PRIVATE-OWNERSHIP-FIGI-CUSIP-PERMA'} and j_raw==raw['dictionary']
            order.append('semantics')
            if state.semantics_fail:raise m.Refused('input')
            return summary(),{'private_rows':['PRIVATE-EVENT-TICKER-NAME-DATE-VALUE','PRIVATE-OWNERSHIP-FIGI-CUSIP-PERMA']}
    def bootstrap(role,stack,deadline):
        stack.enter_context(SourceClose());return {'security':Security,'pure':Semantics,'guard':NS(FixedDataGuard=Guard)}
    monkeypatch.setattr(m,'bootstrap',bootstrap);monkeypatch.setattr(m,'preflight',lambda *a:None)
    original=m.Store.write
    def write(store,name,value):
        if name in ('private-diagnosis.json','report.json'):
            assert 'data_normal_return' in order and 'source_normal_return' in order
            assert order.index('data_normal_return')<order.index('source_normal_return')
        order.append('write_'+name)
        if state.late_fail and name=='report.json':raise m.Refused('output')
        return original(store,name,value)
    monkeypatch.setattr(m.Store,'write',write);monkeypatch.setattr(m,'CLAIM_STATE','unallocated')
    def run():
        selected=args();read,write=os.pipe()
        try:os.write(write,m.canonical(m.binding(selected)))
        finally:os.close(write)
        selected.intent_fd=read;return m.worker(selected,time.monotonic()+149)
    state.run=run;return state


def test_exclusive_claim_marker_exact_three_DATA_then_semantics_and_normal_return_before_publication(worker_setup):
    packet=worker_setup.run();assert packet['result']['complete'] is True
    assert packet['result']['summary']==summary() and packet['result']['all_three_DATA_authenticated'] is True
    order=worker_setup.order
    assert order.index('write_claim.json')<order.index('write_worker-started.json')<order.index('data_read')<order.index('semantics')
    assert order.index('source_normal_return')<order.index('write_private-diagnosis.json')<order.index('write_report.json')
    raw=m.canonical(packet)+b'\n';m.validate_envelope(raw,0,args())
    assert not any(marker in raw for marker in (b'PRIVATE-',b'private_rows',b'PRIVATE-NORMATIVE-PROSE'))
    assert (m.CONTROL/'private-diagnosis.json').exists();refuse('claim_spent',worker_setup.run)


@pytest.mark.parametrize('failure',['guard','source','semantics','late'])
def test_every_late_or_private_failure_is_finite_and_never_success(worker_setup,monkeypatch,failure):
    setattr(worker_setup,{'guard':'guard_fail','source':'source_fail','semantics':'semantics_fail','late':'late_fail'}[failure],True)
    monkeypatch.setattr(m,'ACTIVE_BINDING',m.binding(args()))
    with pytest.raises(m.Refused) as error:worker_setup.run()
    packet=m.failure_packet(m.finite(error.value));m.validate_failure(packet,args())
    assert packet['attempt_reusable'] is False and b'PRIVATE-' not in m.canonical(packet)
    assert (m.CONTROL/'claim.json').exists() and (m.CONTROL/'worker-started.json').exists()
    assert not (m.CONTROL/'report.json').exists()
    assert (m.CONTROL/'private-diagnosis.json').exists() is (failure=='late')


@pytest.mark.parametrize('field,value',[('complete',1),('all_three_DATA_authenticated',1),('source_guard_normal_return',1),
    ('source_receipt_sha256','bad'),('identity_admitted',True),('price_input_admitted',True),('generic_prose_disclosed',True),
    ('private_pin',{'byte_count':True,'sha256':'a'*64}),('worker_marker_pin',{'byte_count':0,'sha256':'a'*64}),('extra',False)])
def test_closed_result_types_flags_marker_private_pin_and_receipt(field,value):
    selected=result();selected[field]=value;refuse('output',lambda:m.validate_result(selected,args()))


def test_valid_worker_and_parent_output_accept_only_actual0_and_no_private_payload():
    packet=parent_packet();checked=m.validate_parent_output(m.canonical(packet)+b'\n',0,args())
    assert checked['accepted'] is True and checked['result']['summary']==summary()
    assert b'PRIVATE-' not in m.canonical(packet)


@pytest.mark.parametrize('which',['actual2','actualbool','actualnone','workerexit','stderrbool','stderr','stderrhash','stdoutpin',
    'reportpin','markerpin','bind','flag','summary','trailing','doubleLF'])
def test_actual_exit_worker_stdout_report_source_binding_and_strict_frame(which):
    packet=parent_packet();actual=0
    if which=='actual2':actual=2
    elif which=='actualbool':actual=True
    elif which=='actualnone':actual=None
    elif which=='workerexit':packet['observation']['actual_child_exit']=2
    elif which=='stderrbool':packet['observation']['child_stderr_byte_count']=False
    elif which=='stderr':packet['observation']['child_stderr_byte_count']=1
    elif which=='stderrhash':packet['observation']['child_stderr_sha256']='f'*64
    elif which=='stdoutpin':packet['observation']['child_stdout_pin']['sha256']='f'*64
    elif which=='reportpin':packet['outcome']['report_pin']['sha256']='f'*64
    elif which=='markerpin':packet['outcome']['result']['worker_marker_pin']['sha256']='f'*64
    elif which=='bind':packet['binding']['expected_head']='f'*40
    elif which=='flag':packet['outcome']['result']['identity_admitted']=True
    elif which=='summary':packet['outcome']['result']['summary']['selected_case_count']=True
    raw=m.canonical(packet)+b'\n'+(b'noise' if which=='trailing' else b'\n' if which=='doubleLF' else b'')
    refuse('output',lambda:m.validate_parent_output(raw,actual,args()))


def test_private_output_pin_cannot_be_replaced_with_fresh_report_pin_but_unchanged_worker_stdout():
    packet=parent_packet();value=packet['outcome'];value['result']['private_pin']['sha256']='f'*64
    value['report_pin']=m.pin(m.canonical({'binding':value['binding'],'result':value['result']}))
    m.validate_envelope(m.canonical(value)+b'\n',0,args())
    refuse('output',lambda:m.validate_parent_output(m.canonical(packet)+b'\n',0,args()))


@pytest.mark.parametrize('code',['input','changed','source_pin','deadline','output'])
def test_parent_preserves_finite_actual_child2_failure(code,monkeypatch):
    monkeypatch.setattr(m,'ACTIVE_BINDING',m.binding(args()));monkeypatch.setattr(m,'CHILD_OBSERVATION',None)
    failed=m.failure_packet(code);packet={'binding':m.binding(args()),'output_authenticated':True,'failure':failed,
        'observation':{'actual_child_exit':2,'child_stdout_pin':m.pin(m.canonical(failed)+b'\n'),
            'child_stderr_byte_count':0,'child_stderr_sha256':m.sha(b''),'failure_code':None}}
    result=m.validate_parent_output(m.canonical(packet)+b'\n',2,args())
    assert result['accepted'] is False and result['failure']['failure_code']==code
    refuse('output',lambda:m.validate_parent_output(m.canonical(packet)+b'\n',0,args()))


@pytest.mark.parametrize('problem',['deadline','child_stderr','bound'])
def test_parent_late_ambiguity_retains_measured_child_evidence(tmp_path,monkeypatch,problem):
    monkeypatch.setattr(m,'preflight',lambda *a:None);monkeypatch.setattr(m,'ACTIVE_BINDING',m.binding(args()))
    monkeypatch.setattr(m,'ENTRY_DEADLINE',time.monotonic()+149)
    state=NS(calls=0)
    def capture(command,descriptors,deadline):
        state.calls+=1;assert len(descriptors)==1 and command[:2]==['/usr/bin/sandbox-exec','-p']
        assert os.read(descriptors[0],4097)==m.canonical(m.binding(args()))
        return -9,b'finite partial stdout',0,m.sha(b''),problem
    monkeypatch.setattr(m,'run_child',capture)
    with pytest.raises(m.Refused) as error:m._parent_bound(args())
    assert state.calls==1 and m.CHILD_OBSERVATION['actual_child_exit']==-9
    assert m.CHILD_OBSERVATION['child_stdout_pin']==m.pin(b'finite partial stdout')
    assert m.CHILD_OBSERVATION['failure_code']==problem
    packet=m.failure_packet(m.finite(error.value))
    assert m.validate_parent_output(m.canonical(packet)+b'\n',2,args())['accepted'] is False


@pytest.mark.parametrize('field,value',[('expected_head',True),('expected_head','a'*39),('caller_sha256','bad'),('profile_sha256',None)])
def test_binding_exact_source_values(field,value):
    selected=args();setattr(selected,field,value);refuse('arguments',lambda:m.binding(selected))


@pytest.mark.parametrize('raw',[b'{}\nnoise',b'{"a":1,"a":2}',b'{"a":NaN}',b''])
def test_duplicate_constant_malformed_or_empty_JSON(raw):
    with pytest.raises(m.Refused):m.parse(raw,100)


@pytest.mark.parametrize('kind',['symlink','unknown','bytes','mode','security'])
def test_held_chain_owned_control_and_security_mismatch_refuse(tmp_path,monkeypatch,kind):
    fixture_root(tmp_path,monkeypatch)
    if kind=='symlink':
        other=tmp_path/'other';other.mkdir();m.CONTROL.parent.symlink_to(other,target_is_directory=True)
        with pytest.raises((OSError,m.Refused)):m.Store(Security).__enter__()
        assert not (other/'R336-N').exists();return
    class Current(Security):
        changed=False
        @staticmethod
        def snapshot(fd):return {'synthetic_current_security':Current.changed}
    with pytest.raises(m.Refused):
        with m.Store(Current) as store:
            store.write('claim.json',b'{}')
            if kind=='unknown':(m.CONTROL/'unknown').write_bytes(b'PRIVATE')
            elif kind=='bytes':(m.CONTROL/'claim.json').write_bytes(b'PRIVATE')
            elif kind=='mode':(m.CONTROL/'claim.json').chmod(0o644)
            else:Current.changed=True
            store.verify()


@pytest.mark.parametrize('mode',['success','failure','stderr','timeout','bound'])
def test_real_small_child_bounded_capture_inherited_denial_and_own_kill_reap(monkeypatch,mode):
    actual=subprocess.Popen;children=[]
    monkeypatch.setattr(m,'safe_env',lambda:{'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    def tracked(*a,**k):child=actual(*a,**k);children.append(child);return child
    monkeypatch.setattr(m.subprocess,'Popen',tracked)
    code='import os,time\n'
    if mode=='timeout':code+='time.sleep(5)\n'
    if mode=='stderr':code+='os.write(2,b"synthetic error")\n'
    if mode=='bound':monkeypatch.setattr(m,'MAX_OUTPUT',32);code+='os.write(1,b"x"*33)\n'
    else:code+='os.write(1,b"finite synthetic output\\n")\n'
    code+='raise SystemExit('+('2' if mode=='failure' else '0')+')'
    result=m.run_child([sys.executable,'-I','-B','-c',code],(),time.monotonic()+(.2 if mode=='timeout' else 10))
    exitcode,raw,count,digest,problem=result
    assert children[0].poll() is not None and children[0].stdout.closed and children[0].stderr.closed
    if mode=='timeout':assert exitcode<0 and problem=='deadline'
    elif mode=='bound':assert problem=='bound' and raw==b''
    else:assert exitcode==(2 if mode=='failure' else 0) and problem is None and count==(15 if mode=='stderr' else 0)


@pytest.mark.parametrize('mode',['launch','worker','validate'])
def test_parent_worker_and_reader_actual_alarms_and_preflight(monkeypatch,mode):
    selected=args();argv=[str(m.SOURCE),mode,'--expected-head',selected.expected_head,'--caller-sha256',selected.caller_sha256,'--profile-sha256',selected.profile_sha256]
    if mode=='worker':argv+=['--intent-fd','3','--outer-deadline',repr(time.monotonic()+89)]
    if mode=='validate':argv+=['--actual-parent-exit','2']
    order=[];monkeypatch.setattr(m.sys,'argv',argv);monkeypatch.setattr(m,'ENTRY_DEADLINE',time.monotonic()+149)
    monkeypatch.setattr(m.signal,'signal',lambda *a:None);monkeypatch.setattr(m.signal,'setitimer',lambda *a:order.append(('alarm',a[1])))
    monkeypatch.setattr(m,'parent',lambda *a:{'mode':'launch'});monkeypatch.setattr(m,'worker',lambda *a:{'mode':'worker'})
    monkeypatch.setattr(m,'preflight',lambda *a:order.append(('preflight',None)))
    monkeypatch.setattr(m,'bootstrap',lambda *a:(order.append(('bootstrap',None)) or {}))
    monkeypatch.setattr(m.sys,'stdin',NS(buffer=io.BytesIO(b'synthetic')))
    monkeypatch.setattr(m,'validate_parent_output',lambda *a:{'mode':'validate'})
    assert m.main()=={'mode':mode} and order[0][0]=='alarm' and 0<order[0][1]<=(30 if mode=='validate' else 90 if mode=='worker' else 150)
    if mode=='validate':assert [item[0] for item in order]==['alarm','preflight','bootstrap']


def test_CLI_argument_failure_no_raw_argument_traceback_or_unknown_global():
    child=subprocess.run([sys.executable,'-I','-B',str(m.SOURCE),'launch','--PRIVATE-ARGUMENT'],cwd=m.ROOT,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    assert child.returncode==2 and not child.stderr and b'PRIVATE-' not in child.stdout
    assert m.parse(child.stdout,10000)['failure_code']=='arguments'


def test_native_scope_exact3DATA_no_Jtransport_G_F_original_archive_or_oldcontrols():
    policy=m.native_profile()
    assert set(m.DATA_PLAN)=={'events','ownership','dictionary'}
    assert all(str(m.ROOT/value['relative_path']) in policy for value in m.DATA_PLAN.values())
    for text in ('(deny network*)','/Volumes','/Library/Keychains','/usr/bin/security','[.]pyc$'):assert text in policy
    for text in ('01-tickers-years-full.zip','R335-20261103-J/transport','R335-20261103-G','R335-20261103-F','R336-20261103-M/report'):assert text not in policy


def test_held_source_and_Store_policy_is_copied_proven_M_with_only_new_marker_name():
    old=ast.parse((m.ROOT/'scripts/inspect_arv2_r336_original_identity_ownership.py').read_bytes());new=ast.parse(m.SOURCE.read_bytes())
    get=lambda tree,name:next(node for node in tree.body if isinstance(node,(ast.ClassDef,ast.FunctionDef)) and node.name==name)
    for name in ('HeldFile','preflight','meta','binding','safe_env'):
        assert ast.dump(get(old,name),include_attributes=False)==ast.dump(get(new,name),include_attributes=False),name
    old_store=copy.deepcopy(get(old,'Store'));new_store=get(new,'Store')
    for node in ast.walk(old_store):
        if isinstance(node,ast.Tuple) and [x.value for x in node.elts if isinstance(x,ast.Constant)]==['claim.json','private-diagnosis.json','report.json','failure.json']:
            node.elts.insert(1,ast.Constant('worker-started.json'))
    assert ast.dump(old_store,include_attributes=False)==ast.dump(new_store,include_attributes=False)


@pytest.mark.parametrize('change',['profile','head','source','platform','isolated','dirty'])
def test_preflight_exact_clean_host_HEAD_self_source_and_profile(tmp_path,monkeypatch,change):
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


def test_parent_source_context_closes_normally_before_returned_output(monkeypatch):
    order=[]
    class PublicSources:
        def __enter__(self):return self
        def __exit__(self,*a):order.append('source_normal_return')
    def boot(role,stack,deadline):stack.enter_context(PublicSources());return {}
    monkeypatch.setattr(m,'preflight',lambda *a:None);monkeypatch.setattr(m,'bootstrap',boot)
    monkeypatch.setattr(m,'_parent_bound',lambda *a:(order.append('bounded_child_return') or {'synthetic':'public'}))
    assert m.parent(args())=={'synthetic':'public'}
    assert order==['bounded_child_return','source_normal_return']


@pytest.mark.parametrize('role',['worker','validate'])
def test_fresh_selected_source_byte_bootstrap_closure_no_repo_pyc_oldcaller_or_Keychain(role):
    code="""from scripts import inspect_arv2_r336_action_semantics as m
from contextlib import ExitStack
import sys,time
with ExitStack() as stack:
 modules=m.bootstrap(ROLE,stack,time.monotonic()+149)
 assert set(modules)==({'security','pure','guard'} if ROLE=='worker' else {'security','pure'})
 assert modules['pure'].FINITE==m.PURE_CODES
 assert m.pin(m.canonical(modules['pure'].profile_record()))==m.PURE_PROFILE_PIN
 assert modules['pure'].profile_record()['maximum_seconds']==150
 for name in ('arv2_relocation_security','arv2_r336_original_identity_ownership','arv2_r336_action_semantics'):
  module=sys.modules['scripts.'+name]
  assert module.__spec__.loader is None and getattr(module,'__cached__',None) is None
 assert not any(name.startswith(('scripts.run_arv2_r335','scripts.inspect_arv2_r335','scripts.inspect_arv2_r336_original')) for name in sys.modules)
 assert 'scripts.arv2_keychain_connections' not in sys.modules
 assert 'scripts.arv2_r335_action_types' not in sys.modules
""".replace('ROLE',repr(role))
    child=subprocess.run([sys.executable,'-I','-B','-c','import sys;sys.path.insert(0,'+repr(str(m.ROOT))+');'+code],cwd=m.ROOT,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    assert child.returncode==0 and not child.stdout and not child.stderr


def test_selected_dependency_pins_profile_and_exact_public_import_closure():
    for name,expected in m.SOURCE_PINS.items():assert m.sha((m.ROOT/name).read_bytes())==expected
    tree=ast.parse(m.SOURCE.read_bytes())
    assert not any(isinstance(node,ast.ImportFrom) and (node.module or '').startswith(('scripts.','research.')) for node in ast.walk(tree))
    assert set(m.SOURCE_PINS)=={'scripts/arv2_relocation_security.py','scripts/arv2_r298_fixed_data_guard.py',
        'scripts/arv2_r336_original_identity_ownership.py','scripts/arv2_r336_action_semantics.py'}
    profile=m.profile_record();assert profile['pure_profile_pin']==m.PURE_PROFILE_PIN
    assert profile['native_worker_policy_sha256']==m.sha(m.native_profile().encode())
