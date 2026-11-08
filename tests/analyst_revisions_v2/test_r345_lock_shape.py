"""Synthetic bounded redaction and exact A2 read-only scope checks."""
import copy
import os
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from scripts import observe_arv2_r345_lock_shape as m


def refused(code, action):
    with pytest.raises(m.Refused) as caught: action()
    assert caught.value.args == (code,)


def packets(monkeypatch):
    owner={'owner':True,'uid':123,'permission':'write','liveControl':True,
        'name':'PRIVATE OWNER','email':'PRIVATE-EMAIL','profileImage':'PRIVATE-URL','bio':'PRIVATE BIO'}
    extra={'owner':False,'uid':None,'permission':'write','liveControl':True,
        'name':m.CODE_SOURCE_ID,'publicId':m.CODE_SOURCE_ID,'codeSourceId':m.CODE_SOURCE_ID,
        'untrusted-key-must-never-appear':'PRIVATE UNKNOWN VALUE'}
    org='a'*32
    monkeypatch.setattr(m,'ORGANIZATION_SHA256',m.sha(org.encode()))
    monkeypatch.setattr(m,'OWNER_ROW_SHA256',m.sha(m.canonical(owner)+b'\n'))
    row={'projectId':m.PROJECT,'name':m.PROJECT_NAME,'language':'Py','owner':True,
        'ownerId':123,'organizationId':org,'public':False,'codeRunning':False,
        'collaborators':[owner,extra]}
    dedicated={'success':True,'collaborators':[owner],'userPermissions':'write','userLiveControl':True}
    return {'success':True,'projects':[row]},dedicated


def test_profile_exact_new_scope_no_mutation_or_acceptance():
    value=m.profile_record()
    assert value['project_id']==39054561
    assert value['endpoints']==['authenticate','projects/read','projects/collaboration/read','backtests/list']
    assert value['maximum_requests']==4 and value['seconds']==90
    assert value['native_policy_sha256']==m.sha(m.native_profile().encode())
    assert all(value[key] is False for key in m.FALSE_FLAGS)
    assert str(m.CONTROL).endswith('/legacy_six_lock_shape/R345-20261107-A')
    assert 'legacy_six_availability' not in str(m.CONTROL)


def test_native_policy_preserves_external_denials_and_own_control_only():
    policy=m.native_profile()
    for text in ('/Volumes','/Users/sheltonchen/Library/Keychains','/Library/Keychains',
            '/usr/bin/security','deny network-bind','deny network-inbound',
            'remote tcp "*:443"',str(m.CONTROL),str(m.SUPPORT)):
        assert text in policy
    assert 'file-write*' in policy and str(m.ROOT/'artifacts') in policy


def test_project_summary_retains_hashes_and_closed_shapes_without_remote_values(monkeypatch):
    project,dedicated=packets(monkeypatch)
    result=m.project_summary(project,dedicated,'123')
    assert result['general_row_count']==2 and result['expected_general_count_two'] is True
    assert result['dedicated_owner_only'] is True and result['dedicated_owner_pin_matches'] is True
    owner,extra=result['general_rows']
    assert owner['uid_equals_authenticated_owner'] is True
    assert extra['uid_equals_authenticated_owner'] is False
    assert extra['known_field_types']['uid']=='null'
    assert extra['unknown_key_count']==1
    assert all(extra['known_A2_code_source_matches'].values())
    assert owner['canonical_row_pin']==m.pin(m.canonical(project['projects'][0]['collaborators'][0]))
    raw=m.canonical(result).decode()
    for private in ('PRIVATE OWNER','PRIVATE-EMAIL','PRIVATE-URL','PRIVATE BIO',
            'PRIVATE UNKNOWN VALUE','untrusted-key-must-never-appear',m.CODE_SOURCE_ID):
        assert private not in raw
    assert 'privacy_proven' not in result  # Top-level run explicitly keeps all such flags false.


@pytest.mark.parametrize('value,expected',[(None,'null'),(123,'int'),('123','string'),
    (True,'bool'),(1.5,'float'),([], 'list'),({},'object')])
def test_uid_exact_type_and_equality_never_coerced(value,expected):
    result=m.general_row({'uid':value},'123')
    assert result['known_field_types']['uid']==expected
    assert result['uid_equals_authenticated_owner'] is (type(value) is int and value==123)


def test_absent_uid_is_distinct_from_explicit_null():
    assert m.general_row({},'123')['known_field_types']['uid']=='absent'
    assert m.general_row({'uid':None},'123')['known_field_types']['uid']=='null'


@pytest.mark.parametrize('value,expected', [(m.CODE_SOURCE_ID, True),
    (m.CODE_SOURCE_ID + 'OTHER', False), (None, False), (123, False)])
