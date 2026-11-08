"""Synthetic R327-H only: no retained DATA, credential or provider operations."""
import copy
import inspect
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import time
from types import SimpleNamespace as NS

import pytest
import requests

from scripts import run_arv2_r327_public_figi_hierarchy as m
assert 'assistant.dispatch_fence' not in sys.modules


def args():return NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def fail(code,call):
    with pytest.raises(m.Refused) as error:call()
    assert m.finite(error.value)==code


def figis(count=20):
    result=[]
    for number in range(count):
        first='BBG000000'+format(number,'02d')
        result.append(next(first+str(end) for end in range(10) if m.hierarchy.old._figi(first+str(end))))
    return result


def selected():
    claims=sorted(figis(9))
    return {'schema':'synthetic-selection','figis':claims,'cases':[
        {'case_ordinal':index,'original_figi':claims[index],'candidate_figis':[claims[index+4]]}
        for index in range(5)]}


def evidence():
    return {'selected_whole_binding_sha256s':[format(i,'064x') for i in range(1,6)],
        'selected_case_count':5,'original_binding_schema_and_semantic_row_hash_checked_count':5,
        'original_class_and_identity_evidence_checked_count':5,'original_non_USD_functional_reporting_currency_count':0,
        'original_native_QC_SIDs_available':False,'vendor_source_blockers_remaining':5}


def row(claim,*,composite=None,exchange='US',share=None):
    return {'figi':claim,'name':'Synthetic','ticker':'SYNTH','exchCode':exchange,'marketSector':'Equity',
        'securityType':'Common Stock','securityType2':'Common Stock','securityDescription':'Synthetic',
        'compositeFIGI':composite or claim,'shareClassFIGI':share or claim}


def responses(selection,*,second=False):
    claims=selection['figis'];other=figis(10)[9];share=figis(11)[10]
    first=m.canonical([{'data':[row(claim,composite=other if second else claim,
        exchange='LN' if second else 'US',share=share)]} for claim in claims])
    second_raw=m.canonical([{'data':[row(other,share=share)]}]) if second else b''
    return first,second_raw


def actual(packet,exit=0):
    raw=m.canonical(packet)+b'\n'
    return {'actual_exit':exit,'spawn_observed':True,'bound':None,'stdout_bytes':len(raw),
        'stdout_sha256':m.sha(raw),'stderr_bytes':0,'stderr_sha256':m.sha(b'')}


def packet(role,value,code=None):return {'binding':m.binding(args()),'role':role,'result':value,'failure_code':code}


def fake_receipt():
    return {'schema':m.guard_module.SCHEMA+'-receipt','profile_sha256':m.sha(m.canonical(m.guard_module.profile_record(m.SOURCE_PLAN))),
        'files':{'ad_selection':{**m.SOURCE_PLAN['ad_selection'],'current_metadata_sha256':'d'*64,'current_security_sha256':'e'*64}},
        'fresh_current_security_authenticated':True,'fixed_bytes_authenticated':True,'requires_normal_return_before_use':True,
        'historical_continuity_proven':False,'continuous_integrity_proven':False}


def source():
    observation={'schema':m.SCHEMA+'-source','source_guard_receipt':fake_receipt(),'source_guard_normal_return':True,
        'selection_pin':dict(m.SELECTION_PIN),'original_case_count':5,'original_public_identifier_count':9,
        'selected_candidate_pair_count':sum(len(case['candidate_figis']) for case in selected()['cases']),
        'original_binding_evidence':evidence(),'prior_context':m.source_context(),**m.FALSE_FLAGS}
    return {'observation':observation,'source_metadata_pin':m.pin(m.canonical(observation))}


