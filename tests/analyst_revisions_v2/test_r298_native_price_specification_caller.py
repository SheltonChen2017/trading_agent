"""AE synthetic DATA-to-metadata preparation; no vendor, original archive or QC I/O."""
import copy
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import prepare_arv2_r298_native_price_specification as m
from tests.analyst_revisions_v2 import test_r298_sharadar_all_routes as original_fixture
from tests.analyst_revisions_v2 import test_r298_sharadar_eligibility_observation as metadata_fixture

ARGS=NS(expected_head='a'*40,caller_sha256='b'*64)


def refused(code,function):
    with pytest.raises(m.Refused) as caught: function()
    assert m.finite(caught.value)==code


def valid_figi(index):
    stem='BBG'+('%08d'%index)
    return next(stem+str(digit) for digit in range(10) if m.previous._valid_figi(stem+str(digit)))


def selection_fixture(*, category=None):
    contract=m.previous.source_binding()['aa_routing_summary']['binding_contract']
    price=m.previous.previous.routes
    cases=[];all_figis=set()
    for index in range(5):
        source=original_fixture.source(index+1)
        source['figi']=valid_figi(index)
        source['name']='PRIVATE-ORIGINAL-ISSUER'
        if index==0: source['currency']='CAD'
        if category is not None and index==0: source['category']=category
        binding=original_fixture.binding(source,6151)
        binding['security_master_admission_sha256']=m.diagnostic.ADMISSION_SHA256
        binding['admitted_mapping_inventory_sha256']=contract['admitted_mapping_inventory_sha256']
        semantic=dict(binding);semantic.pop('row_sha256')
        binding['row_sha256']=hashlib.sha256(m.diagnostic.figi._canonical(semantic)).hexdigest()
        ids=([valid_figi(5),valid_figi(6)] if index==0 else
            [valid_figi(7)] if index==1 else [valid_figi(8)] if index==2 else [valid_figi(index-3)])
        current=[]
        for ordinal,figi in enumerate(ids):
            row=metadata_fixture.metadata('SYN-CURRENT',100+index*2+ordinal)
            row['figi']=figi;current.append(row)
        reason='identity_missing' if index<4 else 'global_collision'
        aa={'binding_ordinal':index,'binding':copy.deepcopy(binding),'original_row':source,
            'original_cusip_tokens':list(price.routes.current.parse_vocabulary(source['cusips'])),
            'required_first_date':'2020-12-31','required_last_date':'2026-10-13','current_candidate_rows':current,
            'disposition':'refused','reason':'current_identity_changed','route':None}
        ac={'binding_ordinal':index,'binding':binding,'aa_disposition':aa['disposition'],'aa_reason':aa['reason'],
            'potential':True,'conditional_never_potential':False,'disposition':'refused','reason':reason,
            'route':None,'observed_flags':dict.fromkeys(price.FLAGS,False),'query_window':None}
        cases.append({'case_ordinal':index,'ac_stock':ac,'aa_stock':aa,
            'original_figi':binding['composite_figi'],'candidate_figis':sorted(set(ids))})
        all_figis.add(binding['composite_figi']);all_figis.update(ids)
    return {'schema':m.previous.SCHEMA+'-private-selection','cases':cases,'figis':sorted(all_figis)}


def make_package(selection):
    case_raw=m.diagnostic.canonical(selection)
    expected=copy.deepcopy(m.anchor.expected_failure()['state']['selection_summary'])
    expected['private_case_byte_count']=len(case_raw);expected['private_case_sha256']=m.sha(case_raw)
    value={'schema':m.previous.SCHEMA+'-private','source_pins':{role:{'byte_count':row['byte_count'],'sha256':row['sha256']}
        for role,row in m.previous.FILE_PLAN.items()},'AC_summary_sha256':m.previous.AC_SUMMARY_SHA256,
        'selection_summary':expected,'selection':selection,'mapping_batches':[],'corroborations':[],
        'response_pins':{},'terminal_failure_code':'transport_unknown','vendor_source_blockers_remaining':5,
        'candidate_scope':'complete_retained_AA_subset_not_vendor_global_counterparty_census',
        'no_original_identifier_or_vendor_collision_clearance':True}
    return value,expected


