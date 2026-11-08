"""AF synthetic only: no original DATA, credential lookup, QC or provider contact."""
import copy
import hashlib
import inspect
import io
import json
import os
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import observe_arv2_r298_native_qc_rights as m
from scripts import arv2_r298_aa_source_binding as aa

ARGS=NS(operation='run',expected_head='a'*40,caller_sha256='b'*64)
ORG='0123456789abcdef0123456789abcdef'
UID='42'


def refused(code,callback):
    with pytest.raises(m.Refused) as caught:callback()
    assert m.finite(caught.value)==code


def actual(raw=b'',*,exit=0,bound=None):
    return {'actual_exit':exit,'bound':bound,'spawn_observed':True,
        'dispatched_at':'2026-10-27T10:00:00.000000Z','completion_observed_at':'2026-10-27T10:00:01.000000Z',
        'stdout_bytes':len(raw),'stdout_sha256':m.sha(raw),'stderr_bytes':0,'stderr_sha256':m.sha(b'')}


def input_result():
    return {'schema':m.SCHEMA+'-input','input_binding':aa.expected_summary()['input_binding'],
        'specification_sha256':m.SPEC_SHA256,
        'selected_whole_binding_sha256s':m.source_binding()['selected_whole_binding_sha256s'],
        'full_binding_count':6151,'selected_exact_unique_count':5,
        'same_process_genuine_plain_capability_checked':True,'all_five_transport_role_byte_inventories_checked':True,
        'input_unchanged_checks_complete':True,'old_controls_or_TICKERS_read':False}


def source_packet():
    value={'binding':m.binding(ARGS),'role':'source','result':input_result()}
    return value,actual(m.canonical(value))


def project_response():
    return {'success':True,'projects':[{'projectId':m.REFERENCE_PROJECT,'name':m.REFERENCE_NAME,
        'language':'Py','owner':True,'ownerId':int(UID),'organizationId':ORG,'codeRunning':True,
        'sharingTokenBacktest':'PRIVATE-SHARING-TOKEN',
        'collaborators':[{'uid':int(UID),'owner':True,'permission':'write','liveControl':True,
            'name':'PRIVATE-OWNER','email':'PRIVATE-EMAIL'}]}]}


def org_response():
    return {'success':True,'organization':{'id':ORG,'name':'PRIVATE-COMPANY','type':'Quant Researcher',
        'seats':1,'credit':{'card':'PRIVATE-CARD'},'data':{'current':True,'signedTime':123456},
        'products':[{'name':'PRIVATE-PRODUCT-GROUP','items':[{'productId':8675309,'name':'PRIVATE-PRODUCT',
            'quantity':1,'unitPrice':99.9,'total':99.9}]}],
        'members':[{'id':int(UID),'name':'PRIVATE-MEMBER','email':'PRIVATE-EMAIL','isAdmin':True}]}}


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    def denied(*args,**kwargs):raise AssertionError('old CLI, private I/O, credential or QC capability called')
    for obj,name in ((m.previous,'run'),(m.previous,'main'),(m.worker,'prepare'),
        (m.worker.previous,'prepare'),(m.submission,'_client')):
        monkeypatch.setattr(obj,name,denied)


@pytest.fixture
def scope(monkeypatch):
    monkeypatch.setattr(m,'ORGANIZATION_SHA256',m.sha(ORG.encode()))
    monkeypatch.setattr(m,'OWNER_ROW_SHA256',m.sha(m.canonical(project_response()['projects'][0]['collaborators'][0])))
    return NS(project=project_response(),organization=org_response())


