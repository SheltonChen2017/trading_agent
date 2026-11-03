"""Synthetic gap/metadata protocol tests; real DATA/USB/artifacts denied."""
import ast
import copy
from contextlib import ExitStack
from datetime import date,timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace as NS
import pytest
from scripts import inspect_arv2_r335_firstrate_gap_metadata as m
from scripts import arv2_r327_available_history_period as period
from research.analyst_revisions_v2_qc import accepted_risk_october_order_package as october


def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64, profile_sha256='c' * 64)


def refuse(code, call):
    with pytest.raises(m.Refused) as caught:
        call()
    assert m.finite(caught.value) == code


def test_changed_bootstrap_source_refuses_before_any_repository_import(tmp_path, monkeypatch):
    root = tmp_path / 'root'; (root / 'scripts').mkdir(parents=True)
    (root / 'scripts' / 'synthetic.py').write_bytes(b'pass\n')
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'SOURCE_PINS', {'scripts/synthetic.py': 'f' * 64})
    monkeypatch.setattr(m, 'ORIGINAL_SERIALIZATION_REFERENCE', {'relative_path':'scripts/synthetic.py',**m.pin(b'pass\n')})
    monkeypatch.setattr(m.importlib, 'import_module', lambda *args: pytest.fail('executed before pin equality'))
    with ExitStack() as stack:
        refuse('source_pin', lambda: m.load_modules(stack, time.monotonic() + 299))


@pytest.mark.parametrize('field,value', [('expected_head', 'a' * 39), ('expected_head', True),
    ('caller_sha256', 'x' * 64), ('profile_sha256', None), ('caller_sha256', 'b' * 65)])
def test_arguments_refuse_malformed_bindings(field, value):
    value_args = args(); setattr(value_args, field, value)
    refuse('arguments', lambda: m.binding(value_args))


def test_binding_accepts_exact_source_run_pins_only():
    assert m.binding(args()) == {'schema': m.SCHEMA, 'expected_head': 'a' * 40,
        'caller_sha256': 'b' * 64, 'profile_sha256': 'c' * 64}


@pytest.mark.parametrize('raw', [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'not-json', b''])
def test_json_refuses_duplicates_constants_and_malformed(raw):
    with pytest.raises(m.Refused): m.parse(raw, 100)


def listing_raw():
    return b'Ticker,Name,First Date,Last Date\nSYN0,Synthetic,2020-01-02,2026-10-16\n'


def test_listing_schema_is_fixed_and_keeps_duplicate_symbol_candidates():
    raw = listing_raw() + b'SYN0,Other Synthetic,2000-01-03,2006-06-30\n'
    rows = m.listings(raw)
    assert len(rows) == 2 and rows[0]['Ticker'] == rows[1]['Ticker']
    assert m.listings(b'\xef\xbb\xbf' + raw) == rows
    refuse('listing', lambda: m.listings(raw.replace(b'First Date', b'Other Date')))


def test_original_held_named_file_rejects_byte_pin_symlink_and_late_replacement(tmp_path):
    source = tmp_path / 'source'; source.write_bytes(b'synthetic')
    deadline = time.monotonic() + 299
    with m.HeldFile(source, maximum=100, expected=m.pin(b'synthetic'), deadline=deadline) as held:
        assert held.read() == b'synthetic'
    with pytest.raises(m.Refused):
        with m.HeldFile(source, maximum=100, expected=m.pin(b'other'), deadline=deadline) as held: held.read()
    link = tmp_path / 'link'; link.symlink_to(source)
    with pytest.raises(OSError):
        with m.HeldFile(link, maximum=100, deadline=deadline): pass
    with pytest.raises(m.Refused):
        with m.HeldFile(source, maximum=100, deadline=deadline) as held:
            source.write_bytes(b'changed!'); held.verify()


class Security:
    @staticmethod
    def snapshot(fd): return {'acl_empty': True, 'xattrs': {}}


