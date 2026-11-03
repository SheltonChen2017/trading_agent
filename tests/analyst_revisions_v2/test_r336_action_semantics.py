"""Synthetic normative semantics only; no retained DATA or provider access."""
import ast
import copy
import csv
from datetime import date,timedelta
import io
import json
from pathlib import Path
import time
from types import SimpleNamespace as NS
import pytest
from scripts import arv2_r336_action_semantics as n
from scripts import arv2_r336_original_identity_ownership as m

def refuse(code,call):
    with pytest.raises(n.Refused) as caught:call()
    assert n.finite(caught.value)==code

def source_row(index):
    row={key:'' for key in m.REQUIRED};row.update(table='SF1',ticker='S'+str(index),permaticker=str(index+100),
      figi='BBG'+str(index).zfill(9),cusips=str(index+1).zfill(9),exchange='NASDAQ',category='Domestic Common Stock',
      currency='USD',firstpricedate='2000-01-03',lastpricedate='2026-10-13',isdelisted='N',sector='Technology',industry='Synthetic',
      name='Synthetic issuer',lastupdated='2026-09-13')
    row.update({'extra'+str(i):'' for i in range(28-len(row))});return row

def source_binding(row):
    evidence={'permaticker':row['permaticker'],'composite_figi':row['figi'],'source_table':'SF1','ticker':row['ticker'],
      'cusips':[row['cusips']],'exchange':'NASDAQ','exchange_mic':'XNAS','firstpricedate':'2000-01-03','lastpricedate':'2026-10-13',
      'source_row_sha256':m.sha(m.row_bytes(row)),'availability_semantics':'capture_time_current_snapshot_active_and_delisted_not_point_in_time'}
    digest=m.sha(m.original_json_bytes(evidence))
    return {'source_row_sha256':evidence['source_row_sha256'],'security_id':'sharadar-composite-figi-'+row['figi'],
      'issuer_id':'sharadar-permaticker-'+row['permaticker'],'composite_figi':row['figi'],'listing_id':'sharadar-listing-'+digest[:24],
      'diagnostic_current_ticker':row['ticker'],'diagnostic_exchange_mic':'XNAS','identity_evidence_sha256':digest}

def event(code='listed',**changes):
    row={'date':'2024-01-03','action':code,'ticker':'S0','name':'Synthetic issuer','value':'1','contraticker':'','contraname':''}
    row.update(changes);return row

