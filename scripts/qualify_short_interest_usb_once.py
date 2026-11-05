"""One finite offline USB inspection envelope; never source admission.

The original five-code initial/source/terminal transaction is unchanged.
An independent owner must retain original stdout and own the actual process
wait, EOF and the SAME 180-second deadline before accepting this observation.
"""
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from types import FrameType, ModuleType

ROOT=Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest')
USB=Path('/Volumes/SANDISK/firstrate')
DRIVER='scripts/qualify_short_interest_usb_once.py'
HELPER='scripts/diagnose_short_interest_code_read_interval.py'
ORIGINAL='scripts/inspect_short_interest_usb_code_snapshot.py'
ORIGINAL_FILES=('data/__init__.py','data/hashing.py','research/short_interest_etf/firstrate_short_interest_inspection.py',
    'scripts/inspect_short_interest_usb_archive.py',ORIGINAL)
CODE_FILES=(*ORIGINAL_FILES,HELPER,DRIVER)
INPUTS=(('full','fundamentals/Short_Interest/Full_Dataset.zip',34319601,'08f019c20384bde811b10d1674dc5067cfded4e4c0097fc8c383649c528429c8'),
    ('year','fundamentals/Short_Interest/2026_data_only.zip',9660009,'3a8a07dec5c91f4e54cda396d9b1483895769d6ecac1a8d1a15a64e873fa191a'),
    ('manifest','manifest.json',327907,'c681af584244d38e3f9dea2ff765cc2c991cb383107a3e542115a4338ee4cdf8'),
    ('readme','fundamentals/Short_Interest/Read_Me_Documentation.txt',1051,'bbcddf477ba3ffacb4b0116e9d3f6c2c2a864576ae748abc8daa825602a16ecf'))
INVOCATION='si-usb-offline-once-20261104-v1'
REF='refs/heads/codex/strategy-short-interest'
ENV={'PATH':'/usr/bin:/bin','GIT_OPTIONAL_LOCKS':'0'}
MAX_SECONDS,MAX_CODE_BYTES,MAX_OUTPUT=180,1024**2,65536
MAX_PRIVATE_AGGREGATE=16384
_USED=False
_ADD_AUDIT=sys.addaudithook
_MODULES=('_si_usb_once_original_v1','_si_usb_once_pipe_helper_v1')
_CODES=frozenset('arguments interpreter attempt_spent clock root code code_changed module_changed original_result private_aggregate namespace_changed forbidden_open forbidden_write forbidden_socket forbidden_subprocess output_bound cleanup'.split())
_DENIALS=('python_write_attempts','python_socket_attempts','forbidden_read_open_attempts','unexpected_subprocess_attempts')


class UsbOnceRefusal(ValueError):pass


def require(value,code):
    if not value:raise UsbOnceRefusal(code)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def authority():
    return {'finite_offline_byte_inspection_only':True,'source_qualified':False,'source_admitted':False,
        'protected_source_custody_verified':False,'denominator_admitted':False,'actual_input_admitted':False,
        'ready_for_backtest':False,'provider_HTTP':0,'source_credential_reads':0,'new_claims':0,'new_STARTs':0,
        'new_charged_bytes':0,'outcome_looks':0,'qc_attempts':0,'QC_or_Safari':False}


def _stamp(info):
    return tuple(getattr(info,name) for name in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink',
        'st_size','st_mtime_ns','st_ctime_ns'))+(getattr(info,'st_flags',0),)


def _check(start):
    now=time.monotonic_ns()
    require(type(start) is int and type(now) is int and 0<=start<=now and now-start<=MAX_SECONDS*10**9,'clock')
    return now


def _failure(error,phase):
    args=BaseException.args.__get__(error,BaseException)
    code=args[0] if type(error) is UsbOnceRefusal and len(args)==1 and type(args[0]) is str and args[0] in _CODES else None
    return {'phase':phase if phase in ('bootstrap','original','extra_code','cleanup','final_format') else 'bootstrap',
        'role':'unknown','code_ordinal':None,'code':code,'original_comparison':None,'actor':'unknown'}


def _git(arguments,start):
    _check(start)
    result=subprocess.run(['git',*arguments],cwd=ROOT,env=ENV,stdin=None,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,timeout=max(.001,min(20,(MAX_SECONDS*10**9-(time.monotonic_ns()-start))/10**9)),check=False)
    require(type(result.returncode) is int and result.returncode==0 and type(result.stdout) is bytes,'code');_check(start)
    return result.stdout


