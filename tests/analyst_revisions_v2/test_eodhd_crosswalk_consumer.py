"""Synthetic BB source/guard/publication boundaries; no production DATA."""
import copy
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace as NS

import pytest

from scripts import prepare_arv2_r298_eodhd_crosswalk as m


def args():return NS(operation='produce',expected_head='a'*40,caller_sha256='b'*64,profile_sha256='c'*64)


def fails(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def receipt(plan):
    return {'schema':m.guard_module.SCHEMA+'-receipt','profile_sha256':m.sha(m.canonical(m.guard_module.profile_record(plan))),
        'files':{role:{**item,'current_metadata_sha256':'a'*64,'current_security_sha256':'b'*64} for role,item in plan.items()},
        'fresh_current_security_authenticated':True,'fixed_bytes_authenticated':True,'requires_normal_return_before_use':True,
        'historical_continuity_proven':False,'continuous_integrity_proven':False}


def model():
    context=m.source_context();inventory=m.inventory_context(context)
    source={'AA':m.crosswalk.AA_PIN,'AC':m.crosswalk.AC_PIN,'AP_plan':m.crosswalk.AP_PIN,
        'genuine_binding_stream_sha256':m.crosswalk.prices.native.BINDING_STREAM_SHA256,'AW':inventory}
    roles={'Sharadar_RAW_full_window':5636,'pending_native_original_identity_source':5,
        'conditional_never_potential_empty_initial_holdings_required':510}
    summary={'schema':m.crosswalk.SCHEMA,'scope':'all_supplied_current_identifier_evidence_not_route_or_history_admission',
        'source_fingerprint':m.crosswalk.digest(source),'source_pins':source,'stock_count':6151,'fund_count':8,
        'original_proof_counts':{'pass':6151,'refused':0,'unavailable':0},'original_reporting_currency_not_usd_count':0,
        'original_token_count':6151,'qualified_current_token_count':6151,'union_token_count':6151,
        'distinct_source_owner_count':6159,'repeated_source_owner_binding_count':0,
        'disposition_counts':{'stocks':{'matched_current_crosswalk':5635,'unresolved':516},'funds':{'matched_current_crosswalk':8}},
        'reason_counts':{'stocks':{'no_identifier_match':516},'funds':{}},'AP_stock_role_counts':roles,
        'exact_FIGI_only_unresolved_count':0,'provider_row_counts':{'active':50668,'delisted':59979,'mapping':110346},
        'provider_duplicate_row_counts':{'active':0,'delisted':0,'mapping':0},'all_original_rows_retained':True,
        'all_supplied_provider_rows_indexed':True,**m.crosswalk.FALSE_FLAGS}
    stocks=[]
    for role,count in roles.items():
        for index in range(count):
            matched=role=='Sharadar_RAW_full_window' and index>0
            stocks.append({'AP_role':role,'potential':role!='conditional_never_potential_empty_initial_holdings_required',
                'status':'matched_current_crosswalk' if matched else 'unresolved','reason':None if matched else 'no_identifier_match'})
    record={'schema':m.crosswalk.PRIVATE_SCHEMA,'source_fingerprint':summary['source_fingerprint'],
        'stocks':stocks,'funds':[{'synthetic_fund_ordinal':i} for i in range(8)]}
    raw=m.canonical(record);summary['private_payload_pin']=m.pin(raw);m.crosswalk.validate_summary(summary)
    private=m.crosswalk.PrivateCrosswalk(raw,m.crosswalk.digest(summary))
    return context,summary,private


def output_result():
    context,summary,private=model()
    return {'schema':m.SCHEMA,'crosswalk_summary':summary,'stock_AP_role_potential_breakdown':m._breakdown(private,summary),
        'genuine_input_binding':context['genuine_input_binding'],'source_receipt':receipt(m.SOURCE_PLAN),
        'catalog_receipt':receipt(m.CATALOG_PLAN),'both_source_guards_normal_return':True,'genuine_input_unchanged':True,
        'private_pin':copy.deepcopy(summary['private_payload_pin']),'BA_fact_sha256':m.FACT_SHA256,'BA_authentication_sha256':m.AUTH_SHA256,
        'post_checks_complete':True,**m.FALSE_FLAGS}


def envelope(value):
    report=m.pin(m.canonical({**m.binding(args()),'result':value}))
    return m.canonical({'binding':m.binding(args()),'outcome':{'result':value,'report':report}})+bytes([10])


def test_public_actual_BA_report_reconstruction_and_fixed_groups_are_exact():
    context=m.source_context();assert context['BA_fact_sha256']==m.FACT_SHA256
    assert context['authentication']['mapping']['row_count']==110346
    assert context['authentication']['mapping']['ordered_records_sha256']=='9b49e14223906b5c0cd0e194265df23b5363146fa786e025f965dc2ac3c03ded'
    first,second=m.checked_groups();assert len(first)==3 and len(second)==5
    assert sum(item['byte_count'] for item in first.values())==39168001
    assert sum(item['byte_count'] for item in second.values())==27492064
    assert sum(item['byte_count'] for item in (*first.values(),*second.values()))==66660065
    assert all(m.sha((m.ROOT/name).read_bytes())==expected for name,expected in m.pins().items())
    assert m.sha(m.canonical(m.crosswalk.profile_record()))==m.CROSSWALK_PROFILE_SHA256


@pytest.mark.parametrize('role',('producer','validator','source_actual','provider_actual','authentication_actual'))
@pytest.mark.parametrize('bad',(False,True,2))
def test_external_actual_zero_is_structural_integer_not_bool_or_nonzero(monkeypatch,role,bad):
    fact=m.anchor.observed_fact();fact[role]['actual_exit']=bad
    # Fixture-only rebind removes the initial fixed-fact hash refusal so the
    # independent actual-type/zero predicates are exercised as well.
    monkeypatch.setattr(m.anchor,'observed_fact',lambda:fact)
    monkeypatch.setattr(m,'FACT_SHA256',m.sha(m.canonical(fact)))
    with pytest.raises((m.Refused,m.ba.Refused,m.ba.ap.Refused)):m.source_context()


@pytest.mark.parametrize('issue',('packet_hash','report','data_pin','count_bool','permission','summary'))
def test_prior_data_packets_counts_and_no_grant_are_not_silently_refreshed(monkeypatch,issue):
    fact=m.anchor.observed_fact()
    if issue=='packet_hash':fact['provider_actual']['stdout_sha256']='e'*64
    elif issue=='report':fact['report']['sha256']='f'*64
    elif issue=='data_pin':fact['data_plan']['capture']['sha256']='d'*64
    elif issue=='count_bool':fact['application_dispatch_intents']=True
    elif issue=='permission':fact['new_operation_or_read_granted']=True
    else:
        value=m.anchor.authentication_summary();value['mapping']['row_count']=110345
        monkeypatch.setattr(m.anchor,'authentication_summary',lambda:value)
    monkeypatch.setattr(m.anchor,'observed_fact',lambda:fact)
    with pytest.raises((m.Refused,m.ba.Refused)):m.source_context()


def test_summary_keeps_conditional_and_potential_unresolved_reasons_separate():
    _,summary,private=model();groups=m._breakdown(private,summary)
    by_role={group['AP_role']:group for group in groups}
    assert by_role['conditional_never_potential_empty_initial_holdings_required']['potential'] is False
    assert by_role['conditional_never_potential_empty_initial_holdings_required']['unresolved_reason_counts']=={'no_identifier_match':510}
    assert by_role['pending_native_original_identity_source']['unresolved_reason_counts']=={'no_identifier_match':5}
    assert by_role['Sharadar_RAW_full_window']['unresolved_reason_counts']=={'no_identifier_match':1}
    assert sum(group['stock_count'] for group in groups if group['potential'])==5641
    raw=m.canonical(groups);assert b'security_id' not in raw and b'ticker' not in raw and b'route' not in raw


@pytest.mark.parametrize('issue',('merge','bool','reason','role','count','duplicate'))
def test_grouped_reason_metadata_cannot_drop_or_reclassify_original_rows(issue):
    _,summary,private=model();groups=m._breakdown(private,summary)
    if issue=='merge':groups.pop()
    elif issue=='bool':groups[0]['potential']=1
    elif issue=='reason':groups[0]['unresolved_reason_counts']={'private_identifier':groups[0]['stock_count']}
    elif issue=='role':groups[0]['AP_role']='private_symbol_value'
    elif issue=='count':groups[0]['stock_count']-=1
    else:groups.append(copy.deepcopy(groups[0]))
    fails('output',lambda:m.validate_breakdown(groups,summary))


@pytest.mark.parametrize('issue',('actual','normal','genuine','private_pin','catalog_pin','source_pin','grant','result_bool'))
def test_external_success_requires_actual0_all_receipts_and_false_gates(issue):
    value=output_result();actual=0
    if issue=='actual':actual=2
    elif issue=='normal':value['both_source_guards_normal_return']=False
    elif issue=='genuine':value['genuine_input_unchanged']=False
    elif issue=='private_pin':value['private_pin']['sha256']='a'*64
    elif issue=='catalog_pin':value['catalog_receipt']['files']['capture']['sha256']='b'*64
    elif issue=='source_pin':value['source_receipt']['files']['aa']['sha256']='c'*64
    elif issue=='grant':value['source_or_price_admission_granted']=True
    else:value['result_cell']=False
    with pytest.raises((m.Refused,m.crosswalk.Refused,m.guard_module.Refused)):m.validate_output(envelope(value),actual,args())


def test_complete_metadata_success_roundtrips_with_one_real_LF_and_no_private_rows():
    value=output_result();raw=envelope(value);checked=m.validate_output(raw,0,args())
    assert checked['outcome']['result']==value and raw.count(bytes([10]))==1
    assert m.canonical(m.parse(raw[:-1]))+bytes([10])==raw
    assert b'synthetic_fund_ordinal' not in raw and b'"stocks":[' not in raw and b'"binding":{' not in m.canonical(value)
    fails('output',lambda:m.validate_output(raw[:-1]+bytes([92,110]),0,args()))


@pytest.mark.parametrize('mode',('produce','validate'))
def test_native_policy_has_exact_eight_DATA_and_fresh_package_only(mode):
    policy=m.native_profile(mode);assert '(deny network*)' in policy and '/Library/Keychains' in policy
    assert '(deny process-exec (literal "/usr/bin/security"))' in policy and 'remote tcp' not in policy
    for plan in (m.SOURCE_PLAN,m.CATALOG_PLAN):
        for row in plan.values():assert (row['relative_path'] in policy) is (mode=='produce')
    assert (str(m.worker.previous.PACKAGE) in policy) is (mode=='produce')
    assert (f'(require-not (literal "{m.CONTROL.parent}"))' in policy) is (mode=='produce')
    assert f'(require-not (subpath "{m.CONTROL.parent}"))' not in policy
    for forbidden in ('/report.json','/claim.json','R326-20261027-AY/','R326-20261027-AZ/'):
        assert forbidden not in policy


@pytest.fixture
def fake_guards(monkeypatch):
    context=m.source_context()
    source_plan=copy.deepcopy(m.SOURCE_PLAN);catalog_plan=copy.deepcopy(m.CATALOG_PLAN)
    source_values={role:('synthetic-'+role).encode() for role in source_plan}
    catalog_values={role:('synthetic-'+role).encode() for role in catalog_plan}
    for plan,values in ((source_plan,source_values),(catalog_plan,catalog_values)):
        for role,item in plan.items():item.update(m.pin(values[role]))
    monkeypatch.setattr(m,'SOURCE_PLAN',source_plan);monkeypatch.setattr(m,'CATALOG_PLAN',catalog_plan)
    monkeypatch.setattr(m,'source_context',lambda:copy.deepcopy(context))
    return source_values,catalog_values


@pytest.mark.parametrize('failure',(None,'source_read','catalog_read','source_pin','catalog_pin','genuine',
    'catalog_analysis','crosswalk','unchanged','source_return','catalog_return'))
def test_all_eight_hashes_and_both_live_guards_cover_genuine_catalog_and_crosswalk(monkeypatch,fake_guards,failure):
    source_values,catalog_values=fake_guards;events=[];active=set();context,summary,private=model()
    class Guard:
        def __init__(self,plan,*,deadline):self.plan=plan;self.name='source' if 'aa' in plan else 'catalog'
        def __enter__(self):active.add(self.name);events.append(self.name+'-enter');return self
        def __exit__(self,kind,*_):
            active.remove(self.name);events.append(self.name+'-normal' if kind is None else self.name+'-exception')
            if kind is None and failure==self.name+'_return':raise m.guard_module.Refused('named_changed')
        def read_all_once(self):
            events.append(self.name+'-all-whole-pins')
            if failure==self.name+'_read':raise m.guard_module.Refused('byte_pin')
            values=copy.deepcopy(source_values if self.name=='source' else catalog_values)
            if failure==self.name+'_pin':values[next(iter(values))]+=b'changed'
            return values
        def verify(self):assert active=={'source','catalog'}
        def receipt(self):return receipt(self.plan)
    monkeypatch.setattr(m.guard_module,'FixedDataGuard',Guard)
    def load(deadline):
        events.append('genuine-load');assert active=={'source','catalog'}
        assert 'source-all-whole-pins' in events and 'catalog-all-whole-pins' in events
        if failure=='genuine':raise m.Refused('genuine')
        return object()
    monkeypatch.setattr(m.worker,'_load_plain',load)
    monkeypatch.setattr(m.worker,'_catalog',lambda plain,deadline:('initial','record',{},[{}]*6151,context['genuine_input_binding']))
    monkeypatch.setattr(m,'_genuine',lambda *_:events.append('genuine-checked'))
    def catalog(values,c,deadline):
        events.append('pure-BA-analyse');assert active=={'source','catalog'}
        if failure=='catalog_analysis':raise m.Refused('catalog')
        return b'active',b'delisted',[]
    monkeypatch.setattr(m,'_catalog_data',catalog)
    def prepare(*values,**kwargs):
        events.append('crosswalk');assert active=={'source','catalog'}
        assert kwargs['expected_aw_inventory']==m.inventory_context(context)
        if failure=='crosswalk':raise m.Refused('catalog')
        return summary,private
    monkeypatch.setattr(m.crosswalk,'prepare',prepare)
    def unchanged(*_):
        events.append('genuine-unchanged');assert active=={'source','catalog'}
        if failure=='unchanged':raise m.Refused('genuine')
    monkeypatch.setattr(m.worker,'_catalog_unchanged',unchanged)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    if failure is None:
        result,raw=m.construct(context,time.monotonic()+100)
        assert result['both_source_guards_normal_return'] is True and raw==private._raw and not active
        assert events.index('genuine-unchanged')<events.index('catalog-normal')<events.index('source-normal')
    else:
        with pytest.raises((m.Refused,m.guard_module.Refused)):m.construct(context,time.monotonic()+100)
        assert not active
        if failure in ('source_read','catalog_read','source_pin','catalog_pin'):assert 'genuine-load' not in events


@pytest.fixture
def store_scope(monkeypatch,tmp_path):
    monkeypatch.setattr(m,'CONTROL',tmp_path/'parent'/'BB');monkeypatch.setattr(m,'_security',lambda fd:('synthetic',))
    def walk(path):
        chain=tuple((os.stat(Path(*path.parts[:i+1])).st_dev,os.stat(Path(*path.parts[:i+1])).st_ino) for i in range(1,len(path.parts)))
        return os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW),chain
    monkeypatch.setattr(m.admitted,'_storage_module',lambda:NS(_walk=walk));return m.CONTROL


