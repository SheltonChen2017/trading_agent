"""O synthetic orchestration; actual USB/DATA/network/Keychains are denied."""
import ast
import copy
from contextlib import ExitStack
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS
import zipfile
import pytest
from scripts import inspect_arv2_r336_historical_symbol_coverage as m
from scripts import arv2_r336_historical_symbol_coverage as prices


def args():return NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def refuse(code,call):
    with pytest.raises(m.Refused) as error:call()
    assert m.finite(error.value)==code


class Security:
    @staticmethod
    def snapshot(fd):return {'acl_empty':True,'xattrs':{}}


class Pure:
    Refused=prices.Refused
    finite=staticmethod(prices.finite)
    assess_member=staticmethod(prices.assess_member)
    validate_coverage=staticmethod(prices.validate_coverage)
    private_member_index=staticmethod(prices.private_member_index)
    private_original_bytes=staticmethod(prices.private_original_bytes)
    @staticmethod
    def validate_plan_summary(value):
        m.require(type(value) is dict and value.get('schema')=='synthetic-plan' and len(value.get('cases',()))==5,'output')
        for ordinal,case in enumerate(value['cases']):
            m.require(case['case_ordinal']==ordinal and type(case['required_session_count']) is int
                and type(case['reference_session_count']) is int and type(case['family_symbol_role_matrix']) is list,'output')
        return value


def zip_bytes(members):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as zipped:
        for name,raw in members.items():zipped.writestr(name,raw)
    return stream.getvalue()


def marker(phase='historical_symbols'):return m.canonical({'binding':m.binding(args()),'phase':phase})


