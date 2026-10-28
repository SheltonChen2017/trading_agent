"""Pure fixed-five EOD/FMP query preparation over supplied authenticated DATA.

FMP requests are only prospective transport plans. Neither an ISIN nor an FMP
symbol replaces the original composite FIGI, original CUSIP or original binding.
All five cases and every related EOD row survive, including blocked cases.
"""
from collections import Counter, defaultdict
import json
import math
import re
import struct
import time
from types import SimpleNamespace

from scripts import arv2_r327_available_history_identity as identity
from scripts import inspect_arv2_r327_available_history_identity as i_caller
from scripts import arv2_r327_i_source_binding as i_anchor
from scripts import read_arv2_r298_eodhd_crosswalk_gaps as evidence

bb,ba,crosswalk=evidence.bb,evidence.ba,evidence.crosswalk
canonical,sha=identity.canonical,identity.sha
SCHEMA='arv2-r327-offline-fixed-five-EODHD-FMP-query-plan-j-v1'
PRIVATE_SCHEMA=SCHEMA+'-private'
MAX_PRIVATE,MAX_SUMMARY,MAX_REFERENCES=16*1024*1024,131072,100000
LEGACY_BUDGET_SECONDS=300
I_FACT_SHA256='8fd5f90a0990b82a08f18a5037a54ed772c9c8c033bd2430501bdfd88620874e'
DATA_PLAN={
 'identity':{'relative_path':'artifacts/analyst_revisions_v2/newrule_available_history_identity/R327-20261027-I/identity-demand-private.json',
  'byte_count':4984462,'sha256':'c85ae5ddf2e918d194f6aa2939ee1249229d0989f75c334ef92ea793b61b711d'},
 'crosswalk':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_crosswalk/R326-20261027-BB/crosswalk-private.json',
  'byte_count':13445076,'sha256':'5006dc2f1313d02c18f521172e2e454ca190a0191e2f85799b54a9d7d963d753'},
 'seed':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_catalog/R326-20261027-BA/seed-bodies.bin',
  'byte_count':16140080,'sha256':'02d64c177446409f43f6f443cda77afa4c6e9503ebb17844a9910a52b1093005'},
 'capture':{'relative_path':'artifacts/analyst_revisions_v2/newrule_eodhd_catalog/R326-20261027-BA/mapping-bodies.bin',
  'byte_count':11322284,'sha256':'1b601920ea0bf26c2f7354b99276cdd88d0e9f979b4337fa8badcb5a85fe8596'}}
SOURCE_PINS={
 'scripts/arv2_r327_available_history_identity.py':'e8940f07f62015e185f159ef7469955f72945efb7da6ca800c4d491ea7b10ac1',
 'scripts/inspect_arv2_r327_available_history_identity.py':'70b171d141798951d4a136c92e131454a4eec58f8ee6ba7ebab8a737a919250f',
 'scripts/arv2_r327_i_source_binding.py':'44405001183804020d8b211d79846d8ea70019758059cc73878cca883bac6416',
 'scripts/read_arv2_r298_eodhd_crosswalk_gaps.py':'a80a0d784cee31cf1778f135f411e5e859f44f36fd1d26dba7f3b6b2e8c753b8',
 'scripts/arv2_r298_bb_source_binding.py':'8aa1f5c9379f94275535c158c61c791ee482ba49fa01be299bbdd2b3ed921b5c',
 'scripts/prepare_arv2_r298_eodhd_crosswalk.py':'daec25bbe62c5855e0b21420f695f9816a87093f41c2f19f83452393abe66ab6',
 'scripts/arv2_r298_ba_source_binding.py':'fdc6cd8eb38a017961f67b351ae525e280e3e8bd6c141a1af7710c7bf27dc0d4',
 'scripts/run_arv2_r298_eodhd_catalog_continuation.py':'8eb6b92db6c8833998cd2fef4388091f8e65c6dbc8e0a77a79f86d9b2d4dc6e7',
 'scripts/arv2_r298_eodhd_crosswalk.py':'39464645b7acb8187eac2209e7e994d74ddd3c077911cb32d1a9c1820ffd6843',
 'scripts/arv2_r298_eodhd_catalog_schema_v2.py':'ad0c34e95c29c909bcb35f479fbfbb6b4580cbad36d81ab1b1bbdbba9c0b194c'}
FALSE_FLAGS={'provider_contact':False,'credential_access':False,'QC_contact':False,'Safari_access':False,
 'old_control_read':False,'old_operation_replayed':False,'fresh_genuine_package_authenticated':False,
 'FMP_request_dispatched':False,'FMP_profile_observed':False,'FMP_endpoint_entitlement_proven':False,
 'raw_CUSIP_overridden':False,'CUSIP_fabricated_or_repaired':False,'ISIN_slice_used_as_CUSIP':False,
 'ticker_used_as_cross_vendor_identity':False,'original_FIGI_replaced':False,'original_identifiers_rewritten':False,
 'current_vendor_alias_created':False,'new_route_admitted':False,'source_assignments_changed':False,
 'source_or_processing_rights_granted':False,'price_acquired':False,'price_input_admitted':False,
 'price_coverage_proven':False,'known_native_gap_resolved':False,'point_in_time_proven':False,
 'permanent_master_proven':False,'formal_forward_ready':False,'paper_or_live_ready':False,'licensed_values_disclosed':False}
