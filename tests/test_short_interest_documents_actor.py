"""Passive trace framing/metadata tests; no sudo/eslogger or real Documents."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import shlex
from types import SimpleNamespace, ModuleType

import pytest

from scripts import trace_short_interest_documents_actor as d


HEAD,TRACKING,NEW,OLD='a'*40,'b'*40,'c'*64,'d'*64
REPO=Path(__file__).resolve().parents[1]


class Clock:
    begin=0;last=0
    def check(self,reserve=0):self.last+=1000000;return self.last
    def remaining(self):return 100


@pytest.fixture(autouse=True)
def no_actual_native(monkeypatch):
    def denied(*args,**kwargs):raise AssertionError('Actual native/privileged command forbidden')
    monkeypatch.setattr(subprocess,'Popen',denied)


@pytest.fixture
def context(tmp_path,monkeypatch):
    # Explicit fabricated ancestor-protection seam: production uses the fixed
    # protected home/Library chain, not world-writable /private/tmp. Every
    # fixture-owned target/output directory retains real, mutable metadata.
    fstat,stat_call,lstat=os.fstat,os.stat,os.lstat
    shared={(info.st_dev,info.st_ino) for path in tmp_path.parents for info in (lstat(path),)}
    def protected(info):
        if (info.st_dev,info.st_ino) not in shared:return info
        values={name:getattr(info,name) for name in dir(info) if name.startswith('st_')}
        values['st_mode']&=~0o022;return SimpleNamespace(**values)
    monkeypatch.setattr(os,'fstat',lambda fd:protected(fstat(fd)))
    monkeypatch.setattr(os,'stat',lambda path,*args,**kw:protected(stat_call(path,*args,**kw)))
    monkeypatch.setattr(os,'lstat',lambda path,*args,**kw:protected(lstat(path,*args,**kw)))
    target=tmp_path/'Documents';target.mkdir(mode=0o700)
    base=tmp_path/'Attribution';base.mkdir(mode=0o700)
    directory=base/'documents-v1';directory.mkdir(mode=0o700)
    root=tmp_path/'lane';root.mkdir(mode=0o700)
    monkeypatch.setattr(d,'TARGET',target);monkeypatch.setattr(d,'BASE',base)
    monkeypatch.setattr(d,'DIRECTORY',directory);monkeypatch.setattr(d,'OUTPUT',directory/'report.private.json')
    monkeypatch.setattr(d,'ROOT',root)
    clock=Clock();watch=d.Watch(clock)
    framer=d.load_framer((REPO/d.FRAMER).read_bytes());consumer=d.make_consumer(framer,watch)
    consumer.tracer_pid=9000
    try:yield SimpleNamespace(target=target,base=base,directory=directory,root=root,clock=clock,watch=watch,framer=framer,consumer=consumer)
    finally:
        if not watch.closed:watch.close()


def file(path,key=(7,8),truncated=False):
    return {'path':str(path),'path_truncated':truncated,'stat':{'st_dev':key[0],'st_ino':key[1]}}


def event(h,kind,seq=0):
    target=file(h.target,h.watch.key[:2]);child=file(str(h.target)+'/PRIVATE-child-name')
    if kind in ('setflags','setattrlist','utimes'):body={'target':target,'flags':2}
    elif kind=='unlink':body={'parent_dir':target,'target':child}
    elif kind in ('link','clone','copyfile'):body={'target_dir':target,'source':file('/PRIVATE-unrelated/source'),'target_filename':'PRIVATE-child-name','target_file':None}
    elif kind=='create':body={'destination_type':1,'destination':{'new_path':{'dir':target,'filename':'PRIVATE-child-name','mode':0o644}}}
    else:body={'source':child,'destination_type':1,'destination':{'new_path':{'dir':target,'filename':'PRIVATE-destination'}}}
    return {'schema_version':1,'version':5,'action_type':1,'global_seq_num':seq,'event_type':d.EVENTS[kind],
        'event':{kind:body},'time':'2026-11-03T01:02:03.123456789Z',
        'process':{'audit_token':{'pid':101,'pidversion':3},'group_id':102,'signing_id':'com.apple.fileproviderd',
            'executable':{'path':'/usr/libexec/fileproviderd','path_truncated':False}}}


@pytest.mark.parametrize('kind',tuple(d.EVENTS))
def test_nine_event_numeric_concordance_strict_target_relations_and_no_child_names(context,kind):
    h=context;h.consumer.feed(d.canonical(event(h,kind)))
    assert h.consumer.records==1 and len(h.consumer.matches)==1
    row=h.consumer.matches[0]
    assert row['event']==kind and row['target_role']=='Documents'
    assert row['interpretation']=='native_notification_candidate_not_success_or_causation'
    assert any('exact_parent_inode' in relation or 'exact_target_inode' in relation for relation in row['relations'])
    encoded=json.dumps(row)
    assert 'PRIVATE' not in encoded and 'target_filename' not in encoded
    assert row['actor']['signing_id']=='com.apple.fileproviderd'


@pytest.mark.parametrize('kind',['create','rename'])
@pytest.mark.parametrize('wrong',[0,True,2])
def test_destination_enum_must_match_exact_union_before_projection(context,kind,wrong):
    h=context;obj=event(h,kind);obj['event'][kind]['destination_type']=wrong
    with pytest.raises(d.DocumentsTraceRefusal,match='event_schema'):h.consumer.consume(obj)
    assert not h.consumer.matches


@pytest.mark.parametrize('kind',['create','rename'])
def test_existing_file_and_source_parent_are_explicitly_path_only(context,kind):
    h=context;obj=event(h,kind);body=obj['event'][kind]
    body['destination_type']=0;body['destination']={'existing_file':file(str(h.target)+'/PRIVATE-destination')}
    h.consumer.consume(obj);relations=h.consumer.matches[0]['relations']
    assert relations and all('path_only_parent' in relation for relation in relations)


@pytest.mark.parametrize('truncated',[False,True])
def test_original_parent_inode_match_survives_aliased_or_truncated_path_as_negative(context,truncated):
    h=context;obj=event(h,'unlink');obj['event']['unlink']['parent_dir']=file('/PRIVATE-aliased',h.watch.key[:2],truncated)
    h.consumer.consume(obj)
    assert h.consumer.matches and 'original_target_inode_path_drift_or_truncation' in h.consumer.issues
    assert 'PRIVATE' not in json.dumps(h.consumer.matches)


def test_unrelated_actor_is_not_parsed_or_persisted(context):
    h=context;obj=event(h,'unlink');obj['event']['unlink']['parent_dir']=file('/PRIVATE-other')
    obj['process']={'PRIVATE':'malformed actor must never be parsed'}
    h.consumer.consume(obj);h.consumer.finish()
    assert h.consumer.records==1 and not h.consumer.matches and not h.consumer.issues


@pytest.mark.parametrize('signing',['com.PRIVATE.valid.identifier','PRIVATE /path@email'])
def test_unknown_signing_identity_is_hashed_even_if_dotted(context,signing):
    h=context;obj=event(h,'setflags');obj['process']['signing_id']=signing
    obj['process']['executable']['path']='/Users/PRIVATE/Actor'
    h.consumer.consume(obj);row=h.consumer.matches[0]['actor']
    assert row['signing_id'] is None and row['unclassified_signing_id_sha256']==d.sha(signing.encode())
    assert row['allowlisted_system_executable'] is None and 'PRIVATE' not in json.dumps(row)


def test_unknown_result_is_negative_never_success_inference(context):
    h=context;obj=event(h,'create');obj['result']={'UNKNOWN':'PRIVATE'}
    h.consumer.consume(obj)
    assert 'native_result_schema_unverified' in h.consumer.issues
    assert h.consumer.matches[0]['native_result_success_inferred'] is False
    assert 'PRIVATE' not in json.dumps(h.consumer.matches)


def test_watch_observes_timestamp_size_nlink_without_resealing(context):
    h=context;original=h.watch.original
    (h.target/'PRIVATE').mkdir()
    row=h.watch.sample('native_active')
    assert h.watch.original is original and not row['protection_changed']
    assert 'mtime_ns' in row['fd_changed_fields'] and 'nlink' in row['name_changed_fields']


def test_watch_close_uses_name_only_observation_without_descriptor_mislabel(context):
    h=context;h.watch.close();row=h.watch.samples[-1]
    assert row['descriptor_open'] is False and row['fd_mtime_ns'] is None
    assert row['metadata_pair_concordant'] is None and row['fd_changed_fields']==[]


def test_failed_initial_watch_sample_closes_original_fd(context,monkeypatch):
    opened=[];closed=[];op=os.open;close=os.close
    monkeypatch.setattr(os,'open',lambda *a,**kw:(opened.append(op(*a,**kw)) or opened[-1]))
    monkeypatch.setattr(os,'close',lambda fd:(closed.append(fd),close(fd))[1])
    sample=d.Watch.sample
    monkeypatch.setattr(d.Watch,'sample',lambda *a:(_ for _ in ()).throw(d.DocumentsTraceRefusal('target_identity')))
    with pytest.raises(d.DocumentsTraceRefusal):d.Watch(context.clock)
    assert len(opened)==1 and closed==opened
    monkeypatch.setattr(d.Watch,'sample',sample)


@pytest.mark.parametrize('boundary',['fstat','pin'])
@pytest.mark.parametrize('ordinal',[1,3])
def test_output_constructor_owns_each_fd_before_fstat_or_pin(context,monkeypatch,boundary,ordinal):
    opened=[];closed=[];calls=0;op=os.open;close=os.close;fstat=os.fstat;pin=d.OutputDirectory.pin
    def opening(*args,**kwargs):
        fd=op(*args,**kwargs);opened.append(fd);return fd
    def closing(fd):
        closed.append(fd);return close(fd)
    def failing(value):
        nonlocal calls
        calls+=1
        if calls==ordinal:raise d.DocumentsTraceRefusal('directory')
        return fstat(value) if boundary=='fstat' else pin(value)
    with monkeypatch.context() as patch:
        patch.setattr(os,'open',opening);patch.setattr(os,'close',closing)
        if boundary=='fstat':patch.setattr(os,'fstat',failing)
        else:patch.setattr(d.OutputDirectory,'pin',staticmethod(failing))
        try:
            with pytest.raises(d.DocumentsTraceRefusal,match='directory'):
                d.OutputDirectory(context.root.stat())
            assert len(opened)==ordinal and closed==list(reversed(opened))
            for fd in opened:
                with pytest.raises(OSError):fstat(fd)
        finally:
            # A deliberate causal reversal may leak a fabricated test FD.
            for fd in opened:
                try:close(fd)
                except OSError:pass


def test_postlaunch_clock_failure_still_reaps_and_closes_both_streams(context,monkeypatch):
    h=context;events=[]
    class Stream:
        def close(self):events.append('close')
    class Child:
        pid=10;stdout=Stream();stderr=Stream()
        def poll(self):return None
        def terminate(self):events.append('terminate')
        def wait(self,timeout):events.append(('wait',timeout));return -15
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**kw:Child())
    class Bad(Clock):
        def check(self,reserve=0):raise d.DocumentsTraceRefusal('clock')
    result=d.observe(h.consumer,h.watch,Bad())
    assert events==['terminate',('wait',2),'close','close']
    assert result['first_failure']['code']=='clock' and result['actual_native_exit']==-15


@pytest.fixture
def root_run(context,monkeypatch):
    h=context;monkeypatch.setattr(os,'geteuid',lambda:0);monkeypatch.setattr(sys,'platform','darwin')
    monkeypatch.setattr(d,'_BOOTSTRAP_START',d.time.monotonic_ns(),raising=False)
    raw=(REPO/d.FRAMER).read_bytes();monkeypatch.setattr(d,'code_guard',lambda *a:raw)
    def observe(consumer,watch,clock):
        consumer.consume(event(SimpleNamespace(target=h.target,watch=watch),'setflags'))
        consumer.finish();watch.sample('native_active')
        return {'actual_native_exit':-15,'native_stdout_stderr_EOF':True,'planned_original_handle_shutdown':True,
            'stderr_bytes_discarded':0,'first_failure':None,'cleanup_failures':[]}
    monkeypatch.setattr(d,'observe',observe)
    h.run=lambda:d.root_trace(HEAD,TRACKING,NEW,OLD)
    return h


def test_genuine_report_fd_directory_closure_and_terminal_original_hashes(root_run):
    h=root_run;result=h.run();raw=d.OUTPUT.read_bytes();report=json.loads(raw)
    assert result['status']=='closed_passive_observation' and result['source_authority'] is False
    assert report['status']=='provisional_until_terminal_context_close'
    assert result['original_report_sha256']==d.sha(raw) and result['original_report_bytes']==len(raw)
    assert result['original_report_stamp10_sha256']==d.sha(d.canonical(list(d.stamp(d.OUTPUT.stat())))[:-1])
    assert result['final_target_observation']['descriptor_open'] is False
    assert not result['first_failure']


def test_late_target_protection_change_after_report_close_vetoes_terminal_without_rewrite(root_run,monkeypatch):
    h=root_run;close=os.close;changed=False
    def close_and_change(fd):
        nonlocal changed
        selected=d.OUTPUT.exists() and os.fstat(fd).st_ino==d.OUTPUT.stat().st_ino
        close(fd)
        if selected and not changed:changed=True;h.target.chmod(0o750)
    monkeypatch.setattr(os,'close',close_and_change)
    result=h.run();raw=d.OUTPUT.read_bytes()
    assert result['status']=='incomplete' and result['first_failure']['code']=='target_protection'
    assert json.loads(raw)['status']=='provisional_until_terminal_context_close'


def test_output_ancestor_symlink_after_close_never_becomes_original(root_run,monkeypatch):
    h=root_run;close=d.OutputDirectory.close
    def redirect(self):
        close(self);moved=h.base.with_name('Moved');h.base.rename(moved);h.base.symlink_to(moved,target_is_directory=True)
    monkeypatch.setattr(d.OutputDirectory,'close',redirect)
    result=h.run();assert result['status']=='incomplete' and result['first_failure']['code']=='directory'


def test_nonzero_native_lifecycle_never_positive(root_run,monkeypatch):
    h=root_run
    def failed(consumer,watch,clock):
        consumer.issue('tracer_exit_unsuccessful')
        return {'actual_native_exit':1,'stderr_bytes_discarded':0,'first_failure':None,'cleanup_failures':[]}
    monkeypatch.setattr(d,'observe',failed)
    assert h.run()['status']=='incomplete'


def test_plan_is_bound_to_four_identifiers_and_bootstrap_precedes_code_open():
    plan=d.plan(HEAD,TRACKING,NEW,OLD)
    assert plan['source_authority'] is False
    tokens=shlex.split(plan['shell_command'])
    # SI-CR27-003: never resolve sudo through the owner's PATH.
    assert tokens.count('/usr/bin/sudo')==1 and 'sudo' not in tokens and tokens[-4:]==[HEAD,TRACKING,NEW,OLD]
    assert plan['shell_command'].startswith('cd ') and tokens[tokens.index('&&')+1]=='/usr/bin/sudo'
    assert d.BOOTSTRAP.index('started=time.monotonic_ns()')<d.BOOTSTRAP.index('os.open(path')
    assert d.BOOTSTRAP.index('hashlib.sha256(raw)')<d.BOOTSTRAP.index('exec(compile')
    assert plan['whole_seconds']==120 and plan['passive_seconds']==30


def test_root_code_guard_runs_every_Git_read_as_the_lane_owner(tmp_path,monkeypatch):
    """SI-CR27-004: root never parses owner-writable repository config itself."""
    raw={d.SCRIPT:b'# fabricated driver\n',d.FRAMER:b'# fabricated framer\n'};held=[]
    for name,body in raw.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
        held.append((str(path),body,d.stamp(os.stat(path,follow_symlinks=False))))
    monkeypatch.setattr(d,'ROOT',tmp_path);monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(d.__dict__,'_HELD_CODE',tuple(held))
    owner=os.stat(tmp_path,follow_symlinks=False);calls=[]
    replies={('rev-parse','--show-toplevel'):str(tmp_path).encode()+b'\n',('branch','--show-current'):b'codex/strategy-short-interest\n',
        ('rev-parse','HEAD'):HEAD.encode()+b'\n',('status','--porcelain=v1','-z','--untracked-files=all'):b'',
        ('rev-parse','refs/remotes/origin/codex/strategy-short-interest'):TRACKING.encode()+b'\n',
        ('show',HEAD+':'+d.SCRIPT):raw[d.SCRIPT],('show',HEAD+':'+d.FRAMER):raw[d.FRAMER]}
    def run(argv,**kwargs):
        calls.append((argv,kwargs));args=tuple(argv[argv.index('-C')+2:])
        return SimpleNamespace(returncode=0,stdout=replies[args],stderr=b'')
    monkeypatch.setattr(d.subprocess,'run',run)
    assert d.code_guard(HEAD,TRACKING,d.sha(raw[d.SCRIPT]),d.sha(raw[d.FRAMER]),Clock())==raw[d.FRAMER]
    assert len(calls)==7
    for argv,kwargs in calls:
        assert argv[0]=='/usr/bin/git' and not any('safe.directory' in token for token in argv)
        assert (kwargs['user'],kwargs['group'],kwargs['extra_groups'])==(owner.st_uid,owner.st_gid,[])


def test_unknown_exception_diagnostic_never_formats_private_text():
    row=d.diagnostic(RuntimeError('PRIVATE /path names'),'native_observation')
    assert row['code'] is None and 'PRIVATE' not in json.dumps(row)


@pytest.mark.parametrize('role',['unlink_object','rename_source','create_existing','rename_existing'])
def test_original_Documents_object_is_retained_separately_from_parent_relation(context,role):
    h=context;kind={'unlink_object':'unlink','rename_source':'rename','create_existing':'create','rename_existing':'rename'}[role]
    obj=event(h,kind);body=obj['event'][kind];original=file(h.target,h.watch.key[:2]);other=file('/PRIVATE-unrelated')
    if role=='unlink_object':body['parent_dir']=other;body['target']=original
    elif role=='rename_source':body['source']=original;body['destination']['new_path']['dir']=other
    else:
        if kind=='rename':body['source']=other
        body['destination_type']=0;body['destination']={'existing_file':original}
    h.consumer.consume(obj);relations=h.consumer.matches[0]['relations']
    assert relations and all('exact_target_inode' in value for value in relations)
    assert 'PRIVATE' not in json.dumps(h.consumer.matches)


def test_constructor_primary_and_cleanup_errors_remain_separate(context,monkeypatch):
    sample=d.Watch.sample;close=os.close
    def fail_sample(*args):raise d.DocumentsTraceRefusal('target_identity')
    def fail_close(fd):close(fd);raise OSError('PRIVATE cleanup')
    monkeypatch.setattr(d.Watch,'sample',fail_sample);monkeypatch.setattr(os,'close',fail_close)
    try:
        with pytest.raises(d.ConstructorFailure) as caught:d.Watch(context.clock)
        assert d.diagnostic(caught.value.primary,'target')['code']=='target_identity'
        assert d.diagnostic(caught.value.cleanup,'close')['code'] is None
    finally:
        monkeypatch.setattr(d.Watch,'sample',sample);monkeypatch.setattr(os,'close',close)


def test_output_constructor_primary_and_cleanup_are_separate(context,monkeypatch):
    close=d.OutputDirectory.close
    monkeypatch.setattr(d.OutputDirectory,'audit',lambda *a,**kw:(_ for _ in ()).throw(d.DocumentsTraceRefusal('directory')))
    def fail_close(self):close(self);raise OSError('PRIVATE cleanup')
    monkeypatch.setattr(d.OutputDirectory,'close',fail_close)
    with pytest.raises(d.ConstructorFailure) as caught:d.OutputDirectory(context.root.stat())
    assert d.diagnostic(caught.value.primary,'output_create')['code']=='directory'
    assert caught.value.owner.closed is True


def test_nonTimeout_wait_and_kill_error_still_make_independent_second_wait(context,monkeypatch):
    h=context;events=[]
    class Stream:
        def close(self):events.append('close')
    class Child:
        pid=80;stdout=Stream();stderr=Stream();waits=0
        def poll(self):return None
        def terminate(self):events.append('terminate')
        def kill(self):events.append('kill');raise OSError('PRIVATE kill')
        def wait(self,timeout):
            self.waits+=1;events.append(('wait',timeout))
            if self.waits==1:raise OSError('PRIVATE wait')
            return -15
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**kw:Child())
    class Bad(Clock):
        def check(self,reserve=0):raise d.DocumentsTraceRefusal('clock')
    result=d.observe(h.consumer,h.watch,Bad())
    assert events==['terminate',('wait',2),'kill',('wait',2),'close','close']
    assert result['actual_native_exit']==-15 and result['tracer_pid']==80
    assert result['first_failure']['code']=='clock' and result['cleanup_failures']


def test_child_dead_at_deadline_never_counts_as_owned_planned_shutdown(context,monkeypatch):
    h=context;actions=[]
    class Stream:
        def __init__(self,fd):self.fd=fd
        def fileno(self):return self.fd
        def close(self):pass
    class Child:
        pid=80;stdout=Stream(111);stderr=Stream(222)
        def poll(self):return 0
        def terminate(self):actions.append('terminate')
        def wait(self,timeout):return 0
    class Selector:
        def __init__(self):self.map={}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def register(self,stream,events,role):self.map[stream]=SimpleNamespace(fileobj=stream,data=role)
        def get_map(self):return self.map
        def unregister(self,stream):del self.map[stream]
        def select(self,timeout):return [(key,None) for key in tuple(self.map.values())]
    class Timer(Clock):
        def __init__(self):self.calls=0;self.last=0
        def check(self,reserve=0):self.last=0 if self.calls==0 else 31000000000+self.calls;self.calls+=1;return self.last
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**kw:Child())
    monkeypatch.setattr(d.selectors,'DefaultSelector',Selector);monkeypatch.setattr(os,'set_blocking',lambda *a:None)
    read=os.read;monkeypatch.setattr(os,'read',lambda fd,size:b'' if fd in (111,222) else read(fd,size))
    result=d.observe(h.consumer,h.watch,Timer())
    assert result['planned_original_handle_shutdown'] is False and not actions
    assert 'ended_before_owned_shutdown' in h.consumer.issues


def test_last_fresh_report_RO_close_ancestor_change_vetoes_terminal(root_run,monkeypatch):
    h=root_run;close=os.close;count=0
    def close_and_redirect(fd):
        nonlocal count
        selected=d.OUTPUT.exists() and os.fstat(fd).st_ino==d.OUTPUT.stat().st_ino
        close(fd)
        if selected:
            count+=1
            if count==2:
                moved=h.base.with_name('Moved');h.base.rename(moved);h.base.symlink_to(moved,target_is_directory=True)
    monkeypatch.setattr(os,'close',close_and_redirect)
    result=h.run();assert result['status']=='incomplete' and result['first_failure']['code']=='directory'


def test_actual_main_terminal_serialization_is_inside_original_clock(monkeypatch,capsys):
    now=[0];monkeypatch.setattr(d.time,'monotonic_ns',lambda:now[0]);clock=d.Clock(0)
    monkeypatch.setattr(d,'_TERMINAL_CLOCK',clock)
    monkeypatch.setattr(d,'root_trace',lambda *a:{'status':'closed_passive_observation','source_authority':False,'first_failure':None,'cleanup_failures':[]})
    encode=d.canonical;calls=0
    def slow(value):
        nonlocal calls
        raw=encode(value);calls+=1
        if calls==1:now[0]=d.WHOLE_NS+1
        return raw
    monkeypatch.setattr(d,'canonical',slow)
    assert d.main(['root-trace','--head',HEAD,'--matching-tracking',TRACKING,'--code-sha256',NEW,'--framer-sha256',OLD])==2
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='incomplete' and result['first_failure']['stage']=='format'