@pytest.fixture
def scenario(tmp_path,monkeypatch):
    root=tmp_path/'root';root.mkdir(mode=0o755);root.chmod(0o755)
    artifacts=root/'artifacts';artifacts.mkdir(mode=0o700);lane=artifacts/'analyst_revisions_v2';lane.mkdir(mode=0o700)
    usb=tmp_path/'synthetic-usb';(usb/m.STOCK_DIR).mkdir(parents=True)
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'CONTROL',lane/'firstrate/R336-O');monkeypatch.setattr(m,'USB',usb)
    monkeypatch.setattr(m,'CLAIM_STATE','unallocated');monkeypatch.setattr(m,'CHILD_OBSERVATION',None);monkeypatch.setattr(m,'PURE_MODULE',Pure)
    excluded=[name for n in range(5) for name in (f'CUR{n}',f'CUR{n}-DELISTED')]
    raw0=b'2024-01-02,10,12,9,11,1.5\r\n2024-01-03,11,13,10,12,2\n'
    raw1=b'2024-01-03,11,13,10,12,3\n'
    old_raw=b'PRIVATE-OLD-E-MEMBER-NEVER-DECOMPRESS'
    known_archive=m.DELISTED_ARCHIVES[0]
    payloads={m.STOCK_DIR+'Tickers_O_Day_Unadjusted_Full_Dataset.zip':{'OLD_full_1day_UNADJUSTED.txt':raw0},
        known_archive:{'OLD-DELISTED_full_1day_UNADJUSTED.txt':raw1,'CUR0_full_1day_UNADJUSTED.txt':old_raw}}
    archives={relative:zip_bytes(payloads.get(relative,{'UNSELECTED_full_1day_UNADJUSTED.txt':b'PRIVATE-UNSELECTED'}))
        for relative in (m.STOCK_DIR+'Tickers_O_Day_Unadjusted_Full_Dataset.zip',*m.DELISTED_ARCHIVES)}
    manifest={relative[:-4]:{'path':'PRIVATE-PATH','bytes':len(raw),'md5':hashlib.md5(raw).hexdigest(),'ok':True,'fetched':True,
        'url':'https://PRIVATE-CREDENTIAL-URL'} for relative,raw in archives.items()}
    for relative,raw in archives.items():(usb/relative).write_bytes(raw)
    manifest_raw=m.canonical(manifest);(usb/'manifest.json').write_bytes(manifest_raw)
    listing_raw=b'Ticker,Name,First Date,Last Date\nOLD,PRIVATE-LISTING-NAME,2024-01-02,2024-01-03\nOLD-DELISTED,PRIVATE-NAME,2024-01-03,2024-01-03\n'
    (usb/m.STOCK_DIR/'Ticker_Listing.txt').write_bytes(listing_raw)
    monkeypatch.setattr(m,'USB_PINS',{'manifest.json':m.pin(manifest_raw),m.STOCK_DIR+'Ticker_Listing.txt':m.pin(listing_raw)})
    cases=[];leads=[]
    for ordinal in range(5):
        cases.append({'case_ordinal':ordinal,'whole_binding_sha256':str(ordinal)*64,'required_sessions':['2024-01-02','2024-01-03'],
            'reference_sessions':['2024-01-02'],'original_ticker':f'CUR{ordinal}','previously_E_searched_symbols':excluded,
            'prior_E_candidates':([{'archive':known_archive,'container_pin':m.pin(archives[known_archive]),
                'member_name':'CUR0_full_1day_UNADJUSTED.txt','member_pin':m.pin(old_raw)}] if ordinal==0 else []),'lead_ordinals':[]})
    for ordinal,role in ((0,'prior_unit_counterparty'),(1,'prior_unit_counterparty')):
        index=len(leads);cases[ordinal]['lead_ordinals'].append(index)
        leads.append({'lead_ordinal':index,'case_ordinal':ordinal,'family':'spac_unit_separation','symbol_role':role,
            'origin':'N.synthetic','source_row_ordinals':[0],'pair_ordinal':None,'raw_symbol':'OLD','supported':True,
            'excluded_E':False,'unresolved_pair':False,'eligible':True,'window_relation':'inside_required_window'})
    plan={'schema':'synthetic-private-plan','input_N_pin':{},'N_policy_sha256':'a'*64,'cases':cases,'lead_records':leads,
        'transport_tokens':['OLD'],'transport_specs':[{'token':'OLD','current_letter':'O','member_aliases':['OLD','OLD-DELISTED'],
            'lead_links':[{'case_ordinal':lead['case_ordinal'],'lead_ordinal':lead['lead_ordinal']} for lead in leads]}],
        'unresolved_pair_evidence':[]}
    public={'schema':'synthetic-plan','cases':[{'case_ordinal':ordinal,'required_session_count':2,'reference_session_count':1,
        'family_symbol_role_matrix':([{'family':'spac_unit_separation','symbol_role':'prior_unit_counterparty','eligible_count':1}]
            if ordinal<2 else [])} for ordinal in range(5)]}
    state=NS(root=root,usb=usb,plan=plan,public=public,manifest=manifest,listing=m.listings(listing_raw),raw0=raw0,raw1=raw1,
        archives=archives,known_archive=known_archive,order=[],member_reads=[],source_fail=False,USB_fail=False,DATA_fail=False,late_file_fail=False)
    state.run_study=lambda:m.study(state.public,state.plan,state.manifest,state.listing,Pure,time.monotonic()+299)
    return state


def test_study_preserves_two_physical_members_all_case_role_links_and_no_union(scenario,monkeypatch):
    original=m.Archive.member
    def read(archive,name):scenario.member_reads.append((archive.held.path.name,name));return original(archive,name)
    monkeypatch.setattr(m.Archive,'member',read)
    summary,private,raw=scenario.run_study()
    assert raw==[scenario.raw1,scenario.raw0] or raw==[scenario.raw0,scenario.raw1]
    assert summary['physical_member_count']==2 and summary['raw_member_bytes']==len(scenario.raw0)+len(scenario.raw1)
    assert summary['known_E_container_SHA_count']==1 and summary['new_retained_SHA_without_E_pin_count']==6
    assert [case['candidate_count'] for case in summary['cases']]==[2,2,0,0,0]
    assert sorted(row['coverage']['missing_required_count'] for row in summary['cases'][0]['candidates'])==[0,1]
    assert len(scenario.member_reads)==len(set(scenario.member_reads))==14
    assert all('CUR' not in name and 'UNSELECTED' not in name for _,name in scenario.member_reads)
    assert all(len(member['case_assessments'])==2 for member in private['physical_members'])
    assert not any(text in m.canonical(summary) for text in (b'PRIVATE-',b'OLD',b'CUR',b'https://'))
    m.validate_summary(summary,Pure)


