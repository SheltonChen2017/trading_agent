"""Pure supplied ORIGINAL-output and observed-exit tests; no operational IO."""
import copy
import json

import pytest

from scripts import arv2_r347_a4_output as m


def refused(code,operation):
    with pytest.raises(m.Refused) as caught:operation()
    assert caught.value.args==(code,)


def binding():
    return {'schema':m.SCHEMA,'candidate_id':m.CANDIDATE,'attempt':4,'expected_head':'a'*40,
        'caller_sha256':'b'*64,'plan_sha256':'c'*64,'profile_sha256':'d'*64}


def look(*,consumed=True):
    return {'shared_look_delta':int(consumed),'development_look_delta':int(consumed),
        'infrastructure_look_delta':0,'accepted_result_cell_delta':0,
        'first_application_dispatch':{'endpoint':'compile/create','application_dispatch_ordinal':17,
            'candidate_id':m.CANDIDATE,'attempt':4} if consumed else None,
        'physical_request_count_measured':False}


def input_metadata():
    objects=[]
    prefix='arv2/newrule-plain-v1/95405d1b569d4bfeeb6c6d87/'
    for ordinal,(name,size,digest) in enumerate(m.OBJECT_FILES):
        objects.append({'ordinal':ordinal,'key_sha256':m.pin((prefix+name).encode('ascii'))['sha256'],
            'byte_count':size,'local_payload_sha256':digest,'metadata_md5':'a'*32,
            'verification':'fresh_properties_key_size_MD5_only_runtime_SHA256_required',
            **dict.fromkeys(m.OBJECT_FLAGS,False)})
    return {'observations':[{'phase':'begin','objects':copy.deepcopy(objects)},
        {'phase':'launch-0','objects':copy.deepcopy(objects)}],
        'qualification':'current_key_size_MD5_metadata_not_remote_SHA256_attestation_runtime_reader_rechecks_all_SHA256'}


@pytest.fixture
def success():
    receipt={'candidate_id':m.CANDIDATE,'attempt':4,'project_id':m.PROJECT,
        'compile_id':'synthetic-compile','backtest_id':'synthetic-backtest','backtest_name':m.BACKTEST_NAME}
    access={'schema':'arv2-r345-legacy-six-qc-v3','reference_project_id':37165262,
        'organization_sha256':'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880',
        'owner_row_sha256':'e'*64,'reference_code_running':False,'reference_privacy':'unproven',
        'capacity':{'node_count':2,'busy_count':1,'selected_count':2,'auto_select':True,'available_count':1},
        **dict.fromkeys(m.FLAGS[:-1],False)}
    result={'candidate_id':m.CANDIDATE,'attempt':4,'project_id':m.PROJECT,'launch_receipt':receipt,
        'terminal_receipt':None,'observed_status':'In Progress...','running_observed':True,
        'terminal_identity_observed':False,'access':access,'source_identity':copy.deepcopy(m.SOURCE_IDENTITY),
        'input_metadata_admission':input_metadata(),
        'application_dispatch_count':88,'last_access_observation':None,'last_api_diagnostic':None,
        'look_accounting':look(),'result_semantics':'statistics_disabled_status_only_no_strategy_result',
        **dict.fromkeys(m.FLAGS,False)}
    report={'schema':m.SCHEMA+'-result','binding':binding(),'attempt_consumed':True,'result':result}
    return {**report,'report_pin':m.pin(m.canonical(report))}


def repin(value):
    report={key:value[key] for key in ('schema','binding','attempt_consumed','result')}
    value['report_pin']=m.pin(m.canonical(report))


def validate(value,*,actual_exit=0,expected=None):
    return m.validate_original_stdout(m.canonical(value)+b'\n',actual_exit=actual_exit,
        expected_binding=binding() if expected is None else expected)


def test_exact_running_original_output_is_detached_without_readiness_or_result_acceptance(success):
    output=validate(success)
    assert output['success'] is output['running_observed'] is True
    assert output['actual_exit']==0 and output['terminal_identity_observed'] is False
    assert output['independent_QC_authentication'] is output['result_read'] is output['paper_or_live_ready'] is False
    assert output['qualification']==m.QUALIFICATION
    success['result']['launch_receipt']['backtest_id']='changed'
    assert output['original_envelope']['result']['launch_receipt']['backtest_id']=='synthetic-backtest'


def test_exact_completed_identity_is_accepted_without_strategy_statistics(success):
    result=success['result'];result.update(observed_status='Completed.',running_observed=False,
        terminal_identity_observed=True,terminal_receipt={**result['launch_receipt'],'status':'Completed.'})
    repin(success);output=validate(success)
    assert output['success'] is output['terminal_identity_observed'] is True
    assert output['running_observed'] is output['result_read'] is False


