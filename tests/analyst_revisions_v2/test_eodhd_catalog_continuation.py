"""Synthetic forward catalog continuation; no old DATA/provider/credential use."""
import copy
import inspect
import json
import os
from pathlib import Path
import struct
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_r298_eodhd_catalog_continuation as m
assert 'assistant.dispatch_fence' not in sys.modules


def fails(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def args():return NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def page(offset):
    rows=[{'symbol':'SYNTH.US','figi':None}]*min(m.PAGE_SIZE,m.MAX_MAPPING_ROWS-offset)
    return m.canonical({'meta':{'total':m.MAX_MAPPING_ROWS,'limit':m.PAGE_SIZE,'offset':offset},
        'data':rows,'links':{'next':None}})


def seed_raw():
    row={'Code':'SYNTH','Name':'Synthetic\nopaque € display','Country':None,'Exchange':None,
        'Currency':None,'Type':'Unknown label','Isin':'N/A'}
    bodies=(m.canonical([row]),m.canonical([]),page(0))
    return bodies,b''.join(struct.pack('>Q',len(body))+body for body in bodies)


@pytest.fixture
def source_scope(monkeypatch,tmp_path):
    root=tmp_path/'root';root.mkdir(mode=0o755);root.chmod(0o755)
    path=root
    for name in ('artifacts','analyst_revisions_v2','source'):
        path=path/name;path.mkdir(mode=0o700)
    bodies,seed=seed_raw();path=path/'seed.bin';path.write_bytes(seed);path.chmod(0o600)
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m.guard_module,'ROOT',root);monkeypatch.chdir(root)
    monkeypatch.setattr(m,'SOURCE_FRAME_PINS',tuple(m.pin(raw) for raw in bodies))
    monkeypatch.setattr(m,'SOURCE_PLAN',{'old_frames':{'relative_path':'artifacts/analyst_revisions_v2/source/seed.bin',**m.pin(seed)}})
    monkeypatch.setattr(m,'CONTROL',root/'output'/'BA')
    (root/'.pytest_cache').mkdir(mode=0o700)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    def walk(path):
        chain=tuple((os.stat(Path(*path.parts[:i+1])).st_dev,os.stat(Path(*path.parts[:i+1])).st_ino) for i in range(1,len(path.parts)))
        return os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW),chain
    monkeypatch.setattr(m.admitted,'_storage_module',lambda:NS(_walk=walk))
    return path,bodies,seed


def actual(value,exit=0):
    raw=m.canonical(value)+b'\n'
    return {'actual_exit':exit,'spawn_observed':True,'bound':None,'stdout_bytes':len(raw),'stdout_sha256':m.sha(raw),
        'stderr_bytes':0,'stderr_sha256':m.sha(b'')}


def packet(role,value,code=None):return {'binding':m.binding(args()),'role':role,'result':value,'failure_code':code}


def fake_source():
    listed={'row_count':1,'ordered_records_sha256':'a'*64,'known_field_shapes':{
        name:{'missing':0,'null':0,'nonempty_string':1,'empty_string':0,'other':0} for name in m.LIST_FIELDS},
        'unknown_field_name_count':0,'unknown_field_names_sha256':m.sha(b'[]')}
    receipt={'schema':m.guard_module.SCHEMA+'-receipt',
        'profile_sha256':m.sha(m.canonical(m.guard_module.profile_record(m.SOURCE_PLAN))),
        'files':{'old_frames':{**m.SOURCE_PLAN['old_frames'],'current_metadata_sha256':'b'*64,'current_security_sha256':'c'*64}},
        'fresh_current_security_authenticated':True,'fixed_bytes_authenticated':True,'requires_normal_return_before_use':True,
        'historical_continuity_proven':False,'continuous_integrity_proven':False}
    obs={'schema':m.SCHEMA+'-source-observation','seed_pin':{key:m.SOURCE_PLAN['old_frames'][key] for key in ('byte_count','sha256')},
        'external_frame_body_pins':list(m.SOURCE_FRAME_PINS),'source_guard_receipt':receipt,'source_guard_normal_return':True,
        'symbol_lists':{'active':copy.deepcopy(listed),'delisted':copy.deepcopy(listed)},
        'first_mapping_total':m.MAX_MAPPING_ROWS,'first_mapping_limit':1000,'first_mapping_offset':0,
        'first_mapping_row_count':1000,'prior_candidate_whole_pin_itself_admitted':False,**m.FALSE_FLAGS}
    return {'observation':obs,'source_metadata_pin':m.pin(m.canonical(obs))}


