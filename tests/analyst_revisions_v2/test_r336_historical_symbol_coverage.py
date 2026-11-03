"""Synthetic typed leads and raw daily coverage; never actual N/USB data."""
import ast
import copy
from dataclasses import replace
from decimal import Decimal
import importlib.util
from pathlib import Path
import pickle
import time
from types import SimpleNamespace as NS
import pytest
from scripts import arv2_r336_historical_symbol_coverage as o

def refuse(code,call):
    with pytest.raises(o.Refused) as caught:call()
    assert o.finite(caught.value)==code

@pytest.fixture
def fixture(monkeypatch):
    # Reuse only the frozen N test's synthetic object factory, no fixture files,
    # shared conftest, source DATA or operational function is invoked.
    path=Path(__file__).with_name('test_r336_action_semantics.py')
    spec=importlib.util.spec_from_file_location('synthetic_N_fixture_only',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    seed=module.fixture.__wrapped__(monkeypatch)
    def value():
        ivalue,mvalue,jraw=seed.values()
        for ordinal,case in enumerate(ivalue['cases']):
            retained=case['original_F_case'];count=o.semantics.original.GEOMETRY[ordinal][1]
            retained['potential_reference_sessions']=retained['required_sessions'][:count]
            for candidate in retained['candidates']:
                candidate.update(archive='synthetic/Original.zip',container_pin=o.pin(b'prior archive'),
                  member_name='S'+str(ordinal)+'_full_1day_UNADJUSTED.txt',member_pin=o.pin(b'prior source'))
        monkeypatch.setattr(o.semantics,'I_PIN',o.pin(o.canonical(ivalue)))
        n_public,n_private=o.semantics.analyze(ivalue,mvalue,jraw,deadline=time.monotonic()+30)
        monkeypatch.setattr(o,'N_PIN',o.pin(o.canonical(n_private)))
        return n_private
    return NS(rows=seed.rows,value=value)

def planned(fixture):return o.plan(fixture.value(),deadline=time.monotonic()+30)

def test_role_leads_preserve_origins_and_transport_only_deduplicates(fixture):
    public,private=planned(fixture)
    assert public['case_count']==5 and public['transport_token_count']==7
    assert public['lead_record_count']==12 and public['eligible_lead_count']==7
    assert len(private['cases'])==5 and private['cases'][2]['lead_ordinals']==[]
    assert len(private['lead_records'])==12 and len(private['transport_specs'])==7
    assert all(lead['alias_or_identity_admitted'] is False for lead in private['lead_records'])
    assert all(public[key] is False for key in o.FALSE_FLAGS)
    assert all(case['prior_E_candidates'][0]['container_pin']==o.pin(b'prior archive') for case in private['cases'])
    assert o.validate_plan_summary(public)==public

@pytest.mark.parametrize('symbol',['S0','S1','S1-DELISTED'])
def test_global_previously_E_scanned_symbols_excluded_even_under_another_case(fixture,symbol):
    fixture.rows[0]['contraticker']=symbol;public,private=planned(fixture)
    lead=next(lead for lead in private['lead_records'] if lead['symbol_role']=='historical_ticker_from')
    assert lead['case_ordinal']==0 and lead['excluded_E'] and not lead['eligible']
    assert symbol not in private['transport_tokens'] and public['excluded_E_lead_count']>=6

def test_F_listing_only_counterparty_is_still_a_new_typed_price_lead(fixture):
    fixture.rows[7]['contraticker']='C0';_,private=planned(fixture)
    assert 'C0' in private['transport_tokens']
    lead=next(lead for lead in private['lead_records'] if lead['raw_symbol']=='C0')
    assert lead['symbol_role']=='merger_non_survivor_counterparty' and lead['current_candidate_ticker_literal_match']

def test_joint_role_counts_show_original_literal_as_unit_and_acquired_without_equating_instruments(fixture):
    fixture.rows[6]['contraticker']='S0';public,private=planned(fixture)
    cells={(row['family'],row['symbol_role']):row for row in public['cases'][0]['family_symbol_role_matrix']}
    assert cells['spac_unit_separation','prior_unit_counterparty']['original_ticker_match_count']==1
    assert cells['acquisition_consideration','acquired_primary_security']['original_ticker_match_count']==1
    assert not public['unit_common_equivalence_admitted'] and not public['terminal_payoff_proven']
    assert private['cases'][0]['required_sessions'][0]=='2023-12-01'

def test_typed_event_window_relations_are_joint_with_family_and_role(fixture):
    fixture.rows[6]['date']='2023-11-30';public,_=planned(fixture)
    cell=next(row for row in public['cases'][0]['family_symbol_role_matrix'] if row['symbol_role']=='prior_unit_counterparty')
    assert cell['family']=='spac_unit_separation' and cell['window_relation_counts']['before_required_window']==1

def test_unresolved_pair_tokens_retained_privately_but_never_price_searched(fixture):
    fixture.rows[1]['date']='2024-01-04';public,private=planned(fixture)
    assert 'OLD' not in private['transport_tokens'] and 'NEW' not in private['transport_tokens']
    leads=[lead for lead in private['lead_records'] if lead['family']=='ticker_change']
    assert len(leads)==2 and all(lead['unresolved_pair'] and not lead['eligible'] for lead in leads)
    assert len(private['unresolved_pair_evidence'])==2 and public['unresolved_pair_lead_count']==2

def test_supported_digit_first_token_has_no_guessed_current_archive(fixture):
    fixture.rows[0]['contraticker']='1OLD';_,private=planned(fixture)
    spec=next(spec for spec in private['transport_specs'] if spec['token']=='1OLD')
    assert spec['current_letter'] is None and spec['member_aliases']==['1OLD','1OLD-DELISTED']

def test_explicit_delisted_token_suffix_is_idempotent(fixture):
    fixture.rows[0]['contraticker']='OLD-DELISTED';_,private=planned(fixture)
    spec=next(spec for spec in private['transport_specs'] if spec['token']=='OLD-DELISTED')
    assert spec['member_aliases']==['OLD-DELISTED']

@pytest.mark.parametrize('symbol',['OLD NEW','OLD/NEW','old','RELATED,OTHER',''])
def test_all_opaque_role_literals_retained_unsplit_and_ineligible(fixture,symbol):
    fixture.rows[10]['contraticker']=symbol;public,private=planned(fixture)
    record=next(row for row in private['lead_records'] if row['symbol_role']=='related_security_counterparty')
    assert record['raw_symbol']==symbol and not record['supported'] and not record['eligible']
    assert symbol not in private['transport_tokens'] and public['unsupported_lead_count']>=1

def test_duplicate_role_origins_are_never_collapsed_but_transport_is_unique(fixture):
    fixture.rows[7]['contraticker']='RECEIVED';_,private=planned(fixture)
    spec=next(spec for spec in private['transport_specs'] if spec['token']=='RECEIVED')
    assert len(spec['lead_links'])==2
    assert {private['lead_records'][link['lead_ordinal']]['symbol_role'] for link in spec['lead_links']}=={
      'merger_non_survivor_counterparty','received_security_counterparty'}

@pytest.mark.parametrize('cap,code',[('MAX_LEADS','lead_bound'),('MAX_TOKENS','token_bound')])
def test_lead_and_transport_caps_refuse_without_truncating(fixture,monkeypatch,cap,code):
    monkeypatch.setattr(o,cap,1);refuse(code,lambda:planned(fixture))

def test_exact_N_pin_checked_before_any_evidence_projection(fixture):
    value=fixture.value();value['cases'][0]['original_I_case']['original_F_case']['original_row']['name']='changed'
    refuse('input_pin',lambda:o.plan(value,deadline=time.monotonic()+30))

@pytest.mark.parametrize('kind',['case','whole','required','references','prior_pin','role','pair_payload','N_policy'])
def test_fixed_case_source_geometry_and_normative_provenance_refuse(fixture,monkeypatch,kind):
    value=fixture.value();case=value['cases'][0]
    if kind=='case':case['case_ordinal']=True
    elif kind=='whole':case['whole_binding_sha256']='0'*64
    elif kind=='required':case['original_I_case']['original_F_case']['required_sessions'].pop()
    elif kind=='references':case['original_I_case']['original_F_case']['potential_reference_sessions'].pop()
    elif kind=='prior_pin':case['original_I_case']['original_F_case']['candidates'][0]['member_pin']['byte_count']=True
    elif kind=='role':value['all_original_events'][6]['normative_rule']['field_roles']='alias'
    elif kind=='pair_payload':next(group for group in value['all_pair_evidence'] if group['family']=='ticker_change')['from_payload']=['FORGED']
    else:value['normative_policy_sha256']='0'*64
    monkeypatch.setattr(o,'N_PIN',o.pin(o.canonical(value)))
    with pytest.raises(o.Refused):o.plan(value,deadline=time.monotonic()+30)

@pytest.mark.parametrize('kind',['impossible_role','eligible_lower_bound','zero_tokens','bool','raw_key','window_count'])
def test_public_plan_truth_and_joint_schema_refuse_forgery(fixture,kind):
    public,_=planned(fixture);cell=public['cases'][0]['family_symbol_role_matrix'][0]
    if kind=='impossible_role':cell['symbol_role']='prior_unit_counterparty'
    elif kind=='eligible_lower_bound':
        for row in public['cases'][0]['family_symbol_role_matrix']:row['eligible_count']=0
        public['eligible_lead_count']=public['cases'][0]['eligible_lead_count']=0;public['transport_token_count']=0
    elif kind=='zero_tokens':public['transport_token_count']=0
    elif kind=='bool':public['case_count']=True
    elif kind=='raw_key':cell['raw_symbol']='SECRET'
    else:cell['window_relation_counts']['before_required_window']+=1
    refuse('output',lambda:o.validate_plan_summary(public))

def raw_line(day,volume='10',ending=b'\n',ohlc='10,12,9,11'):
    return (day+','+ohlc+','+volume).encode()+ending

def assessed(raw,required=('2025-01-02','2025-01-03'),refs=('2025-01-02',),ticker='TEST'):
    return o.assess_member(raw,expected_pin=o.pin(raw),member_name=ticker+'_full_1day_UNADJUSTED.txt',expected_ticker=ticker,
      required_sessions=required,reference_sessions=refs)

def test_fractional_and_integer_volumes_are_exact_Decimals_and_every_raw_byte_retained():
    raw=raw_line('2025-01-02','00010.500',b'\r\n')+raw_line('2025-01-03','12.000',b'')
    public,private=assessed(raw);series=private['opaque_series'];rows=o.private_rows(series);index=o.private_member_index(private)
    assert rows[0].volume==Decimal('10.500') and rows[0].volume.as_tuple().exponent==-3
    assert all(type(row.volume) is Decimal for row in rows)
    assert public['fractional_volume_row_count']==public['integer_volume_row_count']==1
    assert o.private_original_bytes(series)==raw and index['row_offsets']==[0,len(raw_line('2025-01-02','00010.500',b'\r\n')),len(raw)]
    assert not public['volume_units_admitted'] and not public['volume_precision_admitted']

def test_missing_reference_and_held_window_sets_remain_separate_no_union():
    first=raw_line('2025-01-02');second=raw_line('2025-01-03')
    p1,r1=assessed(first);p2,r2=assessed(second)
    assert not p1['observed_date_coverage_complete'] and not p2['observed_date_coverage_complete']
    assert r1['missing_required_sessions']==('2025-01-03',) and r1['missing_reference_sessions']==()
    assert r2['missing_required_sessions']==r2['missing_reference_sessions']==('2025-01-02',)

def test_nonrequired_source_rows_are_validated_and_preserved_without_drop():
    raw=raw_line('2025-01-01')+raw_line('2025-01-02')+raw_line('2025-01-03')
    public,private=assessed(raw);assert public['row_count']==3 and len(o.private_rows(private['opaque_series']))==3
    invalid=raw_line('2025-01-01',ohlc='0,12,0,11')+raw_line('2025-01-02')+raw_line('2025-01-03')
    with pytest.raises(o.Refused):assessed(invalid)

@pytest.mark.parametrize('raw',[b'',b'header,open,high,low,close,volume\n',raw_line('2025-01-02','NaN'),
 raw_line('2025-01-02','Infinity'),raw_line('2025-01-02','-1'),raw_line('2025-01-02','1e3'),
 raw_line('2025-01-02','1',ohlc='10,9,8,11'),raw_line('2025-01-02','1',ohlc='10,12,9,0'),
 raw_line('2025-01-02')+raw_line('2025-01-02'),raw_line('2025-01-03')+raw_line('2025-01-02'),
 b'2025-01-02,10,12,9,11,',b'2025-01-02,10,12,9,11,1\r',raw_line('2025-01-02')+b'\n',
 b'2025-01-02,10,12,9,11,\xff\n',raw_line('2025-01-02 09:30:00')])
def test_financial_date_encoding_and_complete_record_guards_remain_strict(raw):
    with pytest.raises(o.Refused):assessed(raw)

def test_actual_mixed_separator_structural_signature_is_supported_without_normalization():
    from datetime import date,timedelta
    raw=b''.join(raw_line((date(2020,1,1)+timedelta(days=i)).isoformat(),'1.5' if i%2 else '2',b'\r\n' if i<5 else b'\n') for i in range(1341))
    public,private=assessed(raw,required=('2020-01-01',),refs=())
    evidence=public['line_ending_evidence'];assert evidence['LF_count']==1341 and evidence['CRLF_count']==5
    assert evidence['line_endings_supported'] and not evidence['line_endings_consistent']
    assert o.private_original_bytes(private['opaque_series'])==raw

@pytest.mark.parametrize('field,value',[('volume',True),('volume',1),('volume',Decimal('NaN')),('close',Decimal('NaN')),('close',Decimal('99'))])
def test_opaque_series_cannot_forge_rows_after_source_authentication(field,value):
    _,private=assessed(raw_line('2025-01-02')+raw_line('2025-01-03'));series=private['opaque_series']
    bars=(replace(series._rows[0],**{field:value}),*series._rows[1:]);forged=replace(series,_rows=bars)
    refuse('series',lambda:o.private_rows(forged))

def test_original_bytes_offsets_and_pickle_boundary_cannot_be_forged():
    raw=raw_line('2025-01-02')+raw_line('2025-01-03');_,private=assessed(raw);series=private['opaque_series']
    refuse('series',lambda:o.private_rows(replace(series,_offsets=(0,1,len(raw)))))
    assert '2025' not in repr(series) and '10' not in repr(series._rows[0])
    with pytest.raises(TypeError):pickle.dumps(series)
    with pytest.raises(TypeError):pickle.dumps(series._rows[0])

@pytest.mark.parametrize('kind',['extra_lexical','bool_lexical','bad_ending','row_count','fraction_count','acceptance'])
def test_public_coverage_closed_lexical_types_and_cardinality_are_enforced(kind):
    public,_=assessed(raw_line('2025-01-02')+raw_line('2025-01-03'))
    if kind=='extra_lexical':public['line_ending_evidence']['raw_symbol']='SECRET'
    elif kind=='bool_lexical':public['line_ending_evidence']['bare_CR_count']=False
    elif kind=='bad_ending':public['line_ending_evidence']['ends_CRLF']=True
    elif kind=='row_count':
        public['row_count']=public['integer_volume_row_count']=1
        public['line_ending_evidence']['physical_record_count']=1;public['line_ending_evidence']['LF_count']=1
    elif kind=='fraction_count':public['fractional_volume_row_count']=1
    else:public['price_input_admitted']=True
    refuse('output',lambda:o.validate_coverage(public))

@pytest.mark.parametrize('required,refs',[((),()),(('2025-01-03','2025-01-02'),()),(('2025-01-02','2025-01-02'),()),
 (('2025-01-02',),('2025-01-03',)),(('bad',),())])
def test_required_and_reference_calendars_are_explicit_not_silently_fixed(required,refs):
    with pytest.raises(o.Refused):assessed(raw_line('2025-01-02'),required=required,refs=refs)

def function_ast(path,name):
    raw=path.read_text();tree=ast.parse(raw);node=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==name)
    return ast.dump(node,include_attributes=False)

