"""Synthetic prospective caller checks; no private DATA, credentials or QC."""
import copy
import json
import os
from pathlib import Path
import re
import time
from types import SimpleNamespace

import pytest

from scripts import run_arv2_r348_remaining_six as m

ORG,USER='a'*32,71
OWNER={'uid':USER,'owner':True,'name':'synthetic owner','publicId':'synthetic-owner',
    'permission':'write','liveControl':True,'profileImage':'','email':'','bio':''}


def a4_fact():
    stats={name:'{}' for name in m.STATISTICS}
    result={'candidate_id':'R343-AR100','attempt':4,'project_id':m.A4_PROJECT,
        'compile_id':'251b7dbcc94a6db5740a3b83a83ec133-232313c1c0b6b9f62aae03cca921fd2f',
        'backtest_id':'007d4ab27c26d337ae53acb492a83410',
        'backtest_name':'ARV2 LEGACY SIX R343-AR100 OCT2026 A4','observed_status':'Completed.',
        'result_read':True,'selected_result_read':True,'semantic_validation':{'accepted':True,'run_valid':True},
        'statistics':stats,'statistics_pin':m.pin(m.canonical(stats)),
        'input_source_identity':{'synthetic_identity':'matched-current-DATA'},
        'source':{'file_count':18,'source_byte_total':417652,'source_inventory_pin':{'byte_count':2775,
            'sha256':'71857bac63298b6b9dd4221ffc180ca4a59f10574edd109220a335d9370a232c'}},**m.FLAGS}
    binding=copy.deepcopy(m.D1_BINDING)
    value={'schema':'arv2-r348-ar100-result-fact-v1',
        'observation':{'actual_exit':0,'original_stdout_validated':True},
        'original_result':{'schema':'arv2-r348-ar100-status-result-v1-result','binding':binding,
            'attempt_consumed':True,'report_pin':{'byte_count':1,'sha256':'e'*64},'result':result}}
    repin_a4(value)
    return value


def repin_a4(value):
    original=value['original_result']
    original['report_pin']=m.pin(m.canonical({key:item for key,item in original.items() if key!='report_pin'}))
    value['observation']['original_stdout_pin']=m.pin(m.canonical(original)+b'\n')


def bind_fact(monkeypatch,value):
    raw=m.canonical(value)+b'\n';monkeypatch.setattr(m,'A4_RESULT_FACT_PIN',m.pin(raw));return raw


def test_unselected_prerequisite_refuses_before_any_environment_or_private_access(monkeypatch):
    monkeypatch.setattr(m,'A4_RESULT_FACT_PIN',None)
    assert m.A4_RESULT_FACT_PIN is None
    with pytest.raises(m.Refused,match='a4_result_unselected'):m.preflight(None,None)
    with pytest.raises(m.Refused,match='a4_result_unselected'):m.validate_a4_result_fact(b'{}\n')
    assert m.profile_record(m.CANDIDATES[0])['preparation_status'].startswith('unselected_')


def test_selected_positive_fact_is_bound_to_original_actual_exit_and_semantics(monkeypatch):
    fact=a4_fact();raw=bind_fact(monkeypatch,fact)
    assert m.validate_a4_result_fact(raw)==fact
    with pytest.raises(m.Refused,match='a4_result'):m.validate_a4_result_fact(raw+b'\n')


@pytest.mark.parametrize('change',['exit','bool_exit','stdout','accepted','valid','status','candidate',
    'backtest','source','statistics_pin','read','formal'])
def test_pinned_but_inadmissible_fact_never_supplies_acceptance(monkeypatch,change):
    fact=a4_fact();result=fact['original_result']['result']
    if change=='exit':fact['observation']['actual_exit']=2
    elif change=='bool_exit':fact['observation']['actual_exit']=False
    elif change=='stdout':fact['observation']['original_stdout_validated']=False
    elif change=='accepted':result['semantic_validation']['accepted']=False
    elif change=='valid':result['semantic_validation']['run_valid']=False
    elif change=='status':result['observed_status']='In Progress...'
    elif change=='candidate':result['candidate_id']='R343-AR080'
    elif change=='backtest':result['backtest_id']='other-run'
    elif change=='source':result['source']['source_inventory_pin']['sha256']='0'*64
    elif change=='statistics_pin':result['statistics_pin']['sha256']='0'*64
    elif change=='read':result['selected_result_read']=False
    else:result['paper_or_live_ready']=True
    with pytest.raises(m.Refused,match='a4_result'):m.validate_a4_result_fact(bind_fact(monkeypatch,fact))