def test_known_container_SHA_is_checked_before_any_ZIP_parsing(scenario,monkeypatch):
    path=scenario.usb/scenario.known_archive;called=[]
    def forbidden(*a,**k):called.append(True);raise AssertionError('known SHA mismatch must precede ZIP parse')
    monkeypatch.setattr(m.zipfile,'ZipFile',forbidden)
    expected=m.manifest_entry(scenario.manifest,scenario.known_archive)
    with m.HeldFile(path,maximum=m.MAX_ZIP_BYTES,deadline=time.monotonic()+299) as held:
        with pytest.raises(m.Refused) as error:m.Archive(held,expected,known_pin={'byte_count':path.stat().st_size,'sha256':'f'*64}).__enter__()
    assert m.finite(error.value)=='known_pin' and not called


def test_conflicting_known_container_or_member_pins_refuse_without_refresh(scenario):
    previous=scenario.plan['cases'][0]['prior_E_candidates'][0]
    scenario.plan['cases'][1]['prior_E_candidates']=[{**previous,'container_pin':{'byte_count':1,'sha256':'f'*64}}]
    refuse('known_pin',lambda:m.known_sources(scenario.plan))


def test_known_member_SHA_is_compared_before_member_price_parsing(scenario,monkeypatch):
    previous=scenario.plan['cases'][0]['prior_E_candidates'][0]
    previous['member_name']='OLD-DELISTED_full_1day_UNADJUSTED.txt';previous['member_pin']={'byte_count':len(scenario.raw1),'sha256':'f'*64}
    called=[]
    def forbidden(*a,**k):called.append(True);raise AssertionError('known member pin before parse')
    monkeypatch.setattr(Pure,'assess_member',forbidden)
    refuse('known_pin',scenario.run_study);assert not called


def test_E_exclusion_is_global_across_all_five_cases(scenario):
    plan=scenario.plan;plan['transport_tokens']=['CUR4'];plan['lead_records'][0]['raw_symbol']='CUR4'
    plan['transport_specs']=[{'token':'CUR4','current_letter':'C','member_aliases':['CUR4','CUR4-DELISTED'],
        'lead_links':[{'case_ordinal':0,'lead_ordinal':0}]}]
    _,_,excluded=m.known_sources(plan)
    refuse('plan',lambda:m.schedule(plan,excluded))


def test_digit_first_and_existing_delisted_suffix_use_only_exact_supported_paths(scenario):
    plan=scenario.plan;plan['transport_tokens']=['1OLD-DELISTED'];plan['lead_records'][0]['raw_symbol']='1OLD-DELISTED'
    plan['transport_specs']=[{'token':'1OLD-DELISTED','current_letter':None,'member_aliases':['1OLD-DELISTED'],
        'lead_links':[{'case_ordinal':0,'lead_ordinal':0}]}]
    _,_,excluded=m.known_sources(plan);jobs=m.schedule(plan,excluded)
    assert set(jobs)==set(m.DELISTED_ARCHIVES)
    assert all(set(names)=={'1OLD-DELISTED_full_1day_UNADJUSTED.txt'} for names in jobs.values())


def test_shared_alias_queries_are_deduplicated_without_discarding_lead_links(scenario):
    plan=scenario.plan;plan['transport_tokens']=['OLD','OLD-DELISTED']
    lead=copy.deepcopy(plan['lead_records'][0]);lead.update(lead_ordinal=2,raw_symbol='OLD-DELISTED');plan['lead_records'].append(lead)
    plan['transport_specs'].append({'token':'OLD-DELISTED','current_letter':'O','member_aliases':['OLD-DELISTED'],
        'lead_links':[{'case_ordinal':0,'lead_ordinal':2}]})
    _,_,excluded=m.known_sources(plan);jobs=m.schedule(plan,excluded)
    target=jobs[m.DELISTED_ARCHIVES[0]]['OLD-DELISTED_full_1day_UNADJUSTED.txt']
    assert target['tokens']==['OLD','OLD-DELISTED'] and len(target['lead_links'])==3


