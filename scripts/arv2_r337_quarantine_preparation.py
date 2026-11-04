"""Supplied-byte R337 quarantine preparation, never strategy or source admission.

Only the new caller may authorize actual retained-byte use. This pure helper
extracts the five denied original bodies and authenticates the old vendor
archive ranges; it never rewrites the old catalog, parses individual prices,
resolves QC identities, or grants a launch.
"""
import hashlib
import json
import math
import re
import time

from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_policy as policy
from research.analyst_revisions_v2_qc import newrule_common_price_format as fmt

SCHEMA = 'arv2-r337-offline-quarantine-preparation-v1'
N_PIN = {'byte_count':294888,'sha256':'fd52e0d4177bf5c6b74dd0f1b6e8616ca03a9c8fb60ae5d9c57f584f075de86e'}
ARCHIVE_PIN = {'byte_count':148543046,'sha256':'2a2815b543c41728b441b0b300a9d269f282778ef1915923fd68f61993f9ca1f'}
MAGIC = b'ARV2-PRIVATE-PRICE-PAYLOAD-V1\n'
ARCHIVE_SCHEMA = 'arv2-r326-common-price-private-payload-v1-header'
PLAN_SHA256 = '1ad4590b361787b6126f5e4790034565c53a5e51d0173de67c422879160f74d4'
FACT_SHA256 = '19194ca0fc562b4b0fed8331d7c6e725c3dd7cc31fada7fa519a08acc10d28b3'
OUTPUT_SHA256 = '70e6def0fe2621965904e31fe8121c7713c5201b9b151397766f78091e7ab843'
ROLES = ('catalog',*(f'month_{i:03d}' for i in range(71)),'manifest')
HEADER_FLAGS = ('operation_granted','genuine_input_authenticated','source_admission_granted',
    'price_input_admitted','QC_transfer_granted','QC_processing_rights_granted','remote_durability_proven',
    'continuous_or_historical_integrity_proven','point_in_time_proven','formal_forward_ready','paper_or_live_ready')
FALSE_FLAGS = {name:False for name in ('provider_contact','QC_contact','Safari_access','credential_access',
    'USB_read','old_control_read','old_operation_replayed','original_catalog_rewritten',
    'full_original_binding_package_freshly_authenticated','fresh_QC_resolution_performed',
    'individual_price_rows_parsed','complete_price_coverage_proven','actual_target_or_holdings_path_proven',
    'source_admission_granted','strategy_result_accepted','point_in_time_proven','formal_identity_admitted',
    'formal_forward_ready','paper_or_live_ready','licensed_rows_disclosed','new_launch_attempt_granted')}
FINITE = frozenset(('input_pin','json','shape','case_binding','catalog','header','range','range_hash',
    'vendor_format','assignment','period','quarantine','bound','output','deadline','unknown'))
MAX_PRIVATE = 1024*1024
CELLS = ((6,0),(6,100),(6,200),(8,0),(8,100),(8,200))

class Refused(ValueError): pass

def require(value,code):
    if not value: raise Refused(code)

def canonical(value):
    try: return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
    except (ValueError,TypeError,UnicodeError,RecursionError): raise Refused('json') from None

def sha(raw): return hashlib.sha256(raw).hexdigest()
def pin(raw): return {'byte_count':len(raw),'sha256':sha(raw)}
def finite(error):
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
def budget(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline) and 0<deadline-time.monotonic()<=300,'deadline')

def loads(raw,maximum):
    require(type(raw) is bytes and 0<len(raw)<=maximum,'bound')
    def pairs(values):
        result={}
        for key,value in values:
            require(key not in result,'json');result[key]=value
        return result
    try:
        result=json.loads(raw.decode('ascii'),object_pairs_hook=pairs,
            parse_constant=lambda _:(_ for _ in ()).throw(Refused('json')))
        require(canonical(result)==raw,'json');return result
    except Refused: raise
    except (ValueError,UnicodeError,TypeError,RecursionError):raise Refused('json') from None

