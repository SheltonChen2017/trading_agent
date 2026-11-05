"""One instrumented original initial-code window; never source admission.

The Root coordinator must launch this owner-UID process only after native
subscription readiness, inside its fixed OS sandbox. Python audit events do
not cover all metadata syscalls; this module makes no contrary claim.
"""
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from types import FrameType, ModuleType

ROOT = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest')
DRIVER = 'scripts/diagnose_short_interest_code_read_interval.py'
ORIGINAL = 'scripts/inspect_short_interest_usb_code_snapshot.py'
CODE_FILES = ('data/__init__.py','data/hashing.py',
    'research/short_interest_etf/firstrate_short_interest_inspection.py',
    'scripts/inspect_short_interest_usb_archive.py',ORIGINAL)
DOCUMENTS = Path('/Users/sheltonchen/Documents')
REF = 'refs/heads/codex/strategy-short-interest'
ENV = {'PATH':'/usr/bin:/bin','GIT_OPTIONAL_LOCKS':'0'}
MAX_SECONDS, MAX_BYTES, MAX_OUTPUT, MAX_COMPARISONS = 30, 1024**2, 32768, 128
MODULE = '_si_original_code_interval_v1'
_USED = False
_ADD_AUDIT = sys.addaudithook
_CODES = frozenset('arguments interpreter attempt_spent clock root code code_runtime original_negative window_witness stop_witness profile_callback profile_changed source_barrier forbidden_open forbidden_write forbidden_socket forbidden_subprocess forbidden_import output_bound cleanup'.split())
_DENIAL_KEYS = ('python_write_attempts','python_socket_attempts','forbidden_read_open_attempts',
    'unexpected_subprocess_attempts','unexpected_source_entry_attempts')
_FIELDS = ('dev','ino','uid','gid','mode','nlink','size','mtime_ns','ctime_ns','flags')


class IntervalRefusal(ValueError): pass
class StopBeforeSnapshot(BaseException): pass


def require(value,code):
    if not value:raise IntervalRefusal(code)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def digest(raw):return hashlib.sha256(raw).hexdigest()


def authority():
    return {'source_free_diagnostic_only':True,'source_admitted':False,'protected_source_custody_verified':False,
        'denominator_admitted':False,'actual_input_admitted':False,'ready_for_backtest':False,
        'provider_HTTP':0,'source_credential_reads':0,'new_claims':0,'new_STARTs':0,'new_charged_bytes':0,
        'outcome_looks':0,'qc_attempts':0,'QC_or_Safari':False}


def _stamp(info):
    return tuple(getattr(info,name) for name in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink',
        'st_size','st_mtime_ns','st_ctime_ns'))+(getattr(info,'st_flags',0),)


def _now():return time.monotonic_ns(),time.time_ns()


def _check(start):
    now=time.monotonic_ns()
    require(type(start) is int and type(now) is int and 0<=start<=now and now-start<=MAX_SECONDS*10**9,'clock')
    return now


def _git_allowed(arguments,head):
    return arguments in (['rev-parse','--show-toplevel'],['branch','--show-current'],['rev-parse','HEAD'],
        ['status','--porcelain=v1','-z','--untracked-files=all'],
        ['rev-parse','refs/remotes/origin/codex/strategy-short-interest'],
        ['ls-remote','--exit-code','--refs','origin',REF]) or (type(arguments) is list and len(arguments)==2
        and arguments[0]=='show' and arguments[1] in tuple(head+':'+name for name in (*CODE_FILES,DRIVER)))


def _git(arguments,head,start):
    require(_git_allowed(arguments,head),'forbidden_subprocess');_check(start)
    value=subprocess.run(['git',*arguments],cwd=ROOT,env=ENV,stdin=None,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,timeout=max(.001,min(20,(MAX_SECONDS*10**9-(time.monotonic_ns()-start))/10**9)),check=False)
    _check(start);require(type(value.returncode) is int and value.returncode==0 and type(value.stdout) is bytes,'code')
    return value.stdout


