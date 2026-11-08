"""A4 injected control/ordering tests; no QC, credentials or production DATA."""
import copy
import json
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_r347_legacy_six_a4 as m


def refused(code, call):
    with pytest.raises(m.Refused) as caught:
        call()
    assert caught.value.args == (code,)


class FakeStore:
    def __init__(self):
        self.events = []
        self.application_dispatch_count = 0
        self.intents = 0
        self.first_evaluation_dispatch = None
    def journal(self, marker, value): self.events.append((marker, copy.deepcopy(value)))
    intent = m.Store.intent
    attempt = m.Store.attempt
    look_accounting = m.Store.look_accounting


def fixture(*, compile_states=('Building', 'BuildSuccess'), launch_status='In Progress...',
            statuses=('In Progress...',), initial_capacity=(1,), launch_states=('launched',), hook=None):
    events, store = [], FakeStore()
    objects = tuple(NS(object_store_key=f'synthetic/key-{index}.json', payload=f'opaque-{index}'.encode(),
        descriptor_json=m.canonical({'object_store_key':f'synthetic/key-{index}.json'})) for index in range(6))
    candidate = NS(candidate_id='R343-AR100', cell_record=lambda: {'synthetic_source': True})
    submission = NS(candidates=(candidate,), uploads=objects, source_identity_json=m.canonical({'synthetic_identity': True}))
    class EngineRefused(ValueError): pass
    class Engine:
        REFERENCE_PROJECT = 37165262
        ORGANIZATION_SHA256 = m.pin(b'a'*32)['sha256']
        PAYLOAD_KEYS = {'authenticate':set(), 'projects/read':{'projectId'},
            'projects/collaboration/lock/acquire':{'projectId','codeSourceId'},
            'compile/create':{'projectId'},'backtests/create':{'projectId'},'files/read':{'projectId'}}
        COMPILE_POLLS, COMPILE_INTERVAL, CAPACITY_POLLS, CAPACITY_INTERVAL = 3, 2, 3, 60
        STATUS_INTERVAL = 60
        Refused, FINITE = EngineRefused, frozenset(('source_changed',))
        @staticmethod
        def access_capacity(request, *, user_id, journal):
            count = sum(item == 'access' for item in events)
            events.append('access'); request('authenticate', {})
            return {'organization_id':'a'*32, 'public':{'capacity':{'available_count':initial_capacity[min(count,len(initial_capacity)-1)]}}}
        class LegacySixQc:
            def __init__(self, cell, uploads, **kwargs):
                assert cell == {'synthetic_source': True} and len(uploads)==6
                assert kwargs['attempt']==4 and kwargs['reconciliation_fact']=={'synthetic_fact': True}
                self.request=kwargs['request']; self.project_id=m.PROJECT; self.compile_id='compile-id'
                self.launch_receipt=self.terminal_receipt=None
                self.last_request=self.last_failure=None
                self.metadata_admissions=[]
                events.append('constructed')
            def begin_once(self):
                events.append('begin')
                if hook is not None: hook(self.request)
                self.metadata_admissions.append({'phase':'begin','objects':[]})
                self.request('compile/create',{'projectId':m.PROJECT})
                return {'state':'compiling'}
            def poll_compile(self,index):
                events.append('compile-'+str(index))
                return {'state':compile_states[min(index,len(compile_states)-1)]}
            def launch_once(self):
                index=sum(item.startswith('launch-') for item in events)
                events.append('launch-'+str(index))
                state=launch_states[min(index,len(launch_states)-1)]
                if state!='launched': return {'state':state}
                self.metadata_admissions.append({'phase':'launch-'+str(index),'objects':[]})
                self.request('backtests/create',{'projectId':m.PROJECT})
                self.launch_receipt={'candidate_id':'R343-AR100','attempt':4,'project_id':m.PROJECT,
                    'compile_id':'compile-id','backtest_id':'job-id','backtest_name':'synthetic-job'}
                if launch_status in ('Completed.','Runtime Error'):
                    self.terminal_receipt={**self.launch_receipt,'status':launch_status}
                return {'state':'launched','launch_receipt':dict(self.launch_receipt),
                    'terminal_receipt':self.terminal_receipt,'launch_status':launch_status}
            def poll_status(self,index):
                events.append('status-'+str(index)); status=statuses[min(index,len(statuses)-1)]
                if status in ('Completed.','Runtime Error'):
                    self.terminal_receipt={**self.launch_receipt,'status':status}
                return {'status':status}
    class API:
        deadline=None
        last_http_status,statuses,responses=200,[],[]
        def _exchange(self,endpoint,payload):
            store.intent(endpoint,payload.get('projectId'))
            store.attempt(endpoint,payload.get('projectId'))
            events.append(endpoint)
            return {'success':True}
    return submission,Engine,API(),store,events


