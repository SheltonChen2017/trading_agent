"""Pure ORIGINAL-stdout/observed-exit validation for the single R347 A4.

No file, credential, process or network operation exists here. Successful
validation checks supplied bytes and external scope, not provenance of those
bytes, private control files, current QC state, strategy results or readiness.
"""
import hashlib
import json
import re

SCHEMA='arv2-r347-legacy-six-operation-a4-v1'
OUTPUT_SCHEMA='arv2-r347-A4-original-output-validation-v1'
PROJECT=39054561
CANDIDATE='R343-AR100'
BACKTEST_NAME='ARV2 LEGACY SIX R343-AR100 OCT2026 A4'
MAX_OUTPUT=64*1024
FLAGS=('point_in_time_proven','formal_identity_admitted','formal_forward_ready','paper_or_live_ready','result_read')
QUALIFICATION='original_output_and_observed_exit_only_not_independent_control_or_QC_authentication'
FAILURE_CODES=frozenset(('arguments','environment','git','plan','source_pin','source_changed','inventory',
    'claim_spent','control','deadline','data','credentials','access','capacity','object_admission',
    'request','operation','compile','launch','output','close','unknown'))
STAGES=frozenset(('preflight','data','credentials','access','objects','source_compile','launch','status',
    'launched','running','completed_identity','complete'))
OBJECT_FILES=(('evaluator-manifest.json',3020,'06ebade9821c112726daed1f14a61144905c588242733a9d30c44aaefa3749e3'),
    ('session_axis-0000.jsonl',317762,'3e976a6e9df64472fcbc0d0dd775eab52d68fe0b1d2d665709ac03b18dc55a98'),
    ('memberships-0000.jsonl',1876147,'6da39a900784aea5f0be81a9a329b28a1399d8dc5d95ec60b3951f55e31f40cd'),
    ('contributions-0000.jsonl',9077887,'fe1412b460c60d2600f9999e307ba7ab47f3574652af2b1c6c468ae844407904'),
    ('runtime_symbol_bindings-0000.jsonl',7884142,'73ba4ac73c0485b2d274c31b5ec740a97a64de27a4f6dfbfb9cb63bc8e7cd15f'),
    ('transport-manifest.json',5901,'ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b'))
OBJECT_FLAGS=(*FLAGS[:-1],'remote_payload_sha256_attested','physical_request_count_measured',
    'continuous_privacy_proven','exclusive_resource_lease','attempt_budget_reset')
SOURCE_IDENTITY={'schema':'arv2-r347-fresh-plain-submission-DATA-v1',
    'actual_plain_package_sha256':'1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2',
    'source_lineage_sha256':'e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9',
    'ancestral_source_package_sha256':'411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad',
    'parent_proof_sha256':'95405d1b569d4bfeeb6c6d87fdb430f2fd27b8b7a31d6dcde7f82276d9903cd1',
    'actual_activation':{'schema':'arv2-newrule-plain-upload-object-v1','role':'activation_manifest','ordinal':0,
        'object_store_key':'arv2/newrule-plain-v1/95405d1b569d4bfeeb6c6d87/transport-manifest.json',
        'relative_path':'transport-manifest.json','byte_count':5901,
        'content_sha256':'ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b',
        'record_count':1,'compression':'identity','activation_manifest':True},
    'source_proposal_pin':{'byte_count':3055714,'sha256':'7149931d0ff1c02427b197058d90aa0b59629a9b805b7c8467f2c31d538b033a'},
    'current_QC_admission_granted':False,'attempt_budget_reset':False,'paper_or_live_ready':False}


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def canonical(value):
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
    except (TypeError,ValueError,UnicodeError,RecursionError):raise Refused('shape') from None