@pytest.fixture
def fixture(monkeypatch):
    originals=[source_row(i) for i in range(5)];wholes=[];base_cases=[];i_cases=[]
    for ordinal,(old,(first,count)) in enumerate(zip(originals,n.GEOMETRY,strict=True)):
        binding=source_binding(old);whole=m.sha(m.canonical(binding));wholes.append(whole)
        current=[{key:old[key] for key in m.CURRENT_FIELDS}];current[0].update(table='stocks',figi='BBG'+str(ordinal+20).zfill(9))
        if ordinal==0:current.append(dict(current[0],ticker='C0',permaticker='999',cusips='999999999'))
        demand={'whole_binding_sha256':whole,'required_price_first':first,'required_price_last':n.LAST,
          'source_role':'pending_native_original_identity_source','membership_or_binding_end_used_as_price_end':False}
        base_cases.append({'case_ordinal':ordinal,'whole_binding_sha256':whole,'demand':demand,
          'original_case':{'aa_stock':{'binding':binding,'original_row':old,'current_candidate_rows':current}}})
        required=[(date.fromisoformat(first)+timedelta(days=i)).isoformat() for i in range(count-1)]+[n.LAST]
        retained={'case_ordinal':ordinal,'whole_binding_sha256':whole,'binding':binding,'original_row':old,
          'current_candidate_rows':current,'required_sessions':required,
          'candidates':[{'gap_geometry':{'missing_required_sessions':[required[1]]}}],
          'no_candidate_gap':{'missing_required_sessions':[]}}
        i_cases.append({'case_ordinal':ordinal,'whole_binding_sha256':whole,'original_F_case':retained,
          'event_links':[],'alias_admitted':False,'source_assignment_changed':False})
    monkeypatch.setattr(m,'WHOLes',tuple(wholes))
    _,ownership=m.inspect(originals,{'schema':'arv2-r327-W5-identity-necessary-demand-i-v1-private','cases':base_cases},deadline=time.monotonic()+30)
    header=['table','indicator','isfilter','isprimarykey','title','description','unittype']
    dictionary=[dict(zip(header,('actiontypes','synthetic'+str(i),'N','N','Synthetic title','Synthetic definition','text'),strict=True)) for i in range(75)]
    rules={}
    for code,rule in n.RULES.items():
        rawrow=dict(zip(header,('actiontypes',code,'N','N','Synthetic '+code,'Normative synthetic definition '+code,'text'),strict=True))
        dictionary[rule[0]]=rawrow;pin=n.pin(n.canonical(rawrow));rules[code]=(rule[0],pin['byte_count'],pin['sha256'],*rule[3:])
    monkeypatch.setattr(n,'RULES',rules)
    rows=[event(date=(date(2024,6,1)+timedelta(days=i)).isoformat()) for i in range(33)]
    rows[:14]=[
      event('tickerchangefrom',contraticker='OLD'),event('tickerchangeto',contraticker='NEW'),
      event('namechangefrom',contraname='Old Issuer'),event('namechangeto',contraname='New Issuer'),
      event('sicchangefrom',value='1234',contraname='Prior industry'),event('sicchangeto',value='5678',contraname='New industry'),
      event('spacunitseparation',contraticker='UNIT.A',value=''),event('mergerfrom',contraticker='NON.SURVIVOR'),
      event('mergerto',contraticker='SURVIVOR'),event('acquisitionstock',contraticker='RECEIVED',value='1.25'),
      event('relation',contraticker='RELATED'),event('spacmerger',value=''),event('delisted',value='100'),event('listed',value='200')]
    def values():
        stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n');writer.writerow(header)
        for row in dictionary:writer.writerow([row[key] for key in header])
        jraw=stream.getvalue().encode();monkeypatch.setattr(n,'J_PIN',n.pin(jraw))
        events=[];cases=copy.deepcopy(i_cases)
        for ordinal,row in enumerate(rows):
            owners=[0] if row['ticker'] in ('S0','C0') else [int(row['ticker'][1:])]
            events.append({'source_row_ordinal':ordinal,'row':dict(row),'action_family':'unknown','primary_owner_case_ordinals':owners,
              'shared_primary_ticker_ownership':False,'literal_counterparty_metadata_lead':row['contraticker'] if n.safe_token(row['contraticker']) else None,
              'opaque_contraticker_verbatim':row['contraticker'],'ticker_change_search_lead':None,
              'same_security_or_share_class_proven':False,'alias_admitted':False,'corporate_action_applied':False})
            for owner in owners:
                first=cases[owner]['original_F_case']['required_sessions'][0]
                cases[owner]['event_links'].append({'source_row_ordinal':ordinal,'required_window_relation':n.relation(row['date'],first,n.LAST)})
        ivalue={'schema':'arv2-r335-offline-actions-metadata-links-v1-private','cases':cases,'all_original_rows':events}
        monkeypatch.setattr(n,'I_PIN',n.pin(n.canonical(ivalue)));monkeypatch.setattr(n,'M_PIN',n.pin(n.canonical(ownership)))
        return ivalue,copy.deepcopy(ownership),jraw
    return NS(rows=rows,dictionary=dictionary,values=values,ownership=ownership)

def analyze(fixture):return n.analyze(*fixture.values(),deadline=time.monotonic()+30)

def test_every_row_classified_under_exact_rules_and_all_rows_retained(fixture):
    summary,private=analyze(fixture)
    assert summary['rule_state_counts']['frozen_rule']==33 and summary['family_counts']['unresolved']==0
    assert summary['source_event_count']==len(private['all_original_events'])==33
    assert [entry['row'] for entry in private['all_original_events']]==fixture.rows
    assert summary['case_event_link_count']==33 and summary['cases'][0]['event_link_count']==33
    assert all(summary[key] is False for key in n.FALSE_FLAGS)
    assert n.validate_summary(summary)==summary

def test_ticker_pair_uses_from_to_literals_not_current_primary(fixture):
    summary,private=analyze(fixture)
    pair=next(pair for pair in private['all_pair_evidence'] if pair['family']=='ticker_change')
    assert pair['primary_current_dataset_ticker']=='S0' and pair['from_payload']==['OLD'] and pair['to_payload']==['NEW']
    assert pair['state']=='paired_metadata' and not pair['primary_is_asof_new_symbol_assumed']
    assert not pair['alias_or_identity_admitted'] and summary['pair_counts']['ticker_change']['state_counts']['paired_metadata']==1

@pytest.mark.parametrize('payload',['OLD NEW','OLD/NEW','old','OLD,NEW','..BAD',''])
def test_opaque_ticker_payload_is_never_split_normalized_or_admitted(fixture,payload):
    fixture.rows[0]['contraticker']=payload;summary,private=analyze(fixture)
    pair=next(pair for pair in private['all_pair_evidence'] if pair['family']=='ticker_change')
    assert pair['state']=='unsupported_payload' and pair['from_payload']==[payload]
    assert summary['pair_counts']['ticker_change']['state_counts']['paired_metadata']==0
    assert private['all_original_events'][0]['row']['contraticker']==payload

@pytest.mark.parametrize('change',['different_date','different_primary','missing_to'])
def test_no_pair_across_date_current_dataset_primary_or_missing_counterpart(fixture,change):
    if change=='different_date':fixture.rows[1]['date']='2024-01-04'
    elif change=='different_primary':fixture.rows[1]['ticker']='S1'
    else:fixture.rows[1]['action']='listed'
    summary,_=analyze(fixture)
    assert summary['pair_counts']['ticker_change']['state_counts']['paired_metadata']==0
    assert summary['pair_counts']['ticker_change']['state_counts']['missing_counterpart']>=1

@pytest.mark.parametrize('payload',['OLD','CONFLICT'])
def test_duplicate_and_conflicting_from_rows_are_preserved_and_unresolved(fixture,payload):
    fixture.rows[14]=event('tickerchangefrom',contraticker=payload)
    summary,private=analyze(fixture);pair=next(pair for pair in private['all_pair_evidence'] if pair['family']=='ticker_change')
    assert pair['state']=='duplicate_or_conflicting' and pair['from_row_ordinals']==[0,14]
    assert pair['duplicate_payload_present'] is (payload=='OLD')
    assert pair['conflicting_payload_present'] is (payload=='CONFLICT')
    assert len(private['all_original_events'])==33

def test_name_and_SIC_pairs_have_distinct_payloads_without_identity_inference(fixture):
    summary,private=analyze(fixture)
    groups={pair['family']:pair for pair in private['all_pair_evidence']}
    assert groups['name_change']['from_payload']==['Old Issuer'] and groups['name_change']['to_payload']==['New Issuer']
    assert groups['industry_change']['from_payload']==['1234'] and groups['industry_change']['to_payload']==['5678']
    assert not summary['same_security_or_share_class_proven']

def test_unit_common_merger_acquisition_and_related_security_are_never_aliases_or_cash(fixture):
    summary,private=analyze(fixture);families=summary['family_counts'];pred=summary['cases'][0]['predicate_counts']
    assert families['spac_unit_separation']==1 and families['merger']==2 and families['acquisition_consideration']==1
    assert pred['distinct_security_relationship']==5 and pred['spac_continuity_unproven']==2
    unit=private['all_original_events'][6]['normative_rule']
    assert unit['field_roles']=='current_common_primary_prior_unit_contra_distinct_instruments'
    assert not summary['alias_admitted'] and not summary['terminal_payoff_proven'] and not summary['synthetic_cash_created']

def test_listing_delisting_events_preserve_required_window_and_missing_dates(fixture):
    original=copy.deepcopy(fixture.ownership)
    fixture.rows[12]['date']='2023-12-02';summary,private=analyze(fixture)
    assert summary['cases'][0]['predicate_counts']['event_on_any_recorded_missing_date']==1
    assert summary['cases'][0]['predicate_counts']['delisting_inside_required_window']==1
    assert fixture.ownership==original and not summary['membership_intervals_changed']