STATUSES=frozenset(('query_preparable_absent_raw_CUSIP','already_exact_original_pair_observed','blocked'))
BLOCKERS=frozenset(('original_CUSIP_unavailable','original_owner_collision','no_related_mapping','mapping_fields_unknown',
 'invalid_EOD_symbol','invalid_EOD_FIGI','different_EOD_FIGI','nonempty_invalid_raw_CUSIP','conflicting_raw_CUSIP',
 'missing_or_invalid_ISIN','multiple_ISINs','multiple_EOD_symbols','catalog_symbol_missing','catalog_identity_ambiguous',
 'catalog_instrument_or_currency','catalog_ISIN_missing_or_invalid','catalog_ISIN_disagreement',
 'global_mapping_ISIN_owner_conflict','global_catalog_ISIN_owner_conflict'))
RAW_STATES=('missing','null','empty','nonempty_invalid','valid_original','valid_other')
FINITE=frozenset(('deadline','source_context','byte_pin','json','inventory','framing','private','source_proof',
 'mapping_reproduction','reference_bound','case','private_bound','summary','unknown'))


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    if len(args)==1 and type(args[0]) is str and args[0] in FINITE:return args[0]
    for module,code in ((identity,'private'),(evidence,'private'),(bb,'source_context'),(ba,'inventory'),(crosswalk,'mapping_reproduction')):
        if type(error) is module.Refused:return 'deadline' if module.finite(error)=='deadline' else code
    return 'unknown'


def digest(value):return sha(canonical(value))
def pin(raw):return {'byte_count':len(raw),'sha256':sha(raw)}
def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def _budget(deadline):
    if deadline is not None:require(type(deadline) in (int,float) and math.isfinite(deadline) and time.monotonic()<deadline,'deadline')


def _legacy_deadline(deadline):
    _budget(deadline);limit=time.monotonic()+LEGACY_BUDGET_SECONDS
    return limit if deadline is None else min(deadline,limit)


def _loads(raw):
    def pairs(items):
        value={}
        for key,item in items:require(key not in value,'json');value[key]=item
        return value
    try:
        value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(Refused('json')))
        require(canonical(value)==raw,'json');return value
    except Refused:raise
    except (ValueError,TypeError,UnicodeError,RecursionError):raise Refused('json') from None


def _source_context():
    fact=i_anchor.observed_fact();require(digest(fact)==I_FACT_SHA256,'source_context')
    require(fact['caller_sha256']==SOURCE_PINS['scripts/inspect_arv2_r327_available_history_identity.py']
        and fact['private_data']==DATA_PLAN['identity']
        and fact['expected_head']=='60f76c0a5ed24703753117f5e4517e0357186043'
        and type(fact['collector_actual_exit_observed_by_tool']) is int and fact['collector_actual_exit_observed_by_tool']==0,
        'source_context')
    args=SimpleNamespace(expected_head=fact['expected_head'],caller_sha256=fact['caller_sha256'],profile_sha256=fact['caller_profile_sha256'])
    binding=i_caller.binding(args);result=fact['result']
    report=pin(canonical({**binding,'result':result}));require(report==fact['report_pin'],'source_context')
    raw=canonical({'binding':binding,'outcome':{'result':result,'report':report}})+b'\n'
    i_caller.validate_output(raw,0,args)
    require(pin(raw)==fact['public_envelope_pin'] and result['private_pin']=={key:DATA_PLAN['identity'][key] for key in ('byte_count','sha256')},'source_context')
    for role in ('producer','validator'):
        identity._zero(fact[role]);require(fact[role]['stdout_bytes']==len(raw) and fact[role]['stdout_sha256']==sha(raw),'source_context')
    require(fact['technical_observation_authenticated'] is True,'source_context')
    for key in ('new_operation_or_read_granted','source_or_price_admission_granted','known_native_gap_resolved',
        'old_gap_case_attributed','original_identifiers_rewritten','source_assignments_changed','point_in_time_proven',
        'permanent_master_proven','formal_forward_ready','paper_or_live_ready'):require(fact[key] is False,'source_context')
    prior=evidence.source_context();ba_context=prior['BA_context'];provider=ba_context['provider']
    require(DATA_PLAN['crosswalk']==evidence.DATA_PLAN['crosswalk']
        and DATA_PLAN['seed']==bb.CATALOG_PLAN['seed'] and DATA_PLAN['capture']==bb.CATALOG_PLAN['capture']
        and provider['capture_pin']=={key:DATA_PLAN['capture'][key] for key in ('byte_count','sha256')},'source_context')
    return {'I_fact_sha256':I_FACT_SHA256,'BB_fact_sha256':prior['BB_fact_sha256'],
        'BA_fact_sha256':ba_context['BA_fact_sha256'],'I_summary':result['identity_summary'],
        'BB_summary':prior['BB_result']['crosswalk_summary'],'BB_result':prior['BB_result'],
        'BA_source':ba_context['source'],'BA_provider':provider,'BA_authentication':ba_context['authentication'],
        'inventory':bb.inventory_context(ba_context),'period_sha256':result['identity_summary']['period_sha256']}


