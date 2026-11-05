"""Fabricated owned children/metadata; never sudo/eslogger/USB/provider access."""
import ast
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import trace_short_interest_code_read_actor as t
from scripts import trace_short_interest_documents_actor as d
from scripts import diagnose_short_interest_code_read_interval as helper


HEAD,REMOTE='a'*40,'b'*40
MAPPING={name:'c'*64 for name in t.CODE_FILES}
MAPPING[t.DOCUMENTS]=t.DOCUMENTS_SHA;MAPPING[t.FRAMER]=t.FRAMER_SHA
REPO=Path(__file__).resolve().parents[1]
ORIGINAL_CONTROL_AUDIT=t.final_control_audit
_support_spec=importlib.util.spec_from_file_location('code_read_coordinator_helper_support',Path(__file__).with_name('test_short_interest_code_read_interval.py'))
_support=importlib.util.module_from_spec(_support_spec);sys.modules[_support_spec.name]=_support;_support_spec.loader.exec_module(_support)
fixture=_support.fixture
prepared=_support.prepared
_docs_spec=importlib.util.spec_from_file_location('code_read_coordinator_documents_support',Path(__file__).with_name('test_short_interest_documents_actor.py'))
_docs_support=importlib.util.module_from_spec(_docs_spec);sys.modules[_docs_spec.name]=_docs_support;_docs_spec.loader.exec_module(_docs_support)
context=_docs_support.context


def packet(status='observed_original_initial_window_refusal'):
    closed=status=='closed_initial_window_stopped_before_snapshot'
    return {'schema':'si-code-read-interval-diagnostic-v1','status':status,
        'runtime_head':HEAD,'matching_remote':REMOTE,'helper_sha256':MAPPING[t.HELPER],
        'interpreter_version':list(t.WORKER_VERSION),
        'code_manifest_sha256':t.digest(t.canonical({name:MAPPING[name] for name in (*t.CODE_FILES[:5],t.HELPER)})[:-1]),
        'authority':helper.authority(),
        'snapshot_body_unentered':True,'source_body_unentered':True,'model_body_unentered':True,
        'expected_stop_before_snapshot':closed,
        'window':{'entered':True,'original_closed':closed,'start_monotonic_ns':'10','end_monotonic_ns':'20',
            'start_unix_ns':'100','end_unix_ns':'110'},
        'worker_start_monotonic_ns':'1','worker_start_unix_ns':'91','worker_end_monotonic_ns':'21','worker_end_unix_ns':'111',
        'first_failure':None,'cleanup_failures':[],'documents_comparisons':[],
        'profile_instrumented':True,'profile_overhead_excluded':False,'external_OS_sandbox_required':True,
        'python_audit_covers_all_metadata':False,'git_scope':'original_matching_lane_metadata_environment_ambient_credential_behavior_not_proven',
        'denials':{name:0 for name in ('python_write_attempts','python_socket_attempts','forbidden_read_open_attempts','unexpected_subprocess_attempts','unexpected_source_entry_attempts')}}


class Clock:
    begin=0
    def __init__(self):self.last=0;self.failed=False
    def check(self,reserve=0):
        if self.failed:raise t.CodeReadTraceRefusal('clock')
        self.last+=100_000_000
        if self.last>t.WHOLE_NS-reserve:raise t.CodeReadTraceRefusal('clock')
        return self.last
    def remaining(self):return (t.WHOLE_NS-self.last)/1e9


class Consumer:
    first_record_ns=None;records=0;first_seq=None
    def __init__(self,world):
        self.world=world;self.issues=[];self.native_claims=SimpleNamespace(feed=lambda raw:None)
    def issue(self,code):
        if code not in self.issues:self.issues.append(code)
    def feed(self,raw):
        assert raw==b'NATIVE';self.records+=1;self.first_seq=0
        self.first_record_ns=self.world.clock.check()
        if self.world.native_issue:self.issue('fabricated_sequence_gap')
    def finish(self):
        if not self.records:self.issue('no_valid_native_records')


class Stream:
    def __init__(self,world,child,channel,number):self.world,self.child,self.channel,self.number=world,child,channel,number;self.closed=False
    def fileno(self):return self.number
    def close(self):self.closed=True;self.world.closed.append(self.number)


class Child:
    def __init__(self,world,role):
        self.world,self.role=world,role;self.pid=100 if role=='native' else 200;self.terminated=self.killed=False;self.waited=0
        self.returncode=None;self.sent=False
        self.stdout=Stream(world,self,'stdout',self.pid+1);self.stderr=Stream(world,self,'stderr',self.pid+2)
        world.streams[self.pid+1]=self.stdout;world.streams[self.pid+2]=self.stderr
    def poll(self):
        if self.returncode is not None:return self.returncode
        if self.role=='native' and self.world.early_native:return 0
        if self.role=='worker' and not self.world.worker_hang:return self.world.worker_exit
        return None
    def terminate(self):self.terminated=True;self.returncode=-15;self.world.terminations.append(self.role)
    def kill(self):self.killed=True;self.returncode=-9
    def wait(self,timeout=None):
        self.waited+=1
        value=self.poll()
        if value is None:raise subprocess.TimeoutExpired('fixed',timeout)
        return value