def source_receipt():
    return {'schema':m.data_guard.SCHEMA+'-receipt',
        'profile_sha256':m.sha(m.data_guard.canonical(m.data_guard.profile_record(m.FILE_PLAN))),
        'files':{role:{**pin,'current_metadata_sha256':'d'*64,'current_security_sha256':'e'*64}
            for role,pin in m.FILE_PLAN.items()},'fresh_current_security_authenticated':True,
        'fixed_bytes_authenticated':True,'requires_normal_return_before_use':True,
        'historical_continuity_proven':False,'continuous_integrity_proven':False}


def actual(output=b'',*,exit=0,bound=None,errors=b''):
    return {'actual_exit':exit,'bound':bound,'spawn_observed':True,
        'dispatched_at':'2026-10-27T00:00:00Z','completion_observed_at':'2026-10-27T00:00:01Z',
        'stdout_bytes':len(output),'stdout_sha256':m.sha(output),'stderr_bytes':len(errors),'stderr_sha256':m.sha(errors)}


@pytest.fixture(autouse=True)
def no_operations(monkeypatch):
    def deny(*args,**kwargs):raise AssertionError('spent operation/provider/QC capability forbidden')
    monkeypatch.setattr(m.previous,'run',deny);monkeypatch.setattr(m.previous,'observe',deny)
    monkeypatch.setattr(m.previous,'preflight',deny);monkeypatch.setattr(m.previous,'_session',deny)
    monkeypatch.setattr(m.diagnostic,'NativePriceSourceDiagnostic',deny)


@pytest.fixture
def supplied(monkeypatch):
    selection=selection_fixture()
    package,expected=make_package(selection)
    raw=m.diagnostic.canonical(package)
    plan=copy.deepcopy(m.FILE_PLAN)
    plan['ad_selection'].update(byte_count=len(raw),sha256=m.sha(raw))
    monkeypatch.setattr(m,'FILE_PLAN',plan)
    monkeypatch.setattr(m,'SELECTION_BYTES',expected['private_case_byte_count'])
    monkeypatch.setattr(m,'SELECTION_SHA256',expected['private_case_sha256'])
    monkeypatch.setattr(m,'source_binding',lambda:copy.deepcopy(expected))
    return NS(selection=selection,package=package,raw=raw,expected=expected)


@pytest.fixture
def state(supplied,monkeypatch):
    state=NS(events=[],files={},stores=0,prepares=0,fail_stage=None,raw=supplied.raw)
    monkeypatch.setattr(m,'binding',lambda args:{'schema':m.SCHEMA,'expected_head':args.expected_head,
        'caller_sha256':args.caller_sha256,'profile_sha256':'c'*64})
    class MemoryStore:
        def __init__(self):
            state.stores+=1;m.require(state.stores==1,'claim_spent')
        def __enter__(self):return self
        def __exit__(self,*_):state.events.append('store_close')
        def verify(self):state.events.append('store_verify')
        def write(self,name,value):return self.write_bytes(name,m.canonical(value),private=False)
        def write_bytes(self,name,raw,*,private):
            assert private is False
            m.require(name not in state.files,'control_name');state.events.append('write:'+name)
            if state.fail_stage==name:raise m.Refused('control_write')
            if name==m.SPEC_NAME:assert 'source_return' in state.events
            state.files[name]=bytes(raw);return {'byte_count':len(raw),'sha256':m.sha(raw)}
    class MemoryGuard:
        def __init__(self,plan,*,deadline):assert plan==m.FILE_PLAN
        def __enter__(self):
            assert 'claim.json' in state.files and 'source-start.json' in state.files
            state.events.append('source_enter');return self
        def __exit__(self,kind,*_):
            state.events.append('source_exit')
            if state.fail_stage=='guard_return' and kind is None:raise m.data_guard.Refused('named_changed')
            if kind is None:state.events.append('source_return')
        def read_all_once(self):state.events.append('source_read');return {'ad_selection':state.raw}
        def receipt(self):
            if state.fail_stage=='source_receipt':raise m.data_guard.Refused('named_changed')
            return source_receipt()
    prepare=m.prepare
    def observed_prepare(raw,deadline):
        state.prepares+=1;state.events.append('prepare')
        assert state.prepares==1 and 'source_exit' not in state.events
        if state.fail_stage=='prepare':raise m.Refused('selection')
        return prepare(raw,deadline)
    def preflight(*args):
        state.events.append('postflight')
        if state.fail_stage=='postflight':raise m.Refused('source_pin')
    monkeypatch.setattr(m,'Store',MemoryStore);monkeypatch.setattr(m.data_guard,'FixedDataGuard',MemoryGuard)
    monkeypatch.setattr(m,'prepare',observed_prepare);monkeypatch.setattr(m,'preflight',preflight)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:state.events.append('safe_environment'))
    return state


