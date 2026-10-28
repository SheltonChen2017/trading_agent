"""Synthetic fixed-source API readback; native network/production artifacts denied."""
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import subprocess
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import verify_arv2_r329_qc_source_readback as m
from tests.analyst_revisions_v2 import test_r329_native_coverage_projection as fixtures

REAL_ROOT, REAL_SOURCE, REAL_STAGE = m.ROOT, m.SOURCE, m.stage.SOURCE
SECRET = {'QC_USER_ID': '12345', 'QC_API_TOKEN': 'synthetic-test-token'}
DNS = {'answer_count': 1, 'ordered_answers_sha256': 'a'*64, 'selected_address_sha256': 'b'*64, 'family': int(socket.AF_INET)}
ADDRESS = {'family': int(socket.AF_INET), 'address': ['8.8.8.8', 443]}


def deadline():
    return time.monotonic() + m.SECONDS - 1


def args():
    return NS(mode='worker', expected_head='a'*40, caller_sha256=m.sha(REAL_SOURCE.read_bytes()),
        profile_sha256=m.sha(m.canonical(m.profile_record())), intent_fd=None, credential_fd=None, actual_parent_exit=None,
        outer_deadline=deadline())


def refused(code, call):
    with pytest.raises(m.Refused) as caught:
        call()
    assert m.finite(caught.value) == code


@pytest.fixture(scope='module')
def generated():
    return fixtures.generate(fixtures.inputs.__wrapped__())


def test_public_sources_protocol_scope_and_native_policy_are_exact():
    assert len(m.selected_plan()) == 26
    assert all(m.sha((REAL_ROOT / path).read_bytes()) == pin for path, pin in m.selected_plan().items())
    profile = m.profile_record()
    assert profile['project_id'] == 38522505 and profile['endpoint'] == '/api/v2/files/read'
    assert len(profile['names']) == 11 and profile['maximum_application_dispatches'] == 11
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    policy = m.native_profile()
    for token in ('mDNSResponder', '*:443', '*:53', 'Keychains', '/usr/bin/security', '[.]pyc$'):
        assert token in policy
    assert profile['port_policy_is_domain_fence'] is False


@pytest.mark.parametrize('change', ('missing', 'extra', 'user_bool', 'user_space', 'token_newline', 'token_short'))
def test_credentials_are_exact_and_never_rendered(change):
    value = dict(SECRET)
    if change == 'missing': value.pop('QC_API_TOKEN')
    elif change == 'extra': value['other'] = 'secret'
    elif change == 'user_bool': value['QC_USER_ID'] = True
    elif change == 'user_space': value['QC_USER_ID'] = ' 123'
    elif change == 'token_newline': value['QC_API_TOKEN'] += '\n'
    else: value['QC_API_TOKEN'] = 'short'
    refused('credentials', lambda: m.credentials(value))


def test_auth_recipe_matches_pinned_public_reference_and_exact_preparation():
    import base64
    body, headers = m.request_parts('main.py', SECRET, 123456)
    assert body == b'{"name":"main.py","projectId":38522505}'
    digest = hashlib.sha256(b'synthetic-test-token:123456').hexdigest()
    expected = base64.b64encode(('12345:' + digest).encode()).decode()
    assert headers == {'Authorization': 'Basic '+expected, 'Timestamp': '123456',
        'Host': 'www.quantconnect.com', 'Content-Type': 'application/json',
        'Content-Length': str(len(body)), 'Accept-Encoding': 'identity', 'Connection': 'close'}
    assert SECRET['QC_API_TOKEN'] not in repr(headers)
    refused('response', lambda: m.request_parts('other.py', SECRET, 1))


def response(content='print(1)\n', **extra):
    return {'success': True, 'files': [{'projectId': m.PROJECT, 'name': 'main.py', 'content': content, **extra}]}


def test_optional_errors_and_file_metadata_preserve_exact_bytes():
    raw = b'print(1)\n'
    for packet in (response(), {**response(), 'errors': []}, response(id=None, open=True, modified='2026-10-28', isLibrary=False)):
        assert m.exact_file(packet, 'main.py', raw) == {'name': 'main.py', **m.pin(raw)}