class Selector:
    def __init__(self,world):self.world=world;self.rows={}
    def __enter__(self):return self
    def __exit__(self,*unused):pass
    def register(self,stream,event,data):self.rows[stream]=SimpleNamespace(fileobj=stream,data=data)
    def unregister(self,stream):del self.rows[stream]
    def get_map(self):return self.rows
    def select(self,timeout):return [(key,1) for key in list(self.rows.values())]


@pytest.fixture
def world(monkeypatch):
    w=SimpleNamespace(clock=Clock(),streams={},children=[],closed=[],terminations=[],launches=[],
        native_issue=False,no_native_record=False,early_native=False,native_eof_early=False,
        worker_hang=False,worker_exit=0,worker_stderr=b'',native_stderr=b'',worker_raw=t.canonical(packet()),worker_extra=False)
    def popen(command,**kw):
        role='native' if command==('NATIVE',) else 'worker'
        if role=='worker':
            assert w.consumer.records>0 and w.consumer.first_seq==0 and not w.consumer.issues
            assert w.children[0].poll() is None
            assert kw['user']==501 and kw['group']==20 and kw['extra_groups']==[]
            assert kw['stdin'] is subprocess.DEVNULL and kw['start_new_session'] is True
            assert command[:3]==['/usr/bin/sandbox-exec','-p',t.SANDBOX]
        child=Child(w,role);w.children.append(child);w.launches.append((role,dict(kw)));return child
    def read(fd,limit):
        stream=w.streams[fd];child=stream.child
        if child.role=='native':
            if stream.channel=='stdout' and not child.sent and not w.no_native_record:
                child.sent=True;return b'NATIVE'
            if stream.channel=='stderr' and w.native_stderr:
                raw=w.native_stderr;w.native_stderr=b'';return raw
            if child.poll() is not None or w.native_eof_early:return b''
            raise BlockingIOError
        if w.worker_hang and child.poll() is None:raise BlockingIOError
        if stream.channel=='stdout':
            if not child.sent:child.sent=True;return w.worker_raw
            return b''
        if w.worker_stderr:
            raw=w.worker_stderr;w.worker_stderr=b'';return raw
        return b''
    w.consumer=Consumer(w);w.samples=[]
    w.watch=SimpleNamespace(sample=lambda name:w.samples.append(name))
    w.docs=SimpleNamespace(COMMAND=('NATIVE',),SHUTDOWN_NS=8_000_000_000,MAX_STDERR=4096,SAMPLE_NS=100_000_000)
    monkeypatch.setattr(t.subprocess,'Popen',popen);monkeypatch.setattr(t.selectors,'DefaultSelector',lambda:Selector(w))
    monkeypatch.setattr(t.os,'set_blocking',lambda *a:None);monkeypatch.setattr(t.os,'read',read)
    monkeypatch.setattr(t.os,'getpgid',lambda pid:pid)
    def killpg(pid,kind):
        child=next(child for child in w.children if child.pid==pid)
        assert child.poll() is None
        (child.terminate if kind==t.signal.SIGTERM else child.kill)()
    monkeypatch.setattr(t.os,'killpg',killpg)
    monkeypatch.setattr(t,'capture_runtime',lambda clock,original=None:tuple(range(10)))
    monkeypatch.setattr(t,'ROOT',SimpleNamespace(stat=lambda:SimpleNamespace(st_uid=501,st_gid=20)))
    return w


def observe(w):return t.observe(w.consumer,w.watch,w.clock,w.docs,HEAD,REMOTE,MAPPING,tuple(range(10)))


def test_original_refusal_is_closed_diagnostic_not_observer_failure(world):
    result=observe(world)
    assert result['first_failure'] is None and result['cleanup_failures']==[]
    assert result['actual_native_exit']==-15 and result['native_stdout_stderr_EOF'] is True
    assert result['planned_original_handle_shutdown'] is True and not world.consumer.issues
    reproduction=result['reproducer']
    assert reproduction['actual_exit']==0 and reproduction['stdout_stderr_EOF'] is True
    assert reproduction['complete_lifetime_inside_native_interval'] is True
    assert reproduction['report']['status']=='observed_original_initial_window_refusal'
    assert len(world.children)==2 and all(child.waited for child in world.children)
    assert set(world.closed)=={101,102,201,202}


def test_successful_code_window_is_stopped_before_snapshot(world):
    world.worker_raw=t.canonical(packet('closed_initial_window_stopped_before_snapshot'))
    result=observe(world)
    assert result['first_failure'] is None and not world.consumer.issues
    assert result['reproducer']['report']['snapshot_body_unentered'] is True


@pytest.mark.parametrize('setting',['no_native_record','native_issue','early_native'])
def test_no_worker_before_genuine_native_readiness(world,setting):
    setattr(world,setting,True);result=observe(world)
    assert len(world.children)==1 and result['reproducer']['pid'] is None
    assert world.consumer.issues and result['reproducer']['report'] is None


def test_no_worker_after_readiness_deadline_even_if_record_arrives(world):
    world.clock.last=20_000_000_000
    # The deadline is relative to original native start, not whole-process epoch.
    world.no_native_record=True
    result=observe(world)
    assert len(world.children)==1 and 'read_interval_readiness_unverified' in world.consumer.issues


def test_valid_native_record_with_stderr_same_batch_never_launches_worker(world):
    world.native_stderr=b'ES_NEW_CLIENT_RESULT_ERR_NOT_PERMITTED'
    result=observe(world)
    assert world.consumer.records==1 and len(world.children)==1
    assert result['reproducer']['pid'] is None and result['stderr_bytes_discarded']>0
    assert 'native_stderr_observed' in world.consumer.issues
    assert result['owner_action_required_if_termination_unknown'] is False


@pytest.mark.parametrize('change',[
    lambda w:setattr(w,'worker_exit',2),
    lambda w:setattr(w,'worker_stderr',b'PRIVATE-RAW-ERR'),
    lambda w:setattr(w,'worker_raw',w.worker_raw+b'{}'),
    lambda w:setattr(w,'worker_raw',b'x'*(t.MAX_HELPER+1)),
    lambda w:setattr(w,'worker_hang',True),
])
def test_worker_nonzero_stderr_extra_packet_bound_or_overlap_veto(world,change):
    change(world);result=observe(world)
    assert result['first_failure'] is not None or world.consumer.issues
    assert not result['reproducer']['complete_lifetime_inside_native_interval']
    assert 'PRIVATE' not in json.dumps(result)
    assert all(child.waited for child in world.children)


def test_native_pipes_EOF_before_passive_window_is_not_success(world):
    world.native_eof_early=True;result=observe(world)
    assert result['planned_original_handle_shutdown'] is False
    assert 'passive_window_not_completed' in world.consumer.issues


def test_slow_worker_is_reaped_and_EOF_drained_before_native_termination(world):
    world.worker_hang=True;result=observe(world)
    assert result['reproducer']['cancelled_in_native_shutdown_reserve'] is True
    assert result['reproducer']['stdout_stderr_EOF'] is True
    assert world.terminations.index('worker')<world.terminations.index('native')
    assert int(result['reproducer']['owned_wait_EOF_close_offset_ns'])<int(result['reproducer']['native_shutdown_offset_ns'])
    assert result['reproducer']['complete_lifetime_inside_native_interval'] is False
    assert result['planned_original_handle_shutdown'] is True


def test_clock_failure_does_not_prevent_independent_owned_cleanup(world,monkeypatch):
    original=world.consumer.feed
    def fail_after_record(raw):original(raw);world.clock.failed=True
    monkeypatch.setattr(world.consumer,'feed',fail_after_record)
    result=observe(world)
    assert result['first_failure']['code']=='clock'
    assert world.children[0].terminated and world.children[0].waited and set(world.closed)=={101,102}


def test_unknown_worker_wait_requires_owner_action_even_when_native_wait_known(world,monkeypatch):
    original=Child.wait
    def wait(child,timeout=None):
        if child.role=='worker':raise subprocess.TimeoutExpired('fixed',timeout)
        return original(child,timeout)
    monkeypatch.setattr(Child,'wait',wait)
    result=observe(world)
    assert type(result['actual_native_exit']) is int
    assert result['reproducer']['pid']==200 and result['reproducer']['actual_exit'] is None
    assert result['owner_action_required_if_termination_unknown'] is True
    assert result['reproducer']['owner_action_required_if_termination_unknown'] is True
    assert not result['reproducer']['complete_lifetime_inside_native_interval']


def test_original_worker_refusal_survives_later_native_limit_failure(world,monkeypatch):
    world.worker_exit=2;original=Child.wait
    def wait(child,timeout=None):
        value=original(child,timeout)
        if child.role=='worker':world.native_stderr=b'UNPROJECTED-NATIVE-STDERR'*200
        return value
    monkeypatch.setattr(Child,'wait',wait)
    result=observe(world)
    assert result['first_failure']['code']=='worker_exit'
    assert any(failure['code']=='native' and failure['stage']=='native_observation' for failure in result['cleanup_failures'])
    assert 'UNPROJECTED' not in json.dumps(result)