def operate(parts, **kwargs):
    submission,engine,api,store,events=parts
    state=kwargs.pop('state',{})
    result=m.operate(submission,'R343-AR100',engine=engine,api=api,secret={'QC_USER_ID':'1'},
        store=store,deadline=time.monotonic()+3599,state=state,
        reconciliation_fact={'synthetic_fact':True},sleep=lambda seconds:events.append('sleep-'+str(seconds)),**kwargs)
    return result,state


def test_A4_one_compile_launch_and_actual_running_not_result():
    parts=fixture(); result,state=operate(parts)
    events=parts[-1]
    assert events.count('compile/create')==events.count('backtests/create')==1
    assert result['observed_status']=='In Progress...' and result['running_observed'] is True
    assert result['terminal_identity_observed'] is False and result['terminal_receipt'] is None
    assert result['result_read'] is False and result['paper_or_live_ready'] is False
    assert result['look_accounting']['shared_look_delta']==1
    assert result['look_accounting']['development_look_delta']==1
    assert result['look_accounting']['first_application_dispatch']['endpoint']=='compile/create'
    assert result['input_metadata_admission']['observations']==state['operation'].metadata_admissions
    assert 'backtests/read' not in events and 'projects/create' not in events


@pytest.mark.parametrize('status', ['In Progress...','Completed.'])
def test_queued_allocation_is_followed_until_running_or_terminal_identity(status):
    parts=fixture(launch_status='In Queue...',statuses=('In Queue...',status))
    result,state=operate(parts)
    assert parts[-1].count('sleep-60')==2
    assert result['observed_status']==status
    assert result['running_observed'] is (status=='In Progress...')
    assert result['terminal_identity_observed'] is (status=='Completed.')
    assert result['terminal_receipt']==state['operation'].terminal_receipt
    if status=='Completed.': assert result['terminal_receipt']['status']=='Completed.'


@pytest.mark.parametrize('status',['Runtime Error','Unknown','InQueue'])
def test_nonaccepted_launch_status_preserves_allocation_but_refuses(status):
    parts,state=fixture(launch_status=status),{}
    refused('launch',lambda:operate(parts,state=state))
    assert state['operation'].launch_receipt['backtest_id']=='job-id'
    assert parts[-1].count('backtests/create')==1


def test_runtime_error_after_queue_keeps_terminal_receipt():
    parts,state=fixture(launch_status='In Queue...',statuses=('Runtime Error',)),{}
    refused('launch',lambda:operate(parts,state=state))
    assert state['operation'].terminal_receipt['status']=='Runtime Error'
    assert parts[-1].count('backtests/create')==1


def test_queue_wait_is_bounded_and_no_second_launch():
    parts,state=fixture(launch_status='In Queue...',statuses=('In Queue...',)),{}
    refused('launch',lambda:operate(parts,state=state))
    assert sum(item.startswith('status-') for item in parts[-1])==m.STATUS_CHECKS
    assert parts[-1].count('sleep-60')==m.STATUS_CHECKS
    assert parts[-1].count('backtests/create')==1


def test_initial_capacity_wait_precedes_mutation_and_is_bounded():
    parts=fixture(initial_capacity=(0,0,1)); operate(parts)
    assert parts[-1].index('begin')>parts[-1].index('sleep-60')
    assert parts[-1].count('access')==3 and parts[-1].count('begin')==1
    parts=fixture(initial_capacity=(0,))
    refused('capacity',lambda:operate(parts))
    assert 'begin' not in parts[-1] and 'compile/create' not in parts[-1]
    assert parts[3].look_accounting()['shared_look_delta']==0