@pytest.fixture
def scope(monkeypatch,tmp_path):
    root=tmp_path/'root';root.mkdir(mode=0o755);root.chmod(0o755)
    for name in ('artifacts','artifacts/analyst_revisions_v2','artifacts/analyst_revisions_v2/source','.pytest_cache'):
        (root/name).mkdir(mode=0o700)
    selection=selected();seed=m.canonical(selection);raw=m.canonical({'selection':selection})
    path=root/'artifacts/analyst_revisions_v2/source/package.json';path.write_bytes(raw);path.chmod(0o600)
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m.guard_module,'ROOT',root);monkeypatch.chdir(root)
    monkeypatch.setattr(m,'CONTROL',root/'output'/'H')
    monkeypatch.setattr(m,'SOURCE_PLAN',{'ad_selection':{'relative_path':'artifacts/analyst_revisions_v2/source/package.json',**m.pin(raw)}})
    monkeypatch.setattr(m,'SELECTION_PIN',m.pin(seed));monkeypatch.setattr(m,'source_context',lambda:{'synthetic':'context'})
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    monkeypatch.setattr(m.ar,'_credential_free',lambda:None)
    monkeypatch.setattr(m.selection_proof,'prepare',lambda value,deadline:(evidence(),{}))
    def select(value,deadline):
        m.require(m.pin(value)==m.SELECTION_PIN,'selection')
        return json.loads(value),evidence()
    monkeypatch.setattr(m,'_selection',select)
    monkeypatch.setattr(m.selection_proof,'_evidence',lambda value:value)
    def walk(path):
        chain=tuple((os.stat(Path(*path.parts[:i+1])).st_dev,os.stat(Path(*path.parts[:i+1])).st_ino) for i in range(1,len(path.parts)))
        return os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW),chain
    monkeypatch.setattr(m.admitted,'_storage_module',lambda:NS(_walk=walk))
    return NS(root=root,path=path,selection=selection,seed=seed,raw=raw)


def allocated():
    store=m.Store();store.write('claim.json',m.binding(args()))
    for name in m.DATA_FILES:store.create(name)
    return store,[store.held[name]['fd'] for name in m.DATA_FILES]


def seed_store(store,fds):
    supplied=source()
    m._write(fds[0],m.canonical(selected()));m._write(fds[5],m.canonical(supplied['observation']))
    store.refresh((m.DATA_FILES[0],m.DATA_FILES[5]));return supplied


def test_actual_prior_failure_context_is_preserved():
    result=m.source_context()
    assert result['AD_actual_producer_exit']==2 and result['AD_actual_validator_exit']==0
    assert result['AD_mapping_accepted'] is False
    assert m.SOURCE_PLAN['ad_selection']['byte_count']==26503
    assert m.SELECTION_PIN=={'byte_count':24516,'sha256':'0776dc737e2b35f481b2f732d8bb17f5e2bf32e8faa3478e2897f64488740e7a'}


def test_prior_failure_cannot_be_relabelled_success(monkeypatch):
    fact=m.ad_anchor.observed_fact();fact['producer']['actual_exit']=0
    monkeypatch.setattr(m.ad_anchor,'observed_fact',lambda:fact)
    fail('source_binding',m.source_context)


def test_source_normal_return_before_owned_seed(scope,monkeypatch):
    store,fds=allocated()
    original=m.guard_module.FixedDataGuard;seen=[]
    class Guard:
        def __init__(self,*args,**kwargs):self.inner=original(*args,**kwargs)
        def __enter__(self):seen.append('enter');return self.inner.__enter__()
        def __exit__(self,*args):
            assert os.fstat(fds[0]).st_size==0
            result=self.inner.__exit__(*args);seen.append('normal_return');return result
    monkeypatch.setattr(m.guard_module,'FixedDataGuard',Guard)
    try:
        value=m.source_observation(fds,time.monotonic()+30)
        assert seen==['enter','normal_return'] and value['observation']['source_guard_normal_return'] is True
        assert m._read(fds[0],65536,time.monotonic()+5)==scope.seed
        m.validate_source(value)
    finally:store.__exit__()


def test_source_corruption_refuses_before_json(scope,monkeypatch):
    raw=bytearray(scope.raw);raw[-2]^=1;scope.path.write_bytes(raw)
    called=[];monkeypatch.setattr(m.selection_proof,'prepare',lambda *args:called.append(True))
    store,fds=allocated()
    try:
        with pytest.raises(m.guard_module.Refused):m.source_observation(fds,time.monotonic()+20)
        assert not called and all(os.fstat(fd).st_size==0 for fd in fds)
    finally:store.__exit__()


def test_source_named_replacement_refuses_before_publication(scope,monkeypatch):
    def prepare(raw,deadline):
        scope.path.rename(scope.path.with_suffix('.old'))
        scope.path.write_bytes(scope.raw);scope.path.chmod(0o600)
        return evidence(),{}
    monkeypatch.setattr(m.selection_proof,'prepare',prepare)
    store,fds=allocated()
    try:
        with pytest.raises(m.guard_module.Refused):m.source_observation(fds,time.monotonic()+20)
        assert os.fstat(fds[0]).st_size==0
    finally:store.__exit__()


