"""Synthetic availability predicates and reached one-use/transport checks."""
import ast
import copy
import os
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from scripts import observe_arv2_r345_qc_availability as m


def refused(code, action):
    with pytest.raises(m.Refused) as caught:
        action()
    assert caught.value.args == (code,)


def test_profile_is_finite_no_operation_or_readiness_claim():
    profile = m.profile_record()
    assert profile['maximum_requests'] == 4
    assert profile['endpoints'] == ['authenticate', 'projects/read', 'projects/collaboration/read', 'projects/nodes/read']
    assert profile['native_policy_sha256'] == m.sha(m.native_profile().encode())
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    assert 'uninterruptible' in profile['deadline_qualification']


def test_native_policy_protects_external_stores_and_limits_outbound_ports():
    profile = m.native_profile()
    for value in ('/Volumes', '/Users/sheltonchen/Library/Keychains', '/Library/Keychains',
            '/usr/bin/security', 'deny network-bind', 'deny network-inbound',
            'remote tcp "*:443"', 'remote tcp "*:53"', 'remote udp "*:53"',
            'file-write*', str(m.CONTROL), str(m.SUPPORT)):
        assert value in profile


@pytest.mark.parametrize('field,bad', [('expected_head',False),('expected_head','a'*39),
    ('caller_sha256','g'*64),('profile_sha256',None)])
def test_bad_source_bindings_refuse(field,bad):
    args = NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)
    setattr(args,field,bad)
    refused('arguments',lambda:m.binding(args))


@pytest.mark.parametrize('raw', [b'', b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'\xff'])
def test_duplicate_nonfinite_malformed_or_empty_response_refuses(raw):
    with pytest.raises(m.Refused):
        m.parse(raw)


def packet(rows,auto=False):
    return {'success':True,'nodes':{'backtest':rows},'autoSelectNode':auto}


@pytest.mark.parametrize('auto,busy,active,expected', [
    (False,False,False,0),(False,False,True,1),(False,True,True,0),
    (True,False,False,1),(True,False,True,1),(True,True,False,0),(True,True,True,0)])
def test_capacity_exact_predicate(auto,busy,active,expected):
    result=m.capacity_summary(packet([{'busy':busy,'active':active,
        'nodeId':'OTHER_LANE_SECRET_IDENTIFIER','projectId':999}],auto))
    assert result['available_backtest_count']==expected
    assert result['busy_node_count']==int(busy)
    assert result['state']==('available_observed' if expected else 'wait_occupied_or_unavailable')
    assert 'OTHER_LANE' not in m.canonical(result).decode()
    assert 'projectId' not in result and 'nodeId' not in result


@pytest.mark.parametrize('fault', ['auto_int','busy_int','active_int','missing_busy','many','node_type','errors'])
def test_capacity_malformed_bool_or_nodes_fail_closed(fault):
    value=packet([{'busy':False,'active':True}])
    if fault=='auto_int':value['autoSelectNode']=1
    elif fault=='busy_int':value['nodes']['backtest'][0]['busy']=0
    elif fault=='active_int':value['nodes']['backtest'][0]['active']=1
    elif fault=='missing_busy':del value['nodes']['backtest'][0]['busy']
    elif fault=='many':value['nodes']['backtest']*=65
    elif fault=='node_type':value['nodes']['backtest']=[None]
    else:value['errors']=['secret']
    with pytest.raises(m.Refused):m.capacity_summary(value)


def project_packets(monkeypatch):
    owner={'owner':True,'uid':123,'permission':'write','liveControl':True,'name':'SYNTHETIC'}
    org='a'*32
    monkeypatch.setattr(m,'ORGANIZATION_SHA256',m.sha(org.encode()))
    monkeypatch.setattr(m,'OWNER_ROW_SHA256',m.sha(m.canonical(owner)+b'\n'))
    row={'projectId':m.PROJECT,'name':m.PROJECT_NAME,'language':'Py','owner':True,
        'ownerId':123,'organizationId':org,'public':False,'codeRunning':False,
        'collaborators':[owner,{'unknown_general_edit_lock':'not_privacy_proof'}]}
    dedicated={'success':True,'collaborators':[owner],'userPermissions':'write','userLiveControl':True}
    return {'success':True,'projects':[row]},dedicated


def test_project_is_dedicated_owner_scoped_and_general_rows_not_privacy(monkeypatch):
    project,dedicated=project_packets(monkeypatch)
    result=m.project_summary(project,dedicated,'123')
    assert result['dedicated_owner_only'] is True
    assert result['private_field_present_and_false'] is True
    assert result['reference_editor_idle'] is True
    assert result['general_collaborators_authoritative'] is False