def fake_success():
    src=fake_source();p=m._provider_state()
    p.update(application_dispatch_intents=110,completed_HTTP200_bodies=110,current_ordinal=109,HTTP_status_type='int',
        HTTP_status=200,source_observation_sha256=m.sha(m.canonical(src['observation'])),
        body_pins=[{'byte_count':100000,'sha256':'d'*64} for _ in range(110)],
        capture_pin={'byte_count':110*100008,'sha256':'e'*64},
        index_pin={'byte_count':16000,'sha256':'f'*64},journal_pin={'byte_count':11000,'sha256':'a'*64})
    mapping=copy.deepcopy(src['observation']['symbol_lists']['active']);mapping['row_count']=m.MAX_MAPPING_ROWS
    mapping['known_field_shapes']={name:{'missing':0,'null':m.MAX_MAPPING_ROWS,'nonempty_string':0,'empty_string':0,'other':0}
        for name in m.MAPPING_FIELDS}
    a={'schema':m.SCHEMA+'-authentication','body_pins':[*m.SOURCE_FRAME_PINS,*p['body_pins']],
        'seed_pin':src['observation']['seed_pin'],'capture_pin':p['capture_pin'],'index_pin':p['index_pin'],'journal_pin':p['journal_pin'],
        'source_observation_sha256':p['source_observation_sha256'],'active':src['observation']['symbol_lists']['active'],
        'delisted':src['observation']['symbol_lists']['delisted'],'mapping':mapping,'mapping_pages':111,'new_mapping_pages':110,
        'bounded_catalog_protocol_complete':True,'identity_crosswalk_admitted':False,**m.FALSE_FLAGS}
    packets={role:packet(role,value) for role,value in (('source',src),('provider',p),('authenticate',a))}
    return {'schema':m.SCHEMA,'stage':'postflight','credential_handoff_complete':True,
        'source':src,'source_actual':actual(packets['source']),'provider':p,'provider_actual':actual(packets['provider']),
        'authentication':a,'authentication_actual':actual(packets['authenticate']),'child_packets':packets,
        'prior_context':m.source_context(),'provider_request_count':None,'post_checks_complete':True,**m.FALSE_FLAGS}


def envelope(value):
    return m.canonical({'binding':m.binding(args()),'outcome':{'result':value,
        'report':m.pin(m.canonical({**m.binding(args()),'result':value}))}})+b'\n'


def test_exact_unrequested_inventory_prior_facts_pins_and_inert_import():
    assert m.CONTROL.name=='R326-20261027-BA' and m.ROLES==('source','provider','authenticate')
    assert len(m.pins())==209 and all(m.sha((m.ROOT/name).read_bytes())==digest for name,digest in m.pins().items())
    records=[m.request_record(i) for i in range(110)]
    assert [item['parameters']['page[offset]'] for item in records]==[str(i) for i in range(1000,110001,1000)]
    assert all(item['endpoint']=='https://eodhd.com/api/id-mapping' for item in records)
    assert all(item['parameters']['filter[ex]']=='US' for item in records)
    assert m.SOURCE_PLAN['old_frames']['byte_count']==16140080 and sum(item['byte_count']+8 for item in m.SOURCE_FRAME_PINS)==16140080
    context=m.source_context();assert context['AY_actual_exit']==-9 and context['AY_native_validator_invoked'] is False
    assert context['AY_candidate_whole_pin_admitted'] is False and context['AZ_parent_actual_exit']==0
    assert m.profile_record()['own_protocol_files_maximum']==16
    code=inspect.getsource(m)
    assert 'evidence.run(' not in code and '/api/eod/' not in str(records)
    assert 'RAW' not in m.SCHEMA and 'MAX_FRAME' in code