def _authenticate(head,remote,own_sha,start):
    require(ROOT.resolve()==ROOT and Path.cwd().resolve()==ROOT,'root')
    require(_git(['rev-parse','--show-toplevel'],head,start).decode().strip()==str(ROOT)
        and _git(['branch','--show-current'],head,start).decode().strip()=='codex/strategy-short-interest'
        and _git(['rev-parse','HEAD'],head,start).decode().strip()==head
        and _git(['status','--porcelain=v1','-z','--untracked-files=all'],head,start)==b''
        and _git(['rev-parse','refs/remotes/origin/codex/strategy-short-interest'],head,start).decode().strip()==remote,'root')
    bodies={};originals={}
    for name in (DRIVER,*CODE_FILES):
        _check(start);path=ROOT/name;require(path.resolve()==path,'code')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        try:
            info=os.fstat(fd);pin=_stamp(info)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and 0<=info.st_size<=MAX_BYTES,'code')
            raw=os.read(fd,MAX_BYTES+1)
            require(len(raw)==info.st_size and _stamp(os.fstat(fd))==_stamp(path.lstat())==pin,'code')
            require(raw==_git(['show',head+':'+name],head,start),'code')
            require(_stamp(os.fstat(fd))==_stamp(path.lstat())==pin,'code')
            bodies[name]=raw;originals[name]=pin
        finally:os.close(fd)
        require(_stamp(path.lstat())==pin,'code')
    require(digest(bodies[DRIVER])==own_sha,'code')
    return bodies,originals


def _load_original(bodies):
    require(MODULE not in sys.modules,'code_runtime')
    module=ModuleType(MODULE);module.__file__=str(ROOT/ORIGINAL);sys.modules[MODULE]=module
    try:
        exec(compile(bodies[ORIGINAL],module.__file__,'exec'),module.__dict__)
        require(module.ROOT==ROOT and module.CODE_FILES==CODE_FILES and module.MAX_SECONDS==180,'code_runtime')
        # Preload only the original fixed stdlib catalogue before the permanent
        # audit hook. No repository package is imported from disk.
        for name in sorted(module._STDLIB):importlib.import_module(name)
        return module
    except BaseException:
        if sys.modules.get(MODULE) is module:del sys.modules[MODULE]
        raise


def _safe_failure(error,phase='bootstrap'):
    args=BaseException.args.__get__(error,BaseException)
    code=args[0] if type(error) is IntervalRefusal and len(args)==1 and type(args[0]) is str and args[0] in _CODES else None
    return {'phase':phase,'role':'unknown','code_ordinal':None,'code':code,'original_comparison':None,'actor':'unknown'}


def _negative(module,error):
    row=module._NEGATIVES.get(id(error))
    require(type(error) is module.CodeSnapshotRefusal and type(row) is tuple and len(row)==4 and row[0] is error,'original_negative')
    frame=row[3]
    require(type(frame) is FrameType and frame.f_code is module.inspect_registered.__code__ and frame.f_globals is module.__dict__
        and frame.f_locals.get('error') is error and frame.f_locals.get('negative') is row
        and frame.f_locals.get('state') is row[2] and type(row[1]) is bytes,'original_negative')
    payload=module.failure_summary(error)
    require(canonical(payload)==row[1] and type(payload) is dict and payload.get('status')=='refused_finite_code_window_inspection','original_negative')
    return row,payload


def _window_witness(module,frame,value):
    row=module._WINDOWS.get(id(value))
    require(type(frame) is FrameType and type(value) is tuple and len(value)==5 and type(row) is tuple and len(row)==6
        and row[0] is value and row[3]=='initial' and row[4] is frame
        and frame.f_code is module._code_window.__code__ and frame.f_globals is module.__dict__
        and frame.f_locals.get('window') is value and frame.f_locals.get('receipt') is row
        and frame.f_locals.get('committed') is row[2] and frame.f_locals.get('graph') is row[1]
        and type(row[1]) is module._Graph and row[1].original_validate is module._Graph.validate,'window_witness')
    committed=module._COMMITS.get(id(row[2]));clock=frame.f_locals.get('clock')
    require(type(committed) is tuple and len(committed)==4 and committed[0] is row[2] and committed[1] is clock
        and committed[3].f_code is module._committed_code.__code__ and committed[3].f_globals is module.__dict__
        and committed[3].f_locals.get('committed') is row[2] and committed[3].f_locals.get('row') is committed,'window_witness')
    caller=frame.f_back
    require(type(caller) is FrameType and caller.f_code is module.inspect_registered.__code__
        and caller.f_globals is module.__dict__ and caller.f_locals.get('graph') is row[1]
        and caller.f_locals.get('committed') is row[2] and caller.f_locals.get('clock') is clock,'window_witness')
    return row