@pytest.mark.parametrize('normal', [False,None,1])
def test_source_normal_return_is_exact_boolean(scope,normal):
    value=source();value['observation']['source_guard_normal_return']=normal
    value['source_metadata_pin']=m.pin(m.canonical(value['observation']))
    fail('source_metadata',lambda:m.validate_source(value))


@pytest.mark.parametrize('second',[False,True])
def test_provider_and_authentication_full_round_trip(scope,monkeypatch,second):
    store,fds=allocated();supplied=seed_store(store,fds);raw1,raw2=responses(scope.selection,second=second);seen=[]
    monkeypatch.setattr(m,'_ca_bytes',lambda:b'synthetic')
    def fetch(request,phase,state,ca,deadline):
        seen.append(phase);state['HTTP_statuses'].append({'phase':phase,'status':200})
        return raw1 if phase==1 else raw2
    monkeypatch.setattr(m,'_fetch',fetch)
    try:
        state=m.provider_observation(fds,m._provider_state(),supplied,time.monotonic()+40)
        assert seen==([1,2] if second else [1])
        assert state['completed_body_bytes']==len(raw1)+len(raw2)
        assert m._read(fds[3],8192,time.monotonic()+5).count(b'\n')==len(seen)
        summary=m.authenticate_observation(fds,supplied,state,time.monotonic()+40)
        assert summary['phase_count']==len(seen) and summary['original_case_count']==5
        assert summary['corroboration_pair_count']==5
        assert all(summary[key] is False for key in m.FALSE_FLAGS)
        assert m.pin(m._read(fds[6],m.MAX_PRIVATE,time.monotonic()+5))==summary['private_pin']
    finally:
        store.refresh(m.DATA_FILES);store.__exit__()


def test_phase1_parse_refusal_retains_raw_and_never_dispatches_phase2(scope,monkeypatch):
    store,fds=allocated();supplied=seed_store(store,fds);seen=[]
    monkeypatch.setattr(m,'_ca_bytes',lambda:b'synthetic')
    def fetch(request,phase,state,ca,deadline):
        seen.append(phase);state['HTTP_statuses'].append({'phase':phase,'status':200});return b'bad-json'
    monkeypatch.setattr(m,'_fetch',fetch);state=m._provider_state()
    try:
        with pytest.raises(m.hierarchy.Refused):m.provider_observation(fds,state,supplied,time.monotonic()+30)
        assert seen==[1] and state['response_pins']=={'1':m.pin(b'bad-json')}
        assert m._read(fds[1],20,time.monotonic()+5)==b'bad-json'
        m.validate_provider(state)
    finally:store.refresh(m.DATA_FILES);store.__exit__()


def test_parent_rehashes_same_size_seed_before_provider(scope,monkeypatch):
    monkeypatch.setattr(m,'preflight',lambda *args:None);seen=[]
    def child(a,store,role,payload,runtime,deadline):
        seen.append(role);supplied=source();fds=[store.held[name]['fd'] for name in m.DATA_FILES]
        bad=bytearray(scope.seed);bad[-2]^=1
        m._write(fds[0],bytes(bad));m._write(fds[5],m.canonical(supplied['observation']));store.refresh(m.DATA_FILES)
        value=packet(role,supplied);return value,actual(value)
    monkeypatch.setattr(m,'_child',child)
    outcome=m.run(args(),time.monotonic()+50)
    assert seen==['source'] and outcome['failure']['failure_code']=='source_metadata'


@pytest.mark.parametrize('method',['source','provider','authenticate','validate'])
def test_native_scopes_and_keychains(method):
    policy=m.native_profile(method)
    assert '/private/var/run/mDNSResponder' in policy if method=='provider' else '(deny network*)' in policy
    assert '/usr/bin/security' in policy and '/Users/sheltonchen/Library/Keychains' in policy
    if method=='source':assert m.SOURCE_PLAN['ad_selection']['relative_path'] in policy
    if method=='validate':assert '(deny file-read* (subpath "'+str(m.ROOT/'artifacts')+'"))' in policy