@pytest.mark.parametrize('name',['_number','_timestamp','_session','_calendar','line_ending_evidence'])
def test_unmodified_financial_calendar_and_separator_primitives_match_frozen_M3(name):
    previous=Path(o.__file__).with_name('arv2_r335_firstrate_prices_v3.py')
    assert function_ast(Path(o.__file__),name)==function_ast(previous,name)

def test_M3_row_parser_exact_inverse_only_changes_Decimal_volume_requirement():
    previous=Path(o.__file__).with_name('arv2_r335_firstrate_prices_v3.py').read_text();current=Path(o.__file__).read_text()
    pnode=next(node for node in ast.parse(previous).body if isinstance(node,ast.FunctionDef) and node.name=='_rows')
    node=next(node for node in ast.parse(current).body if isinstance(node,ast.FunctionDef) and node.name=='_rows')
    old=ast.get_source_segment(previous,pnode);new=ast.get_source_segment(current,node)
    assert new.replace("require(volume.is_finite() and volume >= 0, 'volume')","require(volume >= 0 and volume == volume.to_integral_value(), 'volume')").replace('close, volume))','close, int(volume)))')==old

def test_only_selected_pure_semantics_dependency_and_stdlib_no_IO_or_operation_import():
    tree=ast.parse(Path(o.__file__).read_text())
    roots=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):roots.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node,ast.ImportFrom):roots.add(node.module.split('.')[0])
    assert roots<={'collections','dataclasses','datetime','decimal','hashlib','json','math','re','time','scripts'}
    assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('open','exec','eval') for node in ast.walk(tree))
