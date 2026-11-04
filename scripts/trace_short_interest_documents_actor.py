"""One passive Documents metadata observation; no source/custody authority.

eslogger's subscribed systemwide JSON necessarily crosses bounded transient
RAM. Unrelated records/child names are never projected, persisted or logged.
Native notifications are candidates, not successful syscalls or causation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import stat
import subprocess
import sys
import time
from types import ModuleType

ROOT = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest')
SCRIPT = 'scripts/trace_short_interest_documents_actor.py'
FRAMER = 'scripts/trace_short_interest_journal_actor.py'
TARGET = Path('/Users/sheltonchen/Documents')
BASE = Path('/Users/sheltonchen/Library/Application Support/CodexShortInterestAttribution')
DIRECTORY = BASE / 'documents-20261103-v1'
OUTPUT = DIRECTORY / 'report.private.json'
EVENTS = {'create':13, 'link':19, 'rename':25, 'setattrlist':26, 'setflags':28,
          'unlink':32, 'utimes':59, 'clone':61, 'copyfile':110}
COMMAND = ('/usr/bin/eslogger', '--format', 'json', *EVENTS)
ENV = {'PATH':'/usr/bin:/bin', 'LC_ALL':'C', 'GIT_OPTIONAL_LOCKS':'0'}
PASSIVE_NS, WHOLE_NS, SHUTDOWN_NS = 30_000_000_000, 120_000_000_000, 8_000_000_000
SAMPLE_NS, MAX_SAMPLES = 100_000_000, 400
MAX_INPUT, MAX_RECORD, MAX_MATCHES, MAX_OUTPUT, MAX_STDERR = 8*1024**2, 65536, 256, 1024**2, 4096
SCHEMA = 'si-documents-passive-actor-trace-v1'
FIELDS = ('dev','ino','uid','gid','mode','nlink','size','mtime_ns','ctime_ns','flags')
_CODES = frozenset('arguments clock platform code lane directory target_identity target_protection output_exists output_changed output_bound output_close framer native_schema event_schema target_schema actor_schema path_schema result_schema stream_limit shutdown_unknown cleanup'.split())
_PHASES = frozenset('bootstrap guard target output_create native_observation shutdown final_guard publication close post_close format'.split())
_SYSTEM_PATHS = frozenset(('/usr/libexec/fileproviderd', '/System/Library/Frameworks/FileProvider.framework/Support/fileproviderd'))
_SIGNING_IDS = frozenset(('com.apple.fileproviderd','com.apple.finder','com.apple.bird','com.apple.cloudd','com.apple.mdworker','com.apple.mdworker.shared','com.apple.mds','com.apple.mds_stores'))
_TERMINAL_CLOCK = None

# Both exact, held, owner-reviewed public files are authenticated BEFORE exec.
BOOTSTRAP = '''import hashlib,os,re,stat,sys,time
started=time.monotonic_ns()
head,tracking,newsha,oldsha=sys.argv[1:]
root=%r
paths=(%r,%r)
if os.geteuid()!=0 or any(re.fullmatch('[0-9a-f]{40}',x) is None for x in (head,tracking)) or any(re.fullmatch('[0-9a-f]{64}',x) is None for x in (newsha,oldsha)):raise SystemExit(2)
owner=os.stat(root,follow_symlinks=False).st_uid
held=[]
pin=lambda q:(q.st_dev,q.st_ino,q.st_uid,q.st_gid,q.st_mode,q.st_nlink,q.st_size,q.st_mtime_ns,q.st_ctime_ns,getattr(q,'st_flags',0))
for path,wanted in zip(paths,(newsha,oldsha)):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  info=os.fstat(fd)
  if owner==0 or info.st_uid!=owner or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_mode&0o022 or not 0<info.st_size<=65536:raise SystemExit(2)
  raw=os.read(fd,65537)
  if len(raw)!=info.st_size or hashlib.sha256(raw).hexdigest()!=wanted or pin(os.fstat(fd))!=pin(info) or pin(os.stat(path,follow_symlinks=False))!=pin(info):raise SystemExit(2)
  held.append((path,raw,pin(info)))
 finally:os.close(fd)
 if pin(os.stat(path,follow_symlinks=False))!=held[-1][2]:raise SystemExit(2)
sys.argv=[paths[0],'root-trace','--head',head,'--matching-tracking',tracking,'--code-sha256',newsha,'--framer-sha256',oldsha]
exec(compile(held[0][1],paths[0],'exec'),{'__name__':'__main__','__file__':paths[0],'_BOOTSTRAP_START':started,'_HELD_CODE':tuple(held)})
''' % (str(ROOT), str(ROOT / SCRIPT), str(ROOT / FRAMER))


class DocumentsTraceRefusal(ValueError): pass
class ConstructorFailure(Exception):
    def __init__(self,primary,cleanup,owner):
        self.primary,self.cleanup,self.owner=primary,cleanup,owner


def require(value, code):
    if not value: raise DocumentsTraceRefusal(code)


def canonical(value): return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def stamp(info):
    return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode,info.st_nlink,
            info.st_size,info.st_mtime_ns,info.st_ctime_ns,getattr(info,'st_flags',0))
def identity(info): return info.st_dev,info.st_ino,stat.S_IFMT(info.st_mode)


class Clock:
    def __init__(self, started):
        self.begin=self.last=started;self.original=time.monotonic_ns
        self.check()
    def check(self, reserve=0):
        now=self.original()
        require(time.monotonic_ns is self.original and type(now) is int and type(self.begin) is int
            and 0<=self.begin<=self.last<=now and now-self.begin<=WHOLE_NS-reserve,'clock')
        self.last=now;return now
    def remaining(self): return max(.001,(WHOLE_NS-(self.check()-self.begin))/1e9)


def code_guard(head,tracking,newsha,oldsha,clock):
    require(all(re.fullmatch('[0-9a-f]{40}',x) for x in (head,tracking)) and all(re.fullmatch('[0-9a-f]{64}',x) for x in (newsha,oldsha)),'arguments')
    require(Path.cwd().resolve()==ROOT and ROOT.resolve()==ROOT,'lane')
    def git(*args):
        clock.check(SHUTDOWN_NS)
        result=subprocess.run(['/usr/bin/git','-c','safe.directory='+str(ROOT),'-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null','-C',str(ROOT),*args],
            env=ENV,stdin=None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=min(20,clock.remaining()),check=False)
        require(type(result.returncode) is int and result.returncode==0,'lane');clock.check(SHUTDOWN_NS);return result.stdout
    require(git('rev-parse','--show-toplevel').decode().strip()==str(ROOT)
        and git('branch','--show-current').decode().strip()=='codex/strategy-short-interest'
        and git('rev-parse','HEAD').decode().strip()==head
        and git('status','--porcelain=v1','-z','--untracked-files=all')==b'','lane')
    # Root does no network/credential-context operation. Main independently
    # checks actual matching origin before issue and after receipt validation.
    require(git('rev-parse','refs/remotes/origin/codex/strategy-short-interest').decode().strip()==tracking,'lane')
    held=globals().get('_HELD_CODE')
    require(type(held) is tuple and len(held)==2,'code')
    for (path,raw,original),name,digest in zip(held,(SCRIPT,FRAMER),(newsha,oldsha)):
        require(path==str(ROOT/name) and type(raw) is bytes and sha(raw)==digest
            and raw==git('show',head+':'+name) and stamp(os.stat(path,follow_symlinks=False))==original,'code')
    return held[1][1]


def load_framer(raw):
    module=ModuleType('_si_documents_original_framer_v1');module.__file__=str(ROOT/FRAMER)
    exec(compile(raw,module.__file__,'exec'),module.__dict__)
    require(module.MAX_INPUT==MAX_INPUT and module.MAX_RECORD==MAX_RECORD,'framer')
    return module


class Watch:
    """Existing target only; no directory enumeration/reopen/rebaseline."""
    def __init__(self,clock):
        require(TARGET.resolve()==TARGET,'directory');self.clock=clock
        self.fd=os.open(TARGET,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            self.original=stamp(os.fstat(self.fd));self.key=identity(os.fstat(self.fd));self.samples=[];self.closed=False
            self.sample('before_native')
        except BaseException as primary:
            try:os.close(self.fd)
            except BaseException as cleanup:raise ConstructorFailure(primary,cleanup,self) from None
            finally:self.closed=True
            raise
    def sample(self,interval):
        now=self.clock.check();info=os.fstat(self.fd) if not self.closed else os.stat(TARGET,follow_symlinks=False)
        named=os.stat(TARGET,follow_symlinks=False)
        require(TARGET.resolve()==TARGET and stat.S_ISDIR(info.st_mode) and identity(info)==identity(named)==self.key,'target_identity')
        a,b=stamp(info),stamp(named)
        require(len(self.samples)<MAX_SAMPLES,'stream_limit')
        row={'sample':len(self.samples),'interval':interval,'monotonic_offset_ns':str(now-self.clock.begin),
            'unix_time_ns':str(time.time_ns()),'descriptor_open':not self.closed,
            'fd_mtime_ns':None if self.closed else str(a[7]),'fd_ctime_ns':None if self.closed else str(a[8]),
            'name_mtime_ns':str(b[7]),'name_ctime_ns':str(b[8]),'metadata_pair_concordant':None if self.closed else a==b,
            'fd_changed_fields':[] if self.closed else [name for name,x,y in zip(FIELDS,a,self.original) if x!=y],
            'name_changed_fields':[name for name,x,y in zip(FIELDS,b,self.original) if x!=y],
            'protection_changed':a[2:5]!=self.original[2:5] or b[2:5]!=self.original[2:5]
                or a[9]!=self.original[9] or b[9]!=self.original[9]}
        self.samples.append(row);return row
    def close(self):
        if not self.closed:
            fd=self.fd;self.closed=True;os.close(fd)
        self.sample('after_target_close')


def make_consumer(framer,watch):
    class Consumer(framer.Consumer):
        def __init__(self):
            super().__init__();self.relevant=0;self.first_record_ns=None
        def finish(self):
            self.native_claims.finish()
            if self.buffer:self.issue('truncated_json_record')
            if not self.records:self.issue('no_valid_native_records')
            # Zero target candidates is an honest passive observation, not
            # proof of no writer and never an automatic retry allowance.
        def consume(self,obj):
            require(type(obj) is dict and type(obj.get('schema_version')) is int and obj['schema_version']==1
                and type(obj.get('version')) is int and obj['version']>=5
                and type(obj.get('action_type')) is int and obj['action_type']==1,'native_schema')
            sequence=framer.uint(obj.get('global_seq_num'))
            if self.first_seq is None:self.first_seq=sequence
            if self.last_seq is not None and sequence!=self.last_seq+1:self.issue('global_sequence_gap_or_reorder')
            self.last_seq=sequence;self.records+=1
            if self.first_record_ns is None:self.first_record_ns=watch.clock.check()
            event=obj.get('event');require(type(event) is dict and len(event)==1,'event_schema')
            kind=next(iter(event));require(kind in EVENTS and type(obj.get('event_type')) is int and obj['event_type']==EVENTS[kind],'event_schema')
            body=event[kind];require(type(body) is dict,'event_schema')
            relations=[]
            def path(file):
                require(type(file) is dict and type(file.get('path')) is str and type(file.get('path_truncated')) is bool,'path_schema')
                if file['path_truncated']:self.issue('truncated_target_path');return None
                return file['path']
            def parent(file,label,target_object=False):
                require(type(file) is dict and type(file.get('stat')) is dict,'target_schema')
                info=file['stat'];key=(framer.uint(info.get('st_dev')),framer.uint(info.get('st_ino')))
                if key==watch.key[:2]:
                    relations.append(label+('_exact_target_inode' if target_object else '_exact_parent_inode'))
                    text=path(file)
                    if text!=str(TARGET):self.issue('original_target_inode_path_drift_or_truncation')
                elif path(file)==str(TARGET):self.issue('target_parent_inode_changed')
            def path_parent(file,label):
                text=path(file)
                if text and text.rpartition('/')[0]==str(TARGET):relations.append(label+'_path_only_parent')
            if kind in ('setflags','setattrlist','utimes'):parent(body.get('target'),'direct_target',True)
            elif kind=='unlink':
                parent(body.get('parent_dir'),'unlink_parent');parent(body.get('target'),'unlink_object',True)
            elif kind in ('link','clone','copyfile'):parent(body.get('target_dir'),kind+'_destination')
            elif kind=='create':
                destination=body.get('destination');require(type(destination) is dict,'event_schema')
                require(type(body.get('destination_type')) is int,'event_schema')
                if set(destination)=={'new_path'} and body['destination_type']==1:parent(destination['new_path'].get('dir'),'create_destination')
                elif set(destination)=={'existing_file'} and body['destination_type']==0:
                    parent(destination['existing_file'],'create_object',True);path_parent(destination['existing_file'],'create_existing')
                else:raise DocumentsTraceRefusal('event_schema')
            else:
                parent(body.get('source'),'rename_source_object',True);path_parent(body.get('source'),'rename_source')
                destination=body.get('destination');require(type(destination) is dict,'event_schema')
                require(type(body.get('destination_type')) is int,'event_schema')
                if set(destination)=={'new_path'} and body['destination_type']==1:parent(destination['new_path'].get('dir'),'rename_destination')
                elif set(destination)=={'existing_file'} and body['destination_type']==0:
                    parent(destination['existing_file'],'rename_destination_object',True);path_parent(destination['existing_file'],'rename_existing_destination')
                else:raise DocumentsTraceRefusal('event_schema')
            if not relations:return # No actor/filename projection for unrelated rows.
            process=obj.get('process');require(type(process) is dict and type(process.get('audit_token')) is dict,'actor_schema')
            token=process['audit_token'];pid=framer.uint(token.get('pid'),32);pgid=framer.uint(process.get('group_id'),32)
            signing=process.get('signing_id');require(type(signing) is str and len(signing)<=1024,'actor_schema')
            executable=process.get('executable');require(type(executable) is dict and executable.get('path_truncated') is False,'actor_schema')
            text=framer.string(executable.get('path'));require(text.startswith('/'),'actor_schema')
            valid=signing in _SIGNING_IDS
            actor={'pid':pid,'pidversion':framer.uint(token.get('pidversion'),32),'pgid':pgid,
                'signing_id':signing if valid else None,'unclassified_signing_id_sha256':None if valid else sha(signing.encode()),
                'executable_sha256':sha(text.encode()),'allowlisted_system_executable':text if text in _SYSTEM_PATHS and signing.startswith('com.apple.') else None}
            result={'event':kind,'global_seq_num':sequence,'time':framer.timestamp(obj.get('time')),
                'target_role':'Documents','target_dev':str(watch.key[0]),'target_ino':str(watch.key[1]),
                'relations':relations,'actor':actor,'interpretation':'native_notification_candidate_not_success_or_causation'}
            if 'result' in obj:
                outcome=obj['result'];known=False
                if type(outcome) is dict and set(outcome)=={'result_type','result'} and type(outcome['result_type']) is int and type(outcome['result']) is dict:
                    union=outcome['result']
                    known=(outcome['result_type']==0 and set(union)=={'auth'} and type(union['auth']) is int and union['auth'] in (0,1)
                        or outcome['result_type']==1 and set(union)=={'flags'} and type(union['flags']) is int and 0<=union['flags']<2**32)
                if not known:self.issue('native_result_schema_unverified')
                result['native_result_present']=True;result['native_result_schema_verified']=known;result['native_result_success_inferred']=False
            if pgid==self.tracer_pid:self.issue('actor_in_suppressed_tracer_process_group')
            require(len(self.matches)<MAX_MATCHES,'stream_limit')
            self.projected_bytes+=len(canonical(result));require(self.projected_bytes<MAX_OUTPUT//2,'stream_limit')
            self.matches.append(result);self.relevant+=1
    return Consumer()


class OutputDirectory:
    """Original nofollow FD chain outside Documents; no parent adoption."""
    def __init__(self,owner):
        self.nodes=[];self.descriptors=[];self.closed=False
        require(DIRECTORY.parent==BASE and not str(DIRECTORY).startswith(str(TARGET)+'/'),'directory')
        try:
            fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            self.descriptors.append(fd)
            path=Path('/');self.nodes.append((path,fd,self.pin(os.fstat(fd))))
            for part in DIRECTORY.parts[1:]:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
                self.descriptors.append(child)
                path/=part;self.nodes.append((path,child,self.pin(os.fstat(child))));fd=child
                if path in (BASE,DIRECTORY):
                    info=os.fstat(fd);require(info.st_uid==owner.st_uid and info.st_gid==owner.st_gid and stat.S_IMODE(info.st_mode)==0o700,'directory')
            self.fd=fd;self.audit(set())
        except BaseException as primary:
            try:self.close()
            except BaseException as cleanup:raise ConstructorFailure(primary,cleanup,self) from None
            raise
    @staticmethod
    def pin(info):
        require(stat.S_ISDIR(info.st_mode) and not stat.S_IMODE(info.st_mode)&0o022,'directory')
        return info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode
    def audit(self,names,named=False):
        for path,fd,original in self.nodes:
            require(path.resolve()==path and self.pin(path.lstat())==original
                and (named or self.pin(os.fstat(fd))==original),'directory')
        require(set(os.listdir(DIRECTORY if named else self.fd))==names,'directory')
    def close(self):
        if self.closed:return
        first=None
        for fd in reversed(self.descriptors):
            try:os.close(fd)
            except BaseException as error:
                if first is None:first=error
        self.closed=True
        if first is not None:raise first


def observe(consumer,watch,clock):
    child=subprocess.Popen(COMMAND,stdin=None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=ROOT,
        env=ENV,close_fds=True,start_new_session=True)
    stderr_bytes=0;wait=None;eof=False;planned=False;stop_sent=False;start=None;first=None;cleanup=[]
    try:
        consumer.tracer_pid=child.pid;start=clock.check(SHUTDOWN_NS);deadline=start+PASSIVE_NS;last_sample=start
        with selectors.DefaultSelector() as selector:
            for stream,role in ((child.stdout,'stdout'),(child.stderr,'stderr')):
                os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,role)
            while selector.get_map():
                now=clock.check(SHUTDOWN_NS)
                if now-last_sample>=SAMPLE_NS:watch.sample('native_active');last_sample=now
                if now>=deadline and not stop_sent:
                    stop_sent=True
                    if child.poll() is None:
                        planned=True;child.terminate()
                    else:consumer.issue('ended_before_owned_shutdown')
                if stop_sent and now>=deadline+4_000_000_000:
                    if child.poll() is None:child.kill();consumer.issue('tracer_required_kill')
                    break
                for key,unused in selector.select(.05):
                    try:data=os.read(key.fileobj.fileno(),8192)
                    except BlockingIOError:continue
                    if not data:selector.unregister(key.fileobj);continue
                    if key.data=='stdout':consumer.feed(data)
                    else:
                        stderr_bytes+=len(data);require(stderr_bytes<=MAX_STDERR,'stream_limit');consumer.native_claims.feed(data)
                if child.poll() is not None and not planned:consumer.issue('tracer_ended_before_passive_window')
            eof=not selector.get_map()
    except BaseException as error:first=diagnostic(error,'native_observation')
    finally:
        # Reaping/independent stream closes NEVER depend on a throwing clock.
        try:
            if child.poll() is None:child.terminate();stop_sent=True
        except BaseException as error:cleanup.append(diagnostic(error,'shutdown'))
        try:wait=child.wait(timeout=2)
        except BaseException as error:
            cleanup.append(diagnostic(error,'shutdown'))
            try:child.kill();consumer.issue('tracer_required_kill')
            except BaseException as error:cleanup.append(diagnostic(error,'shutdown'))
            try:wait=child.wait(timeout=2)
            except BaseException as error:cleanup.append(diagnostic(error,'shutdown'))
        for stream in (child.stdout,child.stderr):
            try:stream.close()
            except BaseException as error:cleanup.append(diagnostic(error,'close'))
    if type(wait) is not int:consumer.issue('tracer_termination_unknown');wait=None
    if wait not in (0,-15) or wait==-15 and not stop_sent:consumer.issue('tracer_exit_unsuccessful')
    if not planned:consumer.issue('passive_window_not_completed')
    if not eof:consumer.issue('native_EOF_unverified')
    if stderr_bytes:consumer.issue('native_stderr_observed')
    consumer.finish()
    try:clock.check(SHUTDOWN_NS);watch.sample('after_native')
    except BaseException as error:
        if first is None:first=diagnostic(error,'shutdown')
        else:cleanup.append(diagnostic(error,'shutdown'))
    return {'actual_native_exit':wait,'native_stdout_stderr_EOF':eof,'planned_original_handle_shutdown':planned,
        'tracer_pid':child.pid,'tracer_pgid':child.pid,'tracer_pgid_basis':'original_Popen_PID_with_start_new_session',
        'owner_action_required_if_termination_unknown':type(wait) is not int,
        'first_failure':first,'cleanup_failures':cleanup,
        'stderr_bytes_discarded':stderr_bytes,'native_observation_start_ns':None if start is None else str(start-clock.begin),
        'first_record_received_offset_ns':None if consumer.first_record_ns is None else str(consumer.first_record_ns-clock.begin),
        'native_observation_end_ns':str(clock.last-clock.begin)}


def diagnostic(error,stage):
    args=BaseException.args.__get__(error,BaseException)
    code=args[0] if type(error) is DocumentsTraceRefusal and len(args)==1 and type(args[0]) is str and args[0] in _CODES else None
    return {'stage':stage if stage in _PHASES else 'bootstrap','code':code,'category':'local_contract_refusal' if code else 'unknown_local_failure'}


def root_trace(head,tracking,newsha,oldsha):
    require(sys.platform=='darwin' and os.geteuid()==0,'platform')
    clock=Clock(globals().get('_BOOTSTRAP_START'));stage='guard';failures=[];retained=[];watch=directory=output=anchors=None;original=None;consumer=None;native=None;encoded=None;closed_pin=None
    def failed(error,phase):
        retained.append(error)
        if type(error) is ConstructorFailure:
            if len(failures)<16:failures.append(diagnostic(error.primary,phase))
            if len(failures)<16:failures.append(diagnostic(error.cleanup,'close'))
            return
        if len(failures)<16:failures.append(diagnostic(error,phase))
    try:
        framer=load_framer(code_guard(head,tracking,newsha,oldsha,clock));stage='target';watch=Watch(clock);consumer=make_consumer(framer,watch)
        owner=ROOT.stat();require(owner.st_uid!=0,'platform')
        anchors=OutputDirectory(owner);directory=anchors.fd
        stage='output_create';output=os.open(OUTPUT.name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory)
        created=os.fstat(output);require(stat.S_ISREG(created.st_mode) and created.st_nlink==1 and created.st_size==0,'output_changed')
        os.fchown(output,owner.st_uid,owner.st_gid);os.fchmod(output,0o600);info=os.fstat(output)
        require(identity(info)==identity(created) and stat.S_ISREG(info.st_mode) and info.st_uid==owner.st_uid
            and info.st_gid==owner.st_gid and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1 and info.st_size==0,'output_changed')
        original=stamp(info);anchors.audit({OUTPUT.name})
        stage='native_observation';native=observe(consumer,watch,clock)
        if native['first_failure'] is not None:failures.append(native['first_failure'])
        failures.extend(native['cleanup_failures'][:max(0,16-len(failures))])
        if any(sample['protection_changed'] for sample in watch.samples):consumer.issue('Documents_protection_changed')
        stage='final_guard';code_guard(head,tracking,newsha,oldsha,clock);watch.sample('after_native_final_guard')
    except BaseException as error:failed(error,stage)
    finally:
        stage='close'
        if watch is not None:
            try:watch.close()
            except BaseException as error:failed(error,stage)
    # All target contexts close BEFORE final report formatting/publication.
    try:
        stage='publication';clock.check(SHUTDOWN_NS)
        issues=[] if consumer is None else list(consumer.issues)
        if watch is not None and any(row['protection_changed'] for row in watch.samples) and 'Documents_protection_changed' not in issues:issues.append('Documents_protection_changed')
        candidate=not failures and not issues and native is not None
        report={'schema':SCHEMA,'head':head,'matching_tracking':tracking,'code_sha256':newsha,'framer_sha256':oldsha,
            'status':'provisional_until_terminal_context_close' if candidate else 'incomplete',
            'observation_complete_candidate':candidate,'tracking_scope':'local_tracking_only_Main_checks_actual_matching_origin_separately',
            'target_role':'Documents','scope':'nine_native_notifications_not_all_possible_mutations',
            'interpretation':'native_notification_candidates_success_and_causation_not_inferred_VFS_retries_possible',
            'privacy':'systemwide_subscribed_JSON_transient_bounded_RAM_unrelated_never_projected_or_persisted_OS_swap_crash_not_proven',
            'native_actor_assignment':'unknown_until_separate_original_delta_correlation_and_success_evidence',
            'attribution_status':'native_candidates_only' if consumer is not None and consumer.matches else
                'target_transition_unattributed' if watch is not None and any(row['name_changed_fields'] for row in watch.samples) else 'no_target_transition_observed',
            'source_authority':False,'new_source_requests':0,'new_claims':0,'new_STARTs':0,'new_charged_bytes':0,
            'passive_seconds':30,'maximum_whole_seconds':120,'native':native,'issues':issues,
            'first_failure':failures[0] if failures else None,'cleanup_failures':failures[1:],
            'matched_events':[] if consumer is None else list(consumer.matches),
            'records_seen':0 if consumer is None else consumer.records,'input_bytes':0 if consumer is None else consumer.total,
            'first_global_seq':None if consumer is None else consumer.first_seq,'last_global_seq':None if consumer is None else consumer.last_seq,
            'samples':[] if watch is None else list(watch.samples),
            'native_stderr_claim':None if consumer is None else consumer.native_claims.to_payload(native['stderr_bytes_discarded'] if native else 0)}
        encoded=canonical(report);require(len(encoded)<=MAX_OUTPUT,'output_bound')
        require(output is not None and original is not None,'output_changed')
        require(stamp(os.fstat(output))==original and stamp(os.stat(OUTPUT.name,dir_fd=directory,follow_symlinks=False))==original,'output_changed')
        offset=0
        while offset<len(encoded):
            clock.check();written=os.write(output,encoded[offset:]);require(type(written) is int and written>0,'output_changed');offset+=written
        os.fsync(output);os.fsync(directory)
        require(os.pread(output,len(encoded)+1,0)==encoded,'output_changed')
        closed_pin=stamp(os.fstat(output));require(closed_pin[:6]==original[:6] and closed_pin[6]==len(encoded) and closed_pin[9]==original[9]
            and stamp(os.stat(OUTPUT.name,dir_fd=directory,follow_symlinks=False))==closed_pin,'output_changed')
        anchors.audit({OUTPUT.name})
    except BaseException as error:failed(error,stage)
    finally:
        for descriptor in (output,):
            if descriptor is not None:
                try:os.close(descriptor)
                except BaseException as error:failed(error,'close')
        if anchors is not None:
            try:anchors.close()
            except BaseException as error:failed(error,'close')
    try:
        stage='post_close'
        if closed_pin is not None:
            anchors.audit({OUTPUT.name},named=True)
            require(stamp(os.stat(OUTPUT,follow_symlinks=False))==closed_pin,'output_changed')
            anchors.audit({OUTPUT.name},named=True)
            check=os.open(OUTPUT,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            try:
                require(stamp(os.fstat(check))==closed_pin and os.read(check,MAX_OUTPUT+1)==encoded
                    and stamp(os.fstat(check))==closed_pin,'output_changed')
            finally:os.close(check)
            require(stamp(os.stat(OUTPUT,follow_symlinks=False))==closed_pin,'output_changed')
            anchors.audit({OUTPUT.name},named=True)
        final_sample=None
        if watch is not None:
            final_sample=watch.sample('after_output_contexts_close')
            require(not final_sample['protection_changed'],'target_protection')
        clock.check();stage='format'
        summary={'schema':SCHEMA+'-terminal','status':'closed_passive_observation' if not failures and report['observation_complete_candidate'] else 'incomplete',
            'source_authority':False,'original_report_sha256':sha(encoded) if closed_pin is not None else None,
            'original_report_bytes':len(encoded) if closed_pin is not None else None,
            'original_report_stamp10_sha256':sha(canonical(list(closed_pin))[:-1]) if closed_pin is not None else None,
            'original_output_directory_identity_sha256':sha(canonical(list(anchors.nodes[-1][2]))[:-1]) if anchors is not None else None,
            'report_stamp_schema':'dev_ino_uid_gid_fullmode_nlink_size_mtime_ns_ctime_ns_flags',
            'directory_identity_schema':'dev_ino_uid_gid_fullmode',
            'final_target_observation':final_sample,
            'first_failure':failures[0] if failures else None,'cleanup_failures':failures[1:]}
        canonical(summary);clock.check();globals()['_TERMINAL_CLOCK']=clock;return summary
    except BaseException as error:
        failed(error,stage)
        globals()['_TERMINAL_CLOCK']=clock
        return {'schema':SCHEMA+'-terminal','status':'incomplete','source_authority':False,
            'original_report_sha256':None,'original_report_bytes':None,'first_failure':failures[0],'cleanup_failures':failures[1:]}


def plan(head,tracking,newsha,oldsha):
    require(all(re.fullmatch('[0-9a-f]{40}',value) for value in (head,tracking)) and all(re.fullmatch('[0-9a-f]{64}',value) for value in (newsha,oldsha)),'arguments')
    command=['sudo','/usr/bin/python3','-I','-S','-B','-c',BOOTSTRAP,head,tracking,newsha,oldsha]
    return {'shell_command':'cd '+shlex.quote(str(ROOT))+' && '+shlex.join(command),
        'root_authentication_required':True,'responsible_Terminal_Full_Disk_Access_required':True,
        'prepared_private_directory_required':str(DIRECTORY),'exclusive_output':str(OUTPUT),
        'target_role':'Documents','passive_seconds':30,'whole_seconds':120,
        'window_scope':'after_sudo_auth_before_bootstrap_first_code_open_through_final_context_close_format_before_stdout_delivery',
        'source_authority':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('print-plan','root-trace'))
    parser.add_argument('--head',required=True);parser.add_argument('--matching-tracking',required=True);parser.add_argument('--code-sha256',required=True);parser.add_argument('--framer-sha256',required=True)
    args=parser.parse_args(argv)
    result=None
    try:
        result=plan(args.head,args.matching_tracking,args.code_sha256,args.framer_sha256) if args.action=='print-plan' else root_trace(args.head,args.matching_tracking,args.code_sha256,args.framer_sha256)
        encoded=canonical(result)
        if args.action=='root-trace':
            clock=globals().get('_TERMINAL_CLOCK');require(type(clock) is Clock,'clock');clock.check()
        print(encoded.decode().rstrip('\n'),flush=True);return 2 if result.get('status')=='incomplete' else 0
    except BaseException as error:
        if args.action=='root-trace' and type(result) is dict:
            result={**result,'status':'incomplete'};late=diagnostic(error,'format')
            if result.get('first_failure') is None:result['first_failure']=late
            else:result['cleanup_failures']=[*result.get('cleanup_failures',()),late][:16]
        else:result={'schema':SCHEMA+'-terminal','status':'incomplete','source_authority':False,'failure':diagnostic(error,'bootstrap')}
        print(canonical(result).decode().rstrip('\n'),flush=True);return 2


if __name__=='__main__':raise SystemExit(main())
