"""Fresh bounded genuine October input for a separately frozen R338 consumer.

Import/constructor are inert. The caller must exclusively claim BEFORE entry,
apply native denial and wait for this context's normal return before using or
publishing derived output. Only the exact original package/lineage are read;
no old operational producer, claim, report or source assessment is invoked.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from subprocess import TimeoutExpired
import time

from scripts import arv2_relocation_security as security
from research.analyst_revisions_v2_qc import accepted_risk_october_order_package as october
from research.analyst_revisions_v2_qc import accepted_risk_preliminary_package as compact
from research.analyst_revisions_v2_qc import accepted_risk_preliminary_rating_evaluator as evaluator
from research.analyst_revisions_v2_qc import accepted_risk_preliminary_qc_figi as figi
from research.analyst_revisions_v2_qc import newrule_plain_transport as transport

ROOT=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
INPUT_ROOT=ROOT/'artifacts/analyst_revisions_v2/massive_ratings_delta/R297-20261013-D5/package'
PACKAGE_SHA256='411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad'
LINEAGE_SHA256='e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9'
PACKAGE=INPUT_ROOT/('arv2-preliminary-qc-package-'+PACKAGE_SHA256[:24])
LINEAGE=INPUT_ROOT/('arv2-october-lineage-'+LINEAGE_SHA256)/'lineage.json'
SOURCE_ACTIVATION={'byte_count':4631,'sha256':'70f64450a44bedfa8ea371ac74a00e2134045fb79b433b93f0114be652bc6147'}
SOURCE_TOTAL_BYTES=2776584
PLAIN_PACKAGE_SHA256='1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2'
PLAIN_ACTIVATION={'byte_count':5901,'sha256':'ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b'}
PARENT_PROOF_SHA256='95405d1b569d4bfeeb6c6d87fdb430f2fd27b8b7a31d6dcde7f82276d9903cd1'
UPLOAD_INVENTORY_SHA256='e5b57a9a2264acc19fda9be25ff50f4d757c0dbca4e3d2bc6331f53265ad4bf0'
MANIFEST_SHA256='214dfc9b9bde4f8c44ebff5ce5b33c0cf63bb267aa94fe2303aaffd5832f2325'
AXIS_COUNT, BINDING_COUNT=3466,6151
AXIS_SHA256='4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585'
SESSION_STREAM_SHA256='3e976a6e9df64472fcbc0d0dd775eab52d68fe0b1d2d665709ac03b18dc55a98'
MEMBERSHIP_STREAM_SHA256='6da39a900784aea5f0be81a9a329b28a1399d8dc5d95ec60b3951f55e31f40cd'
BINDING_STREAM_SHA256='73ba4ac73c0485b2d274c31b5ec740a97a64de27a4f6dfbfb9cb63bc8e7cd15f'
ADMISSION_SHA256='5d0075cfe24cdfaaa56992de1d3b30bb4895d2495a8356ade47a4c3bc9dea281'
MAPPING_SHA256='2dedd92e902aa5c0ba88a7ddd40abf75b933fb99fe20b06fd07d7c75156a5359'
SCHEMA='arv2-r338-genuine-quarantine-input-v1'
INPUT_SCHEMA='arv2-r298-all-route-worker-v1-input'
MAX_FILES,MAX_LEAF_BYTES,MAX_SOURCE_BYTES,MAX_PLAIN_BYTES,MAX_LINEAGE_BYTES=96,32*1024*1024,44*1024*1024,44*1024*1024,64*1024
MAX_SECONDS,MAX_ROW_BYTES=900,8*1024*1024
ROLES=('evaluator_manifest','session_axis','memberships','contributions','runtime_symbol_bindings')
PARSED_ROLES=('evaluator_manifest','session_axis','memberships','runtime_symbol_bindings')
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
FALSE_FLAGS={'provider_contact':False,'QC_contact':False,'Safari_access':False,'USB_read':False,
    'credential_access':False,'old_control_read':False,'old_operator_invoked':False,
    'price_coverage_proven':False,'actual_target_or_holdings_path_proven':False,
    'source_admission_granted':False,'formal_identity_admitted':False,'point_in_time_proven':False,
    'historical_continuity_proven':False,'continuous_integrity_proven':False,'paper_or_live_ready':False}
FINITE=frozenset(('scope','state','deadline','metadata','path_open','shape','security','security_changed',
    'named_changed','inventory','byte_pin','json','descriptor','genuine','plain','stream','manifest',
    'axis','bindings','memberships','contributions','changed','close','output','unknown'))


class Refused(ValueError):
    """Finite input/technical stop, never source text, identifiers or raw errors."""


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    if type(error) in (TimeoutError,TimeoutExpired):return 'deadline'
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
    except (TypeError,ValueError,UnicodeError,RecursionError):raise Refused('json') from None


def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(raw):return {'byte_count':len(raw),'sha256':sha(raw)}
def clone(value):return json.loads(canonical(value))


def _budget(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline)
        and 0<deadline-time.monotonic()<=MAX_SECONDS,'deadline')


def _problem(error,default):
    if type(error) is Refused:raise error
    if type(error) in (TimeoutError,TimeoutExpired):raise Refused('deadline') from None
    raise Refused(default) from None


def _loads(raw,maximum,*,lf=False):
    require(type(raw) is bytes and 0<len(raw)<=maximum,'json')
    def pairs(items):
        result={}
        for k,v in items:
            require(k not in result,'json');result[k]=v
        return result
    try:
        value=json.loads(raw.decode('ascii'),object_pairs_hook=pairs,
            parse_constant=lambda _:(_ for _ in ()).throw(Refused('json')))
        require(canonical(value)+(b'\n' if lf else b'')==raw,'json');return value
    except Exception as error:_problem(error,'json')


def input_paths():
    """Static native scope, not an inventory discovered outside a fresh claim.

    The exact pinned source activation authenticates the flat dynamic payload
    inventory. Native policy may allow this package subtree and exact lineage
    leaf, with metadata-only ancestry, but no sibling directory/control scope.
    """
    return {'package_directory':str(PACKAGE),'source_activation':str(PACKAGE/'transport-manifest.json'),
        'source_activation_pin':dict(SOURCE_ACTIVATION),'lineage_file':str(LINEAGE),
        'lineage_sha256':LINEAGE_SHA256,'source_package_sha256':PACKAGE_SHA256,
        'package_payload_inventory':'claim_bound_authenticated_activation_flat_names_only',
        'maximum_package_leaf_count':MAX_FILES,'maximum_source_payload_bytes':MAX_SOURCE_BYTES,
        'maximum_lineage_bytes':MAX_LINEAGE_BYTES}


def profile_record():
    return {'schema':SCHEMA,'root':str(ROOT),'input_paths':input_paths(),
        'plain_package_sha256':PLAIN_PACKAGE_SHA256,'plain_activation_pin':dict(PLAIN_ACTIVATION),
        'parent_proof_sha256':PARENT_PROOF_SHA256,'upload_inventory_sha256':UPLOAD_INVENTORY_SHA256,
        'evaluator_manifest_sha256':MANIFEST_SHA256,'binding_count':BINDING_COUNT,
        'binding_stream_sha256':BINDING_STREAM_SHA256,'full_axis_count':AXIS_COUNT,
        'ordered_full_axis_sha256':AXIS_SHA256,'session_stream_sha256':SESSION_STREAM_SHA256,
        'membership_stream_sha256':MEMBERSHIP_STREAM_SHA256,'roles':list(ROLES),'parsed_roles':list(PARSED_ROLES),
        'contributions':'all_payload_bytes_authenticated_and_genuine_compact_evaluator_validated_no_duplicate_local_JSON_expansion',
        'maximum_seconds':MAX_SECONDS,'metadata_fields':list(FIELDS),
        'guard':'all_original_nofollow_ancestor_leaf_descriptors_native_security_full_metadata_and_whole_leaf_bytes_held',
        'inventory':'exact_package_manifest_authenticated_before_any_dynamic_leaf_name_parse_no_census_of_sibling_controls',
        'authority':'direct_genuine_October_compact_plain_process_authority_not_an_old_operator_or_report',
        'normal_return_required_before_use':True,'output':'finite_count_hash_receipt_only_private_properties_never_print',
        **FALSE_FLAGS}


def _meta(info):
    result=tuple(getattr(info,key,None) for key in FIELDS)
    require(all(type(v) is int and v>=0 for v in result),'metadata');return result


class _InputGuard:
    """One current-use dynamically pinned exact-package guard; no publication."""
    def __init__(self,deadline):
        self.deadline=deadline;self.objects=[];self.by_path={};self.leaves={};self.active=False
        self.expected_names=None;self.source_activation=self.lineage_raw=None

    def _security(self,path,fd):
        if path!=ROOT and ROOT not in path.parents:return None
        try:return security.snapshot(fd)
        except Exception as error:_problem(error,'security')

    def _policy(self,path,info,expected=None):
        isleaf=expected is not None
        require(stat.S_ISREG(info[2]) if isleaf else stat.S_ISDIR(info[2]),'shape')
        if path==ROOT or ROOT in path.parents:
            require(info[3]==os.getuid() and not info[9]&~(stat.UF_TRACKED|stat.UF_HIDDEN),'shape')
            require(stat.S_IMODE(info[2])==(0o600 if isleaf else 0o755 if path==ROOT else 0o700),'shape')
            if isleaf:require(info[5]==1 and 0<info[6]<=expected['maximum']
                and (expected.get('byte_count') is None or info[6]==expected['byte_count']),'shape')

    def _hold(self,path,parent,name,expected=None):
        _budget(self.deadline)
        try:
            named=_meta(os.stat(name,dir_fd=parent,follow_symlinks=False));self._policy(path,named,expected)
            flags=os.O_RDONLY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0)
            flags|=os.O_NONBLOCK if expected is not None else os.O_DIRECTORY
            fd=os.open(name,flags,dir_fd=parent)
        except Exception as error:_problem(error,'path_open')
        row={'path':path,'fd':fd,'parent':parent,'name':name,'metadata':named,'expected':expected}
        self.objects.append(row);self.by_path[path]=row
        require(_meta(os.fstat(fd))==named,'named_changed')
        row['security']=self._security(path,fd)
        require(_meta(os.fstat(fd))==named==_meta(os.stat(name,dir_fd=parent,follow_symlinks=False)),'named_changed')
        if expected is not None:self.leaves[path]=row
        return row

    def _directory(self,path):
        current=Path('/');row=self.by_path[current]
        for part in path.parts[1:]:
            current/=part
            row=self.by_path[current] if current in self.by_path else self._hold(current,row['fd'],part)
        return row

    def _leaf(self,path,expected):
        parent=self._directory(path.parent)
        return self._hold(path,parent['fd'],path.name,expected)

    def _read(self,row):
        _budget(self.deadline);expected=row['expected'];size=row['metadata'][6];offset=0;chunks=[]
        while offset<size:
            _budget(self.deadline)
            chunk=os.pread(row['fd'],min(65536,size-offset),offset)
            require(chunk,'byte_pin');chunks.append(chunk);offset+=len(chunk)
        raw=b''.join(chunks)
        require(len(raw)==size and sha(raw)==expected['sha256'],'byte_pin');return raw

    def __enter__(self):
        require(Path.cwd()==ROOT and ROOT.is_absolute() and PACKAGE.parent==INPUT_ROOT
            and ROOT in PACKAGE.parents and ROOT in LINEAGE.parents,'scope')
        try:
            fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0))
            self.objects.append({'path':Path('/'),'fd':fd,'parent':fd,'name':'.',
                'metadata':_meta(os.fstat(fd)),'expected':None,'security':None});self.by_path[Path('/')]=self.objects[0]
            manifest=self._leaf(PACKAGE/'transport-manifest.json',{**SOURCE_ACTIVATION,'maximum':MAX_LEAF_BYTES})
            lineage=self._leaf(LINEAGE,{'sha256':LINEAGE_SHA256,'maximum':MAX_LINEAGE_BYTES})
            self.source_activation=self._read(manifest);self.lineage_raw=self._read(lineage)
            # No dynamic filename is parsed before both out-of-band byte pins.
            record=_loads(self.source_activation,MAX_LEAF_BYTES,lf=True)
            require(type(record) is dict and record.get('schema')==compact.TRANSPORT_MANIFEST_SCHEMA
                and record.get('package_sha256')==PACKAGE_SHA256 and record.get('source_disposition_sha256')==LINEAGE_SHA256
                and type(record.get('objects')) is list and 5<=len(record['objects'])<MAX_FILES,'descriptor')
            descriptors=[]
            for raw in record['objects']:
                _budget(self.deadline)
                try:item=compact._upload_object_from_record(raw)
                except Exception as error:_problem(error,'descriptor')
                name=item.relative_path
                require(type(name) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,255}',name)
                    and name not in ('.','..','transport-manifest.json') and '..' not in name
                    and item.activation_manifest is False and item.role in ROLES
                    and type(item.byte_count) is int and 0<item.byte_count<=MAX_LEAF_BYTES,'descriptor')
                descriptors.append(item)
            names=[item.relative_path for item in descriptors]
            require(len(set(names))==len(names) and len({item.object_store_key for item in descriptors})==len(names)
                and sum(item.byte_count for item in descriptors)+SOURCE_ACTIVATION['byte_count']==SOURCE_TOTAL_BYTES
                and SOURCE_TOTAL_BYTES<=MAX_SOURCE_BYTES,'inventory')
            self.expected_names=frozenset((*names,'transport-manifest.json'))
            package=self.by_path[PACKAGE];lineagedir=self.by_path[LINEAGE.parent]
            require(set(os.listdir(package['fd']))==set(self.expected_names)
                and set(os.listdir(lineagedir['fd']))=={'lineage.json'},'inventory')
            for item in descriptors:
                row=self._leaf(PACKAGE/item.relative_path,{'byte_count':item.byte_count,
                    'sha256':item.content_sha256,'maximum':MAX_LEAF_BYTES})
                self._read(row)
            self.active=True;self.verify(rehash=False);return self
        except BaseException:
            self.close();raise

    def verify(self,*,rehash=True):
        require(self.active,'state')
        for row in self.objects:
            _budget(self.deadline)
            require(_meta(os.fstat(row['fd']))==row['metadata']
                ==_meta(os.stat(row['name'],dir_fd=row['parent'],follow_symlinks=False)),'named_changed')
            self._policy(row['path'],row['metadata'],row['expected'])
            require(self._security(row['path'],row['fd'])==row['security'],'security_changed')
            if rehash and row['expected'] is not None:self._read(row)
            require(_meta(os.fstat(row['fd']))==row['metadata'],'metadata')
        require(set(os.listdir(self.by_path[PACKAGE]['fd']))==set(self.expected_names)
            and set(os.listdir(self.by_path[LINEAGE.parent]['fd']))=={'lineage.json'},'inventory')

    def receipt(self):
        self.verify(rehash=False)
        return {'schema':SCHEMA+'-source','source_leaf_count':len(self.leaves),
            'source_payload_byte_count':sum(row['metadata'][6] for row in self.leaves.values()),
            'current_endpoint_sha256':sha(canonical([{ 'metadata':list(row['metadata']),
                'security':row['security'],'pin':{k:row['expected'].get(k) for k in ('byte_count','sha256')}}
                for row in self.leaves.values()])),
            'full_current_native_security_checked':True,'full_current_metadata_checked':True,
            'fixed_leaf_bytes_authenticated':True,'normal_return_required_before_use':True,
            'historical_continuity_proven':False,'continuous_integrity_proven':False}

    def close(self):
        failed=False
        for row in reversed(self.objects):
            try:os.close(row['fd'])
            except OSError:failed=True
        self.objects.clear();self.by_path.clear();self.leaves.clear();self.active=False
        require(not failed,'close')

    def __exit__(self,kind,*_):
        try:
            if kind is None:self.verify()
        finally:self.close()


def _stream(rows):return sha(b''.join(canonical(row)+b'\n' for row in rows))


class GenuineInput:
    """Sealed genuine package plus current source guard for one fresh consumer."""
    def __init__(self,*,deadline):
        _budget(deadline);self.deadline=deadline;self._guard=None;self._active=False;self._spent=False
        self._wrapped=self._package=self._plain=None;self._selected=None

    def _select(self):
        rows={role:[] for role in PARSED_ROLES};ordinals={role:[] for role in ROLES};inventory=[];activation=False
        counts={role:0 for role in ROLES}
        for item,raw in transport.iter_plain_upload_objects(self._plain):
            _budget(self.deadline)
            require(type(raw) is bytes and pin(raw)=={'byte_count':item.byte_count,'sha256':item.content_sha256},'stream')
            inventory.append(item.to_record())
            if item.activation_manifest:
                require(not activation and item.role=='activation_manifest' and raw==self._plain.record_bytes,'stream')
                activation=True;continue
            require(not activation and item.role in ROLES and type(item.ordinal) is int
                and item.ordinal==len(ordinals[item.role]) and type(item.record_count) is int and item.record_count>0,'stream')
            ordinals[item.role].append(item.ordinal);counts[item.role]+=item.record_count
            if item.role not in rows:continue
            if item.role=='evaluator_manifest':
                require(item.ordinal==0 and item.record_count==1,'manifest');values=[_loads(raw,MAX_LEAF_BYTES,lf=True)]
            else:
                require(len(raw)<=MAX_PLAIN_BYTES,'stream')
                lines=raw.splitlines(keepends=True);require(len(lines)==item.record_count,'stream')
                values=[]
                for line in lines:
                    _budget(self.deadline);values.append(_loads(line,MAX_ROW_BYTES,lf=True))
            rows[item.role].extend(values)
        require(activation and all(ordinals.values()) and len(inventory)<=MAX_FILES
            and sha(canonical(inventory))==UPLOAD_INVENTORY_SHA256,'stream')
        return {role:tuple(values) for role,values in rows.items()},counts

    def _analyze(self):
        selected,counts=self._select();manifest=selected['evaluator_manifest'][0]
        require(type(manifest) is dict and set(manifest)==set(evaluator._MANIFEST_FIELDS),'manifest')
        seed=dict(manifest);manifest_sha=seed.pop('manifest_sha256',None);manifest_id=seed.pop('manifest_id',None)
        require(manifest_sha==MANIFEST_SHA256==sha(canonical(seed))
            and manifest_id=='arv2-preliminary-rating-manifest-'+MANIFEST_SHA256[:24],'manifest')
        axis=evaluator._parse_sessions(selected['session_axis'])
        require(len(axis)==AXIS_COUNT and sha(canonical(list(axis)))==AXIS_SHA256
            and axis[0]=='2013-01-02' and axis[-1]=='2026-10-13'
            and _stream(selected['session_axis'])==SESSION_STREAM_SHA256==manifest['session_axis_sha256'],'axis')
        raw=selected['runtime_symbol_bindings'];require(len(raw)==BINDING_COUNT,'bindings')
        checked=tuple(figi._input_row(row,ADMISSION_SHA256) for row in raw)
        require(canonical(checked)==canonical(raw) and tuple(row['security_id'] for row in checked)
            ==tuple(sorted({row['security_id'] for row in checked})) and len({row['composite_figi'] for row in checked})==BINDING_COUNT
            and all(row['admitted_mapping_count']==BINDING_COUNT and row['admitted_mapping_inventory_sha256']==MAPPING_SHA256 for row in checked)
            and _stream(checked)==BINDING_STREAM_SHA256,'bindings')
        memberships=selected['memberships']
        require(type(manifest['membership_row_count']) is int and len(memberships)==manifest['membership_row_count']
            and _stream(memberships)==MEMBERSHIP_STREAM_SHA256==manifest['membership_rows_sha256'],'memberships')
        parsed=evaluator._parse_memberships(memberships,len(axis));ids={row['security_id'] for row in checked}
        require(all(row.security_id in ids for row in parsed),'memberships')
        require(type(manifest['contribution_row_count']) is int
            and counts['contributions']==manifest['contribution_row_count'],'contributions')
        # Genuine source loader has already run full evaluator validation. Do not
        # turn retained contributions into a selector, outcome or new scoring run.
        result={'schema':INPUT_SCHEMA,'source_package_sha256':PACKAGE_SHA256,'source_lineage_sha256':LINEAGE_SHA256,
            'plain_package_sha256':self._plain.package_sha256,'activation_manifest_sha256':self._plain.activation_manifest_sha256,
            'parent_proof_sha256':self._plain.parent_proof_sha256,'upload_inventory_sha256':UPLOAD_INVENTORY_SHA256,
            'evaluator_manifest_sha256':MANIFEST_SHA256,'session_axis_count':len(axis),
            'session_axis_sha256':SESSION_STREAM_SHA256,'ordered_session_values_sha256':AXIS_SHA256,
            'first_session':axis[0],'last_session':axis[-1],
            'binding_contract':{'binding_count':BINDING_COUNT,'binding_stream_sha256':BINDING_STREAM_SHA256,
                'security_master_admission_sha256':ADMISSION_SHA256,'admitted_mapping_inventory_sha256':MAPPING_SHA256}}
        return selected,axis,checked,result,counts

    def _libraries(self):
        try:
            october.require_october_order_input_package(self._wrapped)
            compact.require_accepted_risk_preliminary_package(self._package)
            require(self._wrapped.package is self._package and self._wrapped.lineage_sha256==LINEAGE_SHA256
                and self._wrapped.lineage_bytes==self._guard.lineage_raw,'genuine')
            require(compact._package_fingerprint(self._package)==self._package_fingerprint,'changed')
            transport.require_plain_transport(self._plain)
            require(transport._fingerprint(self._plain)==self._plain_fingerprint
                and self._plain.to_record()==self._plain_record,'changed')
        except Exception as error:_problem(error,'genuine')

    def __enter__(self):
        require(not self._active and not self._spent,'state');self._spent=True
        try:
            self._guard=_InputGuard(self.deadline).__enter__()
            _budget(self.deadline)
            self._wrapped=october.load_october_order_input_package(PACKAGE,expected_package_sha256=PACKAGE_SHA256,
                lineage_path=LINEAGE,expected_lineage_sha256=LINEAGE_SHA256)
            october.require_october_order_input_package(self._wrapped)
            self._package=compact.require_accepted_risk_preliminary_package(self._wrapped.package)
            require(self._package.package_sha256==PACKAGE_SHA256
                and self._package.source_disposition_sha256==LINEAGE_SHA256
                and self._package.total_upload_byte_count==SOURCE_TOTAL_BYTES,'genuine')
            self._package_fingerprint=compact._package_fingerprint(self._package)
            self._plain=transport.build_plain_transport(self._package,expected_package_sha256=PACKAGE_SHA256,
                expected_lineage_sha256=LINEAGE_SHA256)
            transport.require_plain_transport(self._plain)
            require(self._plain.package_sha256==PLAIN_PACKAGE_SHA256
                and self._plain.parent_proof_sha256==PARENT_PROOF_SHA256
                and {'byte_count':self._plain.activation_manifest_byte_count,'sha256':self._plain.activation_manifest_sha256}==PLAIN_ACTIVATION,'plain')
            self._plain_fingerprint=transport._fingerprint(self._plain);self._plain_record=self._plain.to_record()
            self._selected,self._axis,self._bindings,self._input_binding,self._role_counts=self._analyze()
            self._semantic_pin=sha(canonical(self._selected));self._input_pin=sha(canonical(self._input_binding))
            self._active=True;self.verify(deadline=self.deadline);return self
        except Exception as error:
            if self._guard is not None:self._guard.close()
            _problem(error,'genuine')
        except BaseException:
            if self._guard is not None:self._guard.close()
            raise

    def _ready(self):require(self._active,'state')
    @property
    def axis(self):self._ready();return tuple(self._axis)
    @property
    def bindings(self):self._ready();return tuple(clone(row) for row in self._bindings)
    @property
    def memberships(self):self._ready();return tuple(clone(row) for row in self._selected['memberships'])
    @property
    def manifest(self):self._ready();return clone(self._selected['evaluator_manifest'][0])
    @property
    def input_binding(self):self._ready();return clone(self._input_binding)
    @property
    def plain(self):self._ready();return self._plain
    @property
    def selected(self):self._ready();return {role:tuple(clone(row) for row in rows) for role,rows in self._selected.items()}

    def verify(self,*,deadline):
        self._ready();require(type(deadline) in (int,float) and deadline==self.deadline,'deadline');_budget(deadline)
        self._guard.verify();self._libraries()
        selected,axis,bindings,input_binding,counts=self._analyze()
        require(counts==self._role_counts and sha(canonical(selected))==self._semantic_pin and axis==self._axis
            and canonical(bindings)==canonical(self._bindings) and sha(canonical(input_binding))==self._input_pin
            and canonical(input_binding)==canonical(self._input_binding),'changed')
        self._guard.verify(rehash=False)
        return True

    def receipt(self):
        self._ready();self._libraries();source=self._guard.receipt()
        result={'schema':SCHEMA+'-receipt','input_binding':clone(self._input_binding),
            'input_binding_sha256':self._input_pin,'parsed_role_streams_sha256':self._semantic_pin,
            'role_row_counts':dict(self._role_counts),'parsed_roles':list(PARSED_ROLES),
            'source_package_object_count':len(self._package.upload_objects),
            'plain_upload_object_count':len(self._plain.upload_objects),
            'plain_payload_byte_count':self._plain.total_upload_byte_count,
            'lineage_byte_count':len(self._guard.lineage_raw),
            'genuine_October_package_and_plain_process_authority_authenticated':True,
            'full_original_binding_stream_authenticated':True,'full_original_axis_authenticated':True,
            'full_membership_stream_authenticated':True,'all_source_payloads_reauthenticated':True,
            'contributions_validated_by_genuine_compact_evaluator':True,'contributions_reparsed_by_this_helper':False,
            'source_guard':source,'normal_return_required_before_use':True,**FALSE_FLAGS}
        return validate_receipt(result)

    def __exit__(self,kind,*_):
        try:
            if kind is None:self.verify(deadline=self.deadline)
        finally:
            self._active=False
            if self._guard is not None:self._guard.close()


def expected_input_binding():
    return {'schema':INPUT_SCHEMA,'source_package_sha256':PACKAGE_SHA256,'source_lineage_sha256':LINEAGE_SHA256,
        'plain_package_sha256':PLAIN_PACKAGE_SHA256,'activation_manifest_sha256':PLAIN_ACTIVATION['sha256'],
        'parent_proof_sha256':PARENT_PROOF_SHA256,'upload_inventory_sha256':UPLOAD_INVENTORY_SHA256,
        'evaluator_manifest_sha256':MANIFEST_SHA256,'session_axis_count':AXIS_COUNT,
        'session_axis_sha256':SESSION_STREAM_SHA256,'ordered_session_values_sha256':AXIS_SHA256,
        'first_session':'2013-01-02','last_session':'2026-10-13',
        'binding_contract':{'binding_count':BINDING_COUNT,'binding_stream_sha256':BINDING_STREAM_SHA256,
            'security_master_admission_sha256':ADMISSION_SHA256,'admitted_mapping_inventory_sha256':MAPPING_SHA256}}


def validate_receipt(value):
    truths=('genuine_October_package_and_plain_process_authority_authenticated',
        'full_original_binding_stream_authenticated','full_original_axis_authenticated',
        'full_membership_stream_authenticated','all_source_payloads_reauthenticated',
        'contributions_validated_by_genuine_compact_evaluator','normal_return_required_before_use')
    keys={'schema','input_binding','input_binding_sha256','parsed_role_streams_sha256',
        'role_row_counts','parsed_roles','source_package_object_count','plain_upload_object_count',
        'plain_payload_byte_count','lineage_byte_count','contributions_reparsed_by_this_helper',
        'source_guard',*truths,*FALSE_FLAGS}
    require(type(value) is dict and set(value)==keys and value['schema']==SCHEMA+'-receipt'
        and canonical(value['input_binding'])==canonical(expected_input_binding())
        and value['input_binding_sha256']==sha(canonical(expected_input_binding()))
        and type(value['parsed_role_streams_sha256']) is str
        and re.fullmatch('[0-9a-f]{64}',value['parsed_role_streams_sha256'])
        and value['parsed_roles']==list(PARSED_ROLES)
        and all(value[k] is True for k in truths)
        and value['contributions_reparsed_by_this_helper'] is False
        and all(value[k] is False for k in FALSE_FLAGS),'output')
    counts=value['role_row_counts'];require(type(counts) is dict and set(counts)==set(ROLES)
        and all(type(v) is int and 0<v<=2000000 for v in counts.values())
        and counts['evaluator_manifest']==1 and counts['session_axis']==AXIS_COUNT
        and counts['runtime_symbol_bindings']==BINDING_COUNT and counts['memberships']<=25000,'output')
    for key in ('source_package_object_count','plain_upload_object_count'):
        require(type(value[key]) is int and 6<=value[key]<=MAX_FILES,'output')
    require(type(value['plain_payload_byte_count']) is int and 0<value['plain_payload_byte_count']<=MAX_PLAIN_BYTES
        and type(value['lineage_byte_count']) is int and 0<value['lineage_byte_count']<=MAX_LINEAGE_BYTES,'output')
    source=value['source_guard'];sourcekeys={'schema','source_leaf_count','source_payload_byte_count',
        'current_endpoint_sha256','full_current_native_security_checked','full_current_metadata_checked',
        'fixed_leaf_bytes_authenticated','normal_return_required_before_use','historical_continuity_proven','continuous_integrity_proven'}
    require(type(source) is dict and set(source)==sourcekeys and source['schema']==SCHEMA+'-source'
        and type(source['source_leaf_count']) is int and source['source_leaf_count']==value['source_package_object_count']+1
        and type(source['source_payload_byte_count']) is int
        and source['source_payload_byte_count']==SOURCE_TOTAL_BYTES+value['lineage_byte_count']
        and type(source['current_endpoint_sha256']) is str and re.fullmatch('[0-9a-f]{64}',source['current_endpoint_sha256'])
        and all(source[k] is True for k in ('full_current_native_security_checked','full_current_metadata_checked',
            'fixed_leaf_bytes_authenticated','normal_return_required_before_use'))
        and source['historical_continuity_proven'] is source['continuous_integrity_proven'] is False,'output')
    return clone(value)
