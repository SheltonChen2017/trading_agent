"""Exact retained-event interpretation using fourteen frozen normative rules.

No names/prose classifier, alias construction, price source or action execution.
All original rows and unresolved pair evidence are retained privately.
"""
from collections import Counter,defaultdict
import csv
from datetime import date
from decimal import Decimal,InvalidOperation
import hashlib
import io
import json
import math
import re
import time

from scripts import arv2_r336_original_identity_ownership as original

SCHEMA='arv2-r336-retained-action-semantics-v1'
I_PIN={'byte_count':126797,'sha256':'abf7c0b602757a6c915e1d7d452ad5ff88901f7c619b33aaee638ead6c7bbb7d'}
M_PIN={'byte_count':71708,'sha256':'ed177bf0b7b8ec5683d3bda27ef69c82b72ef97b57efa8e3db5605effde4044a'}
J_PIN={'byte_count':50967,'sha256':'ad3acf93fedbdf7f4bd3af47ca7347beca615358a1736382360ba048ebfb415f'}
ORIGINAL_SOURCE_SHA256='e0e829c662c5dbc7c1a1e95f720db0e87e0725f3f3d428b3b785d991b55bef5b'
K_PROVENANCE={'clean_head':'0b78b00c7cf6a75cf21044a8aaaffee852c59a21','actual_parent_exit':0,
 'actual_worker_exit':0,'actual_validator_exit':0,'report_pin':{'byte_count':13804,
 'sha256':'6430ce4e54746272084707db462b10fbc7bee06af3c8df8bd7b6f663792ac66d'},
 'normative_definitions_reviewed_by':'Codex_root_not_independent_review'}
# code: original J row ordinal, full original-header row pin, family,
# direction, payload field, and normative field roles. These roles are a
# frozen interpretation of the exact generic definitions, not prose heuristics.
RULES={
 'acquisitionstock':(43,832,'fd4525b5f8d8ac39b70d88bfe8ea092db2f6202e107fd014f78bc8dedca7e441','acquisition_consideration','none','value','primary_acquired_contra_received_security_shares_per_old_share_last_trade'),
 'delisted':(48,481,'a1c549f73280ffee80d0b283e598a873e68fba820b2e40c316cf7e6eb4ab10d7','delisting','none','value','last_trade_final_market_cap_if_covered_not_cash_payoff'),
 'listed':(54,474,'f15e58ec595be71e42597064155c0f803d21a7a634c4ca69b47039dff420d7dd','listing','none','value','first_trading_date_initial_market_cap_if_covered_not_eligibility'),
 'mergerfrom':(55,533,'fb70da410dee6ecf90af280a486e229f057ac9d8eeeb61fcbc723f10739c42cd','merger','from','contraticker','primary_survivor_contra_non_survivor_last_trade_final_market_cap'),
 'mergerto':(56,529,'758e77f88350dcd74a6e0eb83c434a00af9e2352ffc0cf28fb23b3f45150b3e0','merger','to','contraticker','primary_non_survivor_contra_survivor_last_trade_final_market_cap'),
 'namechangefrom':(57,593,'dc2716dc656de0ce3b2cee46302e1d5a3ec2252c5ebc175646dd230c6cd35f20','name_change','from','contraname','current_dataset_primary_prior_name_effective_date'),
 'namechangeto':(58,523,'3a050fe3f0d2ae52cd5b20e566860dcb73cd138a9b0413584d6177ee30b9e176','name_change','to','contraname','current_dataset_primary_new_name_asof_effective_date'),
 'relation':(60,429,'612bfa86b955c33c1da26e5bad571cc058d10eab277f1d8cca1fe58c229342c8','same_issuer_relationship','none','contraticker','issuer_primary_to_related_different_security_not_alias'),
 'sicchangefrom':(64,647,'78f8fa1c80a1498f5e8030612da7f9f490294610394b0701f8da0a2f5df89fb3','industry_change','from','value','current_dataset_primary_prior_SIC_value_industry_title_effective_date'),
 'sicchangeto':(65,606,'f2b2959a9972babf059d4b9ad63bf30164763f4e057c505e254378767a9056c2','industry_change','to','value','current_dataset_primary_new_SIC_value_industry_title_asof_effective_date'),
 'spacmerger':(66,508,'f44b221f94b5d94d8c6c1df32f71380ecee796ece56cdcd67a84986dc6aba819','spac_business_combination','none','none','current_dataset_primary_business_combination_date_not_one_to_one_continuity'),
 'spacunitseparation':(67,524,'064c1ae7604eb0a7668675653390911d94692e574c83d8dbd15182663c4d9540','spac_unit_separation','none','contraticker','current_common_primary_prior_unit_contra_distinct_instruments'),
 'tickerchangefrom':(72,711,'7290011eb478ad9b9cc060e77b921b9d86c0b33d3372d57987eb4b3e63accdb2','ticker_change','from','contraticker','current_dataset_primary_prior_symbol_asof_effective_date'),
 'tickerchangeto':(73,711,'a69e48795e3693fa4145d6c3674edfdad5cfb8c25babd340b67a9cf251647961','ticker_change','to','contraticker','current_dataset_primary_new_symbol_asof_effective_date')}