def pin(raw):return {'byte_count':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def _keys(value,keys):require(type(value) is dict and set(value)==set(keys),'shape')
def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None
def _nat(value,maximum):return type(value) is int and 0<=value<=maximum
def _identifier(value):return type(value) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',value) is not None


def _tree(value):
    pending=[(value,0)];count=0
    while pending:
        item,depth=pending.pop();count+=1
        require(count<=12000 and depth<=32,'bound')
        if type(item) is dict:
            require(len(item)<=128 and all(type(key) is str and len(key)<=120 for key in item),'bound')
            pending.extend((child,depth+1) for child in item.values())
        elif type(item) is list:
            require(len(item)<=4096,'bound');pending.extend((child,depth+1) for child in item)
        elif type(item) is str:require(item.isascii() and len(item)<=8192,'bound')
        elif type(item) is int:require(-(2**63)<item<2**63,'bound')
        else:require(item is None or type(item) is bool,'shape')


def _loads(raw):
    require(type(raw) is bytes and 0<len(raw)<=MAX_OUTPUT,'bound')
    def pairs(items):
        result={}
        for key,value in items:require(key not in result,'shape');result[key]=value
        return result
    try:
        result=json.loads(raw.decode('ascii'),object_pairs_hook=pairs,
            parse_constant=lambda _:(_ for _ in ()).throw(Refused('shape')))
    except Refused:raise
    except (ValueError,UnicodeError,RecursionError):raise Refused('shape') from None
    require(canonical(result)+b'\n'==raw,'canonical');_tree(result);return result


def _binding(value):
    _keys(value,('schema','candidate_id','attempt','expected_head','caller_sha256','plan_sha256','profile_sha256'))
    require(value['schema']==SCHEMA and value['candidate_id']==CANDIDATE
        and type(value['attempt']) is int and value['attempt']==4
        and type(value['expected_head']) is str and re.fullmatch('[0-9a-f]{40}',value['expected_head'])
        and all(_hash(value[key]) for key in ('caller_sha256','plan_sha256','profile_sha256')),'binding')


def _receipt(value):
    _keys(value,('candidate_id','attempt','project_id','compile_id','backtest_id','backtest_name'))
    require(value['candidate_id']==CANDIDATE and type(value['attempt']) is int and value['attempt']==4
        and type(value['project_id']) is int and value['project_id']==PROJECT
        and all(_identifier(value[key]) for key in ('compile_id','backtest_id'))
        and value['backtest_name']==BACKTEST_NAME,'receipt')


def _look(value,*,success):
    _keys(value,('shared_look_delta','development_look_delta','infrastructure_look_delta',
        'accepted_result_cell_delta','first_application_dispatch','physical_request_count_measured'))
    require(all(_nat(value[key],1) for key in ('shared_look_delta','development_look_delta'))
        and value['shared_look_delta']==value['development_look_delta']
        and type(value['infrastructure_look_delta']) is int and value['infrastructure_look_delta']==0
        and type(value['accepted_result_cell_delta']) is int and value['accepted_result_cell_delta']==0
        and value['physical_request_count_measured'] is False,'look')
    first=value['first_application_dispatch']
    if first is None:require(not success and value['shared_look_delta']==0,'look')
    else:
        _keys(first,('endpoint','application_dispatch_ordinal','candidate_id','attempt'))
        require(first['endpoint'] in ('compile/create','backtests/create')
            and _nat(first['application_dispatch_ordinal'],1200) and first['candidate_id']==CANDIDATE
            and type(first['attempt']) is int and first['attempt']==4
            and value['shared_look_delta']==1,'look')


def _access(value):
    _keys(value,('schema','reference_project_id','organization_sha256','owner_row_sha256','reference_code_running',
        'reference_privacy','capacity',*FLAGS[:-1]))
    require(value['schema']=='arv2-r345-legacy-six-qc-v3'
        and type(value['reference_project_id']) is int and value['reference_project_id']==37165262
        and value['organization_sha256']=='a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
        and _hash(value['owner_row_sha256']) and type(value['reference_code_running']) is bool
        and value['reference_privacy'] in ('explicit_private','unproven')
        and all(value[key] is False for key in FLAGS[:-1]),'access')
    capacity=value['capacity'];_keys(capacity,('node_count','busy_count','selected_count','auto_select','available_count'))
    require(all(_nat(capacity[key],64) for key in ('node_count','busy_count','selected_count','available_count'))
        and type(capacity['auto_select']) is bool and capacity['busy_count']<=capacity['node_count']
        and capacity['selected_count']<=capacity['node_count']
        and 0<capacity['available_count']<=capacity['node_count']-capacity['busy_count'],'access')


def _metadata(value):
    if value is None:return
    fields={'public','isLibrary','libraries','lastLiveDeployment','leanEnvironment','codeRunning',
        'owner','ownerId','organizationId','language','collaborators'}
    _keys(value,('schema','project_count','field_types','flags','library_count','collaborator_count',
        'last_live_empty','lean_environment_nonnegative_integer'))
    require(value['schema']=='arv2-r345-legacy-six-qc-v3-owned-access-metadata','metadata')
    _keys(value['field_types'],fields);_keys(value['flags'],('public','isLibrary','codeRunning','owner'))
    require(all(type(kind) is str and kind in ('absent','null','bool','int','float','str','list','dict','other')
        for kind in value['field_types'].values()) and all(flag in ('absent','true','false','other')
        for flag in value['flags'].values()) and all(value[key] is None or _nat(value[key],1000)
        for key in ('project_count','library_count','collaborator_count'))
        and value['last_live_empty'] in ('absent','empty','other')
        and type(value['lean_environment_nonnegative_integer']) is bool,'metadata')
    for key,flag in value['flags'].items():
        kind=value['field_types'][key]
        require((flag=='absent') is (kind=='absent') and ((flag in ('true','false')) is (kind=='bool')),'metadata')


def _input_metadata(value):
    _keys(value,('observations','qualification'))
    require(value['qualification']=='current_key_size_MD5_metadata_not_remote_SHA256_attestation_runtime_reader_rechecks_all_SHA256',
        'input_metadata')
    observations=value['observations']
    require(type(observations) is list and 2<=len(observations)<=4,'input_metadata')
    expected_prefix='arv2/newrule-plain-v1/95405d1b569d4bfeeb6c6d87/'
    first=None
    for index,observation in enumerate(observations):
        _keys(observation,('phase','objects'))
        require(observation['phase']==('begin' if index==0 else f'launch-{index-1}')
            and type(observation['objects']) is list and len(observation['objects'])==6,'input_metadata')
        for ordinal,(item,(name,size,digest)) in enumerate(zip(observation['objects'],OBJECT_FILES,strict=True)):
            _keys(item,('ordinal','key_sha256','byte_count','local_payload_sha256','metadata_md5','verification',*OBJECT_FLAGS))
            require(type(item['ordinal']) is int and item['ordinal']==ordinal
                and item['key_sha256']==pin((expected_prefix+name).encode('ascii'))['sha256']
                and type(item['byte_count']) is int and item['byte_count']==size
                and item['local_payload_sha256']==digest and type(item['metadata_md5']) is str
                and re.fullmatch('[0-9a-f]{32}',item['metadata_md5'])
                and item['verification']=='fresh_properties_key_size_MD5_only_runtime_SHA256_required'
                and all(item[key] is False for key in OBJECT_FLAGS),'input_metadata')
        if first is None:first=canonical(observation['objects'])
        else:require(canonical(observation['objects'])==first,'input_metadata')


def _success(value,expected):
    _keys(value,('schema','binding','attempt_consumed','result','report_pin'))
    require(value['schema']==SCHEMA+'-result' and value['attempt_consumed'] is True
        and canonical(value['binding'])==canonical(expected),'binding')
    report={key:value[key] for key in ('schema','binding','attempt_consumed','result')}
    require(value['report_pin']==pin(canonical(report)),'report_pin')
    result=value['result']
    _keys(result,('candidate_id','attempt','project_id','launch_receipt','terminal_receipt','observed_status',
        'running_observed','terminal_identity_observed','access','source_identity','application_dispatch_count',
        'input_metadata_admission','last_access_observation','last_api_diagnostic','look_accounting','result_semantics',*FLAGS))
    require(result['candidate_id']==CANDIDATE and type(result['attempt']) is int and result['attempt']==4
        and type(result['project_id']) is int and result['project_id']==PROJECT
        and _nat(result['application_dispatch_count'],1200) and result['application_dispatch_count']>0
        and result['result_semantics']=='statistics_disabled_status_only_no_strategy_result'
        and all(result[key] is False for key in FLAGS),'result')
    _receipt(result['launch_receipt']);status=result['observed_status']
    require(status in ('In Progress...','Completed.')
        and result['running_observed'] is (status=='In Progress...')
        and result['terminal_identity_observed'] is (status=='Completed.'),'status')
    if status=='Completed.':
        require(canonical(result['terminal_receipt'])==canonical({**result['launch_receipt'],'status':status}),'receipt')
    else:require(result['terminal_receipt'] is None,'receipt')
    _access(result['access']);_metadata(result['last_access_observation']);_look(result['look_accounting'],success=True)
    _input_metadata(result['input_metadata_admission'])
    require(result['last_api_diagnostic'] is None
        and canonical(result['source_identity'])==canonical(SOURCE_IDENTITY),'identity')
    return result


def _failure(value):
    _keys(value,('schema','stage','claim_state','failure_code','evidence',*FLAGS))
    require(value['schema']==SCHEMA+'-failure' and type(value['stage']) is str and value['stage'] in STAGES
        and type(value['claim_state']) is str and value['claim_state'] in ('unallocated','allocated_unknown','consumed')
        and type(value['failure_code']) is str and value['failure_code'] in FAILURE_CODES
        and all(value[key] is False for key in FLAGS),'failure')
    evidence=value['evidence']
    if evidence is None:return
    _keys(evidence,('module_error','last_http_status','http_status_count','http_status_vector_pin',
        'last_http_statuses','response_pin_count','response_pin_vector_pin','last_response_pins','last_request',
        'engine_last_request','engine_last_failure','last_access_observation','last_api_diagnostic',
        'allocated_identities','object_observation','look_accounting'))
    _keys(evidence['module_error'],('module','code'))
    require(evidence['module_error']['module'] in ('caller','consumer','engine','transport','unknown')
        and type(evidence['module_error']['code']) is str
        and re.fullmatch('[a-z_]{1,100}',evidence['module_error']['code']),'failure')
    require(evidence['last_http_status'] is None or _nat(evidence['last_http_status'],599)
        and evidence['last_http_status']>=100,'failure')
    _keys(evidence['allocated_identities'],('project_id','compile_id','backtest_id'))
    allocated=evidence['allocated_identities']
    require(allocated['project_id'] is None or type(allocated['project_id']) is int and allocated['project_id']==PROJECT,
        'failure')
    require(all(allocated[key] is None or _identifier(allocated[key]) for key in ('compile_id','backtest_id')),'failure')
    _metadata(evidence['last_access_observation'])
    if evidence['look_accounting'] is not None:_look(evidence['look_accounting'],success=False)
    # The caller already emits only its bounded, closed diagnostic projection.
    # This pure consumer preserves that original finite JSON; it does not
    # authenticate the response, cause, secret detection or remote effects.


def validate_original_stdout(raw,*,actual_exit,expected_binding):
    """Return a detached finite record; never read a report/control artifact."""
    _binding(expected_binding)
    require(type(actual_exit) is int and actual_exit in (0,2),'actual_exit')
    value=_loads(raw)
    if actual_exit==0:
        result=_success(value,expected_binding);success=True
        running,terminal=result['running_observed'],result['terminal_identity_observed']
    else:
        _failure(value);success=False;running=terminal=False
    return {'schema':OUTPUT_SCHEMA,'original_output_validated':True,'actual_exit':actual_exit,
        'success':success,'running_observed':running,'terminal_identity_observed':terminal,
        'original_envelope':json.loads(canonical(value)),'original_stdout_pin':pin(raw),
        'qualification':QUALIFICATION,'independent_QC_authentication':False,'result_read':False,
        'failure_binding_in_stdout':False if not success else None,
        'point_in_time_proven':False,'paper_or_live_ready':False}
