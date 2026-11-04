"""Real pure parsers over synthetic bound bytes, never private DATA or QC."""
import ast
import copy
import hashlib
import inspect
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r338_quarantine_coverage as m

SYNTHETIC_NONCE='1234abcd'*8

def refused(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def binding(index):
    f=m.targets.figi;token='BBG'+str(index).zfill(9)
    return f.build_preliminary_qc_figi_binding(security_id='sharadar-composite-figi-'+token,
        issuer_id=f'SYNTHETIC-ISSUER-{index}',composite_figi=token,listing_id=f'SYNTHETIC-LISTING-{index}',
        diagnostic_current_ticker=f'SYNTH{index}',diagnostic_exchange_mic='XNYS',
        candidate_first_session='2013-01-02',candidate_last_session='2026-10-13',
        source_snapshot_available_at='2026-10-01T00:00:00.000000Z',
        source_row_sha256=m.digest({'source':index}),identity_evidence_sha256=m.digest({'evidence':index}),
        security_master_admission_sha256=m.targets.ADMISSION_SHA256,
        admitted_mapping_inventory_sha256='b'*64,admitted_mapping_count=8)


def package_binding(axis,rows,manifest):
    return {'schema':'arv2-r298-all-route-worker-v1-input','source_package_sha256':'a'*64,
        'source_lineage_sha256':'c'*64,'plain_package_sha256':'d'*64,'activation_manifest_sha256':'e'*64,
        'parent_proof_sha256':'f'*64,'upload_inventory_sha256':'1'*64,
        'evaluator_manifest_sha256':manifest['manifest_sha256'],'session_axis_count':len(axis),
        'session_axis_sha256':manifest['session_axis_sha256'],'ordered_session_values_sha256':m.digest(list(axis)),
        'first_session':axis[0],'last_session':axis[-1],'binding_contract':{'binding_count':len(rows),
        'binding_stream_sha256':m.fmt.BINDING_SHA256,'security_master_admission_sha256':m.targets.ADMISSION_SHA256,
        'admitted_mapping_inventory_sha256':'b'*64}}


def archive_bytes(parts):
    a=m.archive;roles=('catalog',*(f'month_{i:03d}' for i in range(m.fmt.MONTH_COUNT)),'manifest')
    entries=[];payload=bytearray()
    for ordinal,role in enumerate(roles):
        raw=parts[role];entries.append({'ordinal':ordinal,'role':role,'offset':len(payload),**m.pin(raw)});payload.extend(raw)
    header={'schema':a.ARCHIVE_SCHEMA,'data_plan_sha256':a.PLAN_SHA256,'source_fact_sha256':a.FACT_SHA256,
        'source_output_sha256':a.OUTPUT_SHA256,'entries':entries,'range_count':len(entries),
        'payload_byte_count':len(payload),**{key:False for key in a.HEADER_FLAGS}}
    raw=m.canonical(header)
    return a.MAGIC+len(raw).to_bytes(8,'big')+raw+bytes(payload)


def rebuild_archive(case,monkeypatch,*,nulls=None,invalid=None,catalog_change=None,manifest_change=None):
    f=m.fmt;catalog=copy.deepcopy(case.vendor)
    if catalog_change:catalog_change(catalog)
    catalog_raw=f.canonical(catalog)
    parts={'catalog':catalog_raw};summaries=[]
    for month in catalog['months']:
        values=[];valid=0
        for slot in catalog['vendor_slots']:
            for index in month['session_indexes']:
                value=None if (slot,index) in (case.nulls if nulls is None else nulls) else '123.45'
                if invalid and (slot,index)==invalid:value='0'
                valid+=value is not None;values.append([slot,index,value])
        raw=b''.join(f.canonical(value)+b'\n' for value in values)
        parts[f"month_{month['month_ordinal']:03d}"]=raw
        summaries.append({**month,'row_count':len(values),'valid_count':valid,'absent_count':len(values)-valid,**m.pin(raw)})
    manifest={'schema':f.SCHEMA+'-manifest','catalog_pin':f.pin(catalog_raw),
        'AP_fact_sha256':f.AP_FACT_SHA256,'AP_authentication_sha256':f.AP_AUTH_SHA256,
        'binding_stream_sha256':f.BINDING_SHA256,'full_axis_sha256':f.FULL_AXIS_SHA256,
        'assignment_count':f.STOCK_COUNT+f.FUND_COUNT,'vendor_slot_count':f.VENDOR_COUNT+f.FUND_COUNT,
        'session_count':f.SESSION_COUNT,'months':summaries,'row_count':sum(row['row_count'] for row in summaries),
        'valid_count':sum(row['valid_count'] for row in summaries),'absent_count':sum(row['absent_count'] for row in summaries),
        'total_shard_bytes':sum(row['byte_count'] for row in summaries),**f.FALSE_FLAGS}
    if manifest_change:manifest_change(manifest)
    monkeypatch.setattr(f,'OBSERVED_ROWS',manifest['valid_count']);monkeypatch.setattr(f,'ABSENT_CELLS',manifest['absent_count'])
    parts['manifest']=f.canonical(manifest)
    raw=archive_bytes(parts);monkeypatch.setattr(m.archive,'ARCHIVE_PIN',m.pin(raw))
    return raw,parts,manifest


@pytest.fixture
def case(monkeypatch):
    axis=('2013-01-02','2020-12-31','2021-10-29','2021-11-01','2021-11-02','2022-10-21','2026-10-12','2026-10-13')
    prices=list(axis[1:]);rows=tuple(binding(i) for i in range(8));f=m.fmt;q=m.targets
    stream=hashlib.sha256(b''.join(q.figi._canonical(row) for row in rows)).hexdigest()
    for owner in (q,q.policy):
        monkeypatch.setattr(owner,'ORIGINAL_BINDING_COUNT',8)
        monkeypatch.setattr(owner,'ORIGINAL_BINDING_STREAM_SHA256',stream)
        monkeypatch.setattr(owner,'QUARANTINED_WHOLE_BINDING_SHA256S',tuple(m.digest(row) for row in rows[:5]))
    for name,value in {'STOCK_COUNT':8,'VENDOR_COUNT':2,'NATIVE_COUNT':5,'CONDITIONAL_COUNT':1,
        'SESSION_COUNT':7,'MONTH_COUNT':5,'BINDING_SHA256':stream,'FULL_AXIS_SHA256':m.digest(list(axis))}.items():
        monkeypatch.setattr(f,name,value)
    monkeypatch.setattr(m,'AXIS_COUNT',len(axis));monkeypatch.setattr(m,'AXIS_SHA256',m.digest(list(axis)))
    monkeypatch.setattr(m,'EXPECTED_PRICE_SESSIONS',6);monkeypatch.setattr(m,'EXPECTED_DECISIONS',3)
    monkeypatch.setattr(m.archive,'ROLES',('catalog',*(f'month_{i:03d}' for i in range(5)),'manifest'))
    catalog=q.make_quarantine_catalog(rows);catalog_raw=m.canonical(catalog)
    monkeypatch.setattr(m,'CATALOG_PIN',m.pin(catalog_raw))
    memberships=tuple(m.evaluator.build_membership_record(security_id=row['security_id'],
        first_session_index=0 if index==7 else 5 if index==6 else 3,
        last_session_index_exclusive=1 if index==7 else 6 if index==6 else len(axis),sector_id='SYNTHETIC-SECTOR')
        for index,row in enumerate(rows))
    session_rows=tuple({'schema':m.evaluator.SESSION_SCHEMA,'session_index':index,'session':day} for index,day in enumerate(axis))
    lineage={name:('a'*64 if name!='security_master_admission_sha256' else q.ADMISSION_SHA256)
        for name in m.evaluator._SOURCE_LINEAGE_FIELDS}
    manifest=m.evaluator.build_preliminary_rating_manifest(benchmark_security_id='SYNTHETIC-BENCHMARK',
        session_axis_records=session_rows,membership_records=memberships,contribution_records=(),source_lineage_sha256s=lineage)
    input_binding=package_binding(axis,rows,manifest)
    monkeypatch.setattr(m,'INPUT_BINDING_PIN',m.pin(m.canonical(input_binding)))
    assignments=[]
    for ordinal,row in enumerate(rows):
        role=f.NATIVE if ordinal<5 else f.CONDITIONAL if ordinal==7 else f.VENDOR
        assignments.append({'binding_ordinal':ordinal,'security_id':row['security_id'],
            'whole_binding_sha256':m.digest(row),'semantic_binding_sha256':row['row_sha256'],
            'role':role,'table':'stocks' if role==f.VENDOR else None,
            'ticker':f'SYNTH{ordinal}' if role==f.VENDOR else None,'refusal_reason':None if role==f.VENDOR else 'synthetic'})
    for ordinal,ticker in enumerate(f.OWN_FUNDS):assignments.append({'fund_ordinal':ordinal,'own_ETF':ticker,
        'role':f.VENDOR,'table':'funds','ticker':ticker,'route_sha256':m.digest({'fund':ordinal})})
    vendor={'schema':f.SCHEMA+'-catalog','AP_fact_sha256':f.AP_FACT_SHA256,'AP_source_sha256':f.AP_SOURCE_SHA256,
        'AP_authentication_sha256':f.AP_AUTH_SHA256,'source_data_pins':copy.deepcopy(f.AP_DATA_PINS),
        'binding_stream_sha256':stream,'full_axis_sha256':m.AXIS_SHA256,'price_sessions':prices,
        'assignments':assignments,'vendor_slots':[5,6,*range(8,16)],'months':f.months(prices),**f.FALSE_FLAGS}
    value=NS(axis=axis,rows=rows,memberships=memberships,manifest=manifest,input_binding=input_binding,
        catalog_raw=catalog_raw,vendor=vendor,nulls={(5,1),(6,2),(6,6),(15,6)})
    value.raw,value.parts,value.price_manifest=rebuild_archive(value,monkeypatch)
    return value


def run(case,**changes):
    kwargs={'axis':case.axis,'bindings':case.rows,'membership_rows':case.memberships,
        'evaluator_manifest':case.manifest,'input_binding':case.input_binding,
        'transport_nonce':SYNTHETIC_NONCE,'deadline':time.monotonic()+299}
    raw=changes.pop('archive_raw',case.raw);catalog_raw=changes.pop('catalog_raw',case.catalog_raw)
    kwargs.update(changes)
    return m.prepare(raw,catalog_raw,**kwargs)


def test_real_all_month_grid_parsing_authenticates_incomplete_diagnostic_not_returns(case,monkeypatch):
    original=m.fmt.validate_shard;seen=[]
    def observe(raw,**kwargs):seen.append(kwargs['summary']['month_ordinal']);return original(raw,**kwargs)
    monkeypatch.setattr(m.fmt,'validate_shard',observe)
    summary,private=run(case)
    assert seen==list(range(5))
    assert summary['observation_complete'] is True and summary['conservative_required_price_coverage_complete'] is False
    assert summary['observed_grid_row_count']==70 and summary['observed_null_cell_count']==4
    assert summary['missing_pair_count']==3 and summary['missing_reason_counts']=={'authenticated_explicit_null':3}
    assert private['missing_required_pairs']==[[5,1,3],[6,6,1],[15,6,1]]
    assert summary['cells'][0]['combined']['missing_required_dense_cell_count']==2
    assert summary['cells'][3]['combined']['missing_required_dense_cell_count']==3
    assert all(cell['stock']==summary['cells'][0]['stock'] for cell in summary['cells'])
    assert all(summary[key] is False for key in m.FALSE_FLAGS)
    assert summary['private_evidence_pin']==m.pin(m.canonical(private))
    assert len(private['demand_records'])==16
    assert '123.45' not in m.canonical(private).decode()
    assert b'SYNTH' not in m.canonical(summary) and b'sharadar-composite' not in m.canonical(summary)
    assert 'assistant.dispatch_fence' not in sys.modules


def test_dense_tail_survives_membership_and_binding_expiry(case):
    summary,private=run(case)
    row=private['demand_records'][6]
    assert row['eligible_decision_count']==1
    assert row['reference_price_session_indexes']==[3] and row['first_price_session_index']==3
    assert [6,6,1] in private['missing_required_pairs']  # After this membership interval ended.
    assert [6,2,1] not in private['missing_required_pairs']  # A real null before first possible exposure.


def test_quarantine_all_five_have_no_prices_in_all_six_cells(case):
    summary,private=run(case)
    for row in private['demand_records'][:5]:
        assert row['quarantined'] is True and row['first_price_session_index'] is None
        assert row['reference_price_session_indexes']==[] and row['eligible_decision_count']==3
    assert all(slot>=5 for slot,_,_ in private['missing_required_pairs'])
    assert summary['quarantined_demand_count']==0


def test_complete_superset_observation_still_not_strategy_or_engine_readiness(case,monkeypatch):
    raw,_,_=rebuild_archive(case,monkeypatch,nulls=set())
    summary,private=run(case,archive_raw=raw)
    assert summary['conservative_required_price_coverage_complete'] is True
    assert summary['missing_pair_count']==0 and private['missing_required_pairs']==[]
    assert all(cell['conservative_required_price_coverage_complete'] is True for cell in summary['cells'])
    assert all(summary[key] is False for key in m.FALSE_FLAGS)


def test_all_eight_funds_have_dense_coverage_but_six_cohort_uses_only_six(case):
    summary,private=run(case)
    assert summary['cells'][0]['fund']['required_dense_cell_count']==6*6
    assert summary['cells'][3]['fund']['required_dense_cell_count']==8*6
    assert summary['cells'][0]['fund']['potential_reference_cell_count']==6*3
    assert summary['cells'][3]['fund']['potential_reference_cell_count']==8*3
    assert len(private['demand_records'][8:])==8


@pytest.mark.parametrize('which',['archive','catalog'])
def test_whole_input_pins_checked_before_parse(case,monkeypatch,which):
    seen=[]
    if which=='archive':
        original=m.archive.loads
        def forbidden(raw,*args,**kwargs):
            if raw==case.catalog_raw:return original(raw,*args,**kwargs)
            seen.append(True);raise AssertionError('unbound archive parsed')
        monkeypatch.setattr(m.archive,'loads',forbidden)
        refused('archive',lambda:run(case,archive_raw=case.raw+b' '))
    else:
        def forbidden(*args,**kwargs):seen.append(True);raise AssertionError('unbound catalog parsed')
        monkeypatch.setattr(m.targets,'make_quarantine_catalog',forbidden)
        refused('input_pin',lambda:run(case,catalog_raw=case.catalog_raw+b' '))
    assert seen==[]


@pytest.mark.parametrize('field',['axis','input_binding','manifest','membership_hash','membership_count','binding'])
def test_independent_original_input_commitments_refuse_before_price_rows(case,monkeypatch,field):
    def forbidden(*args,**kwargs):raise AssertionError('price grid parsed before original input authentication')
    monkeypatch.setattr(m.fmt,'validate_shard',forbidden)
    changes={}
    if field=='axis':changes['axis']=tuple(reversed(case.axis))
    elif field=='input_binding':changes['input_binding']={**case.input_binding,'parent_proof_sha256':'0'*64}
    elif field=='manifest':changes['evaluator_manifest']={**case.manifest,'session_axis_count':999}
    elif field=='membership_count':changes['membership_rows']=case.memberships[:-1]
    elif field=='membership_hash':
        rows=list(case.memberships)
        rows[0]=m.evaluator.build_membership_record(security_id=case.rows[0]['security_id'],
            first_session_index=4,last_session_index_exclusive=8,sector_id='SYNTHETIC-SECTOR')
        changes['membership_rows']=rows
    else:
        rows=copy.deepcopy(list(case.rows));rows[-1]['diagnostic_current_ticker']='CHANGED';changes['bindings']=rows
    with pytest.raises(m.Refused):run(case,**changes)


def rebind_memberships(case,monkeypatch,memberships):
    manifest=copy.deepcopy(case.manifest);manifest['membership_row_count']=len(memberships)
    manifest['membership_rows_sha256']=m.evaluator._stream_sha256(tuple(memberships))
    seed={key:value for key,value in manifest.items() if key not in ('manifest_id','manifest_sha256')}
    manifest['manifest_sha256']=m.digest(seed);manifest['manifest_id']='arv2-preliminary-rating-manifest-'+manifest['manifest_sha256'][:24]
    bound={**case.input_binding,'evaluator_manifest_sha256':manifest['manifest_sha256']}
    monkeypatch.setattr(m,'INPUT_BINDING_PIN',m.pin(m.canonical(bound)))
    return {'membership_rows':memberships,'evaluator_manifest':manifest,'input_binding':bound}


def test_conditional_demand_refuses_never_relabelled_or_dropped(case,monkeypatch):
    rows=list(case.memberships);rows[-1]=m.evaluator.build_membership_record(
        security_id=case.rows[-1]['security_id'],first_session_index=3,last_session_index_exclusive=8,sector_id='SYNTHETIC-SECTOR')
    changes=rebind_memberships(case,monkeypatch,rows)
    refused('conditional_demand',lambda:run(case,**changes))


def test_membership_outside_full_original_catalog_refuses(case,monkeypatch):
    rows=list(case.memberships);rows[-1]=m.evaluator.build_membership_record(
        security_id='UNKNOWN-SYNTHETIC-SECURITY',first_session_index=3,last_session_index_exclusive=8,sector_id='SYNTHETIC-SECTOR')
    changes=rebind_memberships(case,monkeypatch,rows)
    refused('memberships',lambda:run(case,**changes))


@pytest.mark.parametrize('field',['security_id','semantic_binding_sha256'])
def test_source_assignment_exact_original_security_and_semantic_join(case,monkeypatch,field):
    def change(catalog):catalog['assignments'][5][field]='FORGED-ID' if field=='security_id' else 'f'*64
    raw,_,_=rebuild_archive(case,monkeypatch,catalog_change=change)
    refused('assignment',lambda:run(case,archive_raw=raw))


def test_native_role_cannot_be_swapped_with_vendor(case,monkeypatch):
    def change(catalog):
        for slot,role in ((0,m.fmt.VENDOR),(5,m.fmt.NATIVE)):
            row=catalog['assignments'][slot];row.update(role=role,table='stocks' if slot==0 else None,
                ticker='SYNTH0' if slot==0 else None,refusal_reason=None if slot==0 else 'synthetic')
        catalog['vendor_slots']=[0,6,*range(8,16)]
    raw,_,_=rebuild_archive(case,monkeypatch,catalog_change=change)
    refused('quarantine',lambda:run(case,archive_raw=raw))


def test_invalid_nonrequired_price_row_refuses_instead_of_ignored(case,monkeypatch):
    raw,_,_=rebuild_archive(case,monkeypatch,invalid=(6,0))
    refused('grid',lambda:run(case,archive_raw=raw))


def test_changed_last_archive_range_refuses_before_any_month_parse(case,monkeypatch):
    raw=case.raw[:-1]+bytes([case.raw[-1]^1]);monkeypatch.setattr(m.archive,'ARCHIVE_PIN',m.pin(raw))
    def forbidden(*args,**kwargs):raise AssertionError('price rows parsed before all range hashes')
    monkeypatch.setattr(m.fmt,'validate_shard',forbidden)
    refused('archive',lambda:run(case,archive_raw=raw))


def test_missing_pair_bound_refuses_without_truncation(case,monkeypatch):
    monkeypatch.setattr(m,'MAX_MISSING_PAIRS',2)
    refused('missing_bound',lambda:run(case))


def test_private_bound_refuses_without_dropping_missing_evidence(case,monkeypatch):
    monkeypatch.setattr(m,'MAX_PRIVATE_BYTES',1)
    refused('private_bound',lambda:run(case))


@pytest.mark.parametrize('bad',[None,True,-1,float('inf'),float('nan')])
def test_deadline_is_finite_before_any_input_parse(case,monkeypatch,bad):
    def forbidden(*args,**kwargs):raise AssertionError('input parsed before deadline')
    monkeypatch.setattr(m,'_inputs',forbidden)
    refused('deadline',lambda:run(case,deadline=bad))


def test_deadline_after_full_grid_is_not_success(case,monkeypatch):
    original=m.fmt.validate_shard;state={'expired':False}
    def last(raw,**kwargs):
        result=original(raw,**kwargs)
        if kwargs['summary']['month_ordinal']==4:state['expired']=True
        return result
    monkeypatch.setattr(m.fmt,'validate_shard',last)
    budget=m.budget
    def expired(value):
        if state['expired']:raise m.Refused('deadline')
        budget(value)
    monkeypatch.setattr(m,'budget',expired)
    refused('deadline',lambda:run(case))


@pytest.mark.parametrize('fault',['extra','bool_count','false_complete','stock_marginal','fund_subset','false_flags','private_pin','missing_reason'])
def test_summary_closed_counts_cross_cell_relations_and_no_false_acceptance(case,fault):
    summary,_=run(case)
    if fault=='extra':summary['security_id']='NEVER-PUBLIC'
    elif fault=='bool_count':summary['missing_pair_count']=True
    elif fault=='false_complete':summary['conservative_required_price_coverage_complete']=True
    elif fault=='stock_marginal':summary['cells'][1]['stock']['missing_required_dense_cell_count']+=1
    elif fault=='fund_subset':summary['cells'][0]['fund']['demanded_binding_count']=8
    elif fault=='false_flags':summary['actual_targets_proven']=True
    elif fault=='private_pin':summary['private_evidence_pin']['sha256']='SYNTHETIC-INVALID'
    else:summary['missing_reason_counts']['unclassified']=1
    refused('output',lambda:m.validate_summary(summary))


def test_no_engine_order_NAV_or_frozen_operation_dependency():
    tree=ast.parse(inspect.getsource(m))
    calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call)]
    assert not any(isinstance(node.func,ast.Name) and node.func.id in ('open','eval','exec','compile','__import__') for node in calls)
    assert not any(isinstance(node.func,ast.Attribute) and node.func.attr in ('market_order','History','history',
        'resolve_preliminary_qc_figis','build_target','score_session','load_october_order_input_package') for node in calls)
    assert m.profile_record()['stock_demand'].endswith('no_expiry_clip')
    assert m.MAX_SECONDS==300 and m.MAX_PRIVATE_BYTES==64*1024*1024


