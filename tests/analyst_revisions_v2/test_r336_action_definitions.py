"""Synthetic generic-doc reduction and one-shot isolation; no actual DATA."""
import ast
import copy
from contextlib import ExitStack
import csv
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS
import pytest
from scripts import inspect_arv2_r336_action_definitions as m
from scripts import arv2_r335_action_types as dictionary


def args():return NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def refuse(code,call):
    with pytest.raises(m.Refused) as error:call()
    assert m.finite(error.value)==code


def csv_bytes(rows,header=dictionary.FIELDS):
    text=io.StringIO(newline='');writer=csv.writer(text,lineterminator='\n');writer.writerow(header)
    for row in rows:writer.writerow([row[dictionary.VARIANTS[name]] for name in header])
    return text.getvalue().encode()


@pytest.fixture
def inputs(monkeypatch):
    rows=[{'table':'actiontypes','indicator':'generic'+str(n),'isFilter':'N','isPrimaryKey':'N',
        'title':'Generic documentation '+str(n),'description':'Normative generic definition '+str(n),'unitType':'text'} for n in range(75)]
    events=[]
    for n in range(33):
        events.append({'source_row_ordinal':n,'row':{'date':'PRIVATE-DATE','action':'generic'+str(n%3),
            'ticker':'PRIVATE-TICKER','name':'PRIVATE-NAME','value':'PRIVATE-VALUE','contraticker':'PRIVATE-CONTRA','contraname':'PRIVATE-COUNTERNAME'},
            'action_family':'unknown','primary_owner_case_ordinals':[n%5],'shared_primary_ticker_ownership':False,
            'literal_counterparty_metadata_lead':None,'opaque_contraticker_verbatim':'PRIVATE-CONTRA','ticker_change_search_lead':None,
            'same_security_or_share_class_proven':False,'alias_admitted':False,'corporate_action_applied':False})
    private={'schema':'arv2-r335-offline-actions-metadata-links-v1-private','input_DATA_pins':{},'original_G_plan':{},
        'projected_v2_plan':{},'original_G_transport':{},'all_original_rows':events,'cases':[],'inspection':{},'retained_H_observation':{},**m.I_FALSE_FLAGS}
    state=NS(rows=rows,events=private,header=dictionary.FIELDS)
    def repin():
        state.event_raw=m.canonical(state.events);state.dictionary_raw=csv_bytes(state.rows,state.header)
        state.transport={'schema':dictionary.SCHEMA+'-private-transport','plan_sha256':m.sha(m.canonical(dictionary.plan_record())),
            'request_ordinal':0,'role':'actiontypes','http_status':200,'body_pin':m.pin(state.dictionary_raw),'CSV_validation_complete':False}
        state.transport_raw=m.canonical(state.transport)
        captures={'schema':dictionary.SCHEMA+'-capture','plan_sha256':state.transport['plan_sha256'],
            'application_dispatch_attempts':1,'provider_request_count':None,'http_status':200,'response_pin':m.pin(state.dictionary_raw),
            'CSV_validation_complete':False,**dictionary.FALSE_FLAGS}
        monkeypatch.setattr(m,'J_PROVENANCE',{**m.J_PROVENANCE,'capture_receipt_sha256':m.sha(m.canonical(captures))})
        monkeypatch.setattr(m,'DATA_PLAN',{name:{'relative_path':'artifacts/analyst_revisions_v2/synthetic/'+name,**m.pin(raw)}
            for name,raw in (('events',state.event_raw),('dictionary',state.dictionary_raw),('transport',state.transport_raw))})
        return state
    state.repin=repin
    state.run=lambda:m.inspect_definitions(state.event_raw,state.dictionary_raw,state.transport_raw,dictionary)
    return repin()


