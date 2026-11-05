"""Synthetic supplied-data query preparation; no production DATA or contact."""
import copy
from collections import defaultdict
import inspect
import json
import pickle
import struct
import time
import pytest
from scripts import arv2_r327_eodhd_fmp_query_plan as m
from tests.analyst_revisions_v2 import test_eodhd_crosswalk_gaps as sample
from tests.analyst_revisions_v2 import test_r298_sharadar_all_routes_v2 as supplied


def fail(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def test_public_context_authenticates_original_actuals_without_new_operations():
    context=m.source_context()
    assert context['I_fact_sha256']==m.I_FACT_SHA256
    assert context['I_summary']['selected_case_count']==5
    assert context['BB_summary']['original_proof_counts']=={'pass':6151,'refused':0,'unavailable':0}
    assert context['BA_authentication']['mapping']['row_count']==110346
    assert len(m.DATA_PLAN)==4 and sum(row['byte_count'] for row in m.DATA_PLAN.values())==45891902
    profile=m.profile_record()
    assert profile['all_four_whole_pins_before_any_DATA_JSON'] is True
    assert profile['BA_index_journal_and_source_metadata_not_reread'] is True
    assert all(profile[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('role',('producer','validator'))
@pytest.mark.parametrize('bad',(False,True,2))
def test_original_actual_exit_zero_is_not_boolean(monkeypatch,role,bad):
    fact=m.i_anchor.observed_fact();fact[role]['actual_exit']=bad
    monkeypatch.setattr(m.i_anchor,'observed_fact',lambda:fact)
    monkeypatch.setattr(m,'I_FACT_SHA256',m.digest(fact))
    fail('source_context',m.source_context)


@pytest.mark.parametrize('bad',(False,True,2))
def test_original_collector_zero_is_structural(monkeypatch,bad):
    fact=m.i_anchor.observed_fact();fact['collector_actual_exit_observed_by_tool']=bad
    monkeypatch.setattr(m.i_anchor,'observed_fact',lambda:fact)
    monkeypatch.setattr(m,'I_FACT_SHA256',m.digest(fact))
    fail('source_context',m.source_context)


def test_whole_byte_pins_precede_every_DATA_parse_and_source_semantics(monkeypatch):
    monkeypatch.setattr(m,'source_context',lambda:pytest.fail('source semantics before four pins'))
    monkeypatch.setattr(m,'_loads',lambda _:pytest.fail('DATA parsed before four pins'))
    fail('byte_pin',lambda:m.prepare(b'bad',b'bad',b'bad',b'bad'))


@pytest.mark.parametrize('seconds',(None,300,30))
def test_actual_legacy_BC_deadline_accepts_parent_bounded_cap(seconds):
    parent=None if seconds is None else time.monotonic()+seconds
    deadline=m._legacy_deadline(parent)
    assert 0<m.evidence.remaining(deadline)<=300
    if parent is not None:assert deadline<=parent


def test_expired_parent_refuses_before_DATA_or_public_context(monkeypatch):
    monkeypatch.setattr(m,'source_context',lambda:pytest.fail('context after deadline'))
    fail('deadline',lambda:m.prepare(b'',b'',b'',b'',deadline=time.monotonic()-1))


@pytest.fixture
def frames(monkeypatch):
    # The actual frozen frame and envelope decoders are exercised against
    # synthetic bytes. Contract literals are replaced only for this fixture.
    active=[sample.catalog('SYNTHETIC')];active[0]['Isin']=sample.isin(sample.cusip(100))
    lists=[m.canonical(active),m.canonical([])]
    bodies=[];all_rows=[]
    for offset in range(0,110346,1000):
        rows=[{'symbol':'SYNTHETIC.US','figi':sample.figi(1),'cusip':None,
            'isin':sample.isin(sample.cusip(100)),'lei':None,'cik':None}] * min(1000,110346-offset)
        all_rows.extend(rows)
        bodies.append(m.canonical({'meta':{'total':110346,'limit':1000,'offset':offset},'data':rows,'links':{'next':None}}))
    seed_parts=[*lists,bodies[0]];seed=b''.join(struct.pack('>Q',len(raw))+raw for raw in seed_parts)
    capture=b''.join(struct.pack('>Q',len(raw))+raw for raw in bodies[1:])
    monkeypatch.setattr(m.ba,'SOURCE_FRAME_PINS',tuple(m.pin(raw) for raw in seed_parts))
    monkeypatch.setattr(m.ba,'SOURCE_PLAN',{'old_frames':{'relative_path':'synthetic','byte_count':len(seed),'sha256':m.sha(seed)}})
    context={'BA_provider':{'body_pins':[m.pin(raw) for raw in bodies[1:]]},'BA_authentication':{
        'active':m.ba._record_observation(active,m.ba.LIST_FIELDS,time.monotonic()+100),
        'delisted':m.ba._record_observation([],m.ba.LIST_FIELDS,time.monotonic()+100),
        'mapping':m.ba._record_observation(all_rows,m.ba.MAPPING_FIELDS,time.monotonic()+100)}}
    return seed,capture,context,active


def test_three_seed_and110_new_frames_preserve_all111_pages_in_order(frames):
    seed,capture,context,active=frames
    a,d,rows=m._catalog(seed,capture,context,time.monotonic()+100)
    assert a==active and d==[] and len(rows)==110346
    assert m.ba._record_observation(rows,m.ba.MAPPING_FIELDS,time.monotonic()+100)==context['BA_authentication']['mapping']


@pytest.mark.parametrize('mode',('tail','header','body','truncated','order','frame_count'))
def test_every_frame_pin_and_exact_extent_precede_catalog_JSON(frames,monkeypatch,mode):
    seed,capture,context,_=frames;context=copy.deepcopy(context)
    if mode=='tail':capture+=b'x'
    elif mode=='header':capture=struct.pack('>Q',2**63)+capture[8:]
    elif mode=='body':capture=capture[:20]+bytes([capture[20]^1])+capture[21:]
    elif mode=='truncated':capture=capture[:-1]
    elif mode=='order':context['BA_provider']['body_pins'][:2]=reversed(context['BA_provider']['body_pins'][:2])
    else:context['BA_provider']['body_pins'].pop()
    monkeypatch.setattr(m.ba.catalog_schema,'checked_symbol_rows',lambda _:pytest.fail('catalog parsed before all frame pins'))
    fail('inventory' if mode=='frame_count' else 'framing',lambda:m._catalog(seed,capture,context,time.monotonic()+100))


def test_complete_mapping_ordered_hash_must_match_external_authentication(frames):
    seed,capture,context,_=frames;context=copy.deepcopy(context)
    context['BA_authentication']['mapping']['ordered_records_sha256']='0'*64
    fail('inventory',lambda:m._catalog(seed,capture,context,time.monotonic()+100))


@pytest.fixture
def case(monkeypatch):
    data=supplied.case(1);f,c=sample.figi(1),sample.cusip(100)
    data[1][0].update(figi=f,cusips=c);data[2][0].update(figi=f,cusips=c)
    data[0][0]=supplied.supplied.binding(data[1][0],1)
    _,private=supplied.m.join(*data,binding_contract=supplied.supplied.contract(data[0]))
    aa=private.private_record()['stocks'][0];binding=data[0][0];ISIN=sample.isin(c)
    source={'kind':'stock','ordinal':0,'binding':binding,'original_proof':'pass','owner':('stock',binding['security_id'],f),
        'figi':f,'tokens':[c],'original_tokens':[c],'AP_role':m.identity.fmt.NATIVE,'potential':True}
    old={'binding_ordinal':0,'binding':binding,'original_proof':'pass','validated_original_cusip_tokens':[c],
        'mapping_indices':[0],'status':'unresolved','reason':'mapping_identifier_invalid'}
    i_case={'case_ordinal':0,'whole_binding_sha256':m.digest(binding),'original_case':{'aa_stock':aa,'ac_stock':{'binding':binding}},
        'demand':{'binding_ordinal':0,'whole_binding_sha256':m.digest(binding),'potential':True}}
    mapping=[sample.mapping('SYNTHETIC.US',f,None,ISIN)]
    active=[sample.catalog('SYNTHETIC')];active[0]['Isin']=ISIN
    def rebuild():
        indexes=m.crosswalk._indexes(active,[],mapping,[source],None)
        indexes['all_mapping_ISIN']=defaultdict(list);indexes['all_catalog_ISIN']=defaultdict(list)
        for row in mapping:
            if m.crosswalk._isin(row.get('isin')):indexes['all_mapping_ISIN'][row['isin']].append(row)
        for ordinal,row in enumerate(active):
            if m.crosswalk._isin(row['Isin']):indexes['all_catalog_ISIN'][row['Isin']].append(('active',ordinal,row))
        return indexes
    return source,old,i_case,mapping,active,rebuild


def run_case(case):
    source,old,i_case,mapping,_,rebuild=case
    return m._case(source,old,i_case,rebuild(),mapping,time.monotonic()+100)


@pytest.mark.parametrize('raw',('missing',None,''))
def test_only_genuinely_absent_raw_CUSIP_prepares_exact_observed_ISIN(case,raw):
    if raw=='missing':case[3][0].pop('cusip')
    else:case[3][0]['cusip']=raw
    result=run_case(case)
    assert result['status']=='query_preparable_absent_raw_CUSIP' and result['blockers']==[]
    assert result['query_ISINs']==[case[3][0]['isin']]
    assert result['original_binding']==case[0]['binding']
    public=m.canonical(m._public_case(result))
    for value in (case[3][0]['isin'],case[0]['figi'],case[0]['tokens'][0],'SYNTHETIC'):
        assert value.encode() not in public


@pytest.mark.parametrize('value',('N/A',' ',False,'00000000',sample.cusip(200)))
def test_nonempty_placeholder_malformed_and_conflicting_raw_CUSIP_never_overridden(case,value):
    case[3][0]['cusip']=value;result=run_case(case)
    assert result['status']=='blocked' and result['query_ISINs']==[]
    assert ('conflicting_raw_CUSIP' if m.crosswalk._cusip(value) else 'nonempty_invalid_raw_CUSIP') in result['blockers']
    assert result['related_mapping_rows'][0]['row']['cusip']==value


def test_existing_exact_pair_is_preserved_without_redundant_FMP_query(case):
    case[3][0]['cusip']=case[0]['tokens'][0];case[1].update(status='matched_current_crosswalk',reason=None)
    result=run_case(case)
    assert result['status']=='already_exact_original_pair_observed' and result['query_ISINs']==[]


def test_different_valid_EOD_FIGI_cannot_be_repaired_by_valid_ISIN_or_FMP(case):
    case[3][0]['figi']=sample.figi(2);result=run_case(case)
    assert result['status']=='blocked' and 'different_EOD_FIGI' in result['blockers'] and not result['query_ISINs']


@pytest.mark.parametrize('field,value,blocker',[
    ('figi',None,'invalid_EOD_FIGI'),('symbol','bad symbol','invalid_EOD_symbol'),
    ('isin',None,'missing_or_invalid_ISIN'),('isin','US0000000000','missing_or_invalid_ISIN')])
def test_identifier_shape_failures_are_named_and_never_inferred(case,field,value,blocker):
    case[3][0][field]=value;result=run_case(case)
    assert result['status']=='blocked' and blocker in result['blockers']


def test_all_related_rows_survive_and_one_bad_row_blocks_favourable_row_selection(case):
    second=copy.deepcopy(case[3][0]);second['figi']=sample.figi(2);case[3].append(second);case[1]['mapping_indices'].append(1)
    result=run_case(case)
    assert len(result['related_mapping_rows'])==2 and result['status']=='blocked' and 'different_EOD_FIGI' in result['blockers']


@pytest.mark.parametrize('kind',('mapping_other_FIGI','mapping_other_symbol','mapping_null_FIGI','catalog_other_symbol','catalog_other_type'))
def test_global_exact_ISIN_ownership_indexes_include_non_candidate_bad_rows(case,kind):
    if kind.startswith('mapping'):
        row=copy.deepcopy(case[3][0])
        if kind=='mapping_other_FIGI':row['figi']=sample.figi(2)
        elif kind=='mapping_null_FIGI':row['figi']=None
        else:row['symbol']='OTHER.US'
        case[3].append(row)  # deliberately absent from this case's local refs
    else:
        row=copy.deepcopy(case[4][0]);row['Code']='OTHER' if kind=='catalog_other_symbol' else row['Code']
        if kind=='catalog_other_type':row['Type']='ETF'
        case[4].append(row)
    result=run_case(case)
    assert result['status']=='blocked' and ('global_mapping_ISIN_owner_conflict' if kind.startswith('mapping')
        else 'global_catalog_ISIN_owner_conflict') in result['blockers']


@pytest.mark.parametrize('field,value,blocker',[
    ('Currency','EUR','catalog_instrument_or_currency'),('Type','ETF','catalog_instrument_or_currency'),
    ('Isin',None,'catalog_ISIN_missing_or_invalid'),('Isin',sample.isin(sample.cusip(200)),'catalog_ISIN_disagreement')])
def test_catalog_type_currency_and_exact_ISIN_are_not_inferred(case,field,value,blocker):
    case[4][0][field]=value;result=run_case(case)
    assert result['status']=='blocked' and blocker in result['blockers']


def test_original_source_evidence_is_reconstructed_not_adopted_from_case_label(case):
    case[2]['original_case']['aa_stock']['original_row']['unused_fixture_column']='tampered'
    fail('source_proof',lambda:run_case(case))


def test_original_current_union_only_CUSIP_cannot_replace_original_vocabulary(case):
    case[1]['validated_original_cusip_tokens']=[sample.cusip(200)]
    fail('source_proof',lambda:run_case(case))


@pytest.fixture(scope='module')
def full_BB():
    # Construct all 6,151+8 binding records from the existing public synthetic
    # fixture; no private source leaf or production parser is opened.
    return sample.full_case.__wrapped__()


def test_all6151_and8_prior_match_results_are_reproduced_before_fixed_five(full_BB):
    context,record,mapping,active=full_BB
    sources,_=m._reproduce(record,active,[],mapping,{'BB_summary':context['BB_result']['crosswalk_summary'],
        'BB_result':context['BB_result']},time.monotonic()+100)
    assert len(sources)==6159 and sum(source['kind']=='stock' for source in sources)==6151


def test_BB_mapping_refs_cannot_be_changed_under_retained_disposition(full_BB):
    context,record,mapping,active=full_BB;record=copy.deepcopy(record)
    record['stocks'][0]['mapping_indices']=[]
    fail('mapping_reproduction',lambda:m._reproduce(record,active,[],mapping,
        {'BB_summary':context['BB_result']['crosswalk_summary'],'BB_result':context['BB_result']},time.monotonic()+100))


@pytest.fixture
def prepared(monkeypatch):
    # Isolate prepare's four-pin -> fixed-five -> private/closed-output flow.
    # Full-catalog decoding and full-BB reproduction are tested separately
    # above using their real frozen predicates, rather than mocked as proof.
    data=supplied.case(5)
    for index in range(5):
        data[1][index].update(figi=sample.figi(index+1),cusips=sample.cusip(index+100))
        data[2][index].update(figi=sample.figi(index+1),cusips=sample.cusip(index+100))
        data[0][index]=supplied.supplied.binding(data[1][index],5)
    _,p=supplied.m.join(*data,binding_contract=supplied.supplied.contract(data[0]));aa=p.private_record()
    sources=[];stocks=[];cases=[];mapping=[];active=[]
    for index,binding in enumerate(data[0]):
        f,c=binding['composite_figi'],sample.cusip(index+100);code='Q'+str(index)
        source={'kind':'stock','ordinal':index,'binding':binding,'original_proof':'pass','owner':('stock',binding['security_id'],f),
            'figi':f,'tokens':[c],'original_tokens':[c],'AP_role':m.identity.fmt.NATIVE,'potential':True}
        sources.append(source)
        stocks.append({'binding_ordinal':index,'binding':binding,'original_proof':'pass','validated_original_cusip_tokens':[c],
            'mapping_indices':[index],'status':'matched_current_crosswalk' if index==0 else 'unresolved',
            'reason':None if index==0 else 'mapping_identifier_invalid'})
        cases.append({'case_ordinal':index,'whole_binding_sha256':m.digest(binding),
            'original_case':{'aa_stock':aa['stocks'][index],'ac_stock':{'binding':binding}},
            'demand':{'binding_ordinal':index,'whole_binding_sha256':m.digest(binding),'potential':True}})
        mapping.append(sample.mapping(code+'.US',sample.figi(999) if index==2 else f,c if index==0 else None,sample.isin(c)))
        row=sample.catalog(code);row['Isin']=sample.isin(c);active.append(row)
    indexes=m.crosswalk._indexes(active,[],mapping,sources,None)
    i_raw=m.canonical({'cases':cases});bb_raw=m.canonical({'stocks':stocks,'funds':[]});seed_raw=b'synthetic seed';capture_raw=b'synthetic capture'
    monkeypatch.setattr(m,'DATA_PLAN',{role:{'relative_path':'synthetic/'+role,**m.pin(raw)} for role,raw in
        zip(('identity','crosswalk','seed','capture'),(i_raw,bb_raw,seed_raw,capture_raw),strict=True)})
    monkeypatch.setattr(m.identity.period,'NATIVE_WHOLE_BINDING_SHA256S',tuple(sorted(m.digest(row) for row in data[0])))
    context={'I_fact_sha256':'a'*64,'BB_fact_sha256':'b'*64,'BA_fact_sha256':'c'*64,'I_summary':{},'BB_summary':{},
        'BB_result':{},'inventory':{'synthetic':True},'period_sha256':'d'*64}
    monkeypatch.setattr(m,'source_context',lambda:copy.deepcopy(context))
    monkeypatch.setattr(m.identity,'validate_private_record',lambda record,**_:record)
    monkeypatch.setattr(m.evidence,'_decode_private',lambda *_:{'stocks':stocks,'funds':[]})
    mapping=mapping+[{}]*(110346-len(mapping))
    extra=sample.catalog('UNRELATED');extra['Isin']=None
    active=active+[extra]*(50668-len(active));delisted=[extra]*59979
    monkeypatch.setattr(m,'_catalog',lambda *_:(active,delisted,mapping))
    monkeypatch.setattr(m,'_reproduce',lambda *_:(sources,indexes))
    return m.prepare(i_raw,bb_raw,seed_raw,capture_raw,deadline=time.monotonic()+100)


def test_prepare_retains_all_five_including_blocked_and_already_linked(prepared):
    summary,private=prepared;record=private.private_record()
    assert summary['selected_case_count']==len(record['cases'])==5
    assert summary['status_counts']=={'already_exact_original_pair_observed':1,'blocked':1,'query_preparable_absent_raw_CUSIP':3}
    assert summary['unique_search_ISIN_count']==len(record['requests'])==3
    assert record['cases'][2]['status']=='blocked' and record['cases'][2]['query_ISINs']==[]
    assert all(row['endpoint']=='https://financialmodelingprep.com/stable/search-isin' for row in record['requests'])
    assert m.validate_private_record(record,expected_summary=summary)==record
    assert all(summary[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('field',('original_stock_count','own_fund_count','selected_case_count','complete_mapping_row_count','unique_search_ISIN_count'))
def test_closed_summary_integer_counts_refuse_boolean(prepared,field):
    summary,_=prepared;value=copy.deepcopy(summary);value[field]=True
    fail('summary',lambda:m.validate_summary(value))


@pytest.mark.parametrize('issue',('case_omitted','claim_changed','query_count','row_hash','extra_private_field','query_case_omitted'))
def test_private_plan_pin_claim_queries_and_complete_rows_are_bound(prepared,issue):
    summary,private=prepared;record=private.private_record();changed=copy.deepcopy(summary)
    if issue=='case_omitted':record['cases'].pop()
    elif issue=='claim_changed':record['cases'][0]['original_binding']['issuer_id']='changed'
    elif issue=='query_count':record['cases'][1]['query_ISINs']=[]
    elif issue=='row_hash':record['cases'][1]['related_mapping_rows'][0]['row']['cusip']='N/A'
    elif issue=='extra_private_field':record['cases'][0]['unexpected']=True
    else:record['requests'][0]['case_ordinals']=[]
    # Recompute the outer private pin to test semantic joins independently.
    changed['private_payload_pin']=m.pin(m.canonical(record))
    fail('private',lambda:m.validate_private_record(record,expected_summary=changed))


def test_query_plan_finite_failures_never_echo_opaque_exception_text():
    assert m.finite(RuntimeError('sensitive synthetic row'))=='unknown'


def test_closed_private_wrapper_is_immutable_redacted_and_unpicklable(case):
    raw=m.canonical({'synthetic':run_case(case)})
    private=m.PrivateFmpQueryPlan(raw,'a'*64)
    assert private.private_record()==json.loads(raw) and 'SYNTHETIC' not in repr(private)
    with pytest.raises(TypeError):private.sha256='x'
    with pytest.raises(TypeError):pickle.dumps(private)


def test_source_has_no_operational_entrypoint_or_generic_callback_or_credential_lookup():
    source=inspect.getsource(m)
    for text in ('def main(', 'def run(', 'load_key(', 'requests.get(', 'requests.post(', 'open(', 'eval(', 'callback('):
        assert text not in source
    assert 'financialmodelingprep.com/stable/search-isin' in source