@pytest.mark.parametrize('change', ('error_none', 'error_string', 'error_nonempty', 'wrong_project', 'bool_project',
    'wrong_name', 'missing_content', 'extra_file', 'library', 'id_bool', 'open_string', 'surrogate', 'line_ending', 'unknown'))
def test_single_file_response_refuses_malformed_or_changed_content(change):
    value = response()
    row = value['files'][0]
    if change == 'error_none': value['errors'] = None
    elif change == 'error_string': value['errors'] = ''
    elif change == 'error_nonempty': value['errors'] = ['SECRET']
    elif change == 'wrong_project': row['projectId'] += 1
    elif change == 'bool_project': row['projectId'] = True
    elif change == 'wrong_name': row['name'] = 'other.py'
    elif change == 'missing_content': row.pop('content')
    elif change == 'extra_file': value['files'].append(dict(row))
    elif change == 'library': row['isLibrary'] = True
    elif change == 'id_bool': row['id'] = False
    elif change == 'open_string': row['open'] = 'true'
    elif change == 'surrogate': row['content'] = '\ud800'
    elif change == 'line_ending': row['content'] = 'print(2)\n'
    else: value['unknown'] = 'SECRET'
    with pytest.raises(m.Refused):
        m.exact_file(value, 'main.py', b'print(1)\n')


@pytest.mark.parametrize('ip', ('127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', 'not-an-IP'))
def test_dns_rejects_local_or_invalid_addresses(ip):
    family = int(socket.AF_INET6) if ':' in ip else int(socket.AF_INET)
    address = [ip, 443, 0, 0] if family == socket.AF_INET6 else [ip, 443]
    refused('dns', lambda: m.address_row(family, address))