def test_pure_plan_preserves_all_210_closure_pins_and_only_adds_engine_and_fact(monkeypatch):
    root=Path(__file__).resolve().parents[2]
    parent=(root/'scripts/arv2_r348_ar100_result_plan.json').read_bytes()
    raw=bind_fact(monkeypatch,a4_fact())
    additions={m.ENGINE_PATH:b'# synthetic engine\n',m.A4_RESULT_FACT.relative_to(m.ROOT).as_posix():raw}
    plan=json.loads(m.build_plan(parent,additions));old=json.loads(parent)['source_pins']
    assert m.pin(parent)==m.PARENT_PLAN_PIN
    assert len(old)==210 and len(plan['source_pins'])==212
    assert all(plan['source_pins'][name]==value for name,value in old.items())
    assert plan['source_pins'][m.CONSUMER_PATH]==m.CONSUMER_PIN
    assert m.VALIDATOR_PATH in old
    assert set(plan['source_pins'])-set(old)==set(additions)
    additions[m.CONSUMER_PATH]=b'# forbidden consumer refresh\n'
    with pytest.raises(m.Refused,match='plan'):m.build_plan(parent,additions)


def test_parent_closure_cannot_be_replaced_with_the_old_176_pin_inventory(monkeypatch):
    root=Path(__file__).resolve().parents[2]
    old=(root/'scripts/arv2_r347_legacy_six_plan_a4.json').read_bytes()
    raw=bind_fact(monkeypatch,a4_fact())
    additions={m.ENGINE_PATH:b'# synthetic engine\n',m.A4_RESULT_FACT.relative_to(m.ROOT).as_posix():raw}
    with pytest.raises(m.Refused,match='plan'):m.build_plan(old,additions)


class Candidate:
    candidate_id='R343-AR080'
    def cell_record(self):return {'candidate_id':self.candidate_id}


class Store:
    def __init__(self):self.events=[];self.application_dispatch_count=0;self.evaluated=False
    def journal(self,marker,value):self.events.append((marker,copy.deepcopy(value)))
    def look_accounting(self):return {'shared_look_delta':int(self.evaluated),
        'development_look_delta':int(self.evaluated),'infrastructure_look_delta':0,
        'accepted_result_cell_delta':0,'physical_request_count_measured':False}


class Operation:
    def __init__(self,cell,uploads,*,request,organization_id,user_id,attempt,journal):
        assert attempt==1 and cell['candidate_id']=='R343-AR080'
        self.request,self.organization=request,organization_id
        self.candidate=cell['candidate_id'];self.name='ARV2 LEGACY SIX R343-AR080 OCT2026'
        self.backtest_name=self.name+' A1';self.code_source='Codex R348 R343-AR080 A1'
        self.sources={f'module_{index:02d}.py':'# synthetic\n' for index in range(17)}
        self.sources['main.py']='# synthetic main\n'
        self.project_id=self.compile_id=self.launch_receipt=self.terminal_receipt=None
        self._lock=False;self._owner_raw=m.canonical(OWNER)
        self.metadata_admissions=[];self.last_access_observation=None
    def begin_once(self):
        self.request('projects/read',{})
        response=self.request('projects/create',{'name':self.name,'language':'Py','organizationId':self.organization})
        self.project_id=response['projects'][0]['projectId']
        self.request('projects/collaboration/lock/acquire',{'projectId':self.project_id,'codeSourceId':self.code_source})
        self._lock=True
        extra={'uid':None,'owner':False,'name':self.code_source,'publicId':'opaque-context',
            'permission':'write','liveControl':True,'profileImage':'','email':'','bio':''}
        self._general_pin=m.pin(m.canonical([OWNER,extra]))
        self.request('compile/create',{'projectId':self.project_id});self.compile_id='synthetic-compile'
        return {'state':'compiling'}
    def poll_compile(self,index):return {'state':'BuildSuccess'}
    def launch_once(self):
        row=self.request('backtests/create',{'projectId':self.project_id,'compileId':self.compile_id,
            'backtestName':self.backtest_name})['backtest']
        self.launch_receipt={'candidate_id':self.candidate,'attempt':1,'project_id':self.project_id,
            'compile_id':self.compile_id,'backtest_id':row['backtestId'],'backtest_name':self.backtest_name}
        if row['status'] in ('Completed.','Runtime Error'):self.terminal_receipt={**self.launch_receipt,'status':row['status']}
        return {'state':'launched','launch_receipt':self.launch_receipt,'launch_status':row['status']}
    def poll_status(self,index):
        row=self._history('synthetic',own=True)
        if row['status'] in ('Completed.','Runtime Error'):self.terminal_receipt={**self.launch_receipt,'status':row['status']}
        return {'status':row['status']}
    def _history(self,prefix,*,own):
        return self.request('backtests/list',{'projectId':self.project_id,'includeStatistics':False})['backtests'][0]