def test_reference_busy_is_observation_without_touching_reference(monkeypatch):
    project,dedicated=project_packets(monkeypatch)
    project['projects'][0]['codeRunning']=True
    result=m.project_summary(project,dedicated,'123')
    assert result['reference_editor_idle'] is False


def test_absent_private_field_is_not_invented_proof(monkeypatch):
    project,dedicated=project_packets(monkeypatch)
    del project['projects'][0]['public']
    assert m.project_summary(project,dedicated,'123')['private_field_present_and_false'] is False


@pytest.mark.parametrize('fault', ['project_bool','project_other','name','language','owner','owner_bool',
    'public','public_int','idle_int','org','extra_owner','owner_uid','permissions','live','owner_bytes','dedicated_scope'])
def test_project_and_dedicated_identity_refuse_mismatches(monkeypatch,fault):
    project,dedicated=project_packets(monkeypatch);row=project['projects'][0]
    if fault=='project_bool':row['projectId']=True
    elif fault=='project_other':row['projectId']+=1
    elif fault=='name':row['name']='Another lane'
    elif fault=='language':row['language']='C#'
    elif fault=='owner':row['owner']=False
    elif fault=='owner_bool':row['ownerId']=True
    elif fault=='public':row['public']=True
    elif fault=='public_int':row['public']=0
    elif fault=='idle_int':row['codeRunning']=0
    elif fault=='org':row['organizationId']='b'*32
    elif fault=='extra_owner':dedicated['collaborators']*=2
    elif fault=='owner_uid':dedicated['collaborators'][0]['uid']=321
    elif fault=='permissions':dedicated['userPermissions']='read'
    elif fault=='live':dedicated['userLiveControl']=False
    elif fault=='owner_bytes':dedicated['collaborators'][0]['extra']='unapproved'
    else:dedicated['projectId']=m.PROJECT+1
    with pytest.raises(m.Refused):m.project_summary(project,dedicated,'123')


def bare_api():
    api=object.__new__(m.API);api.used=set();api.events=[]
    api._exchange=lambda endpoint,payload:api.events.append((endpoint,payload)) or {'success':True}
    return api


@pytest.mark.parametrize('endpoint,payload', [('files/update',{'projectId':m.PROJECT}),
    ('projects/read',{}),('authenticate',{'projectId':m.PROJECT}),
    ('projects/nodes/read',{'projectId':True}),('projects/read',{'projectId':m.PROJECT+1}),
    ('projects/read',{'projectId':m.PROJECT,'extra':0}),('backtests/create',{})])
def test_readonly_endpoint_and_exact_payload_allowlist(endpoint,payload):
    api=bare_api()
    refused('endpoint',lambda:api.request(endpoint,payload))
    assert api.events==[]


def test_exact_endpoint_can_only_dispatch_once_even_after_failure():
    api=bare_api()
    def fail(*_):raise m.Refused('transport')
    api._exchange=fail
    refused('transport',lambda:api.request('authenticate',{}))
    refused('endpoint',lambda:api.request('authenticate',{}))


def test_observation_uses_four_exact_reads_and_redacts_responses(monkeypatch):
    project,dedicated=project_packets(monkeypatch)
    responses=[{'success':True},project,dedicated,packet([{'busy':False,'active':True}])]
    events=[]
    def request(endpoint,payload):events.append((endpoint,payload));return responses.pop(0)
    result=m.observe(NS(request=request),'123')
    assert events==[('authenticate',{}),('projects/read',{'projectId':m.PROJECT}),
        ('projects/collaboration/read',{'projectId':m.PROJECT}),('projects/nodes/read',{'projectId':m.PROJECT})]
    assert result['available_backtest_count']==1
    assert 'SYNTHETIC' not in m.canonical(result).decode()


def test_bad_authentication_stops_before_other_endpoints():
    events=[]
    def request(endpoint,payload):events.append(endpoint);return {'success':True,'authenticated':False}
    refused('authentication',lambda:m.observe(NS(request=request),'123'))
    assert events==['authenticate']


@pytest.mark.parametrize('values', [{},{'QC_USER_ID':'123'},
    {'QC_USER_ID':'0','QC_API_TOKEN':'synthetic-token'},
    {'QC_USER_ID':True,'QC_API_TOKEN':'synthetic-token'},
    {'QC_USER_ID':'123','QC_API_TOKEN':'bad\nsecret'},
    {'QC_USER_ID':'123','QC_API_TOKEN':'synthetic-token','other':'secret'}])
def test_credentials_are_shape_only_and_never_implicitly_default(values):
    refused('credentials',lambda:m.credentials(values))