def test_resolver_one_lookup_no_fallback_and_alarm_restored(monkeypatch):
    calls = []
    def lookup(*values):
        calls.append(values)
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('8.8.8.8',443)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('1.1.1.1',443))]
    monkeypatch.setattr(m.socket, 'getaddrinfo', lookup)
    old = signal.getsignal(signal.SIGALRM)
    selected, fact = m.resolver(deadline())
    assert selected == ADDRESS and fact['answer_count'] == 2 and len(calls) == 1
    assert calls[0] == (m.HOST, 443, socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    assert signal.getsignal(signal.SIGALRM) == old and signal.getitimer(signal.ITIMER_REAL) == (0,0)


def test_inherited_pipe_is_owned_bounded_and_consumed_once():
    reader = m._pipe(m.canonical({'purpose': 'synthetic'}))
    assert m.read_pipe(reader, 256) == {'purpose': 'synthetic'}
    with pytest.raises(OSError):
        os.fstat(reader)
    reader = m._pipe(b'x'*300)
    refused('inherited', lambda: m.read_pipe(reader, 256))


class FakeCA:
    raw = b'SYNTHETIC_CA'
    def verify(self): pass
    def __enter__(self): return self
    def __exit__(self,*_): pass


@pytest.fixture
def transport(monkeypatch):
    events = []
    state = NS(status=200, body=m.canonical(response()), headers={}, sent=None, reads=0, connects=0, closes=0)
    class Stream:
        def settimeout(self,v): events.append(('timeout',v))
        def connect(self,address): state.connects += 1; events.append(('connect',address))
        def version(self): return 'TLSv1.3'
        def close(self): state.closes += 1
    class Context:
        def __init__(self, protocol): events.append(('context',protocol))
        def load_verify_locations(self, **kw): events.append(('CA',kw))
        def wrap_socket(self,stream,**kw):
            assert self.check_hostname is True and self.verify_mode == ssl.CERT_REQUIRED and self.minimum_version == ssl.TLSVersion.TLSv1_2
            events.append(('TLS',kw)); return stream
    class Response:
        @property
        def status(self): return state.status
        def getheader(self,key,default=None): return state.headers.get(key,default)
        def read(self,n):
            state.reads += 1
            chunk,state.body=state.body[:n],state.body[n:]
            return chunk
    class Connection:
        debuglevel=0
        def __init__(self,host,port,timeout): events.append(('HTTP',host,port)); self.sock=None
        def request(self,method,url,body,headers):
            assert self.auto_open == 0 and self.sock is not None
            state.sent=(method,url,body,headers)
        def getresponse(self): return Response()
        def close(self): state.closes += 1
    monkeypatch.setattr(m.ssl,'SSLContext',Context)
    monkeypatch.setattr(m.socket,'socket',lambda *a: Stream())
    monkeypatch.setattr(m.http.client,'HTTPConnection',Connection)
    return state,events


def entry():
    return {'ordinal':0,'name':'main.py','request_sha256':m.sha(m.canonical({'projectId':m.PROJECT,'name':'main.py'})),
        'application_dispatch_attempted':False,'http_status':None}


def test_transport_exact_one_socket_TLS_hostname_POST_and_memory_only_comparison(transport):
    state,events=transport; row=entry()
    value=m.fetch('main.py',b'print(1)\n',SECRET,ADDRESS,FakeCA(),row,deadline())
    assert value=={'name':'main.py',**m.pin(b'print(1)\n')}
    assert state.connects==1 and state.closes==1 and state.sent[:2]==('POST','/api/v2/files/read')
    assert ('TLS',{'server_hostname':'www.quantconnect.com'}) in events
    assert ('CA',{'cadata':'SYNTHETIC_CA'}) in events
    assert row['application_dispatch_attempted'] is True and row['http_status']==200
    assert 'print' not in repr(value) and SECRET['QC_API_TOKEN'] not in repr(value)


@pytest.mark.parametrize('status',(301,401,403,429,500))
def test_non200_retains_numeric_status_without_body_or_retry(transport,status):
    state,_=transport;state.status=status;row=entry()
    refused('http_status',lambda:m.fetch('main.py',b'print(1)\n',SECRET,ADDRESS,FakeCA(),row,deadline()))
    assert row['http_status']==status and state.reads==0 and state.connects==1


@pytest.mark.parametrize('change',('length','encoding','cookie','oversize','mismatch'))
def test_response_transport_bounds_refuse(transport,change):
    state,_=transport
    if change=='length': state.headers['Content-Length']=str(m.MAX_BODY+1)
    elif change=='encoding': state.headers['Content-Encoding']='gzip'
    elif change=='cookie': state.headers['Set-Cookie']='SECRET'
    elif change=='oversize': state.body=b'x'*(m.MAX_BODY+1)
    else: state.body=m.canonical(response('print(2)\n'))
    with pytest.raises(m.Refused):m.fetch('main.py',b'print(1)\n',SECRET,ADDRESS,FakeCA(),entry(),deadline())
    assert state.connects==1


class Journal:
    def __init__(self): self.rows=[]
    def append(self,name,raw): assert name=='request-intents.jsonl';self.rows.append(m.parse(raw))


def test_sequence_exact11_intent_before_request_no_retry(generated,monkeypatch):
    store=Journal();seen=[]
    def fetch(name,expected,secret,selected,ca,row,end):
        assert store.rows[-1]['name']==name and len(store.rows)==len(seen)+1
        row['application_dispatch_attempted']=True;row['http_status']=200;seen.append(name)
        return {'name':name,**m.pin(expected)}
    monkeypatch.setattr(m,'fetch',fetch)
    state=m.validate_state(m.sequence(store,dict(generated.source_pairs),SECRET,ADDRESS,FakeCA(),deadline()))
    assert state['complete'] and state['application_dispatch_count']==state['intent_count']==11
    assert tuple(seen)==m.projection.CLOUD_NAMES and state['source_files']==generated.to_record()['source_files']


def test_sequence_refusal_stops_at_exact_attempt(generated,monkeypatch):
    store=Journal()
    def fetch(name,expected,secret,selected,ca,row,end):
        row['application_dispatch_attempted']=True;row['http_status']=403
        raise m.Refused('http_status')
    monkeypatch.setattr(m,'fetch',fetch)
    state=m.validate_state(m.sequence(store,dict(generated.source_pairs),SECRET,ADDRESS,FakeCA(),deadline()))
    assert not state['complete'] and state['intent_count']==state['application_dispatch_count']==len(store.rows)==1
    assert state['failure_code']=='http_status' and state['source_files']==[]


@pytest.fixture
def local(monkeypatch,tmp_path):
    root=tmp_path/'root';root.mkdir(mode=0o700)
    control=root/'artifacts/analyst_revisions_v2/newrule_available_history_native_coverage_source/R329-20261028-D'
    control.parent.mkdir(parents=True,mode=0o700)
    for path in (root/'artifacts',root/'artifacts/analyst_revisions_v2'):path.chmod(0o700)
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'CONTROL',control)
    monkeypatch.setattr(m.stage,'ROOT',root)
    monkeypatch.setattr(m.stage,'CONTROL',control.with_name('R329-20261028-A'))
    return root,control