def run():
    return m.run(ARGS,time.monotonic()+100)


def test_five_exact_original_bindings_produce_metadata_spec_after_normal_guard_return_without_QC(state):
    outcome=run()
    assert set(outcome)=={'result','report'} and state.prepares==1
    result=outcome['result'];spec=result['specification']
    assert result['AD_actual_producer_exit']==2 and result['AD_actual_validator_exit']==0
    assert result['AD_mapping_accepted'] is False and result['old_AD_mapping_accepted'] is False
    assert len(spec['selected_whole_binding_sha256s'])==5 and spec['requested_session_count']==1452
    assert spec['maximum_history_calls']==5 and spec['first_session']=='2020-12-31' and spec['last_session']=='2026-10-13'
    assert result['selection_evidence']['original_non_USD_functional_reporting_currency_count']==1
    assert result['selection_evidence']['original_native_QC_SIDs_available'] is False
    assert state.events.index('source_return')<state.events.index('write:'+m.SPEC_NAME)
    assert state.events.count('safe_environment')==6
    assert state.files[m.SPEC_NAME]==m.diagnostic.canonical(spec)
    raw=m.canonical(outcome)
    assert b'PRIVATE-ORIGINAL' not in raw and b'BBG' not in raw and b'SYN-CURRENT' not in raw
    assert all(result[flag] is False for flag in m.FALSE_FLAGS)
    value={'binding':m.binding(ARGS),'outcome':outcome}
    assert m.validate_output(m.canonical(value),0,ARGS)==value


@pytest.mark.parametrize('failure',['source_receipt','prepare','guard_return','native-price-specification.json','postflight','report.json'])
def test_failure_preserves_spent_source_evidence_without_replay_early_publication_or_false_AD_success(state,failure):
    state.fail_stage=failure
    failed=run()['failure']
    assert failed['claim_consumed'] is True and state.prepares<=1
    if failure in ('source_receipt','prepare','guard_return'):assert m.SPEC_NAME not in state.files
    assert all(failed[flag] is False for flag in m.FALSE_FLAGS)
    value={'binding':m.binding(ARGS),'outcome':{'failure':failed}}
    assert m.validate_output(m.canonical(value),2,ARGS)==value
    refused('claim_spent',run)


def test_whole_binding_hashes_use_full_ASCII_NO_LF_namespace_and_frozen_semantic_row_validation(supplied):
    evidence,spec=m.prepare(supplied.raw,time.monotonic()+30)
    rows=[case['ac_stock']['binding'] for case in supplied.selection['cases']]
    expected=sorted(m.diagnostic.digest(m.diagnostic.figi._input_row(row,m.diagnostic.ADMISSION_SHA256)) for row in rows)
    assert evidence['selected_whole_binding_sha256s']==spec['selected_whole_binding_sha256s']==expected
    assert all(m.diagnostic.canonical(row).endswith(b'\n') is False for row in rows)
    assert all(m.diagnostic.figi._canonical(row).endswith(b'\n') for row in rows)
    assert set(expected).isdisjoint(m.sha(m.diagnostic.figi._canonical(row)) for row in rows)