def test_technical_uid_can_match_only_the_exact_known_code_source(value, expected):
    result = m.general_row({'uid': value}, '123')
    assert result['uid_equals_known_A2_code_source'] is expected
    assert m.CODE_SOURCE_ID not in m.canonical(result).decode('ascii')


@pytest.mark.parametrize('field',['owner','liveControl'])
@pytest.mark.parametrize('value,expected',[(True,'true'),(False,'false'),(0,'other'),(1,'other'),(None,'other'),('true','other')])
def test_flags_are_exact_classes(field,value,expected):
    assert m.general_row({field:value},'123')[field+'_class']==expected


@pytest.mark.parametrize('value,expected',[('read','read'),('write','write'),('admin','other'),(True,'other'),(None,'other')])
def test_permission_class_never_returns_unrecognized_remote_strings(value,expected):
    assert m.general_row({'permission':value},'123')['permission_class']==expected


def test_absent_flags_and_permission_are_preserved():
    result=m.general_row({},'123')
    assert result['owner_class']==result['liveControl_class']==result['permission_class']=='absent'


@pytest.mark.parametrize('field',['name','publicId','codeSourceId'])
def test_only_exact_known_A2_code_source_matches(field):
    assert m.general_row({field:m.CODE_SOURCE_ID},'123')['known_A2_code_source_matches'][field] is True
    assert m.general_row({field:m.CODE_SOURCE_ID+'OTHER'},'123')['known_A2_code_source_matches'][field] is False
    assert m.general_row({field:None},'123')['known_A2_code_source_matches'][field] is False


@pytest.mark.parametrize('count',[0,1,3,8])
def test_general_shape_diagnosis_does_not_require_two_rows(monkeypatch,count):
    project,dedicated=packets(monkeypatch)
    project['projects'][0]['collaborators']=[{'uid':None,'name':'PRIVATE'} for _ in range(count)]
    result=m.project_summary(project,dedicated,'123')
    assert result['general_row_count']==count
    assert result['expected_general_count_two'] is False
    assert result['dedicated_owner_only'] is True


def test_more_than_eight_general_rows_refuse(monkeypatch):
    project,dedicated=packets(monkeypatch)
    project['projects'][0]['collaborators']=[{}]*9
    refused('collaborators',lambda:m.project_summary(project,dedicated,'123'))


@pytest.mark.parametrize('fault',['project','name','owner','org','public','uid','dedicated_count',
    'dedicated_uid','dedicated_permission','owner_pin','dedicated_scope'])
def test_scope_and_dedicated_owner_are_not_weakened(monkeypatch,fault):
    project,dedicated=packets(monkeypatch);row=project['projects'][0]
    if fault=='project':row['projectId']+=1
    elif fault=='name':row['name']='OTHER'
    elif fault=='owner':row['owner']=False
    elif fault=='org':row['organizationId']='b'*32
    elif fault=='public':row['public']=True
    elif fault=='uid':row['ownerId']=124
    elif fault=='dedicated_count':dedicated['collaborators']*=2
    elif fault=='dedicated_uid':dedicated['collaborators'][0]['uid']=124
    elif fault=='dedicated_permission':dedicated['userPermissions']='read'
    elif fault=='owner_pin':dedicated['collaborators'][0]['new-field']='CHANGED'
    else:dedicated['projectId']=m.PROJECT+1
    with pytest.raises(m.Refused):m.project_summary(project,dedicated,'123')


def test_history_empty_and_never_result_or_identifier_export():
    result=m.history_summary({'success':True,'projectId':m.PROJECT,'backtests':[],'count':0})
    assert result['current_job_count']==0 and result['empty_current_history'] is True
    assert result['include_statistics_requested'] is False
    assert all(count==0 for count in result['current_job_status_counts'].values())


@pytest.mark.parametrize('value',[{'success':True,'backtests':[{'status':'Completed.','backtestId':'PRIVATE'}]},
    {'success':True,'backtests':[],'count':True}, {'success':True,'backtests':[],'count':1},
    {'success':True,'projectId':True,'backtests':[]},{'success':True,'backtests':None}])
def test_any_existing_job_or_malformed_inventory_refuses(value):
    with pytest.raises(m.Refused):m.history_summary(value)


def bare_api():
    value=object.__new__(m.API);value.used=set();value.events=[]
    value._exchange=lambda endpoint,payload:value.events.append((endpoint,payload)) or {'success':True}
    return value