@pytest.mark.parametrize('ordinal',(-1,110,True,1.0,None))
def test_request_inventory_does_not_repeat_or_expand(ordinal):fails('request',lambda:m.request_record(ordinal))


@pytest.mark.parametrize('offset,count',((0,1000),(1000,1000),(109000,1000),(110000,346)))
def test_fixed_total_and_exact_last_count(offset,count):
    assert len(m._mapping_envelope(page(offset),offset))==count


@pytest.mark.parametrize('change',('total','total_str','offset','limit','count','extra','next_type','duplicate'))
def test_mapping_pages_cannot_refresh_total_or_skip_or_coerce(change):
    raw=json.loads(page(1000))
    if change=='total':raw['meta']['total']+=1
    elif change=='total_str':raw['meta']['total']=str(m.MAX_MAPPING_ROWS)
    elif change=='offset':raw['meta']['offset']=2000
    elif change=='limit':raw['meta']['limit']=True
    elif change=='count':raw['data']=raw['data'][:-1]
    elif change=='extra':raw['meta']['extra']=1
    elif change=='next_type':raw['links']['next']=42
    else:
        bad=page(1000).replace(b'"total":110346',b'"total":110346,"total":110346')
        fails('mapping_shape',lambda:m._mapping_envelope(bad,1000));return
    fails('mapping_shape',lambda:m._mapping_envelope(m.canonical(raw),1000))


def test_source_independent_frame_pins_and_headers_before_any_JSON(source_scope,monkeypatch):
    path,bodies,seed=source_scope;calls=[]
    old=m._mapping_envelope
    monkeypatch.setattr(m,'_mapping_envelope',lambda *args:(calls.append('JSON'),old(*args))[1])
    old_list=m.catalog_schema.checked_symbol_rows
    monkeypatch.setattr(m.catalog_schema,'checked_symbol_rows',lambda *args:(calls.append('list-JSON'),old_list(*args))[1])
    bad=bytearray(seed);bad[seed.index(b'Synthetic')+1]^=1
    # Even a refreshed whole-file candidate cannot replace the three external body pins.
    m.SOURCE_PLAN['old_frames'].update(m.pin(bytes(bad)));path.write_bytes(bad)
    with m.Store() as store:
        store.write('claim.json',m.binding(args()));fds=[store.create(name) for name in m.DATA_FILES]
        fails('source_shape',lambda:m.source_observation(fds,time.monotonic()+20))
        assert calls==[] and os.fstat(fds[0]).st_size==os.fstat(fds[4]).st_size==0


@pytest.mark.parametrize('change',('header','trailing','truncate'))
def test_seed_frame_extent_is_not_an_unchecked_whole_hash(change,source_scope):
    _,bodies,seed=source_scope
    if change=='header':seed=struct.pack('>Q',len(bodies[0])+1)+seed[8:]
    elif change=='trailing':seed+=b'x'
    else:seed=seed[:-1]
    m.SOURCE_PLAN['old_frames'].update(m.pin(seed))
    fails('source_shape',lambda:m._seed_bodies(seed))


def test_source_normal_return_precedes_seed_publication_and_fresh_readback(source_scope,monkeypatch):
    path,bodies,seed=source_scope;events=[]
    old_exit=m.guard_module.FixedDataGuard.__exit__
    def finish(guard,*args):
        value=old_exit(guard,*args);events.append('normal-return');return value
    monkeypatch.setattr(m.guard_module.FixedDataGuard,'__exit__',finish)
    old_write=m._write
    def write(fd,raw):
        assert events==['normal-return'];return old_write(fd,raw)
    with m.Store() as store:
        store.write('claim.json',m.binding(args()));fds=[store.create(name) for name in m.DATA_FILES]
        monkeypatch.setattr(m,'_write',write)
        result=m.source_observation(fds,time.monotonic()+20);m.validate_source(result);store.refresh(m.DATA_FILES)
        assert m._read(fds[0],32*1024*1024,time.monotonic()+20)==seed
        assert result['observation']['symbol_lists']['active']['known_field_shapes']['Name']['nonempty_string']==1
        assert result['observation']['prior_candidate_whole_pin_itself_admitted'] is False