@pytest.mark.parametrize('which',['rawbytes','membercount'])
def test_whole_observation_refuses_at_cumulative_or_file_bound_without_truncation(scenario,monkeypatch,which):
    if which=='rawbytes':monkeypatch.setattr(m,'MAX_RAW_BYTES',len(scenario.raw0)+len(scenario.raw1)-1)
    else:monkeypatch.setattr(m,'MAX_RAW_FILES',1)
    refuse('bound',scenario.run_study)


@pytest.mark.parametrize('which',['differentrows','differentlexical','differentvolume','differentpin','noneligiblecase','orphan','rawbytes','boolcount','flag'])
def test_summary_shared_physical_metadata_case_eligibility_and_closed_counts(scenario,which):
    summary,_,_=scenario.run_study();row=summary['cases'][1]['candidates'][0]
    if which=='differentrows':row['coverage']['row_count']+=1;row['coverage']['integer_volume_row_count']+=1;row['coverage']['line_ending_evidence']['physical_record_count']+=1
    elif which=='differentlexical':row['coverage']['line_ending_evidence']['LF_count']+=1
    elif which=='differentvolume':
        row['coverage']['integer_volume_row_count'],row['coverage']['fractional_volume_row_count']=row['coverage']['fractional_volume_row_count'],row['coverage']['integer_volume_row_count']
    elif which=='differentpin':row['coverage']['member_pin']['sha256']='f'*64
    elif which=='noneligiblecase':summary['cases'][2]['candidates']=[copy.deepcopy(row)];summary['cases'][2]['candidate_count']=1
    elif which=='orphan':
        for case in summary['cases']:case['candidates']=[item for item in case['candidates'] if item['physical_hit_ordinal']!=0];case['candidate_count']=len(case['candidates'])
    elif which=='rawbytes':summary['raw_member_bytes']+=1
    elif which=='boolcount':summary['physical_member_count']=True
    else:summary['price_input_admitted']=True
    with pytest.raises((m.Refused,prices.Refused)):m.validate_summary(summary,Pure)


@pytest.fixture
def worker_setup(scenario,monkeypatch):
    state=scenario;raw=m.canonical({'private':'PRIVATE-N-SEMANTICS'})
    monkeypatch.setattr(m,'DATA_PLAN',{'semantics':{'relative_path':'artifacts/analyst_revisions_v2/synthetic/N.json',**m.pin(raw)}})
    class Sources:
        def __enter__(self):return self
        def __exit__(self,*a):
            state.order.append('source_return')
            if state.source_fail:raise m.Refused('source_changed')
    class Data:
        def __init__(self,plan,*,deadline):assert plan==m.DATA_PLAN
        def __enter__(self):
            assert (m.CONTROL/'claim.json').exists() and (m.CONTROL/'worker-started.json').exists();state.order.append('N_enter');return self
        def read_all_once(self):state.order.append('N_read');return {'semantics':raw}
        def verify(self):state.order.append('N_verify')
        def receipt(self):return {'synthetic':True}
        def __exit__(self,*a):
            state.order.append('N_return')
            if state.DATA_fail:raise m.Refused('changed')
    class Analysis(Pure):
        @staticmethod
        def plan(value,*,deadline):assert value=={'private':'PRIVATE-N-SEMANTICS'};return state.public,state.plan
    def bootstrap(role,stack,deadline):stack.enter_context(Sources());return {'security':Security,'guard':NS(FixedDataGuard=Data),'pure':Analysis}
    monkeypatch.setattr(m,'bootstrap',bootstrap);monkeypatch.setattr(m,'preflight',lambda *a:None)
    original_exit=m.HeldFile.__exit__
    def held_exit(held,kind,*rest):
        value=original_exit(held,kind,*rest)
        if held.path==m.USB/'manifest.json':
            state.order.append('USB_return')
            if state.USB_fail:raise m.Refused('changed')
        return value
    monkeypatch.setattr(m.HeldFile,'__exit__',held_exit)
    original_write=m.Store.write
    def write(store,name,payload):
        if m.raw_name(name) or name in ('private-diagnosis.json','report.json'):
            assert all(item in state.order for item in ('USB_return','N_return','source_return'))
        state.order.append('write_'+name)
        if state.late_file_fail and name=='member-0001.bin':raise m.Refused('output')
        return original_write(store,name,payload)
    monkeypatch.setattr(m.Store,'write',write)
    def run():
        selected=args();reader,writer=os.pipe()
        try:os.write(writer,m.canonical(m.binding(selected)))
        finally:os.close(writer)
        selected.intent_fd=reader;return m.worker(selected,time.monotonic()+299)
    state.run=run;return state