def source_context():
    # Frozen validators remain immutable. Their finite refusals belong to
    # this new public-source boundary when reached through this contract.
    try:return _source_context()
    except Refused:raise
    except (identity.Refused,i_caller.Refused,evidence.Refused,bb.Refused,ba.Refused,crosswalk.Refused,
        KeyError,TypeError,AttributeError,OverflowError):raise Refused('source_context') from None


def profile_record():
    context=source_context()
    return {'schema':SCHEMA,'data_plan':DATA_PLAN,'source_pins':SOURCE_PINS,'source_context_sha256':digest(context),
      'maximum_private_bytes':MAX_PRIVATE,'maximum_summary_bytes':MAX_SUMMARY,'maximum_related_references':MAX_REFERENCES,
      'legacy_predicate_budget_seconds':LEGACY_BUDGET_SECONDS,'parent_deadline_never_extended':True,
      'purpose':'offline_all_five_EOD_original_FIGI_and_original_CUSIP_claims_to_bounded_future_FMP_ISIN_profile_queries',
      'all_four_whole_pins_before_any_DATA_JSON':True,'all111_mapping_frames_and_complete_catalog_inventory_authenticated':True,
      'BA_index_journal_and_source_metadata_not_reread':True,'all6151_original_bindings_and8_funds_revalidated_from_BB':True,
      'all_five_cases_retained_including_blocked_and_previously_matched':True,
      'FMP_query_condition':'exact_original_FIGI_and_genuinely_absent_raw_CUSIP_and_unique_exact_observed_ISIN_with_no_owner_conflict',
      'FMP_future_positive_condition':'all_search_rows_preserved_exact_query_and_profile_ISIN_and_full_checksum_CUSIP9_in_original_vocabulary',
      'FMP_symbol':'within_FMP_transport_locator_never_cross_vendor_identity',
      'no_FMP_FIGI_or_historical_identity_proof_assumed':True,
      'future_contact_requires_separate_claim_source_authentication_endpoint_rights_and_committed_run_freeze':True,
      'primary_docs':['https://site.financialmodelingprep.com/developer/docs/stable/search-isin',
        'https://site.financialmodelingprep.com/developer/docs/stable/profile-symbol'],**FALSE_FLAGS}


def _catalog(seed,capture,context,deadline):
    bodies=ba._seed_bodies(seed);provider=context['BA_provider'];expected=provider['body_pins']
    require(type(expected) is list and len(expected)==110,'inventory')
    offset=0;frames=[]
    # All frame bytes are pinned before the first symbol list or mapping JSON.
    for descriptor in expected:
        _budget(deadline);require(type(descriptor) is dict and set(descriptor)=={'byte_count','sha256'}
            and type(descriptor['byte_count']) is int and 0<descriptor['byte_count']<=ba.MAX_PAGE and _hash(descriptor['sha256']),'framing')
        size=descriptor['byte_count'];require(offset+8+size<=len(capture)
            and struct.unpack('>Q',capture[offset:offset+8])[0]==size,'framing')
        body=capture[offset+8:offset+8+size];require(pin(body)==descriptor,'framing');frames.append(body);offset+=8+size
    require(offset==len(capture),'framing')
    active=list(ba.catalog_schema.checked_symbol_rows(bodies[0]));delisted=list(ba.catalog_schema.checked_symbol_rows(bodies[1]))
    mapping=list(ba._mapping_envelope(bodies[2],0))
    for ordinal,raw in enumerate(frames):
        _budget(deadline);mapping.extend(ba._mapping_envelope(raw,(ordinal+1)*ba.PAGE_SIZE))
    observed={'active':ba._record_observation(active,ba.LIST_FIELDS,deadline),
        'delisted':ba._record_observation(delisted,ba.LIST_FIELDS,deadline),
        'mapping':ba._record_observation(mapping,ba.MAPPING_FIELDS,deadline)}
    require(len(mapping)==110346 and all(observed[key]==context['BA_authentication'][key] for key in observed),'inventory')
    return active,delisted,mapping