def test_all_110_new_pages_and_full_111_page_join_are_authenticated(source_scope,monkeypatch):
    seen=[];monkeypatch.setattr(m,'_ca_bytes',lambda:b'synthetic')
    def fetch(ordinal,key,state,ca,deadline):
        assert state['application_dispatch_intents']==ordinal+1;seen.append((ordinal,m.request_record(ordinal)))
        state.update(HTTP_status_type='int',HTTP_status=200);return page((ordinal+1)*1000)
    monkeypatch.setattr(m,'fetch',fetch)
    with m.Store() as store:
        store.write('claim.json',m.binding(args()));fds=[store.create(name) for name in m.DATA_FILES]
        source=m.source_observation(fds,time.monotonic()+30);store.refresh(m.DATA_FILES)
        state=m.provider_observation(fds,'synthetic-token',m._provider_state(),source,time.monotonic()+60);store.refresh(m.DATA_FILES)
        value=m.authenticate_observation(fds,source,state,time.monotonic()+90);m.validate_authentication(value,source,state)
        assert len(seen)==110 and value['mapping']['row_count']==110346 and len(value['body_pins'])==113
        assert value['mapping']['known_field_shapes']['cusip']['missing']==110346
        assert value['identity_crosswalk_admitted'] is False
        assert state['source_observation_sha256']==m.sha(m.canonical(source['observation']))


def test_changed_first_new_page_total_is_retained_then_stops_without_second(source_scope,monkeypatch):
    seen=[];monkeypatch.setattr(m,'_ca_bytes',lambda:b'synthetic')
    def fetch(ordinal,key,state,ca,deadline):
        seen.append(ordinal);state.update(HTTP_status_type='int',HTTP_status=200)
        bad=json.loads(page(1000));bad['meta']['total']+=1;return m.canonical(bad)
    monkeypatch.setattr(m,'fetch',fetch)
    with m.Store() as store:
        store.write('claim.json',m.binding(args()));fds=[store.create(name) for name in m.DATA_FILES]
        src=m.source_observation(fds,time.monotonic()+20);store.refresh(m.DATA_FILES);state=m._provider_state()
        fails('mapping_shape',lambda:m.provider_observation(fds,'synthetic-token',state,src,time.monotonic()+20))
        store.refresh(m.DATA_FILES);assert seen==[0] and state['completed_HTTP200_bodies']==1
        assert os.fstat(fds[1]).st_size>8 and os.fstat(fds[3]).st_size==0;m.validate_provider(state)


@pytest.mark.parametrize('change',('source_exit','provider_exit','auth_exit','source_hash','source_admit','old_zero','candidate'))
def test_parent_success_needs_three_actual_zero_and_closed_consistent_source(change):
    value=fake_success();raw=envelope(value);m.validate_output(raw,0,args())
    if change=='source_exit':value['source_actual']['actual_exit']=2
    elif change=='provider_exit':value['provider_actual']['actual_exit']=2
    elif change=='auth_exit':value['authentication_actual']['actual_exit']=2
    elif change=='source_hash':value['provider']['source_observation_sha256']='f'*64
    elif change=='source_admit':value['source']['observation']['identity_crosswalk_admitted']=True
    elif change=='old_zero':value['prior_context']['AY_actual_exit']=0
    else:value['source']['observation']['prior_candidate_whole_pin_itself_admitted']=True
    with pytest.raises((m.Refused,m.ap.Refused)):m.validate_output(envelope(value),0,args())


def test_maximal_public_success_frame_fits_128KiB_and_no_raw_values():
    value=fake_success();raw=envelope(value);m.validate_output(raw,0,args())
    assert len(raw)<m.MAX_FRAME and b'SYNTH.US' not in raw
    fails('output',lambda:m.validate_output(raw,2,args()))


