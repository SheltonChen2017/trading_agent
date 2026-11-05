"""Instrumented original factories on fabricated code/USB; no actual source."""
import importlib.util
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import diagnose_short_interest_code_read_interval as d

spec=importlib.util.spec_from_file_location('code_interval_fabricated_support',Path(__file__).with_name('test_short_interest_usb_code_snapshot.py'))
support=importlib.util.module_from_spec(spec);sys.modules[spec.name]=support;spec.loader.exec_module(support)
fixture=support.fixture
HEAD,REMOTE=support.HEAD,support.REMOTE
REPOSITORY=Path(__file__).resolve().parents[1]
REAL_RUN,REAL_POPEN=subprocess.run,subprocess.Popen


@pytest.fixture
def prepared(fixture,monkeypatch):
    h=fixture;hooks=[];raw=(REPOSITORY/d.DRIVER).read_bytes()
    path=h.root/d.DRIVER;path.write_bytes(raw);h.committed[d.DRIVER]=raw
    monkeypatch.setattr(d,'ROOT',h.root);monkeypatch.setattr(d,'_USED',False)
    monkeypatch.setattr(d,'_BOOTSTRAP_START_NS',d.time.monotonic_ns(),raising=False)
    monkeypatch.setattr(d,'_ADD_AUDIT',hooks.append)  # Explicit test-only registration seam; no permanent pytest audit hook.
    def forbidden(*a,**kw):raise AssertionError('actual subprocess/native operation forbidden')
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    return SimpleNamespace(h=h,hooks=hooks,sha=d.digest(raw),run=lambda:d.run_registered(HEAD,REMOTE,d.digest(raw)))


def test_genuine_initial_window_closes_and_stop_precedes_first_snapshot_or_source_opcode(prepared):
    p=prepared;lines=[];prior=sys.gettrace()
    def trace(frame,event,arg):
        if event=='line' and frame.f_code.co_name in ('_issue_snapshot','_inspect_sources'):lines.append(frame.f_code.co_name)
        return trace
    try:
        sys.settrace(trace);result=p.run()
    finally:sys.settrace(prior)
    assert result['status']=='closed_initial_window_stopped_before_snapshot',result
    assert result['window']['entered'] is result['window']['original_closed'] is True
    assert result['snapshot_body_unentered'] is result['source_body_unentered'] is result['model_body_unentered'] is True
    assert result['expected_stop_before_snapshot'] and not lines and not p.h.model_seen
    assert not any(result['denials'].values()) and len(p.hooks)==1
    assert all(value is False or type(value) is int and value==0 for key,value in result['authority'].items() if key!='source_free_diagnostic_only')
    assert int(result['worker_start_monotonic_ns'])<=int(result['window']['start_monotonic_ns'])<=int(result['window']['end_monotonic_ns'])<=int(result['worker_end_monotonic_ns'])


def test_original_initial_read_refusal_is_preserved_without_snapshot_USB_or_model(prepared):
    p=prepared
    def change(h,name):
        if name=='data/__init__.py' and h.shows==12:
            target=h.root/'data';info=target.stat();os.utime(target,ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
    p.h.on_git=change;result=p.run()
    assert result['status']=='observed_original_initial_window_refusal',result
    assert result['window']['entered'] and not result['window']['original_closed']
    assert result['first_failure']['code']=='original_directory_changed' and result['first_failure']['phase']=='initial_code'
    assert result['snapshot_body_unentered'] and result['source_body_unentered'] and not p.h.model_seen


def test_failure_before_window_is_incomplete_without_claiming_unentered_bodies(prepared):
    p=prepared;p.h.committed['data/hashing.py']+=b'# changed committed bytes\n'
    result=p.run()
    assert result['status']=='incomplete' and not result['window']['entered']
    assert not result['source_body_unentered'] and not p.h.model_seen


@pytest.mark.parametrize('mutation',['short','copy','clock','caller'])
def test_short_copied_or_wrong_clock_caller_window_cannot_supply_original_witness(prepared,monkeypatch,mutation):
    p=prepared;original=d._window_witness;calls=[];prior=sys.gettrace()
    def trace(frame,event,arg):
        if event=='call' and frame.f_code.co_name=='_issue_snapshot' and frame.f_globals.get('__name__')==d.MODULE:calls.append(frame)
        return trace
    def corrupt(module,frame,value):
        row=module._WINDOWS[id(value)]
        if mutation in ('short','copy'):
            replacement=tuple(list(value[:-1] if mutation=='short' else value))
            module._WINDOWS[id(replacement)]=(replacement,*row[1:]);value=replacement
        elif mutation=='clock':
            old=module._COMMITS[id(row[2])];module._COMMITS[id(row[2])]=(old[0],object(),*old[2:])
        else:
            frame=sys._getframe();module._WINDOWS[id(value)]=(*row[:4],frame,row[5])
        return original(module,frame,value)
    monkeypatch.setattr(d,'_window_witness',corrupt)
    try:
        sys.settrace(trace);result=p.run()
    finally:sys.settrace(prior)
    assert result['status']=='incomplete' and not result['expected_stop_before_snapshot'] and not p.h.model_seen
    assert not calls  # A later snapshot barrier must not mask a missing original-window validator.


def test_original_negative_must_retain_exact_issued_stop_not_a_same_class_copy(prepared,monkeypatch):
    p=prepared;original=d._negative
    def substitute(module,error):
        row,payload=original(module,error)
        row[2]['errors'][:]=[d.StopBeforeSnapshot() if type(value) is d.StopBeforeSnapshot else value for value in row[2]['errors']]
        return row,payload
    monkeypatch.setattr(d,'_negative',substitute);result=p.run()
    assert result['status']=='incomplete' and result['first_failure']['code']=='stop_witness'


def test_profile_callback_failure_is_permanent_and_cannot_be_retried(prepared,monkeypatch):
    p=prepared
    def broken(*a):raise RuntimeError('PRIVATE /secret/account')
    monkeypatch.setattr(d,'_window_witness',broken);first=p.run();again=p.run()
    assert first['status']==again['status']=='incomplete' and len(p.hooks)==1
    assert again['first_failure']['code']=='attempt_spent' and 'PRIVATE' not in json.dumps(first)


@pytest.mark.parametrize('event,args,key',[
    ('open',('/Volumes/PRIVATE/data',None,os.O_RDONLY),'forbidden_read_open_attempts'),
    ('open',('/tmp/PRIVATE',None,os.O_WRONLY|os.O_CREAT),'python_write_attempts'),
    ('open',(str(d.ROOT/d.ORIGINAL),None,os.O_RDWR),'python_write_attempts'),  # SI-CR28-005: allowed read path
    ('socket.connect',(object(),('PRIVATE',443)),'python_socket_attempts'),
    ('subprocess.Popen',('/bin/sh',['/bin/sh','-c','PRIVATE'],None,None),'unexpected_subprocess_attempts')])
def test_independent_audit_guards_survive_expected_profiler_stop_and_exclude_raw_values(prepared,event,args,key):
    p=prepared;result=p.run();assert result['status']=='closed_initial_window_stopped_before_snapshot'
    assert not any(result['denials'].values())
    with pytest.raises(d.IntervalRefusal):p.hooks[0](event,args)
    assert result['denials']=={name:int(name==key) for name in d._DENIAL_KEYS}  # SI-CR28-005
    assert 'PRIVATE' not in json.dumps(result)


def test_wrong_helper_hash_refuses_before_profile_or_audit_registration(prepared):
    p=prepared;result=d.run_registered(HEAD,REMOTE,'0'*64)
    assert result['status']=='incomplete' and not result['window']['entered'] and not p.hooks


@pytest.mark.parametrize('mode',['API','CLI'])
def test_malformed_identifiers_never_echo_private_arguments_or_dynamic_types(prepared,capsys,mode):
    p=prepared
    if mode=='API':result=d.run_registered(Path('/PRIVATE/account/path'),REMOTE,p.sha)
    else:
        assert d.main(['PRIVATE/account',REMOTE,p.sha])==2
        result=json.loads(capsys.readouterr().out)
    assert result['status']=='incomplete' and result['first_failure']['code']=='arguments'
    assert result['runtime_head'] is result['matching_remote'] is result['helper_sha256'] is None
    assert 'PRIVATE' not in json.dumps(result) and 'PosixPath' not in json.dumps(result) and not p.hooks


def test_external_metadata_sandbox_requirement_and_ambient_Git_limit_are_explicit(prepared):
    result=prepared.run()
    assert result['external_OS_sandbox_required'] is True and result['python_audit_covers_all_metadata'] is False
    assert result['profile_instrumented'] is True and result['profile_overhead_excluded'] is False
    assert 'ambient_credential_behavior_not_proven' in result['git_scope']
    assert len(d.canonical(result))<=32768


def test_fixed_Git_allowlist_cannot_become_provider_or_other_ref_access():
    assert d._git_allowed(['show',HEAD+':'+d.ORIGINAL],HEAD)
    assert d._git_allowed(['ls-remote','--exit-code','--refs','origin',d.REF],HEAD)
    assert not d._git_allowed(['ls-remote','origin','refs/heads/other-lane'],HEAD)
    assert not d._git_allowed(['show',HEAD+':PRIVATE'],HEAD)
    assert d._safe_failure(d.IntervalRefusal('source_barrier'),'profile')['code']=='source_barrier'


def test_no_general_profiler_change_exception_survives_the_single_expected_auto_clear(prepared):
    p=prepared;result=p.run();assert result['status']=='closed_initial_window_stopped_before_snapshot'
    with pytest.raises(d.IntervalRefusal,match='profile_changed'):p.hooks[0]('sys.setprofile',())


@pytest.mark.parametrize('change',['copied_tuple','copied_stop'])
def test_auto_clear_cannot_be_issued_by_a_copied_stop_or_tuple(prepared,monkeypatch,change):
    p=prepared;assert p.run()['status']=='closed_initial_window_stopped_before_snapshot'
    hook=p.hooks[0];cells=dict(zip(hook.__code__.co_freevars,(cell.cell_contents for cell in hook.__closure__)))
    state=cells['state'];original=state['stop'];copy=tuple(list(original))
    if change=='copied_stop':copy=(d.StopBeforeSnapshot(),*original[1:]);state['stop']=copy
    state['auto_disable_permit']=copy;state['auto_disable_used']=False
    monkeypatch.setattr(sys,'getprofile',lambda:state['profile_function'])  # Explicit seam reaches issuer proof after profile equality.
    with pytest.raises(d.IntervalRefusal,match='profile_changed'):hook('sys.setprofile',())
    assert state['failed'] is True


def test_genuine_failed_Documents_comparison_projects_only_original_frame_values(prepared,monkeypatch):
    p=prepared;target=Path('/').joinpath(*p.h.root.parts[1:4]);key=d._stamp(target.stat())[:2];changed=[False]
    monkeypatch.setattr(d,'DOCUMENTS',target)
    prior_fstat,prior_stat,prior_lstat=os.fstat,os.stat,os.lstat
    def overlay(info):
        if changed[0] and (info.st_dev,info.st_ino)==key:
            values={name:getattr(info,name) for name in dir(info) if name.startswith('st_')}
            values['st_mtime_ns']+=17;values['st_ctime_ns']+=19;return SimpleNamespace(**values)
        return info
    monkeypatch.setattr(os,'fstat',lambda fd:overlay(prior_fstat(fd)))
    monkeypatch.setattr(os,'stat',lambda *a,**kw:overlay(prior_stat(*a,**kw)))
    monkeypatch.setattr(os,'lstat',lambda *a,**kw:overlay(prior_lstat(*a,**kw)))
    def change(h,name):
        if name=='data/__init__.py' and h.shows==12:changed[0]=True
    p.h.on_git=change;result=p.run()
    assert result['status']=='observed_original_initial_window_refusal',result
    assert result['documents_comparisons']
    for row in result['documents_comparisons']:
        assert row['role']=='code' and 1<=row['code_ordinal']<=5 and row['chain_ordinal']==3
        assert row['mismatching_fields']==['mtime_ns','ctime_ns']
        assert int(row['observed']['mtime_ns'])-int(row['original']['mtime_ns'])==17
        assert int(row['observed']['ctime_ns'])-int(row['original']['ctime_ns'])==19
        assert (row['target_dev'],row['target_ino'])==tuple(map(str,key))
        assert int(row['before_monotonic_ns'])<=int(row['after_monotonic_ns'])
    assert str(p.h.root) not in json.dumps(result) and not p.h.model_seen


@pytest.mark.parametrize('when,expected_phase',[(2,'post_close_compare'),(3,'post_close_named_audit')])
def test_genuine_after_close_Documents_drift_preserves_original_refusal_and_metadata(prepared,monkeypatch,when,expected_phase):
    p=prepared;target=Path('/').joinpath(*p.h.root.parts[1:4]);key=d._stamp(target.stat())[:2];changed=[False];closes=[0]
    monkeypatch.setattr(d,'DOCUMENTS',target)
    prior_fstat,prior_stat,prior_lstat,prior_close=os.fstat,os.stat,os.lstat,os.close
    code_key=d._stamp((p.h.root/'data/__init__.py').stat())[:2]
    def overlay(info):
        if changed[0] and (info.st_dev,info.st_ino)==key:
            values={name:getattr(info,name) for name in dir(info) if name.startswith('st_')}
            values['st_mtime_ns']+=23;values['st_ctime_ns']+=29;return SimpleNamespace(**values)
        return info
    def close(fd):
        selected=d._stamp(prior_fstat(fd))[:2]==code_key
        prior_close(fd)
        if selected:
            closes[0]+=1
            if closes[0]==when:changed[0]=True
    monkeypatch.setattr(os,'fstat',lambda fd:overlay(prior_fstat(fd)))
    monkeypatch.setattr(os,'stat',lambda *a,**kw:overlay(prior_stat(*a,**kw)))
    monkeypatch.setattr(os,'lstat',lambda *a,**kw:overlay(prior_lstat(*a,**kw)))
    monkeypatch.setattr(os,'close',close)
    result=p.run()
    assert result['status']=='observed_original_initial_window_refusal',result
    assert result['first_failure']['code']=='post_close_original_changed'
    rows=[row for row in result['documents_comparisons'] if row['entered_phase']==expected_phase]
    assert rows and all(row['mismatching_fields']==['mtime_ns','ctime_ns'] for row in rows)
    assert all(int(row['observed']['ctime_ns'])-int(row['original']['ctime_ns'])==29 for row in rows)
    assert not p.h.model_seen


def test_main_final_serialization_checks_same_original_deadline_and_preserves_primary(prepared,monkeypatch,capsys):
    p=prepared;result=p.run();first={'phase':'initial_code','code':'original_directory_changed'}
    result['first_failure']=first
    monkeypatch.setattr(d,'run_registered',lambda *a:result)
    monkeypatch.setattr(d,'_BOOTSTRAP_START_NS',0)
    monkeypatch.setattr(d.time,'monotonic_ns',lambda:d.MAX_SECONDS*10**9+1)
    assert d.main([HEAD,REMOTE,p.sha])==2
    packet=json.loads(capsys.readouterr().out)
    assert packet['first_failure']==first and packet['cleanup_failures'][-1]['code']=='clock'


def test_fixed_python313_can_construct_actual_stdlib_only_public_model_graph_without_source():
    interpreter='/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
    payload={name:base64.b64encode((REPOSITORY/name).read_bytes()).decode() for name in ('data/hashing.py',d.CODE_FILES[2])}
    child='''import base64,builtins,json,sys,types
assert sys.version_info[:2]==(3,13)
rows=json.loads(sys.stdin.read())
hashing=types.ModuleType('_interval_hashing');exec(compile(base64.b64decode(rows['data/hashing.py']),'public_hashing','exec'),hashing.__dict__)
original=builtins.__import__
def fixed(name,globals=None,locals=None,fromlist=(),level=0):
 if name=='data.hashing':return hashing
 return original(name,globals,locals,fromlist,level)
model=types.ModuleType('_interval_public_model');sys.modules[model.__name__]=model
model.__dict__['__builtins__']={**vars(builtins),'__import__':fixed}
exec(compile(base64.b64decode(rows['research/short_interest_etf/firstrate_short_interest_inspection.py']),'public_model','exec'),model.__dict__)
print(json.dumps({'version':list(sys.version_info[:3]),'model_constructed':True,'source_opened':False}))
'''
    result=subprocess.run([interpreter,'-I','-S','-B','-c',child],input=json.dumps(payload).encode(),
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin'},timeout=10,check=False)
    assert result.returncode==0,result.stderr
    packet=json.loads(result.stdout);assert packet['version'][:2]==[3,13] and packet['model_constructed'] and packet['source_opened'] is False


def test_permanent_real_audit_hook_and_auto_disabled_profile_work_in_isolated_fabricated_child(fixture,monkeypatch):
    h=fixture;raw=(REPOSITORY/d.DRIVER).read_bytes();(h.root/d.DRIVER).write_bytes(raw)
    bodies={**h.committed,d.DRIVER:raw}
    payload={'root':str(h.root),'head':HEAD,'remote':REMOTE,'sha':d.digest(raw),
        'bodies':{name:base64.b64encode(body).decode() for name,body in bodies.items()}}
    child='''import base64,json,os,sys,time,types
payload=json.loads(sys.stdin.read());bodies={k:base64.b64decode(v) for k,v in payload['bodies'].items()}
worker=types.ModuleType('_isolated_interval_helper');worker.__file__=payload['root']+'/scripts/diagnose_short_interest_code_read_interval.py';sys.modules[worker.__name__]=worker
exec(compile(bodies['scripts/diagnose_short_interest_code_read_interval.py'],worker.__file__,'exec'),worker.__dict__)
worker.ROOT=worker.Path(payload['root']);worker._BOOTSTRAP_START_NS=time.monotonic_ns();os.chdir(worker.ROOT)
# Named fabricated shared-host ancestry, matching the parent fixture. Owned
# code/fixture directories retain real metadata and every original predicate.
original_fstat,original_stat,original_lstat=os.fstat,os.stat,os.lstat
shared={}
for parent in worker.ROOT.parent.parents:
 info=original_lstat(parent);shared[(info.st_dev,info.st_ino)]=info
def common(info):return shared.get((info.st_dev,info.st_ino),info)
os.fstat=lambda fd:common(original_fstat(fd))
os.stat=lambda path,*a,**kw:common(original_stat(path,*a,**kw))
os.lstat=lambda path,*a,**kw:common(original_lstat(path,*a,**kw))
def git(argv,**kwargs):
 args=argv[1:]
 if args[0]=='show':raw=bodies[args[1].split(':',1)[1]]
 elif args==['rev-parse','--show-toplevel']:raw=payload['root'].encode()
 elif args==['branch','--show-current']:raw=b'codex/strategy-short-interest'
 elif args==['rev-parse','HEAD']:raw=payload['head'].encode()
 elif args[0]=='status':raw=b''
 elif args[0]=='ls-remote':raw=(payload['remote']+'\\trefs/heads/codex/strategy-short-interest').encode()
 else:raw=payload['remote'].encode()
 return types.SimpleNamespace(returncode=0,stdout=raw,stderr=b'')
worker.subprocess.run=git
profile_events=[]
def add_audit(hook):
 cells=dict(zip(hook.__code__.co_freevars,(cell.cell_contents for cell in hook.__closure__)))
 def observing(event,args):
  if event=='sys.setprofile':profile_events.append({'controlled':cells['state']['profile_change_allowed'],'stop_issued':cells['state']['stop'] is not None})
  hook(event,args)
 sys.addaudithook(observing)
worker._ADD_AUDIT=add_audit
def forbidden(stage):raise AssertionError('model opcode reached')
sys._si_usb_fixture_hook=forbidden
result=worker.run_registered(payload['head'],payload['remote'],payload['sha'])
result['test_profile_events']=profile_events
print(worker.canonical(result).decode())
'''
    with monkeypatch.context() as patch:
        patch.setattr(subprocess,'run',REAL_RUN);patch.setattr(subprocess,'Popen',REAL_POPEN)
        result=subprocess.run(['/Users/sheltonchen/.venvs/trading_agent-py313/bin/python','-I','-S','-B','-c',child],
            input=json.dumps(payload).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env={'PATH':'/usr/bin:/bin'},timeout=20,check=False)
    assert result.returncode==0,result.stderr
    packet=json.loads(result.stdout)
    assert packet['status']=='closed_initial_window_stopped_before_snapshot',json.dumps(packet,sort_keys=True)
    assert not any(packet['denials'].values()) and packet['source_body_unentered']
    assert packet['test_profile_events']==[{'controlled':True,'stop_issued':False},
        {'controlled':False,'stop_issued':True},{'controlled':True,'stop_issued':True}]


def test_actual_local_Git_metadata_uses_owned_readonly_pipe_wrappers_under_permanent_audit():
    """Local rev-parse only; no original window, source, provider or remote read."""
    raw=(REPOSITORY/d.DRIVER).read_bytes();payload={'raw':base64.b64encode(raw).decode()}
    child='''import base64,json,sys,time,types
p=json.loads(sys.stdin.read());m=types.ModuleType('_local_git_audit');m.__file__='public_helper';sys.modules[m.__name__]=m
exec(compile(base64.b64decode(p['raw']),'public_helper','exec'),m.__dict__)
state={'failed':False,'own_failure':None,'window_frame':None,'profile_change_allowed':False,'auto_disable_permit':None,'profile_function':None,'original_module':None,'auto_disable_used':False,'stop':None,'denials':{key:0 for key in m._DENIAL_KEYS}}
m._install_denials('a'*40,state)
value=m._git(['rev-parse','HEAD'],'a'*40,time.monotonic_ns())
print(json.dumps({'head':value.decode().strip(),'denials':state['denials'],'first':state['own_failure']}))
'''
    expected=REAL_RUN(['git','rev-parse','HEAD'],cwd=REPOSITORY,env={'PATH':'/usr/bin:/bin'},
        stdin=None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,check=False)
    assert expected.returncode==0
    result=REAL_RUN(['/Users/sheltonchen/.venvs/trading_agent-py313/bin/python','-I','-S','-B','-c',child],
        input=json.dumps(payload).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=REPOSITORY,
        env={'PATH':'/usr/bin:/bin'},timeout=10,check=False)
    assert result.returncode==0,result.stderr
    packet=json.loads(result.stdout)
    assert packet['head']==expected.stdout.decode().strip()
    assert packet['first'] is None and not any(packet['denials'].values())


def production_public_fixture(tmp_path):
    """Original model/hash/reader bodies; only the fifth's fixture ROOT/policy vary."""
    root=(tmp_path/'public-lane').resolve();root.mkdir()
    bodies={name:(REPOSITORY/name).read_bytes() for name in (*d.CODE_FILES,d.DRIVER)}
    profile=support.replace_assignments(bodies[d.ORIGINAL],{'ROOT':'Path('+repr(str(root))+')','PROFILE_SHA256':repr('PENDING')})
    from types import ModuleType
    seed=ModuleType('_public_profile_seed');exec(compile(profile,str(root/d.ORIGINAL),'exec'),seed.__dict__)
    bodies[d.ORIGINAL]=support.replace_assignments(profile,{'PROFILE_SHA256':repr(seed._hash(seed.policy()))})
    for name,raw in bodies.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    return root,bodies


PUBLIC_GRAPH_CHILD='''import base64,json,os,sys,time,types,threading
p=json.loads(sys.stdin.read());bodies={name:base64.b64decode(raw) for name,raw in p['bodies'].items()};root=p['root'];mode=p['mode'];os.chdir(root)
# Test-only frozen SHARED host ancestors; fixture-owned directories/files stay real.
from pathlib import Path
fstat,stat,lstat=os.fstat,os.stat,os.lstat
shared={}
for parent in Path(root).parent.parents:
 info=lstat(parent);shared[(info.st_dev,info.st_ino)]=info
def common(info):return shared.get((info.st_dev,info.st_ino),info)
os.fstat=lambda fd:common(fstat(fd));os.stat=lambda path,*a,**kw:common(stat(path,*a,**kw));os.lstat=lambda path,*a,**kw:common(lstat(path,*a,**kw))
m=types.ModuleType('_production_interval_helper');m.__file__=root+'/scripts/diagnose_short_interest_code_read_interval.py';sys.modules[m.__name__]=m
exec(compile(bodies['scripts/diagnose_short_interest_code_read_interval.py'],m.__file__,'exec'),m.__dict__)
m.ROOT=Path(root);m._BOOTSTRAP_START_NS=time.monotonic_ns();launches=[];writers=[]
def reply(args):
 if args[0]=='show':return bodies[args[1].split(':',1)[1]]
 if args==['rev-parse','--show-toplevel']:return root.encode()
 if args==['branch','--show-current']:return b'codex/strategy-short-interest'
 if args==['rev-parse','HEAD']:return p['head'].encode()
 if args[0]=='status':return b''
 if args[0]=='ls-remote':return (p['remote']+'\\trefs/heads/codex/strategy-short-interest').encode()
 return p['remote'].encode()
def execute(self,args,executable,preexec_fn,close_fds,pass_fds,cwd,env,startupinfo,creationflags,shell,p2cread,p2cwrite,c2pread,c2pwrite,errread,errwrite,*tail):
 sys.audit('subprocess.Popen',args[0],args,cwd,env);launches.append(tuple(args));raw=reply(args[1:])
 def write():
  try:
   offset=0
   while offset<len(raw):offset+=os.write(c2pwrite,raw[offset:])
  finally:
   os.close(c2pwrite);os.close(errwrite)
 thread=threading.Thread(target=write,daemon=True);writers.append(thread);thread.start()
 self.pid=424242;self.returncode=0;self._closed_child_pipe_fds=True
# Real run/Popen.__init__/_get_handles/io.open/communicate are untouched.
# Only the kernel-child boundary supplies fixed PUBLIC Git responses.
m.subprocess.Popen._execute_child=execute
if mode.startswith('graph'):
 if mode=='graph_identity_drift':m._IO_OPEN=None
 result=m.run_registered(p['head'],p['remote'],m.digest(bodies[m.DRIVER]))
 result['test_kernel_launches']=len(launches)
else:
 state={'failed':False,'own_failure':None,'window_frame':None,'profile_change_allowed':False,'auto_disable_permit':None,'profile_function':None,'original_module':None,'auto_disable_used':False,'stop':None,'denials':{key:0 for key in m._DENIAL_KEYS}}
 readfd,writefd=os.pipe();regular=os.open(root+'/'+m.DRIVER,os.O_RDONLY)
 hook=m._install_denials(p['head'],state);args=['git','rev-parse','HEAD'];kwargs={'cwd':m.ROOT,'env':m.ENV,'stdin':None,'stdout':m.subprocess.PIPE,'stderr':m.subprocess.PIPE,'check':False}
 try:
  if mode=='unowned_pipe':hook('open',(readfd,'r',os.O_RDONLY))
  elif mode=='regular_fd':hook('open',(regular,'r',os.O_RDONLY))
  elif mode=='write_fd':hook('open',(writefd,'w',os.O_WRONLY))
  else:
   if mode=='other_command':args=['curl','https://PRIVATE']
   if mode=='other_git':args=['git','status','--porcelain=v1']
   if mode=='env':kwargs['env']={**m.ENV,'PRIVATE':'PRIVATE'}
   if mode=='cwd':kwargs['cwd']=m.ROOT.parent
   if mode=='role':kwargs['stdout']=regular
   if mode=='stdin':kwargs['stdin']=m.subprocess.PIPE
   if mode=='root_binding':m.ROOT=Path(str(m.ROOT))
   if mode=='constructor_identity':
    original_init=m.subprocess.Popen.__init__
    def changed_init(self,*args,**kwargs):return original_init(self,*args,**kwargs)
    m.subprocess.Popen.__init__=changed_init
   if mode=='handles_identity':
    original_handles=m.subprocess.Popen._get_handles
    def changed_handles(self,*args,**kwargs):return original_handles(self,*args,**kwargs)
    m.subprocess.Popen._get_handles=changed_handles
   m.subprocess.run(args,**kwargs)
 except m.IntervalRefusal:pass
 finally:
  for fd in (readfd,writefd,regular):os.close(fd)
 result={'denials':state['denials'],'first':state['own_failure'],'test_kernel_launches':len(launches),'failed':state['failed']}
for thread in writers:thread.join(2)
print(m.canonical(result).decode())
'''


def public_graph_child(tmp_path,mode):
    root,bodies=production_public_fixture(tmp_path)
    payload={'root':str(root),'head':HEAD,'remote':REMOTE,'mode':mode,
        'bodies':{name:base64.b64encode(raw).decode() for name,raw in bodies.items()}}
    result=REAL_RUN(['/Users/sheltonchen/.venvs/trading_agent-py313/bin/python','-I','-S','-B','-c',PUBLIC_GRAPH_CHILD],
        input=json.dumps(payload).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=REPOSITORY,
        env={'PATH':'/usr/bin:/bin'},timeout=30,check=False)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


def test_real_production_graph_and_stdlib_pipe_wrappers_with_permanent_audit(tmp_path):
    packet=public_graph_child(tmp_path,'graph')
    assert packet['status']=='closed_initial_window_stopped_before_snapshot',packet
    assert packet['window']['entered'] and packet['window']['original_closed'] and packet['source_body_unentered']
    assert packet['test_kernel_launches']>20 and not any(packet['denials'].values())


def test_first_audit_cause_precedes_later_window_veto_in_genuine_production_graph(tmp_path):
    packet=public_graph_child(tmp_path,'graph_identity_drift')
    assert packet['status']=='incomplete' and packet['window']['entered'] is False
    assert packet['first_failure']['code']=='forbidden_open' and packet['first_failure']['phase']=='bootstrap'
    assert any(row['code']=='window_witness' for row in packet['cleanup_failures'])
    assert packet['denials']['forbidden_read_open_attempts']==1 and not packet['documents_comparisons']


@pytest.mark.parametrize('mode',['unowned_pipe','regular_fd','write_fd','other_command','other_git','env','cwd','role','stdin','root_binding','constructor_identity','handles_identity'])
def test_no_generic_int_pipe_or_changed_constructor_permission(tmp_path,mode):
    packet=public_graph_child(tmp_path,mode)
    assert packet['failed'] is True and packet['test_kernel_launches']==0
    assert packet['first']['code'] in ('forbidden_open','forbidden_write')
    assert sum(packet['denials'].values())==1 and 'PRIVATE' not in json.dumps(packet)