FAMILIES=('acquisition_consideration','delisting','listing','merger','name_change','same_issuer_relationship',
 'industry_change','spac_business_combination','spac_unit_separation','ticker_change','unresolved')
PAIR_FAMILIES=('ticker_change','name_change','industry_change')
PAIR_STATES=('paired_metadata','missing_counterpart','duplicate_or_conflicting','unsupported_payload')
RULE_STATES=('frozen_rule','unreviewed_code','definition_missing','definition_ambiguous','definition_pin_mismatch')
RELATIONS=('before_required_window','at_first_required','inside_required_window','at_last_required','after_required_window')
PREDICATES=('primary_equals_original_ticker','primary_matches_current_candidate_ticker','supported_contra_equals_original_ticker',
 'supported_contra_matches_current_candidate_ticker','opaque_nonempty_contra','distinct_security_relationship',
 'spac_continuity_unproven','event_on_any_recorded_missing_date','listing_inside_required_window','delisting_inside_required_window')
I_FIELDS=('date','action','ticker','name','value','contraticker','contraname')
I_EVENT_FIELDS=('source_row_ordinal','row','action_family','primary_owner_case_ordinals','shared_primary_ticker_ownership',
 'literal_counterparty_metadata_lead','opaque_contraticker_verbatim','ticker_change_search_lead',
 'same_security_or_share_class_proven','alias_admitted','corporate_action_applied')
VARIANTS={'table':'table','tablename':'table','indicator':'indicator','isFilter':'isFilter','isfilter':'isFilter',
 'isPrimaryKey':'isPrimaryKey','isprimarykey':'isPrimaryKey','title':'title','description':'description','unitType':'unitType','unittype':'unitType'}
J_FIELDS=('table','indicator','isFilter','isPrimaryKey','title','description','unitType')
GEOMETRY=(('2023-12-01',718),('2025-02-14',417),('2025-02-14',417),('2025-01-24',432),('2025-08-01',302))
LAST='2026-10-13'
MAX_PRIVATE=2*1024*1024
FALSE_FLAGS={key:False for key in ('provider_contact','credential_access','QC_contact','Safari_access','USB_read','old_control_read',
 'old_operation_replayed','raw_instrument_rows_disclosed','normative_prose_disclosed','new_aliases_generated','alias_admitted',
 'same_security_or_share_class_proven','dated_identity_interval_proven','original_identifiers_rewritten','source_assignment_changed',
 'price_input_admitted','price_coverage_proven','terminal_payoff_proven','synthetic_cash_created','membership_intervals_changed',
 'corporate_action_executed','point_in_time_proven','formal_forward_ready','paper_or_live_ready','independent_review_complete',
 'full_current_catalog_freshly_authenticated','full_original_catalog_freshly_authenticated')}