@pytest.fixture
def broker(scope,monkeypatch):
    state=NS(events=[],files={},stores=0,role_fault=None)
    class Directory:
        def __init__(self):
            state.stores+=1;m.require(state.stores==1,'claim_spent')
            self.fd=90;self.held={}
        def __enter__(self):return self
        def __exit__(self,*args):state.events.append('close')
        def verify(self):state.events.append('verify')
        def write(self,name,value):
            m.require(name not in state.files,'control_name')
            state.events.append('write:'+name);raw=m.canonical(value);state.files[name]=raw
            self.held[name]=(91+len(state.files),None)
            return {'byte_count':len(raw),'sha256':m.sha(raw)}
    monkeypatch.setattr(m,'Store',Directory)
    monkeypatch.setattr(m,'preflight',lambda *args:state.events.append('postflight'))
    monkeypatch.setattr(m.environment,'_require_logging',lambda:state.events.append('logging_check'))
    def handoff(environ):
        assert 'source-observed.json' in state.files
        assert state.events.index('write:claim.json')<state.events.index('source_actual0')
        state.events.append('credential_handoff')
        return {'QC_USER_ID':'42','QC_API_TOKEN':'SYNTHETIC-SECRET'}
    monkeypatch.setattr(m.capture_support,'_credential_handoff',handoff)
    def capture(command,safe,timeout,**kwargs):
        role=command[command.index('--role')+1]
        state.events.append('capture:'+role)
        assert command[:2]==['/usr/bin/sandbox-exec','-p']
        assert str(m.SOURCE) in command and kwargs['pass_fds'][0]==90
        assert role+'-intent.json' in state.files
        if role=='source':
            assert 'QC_USER_ID' not in safe and 'QC_API_TOKEN' not in safe
            assert '(deny network*)' in command[2] and str(m.worker.previous.PACKAGE) in command[2]
            assert kwargs['input_bytes']==b''
            value={'binding':m.binding(ARGS),'role':role,'result':input_result()}
            state.events.append('source_actual0')
        else:
            assert safe['QC_API_TOKEN']=='SYNTHETIC-SECRET'
            assert str(m.worker.previous.PACKAGE) not in command[2]
            assert 'credential_handoff' in state.events
            packet=m.parse(kwargs['input_bytes']);m._input_packet(packet)
            if role=='authenticate':
                observation,org={'authenticated':True},None
            elif role=='project':observation,org=m._project(scope.project,UID)
            else:
                assert packet['organization_id']==ORG
                observation,org=m._org(scope.organization,ORG,UID),None
            value={'binding':m.binding(ARGS),'role':role,'result':observation,'organization_id':org,
                'state':{'binding':m.binding(ARGS),'request_dispatch_intent':True,'http_status':200,
                    'complete_body_pin':{'byte_count':100,'sha256':'d'*64}}}
        if state.role_fault==role:
            value={'binding':m.binding(ARGS),'role':role,'failure_code':'input' if role=='source' else 'transport_tls'}
            if role!='source':value['state']={'binding':m.binding(ARGS),'request_dispatch_intent':True,
                'http_status':None,'complete_body_pin':None}
        raw=m.canonical(value);return raw,b'',actual(raw,exit=2 if state.role_fault==role else 0)
    monkeypatch.setattr(m,'capture',capture)
    return state


def test_claim_source_actual_zero_then_credentials_and_exact_three_read_only_calls(broker):
    outcome=m.run(ARGS,time.monotonic()+60);result=outcome['result']
    assert [row['role'] for row in result['children']]==['source',*m.ROLES]
    assert result['source_actual']['actual_exit']==0
    assert broker.events.index('source_actual0')<broker.events.index('credential_handoff')
    assert [event for event in broker.events if event.startswith('capture:')]==[
        'capture:source','capture:authenticate','capture:project','capture:organization']
    for role in ('source',*m.ROLES):
        assert broker.events.index('write:'+role+'-intent.json')<broker.events.index('capture:'+role)
    assert result['observations'][-1]['result']['recognized_type']=='Quant Researcher'
    assert result['observations'][-1]['result']['Storage_Create_status']=='unknown_not_in_validated_SDK_model'
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    encoded=m.canonical(outcome)
    for text in (ORG,'PRIVATE-','SYNTHETIC-SECRET','8675309'):assert text.encode() not in encoded
    envelope={'binding':m.binding(ARGS),'outcome':outcome}
    assert m.validate_output(m.canonical(envelope),0,ARGS)==envelope
    refused('claim_spent',lambda:m.run(ARGS,time.monotonic()+60))


@pytest.mark.parametrize('role',('source',*m.ROLES))
def test_finite_child_failure_spends_and_never_dispatches_next_role(broker,role):
    broker.role_fault=role
    outcome=m.run(ARGS,time.monotonic()+60);failed=outcome['failure']
    assert failed['claim_consumed'] is True and failed['provider_request_count'] is None
    assert failed['failure_code']==('input' if role=='source' else 'transport_tls')
    if role=='source':assert 'credential_handoff' not in broker.events
    index=('source',*m.ROLES).index(role)
    assert [child['role'] for child in failed['state']['children']]==list(('source',*m.ROLES)[:index+1])
    assert m.validate_output(m.canonical({'binding':m.binding(ARGS),'outcome':outcome}),2,ARGS)['outcome']==outcome


