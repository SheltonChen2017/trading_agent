"""Pure privacy projections and injected two-call protocol; no QC or DATA."""
import copy
import json
import time
from types import SimpleNamespace as NS

import pytest

from scripts import observe_arv2_r348_ar100_runtime_error as m


def inventory():
    text='plain Object Store existence check failed'
    return {'schema':'arv2-r348-public-runtime-error-inventory-v1',
        'file_whitelist':['accepted_risk_order_level_input_runtime.py','main.py']+[f'file{i}.py' for i in range(16)],
        'known_literals':{m.sha(text.encode()):text},'attribute_whitelist':['get','contains_key','read_bytes'],
        'key_whitelist':['record_count'],'exception_classes':['AttributeError','KeyError','AcceptedRiskOrderLevelInputRuntimeError']}


def test_inventory_is_static_public_hash_identity_only():
    value=json.loads((m.ROOT/m.INVENTORY).read_bytes());m.validate_inventory(value)
    assert m.pin((m.ROOT/m.INVENTORY).read_bytes())==m.INVENTORY_PIN
    assert len(value['file_whitelist'])==18 and len(value['source_pins'])==17
    assert all(m.sha(text.encode())==digest for digest,text in value['known_literals'].items())


@pytest.mark.parametrize('prefix',['','AcceptedRiskOrderLevelInputRuntimeError: ','AcceptedRiskOrderLevelInputRuntimeError : '])
def test_only_exact_whole_known_public_literal_is_retained(prefix):
    text='plain Object Store existence check failed'
    value=m.project_text(prefix+text,inventory())
    assert value['known_public_literal']==text
    assert value['byte_count']==len((prefix+text).encode())
    assert value['sha256']==m.sha((prefix+text).encode())


@pytest.mark.parametrize('text',['prefix plain Object Store existence check failed','plain Object Store existence check failed suffix',
    'secret API TOKEN 123','price missing for PRIVATE-STOCK','AttributeError: private-name','\u00e9secret'])
def test_unrecognized_or_formatted_error_is_hash_only(text):
    value=m.project_text(text,inventory())
    assert value['known_public_literal'] is value['structured_error'] is None
    assert value['finite_exception_class'] is None
    assert text not in m.canonical(value).decode()


@pytest.mark.parametrize('kind',['str','dict','list','tuple','int','NoneType','bool','Decimal'])
def test_AttributeError_retains_only_closed_type_and_selected_public_attribute(kind):
    value=m.project_text(f"AttributeError: '{kind}' object has no attribute 'contains_key'",inventory())
    assert value['structured_error']=={'kind':'AttributeError','object_type':kind,'attribute':'contains_key'}
    assert value['finite_exception_class']=='AttributeError' and value['known_public_literal'] is None


@pytest.mark.parametrize('text',["AttributeError: 'PrivateUserType' object has no attribute 'get'",
    "AttributeError: 'str' object has no attribute 'SECRET'", "AttributeError: 'str' object has no attribute 'get' trailing",
    "KeyError: 'PRIVATE-STOCK'", "KeyError: 'record_count' trailing"])
def test_grammar_never_admits_unknown_identifiers_or_trailing_text(text):
    value=m.project_text(text,inventory());assert value['structured_error'] is None
    assert text not in m.canonical(value).decode()


def test_exact_public_keyerror_identifier_is_retained_without_raw_field():
    value=m.project_text("KeyError: 'record_count'",inventory())
    assert value['structured_error']=={'kind':'KeyError','key':'record_count'}
    assert 'text' not in value and 'message' not in value


def test_frames_retain_only_known_basename_line_and_function_hash():
    trace='  File "/secret/private/path/accepted_risk_order_level_input_runtime.py", line 199, in secret_function\n'
    trace+='  File "/secret/private.py", line 3, in secret_function\n in main.py: line 10\n'
    result=m.frames(trace,inventory())
    assert result==[{'file':'accepted_risk_order_level_input_runtime.py','line':199,
        'function_sha256':m.sha(b'secret_function')},{'file':'main.py','line':10,'function_sha256':None}]
    assert 'secret' not in m.canonical(result).decode()