@pytest.mark.parametrize('field,value',[
    ('status','incomplete'),('runtime_head','e'*40),('matching_remote','e'*40),
    ('helper_sha256','e'*64),('snapshot_body_unentered',False),('source_body_unentered',False),
    ('model_body_unentered',False),('authority',{'source_authority':True}),
])
def test_worker_packet_rejects_wrong_lineage_or_authority(field,value):
    value_packet=packet();value_packet[field]=value
    with pytest.raises(t.CodeReadTraceRefusal):t.worker_packet(t.canonical(value_packet),HEAD,REMOTE,MAPPING)


@pytest.mark.parametrize('raw',[b'{}\n{}\n',b'{"schema":1,"schema":2}\n',b'NaN\n',b'{}',b''])
def test_worker_packet_canonical_unique_finite_single_frame(raw):
    with pytest.raises((t.CodeReadTraceRefusal,ValueError)):
        t.worker_packet(raw,HEAD,REMOTE,MAPPING)


def test_absolute_plan_complete_catalogue_and_clock_scope_no_execution(monkeypatch):
    monkeypatch.setattr(t.subprocess,'Popen',lambda *a,**kw:pytest.fail('actual child forbidden'))
    result=t.plan(HEAD,REMOTE,MAPPING);tokens=shlex.split(result['shell_command'])
    assert tokens[:4]==['cd',str(t.ROOT),'&&','/usr/bin/sudo']
    assert tokens[4:8]==['/usr/bin/python3','-I','-S','-B']
    assert result['code_mapping_sha256']==t.digest(t.canonical(MAPPING)[:-1])
    assert result['maximum_whole_seconds']==120 and result['native_seconds']==30 and result['readiness_seconds']==10
    assert result['source_authority'] is False
    compile(tokens[tokens.index('-c')+1],'<fabricated-bootstrap>','exec')
    compile(t.WORKER_BOOTSTRAP,'<fabricated-worker-bootstrap>','exec')


@pytest.mark.parametrize('change',[
    lambda m:m.pop(t.HELPER),lambda m:m.update({'PRIVATE-OTHER':'c'*64}),
    lambda m:m.update({t.DOCUMENTS:'a'*64}),lambda m:m.update({t.FRAMER:'b'*64}),
])
def test_mapping_cannot_omit_or_replace_original_observer_framer(change):
    mapping=dict(MAPPING);change(mapping)
    with pytest.raises(t.CodeReadTraceRefusal):t.plan(HEAD,REMOTE,mapping)


@pytest.mark.parametrize('mutation',[
    lambda p:p.update(authority={}),
    lambda p:p['authority'].update(source_free_diagnostic_only=1),
    lambda p:p['authority'].update(provider_HTTP=False),
    lambda p:p['authority'].update(source_admitted=0),
    lambda p:p.update(denials={}),
    lambda p:p['denials'].update(python_write_attempts=False),
    lambda p:p.update(code_manifest_sha256='f'*64),
    lambda p:p.pop('interpreter_version'),
    lambda p:p.update(interpreter_version=[3,9,6]),
    lambda p:p.update(UNREVIEWED='PRIVATE'),
    lambda p:p['window'].update(original_closed=True),
])
def test_complete_packet_requires_exact_typed_marker_counters_manifest_version_and_stop(mutation):
    value=packet();mutation(value)
    with pytest.raises(t.CodeReadTraceRefusal):t.worker_packet(t.canonical(value),HEAD,REMOTE,MAPPING)


def test_expected_worker_bootstrap_refusal_is_preserved_without_success(world):
    value={'schema':'si-code-read-worker-bootstrap-refusal-v1','status':'incomplete','source_authority':False,
        'first_failure':{'stage':'code_read','role':'code_read_worker_bootstrap','code':'code_hash','errno_name':None,'category':'local_contract_refusal'},'cleanup_failures':[]}
    world.worker_raw=t.canonical(value);world.worker_exit=2
    result=observe(world)
    assert result['reproducer']['report']==value
    assert not result['reproducer']['complete_lifetime_inside_native_interval']
    assert result['first_failure']['code']=='worker_exit'