def test_genuine_full_catalog_checks_all6151_and_five_unique_whole_hashes_before_return(monkeypatch):
    rows=[{'synthetic_binding':index} for index in range(6151)]
    hashes=sorted(m.previous.diagnostic.digest(row) for row in rows[:5])
    spec=m.previous.diagnostic.make_specification(hashes)
    monkeypatch.setattr(m,'source_binding',lambda:copy.deepcopy(spec))
    plain=object();initial=object();record=object();selected=object();calls=[]
    monkeypatch.setattr(m.worker,'_load_plain',lambda deadline:(calls.append('load') or plain))
    monkeypatch.setattr(m.worker,'_catalog',lambda value,deadline:
        (initial,record,selected,copy.deepcopy(rows),aa.expected_summary()['input_binding']))
    def unchanged(*args):
        assert args[:4]==(plain,initial,record,selected);calls.append('unchanged')
    monkeypatch.setattr(m.worker,'_catalog_unchanged',unchanged)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:calls.append('safe'))
    result=m.source_observation(time.monotonic()+30)
    assert result['selected_whole_binding_sha256s']==hashes and result['full_binding_count']==6151
    assert result['old_controls_or_TICKERS_read'] is False and calls==['safe','load','unchanged','safe']


@pytest.mark.parametrize('fault',('count','selected_missing','duplicate_selected','changed_after'))
def test_partial_ambiguous_or_changed_genuine_catalog_cannot_authorize_credentials(monkeypatch,fault):
    rows=[{'synthetic_binding':index} for index in range(6151)]
    wanted=sorted(m.previous.diagnostic.digest(row) for row in rows[:5])
    monkeypatch.setattr(m,'source_binding',lambda:m.previous.diagnostic.make_specification(wanted))
    if fault=='count':rows.pop()
    elif fault=='selected_missing':rows[0]={'not_selected':True}
    elif fault=='duplicate_selected':rows[5]=dict(rows[0])
    monkeypatch.setattr(m.worker,'_load_plain',lambda *_:object())
    monkeypatch.setattr(m.worker,'_catalog',lambda *_:(None,None,None,rows,aa.expected_summary()['input_binding']))
    def unchanged(*args):
        if fault=='changed_after':raise m.Refused('input')
    monkeypatch.setattr(m.worker,'_catalog_unchanged',unchanged)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    with pytest.raises(m.Refused):m.source_observation(time.monotonic()+30)


def test_organization_projection_retains_unknowns_and_excludes_confidential_fields(scope):
    value=m._org(scope.organization,ORG,UID)
    assert m.validate_observation('organization',value)==value
    assert value['recognized_type']=='Quant Researcher' and value['paid_tier_representation'] is True
    assert value['paid_billing_active_proven'] is False and value['data_current_observed'] is True
    assert value['Storage_Create_status']=='unknown_not_in_validated_SDK_model'
    assert value['own_isAdmin_observed'] is True
    raw=m.canonical(value)
    for text in ('PRIVATE-','8675309','99.9',UID):assert ('"'+text+'"').encode() not in raw
    response=copy.deepcopy(scope.organization)
    response['organization'].update(type='Unknown New Tier',products=None,data=None,members=None)
    unknown=m._org(response,ORG,UID);m.validate_observation('organization',unknown)
    assert unknown['recognized_type'] is None and unknown['paid_tier_representation'] is None
    assert unknown['member_count'] is None and unknown['own_member_count']==0


@pytest.mark.parametrize('fault',('organization','owner','owner_id','wrong_project','foreign_collaborator','project_count'))
def test_reference_binding_refuses_wrong_project_org_or_owner_without_A5_policy(scope,fault):
    response=copy.deepcopy(scope.project);row=response['projects'][0]
    if fault=='organization':row['organizationId']='b'*32
    elif fault=='owner':row['owner']=False
    elif fault=='owner_id':row['ownerId']=77
    elif fault=='wrong_project':row['projectId']=1
    elif fault=='foreign_collaborator':row['collaborators'][0]['uid']=77
    else:response['projects'].append(dict(row))
    with pytest.raises(m.Refused):m._project(response,UID)


