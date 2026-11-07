"""Injected read-only result protocol: no QC, credentials or private DATA."""
import copy
import json
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from scripts import read_arv2_r348_ar100_result as m


def refused(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert caught.value.args==(code,)


def identity(status='Completed.'):
    return {'projectId':m.PROJECT,'compileId':m.COMPILE,'backtestId':m.BACKTEST,
        'name':m.BACKTEST_NAME,'status':status}


def packets(monkeypatch,status='Completed.'):
    owner={'uid':1,'owner':True,'name':'synthetic-owner','permission':'write','liveControl':True}
    monkeypatch.setattr(m,'OWNER_ROWS_PIN',m.pin(m.canonical([owner])))
    organization='a'*32;monkeypatch.setattr(m,'ORGANIZATION_SHA256',m.pin(organization.encode())['sha256'])
    row={'projectId':m.PROJECT,'name':m.PROJECT_NAME,'language':'Py','owner':True,'ownerId':1,
        'organizationId':organization,'codeRunning':False,'libraries':[],'lastLiveDeployment':None,
        'leanEnvironment':0,'collaborators':[owner]}
    sources=[[f'source{index:02d}.py',f'# synthetic {index}\n'] for index in range(18)]
    vector=[{'project_path':name,**m.pin(text.encode())} for name,text in sources]
    monkeypatch.setattr(m,'SOURCE_VECTOR_PIN',m.pin(m.canonical(vector)))
    monkeypatch.setattr(m,'SOURCE_BYTE_TOTAL',sum(item['byte_count'] for item in vector))
    statistics={name:m.canonical({'synthetic_statistic':name}).decode() for name in m.STATISTICS}
    mapping={'authenticate':{'success':True},
        'projects/read':{'success':True,'projects':[row]},
        'projects/collaboration/read':{'success':True,'collaborators':[owner],
            'userPermissions':'write','userLiveControl':True},
        'files/read':{'success':True,'files':[{'projectId':m.PROJECT,'name':name,'content':text} for name,text in sources]},
        'backtests/list':{'success':True,'count':1,'backtests':[identity(status)]},
        'backtests/read':{'success':True,'backtest':{**identity(),'statistics':statistics,
            'charts':{'SENSITIVE':'NEVER-RETAIN'},'logs':['NEVER-RETAIN']}}}
    candidate=NS(candidate_id='R343-AR100',cell_record=lambda:{'source_pairs':sources})
    return mapping,NS(candidates=(candidate,),evaluation_sessions=('synthetic-session',),
        source_identity_json=m.canonical({'synthetic_identity':True}))


class FakeStore:
    def __init__(self):self.events=[];self.application_dispatch_count=0;self.intents=0
    def journal(self,marker,value):self.events.append((marker,copy.deepcopy(value)))
    intent=m.Store.intent
    attempt=m.Store.attempt


def run_operation(monkeypatch,*,status='Completed.',mutate=None,validator=None):
    mapping,submission=packets(monkeypatch,status)
    if mutate:mutate(mapping,submission)
    store=FakeStore();calls=[];state={'store':store}
    monkeypatch.setattr(m,'RESULT_READ_DISPATCHED',False)
    monkeypatch.setattr(m,'RESULT_READ_RESPONSE_RECEIVED',False)
    monkeypatch.setattr(m,'SELECTED_RESULT_READ',False)
    class API:
        deadline=None;last_http_status=200;statuses=();responses=()
        def _exchange(self,endpoint,payload):
            store.intent(endpoint,payload.get('projectId'));store.attempt(endpoint,payload.get('projectId'))
            calls.append((endpoint,copy.deepcopy(payload)));return copy.deepcopy(mapping[endpoint])
    class Validator:
        @staticmethod
        def validate_statistics(statistics,*,candidate_record,evaluation_sessions):
            assert len(candidate_record['source_pairs'])==18 and evaluation_sessions==('synthetic-session',)
            assert set(statistics)==set(m.STATISTICS)
            return {'accepted':True,'run_valid':True,'synthetic_financial_validation':True}
    call=lambda:m.operate(submission,validator=validator or Validator,api=API(),secret={'QC_USER_ID':'1'},
        store=store,deadline=time.monotonic()+179,state=state)
    return call,calls,state,store,mapping


def test_only_current_completed_exact_job_earns_bounded_selected_aggregate_read(monkeypatch):
    call,calls,state,store,_=run_operation(monkeypatch)
    result=call()
    assert [endpoint for endpoint,_ in calls]==list(m.PAYLOAD_KEYS)
    assert len(calls)==6 and calls[3]==('files/read',{'projectId':m.PROJECT})
    assert calls[4][1]['includeStatistics'] is False
    assert result['result_read'] is result['selected_result_read'] is True
    assert m.RESULT_READ_DISPATCHED is m.RESULT_READ_RESPONSE_RECEIVED is m.SELECTED_RESULT_READ is True
    assert result['observed_status']=='Completed.' and result['source']['file_count']==18
    assert result['look_accounting']['shared_look_delta']==0
    assert all(result[key] is False for key in m.FLAGS)
    assert 'NEVER-RETAIN' not in m.canonical(result).decode()
    assert store.events[-1][0]=='selected-original-statistic-3'


@pytest.mark.parametrize('status,reason',[('Runtime Error','runtime_error'),('In Progress...','not_completed'),
    ('In Queue...','not_completed')])
def test_noncompleted_status_retained_without_result_or_error_log_read(monkeypatch,status,reason):
    call,calls,state,_,_=run_operation(monkeypatch,status=status)
    refused(reason,call)
    assert state['observed_status']==status and len(calls)==5
    assert all(endpoint!='backtests/read' for endpoint,_ in calls)
    assert m.RESULT_READ_DISPATCHED is m.SELECTED_RESULT_READ is False


@pytest.mark.parametrize('field,value',[('backtestId','OTHER'),('projectId',123),('compileId','OTHER'),
    ('name','OTHER'),('status','Completed'),('projectId',True)])
def test_status_identity_mismatch_never_reads_results(monkeypatch,field,value):
    def mutate(mapping,_):mapping['backtests/list']['backtests'][0][field]=value
    call,calls,*_=run_operation(monkeypatch,mutate=mutate)
    refused('status',call);assert len(calls)==5


def test_additional_project_job_is_not_silently_selected(monkeypatch):
    def mutate(mapping,_):mapping['backtests/list']['backtests'].append(identity());mapping['backtests/list']['count']=2
    call,calls,*_=run_operation(monkeypatch,mutate=mutate)
    refused('status',call);assert len(calls)==5


@pytest.mark.parametrize('fault',['content','name','duplicate','missing','other_project'])
def test_source_refusal_precedes_status_or_result(monkeypatch,fault):
    def mutate(mapping,_):
        rows=mapping['files/read']['files']
        if fault=='content':rows[0]['content']='# changed'
        elif fault=='name':rows[0]['name']='unknown.py'
        elif fault=='duplicate':rows[0]=copy.deepcopy(rows[1])
        elif fault=='missing':rows.pop()
        else:rows[0]['projectId']=123
    call,calls,*_=run_operation(monkeypatch,mutate=mutate)
    refused('source',call);assert len(calls)==4


@pytest.mark.parametrize('key,value',[('ownerId',True),('owner',False),('language','C#'),
    ('public',True),('libraries',[1]),('isLibrary',True),('lastLiveDeployment','active'),('liveMode',True)])
def test_project_access_refusal_is_read_only_and_precedes_source(monkeypatch,key,value):
    def mutate(mapping,_):mapping['projects/read']['projects'][0][key]=value
    call,calls,*_=run_operation(monkeypatch,mutate=mutate)
    refused('project',call);assert len(calls)==3


def test_known_own_A4_technical_shape_is_read_only_observation_not_new_lock(monkeypatch):
    def mutate(mapping,_):
        mapping['projects/read']['projects'][0]['collaborators'].append({'uid':None,'owner':False,
            'name':m.CODE_SOURCE,'publicId':'synthetic','permission':'write','liveControl':True,
            'profileImage':'','email':'','bio':''})
    call,calls,_,_,_=run_operation(monkeypatch,mutate=mutate)
    result=call();assert result['access']['general_count']==2
    assert result['access']['extra_rows_match_A4_name']==[True]
    assert result['access']['general_collaborators_authorize_mutation'] is False
    assert not any('lock' in endpoint or endpoint.endswith('create') for endpoint,_ in calls)


@pytest.mark.parametrize('fault',['Mia','uid','owner','permission','liveControl','unknown'])
def test_any_unbound_extra_collaborator_refuses_without_mutation(monkeypatch,fault):
    def mutate(mapping,_):
        extra={'uid':None,'owner':False,'name':m.CODE_SOURCE,'publicId':'synthetic',
            'permission':'write','liveControl':True,'profileImage':'','email':'','bio':''}
        if fault=='Mia':extra['name']='Mia'
        elif fault=='uid':extra['uid']=123
        elif fault=='owner':extra['owner']=True
        elif fault=='permission':extra['permission']='read'
        elif fault=='liveControl':extra['liveControl']=False
        else:extra['unknown']='SENSITIVE'
        mapping['projects/read']['projects'][0]['collaborators'].append(extra)
    call,calls,*_=run_operation(monkeypatch,mutate=mutate)
    refused('collaborators',call);assert len(calls)==3


@pytest.mark.parametrize('fault',['identity','unknown_ARV2','noncanonical','duplicate','long'])
def test_selected_result_refuses_bad_identity_or_statistic_without_retaining_raw_fields(monkeypatch,fault):
    def mutate(mapping,_):
        row=mapping['backtests/read']['backtest']
        if fault=='identity':row['backtestId']='OTHER'
        elif fault=='unknown_ARV2':row['statistics']['ARV2_UNAUTHORIZED']='{}'
        elif fault=='noncanonical':row['statistics'][m.STATISTICS[0]]='{ "x":1}'
        elif fault=='duplicate':row['statistics'][m.STATISTICS[0]]='{"x":1,"x":1}'
        else:row['statistics'][m.STATISTICS[0]]='x'*8193
    call,calls,_,_,_=run_operation(monkeypatch,mutate=mutate)
    with pytest.raises(m.Refused):call()
    assert len(calls)==6 and m.RESULT_READ_DISPATCHED is m.RESULT_READ_RESPONSE_RECEIVED is True
    assert m.SELECTED_RESULT_READ is False


def test_invalid_legacy_run_without_period_statistic_reaches_semantics(monkeypatch):
    class Validator:
        @staticmethod
        def validate_statistics(statistics,**kwargs):
            assert set(statistics)==set(m.STATISTICS[:3]);return {'accepted':False,'run_valid':False,'reason':'synthetic-invalid'}
    def mutate(mapping,_):del mapping['backtests/read']['backtest']['statistics'][m.STATISTICS[3]]
    call,_,state,*_=run_operation(monkeypatch,mutate=mutate,validator=Validator)
    refused('semantic',call)
    assert state['semantic_observation']=={'accepted':False,'run_valid':False,'reason':'synthetic-invalid'}
    assert m.SELECTED_RESULT_READ is True


def test_semantic_refusal_retains_original_strings_before_failure(monkeypatch):
    class Validator:
        @staticmethod
        def validate_statistics(*args,**kwargs):raise m.Refused('semantic')
    call,calls,state,store,_=run_operation(monkeypatch,validator=Validator)
    refused('semantic',call)
    assert m.SELECTED_RESULT_READ is True and state['statistics_pin']
    assert store.events[-1][0]=='selected-original-statistic-3'
    assert len(calls)==6


@pytest.mark.parametrize('endpoint',['files/create','files/update','projects/create','compile/create','backtests/create',
    'projects/nodes/read','object/properties','object/get','projects/collaboration/lock/acquire'])
def test_store_dispatch_rejects_any_mutating_capacity_or_storage_endpoint(endpoint):
    store=FakeStore();store.intent(endpoint,m.PROJECT)
    refused('request',lambda:store.attempt(endpoint,m.PROJECT))
    assert store.application_dispatch_count==0


@pytest.mark.parametrize('data_failure,close_failure',[(False,False),(True,False),(False,True)])
def test_new_claim_fresh_DATA_normal_return_credentials_and_final_close(monkeypatch,data_failure,close_failure):
    events=[]
    class Store(FakeStore):
        def __init__(self,*args):super().__init__()
        def __enter__(self):events.append('exclusive-store');return self
        def __exit__(self,*args):events.append('store-close')
        def write(self,name,value):events.append(name);return m.pin(b'fixture')
        def verify(self):events.append('store-verify')
    class Consumer:
        def __init__(self,**kwargs):assert kwargs['fact_bytes']==b'exact\n'
        def __enter__(self):events.append('DATA-enter');return NS(value='immutable')
        def __exit__(self,*args):
            events.append('DATA-normal-return')
            if data_failure:raise m.Refused('data')
    class Transport:
        @staticmethod
        def credentials(value):events.append('credentials');return value
        class API:
            def __init__(self,*args):events.append('API')
            def close(self):events.append('API-close')
    class Sources:
        def __init__(self,*args):
            self.security=None;self.transport=Transport;self.consumer=NS(FreshAllPlainSubmission=Consumer)
            self.validator=NS();self.preparation_fact_bytes=b'exact\n'
        def __enter__(self):return self
        def __exit__(self,*args):
            events.append('source-close')
            if close_failure:raise m.Refused('source_changed')
        def verify(self):events.append('source-verify')
    def injected(*args,**kwargs):events.append('operate');kwargs['state']['observed_status']='Completed.';return {'synthetic':True}
    monkeypatch.setattr(m,'preflight',lambda *args:{'synthetic':True})
    monkeypatch.setattr(m,'Sources',Sources);monkeypatch.setattr(m,'Store',Store);monkeypatch.setattr(m,'operate',injected)
    if data_failure or close_failure:
        refused('data' if data_failure else 'source_changed',lambda:m.run(NS(candidate='R343-AR100')))
    else:assert m.run(NS(candidate='R343-AR100'))['attempt_consumed'] is True
    assert events.index('claim.json')<events.index('DATA-enter')
    if data_failure:assert 'credentials' not in events and 'API' not in events
    else:assert events.index('DATA-normal-return')<events.index('credentials')<events.index('API')<events.index('operate')


def test_native_and_protocol_scope_is_new_read_only_control_plus_exact_eight_DATA():
    profile=m.profile_record('R343-AR100');native=m.native_profile('R343-AR100')
    assert str(m.control('R343-AR100')).endswith('/R348-20261107-AR100-RESULT-A')
    assert len(m.DATA_NAMES)==8 and 'claim.json' not in m.DATA_NAMES
    assert all(str(m.DATA_DIRECTORY/name) in native for name in m.DATA_NAMES)
    assert '/Volumes' in native and '/usr/bin/security' in native
    assert '/legacy_six_runs/' not in native and '/legacy_six_recovery_state/' not in native
    assert profile['maximum_application_requests']==6 and profile['seconds']==180
    assert profile['prior_attempts_consumed']==4 and not profile['old_controls_read']
    assert set(m.PAYLOAD_KEYS)=={'authenticate','projects/read','projects/collaboration/read','files/read','backtests/list','backtests/read'}
    assert m.PAYLOAD_KEYS['files/read']=={'projectId'}


def original_fixture(monkeypatch):
    binding={'schema':m.SCHEMA,'candidate_id':'R343-AR100','attempt':4,'expected_head':'1'*40,
        'caller_sha256':'2'*64,'plan_sha256':'3'*64,
        'profile_sha256':m.pin(m.canonical(m.profile_record('R343-AR100')))['sha256']}
    identity={'synthetic_identity':True};monkeypatch.setattr(m,'INPUT_IDENTITY_PIN',m.pin(m.canonical(identity)))
    statistics={name:'{}' for name in m.STATISTICS}
    semantic={'schema':'arv2-r348-legacy-six-result-validation-v1','candidate_id':'R343-AR100','ar_percent':100,
        'accepted':True,'run_valid':True,'invalid_reason':None,'account':{},'execution':{},'cash_and_tracking':{},
        'direct_stock_target_counts_by_sleeve':{},'diagnostic_summary':{},'periods':[],
        'statistics_pins':{name:m.pin(text.encode()) for name,text in statistics.items()},
        'source_profile_pin':dict(m.SOURCE_PROFILE_PIN),'source_vector_pin':dict(m.SOURCE_VECTOR_PIN),
        'evaluation_session_count':1451,'evaluation_sessions_sha256':'4'*64,'validation':'synthetic-validation',
        'subperiod_path_metrics_independently_recomputed':False,'preliminary':True,'backtest_only':True,
        'independent_historical_snapshot_authenticated':False,**m.FLAGS}
    access={'general_count':1,'dedicated_count':1,'general_rows_pin':dict(m.OWNER_ROWS_PIN),
        'dedicated_rows_pin':dict(m.OWNER_ROWS_PIN),'extra_row_pins':[],'extra_rows_match_A4_name':[],
        'editor_running':False,'private_field_present_and_false':False,'general_collaborators_authorize_mutation':False}
    result={'candidate_id':'R343-AR100','attempt':4,'project_id':m.PROJECT,'compile_id':m.COMPILE,
        'backtest_id':m.BACKTEST,'backtest_name':m.BACKTEST_NAME,'observed_status':'Completed.',
        'source':{'file_count':18,'source_byte_total':m.SOURCE_BYTE_TOTAL,'source_inventory_pin':dict(m.SOURCE_VECTOR_PIN)},
        'access':access,'statistics':statistics,'statistics_pin':m.pin(m.canonical(statistics)),
        'DATA_guard_returned':True,'input_source_identity':identity,'semantic_validation':semantic,
        'application_dispatch_count':6,'result_read':True,'selected_result_read':True,
        'look_accounting':{'shared_look_delta':0,'development_look_delta':0,'infrastructure_look_delta':0,
            'accepted_result_cell_delta':0,'physical_request_count_measured':False},
        'result_body_qualification':'bounded_full_response_parsed_ephemerally_only_selected_custom_statistics_retained',
        'last_api_diagnostic':None,**m.FLAGS}
    envelope={'schema':m.SCHEMA+'-result','binding':binding,'attempt_consumed':True,'result':result}
    envelope['report_pin']=m.pin(m.canonical(envelope))
    return binding,envelope


def rehash(envelope):
    envelope['report_pin']=m.pin(m.canonical({key:envelope[key] for key in ('schema','binding','attempt_consumed','result')}))
    return m.canonical(envelope)+b'\n'


def test_pure_original_stdout_accepts_only_actual0_and_self_consistent_known_result(monkeypatch):
    binding,value=original_fixture(monkeypatch)
    checked=m.validate_original_stdout(m.canonical(value)+b'\n',actual_exit=0,expected_binding=binding)
    assert checked['accepted_result'] is True and checked['original_output_validated'] is True
    assert checked['original_envelope']==value and checked['original_envelope'] is not value
    assert 'not_independent_disk_process_or_QC_attestation' in checked['qualification']


@pytest.mark.parametrize('exit_code',[2,True,None,1,-1])
def test_original_success_never_substitutes_unknown_or_nonzero_actual_exit(monkeypatch,exit_code):
    binding,value=original_fixture(monkeypatch)
    with pytest.raises(m.Refused):m.validate_original_stdout(m.canonical(value)+b'\n',actual_exit=exit_code,expected_binding=binding)


@pytest.mark.parametrize('field,value',[('observed_status','In Progress...'),('project_id',123),
    ('backtest_id','OTHER'),('compile_id','OTHER'),('result_read',False),('selected_result_read',False),
    ('DATA_guard_returned',False),('application_dispatch_count',True),('point_in_time_proven',True),
    ('paper_or_live_ready',True)])
def test_pure_output_rejects_changed_scope_or_false_truth_even_with_rehashed_report(monkeypatch,field,value):
    binding,envelope=original_fixture(monkeypatch);envelope['result'][field]=value
    with pytest.raises(m.Refused):m.validate_original_stdout(rehash(envelope),actual_exit=0,expected_binding=binding)


@pytest.mark.parametrize('field,value',[('accepted',False),('run_valid',False),('ar_percent',80),
    ('source_profile_pin',{'byte_count':1,'sha256':'a'*64}),('source_vector_pin',{'byte_count':1,'sha256':'a'*64}),
    ('evaluation_session_count',1450),('formal_forward_ready',True),('independent_historical_snapshot_authenticated',True)])
def test_pure_output_rejects_unaccepted_or_unbound_semantics(monkeypatch,field,value):
    binding,envelope=original_fixture(monkeypatch);envelope['result']['semantic_validation'][field]=value
    with pytest.raises(m.Refused):m.validate_original_stdout(rehash(envelope),actual_exit=0,expected_binding=binding)


def test_original_output_rejects_pin_mismatch_unknown_field_noncanonical_and_trailing(monkeypatch):
    binding,value=original_fixture(monkeypatch);raw=m.canonical(value)+b'\n'
    for damaged in (raw+b'\n',b' '+raw,raw[:-1],raw+b'{}'):
        with pytest.raises(m.Refused):m.validate_original_stdout(damaged,actual_exit=0,expected_binding=binding)
    value['report_pin']['sha256']='a'*64
    with pytest.raises(m.Refused):m.validate_original_stdout(m.canonical(value)+b'\n',actual_exit=0,expected_binding=binding)
    binding,value=original_fixture(monkeypatch);value['unknown']='SENSITIVE'
    with pytest.raises(m.Refused):m.validate_original_stdout(m.canonical(value)+b'\n',actual_exit=0,expected_binding=binding)


def test_finite_failure_original_is_preserved_unaccepted_without_invented_binding(monkeypatch):
    binding,_=original_fixture(monkeypatch)
    failure={'schema':m.SCHEMA+'-failure','stage':'status','claim_state':'consumed','failure_code':'runtime_error',
        'evidence':None,'result_read_dispatched':False,'result_read_response_received':False,'selected_result_read':False,**m.FLAGS}
    checked=m.validate_original_stdout(m.canonical(failure)+b'\n',actual_exit=2,expected_binding=binding)
    assert checked['accepted_result'] is False and checked['original_envelope']==failure
    assert 'binding' not in checked['original_envelope']
    with pytest.raises(m.Refused):m.validate_original_stdout(m.canonical(failure)+b'\n',actual_exit=0,expected_binding=binding)


def test_reader_plan_preserves176_ancestors_and_separately_lists34_additions():
    parent=json.loads(m.PARENT_PLAN.read_bytes());plan=json.loads(m.PLAN.read_bytes())
    assert m.pin(m.PARENT_PLAN.read_bytes())==m.PARENT_PLAN_PIN
    assert len(parent['source_pins'])==176 and len(plan['source_pins'])==210
    assert len(plan['additional_pins'])==34
    assert not set(plan['additional_pins'])&set(parent['source_pins'])
    assert plan['source_pins']=={**parent['source_pins'],**plan['additional_pins']}
    assert plan['running_fact_pin']==m.RUNNING_FACT_PIN
    assert plan['schema']==m.PLAN_SCHEMA and plan['attempt']==4 and plan['project_id']==m.PROJECT