@pytest.mark.parametrize('fault',['row_hash','admission','inventory','count','native_sid','source_hash','class','case_order',
    'duplicate_binding','candidate_figi','figi_inventory','reason','binding_mismatch','CUSIP_tokens'])
def test_every_selected_original_binding_class_evidence_and_unique_hash_remains_required(supplied,fault):
    selection=copy.deepcopy(supplied.selection);case=selection['cases'][0]
    if fault=='row_hash':case['ac_stock']['binding']['row_sha256']='f'*64
    elif fault=='admission':case['ac_stock']['binding']['security_master_admission_sha256']='f'*64
    elif fault=='inventory':case['ac_stock']['binding']['admitted_mapping_inventory_sha256']='f'*64
    elif fault=='count':case['ac_stock']['binding']['admitted_mapping_count']=1
    elif fault=='native_sid':case['ac_stock']['binding']['qc_security_id']='PRIVATE-INVENTED-SID'
    elif fault=='source_hash':case['aa_stock']['original_row']['name']='PRIVATE-CHANGED'
    elif fault=='class':case['aa_stock']['original_row']['category']='Preferred Stock'
    elif fault=='case_order':case['case_ordinal']=True
    elif fault=='duplicate_binding':selection['cases'][1]=copy.deepcopy(case);selection['cases'][1]['case_ordinal']=1
    elif fault=='candidate_figi':case['candidate_figis']=['BBG000BLNNH7']
    elif fault=='figi_inventory':selection['figis'].pop()
    elif fault=='reason':case['ac_stock']['reason']='routed'
    elif fault=='binding_mismatch':case['aa_stock']['binding']['diagnostic_current_ticker']='PRIVATE-MISMATCH'
    else:case['aa_stock']['original_cusip_tokens']=[]
    with pytest.raises(m.Refused):m._selection_hashes(selection,time.monotonic()+30)


def test_fixed_package_pin_refuses_before_JSON_decode(monkeypatch):
    monkeypatch.setattr(m.previous,'_decode_private',lambda raw:(_ for _ in ()).throw(AssertionError('no parse')))
    refused('package',lambda:m.prepare(b'not fixed private DATA',time.monotonic()+10))


def test_reporting_currency_exception_does_not_admit_a_correctly_hashed_preferred_original():
    selection=selection_fixture(category='Preferred Stock')
    # Rebuilt evidence, source digest and semantic row digest are internally
    # consistent, so this proves the retained common-stock predicate itself.
    refused('original_evidence',lambda:m._selection_hashes(selection,time.monotonic()+30))


@pytest.mark.parametrize('fault',['extra','terminal','old_mapping','private_selection_digest','source_frame_pin'])
def test_private_package_is_closed_failed_transport_evidence_only(supplied,monkeypatch,fault):
    value=copy.deepcopy(supplied.package)
    if fault=='extra':value['unlicensed_rows']=[]
    elif fault=='terminal':value['terminal_failure_code']='accepted'
    elif fault=='old_mapping':value['mapping_batches']=[{'fabricated':True}]
    elif fault=='private_selection_digest':value['selection']['cases'][0]['original_figi']='BBG000BLNNH7'
    else:value['source_pins']['aa_frame']['sha256']='f'*64
    raw=m.diagnostic.canonical(value)
    m.FILE_PLAN['ad_selection'].update(byte_count=len(raw),sha256=m.sha(raw))
    with pytest.raises(m.Refused):m.prepare(raw,time.monotonic()+30)


@pytest.mark.parametrize('fault',['exit2','exit_bool','report','old_AD_success','new_guard','spec_hash','hashes','source'])
def test_public_new_success_needs_own_actual_zero_closed_metadata_pin_and_preserved_old_actual_two(state,fault):
    value={'binding':m.binding(ARGS),'outcome':run()};result=value['outcome']['result'];exit=0
    if fault=='exit2':exit=2
    elif fault=='exit_bool':exit=False
    elif fault=='report':value['outcome']['report']['sha256']='f'*64
    elif fault=='old_AD_success':result['AD_actual_producer_exit']=0
    elif fault=='new_guard':result['source_guard_returned']=False
    elif fault=='spec_hash':result['specification_pin']['sha256']='f'*64
    elif fault=='hashes':result['specification']['selected_whole_binding_sha256s'][0]='f'*64
    else:result['source_receipt']=None
    # Preserve the outer report hash so each case exercises the semantic
    # gate rather than merely detecting an obsolete report checksum.
    if fault!='report':
        report=m.canonical({**m.binding(ARGS),'result':result})
        value['outcome']['report']={'byte_count':len(report),'sha256':m.sha(report)}
    with pytest.raises((m.Refused,m.diagnostic.Refused,m.data_guard.Refused)):
        m.validate_output(m.canonical(value),exit,ARGS)



@pytest.mark.parametrize('fault', ['producer_nonzero', 'producer_bool', 'producer_timeout',
    'producer_noise', 'producer_binding', 'validator_nonzero', 'validator_bool', 'validator_noise', 'validator_binding'])
def test_no_data_observer_requires_exact_native_producer_and_separate_validator_actuals(state, monkeypatch, fault):
    value = {'binding': m.binding(ARGS), 'outcome': run()}
    raw = m.canonical(value)
    calls = []
    def capture(command, safe, timeout, **kwargs):
        calls.append((command, safe, timeout, kwargs))
        assert command[:2] == ['/usr/bin/sandbox-exec', '-p']
        assert '(deny network*)' in command[2] and '/usr/bin/security' in command[2]
        producer = len(calls) == 1
        errors = b'noise' if fault == ('producer_noise' if producer else 'validator_noise') else b''
        exit = (2 if fault == ('producer_nonzero' if producer else 'validator_nonzero') else
            False if fault == ('producer_bool' if producer else 'validator_bool') else 0)
        if fault == 'producer_nonzero' and not producer:
            # A real external validator refuses a success envelope paired
            # with observed producer exit2, rather than fabricating exit0.
            refused('output', lambda: m.validate_output(raw, 2, ARGS))
            exit = 2
        output = raw if not (fault == 'validator_binding' and not producer) else m.canonical({'wrong': 'metadata'})
        checked = actual(output, exit=exit, errors=errors,
            bound='deadline' if fault == 'producer_timeout' and producer else None)
        if fault == 'producer_binding' and producer: checked['stdout_sha256'] = 'f' * 64
        if not producer:
            assert kwargs['input_bytes'] == raw and timeout == m.VALIDATOR_SECONDS
        return output, errors, checked
    monkeypatch.setattr(m, 'capture', capture)
    outer, code = m.observe(ARGS)
    assert code == 2 and outer['output_authenticated'] is False
    assert len(calls) == (1 if fault.startswith('producer_') and fault != 'producer_nonzero' else 2)
    assert outer['failure_code'] in ('parent_failed', 'validator_failed')


def test_observer_authenticates_failure_without_reclassifying_it_success(state, monkeypatch):
    state.fail_stage = 'prepare'
    raw = m.canonical({'binding': m.binding(ARGS), 'outcome': run()})
    calls = []
    def capture(command, safe, timeout, **kwargs):
        calls.append(command)
        return raw, b'', actual(raw, exit=2 if len(calls) == 1 else 0)
    monkeypatch.setattr(m, 'capture', capture)
    outer, code = m.observe(ARGS)
    assert code == 2 and outer['output_authenticated'] is True and outer['failure_code'] is None
    assert outer['output']['outcome']['failure']['claim_consumed'] is True and len(calls) == 2


