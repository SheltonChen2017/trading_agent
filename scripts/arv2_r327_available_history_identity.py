"""Pure W5 identity and necessary-demand diagnosis over supplied fixed DATA.

No files, callbacks, credentials, provider/QC operation, mapping replacement or
price admission is available. The new caller owns byte/security guards and
fresh genuine traversal, including their normal returns before publication.
"""
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
import math
import re
import time

from scripts import arv2_r327_available_history_period as period
from scripts import run_arv2_r327_public_figi_hierarchy as h
from scripts import arv2_r327_h_source_binding as h_anchor
from scripts import arv2_r298_ar_source_binding as ar_anchor
from scripts import arv2_r298_aa_source_binding as aa_anchor
from scripts import arv2_r298_membership_price_demand as demand
from research.analyst_revisions_v2_qc import newrule_common_price_format as fmt

SCHEMA='arv2-r327-W5-identity-necessary-demand-i-v1'
PRIVATE_SCHEMA=SCHEMA+'-private'
MAX_PRIVATE,MAX_SUMMARY,MAX_RIVAL_REFERENCES=16*1024*1024,131072,100000
H_FACT_SHA256='e72ff5029df04609c1f7eb4d6fc2f2a552c4dfa0065764d2c4dc00f0601beab4'
GAP_SESSION='2022-10-21'
DATA_PLAN={
    'hierarchy':{'relative_path':'artifacts/analyst_revisions_v2/newrule_public_figi_diagnostic/R327-20261027-H/hierarchy-private.json',
        'byte_count':38548,'sha256':'b85c3d37acbe4f72192d4d42d6470654a2e727f0c6a23bed06a3539e2ec3aacd'},
    'catalog':{'relative_path':'artifacts/analyst_revisions_v2/newrule_common_price_sidecar/R326-20261027-AR/catalog-private.json',
        'byte_count':2224206,'sha256':'f55e44f85f39846f0b4946860318760eab68d10d95c79d2cf87da44ad9568cb1'},
    'stocks_metadata':{'relative_path':'artifacts/analyst_revisions_v2/newrule_all_routes/R326-20261026-Z/stocks-metadata.csv',
        'byte_count':2340169,'sha256':'354f578dd11ab0cebe1ff5b6f9ddb596b2d776f4e3161b34b8d4e1723ffe60e6'},
    'funds_metadata':{'relative_path':'artifacts/analyst_revisions_v2/newrule_all_routes/R326-20261026-Z/funds-metadata.csv',
        'byte_count':904679,'sha256':'a85d60f8699ae4b606ee11b7a70fd48e683fd8de223f14f5b4e2599434bdefac'}}
SOURCE_PINS={
    'scripts/run_arv2_r327_public_figi_hierarchy.py':'66fac17278f2468bbbca869da1b1941c5d0ea9c1d55e603efdf5c3448abcd411',
    'scripts/arv2_r327_public_figi_hierarchy.py':'568a82d3cde4834394cb06f614ab48ba4c63e2586ab231ae2b1ffc23677733d6',
    'scripts/arv2_r327_h_source_binding.py':'5280c31f84bce7aa088d57df5a861ab40a159a0e597e90600d339ba9a4590fce',
    'scripts/arv2_r327_available_history_period.py':'722cffeae9fbebcd9bca656c8994273d2b1fb36f6d3e269a018c8fb18e5b7b18',
    'scripts/arv2_r298_membership_price_demand.py':'08a9aa94b8c771eb69ed5876a82f900f0716cff9c47e082d55490c211a2c9b40',
    'scripts/arv2_r298_price_lineage_routes.py':'5a7a289a9f09cc30dc2155a00d23726cb8238d75993cb6d7c40049862e977d5a',
    'research/analyst_revisions_v2_qc/newrule_common_price_format.py':'d254b3e3a6a52445e4422f03885ec58a3d2b30e8ce902cb80ed8f841c374f873'}
PRICE=h.selection_proof.previous.previous.routes
CURRENT=PRICE.routes.current
EVALUATOR=demand.evaluator
canonical,sha=h.canonical,h.sha
FLAGS=('same_permaticker','same_FIGI','same_ticker','same_exchange','same_category','same_MIC',
    'original_CUSIP_subset','CUSIP_overlap','current_currency_USD','current_table_stocks','current_quality',
    'original_first_price_equal','original_last_price_equal','current_first_after_W5_prior',
    'current_last_before_W5_end','current_first_after_gap','current_last_before_gap')
LINKS=('original_permaticker','original_FIGI','original_ticker','candidate_permaticker','candidate_FIGI','candidate_ticker',
    'original_complete_CUSIP','candidate_complete_CUSIP','original_poison_CUSIP','candidate_poison_CUSIP',
    'candidate_refusal_token_complete_CUSIP','candidate_refusal_token_poison_CUSIP')