@pytest.mark.parametrize('code',['unknown','Tickerchangefrom','tickerchangefrom suffix'])
def test_unreviewed_labels_never_inherit_semantics_from_words_or_case(fixture,code):
    fixture.rows[0]['action']=code;summary,_=analyze(fixture)
    assert summary['rule_state_counts']['unreviewed_code']==1 and summary['family_counts']['unresolved']==1

@pytest.mark.parametrize('change',['missing','ambiguous','pin_mismatch'])
def test_unbound_or_conflicting_generic_definition_never_uses_default_meaning(fixture,change):
    ordinal=n.RULES['tickerchangefrom'][0]
    if change=='missing':fixture.dictionary[ordinal]['indicator']='unreviewed'
    elif change=='ambiguous':fixture.dictionary[0]['indicator']='tickerchangefrom'
    else:fixture.dictionary[ordinal]['description']='Changed normative definition'
    summary,_=analyze(fixture)
    assert summary['rule_state_counts']['definition_'+change]==1 and summary['family_counts']['unresolved']==1

@pytest.mark.parametrize('role',['events','ownership','dictionary'])
def test_all_three_external_input_pins_are_required_before_analysis(fixture,role):
    ivalue,mvalue,raw=fixture.values()
    if role=='events':ivalue['all_original_rows'][0]['row']['name']='Changed'
    elif role=='ownership':mvalue['cases'][0]['original_row']['name']='Changed'
    else:raw+=b'\n'
    refuse('input_pin',lambda:n.analyze(ivalue,mvalue,raw,deadline=time.monotonic()+30))

def test_original_proof_failure_is_mapped_to_closed_semantics_error(fixture,monkeypatch):
    ivalue,mvalue,raw=fixture.values()
    def refused(*args):raise m.Refused('original_proof')
    monkeypatch.setattr(m,'original_proof',refused)
    refuse('original_proof',lambda:n.analyze(ivalue,mvalue,raw,deadline=time.monotonic()+30))

@pytest.mark.parametrize('change',['wrong_case','different_binding','different_current','required_end','source_role'])
def test_fixed_five_identity_and_required_window_cannot_be_changed(fixture,change):
    ivalue,mvalue,raw=fixture.values()
    if change=='wrong_case':ivalue['cases'][0]['case_ordinal']=True
    elif change=='different_binding':mvalue['cases'][0]['whole_binding_sha256']='0'*64
    elif change=='different_current':mvalue['cases'][0]['current_candidate_rows'].pop()
    elif change=='required_end':ivalue['cases'][0]['original_F_case']['required_sessions'][-1]='2026-10-12'
    else:mvalue['cases'][0]['original_required_demand']['source_role']='alternate'
    # Input authentication is separately covered; these mutations test semantics.
    n.I_PIN=n.pin(n.canonical(ivalue));n.M_PIN=n.pin(n.canonical(mvalue))
    with pytest.raises(n.Refused):n.analyze(ivalue,mvalue,raw,deadline=time.monotonic()+30)

@pytest.mark.parametrize('change',['row_order','owner','link_order','link_date_relation','alias'])
def test_all_source_event_owners_and_original_links_are_reconciled(fixture,change):
    ivalue,mvalue,raw=fixture.values()
    if change=='row_order':ivalue['all_original_rows'][0]['source_row_ordinal']=1
    elif change=='owner':ivalue['all_original_rows'][0]['primary_owner_case_ordinals']=[1]
    elif change=='link_order':ivalue['cases'][0]['event_links'].reverse()
    elif change=='link_date_relation':ivalue['cases'][0]['event_links'][0]['required_window_relation']='before_required_window'
    else:ivalue['all_original_rows'][0]['alias_admitted']=True
    n.I_PIN=n.pin(n.canonical(ivalue))
    with pytest.raises(n.Refused):n.analyze(ivalue,mvalue,raw,deadline=time.monotonic()+30)