@pytest.mark.parametrize('line',[0,20001,99999])
def test_unbounded_frame_lines_are_omitted(line):
    assert m.frames(f'File "main.py", line {line}, in secret',inventory())==[]


@pytest.mark.parametrize('value',[True,1,{},[]])
def test_wrong_error_types_refuse_without_stringifying(value):
    with pytest.raises(m.Refused):m.project_text(value,inventory())


def packet(status='Runtime Error'):
    return {'success':True,'backtest':{'projectId':m.PROJECT,'backtestId':m.BACKTEST,
        'compileId':m.COMPILE,'name':m.BACKTEST_NAME,'status':status,
        'error':"AttributeError: 'str' object has no attribute 'contains_key'",
        'stacktrace':'File "/private/main.py", line 27, in private_function',
        'statistics':{'NEVER':'RETAIN'},'charts':{'NEVER':'RETAIN'}}}


def test_exact_two_readonly_requests_and_only_projected_error_leave_memory():
    calls=[]
    class API:
        parent_deadline=time.monotonic()+179;statuses=[];responses=[]
        def _exchange(self,endpoint,payload):
            calls.append((endpoint,copy.deepcopy(payload)))
            return {'success':True} if endpoint=='authenticate' else packet()
    result=m.observe(API(),inventory())
    assert calls==[('authenticate',{}),('backtests/read',{'projectId':m.PROJECT,'backtestId':m.BACKTEST})]
    assert result['observed_status']=='Runtime Error' and result['projection_complete'] is True
    assert result['error']['structured_error']['attribute']=='contains_key'
    encoded=m.canonical(result).decode()
    assert 'NEVER' not in encoded and '/private' not in encoded and 'private_function' not in encoded
    assert all(result[key] is False for key in m.FLAGS)


@pytest.mark.parametrize('field,value',[('projectId',123),('projectId',True),('backtestId','OTHER'),
    ('compileId','OTHER'),('status','Completed.'),('name','OTHER')])
def test_response_identity_mismatch_refuses_no_extra_request(field,value):
    calls=[];response=packet();response['backtest'][field]=value
    class API:
        parent_deadline=time.monotonic()+179;statuses=[];responses=[]
        def _exchange(self,endpoint,payload):calls.append(endpoint);return {'success':True} if endpoint=='authenticate' else response
    with pytest.raises(m.Refused):m.observe(API(),inventory())
    assert calls==['authenticate','backtests/read']


def test_absent_error_fields_are_explicit_unknown_not_guessed_aliases():
    response=packet();response['backtest'].pop('error');response['backtest'].pop('stacktrace')
    response['backtest']['errorMessage']='NEVER RETAIN'
    class API:
        parent_deadline=time.monotonic()+179;statuses=[];responses=[]
        def _exchange(self,endpoint,payload):return {'success':True} if endpoint=='authenticate' else response
    value=m.observe(API(),inventory())
    assert value['error']['present'] is value['stacktrace']['present'] is False
    assert value['frames']==[] and 'NEVER' not in m.canonical(value).decode()


def test_profile_native_scope_excludes_all_private_DATA_and_old_controls():
    profile=m.profile_record();native=m.native_profile()
    assert profile['max_requests']==2 and profile['seconds']==180
    assert profile['private_DATA_or_old_controls_read'] is False
    assert str(m.CONTROL).endswith('/R348-20261107-AR100-ERROR-A')
    assert '/Volumes' in native and '/usr/bin/security' in native
    assert '/R348-20261107-AR100-RESULT-A' not in native and '/R346-20261107-A' not in native
    assert set(m.ENDPOINTS)=={'authenticate','backtests/read'}