GAP_STATES=('never_potential_empty_initial_required','gap_before_first_required_prior','gap_inside_possible_exposure')
CASE_KEYS=frozenset(('case_ordinal','whole_binding_sha256','original_source_row_sha256','original_identity_evidence_sha256',
    'original_source_proof_rechecked','candidate_count','candidate_pattern_counts','H_observation_counts','rival_count','rival_table_counts',
    'rival_link_counts','rival_quality_counts','retained_candidate_full_row_equal_owner_count','other_related_owner_count',
    'CUSIP_only_rival_count','potential','eligible_decision_count','first_eligible_decision',
    'last_eligible_decision','required_price_first','required_price_last','gap_state','gap_possible_target_reference',
    'gap_possible_held_NAV','gap_not_required_conditional_on_empty_start'))
FALSE_FLAGS={'provider_contact':False,'credential_access':False,'QC_contact':False,'old_control_read':False,
    'old_operation_replayed':False,'original_identifiers_rewritten':False,'alias_created':False,
    'global_collision_cleared':False,'price_input_admitted':False,'price_coverage_proven':False,
    'actual_target_or_holdings_path_proven':False,'initial_QC_holdings_observed':False,
    'membership_end_used_as_price_end':False,'metadata_date_used_to_retire_holdings':False,
    'terminal_payoff_proven':False,'corporate_event_cause_proven':False,'actual_old_gap_case_attributed':False,
    'original_full_snapshot_CUSIP_ownership_reassessed':False,'source_or_processing_rights_granted':False,
    'strategy_continued':False,'point_in_time_proven':False,'formal_identity_admitted':False,
    'formal_forward_ready':False,'paper_or_live_ready':False,'licensed_values_disclosed':False}