def test_only_generic_exact_definitions_leave_the_private_reduction(inputs):
    value=inputs.run();raw=m.canonical(value)
    assert value['generic_documentation_only'] is True and value['requested_code_count']==value['matched_code_count']==3
    assert value['matched_definition_row_count']==3 and value['missing_code_count']==0
    assert set(value['definitions'])=={'generic0','generic1','generic2'}
    assert value['definitions']['generic0'][0]['definition']=='Normative generic definition 0'
    assert all(value[name] is False for name in m.FALSE_FLAGS)
    for text in (b'PRIVATE-',b'case_ordinal',b'source_row_ordinal',b'primary_owner_case_ordinals',b'event_link_count'):assert text not in raw
    assert len(raw)<=65536 and m.validate_documentation(value)==value


def test_I_permutation_or_frequency_changes_do_not_change_generic_documentation(inputs):
    original=inputs.run();events=inputs.events['all_original_rows'];events.reverse()
    for n,event in enumerate(events):event['source_row_ordinal']=n
    events[0]['row']['action']='generic0';inputs.repin()
    assert inputs.run()==original


def test_UTF8_multiline_and_quoted_generic_definition_preserved_exactly(inputs):
    text='Generic “documentation”, not instructions.\nSecond line with accented é.'
    inputs.rows[0]['description']=text;inputs.repin()
    assert inputs.run()['definitions']['generic0'][0]['definition']==text


def test_all_matching_duplicate_and_conflicting_definitions_preserved_without_default(inputs):
    inputs.rows[74]=dict(inputs.rows[0]);inputs.rows[74]['description']='Different generic definition';inputs.repin()
    value=inputs.run();items=value['definitions']['generic0']
    assert len(items)==2 and [item['dictionary_row_ordinal'] for item in items]==[0,74]
    assert value['repeated_indicator_row_count']==value['conflicting_definition_code_count']==1
    assert len({item['full_generic_row_pin']['sha256'] for item in items})==2
    assert value['definitions_interpreted'] is value['aliases_generated'] is False


def test_missing_exact_code_is_explicit_no_substring_match_or_heuristic(inputs):
    inputs.rows[1]['indicator']='generic1suffix';inputs.repin();value=inputs.run()
    assert value['missing_code_count']==1 and value['matched_code_count']==2 and 'generic1' not in value['definitions']


def test_unmatched_action_text_has_no_generic_dictionary_provenance_and_stays_private(inputs):
    inputs.events['all_original_rows'][0]['row']['action']='PRIVATE-UNRECOGNIZED-ACTION';inputs.repin()
    value=inputs.run()
    assert value['missing_code_count']==1 and b'PRIVATE-UNRECOGNIZED-ACTION' not in m.canonical(value)


@pytest.mark.parametrize('role',['events','dictionary','transport'])
def test_exact_external_DATA_pin_precedes_parsing(inputs,role):
    selected={'events':'event_raw','dictionary':'dictionary_raw','transport':'transport_raw'}[role]
    setattr(inputs,selected,getattr(inputs,selected)+b' ');refuse('source_pin',inputs.run)


@pytest.mark.parametrize('which',['eventbool','extraevent','alias','codeblank','codenonASCII','codectrl','codeoversize','extraI','Iflag'])
def test_private_I_shape_and_original_false_flags_are_checked(inputs,which):
    event=inputs.events['all_original_rows'][0]
    if which=='eventbool':event['source_row_ordinal']=False
    elif which=='extraevent':event['extra']='PRIVATE'
    elif which=='alias':event['alias_admitted']=True
    elif which=='codeblank':event['row']['action']=''
    elif which=='codenonASCII':event['row']['action']='événement'
    elif which=='codectrl':event['row']['action']='generic\n'
    elif which=='codeoversize':event['row']['action']='a'*129
    elif which=='extraI':inputs.events['extra']='PRIVATE'
    else:inputs.events['identity_admitted']=True
    inputs.repin();refuse('events',inputs.run)


@pytest.mark.parametrize('field,value',[('request_ordinal',False),('http_status',True),('CSV_validation_complete',True),('role','other'),
    ('schema','other'),('plan_sha256','f'*64),('body_pin',{'byte_count':1,'sha256':'f'*64})])