FINITE=frozenset(('input_pin','input','dictionary','case_binding','original_proof','demand','events','links','rule','pairs','output','deadline','unknown'))

class Refused(ValueError): pass
def require(value,code):
    if not value:raise Refused(code)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(raw):return {'byte_count':len(raw),'sha256':sha(raw)}
def finite(error):
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
def budget(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline),'deadline')
    require(0<deadline-time.monotonic()<=150,'deadline')
def safe_token(value):
    return type(value) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,63}',value) is not None and '..' not in value
def sessions(values,required=False):
    require(type(values) is list and (values or not required) and all(type(v) is str and len(v)==10 for v in values),'demand')
    try:require(all(date.fromisoformat(v).isoformat()==v for v in values),'demand')
    except ValueError:raise Refused('demand') from None
    require(values==sorted(set(values)),'demand');return list(values)
def relation(value,first,last):
    return 'before_required_window' if value<first else 'at_first_required' if value==first else 'after_required_window' if value>last else 'at_last_required' if value==last else 'inside_required_window'

def profile_record():
    return {'schema':SCHEMA,'DATA_pins':{'events':I_PIN,'ownership':M_PIN,'dictionary':J_PIN},'K_provenance':K_PROVENANCE,
      'original_proof_source_sha256':ORIGINAL_SOURCE_SHA256,'normative_rules':{key:list(value) for key,value in RULES.items()},
      'families':list(FAMILIES),'pair_families':list(PAIR_FAMILIES),'pair_states':list(PAIR_STATES),'rule_states':list(RULE_STATES),
      'pair_key':'exact_current_dataset_primary_ticker_plus_effective_date_not_primary_equals_new_symbol',
      'ticker_payload':'exact_supported_single_contraticker_no_split_normalization_or_lookup',
      'name_payload':'verbatim_contraname_no_identity_inference','industry_payload':'literal_finite_numeric_value_no_classification_mutation',
      'units':'source_events_once_case_links_each_owner_pair_groups_once_case_groups_each_owner_predicates_may_overlap',
      'unknowns':'no_default_semantics_for_missing_ambiguous_unreviewed_or_unpinned_definition',
      'caller_objects':'canonical_hash_bound_then_owned_JSON_copy_before_interpretation',
      'maximum_private_bytes':MAX_PRIVATE,'maximum_seconds':150,'row_count':33,'case_count':5,**FALSE_FLAGS}

def dictionary(raw):
    require(type(raw) is bytes and pin(raw)==J_PIN,'input_pin')
    try:
        reader=csv.reader(io.StringIO(raw.decode('utf-8-sig'),newline=''),strict=True);header=next(reader)
        require(len(header)==7 and len(set(header))==7 and all(key in VARIANTS for key in header)
          and set(VARIANTS[key] for key in header)==set(J_FIELDS),'dictionary')
        rows=[];by_code=defaultdict(list)
        for ordinal,values in enumerate(reader):
            require(ordinal<75 and len(values)==7 and all(type(v) is str and len(v)<=16384 for v in values),'dictionary')
            rawrow=dict(zip(header,values,strict=True));logical={VARIANTS[key]:value for key,value in rawrow.items()}
            require(logical['table']=='actiontypes','dictionary')
            entry={'row_ordinal':ordinal,'original_generic_row':rawrow,'logical_row':logical,'full_generic_row_pin':pin(canonical(rawrow))}
            rows.append(entry);by_code[logical['indicator']].append(entry)
        require(len(rows)==75,'dictionary');return by_code
    except Refused:raise
    except (UnicodeError,csv.Error,ValueError,StopIteration):raise Refused('dictionary') from None