@pytest.mark.parametrize('exit',[None,True,False,-1,1,3,'0'])
def test_unknown_bool_or_nonaccepted_actual_exit_never_becomes_success(success,exit):
    refused('actual_exit',lambda:validate(success,actual_exit=exit))


def test_nonzero_actual_exit_refuses_a_complete_looking_successful_report(success):
    refused('shape',lambda:validate(success,actual_exit=2))


@pytest.mark.parametrize('fault,code',[('head','binding'),('caller','binding'),('plan','binding'),
    ('profile','binding'),('candidate','binding'),('attempt','binding'),('exit_frame','binding'),
    ('report_pin','report_pin'),('extra_outer','shape'),('extra_result','shape'),('raw','shape'),
    ('receipt_project','receipt'),('receipt_attempt','receipt'),('receipt_candidate','receipt'),
    ('receipt_name','receipt'),('receipt_compile','receipt'),('receipt_backtest','receipt'),
    ('result_project','result'),('result_attempt','result'),('semantics','result'),
    ('identity','identity'),('api_diagnostic','identity'),('look_reset','look'),('look_cells','look')])
def test_external_binding_closed_frames_receipts_and_ancestry_are_load_bearing(success,fault,code):
    result=success['result']
    if fault in ('head','caller','plan','profile'):
        key={'head':'expected_head','caller':'caller_sha256','plan':'plan_sha256','profile':'profile_sha256'}[fault]
        success['binding'][key]='e'*(40 if fault=='head' else 64)
    elif fault=='candidate':success['binding']['candidate_id']='R343-AR200'
    elif fault=='attempt':success['binding']['attempt']=3
    elif fault=='exit_frame':success['attempt_consumed']=False
    elif fault=='report_pin':success['report_pin']['sha256']='0'*64
    elif fault=='extra_outer':success['independent_review']=True
    elif fault=='extra_result':result['private_rows']=[]
    elif fault=='raw':result['raw_exception']='PRIVATE-TEXT'
    elif fault.startswith('receipt_'):
        key=fault.removeprefix('receipt_');key={'project':'project_id','candidate':'candidate_id',
            'name':'backtest_name','compile':'compile_id','backtest':'backtest_id'}.get(key,key)
        result['launch_receipt'][key]=3 if key in ('attempt','project_id') else ''
    elif fault=='result_project':result['project_id']=123
    elif fault=='result_attempt':result['attempt']=3
    elif fault=='semantics':result['result_semantics']='accepted strategy result'
    elif fault=='identity':result['source_identity']['actual_plain_package_sha256']='0'*64
    elif fault=='api_diagnostic':result['last_api_diagnostic']={'raw_error':'private'}
    elif fault=='look_reset':result['look_accounting']['shared_look_delta']=0
    else:result['look_accounting']['accepted_result_cell_delta']=1
    if fault!='report_pin':repin(success)
    refused(code,lambda:validate(success))


@pytest.mark.parametrize('flag',m.FLAGS)
def test_rehashed_readiness_or_result_flags_still_refuse(success,flag):
    success['result'][flag]=True;repin(success)
    refused('result',lambda:validate(success))


@pytest.mark.parametrize('status',['In Queue...','Runtime Error','Completed','running',None])
def test_queued_or_error_or_inexact_terminal_status_is_not_running_success(success,status):
    success['result']['observed_status']=status;repin(success)
    refused('status',lambda:validate(success))


@pytest.mark.parametrize('fault',['running_flag','terminal_flag','wrong_terminal','completed_without_receipt'])
def test_status_flags_and_terminal_receipt_cannot_disagree(success,fault):
    result=success['result']
    if fault=='running_flag':result['running_observed']=1
    elif fault=='terminal_flag':result['terminal_identity_observed']=True
    elif fault=='wrong_terminal':result['terminal_receipt']={**result['launch_receipt'],'status':'Completed.'}
    else:result.update(observed_status='Completed.',running_observed=False,terminal_identity_observed=True)
    repin(success)
    refused('receipt' if fault in ('wrong_terminal','completed_without_receipt') else 'status',lambda:validate(success))


@pytest.mark.parametrize('fault',['node_count','busy_count','available_count','reference','extra','privacy'])
def test_reference_capacity_is_closed_qualified_observation(success,fault):
    access=success['result']['access']
    if fault in ('node_count','busy_count','available_count'):access['capacity'][fault]=True
    elif fault=='reference':access['reference_project_id']=123
    elif fault=='extra':access['raw_project']={}
    else:access['reference_privacy']='proven_private'
    repin(success);refused('shape' if fault=='extra' else 'access',lambda:validate(success))