def test_all_normal_source_returns_before_multiple_raw_files_index_and_report(worker_setup):
    value=worker_setup.run();result=value['result']
    assert result['complete'] is result['USB_read_performed'] is True and len(result['raw_outputs'])==2
    assert [row['leaf'] for row in result['raw_outputs']]==['member-0000.bin','member-0001.bin']
    assert sum((m.CONTROL/row['leaf']).stat().st_size for row in result['raw_outputs'])==result['summary']['raw_member_bytes']
    assert b'PRIVATE-' not in m.canonical(value) and b'OLD' not in m.canonical(value)
    for row in result['raw_outputs']:assert m.pin((m.CONTROL/row['leaf']).read_bytes())=={key:row[key] for key in ('byte_count','sha256')}
    m.validate_envelope(m.canonical(value)+b'\n',0,args());refuse('claim_spent',worker_setup.run)


@pytest.mark.parametrize('which',['USB','DATA','source'])
def test_guard_exit_refusal_after_successful_study_publishes_only_claim_and_marker(worker_setup,which):
    setattr(worker_setup,{'USB':'USB_fail','DATA':'DATA_fail','source':'source_fail'}[which],True)
    with pytest.raises(m.Refused):worker_setup.run()
    assert set(path.name for path in m.CONTROL.iterdir())=={'claim.json','worker-started.json'}


def test_late_raw_file_failure_spends_claim_preserves_complete_earlier_files(worker_setup,monkeypatch):
    worker_setup.late_file_fail=True;monkeypatch.setattr(m,'ACTIVE_BINDING',m.binding(args()))
    with pytest.raises(m.Refused) as error:worker_setup.run()
    assert m.CLAIM_STATE=='consumed' and (m.CONTROL/'member-0000.bin').exists()
    assert not (m.CONTROL/'member-0001.bin').exists() and not (m.CONTROL/'report.json').exists()
    failure=m.failure_packet(m.finite(error.value));assert b'PRIVATE-' not in m.canonical(failure)


@pytest.mark.parametrize('which',['parent2','parentbool','stdoutpin','privatepin','rawpin','reportpin','marker','flag','trailing'])
def test_external_parent_exit_worker_stdout_dynamic_file_pins_and_report_authentication(worker_setup,which):
    outcome=worker_setup.run();raw=m.canonical(outcome)+b'\n'
    packet={'binding':m.binding(args()),'observation':{'actual_child_exit':0,'child_stdout_pin':m.pin(raw),
        'child_stderr_byte_count':0,'child_stderr_sha256':m.sha(b''),'failure_code':None},'output_authenticated':True,'outcome':outcome}
    actual=0
    if which=='parent2':actual=2
    elif which=='parentbool':actual=True
    elif which=='stdoutpin':packet['observation']['child_stdout_pin']['sha256']='f'*64
    elif which=='privatepin':outcome['result']['private_pin']['sha256']='f'*64
    elif which=='rawpin':outcome['result']['raw_outputs'][0]['sha256']='f'*64
    elif which=='reportpin':outcome['report_pin']['sha256']='f'*64
    elif which=='marker':outcome['result']['worker_marker_pin']['sha256']='f'*64
    elif which=='flag':outcome['result']['price_input_admitted']=True
    if which in ('privatepin','rawpin','marker','flag'):outcome['report_pin']=m.pin(m.canonical({'binding':m.binding(args()),'result':outcome['result']}))
    frame=m.canonical(packet)+b'\n'+(b'noise' if which=='trailing' else b'')
    refuse('output',lambda:m.validate_parent_output(frame,actual,args()))