def test_real_store_exclusive_claim_start_and_append_integrity(local):
    _,control=local
    with m.Store() as store:
        store.create('claim.json',b'{}');store.create('worker-started.json',b'{}')
        store.create('request-intents.jsonl',b'');store.append('request-intents.jsonl',b'{}\n')
        refused('output',lambda:store.create('worker-started.json',b'{}'))
        refused('output',lambda:store.append('worker-started.json',b'{}'))
        assert (control/'request-intents.jsonl').read_bytes()==b'{}\n'
    with pytest.raises(m.stage.Refused):m.Store()


def test_real_store_changed_leaf_and_unknown_file_refuse(local):
    _,control=local
    with pytest.raises(m.Refused):
        with m.Store() as store:
            store.create('claim.json',b'{}')
            (control/'claim.json').write_bytes(b'xx')
            store.verify()


def test_CA_held_original_descriptor_pin_and_mutation_refusal(local,monkeypatch):
    root,_=local;path=root.parent/'external-public-venv/cacert.pem';path.parent.mkdir(mode=0o700)
    assert root not in path.parents
    path.write_bytes(b'SYNTHETIC_CA');path.chmod(0o600)
    monkeypatch.setattr(m,'CA_PATH',path);monkeypatch.setattr(m,'CA_SIZE',len(b'SYNTHETIC_CA'))
    monkeypatch.setattr(m,'CA_SHA256',m.sha(b'SYNTHETIC_CA'))
    with pytest.raises(m.Refused):
        with m.CA() as held:
            assert held.raw==b'SYNTHETIC_CA'
            path.write_bytes(b'SYNTHETIC_CX');held.verify()


def tiny(source,tmp_path,seconds=3):
    safe={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TMPDIR':str(tmp_path),
        'PYTHONPYCACHEPREFIX':str(tmp_path/'pycache'),'PYTHONDONTWRITEBYTECODE':'1'}
    return m.capture([sys.executable,'-I','-B','-c',source],safe,(),time.monotonic()+seconds)


def test_real_tiny_child_finite_output_and_nonzero_preserved(tmp_path):
    raw,actual=tiny('print("{}") ; raise SystemExit(2)',tmp_path)
    assert raw==b'{}\n' and actual['actual_exit']==2 and actual['status']=='returned'


@pytest.mark.parametrize('case',('stderr','oversize','timeout'))
def test_real_tiny_child_bounds_kill_and_reap(tmp_path,case):
    text={'stderr':'import sys,time;sys.stderr.write("SECRET");sys.stderr.flush();time.sleep(30)',
        'oversize':'import sys,time;sys.stdout.write("X"*50000);sys.stdout.flush();time.sleep(30)',
        'timeout':'import time;time.sleep(30)'}[case]
    raw,actual=tiny(text,tmp_path,seconds=.2 if case=='timeout' else 3)
    assert actual['status'] in ('child_stderr','bound','deadline') and type(actual['actual_exit']) is int
    assert len(raw)<=m.MAX_OUTPUT and b'SECRET' not in raw


def test_supervisor_missing_credentials_before_pipe_or_dispatch(monkeypatch):
    value=args();value.mode='run'
    monkeypatch.setattr(m,'public_preflight',lambda *a:{'PATH':'/usr/bin:/bin'})
    monkeypatch.setattr(m.os,'environ',{})
    monkeypatch.setattr(m,'_pipe',lambda *a:pytest.fail('pipe allocation'))
    monkeypatch.setattr(m,'capture',lambda *a:pytest.fail('dispatch'))
    refused('credentials',lambda:m.supervise(value,deadline()))