def rule_for(code,by_code):
    if code not in RULES:return None,'unreviewed_code',list(by_code.get(code,()))
    rows=by_code.get(code,())
    if not rows:return None,'definition_missing',[]
    if len(rows)!=1:return None,'definition_ambiguous',list(rows)
    rule=RULES[code];row=rows[0]
    if row['row_ordinal']!=rule[0] or row['full_generic_row_pin']!={'byte_count':rule[1],'sha256':rule[2]}:
        return None,'definition_pin_mismatch',list(rows)
    return {'family':rule[3],'direction':rule[4],'payload_field':rule[5],'field_roles':rule[6]},'frozen_rule',list(rows)

def checked_cases(i_value,m_value):
    require(type(i_value) is dict and i_value.get('schema')=='arv2-r335-offline-actions-metadata-links-v1-private'
      and type(i_value.get('cases')) is list and len(i_value['cases'])==5 and type(i_value.get('all_original_rows')) is list
      and len(i_value['all_original_rows'])==33,'input')
    require(type(m_value) is dict and set(m_value)=={'schema','cases','inspection',*original.FLAGS}
      and m_value['schema']==original.SCHEMA+'-private' and all(m_value[key] is False for key in original.FLAGS)
      and type(m_value['cases']) is list and len(m_value['cases'])==5,'input')
    try:original.validate_summary(m_value['inspection'])
    except original.Refused:raise Refused('original_proof') from None
    cases=[];owners=defaultdict(set)
    for ordinal,(icase,mcase,(first,count)) in enumerate(zip(i_value['cases'],m_value['cases'],GEOMETRY,strict=True)):
        require(type(icase) is dict and type(mcase) is dict and type(icase.get('case_ordinal')) is int
          and icase['case_ordinal']==ordinal==mcase['case_ordinal'] and type(mcase['case_ordinal']) is int,'case_binding')
        retained=icase['original_F_case'];binding=retained['binding'];old=retained['original_row'];current=retained['current_candidate_rows']
        require(icase['whole_binding_sha256']==retained['whole_binding_sha256']==mcase['whole_binding_sha256']==original.WHOLes[ordinal]
          and sha(canonical(binding))==original.WHOLes[ordinal] and binding==mcase['binding'] and old==mcase['original_row']
          and current==mcase['current_candidate_rows'],'case_binding')
        try:original.original_proof(binding,old)
        except original.Refused:raise Refused('original_proof') from None
        require(type(current) is list and len(current)==(2 if ordinal==0 else 1),'case_binding')
        required=sessions(retained['required_sessions'],True);demand=mcase['original_required_demand']
        require(len(required)==count and required[0]==first and required[-1]==LAST and type(demand) is dict
          and demand['whole_binding_sha256']==original.WHOLes[ordinal] and demand['required_price_first']==first
          and demand['required_price_last']==LAST and demand['source_role']=='pending_native_original_identity_source'
          and demand['membership_or_binding_end_used_as_price_end'] is False,'demand')
        explicit={binding['diagnostic_current_ticker'],old['ticker'],*(row['ticker'] for row in current)}
        for token in explicit:
            if safe_token(token):owners[token].add(ordinal)
        missing=set()
        for candidate in retained['candidates']:
            dates=sessions(candidate['gap_geometry']['missing_required_sessions'])
            require(set(dates)<=set(required),'demand');missing.update(dates)
        no_candidate=sessions(retained['no_candidate_gap']['missing_required_sessions'])
        require(set(no_candidate)<=set(required),'demand');missing.update(no_candidate)
        require(type(icase['event_links']) is list and icase['alias_admitted'] is icase['source_assignment_changed'] is False,'links')
        cases.append({'ordinal':ordinal,'original_ticker':old['ticker'],'current_tickers':{row['ticker'] for row in current},
          'required':required,'missing':missing,'prior_event_links':icase['event_links'],'retained_I_case':icase,'retained_M_case':mcase})
    return cases,owners