def _reproduce(record,active,delisted,mapping,context,deadline):
    sources=evidence._sources(record,context['BB_summary'],{'BB_result':context['BB_result']},deadline)
    indexes=crosswalk._indexes(active,delisted,mapping,sources,deadline);results=[];owners=defaultdict(set);visits=0
    for source in sources:
        _budget(deadline);refs=set(indexes['map_figi'].get(source['figi'],()))
        for token in source['tokens']:refs.update(indexes['map_cusip'].get(token,()))
        symbols={mapping[index].get('symbol') for index in refs if crosswalk._symbol(mapping[index].get('symbol'))}
        for symbol in symbols:refs.update(indexes['map_symbol'].get(symbol,()))
        visits+=len(refs);require(visits<=evidence.MAX_REFERENCE_VISITS,'reference_bound')
        result=crosswalk._match(source,indexes,deadline);results.append(result)
        if result['route'] is not None:owners[result['route']['symbol']].add(source['owner'])
    for source,result,item in zip(sources,results,record['stocks']+record['funds'],strict=True):
        if result['route'] is not None and len(owners[result['route']['symbol']])>1:
            result.update(status='unresolved',reason='EOD_symbol_owner_collision',route=None)
        require(result=={key:item[key] for key in evidence.RESULT_FIELDS},'mapping_reproduction')
    return sources,indexes


def _raw_cusip(row,tokens):
    if 'cusip' not in row:return 'missing'
    value=row['cusip']
    if value is None:return 'null'
    if value=='':return 'empty'
    if not crosswalk._cusip(value):return 'nonempty_invalid'
    return 'valid_original' if value in tokens else 'valid_other'


def _case(source,old,i_case,indexes,mapping,deadline):
    _budget(deadline);original=i_case['original_case']['aa_stock'];binding=source['binding']
    try:proof=identity.PRICE._original(original)
    except Exception:raise Refused('source_proof') from None
    tokens=old['validated_original_cusip_tokens'];figi=binding['composite_figi'];blockers=set()
    require(old['original_proof']=='pass' and original['binding']==binding==i_case['original_case']['ac_stock']['binding']
        and digest(binding)==i_case['whole_binding_sha256'] and proof['figi']==figi and sorted(proof['tokens'])==sorted(tokens or ())
        and i_case['demand']['binding_ordinal']==old['binding_ordinal'] and i_case['demand']['whole_binding_sha256']==digest(binding),
        'source_proof')
    if not tokens or not all(crosswalk._cusip(value) for value in tokens):blockers.add('original_CUSIP_unavailable')
    if len(indexes['source_figi'][figi])!=1 or any(len(indexes['source_cusip'][token])!=1 for token in tokens or ()):
        blockers.add('original_owner_collision')
    refs=old['mapping_indices'];require(type(refs) is list and refs==sorted(set(refs))
        and all(type(index) is int and 0<=index<len(mapping) for index in refs) and len(refs)<=MAX_REFERENCES,'case')
    rows=[];symbols=set();isins=set();raw_counts=Counter();same_figi=0
    if not refs:blockers.add('no_related_mapping')
    for index in refs:
        _budget(deadline);row=mapping[index];require(type(row) is dict,'case')
        if not set(row)<=crosswalk.MAPPING_FIELDS:blockers.add('mapping_fields_unknown')
        symbol=row.get('symbol');value=row.get('figi');isin=row.get('isin')
        if not crosswalk._symbol(symbol):blockers.add('invalid_EOD_symbol')
        else:symbols.add(symbol)
        if not crosswalk._figi(value):blockers.add('invalid_EOD_FIGI')
        elif value!=figi:blockers.add('different_EOD_FIGI')
        else:same_figi+=1
        state=_raw_cusip(row,tokens or ());raw_counts[state]+=1
        if state=='nonempty_invalid':blockers.add('nonempty_invalid_raw_CUSIP')
        if state=='valid_other':blockers.add('conflicting_raw_CUSIP')
        if not crosswalk._isin(isin):blockers.add('missing_or_invalid_ISIN')
        else: isins.add(isin)
        rows.append({'mapping_ordinal':index,'row_sha256':digest(row),'row':row,'raw_CUSIP_state':state,
            'original_FIGI_equal':crosswalk._figi(value) and value==figi})
    if len(symbols)>1:blockers.add('multiple_EOD_symbols')
    if len(isins)>1:blockers.add('multiple_ISINs')
    catalogs=[];catalog_identities=set()
    for symbol in sorted(symbols):
        related=indexes['catalog'].get(symbol,())
        if not related:blockers.add('catalog_symbol_missing')
        for table,index,row in related:
            _budget(deadline);catalogs.append({'table':table,'ordinal':index,'row_sha256':digest(row),'row':row})
            catalog_identities.add((row['Code'],row['Type'],row['Currency'],row['Isin']))
            if row['Type']!='Common Stock' or row['Currency']!='USD':blockers.add('catalog_instrument_or_currency')
            if not crosswalk._isin(row['Isin']):blockers.add('catalog_ISIN_missing_or_invalid')
            elif row['Isin'] not in isins:blockers.add('catalog_ISIN_disagreement')
    if len(catalog_identities)>1:blockers.add('catalog_identity_ambiguous')
    require(len(rows)+len(catalogs)<=MAX_REFERENCES,'reference_bound')
    # Global exact-ISIN owners include every physical mapping/catalog row,
    # including malformed rows: a favourable local row cannot hide conflict.
    for isin in isins:
        for row in indexes['all_mapping_ISIN'].get(isin,()):
            _budget(deadline)
            if row.get('figi')!=figi or row.get('symbol') not in symbols:blockers.add('global_mapping_ISIN_owner_conflict')
        for table,index,row in indexes['all_catalog_ISIN'].get(isin,()):
            _budget(deadline)
            if row['Code']+'.US' not in symbols or row['Type']!='Common Stock' or row['Currency']!='USD':
                blockers.add('global_catalog_ISIN_owner_conflict')
    absent=sum(raw_counts[key] for key in ('missing','null','empty'))
    status='blocked' if blockers else ('query_preparable_absent_raw_CUSIP' if absent else 'already_exact_original_pair_observed')
    require(status=='blocked' or len(symbols)==len(isins)==1 and bool(rows),'case')
    requests=sorted(isins) if status=='query_preparable_absent_raw_CUSIP' else []
    return {'case_ordinal':i_case['case_ordinal'],'whole_binding_sha256':digest(binding),'binding_ordinal':old['binding_ordinal'],
        'original_binding':binding,'original_validated_CUSIP_tokens':tokens,'original_composite_FIGI':figi,
        'I_case_sha256':digest(i_case),'prior_BB_stock_sha256':digest(old),'prior_BB_status':old['status'],'prior_BB_reason':old['reason'],
        'necessary_demand':i_case['demand'],'related_mapping_rows':rows,'related_catalog_rows':catalogs,
        'observed_valid_ISINs':sorted(isins),'query_ISINs':requests,'status':status,'blockers':sorted(blockers),
        'raw_CUSIP_state_counts':{key:raw_counts[key] for key in RAW_STATES},'original_FIGI_equal_row_count':same_figi}


def _public_case(case):
    return {key:case[key] for key in ('case_ordinal','whole_binding_sha256','binding_ordinal','prior_BB_status','prior_BB_reason',
        'status','blockers','raw_CUSIP_state_counts','original_FIGI_equal_row_count')}|{
        'mapping_row_count':len(case['related_mapping_rows']),'catalog_row_count':len(case['related_catalog_rows']),
        'observed_valid_ISIN_count':len(case['observed_valid_ISINs']),'query_ISIN_count':len(case['query_ISINs']),
        'original_claim_sha256':digest({'binding':case['original_binding'],'CUSIPs':case['original_validated_CUSIP_tokens']}),
        'related_mapping_sha256':digest(case['related_mapping_rows']),'related_catalog_sha256':digest(case['related_catalog_rows']),
        'I_case_sha256':case['I_case_sha256'],'prior_BB_stock_sha256':case['prior_BB_stock_sha256']}


def prepare(i_raw,bb_raw,seed_raw,capture_raw,*,deadline=None):
    deadline=_legacy_deadline(deadline)
    for role,raw in zip(('identity','crosswalk','seed','capture'),(i_raw,bb_raw,seed_raw,capture_raw),strict=True):
        require(type(raw) is bytes and pin(raw)=={key:DATA_PLAN[role][key] for key in ('byte_count','sha256')},'byte_pin')
    context=source_context();i_record=_loads(i_raw)
    try:identity.validate_private_record(i_record,expected_summary=context['I_summary'])
    except Exception:raise Refused('private') from None
    record=evidence._decode_private(bb_raw,context['BB_summary'],deadline)
    active,delisted,mapping=_catalog(seed_raw,capture_raw,context,deadline)
    sources,indexes=_reproduce(record,active,delisted,mapping,context,deadline)
    indexes['all_mapping_ISIN']=defaultdict(list);indexes['all_catalog_ISIN']=defaultdict(list)
    for row in mapping:
        _budget(deadline)
        if crosswalk._isin(row.get('isin')):indexes['all_mapping_ISIN'][row['isin']].append(row)
    for table,rows in (('active',active),('delisted',delisted)):
        for ordinal,row in enumerate(rows):
            _budget(deadline)
            if crosswalk._isin(row['Isin']):indexes['all_catalog_ISIN'][row['Isin']].append((table,ordinal,row))
    native={digest(source['binding']):source for source in sources if source['kind']=='stock' and source['AP_role']==identity.fmt.NATIVE}
    require(len(native)==5 and sorted(native)==list(identity.period.NATIVE_WHOLE_BINDING_SHA256S),'case')
    cases=[];size=1024
    for ordinal,case in enumerate(i_record['cases']):
        _budget(deadline);require(case['case_ordinal']==ordinal and type(case['case_ordinal']) is int,'case')
        source=native.get(case['whole_binding_sha256']);require(source is not None,'case')
        retained=_case(source,record['stocks'][source['ordinal']],case,indexes,mapping,deadline)
        size+=len(canonical(retained))+1;require(size+65536<=MAX_PRIVATE,'private_bound');cases.append(retained)
    require(len(cases)==5 and len({row['whole_binding_sha256'] for row in cases})==5,'case')
    by_isin=defaultdict(list)
    for case in cases:
        for isin in case['query_ISINs']:by_isin[isin].append(case['case_ordinal'])
    require(len(by_isin)<=5,'case')
    requests=[{'query_ordinal':ordinal,'isin':isin,'case_ordinals':by_isin[isin],
        'endpoint':'https://financialmodelingprep.com/stable/search-isin','parameter':'isin',
        'original_claims_sha256':digest([_public_case(cases[index])['original_claim_sha256'] for index in by_isin[isin]])}
        for ordinal,isin in enumerate(sorted(by_isin))]
    source={'data_plan':DATA_PLAN,'I_fact_sha256':context['I_fact_sha256'],'BB_fact_sha256':context['BB_fact_sha256'],
        'BA_fact_sha256':context['BA_fact_sha256'],'inventory_sha256':digest(context['inventory']),
        'period_sha256':context['period_sha256']}
    private={'schema':PRIVATE_SCHEMA,'source_fingerprint':digest(source),'period_sha256':context['period_sha256'],
        'cases':cases,'requests':requests}
    raw=canonical(private);require(0<len(raw)<=MAX_PRIVATE,'private_bound')
    summary={'schema':SCHEMA,'source_pins':source,'source_fingerprint':digest(source),'period_sha256':context['period_sha256'],
        'original_stock_count':6151,'own_fund_count':8,'selected_case_count':5,'complete_mapping_row_count':len(mapping),
        'complete_catalog_counts':{'active':len(active),'delisted':len(delisted)},'cases':[_public_case(row) for row in cases],
        'status_counts':dict(sorted(Counter(row['status'] for row in cases).items())),'unique_search_ISIN_count':len(requests),
        'search_request_plan_sha256':digest(requests),'private_payload_pin':pin(raw),
        'all_original_rows_and_prior_match_results_revalidated':True,'all_five_cases_retained':True,
        'all_complete_catalog_and_mapping_bytes_authenticated':True,**FALSE_FLAGS}
    validate_summary(summary);return summary,PrivateFmpQueryPlan(raw,digest(summary))


