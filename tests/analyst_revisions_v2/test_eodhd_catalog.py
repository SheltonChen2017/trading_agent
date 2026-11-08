"""Synthetic whole-US catalog protocol, no provider/private DATA operations."""
import copy
import inspect
import json
import os
from pathlib import Path
import struct
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_r298_eodhd_catalog as m


def fails(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def args():return NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def page(total=1,offset=0,rows=None):
    if rows is None:rows=[{'symbol':'SYNTH.US','isin':None,'figi':None,'cusip':None,'lei':None,'cik':None}
        for _ in range(min(1000,max(0,total-offset)))]
    return m.canonical({'meta':{'total':total,'limit':1000,'offset':offset},'data':rows,'links':{'next':None}})


def fixture(total=1):
    raws=[m.canonical([{'Code':'SYNTH','Name':'Synthetic € fund','Country':'États-Unis','Exchange':'NYSE',
            'Currency':'USD','Type':'Common Stock','Isin':None}]),
        m.canonical([{'Code':'DEAD','Name':'Synthetic delisted','Country':'USA','Exchange':'NASDAQ',
            'Currency':'USD','Type':'Unknown vendor class','Isin':None}])]
    raws.extend(page(total,offset) for offset in range(0,max(total,1),1000))
    capture=bytearray();descriptors=[]
    for ordinal,raw in enumerate(raws):
        descriptors.append({'ordinal':ordinal,'offset':len(capture),'body':m.pin(raw)})
        capture.extend(struct.pack('>Q',len(raw))+raw)
    index=m.canonical({'schema':m.SCHEMA+'-capture-index','bodies':descriptors})
    journal=b''.join(m.canonical({'ordinal':i,'request_sha256':m.sha(m.canonical(m.request_record(i)))})+b'\n'
        for i in range(len(raws)))
    provider=m._provider_state();provider.update(application_dispatch_intents=len(raws),completed_HTTP200_bodies=len(raws),
        current_ordinal=len(raws)-1,HTTP_status_type='int',HTTP_status=200,body_pins=[m.pin(raw) for raw in raws],
        capture_pin=m.pin(bytes(capture)),journal_pin=m.pin(journal),index_pin=m.pin(index),mapping_total=total,
        mapping_pages=len(raws)-2)
    return bytes(capture),index,journal,provider,raws


def observation(total=1):
    capture,index,journal,p,_=fixture(total)
    return m.analyse(capture,index,journal,p,time.monotonic()+20),p


def packet(role,result,code=None):return {'binding':m.binding(args()),'role':role,'result':result,'failure_code':code}


def actual(value,exit=0):
    raw=m.canonical(value)+b'\n'
    return {'actual_exit':exit,'spawn_observed':True,'bound':None,'stdout_bytes':len(raw),
        'stdout_sha256':m.sha(raw),'stderr_bytes':0,'stderr_sha256':m.sha(b'')}


def result():
    a,p=observation();packets={'provider':packet('provider',p),'authenticate':packet('authenticate',a)}
    return {'schema':m.SCHEMA,'stage':'postflight','credential_handoff_complete':True,'provider':p,
        'provider_actual':actual(packets['provider']),'authentication':a,'authentication_actual':actual(packets['authenticate']),
        'child_packets':packets,'source_context':m.source_context(),'provider_request_count':None,
        'post_checks_complete':True,**m.FALSE_FLAGS}


def envelope(value):
    return m.canonical({'binding':m.binding(args()),'outcome':{'result':value,
        'report':m.pin(m.canonical({**m.binding(args()),'result':value}))}})+b'\n'


def test_exact_scope_current_pins_and_no_history_or_search():
    assert m.CONTROL.name=='R326-20261027-AW'
    assert m.request_record(0)['parameters']=={'fmt':'json','delisted':'0'}
    assert m.request_record(1)['parameters']=={'fmt':'json','delisted':'1'}
    assert m.request_record(2)['parameters']=={'fmt':'json','filter[ex]':'US','page[limit]':'1000','page[offset]':'0'}
    assert m.request_record(101)['parameters']['page[offset]']=='99000'
    assert len(m.pins())==204 and m.pins()[m.previous.SOURCE.relative_to(m.ROOT).as_posix()]==m.NEW_PINS[
        m.previous.SOURCE.relative_to(m.ROOT).as_posix()]
    assert all(m.sha((m.ROOT/name).read_bytes())==sha for name,sha in m.pins().items())
    assert all('/api/eod/' not in m.request_record(i)['endpoint'] for i in range(m.MAX_DISPATCHES))
    assert all(key not in m.request_record(0)['parameters'] for key in ('symbols','type','api_token'))
    assert b'api_token' not in m.canonical(m.profile_record())


@pytest.mark.parametrize('ordinal',(-1,102,True,1.0,None))
def test_request_inventory_is_closed(ordinal):fails('request',lambda:m.request_record(ordinal))


@pytest.mark.parametrize('total,expected',( (0,3),(1,3),(1000,3),(1001,4),(100000,102) ))
def test_explicit_total_page_count_and_empty_zero(total,expected):
    count,pages,rows=m._mapping_envelope(page(total),0)
    assert count==total and 2+pages==expected and len(rows)==min(total,1000)


@pytest.mark.parametrize('field,value,code',(
    ('total',-1,'mapping_bound'),('total',100001,'mapping_bound'),('total',True,'mapping_bound'),
    ('total',1.0,'mapping_bound'),('limit',999,'mapping_shape'),('limit',True,'mapping_shape'),
    ('offset',1,'mapping_shape'),('offset',False,'mapping_shape')))
def test_mapping_meta_requires_exact_ints_bounds_and_offset(field,value,code):
    raw=json.loads(page());raw['meta'][field]=value
    fails(code,lambda:m._mapping_envelope(m.canonical(raw),0))


@pytest.mark.parametrize('change',('duplicate','total_drift','count','links','extra_meta','extra_top','offset_skip'))
def test_mapping_envelope_cannot_skip_or_follow_or_change_inventory(change):
    raw=json.loads(page(1001,1000));offset=1000
    if change=='duplicate':
        bad=page().replace(b'"total":1',b'"total":1,"total":1')
        fails('mapping_shape',lambda:m._mapping_envelope(bad,0));return
    if change=='total_drift':raw['meta']['total']=1002;raw['data'].append({})
    elif change=='count':raw['data']=[]
    elif change=='links':raw['links']={'next':42}
    elif change=='extra_meta':raw['meta']['other']='unexpected'
    elif change=='extra_top':raw['other']='unexpected'
    else:offset=2000
    fails('mapping_shape',lambda:m._mapping_envelope(m.canonical(raw),offset,1001))


def test_server_next_URL_is_inert_and_never_followed():
    raw=json.loads(page());raw['links']['next']='https://invalid.example/credential-steal?next=anything'
    assert m._mapping_envelope(m.canonical(raw),0)[0]==1
    assert 'links' not in inspect.getsource(m.provider_observation)
    assert 'filter[ex]' in str(m.request_record(3)) and m.request_record(3)['endpoint']=='https://eodhd.com/api/id-mapping'


@pytest.mark.parametrize('total',(0,1,1001))
def test_all_records_missing_unknown_and_order_preserved_in_closed_auth(total):
    capture,index,journal,p,raw=fixture(total)
    checked=m.analyse(capture,index,journal,p,time.monotonic()+20);m.validate_authentication(checked,p)
    assert checked['mapping']['row_count']==total and checked['active']['row_count']==checked['delisted']['row_count']==1
    assert checked['active']['known_field_shapes']['Isin']['null']==1
    assert checked['delisted']['known_field_shapes']['Isin']['null']==1
    assert checked['delisted']['known_field_shapes']['Type']['nonempty_string']==1
    assert checked['delisted']['unknown_field_name_count']==0
    assert checked['identity_crosswalk_admitted'] is False
    output=m.canonical(checked)
    assert b'SYNTH' not in output and b'DEAD' not in output and b'Synthetic' not in output
    assert b'synthetic_extra' not in output and b'kept-private' not in output
    assert all(checked[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('change',('capture_hash','index_hash','journal_hash','trailing','offset','ordinal','size','body_hash'))
def test_full_capture_auth_precedes_deserialization_and_exact_frames(change,monkeypatch):
    capture,index,journal,p,_=fixture()
    if change=='capture_hash':
        p['capture_pin']['sha256']='f'*64
        monkeypatch.setattr(m,'_decode',lambda *_:pytest.fail('parsed before external byte pin'))
    elif change=='index_hash':p['index_pin']['sha256']='f'*64
    elif change=='journal_hash':p['journal_pin']['sha256']='f'*64
    elif change=='trailing':capture+=b'x';p['capture_pin']=m.pin(capture)
    else:
        rows=json.loads(index)
        if change=='offset':rows['bodies'][1]['offset']+=1
        elif change=='ordinal':rows['bodies'][1]['ordinal']=True
        elif change=='size':
            capture=struct.pack('>Q',999)+capture[8:];p['capture_pin']=m.pin(capture)
        else:rows['bodies'][0]['body']['sha256']='f'*64
        index=m.canonical(rows);p['index_pin']=m.pin(index)
    fails('output' if change=='trailing' else 'index',lambda:m.analyse(capture,index,journal,p,time.monotonic()+20))


def test_journal_must_bind_every_exact_request_not_just_count():
    capture,index,journal,p,_=fixture()
    journal=journal.replace(b'"ordinal":1',b'"ordinal":0');p['journal_pin']=m.pin(journal)
    fails('journal',lambda:m.analyse(capture,index,journal,p,time.monotonic()+20))


def test_literal_backslash_n_is_not_a_JSONL_journal_or_record_separator():
    capture,index,journal,p,_=fixture()
    assert journal.count(b'\n')==3 and b'\\n' not in journal
    bad=journal.replace(b'\n',b'\\n');p['journal_pin']=m.pin(bad)
    fails('journal',lambda:m.analyse(capture,index,bad,p,time.monotonic()+20))
    rows=[{'symbol':'SYNTH.US'}]
    observed=m._record_observation(rows,m.MAPPING_FIELDS,time.monotonic()+20)
    assert observed['ordered_records_sha256']==m.sha(m.canonical(rows[0])+b'\n')
    assert observed['ordered_records_sha256']!=m.sha(m.canonical(rows[0])+b'\\n')


def test_maximum_100_page_public_envelope_fits_explicit_protocol_bound():
    value=result();p=value['provider'];a=value['authentication']
    body_pins=[{'byte_count':m.MAX_LIST,'sha256':'d'*64} for _ in range(2)]
    body_pins.extend({'byte_count':200000,'sha256':'e'*64} for _ in range(100))
    capture={'byte_count':sum(item['byte_count'] for item in body_pins)+8*102,'sha256':'f'*64}
    p.update(application_dispatch_intents=102,completed_HTTP200_bodies=102,current_ordinal=101,
        body_pins=body_pins,capture_pin=capture,mapping_total=100000,mapping_pages=100)
    a.update(body_pins=body_pins,capture_pin=capture,mapping_pages=100)
    mapping=a['mapping'];mapping['row_count']=100000
    for shapes in mapping['known_field_shapes'].values():
        for name in shapes:shapes[name]=100000 if name=='nonempty_string' else 0
    for role,item in (('provider',p),('authenticate',a)):
        value['child_packets'][role]['result']=copy.deepcopy(item)
        value['provider_actual' if role=='provider' else 'authentication_actual']=actual(value['child_packets'][role])
    raw=envelope(value);assert len(raw)<m.MAX_FRAME
    m.validate_output(raw,0,args())
    impossible=copy.deepcopy(p);impossible['capture_pin']['byte_count']+=1
    fails('output',lambda:m.validate_provider(impossible,success=True))


@pytest.mark.parametrize('ordinal,intents,completed',((None,1,0),(0,2,0),(1,1,0),(2,1,1),(2,3,1),(3,4,2)))
def test_failure_evidence_rejects_impossible_phase_counts(ordinal,intents,completed):
    p=m._provider_state();p.update(current_ordinal=ordinal,application_dispatch_intents=intents,
        completed_HTTP200_bodies=completed,body_pins=[m.pin(b'[]') for _ in range(completed)])
    fails('output',lambda:m.validate_provider(p))


def test_actual_parent_and_child_exits_hashes_and_report_are_not_grant_booleans():
    value=result();raw=envelope(value);m.validate_output(raw,0,args())
    fails('output',lambda:m.validate_output(raw,2,args()))
    for field in ('provider_actual','authentication_actual'):
        for key,changed in (('actual_exit',2),('stdout_sha256','f'*64)):
            bad=copy.deepcopy(value);bad[field][key]=changed
            with pytest.raises((m.Refused,m.ap.Refused)):m.validate_output(envelope(bad),0,args())
    bad=copy.deepcopy(value);bad['authentication']['identity_crosswalk_admitted']=True
    fails('output',lambda:m.validate_output(envelope(bad),0,args()))
    decoded=json.loads(raw);decoded['outcome']['report']['sha256']='f'*64
    fails('output',lambda:m.validate_output(m.canonical(decoded)+b'\n',0,args()))


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
    def json(self):pytest.fail('provider parsed JSON through Response')


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
def test_numeric_status_non200_has_zero_application_body_read(fetch_scope,status):
    config,seen=fetch_scope;config['status']=status;state=m._provider_state()
    with pytest.raises(m.Refused):m.fetch(0,'synthetic-safe-token',state,m._ca_bytes(),time.monotonic()+20)
    assert seen[0].reads==0 and state['HTTP_status']==(status if type(status) is int and 100<=status<=599 else None)


@pytest.mark.parametrize('status',(301,302))
def test_real_Requests_redirect_never_reads_refused_body(monkeypatch,status):
    observed=[]
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    def send(adapter,prepared,**kwargs):
        response=m.requests.Response();response.status_code=status;response.url=prepared.url;response.request=prepared
        response.headers=m.requests.structures.CaseInsensitiveDict({'Location':'https://eodhd.com/api/elsewhere'})
        response.raw=NS(read=lambda *_args,**_kwargs:pytest.fail('redirect failed body read'),
            close=lambda:None,release_conn=lambda:None)
        observed.append(response);return response
    monkeypatch.setattr(m.OwnedAdapter,'send',send)
    fails('http_refused',lambda:m.fetch(0,'synthetic-safe-token',m._provider_state(),m._ca_bytes(),time.monotonic()+20))
    assert len(observed)==1 and observed[0]._content_consumed is False


@pytest.mark.parametrize('encoding',('raw','url','json','csv'))
def test_recognized_credentials_do_not_enter_retained_bodies(fetch_scope,encoding):
    config,_=fetch_scope;key='synthetic-quote"token&'
    payload={'raw':key.encode(),'url':m.urlencode({'x':key}).split('=',1)[1].encode(),
        'json':json.dumps(key).encode(),'csv':key.encode().replace(b'"',b'""')}[encoding]
    config['body']=b'{"synthetic":"'+payload+b'"}'
    fails('credential_echo',lambda:m.fetch(0,key,m._provider_state(),m._ca_bytes(),time.monotonic()+20))


@pytest.mark.parametrize('ordinal,extra',((0,False),(2,True)))
def test_list_and_mapping_body_bounds_are_distinct(fetch_scope,ordinal,extra):
    config,_=fetch_scope;config['body']=b'x'*(m.MAX_PAGE+1)
    if extra:fails('body_bound',lambda:m.fetch(ordinal,'synthetic-safe-token',m._provider_state(),m._ca_bytes(),time.monotonic()+20))
    else:assert len(m.fetch(ordinal,'synthetic-safe-token',m._provider_state(),m._ca_bytes(),time.monotonic()+20))==m.MAX_PAGE+1


def test_environment_is_checked_before_preparing_credential_URL(fetch_scope,monkeypatch):
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:(_ for _ in ()).throw(m.environment.EnvironmentRefused()))
    monkeypatch.setattr(m,'_session',lambda *_:pytest.fail('prepared credential before logging guard'))
    with pytest.raises(m.environment.EnvironmentRefused):
        m.fetch(0,'synthetic-safe-token',m._provider_state(),m._ca_bytes(),time.monotonic()+20)


@pytest.fixture
def store_scope(monkeypatch,tmp_path):
    monkeypatch.setattr(m,'CONTROL',tmp_path/'parent'/'AW')
    monkeypatch.setattr(m,'_security',lambda fd:('synthetic',))
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    def walk(path):
        chain=tuple((os.stat(Path(*path.parts[:i+1])).st_dev,os.stat(Path(*path.parts[:i+1])).st_ino) for i in range(1,len(path.parts)))
        return os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW),chain
    monkeypatch.setattr(m.admitted,'_storage_module',lambda:NS(_walk=walk));return m.CONTROL


@pytest.mark.parametrize('total',(0,1001))
def test_provider_retains_before_minimal_meta_parse_and_dispatches_exact_offsets(store_scope,monkeypatch,total):
    _,_,_,_,raws=fixture(total);seen=[];monkeypatch.setattr(m,'_ca_bytes',lambda:b'synthetic')
    with m.Store() as store:
        store.write('claim.json',m.binding(args()));fds=[store.create(name) for name in m.DATA_FILES]
        old=m._mapping_envelope
        def envelope(raw,offset,expected_total=None):
            assert os.fstat(fds[0]).st_size>=len(raw)+8
            assert os.pread(fds[0],len(raw),os.fstat(fds[0]).st_size-len(raw))==raw
            return old(raw,offset,expected_total)
        monkeypatch.setattr(m,'_mapping_envelope',envelope)
        def fetch(ordinal,key,state,ca,deadline):
            seen.append(ordinal);assert state['application_dispatch_intents']==ordinal+1
            state.update(HTTP_status_type='int',HTTP_status=200);return raws[ordinal]
        monkeypatch.setattr(m,'fetch',fetch)
        p=m.provider_observation(fds,'synthetic-safe-token',m._provider_state(),time.monotonic()+20)
        store.refresh(m.DATA_FILES);assert seen==list(range(len(raws)))
        monkeypatch.setattr(m,'_mapping_envelope',old)
        checked=m.authenticate_observation(fds,p,time.monotonic()+20)
        assert checked['mapping']['row_count']==total


def test_malformed_mapping_is_retained_then_refused_without_next_request(store_scope,monkeypatch):
    _,_,_,_,raws=fixture();raws[2]=b'{"meta":{"total":1,"total":2}}'
    seen=[];monkeypatch.setattr(m,'_ca_bytes',lambda:b'synthetic')
    def fetch(ordinal,key,state,ca,deadline):
        seen.append(ordinal);state.update(HTTP_status_type='int',HTTP_status=200);return raws[ordinal]
    monkeypatch.setattr(m,'fetch',fetch)
    with m.Store() as store:
        store.write('claim.json',m.binding(args()));fds=[store.create(name) for name in m.DATA_FILES];state=m._provider_state()
        fails('mapping_shape',lambda:m.provider_observation(fds,'synthetic-safe-token',state,time.monotonic()+20))
        store.refresh(m.DATA_FILES);assert seen==[0,1,2] and state['completed_HTTP200_bodies']==3
        assert os.pread(fds[0],len(raws[2]),os.fstat(fds[0]).st_size-len(raws[2]))==raws[2]
        assert os.fstat(fds[2]).st_size==0;m.validate_provider(state)


@pytest.mark.parametrize('role',m.ROLES)
def test_original_inherited_FDs_and_persistent_started_file_prevent_bare_or_second_dispatch(store_scope,role):
    a=args();raw=m.canonical({})
    with m.Store() as store:
        claim=store.create('claim.json',m.canonical(m.binding(a)));data=[store.create(name) for name in m.DATA_FILES]
        intent=store.create(role+'-intent.json',m.canonical({**m.binding(a),'role':role,'input_pin':m.pin(raw)}))
        start=store.create(role+'-started.json');a.control_fd=store.fd;a.claim_fd=claim
        a.intent_fd=intent;a.started_fd=start;a.data_fds=tuple(data)
        m._inherited(a,role,raw,time.monotonic()+20);store.refresh((role+'-started.json',))
        fails('worker_scope',lambda:m._inherited(a,role,raw,time.monotonic()+20))


@pytest.mark.parametrize('barrier',('source','credential','provider',None))
def test_parent_claim_and_source_proof_precede_single_Keychain_handoff(store_scope,monkeypatch,barrier):
    seen=[];good=result()
    def proof():
        seen.append('proof')
        if barrier=='source':raise m.Refused('source_binding')
        return good['source_context']
    monkeypatch.setattr(m,'source_context',proof);monkeypatch.setattr(m,'preflight',lambda *_:None)
    def keychain(provider,**_):
        seen.append('keychain');assert provider=='eodhd'
        assert m.CONTROL.joinpath('claim.json').is_file()
        if barrier=='credential':raise m.keychain.KeychainUnavailable()
        return 'synthetic-safe-token'
    monkeypatch.setattr(m.keychain,'load_key',keychain)
    def child(a,store,role,payload,runtime,deadline,key=None):
        seen.append(role);value=copy.deepcopy(good['child_packets'][role])
        if barrier=='provider':value['failure_code']='http_refused';return value,actual(value,2)
        return value,actual(value)
    monkeypatch.setattr(m,'_child',child)
    out=m.run(args(),time.monotonic()+100)
    assert ('result' in out) is (barrier is None)
    if 'keychain' in seen:assert seen.index('proof')<seen.index('keychain')
    if 'provider' in seen:assert seen.index('keychain')<seen.index('provider')
    assert seen.count('keychain')<=1


@pytest.mark.parametrize('role',('provider','authenticate','validate'))
def test_native_scope_denies_old_DATA_and_Keychains(role):
    policy=m.native_profile(role)
    assert '/Library/Keychains' in policy and '/usr/bin/security' in policy
    assert ('/private/var/run/mDNSResponder' in policy) is (role=='provider')
    assert ('remote tcp "*:443"' in policy) is (role=='provider')
    assert ('(deny network*)' in policy) is (role!='provider')
    assert '/R326-20261027-AU/' not in policy and '/R326-20261027-AR/' not in policy
    assert (str(m.CONTROL) in policy) is (role!='validate')


@pytest.mark.parametrize('case',('echo','noise','stderr','timeout'))
def test_real_synthetic_child_capture_bounds_and_own_reap(tmp_path,case):
    import sys
    code={'echo':'import sys;sys.stdout.buffer.write(sys.stdin.buffer.read()+b"\\n")',
        'noise':'print("{}\\n{}")','stderr':'import sys;sys.stderr.write("synthetic-noise");print("{}")',
        'timeout':'import time;time.sleep(2)'}[case]
    safe={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TMPDIR':str(tmp_path),'PYTHONDONTWRITEBYTECODE':'1'}
    raw=m.canonical({'synthetic':True})
    packet,observed=m._capture_child([sys.executable,'-B','-c',code],safe,raw,[],.05 if case=='timeout' else 5)
    m.ap._actual(observed);assert observed['spawn_observed'] is True
    if case=='echo':assert packet=={'synthetic':True} and observed['actual_exit']==0
    else:assert set(packet)=={'capture_failure'}
    if case=='stderr':assert observed['stderr_bytes']==len(b'synthetic-noise')
    if case=='timeout':assert observed['bound']=='deadline' and observed['actual_exit'] is not None


def test_no_old_operation_and_no_CSV_price_or_identity_admission():
    code=inspect.getsource(m)
    assert 'previous.run(' not in code and 'ap.run(' not in code and 'ar.run(' not in code
    assert 'load_key(\'eodhd\'' in inspect.getsource(m.run)
    assert 'json()' not in inspect.getsource(m.fetch)
    assert 'mapping_envelope' in inspect.getsource(m.provider_observation)
    assert 'catalog_protocol_complete' in code