def _documents_comparison(module,graph,frame,before,after,window_frame):
    if frame.f_code is not graph.reader._compare_stamp.__code__ or frame.f_globals is not graph.reader.__dict__:return None
    rows=[row for row in graph.reader._STAMP_FAILURES.values() if type(row) is tuple and len(row)==11 and row[8] is frame]
    if not rows:return None
    require(len(rows)==1,'profile_callback');row=rows[0]
    error,item,actual,original,code,phase,ordinal,relation,unused,component,origin=row
    require(frame.f_locals.get('row') is row and frame.f_locals.get('error') is error
        and frame.f_locals.get('actual') is actual and frame.f_locals.get('original') is original
        and frame.f_locals.get('item') is item and type(error) is graph.reader.UsbInspectionRefusal
        and type(item) is graph.reader._Read and type(origin) is tuple and len(origin)==4
        and graph.reader._READ_ORIGINS.get(id(item)) is origin and origin[0] is item
        and item.component is component is origin[1] and item._reopen is origin[2],'profile_callback')
    caller=frame.f_back
    valid=(type(caller) is FrameType and caller.f_globals is graph.reader.__dict__
        and ((caller.f_code in (graph.reader._Read.audit.__code__,graph.reader._Read.after_close.__code__)
              and caller.f_locals.get('self') is item)
             or (caller.f_code is graph.reader._compare_chains.__code__ and caller.f_locals.get('item') is item
                 and type(caller.f_back) is FrameType and caller.f_back.f_code is graph.reader._Read.after_close.__code__
                 and caller.f_back.f_globals is graph.reader.__dict__ and caller.f_back.f_locals.get('self') is item)))
    ancestor=caller;inside=False
    for unused in range(64):
        if ancestor is window_frame:inside=True;break
        if ancestor is None:break
        ancestor=ancestor.f_back
    require(valid and inside and type(window_frame) is FrameType
        and window_frame.f_code is module._code_window.__code__ and window_frame.f_globals is module.__dict__
        and window_frame.f_locals.get('name')=='initial','profile_callback')
    creator=origin[3]
    require(type(creator) is FrameType and creator.f_code is graph.reader._Read.__init__.__code__
        and creator.f_globals is graph.reader.__dict__ and creator.f_locals.get('self') is item
        and creator.f_locals.get('origin') is origin and item.path==Path(creator.f_locals.get('path')),'profile_callback')
    if ordinal!=3 or item.path not in tuple(ROOT/name for name in CODE_FILES):return None
    require(type(ordinal) is int and Path('/').joinpath(*item.path.parts[1:4])==DOCUMENTS and len(item.directories)>=3
        and item.directories[2][3] is original and type(actual) is type(original) is tuple and len(actual)==len(original)==10
        and actual!=original and phase in graph.reader._PHASES and relation in graph.reader._RELATIONS
        and frame.f_locals.get('component') is component and frame.f_locals.get('origin') is origin
        and BaseException.args.__get__(error,BaseException)==(code,),'profile_callback')
    valid_comparison=(code=='original_directory_changed'
        and phase in ('initial_audit','held_audit','close_audit','post_close_reopen_initial_audit','post_close_reopen_close_audit')
        and relation in ('directory_descriptor_vs_original','directory_name_vs_original')) or (code=='post_close_original_changed'
        and (phase,relation) in (('post_close_compare','reopened_directory_descriptor_vs_original'),
            ('post_close_named_audit','post_close_directory_name_vs_original')))
    require(valid_comparison,'profile_callback')
    require(all(type(value) is int and value>=0 for value in (*actual,*original)),'profile_callback')
    return {'role':'code','code_ordinal':CODE_FILES.index(item.path.relative_to(ROOT).as_posix())+1,'chain_ordinal':3,
        'bracket_scope':'original_window_entry_through_failed_comparison_return',
        'relation':relation,'entered_phase':phase,'target_dev':str(original[0]),'target_ino':str(original[1]),
        'mismatching_fields':[name for name,left,right in zip(_FIELDS,actual,original) if left!=right],
        'original':{'mtime_ns':str(original[7]),'ctime_ns':str(original[8]),'flags':str(original[9])},
        'observed':{'mtime_ns':str(actual[7]),'ctime_ns':str(actual[8]),'flags':str(actual[9])},
        'before_monotonic_ns':str(before[0]),'before_unix_ns':str(before[1]),
        'after_monotonic_ns':str(after[0]),'after_unix_ns':str(after[1])}