class PrivateFmpQueryPlan:
    __slots__=('_raw','byte_count','sha256','summary_sha256')
    def __init__(self,raw,summary_sha256):
        object.__setattr__(self,'_raw',raw);object.__setattr__(self,'byte_count',len(raw));object.__setattr__(self,'sha256',sha(raw));object.__setattr__(self,'summary_sha256',summary_sha256)
    def __setattr__(self,*_):raise TypeError('query plan is immutable')
    def __repr__(self):return '<PrivateFmpQueryPlan fixed-five claims and prospective queries; redacted; no admission>'
    def __reduce_ex__(self,*_):raise TypeError('private query plan cannot be pickled')
    def private_record(self):
        require(type(self._raw) is bytes and len(self._raw)==self.byte_count<=MAX_PRIVATE and sha(self._raw)==self.sha256,'private')
        return _loads(self._raw)


def validate_summary(value):
    keys={'schema','source_pins','source_fingerprint','period_sha256','original_stock_count','own_fund_count','selected_case_count',
        'complete_mapping_row_count','complete_catalog_counts','cases','status_counts','unique_search_ISIN_count',
        'search_request_plan_sha256','private_payload_pin','all_original_rows_and_prior_match_results_revalidated',
        'all_five_cases_retained','all_complete_catalog_and_mapping_bytes_authenticated',*FALSE_FLAGS}
    context=source_context()
    require(type(value) is dict and set(value)==keys and value['schema']==SCHEMA
        and all(value[key] is False for key in FALSE_FLAGS),'summary')
    for name,expected in (('original_stock_count',6151),('own_fund_count',8),('selected_case_count',5),('complete_mapping_row_count',110346)):
        require(type(value[name]) is int and value[name]==expected,'summary')
    require(value['complete_catalog_counts']=={'active':50668,'delisted':59979}
        and all(type(count) is int for count in value['complete_catalog_counts'].values())
        and all(value[key] is True for key in ('all_original_rows_and_prior_match_results_revalidated','all_five_cases_retained',
            'all_complete_catalog_and_mapping_bytes_authenticated')),'summary')
    source=value['source_pins'];require(type(source) is dict and set(source)=={'data_plan','I_fact_sha256','BB_fact_sha256','BA_fact_sha256',
        'inventory_sha256','period_sha256'} and source['data_plan']==DATA_PLAN and digest(source)==value['source_fingerprint']
        and all(source[name]==context[name] for name in ('I_fact_sha256','BB_fact_sha256','BA_fact_sha256','period_sha256'))
        and source['inventory_sha256']==digest(context['inventory']) and value['period_sha256']==context['period_sha256'],'summary')
    require(type(value['cases']) is list and len(value['cases'])==5,'summary');whole=[];statuses=Counter();queries=0
    case_keys={'case_ordinal','whole_binding_sha256','binding_ordinal','prior_BB_status','prior_BB_reason','status','blockers','raw_CUSIP_state_counts',
        'original_FIGI_equal_row_count','mapping_row_count','catalog_row_count','observed_valid_ISIN_count','query_ISIN_count',
        'original_claim_sha256','related_mapping_sha256','related_catalog_sha256','I_case_sha256','prior_BB_stock_sha256'}
    for ordinal,row in enumerate(value['cases']):
        require(type(row) is dict and set(row)==case_keys and type(row['case_ordinal']) is int and row['case_ordinal']==ordinal
            and type(row['binding_ordinal']) is int and 0<=row['binding_ordinal']<6151 and row['status'] in STATUSES
            and row['prior_BB_status'] in ('matched_current_crosswalk','unresolved')
            and (row['prior_BB_reason'] in crosswalk.REASONS if row['prior_BB_status']=='unresolved' else row['prior_BB_reason'] is None)
            and type(row['blockers']) is list and row['blockers']==sorted(set(row['blockers'])) and set(row['blockers'])<=BLOCKERS
            and bool(row['blockers']) is (row['status']=='blocked'),'summary')
        for name in ('whole_binding_sha256','original_claim_sha256','related_mapping_sha256','related_catalog_sha256','I_case_sha256','prior_BB_stock_sha256'):
            require(_hash(row[name]),'summary')
        for name in ('mapping_row_count','catalog_row_count','original_FIGI_equal_row_count'):
            require(type(row[name]) is int and 0<=row[name]<=MAX_REFERENCES,'summary')
        require(type(row['raw_CUSIP_state_counts']) is dict and set(row['raw_CUSIP_state_counts'])==set(RAW_STATES)
            and all(type(n) is int and 0<=n<=row['mapping_row_count'] for n in row['raw_CUSIP_state_counts'].values())
            and sum(row['raw_CUSIP_state_counts'].values())==row['mapping_row_count']
            and row['original_FIGI_equal_row_count']<=row['mapping_row_count'],'summary')
        for name in ('observed_valid_ISIN_count','query_ISIN_count'):require(type(row[name]) is int and 0<=row[name]<=row['mapping_row_count'],'summary')
        require(row['query_ISIN_count']==(1 if row['status']=='query_preparable_absent_raw_CUSIP' else 0),'summary')
        if row['status']!='blocked':
            require(row['observed_valid_ISIN_count']==1 and row['mapping_row_count']>0
                and row['original_FIGI_equal_row_count']==row['mapping_row_count'] and row['catalog_row_count']>0
                and row['raw_CUSIP_state_counts']['nonempty_invalid']==row['raw_CUSIP_state_counts']['valid_other']==0,'summary')
            absent=sum(row['raw_CUSIP_state_counts'][key] for key in ('missing','null','empty'))
            require((absent>0) is (row['status']=='query_preparable_absent_raw_CUSIP'),'summary')
        whole.append(row['whole_binding_sha256']);statuses[row['status']]+=1;queries+=row['query_ISIN_count']
    require(sorted(whole)==list(identity.period.NATIVE_WHOLE_BINDING_SHA256S) and value['status_counts']==dict(sorted(statuses.items()))
        and type(value['status_counts']) is dict and all(type(n) is int for n in value['status_counts'].values())
        and type(value['unique_search_ISIN_count']) is int and 0<=value['unique_search_ISIN_count']<=queries<=5
        and (queries==0) is (value['unique_search_ISIN_count']==0) and _hash(value['search_request_plan_sha256']),'summary')
    item=value['private_payload_pin'];require(type(item) is dict and set(item)=={'byte_count','sha256'}
        and type(item['byte_count']) is int and 0<item['byte_count']<=MAX_PRIVATE and _hash(item['sha256'])
        and len(canonical(value))<=MAX_SUMMARY,'summary');return json.loads(canonical(value))


