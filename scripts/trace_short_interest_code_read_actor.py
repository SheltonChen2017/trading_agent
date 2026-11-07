"""One synchronized, source-free observation of the original code-read window.

The original Documents observer and all five USB code files stay unchanged.
Its private observer instance has a new output namespace and a separately
reviewed owner-UID reproducer. Native candidates and timing do not assign cause.
"""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import signal
import stat
import subprocess
import sys
import time
from types import ModuleType


ROOT = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest')
SCRIPT = 'scripts/trace_short_interest_code_read_actor.py'
HELPER = 'scripts/diagnose_short_interest_code_read_interval.py'
DOCUMENTS = 'scripts/trace_short_interest_documents_actor.py'
FRAMER = 'scripts/trace_short_interest_journal_actor.py'
CODE_FILES = ('data/__init__.py', 'data/hashing.py',
    'research/short_interest_etf/firstrate_short_interest_inspection.py',
    'scripts/inspect_short_interest_usb_archive.py',
    'scripts/inspect_short_interest_usb_code_snapshot.py', DOCUMENTS, FRAMER, HELPER, SCRIPT)
DOCUMENTS_SHA = '4fa266113c4ad23c4c8747a30bcea04f02fdc25fde22a109262eea31bf73c01d'
FRAMER_SHA = 'ed462f3b0552d3f74c468c6a51e47ef215b90d9f7e38a372364aaec5c7fcdf63'
BASE = Path('/Users/sheltonchen/Library/Application Support/CodexShortInterestCodeReadAttribution')
DIRECTORY = BASE / 'code-read-20261104-v2'
OUTPUT = DIRECTORY / 'report.private.json'
SCHEMA = 'si-code-read-actor-trace-v2'
ATTR_GROUPS = ('commonattr','volattr','dirattr','fileattr','forkattr')
ATTR_CURRENT_KEYS = ('bitmapcount',*ATTR_GROUPS)
ATTR_KNOWN_KEYS = ('bitmapcount','reserved',*ATTR_GROUPS)
WHOLE_NS, PASSIVE_NS, READINESS_NS = 120_000_000_000, 30_000_000_000, 10_000_000_000
MAX_CODE, MAX_HELPER, MAX_HELPER_STDERR = 1024**2, 32768, 4096
WORKER_PYTHON = '/Users/sheltonchen/.venvs/trading_agent-py313/bin/python'
WORKER_REAL = '/opt/homebrew/Cellar/python@3.13/3.13.15/Frameworks/Python.framework/Versions/3.13/bin/python3.13'
WORKER_SHA256 = 'fdae91cd6e017f2053cd4e10457b6130e545597b12512ee4180c433ab9ba7dab'
WORKER_VERSION = (3,13,15)
NULL_PARENT = Path('/dev')
NULL_DEVICE = NULL_PARENT/'null'
NULL_RDEV, NULL_MAJOR, NULL_MINOR = 50331650, 3, 2
ENV = {'PATH':'/usr/bin:/bin', 'LC_ALL':'C', 'GIT_OPTIONAL_LOCKS':'0',
    'GIT_TERMINAL_PROMPT':'0', 'GIT_CONFIG_NOSYSTEM':'1'}
SANDBOX = '''(version 1)
(allow default)
(deny file-read* (subpath "/Volumes"))
(deny file-write*)
(allow file-write-data (literal "/dev/null"))
(deny file-read* (subpath "/Users/sheltonchen/Library/Keychains"))
(deny file-read* (subpath "/Library/Keychains"))
(deny mach-lookup (global-name "com.apple.securityd"))
(deny mach-lookup (global-name "com.apple.securityd.xpc"))
(deny process-exec (literal "/usr/bin/security"))
(deny process-exec (literal "/Library/Developer/CommandLineTools/usr/libexec/git-core/git-credential-osxkeychain"))
(deny process-exec (literal "/usr/libexec/git-core/git-credential-osxkeychain"))
(deny process-exec (literal "/bin/sh"))
(deny process-exec (literal "/bin/zsh"))
(deny process-exec (literal "/usr/bin/osascript"))
(deny process-exec (regex #"/git-credential-[^/]+$"))
'''
_CODES = frozenset('arguments platform code_map bootstrap code_shape code_hash code_stamp code_git code_context lane worker_packet worker_bound worker_exit worker_stderr worker_EOF worker_overlap readiness native clock bindings cleanup control null_device'.split())
_ERRNOS = {getattr(errno,name):name for name in ('EACCES','EPERM','ENOENT','EIO','ENOSPC','EROFS','EINTR','EBADF','EINVAL','ESTALE') if hasattr(errno,name)}
_TERMINAL_CLOCK = None


class CodeReadTraceRefusal(ValueError):
    pass


def require(value, code):
    if not value:
        raise CodeReadTraceRefusal(code)


def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pairs(items):
    value = {}
    for key,item in items:
        require(key not in value, 'worker_packet')
        value[key] = item
    return value


def stamp(info):
    return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode,info.st_nlink,
        info.st_size,info.st_mtime_ns,info.st_ctime_ns,getattr(info,'st_flags',0))


def fixed_failure(error, phase):
    args = BaseException.args.__get__(error,BaseException)
    code = args[0] if type(error) is CodeReadTraceRefusal and len(args)==1 and type(args[0]) is str and args[0] in _CODES else None
    number = OSError.errno.__get__(error,OSError) if isinstance(error,OSError) else None
    return {'stage':phase if phase in ('bootstrap','guard','native_observation','shutdown','close','post_close','format') else 'bootstrap',
        'role':'code_read_trace','code':code,'errno_name':_ERRNOS.get(number) if type(number) is int else None,
        'category':'local_contract_refusal' if code else 'local_os_refusal' if isinstance(error,OSError) else 'unknown_local_failure'}


def code_map(value):
    require(type(value) is dict and set(value)==set(CODE_FILES) and len(value)==9, 'code_map')
    require(all(type(k) is str and type(v) is str and re.fullmatch('[0-9a-f]{64}',v) for k,v in value.items()), 'code_map')
    require(value[DOCUMENTS]==DOCUMENTS_SHA and value[FRAMER]==FRAMER_SHA, 'code_map')
    return {name:value[name] for name in CODE_FILES}