def test_observer_public_only_success_broker_never_opens_private_output(state, monkeypatch):
    value = {'binding': m.binding(ARGS), 'outcome': run()}; raw = m.canonical(value)
    calls = []
    def capture(command, safe, timeout, **kwargs):
        calls.append(command)
        return raw, b'', actual(raw)
    monkeypatch.setattr(m, 'capture', capture)
    outer, code = m.observe(ARGS)
    assert code == 0 and outer['output_authenticated'] is True and outer['output'] == value
    assert b'PRIVATE-' not in m.canonical(outer)
    assert len(calls) == 2

@pytest.mark.parametrize('fault', ['zero', 'placeholder', 'conflict', 'baseline_count'])
def test_unfrozen_or_conflicting_source_pin_map_refuses(fault, monkeypatch):
    baseline = {'scripts/existing-' + str(i) + '.py': 'd' * 64 for i in range(178)}
    monkeypatch.setattr(m.previous, 'pins', lambda: baseline)
    additions = {'scripts/new.py': 'e' * 64}
    if fault == 'zero': additions['scripts/new.py'] = '0' * 64
    elif fault == 'placeholder': additions['scripts/new.py'] = 'UNFROZEN'
    elif fault == 'conflict': additions['scripts/existing-1.py'] = 'f' * 64
    else: baseline.pop('scripts/existing-1.py')
    monkeypatch.setattr(m, 'NEW_PINS', additions)
    refused('source_pin', m.pins)


@pytest.mark.parametrize('change',['content','mode','name','extra_name'])
def test_real_owned_control_detects_external_drift_without_cleanup(tmp_path, monkeypatch, change):
    control = tmp_path / 'synthetic-AE-parent/synthetic-AE'
    monkeypatch.setattr(m, 'CONTROL', control)
    with m.Store() as store:
        store.write('claim.json', {'synthetic': True})
        path = control / 'claim.json'
        if change == 'content': path.write_bytes(b'changed')
        elif change == 'mode': path.chmod(0o644)
        elif change == 'extra_name': (control / 'synthetic-unexpected').write_bytes(b'extra')
        else:
            path.rename(control / 'synthetic-retained-old')
            path.write_bytes(b'changed'); path.chmod(0o600)
        refused('control_changed' if change in ('extra_name', 'name') else 'capture_changed', store.verify)
    assert control.is_dir()


def test_cli_parent_and_validator_use_alarm_and_preflight_before_any_operation(monkeypatch):
    events, stdout = [], io.BytesIO()
    class Alarm:
        def __init__(self, deadline):
            assert 0 < deadline - time.monotonic() <= m.DEADLINE_SECONDS
            events.append('alarm_construct')
        def __enter__(self): events.append('alarm_enter')
        def __exit__(self, *_): events.append('alarm_exit')
    monkeypatch.setattr(m.admitted.helpers, '_alarm', Alarm)
    monkeypatch.setattr(m, 'preflight', lambda *args: events.append('preflight'))
    monkeypatch.setattr(m.environment, '_bootstrap_cli_logging', lambda: events.append('logging'))
    monkeypatch.setattr(m, 'binding', lambda args: {'synthetic': True})
    def run(args, deadline):
        events.append('run'); return {'failure': {'synthetic': True}}
    monkeypatch.setattr(m, 'run', run)
    monkeypatch.setattr(m.sys, 'stdout', NS(buffer=stdout))
    assert m.main(['run', '--expected-head', ARGS.expected_head, '--caller-sha256', ARGS.caller_sha256]) == 2
    assert events == ['alarm_construct', 'alarm_enter', 'preflight', 'logging', 'run', 'alarm_exit']
    assert json.loads(stdout.getvalue()) == {'binding': {'synthetic': True},
        'outcome': {'failure': {'synthetic': True}}}