def test_launch_selects_exact_credentials_and_no_secret_argv(monkeypatch,tmp_path):
    value=args();value.mode='launch';value.outer_deadline=None
    monkeypatch.setattr(m.sys,'flags',NS(isolated=1))
    monkeypatch.setattr(m.sys,'dont_write_bytecode',True)
    monkeypatch.setattr(m.os,'environ',{**SECRET,'UNRELATED_SECRET':'SHOULD_NOT_COPY','PYTHONPATH':'ignored-by-isolated'})
    monkeypatch.setattr(m.tempfile,'mkdtemp',lambda **kw:str(tmp_path))
    seen={}
    def execute(path,argv,env):seen.update(path=path,argv=argv,env=env);raise RuntimeError('synthetic-exec-stop')
    monkeypatch.setattr(m.os,'execve',execute)
    with pytest.raises(RuntimeError,match='synthetic-exec-stop'):m.launch(value)
    assert seen['path']==m.PYTHON and seen['argv'][1:3]==['-I','-B']
    assert all(secret not in repr(seen['argv']) for secret in (*SECRET.values(),'SHOULD_NOT_COPY'))
    assert seen['env']['QC_API_TOKEN']==SECRET['QC_API_TOKEN'] and seen['env']['LC_ALL']=='C'
    assert 'UNRELATED_SECRET' not in seen['env'] and 'PYTHONPATH' not in seen['env']


def good_envelope(generated):
    rows=[]
    for ordinal,name in enumerate(m.projection.CLOUD_NAMES):
        rows.append({'ordinal':ordinal,'name':name,'request_sha256':m.sha(m.canonical({'projectId':m.PROJECT,'name':name})),
            'application_dispatch_attempted':True,'http_status':200})
    state={'complete':True,'failure_code':None,'intent_count':11,'application_dispatch_count':11,
        'entries':rows,'source_files':generated.to_record()['source_files'],**m.FALSE_FLAGS}
    result={'schema':m.SCHEMA,'project_id':m.PROJECT,'dns':DNS,'state':state,'projection_pin':m.stage.EXPECTED_PROJECTION_PIN,
        'profile_pin':m.stage.EXPECTED_PROFILE_PIN,'projection_record':generated.to_record(),
        'selected_source_plan_sha256':m.sha(m.canonical({**m.selected_plan(),m.SOURCE.relative_to(m.ROOT).as_posix():args().caller_sha256})),
        'claim_consumed':True,'all_original_source_descriptors_postchecked':True}
    child={'binding':m.binding(args()),'result':result,'report_pin':m.pin(m.canonical({'binding':m.binding(args()),'result':result}))}
    return {'binding':m.binding(args()),'child_envelope':child,'child_actual':{'status':'returned','actual_exit':0,
        'stdout':m.pin(m.canonical(child)+b'\n')},'child_output_accepted':False,'attempt_reusable':False}


def test_success_requires_actual_outer_and_child_zero_whole_projection_and_report(generated):
    packet=good_envelope(generated);raw=m.canonical(packet)+b'\n'
    assert m.validate_output(raw,0,args())==packet
    for exit in (2,True,None):refused('output',lambda:m.validate_output(raw,exit,args()))


@pytest.mark.parametrize('change',('child_exit','child_pin','report_pin','dns','file_size','projection','ready','attempts','extra_file'))
def test_external_validator_rejects_mutations_even_with_rehashed_envelope(generated,change):
    value=good_envelope(generated);child=value['child_envelope'];result=child['result']
    if change=='child_exit':value['child_actual']['actual_exit']=2
    elif change=='child_pin':value['child_actual']['stdout']['sha256']='0'*64
    elif change=='report_pin':child['report_pin']['sha256']='0'*64
    elif change=='dns':result['dns']={}
    elif change=='file_size':result['state']['source_files'][0]['byte_count']+=1
    elif change=='projection':result['projection_record']['project_id']=123
    elif change=='ready':result['state']['paper_or_live_ready']=True
    elif change=='attempts':result['state']['application_dispatch_count']=10
    else:result['state']['source_files'].append(dict(result['state']['source_files'][0]))
    if change not in ('report_pin','child_pin'):
        child['report_pin']=m.pin(m.canonical({'binding':m.binding(args()),'result':result}))
        value['child_actual']['stdout']=m.pin(m.canonical(child)+b'\n')
    refused('output',lambda:m.validate_output(m.canonical(value)+b'\n',0,args()))