def test_same_org_changed_owner_and_matching_new_credential_identity_still_refuses(scope):
    response=copy.deepcopy(scope.project);row=response['projects'][0]
    row['ownerId']=77;row['collaborators'][0]['uid']=77
    refused('project',lambda:m._project(response,'77'))


@pytest.mark.parametrize('error,code',[
    (m.requests.exceptions.ConnectTimeout,'transport_connect_timeout'),
    (m.requests.exceptions.ReadTimeout,'transport_read_timeout'),
    (m.requests.exceptions.SSLError,'transport_tls'),(m.requests.exceptions.ProxyError,'transport_proxy'),
    (m.requests.exceptions.TooManyRedirects,'transport_redirect'),
    (m.requests.exceptions.ConnectionError,'transport_connection'),
    (m.requests.exceptions.Timeout,'transport_timeout'),(m.requests.exceptions.RequestException,'transport_request'),
    (OSError,'transport_os'),(ValueError,'transport_unknown')])
def test_transport_failure_uses_finite_exact_type_without_exception_text(error,code):
    class Hostile(error):
        def __str__(self):raise AssertionError('must not format secrets')
    assert m.transport_failure(error('PRIVATE-CREDENTIAL'))==code
    assert m.transport_failure(Hostile())==('transport_os' if issubclass(Hostile,OSError) else 'transport_unknown')


@pytest.fixture
def api(scope,monkeypatch):
    api=object.__new__(m.submission.QuantConnectClient)
    api._base_url=m.submission.API_BASE;api._transport=m.submission.coverage._bounded_transport;api._timeout=30
    api._credentials=NS(user_id=UID,api_token='SYNTHETIC-TOKEN');api._clock=lambda:123
    monkeypatch.setattr(m.submission,'_client',lambda:api)
    monkeypatch.setattr(m.submission,'build_auth_headers',lambda *_:{'Authorization':'SYNTHETIC-AUTH','Timestamp':'123'})
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    return api


class Raw:
    def __init__(self,raw):self.raw=raw;self.reads=0
    def stream(self,*args,**kwargs):
        self.reads+=1;yield self.raw
    def close(self):pass
    def release_conn(self):pass


def session_adapter(monkeypatch,*,status=200,body=b'{"success":true}',location=False,cookie=False):
    session=m._session();raw=Raw(body);calls=[]
    class Adapter(m.requests.adapters.HTTPAdapter):
        def send(self,request,**kwargs):
            calls.append((request,kwargs))
            response=m.requests.Response();response.status_code=status;response.url=request.url
            response.request=request;response.raw=raw
            response.headers=m.requests.structures.CaseInsensitiveDict(
                {'Content-Type':'application/json','Content-Length':str(len(body))})
            if location:response.headers['Location']='https://example.invalid/forbidden'
            if cookie:session.cookies.set('qc-fixture','SYNTHETIC')
            return response
    session.mount('https://',Adapter(max_retries=0))
    monkeypatch.setattr(m,'_session',lambda:session)
    return NS(session=session,raw=raw,calls=calls)


def test_available_numeric_status_is_retained_even_if_session_cookie_policy_refuses(api,monkeypatch):
    transport=session_adapter(monkeypatch,status=403,body=b'PRIVATE-BODY',cookie=True)
    state={'binding':m.binding(ARGS),'request_dispatch_intent':False,'http_status':None,'complete_body_pin':None}
    with pytest.raises(m.Refused):m._fetch(api,'authenticate',{},state,time.monotonic()+20)
    assert state['http_status']==403 and transport.raw.reads==0


@pytest.mark.parametrize('status',[302,401,403,429,500])
def test_real_requests_send_failed_status_never_reads_body_or_follows_redirect(api,monkeypatch,status):
    transport=session_adapter(monkeypatch,status=status,body=b'PRIVATE-FAILED-BODY',location=status==302)
    state={'binding':m.binding(ARGS),'request_dispatch_intent':False,'http_status':None,'complete_body_pin':None}
    with pytest.raises(m.Refused) as caught:
        m._fetch(api,'authenticate',{},state,time.monotonic()+20)
    assert transport.raw.reads==0 and len(transport.calls)==1
    assert m.finite(caught.value)=='http_refused'
    assert state['http_status']==status and state['request_dispatch_intent'] is True
    assert state['complete_body_pin'] is None