@pytest.mark.parametrize('change',['acceptance','extra','bool','pair_count','distinct_security','family','rule','case_order'])
def test_public_summary_cannot_claim_acceptance_or_inconsistent_counts(fixture,change):
    summary,_=analyze(fixture)
    if change=='acceptance':summary['alias_admitted']=True
    elif change=='extra':summary['raw_ticker']='S0'
    elif change=='bool':summary['case_count']=True
    elif change=='pair_count':summary['pair_counts']['ticker_change']['state_counts']['paired_metadata']=99
    elif change=='distinct_security':summary['cases'][0]['predicate_counts']['distinct_security_relationship']=0
    elif change=='family':summary['family_counts']['listed']=1
    elif change=='rule':summary['rule_state_counts']['frozen_rule']=32
    else:summary['cases'].reverse()
    refuse('output',lambda:n.validate_summary(summary))

@pytest.mark.parametrize('deadline',[True,None,float('inf'),float('nan'),0])
def test_finite_bounded_deadline(deadline):refuse('deadline',lambda:n.budget(deadline))

def test_only_frozen_original_pure_helper_is_imported_no_operations():
    tree=ast.parse(Path(n.__file__).read_text());imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports.extend(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node,ast.ImportFrom):imports.append(node.module)
    assert set(imports)<={'collections','csv','datetime','decimal','hashlib','io','json','math','re','time','scripts'}
    assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('open','eval','exec') for node in ast.walk(tree))

def test_caller_owned_nested_objects_and_public_private_summaries_do_not_alias(fixture):
    ivalue,mvalue,raw=fixture.values();before=copy.deepcopy((ivalue,mvalue))
    public,private=n.analyze(ivalue,mvalue,raw,deadline=time.monotonic()+30)
    ivalue['all_original_rows'][0]['row']['name']='Caller mutation'
    mvalue['cases'][0]['original_row']['name']='Caller mutation'
    assert private['all_original_events'][0]['row']['name']==before[0]['all_original_rows'][0]['row']['name']
    assert private['cases'][0]['original_M_case']['original_row']['name']==before[1]['cases'][0]['original_row']['name']
    public['family_counts']['ticker_change']=999
    assert private['inspection']['family_counts']['ticker_change']==2

def test_joint_family_window_matrix_distinguishes_unit_event_from_name_event_with_equal_marginals(fixture):
    fixture.rows[6]['date']='2023-11-30'
    before,_=analyze(fixture);old=before['cases'][0]
    assert old['family_required_window_matrix']['spac_unit_separation']['before_required_window']==1
    fixture.rows[6]['date'],fixture.rows[2]['date']=fixture.rows[2]['date'],fixture.rows[6]['date']
    after,_=analyze(fixture);new=after['cases'][0]
    assert old['family_counts']==new['family_counts'] and old['required_window_relation_counts']==new['required_window_relation_counts']
    assert new['family_required_window_matrix']['spac_unit_separation']['before_required_window']==0
    assert new['family_required_window_matrix']['name_change']['before_required_window']==1
    assert not after['membership_intervals_changed'] and not after['same_security_or_share_class_proven']

def test_zero_event_cases_have_entire_joint_matrix_and_gap_counts_zero(fixture):
    public,_=analyze(fixture)
    for case in public['cases'][1:]:
        assert case['event_link_count']==0 and not any(case['family_recorded_gap_counts'].values())
        assert all(not any(row.values()) for row in case['family_required_window_matrix'].values())

@pytest.mark.parametrize('kind',['row_total','column_total','gap','zero_case'])
def test_joint_matrix_and_gap_count_inconsistencies_refuse(fixture,kind):
    public,_=analyze(fixture);case=public['cases'][0]
    if kind=='row_total':case['family_required_window_matrix']['spac_unit_separation']['before_required_window']=1
    elif kind=='column_total':
        matrix=case['family_required_window_matrix']['spac_unit_separation'];matrix['inside_required_window']-=1;matrix['before_required_window']+=1
    elif kind=='gap':case['family_recorded_gap_counts']['listing']=1
    else:public['cases'][1]['family_required_window_matrix']['listing']['before_required_window']=1
    refuse('output',lambda:n.validate_summary(public))