class Engine:
    REFERENCE_PROJECT=37165262
    ORGANIZATION_SHA256=m.pin(ORG.encode('ascii'))['sha256']
    CAPACITY_POLLS,CAPACITY_INTERVAL,COMPILE_POLLS,COMPILE_INTERVAL,STATUS_INTERVAL=3,60,30,2,60
    LegacySixQc=Operation
    PAYLOAD_KEYS={'authenticate':set(),'projects/read':{'projectId'},
        'projects/create':{'name','language','organizationId'},'projects/collaboration/read':{'projectId'},
        'projects/collaboration/lock/acquire':{'projectId','codeSourceId'},'files/read':{'projectId','codeSourceId'},
        'compile/create':{'projectId'},'backtests/create':{'projectId','compileId','backtestName'},
        'backtests/list':{'projectId','includeStatistics'},'object/properties':{'organizationId','key'}}
    @staticmethod
    def access_capacity(request,*,user_id,journal):
        request('authenticate',{})
        return {'organization_id':ORG,'public':{'capacity':{'available_count':1}}}


class API:
    def __init__(self,state,store):
        self.state,self.store,self.calls=state,store,[]
        self.created_status='In Progress...';self.statuses=['In Progress...','Completed.']
        self.extra_stat=False;self.source_drift=False;self.foreign_owner=False
    def row(self,status):
        op=self.state['operation']
        return {'projectId':op.project_id,'compileId':op.compile_id,'backtestId':'synthetic-run',
            'name':op.backtest_name,'status':status}
    def _exchange(self,endpoint,payload):
        self.calls.append((endpoint,copy.deepcopy(payload)));self.store.application_dispatch_count+=1
        if endpoint in ('compile/create','backtests/create'):self.store.evaluated=True
        op=self.state.get('operation');packet={'success':True}
        if endpoint=='projects/create':packet['projects']=[{'projectId':39999000}]
        elif endpoint=='projects/read' and not payload:packet['projects']=[]
        elif endpoint=='projects/read':
            owners=[copy.deepcopy(OWNER)]
            packet['projects']=[{'projectId':op.project_id,'name':op.name,'language':'Py','organizationId':ORG,
                'owner':True,'ownerId':USER+int(self.foreign_owner),'codeRunning':False,'libraries':[],
                'lastLiveDeployment':None,'leanEnvironment':0,'collaborators':owners}]
        elif endpoint=='projects/collaboration/read':
            packet.update(collaborators=[copy.deepcopy(OWNER)],userPermissions='write',userLiveControl=True)
        elif endpoint=='files/read':
            packet['files']=[{'projectId':op.project_id,'name':name,'content':raw+('# drift' if self.source_drift else '')}
                for name,raw in op.sources.items()]
        elif endpoint=='backtests/create':packet['backtest']=self.row(self.created_status)
        elif endpoint=='backtests/list':
            status=self.statuses.pop(0) if len(self.statuses)>1 else self.statuses[0]
            packet.update(backtests=[self.row(status)],count=1)
        elif endpoint=='backtests/read':
            stats={name:'{}' for name in m.STATISTICS}
            if self.extra_stat:stats['ARV2_UNEXPECTED']='{}'
            packet['backtest']={**self.row('Completed.'),'statistics':stats}
        return packet