def _checked_pin(value,maximum):
    require(type(value) is dict and set(value)=={'byte_count','sha256'}
        and type(value['byte_count']) is int and 0<value['byte_count']<=maximum
        and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']),'shape')
    return value

def profile_record():
    return {'schema':SCHEMA,'N_DATA_pin':N_PIN,'vendor_archive_pin':ARCHIVE_PIN,
        'archive_roles':list(ROLES),'archive_magic_sha256':sha(MAGIC),
        'archive_source_plan_sha256':PLAN_SHA256,'archive_source_fact_sha256':FACT_SHA256,
        'archive_source_output_sha256':OUTPUT_SHA256,'maximum_private_bytes':MAX_PRIVATE,
        'maximum_seconds':300,'quarantine_policy_sha256':policy.quarantine_policy_sha256(),
        'evidence_epoch':policy.RESEARCH_EPOCH_ID,'cells':[list(cell) for cell in CELLS],
        'source_authentication':'whole_exact_archive_plus_all73_contiguous_range_pins_before_catalog_join',
        'quarantine':'exact_original_five_bodies_and_all_native_role_assignments_match_no_other_row_changed',
        'price_scope':'catalog_and_manifest_only_all_range_bytes_hashed_no_price_row_parse_or_completeness_claim',
        'runtime_gate':'future_genuine_full_binding_package_resolution_project_source_and_run_freeze_required',
        **FALSE_FLAGS}

def extract_catalog(n_raw):
    require(type(n_raw) is bytes and pin(n_raw)==N_PIN,'input_pin')
    n=loads(n_raw,N_PIN['byte_count'])
    require(type(n) is dict and n.get('schema')=='arv2-r336-retained-action-semantics-v1-private'
        and type(n.get('cases')) is list and len(n['cases'])==5,'shape')
    bindings=[]
    for ordinal,(case,whole) in enumerate(zip(n['cases'],policy.QUARANTINED_WHOLE_BINDING_SHA256S,strict=True)):
        require(type(case) is dict and type(case.get('case_ordinal')) is int
            and case['case_ordinal']==ordinal and case.get('whole_binding_sha256')==whole
            and case.get('identity_admitted') is False,'case_binding')
        require(type(case.get('original_M_case')) is dict and type(case.get('original_I_case')) is dict,'case_binding')
        m=case['original_M_case'];i=case['original_I_case'];f=i.get('original_F_case')
        require(type(f) is dict and type(m.get('binding')) is dict
            and m.get('whole_binding_sha256')==i.get('whole_binding_sha256')==f.get('whole_binding_sha256')==whole
            and m['binding']==f.get('binding') and sha(canonical(m['binding']))==whole,'case_binding')
        bindings.append(m['binding'])
    try:
        catalog=policy.make_quarantine_catalog_from_bindings(bindings)
        return policy.validate_quarantine_catalog(catalog,expected_sha256=sha(canonical(catalog)))
    except policy.NewruleError:raise Refused('quarantine') from None

def parse_archive(raw,*,deadline):
    budget(deadline);require(type(raw) is bytes and pin(raw)==ARCHIVE_PIN,'input_pin')
    start=len(MAGIC)+8
    require(raw.startswith(MAGIC) and len(raw)>=start,'header')
    length=int.from_bytes(raw[len(MAGIC):start],'big');require(0<length<=65536 and start+length<len(raw),'header')
    header=loads(raw[start:start+length],65536);base=start+length
    require(type(header) is dict and set(header)=={'schema','data_plan_sha256','source_fact_sha256',
        'source_output_sha256','entries','range_count','payload_byte_count',*HEADER_FLAGS}
        and header['schema']==ARCHIVE_SCHEMA and header['data_plan_sha256']==PLAN_SHA256
        and header['source_fact_sha256']==FACT_SHA256 and header['source_output_sha256']==OUTPUT_SHA256
        and all(header[key] is False for key in HEADER_FLAGS)
        and type(header['range_count']) is int and header['range_count']==len(ROLES)
        and type(header['payload_byte_count']) is int and header['payload_byte_count']==len(raw)-base
        and type(header['entries']) is list and len(header['entries'])==len(ROLES),'header')
    offset=0;parts={};descriptors={}
    for ordinal,(role,row) in enumerate(zip(ROLES,header['entries'],strict=True)):
        budget(deadline)
        require(type(row) is dict and set(row)=={'ordinal','role','offset','byte_count','sha256'}
            and type(row['ordinal']) is int and row['ordinal']==ordinal and row['role']==role
            and type(row['offset']) is int and row['offset']==offset,'range')
        maximum=fmt.MAX_CATALOG_BYTES if role=='catalog' else fmt.MAX_MANIFEST_BYTES if role=='manifest' else fmt.MAX_MONTH_BYTES
        expected=_checked_pin({k:row[k] for k in ('byte_count','sha256')},maximum)
        end=base+offset+expected['byte_count'];require(end<=len(raw),'range')
        chunk=memoryview(raw)[base+offset:end];require(sha(chunk)==expected['sha256'],'range_hash')
        if role in ('catalog','manifest'):parts[role]=bytes(chunk)
        descriptors[role]={**expected,'payload_offset':base+offset};offset+=expected['byte_count']
    require(base+offset==len(raw),'range');budget(deadline)
    try:
        vendor=fmt.validate_catalog(fmt.loads(parts['catalog'],fmt.MAX_CATALOG_BYTES))
        manifest=fmt.validate_manifest(fmt.loads(parts['manifest'],fmt.MAX_MANIFEST_BYTES))
        require(manifest['catalog_pin']==fmt.pin(parts['catalog']),'vendor_format')
        require([{k:row[k] for k in ('month_ordinal','month','session_indexes')} for row in manifest['months']]==vendor['months'],'vendor_format')
        for ordinal,row in enumerate(manifest['months']):
            expected={k:row[k] for k in ('byte_count','sha256')}
            require(expected=={k:descriptors[f'month_{ordinal:03d}'][k] for k in ('byte_count','sha256')},'range_hash')
    except fmt.Refused:raise Refused('vendor_format') from None
    return vendor,manifest,descriptors

def prepare(n_raw,archive_raw,*,deadline):
    budget(deadline);catalog=extract_catalog(n_raw)
    vendor,manifest,descriptors=parse_archive(archive_raw,deadline=deadline)
    assignments=vendor['assignments'];denied=catalog['quarantined_bindings'];by_whole={row['whole_binding_sha256']:row for row in assignments[:fmt.STOCK_COUNT]}
    native_rows=[row for row in assignments[:fmt.STOCK_COUNT] if row['role']==fmt.NATIVE]
    require(len(native_rows)==5 and {row['whole_binding_sha256'] for row in native_rows}==set(policy.QUARANTINED_WHOLE_BINDING_SHA256S),'assignment')
    joins=[]
    for ordinal,binding in enumerate(denied):
        whole=sha(canonical(binding));row=by_whole.get(whole)
        require(type(row) is dict and row['role']==fmt.NATIVE and row['security_id']==binding['security_id']
            and row['semantic_binding_sha256']==binding['row_sha256'],'assignment')
        joins.append({'case_ordinal':ordinal,'original_binding':binding,'source_index_assignment':row})
    sessions=[day for day in vendor['price_sessions'] if '2021-10-29'<=day<='2026-10-13']
    require(len(sessions)==1243 and sessions[0]=='2021-10-29' and sessions[1]=='2021-11-01'
        and sessions[-1]=='2026-10-13','period')
    summary={'schema':SCHEMA,'evidence_epoch':policy.RESEARCH_EPOCH_ID,'cell_order':[list(c) for c in CELLS],
        'quarantine_policy_sha256':policy.quarantine_policy_sha256(),'quarantine_catalog_pin':pin(canonical(catalog)),
        'N_DATA_pin':dict(N_PIN),'vendor_archive_pin':dict(ARCHIVE_PIN),
        'vendor_catalog_pin':{k:descriptors['catalog'][k] for k in ('byte_count','sha256')},
        'vendor_manifest_pin':{k:descriptors['manifest'][k] for k in ('byte_count','sha256')},
        'all_range_count':len(descriptors),'stock_assignment_count':fmt.STOCK_COUNT,'fund_assignment_count':fmt.FUND_COUNT,
        'unchanged_vendor_stock_count':fmt.VENDOR_COUNT,'unchanged_conditional_count':fmt.CONDITIONAL_COUNT,
        'quarantined_original_native_count':len(native_rows),'quarantine_source_index_join_count':len(joins),
        'manifest_declared_valid_price_cells':manifest['valid_count'],'manifest_declared_absent_price_cells':manifest['absent_count'],
        'reference_and_valuation_session_count':len(sessions),'source_catalog_and_manifest_authenticated':True,
        'all_archive_ranges_authenticated':True,'runtime_project_binding_pending':True,**FALSE_FLAGS}
    private={'schema':SCHEMA+'-private','quarantine_catalog':catalog,'source_index_joins':joins,
        'archive_range_descriptors':descriptors,'reference_and_valuation_sessions':sessions,
        'input_pins':{'semantics':dict(N_PIN),'archive':dict(ARCHIVE_PIN)},'inspection':summary,**FALSE_FLAGS}
    require(len(canonical(private))<=MAX_PRIVATE,'bound');validate_summary(summary);budget(deadline)
    return summary,catalog,private

def validate_summary(value):
    counts={'all_range_count':73,'stock_assignment_count':6151,'fund_assignment_count':8,
        'unchanged_vendor_stock_count':5636,'unchanged_conditional_count':510,'quarantined_original_native_count':5,
        'quarantine_source_index_join_count':5,'reference_and_valuation_session_count':1243,
        'manifest_declared_valid_price_cells':fmt.OBSERVED_ROWS,'manifest_declared_absent_price_cells':fmt.ABSENT_CELLS}
    pins=('quarantine_catalog_pin','vendor_catalog_pin','vendor_manifest_pin')
    keys={'schema','evidence_epoch','cell_order','quarantine_policy_sha256','N_DATA_pin','vendor_archive_pin',
        'source_catalog_and_manifest_authenticated','all_archive_ranges_authenticated','runtime_project_binding_pending',*pins,*counts,*FALSE_FLAGS}
    require(type(value) is dict and set(value)==keys and value['schema']==SCHEMA
        and value['evidence_epoch']==policy.RESEARCH_EPOCH_ID and value['cell_order']==[list(c) for c in CELLS]
        and value['quarantine_policy_sha256']==policy.quarantine_policy_sha256()
        and value['N_DATA_pin']==N_PIN and value['vendor_archive_pin']==ARCHIVE_PIN
        and all(value[k] is True for k in ('source_catalog_and_manifest_authenticated','all_archive_ranges_authenticated','runtime_project_binding_pending'))
        and all(value[k] is False for k in FALSE_FLAGS),'output')
    require(all(type(value[k]) is int and value[k]==n for k,n in counts.items()),'output')
    for key in pins:
        maximum=MAX_PRIVATE if key=='quarantine_catalog_pin' else fmt.MAX_MANIFEST_BYTES if key=='vendor_manifest_pin' else fmt.MAX_CATALOG_BYTES
        _checked_pin(value[key],maximum)
    return value