def checked_events(i_value,owners,by_code,deadline):
    events=[]
    for ordinal,event in enumerate(i_value['all_original_rows']):
        budget(deadline)
        require(type(event) is dict and set(event)==set(I_EVENT_FIELDS) and type(event['source_row_ordinal']) is int
          and event['source_row_ordinal']==ordinal and event['same_security_or_share_class_proven'] is
          event['alias_admitted'] is event['corporate_action_applied'] is False and event['ticker_change_search_lead'] is None,'events')
        row=event['row'];require(type(row) is dict and set(row)==set(I_FIELDS)
          and all(type(v) is str and len(v)<=2048 and v==v.strip() and not any(ord(c)<32 or ord(c)==127 for c in v) for v in row.values()),'events')
        require(row['ticker'] and safe_token(row['ticker']) and row['action'] and row['action'].isascii() and row['name'],'events')
        sessions([row['date']],True)
        if row['value']:
            require(len(row['value'])<=128 and re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]{1,4})?',row['value']),'events')
            try:require(Decimal(row['value']).is_finite(),'events')
            except InvalidOperation:raise Refused('events') from None
        actual=sorted(owners.get(row['ticker'],()))
        require(actual and event['primary_owner_case_ordinals']==actual and all(type(n) is int for n in event['primary_owner_case_ordinals'])
          and event['shared_primary_ticker_ownership'] is (len(actual)>1)
          and event['opaque_contraticker_verbatim']==row['contraticker']
          and event['literal_counterparty_metadata_lead']==(row['contraticker'] if safe_token(row['contraticker']) else None),'links')
        rule,state,definitions=rule_for(row['action'],by_code)
        events.append({'source_row_ordinal':ordinal,'original_I_event':event,'row':dict(row),'case_ordinals':actual,
          'family':'unresolved' if rule is None else rule['family'],'rule_state':state,'normative_rule':rule,
          'definition_evidence':definitions,'identity_or_action_applied':False})
    return events

def pair_groups(events):
    groups=defaultdict(list)
    for event in events:
        if event['family'] in PAIR_FAMILIES:
            groups[(event['family'],event['row']['ticker'],event['row']['date'])].append(event)
    result=[]
    for (family,primary,effective),members in sorted(groups.items()):
        before=[event for event in members if event['normative_rule']['direction']=='from']
        after=[event for event in members if event['normative_rule']['direction']=='to']
        fields={event['normative_rule']['payload_field'] for event in members};require(len(fields)==1,'pairs');field=next(iter(fields))
        supported=lambda value:safe_token(value) if family=='ticker_change' else bool(value) if family=='name_change' else bool(value)
        payloads={direction:[event['row'][field] for event in rows] for direction,rows in (('from',before),('to',after))}
        multiple=len(before)>1 or len(after)>1;missing=not before or not after
        unsupported=any(not supported(value) for values in payloads.values() for value in values)
        state='duplicate_or_conflicting' if multiple else 'missing_counterpart' if missing else 'unsupported_payload' if unsupported else 'paired_metadata'
        result.append({'family':family,'primary_current_dataset_ticker':primary,'effective_date':effective,
          'source_row_ordinals':[event['source_row_ordinal'] for event in members],
          'case_ordinals':sorted(set(case for event in members for case in event['case_ordinals'])),
          'from_row_ordinals':[event['source_row_ordinal'] for event in before],'to_row_ordinals':[event['source_row_ordinal'] for event in after],
          'state':state,'missing_from':not before,'missing_to':not after,'multiple_from':len(before)>1,'multiple_to':len(after)>1,
          'unsupported_payload_present':unsupported,'duplicate_payload_present':any(len(values)!=len(set(values)) for values in payloads.values()),
          'conflicting_payload_present':any(len(set(values))>1 for values in payloads.values()),
          'from_payload':payloads['from'],'to_payload':payloads['to'],'same_payload':bool(state=='paired_metadata' and payloads['from']==payloads['to']),
          'primary_is_asof_new_symbol_assumed':False,'alias_or_identity_admitted':False})
    return result