def test_owned_private_publication_original_FDs_readback_exclusive_claim_and_no_overwrite(store_scope):
    with m.Store() as store:
        store.write('claim.json',b'{}',time.monotonic()+20)
        body=b'private-synthetic'*8192
        assert store.write(m.PRIVATE_NAME,body,time.monotonic()+20)==m.pin(body)
        store.verify();assert os.fstat(store.files[m.PRIVATE_NAME]['fd']).st_size==len(body)
        fails('output_bound',lambda:store.write(m.PRIVATE_NAME,body,time.monotonic()+20))
    fails('claim_spent',m.Store)


def test_private_serialized_bound_refuses_without_creating_file(store_scope,monkeypatch):
    monkeypatch.setattr(m,'MAX_PRIVATE',4)
    with m.Store() as store:
        store.write('claim.json',b'{}',time.monotonic()+20)
        fails('output_bound',lambda:store.write(m.PRIVATE_NAME,b'too-long',time.monotonic()+20))
        assert m.PRIVATE_NAME not in os.listdir(store.fd)


def test_claim_precedes_construct_and_private_write_follows_both_returns(store_scope,monkeypatch):
    value=output_result();events=[];private=b'private-synthetic-crosswalk'
    value['crosswalk_summary']['private_payload_pin']=m.pin(private)
    returned={key:value[key] for key in ('crosswalk_summary','stock_AP_role_potential_breakdown','genuine_input_binding',
        'source_receipt','catalog_receipt','both_source_guards_normal_return','genuine_input_unchanged')}
    def construct(*_):
        assert (store_scope/'claim.json').exists() and not (store_scope/m.PRIVATE_NAME).exists()
        events.extend(('both-guaranteed-returns','construct-return'));return returned,private
    monkeypatch.setattr(m,'construct',construct);monkeypatch.setattr(m,'preflight',lambda *_:None)
    monkeypatch.setattr(m.environment,'require_safe_environment',lambda:None)
    result=m.run(args(),time.monotonic()+100)
    assert 'result' in result and (store_scope/m.PRIVATE_NAME).read_bytes()==private
    assert result['result']['private_pin']==m.pin(private)