def test_compile_failure_consumes_one_look_without_launch():
    parts=fixture(compile_states=('BuildError',))
    refused('compile',lambda:operate(parts))
    assert 'backtests/create' not in parts[-1]
    assert parts[3].look_accounting()['shared_look_delta']==1


@pytest.mark.parametrize('endpoint,payload',[
    ('projects/create',{'name':'NO'}),('backtests/read',{'projectId':m.PROJECT}),
    ('files/delete',{'projectId':m.PROJECT}),('object/get',{'key':'synthetic/key-0.json'}),
    ('object/set',{}),('projects/collaboration/lock/release',{'projectId':m.PROJECT}),
    ('projects/read',{}),('projects/read',{'projectId':123}),
    ('projects/read',{'projectId':m.PROJECT,'codeSourceId':'Codex R347 R343-AR100 A4'}),
    ('files/read',{'projectId':m.PROJECT,'codeSourceId':'Mia'}),
    ('object/properties',{'organizationId':'a'*32,'key':'unknown'}),
    ('object/properties',{'organizationId':'b'*32,'key':'synthetic/key-0.json'}),
])
def test_transport_wrapper_refuses_out_of_scope_before_API(endpoint,payload):
    parts=fixture(hook=lambda request:request(endpoint,payload))
    refused('request',lambda:operate(parts))
    assert endpoint not in parts[-1] and 'backtests/create' not in parts[-1]


def test_only_one_fresh_A4_lock_dispatch():
    payload={'projectId':m.PROJECT,'codeSourceId':'Codex R347 R343-AR100 A4'}
    def twice(request):
        request('projects/collaboration/lock/acquire',payload)
        request('projects/collaboration/lock/acquire',payload)
    parts=fixture(hook=twice)
    refused('request',lambda:operate(parts))
    assert parts[-1].count('projects/collaboration/lock/acquire')==1


def test_look_accounting_never_doublecounts_compile_then_launch():
    store=FakeStore()
    for endpoint in ('authenticate','compile/create','backtests/create'):
        project=None if endpoint=='authenticate' else m.PROJECT
        store.intent(endpoint,project); store.attempt(endpoint,project)
    value=store.look_accounting()
    assert value=={'shared_look_delta':1,'development_look_delta':1,'infrastructure_look_delta':0,
        'accepted_result_cell_delta':0,'first_application_dispatch':{'endpoint':'compile/create',
        'application_dispatch_ordinal':1,'candidate_id':'R343-AR100','attempt':4},
        'physical_request_count_measured':False}