def count_map(values,labels):return {label:values.get(label,0) for label in labels}
def pair_counts(groups):
    return {family:{'group_count':sum(row['family']==family for row in groups),
      'state_counts':count_map(Counter(row['state'] for row in groups if row['family']==family),PAIR_STATES),
      'predicate_counts':{key:sum(row[key] for row in groups if row['family']==family) for key in
       ('missing_from','missing_to','multiple_from','multiple_to','unsupported_payload_present','duplicate_payload_present','conflicting_payload_present','same_payload')}}
      for family in PAIR_FAMILIES}

def analyze(i_value,m_value,j_raw,*,deadline):
    budget(deadline)
    try:require(type(i_value) is dict and type(m_value) is dict and pin(canonical(i_value))==I_PIN and pin(canonical(m_value))==M_PIN
      and type(j_raw) is bytes and pin(j_raw)==J_PIN,'input_pin')
    except (TypeError,ValueError,UnicodeError,RecursionError):raise Refused('input_pin') from None
    i_value=json.loads(canonical(i_value));m_value=json.loads(canonical(m_value))
    by_code=dictionary(j_raw);cases,owners=checked_cases(i_value,m_value);events=checked_events(i_value,owners,by_code,deadline)
    groups=pair_groups(events);public_cases=[];private_cases=[];total_links=0
    for case in cases:
        budget(deadline);ordinal=case['ordinal'];linked=[event for event in events if ordinal in event['case_ordinals']]
        original_links=case['prior_event_links'];require([row['source_row_ordinal'] for row in original_links]==[row['source_row_ordinal'] for row in linked],'links')
        predicates=Counter();relations=Counter();private_links=[]
        family_relations={family:Counter() for family in FAMILIES};family_gaps=Counter()
        for event,prior in zip(linked,original_links,strict=True):
            row=event['row'];rel=relation(row['date'],case['required'][0],case['required'][-1])
            require(prior['required_window_relation']==rel,'links')
            supported=safe_token(row['contraticker']);inside=case['required'][0]<=row['date']<=case['required'][-1]
            values={'primary_equals_original_ticker':row['ticker']==case['original_ticker'],
              'primary_matches_current_candidate_ticker':row['ticker'] in case['current_tickers'],
              'supported_contra_equals_original_ticker':supported and row['contraticker']==case['original_ticker'],
              'supported_contra_matches_current_candidate_ticker':supported and row['contraticker'] in case['current_tickers'],
              'opaque_nonempty_contra':bool(row['contraticker']) and not supported,
              'distinct_security_relationship':event['family'] in ('acquisition_consideration','merger','same_issuer_relationship','spac_unit_separation'),
              'spac_continuity_unproven':event['family'] in ('spac_business_combination','spac_unit_separation'),
              'event_on_any_recorded_missing_date':row['date'] in case['missing'],
              'listing_inside_required_window':event['family']=='listing' and inside,
              'delisting_inside_required_window':event['family']=='delisting' and inside}
            predicates.update({key:int(value) for key,value in values.items()});relations[rel]+=1
            family_relations[event['family']][rel]+=1
            family_gaps[event['family']]+=int(values['event_on_any_recorded_missing_date'])
            private_links.append({'source_row_ordinal':event['source_row_ordinal'],'original_I_link':prior,'normative_family':event['family'],
              'required_window_relation':rel,'predicates':values,'same_security_or_payoff_proven':False})
        case_groups=[group for group in groups if ordinal in group['case_ordinals']];total_links+=len(linked)
        public_cases.append({'case_ordinal':ordinal,'event_link_count':len(linked),
          'family_counts':count_map(Counter(row['family'] for row in linked),FAMILIES),
          'rule_state_counts':count_map(Counter(row['rule_state'] for row in linked),RULE_STATES),
          'required_window_relation_counts':count_map(relations,RELATIONS),'predicate_counts':count_map(predicates,PREDICATES),
          'family_required_window_matrix':{family:count_map(family_relations[family],RELATIONS) for family in FAMILIES},
          'family_recorded_gap_counts':count_map(family_gaps,FAMILIES),
          'pair_counts':pair_counts(case_groups),'identity_admitted':False})
        private_cases.append({'case_ordinal':ordinal,'whole_binding_sha256':original.WHOLes[ordinal],
          'original_I_case':case['retained_I_case'],'original_M_case':case['retained_M_case'],'semantic_event_links':private_links,
          'pair_evidence':case_groups,'identity_admitted':False})
    summary={'schema':SCHEMA,'source_event_count':33,'case_event_link_count':total_links,'case_count':5,
      'family_counts':count_map(Counter(row['family'] for row in events),FAMILIES),
      'rule_state_counts':count_map(Counter(row['rule_state'] for row in events),RULE_STATES),
      'pair_counts':pair_counts(groups),'cases':public_cases,**FALSE_FLAGS}
    detail={'schema':SCHEMA+'-private','DATA_pins':{'events':I_PIN,'ownership':M_PIN,'dictionary':J_PIN},
      'normative_policy_sha256':sha(canonical(profile_record())),'all_original_events':events,'cases':private_cases,
      'all_pair_evidence':groups,'inspection':json.loads(canonical(summary)),**FALSE_FLAGS}
    require(len(canonical(detail))<=MAX_PRIVATE,'output');validate_summary(summary);budget(deadline)
    return summary,detail