def test_pure_BA_analyse_is_required_before_full111_page_extraction(monkeypatch):
    context=m.source_context();events=[];source=context['source'];auth={'synthetic_authenticated':True}
    monkeypatch.setattr(m,'AUTH_SHA256',m.sha(m.canonical(auth)));context['authentication']=auth
    values={'seed':b'seed','capture':b''.join(b'\x00'*8+b'x' for _ in range(110)),'index':b'index','journal':b'journal',
        'source_metadata':m.canonical(source['observation'])}
    def analyse(*_):events.append('full-BA-analysis');return auth
    monkeypatch.setattr(m.ba,'analyse',analyse);monkeypatch.setattr(m.ba,'_seed_bodies',lambda _: (b'active',b'delisted',b'first-page'))
    index={'bodies':[{'offset':i*9,'body':m.pin(b'x')} for i in range(110)]}
    monkeypatch.setattr(m.ba,'_decode',lambda *_:index)
    def page(body,offset):
        assert events and events[0]=='full-BA-analysis';events.append(offset)
        return [{'synthetic_mapping':True}]*(346 if offset==110000 else 1000)
    monkeypatch.setattr(m.ba,'_mapping_envelope',page)
    active,delisted,mapping=m._catalog_data(values,context,time.monotonic()+100)
    assert active==b'active' and delisted==b'delisted' and len(mapping)==110346
    assert events[1:]==list(range(0,110001,1000))


def test_no_old_operational_callbacks_or_unfenced_shared_suite():
    import ast
    import inspect
    source=inspect.getsource(m)
    for forbidden in ('ba.run(','ba.main(','ba.provider_observation(','keychain','load_key('):assert forbidden not in source
    assert all(not (isinstance(node,ast.Import) and any(alias.name=='requests' or alias.name.startswith('requests.') for alias in node.names))
        and not (isinstance(node,ast.ImportFrom) and node.module is not None and (node.module=='requests' or node.module.startswith('requests.')))
        for node in ast.walk(ast.parse(source)))
    code=inspect.getsource(m.construct)
    assert code.index('catalog_guard.read_all_once()')<code.index('worker._load_plain(')
    assert code.index('_breakdown(')<code.index('worker._catalog_unchanged(')
    assert 'both_source_guards_normal_return' in code