@pytest.mark.parametrize('closing_failure,DATA_failure',[(False,False),(True,False),(False,True)])
def test_claim_DATA_normal_return_credentials_and_close_order(monkeypatch,closing_failure,DATA_failure):
    events=[]
    class Store(FakeStore):
        def __init__(self,*args): super().__init__()
        def __enter__(self): events.append('exclusive-store'); return self
        def __exit__(self,*args): events.append('store-closed')
        def write(self,name,value): events.append(name); return m.pin(b'fixture')
        def verify(self): events.append('store-verify')
    class Consumer:
        def __init__(self,**kwargs): assert kwargs['fact_bytes']==b'exact-fact\n'
        def __enter__(self): events.append('DATA-enter'); return NS(value='immutable')
        def __exit__(self,*args):
            events.append('DATA-normal-return')
            if DATA_failure: raise m.Refused('data')
    class Transport:
        @staticmethod
        def credentials(value): events.append('credentials'); return value
        class API:
            def __init__(self,*args): events.append('API')
            def close(self): events.append('API-close')
    class Sources:
        def __init__(self,*args):
            self.consumer=NS(FreshPlainSubmission=Consumer,Refused=type('ConsumerRefused',(ValueError,),{}),FINITE=frozenset())
            self.transport=Transport; self.security=None
            self.engine=NS(PAYLOAD_KEYS={},FINITE=frozenset())
            self.preparation_fact_bytes=b'exact-fact\n';self.reconciliation_fact={'synthetic_fact':True}
        def __enter__(self): return self
        def __exit__(self,*args):
            events.append('sources-normal-return')
            if closing_failure: raise m.Refused('source_changed')
        def verify(self): events.append('sources-verify')
    def injected(*args,**kwargs):
        events.append('operate')
        kwargs['state']['operation']=NS(project_id=m.PROJECT,compile_id='compile-id',launch_receipt={'backtest_id':'job-id'})
        return {'synthetic':True}
    monkeypatch.setattr(m,'preflight',lambda *args:{'synthetic':True})
    monkeypatch.setattr(m,'Sources',Sources);monkeypatch.setattr(m,'Store',Store)
    monkeypatch.setattr(m,'operate',injected)
    if closing_failure or DATA_failure:
        refused('source_changed' if closing_failure else 'data',lambda:m.run(NS(candidate='R343-AR100')))
        if closing_failure: assert m.LAST_FAILURE['allocated_identities']['backtest_id']=='job-id'
    else:
        assert m.run(NS(candidate='R343-AR100'))['attempt_consumed'] is True
    assert events.index('claim.json')<events.index('DATA-enter')
    if DATA_failure: assert 'credentials' not in events and 'API' not in events
    else: assert events.index('DATA-normal-return')<events.index('credentials')<events.index('API')<events.index('operate')


def test_exact_fixed_control_plain_eight_read_scope_no_old_artifacts():
    profile=m.profile_record('R343-AR100');native=m.native_profile('R343-AR100')
    assert profile['attempt']==4 and profile['prior_attempts_consumed']==3
    assert profile['recovery_project_id']==39054561 and profile['queue_status_checks']==30
    assert len(m.DATA_NAMES)==8 and 'claim.json' not in m.DATA_NAMES
    assert str(m.control('R343-AR100')).endswith('/R347-20261107-AR100-A4')
    assert 'R343-20261106-B' not in native and '/Volumes' in native and '/usr/bin/security' in native
    assert all(str(m.DATA_DIRECTORY/name) in native for name in m.DATA_NAMES)
    assert 'object/get' not in profile['object_policy']


@pytest.mark.parametrize('candidate',['R343-AR0','R343-AR50','R343-AR75','R343-AR150','R343-AR200','R343-AR100-A5'])
def test_no_other_arm_or_new_attempt(candidate): refused('arguments',lambda:m.control(candidate))


def test_public_plan_preserves_all170_parent_pins_and_only_six_additions():
    plan=json.loads(m.PLAN.read_bytes());parent=json.loads(m.PARENT_PLAN.read_bytes())
    assert m.pin(m.PARENT_PLAN.read_bytes())==m.PARENT_PLAN_PIN
    assert len(parent['source_pins'])==170 and len(plan['source_pins'])==176
    assert all(plan['source_pins'][key]==value for key,value in parent['source_pins'].items())
    assert set(plan['source_pins'])==set(parent['source_pins'])|{m.CONSUMER_PATH,m.ENGINE_PATH,*m.FIXED_ADDITIONAL_PINS}
    assert all(plan['source_pins'][key]==value for key,value in m.FIXED_ADDITIONAL_PINS.items())
    assert plan['attempt']==4 and plan['project_id']==m.PROJECT


def test_failure_output_preserves_accountable_look_without_raw_error():
    _,engine,api,store,_=fixture()
    store.intent('compile/create',m.PROJECT);store.attempt('compile/create',m.PROJECT)
    sources=NS(engine=engine,consumer=NS(Refused=type('ConsumerRefused',(ValueError,),{}),FINITE=frozenset()),
        transport=NS(Refused=type('TransportRefused',(ValueError,),{}),FINITE=frozenset()))
    result=m.failure_evidence({'api':api,'operation':None,'store':store},sources,RuntimeError('SENSITIVE'))
    assert result['look_accounting']['shared_look_delta']==1 and b'SENSITIVE' not in m.canonical(result)
