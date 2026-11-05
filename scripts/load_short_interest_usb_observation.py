"""Authenticate a fixed historical observation, never a live/source capability.

Detailed assessment bytes are PRIVATE. Main's committed historical attestation
does not reconstruct its old process handle, upstream provenance or row inputs.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from types import FrameType, FunctionType, ModuleType

ROOT=Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest')
DIRECTORY=Path('/Users/sheltonchen/Library/Application Support/CodexShortInterestUSBObservation/si-usb-offline-once-20261104-v1')
DRIVER='scripts/load_short_interest_usb_observation.py'
MODEL='research/short_interest_etf/firstrate_retained_qualification.py'
ANCHOR='research/short_interest_etf/specs/usb_observation_anchor_20261104_v1.json'
ANCHOR_SHA256='dc8518ff48d574dab0b0ac798ae09624784a54ee94ef90138de8e1064f1c7cb9'
MODEL_POLICY_SHA256='9408f0c4c4f2edca105c9f710670ed34d3fef507bdf0bb6b44bce0e266063230'
INVOCATION='si-usb-offline-once-20261104-v1'
NAMES=('producer.stdout.private','observation.private.json')
CODE_FILES=(DRIVER,MODEL,ANCHOR)
MAX_SECONDS=30
MAX_CODE=1024**2
MAX_PACKET=65537
MAX_ASSESSMENT=32768
ALIAS='_si_firstrate_retained_qualification_v1'
TRUST='Main-attested historical closure authenticated from committed evidence; not a live process or source capability'
_USED=False
_ISSUED={}
_FAILED=set()
_NEGATIVES={}
_CLOCKS={}
_ATTEMPTS=[]
_REGISTRIES=(_ISSUED,_FAILED,_NEGATIVES,_CLOCKS,_ATTEMPTS)
_CODES=frozenset('arguments spent clock lane code anchor history directory membership file stamp bytes model model_changed report closure namespace'.split())
_PHASES=frozenset('bootstrap code anchor historical_code directory files packet qualification close postclose final issue final_format'.split())


class UsbObservationRefusal(ValueError):pass


def require(value,code):
    if not value:raise UsbObservationRefusal(code)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def authority():
    return {'historical_observation_only':True,'source_qualified':False,'source_admitted':False,
        'protected_source_custody_verified':False,'native_identity_admitted':False,'share_class_admitted':False,
        'denominator_admitted':False,'actual_input_admitted':False,'point_in_time_data':False,
        'ready_for_backtest':False,'live_process_capability':False,'provider_HTTP':0,'source_credential_reads':0,
        'new_claims':0,'new_STARTs':0,'new_charged_bytes':0,'outcome_looks':0,'qc_attempts':0,'QC_or_Safari':False}


def _closed_authority(value,marker):
    counters={'provider_HTTP','credential_reads','source_credential_reads','new_claims','new_STARTs','new_charged_bytes','outcome_looks','qc_attempts','allocated_alpha'}
    return (type(value) is dict and value.get(marker) is True and value.get('source_admitted') is False
        and all(type(item) is int and item==0 for key,item in value.items() if key in counters)
        and all(item is True if key==marker else item is False or type(item) is int and item==0 for key,item in value.items()))


def _same(value,expected):
    if type(value) is not type(expected):return False
    if type(expected) is dict:return set(value)==set(expected) and all(_same(value[key],item) for key,item in expected.items())
    if type(expected) is list:return len(value)==len(expected) and all(_same(a,b) for a,b in zip(value,expected))
    return value==expected


def _pairs(items):
    value={}
    for key,item in items:require(key not in value,'bytes');value[key]=item
    return value


def _json(raw,lf=False):
    require(type(raw) is bytes,'bytes')
    value=json.loads(raw,object_pairs_hook=_pairs,parse_constant=lambda unused:require(False,'bytes'))
    require(canonical(value)+(b'\n' if lf else b'')==raw,'bytes');return value


def _stamp(info):
    return tuple(getattr(info,name) for name in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink',
        'st_size','st_mtime_ns','st_ctime_ns'))+(getattr(info,'st_flags',0),)


def _dir(info):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0,os.getuid()) and not info.st_mode&0o022,'directory')
    return info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode


def _fact(error,phase):
    args=BaseException.args.__get__(error,BaseException)
    code=args[0] if type(error) is UsbObservationRefusal and len(args)==1 and type(args[0]) is str and args[0] in _CODES else None
    return {'phase':phase if phase in _PHASES else 'bootstrap','code':code}


class _Clock:
    def __init__(self):
        function=time.monotonic_ns;began=function();self.function=function;self.start=self.last=began;self.failed=False
        require(type(began) is int and began>=0,'clock')
        origin=self,began,function,getattr(function,'__code__',None),sys._getframe();self.origin=origin;_CLOCKS[id(self)]=origin
    def check(self):
        try:
            row=_CLOCKS.get(id(self));require(not self.failed and type(row) is tuple and row is self.origin and row[0] is self
                and self.start==row[1] and self.function is row[2] is time.monotonic_ns
                and getattr(row[2],'__code__',None) is row[3] and row[4].f_code is _Clock.__init__.__code__
                and row[4].f_globals is globals() and row[4].f_locals.get('origin') is row,'clock');now=row[2]()
            require(type(now) is int and row[1]<=self.last<=now and now-row[1]<=MAX_SECONDS*10**9,'clock')
            self.last=now;_runtime();return now
        except BaseException:self.failed=True;raise


def _git(clock,*arguments):
    clock.check();value=subprocess.run(['git',*arguments],cwd=ROOT,env={'PATH':'/usr/bin:/bin','GIT_OPTIONAL_LOCKS':'0'},
        stdin=None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=max(.001,min(10,(MAX_SECONDS*10**9-(clock.last-clock.start))/10**9)),check=False)
    require(type(value.returncode) is int and value.returncode==0 and type(value.stdout) is bytes,'code');clock.check();return value.stdout


def _guard(clock,head,remote):
    require(ROOT.resolve()==ROOT and Path.cwd().resolve()==ROOT,'lane')
    require(_git(clock,'rev-parse','--show-toplevel').decode().strip()==str(ROOT)
        and _git(clock,'branch','--show-current').decode().strip()=='codex/strategy-short-interest'
        and _git(clock,'rev-parse','HEAD').decode().strip()==head
        and _git(clock,'status','--porcelain=v1','-z','--untracked-files=all')==b''
        and _git(clock,'rev-parse','refs/remotes/origin/codex/strategy-short-interest').decode().strip()==remote
        and _git(clock,'ls-remote','--exit-code','--refs','origin','refs/heads/codex/strategy-short-interest').decode().split()==[remote,'refs/heads/codex/strategy-short-interest'],'lane')


def _code_open(clock,head,rows):
    bodies={}
    for name in CODE_FILES:
        clock.check();path=ROOT/name;require(path.resolve()==path,'code')
        expected=_git(clock,'show',head+':'+name)
        require(len(expected)<=MAX_CODE,'code')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC);row=[name,fd,None,None];rows.append(row)
        info=os.fstat(fd);pin=_stamp(info)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid() and not info.st_mode&0o022 and info.st_size==len(expected),'code')
        raw=os.read(fd,MAX_CODE+1)
        require(raw==expected and _stamp(os.fstat(fd))==_stamp(path.lstat())==pin,'code')
        row[2:]=pin,raw;bodies[name]=raw
    return bodies


def _code_audit(clock,rows,named=False):
    for name,fd,pin,raw in rows:
        clock.check();path=ROOT/name;require(pin is not None and path.resolve()==path and _stamp(path.lstat())==pin,'code')
        if not named:
            require(_stamp(os.fstat(fd))==pin,'code');os.lseek(fd,0,os.SEEK_SET)
            require(os.read(fd,MAX_CODE+1)==raw and _stamp(os.fstat(fd))==pin,'code')
    clock.check()


def _anchor(raw,clock,head):
    require(digest(raw)==ANCHOR_SHA256,'anchor');value=_json(raw,lf=True)
    require(set(value)=={'schema','anchor_id','trust_statement','main_attestation','historical_runtime','private_artifacts',
        'original_owned_observation','original_owned_observation_sha256','original_profile_proof','original_copier_receipt',
        'original_independent_audit','original_local_process_closures','interpretation','unchanged_access'}
        and value['schema']=='si-firstrate-retained-observation-main-anchor-v1'
        and value['trust_statement']==TRUST,'anchor')
    history=value['historical_runtime'];owned=value['original_owned_observation'];proof=value['original_profile_proof'];artifacts=value['private_artifacts']
    require(history['physical_root']==str(ROOT) and history['branch']=='codex/strategy-short-interest'
        and artifacts['fixed_run']==str(DIRECTORY) and artifacts['exact_members']==list(NAMES)
        and set(artifacts['files'])==set(NAMES),'anchor')
    require(digest(canonical(owned))==value['original_owned_observation_sha256']
        and owned['status']=='closed_finite_offline_byte_observation' and owned['source_qualified'] is False
        and owned['runtime_head']==history['creator_head'] and owned['matching_remote']==history['matching_remote']
        and proof['runtime_head']==history['creator_head'] and proof['matching_remote']==history['matching_remote']
        and owned['private_model_aggregate_sha256']==proof['inspection_report_sha256']
        and digest(canonical({key:item for key,item in proof.items() if key!='observation_sha256'}))==proof['observation_sha256'],'anchor')
    require(artifacts['files']==value['original_copier_receipt']['files']==value['original_independent_audit']['files']
        and all(artifacts[key]==value['original_copier_receipt'][key]==value['original_independent_audit'][key] for key in ('directory5_sha256','ancestry5_sha256')),'anchor')
    require(value['main_attestation']['historical_only'] is True and value['main_attestation']['source_authority'] is False
        and value['main_attestation']['accepted_before_original_deadline'] is True
        and type(value['main_attestation']['captured_final_controller_elapsed_ms']) is int
        and 0<=value['main_attestation']['captured_final_controller_elapsed_ms']<=180000
        and value['interpretation']['source_rows_retained_in_observation_packet'] is False
        and value['interpretation']['source_qualified'] is value['interpretation']['source_admitted'] is False
        and _closed_authority(proof['authority'],'external_byte_inspection_only')
        and all(type(item) is int and item==0 for item in value['unchanged_access'].values()),'anchor')
    require(type(owned['actual_exit_code']) is int and owned['actual_exit_code']==0 and owned['actual_signal'] is None
        and all(owned[key] is True for key in ('exit_observed','close_observed','stdout_EOF','stderr_EOF','original_stdout_complete'))
        and owned['test_seams_used'] is False and owned['first_failure'] is None and owned['cleanup_failures']==[],'anchor')
    require(len(value['original_local_process_closures'])==2 and all(type(row['exit_code']) is int and row['exit_code']==0
        and row['signal'] is None and row['failure'] is None and row['stderr_bytes']==0
        and all(row[key] is True for key in ('close_observed','exit_observed','stdout_EOF','stderr_EOF')) for row in value['original_local_process_closures']),'anchor')
    require(_git(clock,'merge-base','--is-ancestor',history['creator_head'],head)==b'','history')
    mapping=history['source_code_mapping'];worker=history['worker_source_code_mapping'];ordered=history['execution9_path_list']
    require(type(mapping) is dict and len(mapping)==9 and type(worker) is dict and len(worker)==7
        and type(ordered) is list and len(ordered)==len(set(ordered))==9 and set(ordered)==set(mapping)
        and set(worker)<set(mapping) and all(mapping[key]==item for key,item in worker.items())
        and digest(canonical(mapping))==history['execution9_mapping_sha256']
        and digest(canonical(ordered))==history['execution9_path_list_sha256']
        and digest(canonical(worker))==history['worker7_mapping_sha256']
        and set(ordered[:7])==set(worker)
        and digest(canonical({path:mapping[path] for path in ordered[:5]}))==proof['code_mapping_sha256'],'history')
    for path,expected in mapping.items():
        require(type(path) is str and not Path(path).is_absolute() and '..' not in Path(path).parts
            and type(expected) is str and re.fullmatch('[0-9a-f]{64}',expected),'history')
        require(digest(_git(clock,'show',history['creator_head']+':'+path))==expected,'history')
    return value


class _PrivateFiles:
    def __init__(self,clock,anchor):self.clock=clock;self.anchor=anchor;self.nodes=[];self.fds=[];self.rows=[];self.fd=None
    def open(self):
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);self.fds.append(fd)
        path=Path('/');self.nodes.append((path,fd,_dir(os.fstat(fd))))
        for part in DIRECTORY.parts[1:]:
            self.clock.check();path/=part;fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            self.fds.append(fd);self.nodes.append((path,fd,_dir(os.fstat(fd))))
        self.fd=fd;self.audit();bodies={}
        for name in NAMES:
            expected=self.anchor['private_artifacts']['files'][name];self.clock.check()
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=self.fd)
            row=[name,fd,None,None];self.rows.append(row);info=os.fstat(fd);pin=_stamp(info)
            require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1
                and 0<info.st_size<=MAX_PACKET and info.st_size==expected['bytes']
                and digest(canonical(list(pin)))==expected['original_file10_sha256'],'stamp')
            raw=os.read(fd,MAX_PACKET+1)
            require(len(raw)==expected['bytes'] and digest(raw)==expected['sha256'],'bytes');row[2:]=pin,raw;bodies[name]=raw;self.file_audit(row)
        return bodies
    def audit(self,named=False):
        self.clock.check();pins=[]
        for path,fd,pin in self.nodes:
            require(path.resolve()==path and _dir(path.lstat())==pin and (named or _dir(os.fstat(fd))==pin),'directory');pins.append(list(pin))
        expected=self.anchor['private_artifacts']
        require(self.fd is not None and digest(canonical(pins))==expected['ancestry5_sha256']
            and digest(canonical(pins[-1]))==expected['directory5_sha256']
            and stat.S_IMODE(pins[-1][4])==0o700 and pins[-1][2]==os.getuid(),'directory')
        require(set(os.listdir(DIRECTORY if named else self.fd))==set(NAMES),'membership');self.clock.check()
    def file_audit(self,row,named=False):
        name,fd,pin,raw=row;self.audit(named)
        require(pin is not None and _stamp((DIRECTORY/name).lstat())==pin,'stamp')
        if not named:
            require(_stamp(os.fstat(fd))==pin,'stamp');os.lseek(fd,0,os.SEEK_SET)
            require(os.read(fd,MAX_PACKET+1)==raw and _stamp(os.fstat(fd))==pin,'bytes')
        self.clock.check()


def _packet(bodies,anchor):
    raw=bodies[NAMES[0]];require(raw.endswith(b'\n') and not raw.endswith(b'\n\n'),'bytes');packet=_json(raw,lf=True)
    saved=_json(bodies[NAMES[1]]);owned=anchor['original_owned_observation'];proof=anchor['original_profile_proof']
    require(set(saved)=={'schema','runtime_head','matching_remote','invocation_id','process_claims','original_stdout_bytes','original_stdout_sha256','owned_observation','source_authority'}
        and saved['schema']=='si-usb-observation-private-copy-v1' and saved['runtime_head']==owned['runtime_head']
        and saved['matching_remote']==owned['matching_remote'] and saved['invocation_id']==INVOCATION
        and _same(saved['owned_observation'],owned) and digest(canonical(saved['owned_observation']))==anchor['original_owned_observation_sha256']
        and saved['process_claims']=='caller_attested_historical_copy_not_independently_observed'
        and saved['source_authority'] is False and saved['original_stdout_sha256']==digest(raw)
        and saved['original_stdout_bytes']==len(raw),'anchor')
    require(packet['schema']=='si-usb-once-envelope-v1' and packet['status']=='closed_finite_offline_byte_inspection'
        and packet['invocation_id']==INVOCATION and packet['runtime_head']==owned['runtime_head']
        and packet['matching_remote']==owned['matching_remote'] and _same(packet['original_profile_proof'],proof)
        and packet['code_manifest_sha256']==owned['producer_code_manifest_sha256']
        and packet['source_qualified'] is False and packet['first_failure'] is None and packet['cleanup_failures']==[]
        and _closed_authority(packet['authority'],'finite_offline_byte_inspection_only')
        and set(packet['denials'])=={'python_write_attempts','python_socket_attempts','forbidden_read_open_attempts','unexpected_subprocess_attempts'}
        and all(type(item) is int and item==0 for item in packet['denials'].values()),'anchor')
    aggregate=canonical(packet['private_model_aggregate'])
    require(len(aggregate)==owned['private_model_aggregate_bytes']<=16384
        and digest(aggregate)==owned['private_model_aggregate_sha256']==proof['inspection_report_sha256'],'anchor')
    return aggregate


def _model(raw):
    require(ALIAS not in sys.modules,'namespace');module=ModuleType(ALIAS);module.__file__=str(ROOT/MODEL);sys.modules[ALIAS]=module
    try:exec(compile(raw,module.__file__,'exec'),module.__dict__)
    except BaseException:
        if sys.modules.get(ALIAS) is module:del sys.modules[ALIAS]
        raise
    bindings=[]
    for name,value in module.__dict__.items():
        code=value.__code__ if type(value) is FunctionType else None
        methods=tuple((key,item,item.fget if type(item) is property else item,getattr(item.fget if type(item) is property else item,'__code__',None))
            for key,item in value.__dict__.items()) if type(value) is type and value.__module__==ALIAS else None
        bindings.append((name,value,code,methods))
    return module,tuple(bindings)


def _model_audit(module,bindings):
    require(sys.modules.get(ALIAS) is module and tuple(module.__dict__)==tuple(row[0] for row in bindings),'model_changed')
    for name,value,code,methods in bindings:
        require(module.__dict__[name] is value and (code is None or value.__code__ is code),'model_changed')
        if methods is not None:
            require(tuple(value.__dict__)==tuple(row[0] for row in methods),'model_changed')
            for key,item,function,original_code in methods:require(value.__dict__[key] is item and (original_code is None or function.__code__ is original_code),'model_changed')


class ClosedRetainedUsbQualification:
    __slots__=('_anchor',)
    def __init__(self):raise UsbObservationRefusal('report')
    def _record(self):
        try:
            _runtime();row=_ISSUED.get(id(self));require(id(self) not in _FAILED and type(self) is ClosedRetainedUsbQualification
                and type(row) is tuple and len(row)==7 and row[0] is self and self._anchor is row,'report')
            frame=row[6];require(type(frame) is FrameType and frame.f_code is _issue.__code__ and frame.f_globals is globals()
                and frame.f_locals.get('row') is row and frame.f_locals.get('value') is self
                and frame.f_locals.get('terminal') is row[4] and digest(row[1])==row[2],'report');return row
        except BaseException:
            if type(self) is ClosedRetainedUsbQualification:_FAILED.add(id(self))
            raise
    def canonical_bytes(self):return self._record()[1]
    @property
    def sha256(self):return self._record()[2]
    def public_summary(self):return _json(self._record()[3])


def _issue(payload,summary,terminal,clock):
    caller=sys._getframe(1);require(caller.f_code is qualify_registered_observation.__code__ and caller.f_globals is globals()
        and caller.f_locals.get('terminal') is terminal and caller.f_locals.get('payload') is payload
        and caller.f_locals.get('summary') is summary and terminal[0]=='all_original_contexts_closed','closure')
    raw=canonical(payload);public=canonical(summary);clock.check();value=object.__new__(ClosedRetainedUsbQualification)
    row=value,raw,digest(raw),public,terminal,clock,sys._getframe();value._anchor=row;_ISSUED[id(value)]=row;return value


def qualify_registered_observation(head,remote):
    global _USED
    clock=_Clock();state={'first':None,'later':[]};rows=[];scope=module=bindings=anchor=assessment_raw=None;phase='bootstrap'
    def fail(error,where):
        fact=_fact(error,where)
        if state['first'] is None:state['first']=fact
        elif len(state['later'])<16:state['later'].append(fact)
    try:
        require(not _USED and not _ATTEMPTS,'spent');_USED=True;_ATTEMPTS.append((clock,sys._getframe()))
        require(type(head) is type(remote) is str and re.fullmatch('[0-9a-f]{40}',head) and re.fullmatch('[0-9a-f]{40}',remote),'arguments')
        _guard(clock,head,remote);phase='code';bodies=_code_open(clock,head,rows);phase='anchor';anchor=_anchor(bodies[ANCHOR],clock,head)
        phase='qualification';module,bindings=_model(bodies[MODEL]);entry=module.evaluate_retained_aggregate;entry_code=entry.__code__
        require(module.POLICY_SHA256==MODEL_POLICY_SHA256 and digest(canonical(module.qualification_policy()))==MODEL_POLICY_SHA256,'model')
        phase='directory';scope=_PrivateFiles(clock,anchor);private=scope.open();phase='packet';aggregate=_packet(private,anchor)
        phase='qualification';_model_audit(module,bindings);assessment=entry(aggregate)
        require(module.evaluate_retained_aggregate is entry and entry.__code__ is entry_code
            and type(assessment) is module.RetainedAggregateAssessment,'model')
        _model_audit(module,bindings);getter=module.RetainedAggregateAssessment.canonical_bytes;assessment_raw=getter(assessment)
        require(type(assessment_raw) is bytes and 0<len(assessment_raw)<=MAX_ASSESSMENT and digest(assessment_raw)==assessment.sha256,'model')
        assessed=_json(assessment_raw)
        require(assessed['policy_sha256']==MODEL_POLICY_SHA256 and assessed['input_aggregate_sha256']==digest(aggregate)
            and _same(assessed['authority'],module.authority()),'model');_model_audit(module,bindings)
        for row in scope.rows:scope.file_audit(row)
        _code_audit(clock,rows);_guard(clock,head,remote)
    except BaseException as error:fail(error,phase)
    finally:
        if scope is not None:
            for row in reversed(scope.rows):
                try:os.close(row[1])
                except BaseException as error:fail(error,'close')
            for fd in reversed(scope.fds):
                try:os.close(fd)
                except BaseException as error:fail(error,'close')
            try:
                scope.audit(named=True)
                for row in scope.rows:scope.file_audit(row,named=True)
            except BaseException as error:fail(error,'postclose')
        if module is not None:
            try:_model_audit(module,bindings)
            except BaseException as error:fail(error,'close')
            if sys.modules.get(ALIAS) is module:del sys.modules[ALIAS]
            else:fail(UsbObservationRefusal('namespace'),'close')
        try:_code_audit(clock,rows)
        except BaseException as error:fail(error,'close')
        for row in reversed(rows):
            try:os.close(row[1])
            except BaseException as error:fail(error,'close')
    try:
        _code_audit(clock,rows,named=True);_guard(clock,head,remote)
        if scope is not None:
            scope.audit(named=True)
            for row in scope.rows:scope.file_audit(row,named=True)
        clock.check()
    except BaseException as error:fail(error,'final')
    if state['first'] is None:
        try:
            require(anchor is not None and assessment_raw is not None,'closure')
            terminal=('all_original_contexts_closed',clock.check(),ANCHOR_SHA256)
            payload={'schema':'si-authenticated-historical-usb-qualification-v1','trust_statement':TRUST,'runtime_head':head,'matching_remote':remote,
                'anchor_sha256':ANCHOR_SHA256,'historical_creator_head':anchor['historical_runtime']['creator_head'],
                'original_observation_sha256':anchor['original_owned_observation_sha256'],'private_aggregate_sha256':anchor['original_profile_proof']['inspection_report_sha256'],
                'assessment':_json(assessment_raw),'authority':authority()}
            summary={'schema':'si-retained-usb-qualification-summary-v1','status':'closed_authenticated_historical_metadata_only','trust_statement':TRUST,
                'runtime_head':head,'matching_remote':remote,'anchor_sha256':ANCHOR_SHA256,'assessment_sha256':digest(assessment_raw),
                'original_observation_sha256':anchor['original_owned_observation_sha256'],'maximum_local_seconds':MAX_SECONDS,
                'first_failure':None,'cleanup_failures':[],'authority':authority()}
            return _issue(payload,summary,terminal,clock)
        except BaseException as error:fail(error,'issue')
    error=UsbObservationRefusal('closure');negative=error,canonical({'schema':'si-retained-usb-qualification-summary-v1','status':'incomplete',
        'first_failure':state['first'],'cleanup_failures':state['later'],'authority':authority()}),sys._getframe()
    _NEGATIVES[id(error)]=negative;raise error


def _make_failure_summary(authority_raw):
    registry=_NEGATIVES;issuer=qualify_registered_observation;issuer_code=issuer.__code__;namespace=globals()
    decoder=json.loads;codes=_CODES;error_class=UsbObservationRefusal;arguments=BaseException.args
    def project(error):
        row=registry.get(id(error))
        if type(row) is tuple and len(row)==3 and row[0] is error:
            frame=row[2]
            if (type(frame) is FrameType and frame.f_code is issuer_code and frame.f_globals is namespace
                    and frame.f_locals.get('negative') is row and frame.f_locals.get('error') is error):
                value=decoder(row[1]);value['authority']=decoder(authority_raw);return value
        args=arguments.__get__(error,BaseException) if isinstance(error,BaseException) else ()
        code=args[0] if type(error) is error_class and len(args)==1 and type(args[0]) is str and args[0] in codes else None
        return {'schema':'si-retained-usb-qualification-summary-v1','status':'incomplete',
            'first_failure':{'phase':'bootstrap','code':code},'cleanup_failures':[],'authority':decoder(authority_raw)}
    return project


def main(argv=None):
    arguments=sys.argv[1:] if argv is None else argv;value=None
    try:
        require(len(arguments)==2,'arguments');value=qualify_registered_observation(*arguments);summary=value.public_summary()
        raw=canonical(summary);value._record()[5].check()
    except BaseException as error:
        if value is not None:
            _FAILED.add(id(value));summary=failure_summary(error);summary['first_failure']=_fact(error,'final_format')
        else:summary=failure_summary(error)
        raw=canonical(summary)
    print(raw.decode(),flush=True);return 0 if summary['status']=='closed_authenticated_historical_metadata_only' else 2


def _runtime():
    require(all(globals().get(name) is original for name,original in zip(('_ISSUED','_FAILED','_NEGATIVES','_CLOCKS','_ATTEMPTS'),_REGISTRIES)),'code')
    for name,function,code in _PRODUCERS:
        require(globals().get(name) is function and function.__code__ is code,'code')
    require(all(globals().get(name) is original for name,original in _POLICY),'code')
    for name,cls,methods in _METHODS:
        require(globals().get(name) is cls and tuple(cls.__dict__)==tuple(row[0] for row in methods),'code')
        for key,item,function,code in methods:require(cls.__dict__[key] is item and (code is None or function.__code__ is code),'code')


failure_summary=_make_failure_summary(canonical(authority()))
_POLICY=tuple((name,globals()[name]) for name in ('ROOT','DIRECTORY','DRIVER','MODEL','ANCHOR','ANCHOR_SHA256','MODEL_POLICY_SHA256','INVOCATION','NAMES','CODE_FILES','MAX_SECONDS','MAX_CODE','MAX_PACKET','MAX_ASSESSMENT','ALIAS','TRUST'))
_PRODUCERS=tuple((name,value,value.__code__) for name,value in tuple(globals().items()) if type(value) is FunctionType)
_METHODS=tuple((name,value,tuple((key,item,item.fget if type(item) is property else item,getattr(item.fget if type(item) is property else item,'__code__',None))
    for key,item in value.__dict__.items())) for name,value in tuple(globals().items()) if type(value) is type and value.__module__==__name__)

if __name__=='__main__':raise SystemExit(main())