def _install_denials(head,state):
    absolute={str(ROOT/name) for name in (DRIVER,*CODE_FILES)}
    absolute.update(str(path) for name in (DRIVER,*CODE_FILES) for path in (ROOT/name).parents)
    relative={part for name in (DRIVER,*CODE_FILES) for part in (ROOT/name).parts}
    def denied(key,code):
        state['denials'][key]+=1;state['failed']=True;raise IntervalRefusal(code)
    def audit(event,args):
        if event=='open':
            path,mode,flags=args
            if type(flags) is not int or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):denied('python_write_attempts','forbidden_write')
            text=os.fsdecode(path) if type(path) in (str,bytes) else None
            if text not in absolute and text not in relative:denied('forbidden_read_open_attempts','forbidden_open')
        elif event.startswith('socket.') or event in ('socket.getaddrinfo','socket.gethostbyname'):
            denied('python_socket_attempts','forbidden_socket')
        elif event=='subprocess.Popen':
            executable,arguments,cwd,environment=args
            if (executable not in ('git','/usr/bin/git') or type(arguments) is not list or arguments[:1]!=['git']
                    or not _git_allowed(arguments[1:],head) or Path(cwd)!=ROOT or environment!=ENV):
                denied('unexpected_subprocess_attempts','forbidden_subprocess')
        elif event in ('os.system','os.exec','os.posix_spawn','os.spawn'):
            denied('unexpected_subprocess_attempts','forbidden_subprocess')
        elif event=='sys.setprofile' and not state['profile_change_allowed']:
            # CPython audits its automatic clear after a profiling callback
            # raises. Permit that ONE clear only for our genuine issued stop.
            permit=state['auto_disable_permit'];profile=state['profile_function'];module=state['original_module']
            valid=type(permit) is tuple and len(permit)==4 and permit is state['stop'] and not state['auto_disable_used']
            if valid:
                stop,producer,source,witness=permit
                valid=(type(stop) is StopBeforeSnapshot and type(producer) is FrameType and type(source) is FrameType
                    and sys.getprofile() is profile
                    and producer.f_code is profile.__code__ and producer.f_globals is globals()
                    and producer.f_locals.get('issued') is permit and producer.f_locals.get('stop') is stop
                    and producer.f_locals.get('state') is state and producer.f_locals.get('frame') is source
                    and source.f_code is module._issue_snapshot.__code__ and source.f_globals is module.__dict__
                    and witness is state['witness'] and source.f_locals.get('window') is witness[0]
                    and source.f_locals.get('graph') is witness[1] and source.f_locals.get('committed') is witness[2])
            if not valid:state['failed']=True;raise IntervalRefusal('profile_changed')
            state['auto_disable_used']=True;state['auto_disable_permit']=None
    _ADD_AUDIT(audit)
    return audit