def validate_private_record(record,*,expected_summary):
    summary=validate_summary(expected_summary);raw=canonical(record)
    require(pin(raw)==summary['private_payload_pin'] and type(record) is dict
        and set(record)=={'schema','source_fingerprint','period_sha256','cases','requests'} and record['schema']==PRIVATE_SCHEMA
        and record['source_fingerprint']==summary['source_fingerprint'] and record['period_sha256']==summary['period_sha256']
        and type(record['cases']) is list and len(record['cases'])==5 and [_public_case(row) for row in record['cases']]==summary['cases'],
        'private')
    requests=record['requests'];require(type(requests) is list and len(requests)==summary['unique_search_ISIN_count']
        and digest(requests)==summary['search_request_plan_sha256'],'private')
    by_isin=defaultdict(list)
    for ordinal,case in enumerate(record['cases']):
        require(type(case) is dict and set(case)=={'case_ordinal','whole_binding_sha256','binding_ordinal','original_binding',
            'original_validated_CUSIP_tokens','original_composite_FIGI','I_case_sha256','prior_BB_stock_sha256','prior_BB_status',
            'prior_BB_reason','necessary_demand','related_mapping_rows','related_catalog_rows','observed_valid_ISINs','query_ISINs',
            'status','blockers','raw_CUSIP_state_counts','original_FIGI_equal_row_count'}
            and case['case_ordinal']==ordinal and digest(case['original_binding'])==case['whole_binding_sha256']
            and case['original_binding']['composite_figi']==case['original_composite_FIGI']
            and crosswalk._figi(case['original_composite_FIGI'])
            and type(case['original_validated_CUSIP_tokens']) is list and bool(case['original_validated_CUSIP_tokens'])
            and len(case['original_validated_CUSIP_tokens'])==len(set(case['original_validated_CUSIP_tokens']))
            and all(crosswalk._cusip(value) for value in case['original_validated_CUSIP_tokens'])
            and type(case['observed_valid_ISINs']) is list and case['observed_valid_ISINs']==sorted(set(case['observed_valid_ISINs']))
            and all(crosswalk._isin(value) for value in case['observed_valid_ISINs'])
            and type(case['query_ISINs']) is list and case['query_ISINs']==sorted(set(case['query_ISINs']))
            and all(crosswalk._isin(value) for value in case['query_ISINs'])
            and set(case['query_ISINs'])<=set(case['observed_valid_ISINs'])
            and len(case['query_ISINs'])==summary['cases'][ordinal]['query_ISIN_count'],'private')
        raw_counts=Counter();observed=set();same=0;last=-1
        for row in case['related_mapping_rows']:
            require(type(row) is dict and set(row)=={'mapping_ordinal','row_sha256','row','raw_CUSIP_state','original_FIGI_equal'}
                and type(row['mapping_ordinal']) is int and last<row['mapping_ordinal']<110346 and type(row['row']) is dict
                and digest(row['row'])==row['row_sha256'] and row['raw_CUSIP_state']==_raw_cusip(row['row'],case['original_validated_CUSIP_tokens'])
                and type(row['original_FIGI_equal']) is bool
                and row['original_FIGI_equal'] is (crosswalk._figi(row['row'].get('figi')) and row['row']['figi']==case['original_composite_FIGI']), 'private')
            last=row['mapping_ordinal'];raw_counts[row['raw_CUSIP_state']]+=1;same+=row['original_FIGI_equal']
            if crosswalk._isin(row['row'].get('isin')):observed.add(row['row']['isin'])
        require({key:raw_counts[key] for key in RAW_STATES}==case['raw_CUSIP_state_counts']
            and same==case['original_FIGI_equal_row_count'] and sorted(observed)==case['observed_valid_ISINs'],'private')
        physical=set()
        for row in case['related_catalog_rows']:
            require(type(row) is dict and set(row)=={'table','ordinal','row_sha256','row'} and type(row['row']) is dict
                and set(row['row'])==set(ba.catalog_schema.FIELDS) and digest(row['row'])==row['row_sha256']
                and row['table'] in ('active','delisted') and type(row['ordinal']) is int
                and 0<=row['ordinal']<(50668 if row['table']=='active' else 59979)
                and (row['table'],row['ordinal']) not in physical,'private')
            physical.add((row['table'],row['ordinal']))
        if case['query_ISINs']:
            require(case['status']=='query_preparable_absent_raw_CUSIP' and case['query_ISINs']==case['observed_valid_ISINs']
                and same==len(case['related_mapping_rows']) and raw_counts['nonempty_invalid']==raw_counts['valid_other']==0
                and sum(raw_counts[key] for key in ('missing','null','empty'))>0,'private')
            symbols={row['row'].get('symbol') for row in case['related_mapping_rows']}
            require(len(symbols)==1 and all(crosswalk._symbol(symbol) for symbol in symbols)
                and bool(case['related_catalog_rows']) and all(row['row']['Code']+'.US' in symbols
                    and row['row']['Isin']==case['query_ISINs'][0] and row['row']['Currency']=='USD'
                    and row['row']['Type']=='Common Stock' for row in case['related_catalog_rows']),'private')
        for isin in case['query_ISINs']:by_isin[isin].append(ordinal)
    expected=[{'query_ordinal':ordinal,'isin':isin,'case_ordinals':by_isin[isin],
        'endpoint':'https://financialmodelingprep.com/stable/search-isin','parameter':'isin',
        'original_claims_sha256':digest([summary['cases'][index]['original_claim_sha256'] for index in by_isin[isin]])}
        for ordinal,isin in enumerate(sorted(by_isin))]
    require(requests==expected,'private');return json.loads(raw)