@pytest.mark.parametrize('barrier',('source','precredential','credential','provider',None))
def test_parent_source_actual_zero_and_held_seed_checks_before_single_Keychain(source_scope,monkeypatch,barrier):
    events=[];good=fake_success();monkeypatch.setattr(m,'preflight',lambda *_:None)
    def check(store,src,deadline):
        events.append('held-seed')
        if barrier=='precredential':raise m.Refused('source_metadata')
    monkeypatch.setattr(m,'_check_source_files',check)
    def keychain(provider,**_):
        assert provider=='eodhd' and (m.CONTROL/'claim.json').is_file()
        assert events[:2]==['source','held-seed'];events.append('keychain')
        if barrier=='credential':raise m.keychain.KeychainUnavailable()
        return 'synthetic-token'
    monkeypatch.setattr(m.keychain,'load_key',keychain)
    def child(a,store,role,payload,runtime,deadline,key=None):
        events.append(role);out=copy.deepcopy(good['child_packets'][role])
        if barrier==role:
            out['failure_code']='source_shape' if role=='source' else 'http_refused'
            if role=='source':out['result']=None
            return out,actual(out,2)
        return out,actual(out)
    monkeypatch.setattr(m,'_child',child)
    out=m.run(args(),time.monotonic()+100)
    assert ('result' in out) is (barrier is None)
    assert events.count('keychain')<=1
    if barrier in ('source','precredential'):assert 'keychain' not in events


def test_same_size_seed_drift_after_source_observation_refuses_before_Keychain(source_scope,monkeypatch):
    _,_,seed=source_scope;good=fake_success();calls=[]
    monkeypatch.setattr(m,'preflight',lambda *_:None)
    monkeypatch.setattr(m.keychain,'load_key',lambda *_args,**_kwargs:(calls.append('keychain'),'synthetic-token')[1])
    def child(a,store,role,payload,runtime,deadline,key=None):
        if role=='source':
            m._write(store.held[m.DATA_FILES[0]]['fd'],b'x'*len(seed))
            m._write(store.held[m.DATA_FILES[4]]['fd'],m.canonical(good['source']['observation']))
            store.refresh(m.DATA_FILES)
        value=copy.deepcopy(good['child_packets'][role]);return value,actual(value)
    monkeypatch.setattr(m,'_child',child)
    output=m.run(args(),time.monotonic()+100)
    assert 'failure' in output and output['failure']['failure_code']=='source_metadata'
    assert calls==[]


def test_spawn_refusal_preserves_finite_no_child_actual_without_error_values(monkeypatch):
    def refused(*_args,**_kwargs):raise OSError('synthetic-sensitive-error-do-not-return')
    monkeypatch.setattr(m.subprocess,'Popen',refused)
    out,observed=m._capture_child(['synthetic-sensitive-argv'],{},b'',[],10)
    assert out=={'capture_failure':'spawn_refused'}
    assert observed['spawn_observed'] is False and observed['actual_exit'] is None and observed['bound'] is None
    assert observed['stdout_bytes']==observed['stderr_bytes']==0;m.ap._actual(observed)
    assert b'synthetic-sensitive' not in m.canonical({'packet':out,'actual':observed})


@pytest.fixture
def fd_store(monkeypatch,tmp_path):
    monkeypatch.setattr(m,'CONTROL',tmp_path/'parent'/'BA');monkeypatch.setattr(m,'_security',lambda fd:('synthetic',))
    def walk(path):
        chain=tuple((os.stat(Path(*path.parts[:i+1])).st_dev,os.stat(Path(*path.parts[:i+1])).st_ino) for i in range(1,len(path.parts)))
        return os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW),chain
    monkeypatch.setattr(m.admitted,'_storage_module',lambda:NS(_walk=walk));return m.CONTROL


def test_owned_credential_pipe_is_distinct_and_secret_not_in_argv_environment_or_packet(fd_store,monkeypatch,tmp_path):
    secret='synthetic-owned-credential';seen=[]
    def capture(command,safe,payload,inherited,seconds):
        descriptor=int(command[command.index('--credential-fd')+1])
        assert descriptor==inherited[-1] and descriptor not in inherited[:-1]
        assert len(inherited)==10 and len(set(inherited))==10
        assert os.read(descriptor,4097)==secret.encode('ascii')
        assert secret not in str(command) and secret not in str(safe) and secret.encode() not in payload
        assert 'QC_API_TOKEN' not in safe and 'QC_USER_ID' not in safe
        seen.append(descriptor)
        return {'capture_failure':'worker_packet'},{'actual_exit':2,'spawn_observed':True,'bound':None,
            'stdout_bytes':0,'stdout_sha256':m.sha(b''),'stderr_bytes':0,'stderr_sha256':m.sha(b'')}
    monkeypatch.setattr(m,'_capture_child',capture)
    with m.Store() as store:
        store.write('claim.json',m.binding(args()))
        for name in m.DATA_FILES:store.create(name)
        out,observed=m._child(args(),store,'provider',{'source':fake_source()},tmp_path,time.monotonic()+30,key=secret)
        assert out=={'capture_failure':'worker_packet'} and observed['actual_exit']==2
    with pytest.raises(OSError):os.fstat(seen[0])


