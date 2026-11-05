"""Synthetic AU protocol/privacy/semantic boundaries; no API or private DATA."""
import copy
from decimal import Decimal
import inspect
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_r298_eodhd_history_diagnostic as m


def fails(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def bodies():
    meta=[{'Code':'SPY','Name':'Synthetic fund','Country':'USA','Exchange':'NYSE ARCA',
        'Currency':'USD','Type':'ETF','Isin':m.EXPECTED_ISIN}]
    history=[{'date':day,'open':300,'high':302,'low':299,'close':300.125,
        'adjusted_close':275.75,'volume':100} for day in m.DATES]
    return json.dumps(meta).encode(),json.dumps(history).encode()


def provider():
    meta,history=bodies();value=m._provider_state();value.update(application_dispatch_intents=2,
        completed_HTTP200_bodies=2,current_ordinal=1,HTTP_status_type='int',HTTP_status=200,
        body_pins=[m.pin(meta),m.pin(history)],journal_pin=m.pin(b'journal'))
    return value


def args():return NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def packet(role,result,code=None):return {'binding':m.binding(args()),'role':role,'result':result,'failure_code':code}


def actual(value,exit=0):
    raw=m.canonical(value)+b'\n'
    return {'actual_exit':exit,'spawn_observed':True,'bound':None,'stdout_bytes':len(raw),
        'stdout_sha256':m.sha(raw),'stderr_bytes':0,'stderr_sha256':m.sha(b'')}


def result():
    p=provider();a=m.analyse(*bodies());packets={'provider':packet('provider',p),'authenticate':packet('authenticate',a)}
    return {'schema':m.SCHEMA,'stage':'postflight','credential_handoff_complete':True,
        'provider':p,'provider_actual':actual(packets['provider']),'authentication':a,
        'authentication_actual':actual(packets['authenticate']),'child_packets':packets,
        'source_context':m.source_context(),'provider_request_count':None,'post_checks_complete':True,**m.FALSE_FLAGS}


def envelope(value):
    return m.canonical({'binding':m.binding(args()),'outcome':{'result':value,
        'report':m.pin(m.canonical({**m.binding(args()),'result':value}))}})+b'\n'


def test_exact_fixed_scope_source_chain_and_inert_import():
    assert m.CONTROL.name=='R326-20261027-AU' and len(m.REQUESTS)==2
    assert m.request_record(0)=={'ordinal':0,'endpoint':'https://eodhd.com/api/exchange-symbol-list/US',
        'parameters':{'fmt':'json','symbols':'SPY','delisted':'0','type':'etf'}}
    assert m.request_record(1)['parameters']=={'fmt':'json','from':'2020-12-31','to':'2021-01-08','period':'d','order':'a'}
    assert m.source_context()['AR_AS_fact_sha256']==m.ANCHOR_FACT_SHA256
    selected=m.pins();assert len(selected)==202
    assert all(m.sha((m.ROOT/name).read_bytes())==value for name,value in selected.items())
    assert m.profile_record()['existing_keychain_service']=='trading-agent-eodhd'
    assert m.profile_record()['maximum_body_bytes']==65536


@pytest.mark.parametrize('change',('AS_exit','AR_exit','validator_exit','stdout','permission','output'))
def test_AR_AS_complete_external_proof_cannot_be_refreshed_or_waived(monkeypatch,change):
    fact=m.anchor.observed_fact();out=m.anchor.sidecar_output()
    if change=='AS_exit':fact['AS_actual']['actual_exit']=2
    elif change=='AR_exit':fact['AR_producer']['actual_exit']=2
    elif change=='validator_exit':fact['AR_native_validator']['actual_exit']=71
    elif change=='stdout':fact['AS_actual']['stdout_sha256']='d'*64
    elif change=='permission':fact['QC_processing_rights_granted']=True
    else:out['outcome']['report']['sha256']='e'*64
    monkeypatch.setattr(m.anchor,'observed_fact',lambda:fact);monkeypatch.setattr(m.anchor,'sidecar_output',lambda:out)
    fails('source_binding',m.source_context)


def test_raw_close_six_dates_and_Isin_are_used_without_exporting_rows():
    value=m.analyse(*bodies());m.validate_authentication(value,provider())
    assert value['identity_matched'] is value['expected_date_coverage'] is True
    assert value['positive_RAW_close_count']==value['history_row_count']==6
    raw=m.canonical(value)
    assert b'300.125' not in raw and b'275.75' not in raw and b'Synthetic fund' not in raw
    assert b'"Isin"' not in raw and b'"close"' not in raw
    assert all(value[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('ordinal,intents,completed',((None,1,0),(None,1,1),(None,2,2),
    (0,2,0),(0,2,1),(0,2,2),(1,0,0),(1,1,0),(1,2,0)))
def test_failed_provider_phase_cannot_claim_impossible_dispatch_or_completed_count(ordinal,intents,completed):
    value=m._provider_state();value.update(current_ordinal=ordinal,application_dispatch_intents=intents,
        completed_HTTP200_bodies=completed,body_pins=[m.pin(b'synthetic-body') for _ in range(completed)])
    fails('output',lambda:m.validate_provider(value))


@pytest.mark.parametrize('ordinal,intents,completed',((None,0,0),(0,0,0),(0,1,0),(0,1,1),
    (1,1,1),(1,2,1),(1,2,2)))
def test_failed_provider_phase_preserves_reachable_before_and_after_intent_states(ordinal,intents,completed):
    value=m._provider_state();value.update(current_ordinal=ordinal,application_dispatch_intents=intents,
        completed_HTTP200_bodies=completed,body_pins=[m.pin(b'synthetic-body') for _ in range(completed)])
    assert m.validate_provider(value)==value


@pytest.mark.parametrize('change',('null_ISIN','wrong_ISIN','wrong_Code','wrong_Type','wrong_Currency','uppercase_ISIN'))
def test_identity_unknown_retains_independent_native_history_evidence(change):
    meta,history=bodies();value=json.loads(meta);row=value[0]
    if change=='null_ISIN':row['Isin']=None
    elif change=='wrong_ISIN':row['Isin']='US0000000000'
    elif change=='wrong_Code':row['Code']='OTHER'
    elif change=='wrong_Type':row['Type']='Common Stock'
    elif change=='wrong_Currency':row['Currency']='CAD'
    else:row['ISIN']=row.pop('Isin')
    result=m.analyse(json.dumps(value).encode(),history)
    assert result['identity_matched'] is False and result['identity_status']=='unresolved'
    assert result['history_schema_valid'] is result['expected_date_coverage'] is True
    assert result['positive_RAW_close_count']==6 and result['RAW_close_series_sha256'] is not None


@pytest.mark.parametrize('change',('missing','extra','duplicate','reverse','weekend','invalid_date','adjusted_only','string_close',
    'bool_close','zero','negative','nan','oversized_number','too_precise'))
def test_history_incomplete_or_invalid_never_gains_coverage_and_keeps_identity(change):
    meta,history=bodies();rows=json.loads(history)
    if change=='missing':rows.pop()
    elif change=='extra':rows.append(dict(rows[-1],date='2021-01-09'))
    elif change=='duplicate':rows[-1]['date']=rows[0]['date']
    elif change=='reverse':rows.reverse()
    elif change=='weekend':rows[-1]['date']='2021-01-02'
    elif change=='invalid_date':rows[-1]['date']='2021-99-99'
    elif change=='adjusted_only':rows[-1].pop('close')
    elif change=='string_close':rows[-1]['close']='300.125'
    elif change=='bool_close':rows[-1]['close']=True
    elif change=='zero':rows[-1]['close']=0
    elif change=='negative':rows[-1]['close']=-1
    elif change=='nan':rows[-1]['close']=float('nan')
    elif change=='oversized_number':rows[-1]['close']=1e99
    else:rows[-1]['close']=1e-13
    value=m.analyse(meta,json.dumps(rows).encode())
    assert value['identity_matched'] is True and value['expected_date_coverage'] is False
    assert all(value[key] is False for key in m.FALSE_FLAGS)


def test_decimal_exactness_uses_close_not_adjusted_close_and_rejects_duplicate_keys():
    meta,history=bodies();a=m.analyse(meta,history)
    changed=json.loads(history)
    for row in changed:row['adjusted_close']=0.01
    b=m.analyse(meta,json.dumps(changed).encode())
    assert a['RAW_close_series_sha256']==b['RAW_close_series_sha256']
    bad=history.replace(b'"close": 300.125',b'"close": 1,"close": 300.125',1)
    assert m.analyse(meta,bad)['history_schema_valid'] is False
    decoded=m._decode(b'[0.123456789012]','history_shape');assert decoded==[Decimal('0.123456789012')]


class Response:
    def __init__(self,prepared,status,body,headers=None):
        self.request,self.url,self.history,self.status_code=prepared,prepared.url,[],status
        self.headers={} if headers is None else headers;self.raw_body=body;self.reads=0
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def iter_content(self,chunk_size):
        self.reads+=1
        for offset in range(0,len(self.raw_body),max(1,chunk_size//2)):yield self.raw_body[offset:offset+max(1,chunk_size//2)]
    @property
    def content(self):pytest.fail('content read')
    def json(self):pytest.fail('network-role JSON parse')


@pytest.fixture
def fetch_scope(monkeypatch):
    observed=[];configuration={'status':200,'body':b'[]','headers':{}}
    def send(session,prepared,**kwargs):
        assert kwargs['stream'] is True and kwargs['allow_redirects'] is False and kwargs['verify'] is True and kwargs['proxies']=={}
        assert 0<kwargs['timeout']<=25
        response=Response(prepared,**configuration);observed.append(response);return response
    monkeypatch.setattr(m.OwnedSession,'send',send)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    return configuration,observed


@pytest.mark.parametrize('status',(301,302,401,403,429,500,True,'200',999))
def test_numeric_HTTP_refusal_or_malformed_status_has_no_body_read(fetch_scope,status):
    config,seen=fetch_scope;config['status']=status;state=m._provider_state()
    with pytest.raises(m.Refused):m.fetch(0,'synthetic-safe-token',state,m._ca_bytes(),time.monotonic()+20)
    assert seen[0].reads==0 and state['HTTP_status']==(status if type(status) is int and 100<=status<=599 else None)
    m.validate_provider(state)


@pytest.mark.parametrize('encoding',('raw','url','json','csv','json_in_csv'))
def test_recognized_secret_echo_refuses_before_retention(fetch_scope,encoding):
    config,_=fetch_scope;key='synthetic-quote"token&'
    variants=m.ap._secret_encodings(key)
    if encoding=='raw':payload=key.encode()
    elif encoding=='url':payload=m.urlencode({'x':key}).split('=',1)[1].encode()
    elif encoding=='json':payload=json.dumps(key).encode()
    elif encoding=='csv':payload=key.encode().replace(b'"',b'""')
    else:payload=json.dumps(key).encode().replace(b'"',b'""')
    config['body']=b'{"synthetic":"'+payload+b'"}'
    fails('credential_echo',lambda:m.fetch(0,key,m._provider_state(),m._ca_bytes(),time.monotonic()+20))
    assert any(secret in config['body'] for secret in variants)


@pytest.mark.parametrize('issue',('oversize','length','gzip','cookie','header_echo'))
def test_success_body_transport_bounds_and_header_secret_refusals(fetch_scope,issue):
    config,seen=fetch_scope;key='synthetic-safe-token'
    if issue=='oversize':config['body']=b'x'*(m.MAX_BODY+1)
    elif issue=='length':config['headers']={'Content-Length':'3'}
    elif issue=='gzip':config['headers']={'Content-Encoding':'gzip'}
    elif issue=='cookie':config['headers']={'Set-Cookie':'x=y'}
    else:config['headers']={'X-Unknown':key}
    with pytest.raises(m.Refused):m.fetch(1,key,m._provider_state(),m._ca_bytes(),time.monotonic()+20)
    if issue in ('gzip','cookie','header_echo'):assert seen[0].reads==0


def test_owned_session_is_no_proxy_no_retries_no_redirect_body_and_pinned_CA():
    with m._session(m._ca_bytes()) as session:
        m._session_check(session,m.HOST+'/api/eod/SPY.US')
        assert tuple(session.resolve_redirects(None,None))==()
        session.trust_env=True
        fails('request',lambda:m._session_check(session,m.HOST+'/api/eod/SPY.US'))
    fails('public_CA',lambda:m.OwnedAdapter(b'not-pinned'))


@pytest.mark.parametrize('status',(301,302))
def test_real_Requests_send_redirect_path_never_consumes_refused_body(monkeypatch,status):
    observed=[]
    def send(adapter,prepared,**kwargs):
        response=m.requests.Response();response.status_code=status;response.url=prepared.url;response.request=prepared
        response.headers=m.requests.structures.CaseInsensitiveDict({'Location':'https://eodhd.com/api/elsewhere'})
        response.raw=NS(read=lambda *_args,**_kwargs:pytest.fail('redirect secretly read refused body'),
            close=lambda:None,release_conn=lambda:None)
        observed.append(response);return response
    monkeypatch.setattr(m.OwnedAdapter,'send',send)
    fails('http_refused',lambda:m.fetch(0,'synthetic-safe-token',m._provider_state(),m._ca_bytes(),time.monotonic()+20))
    assert len(observed)==1 and observed[0]._content_consumed is False


@pytest.mark.parametrize('role',('provider','authenticate','validate'))
def test_native_role_egress_and_artifact_boundaries_are_exact(role):
    policy=m.native_profile(role)
    assert '(deny process-exec (literal "/usr/bin/security"))' in policy and '/Library/Keychains' in policy
    assert ('/private/var/run/mDNSResponder' in policy) is (role=='provider')
    assert ('remote tcp "*:443"' in policy) is (role=='provider')
    assert ('(deny network*)' in policy) is (role!='provider')
    assert '/R326-20261027-AR/' not in policy and '/R326-20261027-AP/' not in policy
    assert str(m.ar.worker.previous.PACKAGE) not in policy
    assert (str(m.CONTROL) in policy) is (role!='validate')


@pytest.fixture
def store_scope(monkeypatch,tmp_path):
    monkeypatch.setattr(m,'CONTROL',tmp_path/'parent'/'AU')
    monkeypatch.setattr(m,'_security',lambda fd:('synthetic',))
    def walk(path):
        chain=tuple((os.stat(Path(*path.parts[:i+1])).st_dev,os.stat(Path(*path.parts[:i+1])).st_ino) for i in range(1,len(path.parts)))
        return os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW),chain
    monkeypatch.setattr(m.admitted,'_storage_module',lambda:NS(_walk=walk));return m.CONTROL


def test_two_bodies_retained_before_any_semantics_and_one_fsynced_intent_each(store_scope,monkeypatch):
    seen=[];raws=bodies();monkeypatch.setattr(m,'_ca_bytes',lambda:b'syntheticCA')
    def fetch(ordinal,key,state,ca,deadline):
        seen.append(ordinal);assert state['application_dispatch_intents']==ordinal+1
        state.update(HTTP_status_type='int',HTTP_status=200);return raws[ordinal]
    monkeypatch.setattr(m,'fetch',fetch)
    monkeypatch.setattr(m,'analyse',lambda *_:pytest.fail('provider parsed response'))
    with m.Store() as store:
        store.write('claim.json',m.binding(args()));fds=[store.create(name) for name in m.DATA_FILES]
        state=m.provider_observation(fds,'synthetic-token',m._provider_state(),time.monotonic()+20)
        store.refresh(m.DATA_FILES);assert seen==[0,1]
        assert [m._read(fd,m.MAX_BODY,time.monotonic()+20) for fd in fds[:2]]==list(raws)
        journal=m._read(fds[2],m.MAX_JOURNAL,time.monotonic()+20)
        assert len(journal.splitlines())==2 and state['body_pins']==[m.pin(raw) for raw in raws]


def test_first_refusal_is_one_intent_no_second_request_and_no_body_write(store_scope,monkeypatch):
    seen=[];monkeypatch.setattr(m,'_ca_bytes',lambda:b'syntheticCA')
    def fetch(ordinal,*_):seen.append(ordinal);raise m.Refused('http_refused')
    monkeypatch.setattr(m,'fetch',fetch)
    with m.Store() as store:
        store.write('claim.json',m.binding(args()));fds=[store.create(name) for name in m.DATA_FILES];state=m._provider_state()
        fails('http_refused',lambda:m.provider_observation(fds,'synthetic-token',state,time.monotonic()+20))
        store.refresh(m.DATA_FILES);assert seen==[0] and state['application_dispatch_intents']==1
        assert state['completed_HTTP200_bodies']==0 and all(os.fstat(fd).st_size==0 for fd in fds[:2])


def test_success_output_needs_actual_parent_and_every_child_packet_pin():
    value=result();raw=envelope(value);m.validate_output(raw,0,args())
    fails('output',lambda:m.validate_output(raw,2,args()))
    for field in ('provider_actual','authentication_actual'):
        for change in ('exit','hash'):
            bad=copy.deepcopy(value)
            if change=='exit':bad[field]['actual_exit']=2
            else:bad[field]['stdout_sha256']='f'*64
            with pytest.raises((m.Refused,m.ap.Refused)):m.validate_output(envelope(bad),0,args())


def test_unresolved_identity_failure_keeps_history_and_joins_actual_auth2():
    p=provider();meta,history=bodies();rows=json.loads(meta);rows[0]['Isin']=None
    summary=m.analyse(json.dumps(rows).encode(),history);summary['body_pins']=p['body_pins']
    pp=packet('provider',p);aa=packet('authenticate',summary,'diagnostic_incomplete')
    state={'stage':'authenticate','credential_handoff_complete':True,'provider':p,'provider_actual':actual(pp),
        'authentication':summary,'authentication_actual':actual(aa,2),'child_packets':{'provider':pp,'authenticate':aa}}
    failed={'failure_code':'diagnostic_incomplete','state':state,'claim_consumed':True,'provider_request_count':None,**m.FALSE_FLAGS}
    raw=m.canonical({'binding':m.binding(args()),'outcome':{'failure':failed}})+b'\n'
    assert m.validate_output(raw,2,args())['outcome']['failure']['state']['authentication']['expected_date_coverage'] is True
    fails('output',lambda:m.validate_output(raw,0,args()))
    bad=copy.deepcopy(failed);bad['state']['child_packets']['authenticate']['failure_code']='unknown'
    with pytest.raises(m.Refused):m.validate_output(m.canonical({'binding':m.binding(args()),'outcome':{'failure':bad}})+b'\n',2,args())


@pytest.mark.parametrize('issue',('none','identity','coverage'))
def test_auth_success_packet_cannot_claim_zero_without_both_independent_predicates(issue):
    value=m.analyse(*bodies())
    if issue=='none':value=None
    elif issue=='identity':value.update(identity_matched=False,identity_status='unresolved')
    else:value['expected_date_coverage']=False
    assert m._safe_packet(packet('authenticate',value),args(),'authenticate')=={'capture_failure':'worker_packet'}


@pytest.mark.parametrize('barrier',('source','credential','provider','authenticate','postflight',None))
def test_parent_claim_and_complete_source_before_one_Keychain_then_actual0_auth_order(store_scope,monkeypatch,barrier):
    events=[];calls=[];good=result()
    monkeypatch.setattr(m,'source_context',lambda:events.append('proof') or good['source_context'])
    def preflight(*_):
        events.append('preflight')
        if barrier=='source' or barrier=='postflight' and len(calls)==2:raise m.Refused('source_pin')
    monkeypatch.setattr(m,'preflight',preflight)
    def keychain(provider,**_):
        events.append('keychain');assert provider=='eodhd' and (store_scope/'claim.json').exists()
        assert 'proof' in events and 'preflight' in events
        if barrier=='credential':raise m.Refused('credential_handoff')
        return 'synthetic-token'
    monkeypatch.setattr(m.keychain,'load_key',keychain)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    def child(a,store,role,payload,runtime,deadline,key=None):
        calls.append(role);events.append(role)
        value=copy.deepcopy(good['child_packets'][role]);code=0
        if barrier==role:
            value['failure_code']='http_refused' if role=='provider' else 'diagnostic_incomplete';code=2
            if role=='authenticate':value['result']['identity_matched']=False;value['result']['identity_status']='unresolved'
        return value,actual(value,code)
    monkeypatch.setattr(m,'_child',child)
    output=m.run(args(),time.monotonic()+100)
    assert ('result' in output) is (barrier is None)
    assert events.count('keychain')<=1 and calls in ([],['provider'],['provider','authenticate'])
    if barrier=='source':assert 'keychain' not in events
    if barrier in ('source','credential'):assert calls==[]
    if barrier=='provider':assert calls==['provider']
    if calls:assert events.index('proof')<events.index('keychain')<events.index('provider')


@pytest.mark.parametrize('role',m.ROLES)
def test_inherited_original_FDs_claim_intent_and_persistent_start_disallow_duplicate_dispatch(store_scope,role):
    a=args();payload={} if role=='provider' else {'provider':provider()};raw=m.canonical(payload)
    with m.Store() as store:
        claim=store.create('claim.json',m.canonical(m.binding(a)))
        data=[store.create(name) for name in m.DATA_FILES]
        intent=store.create(role+'-intent.json',m.canonical({**m.binding(a),'role':role,'input_pin':m.pin(raw)}))
        start=store.create(role+'-started.json');a.control_fd=store.fd;a.claim_fd=claim
        a.intent_fd=intent;a.started_fd=start;a.data_fds=tuple(data)
        m._inherited(a,role,raw,time.monotonic()+20);store.refresh((role+'-started.json',))
        assert os.fstat(start).st_size>0
        fails('worker_scope',lambda:m._inherited(a,role,raw,time.monotonic()+20))


@pytest.mark.parametrize('case',('echo','noise','stderr','timeout'))
def test_real_synthetic_owned_child_capture_is_bounded_hash_only_and_kill_reap(tmp_path,case):
    import sys
    code={'echo':'import sys;sys.stdout.buffer.write(sys.stdin.buffer.read()+b"\\n")',
        'noise':'print("{}\\n{}")','stderr':'import sys;sys.stderr.write("synthetic-noise");print("{}")',
        'timeout':'import time;time.sleep(2)'}[case]
    safe={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TMPDIR':str(tmp_path),'PYTHONDONTWRITEBYTECODE':'1'}
    raw=m.canonical({'synthetic':True})
    packet,observed=m._capture_child([sys.executable,'-B','-c',code],safe,raw,[],.05 if case=='timeout' else 5)
    m.ap._actual(observed)
    assert observed['spawn_observed'] is True
    if case=='echo':assert packet=={'synthetic':True} and observed['actual_exit']==0
    else:assert set(packet)=={'capture_failure'}
    if case=='stderr':assert observed['stderr_bytes']==len(b'synthetic-noise')
    if case=='timeout':assert observed['bound']=='deadline' and observed['actual_exit'] is not None


def test_no_public_token_or_raw_response_in_protocol_profile_and_no_old_operation_call():
    profile=m.canonical(m.profile_record());assert b'api_token' not in profile
    code=inspect.getsource(m)
    assert 'ap.run(' not in code and 'ar.run(' not in code and 'support.run(' not in code
    assert '.json()' not in inspect.getsource(m.fetch) and '_decode(' not in inspect.getsource(m.provider_observation)
    assert 'load_key(\'eodhd\'' in inspect.getsource(m.run)
