"""Supplied synthetic bytes only: no production DATA, prices, USB or QC."""
import ast
import copy
from datetime import date, timedelta
from functools import lru_cache
import inspect
import json
import sys
import time
from types import SimpleNamespace

import pytest

from scripts import arv2_r337_quarantine_preparation as m
from research.analyst_revisions_v2_qc import accepted_risk_preliminary_qc_figi as figi


def refused(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def binding(index):
    token='BBG'+str(index).zfill(9)
    return figi.build_preliminary_qc_figi_binding(
        security_id='sharadar-composite-figi-'+token,issuer_id=f'synthetic-issuer-{index}',
        composite_figi=token,listing_id=f'synthetic-listing-{index}',
        diagnostic_current_ticker=f'SYNTH{index}',diagnostic_exchange_mic='XNYS',
        candidate_first_session='2020-12-31',candidate_last_session='2026-10-13',
        source_snapshot_available_at='2026-10-01T00:00:00.000000Z',
        source_row_sha256=m.sha(f'source-{index}'.encode()),identity_evidence_sha256=m.sha(f'evidence-{index}'.encode()),
        security_master_admission_sha256=m.policy.ADMISSION_SHA256,
        admitted_mapping_inventory_sha256='b'*64,admitted_mapping_count=6151)


def sample_weekdays(first,last,count):
    current=date.fromisoformat(first);last=date.fromisoformat(last);days=[]
    while current<=last:
        if current.weekday()<5:days.append(current.isoformat())
        current+=timedelta(days=1)
    assert len(days)>=count
    return [days[i*(len(days)-1)//(count-1)] for i in range(count)]


def encode(header,payload):
    raw=m.canonical(header)
    return m.MAGIC+len(raw).to_bytes(8,'big')+raw+payload


@lru_cache(maxsize=1)
def synthetic_source():
    rows=tuple(binding(i) for i in range(5));whole=tuple(m.sha(m.canonical(row)) for row in rows)
    n={'schema':'arv2-r336-retained-action-semantics-v1-private','cases':[]}
    for ordinal,(row,pin) in enumerate(zip(rows,whole)):
        f={'whole_binding_sha256':pin,'binding':row}
        i={'whole_binding_sha256':pin,'original_F_case':f}
        original={'whole_binding_sha256':pin,'binding':row}
        n['cases'].append({'case_ordinal':ordinal,'whole_binding_sha256':pin,
            'identity_admitted':False,'original_M_case':original,'original_I_case':i})
    sessions=sample_weekdays('2020-12-31','2021-10-28',209)+sample_weekdays('2021-10-29','2026-10-13',1243)
    assert sessions[209:211]==['2021-10-29','2021-11-01']
    f=m.fmt
    months=f.months(sessions)
    assignments=[]
    for ordinal in range(f.STOCK_COUNT):
        if ordinal<5:
            row=rows[ordinal];role=f.NATIVE;sid=row['security_id'];pin=whole[ordinal];semantic=row['row_sha256']
        else:
            role=f.VENDOR if ordinal<5+f.VENDOR_COUNT else f.CONDITIONAL
            sid=f'SYNTHETIC-SECURITY-{ordinal:05d}';pin=m.sha(f'whole-{ordinal}'.encode());semantic=m.sha(f'semantic-{ordinal}'.encode())
        assignments.append({'binding_ordinal':ordinal,'security_id':sid,'whole_binding_sha256':pin,
            'semantic_binding_sha256':semantic,'role':role,'table':'stocks' if role==f.VENDOR else None,
            'ticker':f'STK{ordinal}' if role==f.VENDOR else None,'refusal_reason':None if role==f.VENDOR else 'synthetic-refusal'})
    for ordinal,ticker in enumerate(f.OWN_FUNDS):
        assignments.append({'fund_ordinal':ordinal,'own_ETF':ticker,'role':f.VENDOR,
            'table':'funds','ticker':ticker,'route_sha256':m.sha(f'fund-{ordinal}'.encode())})
    catalog={'schema':f.SCHEMA+'-catalog','AP_fact_sha256':f.AP_FACT_SHA256,'AP_source_sha256':f.AP_SOURCE_SHA256,
        'AP_authentication_sha256':f.AP_AUTH_SHA256,'source_data_pins':copy.deepcopy(f.AP_DATA_PINS),
        'binding_stream_sha256':f.BINDING_SHA256,'full_axis_sha256':f.FULL_AXIS_SHA256,
        'price_sessions':sessions,'assignments':assignments,
        'vendor_slots':[index for index,row in enumerate(assignments) if row['role']==f.VENDOR],
        'months':months,**f.FALSE_FLAGS}
    catalog_raw=f.canonical(catalog)
    assert f.validate_catalog(catalog)==catalog
    parts={'catalog':catalog_raw}
    shard_summaries=[];remaining_valid=f.OBSERVED_ROWS
    for ordinal,month in enumerate(months):
        raw=f'OPAQUE SYNTHETIC MONTH {ordinal:03d}: never a price row'.encode()
        parts[f'month_{ordinal:03d}']=raw
        count=(f.VENDOR_COUNT+f.FUND_COUNT)*len(month['session_indexes'])
        valid=min(count,remaining_valid);remaining_valid-=valid
        shard_summaries.append({**month,'row_count':count,'valid_count':valid,'absent_count':count-valid,**f.pin(raw)})
    assert remaining_valid==0
    manifest={'schema':f.SCHEMA+'-manifest','catalog_pin':f.pin(catalog_raw),
        'AP_fact_sha256':f.AP_FACT_SHA256,'AP_authentication_sha256':f.AP_AUTH_SHA256,
        'binding_stream_sha256':f.BINDING_SHA256,'full_axis_sha256':f.FULL_AXIS_SHA256,
        'assignment_count':f.STOCK_COUNT+f.FUND_COUNT,'vendor_slot_count':f.VENDOR_COUNT+f.FUND_COUNT,
        'session_count':f.SESSION_COUNT,'months':shard_summaries,
        'row_count':sum(row['row_count'] for row in shard_summaries),
        'valid_count':sum(row['valid_count'] for row in shard_summaries),
        'absent_count':sum(row['absent_count'] for row in shard_summaries),
        'total_shard_bytes':sum(row['byte_count'] for row in shard_summaries),**f.FALSE_FLAGS}
    assert f.validate_manifest(manifest)==manifest
    parts['manifest']=f.canonical(manifest)
    return rows,whole,n,catalog,manifest,parts


def pack_parts(parts):
    payload=b''.join(parts[role] for role in m.ROLES)
    offset=0;entries=[]
    for ordinal,role in enumerate(m.ROLES):
        raw=parts[role]
        entries.append({'ordinal':ordinal,'role':role,'offset':offset,**m.pin(raw)})
        offset+=len(raw)
    header={'schema':m.ARCHIVE_SCHEMA,'data_plan_sha256':m.PLAN_SHA256,'source_fact_sha256':m.FACT_SHA256,
        'source_output_sha256':m.OUTPUT_SHA256,'entries':entries,'range_count':len(entries),
        'payload_byte_count':len(payload),**{key:False for key in m.HEADER_FLAGS}}
    return header,payload,encode(header,payload)


@pytest.fixture
def case(monkeypatch):
    rows,whole,n,catalog,manifest,parts=synthetic_source()
    n_raw=m.canonical(n);header,payload,raw=pack_parts(parts)
    monkeypatch.setattr(m.policy,'QUARANTINED_WHOLE_BINDING_SHA256S',whole)
    monkeypatch.setattr(m,'N_PIN',m.pin(n_raw));monkeypatch.setattr(m,'ARCHIVE_PIN',m.pin(raw))
    return SimpleNamespace(rows=rows,whole=whole,n=copy.deepcopy(n),n_raw=n_raw,
        catalog=copy.deepcopy(catalog),manifest=copy.deepcopy(manifest),parts=dict(parts),
        header=copy.deepcopy(header),payload=payload,raw=raw)


def deadline():return time.monotonic()+299

def rebind(monkeypatch,header,payload):
    raw=encode(header,payload);monkeypatch.setattr(m,'ARCHIVE_PIN',m.pin(raw));return raw


def test_full_6159_census_and_all73_ranges_preserved_without_price_parse(case,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('individual price shard parsed')
    monkeypatch.setattr(m.fmt,'validate_shard',forbidden)
    summary,catalog,private=m.prepare(case.n_raw,case.raw,deadline=deadline())
    assert summary==m.validate_summary(summary)
    assert summary['stock_assignment_count']==6151 and summary['fund_assignment_count']==8
    assert summary['unchanged_vendor_stock_count']==5636 and summary['unchanged_conditional_count']==510
    assert summary['quarantine_source_index_join_count']==5 and summary['all_range_count']==73
    assert summary['reference_and_valuation_session_count']==1243
    assert all(summary[key] is False for key in m.FALSE_FLAGS)
    assert set(private['archive_range_descriptors'])==set(m.ROLES)
    assert private['inspection']==summary
    assert len(catalog['quarantined_bindings'])==5
    assert [item['original_binding'] for item in private['source_index_joins']]==list(case.rows)
    assert all(item['source_index_assignment']['role']==m.fmt.NATIVE for item in private['source_index_joins'])
    assert 'price_rows' not in private and 'prices' not in private
    assert 'assistant.dispatch_fence' not in sys.modules


def test_N_pin_checked_before_any_JSON_interpretation(case,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('unpinned N bytes parsed')
    monkeypatch.setattr(m,'loads',forbidden)
    refused('input_pin',lambda:m.extract_catalog(case.n_raw+b' '))


def test_archive_pin_checked_before_header_or_catalog_parse(case,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('unpinned archive parsed')
    monkeypatch.setattr(m,'loads',forbidden)
    refused('input_pin',lambda:m.parse_archive(case.raw+b' ',deadline=deadline()))


def test_all_ranges_authenticate_before_any_vendor_parse(case,monkeypatch):
    raw=bytearray(case.raw);raw[-1]^=1;raw=bytes(raw)
    monkeypatch.setattr(m,'ARCHIVE_PIN',m.pin(raw))
    calls=[]
    def forbidden(*args,**kwargs):calls.append(True);raise AssertionError('vendor parsed before last range authentication')
    monkeypatch.setattr(m.fmt,'loads',forbidden)
    refused('range_hash',lambda:m.parse_archive(raw,deadline=deadline()))
    assert calls==[]


@pytest.mark.parametrize('fault',['order','bool_ordinal','whole','identity_flag','M_whole','I_whole','F_whole','F_binding','missing_case','schema'])
def test_N_case_original_provenance_links_exact(case,monkeypatch,fault):
    n=case.n;row=n['cases'][0]
    if fault=='order':n['cases'].reverse()
    elif fault=='bool_ordinal':row['case_ordinal']=False
    elif fault=='whole':row['whole_binding_sha256']='f'*64
    elif fault=='identity_flag':row['identity_admitted']=True
    elif fault=='M_whole':row['original_M_case']['whole_binding_sha256']='f'*64
    elif fault=='I_whole':row['original_I_case']['whole_binding_sha256']='f'*64
    elif fault=='F_whole':row['original_I_case']['original_F_case']['whole_binding_sha256']='f'*64
    elif fault=='F_binding':row['original_I_case']['original_F_case']['binding']={'security_id':'FORGED'}
    elif fault=='missing_case':n['cases'].pop()
    else:n['schema']='OTHER'
    raw=m.canonical(n);monkeypatch.setattr(m,'N_PIN',m.pin(raw))
    with pytest.raises(m.Refused):m.extract_catalog(raw)


@pytest.mark.parametrize('fault',['magic','header_zero','header_oversize','header_truncated','duplicate_key','schema','flag','bool_range_count','negative_payload','payload_count','extra_key'])
def test_archive_header_finite_closed_and_canonical(case,monkeypatch,fault):
    h=case.header;payload=case.payload
    if fault=='magic':raw=b'X'+case.raw[1:]
    elif fault=='header_zero':raw=m.MAGIC+(0).to_bytes(8,'big')+payload
    elif fault=='header_oversize':raw=m.MAGIC+(65537).to_bytes(8,'big')+payload
    elif fault=='header_truncated':raw=m.MAGIC+(100).to_bytes(8,'big')+b'{}'
    elif fault=='duplicate_key':
        raw_header=m.canonical(h).replace(b'{',b'{"schema":"DUPLICATE",',1)
        raw=m.MAGIC+len(raw_header).to_bytes(8,'big')+raw_header+payload
    else:
        if fault=='schema':h['schema']='OTHER'
        elif fault=='flag':h[m.HEADER_FLAGS[0]]=0
        elif fault=='bool_range_count':h['range_count']=True
        elif fault=='negative_payload':h['payload_byte_count']=-1
        elif fault=='payload_count':h['payload_byte_count']+=1
        else:h['extra']='SHOULD-NOT-ESCAPE'
        raw=encode(h,payload)
    monkeypatch.setattr(m,'ARCHIVE_PIN',m.pin(raw))
    with pytest.raises(m.Refused):m.parse_archive(raw,deadline=deadline())


@pytest.mark.parametrize('fault',['offset_gap','overlap','order','wrong_role','bool_ordinal','negative_count','bool_count','range_oversize','range_hash','extra_row_key','trailing_bytes'])
def test_archive_range_geometry_and_every_pin_required(case,monkeypatch,fault):
    h=case.header;payload=case.payload;row=h['entries'][5]
    if fault=='offset_gap':row['offset']+=1
    elif fault=='overlap':row['offset']-=1
    elif fault=='order':h['entries'][4:6]=reversed(h['entries'][4:6])
    elif fault=='wrong_role':row['role']='month_099'
    elif fault=='bool_ordinal':row['ordinal']=True
    elif fault=='negative_count':row['byte_count']=-1
    elif fault=='bool_count':row['byte_count']=True
    elif fault=='range_oversize':row['byte_count']=m.fmt.MAX_MONTH_BYTES+1
    elif fault=='range_hash':row['sha256']='f'*64
    elif fault=='extra_row_key':row['private']='NOT-ALLOWED'
    else:payload+=b'EXTRA';h['payload_byte_count']=len(payload)
    raw=rebind(monkeypatch,h,payload)
    with pytest.raises(m.Refused):m.parse_archive(raw,deadline=deadline())


def changed_catalog_archive(case,monkeypatch,catalog):
    parts=case.parts;parts['catalog']=m.fmt.canonical(catalog)
    manifest=case.manifest;manifest['catalog_pin']=m.fmt.pin(parts['catalog'])
    parts['manifest']=m.fmt.canonical(manifest)
    _,_,raw=pack_parts(parts);monkeypatch.setattr(m,'ARCHIVE_PIN',m.pin(raw));return raw


@pytest.mark.parametrize('fault',['native_id','native_semantic','native_whole','native_count','duplicate_whole','conditional_count','vendor_role','fund_role'])
def test_exact_five_source_index_native_joins_and_all_other_roles(case,monkeypatch,fault):
    catalog=case.catalog;row=catalog['assignments'][0]
    if fault=='native_id':row['security_id']='SYNTHETIC-FORGED-ID'
    elif fault=='native_semantic':row['semantic_binding_sha256']='f'*64
    elif fault=='native_whole':row['whole_binding_sha256']='f'*64
    elif fault=='native_count':row['role']=m.fmt.CONDITIONAL
    elif fault=='duplicate_whole':catalog['assignments'][1]['whole_binding_sha256']=row['whole_binding_sha256']
    elif fault=='conditional_count':catalog['assignments'][-9]['role']=m.fmt.NATIVE
    elif fault=='vendor_role':catalog['assignments'][6]['role']=m.fmt.NATIVE
    else:catalog['assignments'][-1]['role']=m.fmt.NATIVE
    raw=changed_catalog_archive(case,monkeypatch,catalog)
    with pytest.raises(m.Refused):m.prepare(case.n_raw,raw,deadline=deadline())


@pytest.mark.parametrize('fault',['catalog_pin','shard_pin','negative_count','bool_count','missing_month','month_geometry','false_flag'])
def test_manifest_crosschecks_and_counts_never_assumed_from_archive(case,monkeypatch,fault):
    manifest=case.manifest
    if fault=='catalog_pin':manifest['catalog_pin']['sha256']='f'*64
    elif fault=='shard_pin':manifest['months'][5]['sha256']='f'*64
    elif fault=='negative_count':manifest['valid_count']=-1
    elif fault=='bool_count':manifest['months'][0]['valid_count']=True
    elif fault=='missing_month':manifest['months'].pop()
    elif fault=='month_geometry':manifest['months'][0]['session_indexes']=[0,1]
    else:manifest['point_in_time_proven']=True
    parts=case.parts;parts['manifest']=m.fmt.canonical(manifest)
    _,_,raw=pack_parts(parts);monkeypatch.setattr(m,'ARCHIVE_PIN',m.pin(raw))
    with pytest.raises(m.Refused):m.parse_archive(raw,deadline=deadline())


@pytest.mark.parametrize('bad',[None,True,-1,float('inf'),float('nan')])
def test_deadline_types_are_finite_before_any_input_parse(case,monkeypatch,bad):
    def forbidden(*args,**kwargs):raise AssertionError('invalid deadline parsed source')
    monkeypatch.setattr(m,'extract_catalog',forbidden)
    refused('deadline',lambda:m.prepare(case.n_raw,case.raw,deadline=bad))


def test_deadline_expires_after_authentication_before_success(case,monkeypatch):
    original=m.parse_archive;state={'expired':False}
    def parse(*args,**kwargs):
        result=original(*args,**kwargs);state['expired']=True;return result
    monkeypatch.setattr(m,'parse_archive',parse)
    original_budget=m.budget
    def budget(value):
        if state['expired']:raise m.Refused('deadline')
        original_budget(value)
    monkeypatch.setattr(m,'budget',budget)
    refused('deadline',lambda:m.prepare(case.n_raw,case.raw,deadline=deadline()))


def test_summary_is_closed_exact_counts_and_false_flags(case):
    summary,_,_=m.prepare(case.n_raw,case.raw,deadline=deadline())
    for key,value in [('stock_assignment_count',6150),('quarantine_source_index_join_count',True),
        ('new_launch_attempt_granted',True),('source_catalog_and_manifest_authenticated',1)]:
        changed=copy.deepcopy(summary);changed[key]=value
        refused('output',lambda:m.validate_summary(changed))
    summary['unrecognized_private_label']='NOT-ALLOWED'
    refused('output',lambda:m.validate_summary(summary))


def test_pure_helper_import_and_call_boundary_no_operational_API():
    source=inspect.getsource(m);tree=ast.parse(source)
    imported={node.names[0].name for node in ast.walk(tree) if isinstance(node,ast.Import)}
    assert imported<={'hashlib','json','math','re','time'}
    assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
        and node.func.id in ('open','exec','eval','compile','__import__') for node in ast.walk(tree))
    assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
        and node.func.attr in ('read_bytes','read_text','write_bytes','write_text','validate_shard','price')
        for node in ast.walk(tree))