def test_zero_new_member_observation_has_exactly_zero_binary_outputs(worker_setup):
    worker_setup.plan['transport_tokens']=[];worker_setup.plan['transport_specs']=[]
    for lead in worker_setup.plan['lead_records']:lead['eligible']=False
    for case in worker_setup.public['cases']:
        for row in case['family_symbol_role_matrix']:row['eligible_count']=0
    result=worker_setup.run()['result']
    assert result['raw_outputs']==[] and result['summary']['physical_member_count']==result['summary']['raw_member_bytes']==0
    assert not list(m.CONTROL.glob('member-*.bin'))


def test_Store_enforces_per_file_cumulative_names_and_held_original_FDs(scenario,monkeypatch):
    monkeypatch.setattr(m,'MAX_MEMBER_BYTES',5);monkeypatch.setattr(m,'MAX_RAW_BYTES',8)
    with m.Store(Security) as store:
        store.write('claim.json',b'{}');store.write('member-0000.bin',b'first')
        refuse('bound',lambda:store.write('member-0001.bin',b'next'))
        assert not (m.CONTROL/'member-0001.bin').exists()
        refuse('output',lambda:store.write('member-0001.bin',b'123456'))
        refuse('bound',lambda:store.write('member-0002.bin',b'x'))
        refuse('output',lambda:store.write('../member-0001.bin',b'x'))
        refuse('output',lambda:store.write('member-0128.bin',b'x'))
        assert os.pread(store.held[-1][1],6,0)==b'first'
    assert (m.CONTROL/'member-0000.bin').read_bytes()==b'first'


def test_late_output_byte_mutation_is_refused_and_original_evidence_not_repaired(scenario):
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json',b'{}');store.write('member-0000.bin',b'original')
            (m.CONTROL/'member-0000.bin').write_bytes(b'changed');store.verify()
    assert (m.CONTROL/'member-0000.bin').read_bytes()==b'changed'


@pytest.mark.parametrize('change',['profile','head','source','platform','isolated','dirty'])
def test_preflight_exact_clean_host_HEAD_self_source_and_profile(tmp_path,monkeypatch,change):
    source=tmp_path/'scripts/caller.py';source.parent.mkdir();source.write_bytes(b'synthetic public source')
    monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'SOURCE',source);monkeypatch.setattr(m,'__file__',str(source))
    selected=args();selected.caller_sha256=m.sha(source.read_bytes());selected.profile_sha256=m.sha(m.canonical(m.profile_record()))
    monkeypatch.setattr(m,'sys',NS(platform='darwin',version_info=(3,13),executable=m.PYTHON,flags=NS(isolated=1),dont_write_bytecode=True))
    monkeypatch.setattr(m.Path,'cwd',classmethod(lambda cls:tmp_path));monkeypatch.setattr(m,'safe_env',lambda:{})
    def run(command,**kwargs):
        if command[1]=='cat-file':out=source.read_bytes() if change!='source' else b'changed'
        elif command[1]=='status':out=b'untracked' if change=='dirty' else b''
        elif command[1]=='branch':out=m.BRANCH.encode()
        elif command[-1]=='HEAD':out=('d'*40 if change=='head' else selected.expected_head).encode()
        else:out=str(tmp_path).encode()
        return NS(returncode=0,stderr=b'',stdout=out)
    monkeypatch.setattr(m.subprocess,'run',run)
    if change=='profile':selected.profile_sha256='d'*64
    if change=='platform':m.sys.platform='other'
    if change=='isolated':m.sys.flags.isolated=0
    refuse('host' if change in ('platform','isolated') else 'git_state' if change in ('head','dirty') else 'source_pin',
        lambda:m.preflight(selected,time.monotonic()+299))