def counts(value,labels,total):
    require(type(value) is dict and set(value)==set(labels) and all(type(n) is int and 0<=n<=total for n in value.values())
      and sum(value.values())==total,'output')
def validate_pairs(value,maximum,family_counts):
    require(type(value) is dict and set(value)==set(PAIR_FAMILIES),'output')
    for family,row in value.items():
        require(type(row) is dict and set(row)=={'group_count','state_counts','predicate_counts'} and type(row['group_count']) is int
          and 0<=row['group_count']<=maximum,'output');n=row['group_count'];counts(row['state_counts'],PAIR_STATES,n)
        keys={'missing_from','missing_to','multiple_from','multiple_to','unsupported_payload_present','duplicate_payload_present','conflicting_payload_present','same_payload'}
        require(type(row['predicate_counts']) is dict and set(row['predicate_counts'])==keys
          and all(type(c) is int and 0<=c<=n for c in row['predicate_counts'].values())
          and row['predicate_counts']['same_payload']<=row['state_counts']['paired_metadata'],'output')
        states,pred=row['state_counts'],row['predicate_counts']
        require(n<=family_counts[family] and 2*states['paired_metadata']+states['missing_counterpart']+
          2*states['duplicate_or_conflicting']+2*states['unsupported_payload']<=family_counts[family]
          and pred['multiple_from']<=states['duplicate_or_conflicting'] and pred['multiple_to']<=states['duplicate_or_conflicting']
          and pred['duplicate_payload_present']<=states['duplicate_or_conflicting']
          and pred['conflicting_payload_present']<=states['duplicate_or_conflicting']
          and states['missing_counterpart']<=pred['missing_from']+pred['missing_to']
          and pred['unsupported_payload_present']<=n-states['paired_metadata'],'output')
def validate_summary(value):
    require(type(value) is dict and set(value)=={'schema','source_event_count','case_event_link_count','case_count','family_counts',
      'rule_state_counts','pair_counts','cases',*FALSE_FLAGS} and value['schema']==SCHEMA
      and type(value['source_event_count']) is int and value['source_event_count']==33
      and type(value['case_count']) is int and value['case_count']==5 and type(value['case_event_link_count']) is int
      and 33<=value['case_event_link_count']<=165 and type(value['cases']) is list and len(value['cases'])==5
      and all(value[key] is False for key in FALSE_FLAGS),'output')
    counts(value['family_counts'],FAMILIES,33);counts(value['rule_state_counts'],RULE_STATES,33);validate_pairs(value['pair_counts'],33,value['family_counts'])
    require(value['family_counts']['unresolved']==33-value['rule_state_counts']['frozen_rule'],'output')
    for ordinal,case in enumerate(value['cases']):
        require(type(case) is dict and set(case)=={'case_ordinal','event_link_count','family_counts','rule_state_counts',
          'required_window_relation_counts','predicate_counts','family_required_window_matrix','family_recorded_gap_counts',
          'pair_counts','identity_admitted'} and type(case['case_ordinal']) is int
          and case['case_ordinal']==ordinal and type(case['event_link_count']) is int and 0<=case['event_link_count']<=33
          and case['identity_admitted'] is False,'output');n=case['event_link_count']
        counts(case['family_counts'],FAMILIES,n);counts(case['rule_state_counts'],RULE_STATES,n)
        counts(case['required_window_relation_counts'],RELATIONS,n);validate_pairs(case['pair_counts'],n,case['family_counts'])
        matrix=case['family_required_window_matrix'];gaps=case['family_recorded_gap_counts']
        require(type(matrix) is dict and set(matrix)==set(FAMILIES) and type(gaps) is dict and set(gaps)==set(FAMILIES),'output')
        for family in FAMILIES:
            counts(matrix[family],RELATIONS,case['family_counts'][family])
            require(type(gaps[family]) is int and 0<=gaps[family]<=case['family_counts'][family],'output')
        require(all(sum(matrix[family][rel] for family in FAMILIES)==case['required_window_relation_counts'][rel] for rel in RELATIONS),'output')
        require(type(case['predicate_counts']) is dict and set(case['predicate_counts'])==set(PREDICATES)
          and all(type(c) is int and 0<=c<=n for c in case['predicate_counts'].values())
          and case['family_counts']['unresolved']==n-case['rule_state_counts']['frozen_rule']
          and case['predicate_counts']['listing_inside_required_window']<=case['family_counts']['listing']
          and case['predicate_counts']['delisting_inside_required_window']<=case['family_counts']['delisting']
          and case['predicate_counts']['distinct_security_relationship']==sum(case['family_counts'][key] for key in
           ('acquisition_consideration','merger','same_issuer_relationship','spac_unit_separation'))
          and case['predicate_counts']['spac_continuity_unproven']==case['family_counts']['spac_business_combination']+case['family_counts']['spac_unit_separation'],'output')
        require(sum(gaps.values())==case['predicate_counts']['event_on_any_recorded_missing_date']
          and case['predicate_counts']['listing_inside_required_window']==sum(matrix['listing'][key] for key in ('at_first_required','inside_required_window','at_last_required'))
          and case['predicate_counts']['delisting_inside_required_window']==sum(matrix['delisting'][key] for key in ('at_first_required','inside_required_window','at_last_required')),'output')
    require(sum(row['event_link_count'] for row in value['cases'])==value['case_event_link_count'],'output')
    for family in FAMILIES:
        total=sum(row['family_counts'][family] for row in value['cases'])
        require(value['family_counts'][family]<=total<=5*value['family_counts'][family],'output')
    for state in RULE_STATES:
        total=sum(row['rule_state_counts'][state] for row in value['cases'])
        require(value['rule_state_counts'][state]<=total<=5*value['rule_state_counts'][state],'output')
    for family in PAIR_FAMILIES:
        for state in PAIR_STATES:
            total=sum(row['pair_counts'][family]['state_counts'][state] for row in value['cases'])
            source=value['pair_counts'][family]['state_counts'][state]
            require(source<=total<=5*source,'output')
    return value