def test_J_transport_plan_body_status_and_schema_are_bound(inputs,field,value,monkeypatch):
    inputs.transport[field]=value;inputs.transport_raw=m.canonical(inputs.transport)
    monkeypatch.setattr(m,'DATA_PLAN',{**m.DATA_PLAN,'transport':{**m.DATA_PLAN['transport'],**m.pin(inputs.transport_raw)}})
    refuse('transport',inputs.run)


@pytest.mark.parametrize('limit',['field','packet','definition_count'])
def test_generic_text_bounds_refuse_without_truncation(inputs,limit):
    if limit=='field':inputs.rows[0]['description']='x'*16385
    elif limit=='packet':
        for n,event in enumerate(inputs.events['all_original_rows']):event['row']['action']='generic'+str(n%5)
        for row in inputs.rows[:5]:row['description']='x'*16000
    else:
        for row in inputs.rows:row['indicator']='generic0'
    inputs.repin()
    with pytest.raises((m.Refused,dictionary.Refused)):inputs.run()


@pytest.mark.parametrize('field,value',[('requested_code_count',True),('dictionary_row_count',True),('matched_code_count',True),
    ('matched_definition_row_count',True),('generic_documentation_only',1),('identity_admitted',True),('definitions_interpreted',True),('extra',False)])
def test_public_closed_counts_types_and_false_flags(inputs,field,value):
    output=inputs.run();output[field]=value;refuse('output',lambda:m.validate_documentation(output))


@pytest.mark.parametrize('which',['ordinalbool','ordinalduplicate','indicator','missing','repeat','conflict','count','genericrowpin','titleoversize','definitiontype'])
def test_public_definition_provenance_and_count_consistency(inputs,which):
    value=inputs.run();item=value['definitions']['generic0'][0]
    if which=='ordinalbool':item['dictionary_row_ordinal']=False
    elif which=='ordinalduplicate':value['definitions']['generic1'][0]['dictionary_row_ordinal']=0
    elif which=='indicator':item['indicator']='generic1'
    elif which=='missing':value['missing_code_count']=1
    elif which=='repeat':value['repeated_indicator_row_count']=1
    elif which=='conflict':value['conflicting_definition_code_count']=1
    elif which=='count':value['matched_definition_row_count']=4
    elif which=='genericrowpin':item['full_generic_row_pin']['byte_count']=True
    elif which=='titleoversize':item['title']='x'*16385
    else:item['definition']=False
    refuse('output',lambda:m.validate_documentation(value))


class Security:
    @staticmethod
    def snapshot(fd):return {'acl_empty':True,'xattrs':{}}


def fixture_control(tmp_path,monkeypatch):
    root=tmp_path/'root';root.mkdir(mode=0o755);root.chmod(0o755)
    artifacts=root/'artifacts';artifacts.mkdir(mode=0o700);lane=artifacts/'analyst_revisions_v2';lane.mkdir(mode=0o700)
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'CONTROL',lane/'firstrate/R336-K')


class SyntheticGuard:
    @staticmethod
    def validate_receipt(value,plan):
        assert value=={'synthetic_guard':True,'files':plan};return value