def fixture_control(tmp_path, monkeypatch):
    root = tmp_path / 'root'; root.mkdir(mode=0o755); root.chmod(0o755)
    artifacts = root / 'artifacts'; artifacts.mkdir(mode=0o700)
    lane = artifacts / 'analyst_revisions_v2'; lane.mkdir(mode=0o700)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'CONTROL', lane / 'firstrate/R335-A')
    return lane


def test_one_exclusive_claim_all_outputs_original_FDs_and_no_retry(tmp_path, monkeypatch):
    fixture_control(tmp_path, monkeypatch)
    with m.Store(Security) as store:
        store.write('claim.json', b'{"synthetic":true}')
        assert store.write('report.json', b'{}') == m.pin(b'{}')
        store.verify()
        assert all(stat_mode == 0o600 for stat_mode in [
            (m.CONTROL / name).stat().st_mode & 0o777 for name in ('claim.json', 'report.json')])
    refuse('claim_spent', lambda: m.Store(Security).__enter__())
    assert (m.CONTROL / 'claim.json').read_bytes() == b'{"synthetic":true}'


def test_symlink_output_ancestor_refuses_before_any_own_claim(tmp_path, monkeypatch):
    lane = fixture_control(tmp_path, monkeypatch)
    other = tmp_path / 'other'; other.mkdir()
    (lane / 'firstrate').symlink_to(other, target_is_directory=True)
    with pytest.raises((OSError, m.Refused)): m.Store(Security).__enter__()
    assert not (other / 'R335-A').exists()


def test_late_output_mutation_is_refused_and_evidence_retained(tmp_path, monkeypatch):
    fixture_control(tmp_path, monkeypatch)
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json', b'{}')
            (m.CONTROL / 'claim.json').write_bytes(b'changed')
            store.verify()
    assert (m.CONTROL / 'claim.json').read_bytes() == b'changed'


def test_unexpected_owned_control_leaf_is_not_absorbed_by_later_own_write(tmp_path, monkeypatch):
    fixture_control(tmp_path, monkeypatch)
    with pytest.raises(m.Refused):
        with m.Store(Security) as store:
            store.write('claim.json', b'{}')
            (m.CONTROL / 'unexpected').write_bytes(b'synthetic')
            refuse('control', lambda: store.write('report.json', b'{}'))
    assert (m.CONTROL / 'unexpected').read_bytes() == b'synthetic'
    assert not (m.CONTROL / 'report.json').exists()