def test_operation_deadline_respects_frozen_stage180_and_outer210():
    outer=deadline();operation=m.operation_deadline(outer)
    assert 0<m.stage.remaining(operation)<=180 and operation<=outer
    assert m.profile_record()['operation_seconds']==180


@pytest.fixture
def pipeline(local,monkeypatch):
    root,control=local
    plan=m.selected_plan()
    for name in (*plan,REAL_SOURCE.relative_to(REAL_ROOT).as_posix()):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes((REAL_ROOT/name).read_bytes());path.chmod(0o644)
    monkeypatch.setattr(m,'SOURCE',root/REAL_SOURCE.relative_to(REAL_ROOT))
    monkeypatch.setattr(m.stage,'SOURCE',root/REAL_STAGE.relative_to(REAL_ROOT))
    def metadata(path):
        fd=os.open(path,os.O_RDONLY)
        try:return m.stage.metadata(fd)
        finally:os.close(fd)
    monkeypatch.setattr(m,'BOOTSTRAP_STAGE_METADATA',metadata(m.stage.SOURCE))
    monkeypatch.setattr(m.stage,'BOOTSTRAP_METADATA',{name:metadata(root/name) for name in m.stage.public_plan()})
    monkeypatch.setattr(m,'public_preflight',lambda *a:{})
    monkeypatch.setattr(m,'CA',FakeCA)
    calls=[]
    def dns(end):
        assert not control.exists();calls.append('dns');return ADDRESS,DNS
    def fetch(name,expected,secret,selected,ca,row,end):
        assert (control/'claim.json').is_file() and (control/'worker-started.json').is_file()
        assert secret==SECRET
        row['application_dispatch_attempted']=True;row['http_status']=200
        calls.append(name);return {'name':name,**m.pin(expected)}
    monkeypatch.setattr(m,'resolver',dns);monkeypatch.setattr(m,'fetch',fetch)
    return root,control,calls


def inputs():
    value=args()
    value.intent_fd=m._pipe(m.canonical({'binding':m.binding(value),'purpose':'one_named_source_readback_worker'}))
    value.credential_fd=m._pipe(m.canonical(SECRET))
    return value


def close_inputs(value):
    for fd in (value.intent_fd,value.credential_fd):
        try:os.close(fd)
        except OSError:pass


def test_complete_synthetic_source_to_claim_to11read_pipeline_and_no_duplicate(pipeline):
    _,control,calls=pipeline;value=inputs()
    try:
        output=m.produce(value,deadline())
    finally:close_inputs(value)
    assert output['result']['state']['complete'] is True
    assert calls==['dns',*m.projection.CLOUD_NAMES]
    assert set(p.name for p in control.iterdir())==set(m.FILES[:-1])
    journal=(control/'request-intents.jsonl').read_bytes().splitlines()
    assert len(journal)==11 and all('content' not in m.parse(row) for row in journal)
    raw=(control/'report.json').read_bytes()
    assert m.pin(raw)==output['report_pin'] and SECRET['QC_API_TOKEN'].encode() not in raw
    second=inputs()
    try:refused('claim_spent',lambda:m.produce(second,deadline()))
    finally:close_inputs(second)
    assert calls==['dns',*m.projection.CLOUD_NAMES]


def test_preclaim_dns_failure_leaves_control_unallocated(pipeline,monkeypatch):
    _,control,_=pipeline;value=inputs()
    monkeypatch.setattr(m,'resolver',lambda *a:(_ for _ in ()).throw(m.Refused('dns')))
    try:refused('dns',lambda:m.produce(value,deadline()))
    finally:close_inputs(value)
    assert not control.exists()


def test_all_bootstrap_metadata_is_compared_before_DNS_or_claim(pipeline,monkeypatch):
    root,control,_=pipeline;value=inputs()
    one=next(iter(m.stage.BOOTSTRAP_METADATA));path=root/one
    path.write_bytes(path.read_bytes())
    monkeypatch.setattr(m,'resolver',lambda *a:pytest.fail('DNS before source authentication'))
    try:refused('source_changed',lambda:m.produce(value,deadline()))
    finally:close_inputs(value)
    assert not control.exists()