@pytest.mark.parametrize('mode',['launch','worker','validate'])
def test_parent_worker_and_reader_actual_alarms_before_preflight(monkeypatch,mode):
    selected=args();argv=[str(m.SOURCE),mode,'--expected-head',selected.expected_head,'--caller-sha256',selected.caller_sha256,'--profile-sha256',selected.profile_sha256]
    if mode=='worker':argv+=['--intent-fd','3','--outer-deadline',repr(time.monotonic()+239)]
    if mode=='validate':argv+=['--actual-parent-exit','2']
    order=[];monkeypatch.setattr(m.sys,'argv',argv);monkeypatch.setattr(m,'ENTRY_DEADLINE',time.monotonic()+299)
    monkeypatch.setattr(m.signal,'signal',lambda *a:None);monkeypatch.setattr(m.signal,'setitimer',lambda *a:order.append(('alarm',a[1])))
    monkeypatch.setattr(m,'parent',lambda *a:{'mode':'launch'});monkeypatch.setattr(m,'worker',lambda *a:{'mode':'worker'})
    monkeypatch.setattr(m,'preflight',lambda *a:order.append(('preflight',None)))
    monkeypatch.setattr(m,'bootstrap',lambda *a:(order.append(('bootstrap',None)) or {}))
    monkeypatch.setattr(m.sys,'stdin',NS(buffer=io.BytesIO(b'synthetic')))
    monkeypatch.setattr(m,'validate_parent_output',lambda *a:{'mode':'validate'})
    assert m.main()=={'mode':mode} and order[0][0]=='alarm' and 0<order[0][1]<=(30 if mode=='validate' else 240 if mode=='worker' else 300)
    if mode=='validate':assert [item[0] for item in order]==['alarm','preflight','bootstrap']


