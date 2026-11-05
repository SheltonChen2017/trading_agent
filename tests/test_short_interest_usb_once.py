"""Finite envelope on fabricated four inputs; no actual Root/USB window."""
import ast
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import qualify_short_interest_usb_once as q

REPOSITORY=Path(__file__).resolve().parents[1]
REAL_RUN,REAL_POPEN=subprocess.run,subprocess.Popen
spec=importlib.util.spec_from_file_location('usb_once_original_profile_support',Path(__file__).with_name('test_short_interest_usb_code_snapshot.py'))
support=importlib.util.module_from_spec(spec);sys.modules[spec.name]=support;spec.loader.exec_module(support)
fixture=support.fixture
HEAD,REMOTE=support.HEAD,support.REMOTE


@pytest.fixture
def prepared(fixture,monkeypatch):
    h=fixture;hooks=[];helper=(REPOSITORY/q.HELPER).read_bytes()
    helper=support.replace_assignments(helper,{'ROOT':'Path('+repr(str(h.root))+')'})
    own=(REPOSITORY/q.DRIVER).read_bytes()
    for name,raw in ((q.HELPER,helper),(q.DRIVER,own)):
        (h.root/name).write_bytes(raw);h.committed[name]=raw
    # Actual sealed report class/guard/getter/registry, with one explicitly
    # fabricated tiny-pair producer. No actual archive/model scan is performed.
    model=(REPOSITORY/h.module.MODEL).read_bytes();tree=ast.parse(model)
    replacement=ast.parse("def inspect_registered_pair(**blobs):\n import sys\n sys._si_usb_fixture_hook('model')\n return _seal({'scope':'fabricated_pair'})\n").body[0]
    tree.body=[replacement if isinstance(node,ast.FunctionDef) and node.name=='inspect_registered_pair' else node for node in tree.body]
    model=(ast.unparse(ast.fix_missing_locations(tree))+'\n').encode()
    (h.root/h.module.MODEL).write_bytes(model);h.committed[h.module.MODEL]=model
    monkeypatch.setattr(q,'ROOT',h.root);monkeypatch.setattr(q,'USB',h.usb);monkeypatch.setattr(q,'INPUTS',h.module.INPUTS)
    monkeypatch.setattr(q,'_USED',False);monkeypatch.setattr(q,'_BOOTSTRAP_START_NS',q.time.monotonic_ns(),raising=False)
    monkeypatch.setattr(q,'_ADD_AUDIT',hooks.append)  # Test-only hook registration; permanent hook tested in an isolated child below.
    h.hooks=hooks;h.own_sha=q.digest(own);h.run=lambda:q.run_registered(HEAD,REMOTE,h.own_sha)
    return h


def test_genuine_full_profile_reads_fake_four_closes_and_never_grants_source_authority(prepared):
    h=prepared;value=h.run()
    assert value['status']=='closed_finite_offline_byte_inspection',value
    assert h.model_seen and value['original_profile_proof']['all_source_contexts_closed'] is True
    assert value['source_qualified'] is False and value['first_failure'] is None and not value['cleanup_failures']
    assert not any(value['denials'].values()) and len(h.hooks)==1
    assert value['code_manifest_sha256']==q.digest(q.canonical({name:q.digest(h.committed[name]) for name in q.CODE_FILES}))
    assert all(value is False or type(value) is int and value==0 for key,value in value['authority'].items() if key!='finite_offline_byte_inspection_only')
    aggregate=value['private_model_aggregate']
    assert q.digest(q.canonical(aggregate))==value['original_profile_proof']['inspection_report_sha256']
    assert aggregate['authority']['source_admitted'] is False
    assert 'fabricated-full' not in json.dumps(value) and 'row_reason_counts' not in json.dumps(value)
    assert not any(name in sys.modules for name in q._MODULES)


def test_copied_original_profile_dict_is_not_an_original_factory_result(prepared,monkeypatch):
    original=q._original_result
    monkeypatch.setattr(q,'_original_result',lambda module,value,*pins:original(module,dict(value),*pins))
    result=prepared.run();assert result['status']=='incomplete' and result['first_failure']['code']=='original_result'