def test_one_fixed_TLS_request_completed_body_pin_and_strict_success_schema(api,monkeypatch):
    transport=session_adapter(monkeypatch)
    state={'binding':m.binding(ARGS),'request_dispatch_intent':False,'http_status':None,'complete_body_pin':None}
    value=m._fetch(api,'authenticate',{},state,time.monotonic()+20)
    assert value=={'success':True} and transport.raw.reads==1
    request,kwargs=transport.calls[0]
    assert request.url==m.submission.API_BASE+'/authenticate'
    assert kwargs['stream'] is True and kwargs['verify'] is True
    assert transport.session.max_redirects==0 and list(transport.session.resolve_redirects(None,None))==[]
    assert kwargs['proxies']=={} and state['complete_body_pin']['sha256']==m.sha(b'{"success":true}')


@pytest.mark.parametrize('body',[b'{"success":false}',b'{"success":true,"errors":["PRIVATE-ERROR"]}',
    b'{"success":true,"success":true}',b'{"success":NaN}',b'not JSON'])
def test_refused_or_malformed_API_body_is_not_authenticated_or_disclosed(api,monkeypatch,body):
    session_adapter(monkeypatch,body=body)
    state={'binding':m.binding(ARGS),'request_dispatch_intent':False,'http_status':None,'complete_body_pin':None}
    with pytest.raises(m.Refused):m._fetch(api,'authenticate',{},state,time.monotonic()+20)


@pytest.mark.parametrize('fault',['exit2','boolean_exit','report','source_lost','source_count','old_controls',
    'Storage_clearance','role_order','HTTP_status','parent_claim','physical_zero'])
def test_semantic_output_gates_independent_of_outer_report_hash(broker,fault):
    outcome=m.run(ARGS,time.monotonic()+60);result=outcome['result'];exit=0
    if fault=='exit2':exit=2
    elif fault=='boolean_exit':exit=False
    elif fault=='report':outcome['report']['sha256']='f'*64
    elif fault=='source_lost':result['source']=None
    elif fault=='source_count':result['source']['result']['full_binding_count']=1
    elif fault=='old_controls':result['source']['result']['old_controls_or_TICKERS_read']=True
    elif fault=='Storage_clearance':result['storage_Create_proven']=True
    elif fault=='role_order':result['observations'].reverse()
    elif fault=='HTTP_status':result['observations'][0]['state']['http_status']=302
    elif fault=='parent_claim':result['credential_handoff_complete']=False
    else:result['provider_request_count']=0
    if fault!='report':
        raw=m.canonical({**m.binding(ARGS),'result':result})
        outcome['report']={'byte_count':len(raw),'sha256':m.sha(raw)}
    with pytest.raises((m.Refused,m.worker.previous.Refused)):
        m.validate_output(m.canonical({'binding':m.binding(ARGS),'outcome':outcome}),exit,ARGS)


def test_native_scope_source_genuine_only_HTTP_no_input_DATA_validator_no_artifacts():
    source,http,validator=(m.native_profile(mode) for mode in ('source','http','validator'))
    assert '(deny network*)' in source and '(deny network*)' in validator
    assert str(m.worker.previous.PACKAGE) in source and str(m.worker.previous.LINEAGE) in source
    assert str(m.worker.previous.PACKAGE) not in http and str(m.worker.source_guard.CAPTURE) not in source
    assert str(m.CONTROL/'source-intent.json') in source
    assert str(m.ROOT/'artifacts') in validator and str(m.CONTROL) not in validator
    for profile in (source,http,validator):
        assert 'Library/Keychains' in profile and '/usr/bin/security' in profile
    assert set(m.ENDPOINTS.values())=={'authenticate','projects/read','organizations/read'}
    text=inspect.getsource(m)
    for old in ('previous.run(','worker.prepare(','admission.admit(','projects/create','projects/nodes/read','files/read','backtests/list'):
        assert old not in text
    assert 'assistant.dispatch_fence' not in sys.modules


def test_real_public_source_pin_closure_is183_and_never_refreshed():
    assert len(m.pins())==183
    for name,pin in m.pins().items():assert m.sha((m.ROOT/name).read_bytes())==pin