def identifiers(head, tracking, mapping):
    require(all(type(x) is str and re.fullmatch('[0-9a-f]{40}',x) for x in (head,tracking)), 'arguments')
    return code_map(mapping)


def _bootstrap():
    # This prefix executes before owner-writable Python. Its expected hashes
    # are explicit arguments in the already-reviewed command issued by Main.
    return '''import errno,hashlib,json,os,re,stat,sys,time
started=time.monotonic_ns()
root=%r;paths=%r;driver=%r
codes=frozenset(('arguments','platform','clock','code_shape','code_hash','code_stamp'))
class Refusal(Exception):pass
def need(ok,code):
 if not ok:raise Refusal(code)
def check():
 now=time.monotonic_ns();need(type(now) is int and 0<=started<=now and now-started<=120000000000,'clock')
def pin(q):return(q.st_dev,q.st_ino,q.st_uid,q.st_gid,q.st_mode,q.st_nlink,q.st_size,q.st_mtime_ns,q.st_ctime_ns,getattr(q,'st_flags',0))
held=[];fd=None;first=None;cleanup=[]
try:
 need(len(sys.argv)==4,'arguments');head,remote,encoded=sys.argv[1:]
 need(all(re.fullmatch('[0-9a-f]{40}',x) for x in(head,remote)),'arguments')
 def pairs(rows):
  value={}
  for k,v in rows:need(k not in value,'arguments');value[k]=v
  return value
 mapping=json.loads(encoded,object_pairs_hook=pairs);need(type(mapping) is dict and set(mapping)==set(paths),'arguments')
 need(all(type(v) is str and re.fullmatch('[0-9a-f]{64}',v) for v in mapping.values()),'arguments')
 need(os.geteuid()==0 and sys.platform=='darwin','platform');check()
 owner=os.stat(root,follow_symlinks=False).st_uid;need(owner!=0,'platform')
 for rel in paths:
  check();path=root+'/'+rel;fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK);q=os.fstat(fd)
  need(stat.S_ISREG(q.st_mode) and q.st_uid==owner and q.st_nlink==1 and not q.st_mode&0o022 and 0<=q.st_size<=1048576,'code_shape')
  pieces=[];total=0
  while True:
   check();part=os.read(fd,min(65536,1048577-total))
   if not part:break
   pieces.append(part);total+=len(part);need(total<=1048576,'code_shape')
  raw=b''.join(pieces);need(len(raw)==q.st_size and hashlib.sha256(raw).hexdigest()==mapping[rel],'code_hash')
  need(pin(os.fstat(fd))==pin(q)==pin(os.stat(path,follow_symlinks=False)),'code_stamp')
  os.close(fd);fd=None;need(pin(os.stat(path,follow_symlinks=False))==pin(q),'code_stamp');held.append((rel,raw,pin(q)))
 compiled=compile(dict((name,raw) for name,raw,p in held)[driver],root+'/'+driver,'exec');check()
except BaseException as error:
 args=BaseException.args.__get__(error,BaseException);code=args[0] if type(error) is Refusal and len(args)==1 and type(args[0]) is str and args[0] in codes else None
 number=OSError.errno.__get__(error,OSError) if isinstance(error,OSError) else None
 known={getattr(errno,n):n for n in('EACCES','EPERM','ENOENT','EIO','ENOSPC','EROFS','EINTR','EBADF','EINVAL','ESTALE') if hasattr(errno,n)}
 first={'stage':'bootstrap','role':'code_read_trace','code':code,'errno_name':known.get(number) if type(number) is int else None,'category':'local_contract_refusal' if code else 'local_os_refusal' if isinstance(error,OSError) else 'unknown_local_failure'}
finally:
 if fd is not None:
  try:os.close(fd)
  except BaseException:cleanup.append({'stage':'close','role':'code_read_trace','code':None,'errno_name':None,'category':'unknown_local_failure'})
if first is not None or cleanup:
 print(json.dumps({'schema':'si-code-read-actor-bootstrap-refusal-v1','status':'incomplete','source_authority':False,'first_failure':first,'cleanup_failures':cleanup},sort_keys=True,separators=(',',':')),flush=True);raise SystemExit(2)
sys.argv=[root+'/'+driver,'root-trace','--head',head,'--matching-tracking',remote,'--code-map-json',encoded]
exec(compiled,{'__name__':'__main__','__file__':root+'/'+driver,'_BOOTSTRAP_START_NS':started,'_HELD_PUBLIC':tuple(held)})
''' % (str(ROOT), CODE_FILES, SCRIPT)