@pytest.fixture
def public_preflight(monkeypatch):
    raw = m.SOURCE.read_bytes()
    args = NS(expected_head='a' * 40, caller_sha256=m.sha(raw))
    state = NS(raw=raw, args=args, calls=[], change=None)
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: False)
    monkeypatch.setattr(m.environment, '_require_environment', lambda: None)
    monkeypatch.setattr(m, 'pins', lambda: {m.SOURCE.relative_to(m.ROOT).as_posix():
        'f' * 64 if state.change == 'selected_pin' else m.sha(raw)})
    values = {('rev-parse', '--show-toplevel'): str(m.ROOT),
        ('branch', '--show-current'): m.admitted.frozen.BRANCH,
        ('rev-parse', 'HEAD'): args.expected_head, ('status', '--porcelain'): ''}
    def git(command, deadline, *args):
        state.calls.append(command)
        if command[0] == 'cat-file':
            return b'wrong committed source bytes' if state.change == 'committed_blob' else raw
        value = values[tuple(command)]
        if state.change == tuple(command): value = 'concurrent or mismatched synthetic state'
        return value.encode('ascii')
    monkeypatch.setattr(m.admitted.v5, '_git', git)
    return state


def test_preflight_binds_exact_host_clean_root_branch_head_source_and_committed_blob(public_preflight):
    fixture = public_preflight
    m.preflight(fixture.args, time.monotonic() + 30)
    assert fixture.calls[:4] == [['rev-parse', '--show-toplevel'], ['branch', '--show-current'],
        ['rev-parse', 'HEAD'], ['status', '--porcelain']]
    assert fixture.calls[-1] == ['cat-file', 'blob', fixture.args.expected_head + ':'
        + m.SOURCE.relative_to(m.ROOT).as_posix()]


@pytest.mark.parametrize('change', [('rev-parse', '--show-toplevel'), ('branch', '--show-current'),
    ('rev-parse', 'HEAD'), ('status', '--porcelain'), 'selected_pin', 'caller_pin', 'committed_blob'])
def test_preflight_concurrent_git_or_source_mismatch_refuses_without_refresh(public_preflight, change):
    fixture = public_preflight; fixture.change = change
    if change == 'caller_pin': fixture.args.caller_sha256 = 'f' * 64
    refused('git_state' if type(change) is tuple else 'source_pin',
        lambda: m.preflight(fixture.args, time.monotonic() + 30))


def test_preflight_test_host_and_invalid_args_refuse_before_git(public_preflight, monkeypatch):
    fixture = public_preflight
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: True)
    refused('host', lambda: m.preflight(fixture.args, time.monotonic() + 30))
    assert fixture.calls == []
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: False)
    fixture.args.expected_head = 'not a frozen commit'
    refused('arguments', lambda: m.preflight(fixture.args, time.monotonic() + 30))
    assert fixture.calls == []

def test_real_metadata_only_new_store_is_exclusive_and_never_accepts_private_bytes(tmp_path,monkeypatch):
    control=tmp_path/'synthetic-AE-parent/synthetic-AE'
    monkeypatch.setattr(m,'CONTROL',control)
    with m.Store() as directory:
        directory.write('claim.json',{'metadata_only':True})
        raw=b'{"metadata_only":true}'
        pin=directory.write_bytes(m.SPEC_NAME,raw,private=False)
        assert pin=={'byte_count':len(raw),'sha256':m.sha(raw)}
        held=directory.held[m.SPEC_NAME][0]
        assert directory._read(held,len(raw))==raw
        refused('control_name',lambda:directory.write_bytes('forbidden.json',b'PRIVATE-',private=True))
        refused('control_name',lambda:directory.write('claim.json',{}))
        refused('control_name',lambda:directory.write('../outside.json',{}))
        refused('control_bound',lambda:directory.write_bytes('empty.json',b'',private=False))
        refused('claim_spent',m.Store)
        directory.verify()
    assert {item.name for item in control.iterdir()}=={'claim.json',m.SPEC_NAME}
    with pytest.raises(OSError):os.fstat(held)