@pytest.mark.parametrize('role',m.ROLES)
def test_real_tiny_child_original_FDs_and_persistent_once_start(fd_store,role,tmp_path):
    a=args();raw=m.canonical({});safe={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TMPDIR':str(tmp_path),'PYTHONDONTWRITEBYTECODE':'1'}
    with m.Store() as store:
        claim=store.create('claim.json',m.canonical(m.binding(a)));fds=[store.create(name) for name in m.DATA_FILES]
        intent=store.create(role+'-intent.json',m.canonical({**m.binding(a),'role':role,'input_pin':m.pin(raw)}))
        started=store.create(role+'-started.json');inherited=[store.fd,claim,intent,started,*fds]
        code="""import json,sys,time
from pathlib import Path
from types import SimpleNamespace as NS
from scripts import run_arv2_r298_eodhd_catalog_continuation as m
assert 'assistant.dispatch_fence' not in sys.modules
m.CONTROL=Path(sys.argv[1]);m._security=lambda fd:('synthetic',)
role=sys.argv[2];fds=list(map(int,sys.argv[3].split(',')))
a=NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64,control_fd=fds[0],claim_fd=fds[1],intent_fd=fds[2],started_fd=fds[3],data_fds=tuple(fds[4:]))
raw=sys.stdin.buffer.read()
try:
 m._inherited(a,role,raw,time.monotonic()+10);print(m.canonical({'role':role,'data_fds':len(a.data_fds),'nonce':m.sha(raw)}).decode('ascii'))
except BaseException as error:
 print(m.canonical({'refused':m.finite(error)}).decode('ascii'));raise SystemExit(2)
"""
        cmd=[sys.executable,'-B','-c',code,str(m.CONTROL),role,','.join(map(str,inherited))]
        out,seen=m._capture_child(cmd,safe,raw,inherited,10)
        assert seen['actual_exit']==0 and out=={'role':role,'data_fds':5,'nonce':m.sha(raw)}
        store.refresh((role+'-started.json',))
        out,seen=m._capture_child(cmd,safe,raw,inherited,10)
        assert seen['actual_exit']==2 and out=={'refused':'worker_scope'}


@pytest.mark.parametrize('role',(*m.ROLES,'validate'))
def test_native_roles_old_source_only_readable_in_source_and_network_only_provider(role):
    policy=m.native_profile(role)
    assert '/Library/Keychains' in policy and '/usr/bin/security' in policy
    assert ('remote tcp "*:443"' in policy) is (role=='provider')
    assert ('(deny network*)' in policy) is (role!='provider')
    assert (m.SOURCE_PLAN['old_frames']['relative_path'] in policy) is (role=='source')
    assert '/R326-20261027-AY/' not in policy and '/R326-20261027-AZ/' not in policy


@pytest.mark.parametrize('case',('noise','stderr','timeout'))
def test_owned_process_capture_bounds_and_kill_reap(tmp_path,case):
    code={'noise':'print("{}\\n{}")','stderr':'import sys;sys.stderr.write("synthetic");print("{}")','timeout':'import time;time.sleep(2)'}[case]
    safe={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TMPDIR':str(tmp_path),'PYTHONDONTWRITEBYTECODE':'1'}
    out,seen=m._capture_child([sys.executable,'-B','-c',code],safe,b'{}',[],.05 if case=='timeout' else 10)
    assert set(out)=={'capture_failure'} and seen['actual_exit'] is not None
    if case=='timeout':assert seen['bound']=='deadline'