def test_real_inherited_claim_and_stage_original_FDs_match_named_full_metadata(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'CONTROL',tmp_path/'synthetic-AF-parent/synthetic-AF')
    with m.Store() as directory:
        directory.write('claim.json',{**m.binding(ARGS),'read_only':True,'no_project_creation':True})
        directory.write('source-intent.json',{**m.binding(ARGS),'role':'source',
            'input_pin':{'byte_count':0,'sha256':m.sha(b'')}})
        args=NS(**vars(ARGS),control_fd=directory.fd,claim_fd=directory.held['claim.json'][0],
            intent_fd=directory.held['source-intent.json'][0])
        m._inherited(args,'source',b'')
        directory.verify()
    with pytest.raises(OSError):os.fstat(args.intent_fd)


@pytest.mark.parametrize('fault',['same_fd','wrong_marker','marker_content','mode','name','hardlink','directory_mode'])
def test_inherited_FDs_tampering_never_reaches_source_or_credentials(tmp_path,monkeypatch,fault):
    control=tmp_path/'synthetic-AF-parent/synthetic-AF'
    monkeypatch.setattr(m,'CONTROL',control)
    with m.Store() as directory:
        directory.write('claim.json',{**m.binding(ARGS),'read_only':True,'no_project_creation':True})
        directory.write('source-intent.json',{**m.binding(ARGS),'role':'source',
            'input_pin':{'byte_count':0,'sha256':m.sha(b'')}})
        args=NS(**vars(ARGS),control_fd=directory.fd,claim_fd=directory.held['claim.json'][0],
            intent_fd=directory.held['source-intent.json'][0])
        path=control/'source-intent.json';role='source'
        if fault=='same_fd':args.intent_fd=args.claim_fd
        elif fault=='wrong_marker':role='project'
        elif fault=='marker_content':path.write_bytes(b'{"wrong":"metadata"}\n')
        elif fault=='mode':path.chmod(0o644)
        elif fault=='hardlink':os.link(path,control/'synthetic-link')
        elif fault=='directory_mode':control.chmod(0o755)
        else:
            path.rename(control/'synthetic-retained-old')
            path.write_bytes(b'new');path.chmod(0o600)
        with pytest.raises((m.Refused,OSError)):m._inherited(args,role,b'')


@pytest.fixture
def public_preflight(monkeypatch):
    raw=m.SOURCE.read_bytes();args=NS(operation='run',expected_head='a'*40,caller_sha256=m.sha(raw))
    state=NS(raw=raw,args=args,calls=[],change=None)
    monkeypatch.setattr(m.admitted.v5,'_under_test',lambda:False)
    monkeypatch.setattr(m,'pins',lambda:{m.SOURCE.relative_to(m.ROOT).as_posix():
        'f'*64 if state.change=='selected_pin' else m.sha(raw)})
    values={('rev-parse','--show-toplevel'):str(m.ROOT),
        ('branch','--show-current'):m.admitted.frozen.BRANCH,
        ('rev-parse','HEAD'):args.expected_head,('status','--porcelain'):''}
    def git(command,deadline,*args):
        state.calls.append(command)
        if command[0]=='cat-file':return b'changed source' if state.change=='committed_blob' else raw
        return ('concurrent synthetic state' if state.change==tuple(command) else values[tuple(command)]).encode()
    monkeypatch.setattr(m.admitted.v5,'_git',git)
    return state


def test_public_preflight_binds_exact_clean_root_branch_HEAD_and_committed_caller(public_preflight):
    fixture=public_preflight;m.preflight(fixture.args,time.monotonic()+30)
    assert fixture.calls[:4]==[['rev-parse','--show-toplevel'],['branch','--show-current'],
        ['rev-parse','HEAD'],['status','--porcelain']]
    assert fixture.calls[-1][0]=='cat-file'


@pytest.mark.parametrize('change',[('rev-parse','--show-toplevel'),('branch','--show-current'),
    ('rev-parse','HEAD'),('status','--porcelain'),'selected_pin','committed_blob','caller_pin'])
def test_changed_source_or_concurrent_lane_state_refuses_without_refresh(public_preflight,change):
    fixture=public_preflight;fixture.change=change
    if change=='caller_pin':fixture.args.caller_sha256='f'*64
    refused('git_state' if type(change) is tuple else 'source_pin',
        lambda:m.preflight(fixture.args,time.monotonic()+30))