def _authenticate(head,remote,own_sha,start,cleanup):
    require(ROOT.resolve()==ROOT and Path.cwd().resolve()==ROOT,'root')
    require(_git(['rev-parse','--show-toplevel'],start).decode().strip()==str(ROOT)
        and _git(['branch','--show-current'],start).decode().strip()=='codex/strategy-short-interest'
        and _git(['rev-parse','HEAD'],start).decode().strip()==head
        and _git(['status','--porcelain=v1','-z','--untracked-files=all'],start)==b''
        and _git(['rev-parse','refs/remotes/origin/codex/strategy-short-interest'],start).decode().strip()==remote,'root')
    bodies={};rows=[]
    try:
        for name in CODE_FILES:
            _check(start);path=ROOT/name;require(path.resolve()==path,'code')
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
            row=[name,fd,None,None];rows.append(row)  # Own the FD before any fstat/read.
            info=os.fstat(fd);pin=_stamp(info)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and 0<=info.st_size<=MAX_CODE_BYTES,'code')
            raw=os.read(fd,MAX_CODE_BYTES+1)
            require(len(raw)==info.st_size and _stamp(os.fstat(fd))==_stamp(path.lstat())==pin
                and raw==_git(['show',head+':'+name],start),'code')
            require(_stamp(os.fstat(fd))==_stamp(path.lstat())==pin,'code');row[2:]=pin,raw;bodies[name]=raw
        require(digest(bodies[DRIVER])==own_sha,'code')
        return bodies,rows
    except BaseException:
        for row in reversed(rows):
            try:os.close(row[1])
            except BaseException as error:cleanup.append(_failure(error,'cleanup'))
        raise


def _load(name,path,raw):
    require(name not in sys.modules,'namespace_changed')
    module=ModuleType(name);module.__file__=str(ROOT/path);sys.modules[name]=module
    try:exec(compile(raw,module.__file__,'exec'),module.__dict__);return module
    except BaseException:
        if sys.modules.get(name) is module:del sys.modules[name]
        raise


def _install_audit(helper,head,state):
    root=ROOT;helper_root=helper.ROOT;pipe=helper._owned_git_pipe;pipe_code=pipe.__code__
    predicate=helper._git_allowed;predicate_code=predicate.__code__
    policy=tuple((name,helper.__dict__[name]) for name in ('ROOT','REF','CODE_FILES','DRIVER','ENV'))
    helper_environment=tuple(helper.ENV.items());own_environment=ENV;own_environment_items=tuple(ENV.items())
    def original_helper():
        return (ROOT is root and helper.ROOT is helper_root and helper_root==root
            and helper._owned_git_pipe is pipe and pipe.__code__ is pipe_code
            and helper._git_allowed is predicate and predicate.__code__ is predicate_code
            and pipe.__globals__ is predicate.__globals__ is helper.__dict__
            and all(helper.__dict__.get(name) is original for name,original in policy)
            and tuple(helper.ENV.items())==helper_environment
            and ENV is own_environment and tuple(own_environment.items())==own_environment_items)
    code_paths=tuple(ROOT/name for name in CODE_FILES);source_paths=tuple(USB/name for unused,name,unused2,unused3 in INPUTS)
    absolute={str(path) for path in (*code_paths,*source_paths)}
    absolute.update(str(parent) for path in (*code_paths,*source_paths) for parent in path.parents)
    relative={part for path in (*code_paths,*source_paths) for part in path.parts}
    def refuse(key,code):
        state['denials'][key]+=1;error=UsbOnceRefusal(code)
        if state['first'] is None:state['first']=_failure(error,'original')
        raise error
    def audit(event,args):
        if event=='open':
            path,mode,flags=args
            if type(flags) is not int or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):refuse('python_write_attempts','forbidden_write')
            if type(path) is int:
                if original_helper() and pipe(path,mode,flags,head,helper_root):return
                refuse('forbidden_read_open_attempts','forbidden_open')
            text=os.fsdecode(path) if type(path) in (str,bytes) else None
            if text not in absolute and text not in relative:refuse('forbidden_read_open_attempts','forbidden_open')
        elif event.startswith('socket.'):refuse('python_socket_attempts','forbidden_socket')
        elif event=='subprocess.Popen':
            executable,arguments,cwd,environment=args
            if (not original_helper() or executable not in ('git','/usr/bin/git') or type(arguments) is not list or arguments[:1]!=['git']
                    or not predicate(arguments[1:],head) or Path(cwd)!=root or environment!=own_environment):
                refuse('unexpected_subprocess_attempts','forbidden_subprocess')
        elif event in ('os.system','os.exec','os.posix_spawn','os.spawn'):refuse('unexpected_subprocess_attempts','forbidden_subprocess')
    _ADD_AUDIT(audit)
    return audit


def _original_result(module,value,entry,entry_code):
    require(type(value) is dict and len(module._RUNS)==1,'original_result')
    issued=module._RUNS[0];require(type(issued) is tuple and len(issued)==3,'original_result');frame=issued[2]
    require(type(frame) is FrameType
        and module.inspect_registered is entry and entry.__code__ is entry_code
        and frame.f_code is entry_code and frame.f_globals is module.__dict__
        and frame.f_locals.get('result') is value and frame.f_locals.get('state') is issued[1]
        and issued[1]['first'] is None and not issued[1]['later'] and not issued[1]['truncated']
        and value.get('status')=='closed_finite_code_windows_external_byte_inspection'
        and value.get('authority')==module.authority() and value.get('code_file_original10_equal') is True
        and all(value.get(key) is True for key in ('all_initial_code_contexts_closed','all_source_contexts_closed','all_terminal_code_contexts_closed','executed_verified_RAM'))
        and value.get('continuous_shared_ancestor_timestamp_custody') is False,'original_result')
    require(value.get('observation_sha256')==digest(canonical({key:item for key,item in value.items() if key!='observation_sha256'})),'original_result')
    require(all(name not in sys.modules for name in module._ALIASES),'namespace_changed')
    return value


def _private_aggregate(module,proof):
    """Recover only the original retained aggregate, never rows or a new scan."""
    frame=module._RUNS[0][2];graph=frame.f_locals.get('graph')
    require(type(graph) is module._Graph and graph.closed is True
        and graph.model is graph.modules[module._ALIASES[3]] and graph.hashing is graph.modules[module._ALIASES[1]]
        and tuple(graph.modules.items())==graph.module_originals,'private_aggregate')
    auditors=[row for row in graph.runtime_functions if row[0]=='_audit_module']
    require(len(auditors)==1 and module._audit_module is auditors[0][1]
        and auditors[0][1].__code__ is auditors[0][2],'private_aggregate')
    audit=auditors[0][1]
    pins={id(owner):pin for owner,pin in graph.pins}
    require(all(id(owner) in pins for owner in (graph.model,graph.hashing,graph.reader)),'private_aggregate')
    for owner in (graph.model,graph.hashing,graph.reader):audit(owner,pins[id(owner)])
    rows={name:(kind,pin) for name,kind,pin in pins[id(graph.model)]}
    kind,class_pin=rows['FirstRateByteInspection'];require(kind=='class' and graph.model.FirstRateByteInspection is class_pin[0],'private_aggregate')
    methods={name:(kind,pin) for name,kind,pin in class_pin[1]}
    require(methods['_guard'][0]==methods['to_payload'][0]=='function','private_aggregate')
    guard,getter=methods['_guard'][1],methods['to_payload'][1]
    require(class_pin[0].__dict__['_guard'] is guard[0] and guard[0].__code__ is guard[1]
        and class_pin[0].__dict__['to_payload'] is getter[0] and getter[0].__code__ is getter[1],'private_aggregate')
    issued=graph.model._ISSUED
    require(type(issued) is dict and len(issued)==1,'private_aggregate')
    identifier,witness=next(iter(issued.items()))
    require(type(identifier) is int and type(witness) is tuple and len(witness)==2,'private_aggregate')
    value,anchor=witness
    require(type(value) is class_pin[0] and identifier==id(value) and type(anchor) is tuple and len(anchor)==2
        and value._anchor is value._identity is anchor and value._raw is anchor[0] and value._sha is anchor[1]
        and type(value._raw) is bytes and 0<len(value._raw)<=MAX_PRIVATE_AGGREGATE,'private_aggregate')
    source_producers=[row for row in graph.runtime_functions if row[0]=='_inspect_sources']
    require(len(source_producers)==1 and module._inspect_sources is source_producers[0][1]
        and source_producers[0][1].__code__ is source_producers[0][2],'private_aggregate')
    inspected=frame.f_locals.get('inspected')
    require(type(inspected) is tuple and len(inspected)==2
        and inspected==(proof['inspection_report_sha256'],proof['model_policy_sha256']),'private_aggregate')
    sources=[]
    expected_paths={role:USB/name for role,name,unused,unused2 in INPUTS}
    for origin in graph.reader._READ_ORIGINS.values():
        if type(origin) is not tuple or len(origin)!=4:continue
        item,component,reopen,creator=origin
        if reopen is not False or type(component) is not tuple or len(component)!=2 or component[0] not in expected_paths:continue
        require(type(item) is graph.reader._Read and item.component is component and item._reopen is reopen
            and type(creator) is FrameType and creator.f_code is graph.reader._Read.__init__.__code__
            and creator.f_globals is graph.reader.__dict__ and creator.f_locals.get('origin') is origin
            and creator.f_locals.get('self') is item and item.path==expected_paths[component[0]],'private_aggregate')
        source=creator.f_back
        require(type(source) is FrameType and source.f_code is source_producers[0][2] and source.f_globals is module.__dict__
            and source.f_back is frame and source.f_locals.get('graph') is graph
            and source.f_locals.get('report') is value and source.f_locals.get('inspected') is inspected,'private_aggregate')
        sources.append((component[0],source))
    require(len(sources)==4 and {role for role,unused in sources}==set(expected_paths)
        and all(source is sources[0][1] for unused,source in sources),'private_aggregate')
    guard[0](value);payload=getter[0](value);raw=canonical(payload)
    expected=graph.model.authority();observed=payload.get('authority')
    require(raw==value._raw and digest(raw)==value._sha==proof['inspection_report_sha256']
        and digest(canonical(graph.model.inspection_policy()))==proof['model_policy_sha256']==payload.get('policy_sha256')
        and type(observed) is dict and set(observed)==set(expected)
        and all(type(observed[key]) is type(item) and observed[key]==item for key,item in expected.items()),'private_aggregate')
    guard[0](value)
    for owner in (graph.model,graph.hashing,graph.reader):audit(owner,pins[id(owner)])
    return payload


def run_registered(head,matching_remote,driver_sha256):
    global _USED
    valid=bool(type(head) is type(matching_remote) is type(driver_sha256) is str
        and re.fullmatch('[0-9a-f]{40}',head) and re.fullmatch('[0-9a-f]{40}',matching_remote)
        and re.fullmatch('[0-9a-f]{64}',driver_sha256))
    identifiers=(head,matching_remote,driver_sha256) if valid else (None,None,None)
    start=globals().get('_BOOTSTRAP_START_NS');state={'first':None,'denials':{name:0 for name in _DENIALS}}
    rows=[];loaded=[];bodies=proof=aggregate=None;later=[];phase='bootstrap';status='incomplete'
    try:
        require(not _USED,'attempt_spent');_USED=True;require(valid,'arguments');require(sys.version_info[:2]==(3,13),'interpreter');_check(start)
        bodies,rows=_authenticate(head,matching_remote,driver_sha256,start,later)
        helper=_load(_MODULES[1],HELPER,bodies[HELPER]);loaded.append(helper)
        original=_load(_MODULES[0],ORIGINAL,bodies[ORIGINAL]);loaded.append(original)
        require(helper.ROOT==ROOT and original.ROOT==ROOT and original.USB==USB and original.CODE_FILES==ORIGINAL_FILES
            and original.INPUTS==INPUTS and original.MAX_SECONDS==180,'module_changed')
        for name in sorted(original._STDLIB):importlib.import_module(name)
        entry=original.inspect_registered;entry_code=entry.__code__
        _install_audit(helper,head,state);phase='original'
        # No diagnostic stop hook and no helper.run_registered invocation.
        proof=_original_result(original,entry(head,matching_remote),entry,entry_code);_check(start)
        aggregate=_private_aggregate(original,proof);_check(start)
        require(not any(state['denials'].values()),'original_result');phase='extra_code'
        # Git equality for all7 was established before audit. The unchanged
        # original5 terminal Git/HEAD guard has returned. No post-audit show(self).
        for name,fd,pin,raw in rows:
            if name not in (HELPER,DRIVER):continue
            require((ROOT/name).resolve()==ROOT/name and _stamp(os.fstat(fd))==_stamp((ROOT/name).lstat())==pin,'code_changed')
            os.lseek(fd,0,os.SEEK_SET);require(os.read(fd,MAX_CODE_BYTES+1)==raw,'code_changed')
            require(_stamp(os.fstat(fd))==_stamp((ROOT/name).lstat())==pin,'code_changed');_check(start)
        require(_git(['rev-parse','HEAD'],start).decode().strip()==head,'root')
        status='closed_finite_offline_byte_inspection'
    except BaseException as error:
        if loaded and loaded[-1].__name__==_MODULES[0] and type(error) is loaded[-1].CodeSnapshotRefusal:
            original_failure=loaded[-1].failure_summary(error);fact=original_failure['first_failure'];later=original_failure['cleanup_failures']
        else:fact=_failure(error,phase)
        if state['first'] is None:state['first']=fact
        elif fact!=state['first']:later=[*later,fact]
    finally:
        for name,fd,pin,raw in reversed(rows):
            try:os.close(fd)
            except BaseException as error:
                status='incomplete';fact=_failure(error,'cleanup')
                if state['first'] is None:state['first']=fact
                else:later.append(fact)
        for module in reversed(loaded):
            if sys.modules.get(module.__name__) is module:del sys.modules[module.__name__]
            else:
                status='incomplete';fact=_failure(UsbOnceRefusal('namespace_changed'),'cleanup')
                if state['first'] is None:state['first']=fact
                else:later.append(fact)
    try:
        for name,fd,pin,raw in rows:
            if name in (HELPER,DRIVER):require((ROOT/name).resolve()==ROOT/name and _stamp((ROOT/name).lstat())==pin,'code_changed')
        _check(start)
    except BaseException as error:
        status='incomplete';fact=_failure(error,'cleanup')
        if state['first'] is None:state['first']=fact
        else:later.append(fact)
    result={'schema':'si-usb-once-envelope-v1','invocation_id':INVOCATION,'status':status,
        'runtime_head':identifiers[0],'matching_remote':identifiers[1],'driver_sha256':identifiers[2],
        'interpreter_version':list(sys.version_info[:3]),'maximum_whole_seconds':MAX_SECONDS,
        'whole_start_monotonic_ns':str(start) if type(start) is int else None,'whole_end_monotonic_ns':str(time.monotonic_ns()),
        'code_manifest_sha256':digest(canonical({name:digest(raw) for name,raw in bodies.items()})) if bodies is not None else None,
        'original_profile_proof':proof,'private_model_aggregate':aggregate,'source_qualified':False,'first_failure':state['first'],'cleanup_failures':later[:32],
        'denials':state['denials'],'external_OS_sandbox_and_independent_owned_wait_required':True,
        'python_audit_covers_all_metadata':False,'extra_code_continuous_ancestor_timestamp_custody':False,
        'git_scope':'original_matching_lane_metadata_environment_ambient_credential_behavior_not_proven','authority':authority()}
    try:require(len(canonical(result))<=MAX_OUTPUT,'output_bound');_check(start)
    except BaseException as error:
        result['status']='incomplete';fact=_failure(error,'final_format')
        if result['first_failure'] is None:result['first_failure']=fact
        else:result['cleanup_failures']=[*result['cleanup_failures'],fact][:32]
    return result


def main(argv=None):
    arguments=sys.argv[1:] if argv is None else argv
    if len(arguments)==3:result=run_registered(*arguments)
    else:result={'schema':'si-usb-once-envelope-v1','invocation_id':INVOCATION,'status':'incomplete','source_qualified':False,
        'runtime_head':None,'matching_remote':None,'driver_sha256':None,'first_failure':_failure(UsbOnceRefusal('arguments'),'bootstrap'),'authority':authority()}
    raw=canonical(result)
    try:
        require(len(raw)<=MAX_OUTPUT,'output_bound')
        if len(arguments)==3:_check(globals().get('_BOOTSTRAP_START_NS'))
    except BaseException as error:
        result['status']='incomplete';fact=_failure(error,'final_format')
        if result.get('first_failure') is None:result['first_failure']=fact
        else:result['cleanup_failures']=[*result.get('cleanup_failures',()),fact][:32]
        raw=canonical(result)
    print(raw.decode(),flush=True);return 0 if result['status']=='closed_finite_offline_byte_inspection' else 2


if __name__=='__main__':raise SystemExit(main())