@pytest.fixture
def bootstrap_world(monkeypatch):
    raw=b"raise AssertionError('verified body must be outside bootstrap catch')\n"
    values=dict(st_dev=1,st_ino=2,st_uid=501,st_gid=20,st_mode=0o100644,st_nlink=1,st_size=len(raw),st_mtime_ns=3,st_ctime_ns=4,st_flags=0)
    info=SimpleNamespace(**values);calls=[]
    fake=SimpleNamespace(**{name:getattr(os,name) for name in ('O_RDONLY','O_NOFOLLOW','O_CLOEXEC','O_NONBLOCK')})
    fake.geteuid=lambda:501;fake.stat=lambda *a,**k:info;fake.fstat=lambda *a:info
    fake.open=lambda *a,**k:(calls.append('open') or 77)
    fake.read=lambda *a,**k:raw;fake.close=lambda fd:calls.append('close')
    monkeypatch.setitem(sys.modules,'os',fake)
    monkeypatch.setattr(sys,'argv',['-c',HEAD,REMOTE,t.digest(raw)])
    return SimpleNamespace(raw=raw,fake=fake,calls=calls,monkeypatch=monkeypatch,info=info)


@pytest.mark.parametrize('case,expected',[
    ('hash','code_hash'),('owner','owner'),('read_errno',None),('compile',None),('close',None),
])
def test_worker_bootstrap_fixed_refusals_precede_unverified_exec(bootstrap_world,capsys,case,expected):
    w=bootstrap_world
    if case=='hash':w.monkeypatch.setattr(sys,'argv',['-c',HEAD,REMOTE,'f'*64])
    if case=='owner':w.fake.geteuid=lambda:0
    if case=='read_errno':
        def refused(*a):raise PermissionError(1,'PRIVATE exception text')
        w.fake.read=refused
    if case=='compile':
        raw=b'def :';w.info.st_size=len(raw);w.fake.read=lambda *a:raw
        w.monkeypatch.setattr(sys,'argv',['-c',HEAD,REMOTE,t.digest(raw)])
    if case=='close':
        def refused_close(fd):raise OSError(5,'PRIVATE close text')
        w.fake.close=refused_close
    with pytest.raises(SystemExit) as caught:exec(compile(t.WORKER_BOOTSTRAP,'<fabricated-bootstrap>','exec'),{})
    assert caught.value.code==2
    value=json.loads(capsys.readouterr().out)
    assert value['schema']=='si-code-read-worker-bootstrap-refusal-v1'
    assert value['first_failure']['code']==expected
    if case=='read_errno':assert value['first_failure']['errno_name']=='EPERM'
    if case=='close':assert value['cleanup_failures']
    assert 'PRIVATE' not in json.dumps(value)


def test_worker_bootstrap_verified_body_errors_are_not_double_wrapped(bootstrap_world,capsys):
    with pytest.raises(AssertionError,match='verified body must be outside'):
        exec(compile(t.WORKER_BOOTSTRAP,'<fabricated-bootstrap>','exec'),{})
    assert capsys.readouterr().out==''