def _observe_original(module,head,remote,state):
    codes={name:getattr(module,name).__code__ for name in ('inspect_registered','_new_graph','_code_window','_issue_snapshot','_inspect_sources')}
    def profile(frame,event,arg):
        try:
            if frame.f_globals is not module.__dict__:
                graph=state['graph']
                if graph is not None and frame.f_code is graph.reader._compare_stamp.__code__:
                    if event=='call':
                        require(len(state['comparison_calls'])<MAX_COMPARISONS,'profile_callback');state['comparison_calls'][id(frame)]=(frame,_now())
                    elif event=='return':
                        entry=state['comparison_calls'].pop(id(frame),None)
                        if entry is not None:
                            # Stat operands are evaluated before comparison
                            # entry: window entry is the conservative lower bound.
                            row=_documents_comparison(module,graph,frame,state['start'],_now(),state['window_frame'])
                            if row is not None:
                                require(len(state['documents'])<8,'profile_callback');state['documents'].append(row)
                return
            caller=frame.f_back
            if frame.f_code is codes['_new_graph'] and event=='return' and arg is not None:
                require(caller.f_code is codes['inspect_registered'] and frame.f_locals.get('graph') is arg,'profile_callback')
                state['graph']=arg
            elif frame.f_code is codes['_code_window']:
                require(caller.f_code is codes['inspect_registered'] and frame.f_locals.get('name')=='initial','profile_callback')
                if event=='call':
                    require(state['window_frame'] is None,'profile_callback');state['window_frame']=frame;state['start']=_now()
                elif event=='return':
                    require(state['window_frame'] is frame and state['end'] is None,'profile_callback');state['end']=_now()
                    if arg is not None:state['witness']=_window_witness(module,frame,arg)
            elif event=='call' and frame.f_code in (codes['_issue_snapshot'],codes['_inspect_sources']):
                require(caller.f_code is codes['inspect_registered'],'profile_callback')
                if frame.f_code is codes['_inspect_sources']:
                    state['denials']['unexpected_source_entry_attempts']+=1;state['failed']=True
                    raise IntervalRefusal('source_barrier')
                witness=state['witness'];require(witness is not None and frame.f_locals.get('window') is witness[0]
                    and frame.f_locals.get('graph') is witness[1] and frame.f_locals.get('committed') is witness[2],'window_witness')
                stop=StopBeforeSnapshot();issued=(stop,sys._getframe(),frame,witness)
                state['stop']=issued;state['auto_disable_permit']=issued;raise stop
        except StopBeforeSnapshot:raise
        except BaseException as error:
            state['failed']=True
            if state['own_failure'] is None:state['own_failure']=_safe_failure(error,'profile')
            raise IntervalRefusal('profile_callback') from None
    require(sys.getprofile() is None,'profile_changed')
    state['profile_function']=profile;state['original_module']=module
    state['profile_change_allowed']=True
    try:sys.setprofile(profile)
    finally:state['profile_change_allowed']=False
    original_error=None
    try:module.inspect_registered(head,remote)
    except BaseException as error:original_error=error
    finally:
        current=sys.getprofile()
        if current is not None and current is not profile:state['failed']=True
        state['auto_disable_permit']=None
        state['profile_change_allowed']=True
        try:sys.setprofile(None)
        finally:state['profile_change_allowed']=False
    require(original_error is not None,'original_negative')
    row,payload=_negative(module,original_error)
    if state['stop'] is not None:
        stop,producer,source,witness=state['stop']
        require(type(stop) is StopBeforeSnapshot and producer.f_code is profile.__code__ and producer.f_globals is globals()
            and producer.f_locals.get('issued') is state['stop'] and producer.f_locals.get('stop') is stop
            and producer.f_locals.get('frame') is source and source.f_code is codes['_issue_snapshot']
            and source.f_globals is module.__dict__ and witness is state['witness']
            and any(value is stop for value in row[2]['errors']) and not module._SNAPSHOTS,'stop_witness')
    require(all(name not in sys.modules for name in module._ALIASES),'cleanup')
    return payload


def run_registered(head,matching_remote,helper_sha256):
    global _USED
    valid_arguments=bool(type(head) is type(matching_remote) is type(helper_sha256) is str
        and re.fullmatch('[0-9a-f]{40}',head) and re.fullmatch('[0-9a-f]{40}',matching_remote)
        and re.fullmatch('[0-9a-f]{64}',helper_sha256))
    identifiers=(head,matching_remote,helper_sha256) if valid_arguments else (None,None,None)
    worker_begin=_now();state={'failed':False,'own_failure':None,'graph':None,'window_frame':None,
        'start':None,'end':None,'witness':None,'stop':None,'comparison_calls':{},'documents':[],
        'profile_change_allowed':False,'profile_function':None,'original_module':None,
        'auto_disable_permit':None,'auto_disable_used':False,'denials':{name:0 for name in _DENIAL_KEYS}}
    module=payload=bodies=originals=None;first=None;later=[];status='incomplete'
    try:
        require(not _USED,'attempt_spent');_USED=True
        require(sys.version_info[:2]==(3,13),'interpreter')
        require(valid_arguments,'arguments')
        start=globals().get('_BOOTSTRAP_START_NS');_check(start)
        bodies,originals=_authenticate(head,matching_remote,helper_sha256,start)
        module=_load_original(bodies);_install_denials(head,state)
        payload=_observe_original(module,head,matching_remote,state)
        first=payload['first_failure'];later=payload['cleanup_failures']
        require(state['window_frame'] is not None and state['start'] is not None and state['end'] is not None,'window_witness')
        require(not state['failed'] and not any(state['denials'].values()),'profile_callback')
        status='closed_initial_window_stopped_before_snapshot' if state['stop'] is not None else 'observed_original_initial_window_refusal'
        if state['stop'] is None:require(state['witness'] is None and first['phase']=='initial_code','window_witness')
        for name,pin in originals.items():require(_stamp((ROOT/name).lstat())==pin,'code')
        _check(start)
    except BaseException as error:
        first=state['own_failure'] or _safe_failure(error)
        status='incomplete'
    finally:
        if module is not None:
            if sys.modules.get(MODULE) is module:del sys.modules[MODULE]
            else:status='incomplete';later=[*later,_safe_failure(IntervalRefusal('cleanup'))]
    worker_end=_now();interval=state['start'],state['end']
    result={'schema':'si-code-read-interval-diagnostic-v1','status':status,'runtime_head':identifiers[0],'matching_remote':identifiers[1],
        'interpreter_version':list(sys.version_info[:3]),
        'helper_sha256':identifiers[2],'code_manifest_sha256':digest(canonical({name:digest(raw) for name,raw in bodies.items()})) if bodies is not None else None,
        'window':{'entered':state['window_frame'] is not None,'original_closed':state['witness'] is not None,
            'start_monotonic_ns':str(interval[0][0]) if interval[0] else None,'start_unix_ns':str(interval[0][1]) if interval[0] else None,
            'end_monotonic_ns':str(interval[1][0]) if interval[1] else None,'end_unix_ns':str(interval[1][1]) if interval[1] else None},
        'worker_start_monotonic_ns':str(worker_begin[0]),'worker_start_unix_ns':str(worker_begin[1]),
        'worker_end_monotonic_ns':str(worker_end[0]),'worker_end_unix_ns':str(worker_end[1]),
        'first_failure':first,'cleanup_failures':later[:32],'documents_comparisons':state['documents'],
        'snapshot_body_unentered':status!='incomplete' and module is not None and not module._SNAPSHOTS,
        'source_body_unentered':status!='incomplete' and state['denials']['unexpected_source_entry_attempts']==0,
        'model_body_unentered':status!='incomplete','expected_stop_before_snapshot':state['stop'] is not None,
        'profile_instrumented':True,'profile_overhead_excluded':False,'external_OS_sandbox_required':True,
        'python_audit_covers_all_metadata':False,
        'git_scope':'original_matching_lane_metadata_environment_ambient_credential_behavior_not_proven',
        'denials':state['denials'],'authority':authority()}
    try:
        encoded=canonical(result);require(len(encoded)<=MAX_OUTPUT,'output_bound');_check(globals().get('_BOOTSTRAP_START_NS'))
    except BaseException as error:
        result['status']='incomplete';late=_safe_failure(error,'final_format')
        if result['first_failure'] is None:result['first_failure']=late
        else:result['cleanup_failures']=[*result['cleanup_failures'],late][:32]
    return result


def main(argv=None):
    arguments=sys.argv[1:] if argv is None else argv
    if len(arguments)!=3:
        result={'schema':'si-code-read-interval-diagnostic-v1','status':'incomplete','runtime_head':None,'matching_remote':None,
            'helper_sha256':None,'first_failure':_safe_failure(IntervalRefusal('arguments')),'authority':authority()}
    else:result=run_registered(*arguments)
    raw=canonical(result)
    try:
        require(len(raw)<=MAX_OUTPUT,'output_bound')
        if len(arguments)==3:_check(globals().get('_BOOTSTRAP_START_NS'))
    except BaseException as error:
        result['status']='incomplete';late=_safe_failure(error,'final_format')
        if result.get('first_failure') is None:result['first_failure']=late
        else:result['cleanup_failures']=[*result.get('cleanup_failures',()),late][:32]
        raw=canonical(result)
    print(raw.decode(),flush=True)
    return 2 if result['status']=='incomplete' else 0


if __name__=='__main__':raise SystemExit(main())