WORKER_BOOTSTRAP = '''import errno,hashlib,json,os,re,stat,sys,time
started=time.monotonic_ns()
root=%r;path=root+'/'+%r
codes=frozenset(('arguments','owner','clock','code_shape','code_hash','code_stamp','runtime'))
class Refusal(Exception):pass
def need(ok,code):
 if not ok:raise Refusal(code)
def check():
 now=time.monotonic_ns();need(type(now) is int and 0<=started<=now and now-started<=30000000000,'clock')
pin=lambda q:(q.st_dev,q.st_ino,q.st_uid,q.st_gid,q.st_mode,q.st_nlink,q.st_size,q.st_mtime_ns,q.st_ctime_ns,getattr(q,'st_flags',0))
fd=None;first=None;cleanup=[];stage='arguments'
def detail(error,phase):
 args=BaseException.args.__get__(error,BaseException)
 code=args[0] if type(error) is Refusal and len(args)==1 and type(args[0]) is str and args[0] in codes else None
 number=OSError.errno.__get__(error,OSError) if isinstance(error,OSError) else None
 known={getattr(errno,n):n for n in('EACCES','EPERM','ENOENT','EIO','ENOSPC','EROFS','EINTR','EBADF','EINVAL','ESTALE') if hasattr(errno,n)}
 return {'stage':phase,'role':'code_read_worker_bootstrap','code':code,'errno_name':known.get(number) if type(number) is int else None,'category':'local_contract_refusal' if code else 'local_os_refusal' if isinstance(error,OSError) else 'unknown_local_failure'}
try:
 need(len(sys.argv)==4,'arguments');head,remote,wanted=sys.argv[1:]
 need(all(re.fullmatch('[0-9a-f]{40}',v) for v in(head,remote)) and re.fullmatch('[0-9a-f]{64}',wanted),'arguments')
 check();stage='owner';owner=os.stat(root,follow_symlinks=False).st_uid
 need(os.geteuid()==owner and owner!=0,'owner');need(tuple(sys.version_info[:3])==(3,13,15),'runtime')
 stage='code_open';fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
 stage='code_read'
 q=os.fstat(fd)
 need(stat.S_ISREG(q.st_mode) and q.st_uid==owner and q.st_nlink==1 and not q.st_mode&0o022 and 0<q.st_size<=1048576,'code_shape')
 raw=os.read(fd,1048577)
 need(len(raw)==q.st_size and hashlib.sha256(raw).hexdigest()==wanted,'code_hash')
 need(pin(os.fstat(fd))==pin(q)==pin(os.stat(path,follow_symlinks=False)),'code_stamp')
 stage='code_close';os.close(fd);fd=None;need(pin(os.stat(path,follow_symlinks=False))==pin(q),'code_stamp')
 stage='driver_compile';compiled=compile(raw,path,'exec');check()
except BaseException as error:first=detail(error,stage)
finally:
 if fd is not None:
  try:os.close(fd)
  except BaseException as error:cleanup.append(detail(error,'code_close'))
if first is not None or cleanup:
 print(json.dumps({'schema':'si-code-read-worker-bootstrap-refusal-v1','status':'incomplete','source_authority':False,'first_failure':first,'cleanup_failures':cleanup},sort_keys=True,separators=(',',':')),flush=True);raise SystemExit(2)
sys.argv=[path,head,remote,wanted]
exec(compiled,{'__name__':'__main__','__file__':path,'_BOOTSTRAP_START_NS':started})
''' % (str(ROOT), HELPER)


def _git(clock, owner, *args):
    clock.check(8_000_000_000)
    result = subprocess.run(['/usr/bin/git','-c','credential.helper=','-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null','-C',str(ROOT),*args],
        env=ENV,stdin=None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        user=owner.st_uid,group=owner.st_gid,extra_groups=[],timeout=min(20,clock.remaining()),check=False)
    require(type(result.returncode) is int and result.returncode==0, 'lane')
    clock.check(8_000_000_000)
    return result.stdout