class Validator:
    def __init__(self,store,accepted=True):self.store,self.accepted=store,accepted
    def validate_statistics(self,statistics,*,candidate_record,evaluation_sessions):
        assert self.store.events[-1][0].startswith('statistic-')
        assert len(statistics)==4 and evaluation_sessions==('synthetic-session',)
        return {'accepted':self.accepted,'run_valid':self.accepted,**m.FLAGS}


def operate(*,accepted=True,api_change=None):
    state={'operation':None};store=Store();api=API(state,store)
    if api_change:api_change(api)
    submission=SimpleNamespace(candidates=(Candidate(),),uploads=(),evaluation_sessions=('synthetic-session',),
        source_identity_json=m.canonical({'current_QC_admission_granted':False}))
    sleeps=[]
    value=m.operate(submission,'R343-AR080',engine=Engine,validator=Validator(store,accepted),api=api,
        secret={'QC_USER_ID':str(USER),'QC_API_TOKEN':'synthetic-not-a-real-token'},store=store,
        deadline=time.monotonic()+m.SECONDS-1,state=state,sleep=sleeps.append)
    return value,api,store,sleeps


def test_in_progress_waits_for_completed_before_one_selected_result_and_one_cell():
    value,api,store,sleeps=operate()
    assert sleeps==[60,60] and value['observed_status']=='Completed.'
    assert sum(name=='backtests/create' for name,_ in api.calls)==1
    assert sum(name=='backtests/read' for name,_ in api.calls)==1
    assert all(payload['includeStatistics'] is False for name,payload in api.calls if name=='backtests/list')
    assert value['look_accounting']['shared_look_delta']==value['look_accounting']['development_look_delta']==1
    assert value['look_accounting']['accepted_result_cell_delta']==1
    assert store.look_accounting()['accepted_result_cell_delta']==0


@pytest.mark.parametrize('failure',['runtime','source','owner','unexpected_stat','semantic'])
def test_runtime_or_current_binding_or_semantics_failure_never_accepts_result(failure):
    def change(api):
        if failure=='runtime':api.created_status='Runtime Error'
        elif failure=='source':api.source_drift=True
        elif failure=='owner':api.foreign_owner=True
        elif failure=='unexpected_stat':api.extra_stat=True
    with pytest.raises(m.Refused):operate(accepted=failure!='semantic',api_change=change)


def test_queue_budget_stops_without_result_read(monkeypatch):
    monkeypatch.setattr(m,'STATUS_CHECKS',2)
    with pytest.raises(m.Refused,match='not_completed'):
        operate(api_change=lambda api:setattr(api,'statuses',['In Queue...']))


def test_original_stdout_requires_actual_zero_exit_and_accepted_matching_result():
    value,_,_,_=operate();bound={'schema':m.SCHEMA,'candidate_id':'R343-AR080','attempt':1,
        'expected_head':'a'*40,'caller_sha256':'b'*64,'plan_sha256':'c'*64,'profile_sha256':'d'*64}
    record={'schema':m.SCHEMA+'-result','binding':bound,'attempt_consumed':True,'result':value}
    record['report_pin']=m.pin(m.canonical(record))
    raw=m.canonical(record)+b'\n'
    assert m.validate_original_stdout(raw,actual_exit=0,expected_binding=bound)==record
    for actual_exit in (2,None,False):
        with pytest.raises(m.Refused,match='output'):
            m.validate_original_stdout(raw,actual_exit=actual_exit,expected_binding=bound)
    record['result']['semantic_validation']['accepted']=False
    record['report_pin']=m.pin(m.canonical({key:item for key,item in record.items() if key!='report_pin'}))
    with pytest.raises(m.Refused,match='output'):
        m.validate_original_stdout(m.canonical(record)+b'\n',actual_exit=0,expected_binding=bound)