@pytest.mark.parametrize('role',['worker','validate'])
def test_fresh_pinned_source_bootstrap_no_repo_pyc_or_used_operator_import(role):
    code="""from scripts import inspect_arv2_r336_historical_symbol_coverage as m
from contextlib import ExitStack
import sys,time
with ExitStack() as stack:
 modules=m.bootstrap(ROLE,stack,time.monotonic()+299)
 assert set(modules)==({'security','pure','guard'} if ROLE=='worker' else {'security','pure'})
 assert modules['pure'].FINITE==m.PURE_CODES and m.pin(m.canonical(modules['pure'].profile_record()))==m.PURE_PROFILE_PIN
 for name in ('arv2_relocation_security','arv2_r336_original_identity_ownership','arv2_r336_action_semantics','arv2_r336_historical_symbol_coverage'):
  module=sys.modules['scripts.'+name];assert module.__spec__.loader is None and getattr(module,'__cached__',None) is None
 assert not any(name.startswith(('scripts.inspect_arv2_r335','scripts.inspect_arv2_r336_action_semantics','scripts.run_arv2')) for name in sys.modules)
 assert 'scripts.arv2_keychain_connections' not in sys.modules
""".replace('ROLE',repr(role))
    child=subprocess.run([sys.executable,'-I','-B','-c','import sys;sys.path.insert(0,'+repr(str(m.ROOT))+');'+code],cwd=m.ROOT,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    assert child.returncode==0 and not child.stdout and not child.stderr


def test_pins_native_scope_RO_USB_and_finite_output_qualification():
    policy=m.native_profile();profile=m.profile_record()
    for name,expected in m.SOURCE_PINS.items():assert m.sha((m.ROOT/name).read_bytes())==expected
    assert len(m.ARCHIVES)==32 and set(m.DATA_PLAN)=={'semantics'}
    assert '(deny network*)' in policy and '(deny file-write* (subpath "/Volumes"))' in policy
    assert all(str(m.USB/relative) in policy for relative in (*m.USB_PINS,*m.ARCHIVES))
    for text in ('/Library/Keychains','/usr/bin/security','[.]pyc$'):assert text in policy
    assert 'private-diagnosis.json' in str(m.DATA_PLAN['semantics']) and 'R335-20261103-I/' not in policy
    assert 'whole_archive_hashing_reads_compressed_bytes' in profile['compressed_container_scope']
    assert 'USB_read' not in m.FALSE_FLAGS and profile['maximum_raw_aggregate_bytes']==32*1024*1024
    assert profile['native_worker_policy_sha256']==m.sha(policy.encode())


def test_CLI_invalid_argument_keeps_raw_text_and_traceback_out_of_output():
    child=subprocess.run([sys.executable,'-I','-B',str(m.SOURCE),'launch','--PRIVATE-TOKEN'],cwd=m.ROOT,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    assert child.returncode==2 and not child.stderr and b'PRIVATE-' not in child.stdout
    assert m.parse(child.stdout,10000)['failure_code']=='arguments'


@pytest.mark.parametrize('mode',['success','failure','stderr','timeout','bound'])
def test_real_small_child_bounded_capture_inherited_denial_and_own_kill_reap(monkeypatch,mode):
    actual=subprocess.Popen;children=[]
    monkeypatch.setattr(m,'safe_env',lambda:{'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    def tracked(*a,**k):child=actual(*a,**k);children.append(child);return child
    monkeypatch.setattr(m.subprocess,'Popen',tracked)
    code='import os,time\n'
    if mode=='timeout':code+='time.sleep(5)\n'
    if mode=='stderr':code+='os.write(2,b"synthetic error")\n'
    if mode=='bound':monkeypatch.setattr(m,'MAX_OUTPUT',32);code+='os.write(1,b"x"*33)\n'
    else:code+='os.write(1,b"finite synthetic output\\n")\n'
    code+='raise SystemExit('+('2' if mode=='failure' else '0')+')'
    result=m.run_child([sys.executable,'-I','-B','-c',code],(),time.monotonic()+(.2 if mode=='timeout' else 10))
    exitcode,raw,count,digest,problem=result
    assert children[0].poll() is not None and children[0].stdout.closed and children[0].stderr.closed
    if mode=='timeout':assert exitcode<0 and problem=='deadline'
    elif mode=='bound':assert problem=='bound' and raw==b''
    else:assert exitcode==(2 if mode=='failure' else 0) and problem is None and count==(15 if mode=='stderr' else 0)


@pytest.mark.parametrize('problem',['deadline','child_stderr','bound'])
def test_parent_late_ambiguity_retains_measured_child_evidence(tmp_path,monkeypatch,problem):
    monkeypatch.setattr(m,'preflight',lambda *a:None);monkeypatch.setattr(m,'ACTIVE_BINDING',m.binding(args()))
    monkeypatch.setattr(m,'ENTRY_DEADLINE',time.monotonic()+149)
    state=NS(calls=0)
    def capture(command,descriptors,deadline):
        state.calls+=1;assert len(descriptors)==1 and command[:2]==['/usr/bin/sandbox-exec','-p']
        assert os.read(descriptors[0],4097)==m.canonical(m.binding(args()))
        return -9,b'finite partial stdout',0,m.sha(b''),problem
    monkeypatch.setattr(m,'run_child',capture)
    with pytest.raises(m.Refused) as error:m._parent_bound(args())
    assert state.calls==1 and m.CHILD_OBSERVATION['actual_child_exit']==-9
    assert m.CHILD_OBSERVATION['child_stdout_pin']==m.pin(b'finite partial stdout')
    assert m.CHILD_OBSERVATION['failure_code']==problem
    packet=m.failure_packet(m.finite(error.value))
    assert m.validate_parent_output(m.canonical(packet)+b'\n',2,args())['accepted'] is False
