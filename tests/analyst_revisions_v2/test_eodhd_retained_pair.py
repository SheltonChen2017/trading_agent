"""Synthetic AX pair authentication; no retained AU DATA or operation replay."""
import copy
import json
import time
from types import SimpleNamespace as NS

import pytest

from scripts import read_arv2_r298_eodhd_retained_pair as m


def bodies():
    metadata=[{'Code':'SPY','Name':'Synthetic \u00ae fund','Country':'USA','Exchange':'NYSE ARCA',
        'Currency':'USD','Type':'ETF','Isin':'US78462F1030'}]
    history=[{'date':day,'open':300,'high':302,'low':299,'close':300.125,'adjusted_close':275.5,'volume':100}
        for day in m.au.DATES]
    return json.dumps(metadata,ensure_ascii=False).encode(),json.dumps(history).encode()


def args():return NS(expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def fails(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def receipt(plan):
    return {'schema':m.guard_module.SCHEMA+'-receipt',
        'profile_sha256':m.sha(m.canonical(m.guard_module.profile_record(plan))),
        'files':{role:{**pin,'current_metadata_sha256':'a'*64,'current_security_sha256':'b'*64} for role,pin in plan.items()},
        'fresh_current_security_authenticated':True,'fixed_bytes_authenticated':True,'requires_normal_return_before_use':True,
        'historical_continuity_proven':False,'continuous_integrity_proven':False}


@pytest.fixture
def supplied(monkeypatch):
    raw=bodies();plan=copy.deepcopy(m.DATA_PLAN)
    for role,body in zip(('au_metadata','au_history'),raw,strict=True):plan[role].update(m.pin(body))
    monkeypatch.setattr(m,'DATA_PLAN',plan)
    observation=m.catalog.authenticate_retained_spy(*raw)
    result={'schema':m.SCHEMA+'-result','observation':observation,'source_guard_receipt':receipt(plan),
        'source_guard_normal_return':True,'source_context_sha256':m.sha(m.canonical(m.source_context())),
        'retained_pair_authenticated':True,**m.FALSE_FLAGS}
    return raw,plan,result


def envelope(result):return m.canonical({'binding':m.binding(args()),'result':result})+b'\n'


def test_exact205_pins_two_data_only_and_historical_actual_exits_preserved():
    assert len(m.pins())==205
    assert all(m.sha((m.ROOT/name).read_bytes())==expected for name,expected in m.pins().items())
    assert set(m.DATA_PLAN)=={'au_metadata','au_history'}
    assert m.DATA_PLAN['au_metadata']['byte_count']==170 and m.DATA_PLAN['au_history']['byte_count']==729
    assert m.DATA_PLAN['au_history']['sha256']=='c55a32ca410d5b34ba7601715013b3b93b302d43d2eb7a87fde383d80d40c02d'
    context=m.source_context();assert context['AU']['parent_actual_exit']==2
    assert context['AU']['native_validator_actual_exit']==context['AV']['parent_actual_exit']==context['AV']['native_validator_actual_exit']==0
    assert context['AV']['Unicode_category_C_freedom_not_proven_by_AV'] is True
    assert m.profile_record()['no_provider_or_AU_AV_reader_or_worker_replay'] is True


def test_supplied_unicode_pair_requires_actual0_and_emits_only_qualified_metadata(supplied):
    raw,_,result=supplied;output=envelope(result)
    assert output.endswith(bytes([10])) and output.count(bytes([10]))==1
    assert m.canonical(m.au.parse(output[:-1]))+bytes([10])==output
    assert m.validate_output(output,0,args())['result']==result
    assert result['observation']['identity_matched'] is result['observation']['expected_date_coverage'] is True
    assert result['observation']['positive_RAW_close_count']==6
    for value in (b'Synthetic',b'\\u00ae',b'300.125',b'275.5',b'US78462F1030'):assert value not in output
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    fails('output',lambda:m.validate_output(output,2,args()))
    fails('output',lambda:m.validate_output(output,False,args()))
    fails('output',lambda:m.validate_output(output[:-1]+bytes([92,110]),0,args()))


@pytest.mark.parametrize('change',('metadata_pin','history_pin','swapped','subset','normal_return','source_context',
    'count','identity','coverage','grant','guard_pin'))
def test_external_output_cannot_mix_subset_pins_skip_predicates_or_clear_gates(supplied,change):
    _,_,result=supplied
    if change=='metadata_pin':result['observation']['body_pins'][0]['sha256']='c'*64
    elif change=='history_pin':result['observation']['body_pins'][1]['sha256']='d'*64
    elif change=='swapped':result['observation']['body_pins'].reverse()
    elif change=='subset':result['observation']['body_pins'].pop()
    elif change=='normal_return':result['source_guard_normal_return']=False
    elif change=='source_context':result['source_context_sha256']='e'*64
    elif change=='count':result['observation']['positive_RAW_close_count']=5
    elif change=='identity':result['observation'].update(identity_matched=False,identity_status='unresolved')
    elif change=='coverage':result['observation']['expected_date_coverage']=False
    elif change=='grant':result['strategy_price_input_admitted']=True
    else:result['source_guard_receipt']['files']['au_history']['sha256']='f'*64
    with pytest.raises((m.Refused,m.catalog.Refused,m.guard_module.Refused)):m.validate_output(envelope(result),0,args())


def test_failure_is_finite_allocation_unknown_and_never_accepted_zero():
    value=m.failure(args(),m.Refused('authentication'));output=m.canonical(value)+b'\n'
    assert m.validate_output(output,2,args())==value
    assert value['allocation_unknown'] is True and value['old_operation_replayed'] is False
    fails('output',lambda:m.validate_output(output,0,args()))


def test_native_policy_whitelists_exact_two_DATA_leaves_and_only_own_output_subtree():
    policy=m.native_profile();assert '(deny network*)' in policy and '/Library/Keychains' in policy
    assert '(deny process-exec (literal "/usr/bin/security"))' in policy
    assert 'remote tcp' not in policy
    for row in m.DATA_PLAN.values():assert row['relative_path'] in policy
    assert f'(require-not (literal "{m.CONTROL.parent}"))' in policy
    assert f'(require-not (subpath "{m.CONTROL.parent}"))' not in policy
    for forbidden in ('requests.jsonl','report.json','claim.json','R326-20261027-AR/',str(m.au.ar.worker.previous.PACKAGE)):
        assert forbidden not in policy


@pytest.mark.parametrize('boundary',(None,'read','metadata_pin','history_pin','guard_return','postflight','store_return'))
def test_both_whole_pins_before_authentication_and_normal_return_before_success(monkeypatch,supplied,boundary):
    raw,plan,_=supplied;events=[];writes=[]
    class Store:
        def __enter__(self):return self
        def __exit__(self,*_):
            events.append('store-return')
            if boundary=='store_return':raise m.Refused('output_changed')
        def write(self,name,raw):events.append(name);writes.append((name,raw))
        def verify(self):events.append('store-check')
    class Guard:
        def __init__(self,p,*,deadline):assert p==plan
        def __enter__(self):events.append('guard-enter');return self
        def __exit__(self,kind,*_):
            events.append('guard-normal' if kind is None else 'guard-exception')
            if boundary=='guard_return' and kind is None:raise m.guard_module.Refused('named_changed')
        def read_all_once(self):
            events.append('authenticated-read')
            if boundary=='read':raise m.guard_module.Refused('byte_pin')
            values=dict(zip(('au_metadata','au_history'),raw,strict=True))
            if boundary in ('metadata_pin','history_pin'):values['au_metadata' if boundary=='metadata_pin' else 'au_history']+=b' '
            return values
        def verify(self):events.append('guard-check')
        def receipt(self):return receipt(plan)
    monkeypatch.setattr(m,'Store',Store);monkeypatch.setattr(m.guard_module,'FixedDataGuard',Guard)
    original=m.catalog.authenticate_retained_spy
    def authenticate(*values):events.append('authenticate');return original(*values)
    monkeypatch.setattr(m.catalog,'authenticate_retained_spy',authenticate)
    def preflight(*_):
        events.append('postflight')
        if boundary=='postflight':raise m.Refused('source_pin')
    monkeypatch.setattr(m,'preflight',preflight);monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    if boundary=='store_return':
        fails('output_changed',lambda:m.run(args(),time.monotonic()+20));return
    output=m.run(args(),time.monotonic()+20)
    assert output.endswith(bytes([10])) and output.count(bytes([10]))==1
    value=m.au.parse(output[:-1]);assert m.canonical(value)+bytes([10])==output
    assert ('result' in value) is (boundary is None)
    assert events.index('claim.json')<events.index('authenticated-read')
    assert writes[-1][0]=='result-metadata.json'
    if boundary in ('read','metadata_pin','history_pin'):assert 'authenticate' not in events
    if boundary is None:
        assert events.index('guard-normal')<events.index('postflight')<events.index('result-metadata.json')<events.index('store-return')
        m.validate_output(output,0,args())
    else:m.validate_output(output,2,args())


@pytest.mark.parametrize('field,bad',(('Code','OTHER'),('Type','FUND'),('Currency','CAD'),('Isin',None),('Name','Unsafe\u200b')))
def test_exact_identity_and_Unicode_safety_refuse_without_any_network_or_fallback(monkeypatch,supplied,field,bad):
    raw,plan,_=supplied;metadata=json.loads(raw[0]);metadata[0][field]=bad;changed=json.dumps(metadata).encode()
    raw=(changed,raw[1]);plan['au_metadata'].update(m.pin(changed))
    monkeypatch.setattr(m,'DATA_PLAN',plan)
    class Store:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def write(self,*_):pass
        def verify(self):pass
    class Guard:
        def __init__(self,*_,**__):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def read_all_once(self):return dict(zip(('au_metadata','au_history'),raw,strict=True))
        def verify(self):pass
        def receipt(self):return receipt(plan)
    monkeypatch.setattr(m,'Store',Store);monkeypatch.setattr(m.guard_module,'FixedDataGuard',Guard)
    monkeypatch.setattr(m,'preflight',lambda *_:None);monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    value=m.au.parse(m.run(args(),time.monotonic()+20)[:-1])
    assert value['failure_code']=='authentication' and 'result' not in value


def test_no_old_operation_calls_or_source_mutation_and_exact_host_preflight():
    import inspect
    source=inspect.getsource(m)
    for forbidden in ('au.run(','au.main(','load_key(','requests.','av.run(','av.main('):assert forbidden not in source
    code=inspect.getsource(m.preflight)
    for expected in ("sys.platform=='darwin'",'(3,13)','Path(sys.executable)==PYTHON',"['status','--porcelain']",'cat-file','args.profile_sha256'):
        assert expected in code
