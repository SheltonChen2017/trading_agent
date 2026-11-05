"""Fixed AR DATA streaming/archive mechanics; no operation or transfer grant.

The separately frozen caller claims and authenticates genuine original input.
This helper reads only the 73 supplied fixed DATA leaves. It does not interpret
catalog, price or manifest JSON, acquire credentials, or perform any contact.
An interrupted archive is retained and inadmissible; nothing is truncated or
repaired. READY requires source guard normal return, not just a copied tail.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import resource
import stat
import time

from scripts import arv2_relocation_security as security
from scripts import arv2_r298_ar_source_binding as anchor

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SCHEMA = 'arv2-r326-common-price-private-payload-v1'
FIELDS = ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink',
    'st_size','st_mtime_ns','st_ctime_ns','st_flags')
ROLES = ('catalog',*(f'month_{index:03d}' for index in range(71)),'manifest')
CHUNK, MAX_HEADER, MAX_SECONDS = 65536, 65536, 1800
MAX_CATALOG, MAX_MONTH, MAX_MANIFEST = 4*1024*1024, 32*1024*1024, 1024*1024
MAX_PAYLOAD = 517*1024*1024
MAGIC = b'ARV2-PRIVATE-PRICE-PAYLOAD-V1\n'
MAX_ARCHIVE = len(MAGIC)+8+MAX_HEADER+MAX_PAYLOAD
MIN_FREE_DISK = MAX_ARCHIVE+256*1024*1024
FD_WINDOW, MAX_BASELINE_FDS, MAX_SOURCE_FDS = 128, 16, 96
ANCHOR_SOURCE_SHA256 = '52ae31ddb440e1ecaf693d54fb6cf6d48ee377813d8614e7ce3cee5a02d68d76'
FACT_SHA256 = '19194ca0fc562b4b0fed8331d7c6e725c3dd7cc31fada7fa519a08acc10d28b3'
PLAN_SHA256 = '1ad4590b361787b6126f5e4790034565c53a5e51d0173de67c422879160f74d4'
OUTPUT_SHA256 = '70e6def0fe2621965904e31fe8121c7713c5201b9b151397766f78091e7ab843'
FALSE_FLAGS = {'operation_granted':False,'genuine_input_authenticated':False,
    'source_admission_granted':False,'price_input_admitted':False,'QC_transfer_granted':False,
    'QC_processing_rights_granted':False,'remote_durability_proven':False,
    'continuous_or_historical_integrity_proven':False,'point_in_time_proven':False,
    'formal_forward_ready':False,'paper_or_live_ready':False}
FINITE = frozenset(('plan','scope','deadline','state','path','metadata','shape','security',
    'changed','byte_pin','read_schedule','close','receipt','archive_fd','archive_nonempty',
    'archive_write','archive_bound','header','archive_extent','descriptor_budget','disk_budget','os_error'))


class Refused(ValueError): pass


def require(value,code):
    if not value: raise Refused(code)


def finite(error):
    if isinstance(error,OSError):return 'os_error'
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'state'


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


def sha(raw): return hashlib.sha256(raw).hexdigest()


def _hash(value):
    return type(value) is str and len(value)==64 and all(char in '0123456789abcdef' for char in value)


def _deadline(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline)
        and 0<deadline-time.monotonic()<=MAX_SECONDS,'deadline')


def data_plan():
    fact,output,plan=anchor.observed_fact(),anchor.sidecar_output(),anchor.data_plan()
    require(sha(canonical(fact))==FACT_SHA256 and sha(canonical(output))==OUTPUT_SHA256
        and sha(canonical(plan))==PLAN_SHA256 and fact['complete_original_payload_recovered'] is True,'plan')
    for role in ('AR_producer','AR_native_validator','AS_actual'):
        actual=fact[role]
        require(type(actual['actual_exit']) is int and actual['actual_exit']==0
            and actual['spawn_observed'] is True and actual['bound'] is None
            and actual['stderr_bytes']==0 and actual['stderr_sha256']==sha(b'')
            and actual['stdout_bytes']==28655 and actual['stdout_sha256']
            =='5c0a070c1d2f03e4a78adb9400db8a94c4d11b334e1a777a7f0fb65a281bc52b','plan')
    require(sha(canonical(output)+b'\n')==fact['AR_producer']['stdout_sha256'],'plan')
    for key in ('new_operation_or_read_granted','QC_transfer_granted','QC_processing_rights_granted',
            'price_input_admitted','complete_required_price_coverage_proven','point_in_time_proven',
            'formal_identity_admitted','formal_forward_ready','paper_or_live_ready'):
        require(fact[key] is False,'plan')
    return _plan_shape(plan)


def _plan_shape(plan):
    require(type(plan) is dict and set(plan)==set(ROLES) and len(plan)==73,'plan')
    base='artifacts/analyst_revisions_v2/newrule_common_price_sidecar/R326-20261027-AR/'
    for role in ROLES:
        row=plan[role]; name='catalog-private.json' if role=='catalog' else 'manifest-private.json' if role=='manifest' else role.replace('_','-')+'.jsonl'
        maximum=MAX_CATALOG if role=='catalog' else MAX_MANIFEST if role=='manifest' else MAX_MONTH
        require(type(row) is dict and set(row)=={'relative_path','byte_count','sha256'}
            and type(row['byte_count']) is int and 0<row['byte_count']<=maximum
            and _hash(row['sha256']) and row['relative_path']==base+name,'plan')
        path=PurePosixPath(row['relative_path'])
        require(not path.is_absolute() and path.as_posix()==row['relative_path'],'plan')
    require(sum(row['byte_count'] for row in plan.values())<=MAX_PAYLOAD,'plan')
    return json.loads(canonical(plan))


def checked_plan(plan):
    require(plan==data_plan(),'plan')
    return _plan_shape(plan)


def profile_record():
    return {'schema':SCHEMA,'root':str(ROOT),'source_anchor_sha256':ANCHOR_SOURCE_SHA256,
        'source_fact_sha256':FACT_SHA256,'source_output_sha256':OUTPUT_SHA256,
        'data_plan_sha256':PLAN_SHA256,'data_plan':data_plan(),'ordered_roles':list(ROLES),
        'chunk_bytes':CHUNK,'header_maximum_bytes':MAX_HEADER,'payload_maximum_bytes':MAX_PAYLOAD,
        'archive_maximum_bytes':MAX_ARCHIVE,'seconds':MAX_SECONDS,'metadata_fields':list(FIELDS),
        'source_root_mode':'0755','source_below_directory_mode':'0700','source_leaf_mode':'0600_single_link',
        'source_original_descriptors_all_no_follow':True,'source_native_ACL_xattr_endpoints':True,
        'source_authorized_xattrs_only_ordinary_policy_in_frozen_security_helper':True,
        'maximum_source_descriptors':MAX_SOURCE_FDS,'minimum_soft_RLIMIT_NOFILE':FD_WINDOW,
        'maximum_baseline_descriptors_in_first128':MAX_BASELINE_FDS,'minimum_free_disk_bytes':MIN_FREE_DISK,
        'resource_check_is_current_process_observation_not_reservation':True,'no_RLIMIT_change':True,
        'all73_whole_hashes_before_payload_copy':True,'copy_through_original_held_source_FDs':True,
        'source_guard_normal_return_before_READY':True,'independent_archive_verifier_parses_header_only':True,
        'archive_data_streaming_buffer_maximum':CHUNK,'bounded_header_and_security_working_storage_additional':True,
        'parent_claim_genuine_input_original_archive_named_guard_and_actual_exit_required_separately':True,
        'interrupted_archive_retained_no_truncate_or_repair':True,**FALSE_FLAGS}


def metadata(fd):
    try: info=os.fstat(fd);value=tuple(getattr(info,key,None) for key in FIELDS)
    except OSError: raise Refused('metadata') from None
    require(all(type(item) is int and item>=0 for item in value),'metadata');return value


def _named(parent,name):
    try: info=os.stat(name,dir_fd=parent,follow_symlinks=False)
    except OSError: raise Refused('path') from None
    value=tuple(getattr(info,key,None) for key in FIELDS)
    require(all(type(item) is int and item>=0 for item in value),'metadata');return value


def _security(fd):
    try:return security.snapshot(fd)
    except security.Refusal:raise Refused('security') from None


class PayloadSourceGuard:
    """Exact73 original source FDs; generic guard limits stay frozen."""
    def __init__(self,plan,*,deadline):
        self.plan,self.deadline=checked_plan(plan),deadline
        self.plan_sha256=sha(canonical(self.plan));self.objects=[];self.paths={};self.roles={}
        self.active=self.spent=self.authenticated=self.returned=False;self.copied=0;self._budget()

    def _budget(self):
        _deadline(self.deadline)
        require(sha(canonical(self.plan))==self.plan_sha256,'plan')

    def _policy(self,path,info,payload=None):
        require(stat.S_ISREG(info[2]) if payload is not None else stat.S_ISDIR(info[2]),'shape')
        if path==ROOT or ROOT in path.parents:
            require(info[3]==os.getuid() and not info[9] & ~(stat.UF_TRACKED|stat.UF_HIDDEN),'shape')
            require(stat.S_IMODE(info[2])==((0o755 if path==ROOT else 0o700) if payload is None else 0o600),'shape')
            if payload is not None:require(info[5]==1 and info[6]==payload['byte_count'],'shape')

    def _observe_security(self,row):
        return _security(row['fd']) if row['path']==ROOT or ROOT in row['path'].parents else None

    def _hold(self,path,parent,name,payload=None):
        self._budget();before=_named(parent,name);self._policy(path,before,payload)
        flags=os.O_RDONLY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0)|(os.O_DIRECTORY if payload is None else os.O_NONBLOCK)
        try:fd=os.open(name,flags,dir_fd=parent)
        except OSError:raise Refused('path') from None
        row={'path':path,'parent':parent,'name':name,'fd':fd,'pin':payload,'metadata':before}
        self.objects.append(row);self.paths[path]=row
        require(len(self.objects)<=MAX_SOURCE_FDS,'descriptor_budget')
        require(metadata(fd)==before,'changed');row['security']=self._observe_security(row)
        require(metadata(fd)==before==_named(parent,name),'changed');return row

    def __enter__(self):
        require(not self.spent and not self.active,'state');self.spent=True
        require(type(ROOT) is type(Path()) and ROOT.is_absolute() and ROOT.resolve()==ROOT and Path.cwd()==ROOT,'scope')
        try:
            fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            first={'path':Path('/'),'parent':fd,'name':'.','fd':fd,'pin':None,'metadata':metadata(fd),'security':None}
            self.objects.append(first);self.paths[Path('/')]=first
            for role in ROLES:
                payload=self.plan[role];full=ROOT/payload['relative_path'];path,parent=Path('/'),first
                for part in full.parent.parts[1:]:
                    path=path/part;parent=self.paths[path] if path in self.paths else self._hold(path,parent['fd'],part)
                self.roles[role]=self._hold(full,parent['fd'],full.name,payload)
            self.active=True;self.verify();return self
        except BaseException:self.close();raise

    def verify(self):
        require(self.active,'state')
        for row in self.objects:
            self._budget();require(metadata(row['fd'])==row['metadata']==_named(row['parent'],row['name']),'changed')
            self._policy(row['path'],row['metadata'],row['pin'])
            require(self._observe_security(row)==row['security'],'security')
            require(metadata(row['fd'])==row['metadata']==_named(row['parent'],row['name']),'changed')

    def _chunks(self,role):
        row=self.roles[role];offset=0;length=self.plan[role]['byte_count']
        while offset<length:
            self._budget();require(metadata(row['fd'])==row['metadata']==_named(row['parent'],row['name']),'changed')
            raw=os.pread(row['fd'],min(CHUNK,length-offset),offset)
            require(type(raw) is bytes and 0<len(raw)<=min(CHUNK,length-offset),'byte_pin')
            offset+=len(raw);yield raw

    def authenticate_all(self):
        require(self.active and not self.authenticated and self.copied==0,'read_schedule');self.verify()
        for role in ROLES:
            digest=hashlib.sha256()
            for raw in self._chunks(role):digest.update(raw)
            require(digest.hexdigest()==self.plan[role]['sha256'],'byte_pin');self.verify()
        self.authenticated=True

    def copy_next(self,role,target):
        require(self.active and self.authenticated and self.copied<len(ROLES)
            and role==ROLES[self.copied] and type(target) is _ArchiveWriter,'read_schedule')
        self.verify();digest=hashlib.sha256()
        for raw in self._chunks(role):digest.update(raw);target.append(raw)
        require(digest.hexdigest()==self.plan[role]['sha256'],'byte_pin');self.copied+=1;self.verify()

    def receipt(self):
        self.verify();require(self.authenticated and self.copied==len(ROLES),'read_schedule')
        return {'schema':SCHEMA+'-source-receipt','data_plan_sha256':self.plan_sha256,
            'whole_hashes_checked':len(ROLES),'copied_ranges':self.copied,
            'source_endpoint_sha256':sha(canonical([{'path_sha256':sha(str(row['path']).encode()),
                'metadata':list(row['metadata']),'security_sha256':sha(canonical(row['security']))} for row in self.objects])),
            'requires_normal_return_before_READY':True,**FALSE_FLAGS}

    def close(self):
        failed=False
        for row in reversed(self.objects):
            try:os.close(row['fd'])
            except OSError:failed=True
        self.objects.clear();self.paths.clear();self.roles.clear();self.active=False
        require(not failed,'close')

    def __exit__(self,kind,*_):
        normal=False
        try:
            if kind is None:self.receipt();normal=True
        finally:self.close()
        self.returned=normal


def _archive_fd(fd,expected_metadata,*,empty=False,writable=False):
    require(type(fd) is int and fd>=3 and type(expected_metadata) in (tuple,list)
        and len(expected_metadata)==len(FIELDS) and all(type(value) is int and value>=0 for value in expected_metadata),'archive_fd')
    info=metadata(fd);require(info==tuple(expected_metadata),'changed')
    require(stat.S_ISREG(info[2]) and stat.S_IMODE(info[2])==0o600 and info[3]==os.getuid()
        and info[5] in (0,1) and not info[9] & ~(stat.UF_TRACKED|stat.UF_HIDDEN),'archive_fd')
    if empty:require(info[6]==0,'archive_nonempty')
    require(info[6]<=MAX_ARCHIVE,'archive_bound')
    try:flags=fcntl.fcntl(fd,fcntl.F_GETFL)
    except OSError:raise Refused('archive_fd') from None
    if writable:require(flags & os.O_ACCMODE==os.O_RDWR and not flags & os.O_APPEND,'archive_fd')
    else:require(flags & os.O_ACCMODE in (os.O_RDONLY,os.O_RDWR),'archive_fd')
    return _security(fd)


def check_resources():
    """Current bounded budget observation, not a reservation or system change."""
    soft,_=resource.getrlimit(resource.RLIMIT_NOFILE)
    require(soft==resource.RLIM_INFINITY or soft>=FD_WINDOW,'descriptor_budget')
    occupied=0
    import errno
    for fd in range(FD_WINDOW):
        try:fcntl.fcntl(fd,fcntl.F_GETFD);occupied+=1
        except OSError as error:require(error.errno==errno.EBADF,'descriptor_budget')
    require(occupied<=MAX_BASELINE_FDS and FD_WINDOW-occupied>=MAX_SOURCE_FDS+8,'descriptor_budget')
    info=os.statvfs(ROOT);require(info.f_bavail*info.f_frsize>=MIN_FREE_DISK,'disk_budget')
    return {'baseline_descriptors':occupied,'source_descriptor_cap':MAX_SOURCE_FDS,
        'minimum_free_disk_bytes':MIN_FREE_DISK,'RLIMIT_changed':False}


def header_record():
    plan=data_plan();entries=[];offset=0
    for ordinal,role in enumerate(ROLES):
        item=plan[role];entries.append({'ordinal':ordinal,'role':role,'offset':offset,
            'byte_count':item['byte_count'],'sha256':item['sha256']});offset+=item['byte_count']
    return {'schema':SCHEMA+'-header','data_plan_sha256':PLAN_SHA256,'source_fact_sha256':FACT_SHA256,
        'source_output_sha256':OUTPUT_SHA256,'entries':entries,'range_count':len(ROLES),
        'payload_byte_count':offset,**FALSE_FLAGS}


def _header_bytes():
    raw=canonical(header_record());require(0<len(raw)<=MAX_HEADER,'header')
    return MAGIC+len(raw).to_bytes(8,'big')+raw


class _ArchiveWriter:
    def __init__(self,fd,expected_metadata,deadline):
        require(type(expected_metadata) in (tuple,list),'archive_fd')
        self.fd,self.deadline,self.current=fd,deadline,tuple(expected_metadata)
        self.security=_archive_fd(fd,self.current,empty=True,writable=True)
        self.digest=hashlib.sha256();self.offset=0

    def verify(self):
        _deadline(self.deadline)
        require(metadata(self.fd)==self.current and _security(self.fd)==self.security,'changed')

    def append(self,raw):
        require(type(raw) is bytes and 0<len(raw)<=CHUNK,'archive_write')
        self.verify();require(self.offset+len(raw)<=MAX_ARCHIVE,'archive_bound')
        view=memoryview(raw);offset=0
        while view:
            _deadline(self.deadline)
            count=os.pwrite(self.fd,view,self.offset+offset)
            require(type(count) is int and 0<count<=len(view),'archive_write')
            offset+=count;view=view[count:]
        fresh=metadata(self.fd)
        require(fresh[:6]==self.current[:6] and fresh[9]==self.current[9]
            and fresh[6]==self.offset+len(raw) and _security(self.fd)==self.security,'changed')
        self.current=fresh;self.offset+=len(raw);self.digest.update(raw);self.verify()


def prepare_archive_fd(fd,*,expected_initial_metadata,deadline):
    """Copy to a caller-owned original empty FD; no path or permission supplied."""
    _deadline(deadline);check_resources();writer=_ArchiveWriter(fd,expected_initial_metadata,deadline)
    guard=PayloadSourceGuard(data_plan(),deadline=deadline)
    with guard:
        guard.authenticate_all();header=_header_bytes()
        for offset in range(0,len(header),CHUNK):writer.append(header[offset:offset+CHUNK])
        for role in ROLES:guard.copy_next(role,writer)
        receipt=guard.receipt();writer.verify();os.fsync(fd);writer.verify()
    require(guard.returned is True,'read_schedule');writer.verify()
    expected=len(_header_bytes())+sum(row['byte_count'] for row in data_plan().values())
    require(writer.offset==expected,'archive_extent')
    result={'schema':SCHEMA+'-READY','archive_pin':{'byte_count':writer.offset,'sha256':writer.digest.hexdigest()},
        'header_pin':{'byte_count':len(_header_bytes()),'sha256':sha(_header_bytes())},
        'source_receipt':receipt,'source_guard_normal_return':True,'range_count':len(ROLES),
        'data_plan_sha256':PLAN_SHA256,'archive_metadata_sha256':sha(canonical(list(writer.current))),**FALSE_FLAGS}
    return validate_receipt(result,ready=True)


def _read_exact(fd,offset,length,expected_metadata,expected_security,deadline):
    require(type(offset) is int and offset>=0 and type(length) is int and 0<length<=CHUNK,'archive_bound')
    _deadline(deadline)
    require(metadata(fd)==expected_metadata and _security(fd)==expected_security,'changed')
    raw=os.pread(fd,length,offset);require(len(raw)==length,'byte_pin')
    require(metadata(fd)==expected_metadata,'changed');return raw


def verify_archive_fd(fd,*,expected_metadata,deadline):
    """Header and byte ranges only; no source JSON, readiness or process claims."""
    _deadline(deadline);require(type(expected_metadata) in (tuple,list),'archive_fd')
    expected_metadata=tuple(expected_metadata)
    observed_security=_archive_fd(fd,expected_metadata)
    header=_header_bytes();payload=header_record()['payload_byte_count'];total=len(header)+payload
    require(expected_metadata[6]==total,'archive_extent')
    digest=hashlib.sha256();prefix=bytearray()
    for offset in range(0,len(header),CHUNK):
        raw=_read_exact(fd,offset,min(CHUNK,len(header)-offset),expected_metadata,observed_security,deadline)
        prefix.extend(raw);digest.update(raw)
    require(bytes(prefix)==header,'header')
    # Exact canonical expected-header equality rejects duplicate keys, trailing
    # header bytes, changed roles/ranges, gaps and alternate archive formats.
    for entry in header_record()['entries']:
        local=hashlib.sha256();length=entry['byte_count']
        for offset in range(0,length,CHUNK):
            raw=_read_exact(fd,len(header)+entry['offset']+offset,min(CHUNK,length-offset),
                expected_metadata,observed_security,deadline)
            local.update(raw);digest.update(raw)
        require(local.hexdigest()==entry['sha256'],'byte_pin')
    require(metadata(fd)==expected_metadata and _security(fd)==observed_security,'changed')
    result={'schema':SCHEMA+'-verified','archive_pin':{'byte_count':total,'sha256':digest.hexdigest()},
        'header_pin':{'byte_count':len(header),'sha256':sha(header)},'range_count':len(ROLES),
        'data_plan_sha256':PLAN_SHA256,'archive_metadata_sha256':sha(canonical(list(expected_metadata))),
        'header_and_all_ranges_authenticated':True,**FALSE_FLAGS}
    return validate_receipt(result,ready=False)


def validate_source_receipt(value):
    require(type(value) is dict and set(value)=={'schema','data_plan_sha256','whole_hashes_checked',
        'copied_ranges','source_endpoint_sha256','requires_normal_return_before_READY',*FALSE_FLAGS}
        and value['schema']==SCHEMA+'-source-receipt' and value['data_plan_sha256']==PLAN_SHA256
        and type(value['whole_hashes_checked']) is type(value['copied_ranges']) is int
        and value['whole_hashes_checked']==value['copied_ranges']==len(ROLES)
        and _hash(value['source_endpoint_sha256']) and value['requires_normal_return_before_READY'] is True
        and all(value[key] is False for key in FALSE_FLAGS),'receipt')
    return json.loads(canonical(value))


def validate_receipt(value,*,ready):
    """Closed metadata only; external actual exit and FD binding remain required."""
    require(type(ready) is bool,'receipt')
    fields={'schema','archive_pin','header_pin','range_count','data_plan_sha256','archive_metadata_sha256',*FALSE_FLAGS}
    fields.update(('source_receipt','source_guard_normal_return') if ready else ('header_and_all_ranges_authenticated',))
    require(type(value) is dict and set(value)==fields and value['schema']==SCHEMA+('-READY' if ready else '-verified')
        and type(value['range_count']) is int and value['range_count']==len(ROLES)
        and value['data_plan_sha256']==PLAN_SHA256 and _hash(value['archive_metadata_sha256'])
        and all(value[key] is False for key in FALSE_FLAGS),'receipt')
    header=_header_bytes();total=len(header)+header_record()['payload_byte_count']
    require(value['header_pin']=={'byte_count':len(header),'sha256':sha(header)}
        and type(value['archive_pin']) is dict and set(value['archive_pin'])=={'byte_count','sha256'}
        and type(value['archive_pin']['byte_count']) is int and value['archive_pin']['byte_count']==total
        and _hash(value['archive_pin']['sha256']),'receipt')
    if ready:
        require(value['source_guard_normal_return'] is True,'receipt');validate_source_receipt(value['source_receipt'])
    else:require(value['header_and_all_ranges_authenticated'] is True,'receipt')
    return json.loads(canonical(value))