def test_imported_file_has_no_Keychain_or_production_control_read_entrypoint():
    tree=ast.parse(Path(m.__file__).read_text(encoding='ascii'))
    imports={node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)}
    imports|={alias.name for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names}
    assert all(not item.startswith(('research','scripts.')) for item in imports if item)
    calls=[node for node in tree.body if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call)]
    assert calls==[]
    assert m.CREDENTIALS==('QC_USER_ID','QC_API_TOKEN')


def test_total_alarm_restores_handler_and_prior_deadline(monkeypatch):
    events=[]
    monkeypatch.setattr(m.signal,'signal',lambda *args:events.append(('signal',args)) or 'OLD')
    monkeypatch.setattr(m.signal,'getitimer',lambda *_:(3.0,1.0))
    monkeypatch.setattr(m.signal,'setitimer',lambda *args:events.append(('timer',args)))
    times=iter([100.0,101.0]);monkeypatch.setattr(m.time,'monotonic',lambda:next(times))
    with m.alarm(90):pass
    assert events[1][1][1]==3.0
    assert events[-2][1][1:]==(2.0,1.0)
    assert events[-1][1][1]=='OLD'


@pytest.mark.parametrize('elapsed', [0,-1,91,float('nan'),float('inf')])
def test_deadline_is_finite_bounded_and_not_elapsed(monkeypatch,elapsed):
    monkeypatch.setattr(m.time,'monotonic',lambda:100.0)
    refused('deadline',lambda:m.remaining(100.0+elapsed))


class Security:
    class Refusal(Exception):pass
    @staticmethod
    def snapshot(_fd):return {'synthetic_security':True}


def synthetic_control(tmp_path,monkeypatch):
    root=tmp_path/'root';root.mkdir(mode=0o755)
    artifact=root/'artifacts';artifact.mkdir(mode=0o700)
    monkeypatch.setattr(m,'ROOT',root)
    monkeypatch.setattr(m,'CONTROL',artifact/'control-parent'/'ONE')
    return m.CONTROL


def test_control_exclusive_claim_original_descriptors_and_no_cleanup(tmp_path,monkeypatch):
    control=synthetic_control(tmp_path,monkeypatch)
    with m.Store(Security) as store:
        result=store.write('claim.json',{'claim':True})
        assert result==m.pin(b'{"claim":true}')
        store.intent('authenticate',None);store.attempt('authenticate',None)
        assert store.application_dispatch_count==store.intents==1
        assert len(store.leaves)==3
        store.verify()
    assert sorted(p.name for p in control.iterdir())==['claim.json','dispatch-0.json','intent-0.json']
    refused('claim_spent',lambda:m.Store(Security).__enter__())


def test_replaced_original_control_leaf_is_detected(tmp_path,monkeypatch):
    control=synthetic_control(tmp_path,monkeypatch)
    store=m.Store(Security).__enter__()
    try:
        store.write('claim.json',{'claim':True})
        original=control/'claim.json'
        original.rename(control/'retained-original.json')
        original.write_bytes(b'{"claim":true}')
        refused('control',store.verify)
    finally:store.close()


def test_failed_create_preserves_partial_control_and_no_credential_read(tmp_path,monkeypatch):
    control=synthetic_control(tmp_path,monkeypatch)
    control.parent.mkdir(mode=0o700);control.mkdir(mode=0o700)
    refused('claim_spent',lambda:m.Store(Security).__enter__())
    assert list(control.iterdir())==[]


def test_store_refuses_extra_output_and_pre_dispatch_without_intent(tmp_path,monkeypatch):
    synthetic_control(tmp_path,monkeypatch)
    with m.Store(Security) as store:
        refused('output',lambda:store.write('private-market-data.json',{'licensed':True}))
        refused('bound',lambda:store.attempt('authenticate',None))


def test_runtime_source_contains_claim_before_credential_inspection_and_contact():
    tree=ast.parse(Path(m.__file__).read_text(encoding='ascii'))
    function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='run')
    calls=sorted((node.lineno,ast.unparse(node.func),ast.unparse(node)) for node in ast.walk(function) if isinstance(node,ast.Call))
    claim=min(line for line,name,text in calls if name=='store.write' and "'claim.json'" in text)
    env=min(line for line,name,_ in calls if name=='os.environ.get')
    api=min(line for line,name,_ in calls if name=='API')
    assert claim < env < api


def test_finite_failure_never_formats_exception_or_unknown_payload():
    class Hostile(Exception):
        def __str__(self):raise AssertionError('must not format')
    assert m.finite(Hostile())=='unknown'
    assert m.finite(m.Refused('http_status'))=='http_status'
    assert m.finite(m.Refused('secret-user-token'))=='unknown'