FINITE=frozenset(('deadline','source_context','byte_pin','json','genuine','manifest','memberships','catalog',
    'hierarchy','selection','metadata','candidate','rival_bound','private_bound','summary','private','unknown'))


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def digest(value):return sha(canonical(value))
def pin(raw):return {'byte_count':len(raw),'sha256':sha(raw)}
def _hash(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def _budget(deadline):
    if deadline is not None:require(type(deadline) in (int,float) and math.isfinite(deadline) and time.monotonic()<deadline,'deadline')


def _zero(actual):
    require(type(actual) is dict and type(actual.get('actual_exit')) is int and actual['actual_exit']==0
        and actual.get('spawn_observed') is True and actual.get('bound') is None
        and type(actual.get('stdout_bytes')) is int and actual['stdout_bytes']>0 and _hash(actual.get('stdout_sha256'))
        and type(actual.get('stderr_bytes')) is int and actual['stderr_bytes']==0 and actual.get('stderr_sha256')==sha(b''),'source_context')


def source_context():
    fact=h_anchor.observed_fact();require(digest(fact)==H_FACT_SHA256,'source_context')
    require(fact['H_caller_sha256']==SOURCE_PINS['scripts/run_arv2_r327_public_figi_hierarchy.py']
        and fact['expected_head']=='b11eea5a0f8a213d84603db2ccd3dbc5a95041bb'
        and fact['private_data']==DATA_PLAN['hierarchy']
        and type(fact['collector_actual_exit_observed_by_tool']) is int and fact['collector_actual_exit_observed_by_tool']==0,'source_context')
    for key in ('producer','validator','source_actual','provider_actual','authentication_actual'):_zero(fact[key])
    require(fact['producer']['stdout_bytes']==fact['validator']['stdout_bytes']==32595
        and fact['producer']['stdout_sha256']==fact['validator']['stdout_sha256']=='669d356cf38c7334c13425a1b0ca91a3b5a23bddc145d1eb251648fc72d559be'
        and fact['technical_observation_authenticated'] is fact['all_source_provider_auth_actual_exits_zero'] is True,'source_context')
    for key in ('source_or_price_admission_granted','historical_AD_failure_cause_proven','vendor_global_collision_cleared',
        'original_FIGI_replaced','new_operation_or_read_granted','point_in_time_proven','permanent_identity_proven','formal_forward_ready','paper_or_live_ready'):
        require(fact[key] is False,'source_context')
    h.validate_authentication(fact['authentication'],fact['source'])
    ar=ar_anchor.observed_fact();output=ar_anchor.sidecar_output()
    require(ar_anchor.data_plan()['catalog']==DATA_PLAN['catalog'] and output['outcome']['result']['codec_summary']['catalog_pin']=={
        key:DATA_PLAN['catalog'][key] for key in ('byte_count','sha256')},'source_context')
    public_axis=demand.loader.previous.october._sessions();expected_period=period.make_period(public_axis)
    positions={session:index for index,session in enumerate(public_axis)}
    return {'H_fact_sha256':H_FACT_SHA256,'H_authentication':fact['authentication'],'H_prior_context':h.source_context(),
        'input_binding':aa_anchor.expected_summary()['input_binding'],
        'period_sha256':expected_period['period_sha256'],
        'period_decision_sessions':expected_period['decision_sessions'],
        'period_prior_close_by_decision':{session:public_axis[positions[session]-1] for session in expected_period['decision_sessions']},
        'expected_metadata_rows_sha256':aa_anchor.expected_summary()['routing_summary']['metadata_rows_sha256'],
        'AR_catalog_pin':{key:DATA_PLAN['catalog'][key] for key in ('byte_count','sha256')},
        'AR_observed_fact_sha256':digest(ar),'AR_complete_output_sha256':digest(output)}


def profile_record():
    context=source_context()
    return {'schema':SCHEMA,'data_plan':DATA_PLAN,'source_pins':SOURCE_PINS,'maximum_private_bytes':MAX_PRIVATE,
        'maximum_summary_bytes':MAX_SUMMARY,'maximum_rival_references':MAX_RIVAL_REFERENCES,
        'H_fact_sha256':H_FACT_SHA256,'source_context_sha256':digest(context),'period_profile_sha256':period.digest(period.profile_record()),
        'purpose':'offline_five_original_identity_disagreements_and_W5_membership_necessary_demand_not_route_acceptance',
        'all_four_DATA_byte_pins_before_any_DATA_JSON_or_CSV':True,'fresh_genuine_binding_axis_and_membership_authentication_owned_by_caller':True,
        'every_AR_assignment_checked_against_full_original_binding_inventory':True,'retained_AD_selection_is_embedded_in_H_no_AD_reread':True,
        'rivals':'related_owner_inventory_includes_candidate_self_full_row_equal_and_other_physical_rows_no_quality_filter_or_duplicate_exemption',
        'related_owner_indexes':'perma_FIGI_ticker_all_original_and_candidate_complete_CUSIPs_and_refusal_only_poison_tokens_across_both_tables',
        'metadata_dates':'observed_available_price_bounds_never_holding_retirement_or_price_coverage',
        'actions_evidence':'not_supplied_no_corporate_event_or_terminal_payoff_inference',
        'gap_session':GAP_SESSION,'gap':'necessary_membership_envelope_only_empty_start_required_no_actual_gap_identity_attribution',
        'legacy_selection_predicate_budget_seconds':120,'legacy_selection_budget_never_extends_parent':True,
        'primary_docs':['https://sharadar.com/docs/tickers','https://sharadar.com/docs/faqs','https://sharadar.com/docs/actions','https://sharadar.com/prices'],
        **FALSE_FLAGS}


def _loads(raw):
    try:
        value=json.loads(raw);require(canonical(value)==raw,'json');return value
    except (ValueError,TypeError,UnicodeError,RecursionError):raise Refused('json') from None


def _genuine(full_axis,bindings,membership_rows,manifest,input_binding,context,deadline):
    view=period.make_period(full_axis);require(input_binding==context['input_binding'] and view['period_sha256']==context['period_sha256'],'genuine')
    contract=input_binding['binding_contract'];require(type(bindings) in (tuple,list) and len(bindings)==6151,'genuine')
    checked=PRICE.routes._bindings(bindings,contract)
    require(type(manifest) is dict and set(manifest)==set(EVALUATOR._MANIFEST_FIELDS)
        and manifest['manifest_sha256']==input_binding['evaluator_manifest_sha256']
        and digest({key:value for key,value in manifest.items() if key not in ('manifest_id','manifest_sha256')})==manifest['manifest_sha256']
        and manifest['manifest_id']=='arv2-preliminary-rating-manifest-'+manifest['manifest_sha256'][:24],
        'manifest')
    require(type(membership_rows) in (tuple,list) and type(manifest['membership_row_count']) is int
        and len(membership_rows)==manifest['membership_row_count']
        and EVALUATOR._stream_sha256(tuple(membership_rows))==manifest['membership_rows_sha256'],'memberships')
    try:memberships=EVALUATOR._parse_memberships(tuple(membership_rows),len(full_axis))
    except (ValueError,TypeError,KeyError):raise Refused('memberships') from None
    ids={row['security_id'] for row in checked};require(all(row.security_id in ids for row in memberships),'memberships')
    _budget(deadline);return view,checked,memberships


def _hierarchy(raw,context,deadline):
    _budget(deadline)
    value=_loads(raw);require(type(value) is dict and set(value)=={'schema','selection_pin','selection','phases','observations','prior_context',
        'vendor_source_blockers_remaining','no_original_identifier_or_collision_clearance'} and value['schema']==h.SCHEMA+'-private'
        and value['selection_pin']==h.SELECTION_PIN and value['prior_context']==context['H_prior_context']
        and type(value['vendor_source_blockers_remaining']) is int and value['vendor_source_blockers_remaining']==5
        and value['no_original_identifier_or_collision_clearance'] is True,'hierarchy')
    require(type(h.selection_proof.DEADLINE_SECONDS) is int and h.selection_proof.DEADLINE_SECONDS==120,'selection')
    selection_deadline=time.monotonic()+h.selection_proof.DEADLINE_SECONDS
    if deadline is not None:selection_deadline=min(deadline,selection_deadline)
    selection,evidence=h._selection(canonical(value['selection']),selection_deadline)
    require(evidence['selected_whole_binding_sha256s']==list(period.NATIVE_WHOLE_BINDING_SHA256S)
        and type(value['phases']) is list and len(value['phases'])==context['H_authentication']['phase_count'],'hierarchy')
    phases=[]
    for item,expected in zip(value['phases'],context['H_authentication']['phase_summaries'],strict=True):
        require(type(item) is dict and set(item)=={'summary','private_mapping'} and item['summary']==expected,'hierarchy')
        parsed=h.hierarchy.validate_private_record(item['private_mapping'],expected_summary=expected,deadline=deadline)
        phases.append((expected,parsed))
    observations=[]
    for case in selection['cases']:
        for current in case['candidate_figis']:
            _budget(deadline);observation=h.hierarchy.corroborate(case['original_figi'],current,phase1=phases[0],
                phase2=phases[1] if len(phases)>1 else None,deadline=deadline)
            observations.append({'case_ordinal':case['case_ordinal'],'original_figi':case['original_figi'],'candidate_figi':current,'observation':observation})
    require(observations==value['observations'] and dict(Counter(item['observation']['observation'] for item in observations))==
        context['H_authentication']['corroboration_counts'],'hierarchy')
    return selection,observations


def _demand(view,axis,bindings,memberships,assignments,deadline):
    positions={session:index for index,session in enumerate(axis)};intervals=defaultdict(list)
    for row in memberships:intervals[row.security_id].append(row)
    rows=[];groups=defaultdict(Counter)
    for ordinal,(binding,assignment) in enumerate(zip(bindings,assignments[:6151],strict=True)):
        _budget(deadline);eligible=[session for session in view['decision_sessions'] if any(
            interval.first_session_index<=positions[session]<interval.last_session_index_exclusive for interval in intervals[binding['security_id']])]
        first,last=(eligible[0],eligible[-1]) if eligible else (None,None);prior=axis[positions[first]-1] if first else None
        gap_state=GAP_STATES[0] if not eligible else GAP_STATES[1] if prior>GAP_SESSION else GAP_STATES[2]
        possible_reference=any(axis[positions[session]-1]==GAP_SESSION for session in eligible)
        possible_held=any(session<=GAP_SESSION for session in eligible)
        row={'binding_ordinal':ordinal,'whole_binding_sha256':digest(binding),'semantic_binding_sha256':binding['row_sha256'],
            'source_role':assignment['role'],'potential':bool(eligible),'eligible_decision_count':len(eligible),
            'eligible_decisions_sha256':digest(eligible),'first_eligible_decision':first,'last_eligible_decision':last,
            'required_price_first':prior,'required_price_last':period.LAST if eligible else None,
            'gap_state':gap_state,'gap_possible_target_reference':possible_reference,'gap_possible_held_NAV':possible_held,
            'gap_not_required_conditional_on_empty_start':not(possible_reference or possible_held),
            'empty_initial_runtime_required':True,'membership_or_binding_end_used_as_price_end':False}
        require(assignment['role']!=fmt.CONDITIONAL or not eligible,'memberships')
        rows.append(row);groups[assignment['role']]['potential' if eligible else 'never_potential']+=1
    funds=[{'fund_ordinal':index,'own_ETF':row['own_ETF'],'source_role':row['role'],
        'required_price_first':period.PRIOR,'required_price_last':period.LAST} for index,row in enumerate(assignments[6151:])]
    return rows,funds,{role:dict(counts) for role,counts in sorted(groups.items())}


def _date_flags(original,row):
    parse=PRICE.evidence._date
    first,last=parse(row['firstpricedate']),parse(row['lastpricedate'])
    old_first,old_last=parse(original['firstpricedate']),parse(original['lastpricedate'])
    return {'original_first_price_equal':None if first is None or old_first is None else first==old_first,
        'original_last_price_equal':None if last is None or old_last is None else last==old_last,
        'current_first_after_W5_prior':None if first is None else first>period.PRIOR,
        'current_last_before_W5_end':None if last is None else last<period.LAST,
        'current_first_after_gap':None if first is None else first>GAP_SESSION,
        'current_last_before_gap':None if last is None else last<GAP_SESSION}


def _patterns(original,identity,row,table,record):
    current_tokens=set(record['tokens']);original_tokens=set(identity['tokens'])
    return {'same_permaticker':row['permaticker']==identity['permaticker'],'same_FIGI':row['figi']==identity['figi'],
        'same_ticker':row['ticker']==identity['ticker'],'same_exchange':row['exchange']==original['exchange'],
        'same_category':row['category']==original['category'],'same_MIC':PRICE.evidence._mic(row,table)==identity['mic'],
        'original_CUSIP_subset':original_tokens<=current_tokens,'CUSIP_overlap':bool(original_tokens&current_tokens),
        'current_currency_USD':row['currency']=='USD','current_table_stocks':table=='stocks',
        'current_quality':record['quality'],**_date_flags(original,row)}


def _rivals(original,identity,candidates,built,deadline,byte_limit=MAX_PRIVATE):
    _,records,indexes,tokens,poison,_=built;sets={key:set() for key in LINKS}
    for field,label in (('permaticker','permaticker'),('figi','FIGI'),('ticker','ticker')):
        sets['original_'+label].update(indexes[field].get(identity['figi'] if field=='figi' else identity[field],()))
        for row in candidates:sets['candidate_'+label].update(indexes[field].get(row[field],()))
    original_tokens=set(identity['tokens']);candidate_tokens=set();candidate_refusal_tokens=set()
    for row in candidates:
        parsed,state=CURRENT._parsed(row['cusips']);candidate_tokens.update(parsed)
        if state!='parsed':candidate_refusal_tokens.update(CURRENT.previous.identities._CUSIP_COLLISION_TOKEN.findall(row['cusips'].upper()))
    for vocabulary,prefix in ((original_tokens,'original'),(candidate_tokens,'candidate')):
        for token in vocabulary:
            sets[prefix+'_complete_CUSIP'].update(tokens.get(token,()));sets[prefix+'_poison_CUSIP'].update(poison.get(token,()))
    for token in candidate_refusal_tokens:
        sets['candidate_refusal_token_complete_CUSIP'].update(tokens.get(token,()))
        sets['candidate_refusal_token_poison_CUSIP'].update(poison.get(token,()))
    owners=set().union(*sets.values());require(len(owners)<=MAX_RIVAL_REFERENCES and type(byte_limit) is int and 0<byte_limit<=MAX_PRIVATE,'rival_bound');rows=[];bytes_seen=0
    for owner in sorted(owners):
        _budget(deadline);record=records[owner]
        item={'table':owner[0],'row_ordinal':owner[1],'row_sha256':digest(record['row']),'row':record['row'],
            'vocabulary_state':record['state'],'quality':record['quality'],'complete_token_count':len(record['tokens']),
            'poison_token_count':len(record['refusal_tokens']),'links':{key:owner in values for key,values in sets.items()},
            'retained_candidate_row_equal':any(row==record['row'] for row in candidates),
            'patterns':_patterns(original,identity,record['row'],owner[0],record)}
        bytes_seen+=len(canonical(item))+1;require(bytes_seen<=byte_limit,'private_bound')
        item['row']=dict(item['row']);rows.append(item)
    return rows


def _public_case(retained):
    case=retained['original_case'];binding=case['aa_stock']['binding'];current=retained['candidate_patterns']
    rivals=retained['rivals'];observed=retained['hierarchy_observations'];needed=retained['demand']
    patterns={flag:{state:sum(item['patterns'][flag] is test for item in current)
        for state,test in (('true',True),('false',False),('unknown',None))} for flag in FLAGS}
    return {'case_ordinal':case['case_ordinal'],'whole_binding_sha256':digest(binding),'original_source_row_sha256':binding['source_row_sha256'],
        'original_identity_evidence_sha256':binding['identity_evidence_sha256'],'original_source_proof_rechecked':True,
        'candidate_count':len(current),'candidate_pattern_counts':patterns,
        'H_observation_counts':dict(sorted(Counter(item['observation'] for item in observed).items())),
        'rival_count':len(rivals),'rival_table_counts':dict(sorted(Counter(item['table'] for item in rivals).items())),
        'rival_link_counts':{key:sum(item['links'][key] for item in rivals) for key in LINKS},
        'rival_quality_counts':{'true':sum(item['quality'] for item in rivals),'false':sum(not item['quality'] for item in rivals)},
        'retained_candidate_full_row_equal_owner_count':sum(item['retained_candidate_row_equal'] for item in rivals),
        'other_related_owner_count':sum(not item['retained_candidate_row_equal'] for item in rivals),
        'CUSIP_only_rival_count':sum(any(item['links'][key] for key in LINKS[6:]) and not any(item['links'][key] for key in LINKS[:6]) for item in rivals),
        **{key:needed[key] for key in ('potential','eligible_decision_count','first_eligible_decision','last_eligible_decision',
            'required_price_first','required_price_last','gap_state','gap_possible_target_reference','gap_possible_held_NAV',
            'gap_not_required_conditional_on_empty_start')}}


def prepare(h_raw,catalog_raw,stocks_raw,funds_raw,*,full_axis,binding_rows,membership_rows,evaluator_manifest,input_binding,deadline=None):
    _budget(deadline);context=source_context()
    for role,raw in (('hierarchy',h_raw),('catalog',catalog_raw),('stocks_metadata',stocks_raw),('funds_metadata',funds_raw)):
        require(type(raw) is bytes and pin(raw)=={key:DATA_PLAN[role][key] for key in ('byte_count','sha256')},'byte_pin')
    view,bindings,memberships=_genuine(full_axis,binding_rows,membership_rows,evaluator_manifest,input_binding,context,deadline)
    selection,observations=_hierarchy(h_raw,context,deadline)
    catalog=fmt.validate_catalog(fmt.loads(catalog_raw,fmt.MAX_CATALOG_BYTES));assignments=catalog['assignments']
    for row,assigned in zip(bindings,assignments[:6151],strict=True):
        require(assigned['whole_binding_sha256']==digest(row) and assigned['semantic_binding_sha256']==row['row_sha256']
            and assigned['security_id']==row['security_id'],'catalog')
    require(sorted(row['whole_binding_sha256'] for row in assignments[:6151] if row['role']==fmt.NATIVE)==list(period.NATIVE_WHOLE_BINDING_SHA256S),'catalog')
    try:
        stocks=CURRENT.metadata(stocks_raw,'stocks',16*1024*1024)[0];funds=CURRENT.metadata(funds_raw,'funds',16*1024*1024)[0]
        built=CURRENT._build(stocks,funds);metadata_receipt=CURRENT.validate_receipt(CURRENT._receipt(built))
    except (ValueError,TypeError,KeyError):raise Refused('metadata') from None
    require(metadata_receipt['metadata_rows_sha256']==context['expected_metadata_rows_sha256'],'metadata')
    demands,fund_demands,groups=_demand(view,full_axis,bindings,memberships,assignments,deadline)
    physical=defaultdict(list)
    for owner,record in built[1].items():physical[digest(record['row'])].append(owner)
    cases=[];public=[];budget=1024+len(canonical(demands))+len(canonical(fund_demands));rival_count=0
    for case in selection['cases']:
        _budget(deadline);ordinal=case['aa_stock']['binding_ordinal'];binding=bindings[ordinal]
        require(binding==case['aa_stock']['binding']==case['ac_stock']['binding'] and assignments[ordinal]['role']==fmt.NATIVE,'selection')
        original=case['aa_stock']['original_row'];identity=PRICE._original(case['aa_stock']);candidates=case['aa_stock']['current_candidate_rows']
        current=[]
        for index,row in enumerate(candidates):
            require(digest(row) in physical and all(built[1][owner]['row']==row for owner in physical[digest(row)]),'candidate')
            owner=physical[digest(row)][0];record=built[1][owner]
            current.append({'candidate_ordinal':index,'row_sha256':digest(row),'physical_refs':[{'table':key[0],'row_ordinal':key[1]} for key in physical[digest(row)]],
                'patterns':_patterns(original,identity,row,owner[0],record)})
        rivals=_rivals(original,identity,candidates,built,deadline,MAX_PRIVATE-budget-65536)
        rival_count+=len(rivals);require(rival_count<=MAX_RIVAL_REFERENCES,'rival_bound')
        observed=[item['observation'] for item in observations if item['case_ordinal']==case['case_ordinal']]
        needed=demands[ordinal]
        retained={'case_ordinal':case['case_ordinal'],'whole_binding_sha256':digest(binding),'original_case':case,
            'candidate_patterns':current,'hierarchy_observations':observed,'demand':needed,'rivals':rivals}
        budget+=len(canonical(retained))+1;require(budget+65536<=MAX_PRIVATE,'private_bound');cases.append(retained)
        public.append(_public_case(retained))
    source={'data_plan':DATA_PLAN,'H_fact_sha256':H_FACT_SHA256,'input_binding_sha256':digest(input_binding),
        'membership_stream_sha256':evaluator_manifest['membership_rows_sha256'],'period_sha256':view['period_sha256']}
    record={'schema':PRIVATE_SCHEMA,'source_fingerprint':digest(source),'period':view,'stock_demand':demands,'fund_demand':fund_demands,
        'cases':cases,'metadata_receipt':metadata_receipt}
    raw=canonical(record);require(0<len(raw)<=MAX_PRIVATE,'private_bound')
    summary={'schema':SCHEMA,'source_pins':source,'source_fingerprint':digest(source),'period_sha256':view['period_sha256'],
        'research_epoch_id':view['research_epoch_id'],'all_original_stock_count':6151,'all_own_fund_count':8,'selected_case_count':5,
        'stock_demand_counts_by_source_role':groups,'cases':public,'rival_reference_count':rival_count,
        'metadata_rows_sha256':metadata_receipt['metadata_rows_sha256'],'private_payload_pin':pin(raw),
        'all_original_assignments_checked_not_replaced':True,'all_global_current_rivals_retained_without_quality_filter':True,
        'gap_session':GAP_SESSION,'empty_initial_runtime_required':True,'actions_evidence_supplied':False,**FALSE_FLAGS}
    validate_summary(summary);return summary,PrivateIdentityDemand(raw,digest(summary))


class PrivateIdentityDemand:
    __slots__=('_raw','byte_count','sha256','summary_sha256')
    def __init__(self,raw,summary_sha256):
        object.__setattr__(self,'_raw',raw);object.__setattr__(self,'byte_count',len(raw));object.__setattr__(self,'sha256',sha(raw));object.__setattr__(self,'summary_sha256',summary_sha256)
    def __setattr__(self,*_):raise TypeError('identity demand is immutable')
    def __repr__(self):return '<PrivateIdentityDemand original evidence and necessary exposure; redacted; no admission>'
    def __reduce_ex__(self,*_):raise TypeError('identity evidence cannot be pickled')
    def private_record(self):
        require(type(self._raw) is bytes and len(self._raw)==self.byte_count<=MAX_PRIVATE and sha(self._raw)==self.sha256,'private')
        return _loads(self._raw)


def validate_summary(value):
    keys={'schema','source_pins','source_fingerprint','period_sha256','research_epoch_id','all_original_stock_count','all_own_fund_count',
        'selected_case_count','stock_demand_counts_by_source_role','cases','rival_reference_count','metadata_rows_sha256','private_payload_pin',
        'all_original_assignments_checked_not_replaced','all_global_current_rivals_retained_without_quality_filter','gap_session',
        'empty_initial_runtime_required','actions_evidence_supplied',*FALSE_FLAGS}
    context=source_context()
    require(type(value) is dict and set(value)==keys and value['schema']==SCHEMA and value['research_epoch_id']==period.RESEARCH_EPOCH_ID
        and type(value['all_original_stock_count']) is type(value['all_own_fund_count']) is type(value['selected_case_count']) is int
        and (value['all_original_stock_count'],value['all_own_fund_count'],value['selected_case_count'])==(6151,8,5)
        and value['all_original_assignments_checked_not_replaced'] is value['all_global_current_rivals_retained_without_quality_filter'] is True
        and value['gap_session']==GAP_SESSION and value['empty_initial_runtime_required'] is True and value['actions_evidence_supplied'] is False
        and all(value[key] is False for key in FALSE_FLAGS) and value['period_sha256']==context['period_sha256']
        and digest(value['source_pins'])==value['source_fingerprint'],'summary')
    source=value['source_pins'];require(type(source) is dict and set(source)=={'data_plan','H_fact_sha256','input_binding_sha256','membership_stream_sha256','period_sha256'}
        and source['data_plan']==DATA_PLAN and source['H_fact_sha256']==H_FACT_SHA256 and source['period_sha256']==value['period_sha256']
        and source['input_binding_sha256']==digest(context['input_binding']) and _hash(source['membership_stream_sha256']),'summary')
    groups=value['stock_demand_counts_by_source_role'];require(type(groups) is dict and set(groups)=={fmt.VENDOR,fmt.NATIVE,fmt.CONDITIONAL},'summary')
    for role,total in ((fmt.VENDOR,5636),(fmt.NATIVE,5),(fmt.CONDITIONAL,510)):
        require(type(groups[role]) is dict and set(groups[role])<={'potential','never_potential'}
            and all(type(count) is int and 0<count<=total for count in groups[role].values()) and sum(groups[role].values())==total,'summary')
    require(type(value['cases']) is list and len(value['cases'])==5,'summary');rivals=0;whole=[]
    for index,row in enumerate(value['cases']):
        require(type(row) is dict and set(row)==CASE_KEYS and row.get('case_ordinal')==index and type(row.get('case_ordinal')) is int
            and _hash(row.get('whole_binding_sha256')) and row.get('original_source_proof_rechecked') is True
            and _hash(row.get('original_source_row_sha256')) and _hash(row.get('original_identity_evidence_sha256')),'summary')
        whole.append(row['whole_binding_sha256']);n=row.get('candidate_count');require(type(n) is int and 0<n<=4096,'summary')
        require(type(row.get('candidate_pattern_counts')) is dict and set(row['candidate_pattern_counts'])==set(FLAGS),'summary')
        for counts in row['candidate_pattern_counts'].values():require(type(counts) is dict and set(counts)=={'true','false','unknown'}
            and all(type(count) is int and 0<=count<=n for count in counts.values()) and sum(counts.values())==n,'summary')
        count=row.get('rival_count');require(type(count) is int and 0<=count<=MAX_RIVAL_REFERENCES,'summary');rivals+=count
        require(all(type(row[key]) is int and 0<=row[key]<=count for key in
            ('retained_candidate_full_row_equal_owner_count','other_related_owner_count'))
            and row['retained_candidate_full_row_equal_owner_count']+row['other_related_owner_count']==count,'summary')
        require(type(row['H_observation_counts']) is dict and set(row['H_observation_counts'])<=h.hierarchy.OBSERVATIONS
            and all(type(number) is int and 0<number<=n for number in row['H_observation_counts'].values())
            and 0<sum(row['H_observation_counts'].values())<=n
            and type(row['CUSIP_only_rival_count']) is int and 0<=row['CUSIP_only_rival_count']<=count,'summary')
        require(type(row.get('rival_link_counts')) is dict and set(row['rival_link_counts'])==set(LINKS)
            and all(type(c) is int and 0<=c<=count for c in row['rival_link_counts'].values())
            and type(row.get('rival_table_counts')) is dict and set(row['rival_table_counts'])<={'stocks','funds'}
            and all(type(c) is int and c>0 for c in row['rival_table_counts'].values()) and sum(row['rival_table_counts'].values())==count
            and type(row.get('rival_quality_counts')) is dict and set(row['rival_quality_counts'])=={'true','false'}
            and all(type(c) is int and c>=0 for c in row['rival_quality_counts'].values()) and sum(row['rival_quality_counts'].values())==count,'summary')
        require(type(row.get('potential')) is bool and type(row.get('eligible_decision_count')) is int
            and 0<=row['eligible_decision_count']<=len(context['period_decision_sessions'])
            and (row['eligible_decision_count']>0) is row['potential'] and row.get('gap_state') in GAP_STATES
            and all(type(row.get(key)) is bool for key in ('gap_possible_target_reference','gap_possible_held_NAV','gap_not_required_conditional_on_empty_start')),'summary')
        for key in ('first_eligible_decision','last_eligible_decision','required_price_first','required_price_last'):
            text=row[key]
            if text is not None:
                try:valid=type(text) is str and len(text)==10 and date.fromisoformat(text).isoformat()==text
                except ValueError:valid=False
                require(valid,'summary')
        require(row['gap_not_required_conditional_on_empty_start'] is not (row['gap_possible_target_reference'] or row['gap_possible_held_NAV']),'summary')
        if row['potential']:
            require(all(type(row[key]) is str for key in ('first_eligible_decision','last_eligible_decision','required_price_first','required_price_last'))
                and row['first_eligible_decision'] in context['period_decision_sessions']
                and row['last_eligible_decision'] in context['period_decision_sessions']
                and row['first_eligible_decision']<=row['last_eligible_decision']
                and row['required_price_first']==context['period_prior_close_by_decision'][row['first_eligible_decision']]
                and row['required_price_last']==period.LAST
                and row['gap_state']==(GAP_STATES[1] if row['required_price_first']>GAP_SESSION else GAP_STATES[2])
                and row['gap_possible_held_NAV'] is (row['first_eligible_decision']<=GAP_SESSION),'summary')
            first=context['period_decision_sessions'].index(row['first_eligible_decision'])
            last=context['period_decision_sessions'].index(row['last_eligible_decision'])
            require((1 if first==last else 2)<=row['eligible_decision_count']<=last-first+1,'summary')
            possible_prior_dates=[context['period_prior_close_by_decision'][session] for session in context['period_decision_sessions'][first:last+1]]
            require(GAP_SESSION in possible_prior_dates or row['gap_possible_target_reference'] is False,'summary')
            if first==last or row['required_price_first']==GAP_SESSION:
                require(row['gap_possible_target_reference'] is (GAP_SESSION in possible_prior_dates),'summary')
        else:require(all(row[key] is None for key in ('first_eligible_decision','last_eligible_decision','required_price_first','required_price_last'))
            and row['gap_state']==GAP_STATES[0] and not row['gap_possible_target_reference'] and not row['gap_possible_held_NAV'],'summary')
    require(sum(row['potential'] for row in value['cases'])==groups[fmt.NATIVE].get('potential',0)
        and sorted(whole)==list(period.NATIVE_WHOLE_BINDING_SHA256S) and type(value['rival_reference_count']) is int
        and value['rival_reference_count']==rivals<=MAX_RIVAL_REFERENCES,'summary')
    require(type(value['metadata_rows_sha256']) is dict and set(value['metadata_rows_sha256'])=={'stocks','funds'}
        and value['metadata_rows_sha256']==context['expected_metadata_rows_sha256'],'summary')
    item=value['private_payload_pin'];require(type(item) is dict and set(item)=={'byte_count','sha256'} and type(item['byte_count']) is int
        and 0<item['byte_count']<=MAX_PRIVATE and _hash(item['sha256']) and 0<len(canonical(value))<=MAX_SUMMARY,'summary')
    return json.loads(canonical(value))


def validate_private_record(record,*,expected_summary):
    summary=validate_summary(expected_summary);raw=canonical(record)
    require(pin(raw)==summary['private_payload_pin'] and type(record) is dict and set(record)=={'schema','source_fingerprint','period','stock_demand','fund_demand','cases','metadata_receipt'}
        and record['schema']==PRIVATE_SCHEMA and record['source_fingerprint']==summary['source_fingerprint']
        and record['period']['period_sha256']==summary['period_sha256'] and type(record['stock_demand']) is list and len(record['stock_demand'])==6151
        and type(record['fund_demand']) is list and len(record['fund_demand'])==8 and type(record['cases']) is list and len(record['cases'])==5,'private')
    require([row['binding_ordinal'] for row in record['stock_demand']]==list(range(6151))
        and [row['fund_ordinal'] for row in record['fund_demand']]==list(range(8))
        and sum(len(case['rivals']) for case in record['cases'])==summary['rival_reference_count'],'private')
    require([_public_case(case) for case in record['cases']]==summary['cases'],'private')
    period_seed=dict(record['period']);declared=period_seed.pop('period_sha256',None)
    require(declared==summary['period_sha256']==digest(period_seed),'private')
    CURRENT.validate_receipt(record['metadata_receipt'])
    require(record['metadata_receipt']['metadata_rows_sha256']==summary['metadata_rows_sha256'],'private')
    return json.loads(raw)