def test_new_plan_preserves_all210_used_D1_pins_and_only_three_new_inputs():
    parent=json.loads(m.PARENT_PLAN.read_bytes());plan=json.loads(m.PLAN.read_bytes())
    assert m.pin(m.PARENT_PLAN.read_bytes())==m.PARENT_PIN and len(parent['source_pins'])==210
    assert len(plan['source_pins'])==213
    assert all(plan['source_pins'][key]==value for key,value in parent['source_pins'].items())
    assert set(plan['source_pins'])==set(parent['source_pins'])|{m.CUSTODY,m.FACT,m.INVENTORY}
    assert plan['source_pins'][m.FACT]==m.FACT_PIN and plan['source_pins'][m.INVENTORY]==m.INVENTORY_PIN


def original_fixture():
    public=json.loads((m.ROOT/m.INVENTORY).read_bytes())
    bound={'schema':m.SCHEMA,'expected_head':'1'*40,'caller_sha256':'2'*64,'plan_sha256':'3'*64,
        'profile_sha256':m.sha(m.canonical(m.profile_record()))}
    class API:
        parent_deadline=time.monotonic()+179
        statuses=[{'endpoint':name,'http_status':200} for name in m.ENDPOINTS]
        responses=[{'endpoint':name,**m.pin(b'fixture')} for name in m.ENDPOINTS]
        def _exchange(self,endpoint,payload):return {'success':True} if endpoint=='authenticate' else packet()
    summary=m.observe(API(),public)
    report={'schema':m.SCHEMA+'-result','binding':bound,'attempt_consumed':True,'complete':True,
        'summary':summary,'application_dispatch_count':2,'request_intent_count':2,
        'physical_request_count_measured':False,**m.FLAGS}
    return public,bound,{**report,'report_pin':m.pin(m.canonical(report))}


def test_original_output_is_pure_actual_exit_and_pin_qualified():
    public,bound,envelope=original_fixture();raw=m.canonical(envelope)+b'\n'
    result=m.validate_original_stdout(raw,actual_exit=0,expected_binding=bound,inventory=public)
    assert result['diagnostic_complete'] is True and result['original_envelope']==envelope
    assert 'not_independent_disk_process_or_authenticated_cause' in result['qualification']


@pytest.mark.parametrize('actual_exit',[2,True,None,1,-1])
def test_original_success_cannot_hide_nonzero_or_unknown_actual_exit(actual_exit):
    public,bound,envelope=original_fixture()
    with pytest.raises(m.Refused):m.validate_original_stdout(m.canonical(envelope)+b'\n',actual_exit=actual_exit,expected_binding=bound,inventory=public)


@pytest.mark.parametrize('fault',['rawtext','unknown_frame','bad_line','raw_function','changed_id','extra_field'])
def test_output_validator_rejects_unapproved_disclosure_even_with_rehashed_report(fault):
    public,bound,envelope=original_fixture();summary=envelope['summary']
    if fault=='rawtext':summary['error']['known_public_literal']='PRIVATE TOKEN'
    elif fault=='unknown_frame':summary['frames'][0]['file']='private.py'
    elif fault=='bad_line':summary['frames'][0]['line']=20001
    elif fault=='raw_function':summary['frames'][0]['function_sha256']='private_function'
    elif fault=='changed_id':summary['known_identities']['project_id']=123
    else:summary['raw_error']='PRIVATE TOKEN'
    envelope['report_pin']=m.pin(m.canonical({k:v for k,v in envelope.items() if k!='report_pin'}))
    with pytest.raises(m.Refused):m.validate_original_stdout(m.canonical(envelope)+b'\n',actual_exit=0,expected_binding=bound,inventory=public)


def test_finite_original_failure_remains_unaccepted_and_no_binding_is_invented():
    public,bound,_=original_fixture()
    envelope={'schema':m.SCHEMA+'-failure','failure_code':'transport','observation':None,**m.FLAGS}
    result=m.validate_original_stdout(m.canonical(envelope)+b'\n',actual_exit=2,expected_binding=bound,inventory=public)
    assert result['diagnostic_complete'] is False and result['original_envelope']==envelope
    assert 'binding' not in result['original_envelope']