def test_selected_worker_runtime_supports_original_public_model_decorator():
    # Isolated stdlib-only runtime check, no repository import or source open.
    code='from dataclasses import dataclass; import json,sys\n@dataclass(frozen=True,slots=True)\nclass V:\n x:int\nprint(json.dumps({"version":list(sys.version_info[:3]),"value":V(1).x}))'
    run=subprocess.run([t.WORKER_PYTHON,'-I','-S','-B','-c',code],stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin'},timeout=10,check=False)
    assert run.returncode==0 and run.stderr==b''
    assert json.loads(run.stdout)=={'version':list(t.WORKER_VERSION),'value':1}


def test_runtime_launcher_exact_bytes_and_original_stamp_are_not_rebased():
    clock=Clock();pin=t.capture_runtime(clock)
    assert len(pin)==10 and pin[6]==34640
    assert t.capture_runtime(clock,pin)==pin
    forged=list(pin);forged[8]+=1
    with pytest.raises(t.CodeReadTraceRefusal,match='code_stamp'):t.capture_runtime(clock,tuple(forged))


def test_mutable_venv_alias_is_never_the_executed_worker_path(monkeypatch):
    command=t.worker_command(HEAD,REMOTE,MAPPING[t.HELPER])
    assert command[3]==t.WORKER_REAL and t.WORKER_PYTHON not in command
    monkeypatch.setattr(t,'WORKER_PYTHON','/PRIVATE/replaced-alias')
    assert t.worker_command(HEAD,REMOTE,MAPPING[t.HELPER])==command


def test_documents_loader_refuses_unverified_bytes_before_exec(monkeypatch):
    called=[]
    monkeypatch.setattr(t,'ModuleType',lambda *a:called.append('constructed'))
    with pytest.raises(t.CodeReadTraceRefusal,match='code_hash'):t.load_documents(b"raise AssertionError('PRIVATE')")
    assert not called


def test_genuine_helper_factory_packet_passes_Root_parser_with_complete_six_file_mapping(prepared):
    value=prepared.run()
    assert value['status']=='closed_initial_window_stopped_before_snapshot'
    mapping=dict(MAPPING)
    mapping.update({name:helper.digest(raw) for name,raw in prepared.h.committed.items()})
    # This is the helper's actual fabricated factory result, not a hand-written
    # payload missing its true diagnostic marker or real manifest calculation.
    parsed=t.worker_packet(helper.canonical(value)+b'\n',HEAD,REMOTE,mapping)
    assert parsed==value and parsed['authority']['source_free_diagnostic_only'] is True


@pytest.fixture
def root_world(monkeypatch):
    held=tuple((name,(REPO/name).read_bytes(),tuple(range(10))) for name in t.CODE_FILES)
    mapping={name:t.digest(raw) for name,raw,pin in held};events=[]
    class RootClock(Clock):
        def __init__(self,begin=None):super().__init__();self.begin=0
    watch=SimpleNamespace(closed=True,changed=False)
    def sample(label):
        events.append(label)
        return {'protection_changed':watch.changed,'interval':label}
    watch.sample=sample
    class Output:
        def __init__(self,owner):self.closed=True
        def audit(self,*a,**kw):pass
        @staticmethod
        def pin(value):return tuple(range(5))
    documents=SimpleNamespace(Clock=RootClock,code_guard=lambda *args:b'',OutputDirectory=Output,
        make_consumer=lambda framer,w:SimpleNamespace(),_TERMINAL_CLOCK=None)
    def original(*args):
        documents.make_consumer(None,watch)
        documents.OutputDirectory(None)
        documents._TERMINAL_CLOCK=RootClock()
        return {'schema':t.SCHEMA+'-terminal','status':'closed_passive_observation',
            'source_authority':False,'first_failure':None,'cleanup_failures':[],
            'original_report_sha256':'e'*64,'original_report_stamp10_sha256':'f'*64}
    documents.root_trace=original
    monkeypatch.setattr(t,'load_documents',lambda raw:documents)
    monkeypatch.setattr(t,'_HELD_PUBLIC',held,raising=False)
    monkeypatch.setattr(t,'_BOOTSTRAP_START_NS',0,raising=False)
    monkeypatch.setattr(t.os,'geteuid',lambda:0)
    monkeypatch.setattr(t,'capture_runtime',lambda clock,original=None:tuple(range(10)))
    monkeypatch.setattr(t,'audit_code',lambda *a:events.append('final_code_audit'))
    monkeypatch.setattr(t,'final_control_audit',lambda *a:events.append('original_controls_after_final_code'))
    return SimpleNamespace(mapping=mapping,documents=documents,watch=watch,events=events)


def test_Root_terminal_follows_last_code_audit_and_original_closed_watch(root_world):
    w=root_world;result=t.root_trace(HEAD,REMOTE,w.mapping)
    assert result['status']=='closed_synchronized_code_read_observation'
    assert result['original_report_sha256']=='e'*64 and result['original_report_stamp10_sha256']=='f'*64
    assert w.events==['final_code_audit','original_controls_after_final_code','after_coordinator_code_audit_outside_native']
    assert result['coordinator_final_target_observation_outside_native']['protection_changed'] is False


@pytest.mark.parametrize('change',['target_protection','late_code_audit','unclosed_watch','bindings'])
def test_late_Root_boundaries_veto_original_provisional_success(root_world,monkeypatch,change):
    w=root_world
    if change=='target_protection':w.watch.changed=True
    elif change=='late_code_audit':
        def late(clock,*unused):clock.failed=True;clock.check()
        monkeypatch.setattr(t,'audit_code',late)
    elif change=='unclosed_watch':w.watch.closed=False
    elif change=='bindings':
        original=w.documents.root_trace
        def drift(*args):
            value=original(*args);w.documents.observe=lambda *a:None;return value
        w.documents.root_trace=drift
    result=t.root_trace(HEAD,REMOTE,w.mapping)
    assert result['status']=='incomplete' and result['source_authority'] is False
    assert result['first_failure'] is not None


def test_final_serialization_clock_can_veto_closed_Root_packet(monkeypatch,capsys):
    def closed(*args):
        clock=Clock();clock.failed=True;monkeypatch.setattr(t,'_TERMINAL_CLOCK',clock)
        return {'schema':t.SCHEMA+'-terminal','status':'closed_synchronized_code_read_observation',
            'source_authority':False,'first_failure':None,'cleanup_failures':[],'original_report_sha256':'e'*64}
    monkeypatch.setattr(t,'root_trace',closed)
    exit_code=t.main(['root-trace','--head',HEAD,'--matching-tracking',REMOTE,'--code-map-json',json.dumps(MAPPING)])
    value=json.loads(capsys.readouterr().out)
    assert exit_code==2 and value['status']=='incomplete' and value['first_failure']['code']=='clock'
    assert value['original_report_sha256']=='e'*64


@pytest.fixture
def original_controls(context,monkeypatch):
    h=context;anchor=d.OutputDirectory(h.root.stat())
    path=h.directory/'report.private.json';raw=b'{"fabricated":true}\n'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:os.write(fd,raw)
    finally:os.close(fd)
    terminal={'original_report_bytes':len(raw),'original_report_sha256':t.digest(raw),
        'original_report_stamp10_sha256':t.digest(t.canonical(list(t.stamp(path.stat())))[:-1]),
        'original_output_directory_identity_sha256':t.digest(t.canonical(list(anchor.nodes[-1][2]))[:-1])}
    anchor.close();monkeypatch.setattr(t,'OUTPUT',path)
    return SimpleNamespace(path=path,raw=raw,terminal=terminal,anchor=anchor,contract=(d.OutputDirectory,d.OutputDirectory.audit,d.OutputDirectory.pin),clock=Clock(),cleanup=[])


def control_audit(h):return t.final_control_audit(h.anchor,h.terminal,h.clock,h.contract,h.cleanup)


def test_final_original_controls_are_reopened_against_original_terminal_seals(original_controls):
    h=original_controls
    assert control_audit(h) is None and h.cleanup==[]
    assert h.path.read_bytes()==h.raw


@pytest.mark.parametrize('kind',['same_bytes_new_stamp','bytes','anchor','extra_member'])
def test_control_drift_after_final_code_audit_cannot_close(original_controls,kind):
    h=original_controls
    if kind=='same_bytes_new_stamp':
        info=h.path.stat();os.utime(h.path,ns=(info.st_atime_ns,info.st_mtime_ns+1))
    elif kind=='bytes':h.path.write_bytes(b'changed')
    elif kind=='anchor':
        row=h.anchor.nodes[-1];pin=list(row[2]);pin[1]+=1;h.anchor.nodes[-1]=(row[0],row[1],tuple(pin))
    else:(h.path.parent/'unexpected.literal').write_bytes(b'fabricated')
    with pytest.raises((t.CodeReadTraceRefusal,d.DocumentsTraceRefusal)):control_audit(h)


def test_control_drift_after_last_fresh_report_FD_close_is_not_rebaselined(original_controls,monkeypatch):
    h=original_controls;real_close=os.close;real_fstat=os.fstat;key=(h.path.stat().st_dev,h.path.stat().st_ino);seen=[]
    def close(fd):
        q=real_fstat(fd);is_report=(q.st_dev,q.st_ino)==key;real_close(fd)
        if is_report:
            seen.append('last_fresh_close');info=h.path.stat();os.utime(h.path,ns=(info.st_atime_ns,info.st_mtime_ns+1))
    monkeypatch.setattr(os,'close',close)
    with pytest.raises(t.CodeReadTraceRefusal,match='control'):control_audit(h)
    assert seen==['last_fresh_close']


def test_original_control_refusal_preserves_later_FD_cleanup_failure(original_controls,monkeypatch):
    h=original_controls;h.terminal['original_report_sha256']='f'*64
    real_close=os.close;real_fstat=os.fstat;key=(h.path.stat().st_dev,h.path.stat().st_ino)
    def close(fd):
        q=real_fstat(fd);is_report=(q.st_dev,q.st_ino)==key;real_close(fd)
        if is_report:raise OSError(5,'PRIVATE cleanup text')
    monkeypatch.setattr(os,'close',close)
    with pytest.raises(t.CodeReadTraceRefusal,match='control'):control_audit(h)
    assert len(h.cleanup)==1 and h.cleanup[0]['errno_name']=='EIO'
    assert 'PRIVATE' not in json.dumps(h.cleanup)


@pytest.mark.parametrize('change',['report','anchor'])
def test_report_or_anchor_changed_by_last_code_audit_vetoes_Root_terminal(root_world,original_controls,monkeypatch,change):
    w,h=root_world,original_controls
    # Named fabricated producer seam: original directory audit/pin methods
    # operate on real fixture anchors; no native/root operation is launched.
    class Output:
        audit=d.OutputDirectory.audit
        pin=staticmethod(d.OutputDirectory.pin)
        def __init__(self,owner):self.nodes=h.anchor.nodes;self.closed=True
    w.documents.OutputDirectory=Output
    original=w.documents.root_trace
    def terminal(*args):
        value=original(*args);value.update(h.terminal);return value
    w.documents.root_trace=terminal
    def changed(*unused):
        if change=='report':h.path.write_bytes(b'changed-after-last-code-audit')
        else:
            row=h.anchor.nodes[-1];pin=list(row[2]);pin[1]+=1;h.anchor.nodes[-1]=(row[0],row[1],tuple(pin))
    monkeypatch.setattr(t,'audit_code',changed)
    monkeypatch.setattr(t,'final_control_audit',ORIGINAL_CONTROL_AUDIT)
    result=t.root_trace(HEAD,REMOTE,w.mapping)
    assert result['status']=='incomplete' and result['first_failure']['code']=='control'


def native_event(kind):
    target={'path':str(d.TARGET),'path_truncated':False,'stat':{'st_dev':7,'st_ino':8}}
    body={'target':target}
    if kind=='setflags':body['flags']=64
    if kind=='utimes':body.update(atime='2026-11-04T01:02:03.123456789Z',mtime='2026-11-04T01:02:04Z')
    if kind=='setattrlist':body['attrlist']={k:0 for k in ('bitmapcount','reserved','commonattr','volattr','dirattr','fileattr','forkattr')}
    return {'schema_version':1,'version':5,'action_type':1,'global_seq_num':0,'event_type':d.EVENTS[kind],
        'event':{kind:body},'time':'2026-11-04T01:02:03.123456789Z',
        'process':{'audit_token':{'pid':101,'pidversion':3},'group_id':102,'signing_id':'com.apple.fileproviderd',
            'executable':{'path':'/usr/libexec/fileproviderd','path_truncated':False}}}


@pytest.mark.parametrize('kind',['setflags','setattrlist','utimes'])
def test_original_matching_setter_metadata_is_bounded_and_exact(kind):
    clock=Clock();watch=SimpleNamespace(clock=clock,key=(7,8,0));captured=[]
    framer=d.load_framer((REPO/d.FRAMER).read_bytes())
    consumer=t._consumer_factory(d.make_consumer,d,captured)(framer,watch)
    consumer.tracer_pid=9000;consumer.feed(d.canonical(native_event(kind)))
    assert len(consumer.matches)==1 and captured==[watch]
    row=consumer.matches[0]
    assert row['received_monotonic_offset_ns'].isdigit() and row['received_unix_time_ns'].isdigit()
    if kind=='setflags':assert row['requested_flags']==64
    if kind=='setattrlist':assert set(row['attribute_bitmaps'])==set(native_event(kind)['event'][kind]['attrlist'])
    if kind=='utimes':assert row['requested_times']['mtime']=='2026-11-04T01:02:04Z'
    assert 'PRIVATE' not in json.dumps(row)


def test_root_git_is_demoted_and_credential_helpers_disabled(monkeypatch):
    calls=[]
    monkeypatch.setattr(t.subprocess,'run',lambda args,**kw:(calls.append((args,kw)) or SimpleNamespace(returncode=0,stdout=b'ok')))
    assert t._git(Clock(),SimpleNamespace(st_uid=501,st_gid=20),'show',HEAD+':x')==b'ok'
    args,kwargs=calls[0]
    assert args[:3]==['/usr/bin/git','-c','credential.helper=']
    assert kwargs['user']==501 and kwargs['group']==20 and kwargs['extra_groups']==[]
    assert 'safe.directory' not in ' '.join(args)


def test_real_owner_sandbox_denies_fabricated_volume_read_stat_write_but_allows_stdout(tmp_path):
    if sys.platform!='darwin':pytest.skip('macOS sandbox profile')
    path=tmp_path/'fabricated-volume';path.mkdir();literal=path/'literal';literal.write_text('fabricated')
    # Explicit test-only literal replacement: production has no USB-root option.
    profile=t.SANDBOX.replace('(subpath "/Volumes")','(subpath '+json.dumps(str(path))+')')+'\n(deny network*)\n'
    code='''import json,os,sys\np=sys.argv[1];r={}\nfor name,operation in (("read",lambda:open(p,"rb").read()),("stat",lambda:os.stat(p)),("write",lambda:open(p,"wb"))):\n try:operation();r[name]="ALLOWED"\n except OSError:r[name]="DENIED"\nprint(json.dumps(r,sort_keys=True))\n'''
    run=subprocess.run(['/usr/bin/sandbox-exec','-p',profile,t.WORKER_PYTHON,'-I','-S','-B','-c',code,str(literal)],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin'},check=False,timeout=10)
    assert run.returncode==0 and run.stderr==b''
    assert json.loads(run.stdout)=={'read':'DENIED','stat':'DENIED','write':'DENIED'}
    assert literal.read_text()=='fabricated'


def test_python39_syntax_and_no_runtime_repository_imports():
    source=(REPO/'scripts/trace_short_interest_code_read_actor.py').read_text()
    tree=ast.parse(source,feature_version=(3,9))
    assert not any(isinstance(node,ast.ImportFrom) and (node.module or '').startswith(('scripts','research','data')) for node in ast.walk(tree))
