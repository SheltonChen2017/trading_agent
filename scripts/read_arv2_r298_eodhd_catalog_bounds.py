"""One fixed three-frame AW DATA bounds diagnostic, never a replay.

All externally pinned body frames authenticate before any JSON. The first
whole-file digest is a new AY observation, never a recovered/refreshed AW pin.
Only public pagination types/counts and aggregate list observations escape.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import sys
import time

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import run_arv2_r298_eodhd_catalog as aw
from scripts import arv2_r298_fixed_data_guard as guard_module

SOURCE=ROOT/'scripts/read_arv2_r298_eodhd_catalog_bounds.py'
CONTROL=ROOT/'artifacts/analyst_revisions_v2/newrule_eodhd_catalog/R326-20261027-AY'
SCHEMA='arv2-r298-fixed-AW-catalog-frame-bounds-ay-v1'
admitted,environment,PYTHON=aw.admitted,aw.environment,aw.PYTHON
canonical,sha,pin,metadata=aw.canonical,aw.sha,aw.pin,aw.metadata
SECONDS,MAX_OUTPUT=120,65536
AW_SOURCE_SHA256='e5a6cf032b52da4fcffbfe17f92fbfbc617e16f4bf3e048a441b4a6844e27323'
DATA_RELATIVE='artifacts/analyst_revisions_v2/newrule_eodhd_catalog/R326-20261027-AW/catalog-bodies.bin'
FRAME_PINS=({'byte_count':7549657,'sha256':'041219222278efc8a53e79a3d1ce2357613e7e88cb39dd542021dc3af420cc63'},
    {'byte_count':8487744,'sha256':'d50b5f1cee071640694bd00aa41de849427d525f39b5978770065aed1b646933'},
    {'byte_count':102655,'sha256':'ec33da7c0fd6b33dc24c303ddae2de794e5e80e4a6dc1bb7e6980ce2c5db747e'})
DATA_BYTES=16140080
FALSE_FLAGS={'identity_accepted':False,'price_input_admitted':False,'QC_transfer_granted':False,
    'provider_contact':False,'credential_access':False,'old_control_read':False,'AW_replayed':False,
    'pagination_contract_changed':False,
    'AW_whole_file_pin_recovered_or_refreshed':False,'licensed_values_disclosed':False,
    'point_in_time_proven':False,'formal_forward_ready':False,'paper_or_live_ready':False}
TYPES=frozenset(('missing','null','boolean','integer','number','string','array','object'))
KNOWN_TOP=frozenset(('meta','data','links'));KNOWN_META=frozenset(('total','limit','offset'))
FINITE=frozenset(('host','arguments','environment','git_state','source_pin','source_binding','deadline','claim_spent',
    'output_changed','output_security','output_write','output_bound','frame','shape','output','os_error','unknown'))|frozenset(
        'guard_'+code for code in guard_module.FINITE)


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args=BaseException.args.__get__(error)
        return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
    if type(error) is guard_module.Refused:return 'guard_'+guard_module.finite(error)
    if type(error) is environment.EnvironmentRefused:return 'environment'
    if type(error) is admitted.helpers.Deadline:return 'deadline'
    if isinstance(error,OSError):return 'os_error'
    return 'unknown'


def remaining(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline) and 0<deadline-time.monotonic()<=SECONDS,'deadline')
    return deadline-time.monotonic()


def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def observed_failure():
    return {'schema':SCHEMA+'-AW-failure-binding','AW_head':'d6dae40dbc4b949bb229583d8ece6d7b1375c598',
        'AW_source_sha256':AW_SOURCE_SHA256,'parent_actual_exit':2,'native_validator_actual_exit':0,
        'parent_stdout_pin':{'byte_count':2854,'sha256':'82a9572938b8f79b364020fe659a457a96c84bbd63b76e024c9220286077ef45'},
        'validator_stdout_pin':{'byte_count':2854,'sha256':'82a9572938b8f79b364020fe659a457a96c84bbd63b76e024c9220286077ef45'},
        'provider_actual_exit':2,'provider_failure_code':'mapping_bound','application_dispatch_intents':3,
        'completed_HTTP200_bodies':3,'mapping_total_and_pages_not_returned':True,
        'external_frame_body_pins':list(FRAME_PINS),'framed_DATA_extent':DATA_BYTES,
        'AW_attempt_spent':True,'failure_evidence_authenticated':True,'AW_capture_accepted':False,
        'new_operation_or_read_granted':False}


def pins():
    values=aw.pins();require('scripts/run_arv2_r298_eodhd_catalog.py' not in values,'source_pin')
    values['scripts/run_arv2_r298_eodhd_catalog.py']=AW_SOURCE_SHA256
    require(values['scripts/arv2_r298_fixed_data_guard.py']=='00de1fbde9ae1925d1231dc863cd4a5bb00974bb596f6368187059452cfae145','source_pin')
    return values


def fixed_frame_plan():
    return {'catalog_frames':{'relative_path':DATA_RELATIVE,'byte_count':DATA_BYTES,'frames':list(FRAME_PINS)}}


def frame_profile():
    return {'schema':SCHEMA+'-fixed-framed-guard','file_plan':fixed_frame_plan(),
        'metadata_fields':list(guard_module.FIELDS),'three_exact_BE64_headers_plus_all_pinned_bodies_cover_every_byte':True,
        'read_original_FD_once_all_external_frame_pins_before_any_JSON':True,
        'new_whole_file_digest_observed_after_all_frames_authenticated':True,
        'initial_plan_digest_checked_each_stage':True,'normal_return_required_before_publication':True,
        'root_mode':'0755','below_root_directories':'0700','leaf_mode':'0600_single_link',
        'native_empty_ACL_ordinary_xattrs_and_full_held_named_metadata':True,
        'endpoint_equality_not_continuous_or_historical_proof':True,'operational_authority_granted':False}


def profile_record():
    return {'schema':SCHEMA,'root':str(ROOT),'branch':admitted.frozen.BRANCH,'source':str(SOURCE),
        'control':str(CONTROL),'python':str(PYTHON),'source_pins':pins(),'seconds':SECONDS,
        'maximum_output_bytes':MAX_OUTPUT,'source_read_schedule':frame_profile(),
        'AW_failure_binding':observed_failure(),'purpose':'diagnose_retained_first_ID_mapping_page_bounds_no_new_contact',
        'known_top_field_names':sorted(KNOWN_TOP),'known_meta_field_names':sorted(KNOWN_META),
        'unknown_field_names_hash_only':True,'maximum_observed_public_integer':100000000,
        'canonical_ASCII_decimal_meta_strings_tagged_interpretation_only_not_pagination_coercion':True,
        'link_next_only_type_hash_never_URL':True,'all_three_external_byte_pins_before_any_JSON':True,
        'normal_source_return_before_emit':True,'strict_duplicate_key_refusal':True,
        'list_Unicode_schema_checks_independent_of_mapping_diagnosis':True,
        'claim_before_any_framed_DATA_read':True,'deadline_uninterruptible_IO_host_suspension_qualification':True,**FALSE_FLAGS}


def binding(args):return {'schema':SCHEMA,'expected_head':args.expected_head,
    'caller_sha256':args.caller_sha256,'profile_sha256':args.profile_sha256}


def preflight(args,deadline):
    require(not admitted.v5._under_test() and sys.platform=='darwin' and os.name=='posix'
        and sys.version_info[:2]==(3,13) and Path(sys.executable)==PYTHON and Path.cwd()==ROOT
        and ROOT.resolve()==ROOT and Path(__file__).absolute()==SOURCE,'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}',args.expected_head)
        and _hash(args.caller_sha256) and _hash(args.profile_sha256),'arguments')
    aw.ar._credential_free();environment._require_environment()
    for command,expected in ((['rev-parse','--show-toplevel'],str(ROOT)),(['branch','--show-current'],admitted.frozen.BRANCH),
        (['rev-parse','HEAD'],args.expected_head),(['status','--porcelain'],'')):
        require(admitted.v5._git(command,deadline).decode('ascii').strip()==expected,'git_state')
    for name,expected in pins().items():require(sha((ROOT/name).read_bytes())==expected,'source_pin')
    require(sha(SOURCE.read_bytes())==args.caller_sha256 and sha(admitted.v5._git(
        ['cat-file','blob',args.expected_head+':'+SOURCE.relative_to(ROOT).as_posix()],deadline,256*1024))==args.caller_sha256
        and sha(canonical(profile_record()))==args.profile_sha256,'source_pin');remaining(deadline)


def native_profile():
    value='(version 1)(allow default)(deny network*)'
    value+=''.join(f'(deny file-read* file-write* (subpath "{path}"))' for path in
        ('/Users/sheltonchen/Library/Keychains','/Library/Keychains'))
    value+='(deny process-exec (literal "/usr/bin/security"))'
    value+=(f'(deny file-write* (require-all (require-not (subpath "{ROOT/".pytest_cache"}"))'
        f'(require-not (literal "/dev/null"))(require-not (subpath "{CONTROL}"))(require-not (literal "{CONTROL.parent}"))))')
    policy=aw.ap.previous._artifact_policy([ROOT/DATA_RELATIVE,CONTROL.parent])
    needle=f'(require-all (subpath "{ROOT/"artifacts"}")';require(policy.count(needle)==1,'source_binding')
    return value+policy.replace(needle,needle+f' (require-not (subpath "{CONTROL}"))',1)


def _security(fd):
    try:return aw.ap.security.snapshot(fd)
    except aw.ap.security.Refusal:raise Refused('output_security') from None


class FramedSourceGuard(guard_module.FixedDataGuard):
    """Fresh fixed-frame byte proof; never an invented historical whole pin."""
    def __init__(self,*,deadline):
        self.plan=json.loads(canonical(fixed_frame_plan()));self.deadline=deadline
        self.initial_plan_sha256=sha(canonical(self.plan))
        self.objects,self.by_path,self.by_role,self.reads=[],{},{},set()
        self.active,self.spent=False,False;self._whole_pin=None
        require(DATA_BYTES==sum(item['byte_count']+8 for item in FRAME_PINS)
            and len(FRAME_PINS)==3 and 0<DATA_BYTES<=32*1024*1024,'frame')
        self._budget()

    def _budget(self):
        try:unchanged=sha(canonical(self.plan))==self.initial_plan_sha256
        except (TypeError,ValueError,UnicodeError,RecursionError):raise Refused('frame') from None
        require(unchanged,'frame');remaining(self.deadline)

    @property
    def whole_pin(self):
        return None if self._whole_pin is None else {'byte_count':self._whole_pin[0],'sha256':self._whole_pin[1]}

    def _policy(self,path,info,*,pin=None):
        guard_module.require(stat.S_ISREG(info[2]) if pin is not None else stat.S_ISDIR(info[2]),'shape')
        if path==ROOT or ROOT in path.parents:
            guard_module.require(info[3]==os.getuid() and not info[9]&~(stat.UF_TRACKED|stat.UF_HIDDEN),'shape')
            if pin is None:guard_module.require(stat.S_IMODE(info[2])==(0o755 if path==ROOT else 0o700),'shape')
            else:guard_module.require(stat.S_IMODE(info[2])==0o600 and info[5]==1 and info[6]==pin['byte_count'],'shape')

    def _security(self,row):
        if row['path']!=ROOT and ROOT not in row['path'].parents:return None
        try:return guard_module.security.snapshot(row['fd'])
        except guard_module.security.Refusal:raise guard_module.Refused('security') from None

    def __enter__(self):
        guard_module.require(not self.active and not self.spent,'state');self.spent=True
        guard_module.require(type(ROOT) is type(Path()) and ROOT.is_absolute() and Path.cwd()==ROOT,'scope')
        try:
            self._budget()
            fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0))
            first={'path':Path('/'),'fd':fd,'parent':fd,'name':'.','pin':None,
                'metadata':guard_module._metadata(fd),'security':None}
            self.objects.append(first);self.by_path[Path('/')]=first
            path,parent=Path('/'),first;plan=self.plan['catalog_frames'];full=ROOT/plan['relative_path']
            for part in full.parent.parts[1:]:
                path=path/part;parent=self._hold(path,parent['fd'],part)
            self.by_role['catalog_frames']=self._hold(full,parent['fd'],full.name,pin=plan)
            self.active=True;self.verify();return self
        except BaseException:self.close();raise

    def read_frames_once(self):
        guard_module.require(self.active and not self.reads,'read_spent');self.reads.add('catalog_frames');self.verify()
        fd=self.by_role['catalog_frames']['fd'];offset=0;headers=[];bodies=[]
        for expected in self.plan['catalog_frames']['frames']:
            self._budget();header=os.pread(fd,8,offset);offset+=8
            require(len(header)==8 and struct.unpack('>Q',header)[0]==expected['byte_count'],'frame')
            chunks=[];read=0;digest=hashlib.sha256()
            while read<expected['byte_count']:
                self._budget();chunk=os.pread(fd,min(65536,expected['byte_count']-read),offset+read)
                require(type(chunk) is bytes and chunk,'frame');digest.update(chunk);chunks.append(chunk);read+=len(chunk)
            require(read==expected['byte_count'] and digest.hexdigest()==expected['sha256'],'frame')
            bodies.append(b''.join(chunks));headers.append(header);offset+=read
        require(offset==DATA_BYTES and os.pread(fd,1,offset)==b'','frame');self.verify()
        # No whole-file digest is observed until all three external body pins pass.
        whole=hashlib.sha256()
        for header,body in zip(headers,bodies,strict=True):whole.update(header);whole.update(body)
        self._whole_pin=(offset,whole.hexdigest());self.verify()
        return tuple(bodies)

    def receipt(self):
        self.verify();guard_module.require(self.reads=={'catalog_frames'} and self.whole_pin is not None,'state')
        row=self.by_role['catalog_frames']
        value={'schema':SCHEMA+'-framed-source-receipt','profile_sha256':sha(canonical(frame_profile())),
            'relative_path':DATA_RELATIVE,'byte_extent':DATA_BYTES,'external_body_pins':list(FRAME_PINS),
            'current_metadata_sha256':sha(canonical(list(row['metadata']))),
            'current_security_sha256':sha(canonical(row['security'])),'AY_observed_whole_file_pin':dict(self.whole_pin),
            'all_extent_bytes_authenticated_by_external_frames':True,'new_AY_whole_pin_not_recovered_AW_pin':True,
            'requires_normal_return_before_use':True,'historical_continuity_proven':False,'continuous_integrity_proven':False}
        return validate_receipt(value)


def validate_receipt(value):
    require(type(value) is dict and set(value)=={'schema','profile_sha256','relative_path','byte_extent',
        'external_body_pins','current_metadata_sha256','current_security_sha256','AY_observed_whole_file_pin',
        'all_extent_bytes_authenticated_by_external_frames','new_AY_whole_pin_not_recovered_AW_pin',
        'requires_normal_return_before_use','historical_continuity_proven','continuous_integrity_proven'}
        and value['schema']==SCHEMA+'-framed-source-receipt' and value['profile_sha256']==sha(canonical(frame_profile()))
        and value['relative_path']==DATA_RELATIVE and type(value['byte_extent']) is int and value['byte_extent']==DATA_BYTES
        and value['external_body_pins']==list(FRAME_PINS) and _hash(value['current_metadata_sha256'])
        and _hash(value['current_security_sha256'])
        and value['all_extent_bytes_authenticated_by_external_frames'] is True
        and value['new_AY_whole_pin_not_recovered_AW_pin'] is True
        and value['requires_normal_return_before_use'] is True and value['historical_continuity_proven'] is False
        and value['continuous_integrity_proven'] is False,'output')
    whole=value['AY_observed_whole_file_pin']
    require(type(whole) is dict and set(whole)=={'byte_count','sha256'} and type(whole['byte_count']) is int
        and whole['byte_count']==DATA_BYTES and _hash(whole['sha256']),'output')
    return json.loads(canonical(value))


class Store:
    def __init__(self):
        self.fd,self.chain,self.files=None,[],{};fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for index,part in enumerate(CONTROL.parts[1:],1):
                here=Path(*CONTROL.parts[:index+1])
                if here in (CONTROL.parent,CONTROL):
                    try:os.mkdir(part,0o700,dir_fd=fd);os.fsync(fd)
                    except FileExistsError:require(here!=CONTROL,'claim_spent')
                nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=nxt;self.chain.append((os.fstat(fd).st_dev,os.fstat(fd).st_ino))
            self.fd,self.security=fd,_security(fd);self.verify()
        except BaseException:os.close(fd);raise
    def __enter__(self):return self
    def __exit__(self,*_):
        failed=False
        for row in self.files.values():
            try:os.close(row['fd'])
            except OSError:failed=True
        try:os.close(self.fd)
        except OSError:failed=True
        require(not failed,'output_changed')
    def verify(self):
        other,chain=admitted._storage_module()._walk(CONTROL)
        try:
            info=os.fstat(other)
            require(chain==tuple(self.chain) and metadata(info)==metadata(os.fstat(self.fd))
                and _security(self.fd)==self.security and stat.S_IMODE(info.st_mode)==0o700
                and info.st_uid==os.getuid() and set(os.listdir(other))==set(self.files),'output_changed')
            for name,row in self.files.items():
                named=os.stat(name,dir_fd=other,follow_symlinks=False)
                require(metadata(named)==row['metadata']==metadata(os.fstat(row['fd'])) and stat.S_ISREG(named.st_mode)
                    and named.st_uid==os.getuid() and named.st_nlink==1 and stat.S_IMODE(named.st_mode)==0o600
                    and _security(row['fd'])==row['security'],'output_changed')
        finally:os.close(other)
    def write(self,name,raw):
        self.verify();require(name in ('claim.json','result-metadata.json') and name not in self.files
            and len(self.files)<2 and type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT,'output_bound')
        fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.fd)
        self.files[name]={'fd':fd,'metadata':metadata(os.fstat(fd)),'security':_security(fd)}
        _write(fd,raw);os.fsync(self.fd);self.files[name]['metadata']=metadata(os.fstat(fd));self.verify()
        require(os.pread(fd,len(raw)+1,0)==raw,'output_write');self.verify();return pin(raw)


def _write(fd,raw):
    view=memoryview(raw)
    while view:
        count=os.write(fd,view);require(count>0,'output_write');view=view[count:]
    os.fsync(fd)


def _type(value):
    if value is None:return 'null'
    if type(value) is bool:return 'boolean'
    if type(value) is int:return 'integer'
    if type(value) is float:return 'number'
    if type(value) is str:return 'string'
    if type(value) is list:return 'array'
    if type(value) is dict:return 'object'
    raise Refused('shape')


def _numeric_field(row,name):
    present=type(row) is dict and name in row;item=row[name] if present else None
    bounded=present and type(item) is int and 0<=item<=100000000
    interpretation=(int(item) if present and type(item) is str
        and re.fullmatch('0|[1-9][0-9]{0,8}',item) and int(item)<=100000000 else None)
    return {'present':present,'wire_type':_type(item) if present else 'missing',
        'bounded_nonnegative_integer':bounded,'public_integer':item if bounded else None,
        'canonical_decimal_string_interpretation':interpretation,
        'value_sha256':sha(canonical(item)) if present else None}


def _names(value,known):
    names=set(value) if type(value) is dict else set()
    return {'known_names':sorted(names&known),'unknown_name_count':len(names-known),
        'unknown_names_sha256':sha(canonical(sorted(names-known)))}


def _list_observation(raw):
    try:
        rows=aw.catalog_schema.checked_symbol_rows(raw)
        stream=hashlib.sha256()
        for row in rows:stream.update(canonical(row)+b'\n')
        return {'schema_valid':True,'row_count':len(rows),'ordered_records_sha256':stream.hexdigest(),'failure_code':None}
    except aw.catalog_schema.Refused as error:
        return {'schema_valid':False,'row_count':None,'ordered_records_sha256':None,'failure_code':aw.catalog_schema.finite(error)}


def shape(raws,whole_pin):
    require(type(raws) is tuple and len(raws)==3 and [pin(raw) for raw in raws]==list(FRAME_PINS),'frame')
    # Every source byte was authenticated by FramedSourceGuard before this call.
    try:value=aw._decode(raws[2],'mapping_shape',aw.MAX_PAGE)
    except BaseException:raise Refused('shape') from None
    meta=value.get('meta') if type(value) is dict else None
    data=value.get('data') if type(value) is dict else None
    links=value.get('links') if type(value) is dict else None
    next_present=type(links) is dict and 'next' in links;next_value=links.get('next') if next_present else None
    result={'schema':SCHEMA+'-shape','external_frame_body_pins':list(FRAME_PINS),'AY_observed_whole_file_pin':whole_pin,
        'mapping_top_level_type':_type(value),'mapping_top_fields':_names(value,KNOWN_TOP),
        'meta_type':_type(meta),'meta_fields':_names(meta,KNOWN_META),
        'numeric_fields':{name:_numeric_field(meta,name) for name in sorted(KNOWN_META)},
        'data_type':_type(data),'data_row_count':len(data) if type(data) is list else None,
        'all_data_records_objects':all(type(item) is dict for item in data) if type(data) is list else False,
        'links_type':_type(links),'next':{'present':next_present,'type':_type(next_value) if next_present else 'missing',
            'value_sha256':sha(canonical(next_value)) if next_present else None},
        'symbol_lists':{'active':_list_observation(raws[0]),'delisted':_list_observation(raws[1])},**FALSE_FLAGS}
    validate_shape(result);return result


def _validate_names(value,known):
    require(type(value) is dict and set(value)=={'known_names','unknown_name_count','unknown_names_sha256'}
        and type(value['known_names']) is list and value['known_names']==sorted(set(value['known_names']))
        and set(value['known_names'])<=known and type(value['unknown_name_count']) is int
        and 0<=value['unknown_name_count']<=4096 and _hash(value['unknown_names_sha256']),'output')


def validate_shape(value):
    require(type(value) is dict and set(value)=={'schema','external_frame_body_pins','AY_observed_whole_file_pin',
        'mapping_top_level_type','mapping_top_fields','meta_type','meta_fields','numeric_fields','data_type',
        'data_row_count','all_data_records_objects','links_type','next','symbol_lists',*FALSE_FLAGS}
        and value['schema']==SCHEMA+'-shape' and value['external_frame_body_pins']==list(FRAME_PINS)
        and all(value[key] is False for key in FALSE_FLAGS),'output')
    require(type(value['AY_observed_whole_file_pin']) is dict
        and set(value['AY_observed_whole_file_pin'])=={'byte_count','sha256'}
        and type(value['AY_observed_whole_file_pin']['byte_count']) is int
        and value['AY_observed_whole_file_pin']['byte_count']==DATA_BYTES
        and _hash(value['AY_observed_whole_file_pin']['sha256']),'output')
    for name in ('mapping_top_level_type','meta_type','data_type','links_type'):require(value[name] in TYPES-{'missing'},'output')
    _validate_names(value['mapping_top_fields'],KNOWN_TOP);_validate_names(value['meta_fields'],KNOWN_META)
    require(type(value['numeric_fields']) is dict and set(value['numeric_fields'])==KNOWN_META,'output')
    for field in value['numeric_fields'].values():
        require(type(field) is dict and set(field)=={'present','wire_type','bounded_nonnegative_integer','public_integer',
            'canonical_decimal_string_interpretation','value_sha256'}
            and type(field['present']) is type(field['bounded_nonnegative_integer']) is bool and field['wire_type'] in TYPES
            and (field['value_sha256'] is None if not field['present'] else _hash(field['value_sha256'])),'output')
        if field['bounded_nonnegative_integer']:
            require(field['present'] and field['wire_type']=='integer' and type(field['public_integer']) is int
                and 0<=field['public_integer']<=100000000,'output')
        else:require(field['public_integer'] is None,'output')
        interpreted=field['canonical_decimal_string_interpretation']
        require(interpreted is None or field['present'] and field['wire_type']=='string' and type(interpreted) is int
            and 0<=interpreted<=100000000,'output')
        require((field['wire_type']=='missing') is (not field['present']),'output')
    require(type(value['all_data_records_objects']) is bool and (type(value['data_row_count']) is int
        and 0<=value['data_row_count']<=100000 if value['data_type']=='array' else
        value['data_row_count'] is None and value['all_data_records_objects'] is False),'output')
    nxt=value['next'];require(type(nxt) is dict and set(nxt)=={'present','type','value_sha256'}
        and type(nxt['present']) is bool and nxt['type'] in TYPES
        and (nxt['value_sha256'] is None if not nxt['present'] else _hash(nxt['value_sha256']))
        and (nxt['type']=='missing') is (not nxt['present']),'output')
    require(type(value['symbol_lists']) is dict and set(value['symbol_lists'])=={'active','delisted'},'output')
    for row in value['symbol_lists'].values():
        require(type(row) is dict and set(row)=={'schema_valid','row_count','ordered_records_sha256','failure_code'}
            and type(row['schema_valid']) is bool,'output')
        if row['schema_valid']:
            require(type(row['row_count']) is int and 0<=row['row_count']<=100000
                and _hash(row['ordered_records_sha256']) and row['failure_code'] is None,'output')
        else:require(row['row_count'] is row['ordered_records_sha256'] is None
            and row['failure_code'] in aw.catalog_schema.FINITE,'output')
    return value


def run(args,deadline):
    with Store() as store:
        store.write('claim.json',canonical(binding(args)));preflight(args,deadline);environment.require_safe_environment()
        with FramedSourceGuard(deadline=deadline) as guard:
            raws=guard.read_frames_once();result=shape(raws,dict(guard.whole_pin))
            guard.verify();receipt=validate_receipt(guard.receipt());environment.require_safe_environment()
        remaining(deadline);preflight(args,deadline);environment.require_safe_environment();store.verify()
        result={'schema':SCHEMA+'-result','shape':result,'source_guard_receipt':receipt,'source_guard_normal_return':True,
            'AW_failure_binding_sha256':sha(canonical(observed_failure())),**FALSE_FLAGS}
        raw=canonical({'binding':binding(args),'result':result})+b'\n'
        require(len(raw)<=MAX_OUTPUT,'output_bound');store.write('result-metadata.json',raw);store.verify()
    remaining(deadline);return raw


def validate_output(raw,actual_exit,args):
    require(type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT and raw.endswith(b'\n')
        and raw.count(b'\n')==1 and type(actual_exit) is int and actual_exit in (0,2),'output')
    value=aw.parse(raw[:-1]);require(value.get('binding')==binding(args),'output')
    if set(value)=={'binding','failure_code','allocation_unknown',*FALSE_FLAGS}:
        require(actual_exit==2 and value['failure_code'] in FINITE and value['allocation_unknown'] is True
            and all(value[key] is False for key in FALSE_FLAGS),'output');return value
    require(actual_exit==0 and set(value)=={'binding','result'},'output');result=value['result']
    require(type(result) is dict and set(result)=={'schema','shape','source_guard_receipt','source_guard_normal_return',
        'AW_failure_binding_sha256',*FALSE_FLAGS} and result['schema']==SCHEMA+'-result'
        and result['source_guard_normal_return'] is True and result['AW_failure_binding_sha256']==sha(canonical(observed_failure()))
        and all(result[key] is False for key in FALSE_FLAGS),'output')
    validate_shape(result['shape']);validate_receipt(result['source_guard_receipt'])
    require(result['shape']['AY_observed_whole_file_pin']==result['source_guard_receipt']['AY_observed_whole_file_pin'],'output')
    return value


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('expected-head','caller-sha256','profile-sha256'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv);deadline=time.monotonic()+SECONDS
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args,deadline);environment._bootstrap_cli_logging();raw=run(args,deadline);validate_output(raw,0,args)
            sys.stdout.buffer.write(raw);return 0
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'binding':binding(args),'failure_code':finite(error),'allocation_unknown':True,**FALSE_FLAGS})+b'\n');return 2


if __name__=='__main__':raise SystemExit(main())
