"""Pure fixed-path metadata classification for the spent R338 input refusal.

Only caller-supplied named metadata endpoints are inspected. No filesystem,
contents, directory listing, ACL/xattr, source authentication, repair or policy
waiver exists here. Absolute lstat is terminal-component nofollow only; this
metadata diagnostic never claims all-component or continuous path integrity.
"""
import hashlib
import json
from pathlib import PurePosixPath
import re
import stat

ROOT=PurePosixPath('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
INPUT_ROOT=ROOT/'artifacts/analyst_revisions_v2/massive_ratings_delta/R297-20261013-D5/package'
PACKAGE_SHA256='411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad'
LINEAGE_SHA256='e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9'
PACKAGE=INPUT_ROOT/('arv2-preliminary-qc-package-'+PACKAGE_SHA256[:24])
LINEAGE=INPUT_ROOT/('arv2-october-lineage-'+LINEAGE_SHA256)/'lineage.json'
INPUT_SOURCE_SHA256='a7e56ca57bd54b4743c18f04f5287119b91c82a9bf7165692ad2cb457b8d7ce8'
SOURCE_ACTIVATION_BYTES=4631
MAX_LEAF_BYTES,MAX_LINEAGE_BYTES=32*1024*1024,64*1024
SCHEMA='arv2-r338-input-metadata-shape-v1'
PRIVATE_SCHEMA=SCHEMA+'-private'
FIELDS=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns','st_flags')
STATUSES=('observed','not_found','permission_denied','not_directory','blocked_ancestor','unavailable')
KINDS=('directory','source_activation','lineage')
OBSERVED_KINDS=('directory','regular_file','symlink','fifo','socket','character_device','block_device','other','unavailable')
PREDICATES=('kind','owner','flags','mode','single_link','positive_size','maximum_size','exact_size')
FLAGS_CLASSES=('ordinary','unsupported','not_required','unavailable')
MAX_PATHS,MAX_PRIVATE_BYTES=64,64*1024
FALSE_FLAGS={key:False for key in ('file_contents_read','directory_names_listed','ACL_or_xattrs_observed',
    'all_component_nofollow_proven','held_descriptor_identity_proven','continuous_path_integrity_proven',
    'source_bytes_authenticated','source_or_policy_repaired','mode_or_owner_waiver_granted','cause_of_old_failure_proven',
    'old_control_or_operation_replayed','QC_contact','Safari_access','USB_read','credential_access',
    'source_admission_granted','price_coverage_proven','backtest_ready','point_in_time_proven','paper_or_live_ready')}
FINITE=frozenset(('scope','rows','metadata','uid','transport_nonce','output','private_bound','unknown'))


class Refused(ValueError):
    """Finite shape/schema predicate only, never an input value or raw error."""


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
    except (ValueError,TypeError,UnicodeError,RecursionError):raise Refused('output') from None


def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(value):return sha(canonical(value))
def pin(raw):return {'byte_count':len(raw),'sha256':sha(raw)}


def scope():
    """Derive only the used guard's static known-path traversal, never list files."""
    paths=[];seen=set()
    leaves=((PACKAGE/'transport-manifest.json','source_activation',MAX_LEAF_BYTES,SOURCE_ACTIVATION_BYTES),
        (LINEAGE,'lineage',MAX_LINEAGE_BYTES,None))
    for leaf,kind,maximum,exact in leaves:
        for path in (*reversed(leaf.parents),leaf):
            if path in seen:continue
            seen.add(path);isleaf=path==leaf;scoped=path==ROOT or ROOT in path.parents
            paths.append({'path_index':len(paths),'path':str(path),'kind':kind if isleaf else 'directory',
                'scoped':scoped,'required_mode':0o600 if isleaf else (0o755 if path==ROOT else 0o700) if scoped else None,
                'maximum_bytes':maximum if isleaf else None,'exact_bytes':exact if isleaf else None})
    require(0<len(paths)<=MAX_PATHS,'scope')
    return tuple(paths)


def profile_record():
    return {'schema':SCHEMA,'private_schema':PRIVATE_SCHEMA,'used_input_source_sha256':INPUT_SOURCE_SHA256,
        'scope':list(scope()),'metadata_fields':list(FIELDS),'maximum_paths':MAX_PATHS,
        'maximum_private_bytes':MAX_PRIVATE_BYTES,'statuses':list(STATUSES),'predicates':list(PREDICATES),
        'policy':'used_InputGuard_policy_kind_then_scoped_owner_flags_mode_then_leaf_links_positive_max_exact_size',
        'all_predicates':'evaluate_individually_on_each_observed_full_ten_field_endpoint_even_after_policy_failure',
        'caller_collection':'parent_first_named_lstat_only_two_passes_block_descendants_of_non_directory_or_unavailable_ancestor',
        'earliest_shape':'first_observed_failing_fixed_path_index_first_endpoint_before_second_no_historical_cause_claim',
        'endpoint_limit':'terminal_component_lstat_only_no_held_fds_no_all_component_or_transient_symlink_proof',
        'private_transport':'mandatory_fresh_claim_bound_64_lowerhex_nonce_private_only_before_evidence_hash',**FALSE_FLAGS}


def _metadata(value):
    require(type(value) is tuple and len(value)==len(FIELDS)
        and all(type(number) is int and number>=0 for number in value),'metadata')
    return value


def _kind(mode):
    for predicate,label in ((stat.S_ISDIR,'directory'),(stat.S_ISREG,'regular_file'),(stat.S_ISLNK,'symlink'),
        (stat.S_ISFIFO,'fifo'),(stat.S_ISSOCK,'socket'),(stat.S_ISCHR,'character_device'),(stat.S_ISBLK,'block_device')):
        if predicate(mode):return label
    return 'other'


def _classify(spec,info,status,uid):
    if info is None:
        return {'status':status,'observed_kind':'unavailable','mode':None,'owner_match':None,
            'flags_class':'unavailable','predicates':{key:None for key in PREDICATES},
            'failed_predicates':[],'policy_passed':None}
    _metadata(info);isleaf=spec['kind']!='directory';scoped=spec['scoped']
    ordinary=(info[9]&~(stat.UF_TRACKED|stat.UF_HIDDEN))==0
    predicates={'kind':stat.S_ISREG(info[2]) if isleaf else stat.S_ISDIR(info[2]),
        'owner':info[3]==uid if scoped else None,'flags':ordinary if scoped else None,
        'mode':stat.S_IMODE(info[2])==spec['required_mode'] if scoped else None,
        'single_link':info[5]==1 if isleaf and scoped else None,
        'positive_size':info[6]>0 if isleaf and scoped else None,
        'maximum_size':info[6]<=spec['maximum_bytes'] if isleaf and scoped else None,
        'exact_size':info[6]==spec['exact_bytes'] if isleaf and scoped and spec['exact_bytes'] is not None else None}
    failed=[key for key in PREDICATES if predicates[key] is False]
    return {'status':status,'observed_kind':_kind(info[2]),'mode':format(stat.S_IMODE(info[2]),'04o'),
        'owner_match':info[3]==uid,'flags_class':'not_required' if not scoped else 'ordinary' if ordinary else 'unsupported',
        'predicates':predicates,'failed_predicates':failed,'policy_passed':not failed}


def inspect_metadata(rows,*,uid,transport_nonce):
    require(type(uid) is int and uid>=0,'uid')
    require(type(transport_nonce) is str and re.fullmatch('[0-9a-f]{64}',transport_nonce) is not None,'transport_nonce')
    plan=scope();require(type(rows) in (list,tuple) and len(rows)==len(plan),'rows')
    public=[];private_rows=[]
    for spec,row in zip(plan,rows,strict=True):
        require(type(row) is dict and set(row)=={'path_index','path','first_metadata','second_metadata','first_status','second_status'}
            and type(row['path_index']) is int and row['path_index']==spec['path_index']
            and type(row['path']) is str and row['path']==spec['path'],'scope')
        endpoints=[]
        for endpoint in ('first','second'):
            info,status=row[endpoint+'_metadata'],row[endpoint+'_status']
            require(type(status) is str and status in STATUSES and (status=='observed') is (info is not None),'rows')
            if info is not None:_metadata(info)
            endpoints.append(_classify(spec,info,status,uid))
        first,second=endpoints
        equal=None if row['first_metadata'] is None or row['second_metadata'] is None else row['first_metadata']==row['second_metadata']
        public.append({'path_index':spec['path_index'],'kind':spec['kind'],'first':first,'second':second,
            'metadata_equal':equal})
        private_rows.append({'path_index':spec['path_index'],'path':spec['path'],
            'first_metadata':list(row['first_metadata']) if row['first_metadata'] is not None else None,
            'second_metadata':list(row['second_metadata']) if row['second_metadata'] is not None else None,
            'first_status':row['first_status'],'second_status':row['second_status']})
    private={'schema':PRIVATE_SCHEMA,'transport_nonce':transport_nonce,'expected_uid':uid,
        'used_input_source_sha256':INPUT_SOURCE_SHA256,'metadata_fields':list(FIELDS),'rows':private_rows,**FALSE_FLAGS}
    raw=canonical(private);require(len(raw)<=MAX_PRIVATE_BYTES,'private_bound')
    first_shape=next((row['path_index'] for row in public
        if row['first']['policy_passed'] is False or row['second']['policy_passed'] is False),None)
    first_unknown=next((row['path_index'] for row in public
        if row['first']['policy_passed'] is None or row['second']['policy_passed'] is None),None)
    first_changed=next((row['path_index'] for row in public if row['metadata_equal'] is False),None)
    summary={'schema':SCHEMA,'profile_sha256':digest(profile_record()),'used_input_source_sha256':INPUT_SOURCE_SHA256,
        'diagnostic_complete':True,'path_count':len(public),'rows':public,
        'earliest_shape_index':first_shape,'first_unavailable_index':first_unknown,'first_changed_index':first_changed,
        'shape_failure_path_count':sum(row['first']['policy_passed'] is False or row['second']['policy_passed'] is False for row in public),
        'unavailable_path_count':sum(row['first']['policy_passed'] is None or row['second']['policy_passed'] is None for row in public),
        'changed_path_count':sum(row['metadata_equal'] is False for row in public),
        'all_observed_policy_passed':first_shape is None and first_unknown is None,
        'all_metadata_endpoints_equal':all(row['metadata_equal'] is True for row in public),
        'private_evidence_pin':pin(raw),**FALSE_FLAGS}
    validate_summary(summary);return summary,private


def validate_summary(value):
    keys={'schema','profile_sha256','used_input_source_sha256','diagnostic_complete','path_count','rows','earliest_shape_index',
        'first_unavailable_index','first_changed_index','shape_failure_path_count','unavailable_path_count','changed_path_count',
        'all_observed_policy_passed','all_metadata_endpoints_equal','private_evidence_pin',*FALSE_FLAGS}
    plan=scope()
    require(type(value) is dict and set(value)==keys and value['schema']==SCHEMA
        and value['profile_sha256']==digest(profile_record()) and value['used_input_source_sha256']==INPUT_SOURCE_SHA256
        and value['diagnostic_complete'] is True and type(value['path_count']) is int and value['path_count']==len(plan)
        and type(value['rows']) is list and len(value['rows'])==len(plan)
        and all(value[key] is False for key in FALSE_FLAGS),'output')
    for spec,row in zip(plan,value['rows'],strict=True):
        require(type(row) is dict and set(row)=={'path_index','kind','first','second','metadata_equal'}
            and type(row['path_index']) is int and row['path_index']==spec['path_index'] and row['kind']==spec['kind']
            and (row['metadata_equal'] is None or type(row['metadata_equal']) is bool),'output')
        for endpoint in ('first','second'):
            item=row[endpoint]
            require(type(item) is dict and set(item)=={'status','observed_kind','mode','owner_match','flags_class','predicates',
                'failed_predicates','policy_passed'} and type(item['status']) is str and item['status'] in STATUSES
                and type(item['observed_kind']) is str and item['observed_kind'] in OBSERVED_KINDS
                and item['flags_class'] in FLAGS_CLASSES and type(item['predicates']) is dict
                and set(item['predicates'])==set(PREDICATES)
                and all(v is None or type(v) is bool for v in item['predicates'].values()),'output')
            predicates=item['predicates'];failed=[key for key in PREDICATES if predicates[key] is False]
            if item['status']!='observed':
                require(item['observed_kind']=='unavailable' and item['mode'] is None and item['owner_match'] is None
                    and item['flags_class']=='unavailable' and all(v is None for v in predicates.values())
                    and item['failed_predicates']==[] and item['policy_passed'] is None,'output')
                continue
            require(type(item['mode']) is str and re.fullmatch('[0-7]{4}',item['mode']) is not None
                and type(item['owner_match']) is bool and type(item['policy_passed']) is bool
                and item['observed_kind']!='unavailable' and item['failed_predicates']==failed
                and item['policy_passed'] is (not failed),'output')
            required={'kind'}|({'owner','flags','mode'} if spec['scoped'] else set())|(
                {'single_link','positive_size','maximum_size'} if spec['kind']!='directory' and spec['scoped'] else set())|(
                {'exact_size'} if spec['exact_bytes'] is not None and spec['scoped'] else set())
            require(all((type(predicates[key]) is bool) if key in required else predicates[key] is None for key in PREDICATES)
                and predicates['kind'] is (item['observed_kind']==('directory' if spec['kind']=='directory' else 'regular_file'))
                and (not spec['scoped'] or predicates['owner'] is item['owner_match'])
                and (item['flags_class']=='not_required' if not spec['scoped'] else item['flags_class'] in ('ordinary','unsupported')
                    and predicates['flags'] is (item['flags_class']=='ordinary'))
                and (not spec['scoped'] or predicates['mode'] is (int(item['mode'],8)==spec['required_mode'])),'output')
        observed=row['first']['status']==row['second']['status']=='observed'
        require((type(row['metadata_equal']) is bool) if observed else row['metadata_equal'] is None,'output')
        if row['metadata_equal'] is True:require(row['first']==row['second'],'output')
    derived={
        'earliest_shape_index':next((row['path_index'] for row in value['rows'] if row['first']['policy_passed'] is False or row['second']['policy_passed'] is False),None),
        'first_unavailable_index':next((row['path_index'] for row in value['rows'] if row['first']['policy_passed'] is None or row['second']['policy_passed'] is None),None),
        'first_changed_index':next((row['path_index'] for row in value['rows'] if row['metadata_equal'] is False),None),
        'shape_failure_path_count':sum(row['first']['policy_passed'] is False or row['second']['policy_passed'] is False for row in value['rows']),
        'unavailable_path_count':sum(row['first']['policy_passed'] is None or row['second']['policy_passed'] is None for row in value['rows']),
        'changed_path_count':sum(row['metadata_equal'] is False for row in value['rows']),
        'all_observed_policy_passed':all(row['first']['policy_passed'] is True and row['second']['policy_passed'] is True for row in value['rows']),
        'all_metadata_endpoints_equal':all(row['metadata_equal'] is True for row in value['rows'])}
    require(all(type(value[key]) is type(expected) and value[key]==expected for key,expected in derived.items()),'output')
    item=value['private_evidence_pin'];require(type(item) is dict and set(item)=={'byte_count','sha256'}
        and type(item['byte_count']) is int and 0<item['byte_count']<=MAX_PRIVATE_BYTES
        and type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}',item['sha256']) is not None,'output')
    return value