def transport_api(monkeypatch, *, status=200, raw=b'{"success":true}', headers=None):
    events=[]
    class Response:
        def __init__(self):self.status=status
        def getheader(self,key,default=None):return (headers or {}).get(key,default)
        def read(self,maximum):events.append(('read',maximum));return raw
    class Stream:
        def settimeout(self,value):events.append(('timeout',value))
        def connect(self,address):events.append(('connect',address))
        def version(self):return 'TLSv1.3'
        def close(self):events.append(('stream_close',))
    class Context:
        def wrap_socket(self,stream,server_hostname):
            events.append(('TLS_hostname',server_hostname));return stream
    class Connection:
        debuglevel=0
        def __init__(self,host,port,timeout):events.append(('connection',host,port));self.debuglevel=0
        def request(self,method,path,body,headers):events.append(('request',method,path,body,headers))
        def getresponse(self):return Response()
        def close(self):events.append(('connection_close',))
    monkeypatch.setattr(m.socket,'socket',lambda *_:Stream())
    monkeypatch.setattr(m.http.client,'HTTPConnection',Connection)
    api=object.__new__(m.API)
    api.secret={'QC_USER_ID':'123','QC_API_TOKEN':'synthetic-token-never-output'}
    api.store=NS(intent=lambda *a:events.append(('intent',*a)),attempt=lambda *a:events.append(('attempt',*a)))
    api.deadline=time.monotonic()+80
    api.last_http_status=None;api.statuses=[];api.responses=[]
    api._ca_verify=lambda:events.append(('CA',))
    api.family=m.socket.AF_INET;api.address=('93.184.216.34',443);api.context=Context()
    return api,events


def test_transport_fixed_host_path_request_and_safe_response_pins(monkeypatch):
    api,events=transport_api(monkeypatch)
    result=api._exchange('authenticate',{})
    assert result=={'success':True}
    assert ('TLS_hostname','www.quantconnect.com') in events
    request=next(e for e in events if e[0]=='request')
    assert request[1:4]==('POST','/api/v2/authenticate',b'{}')
    assert request[4]['Host']=='www.quantconnect.com'
    intent=next(i for i,e in enumerate(events) if e[0]=='intent')
    attempt=next(i for i,e in enumerate(events) if e[0]=='attempt')
    dispatched=next(i for i,e in enumerate(events) if e[0]=='request')
    assert intent < attempt < dispatched
    assert api.statuses==[{'endpoint':'authenticate','http_status':200}]
    assert api.responses==[{'endpoint':'authenticate',**m.pin(b'{"success":true}')}]
    assert 'synthetic-token' not in m.canonical([api.statuses,api.responses]).decode()
    assert events[-1]==('connection_close',)


@pytest.mark.parametrize('status',[301,401,403,429,500])
def test_http_failure_retains_only_validated_status_and_never_reads_body(monkeypatch,status):
    api,events=transport_api(monkeypatch,status=status,raw=b'LICENSED_OR_SECRET_BODY')
    refused('http_status',lambda:api._exchange('authenticate',{}))
    assert api.last_http_status==status
    assert api.statuses==[{'endpoint':'authenticate','http_status':status}]
    assert api.responses==[]
    assert not any(e[0]=='read' for e in events)
    assert events[-1]==('connection_close',)


@pytest.mark.parametrize('headers,raw,code',[
    ({'Content-Encoding':'gzip'},b'{"success":true}','response'),
    ({'Content-Length':'1048577'},b'{"success":true}','bound'),
    ({'Content-Length':'5'},b'{"success":true}','bound'),
    ({},b'{"success":true,"errors":["secret"]}','response'),
    ({},b'{"success":false}','response'),
    ({},b'{"success":true,"success":true}','response')])
def test_success_response_cannot_bypass_transport_bounds(monkeypatch,headers,raw,code):
    api,events=transport_api(monkeypatch,headers=headers,raw=raw)
    refused(code,lambda:api._exchange('authenticate',{}))
    assert events[-1]==('connection_close',)


def test_credential_access_and_contact_wait_for_successful_claim(monkeypatch):
    events=[]
    class Held:
        raw=b''
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def verify(self):events.append('source_verify')
    class Control:
        intents=application_dispatch_count=0
        def __init__(self,*_):pass
        def __enter__(self):events.append('allocation');return self
        def __exit__(self,*_):pass
        def write(self,name,value):
            events.append(name)
            if name=='claim.json':raise m.Refused('control')
    monkeypatch.setattr(m,'preflight',lambda *a:{})
    monkeypatch.setattr(m,'HeldPublic',lambda *a:Held())
    monkeypatch.setattr(m,'Store',Control)
    monkeypatch.setattr(m,'credentials',lambda *a:pytest.fail('credentials before claim'))
    monkeypatch.setattr(m,'API',lambda *a:pytest.fail('API before claim'))
    refused('control',lambda:m.run(NS(caller_sha256='b'*64)))
    assert events==['allocation','claim.json']