def test_native_scope_and_controls_do_not_include_ar100_or_old_operational_leaves():
    paths=[m.control(candidate) for candidate in m.CANDIDATES]
    assert len(set(paths))==6 and all(path.name.endswith('-A1') for path in paths)
    assert all('AR100' not in path.name for path in paths)
    policy=m.native_profile(m.CANDIDATES[0])
    for name in m.DATA_NAMES:assert str(m.DATA_DIRECTORY/name) in policy
    assert 'claim.json' not in policy and 'object/get' not in policy


@pytest.mark.parametrize('field',['expected_head','caller_sha256','plan_sha256','profile_sha256'])
def test_a4_fact_rehashed_wrong_d1_binding_is_still_refused(monkeypatch,field):
    fact=a4_fact();fact['original_result']['binding'][field]='f'*(40 if field=='expected_head' else 64)
    repin_a4(fact)
    with pytest.raises(m.Refused) as caught:m.validate_a4_result_fact(bind_fact(monkeypatch,fact))
    assert caught.value.args==('a4_result',)


@pytest.mark.parametrize('which',['report','stdout'])
def test_a4_fact_outer_pin_cannot_hide_forged_enclosed_report_or_stdout_pin(monkeypatch,which):
    fact=a4_fact()
    if which=='report':
        fact['original_result']['report_pin']['sha256']='0'*64
        fact['observation']['original_stdout_pin']=m.pin(m.canonical(fact['original_result'])+b'\n')
    else:fact['observation']['original_stdout_pin']['sha256']='0'*64
    with pytest.raises(m.Refused) as caught:m.validate_a4_result_fact(bind_fact(monkeypatch,fact))
    assert caught.value.args==('a4_result',)


def test_own_stdout_report_pin_is_recomputed_not_merely_well_shaped():
    result,_,_,_=operate()
    bound={'schema':m.SCHEMA,'candidate_id':'R343-AR080','attempt':1,'expected_head':'a'*40,
        'caller_sha256':'b'*64,'plan_sha256':'c'*64,'profile_sha256':'d'*64}
    value={'schema':m.SCHEMA+'-result','binding':bound,'attempt_consumed':True,'result':result,
        'report_pin':{'byte_count':1,'sha256':'e'*64}}
    with pytest.raises(m.Refused) as caught:
        m.validate_original_stdout(m.canonical(value)+b'\n',actual_exit=0,expected_binding=bound)
    assert caught.value.args==('output',)


@pytest.mark.parametrize('change',['identity','semantics','not_accepted','missing_candidate','duplicate_candidate'])
def test_a4_prerequisite_recomputes_with_current_candidate_input_and_sessions(monkeypatch,change):
    fact=a4_fact();bind_fact(monkeypatch,fact)
    candidate=SimpleNamespace(candidate_id='R343-AR100',cell_record=lambda:{'candidate_id':'R343-AR100'})
    submission=SimpleNamespace(candidates=(candidate,),source_identity_json=m.canonical(
        fact['original_result']['result']['input_source_identity']),evaluation_sessions=('synthetic-current-session',))
    if change=='identity':submission.source_identity_json=m.canonical({'synthetic_identity':'other'})
    elif change=='missing_candidate':submission.candidates=()
    elif change=='duplicate_candidate':submission.candidates=(candidate,candidate)
    recomputed=copy.deepcopy(fact['original_result']['result']['semantic_validation'])
    if change=='semantics':recomputed['newly_recomputed_field']='differs'
    if change=='not_accepted':recomputed['accepted']=False
    class Validator:
        @staticmethod
        def validate_statistics(statistics,*,candidate_record,evaluation_sessions):
            assert candidate_record=={'candidate_id':'R343-AR100'}
            assert evaluation_sessions==('synthetic-current-session',)
            assert statistics==fact['original_result']['result']['statistics']
            return recomputed
    with pytest.raises(m.Refused) as caught:m.validate_a4_prerequisite(fact,submission,Validator)
    assert caught.value.args==('a4_result',)