@pytest.mark.parametrize('fault',['member_shape','product_count','known_type_hash','known_type_shape','invent_Storage_permission'])
def test_closed_organization_shape_cannot_manufacture_current_tier_or_Storage_authority(scope,fault):
    value=m._org(scope.organization,ORG,UID)
    if fault=='member_shape':value['members_shape']='null'
    elif fault=='product_count':value['observed_product_item_count']=2
    elif fault=='known_type_hash':value['type_sha256']='f'*64
    elif fault=='known_type_shape':value['type_shape']='missing'
    else:value['Storage_Create_status']='granted'
    with pytest.raises(m.Refused):m.validate_observation('organization',value)


def test_external_validator_uses_actual_exit_and_does_not_read_output_or_old_controls(broker,monkeypatch):
    outcome=m.run(ARGS,time.monotonic()+60)
    raw=m.canonical({'binding':m.binding(ARGS),'outcome':outcome});output=io.BytesIO()
    events=[]
    class Alarm:
        def __init__(self,deadline):events.append('alarm')
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setattr(m.admitted.helpers,'_alarm',Alarm)
    monkeypatch.setattr(m,'preflight',lambda *args:events.append('preflight'))
    monkeypatch.setattr(m.environment,'_bootstrap_cli_logging',lambda:events.append('logging'))
    monkeypatch.setattr(m.sys,'stdin',NS(buffer=io.BytesIO(raw)))
    monkeypatch.setattr(m.sys,'stdout',NS(buffer=output))
    code=m.main(['validate','--expected-head',ARGS.expected_head,'--caller-sha256',ARGS.caller_sha256,
        '--actual-exit','0'])
    assert code==0 and output.getvalue()==raw and events==['alarm','preflight','logging']


@pytest.mark.parametrize('error',[None,True,float('nan'),float('inf'),-1])
def test_bad_parent_deadline_refuses(error):
    refused('deadline',lambda:m.remaining(error))


def test_deadline_signal_remains_deadline_not_a_transport_unknown(api,monkeypatch):
    session=m._session()
    def send(*args,**kwargs):raise m.admitted.helpers.Deadline()
    monkeypatch.setattr(session,'send',send)
    monkeypatch.setattr(m,'_session',lambda:session)
    state={'binding':m.binding(ARGS),'request_dispatch_intent':False,'http_status':None,'complete_body_pin':None}
    with pytest.raises(m.admitted.helpers.Deadline):m._fetch(api,'authenticate',{},state,time.monotonic()+20)
    assert state['http_status'] is None



@pytest.mark.parametrize('fault',['source_actual_exit','source_binding','source_hash','source_count'])
def test_HTTP_child_refuses_bad_source_proof_before_constructing_credential_client(scope,monkeypatch,fault):
    source,observed=source_packet()
    packet={'source':source,'source_actual':observed,'organization_id':None}
    if fault=='source_actual_exit':observed['actual_exit']=False
    elif fault=='source_binding':source['binding']['expected_head']='f'*40
    elif fault=='source_hash':observed['stdout_sha256']='f'*64
    else:source['result']['full_binding_count']=1
    calls=[]
    monkeypatch.setattr(m.submission,'_client',lambda:calls.append('forbidden credential client'))
    state={'binding':m.binding(ARGS),'request_dispatch_intent':False,'http_status':None,'complete_body_pin':None}
    with pytest.raises(m.Refused):m.http_observation('authenticate',packet,state,time.monotonic()+30)
    assert calls==[] and state['request_dispatch_intent'] is False


def test_source_child_rejects_even_synthetic_QC_credential_environment_before_DATA(monkeypatch):
    monkeypatch.setenv('QC_USER_ID','SYNTHETIC')
    monkeypatch.setattr(m.worker,'_load_plain',lambda *_:(_ for _ in ()).throw(AssertionError('no DATA')))
    refused('worker_credentials',lambda:m.source_observation(time.monotonic()+30))


def test_oversized_public_or_internal_output_refuses_before_parsing(monkeypatch):
    monkeypatch.setattr(m,'parse',lambda *_:(_ for _ in ()).throw(AssertionError('no parse')))
    refused('output',lambda:m.validate_output(b'x'*(m.MAX_OUTPUT+1),0,ARGS))
    refused('output',lambda:m.validate_child(b'x'*(m.MAX_CHILD+1),actual(),ARGS,'source'))