def test_replacement_factory_cannot_manufacture_the_accepted_original_frame(prepared,monkeypatch):
    validator=q._original_result
    def replace(module,value,entry,entry_code):
        module._test_prior=value
        exec("def replacement():\n state={'first':None,'later':[],'truncated':False}\n result=dict(_test_prior)\n _RUNS[:]=[(None,state,sys._getframe())]\n return result\n",module.__dict__)
        module.inspect_registered=module.replacement
        return validator(module,module.replacement(),entry,entry_code)
    monkeypatch.setattr(q,'_original_result',replace)
    result=prepared.run();assert result['status']=='incomplete' and result['first_failure']['code']=='original_result'


def test_original_source_metadata_drift_stays_a_refusal_without_rebaseline(prepared):
    h=prepared
    def change(h):
        path=h.usb/'full.literal';info=path.stat();os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns+1))
    h.action=change;result=h.run()
    assert result['status']=='incomplete' and result['first_failure']['phase'] in ('source_audit','source_after_close','source_close')
    assert result['original_profile_proof'] is result['private_model_aggregate'] is None and result['source_qualified'] is False


@pytest.mark.parametrize('name',[q.HELPER,q.DRIVER])
def test_extra_code_original_leaf_stamp_drift_vetoes_even_after_full_original_profile(prepared,name):
    h=prepared
    def change(h):
        path=h.root/name;info=path.stat();os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns+1000000))
    h.action=change;result=h.run()
    assert result['status']=='incomplete' and result['first_failure']['code']=='code_changed'
    assert result['private_model_aggregate'] is not None and result['source_qualified'] is False


def test_final_extra_code_descriptor_close_failure_is_negative(prepared,monkeypatch):
    h=prepared;close=os.close;key=(h.root/q.DRIVER).stat().st_ino;failed=[False]
    def closing(fd):
        selected=os.fstat(fd).st_ino==key;close(fd)
        if selected and not failed[0]:failed[0]=True;raise OSError('PRIVATE close failure')
    monkeypatch.setattr(os,'close',closing);result=h.run()
    assert result['status']=='incomplete' and result['first_failure']['phase']=='cleanup'
    assert result['private_model_aggregate'] is not None and result['source_qualified'] is False
    assert 'PRIVATE' not in json.dumps(result)


def test_authentication_failure_preserves_primary_and_independent_close_failure(prepared,monkeypatch):
    h=prepared;git=q._git;close=os.close;closed=[]
    def fail(arguments,start):
        if arguments[0]=='show':raise q.UsbOnceRefusal('code')
        return git(arguments,start)
    def closing(fd):
        close(fd);closed.append(fd);raise OSError('PRIVATE cleanup')
    monkeypatch.setattr(q,'_git',fail);monkeypatch.setattr(os,'close',closing)
    result=h.run()
    assert result['status']=='incomplete' and result['first_failure']['code']=='code'
    assert len(closed)==len(result['cleanup_failures'])==1
    assert result['cleanup_failures'][0]['phase']=='cleanup' and 'PRIVATE' not in json.dumps(result)


def test_copied_private_report_and_replaced_registry_cannot_replace_original_source_report(prepared,monkeypatch):
    reader=q._private_aggregate
    def copy(module,proof):
        graph=module._RUNS[0][2].f_locals['graph'];model=graph.model
        value,anchor=next(iter(model._ISSUED.values()));copied=object.__new__(type(value))
        for name in ('_raw','_sha','_anchor','_identity'):object.__setattr__(copied,name,getattr(value,name))
        model._ISSUED.clear();model._ISSUED[id(copied)]=(copied,anchor)
        return reader(module,proof)
    monkeypatch.setattr(q,'_private_aggregate',copy);result=prepared.run()
    assert result['status']=='incomplete' and result['first_failure']['code']=='private_aggregate'
    assert result['private_model_aggregate'] is None and result['source_qualified'] is False