def test_matched_a4_prerequisite_returns_only_recomputed_identity_pins(monkeypatch):
    fact=a4_fact();bind_fact(monkeypatch,fact)
    candidate=SimpleNamespace(candidate_id='R343-AR100',cell_record=lambda:{'candidate_id':'R343-AR100'})
    submission=SimpleNamespace(candidates=(candidate,),source_identity_json=m.canonical(
        fact['original_result']['result']['input_source_identity']),evaluation_sessions=('synthetic-current-session',))
    validator=SimpleNamespace(validate_statistics=lambda *args,**kwargs:
        copy.deepcopy(fact['original_result']['result']['semantic_validation']))
    result=m.validate_a4_prerequisite(fact,submission,validator)
    assert result['accepted_A4_prerequisite_recomputed'] is True
    assert result['current_input_identity_pin']==m.pin(submission.source_identity_json)


def maximal_statistics():
    # Canonical JSON strings, at every allowed byte cap, with worst-case
    # backslash quoting when the original strings enter a JSON journal frame.
    return {name:m.canonical('\\'*(((16384 if name.endswith('DIAGNOSTICS') else 8192)-2)//2)).decode('ascii')
        for name in m.STATISTICS}


def assert_statistic_parts(events,statistics):
    grouped={name:[] for name in statistics}
    for marker,value in events:
        assert re.fullmatch('[a-z0-9-]{1,120}',marker)
        assert len(value['text'])<=4096
        grouped[value['name']].append(value)
    for name,parts in grouped.items():
        parts.sort(key=lambda value:value['part_index'])
        assert [value['part_index'] for value in parts]==list(range(parts[0]['part_count']))
        joined=''.join(value['text'] for value in parts)
        assert joined==statistics[name]
        assert all(value['original_string_pin']==m.pin(joined.encode('ascii')) for value in parts)


def test_all_40k_original_characters_fit_enforced_journal_frames_before_semantics():
    statistics=maximal_statistics();assert sum(len(text) for text in statistics.values())==40960
    events=[]
    class BoundedStore:
        def journal(self,marker,value):
            raw=m.canonical({'ordinal':len(events),'marker':marker,'value':value})+b'\n'
            assert len(raw)<=32768
            events.append((marker,copy.deepcopy(value)))
    m.journal_original_statistics(BoundedStore(),statistics)
    assert len(events)==10
    assert_statistic_parts(events,statistics)


def test_maximal_statistics_pass_real_store_journal_size_and_marker_checks(tmp_path):
    path=tmp_path/'events.jsonl';fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600)
    store=m.Store.__new__(m.Store)
    store.journal_fd=fd;store.event_count=0;store.events=bytearray()
    store.leaves=[['events.jsonl',fd,m.metadata(os.fstat(fd)),None,b'']]
    def verify():assert os.pread(fd,len(store.events)+1,0)==bytes(store.events)
    store.verify=verify
    try:
        statistics=maximal_statistics();m.journal_original_statistics(store,statistics)
        rows=[json.loads(raw) for raw in os.pread(fd,len(store.events)+1,0).splitlines()]
        assert_statistic_parts([(row['marker'],row['value']) for row in rows],statistics)
        assert store.event_count==len(rows)==10
    finally:os.close(fd)


@pytest.mark.parametrize('endpoint',['compile/create','backtests/create'])
def test_wrapper_refuses_reference_project_mutations_before_transport(monkeypatch,endpoint):
    captured=[]
    if endpoint=='compile/create':
        original=Operation.begin_once
        def begin(self):
            result=original(self)
            self.request(endpoint,{'projectId':Engine.REFERENCE_PROJECT})
            return result
        monkeypatch.setattr(Operation,'begin_once',begin)
    else:
        original=Operation.launch_once
        def launch(self):
            self.request(endpoint,{'projectId':Engine.REFERENCE_PROJECT,
                'compileId':self.compile_id,'backtestName':self.backtest_name})
            return original(self)
        monkeypatch.setattr(Operation,'launch_once',launch)
    with pytest.raises(m.Refused) as caught:operate(api_change=captured.append)
    assert caught.value.args==('request',)
    assert not any(name==endpoint and payload.get('projectId')==Engine.REFERENCE_PROJECT
        for name,payload in captured[0].calls)