def session_response(monkeypatch,status,*,raw=b'[]',headers=None):
    session=m._session(m._ca_bytes());adapter=session.get_adapter(m.ENDPOINT);reads=[]
    class Raw:
        def stream(self,*args,**kwargs):reads.append('body');yield raw
        def close(self):pass
        def release_conn(self):pass
    def send(request,**kwargs):
        assert request.url==m.ENDPOINT and request.method=='POST' and kwargs['stream'] is True
        response=requests.Response();response.status_code=status;response.url=request.url;response.request=request
        response.raw=Raw();response.headers=headers or {};return response
    monkeypatch.setattr(adapter,'send',send)
    monkeypatch.setattr(m,'_session',lambda ca:session)
    return session,reads


@pytest.mark.parametrize('status',[301,302,401,403,429,500])
def test_failed_status_body_unread_and_numeric_status_retained(monkeypatch,status):
    session,reads=session_response(monkeypatch,status,headers={'Location':'https://example.invalid/not-followed'})
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    state=m._provider_state();body=m._request_bytes(m.hierarchy.mapping_jobs(sorted(figis(9))))
    fail('http_refused',lambda:m._fetch(body,1,state,b'unused',time.monotonic()+10))
    assert reads==[] and state['HTTP_statuses']==[{'phase':1,'status':status}]
    assert session.trust_env is False


def test_cookie_failed_status_precedes_session_cookie_refusal(monkeypatch):
    session,reads=session_response(monkeypatch,403)
    adapter=session.get_adapter(m.ENDPOINT);base=adapter.send
    def send(request,**kwargs):
        result=base(request,**kwargs);session.cookies.set('synthetic','cookie');return result
    monkeypatch.setattr(adapter,'send',send);monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    state=m._provider_state()
    fail('http_refused',lambda:m._fetch(m._request_bytes(m.hierarchy.mapping_jobs(sorted(figis(9)))),1,state,b'unused',time.monotonic()+10))
    assert state['HTTP_statuses']==[{'phase':1,'status':403}] and reads==[]


@pytest.mark.parametrize('headers,code',[
    ({'Content-Encoding':'gzip'},'response'),({'Content-Length':'99999999'},'body_bound'),
    ({'Content-Length':'3'},'body_bound'),({'Set-Cookie':'synthetic'},'response')])
def test_success_body_bounds_and_headers(monkeypatch,headers,code):
    _,reads=session_response(monkeypatch,200,raw=b'[]',headers=headers)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    state=m._provider_state()
    fail(code,lambda:m._fetch(m._request_bytes(m.hierarchy.mapping_jobs(sorted(figis(9)))),1,state,b'unused',time.monotonic()+10))
    assert len(reads)<=1


def test_transport_error_is_finite_and_has_no_raw_secret(monkeypatch):
    session=m._session(m._ca_bytes())
    def send(*args,**kwargs):raise requests.ConnectionError('SYNTHETIC-DO-NOT-OUTPUT')
    monkeypatch.setattr(session,'send',send);monkeypatch.setattr(m,'_session',lambda ca:session)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    state=m._provider_state()
    with pytest.raises(m.Refused) as error:
        m._fetch(m._request_bytes(m.hierarchy.mapping_jobs(sorted(figis(9)))),1,state,b'unused',time.monotonic()+10)
    assert m.finite(error.value).startswith('transport_')
    assert b'SYNTHETIC-DO-NOT-OUTPUT' not in m.canonical(state)
    assert state['HTTP_statuses']==[]


def test_request_has_only_exact_public_identifier_fields():
    jobs=m.hierarchy.mapping_jobs(sorted(figis(9)));raw=m._request_bytes(jobs)
    assert json.loads(raw)==jobs and all(set(job)=={'idType','idValue','includeUnlistedEquities'} for job in jobs)
    jobs[0]['ticker']='SYNTH';fail('request',lambda:m._request_bytes(jobs))


def test_claim_and_inherited_start_cannot_be_replayed(scope):
    store,fds=allocated()
    try:
        a=args();payload=m.canonical({});role='source'
        intent={**m.binding(a),'role':role,'input_pin':m.pin(payload)}
        store.write(role+'-intent.json',intent);started=store.create(role+'-started.json')
        a.control_fd,a.claim_fd,a.intent_fd,a.started_fd=store.fd,store.held['claim.json']['fd'],store.held[role+'-intent.json']['fd'],started
        a.data_fds=tuple(fds)
        m._inherited(a,role,payload,time.monotonic()+5)
        fail('worker_scope',lambda:m._inherited(a,role,payload,time.monotonic()+5))
    finally:store.refresh(('source-started.json',));store.__exit__()


def test_tampered_inherited_intent_refuses(scope):
    store,fds=allocated()
    try:
        a=args();payload=m.canonical({});role='source'
        store.write(role+'-intent.json',{'wrong':'intent'});started=store.create(role+'-started.json')
        a.control_fd,a.claim_fd,a.intent_fd,a.started_fd=store.fd,store.held['claim.json']['fd'],store.held[role+'-intent.json']['fd'],started
        a.data_fds=tuple(fds)
        fail('worker_scope',lambda:m._inherited(a,role,payload,time.monotonic()+5))
    finally:store.__exit__()


def test_spawn_failure_retains_finite_unspawned_metadata(monkeypatch):
    def spawn(*args,**kwargs):raise OSError('DO-NOT-OUTPUT')
    monkeypatch.setattr(m.subprocess,'Popen',spawn)
    result,observed=m._capture_child(['synthetic'],{},b'{}',[],1)
    assert result=={'capture_failure':'spawn_refused'} and observed['actual_exit'] is None and observed['spawn_observed'] is False
    assert b'DO-NOT-OUTPUT' not in m.canonical(result)


@pytest.mark.parametrize('which',['source','provider','authenticate'])
def test_packet_actual_exit_and_output_hash_join_refuse(which):
    value={'binding':m.binding(args()),'outside_failure':'deadline'};observed=actual(value,2)
    m._packet_join(value,observed,args(),which)
    bad=copy.deepcopy(observed);bad['actual_exit']=0;fail('output',lambda:m._packet_join(value,bad,args(),which))
    bad=copy.deepcopy(observed);bad['stdout_sha256']='0'*64;fail('output',lambda:m._packet_join(value,bad,args(),which))


@pytest.mark.parametrize('exit',[0,1,-9,None,True])
def test_failure_envelope_cannot_be_success(exit):
    state={'stage':'claim','source':None,'source_actual':None,'provider':None,'provider_actual':None,
        'authentication':None,'authentication_actual':None,'child_packets':{}}
    value={'binding':m.binding(args()),'outcome':{'failure':{'failure_code':'deadline','state':state,
        'claim_consumed':True,'provider_request_count':None,**m.FALSE_FLAGS}}}
    raw=m.canonical(value)+b'\n'
    if exit==0 or exit!=2:fail('output',lambda:m.validate_output(raw,exit,args()))


def test_external_nonzero_failure_retained_exactly():
    raw=m.canonical({'binding':m.binding(args()),'outside_failure':'deadline'})+b'\n'
    assert m.validate_output(raw,2,args())['outside_failure']=='deadline'


def test_unknown_exception_text_is_not_diagnostic():
    assert m.finite(ValueError('private'))=='unknown'
    class Foreign(m.Refused):pass
    assert m.finite(Foreign('deadline'))=='unknown'
    assert m.finite(m.admitted.helpers.Deadline())=='deadline'


def test_no_old_operational_calls_or_credentials_in_new_entrypoints():
    source=inspect.getsource(m)
    assert 'keychain.load_key' not in source and '--credential-fd' not in source
    assert 'selection_proof.run(' not in source and 'previous.run(' not in source
    assert "ar._credential_free()" in source
    assert "canonical(row)+b'\\n'" in source


def _safe_child_environment():
    return {'PATH':'/usr/bin:/bin','LANG':'en_US.UTF-8','LC_ALL':'en_US.UTF-8'}


def test_real_nonreading_child_stdin_deadline_kills_and_reaps(monkeypatch):
    children=[];original=m.subprocess.Popen
    def tracked(*args,**kwargs):
        process=original(*args,**kwargs);children.append(process);return process
    monkeypatch.setattr(m.subprocess,'Popen',tracked)
    started=time.monotonic()
    result,observed=m._capture_child([sys.executable,'-B','-c','import time; time.sleep(5)'],
        _safe_child_environment(),b'x'*m.MAX_FRAME,[],.15)
    assert result=={'capture_failure':'deadline'} and observed['bound']=='deadline'
    assert time.monotonic()-started<2 and observed['actual_exit'] is not None
    assert len(children)==1 and children[0].poll()==observed['actual_exit']


def test_real_noisy_child_is_bounded_killed_and_reaped(monkeypatch):
    children=[];original=m.subprocess.Popen
    def tracked(*args,**kwargs):
        process=original(*args,**kwargs);children.append(process);return process
    monkeypatch.setattr(m.subprocess,'Popen',tracked)
    result,observed=m._capture_child([sys.executable,'-B','-c',
        'import os,time;os.write(1,b"x"*'+str(m.MAX_FRAME+1)+');time.sleep(5)'],
        _safe_child_environment(),b'',[],2)
    assert result=={'capture_failure':'worker_packet'} and observed['bound']=='output_bound'
    assert observed['stdout_bytes']==m.MAX_FRAME and children[0].poll()==observed['actual_exit']


@pytest.mark.parametrize('suffix',[b'extra\n',b'\n'])
def test_real_trailing_child_output_is_not_packet(suffix):
    raw=m.canonical({'synthetic':'metadata'})+b'\n'+suffix
    result,observed=m._capture_child([sys.executable,'-B','-c','import os;os.write(1,'+repr(raw)+')'],
        _safe_child_environment(),b'',[],2)
    assert result=={'capture_failure':'worker_packet'} and observed['actual_exit']==0


def test_real_child_exit_two_is_preserved_and_not_success():
    value={'binding':m.binding(args()),'outside_failure':'deadline'};raw=m.canonical(value)+b'\n'
    result,observed=m._capture_child([sys.executable,'-B','-c',
        'import os,sys;os.write(1,'+repr(raw)+');sys.exit(2)'],_safe_child_environment(),b'',[],2)
    assert result==value and observed['actual_exit']==2
    m._packet_join(result,observed,args(),'source')
    fail('output',lambda:m._actual(observed,zero=True))


@pytest.mark.parametrize('tamper',[False,True])
def test_real_child_exact_inherited_FDs_and_started_marker(scope,tamper):
    public_root=Path(inspect.getfile(m)).parents[1];store,fds=allocated()
    try:
        a=args();payload=m.canonical({});role='source'
        store.write(role+'-intent.json',{'tampered':True} if tamper else {**m.binding(a),'role':role,'input_pin':m.pin(payload)})
        started=store.create(role+'-started.json')
        inherited=[store.fd,store.held['claim.json']['fd'],store.held[role+'-intent.json']['fd'],started,*fds]
        child_args={**vars(a),'control_fd':inherited[0],'claim_fd':inherited[1],'intent_fd':inherited[2],
            'started_fd':started,'data_fds':tuple(fds)}
        code='import sys,time;from pathlib import Path;from types import SimpleNamespace as NS;sys.path.insert(0,'+repr(str(public_root))+');'
        code+='from scripts import run_arv2_r327_public_figi_hierarchy as m;m.CONTROL=Path('+repr(str(m.CONTROL))+');'
        code+='a=NS(**'+repr(child_args)+');raw=sys.stdin.buffer.read();\n'
        code+='try:\n m._inherited(a,"source",raw,time.monotonic()+5);m.emit({"descriptor_count":11,"nonce_sha256":m.sha(raw)})\n'
        code+='except m.Refused as error:\n m.emit({"refused":m.finite(error)});raise SystemExit(2)\n'
        result,observed=m._capture_child([sys.executable,'-B','-c',code],_safe_child_environment(),payload,inherited,5)
        assert observed['stderr_bytes']==0
        if tamper:assert result=={'refused':'worker_scope'} and observed['actual_exit']==2
        else:
            assert result=={'descriptor_count':11,'nonce_sha256':m.sha(payload)} and observed['actual_exit']==0
            assert os.fstat(started).st_size>0
    finally:store.refresh(('source-started.json',));store.__exit__()


def test_success_auth_counts_bind_exact_selected_scope(scope,monkeypatch):
    store,fds=allocated();supplied=seed_store(store,fds);raw1,_=responses(scope.selection)
    monkeypatch.setattr(m,'_ca_bytes',lambda:b'synthetic')
    def fetch(request,phase,state,ca,deadline):
        state['HTTP_statuses'].append({'phase':phase,'status':200});return raw1
    monkeypatch.setattr(m,'_fetch',fetch)
    try:
        provider=m.provider_observation(fds,m._provider_state(),supplied,time.monotonic()+40)
        summary=m.authenticate_observation(fds,supplied,provider,time.monotonic()+40)
        invalid=copy.deepcopy(summary);invalid['corroboration_counts']={'invented_category':5}
        fail('output',lambda:m.validate_authentication(invalid,supplied,provider))
        invalid=copy.deepcopy(summary);invalid['corroboration_pair_count']=6
        invalid['corroboration_counts']={next(iter(summary['corroboration_counts'])):6}
        fail('output',lambda:m.validate_authentication(invalid,supplied,provider))
    finally:store.refresh(m.DATA_FILES);store.__exit__()


@pytest.mark.parametrize('field',['url','body','header'])
def test_prepared_request_tamper_refuses_before_send(monkeypatch,field):
    session=m._session(m._ca_bytes());original=session.prepare_request;called=[]
    def prepare(request):
        prepared=original(request)
        if field=='url':prepared.url='https://example.invalid/not-authorized'
        elif field=='body':prepared.body=b'[]'
        else:prepared.headers['Authorization']='Synthetic forbidden header'
        return prepared
    def send(*args,**kwargs):called.append(True);raise AssertionError('send must not occur')
    monkeypatch.setattr(session,'prepare_request',prepare);monkeypatch.setattr(session,'send',send)
    monkeypatch.setattr(m,'_session',lambda ca:session)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    request=m._request_bytes(m.hierarchy.mapping_jobs(sorted(figis(9))))
    fail('request',lambda:m._fetch(request,1,m._provider_state(),b'unused',time.monotonic()+10))
    assert called==[]


def test_maximum_two_phase_job_inventory_fits_external_frame(scope,monkeypatch):
    store,fds=allocated();supplied=seed_store(store,fds)
    initial=scope.selection['figis'];derived=sorted(figis(18)[9:]);share=figis(19)[18]
    raw1=m.canonical([{'data':[row(claim,composite=composite,exchange='LN',share=share)]}
        for claim,composite in zip(initial,derived,strict=True)])
    raw2=m.canonical([{'data':[row(composite,share=share)]} for composite in derived]);seen=[]
    monkeypatch.setattr(m,'_ca_bytes',lambda:b'synthetic')
    def fetch(request,phase,state,ca,deadline):
        seen.append(phase);state['HTTP_statuses'].append({'phase':phase,'status':200})
        return raw1 if phase==1 else raw2
    monkeypatch.setattr(m,'_fetch',fetch)
    try:
        provider=m.provider_observation(fds,m._provider_state(),supplied,time.monotonic()+50)
        authentication=m.authenticate_observation(fds,supplied,provider,time.monotonic()+50)
        assert seen==[1,2] and provider['phase2_job_count']==9
        assert [item['job_count'] for item in provider['phase_summaries']]==[9,9]
        children={'source':packet('source',supplied),'provider':packet('provider',provider),
            'authenticate':packet('authenticate',authentication)}
        result={'schema':m.SCHEMA,'stage':'postflight','source':supplied,'source_actual':actual(children['source']),
            'provider':provider,'provider_actual':actual(children['provider']),
            'authentication':authentication,'authentication_actual':actual(children['authenticate']),
            'child_packets':children,'prior_context':m.source_context(),'provider_request_count':None,
            'post_checks_complete':True,**m.FALSE_FLAGS}
        m.validate_result(result,args())
        report=m.pin(m.canonical({**m.binding(args()),'result':result}))
        raw=m.canonical({'binding':m.binding(args()),'outcome':{'result':result,'report':report}})+b'\n'
        assert 10000<len(raw)<=m.MAX_FRAME
        assert m.validate_output(raw,0,args())['outcome']['result']==result
        fail('output',lambda:m.validate_output(raw,2,args()))
    finally:store.refresh(m.DATA_FILES);store.__exit__()


def test_source_nonzero_actual_stops_before_provider(scope,monkeypatch):
    monkeypatch.setattr(m,'preflight',lambda *args:None);seen=[]
    def child(a,store,role,payload,runtime,deadline):
        seen.append(role);value=packet(role,source())
        return value,actual(value,2)
    monkeypatch.setattr(m,'_child',child)
    outcome=m.run(args(),time.monotonic()+40)
    assert seen==['source'] and outcome['failure']['failure_code']=='output'