def test_exact_input_binding_pin_derived_from_frozen_public_observation_only():
    from pathlib import Path
    tree=ast.parse(Path('scripts/arv2_r298_aa_source_binding.py').read_text())
    raw=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
        and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='_SUMMARY_JSON')
    import json
    assert m.pin(m.canonical(json.loads(raw)['input_binding']))==m.INPUT_BINDING_PIN


def test_actual_71_month_inventory_is_fully_parsed_with_real_fmt(case,monkeypatch):
    # Sparse synthetic dates keep this test small; actual production calendar and
    # membership commitments are external fixed pins, never this fixture axis.
    days=['2020-12-31']
    for year in range(2021,2027):
        for month in range(1,13):
            if year==2026 and month>10:break
            days.append(f'{year:04d}-{month:02d}-01')
    days=sorted(set(days+['2021-10-29','2026-10-12','2026-10-13']))
    axis=('2013-01-02',*days);positions={day:index for index,day in enumerate(axis)}
    seen=set();decisions=[]
    from datetime import date
    for day in axis:
        if m.FIRST<=day<=m.CUTOFF:
            week=date.fromisoformat(day).isocalendar()[:2]
            if week not in seen:seen.add(week);decisions.append(day)
    monkeypatch.setattr(m,'AXIS_COUNT',len(axis));monkeypatch.setattr(m,'AXIS_SHA256',m.digest(list(axis)))
    monkeypatch.setattr(m,'EXPECTED_PRICE_SESSIONS',sum(m.PRIOR<=day<=m.LAST for day in axis))
    monkeypatch.setattr(m,'EXPECTED_DECISIONS',len(decisions))
    monkeypatch.setattr(m.fmt,'SESSION_COUNT',len(days));monkeypatch.setattr(m.fmt,'MONTH_COUNT',71)
    monkeypatch.setattr(m.fmt,'FULL_AXIS_SHA256',m.AXIS_SHA256)
    monkeypatch.setattr(m.archive,'ROLES',('catalog',*(f'month_{i:03d}' for i in range(71)),'manifest'))
    memberships=tuple(m.evaluator.build_membership_record(security_id=row['security_id'],
        first_session_index=0 if index==7 else positions[m.FIRST],
        last_session_index_exclusive=1 if index==7 else len(axis),sector_id='SYNTHETIC-SECTOR')
        for index,row in enumerate(case.rows))
    session_rows=tuple({'schema':m.evaluator.SESSION_SCHEMA,'session_index':index,'session':day} for index,day in enumerate(axis))
    manifest=m.evaluator.build_preliminary_rating_manifest(benchmark_security_id='SYNTHETIC-BENCHMARK',
        session_axis_records=session_rows,membership_records=memberships,contribution_records=(),
        source_lineage_sha256s=case.manifest['source_lineage_sha256s'])
    bound=package_binding(axis,case.rows,manifest)
    monkeypatch.setattr(m,'INPUT_BINDING_PIN',m.pin(m.canonical(bound)))
    case.vendor.update(price_sessions=days,months=m.fmt.months(days),full_axis_sha256=m.AXIS_SHA256)
    raw,_,_=rebuild_archive(case,monkeypatch,nulls=set())
    original=m.fmt.validate_shard;observed=[]
    def parse(raw,**kwargs):
        observed.append(kwargs['summary']['month_ordinal']);return original(raw,**kwargs)
    monkeypatch.setattr(m.fmt,'validate_shard',parse)
    summary,_=run(case,axis=axis,membership_rows=memberships,evaluator_manifest=manifest,
        input_binding=bound,archive_raw=raw)
    assert observed==list(range(71)) and summary['month_count']==71
    assert summary['conservative_required_price_coverage_complete'] is True