def audit_code(clock, head, tracking, mapping, held):
    require(Path.cwd().resolve()==ROOT and ROOT.resolve()==ROOT, 'lane')
    owner=ROOT.stat();require(owner.st_uid!=0, 'platform')
    require(_git(clock,owner,'rev-parse','--show-toplevel').decode().strip()==str(ROOT)
        and _git(clock,owner,'branch','--show-current').decode().strip()=='codex/strategy-short-interest'
        and _git(clock,owner,'rev-parse','HEAD').decode().strip()==head
        and _git(clock,owner,'status','--porcelain=v1','-z','--untracked-files=all')==b''
        and _git(clock,owner,'rev-parse','refs/remotes/origin/codex/strategy-short-interest').decode().strip()==tracking, 'lane')
    require(type(held) is tuple and tuple(row[0] for row in held)==CODE_FILES, 'code_context')
    for name,raw,original in held:
        clock.check(8_000_000_000)
        require(type(raw) is bytes and digest(raw)==mapping[name] and raw==_git(clock,owner,'show',head+':'+name), 'code_git')
        fd=os.open(ROOT/name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
        try:
            require(stamp(os.fstat(fd))==original, 'code_stamp')
            parts=[];total=0
            while True:
                clock.check(8_000_000_000);part=os.read(fd,min(65536,MAX_CODE+1-total))
                if not part:break
                parts.append(part);total+=len(part);require(total<=MAX_CODE,'code_shape')
            require(b''.join(parts)==raw and stamp(os.fstat(fd))==original
                and stamp(os.stat(ROOT/name,follow_symlinks=False))==original,'code_stamp')
        finally:os.close(fd)
        require(stamp(os.stat(ROOT/name,follow_symlinks=False))==original,'code_stamp')
    clock.check(8_000_000_000)


def capture_runtime(clock, original=None):
    """Fixed launcher bytes, not a claim about a complete dylib/stdlib closure."""
    clock.check(8_000_000_000)
    require(str(Path(WORKER_PYTHON).resolve())==WORKER_REAL,'code_context')
    fd=os.open(WORKER_REAL,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    try:
        info=os.fstat(fd);pin=stamp(info)
        require(stat.S_ISREG(info.st_mode) and info.st_uid==501 and info.st_gid==80
            and info.st_mode==0o100755 and info.st_nlink==1 and info.st_size==34640,'code_shape')
        if original is not None:require(pin==original,'code_stamp')
        raw=os.read(fd,34641)
        require(len(raw)==34640 and digest(raw)==WORKER_SHA256 and stamp(os.fstat(fd))==pin
            and stamp(os.stat(WORKER_REAL,follow_symlinks=False))==pin,'code_stamp')
    finally:os.close(fd)
    require(stamp(os.stat(WORKER_REAL,follow_symlinks=False))==pin
        and str(Path(WORKER_PYTHON).resolve())==WORKER_REAL,'code_stamp')
    clock.check(8_000_000_000)
    return pin


def worker_command(head, tracking, helper_sha):
    # Execute the pinned resolved launcher, never the mutable venv alias.
    return ['/usr/bin/sandbox-exec','-p',SANDBOX,WORKER_REAL,'-I','-S','-B','-c',WORKER_BOOTSTRAP,head,tracking,helper_sha]


def capture_null_device(clock, original=None):
    """Typed, root-owned Darwin null sink; never a source/control stamp rule.

    Device identity/protection/rdev is stable across this invocation. Global
    device timestamps are deliberately not asserted: other processes use it.
    The source reader and report/control full10 comparisons stay unchanged.
    """
    clock.check(8_000_000_000)
    require(NULL_PARENT==Path('/dev') and NULL_DEVICE==Path('/dev/null'),'null_device')
    def parent_pin(info):
        require(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and info.st_gid==0
            and not stat.S_IMODE(info.st_mode)&0o022,'null_device')
        return info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode
    def device_pin(info):
        require(stat.S_ISCHR(info.st_mode) and info.st_uid==0 and info.st_gid==0
            and info.st_mode==0o020666 and info.st_nlink==1 and info.st_rdev==NULL_RDEV
            and os.major(info.st_rdev)==NULL_MAJOR and os.minor(info.st_rdev)==NULL_MINOR,'null_device')
        return info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode,info.st_nlink,info.st_rdev
    owned=[];first=None;value=None
    try:
        parent=os.open(NULL_PARENT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);owned.append(parent)
        parent_original=parent_pin(os.fstat(parent))
        descriptor=os.open('null',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=parent);owned.append(descriptor)
        device_original=device_pin(os.fstat(descriptor));value=(parent_original,device_original)
        require(device_original[0]==parent_original[0]
            and parent_pin(os.stat(NULL_PARENT,follow_symlinks=False))==parent_original
            and device_pin(os.stat('null',dir_fd=parent,follow_symlinks=False))==device_original,'null_device')
        if original is not None:require(type(original) is tuple and value==original,'null_device')
    except BaseException as error:first=error
    finally:
        for descriptor in reversed(owned):
            try:os.close(descriptor)
            except BaseException as error:
                if first is None:first=error
    if first is not None:raise first
    require(parent_pin(os.stat(NULL_PARENT,follow_symlinks=False))==value[0]
        and device_pin(os.stat(NULL_DEVICE,follow_symlinks=False))==value[1],'null_device')
    clock.check(8_000_000_000)
    return value


def worker_packet(raw, head, tracking, mapping, allow_incomplete=False):
    require(type(raw) is bytes and 0<len(raw)<=MAX_HELPER,'worker_bound')
    value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda unused:require(False,'worker_packet'))
    require(type(value) is dict and canonical(value)==raw, 'worker_packet')
    if value.get('schema')=='si-code-read-worker-bootstrap-refusal-v1':
        require(allow_incomplete and set(value)=={'schema','status','source_authority','first_failure','cleanup_failures'}
            and value['status']=='incomplete' and value['source_authority'] is False,'worker_packet')
        for failure in [value['first_failure'],*value['cleanup_failures']]:
            require(type(failure) is dict and set(failure)=={'stage','role','code','errno_name','category'}
                and failure['role']=='code_read_worker_bootstrap'
                and failure['stage'] in ('arguments','owner','code_open','code_read','code_close','driver_compile')
                and failure['code'] in (None,'arguments','owner','clock','code_shape','code_hash','code_stamp','runtime')
                and failure['errno_name'] in (None,*_ERRNOS.values())
                and failure['category'] in ('local_contract_refusal','local_os_refusal','unknown_local_failure'),'worker_packet')
        return value
    expected_fields={'schema','status','runtime_head','matching_remote','interpreter_version','helper_sha256','code_manifest_sha256',
        'window','worker_start_monotonic_ns','worker_start_unix_ns','worker_end_monotonic_ns','worker_end_unix_ns',
        'first_failure','cleanup_failures','documents_comparisons','snapshot_body_unentered','source_body_unentered',
        'model_body_unentered','expected_stop_before_snapshot','profile_instrumented','profile_overhead_excluded',
        'external_OS_sandbox_required','python_audit_covers_all_metadata','git_scope','denials','authority'}
    statuses=('observed_original_initial_window_refusal','closed_initial_window_stopped_before_snapshot')
    require(set(value)==expected_fields and value.get('schema')=='si-code-read-interval-diagnostic-v1'
        and value.get('status') in (statuses+('incomplete',) if allow_incomplete else statuses), 'worker_packet')
    require(value.get('runtime_head')==head and value.get('matching_remote')==tracking
        and value.get('helper_sha256')==mapping[HELPER], 'worker_packet')
    # The full schema is fixed by the separately authenticated helper. Root
    # still enforces each authority/denial and lifecycle condition itself.
    expected_authority={'source_free_diagnostic_only':True,'source_admitted':False,'protected_source_custody_verified':False,
        'denominator_admitted':False,'actual_input_admitted':False,'ready_for_backtest':False,
        'provider_HTTP':0,'source_credential_reads':0,'new_claims':0,'new_STARTs':0,'new_charged_bytes':0,
        'outcome_looks':0,'qc_attempts':0,'QC_or_Safari':False}
    require(type(value.get('authority')) is dict and set(value['authority'])==set(expected_authority)
        and all(type(value['authority'][key]) is type(expected) and value['authority'][key]==expected for key,expected in expected_authority.items()),'worker_packet')
    expected_manifest={name:mapping[name] for name in (*CODE_FILES[:5],HELPER)}
    if value['status']!='incomplete':
        require(value.get('code_manifest_sha256')==digest(canonical(expected_manifest)[:-1]),'worker_packet')
    else:require(value['code_manifest_sha256'] is None or value['code_manifest_sha256']==digest(canonical(expected_manifest)[:-1]),'worker_packet')
    require(type(value['interpreter_version']) is list and len(value['interpreter_version'])==3
        and all(type(v) is int for v in value['interpreter_version']) and tuple(value['interpreter_version'])==WORKER_VERSION,'worker_packet')
    denial_keys={'python_write_attempts','python_socket_attempts','forbidden_read_open_attempts','unexpected_subprocess_attempts','unexpected_source_entry_attempts'}
    require(type(value.get('denials')) is dict and set(value['denials'])==denial_keys
        and all(type(v) is int and 0<=v<=4096 for v in value['denials'].values()),'worker_packet')
    if value['status']=='incomplete':return value
    require(not any(value['denials'].values()) and value['profile_instrumented'] is True
        and value['profile_overhead_excluded'] is False and value['external_OS_sandbox_required'] is True
        and value['python_audit_covers_all_metadata'] is False,'worker_packet')
    require(value.get('snapshot_body_unentered') is True and value.get('source_body_unentered') is True
        and value.get('model_body_unentered') is True, 'worker_packet')
    window=value.get('window');require(type(window) is dict and window.get('entered') is True, 'worker_packet')
    require(set(window)=={'entered','original_closed','start_monotonic_ns','end_monotonic_ns','start_unix_ns','end_unix_ns'},'worker_packet')
    closed=value['status']=='closed_initial_window_stopped_before_snapshot'
    require(window['original_closed'] is closed and value.get('expected_stop_before_snapshot') is closed,'worker_packet')
    # A worker failure after the stop must not close the observation with first_failure null.
    require(not closed or value['cleanup_failures']==[],'worker_packet')
    for key in ('start_monotonic_ns','end_monotonic_ns','start_unix_ns','end_unix_ns'):
        require(type(window.get(key)) is str and re.fullmatch('[0-9]{1,24}',window[key]),'worker_packet')
    require(int(window['start_monotonic_ns'])<=int(window['end_monotonic_ns']), 'worker_packet')
    return value


def _signal_owned(child, kind, group):
    # poll(None) leaves this original child unreaped, so its PID cannot have
    # been recycled. Never signal a remembered group after that ownership ends.
    if child.poll() is not None:return
    if group:
        require(type(child.pid) is int and child.pid>0 and os.getpgid(child.pid)==child.pid,'cleanup')
        os.killpg(child.pid,kind)
    elif kind==signal.SIGTERM:child.terminate()
    else:child.kill()


def _stop(child, failures, diagnostic, group=False):
    """Cleanup never relies on a succeeding clock or another child's cleanup."""
    if child is None:return None
    try:
        _signal_owned(child,signal.SIGTERM,group)
    except BaseException as error:
        failures.append(diagnostic(error,'shutdown'))
        try:
            if child.poll() is None:child.terminate()
        except BaseException as error:failures.append(diagnostic(error,'shutdown'))
    try:return child.wait(timeout=2)
    except BaseException as error:
        failures.append(diagnostic(error,'shutdown'))
        try:_signal_owned(child,signal.SIGKILL,group)
        except BaseException as error:
            failures.append(diagnostic(error,'shutdown'))
            try:
                if child.poll() is None:child.kill()
            except BaseException as error:failures.append(diagnostic(error,'shutdown'))
        try:return child.wait(timeout=2)
        except BaseException as error:failures.append(diagnostic(error,'shutdown'));return None


def observe(consumer, watch, clock, documents, head, tracking, mapping, runtime, null_device):
    native=worker=None;native_wait=worker_wait=None;first=None;cleanup=[]
    native_eof=set();worker_eof=set();worker_raw=bytearray();worker_stderr=native_stderr=0
    ready=launch_before=launch_after=worker_closed=stop_time=None
    planned=False;stopped=False;start=None;parsed=None;worker_validated=False;worker_finalized=False;worker_cancelled=False
    try:
        native=subprocess.Popen(documents.COMMAND,stdin=None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            cwd=ROOT,env=ENV,close_fds=True,start_new_session=True)
        consumer.tracer_pid=native.pid;start=clock.check(documents.SHUTDOWN_NS);deadline=start+PASSIVE_NS;last_sample=start
        with selectors.DefaultSelector() as selector:
            def register(child, name):
                for stream,suffix in ((child.stdout,'stdout'),(child.stderr,'stderr')):
                    os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,(name,suffix))
            register(native,'native')
            while selector.get_map():
                now=clock.check(documents.SHUTDOWN_NS)
                if ready is None and now-start>=READINESS_NS:
                    consumer.issue('read_interval_readiness_unverified')
                if worker is None and ready is None and now-start<READINESS_NS and consumer.records>0 and consumer.first_seq==0 and not consumer.issues and native_stderr==0 and native.poll() is None:
                    ready=now;owner=ROOT.stat();launch_before=clock.check(documents.SHUTDOWN_NS)
                    capture_runtime(clock,runtime)
                    capture_null_device(clock,null_device)
                    worker=subprocess.Popen(worker_command(head,tracking,mapping[HELPER]),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        cwd=ROOT,env=ENV,user=owner.st_uid,group=owner.st_gid,extra_groups=[],close_fds=True,start_new_session=True)
                    launch_after=clock.check(documents.SHUTDOWN_NS);register(worker,'worker')
                if worker is not None and not worker_finalized and worker.poll() is not None and worker_eof=={'stdout','stderr'}:
                    worker_wait=worker.wait(timeout=0);worker_closed=clock.check(documents.SHUTDOWN_NS)
                    worker_finalized=True
                    try:
                        parsed=worker_packet(bytes(worker_raw),head,tracking,mapping,allow_incomplete=True)
                        capture_runtime(clock,runtime)
                        capture_null_device(clock,null_device)
                        require(type(worker_wait) is int and worker_wait==0,'worker_exit')
                        require(worker_stderr==0,'worker_stderr')
                        require(parsed.get('status')!='incomplete' and not worker_cancelled,'worker_packet')
                        require(not stopped and worker_closed<deadline and native.poll() is None,'worker_overlap')
                        worker_validated=True
                    except BaseException as error:
                        if first is None:first=fixed_failure(error,'native_observation')
                        else:cleanup.append(fixed_failure(error,'native_observation'))
                        consumer.issue('read_interval_result_unverified')
                if worker is not None and not worker_finalized and not worker_cancelled and now>=deadline-documents.SHUTDOWN_NS:
                    # End an incomplete diagnostic while the native observer
                    # is still active; preserve its original scheduled window.
                    worker_cancelled=True;consumer.issue('read_interval_stopped_in_shutdown_reserve')
                    worker_wait=_stop(worker,cleanup,fixed_failure,group=True)
                if now>=deadline and not stopped:
                    stop_time=now;stopped=True
                    if not worker_validated:consumer.issue('read_interval_not_closed_before_native_shutdown')
                    if native.poll() is None:planned=True;native.terminate()
                    else:consumer.issue('ended_before_owned_shutdown')
                if worker is not None and not worker_finalized and now-launch_before>=PASSIVE_NS:
                    raise CodeReadTraceRefusal('worker_overlap')
                if now-last_sample>=documents.SAMPLE_NS:
                    watch.sample('shutdown_draining' if stopped else 'before_first_record' if consumer.first_record_ns is None else 'observing')
                    last_sample=now
                if stopped and now>=deadline+4_000_000_000:
                    if native.poll() is None:native.kill();consumer.issue('tracer_required_kill')
                    break
                for key,unused in selector.select(.05):
                    try:data=os.read(key.fileobj.fileno(),8192)
                    except BlockingIOError:continue
                    name,channel=key.data
                    if not data:
                        selector.unregister(key.fileobj)
                        (native_eof if name=='native' else worker_eof).add(channel);continue
                    if name=='native' and channel=='stdout':consumer.feed(data)
                    elif name=='native':
                        native_stderr+=len(data);require(native_stderr<=documents.MAX_STDERR,'native');consumer.native_claims.feed(data)
                    elif channel=='stdout':worker_raw.extend(data);require(len(worker_raw)<=MAX_HELPER,'worker_bound')
                    else:worker_stderr+=len(data);require(worker_stderr<=MAX_HELPER_STDERR,'worker_stderr')
                if native.poll() is not None and not planned:consumer.issue('tracer_ended_before_passive_window')
    except BaseException as error:
        failure=fixed_failure(error,'native_observation')
        if first is None:first=failure
        elif len(cleanup)<16:cleanup.append(failure)
    finally:
        worker_wait_final=_stop(worker,cleanup,fixed_failure,group=True)
        native_wait=_stop(native,cleanup,fixed_failure)
        if worker_wait is None:worker_wait=worker_wait_final
        for child in (worker,native):
            if child is not None:
                for stream in (child.stdout,child.stderr):
                    try:stream.close()
                    except BaseException as error:cleanup.append(fixed_failure(error,'close'))
    if native is None:consumer.issue('native_not_started')
    if type(native_wait) is not int:consumer.issue('tracer_termination_unknown')
    if native_wait not in (0,-15) or native_wait==-15 and not planned:consumer.issue('tracer_exit_unsuccessful')
    if not planned:consumer.issue('passive_window_not_completed')
    if native_eof!={'stdout','stderr'}:consumer.issue('native_EOF_unverified')
    if native_stderr:consumer.issue('native_stderr_observed')
    if not worker_validated or parsed is None:consumer.issue('read_interval_result_unverified')
    if worker_eof!={'stdout','stderr'}:consumer.issue('read_interval_EOF_unverified')
    consumer.finish()
    try:clock.check(documents.SHUTDOWN_NS);watch.sample('after_native')
    except BaseException as error:
        if first is None:first=fixed_failure(error,'shutdown')
        else:cleanup.append(fixed_failure(error,'shutdown'))
    def offset(value):return None if value is None else str(value-clock.begin)
    return {'actual_native_exit':native_wait,'native_stdout_stderr_EOF':native_eof=={'stdout','stderr'},
        'planned_original_handle_shutdown':planned,'tracer_pid':None if native is None else native.pid,
        'tracer_pgid':None if native is None else native.pid,'tracer_pgid_basis':'original_Popen_PID_with_start_new_session',
        'owner_action_required_if_termination_unknown':type(native_wait) is not int or worker is not None and type(worker_wait) is not int,
        'first_failure':first,'cleanup_failures':cleanup[:16],'stderr_bytes_discarded':native_stderr,
        'native_observation_start_ns':offset(start),'first_record_received_offset_ns':offset(consumer.first_record_ns),
        'native_observation_end_ns':offset(clock.last),
        'reproducer':{'schema':'si-code-read-owned-reproducer-v1','pid':None if worker is None else worker.pid,
            'actual_exit':worker_wait,'stdout_stderr_EOF':worker_eof=={'stdout','stderr'},'stderr_bytes_discarded':worker_stderr,
            'cancelled_in_native_shutdown_reserve':worker_cancelled,
            'owner_action_required_if_termination_unknown':worker is not None and type(worker_wait) is not int,
            'native_ready_offset_ns':offset(ready),'launch_before_offset_ns':offset(launch_before),'launch_after_offset_ns':offset(launch_after),
            'owned_wait_EOF_close_offset_ns':offset(worker_closed),'native_shutdown_offset_ns':offset(stop_time),
            'complete_lifetime_inside_native_interval':bool(worker_validated and parsed is not None and stop_time is not None and worker_closed<stop_time),
            'clock_scope':'parent_process_envelope_worker_own_monotonic_not_cross_process_epoch_compared',
            'sandbox':'Volumes_read_metadata_all_persistent_file_writes_Keychain_routes_denied_only_typed_null_data_sink_allowed',
            'git_scope':'unchanged_original_matching_lane_Git_metadata_exception_not_market_provider_HTTP_or_universal_credential_zero_claim',
            'runtime_launcher_sha256':WORKER_SHA256,'runtime_original_stamp10_sha256':digest(canonical(list(runtime))[:-1]),
            'runtime_version':list(WORKER_VERSION),'runtime_scope':'fixed_launcher_binary_not_full_stdlib_or_dylib_closure',
            'null_device_original_contract_sha256':digest(canonical([list(pin) for pin in null_device])[:-1]),
            'null_device_contract':'root_owned_nofollow_parent_identity5_character_identity7_rdev_3_2_no_timestamp_stability_claim',
            'interpretation_scope':'parent_native_candidates_and_sampled_deltas_separate_from_child_original_failed_comparisons_no_global_no_transition_inference',
            'report':parsed}}