def test_original_encoding_is_actual_one_LF_and_rejects_trailing_or_bad_report_pin():
    public,bound,envelope=original_fixture();raw=m.canonical(envelope)+b'\n'
    assert raw.endswith(bytes((10,))) and not raw.endswith(b'\\n')
    for wrong in (raw+b'\n',raw[:-1],raw+b'{}',b' '+raw):
        with pytest.raises(m.Refused):m.validate_original_stdout(wrong,actual_exit=0,expected_binding=bound,inventory=public)
    envelope['report_pin']['sha256']='0'*64
    with pytest.raises(m.Refused):m.validate_original_stdout(m.canonical(envelope)+b'\n',actual_exit=0,expected_binding=bound,inventory=public)


@pytest.mark.parametrize('closing_failure',[False,True])
def test_run_new_exclusive_claim_precedes_credentials_and_closes_sources(monkeypatch,closing_failure):
    events=[]
    class API:
        statuses=[];responses=[]
        def __init__(self,*args):events.append('API')
        def close(self):events.append('API-close')
    class TLS:
        @staticmethod
        def credentials(value):events.append('credentials');return value
    TLS.API=API
    class Sources:
        def __init__(self,*args):self.tls=TLS;self.security=None;self.inventory=inventory()
        def __enter__(self):events.append('source-enter');return self
        def verify(self):events.append('source-verify')
        def __exit__(self,*args):
            events.append('source-normal-return')
            if closing_failure:raise m.Refused('source_changed')
    class Store:
        intents=application_dispatch_count=2
        def __init__(self,*args):pass
        def __enter__(self):events.append('exclusive-store');return self
        def __exit__(self,*args):events.append('store-normal-return')
        def write(self,name,value):events.append(name);return m.pin(m.canonical(value))
        def verify(self):events.append('store-verify')
    def observe(*args):events.append('observe');m.SAFE={'synthetic_safe':True};return m.SAFE
    monkeypatch.setattr(m,'preflight',lambda *args:{'synthetic':True});monkeypatch.setattr(m,'Sources',Sources)
    monkeypatch.setattr(m,'Store',Store);monkeypatch.setattr(m,'observe',observe)
    if closing_failure:
        with pytest.raises(m.Refused):m.run(NS())
        assert m.SAFE=={'synthetic_safe':True}
    else:assert m.run(NS())['complete'] is True
    assert events.index('claim.json')<events.index('credentials')<events.index('API')<events.index('observe')
    assert events.index('API-close')<events.index('source-normal-return')


def test_real_Store_original_FDs_and_canonical_claim_are_preserved(tmp_path,monkeypatch):
    root=tmp_path/'synthetic-root';root.mkdir(mode=0o755);root.chmod(0o755)
    (root/'artifacts').mkdir(mode=0o700)
    control=root/'artifacts'/'error-results'/'once'
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'CONTROL',control)
    security=NS(snapshot=lambda fd:(),Refusal=type('SecurityRefusal',(ValueError,),{}))
    with m.Store(security) as store:
        store.write('claim.json',{'synthetic':True})
        store.intent('authenticate',None);store.attempt('authenticate',None)
        store.intent('backtests/read',m.PROJECT);store.attempt('backtests/read',m.PROJECT)
        store.write('report.json',{'synthetic_report':True});store.verify()
        assert store.application_dispatch_count==store.intents==2
        assert (control/'claim.json').read_bytes()==m.canonical({'synthetic':True})
        assert len(store.leaves)==6
    with pytest.raises(m.Refused):m.Store(security).__enter__()


@pytest.mark.parametrize('seconds',[-1,181,float('inf'),float('nan')])
def test_parent_deadline_is_finite_positive_and_bounded(seconds):
    with pytest.raises(m.Refused):m.budget(time.monotonic()+seconds)


def test_incompatible_host_refuses_before_source_claim_or_credentials(monkeypatch):
    monkeypatch.setattr(m.sys,'platform','linux')
    args=NS(expected_head='1'*40,caller_sha256='2'*64,plan_sha256='3'*64)
    with pytest.raises(m.Refused) as caught:m.preflight(args,time.monotonic()+179)
    assert caught.value.args==('host',)