@pytest.mark.parametrize('endpoint,payload',[('projects/collaboration/lock/acquire',{'projectId':m.PROJECT}),
    ('files/read',{'projectId':m.PROJECT}),('files/update',{}),('compile/create',{'projectId':m.PROJECT}),
    ('projects/nodes/read',{'projectId':m.PROJECT}),('backtests/create',{}),
    ('backtests/list',{'projectId':m.PROJECT,'includeStatistics':True}),
    ('backtests/list',{'projectId':m.PROJECT,'includeStatistics':0}),
    ('backtests/list',{'projectId':m.PROJECT}),('projects/read',{'projectId':m.PROJECT+1})])
def test_transport_public_scope_is_four_readonly_exact_requests(endpoint,payload):
    api=bare_api();refused('endpoint',lambda:api.request(endpoint,payload));assert not api.events


def test_four_requests_each_once_and_no_duplicate_retry():
    api=bare_api()
    for endpoint,payload in [('authenticate',{}),('projects/read',{'projectId':m.PROJECT}),
        ('projects/collaboration/read',{'projectId':m.PROJECT}),
        ('backtests/list',{'projectId':m.PROJECT,'includeStatistics':False})]:
        api.request(endpoint,payload)
        refused('endpoint',lambda:api.request(endpoint,payload))
    assert len(api.events)==4


def test_observe_fetches_dedicated_after_general_unknown_shape_before_evaluation(monkeypatch):
    project,dedicated=packets(monkeypatch)
    project['projects'][0]['collaborators'][1]={'uid':None,'owner':False,'name':'UNRECOGNIZED_LOCK'}
    responses=[{'success':True},project,dedicated,{'success':True,'backtests':[]}]
    events=[]
    def request(endpoint,payload):events.append((endpoint,payload));return responses.pop(0)
    result=m.observe(NS(request=request),'123')
    assert [endpoint for endpoint,_ in events]==list(m.ENDPOINTS)
    assert result['general_rows'][1]['known_A2_code_source_matches']['name'] is False
    assert result['dedicated_owner_only'] is True and result['empty_current_history'] is True
    assert events[-1][1]['includeStatistics'] is False


def test_failed_authentication_stops_other_reads():
    events=[]
    def request(endpoint,payload):events.append(endpoint);return {'success':False}
    refused('authentication',lambda:m.observe(NS(request=request),'123'))
    assert events==['authenticate']


@pytest.mark.parametrize('raw',[b'',b'{"x":1,"x":2}',b'{"x":NaN}',b'\xff'])
def test_response_parse_is_strict_bounded_finite(raw):
    with pytest.raises(m.Refused):m.parse(raw)


class Security:
    class Refusal(Exception):pass
    @staticmethod
    def snapshot(_):return {'synthetic':True}


def test_new_control_claim_is_exclusive_fsynced_and_retained(tmp_path,monkeypatch):
    root=tmp_path/'root';root.mkdir(mode=0o755)
    artifact=root/'artifacts';artifact.mkdir(mode=0o700)
    control=artifact/'lock-shape'/'ONE'
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'CONTROL',control)
    with m.Store(Security) as store:
        assert store.write('claim.json',{'claim':True})==m.pin(b'{"claim":true}')
        store.intent('authenticate',None);store.attempt('authenticate',None)
        store.verify()
    assert sorted(p.name for p in control.iterdir())==['claim.json','dispatch-0.json','intent-0.json']
    refused('claim_spent',lambda:m.Store(Security).__enter__())


def test_failed_claim_prevents_credentials_and_contact(monkeypatch):
    events=[]
    class Held:
        raw=b''
        def __enter__(self):return self
        def __exit__(self,*_):pass
    class Control:
        def __init__(self,*_):pass
        def __enter__(self):events.append('allocation');return self
        def __exit__(self,*_):pass
        def write(self,name,value):events.append(name);raise m.Refused('control')
    monkeypatch.setattr(m,'preflight',lambda *a:{})
    monkeypatch.setattr(m,'HeldPublic',lambda *a:Held())
    monkeypatch.setattr(m,'Store',Control)
    monkeypatch.setattr(m,'credentials',lambda *a:pytest.fail('credential before claim'))
    monkeypatch.setattr(m,'API',lambda *a:pytest.fail('contact before claim'))
    refused('control',lambda:m.run(NS(caller_sha256='b'*64)))
    assert events==['allocation','claim.json']


def test_opaque_error_or_response_strings_are_never_formatted():
    class Hostile(Exception):
        def __str__(self):raise AssertionError('unsafe formatting')
    assert m.finite(Hostile())=='unknown'
    assert m.finite(m.Refused('http_status'))=='http_status'
    assert m.finite(m.Refused('PRIVATE RESPONSE'))=='unknown'