@pytest.mark.parametrize('fault',['phase','count','order','pin','key','MD5','remote_sha_claim','changed_later'])
def test_input_metadata_is_exact_six_object_qualified_receipt_at_begin_and_prelaunch(success,fault):
    value=success['result']['input_metadata_admission'];rows=value['observations']
    if fault=='phase':rows[-1]['phase']='unfrozen-fallback'
    elif fault=='count':rows.pop()
    elif fault=='order':rows[0]['objects'].reverse()
    elif fault=='pin':rows[0]['objects'][0]['local_payload_sha256']='0'*64
    elif fault=='key':rows[0]['objects'][0]['key_sha256']='0'*64
    elif fault=='MD5':rows[0]['objects'][0]['metadata_md5']='not-hex'
    elif fault=='remote_sha_claim':rows[0]['objects'][0]['remote_payload_sha256_attested']=True
    else:rows[-1]['objects'][0]['metadata_md5']='b'*32
    repin(success);refused('input_metadata',lambda:validate(success))


@pytest.mark.parametrize('suffix',[b'',b'\n\n',b' \n',b'\ntrailing'])
def test_exact_one_LF_and_no_trailing_bytes(success,suffix):
    refused('canonical' if suffix in (b'',b'\n\n',b' \n') else 'shape',lambda:
        m.validate_original_stdout(m.canonical(success)+suffix,actual_exit=0,expected_binding=binding()))


@pytest.mark.parametrize('raw',[b'{"x":1,"x":1}\n',b'{"x":NaN}\n',b'\xff\n'])
def test_duplicate_nonfinite_or_nonascii_output_refuses(raw):
    refused('shape',lambda:m.validate_original_stdout(raw,actual_exit=0,expected_binding=binding()))


def test_oversized_output_refuses_before_json_parse():
    refused('bound',lambda:m.validate_original_stdout(b'x'*(m.MAX_OUTPUT+1),actual_exit=0,expected_binding=binding()))


def failure():
    return {'schema':m.SCHEMA+'-failure','stage':'source_compile','claim_state':'consumed',
        'failure_code':'operation','evidence':None,**dict.fromkeys(m.FLAGS,False)}


def test_actual_failure_preserves_original_finite_frame_without_success_or_binding_authentication():
    value=failure();result=validate(value,actual_exit=2)
    assert result['success'] is result['running_observed'] is result['terminal_identity_observed'] is False
    assert result['actual_exit']==2 and result['original_envelope']==value
    assert result['failure_binding_in_stdout'] is False and result['independent_QC_authentication'] is False


def test_failure_output_with_actual_zero_never_becomes_success():
    refused('shape',lambda:validate(failure(),actual_exit=0))


@pytest.mark.parametrize('fault',['raw','stage','claim','code','flag'])
def test_failure_outer_envelope_is_closed_and_finite(fault):
    value=failure()
    if fault=='raw':value['traceback']='PRIVATE-RAW-TEXT'
    elif fault=='stage':value['stage']='unknown-stage'
    elif fault=='claim':value['claim_state']='safely-unspent'
    elif fault=='code':value['failure_code']='PRIVATE-RAW-TEXT'
    else:value['result_read']=True
    refused('shape' if fault=='raw' else 'failure',lambda:validate(value,actual_exit=2))


@pytest.mark.parametrize('field',['stage','claim_state','failure_code'])
@pytest.mark.parametrize('wrong',[[],{},True,123,None])
def test_malformed_failure_classification_types_raise_only_finite_refusal(field,wrong):
    value=failure();value[field]=wrong
    refused('failure',lambda:validate(value,actual_exit=2))


def test_failure_retains_known_allocations_and_accounting_without_raw_API_or_cause_claims():
    value=failure()
    value['evidence']={'module_error':{'module':'engine','code':'source_changed'},'last_http_status':200,
        'http_status_count':30,'http_status_vector_pin':m.pin(b'[]'),'last_http_statuses':[],
        'response_pin_count':30,'response_pin_vector_pin':m.pin(b'[]'),'last_response_pins':[],
        'last_request':None,'engine_last_request':None,'engine_last_failure':None,
        'last_access_observation':None,'last_api_diagnostic':None,
        'allocated_identities':{'project_id':m.PROJECT,'compile_id':'compile-id','backtest_id':None},
        'object_observation':None,'look_accounting':look()}
    result=validate(value,actual_exit=2)
    assert result['original_envelope']['evidence']['allocated_identities']['compile_id']=='compile-id'
    assert result['original_envelope']['evidence']['look_accounting']['shared_look_delta']==1
    value['evidence']['raw_exception']='PRIVATE-RAW-TEXT'
    refused('shape',lambda:validate(value,actual_exit=2))


def test_unsupported_numeric_objects_do_not_cross_safe_output_tree(success):
    success['result']['access']['capacity']['available_count']=1.0;repin(success)
    refused('shape',lambda:validate(success))