def _consumer_factory(original, documents, captured):
    def factory(framer,watch):
        require(not captured,'bindings');captured.append(watch)
        original_instance=original(framer,watch)
        class Consumer(type(original_instance)):
            def consume(self,obj):
                before=len(self.matches);super().consume(obj)
                if len(self.matches)==before:return
                row=self.matches[-1];kind=row['event'];body=obj['event'][kind]
                row['received_monotonic_offset_ns']=str(watch.clock.check()-watch.clock.begin)
                row['received_unix_time_ns']=str(time.time_ns())
                if kind=='setflags':row['requested_flags']=framer.uint(body.get('flags'),32)
                elif kind=='setattrlist':
                    attrs=body.get('attrlist');projection=attribute_projection(attrs)
                    if projection is None:
                        # Keep the already validated actor/inode candidate.
                        # Unknown requested metadata vetoes completeness but
                        # does not truncate the remaining bounded capture.
                        row['requested_attribute_projection']='unsupported_schema'
                        row['requested_attribute_schema_signature']=attribute_signature(attrs)
                        self.issue('matching_attribute_schema_unsupported')
                    else:
                        row['requested_attribute_projection']=projection[0]
                        row['attribute_bitmaps']=projection[1]
                elif kind=='utimes':row['requested_times']={key:framer.timestamp(body.get(key)) for key in ('atime','mtime')}
                self.projected_bytes+=len(documents.canonical(row));require(self.projected_bytes<documents.MAX_OUTPUT//2,'native')
        return Consumer()
    return factory


def attribute_projection(attrs):
    """Two explicit producer variants; no arbitrary optional-field fallback.

    Current Apple eslogger CodingKeys omit the C alignment-only reserved word.
    The legacy seven-field variant is accepted only with exact zero padding.
    This diagnostic representation changes no source/control custody checks.
    """
    if type(attrs) is not dict:return None
    keys=set(attrs)
    if keys==set(ATTR_CURRENT_KEYS):variant='native_six_keys'
    elif keys==set(ATTR_KNOWN_KEYS):
        if type(attrs['reserved']) is not int or attrs['reserved']!=0:return None
        variant='legacy_seven_keys_reserved_zero'
    else:return None
    count=attrs['bitmapcount']
    if type(count) is not int or not 0<=count<2**16 or count!=5:return None
    if not all(type(attrs[key]) is int and 0<=attrs[key]<2**32 for key in ATTR_GROUPS):return None
    return variant,{key:attrs[key] for key in ATTR_CURRENT_KEYS}


def attribute_signature(attrs):
    """Only fixed field presence/type enums and an unknown-key count escape."""
    def kind(value):
        for cls,label in ((type(None),'null'),(bool,'bool'),(int,'int'),(float,'float'),(str,'string'),(list,'list'),(dict,'dict')):
            if type(value) is cls:return label
        return 'other'
    is_dict=type(attrs) is dict
    return {'container_type':kind(attrs),
        'known_fields':{key:{'present':is_dict and key in attrs,
            'type':kind(attrs[key]) if is_dict and key in attrs else 'absent'} for key in ATTR_KNOWN_KEYS},
        'unknown_field_count':sum(key not in ATTR_KNOWN_KEYS for key in attrs) if is_dict else None}


def load_documents(raw):
    require(type(raw) is bytes and digest(raw)==DOCUMENTS_SHA,'code_hash')
    module=ModuleType('_si_code_read_original_documents_v1');module.__file__=str(ROOT/DOCUMENTS)
    exec(compile(raw,module.__file__,'exec'),module.__dict__)
    return module


def final_control_audit(anchor, terminal, clock, contract, cleanup):
    """Recheck original terminal pins after the coordinator's LAST code audit."""
    original_type,original_audit,original_pin=contract
    require(type(anchor) is original_type and original_type.audit is original_audit
        and original_type.pin is original_pin and anchor.closed is True,'control')
    require(type(anchor.nodes) is list and 1<=len(anchor.nodes)<=32
        and anchor.nodes[-1][0]==OUTPUT.parent,'control')
    expected_size=terminal.get('original_report_bytes')
    expected_raw=terminal.get('original_report_sha256');expected_stamp=terminal.get('original_report_stamp10_sha256')
    expected_directory=terminal.get('original_output_directory_identity_sha256')
    require(type(expected_size) is int and 0<expected_size<=1024**2
        and all(type(v) is str and re.fullmatch('[0-9a-f]{64}',v) for v in (expected_raw,expected_stamp,expected_directory)),'control')
    require(digest(canonical(list(anchor.nodes[-1][2]))[:-1])==expected_directory,'control')
    clock.check();original_audit(anchor,{OUTPUT.name},named=True)
    fd=os.open(OUTPUT,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    first=None
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600
            and info.st_size==expected_size and digest(canonical(list(stamp(info)))[:-1])==expected_stamp,'control')
        parts=[];total=0
        while True:
            clock.check();part=os.read(fd,min(65536,1024**2+1-total))
            if not part:break
            parts.append(part);total+=len(part);require(total<=1024**2,'control')
        require(total==expected_size and digest(b''.join(parts))==expected_raw
            and digest(canonical(list(stamp(os.fstat(fd))))[:-1])==expected_stamp
            and digest(canonical(list(stamp(os.stat(OUTPUT,follow_symlinks=False))))[:-1])==expected_stamp,'control')
    except BaseException as error:first=error
    finally:
        try:os.close(fd)
        except BaseException as error:
            if first is None:first=error
            else:cleanup.append(fixed_failure(error,'close'))
    if first is not None:raise first
    # This is AFTER the final newly opened report FD closes. These are the
    # original retained directory anchors and original report seals, not a
    # fresh baseline or a rewrite of the provisional report.
    require(digest(canonical(list(stamp(os.stat(OUTPUT,follow_symlinks=False))))[:-1])==expected_stamp,'control')
    original_audit(anchor,{OUTPUT.name},named=True)
    directory_now=original_pin(os.stat(OUTPUT.parent,follow_symlinks=False))
    require(digest(canonical(list(directory_now))[:-1])==expected_directory,'control')
    require(digest(canonical(list(stamp(os.stat(OUTPUT,follow_symlinks=False))))[:-1])==expected_stamp,'control')
    clock.check()


def root_trace(head, tracking, mapping):
    global _TERMINAL_CLOCK
    mapping=identifiers(head,tracking,mapping)
    require(sys.platform=='darwin' and os.geteuid()==0,'platform')
    held=globals().get('_HELD_PUBLIC');require(type(held) is tuple,'bootstrap')
    require(tuple(row[0] for row in held)==CODE_FILES and all(type(row[1]) is bytes and digest(row[1])==mapping[row[0]] for row in held),'bootstrap')
    raw={name:body for name,body,unused in held}
    documents=load_documents(raw[DOCUMENTS])
    clock=documents.Clock(globals().get('_BOOTSTRAP_START_NS'));_TERMINAL_CLOCK=clock
    runtime=capture_runtime(clock)
    null_device=capture_null_device(clock)
    captured=[];outputs=[];original_guard=documents.code_guard;original_consumer=documents.make_consumer
    original_output=documents.OutputDirectory
    output_contract=(original_output,original_output.audit,original_output.pin)
    documents.BASE,documents.DIRECTORY,documents.OUTPUT=BASE,DIRECTORY,OUTPUT
    documents.SCHEMA=SCHEMA;documents._BOOTSTRAP_START=clock.begin
    documents._HELD_CODE=tuple((str(ROOT/name),body,pin) for name,body,pin in held if name in (DOCUMENTS,FRAMER))
    def guarded(h,t,newsha,oldsha,inner_clock):
        audit_code(inner_clock,h,t,mapping,held)
        return original_guard(h,t,newsha,oldsha,inner_clock)
    def observed(consumer,watch,inner_clock):return observe(consumer,watch,inner_clock,documents,head,tracking,mapping,runtime,null_device)
    factory=_consumer_factory(original_consumer,documents,captured)
    def output_factory(owner):
        require(not outputs,'bindings')
        anchor=original_output(owner);require(type(anchor) is original_output,'bindings');outputs.append(anchor)
        return anchor
    documents.code_guard,documents.observe,documents.make_consumer=guarded,observed,factory
    documents.OutputDirectory=output_factory
    expected=(documents.code_guard,documents.observe,documents.make_consumer,documents.OutputDirectory,documents.BASE,documents.DIRECTORY,documents.OUTPUT,documents.SCHEMA)
    result=None
    try:
        result=documents.root_trace(head,tracking,mapping[DOCUMENTS],mapping[FRAMER])
        # The delegated report is provisional. This coordinator still has
        # its own final code/context/target/clock boundary to complete.
        clock=documents._TERMINAL_CLOCK;require(type(clock) is documents.Clock,'clock');_TERMINAL_CLOCK=clock
        require(expected==(documents.code_guard,documents.observe,documents.make_consumer,documents.OutputDirectory,documents.BASE,documents.DIRECTORY,documents.OUTPUT,documents.SCHEMA),'bindings')
        audit_code(clock,head,tracking,mapping,held)
        capture_runtime(clock,runtime)
        capture_null_device(clock,null_device)
        if result.get('status')=='closed_passive_observation':
            require(len(outputs)==1,'bindings')
            final_control_audit(outputs[0],result,clock,output_contract,result['cleanup_failures'])
        final=None
        if captured:
            require(len(captured)==1 and captured[0].closed,'bindings')
            final=captured[0].sample('after_coordinator_code_audit_outside_native')
            require(not final['protection_changed'],'bindings')
        require(result.get('status')=='closed_passive_observation','native')
        result={**result,'status':'closed_synchronized_code_read_observation',
            'coordinator_code_mapping_sha256':digest(canonical(mapping)[:-1]),
            'coordinator_final_target_observation_outside_native':final,
            'source_authority':False,'new_source_requests':0,'new_claims':0,'new_STARTs':0,'new_charged_bytes':0}
        canonical(result);clock.check();return result
    except BaseException as error:
        failure=fixed_failure(error,'post_close')
        if type(result) is not dict:result={'schema':SCHEMA+'-terminal','source_authority':False,'first_failure':None,'cleanup_failures':[]}
        if result.get('first_failure') is None:result['first_failure']=failure
        else:result['cleanup_failures']=[*result.get('cleanup_failures',()),failure][:16]
        return {**result,'status':'incomplete','source_authority':False}


def plan(head, tracking, mapping):
    mapping=identifiers(head,tracking,mapping)
    encoded=canonical(mapping).decode().rstrip('\n')
    command=['/usr/bin/sudo','/usr/bin/python3','-I','-S','-B','-c',_bootstrap(),head,tracking,encoded]
    return {'shell_command':'cd '+shlex.quote(str(ROOT))+' && '+shlex.join(command),
        'prepared_private_directory_required':str(DIRECTORY),'exclusive_output':str(OUTPUT),
        'root_authentication_required':True,'responsible_Terminal_Full_Disk_Access_required':True,
        'source_authority':False,'native_seconds':30,'maximum_whole_seconds':120,'readiness_seconds':10,
        'source_scope':'only_original_initial_five_code_window_no_snapshot_or_USB_admission',
        'null_device_scope':'only_file_write_data_exact_dev_null_after_root_owned_character_identity_and_rdev_3_2_validation_persistent_writes_denied',
        'preload_scope':'root_bootstrap_code_and_runtime_preloads_precede_native_coverage_only_original_owner_read_window_is_synchronized',
        'code_mapping_sha256':digest(canonical(mapping)[:-1])}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('print-plan','root-trace'));parser.add_argument('--head',required=True)
    parser.add_argument('--matching-tracking',required=True);parser.add_argument('--code-map-json',required=True)
    args=parser.parse_args(argv);result=None
    try:
        mapping=json.loads(args.code_map_json,object_pairs_hook=pairs)
        result=plan(args.head,args.matching_tracking,mapping) if args.action=='print-plan' else root_trace(args.head,args.matching_tracking,mapping)
        encoded=canonical(result)
        if args.action=='root-trace':require(_TERMINAL_CLOCK is not None,'clock');_TERMINAL_CLOCK.check()
        print(encoded.decode().rstrip('\n'),flush=True);return 2 if result.get('status')=='incomplete' else 0
    except BaseException as error:
        failure=fixed_failure(error,'format')
        if type(result) is dict:
            result={**result,'status':'incomplete'}
            if result.get('first_failure') is None:result['first_failure']=failure
            else:result['cleanup_failures']=[*result.get('cleanup_failures',()),failure][:16]
        else:result={'schema':SCHEMA+'-terminal','status':'incomplete','source_authority':False,'first_failure':failure,'cleanup_failures':[]}
        print(canonical(result).decode().rstrip('\n'),flush=True);return 2


if __name__=='__main__':raise SystemExit(main())