def test_cli_unknown_argument_never_echoes_supplied_value():
    result = subprocess.run([sys.executable, '-I', '-B', str(m.SOURCE), 'launch', '--SYNTHETIC-SECRET-ARG'],
        cwd=m.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
        env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
    assert result.returncode == 2 and not result.stderr
    assert b'SYNTHETIC-SECRET' not in result.stdout
    assert json.loads(result.stdout)['failure_code'] == 'arguments'


def test_dynamic_output_security_mismatch_is_not_ignored(tmp_path,monkeypatch):
    fixture_control(tmp_path,monkeypatch)
    class Changing(Security):
        changed=False
        @staticmethod
        def snapshot(fd):return {'synthetic_security_state':Changing.changed}
    with pytest.raises(m.Refused):
        with m.Store(Changing) as store:
            store.write('claim.json',b'{}');Changing.changed=True;store.verify()


def test_exact_public_source_input_and_observation_pins_no_archive_scope():
    assert all(m.sha((m.ROOT/name).read_bytes())==value for name,value in m.SOURCE_PINS.items())
    assert len(m.DATA_PLAN)==2 and m.DATA_PLAN['coverage']['byte_count']==17445
    assert len(m.USB_PINS)==1 and next(iter(m.USB_PINS)).endswith('Stocks_Complete_10_000+_Tickers/Ticker_Listing.txt')
    assert not m.ARCHIVES and not hasattr(m,'Archive') and not hasattr(m,'study')
    policy=m.native_profile();profile=m.profile_record()
    assert 'R335-20261103-F' in policy and 'identity-demand-private.json' in policy
    assert 'R335-20261103-E/private-diagnosis.json' in policy
    assert 'Tickers_A_Day' not in policy and 'manifest.json' not in policy and 'ETF-Complete' not in policy
    assert '(deny network*)' in policy and '/Library/Keychains' in policy and '/usr/bin/security' in policy
    assert profile['retained_E_observation']['actual_parent_exit']==0
    assert m.E_CASES[0][1].startswith('f352b4d7') and m.E_CASES[3][1].startswith('1e241c9a')
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    with ExitStack() as stack:
        assert set(m.load_modules(stack,time.monotonic()+299))=={'guard','anchor'}


def original_row(ticker,index):
    row={'ticker':ticker,'permaticker':str(100+index),'figi':'SYNTHETIC-'+str(index),'cusips':'SYNTHETIC-CUSIP',
        'exchange':'SYNTHETIC','currency':'USD','firstpricedate':'2000-01-01','lastpricedate':'2026-10-16',
        'name':'Synthetic café '+str(index),'relatedtickers':'DO-NOT-PARSE OTHER'}
    row.update({'field'+str(index):'' for index in range(28-len(row))})
    assert len(row)==28
    return row


@pytest.fixture(scope='module')
def genuine_period():return period.make_period(october._sessions())


@pytest.fixture
def scenario(monkeypatch,genuine_period):
    from scripts import arv2_r335_firstrate_prices_v3 as prices
    view=copy.deepcopy(genuine_period);axis=tuple(view['reference_and_valuation_price_sessions'])
    decisions=view['decision_sessions'];positions={value:index for index,value in enumerate(axis)}
    expected={};efacts=[];cases=[];stocks=[None]*6151;ecases=[];listing_rows=[]
    lexical=prices.line_ending_evidence(b'2026-10-13,1,2,1,1,1\n')
    lexical.update(byte_count=50000,LF_count=1000,physical_record_count=1000)
    for ordinal,whole_old,required_count,reference_count,missing_counts in m.E_CASES:
        first=m.EXPECTED_DEMAND[whole_old][0];ticker='SYN'+str(ordinal)
        original=original_row(ticker,ordinal)
        binding={'diagnostic_current_ticker':ticker,'row_sha256':str(ordinal)*64,'source_row_sha256':m.sha(m.original_row_bytes(original))}
        whole=m.sha(m.canonical(binding));expected[whole]=(first,required_count,reference_count)
        efacts.append((ordinal,whole,required_count,reference_count,missing_counts))
        required=tuple(value for value in axis if first<=value<=axis[-1])
        eligible=[value for value in decisions if positions[value]>positions[first]]
        assert len(eligible)==reference_count
        references=tuple(axis[positions[value]-1] for value in eligible)
        demand={'whole_binding_sha256':whole,'potential':True,'source_role':'pending_native_original_identity_source',
            'membership_or_binding_end_used_as_price_end':False,'required_price_first':first,'required_price_last':axis[-1],
            'first_eligible_decision':eligible[0],'last_eligible_decision':eligible[-1],
            'eligible_decision_count':reference_count,'eligible_decisions_sha256':m.sha(m.canonical(eligible))}
        stocks[ordinal]=demand
        current={key:'' for key in m.META_FIELDS};current.update(ticker='ALT'+str(ordinal),figi='SYNTHETIC-'+str(ordinal),permaticker=str(100+ordinal))
        cases.append({'case_ordinal':ordinal,'whole_binding_sha256':whole,'demand':demand,
            'original_case':{'aa_stock':{'binding':binding,'binding_ordinal':ordinal,'original_row':original,'current_candidate_rows':[current]}}})
        listing_row={'Ticker':ticker,'Name':original['name'],'First Date':'2000-01-01','Last Date':'2026-10-16'}
        listing_rows.extend((listing_row,{'Ticker':current['ticker'],'Name':'Alternate','First Date':'2000-01-01','Last Date':'2026-10-16'}))
        candidates=[]
        for candidate_ordinal,(missing_count,missing_refs) in enumerate(missing_counts):
            missing=sorted(list(references[:missing_refs])+[value for value in required if value not in set(references)][:missing_count-missing_refs])
            coverage={'schema':'arv2-r335-firstrate-raw-daily-v3-coverage','member_pin':{'byte_count':50000,'sha256':'a'*64},
                'row_count':1000,'selected_row_count':1000,'quarantined_row_count':0,'partition_policy_sha256':None,
                'required_session_count':required_count,'present_required_count':required_count-missing_count,
                'missing_required_count':missing_count,'reference_session_count':reference_count,
                'present_reference_count':reference_count-missing_refs,'missing_reference_count':missing_refs,
                'observed_date_coverage_complete':missing_count==0,**dict.fromkeys(m.PRICE_FLAGS,False)}
            candidates.append({'archive':m.STOCK_DIR+'Tickers_S_Day_Unadjusted_Full_Dataset.zip',
                'container_pin':{'byte_count':1000,'sha256':'b'*64},'member_name':ticker+('-DELISTED' if candidate_ordinal else '')+'_full_1day_UNADJUSTED.txt',
                'member_pin':coverage['member_pin'],'coverage':coverage,'lexical_evidence':lexical,
                'missing_required_sessions':missing,'alias_is_original_identity_proof':False})
        ecases.append({'case_ordinal':ordinal,'whole_binding_sha256':whole,'ticker':ticker,'listing_matches':[listing_row],'candidates':candidates})
    monkeypatch.setattr(m,'EXPECTED_DEMAND',expected);monkeypatch.setattr(m,'E_CASES',tuple(efacts))
    identity={'schema':'arv2-r327-W5-identity-necessary-demand-i-v1-private','source_fingerprint':'f'*64,
        'period':view,'stock_demand':stocks,'fund_demand':[None]*8,'cases':cases,'metadata_receipt':{}}
    coverage={'schema':m.E_SCHEMA+'-private','cases':ecases,**m.E_FLAGS}
    return NS(identity=identity,coverage=coverage,listing=listing_rows,summary={'source_fingerprint':'f'*64},axis=axis)


def result_value(case):
    public,private=m.diagnose(case.identity,case.coverage,case.listing,case.summary)
    return {'schema':m.SCHEMA,'complete':True,'cases':public,'retained_DATA_authenticated':True,
        'source_guard_normal_return':True,'source_receipt_sha256':'a'*64,
        'retained_E_observation_sha256':m.sha(m.canonical(m.E_OBSERVATION)),
        'private_pin':m.pin(m.canonical(private)),**m.FALSE_FLAGS},private


def test_new_missing_pair_diagnosis_preserves_cases_sources_and_all_explicit_leads(scenario):
    result,private=result_value(scenario)
    assert m.validate_result(result)==result
    assert [row['case_ordinal'] for row in private['cases']]==list(range(5))
    assert [row['candidate_count'] for row in result['cases']]==[1,1,0,1,2]
    assert result['cases'][2]['no_candidate_gap']['missing_required_count']==417
    assert result['cases'][2]['no_candidate_gap']['missing_reference_count']==87
    assert result['cases'][4]['candidates'][0]['missing_required_count']==46
    assert result['cases'][4]['candidates'][1]['missing_required_count']==302
    assert all(row['alias_lead_count']==3 for row in result['cases'])
    assert all(row['exact_listing_match_count']==3 for row in result['cases'])
    assert all(row['optional_relatedtickers_raw']=='DO-NOT-PARSE OTHER' for row in private['cases'])
    assert all(row['relatedtickers_parse_state']=='retained_unparsed' for row in private['cases'])
    raw=m.canonical(result)
    assert not any(value in raw for value in (b'SYN0',b'ALT0',b'CUSIP',b'caf',b'first_missing_date',b'whole_binding'))
    assert all(result[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('change', ['ordinal','whole','duplicate','candidate_count','missing_count','missing_refs','missing_unsorted',
    'missing_duplicate','missing_outside','coverage_bool','readiness','listing','member','rowhash','current_extra','current_bool'])
def test_retained_data_cannot_change_case_identity_count_gap_or_original_source_proof(scenario,change):
    row=scenario.coverage['cases'][1];candidate=row['candidates'][0]
    if change=='ordinal':row['case_ordinal']=0
    elif change=='whole':row['whole_binding_sha256']='0'*64
    elif change=='duplicate':scenario.coverage['cases'][2]=copy.deepcopy(row)
    elif change=='candidate_count':row['candidates']=[]
    elif change=='missing_count':candidate['coverage']['missing_required_count']-=1
    elif change=='missing_refs':candidate['coverage']['missing_reference_count']-=1
    elif change=='missing_unsorted':candidate['missing_required_sessions'].reverse()
    elif change=='missing_duplicate':candidate['missing_required_sessions'][1]=candidate['missing_required_sessions'][0]
    elif change=='missing_outside':candidate['missing_required_sessions'][0]='1900-01-01'
    elif change=='coverage_bool':candidate['coverage']['quarantined_row_count']=False
    elif change=='readiness':scenario.coverage['identity_admitted']=True
    elif change=='listing':row['listing_matches']=[]
    elif change=='member':candidate['member_name']='OTHER_full_1day_UNADJUSTED.txt'
    elif change=='rowhash':scenario.identity['cases'][1]['original_case']['aa_stock']['original_row']['name']='changed'
    elif change=='current_extra':scenario.identity['cases'][1]['original_case']['aa_stock']['current_candidate_rows'][0]['secret']='SECRET'
    else:scenario.identity['cases'][1]['original_case']['aa_stock']['current_candidate_rows'][0]['ticker']=True
    with pytest.raises(m.Refused):m.diagnose(scenario.identity,scenario.coverage,scenario.listing,scenario.summary)


def test_case_join_uses_both_fields_and_never_sorted_digest_order(scenario):
    first=m.diagnose(scenario.identity,scenario.coverage,scenario.listing,scenario.summary)
    scenario.identity['cases'].reverse();scenario.coverage['cases'].reverse()
    assert m.diagnose(scenario.identity,scenario.coverage,scenario.listing,scenario.summary)==first
    assert [row['case_ordinal'] for row in first[1]['cases']]==list(range(5))


def test_original_UTF8_LF_hash_matches_frozen_composer_not_envelope_canonical():
    from research.analyst_revisions_v2.canonical import canonical_json_bytes
    row=original_row('SYN',0)
    expected=canonical_json_bytes(row)
    assert m.original_row_bytes(row)==expected and expected.endswith(b'\n') and 'café'.encode() in expected
    assert m.sha(expected)!=m.sha(m.canonical(row))
    path=m.ROOT/'research/analyst_revisions_v2/canonical.py'
    assert m.sha(path.read_bytes())=='c1d1d1aab633b16868fccc371de7c4cf4f3a692943e04a8d785109110e17ae6e'


def test_gap_runs_use_dense_NYSE_positions_not_calendar_days():
    required=('2026-10-09','2026-10-12','2026-10-13','2026-10-14','2026-10-15')
    public,private=m.gap_geometry(['2026-10-09','2026-10-12','2026-10-15'],required,('2026-10-09','2026-10-14'))
    assert public['gap_run_count']==2 and public['longest_gap_run']==2
    assert public['leading_missing_count']==2 and public['trailing_missing_count']==1
    assert private['runs'][0]['first_date']=='2026-10-09' and private['runs'][0]['last_date']=='2026-10-12'
    all_public,_=m.gap_geometry(list(required),required,required)
    assert all_public['leading_missing_count']==all_public['trailing_missing_count']==5
    assert all_public['interior_missing_count']==0
    assert m.validate_gap_summary(all_public,5,5)==all_public


def test_metadata_leads_never_use_names_CUSIP_or_relatedtickers_and_retain_unsupported_tokens(scenario):
    item=scenario.identity['cases'][0]['original_case']['aa_stock']
    item['current_candidate_rows'][0]['ticker']='X/Y'
    scenario.listing.append({'Ticker':'DO-NOT-PARSE','Name':item['original_row']['name'],'First Date':'2000-01-01','Last Date':'2026-10-16'})
    result,private=result_value(scenario)
    leads=private['cases'][0]['metadata_leads']
    assert leads[-1]['token']=='X/Y' and leads[-1]['token_supported'] is False and leads[-1]['listing_matches']==[]
    assert result['cases'][0]['supported_alias_lead_count']==2
    assert not any(lead['token']=='DO-NOT-PARSE' for lead in leads)


@pytest.mark.parametrize('change',['public_identity','flag','case_bool','count_bool','candidate_count','gap_zero_runs','alias_count','extra','source_guard'])
def test_public_output_has_closed_finite_count_only_schema(scenario,change):
    value,_=result_value(scenario)
    if change=='public_identity':value['cases'][0]['ticker']='SECRET'
    elif change=='flag':value['identity_admitted']=True
    elif change=='case_bool':value['cases'][0]['case_ordinal']=False
    elif change=='count_bool':value['cases'][0]['candidate_count']=True
    elif change=='candidate_count':value['cases'][1]['candidate_count']=0
    elif change=='gap_zero_runs':value['cases'][1]['candidates'][0]['gap_run_count']=0
    elif change=='alias_count':value['cases'][0]['alias_lead_count']+=1
    elif change=='extra':value['raw_price']='SECRET'
    else:value['source_guard_normal_return']=False
    refuse('output',lambda:m.validate_result(value))


def test_actual_exit_and_report_pin_gate_success_and_failure_stays_failure(scenario,monkeypatch):
    value,_=result_value(scenario);report={'binding':m.binding(args()),'result':value}
    envelope={**report,'report_pin':m.pin(m.canonical(report))};raw=m.canonical(envelope)+b'\n'
    assert m.validate_envelope(raw,0,args())==envelope
    for actual in (2,True,None,-9):refuse('child_failure',lambda:m.validate_envelope(raw,actual,args()))
    envelope['report_pin']['sha256']='0'*64
    refuse('output',lambda:m.validate_envelope(m.canonical(envelope)+b'\n',0,args()))
    monkeypatch.setattr(m,'ACTIVE_BINDING',m.binding(args()));monkeypatch.setattr(m,'CLAIM_STATE','consumed')
    monkeypatch.setattr(m,'FAILURE_STAGE','case_metadata');monkeypatch.setattr(m,'FAILURE_CASE',2)
    failure=m.failure_packet('coverage_record')
    parent={'binding':m.binding(args()),'actual_child_exit':2,'output_authenticated':True,
        'child_stdout_pin':m.pin(m.canonical(failure)+b'\n'),'child_stderr_byte_count':0,'failure':failure}
    actual=m.validate_parent_output(m.canonical(parent)+b'\n',2,args())
    assert actual['accepted'] is False and actual['failure']['failure_code']=='coverage_record'


def test_finite_guard_failure_retains_safe_exact_code(monkeypatch):
    from scripts import arv2_r298_fixed_data_guard as guard
    monkeypatch.setattr(m,'GUARD_MODULE',guard)
    assert m.finite(guard.Refused('byte_pin'))=='guard_byte_pin'
    assert m.finite(ValueError('PRIVATE SECRET'))=='unknown'


def test_dynamic_worker_claims_before_exact_two_DATA_and_one_USB_listing_normal_return_before_output(scenario,monkeypatch):
    events=[];opened=0;guarded=False
    expected_plan=copy.deepcopy(m.DATA_PLAN)
    raw={'identity':m.canonical(scenario.identity),'coverage':m.canonical(scenario.coverage)}
    listing_raw=('Ticker,Name,First Date,Last Date\n'+''.join(','.join(row[key] for key in ('Ticker','Name','First Date','Last Date'))+'\n' for row in scenario.listing)).encode()
    class Guard:
        def __init__(self,plan,**kwargs):assert plan==expected_plan
        def __enter__(self):
            nonlocal guarded
            assert events==[('write','claim.json')];guarded=True;events.append(('DATA_enter',None));return self
        def read_all_once(self):events.append(('DATA_read',tuple(raw)));return raw
        def verify(self):events.append(('DATA_verify',None))
        def receipt(self):return {'synthetic':True}
        def __exit__(self,*args):
            nonlocal guarded
            guarded=False;events.append(('DATA_return',None))
    class Held:
        def __init__(self,path,**kwargs):assert path==m.USB/next(iter(m.USB_PINS))
        def __enter__(self):
            nonlocal opened
            assert guarded;opened+=1;events.append(('USB_enter',None));return self
        def read(self):events.append(('USB_listing_read',None));return listing_raw
        def __exit__(self,*args):
            nonlocal opened
            opened-=1;events.append(('USB_return',None))
    class Store:
        def __init__(self,security):assert security is Security
        def __enter__(self):return self
        def write(self,name,data):
            assert not guarded and not opened
            assert name in ('claim.json','private-diagnosis.json','report.json')
            events.append(('write',name));return m.pin(data)
        def __exit__(self,*args):events.append(('store_return',None))
    anchor=NS(observed_fact=lambda:{'private_data':expected_plan['identity'],'result':{'identity_summary':scenario.summary}})
    monkeypatch.setattr(m,'preflight',lambda *args:None)
    monkeypatch.setattr(m,'load_modules',lambda *args:{'guard':NS(FixedDataGuard=Guard,security=Security),'anchor':anchor})
    monkeypatch.setattr(m,'HeldFile',Held);monkeypatch.setattr(m,'Store',Store)
    value_args=args();reader,writer=os.pipe();value_args.intent_fd=reader
    os.write(writer,m.canonical(m.binding(value_args)));os.close(writer)
    value=m.worker(value_args,time.monotonic()+299)
    assert m.validate_result(value['result'])==value['result']
    assert [item for item in events if item[0]=='DATA_read']==[('DATA_read',('identity','coverage'))]
    assert [item for item in events if item[0]=='USB_listing_read']==[('USB_listing_read',None)]
    assert [item[1] for item in events if item[0]=='write']==['claim.json','private-diagnosis.json','report.json']
    assert events.index(('DATA_return',None))<events.index(('write','private-diagnosis.json'))
    assert events.index(('USB_return',None))<events.index(('write','private-diagnosis.json'))


def test_real_offline_validator_preserves_actual_two_without_control_DATA_reads(monkeypatch):
    monkeypatch.setattr(m,'ACTIVE_BINDING',m.binding(args()));monkeypatch.setattr(m,'CLAIM_STATE','consumed')
    monkeypatch.setattr(m,'FAILURE_STAGE','case_metadata');monkeypatch.setattr(m,'FAILURE_CASE',2)
    failure=m.failure_packet('coverage_record')
    value={'binding':m.binding(args()),'actual_child_exit':2,'output_authenticated':True,
        'child_stdout_pin':m.pin(m.canonical(failure)+b'\n'),'child_stderr_byte_count':0,'failure':failure}
    result=subprocess.run([sys.executable,'-I','-B',str(m.SOURCE),'validate','--expected-head',args().expected_head,
        '--caller-sha256',args().caller_sha256,'--profile-sha256',args().profile_sha256,'--actual-parent-exit','2'],
        cwd=m.ROOT,input=m.canonical(value)+b'\n',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,
        env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'})
    assert result.returncode==2 and not result.stderr
    observed=json.loads(result.stdout)
    assert observed['accepted'] is False and observed['failure']['failure_code']=='coverage_record'
    assert observed['failure']['case_ordinal']==2 and observed['actual_child_exit']==2


def test_reused_host_parent_and_FD_guards_remain_AST_identical_to_E():
    old_path=m.ROOT/'scripts/inspect_arv2_r335_firstrate_stock_coverage.py'
    raw=old_path.read_bytes();assert m.sha(raw)=='cc804e71d86d1e4fbe792a841379db7acb41080d092f6a8b7e16c60a23435c7d'
    old,new=ast.parse(raw),ast.parse(m.SOURCE.read_bytes())
    for name in ('HeldFile','Store','parent','validate_envelope','validate_parent_output','preflight','safe_env','Parser','main','demands','_sessions'):
        get=lambda tree:next(node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name==name)
        assert ast.dump(get(old),include_attributes=False)==ast.dump(get(new),include_attributes=False)