@pytest.fixture
def launched(inputs,tmp_path,monkeypatch):
    fixture_control(tmp_path,monkeypatch)
    monkeypatch.setattr(m,'preflight',lambda *a:None)
    monkeypatch.setattr(m,'bootstrap',lambda *a:{'security':Security,'dictionary':dictionary,'guard':SyntheticGuard})
    monkeypatch.setattr(m,'ACTIVE_BINDING',m.binding(args()));monkeypatch.setattr(m,'CLAIM_STATE','unallocated')
    state=NS(inputs=inputs,childexit=0,childfailure='dictionary_header',calls=0,noise=False,stderr=0,timeout=False)
    def child(command,descriptors,deadline):
        state.calls+=1;assert state.calls==1 and command[:2]==['/usr/bin/sandbox-exec','-p']
        assert '(deny network*)' in command[2] and len(descriptors)==3
        assert (m.CONTROL/'claim.json').exists() and (m.CONTROL/'review-intent.json').exists()
        directory,claimfd,intentfd=descriptors;intent=os.pread(intentfd,8193,0)
        assert os.pread(claimfd,131073,0)==m.canonical({'binding':m.binding(args()),'profile':m.profile_record()})
        marker=m.canonical({'binding':m.binding(args()),'phase':'review','intent_pin':m.pin(intent)})
        fd=os.open('review-started.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        try:os.write(fd,marker);os.fsync(fd)
        finally:os.close(fd)
        if state.childexit==0:
            packet={'schema':m.SCHEMA+'-worker','binding':m.binding(args()),'documentation':inputs.run(),
                'guard_receipt':{'synthetic_guard':True,'files':m.DATA_PLAN},'guard_normal_return':True,**m.FALSE_FLAGS}
        else:packet=m.failure_packet(state.childfailure)
        output=m.canonical(packet)+b'\n'+(b'noise' if state.noise else b'')
        return state.childexit,output,state.stderr,m.sha(b'x'*state.stderr),'deadline' if state.timeout else None
    monkeypatch.setattr(m,'run_child',child)
    state.run=lambda:m.parent(args(),time.monotonic()+149)
    return state


def test_claim_marker_guard_return_publication_and_external_exit_gate(launched):
    packet=launched.run();assert packet['accepted'] is True and launched.calls==1
    accepted=m.validate_output(m.canonical(packet)+b'\n',0,args(),SyntheticGuard)
    assert accepted['accepted'] is True and accepted['documentation']['generic_documentation_only'] is True
    assert (m.CONTROL/'report.json').exists() and (m.CONTROL/'worker-observation.json').exists()
    refuse('claim_spent',launched.run)


def test_exact_finite_worker_failure_retained_with_actual_exit2(launched):
    launched.childexit=2;packet=launched.run()
    assert packet['accepted'] is False and packet['worker_packet']['failure_code']=='dictionary_header'
    checked=m.validate_output(m.canonical(packet)+b'\n',2,args(),SyntheticGuard)
    assert checked['accepted'] is False and checked['failure']['failure_code']=='dictionary_header'


@pytest.mark.parametrize('which',['actual2','actualbool','reportpin','workerpin','workerdoc','marker','stderrbool','childbool','falseflag','trail'])
def test_exact_parent_exit_report_worker_packet_and_marker_authentication(launched,which):
    packet=launched.run();actual=0
    if which=='actual2':actual=2
    elif which=='actualbool':actual=True
    elif which=='reportpin':packet['report_pin']['sha256']='f'*64
    elif which=='workerpin':packet['observation']['child_stdout_pin']['sha256']='f'*64
    elif which=='workerdoc':packet['worker_packet']['documentation']['definitions']['generic0'][0]['title']='Different definition title'
    elif which=='marker':packet['observation']['marker_authenticated']=False
    elif which=='stderrbool':packet['observation']['child_stderr_byte_count']=False
    elif which=='childbool':packet['observation']['actual_child_exit']=False
    else:packet['worker_packet']['identity_admitted']=True
    if which not in ('reportpin','actual2','actualbool'):packet['report_pin']=m.pin(m.canonical({k:v for k,v in packet.items() if k!='report_pin'}))
    raw=m.canonical(packet)+b'\n'+(b'noise' if which=='trail' else b'')
    refuse('output',lambda:m.validate_output(raw,actual,args(),SyntheticGuard))


@pytest.mark.parametrize('which',['noise','stderr','timeout'])
def test_ambiguous_child_is_terminal_and_retains_observation(launched,which):
    if which=='noise':launched.noise=True
    elif which=='stderr':launched.stderr=1
    else:launched.timeout=True
    with pytest.raises(m.Refused):launched.run()
    observed=m.CHILD_OBSERVATION
    assert observed['actual_child_exit']==0 and (m.CONTROL/'worker-observation.json').exists()
    if which=='timeout':assert observed['failure_code']=='deadline'


def test_late_marker_adoption_refusal_retains_measured_exit_stdout_and_original_finite_cause(launched,monkeypatch):
    def refuse_marker(*args):raise m.Refused('worker_marker')
    monkeypatch.setattr(m,'adopt_marker',refuse_marker)
    with pytest.raises(m.Refused) as error:launched.run()
    observed=m.CHILD_OBSERVATION
    assert observed is not None and observed['actual_child_exit']==0 and observed['child_stdout_pin']['byte_count']>0
    assert observed['child_stderr_byte_count']==0 and observed['child_stderr_sha256']==m.sha(b'')
    assert observed['marker_authenticated'] is False and observed['failure_code']=='worker_marker'
    # Store's later refusal may become the outer code; the original adoption
    # failure and all already measured child facts remain explicitly retained.
    packet=m.failure_packet(m.finite(error.value))
    checked=m.validate_output(m.canonical(packet)+b'\n',2,args(),SyntheticGuard)
    assert checked['accepted'] is False and checked['failure']['child_observation']==observed
    assert b'PRIVATE-' not in m.canonical(packet)


@pytest.mark.parametrize('kind',['secret_exception','instrument_shape','generic_bound'])
def test_finite_failure_never_discloses_private_instrument_markers(inputs,monkeypatch,kind):
    monkeypatch.setattr(m,'ACTIVE_BINDING',m.binding(args()));monkeypatch.setattr(m,'CHILD_OBSERVATION',None)
    if kind=='secret_exception':error=RuntimeError('PRIVATE-TICKER PRIVATE-NAME PRIVATE-DATE PRIVATE-VALUE case-frequency=33')
    else:
        if kind=='instrument_shape':inputs.events['all_original_rows'][0]['row']['action']='PRIVATE-\n'
        else:inputs.rows[0]['description']='x'*16385
        inputs.repin()
        try:inputs.run()
        except BaseException as error:captured=error
        else:raise AssertionError('fixture must refuse')
        error=captured
    packet=m.failure_packet(m.finite(error));raw=m.canonical(packet)
    assert not any(marker in raw for marker in (b'PRIVATE-',b'case-frequency',b'PRIVATE-TICKER',b'PRIVATE-NAME'))
    assert packet['attempt_reusable'] is False and packet['failure_code'] in m.FINITE


@pytest.mark.parametrize('close_failure',[False,True])
def test_worker_exclusive_marker_before_exact_three_DATA_and_guard_return_before_packet(inputs,tmp_path,monkeypatch,close_failure):
    fixture_control(tmp_path,monkeypatch);events=[]
    class Guard:
        def __init__(self,plan,*,deadline):assert plan==m.DATA_PLAN
        def __enter__(self):assert (m.CONTROL/'review-started.json').exists();events.append('enter');return self
        def read_all_once(self):events.append('read');return {'events':inputs.event_raw,'dictionary':inputs.dictionary_raw,'transport':inputs.transport_raw}
        def verify(self):events.append('verify')
        def receipt(self):return {'synthetic_guard':True,'files':m.DATA_PLAN}
        def __exit__(self,*a):
            events.append('normal_return' if not close_failure else 'close_failure')
            if close_failure:raise m.Refused('changed')
    monkeypatch.setattr(m,'preflight',lambda *a:None)
    monkeypatch.setattr(m,'bootstrap',lambda *a:{'security':Security,'dictionary':dictionary,'guard':NS(FixedDataGuard=Guard)})
    selected=args()
    with m.Store(Security) as store:
        claim=m.canonical({'binding':m.binding(selected),'profile':m.profile_record()});store.write('claim.json',claim)
        intent=m.canonical({'binding':m.binding(selected),'phase':'review','claim_pin':m.pin(claim)});store.write('review-intent.json',intent)
        selected.control_fd=store.fd;selected.claim_fd=m._held_fd(store,'claim.json');selected.intent_fd=m._held_fd(store,'review-intent.json')
        if close_failure:refuse('changed',lambda:m.worker(selected,time.monotonic()+149))
        else:
            packet=m.worker(selected,time.monotonic()+149);assert packet['guard_normal_return'] is True
            assert packet['documentation']['generic_documentation_only'] is True
        assert m.adopt_marker(store,'review')==m.canonical({'binding':m.binding(selected),'phase':'review','intent_pin':m.pin(intent)})
        assert events==['enter','read','verify','close_failure' if close_failure else 'normal_return']
        with pytest.raises(FileExistsError):m.worker(selected,time.monotonic()+149)
        assert events.count('read')==1


@pytest.mark.parametrize('kind',['symlink','unexpected','changed','mode','security'])
def test_control_ancestors_owned_names_and_current_security_are_enforced(tmp_path,monkeypatch,kind):
    fixture_control(tmp_path,monkeypatch)
    if kind=='symlink':
        other=tmp_path/'other';other.mkdir();m.CONTROL.parent.symlink_to(other,target_is_directory=True)
        with pytest.raises((OSError,m.Refused)):m.Store(Security).__enter__()
        assert not (other/'R336-K').exists();return
    class Changing(Security):
        changed=False
        @staticmethod
        def snapshot(fd):return {'current_security':Changing.changed}
    with pytest.raises(m.Refused):
        with m.Store(Changing) as store:
            store.write('claim.json',b'{}')
            if kind=='unexpected':(m.CONTROL/'unknown').write_bytes(b'PRIVATE')
            elif kind=='changed':(m.CONTROL/'claim.json').write_bytes(b'PRIVATE')
            elif kind=='mode':(m.CONTROL/'claim.json').chmod(0o644)
            else:Changing.changed=True
            store.verify()


@pytest.mark.parametrize('mode',['success','failure','stderr','timeout','bound'])
def test_real_child_bounded_capture_own_reap_and_closed_descriptors(tmp_path,monkeypatch,mode):
    actual=subprocess.Popen;children=[]
    monkeypatch.setattr(m,'safe_env',lambda:{'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    def tracked(*args,**kwargs):
        child=actual(*args,**kwargs);children.append(child);return child
    monkeypatch.setattr(m.subprocess,'Popen',tracked)
    code='import os,time\n'
    if mode=='timeout':code+='time.sleep(5)\n'
    if mode=='stderr':code+='os.write(2,b"synthetic stderr")\n'
    if mode=='bound':monkeypatch.setattr(m,'MAX_OUTPUT',32);code+='os.write(1,b"x"*33)\n'
    else:code+='os.write(1,b"finite synthetic output\\n")\n'
    code+='raise SystemExit('+('2' if mode=='failure' else '0')+')'
    result=m.run_child([sys.executable,'-I','-B','-c',code],(),time.monotonic()+(.2 if mode=='timeout' else 10))
    assert children[0].poll() is not None and children[0].stdout.closed and children[0].stderr.closed
    actual_exit,raw,stderr_count,stderr_sha,problem=result
    if mode=='timeout':assert actual_exit<0 and problem=='deadline'
    elif mode=='bound':assert problem=='bound' and raw==b''
    else:
        assert actual_exit==(2 if mode=='failure' else 0) and problem is None
        assert stderr_count==(16 if mode=='stderr' else 0) and stderr_sha==m.sha(b'synthetic stderr' if mode=='stderr' else b'')


def test_selected_source_bootstrap_no_repo_pyc_Keychain_or_used_producer_execution():
    code="""from scripts import inspect_arv2_r336_action_definitions as m
from contextlib import ExitStack
import sys,time
with ExitStack() as stack:
 modules=m.bootstrap('validate',stack,time.monotonic()+149)
 assert set(modules)=={'security','guard','dictionary'}
 assert all(module.__spec__.loader is None for module in modules.values())
 assert all(getattr(module,'__cached__',None) is None for module in modules.values())
 assert not any(name.startswith(('scripts.run_arv2_r335','scripts.inspect_arv2_r335')) for name in sys.modules)
 assert 'scripts.arv2_keychain_connections' not in sys.modules
"""
    result=subprocess.run([sys.executable,'-I','-B','-c','import sys;sys.path.insert(0,'+repr(str(m.ROOT))+');'+code],cwd=m.ROOT,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    assert result.returncode==0 and not result.stdout and not result.stderr


def test_native_policy_and_profile_only_exact_I_J_DATA_and_new_own_controls():
    policy=m.native_profile();profile=m.profile_record()
    for part in ('(deny network*)','/Volumes','/Library/Keychains','/usr/bin/security','[.]pyc$'):assert part in policy
    assert set(m.DATA_PLAN)=={'events','dictionary','transport'}
    for row in m.DATA_PLAN.values():assert row['relative_path'] in policy
    for excluded in ('R335-20261103-J/claim.json','R335-20261103-I/report.json','R335-20261103-G/response-00.csv','identity-demand-private.json'):assert excluded not in policy
    assert profile['definition_count_limit']==33 and profile['generic_packet_bytes_limit']==65536
    for name,expected in m.SOURCE_PINS.items():assert m.sha((m.ROOT/name).read_bytes())==expected
    assert profile['worker_native_policy_sha256']==m.sha(policy.encode())


def test_reused_guard_controls_are_exact_new_copy_not_old_global_patches():
    before=ast.parse((m.ROOT/'scripts/run_arv2_r335_action_types.py').read_bytes());after=ast.parse(m.SOURCE.read_bytes())
    get=lambda tree,name:next(node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name==name)
    for name in ('HeldFile','Store','preflight','binding','meta','_regular_fd','_held_fd'):
        assert ast.dump(get(before,name),include_attributes=False)==ast.dump(get(after,name),include_attributes=False)
    imports=[node.module or '' for node in ast.walk(after) if isinstance(node,ast.ImportFrom)]
    assert all(not name.startswith(('scripts.','research.')) for name in imports)


@pytest.mark.parametrize('mode',['launch','worker','validate'])
def test_operational_modes_have_alarm_and_validator_bootstrap_before_stdin(monkeypatch,mode):
    selected=args();argv=[str(m.SOURCE),mode,'--expected-head',selected.expected_head,'--caller-sha256',selected.caller_sha256,'--profile-sha256',selected.profile_sha256]
    if mode=='worker':argv+=['--outer-deadline',repr(time.monotonic()+89),'--control-fd','3','--claim-fd','4','--intent-fd','5']
    if mode=='validate':argv+=['--actual-parent-exit','2']
    order=[];monkeypatch.setattr(m.sys,'argv',argv);monkeypatch.setattr(m,'ENTRY_DEADLINE',time.monotonic()+149)
    monkeypatch.setattr(m.signal,'signal',lambda *a:None);monkeypatch.setattr(m.signal,'setitimer',lambda *a:order.append(('alarm',a[1])))
    monkeypatch.setattr(m,'preflight',lambda *a:order.append(('preflight',None)))
    monkeypatch.setattr(m,'bootstrap',lambda *a:(order.append(('bootstrap',None)) or {'guard':SyntheticGuard}))
    monkeypatch.setattr(m,'parent',lambda *a:{'mode':'launch'});monkeypatch.setattr(m,'worker',lambda *a:{'mode':'worker'})
    monkeypatch.setattr(m,'validate_output',lambda *a:(order.append(('stdin_validated',None)) or {'mode':'validate'}))
    monkeypatch.setattr(m.sys,'stdin',NS(buffer=io.BytesIO(b'synthetic')))
    assert m.main()=={'mode':mode} and order[0][0]=='alarm' and 0<order[0][1]<=(30 if mode=='validate' else 90 if mode=='worker' else 150)
    if mode=='validate':assert [item[0] for item in order]==['alarm','preflight','bootstrap','stdin_validated']