def test_transport_nonce_blinds_only_private_pin_without_economic_or_demand_changes(case):
    first,private_first=run(case)
    second,private_second=run(case,transport_nonce='abcd1234'*8)
    assert private_first['transport_nonce']==SYNTHETIC_NONCE
    assert private_second['transport_nonce']=='abcd1234'*8
    assert first['private_evidence_pin']!=second['private_evidence_pin']
    assert {key:value for key,value in first.items() if key!='private_evidence_pin'}=={
        key:value for key,value in second.items() if key!='private_evidence_pin'}
    assert {key:value for key,value in private_first.items() if key!='transport_nonce'}=={
        key:value for key,value in private_second.items() if key!='transport_nonce'}
    for public in (first,second,m.profile_record()):
        raw=m.canonical(public)
        assert SYNTHETIC_NONCE.encode() not in raw and ('abcd1234'*8).encode() not in raw
        assert 'transport_nonce' not in public


@pytest.mark.parametrize('nonce',[None,True,0,b'a'*64,'','a'*63,'a'*65,'A'*64,'g'*64,'a'*63+'\n'])
def test_malformed_nonce_finite_refusal_before_any_input_parse(case,monkeypatch,nonce):
    def forbidden(*args,**kwargs):raise AssertionError('source parsed before nonce check')
    monkeypatch.setattr(m,'_inputs',forbidden)
    refused('transport_nonce',lambda:run(case,transport_nonce=nonce))


def test_nonce_is_mandatory_keyword_no_default():
    for function in (m.prepare,m._prepare):
        parameter=inspect.signature(function).parameters['transport_nonce']
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty
