"""Synthetic owner-read reconciliation, redaction and five-request scope."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from scripts import observe_arv2_r347_plain_recovery as m


def refused(code, action):
    with pytest.raises(m.Refused) as caught: action()
    assert caught.value.args == (code,)


def packets(monkeypatch):
    owner={'owner':True,'uid':123,'permission':'write','liveControl':True,
        'name':'PRIVATE OWNER','email':'PRIVATE EMAIL','profileImage':'PRIVATE URL'}
    technical={'owner':False,'uid':m.CODE_SOURCE_ID,'name':m.CODE_SOURCE_ID,
        'permission':'write','liveControl':True,'publicId':'PRIVATE-TECH-ID'}
    mia={'owner':False,'uid':'PRIVATE MIA UID','name':'Mia','permission':'write',
        'liveControl':True,'email':'PRIVATE MIA EMAIL','secret-key-field':'PRIVATE EXTRA'}
    org='a'*32
    monkeypatch.setattr(m,'ORGANIZATION_SHA256',m.sha(org.encode()))
    monkeypatch.setattr(m,'OWNER_ROW_SHA256',m.sha(m.canonical(owner)+b'\n'))
    project={'success':True,'projects':[{'projectId':m.PROJECT,'name':m.PROJECT_NAME,
        'language':'Py','organizationId':org,'owner':True,'ownerId':123,
        'codeRunning':False,'collaborators':[owner,technical,mia]}]}
    dedicated={'success':True,'collaborators':[owner,mia], 'userPermissions':'write','userLiveControl':True}
    return project,dedicated


def files(monkeypatch, input_content='#'):
    payloads={name:'synthetic-source-'+str(index)+'\n' for index,name in enumerate(m.UPLOADED_NAMES)}
    pins=dict(m.B_SOURCE_PINS)
    for name,text in payloads.items():pins[name]=m.pin(text.encode('ascii'))
    monkeypatch.setattr(m,'B_SOURCE_PINS',pins)
    payloads['main.py']=m.DEFAULT_MAIN
    if input_content is not None:payloads[m.INPUT_NAME]=input_content
    return {'success':True,'files':[{'projectId':m.PROJECT,'name':name,'content':text}
        for name,text in payloads.items()]}


def test_profile_exact_scope_and_no_candidate_write_authority():
    value=m.profile_record()
    assert value['project_id']==39054561
    assert value['endpoints']==['authenticate','projects/read','projects/collaboration/read','backtests/list','files/read']
    assert value['maximum_requests']==5 and value['seconds']==90
    assert value['native_policy_sha256']==m.sha(m.native_profile().encode())
    assert all(value[key] is False for key in m.FALSE_FLAGS)
    assert str(m.CONTROL).endswith('/legacy_six_recovery_state/R347-20261107-A')
    assert value['B_source_pins']==m.B_SOURCE_PINS


def test_native_policy_denies_private_resources_and_unrelated_artifacts():
    value=m.native_profile()
    for text in ('/Volumes','/Users/sheltonchen/Library/Keychains','/Library/Keychains',
        '/usr/bin/security','deny network-bind','deny network-inbound','remote tcp "*:443"',
        str(m.CONTROL),str(m.SUPPORT),str(m.ROOT/'artifacts')):assert text in value


def test_owner_read_diagnoses_A2_and_Mia_without_granting_extra_writer_access(monkeypatch):
    project,dedicated=packets(monkeypatch)
    result=m.project_summary(project,dedicated,'123')
    assert result['general_row_count']==3 and result['dedicated_row_count']==2
    assert result['dedicated_owner_only'] is False
    assert result['semantic_owner_agreement'] is result['whole_owner_row_agreement'] is True
    assert result['general_rows_pin']==m.pin(m.canonical(project['projects'][0]['collaborators']))
    assert result['dedicated_rows_pin']==m.pin(m.canonical(dedicated['collaborators']))
    assert result['general_rows'][1]['uid_equals_known_A2_code_source'] is True
    assert result['general_rows'][2]['known_Mia_matches']['name'] is True
    assert result['unreviewed_observation'] is True
    output=m.canonical(result).decode()
    for forbidden in ('PRIVATE OWNER','PRIVATE EMAIL','PRIVATE URL','PRIVATE MIA UID',
        'PRIVATE MIA EMAIL','PRIVATE EXTRA','secret-key-field',m.CODE_SOURCE_ID,'PRIVATE-TECH-ID'):
        assert forbidden not in output


def test_read_permissions_do_not_require_edit_or_live_permission(monkeypatch):
    project,dedicated=packets(monkeypatch)
    dedicated['collaborators'][0]['permission']='read'
    dedicated['collaborators'][0]['liveControl']=False
    dedicated['userPermissions']='read';dedicated['userLiveControl']=False
    result=m.project_summary(project,dedicated,'123')
    assert result['requester_permission_class']=='read'
    assert result['dedicated_owner_pin_matches'] is False
    assert result['whole_owner_row_agreement'] is True  # Fixture shares its original owner object.


def test_owner_read_can_record_general_disagreement_without_inventing_agreement(monkeypatch):
    project,dedicated=packets(monkeypatch)
    project['projects'][0]['collaborators']=copy.deepcopy(project['projects'][0]['collaborators'])
    project['projects'][0]['collaborators'][0]['uid']=321
    result=m.project_summary(project,dedicated,'123')
    assert result['semantic_owner_agreement'] is False
    assert result['whole_owner_row_agreement'] is False


@pytest.mark.parametrize('value,kind',[(None,'null'),('123','string'),(123,'int'),(True,'bool')])
def test_uid_types_are_not_coerced(value,kind):
    result=m.general_row({'uid':value},'123')
    assert result['known_field_types']['uid']==kind
    assert result['uid_equals_authenticated_owner'] is (type(value) is int and value==123)
    assert m.general_row({},'123')['known_field_types']['uid']=='absent'


@pytest.mark.parametrize('fault',['project','name','org','owner','owner_uid','dedicated_owner_uid',
    'two_dedicated_owners','no_dedicated_owner','no_read_permission','dedicated_scope'])
def test_fixed_owner_read_scope_still_refuses_contradictions(monkeypatch,fault):
    project,dedicated=packets(monkeypatch);row=project['projects'][0]
    if fault=='project':row['projectId']+=1
    elif fault=='name':row['name']='OTHER LANE'
    elif fault=='org':row['organizationId']='b'*32
    elif fault=='owner':row['owner']=False
    elif fault=='owner_uid':row['ownerId']=True
    elif fault=='dedicated_owner_uid':dedicated['collaborators'][0]['uid']=321
    elif fault=='two_dedicated_owners':dedicated['collaborators'][1]['owner']=True
    elif fault=='no_dedicated_owner':dedicated['collaborators'][0]['owner']=False
    elif fault=='no_read_permission':dedicated['userPermissions']='none'
    else:dedicated['projectId']=m.PROJECT+1
    with pytest.raises(m.Refused):m.project_summary(project,dedicated,'123')


def test_current_source_vector_is_hash_only_and_not_source_acceptance(monkeypatch):
    packet=files(monkeypatch)
    result=m.files_summary(packet)
    assert result['source_file_count']==5 and result['unrecognized_file_count']==0
    assert result['three_prior_B_sources_match'] is True
    assert result['main_classification']=='known_default_main'
    assert result['input_runtime_classification']=='known_one_byte_stub'
    assert result['source_inventory_pin']==m.pin(m.canonical(result['source_inventory']))
    assert result['raw_code_retained'] is result['codeSourceId_supplied'] is False
    assert 'synthetic-source' not in m.canonical(result).decode()
    assert 'BasicTemplateAlgorithm' not in m.canonical(result).decode()
    assert [row['project_path'] for row in result['source_inventory']]==sorted(row['name'] for row in packet['files'])


@pytest.mark.parametrize('content,expected',[(None,'absent'),('#','known_one_byte_stub'),
    ('#\n','other_source'),('different but readable\n','other_source')])
def test_input_runtime_effect_is_observed_not_assumed(monkeypatch,content,expected):
    result=m.files_summary(files(monkeypatch,content))
    assert result['input_runtime_classification']==expected


def test_input_exact_oldB_and_nonmatching_main_can_be_diagnosed(monkeypatch):
    packet=files(monkeypatch,'synthetic old runtime')
    selected=dict(m.B_SOURCE_PINS);selected[m.INPUT_NAME]=m.pin(b'synthetic old runtime')
    monkeypatch.setattr(m,'B_SOURCE_PINS',selected)
    next(row for row in packet['files'] if row['name']=='main.py')['content']='MODIFIED MAIN'
    result=m.files_summary(packet)
    assert result['input_runtime_classification']=='B_source_exact'
    assert result['main_classification']=='other_source'


def test_unknown_file_name_and_content_are_hash_only(monkeypatch):
    packet=files(monkeypatch)
    packet['files'].append({'projectId':m.PROJECT,'name':'PRIVATE-UNKNOWN-NAME.txt','content':'PRIVATE UNKNOWN CONTENT'})
    result=m.files_summary(packet)
    assert result['unrecognized_file_count']==1
    assert result['unrecognized_files']==[{'name_sha256':m.sha(b'PRIVATE-UNKNOWN-NAME.txt'),**m.pin(b'PRIVATE UNKNOWN CONTENT')}]
    assert 'PRIVATE' not in m.canonical(result).decode()


@pytest.mark.parametrize('fault',['duplicate','project','count_bool','name_type','content_type','bound'])
def test_file_inventory_is_bounded_scoped_and_unambiguous(monkeypatch,fault):
    packet=files(monkeypatch)
    if fault=='duplicate':packet['files'].append(packet['files'][0])
    elif fault=='project':packet['files'][0]['projectId']=m.PROJECT+1
    elif fault=='count_bool':packet['count']=True
    elif fault=='name_type':packet['files'][0]['name']=False
    elif fault=='content_type':packet['files'][0]['content']=None
    else:packet['files'][0]['content']='x'*(128*1024+1)
    with pytest.raises(m.Refused):m.files_summary(packet)


def test_history_requires_no_jobs_and_requests_no_statistics():
    result=m.history_summary({'success':True,'backtests':[],'count':0})
    assert result['empty_current_history'] is True and result['current_job_count']==0
    refused('history',lambda:m.history_summary({'success':True,'backtests':[{'status':'Completed.','name':'PRIVATE'}]}))


def bare_api():
    api=object.__new__(m.API);api.used=set();api.events=[]
    api._exchange=lambda endpoint,payload:api.events.append((endpoint,payload)) or {'success':True}
    return api


@pytest.mark.parametrize('endpoint,payload',[('files/create',{}),('files/update',{}),
    ('projects/collaboration/lock/acquire',{'projectId':m.PROJECT}),('projects/nodes/read',{'projectId':m.PROJECT}),
    ('compile/create',{'projectId':m.PROJECT}),('backtests/read',{'projectId':m.PROJECT}),
    ('object/properties',{}),('files/read',{'projectId':m.PROJECT,'codeSourceId':m.CODE_SOURCE_ID}),
    ('files/read',{'projectId':m.PROJECT+1}),('backtests/list',{'projectId':m.PROJECT,'includeStatistics':True})])
def test_public_transport_has_only_five_readonly_exact_payloads(endpoint,payload):
    api=bare_api();refused('endpoint',lambda:api.request(endpoint,payload));assert not api.events


def test_exact_five_requests_are_once_only_no_implicit_retry():
    api=bare_api()
    for endpoint in m.ENDPOINTS:
        payload={} if endpoint=='authenticate' else {'projectId':m.PROJECT}
        if endpoint=='backtests/list':payload['includeStatistics']=False
        api.request(endpoint,payload)
        refused('endpoint',lambda:api.request(endpoint,payload))
    assert len(api.events)==5


def test_observe_uses_five_reads_and_does_not_promote_current_source_matches(monkeypatch):
    project,dedicated=packets(monkeypatch)
    responses=[{'success':True},project,dedicated,{'success':True,'backtests':[]},files(monkeypatch,None)]
    events=[]
    def request(endpoint,payload):events.append((endpoint,payload));return responses.pop(0)
    result=m.observe(NS(request=request),'123')
    assert [endpoint for endpoint,_ in events]==list(m.ENDPOINTS)
    assert result['input_runtime_classification']=='absent'
    assert result['unreviewed_observation'] is True
    assert events[-1][1]=={'projectId':m.PROJECT}


def test_unknown_files_refuse_after_safe_diagnostic_is_retained(monkeypatch):
    project,dedicated=packets(monkeypatch)
    source=files(monkeypatch);source['files'].append({'name':'PRIVATE-NAME','content':'PRIVATE CONTENT'})
    responses=iter([{'success':True},project,dedicated,{'success':True,'backtests':[]},source])
    refused('files',lambda:m.observe(NS(request=lambda *_:next(responses)),'123'))
    assert m.SAFE_OBSERVATION['unrecognized_file_count']==1
    assert 'PRIVATE' not in m.canonical(m.SAFE_OBSERVATION).decode()


class Security:
    class Refusal(Exception):pass
    @staticmethod
    def snapshot(_):return {'synthetic':True}


def test_five_request_intent_files_fit_exclusive_control_without_cleanup(tmp_path,monkeypatch):
    root=tmp_path/'root';root.mkdir(mode=0o755)
    artifacts=root/'artifacts';artifacts.mkdir(mode=0o700)
    control=artifacts/'reconciliation'/'ONE'
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'CONTROL',control)
    with m.Store(Security) as store:
        store.write('claim.json',{'claim':True})
        for endpoint in m.ENDPOINTS:store.intent(endpoint,m.PROJECT);store.attempt(endpoint,m.PROJECT)
        assert store.intents==store.application_dispatch_count==5
        refused('bound',lambda:store.intent('files/read',m.PROJECT))
        store.verify()
    assert len(tuple(control.iterdir()))==11
    refused('claim_spent',lambda:m.Store(Security).__enter__())


def test_failed_claim_prevents_credential_inspection_and_contact(monkeypatch):
    class Held:
        raw=b''
        def __enter__(self):return self
        def __exit__(self,*_):pass
    class Control:
        def __init__(self,*_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def write(self,*_):raise m.Refused('control')
    monkeypatch.setattr(m,'preflight',lambda *a:{})
    monkeypatch.setattr(m,'HeldPublic',lambda *a:Held())
    monkeypatch.setattr(m,'Store',Control)
    monkeypatch.setattr(m,'credentials',lambda *_:pytest.fail('credentials before claim'))
    monkeypatch.setattr(m,'API',lambda *_:pytest.fail('API before claim'))
    refused('control',lambda:m.run(NS(caller_sha256='a'*64)))


def test_secret_exception_text_is_not_formatted():
    class Hostile(Exception):
        def __str__(self):raise AssertionError('do not format')
    assert m.finite(Hostile())=='unknown'
    assert m.finite(m.Refused('PRIVATE RAW ERROR'))=='unknown'


def output(monkeypatch):
    project,dedicated=packets(monkeypatch)
    source=files(monkeypatch,None)
    responses=iter([{'success':True},project,dedicated,{'success':True,'backtests':[]},source])
    observation=m.observe(NS(request=lambda *_:next(responses)),'123')
    args=NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)
    result={**m.binding(args),'complete':True,'attempt_consumed':True,
        'request_intent_count':5,'application_dispatch_count':5,
        'physical_request_count_measured':False,
        'http_statuses':[{'endpoint':name,'http_status':200} for name in m.ENDPOINTS],
        'response_pins':[], **observation, **m.FALSE_FLAGS}
    return args,result


def envelope(result):
    return m.canonical({'result':result,'report':m.pin(m.canonical(result))})+b'\n\n'


def test_original_stdout_actual_exit_and_report_pin_validate_without_artifact_read(monkeypatch):
    args,result=output(monkeypatch)
    value=m.validate_output(envelope(result),0,args)
    assert value['output_envelope_validated'] is True and value['actual_exit']==0
    assert value['observation']['input_runtime_classification']=='absent'
    assert value['observation']['candidate_write_gates_passed'] is False
    assert 'not_independent' in value['qualification']


@pytest.mark.parametrize('actual',[None,True,False,2,-1,'0'])
def test_report_without_actual_zero_exit_never_accepts(monkeypatch,actual):
    args,result=output(monkeypatch)
    refused('output',lambda:m.validate_output(envelope(result),actual,args))


@pytest.mark.parametrize('fault',['report_pin','missing_double_LF','trailing','unknown_key',
    'write_authority','counter_bool','source_inventory_pin','binding','status'])
def test_output_validation_guards_are_load_bearing(monkeypatch,fault):
    args,result=output(monkeypatch)
    if fault=='unknown_key':result['raw_source']='PRIVATE'
    elif fault=='write_authority':result['candidate_write_gates_passed']=True
    elif fault=='counter_bool':result['request_intent_count']=True
    elif fault=='source_inventory_pin':result['source_inventory_pin']['sha256']='d'*64
    elif fault=='binding':result['caller_sha256']='d'*64
    elif fault=='status':result['http_statuses'][-1]['http_status']=403
    raw=envelope(result)
    if fault=='report_pin':
        value=json.loads(raw);value['report']['sha256']='d'*64;raw=m.canonical(value)+b'\n\n'
    elif fault=='missing_double_LF':raw=raw[:-1]
    elif fault=='trailing':raw+=b'PRIVATE'
    with pytest.raises(m.Refused):m.validate_output(raw,0,args)


def test_literal_B_source_pins_match_public_ancestry_plan():
    root=Path(__file__).resolve().parents[2]
    plan=json.loads((root/'scripts/arv2_r345_legacy_six_plan_v3.json').read_bytes())
    cell=plan['source_summary']['cells'][1]
    assert cell['candidate_id']=='R343-AR100'
    assert m.B_SOURCE_PINS=={row['project_path']:{key:row[key] for key in ('byte_count','sha256')}
        for row in cell['sources']}


def test_unknown_unicode_file_name_and_content_remain_hash_only(monkeypatch):
    packet=files(monkeypatch)
    packet['files'].append({'name':'PRIVATE\u00e9.py','content':'PRIVATE\u00e9'})
    result=m.files_summary(packet)
    assert result['unrecognized_file_count']==1
    assert result['unrecognized_files'][0]['name_sha256']==m.sha('PRIVATE\u00e9.py'.encode('utf-8'))
    assert 'PRIVATE' not in m.canonical(result).decode()
