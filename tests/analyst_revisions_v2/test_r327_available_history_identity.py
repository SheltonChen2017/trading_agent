"""Supplied-data W5 identity/demand tests; no DATA, claims or provider/QC use."""
import copy
from collections import Counter
import hashlib
import inspect
import json
import pickle
import time
import pytest
from scripts import arv2_r327_available_history_identity as m
from tests.analyst_revisions_v2 import test_r298_sharadar_all_routes_v2 as source_fixture


def fail(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def test_exact_public_context_retains_H_AD_failure_and_full_original_input():
    context=m.source_context();assert context['H_fact_sha256']==m.H_FACT_SHA256
    assert context['H_prior_context']['AD_actual_producer_exit']==2
    assert context['input_binding']['binding_contract']['binding_count']==6151
    assert context['period_sha256']==m.period.make_period(m.demand.loader.previous.october._sessions())['period_sha256']
    assert len(m.DATA_PLAN)==4 and sum(row['byte_count'] for row in m.DATA_PLAN.values())==5507602


@pytest.mark.parametrize('field',('producer','validator','source_actual','provider_actual','authentication_actual'))
@pytest.mark.parametrize('bad',(False,True,2))
def test_H_actual_zero_is_structural_not_bool(monkeypatch,field,bad):
    fact=m.h_anchor.observed_fact();fact[field]['actual_exit']=bad
    monkeypatch.setattr(m.h_anchor,'observed_fact',lambda:fact);monkeypatch.setattr(m,'H_FACT_SHA256',m.digest(fact))
    fail('source_context',m.source_context)


@pytest.mark.parametrize('outer_seconds',(300,None,30))
def test_frozen_AE_selection_predicate_gets_parent_bounded_120s_budget(monkeypatch,outer_seconds):
    context={'H_prior_context':{'synthetic':True}}
    value={'schema':m.h.SCHEMA+'-private','selection_pin':m.h.SELECTION_PIN,'selection':{},'phases':[],
        'observations':[],'prior_context':context['H_prior_context'],'vendor_source_blockers_remaining':5,
        'no_original_identifier_or_collision_clearance':True}
    monkeypatch.setattr(m,'_loads',lambda _:value);observed=[]
    class ReachedRealPredicate(Exception):pass
    outer=None if outer_seconds is None else time.monotonic()+outer_seconds
    def selection(raw,child_deadline):
        # Invoke the actual frozen AE predicate; no synthetic agreeing clock
        # or copied remaining() implementation can hide its 120-second cap.
        remaining=m.h.selection_proof.remaining(child_deadline)
        assert 0<remaining<=120
        if outer is not None:assert child_deadline<=outer
        if outer_seconds==30:assert child_deadline==outer
        observed.append(child_deadline);raise ReachedRealPredicate
    monkeypatch.setattr(m.h,'_selection',selection)
    with pytest.raises(ReachedRealPredicate):m._hierarchy(b'synthetic',context,outer)
    assert len(observed)==1


def test_expired_parent_refuses_before_H_data_parse_or_selection(monkeypatch):
    monkeypatch.setattr(m,'_loads',lambda _:pytest.fail('DATA parsed after parent deadline'))
    monkeypatch.setattr(m.h,'_selection',lambda *_:pytest.fail('selection dispatched after parent deadline'))
    fail('deadline',lambda:m._hierarchy(b'synthetic',{},time.monotonic()-1))


@pytest.fixture
def source_case():
    data=source_fixture.case(5)
    _,private=m.PRICE.routes.join(*data,binding_contract=source_fixture.supplied.contract(data[0]))
    aa=private.private_record();built=m.CURRENT._build(data[2],data[3]);return data,aa,built


def test_original_proof_real_constructor_and_all_four_byte_pins_precede_JSON(source_case,monkeypatch):
    data,aa,_=source_case
    for row in aa['stocks']:assert m.PRICE._original(row)['figi']==row['binding']['composite_figi']
    monkeypatch.setattr(m,'_genuine',lambda *_:pytest.fail('genuine parse before DATA byte pins'))
    fail('byte_pin',lambda:m.prepare(b'bad',b'bad',b'bad',b'bad',full_axis=(),binding_rows=(),membership_rows=(),
        evaluator_manifest={},input_binding={}))


@pytest.mark.parametrize('mode',('CUSIP_only','poison','bad_quality','cross_table','duplicate','same_FIGI','same_perma'))
def test_global_related_owner_inventory_never_drops_non_candidate_rows(source_case,mode):
    data,aa,_=source_case;item=aa['stocks'][0];original=item['original_row'];identity=m.PRICE._original(item)
    candidate=data[2][0];stocks=copy.deepcopy(data[2]);funds=copy.deepcopy(data[3]);rival=copy.deepcopy(candidate)
    rival.update(permaticker='999991',figi='BBG999999999',ticker='UNRELATED',cusips=identity['tokens'][0])
    if mode=='poison':rival['cusips']='BROKEN '+identity['tokens'][0]
    if mode=='bad_quality':rival['currency']='EUR'
    if mode=='cross_table':rival.update(table='funds',category='ETF');funds.append(rival)
    elif mode=='duplicate':stocks.append(copy.deepcopy(candidate))
    elif mode=='same_FIGI':rival['figi']=identity['figi'];stocks.append(rival)
    elif mode=='same_perma':rival['permaticker']=identity['permaticker'];stocks.append(rival)
    else:stocks.append(rival)
    built=m.CURRENT._build(stocks,funds);rows=m._rivals(original,identity,[candidate],built,None)
    assert all(set(row['links'])==set(m.LINKS) and set(row['patterns'])==set(m.FLAGS) for row in rows)
    assert any(row['retained_candidate_row_equal'] for row in rows)
    target=next(row for row in rows if row['table']==('funds' if mode=='cross_table' else 'stocks')
        and row['row_ordinal']==(len(funds)-1 if mode=='cross_table' else len(stocks)-1))
    if mode=='poison':assert target['links']['original_poison_CUSIP'] and target['vocabulary_state']=='malformed'
    elif mode in ('CUSIP_only','bad_quality','cross_table'):assert target['links']['original_complete_CUSIP']
    if mode=='CUSIP_only':assert not any(target['links'][key] for key in m.LINKS[:6])
    if mode=='bad_quality':assert target['quality'] is False
    if mode=='duplicate':assert target['retained_candidate_row_equal'] is True
    if mode=='same_FIGI':assert target['links']['original_FIGI']
    if mode=='same_perma':assert target['links']['original_permaticker']


def test_related_owner_byte_budget_refuses_instead_of_truncating(source_case):
    data,aa,built=source_case;item=aa['stocks'][0]
    fail('private_bound',lambda:m._rivals(item['original_row'],m.PRICE._original(item),[data[2][0]],built,None,1))


def test_metadata_last_date_is_only_a_field_observation(source_case):
    data,aa,built=source_case;item=aa['stocks'][0];row=copy.deepcopy(data[2][0]);row['lastpricedate']='2022-01-03'
    record=m.CURRENT._build([row],[])[1][('stocks',0)]
    flags=m._patterns(item['original_row'],m.PRICE._original(item),row,'stocks',record)
    assert flags['current_last_before_W5_end'] is flags['current_last_before_gap'] is True
    assert 'price_end' not in flags and m.FALSE_FLAGS['metadata_date_used_to_retire_holdings'] is False


@pytest.mark.parametrize('original,current,expected',[
    ('','',None),('invalid','invalid',None),('','invalid',None),('2022-01-03','',None),
    ('invalid','2022-01-03',None),('2022-01-03','2022-01-03',True),('2022-01-03','2022-01-04',False)])
def test_price_endpoint_equality_is_unknown_when_either_endpoint_unavailable(original,current,expected):
    flags=m._date_flags({'firstpricedate':original,'lastpricedate':original},{'firstpricedate':current,'lastpricedate':current})
    assert flags['original_first_price_equal'] is expected and flags['original_last_price_equal'] is expected


def test_W5_membership_gap_envelope_keeps_carry_until_end_and_prior_close_need():
    axis=m.demand.loader.previous.october._sessions();view=m.period.make_period(axis);pos={s:i for i,s in enumerate(axis)}
    ids=['never','old_only','early','first_after_gap','next_reference_gap']
    intervals=[('old_only','2021-01-04','2021-01-05'),('early','2021-11-01','2021-11-02'),
        ('first_after_gap','2022-10-31','2022-11-01'),('next_reference_gap','2022-10-24','2022-10-25')]
    raw=tuple(sorted((m.EVALUATOR.build_membership_record(security_id=security,first_session_index=pos[first],
        last_session_index_exclusive=pos[last],sector_id='synthetic') for security,first,last in intervals),key=lambda row:row['security_id']))
    members=m.EVALUATOR._parse_memberships(raw,len(axis))
    bindings=[{'security_id':name,'row_sha256':hashlib.sha256(name.encode()).hexdigest()} for name in ids]
    assigned=[{'role':m.fmt.NATIVE} for _ in ids]
    rows,_,_=m._demand(view,axis,bindings,members,assigned,None);by_name=dict(zip(ids,rows))
    assert by_name['never']['potential'] is by_name['old_only']['potential'] is False
    assert by_name['early']['required_price_last']=='2026-10-13' and by_name['early']['gap_possible_held_NAV'] is True
    assert by_name['first_after_gap']['gap_state']=='gap_before_first_required_prior'
    assert by_name['first_after_gap']['gap_not_required_conditional_on_empty_start'] is True
    assert by_name['next_reference_gap']['required_price_first']=='2022-10-21'
    assert by_name['next_reference_gap']['gap_possible_target_reference'] is True and by_name['next_reference_gap']['gap_possible_held_NAV'] is False


def test_conditional_old_assignment_cannot_hide_new_potential():
    axis=m.demand.loader.previous.october._sessions();view=m.period.make_period(axis);index=axis.index(m.period.FIRST)
    raw=(m.EVALUATOR.build_membership_record(security_id='stock',first_session_index=index,last_session_index_exclusive=index+1,sector_id='sector'),)
    members=m.EVALUATOR._parse_memberships(raw,len(axis))
    fail('memberships',lambda:m._demand(view,axis,[{'security_id':'stock','row_sha256':'e'*64}],members,[{'role':m.fmt.CONDITIONAL}],None))


def test_manifest_namespace_is_the_frozen_actual_builder_namespace(monkeypatch):
    axis=m.demand.loader.previous.october._sessions();members=(m.EVALUATOR.build_membership_record(security_id='one',first_session_index=0,last_session_index_exclusive=1,sector_id='sector'),)
    sessions=tuple({'schema':m.EVALUATOR.SESSION_SCHEMA,'session_index':i,'session':s} for i,s in enumerate(axis))
    lineage={key:'d'*64 for key in m.EVALUATOR._SOURCE_LINEAGE_FIELDS}
    manifest=m.EVALUATOR.build_preliminary_rating_manifest(benchmark_security_id='benchmark',session_axis_records=sessions,
        membership_records=members,contribution_records=(),source_lineage_sha256s=lineage)
    context=m.source_context();binding=copy.deepcopy(context['input_binding']);binding['evaluator_manifest_sha256']=manifest['manifest_sha256']
    context['input_binding']=binding
    monkeypatch.setattr(m.PRICE.routes,'_bindings',lambda rows,contract:rows)
    rows=[{'security_id':'one'}]*6151
    value=m._genuine(axis,rows,members,manifest,binding,context,None)
    assert len(value[2])==1
    bad=copy.deepcopy(manifest);bad['manifest_id']='wrong'
    fail('manifest',lambda:m._genuine(axis,rows,members,bad,binding,context,None))


@pytest.fixture
def prepared(source_case,monkeypatch):
    data,aa,built=source_case;context=m.source_context();axis=m.demand.loader.previous.october._sessions();view=m.period.make_period(axis)
    bindings=list(data[0])+[{'security_id':'extra-'+str(i),'row_sha256':hashlib.sha256(str(i).encode()).hexdigest()} for i in range(6146)]
    native=sorted(m.digest(row) for row in bindings[:5]);monkeypatch.setattr(m.period,'NATIVE_WHOLE_BINDING_SHA256S',tuple(native))
    assignments=[]
    for index,row in enumerate(bindings):assignments.append({'whole_binding_sha256':m.digest(row),'semantic_binding_sha256':row['row_sha256'],
        'security_id':row['security_id'],'role':m.fmt.NATIVE if index<5 else m.fmt.VENDOR if index<5641 else m.fmt.CONDITIONAL})
    assignments.extend({'own_ETF':ticker,'role':m.fmt.VENDOR} for ticker in m.period.OWN_FUNDS)
    catalog={'assignments':assignments};selection={'cases':[]};observed=[]
    for index,item in enumerate(aa['stocks']):
        selection['cases'].append({'case_ordinal':index,'aa_stock':item,'ac_stock':{'binding':item['binding']}})
        observed.append({'case_ordinal':index,'observation':{'observation':'unresolved_composite_disagreement'}})
    context['expected_metadata_rows_sha256']=m.CURRENT._receipt(built)['metadata_rows_sha256']
    monkeypatch.setattr(m,'source_context',lambda:copy.deepcopy(context))
    monkeypatch.setattr(m,'_genuine',lambda *_:(view,bindings,()))
    monkeypatch.setattr(m,'_hierarchy',lambda *_:(selection,observed))
    original_loads=m.fmt.loads
    monkeypatch.setattr(m.fmt,'loads',lambda raw,*_:catalog if raw==b'synthetic-catalog' else original_loads(raw,*_))
    monkeypatch.setattr(m.fmt,'validate_catalog',lambda value:value)
    from tests.analyst_revisions_v2 import test_r298_sharadar_eligibility_observation as csv_fixture
    raws=[b'synthetic-hierarchy',b'synthetic-catalog',csv_fixture.csv_bytes(m.CURRENT.FIELDS,data[2]),csv_fixture.csv_bytes(m.CURRENT.FIELDS,data[3])]
    plan=copy.deepcopy(m.DATA_PLAN)
    for role,raw in zip(plan,raws,strict=True):plan[role].update(m.pin(raw))
    monkeypatch.setattr(m,'DATA_PLAN',plan)
    summary,private=m.prepare(*raws,full_axis=axis,binding_rows=bindings,membership_rows=(),
        evaluator_manifest={'membership_rows_sha256':m.EVALUATOR._stream_sha256(())},input_binding=context['input_binding'])
    return summary,private


def test_full_prepare_retains_6151_and8_private_rows_but_no_licensed_summary(prepared):
    summary,private=prepared;record=private.private_record();assert len(record['stock_demand'])==6151 and len(record['fund_demand'])==8 and len(record['cases'])==5
    assert m.validate_private_record(record,expected_summary=summary)==record
    assert private.summary_sha256==m.digest(summary) and private.sha256==summary['private_payload_pin']['sha256']
    raw=m.canonical(summary)
    for forbidden in (b'SYN1',b'BBG000000001',b'000000001',b'NASDAQ',b'original_row',b'current_candidate_rows'):
        assert forbidden not in raw
    assert all(summary[key] is False for key in m.FALSE_FLAGS)
    assert 'redacted' in repr(private)
    with pytest.raises(TypeError):pickle.dumps(private)


@pytest.mark.parametrize('issue',('extra_case_field','raw_reason','count_bool','owner_count','gap','date','grant','period','private_mix'))
def test_closed_summary_and_private_pair_refuse_tampering(prepared,issue):
    summary,private=prepared;summary=copy.deepcopy(summary)
    if issue=='extra_case_field':summary['cases'][0]['ticker']='must-not-escape'
    elif issue=='raw_reason':summary['cases'][0]['H_observation_counts']={'private-identifier':1}
    elif issue=='count_bool':summary['cases'][0]['rival_count']=True
    elif issue=='owner_count':summary['cases'][0]['other_related_owner_count']+=1
    elif issue=='gap':summary['cases'][0]['gap_possible_held_NAV']=True
    elif issue=='date':summary['cases'][0]['first_eligible_decision']='private-name'
    elif issue=='grant':summary['global_collision_cleared']=True
    elif issue=='period':summary['period_sha256']='e'*64
    else:
        record=private.private_record();record['cases'][0]['demand']['potential']=True
        fail('private',lambda:m.validate_private_record(record,expected_summary=summary));return
    fail('summary',lambda:m.validate_summary(summary))


@pytest.mark.parametrize('issue',('count260','Tuesday','wrong_prior'))
def test_potential_metadata_requires_exact_W5_decisions_and_prior_close(prepared,issue):
    summary,_=prepared;summary=copy.deepcopy(summary);row=summary['cases'][0]
    summary['stock_demand_counts_by_source_role'][m.fmt.NATIVE]={'potential':1,'never_potential':4}
    row.update(potential=True,eligible_decision_count=1,first_eligible_decision='2021-11-01',last_eligible_decision='2021-11-01',
        required_price_first='2021-10-29',required_price_last='2026-10-13',gap_state='gap_inside_possible_exposure',
        gap_possible_target_reference=False,gap_possible_held_NAV=True,gap_not_required_conditional_on_empty_start=False)
    if issue=='count260':row.update(eligible_decision_count=260,last_eligible_decision='2026-10-12')
    elif issue=='Tuesday':row.update(first_eligible_decision='2021-11-02',last_eligible_decision='2021-11-02',required_price_first='2021-11-01')
    else:row['required_price_first']='2021-10-28'
    fail('summary',lambda:m.validate_summary(summary))


def test_pure_helper_has_no_operational_call_or_I_O_surface():
    source=inspect.getsource(m)
    for forbidden in ('open(','h.run(','h.main(','h.source_observation(','h.provider','load_key(','requests.','os.'):assert forbidden not in source
    assert list(inspect.signature(m.prepare).parameters)==['h_raw','catalog_raw','stocks_raw','funds_raw','full_axis','binding_rows',
        'membership_rows','evaluator_manifest','input_binding','deadline']