@pytest.mark.parametrize('change',['guard','getter','registry','policy','hash'])
def test_original_private_model_bindings_cannot_be_replaced_after_graph_cleanup(prepared,monkeypatch,change):
    reader=q._private_aggregate
    def substitute(module,proof):
        graph=module._RUNS[0][2].f_locals['graph'];model=graph.model
        if change=='guard':model.FirstRateByteInspection._guard=lambda self:None
        elif change=='getter':model.FirstRateByteInspection.to_payload=lambda self:{}
        elif change=='registry':model._ISSUED=dict(model._ISSUED)
        elif change=='policy':model.inspection_policy=lambda:{}
        else:graph.hashing.hash_payload=lambda value:'0'*64
        return reader(module,proof)
    monkeypatch.setattr(q,'_private_aggregate',substitute);result=prepared.run()
    assert result['status']=='incomplete' and result['private_model_aggregate'] is None
    assert result['source_qualified'] is False


def test_private_aggregate_digest_must_match_immutable_original_inspected_tuple(prepared,monkeypatch):
    reader=q._private_aggregate
    def rebase(module,proof):
        graph=module._RUNS[0][2].f_locals['graph'];model=graph.model
        value,anchor=next(iter(model._ISSUED.values()));payload=json.loads(value._raw)
        payload['scope']='PRIVATE fake replacement';raw=q.canonical(payload);replacement=(raw,q.digest(raw))
        for key,item in (('_raw',raw),('_sha',replacement[1]),('_anchor',replacement),('_identity',replacement)):
            object.__setattr__(value,key,item)
        model._ISSUED[id(value)]=(value,replacement);proof['inspection_report_sha256']=replacement[1]
        return reader(module,proof)
    monkeypatch.setattr(q,'_private_aggregate',rebase);result=prepared.run()
    assert result['status']=='incomplete' and result['first_failure']['code']=='private_aggregate'
    assert result['private_model_aggregate'] is None and 'PRIVATE' not in json.dumps(result)


def test_private_aggregate_bound_is_not_an_admission_or_truncation_route(prepared,monkeypatch):
    monkeypatch.setattr(q,'MAX_PRIVATE_AGGREGATE',1);result=prepared.run()
    assert result['status']=='incomplete' and result['first_failure']['code']=='private_aggregate'
    assert result['private_model_aggregate'] is None and result['source_qualified'] is False


def test_closed_shared_pipe_classifier_cannot_be_substituted(prepared,monkeypatch):
    h=prepared;assert h.run()['status']=='closed_finite_offline_byte_inspection'
    with pytest.raises(q.UsbOnceRefusal,match='forbidden_open'):h.hooks[0]('open',(99,'r',os.O_RDONLY))


@pytest.mark.parametrize('change',['predicate','predicate_code','REF','CODE_FILES','DRIVER','ENV_value','ENV_object','ROOT_object'])
def test_shared_git_predicate_and_exact_policy_globals_cannot_be_rebased(prepared,change):
    h=prepared;assert h.run()['status']=='closed_finite_offline_byte_inspection'
    audit=h.hooks[0];cells=dict(zip(audit.__code__.co_freevars,audit.__closure__));binding=cells['original_helper'].cell_contents
    helper=dict(zip(binding.__code__.co_freevars,binding.__closure__))['helper'].cell_contents
    arguments=['rev-parse','HEAD']
    if change=='predicate':helper._git_allowed=lambda *args:True;arguments=['fetch']
    elif change=='predicate_code':helper._git_allowed.__code__=(lambda *args:True).__code__;arguments=['fetch']
    elif change=='REF':helper.REF='refs/heads/fabricated';arguments=['ls-remote','--exit-code','--refs','origin',helper.REF]
    elif change=='CODE_FILES':helper.CODE_FILES=(*helper.CODE_FILES,'fabricated.py');arguments=['show',HEAD+':fabricated.py']
    elif change=='DRIVER':helper.DRIVER='fabricated.py';arguments=['show',HEAD+':fabricated.py']
    elif change=='ENV_value':helper.ENV['GIT_OPTIONAL_LOCKS']='1'
    elif change=='ENV_object':helper.ENV=dict(helper.ENV)
    else:helper.ROOT=Path(str(helper.ROOT))
    with pytest.raises(q.UsbOnceRefusal,match='forbidden_subprocess'):
        audit('subprocess.Popen',('git',['git',*arguments],str(h.root),dict(q.ENV)))
    with pytest.raises(q.UsbOnceRefusal,match='forbidden_open'):audit('open',(99,'r',os.O_RDONLY))


@pytest.mark.parametrize('replacement',[False,True])
def test_original_producer_environment_identity_and_contents_cannot_change(prepared,monkeypatch,replacement):
    h=prepared;assert h.run()['status']=='closed_finite_offline_byte_inspection'
    if replacement:monkeypatch.setattr(q,'ENV',dict(q.ENV))
    else:monkeypatch.setitem(q.ENV,'GIT_OPTIONAL_LOCKS','1')
    with pytest.raises(q.UsbOnceRefusal,match='forbidden_subprocess'):
        h.hooks[0]('subprocess.Popen',('git',['git','rev-parse','HEAD'],str(h.root),dict(q.ENV)))
    with pytest.raises(q.UsbOnceRefusal,match='forbidden_open'):h.hooks[0]('open',(99,'r',os.O_RDONLY))


def test_unregistered_input_name_or_blob_cannot_be_opened_by_python_audit(prepared):
    h=prepared;value=h.run();assert value['status']=='closed_finite_offline_byte_inspection'
    with pytest.raises(q.UsbOnceRefusal):h.hooks[0]('open',('/Volumes/PRIVATE/other.zip','r',os.O_RDONLY))
    assert 'PRIVATE' not in json.dumps(value)


def test_repeated_invocation_and_bad_identifier_do_not_restart_the_original_profile(prepared):
    h=prepared;assert h.run()['status']=='closed_finite_offline_byte_inspection'
    again=h.run();assert again['status']=='incomplete' and again['first_failure']['code']=='attempt_spent'


def test_bad_arguments_are_not_echoed(prepared,capsys):
    assert q.main(['PRIVATE/secret',REMOTE,prepared.own_sha])==2
    value=json.loads(capsys.readouterr().out)
    assert value['status']=='incomplete' and value['runtime_head'] is value['driver_sha256'] is None
    assert 'PRIVATE' not in json.dumps(value)


def test_same_original_whole_deadline_covers_final_serialization(prepared,monkeypatch,capsys):
    h=prepared;value=h.run();monkeypatch.setattr(q,'run_registered',lambda *args:value)
    monotonic=q.time.monotonic_ns;calls=[0];canonical=q.canonical
    def encode(value):
        raw=canonical(value);calls[0]+=1
        if calls[0]==1:monkeypatch.setattr(q.time,'monotonic_ns',lambda:10**30)
        return raw
    monkeypatch.setattr(q,'canonical',encode)
    try:assert q.main([HEAD,REMOTE,h.own_sha])==2
    finally:monkeypatch.setattr(q.time,'monotonic_ns',monotonic)
    assert json.loads(capsys.readouterr().out)['status']=='incomplete'


def test_original_five_and_shared_helper_production_bytes_are_not_modified_by_this_unit():
    assert len(q.CODE_FILES)==len(set(q.CODE_FILES))==7 and q.MAX_SECONDS==180
    assert q.HELPER not in q.ORIGINAL_FILES and q.DRIVER not in q.ORIGINAL_FILES
    assert 'helper.run_registered(' not in (REPOSITORY/q.DRIVER).read_text()


@pytest.mark.parametrize('substitute',[False,True])
def test_isolated_permanent_audit_full_profile_and_real_stdlib_pipes_on_fake_four(prepared,monkeypatch,substitute):
    h=prepared;payload={'root':str(h.root),'usb':str(h.usb),'head':HEAD,'remote':REMOTE,
        'inputs':h.module.INPUTS,'sha':h.own_sha,'substitute':substitute,'bodies':{name:base64.b64encode(raw).decode() for name,raw in h.committed.items()}}
    child='''import base64,json,os,sys,time,types,threading
from pathlib import Path
p=json.loads(sys.stdin.read());bodies={name:base64.b64decode(raw) for name,raw in p['bodies'].items()};root=Path(p['root']);os.chdir(root)
# Explicit shared-host fixture ancestry; all owned code/input metadata stays real.
fs,st,ls=os.fstat,os.stat,os.lstat;shared={}
for parent in root.parent.parents:
 info=ls(parent);shared[(info.st_dev,info.st_ino)]=info
def common(info):return shared.get((info.st_dev,info.st_ino),info)
os.fstat=lambda fd:common(fs(fd));os.stat=lambda path,*a,**kw:common(st(path,*a,**kw));os.lstat=lambda path,*a,**kw:common(ls(path,*a,**kw))
m=types.ModuleType('_usb_once_actual_audit');m.__file__=str(root/'scripts/qualify_short_interest_usb_once.py');sys.modules[m.__name__]=m
exec(compile(bodies['scripts/qualify_short_interest_usb_once.py'],m.__file__,'exec'),m.__dict__)
m.ROOT=root;m.USB=Path(p['usb']);m.INPUTS=tuple(tuple(row) for row in p['inputs']);m._BOOTSTRAP_START_NS=time.monotonic_ns();launches=[];writers=[]
def reply(args):
 if args[0]=='show':return bodies[args[1].split(':',1)[1]]
 if args==['rev-parse','--show-toplevel']:return str(root).encode()
 if args==['branch','--show-current']:return b'codex/strategy-short-interest'
 if args==['rev-parse','HEAD']:return p['head'].encode()
 if args[0]=='status':return b''
 if args[0]=='ls-remote':return (p['remote']+'\\trefs/heads/codex/strategy-short-interest').encode()
 return p['remote'].encode()
def execute(self,args,executable,preexec_fn,close_fds,pass_fds,cwd,env,startupinfo,creationflags,shell,p2cread,p2cwrite,c2pread,c2pwrite,errread,errwrite,*tail):
 sys.audit('subprocess.Popen',args[0],args,cwd,env);launches.append(args);raw=reply(args[1:])
 def write():
  try:
   offset=0
   while offset<len(raw):offset+=os.write(c2pwrite,raw[offset:])
  finally:os.close(c2pwrite);os.close(errwrite)
 thread=threading.Thread(target=write,daemon=True);writers.append(thread);thread.start();self.pid=424242;self.returncode=0;self._closed_child_pipe_fds=True
m.subprocess.Popen._execute_child=execute
sys._si_usb_fixture_hook=lambda stage:None
install=m._install_audit;installed=[None]
def installing(helper,head,state):
 audit=install(helper,head,state)
 installed[0]=len(launches)
 if p['substitute']:helper._git_allowed=lambda *args:True
 return audit
m._install_audit=installing
value=m.run_registered(p['head'],p['remote'],p['sha'])
for thread in writers:thread.join(2)
if p['substitute']:assert len(launches)==installed[0]
print(m.canonical(value).decode())
'''
    with monkeypatch.context() as patch:
        patch.setattr(subprocess,'run',REAL_RUN);patch.setattr(subprocess,'Popen',REAL_POPEN)
        value=subprocess.run(['/Users/sheltonchen/.venvs/trading_agent-py313/bin/python','-I','-S','-B','-c',child],
            input=json.dumps(payload).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env={'PATH':'/usr/bin:/bin'},timeout=30,check=False)
    assert value.returncode==0,value.stderr
    packet=json.loads(value.stdout)
    assert packet['source_qualified'] is False
    if substitute:
        assert packet['status']=='incomplete' and packet['original_profile_proof'] is None
        assert packet['denials']['forbidden_read_open_attempts']>0
    else:
        assert packet['status']=='closed_finite_offline_byte_inspection',packet
        assert not any(packet['denials'].values())