def test_offline_validator_authenticates_metadata_only_no_producer_or_control(generated,monkeypatch):
    value=args();value.mode='validate';value.outer_deadline=None;value.actual_parent_exit=0
    monkeypatch.setattr(m,'public_preflight',lambda *a:{})
    monkeypatch.setattr(m,'resolver',lambda *a:pytest.fail('DNS'))
    monkeypatch.setattr(m,'credentials',lambda *a:pytest.fail('credential access'))
    monkeypatch.setattr(m,'Store',lambda *a:pytest.fail('control access'))
    result=m.validate_mode(value,m.canonical(good_envelope(generated))+b'\n',time.monotonic()+20)
    assert result['accepted'] is True and result['output_authenticated'] is True
    assert result['file_count']==result['application_dispatch_count']==11
    assert 'source_files' not in result and 'child_envelope' not in result


@pytest.mark.parametrize('change',('actual_exit','oversize','trailing','credential_fd','deadline'))
def test_offline_validator_refuses_changed_external_binding(generated,monkeypatch,change):
    value=args();value.mode='validate';value.outer_deadline=None;value.actual_parent_exit=0
    raw=m.canonical(good_envelope(generated))+b'\n'
    if change=='actual_exit':value.actual_parent_exit=2
    elif change=='oversize':raw=b'x'*(m.MAX_OUTPUT+1)
    elif change=='trailing':raw+=b'\n'
    elif change=='credential_fd':value.credential_fd=8
    else:value.outer_deadline=deadline()
    monkeypatch.setattr(m,'public_preflight',lambda *a:{})
    with pytest.raises(m.Refused):m.validate_mode(value,raw,time.monotonic()+20)


def test_nested_native_policy_refusal_is_retained_as_host_limitation():
    result=subprocess.run(['/usr/bin/sandbox-exec','-p',m.native_profile(),'/usr/bin/true'],
        env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,check=False)
    # Native pytest is already sandboxed. macOS refuses a second sandbox_apply;
    # an independent directly-launched harmless child checks policy syntax.
    assert result.returncode==71 and result.stdout==b''
    assert result.stderr==b'sandbox-exec: sandbox_apply: Operation not permitted\n'


def test_real_tiny_child_owned_FD_handoff_and_no_environment_credentials(tmp_path):
    raw=m.canonical({'purpose':'synthetic-intent'})
    fd=m._pipe(raw)
    program='import os,json; raw=os.read('+str(fd)+',4096); end=os.read('+str(fd)+',1); print(json.dumps({"matched":raw=='+repr(raw)+',"EOF":end==b"","no_credentials":not {"QC_USER_ID","QC_API_TOKEN"}&set(os.environ)}))'
    try:
        observed,actual=m.capture([sys.executable,'-I','-B','-c',program],
            {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},(fd,),time.monotonic()+3)
    finally:os.close(fd)
    assert actual['status']=='returned' and actual['actual_exit']==0
    assert json.loads(observed)=={'matched':True,'EOF':True,'no_credentials':True}


@pytest.mark.parametrize('extra',('LC_CTYPE','PYTHONPATH','QC_API_TOKEN'))
def test_worker_environment_refuses_unfrozen_or_credential_keys(tmp_path,monkeypatch,extra):
    safe={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','LANG':'C',
        'TMPDIR':str(tmp_path),'PYTHONPYCACHEPREFIX':str(tmp_path/'cache'),
        'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1',extra:'synthetic'}
    monkeypatch.setattr(m.os,'environ',safe)
    refused('environment',lambda:m.environment(secret=False))


def test_resolver_refusal_is_finite_without_exception_text(monkeypatch):
    monkeypatch.setattr(m.socket,'getaddrinfo',lambda *a:(_ for _ in ()).throw(socket.gaierror(8,'SECRET')))
    refused('dns',lambda:m.resolver(deadline()))


def test_argument_error_does_not_echo(monkeypatch,capsys):
    monkeypatch.setattr(m.sys,'argv',['caller','run','--SECRET'])
    refused('arguments',m.cli)
    assert capsys.readouterr()==('','')