@pytest.mark.parametrize('deadline',[None,True,float('nan'),float('inf'),-1])
def test_nonfinite_boolean_and_expired_deadlines_refuse(deadline):
    refused('deadline',lambda:m.remaining(deadline))


def test_current_alarm_exact_type_is_finite_but_foreign_subclass_is_unknown():
    assert m.finite(m.admitted.helpers.Deadline())=='deadline'
    class Foreign(m.admitted.helpers.Deadline):pass
    assert m.finite(Foreign())=='unknown_exception'


def test_actual_AD_failure_anchor_is_metadata_only_not_mapping_success():
    summary=m.source_binding()
    assert summary['case_count']==5 and summary['unique_valid_figi_count']==9
    assert summary['inventory_refusal'] is None
    fact=m.anchor.observed_fact()
    assert fact['producer']['actual_exit']==2 and fact['validator']['actual_exit']==0
    assert fact['source_guard_returned'] is True
    assert fact['private_file']==m.FILE_PLAN['ad_selection']


@pytest.mark.parametrize('fault',['actual_exit','guard','selection','private_pin','old_mapping'])
def test_AD_fact_and_failure_public_anchors_are_exactly_pinned(monkeypatch,fault):
    fact,failure=m.anchor.observed_fact(),m.anchor.expected_failure()
    if fault=='actual_exit':fact['producer']['actual_exit']=0
    elif fault=='guard':fact['source_guard_returned']=False
    elif fault=='selection':failure['state']['selection_summary']['unique_valid_figi_count']=8
    elif fault=='private_pin':fact['private_file']['sha256']='f'*64
    else:failure['state']['mapping_complete']=True
    monkeypatch.setattr(m.anchor,'observed_fact',lambda:fact)
    monkeypatch.setattr(m.anchor,'expected_failure',lambda:failure)
    refused('source_binding',m.source_binding)


def test_profile_native_scope_exposes_only_one_new_DATA_and_own_metadata_outputs():
    profile=m.profile_record()
    assert len(profile['source_pins'])==181
    assert profile['source_data_leaf_count']==1 and profile['source_stop_retained_vendor_issues']==5
    assert profile['producer_seconds']==120 and profile['outer_seconds']==150 and profile['validator_seconds']==20
    assert profile['one_native_producer_no_inner_child_or_nested_sandbox'] is True
    assert profile['original_QC_SIDs_absent_never_inferred'] is True
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    producer,validator=m.native_profile(mode='producer'),m.native_profile(mode='validator')
    for policy in (producer,validator):
        assert '(deny network*)' in policy and 'Library/Keychains' in policy and '/usr/bin/security' in policy
    path=m.ROOT/m.FILE_PLAN['ad_selection']['relative_path']
    assert str(path) in producer and str(path) not in validator
    for name in ('claim.json','report.json','dispatch-1.json','response-1.json'):
        assert str(path.parent/name) not in producer
    assert str(m.CONTROL/m.SPEC_NAME) in producer
    assert str(m.ROOT/'artifacts') in validator
    source=inspect.getsource(m)
    assert 'previous.run(' not in source and 'previous.observe(' not in source
    assert 'diagnostic.prepare(' not in source and 'NativePriceSourceDiagnostic(' not in source
    assert 'assistant.dispatch_fence' not in sys.modules


def test_real_selected_public_source_closure_matches_explicit_pins_without_refresh():
    pins=m.pins()
    assert len(pins)==181
    for name,pin in pins.items():
        assert m.sha((m.ROOT/name).read_bytes())==pin
    assert pins['scripts/inspect_arv2_r298_public_figi_lineage.py']==m.AD_CALLER_SHA256
    assert pins['scripts/arv2_r298_ad_source_binding.py']=='0f123b2a81718abbdb1c529f8ac8d974ac62ad45ab358cd99d825b1a5ae4eec2'
