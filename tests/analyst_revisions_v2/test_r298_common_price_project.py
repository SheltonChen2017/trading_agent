"""Synthetic AT metadata/transport/FD tests; no actual credentials or QC."""
import copy
import io
import os
from pathlib import Path
import ssl
import sys
import time
from types import SimpleNamespace as NS

import pytest
import requests

from scripts import create_arv2_r298_common_price_project as m


@pytest.fixture
def args(): return NS(expected_head='a'*40, caller_sha256='b'*64, profile_sha256='c'*64)


@pytest.fixture
def sequence(monkeypatch, tmp_path, args):
    owner={'uid':42,'owner':True,'permission':'write','liveControl':True,'name':'SYNTHETIC OWNER'}
    monkeypatch.setattr(m.owner_policy,'OWNER_ROW_SHA256',m.sha(m.owner_policy._canonical(owner)))
    organization='a'*32; monkeypatch.setattr(m,'ORGANIZATION_SHA256',m.sha(organization.encode()))
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    directory=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
    stages=os.open(tmp_path/'stages.jsonl',os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
    result=os.open(tmp_path/'worker-result.json',os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
    args.control_fd,args.stages_fd,args.result_fd=directory,stages,result
    def project(identity,name):
        return {'success':True,'projects':[{'projectId':identity,'name':name,'language':'Py','owner':True,
            'ownerId':42,'organizationId':organization,'collaborators':[copy.deepcopy(owner)],'libraries':[]}]}
    def collaboration(identity):
        return {'success':True,'projectId':identity,'collaborators':[copy.deepcopy(owner)],
            'userPermissions':'write','userLiveControl':True}
    packets={'authenticate':{'success':True},'reference':project(m.REFERENCE_ID,m.REFERENCE_NAME),
        'reference-collaboration':collaboration(m.REFERENCE_ID),'create':project(40000003,m.PROJECT_NAME),
        'created':project(40000003,m.PROJECT_NAME),'created-collaboration':collaboration(40000003)}
    calls=[]
    def fetch(credentials,stage,payload,entry,ca,deadline):
        assert credentials.user_id=='42' and credentials.api_token=='SYNTHETIC-KEY-123456789'
        calls.append((stage,copy.deepcopy(payload)));entry['http_status']=200
        raw=m.canonical(packets[stage]);entry['body_pin']={'byte_count':len(raw),'sha256':m.sha(raw)}
        return copy.deepcopy(packets[stage])
    monkeypatch.setattr(m,'_fetch',fetch)
    credentials=m.QuantConnectCredentials.from_env({'QC_USER_ID':'42','QC_API_TOKEN':'SYNTHETIC-KEY-123456789'})
    def run():return m._sequence(args,credentials,b'synthetic-unused-CA',time.monotonic()+80)
    yield NS(args=args,owner=owner,packets=packets,calls=calls,run=run,organization=organization)
    for fd in (directory,stages,result):os.close(fd)


def test_exact_AR_AS_source_binding_is_public_only_all_zero_and_no_readiness():
    source=m.source_binding()
    assert source['AR_fact_sha256']==m.FACT_SHA256 and source['AR_output_pin']==m.AR_OUTPUT_PIN
    assert source['source_prices_are_not_admitted'] is True
    assert m.profile_record()['maximum_dispatches']==6 and m.profile_record()['one_create'] is True
    assert all(m.profile_record()[key] is False for key in m.FALSE_FLAGS)


def test_exact_six_requests_one_create_private_default_is_still_UNKNOWN(sequence):
    state=sequence.run();m.validate_state(state)
    assert state['complete'] is True and state['created_project_id']==40000003
    assert [row[0] for row in sequence.calls]==list(m.STAGES)
    create=[payload for stage,payload in sequence.calls if stage=='create']
    assert create==[{'name':m.PROJECT_NAME,'language':'Py','organizationId':sequence.organization}]
    assert state['created']['private_verified'] is False and state['created']['privacy_observation']=='UNKNOWN'
    assert state['created']['documented_private_default_inference'] is True
    assert state['created_collaboration']['organization_manager_or_paid_status_proven'] is False
    raw=m._read(sequence.args.result_fd,m.MAX_OUTPUT)
    checkpoint=m.parse(raw[:-1]);m.validate_creation_observation(checkpoint,sequence.args)
    assert checkpoint==m.creation_observation(sequence.args,state)
    assert len(m._read(sequence.args.stages_fd,m.MAX_OUTPUT).splitlines())==6


def test_explicit_private_false_is_observed_but_not_transfer_permission(sequence):
    for key in ('reference','create','created'):sequence.packets[key]['projects'][0]['public']=False
    state=sequence.run();m.validate_state(state)
    assert state['complete'] and state['created']['private_verified'] is True
    assert state['licensed_transfer_granted'] is False and state['backtest_created'] is False


@pytest.mark.parametrize('stage',['create','created'])
@pytest.mark.parametrize('field,value',[('public',True),('name','UNEXPECTED'),('owner',False),
    ('ownerId',99),('organizationId','b'*32),('language','C#'),('libraries',[{'x':1}])])
def test_created_ID_is_retained_before_any_post_creation_predicate_failure(sequence,stage,field,value):
    sequence.packets[stage]['projects'][0][field]=value
    state=sequence.run();m.validate_state(state)
    assert not state['complete'] and state['created_project_id']==40000003 and state['create_intent'] is True
    checkpoint=m.parse(m._read(sequence.args.result_fd,m.MAX_OUTPUT)[:-1])
    assert checkpoint['created_project_id']==40000003
    assert sum(name=='create' for name,_ in sequence.calls)==1


def test_contradictory_create_success_flag_cannot_erase_observed_ID(sequence):
    sequence.packets['create']['success']=False
    state=sequence.run();m.validate_state(state)
    assert not state['complete'] and state['created_project_id']==40000003
    assert m.parse(m._read(sequence.args.result_fd,m.MAX_OUTPUT)[:-1])['created_project_id']==40000003


def test_multiple_create_rows_preserve_candidates_without_choosing_or_retrying(sequence):
    sequence.packets['create']['projects'].append({**sequence.packets['create']['projects'][0],'projectId':40000004})
    state=sequence.run();m.validate_state(state)
    assert state['observed_created_project_ids']==[40000003,40000004] and state['created_project_id'] is None
    assert len(sequence.calls)==4 and state['failure_code']=='created_ambiguous'


@pytest.mark.parametrize('where',['reference-collaboration','created-collaboration'])
def test_dedicated_collaborator_is_authoritative_and_foreign_user_refuses(sequence,where):
    sequence.packets[where]['collaborators'].append({'uid':99,'owner':False})
    state=sequence.run();m.validate_state(state)
    assert state['failure_code']=='collaboration' and not state['complete']
    assert state['created_project_id']==(40000003 if where=='created-collaboration' else None)


def test_general_unknown_session_row_is_not_a_second_dedicated_collaborator(sequence):
    sequence.packets['reference']['projects'][0]['collaborators'].append({'uid':None,'owner':False,'name':'SYNTHETIC SESSION'})
    state=sequence.run();m.validate_state(state)
    assert state['complete'] and state['reference']['unidentified_general_rows']==1


def test_finite_transport_failure_never_retries_or_creates(sequence,monkeypatch):
    def failed(credentials,stage,payload,entry,ca,deadline):
        sequence.calls.append((stage,payload));entry['http_status']=403;raise m.Refused('http_refused')
    monkeypatch.setattr(m,'_fetch',failed)
    state=sequence.run();m.validate_state(state)
    assert len(sequence.calls)==1 and not state['create_intent'] and state['created_project_id'] is None


def test_worker_marker_prevents_replay_and_keeps_credential_pipe_private(monkeypatch,tmp_path,args):
    monkeypatch.setattr(m,'CONTROL',tmp_path)
    monkeypatch.setattr(m,'source_binding',lambda:{'synthetic':'binding'})
    monkeypatch.setattr(m,'_ca',lambda fd:(b'x',(),()))
    monkeypatch.setattr(m.security,'snapshot',lambda fd:('synthetic',))
    args.control_fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
    names={'claim_fd':'claim.json','intent_fd':'worker-intent.json','started_fd':'worker-started.json','stages_fd':'stages.jsonl','result_fd':'worker-result.json'}
    opened=[args.control_fd]
    for field,name in names.items():
        fd=os.open(tmp_path/name,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600);setattr(args,field,fd);opened.append(fd)
    m._write(args.claim_fd,m.canonical(m.binding(args)))
    m._write(args.intent_fd,m.canonical({'binding':m.binding(args),'source_binding_sha256':m.sha(m.canonical(m.source_binding())),'stages':list(m.STAGES)}))
    args.ca_fd=os.open(tmp_path/'public-CA',os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600);opened.append(args.ca_fd)
    args.credential_fd,write=os.pipe();opened.extend([args.credential_fd,write])
    try:
        m._inherited(args)
        with pytest.raises(m.Refused):m._inherited(args)
        assert os.fstat(args.result_fd).st_size==0
    finally:
        for fd in opened:os.close(fd)


def test_credential_handoff_uses_only_supplied_two_key_mapping_no_fallback():
    raw=m._credential_packet({'QC_USER_ID':'42','QC_API_TOKEN':'SYNTHETIC-KEY-123456789'})
    assert set(m.parse(raw))=={'QC_USER_ID','QC_API_TOKEN'} and len(raw)<=m.MAX_CREDENTIAL
    for values in ({}, {'QC_USER_ID':'42'}, {'QC_USER_ID':'42','QC_API_TOKEN':'too\nshort'}):
        with pytest.raises(m.Refused):m._credential_packet(values)


def test_owned_TLS_pool_forces_exact_CA_context_no_default_or_proxy():
    raw=m.public_transport._ca_bytes()
    with m._session(raw) as session:
        url=m.API_BASE+'/authenticate';m._session_check(session,url);adapter=session.get_adapter(url)
        request=session.prepare_request(requests.Request('POST',url,data=b'{}'))
        _,kwargs=adapter.build_connection_pool_key_attributes(request,True,None)
        assert kwargs['ssl_context'] is adapter.context and kwargs['ca_cert_data']==raw.decode('ascii')
        assert kwargs['ca_certs'] is kwargs['ca_cert_dir'] is None
        assert adapter.context.verify_mode==ssl.CERT_REQUIRED and adapter.context.check_hostname is True
        with pytest.raises(m.Refused):adapter.proxy_manager_for('https://example.invalid')


def test_real_requests_302_session_does_not_consume_body_or_follow(monkeypatch):
    raw=m.public_transport._ca_bytes();session=m._session(raw);reads=[]
    def send(request,**kwargs):
        response=requests.Response();response.status_code=302;response.url=request.url;response.request=request
        response.headers=requests.structures.CaseInsensitiveDict({'Location':'https://example.invalid/elsewhere'})
        class Raw:
            def stream(self,*args,**kwargs):reads.append(True);raise AssertionError('failed body consumed')
            def close(self):pass
            def release_conn(self):pass
        response.raw=Raw();return response
    monkeypatch.setattr(session.get_adapter(m.API_BASE+'/authenticate'),'send',send)
    monkeypatch.setattr(m,'_session',lambda ca:session)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    credentials=m._credential_value({'QC_USER_ID':'42','QC_API_TOKEN':'SYNTHETIC-KEY-123456789'})
    entry={'request_sha256':m.sha(b'{}'),'http_status':None,'body_pin':None,'transport_failure':None}
    with pytest.raises(m.Refused):m._fetch(credentials,'authenticate',{},entry,raw,time.monotonic()+30)
    assert entry['http_status']==302 and entry['body_pin'] is None and reads==[]


def test_native_worker_scope_has_only_exact_TLS_DNS_resolver_and_control():
    worker=m.native_profile('worker');validator=m.native_profile('validate')
    assert '/private/var/run/mDNSResponder' in worker and '/private/var/run/mDNSResponder' not in validator
    assert '(deny network*)' in validator and 'object/set' not in worker and 'projects/nodes/read' not in worker
    assert '/usr/bin/security' in worker and '/Library/Keychains' in worker
    assert str(m.CONTROL/'worker-result.json') in worker
    assert str(m.sidecar.CONTROL/'manifest-private.json') not in worker


def test_closed_state_disallows_false_success_or_price_readiness(sequence):
    state=sequence.run();m.validate_state(state)
    for change in ('endpoint','private','coverage','ID'):
        bad=copy.deepcopy(state)
        if change=='endpoint':bad['dispatches'][0]['endpoint']='object/set'
        elif change=='private':bad['created']['private_verified']=True
        elif change=='coverage':bad['price_coverage_ready']=True
        else:bad['created_project_id']=99
        with pytest.raises(m.Refused):m.validate_state(bad)


@pytest.fixture
def parent_case(sequence,monkeypatch,tmp_path):
    monkeypatch.setattr(m,'CONTROL',tmp_path/'family'/'AT')
    monkeypatch.setattr(m,'preflight',lambda args,deadline:None)
    monkeypatch.setattr(m,'_credential_packet',lambda environ:m.canonical({'QC_USER_ID':'42','QC_API_TOKEN':'SYNTHETIC-KEY-123456789'}))
    calls=[]
    def capture(command,safe,timeout,**kwargs):
        calls.append(command)
        assert not {'QC_USER_ID','QC_API_TOKEN'} & set(safe)
        child=NS(expected_head=sequence.args.expected_head,caller_sha256=sequence.args.caller_sha256,
            profile_sha256=sequence.args.profile_sha256)
        for name in ('control','claim','intent','started','stages','result','ca','credential'):
            setattr(child,name+'_fd',int(command[command.index('--'+name+'-fd')+1]))
        m._inherited(child)
        secret=os.read(child.credential_fd,m.MAX_CREDENTIAL+1)
        assert b'SYNTHETIC-KEY-' in secret and os.read(child.credential_fd,1)==b''
        values=m.parse(secret);credentials=m._credential_value(values);values.clear();secret=None
        state=m._sequence(child,credentials,m._ca(child.ca_fd)[0],time.monotonic()+80)
        raw=m.canonical({'binding':m.binding(child),'state':state})+b'\n'
        actual={'actual_exit':0 if state['complete'] else 2,'bound':None,'spawn_observed':True,
            'dispatched_at':'2026-10-27T16:00:00Z','completion_observed_at':'2026-10-27T16:00:01Z',
            'stdout_bytes':len(raw),'stdout_sha256':m.sha(raw),'stderr_bytes':0,'stderr_sha256':m.sha(b'')}
        return raw,b'',actual
    monkeypatch.setattr(m,'capture',capture)
    return NS(sequence=sequence,calls=calls)


def test_parent_holds_original_claim_result_CA_and_creates_one_exact_child(parent_case):
    args=parent_case.sequence.args
    outcome,code=m.run(args,time.monotonic()+100)
    assert code==0 and len(parent_case.calls)==1
    result=outcome['result']
    assert result['state']['created_project_id']==result['creation_observation']['created_project_id']==40000003
    assert result['worker_actual']['actual_exit']==0 and result['credential_handoff_complete'] is True
    raw=m.canonical({'binding':m.binding(args),'outcome':outcome})+b'\n'
    assert m.validate_output(raw,0,args)['outcome']['result']==result
    with pytest.raises(m.Refused):m.validate_output(raw,2,args)


def test_late_parent_failure_keeps_known_createdID_and_never_accepts_zero(parent_case,monkeypatch):
    def late(args,deadline):raise m.Refused('git')
    monkeypatch.setattr(m,'preflight',late)
    args=parent_case.sequence.args;outcome,code=m.run(args,time.monotonic()+100)
    assert code==2 and outcome['result']['state']['created_project_id']==40000003
    assert outcome['result']['worker_actual']['actual_exit']==0 and outcome['result']['parent_failure']=='git'
    raw=m.canonical({'binding':m.binding(args),'outcome':outcome})+b'\n'
    m.validate_output(raw,2,args)
    with pytest.raises(m.Refused):m.validate_output(raw,0,args)


def test_report_write_refusal_keeps_ID_metadata_and_actual_failure(parent_case,monkeypatch):
    original=m.Store.create
    def fail(self,name,raw=b''):
        if name=='report.json':raise m.Refused('control')
        return original(self,name,raw)
    monkeypatch.setattr(m.Store,'create',fail)
    args=parent_case.sequence.args;outcome,code=m.run(args,time.monotonic()+100)
    assert code==2 and outcome['report'] is None and outcome['result']['creation_observation']['created_project_id']==40000003
    raw=m.canonical({'binding':m.binding(args),'outcome':outcome})+b'\n';m.validate_output(raw,2,args)
    with pytest.raises(m.Refused):m.validate_output(raw,0,args)


def test_same_claim_never_renews_or_dispatches_a_second_child(parent_case):
    args=parent_case.sequence.args;m.run(args,time.monotonic()+100)
    with pytest.raises(m.Refused):m.run(args,time.monotonic()+100)
    assert len(parent_case.calls)==1


def test_source_binding_refusal_precedes_any_credential_handoff(parent_case,monkeypatch):
    calls=[]
    def source():raise m.Refused('source')
    monkeypatch.setattr(m,'source_binding',source)
    def credentials(environ):
        calls.append(True);return m.canonical({'QC_USER_ID':'42','QC_API_TOKEN':'SYNTHETIC-KEY-123456789'})
    monkeypatch.setattr(m,'_credential_packet',credentials)
    with pytest.raises(m.Refused):m.run(parent_case.sequence.args,time.monotonic()+100)
    assert calls==[] and parent_case.calls==[]


def test_real_child_inherits_native_test_fence_owned_FDs_and_fixed_public_CA(monkeypatch,tmp_path,args):
    monkeypatch.setattr(m,'CONTROL',tmp_path/'native-family'/'AT')
    ca_fd=os.open(m.CA_PATH,os.O_RDONLY|os.O_NOFOLLOW);read,write=os.pipe()
    try:
        with m.Store() as store:
            store.create('claim.json',m.canonical(m.binding(args)))
            store.create('worker-intent.json',m.canonical({'binding':m.binding(args),
                'source_binding_sha256':m.sha(m.canonical(m.source_binding())),'stages':list(m.STAGES)}))
            for name in ('worker-started.json','stages.jsonl','worker-result.json'):store.create(name)
            packet=m.canonical({'QC_USER_ID':'42','QC_API_TOKEN':'SYNTHETIC-KEY-123456789'})
            os.write(write,packet);os.close(write);write=None
            fds=[store.fd,*(store.files[name][0] for name in ('claim.json','worker-intent.json',
                'worker-started.json','stages.jsonl','worker-result.json')),ca_fd,read]
            code=('import os,sys;from pathlib import Path;from types import SimpleNamespace as NS;'
                'from scripts import create_arv2_r298_common_price_project as m;'
                'm.CONTROL=Path(sys.argv[1]);names=("control","claim","intent","started","stages","result","ca","credential");'
                'a=NS(expected_head="a"*40,caller_sha256="b"*64,profile_sha256="c"*64);'
                '[setattr(a,n+"_fd",int(v)) for n,v in zip(names,sys.argv[2:],strict=True)];'
                'm._inherited(a);secret=os.read(a.credential_fd,m.MAX_CREDENTIAL+1);'
                'assert set(m.parse(secret))=={"QC_USER_ID","QC_API_TOKEN"};'
                'assert not {"QC_USER_ID","QC_API_TOKEN"}&set(os.environ);'
                'raw,_,_=m._ca(a.ca_fd);s=m._session(raw);m._session_check(s,m.API_BASE+"/authenticate");s.close();'
                'print("owned_fds_and_pinned_CA_only")')
            runtime=tmp_path/'support';runtime.mkdir(mode=0o700)
            # Inherit the outer test's strict native ALL-network/artifact/
            # Keychain fence. macOS rejects nesting a different sandbox with
            # sandbox_apply71; production launches independently from broker.
            command=[str(m.PYTHON),'-B','-c',code,str(m.CONTROL),*(str(fd) for fd in fds)]
            raw,errors,actual=m.capture(command,m.capture_support._environment(runtime),20,stdout_limit=m.MAX_OUTPUT,pass_fds=tuple(fds))
            assert not errors and raw==b'owned_fds_and_pinned_CA_only\n'
            assert actual['actual_exit']==0 and actual['bound'] is None
            store.refresh_worker()
    finally:
        for fd in (ca_fd,read,write):
            if fd is not None:os.close(fd)


@pytest.mark.parametrize('mode',['noise','deadline'])
def test_real_own_child_channel_and_deadline_are_killed_and_reaped(tmp_path,mode):
    runtime=tmp_path/'support';runtime.mkdir(mode=0o700)
    code='import os;os.write(1,b"x"*40000)' if mode=='noise' else 'import time;time.sleep(5)'
    command=[str(m.PYTHON),'-B','-c',code]
    raw,errors,actual=m.capture(command,m.capture_support._environment(runtime),2 if mode=='noise' else .1,stdout_limit=m.MAX_OUTPUT)
    assert actual['spawn_observed'] is True and type(actual['actual_exit']) is int
    assert actual['bound'] is not None
