"""Pure typed historical-symbol discovery and lossless supplied daily coverage.

All leads are metadata evidence. Other-security roles remain explicit; prices,
share-class continuity, unit/common equivalence and execution are never admitted.
"""
from collections import Counter,defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal,InvalidOperation
import hashlib
import json
import math
import re
import time
from scripts import arv2_r336_action_semantics as semantics

SCHEMA='arv2-r336-historical-symbol-coverage-v1'
N_PIN={'byte_count':294888,'sha256':'fd52e0d4177bf5c6b74dd0f1b6e8616ca03a9c8fb60ae5d9c57f584f075de86e'}
N_SOURCE_PIN={'byte_count':30955,'sha256':'d95bfb69b9383306bbee8c83ac34d8c22fb8e9ed9cd33500c886742b8c652bbe'}
M3_SOURCE_PIN={'byte_count':16361,'sha256':'b2b10d2b57d4524434c3a04ed059442417d1c4138abb2e76173f133e31979b0a'}
MAX_MEMBER_BYTES,MAX_ROWS,MAX_LINE_BYTES,MAX_NUMBER_BYTES,MAX_REQUIRED_SESSIONS=4*1024*1024,30000,640,128,4000
MAX_LEADS,MAX_TOKENS=128,64
FAMILIES=(*semantics.FAMILIES,'original_binding')
ROLES=('historical_ticker_from','historical_ticker_to','original_ticker_literal',
 'current_common_primary','prior_unit_counterparty','issuer_primary_security','related_security_counterparty',
 'merger_survivor_primary','merger_non_survivor_counterparty','merger_non_survivor_primary','merger_survivor_counterparty',
 'acquired_primary_security','received_security_counterparty')
RELATIONS=(*semantics.RELATIONS,'not_event_bound')
FALSE_FLAGS=('identity_admitted','source_admission_granted','price_input_admitted','source_assignment_changed',
 'source_or_processing_rights_granted','point_in_time_proven','formal_forward_ready','paper_or_live_ready','backtest_authority_granted',
 'historical_ticker_continuity_proven','alias_admitted','unit_common_equivalence_admitted','terminal_payoff_proven',
 'membership_or_holding_end_changed','volume_units_admitted','volume_precision_admitted','regular_session_close_convention_admitted')
FINITE=frozenset(('input_pin','input','case_binding','demand','pair_binding','event_binding','lead_bound','token_bound','output','deadline',
 'bytes','pin','member','encoding','line_ending','row_bound','row_shape','session','timestamp','date_order','number','price','OHLC',
 'volume','series','calendar','reference_scope','unknown'))
class Refused(ValueError):pass
def require(value,code):
    if not value:raise Refused(code)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(raw):return {'byte_count':len(raw),'sha256':sha(raw)}
def finite(error):
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'
def _flags():return {key:False for key in FALSE_FLAGS}
def budget(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline),'deadline')
    require(0<deadline-time.monotonic()<=300,'deadline')
def safe_token(value):return semantics.safe_token(value)

@dataclass(frozen=True,slots=True,repr=False)
class DailyBar:
    session:str
    open:Decimal
    high:Decimal
    low:Decimal
    close:Decimal
    volume:Decimal
    def __repr__(self):return '<PrivateHistoricalDailyBar>'
    def __reduce_ex__(self,protocol):raise TypeError('private daily row cannot be pickled')
@dataclass(frozen=True,slots=True,repr=False)
class DailySeries:
    _ticker:str
    _member_name:str
    _raw:bytes
    _rows:tuple
    _offsets:tuple
    def __repr__(self):return '<PrivateHistoricalDailySeries; no identity or price admission>'
    def __reduce_ex__(self,protocol):raise TypeError('private daily series cannot be pickled')


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _pin(raw):
    return {'byte_count': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def _checked_pin(value):
    require(type(value) is dict and set(value) == {'byte_count', 'sha256'}
        and type(value['byte_count']) is int and 0 < value['byte_count'] <= MAX_MEMBER_BYTES
        and _hash(value['sha256']), 'pin')
    return value


def _session(value, code='session'):
    require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) is not None, code)
    try:
        require(date.fromisoformat(value).isoformat() == value, code)
    except ValueError:
        raise Refused(code) from None
    return value


def _timestamp(value):
    require(type(value) is str and len(value) in (10, 19), 'timestamp')
    if len(value) == 19:
        require(value[10:] == ' 00:00:00', 'timestamp')
    return _session(value[:10])


def _number(value):
    require(type(value) is str and 0 < len(value) <= MAX_NUMBER_BYTES
        and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', value) is not None, 'number')
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise Refused('number') from None
    require(result.is_finite(), 'number')
    return result


def line_ending_evidence(raw):
    """Return lexical counts only; six fields do not prove a valid market row.

    This may explain a current source shape after a separately authorized read.
    It neither authenticates bytes nor diagnoses a historical failed invocation.
    No field, timestamp, ticker, price, row fingerprint or raw exception escapes.
    """
    require(type(raw) is bytes and 0 < len(raw) <= MAX_MEMBER_BYTES, 'bytes')
    lf, crlf = raw.count(b'\n'), raw.count(b'\r\n')
    bare = raw.count(b'\r') - crlf
    ends_lf, ends_crlf = raw.endswith(b'\n'), raw.endswith(b'\r\n')
    final = raw.rsplit(b'\n', 2)[-2] if ends_lf else raw.rsplit(b'\n', 1)[-1]
    if ends_crlf:
        final = final[:-1]
    field_count = final.count(b',') + 1
    complete = (0 < len(final) <= MAX_LINE_BYTES and field_count == 6
        and not final.startswith(b',') and not final.endswith(b',') and b',,' not in final)
    return {'schema': SCHEMA + '-line-ending-evidence', 'byte_count': len(raw),
        'LF_count': lf, 'CRLF_count': crlf, 'bare_CR_count': bare,
        'ends_LF': ends_lf, 'ends_CRLF': ends_crlf,
        'physical_record_count': lf + (0 if ends_lf else 1),
        'unterminated_final_record': not ends_lf,
        'complete_final_record': bool(complete), 'final_record_field_count': field_count,
        'line_endings_consistent': bare == 0 and (crlf == 0 or crlf == lf),
        'line_endings_supported': bare == 0}


def _rows(raw):
    evidence = line_ending_evidence(raw)
    require(evidence['line_endings_supported'], 'line_ending')
    try:
        raw.decode('ascii')
    except UnicodeDecodeError:
        raise Refused('encoding') from None
    lines = raw.split(b'\n')
    terminated = evidence['ends_LF']
    if terminated:
        require(lines[-1] == b'', 'line_ending')
        lines = lines[:-1]
    require(1 <= len(lines) <= MAX_ROWS, 'row_bound')
    bars, offsets, offset, previous, timestamp_width = [], [], 0, None, None
    for index, line in enumerate(lines):
        separated = index < len(lines) - 1 or terminated
        separator_bytes = 1 if separated else 0
        if separated and line.endswith(b'\r'):
            line = line[:-1]
            separator_bytes = 2
        require(0 < len(line) <= MAX_LINE_BYTES, 'row_bound')
        fields = line.decode('ascii').split(',')
        require(len(fields) == 6, 'row_shape')
        session = _timestamp(fields[0])
        if timestamp_width is None:
            timestamp_width = len(fields[0])
        require(len(fields[0]) == timestamp_width, 'timestamp')
        require(previous is None or previous < session, 'date_order')
        values = tuple(_number(field) for field in fields[1:])
        opening, high, low, close, volume = values
        require(all(value > 0 for value in values[:4]), 'price')
        require(low <= min(opening, close) <= max(opening, close) <= high, 'OHLC')
        require(volume.is_finite() and volume >= 0, 'volume')
        bars.append(DailyBar(session, opening, high, low, close, volume))
        offsets.append(offset)
        offset += len(line) + separator_bytes
        previous = session
    require(offset == len(raw), 'row_bound')
    return tuple(bars), tuple((*offsets, offset))


def _calendar(values, *, empty=False):
    require(type(values) is tuple and (empty or bool(values)) and len(values) <= MAX_REQUIRED_SESSIONS
        and all(type(value) is str for value in values)
        and values == tuple(sorted(set(values))), 'calendar')
    for value in values:
        _session(value, 'calendar')
    return values

def _member(member_name,ticker,code='member'):
    supported=safe_token(ticker) or (type(ticker) is str and ticker.endswith('-DELISTED') and safe_token(ticker[:-9]))
    require(supported and type(member_name) is str and member_name==ticker+'_full_1day_UNADJUSTED.txt',code)

def parse_daily(raw,*,expected_pin,member_name,expected_ticker):
    require(type(raw) is bytes and 0<len(raw)<=MAX_MEMBER_BYTES,'bytes');_checked_pin(expected_pin)
    require(_pin(raw)==expected_pin,'pin');_member(member_name,expected_ticker)
    rows,offsets=_rows(raw);return DailySeries(expected_ticker,member_name,raw,rows,offsets)

def _series(series):
    require(type(series) is DailySeries and type(series._raw) is bytes and 0<len(series._raw)<=MAX_MEMBER_BYTES
      and type(series._rows) is tuple and 1<=len(series._rows)<=MAX_ROWS and type(series._offsets) is tuple
      and len(series._offsets)==len(series._rows)+1 and all(type(n) is int for n in series._offsets)
      and series._offsets[0]==0 and series._offsets[-1]==len(series._raw),'series')
    _member(series._member_name,series._ticker,'series')
    require(all(type(row) is DailyBar and type(row.volume) is Decimal and row.volume.is_finite() and row.volume>=0
      and all(type(value) is Decimal and value.is_finite() and value>0 for value in (row.open,row.high,row.low,row.close))
      for row in series._rows),'series')
    try:require(_rows(series._raw)==(series._rows,series._offsets),'series')
    except Refused:raise Refused('series') from None
    return series

def private_rows(series):return _series(series)._rows
def private_original_bytes(series):return _series(series)._raw

def assess_member(raw,*,expected_pin,member_name,expected_ticker,required_sessions,reference_sessions=()):
    require(type(required_sessions) in (tuple,list) and type(reference_sessions) in (tuple,list),'calendar')
    required=_calendar(tuple(required_sessions));references=_calendar(tuple(reference_sessions),empty=True)
    require(set(references)<=set(required),'reference_scope')
    series=parse_daily(raw,expected_pin=expected_pin,member_name=member_name,expected_ticker=expected_ticker)
    observed={row.session for row in series._rows};missing=tuple(day for day in required if day not in observed)
    missing_ref=tuple(day for day in references if day not in observed)
    integer=sum(row.volume==row.volume.to_integral_value() for row in series._rows)
    public={'schema':SCHEMA+'-member-coverage','member_pin':_pin(raw),'row_count':len(series._rows),
      'required_session_count':len(required),'present_required_count':len(required)-len(missing),'missing_required_count':len(missing),
      'reference_session_count':len(references),'present_reference_count':len(references)-len(missing_ref),'missing_reference_count':len(missing_ref),
      'integer_volume_row_count':integer,'fractional_volume_row_count':len(series._rows)-integer,
      'observed_date_coverage_complete':not missing,'line_ending_evidence':line_ending_evidence(raw),**_flags()}
    private={'opaque_series':series,'required_sessions':required,'reference_sessions':references,
      'missing_required_sessions':missing,'missing_reference_sessions':missing_ref}
    validate_coverage(public);return public,private

def private_member_index(private):
    require(type(private) is dict and set(private)=={'opaque_series','required_sessions','reference_sessions',
      'missing_required_sessions','missing_reference_sessions'},'series')
    series=_series(private['opaque_series']);required=_calendar(private['required_sessions'])
    references=_calendar(private['reference_sessions'],empty=True);require(set(references)<=set(required),'reference_scope')
    observed={row.session for row in series._rows};missing=tuple(day for day in required if day not in observed)
    missing_ref=tuple(day for day in references if day not in observed)
    require(private['missing_required_sessions']==missing and private['missing_reference_sessions']==missing_ref,'series')
    return {'member_pin':_pin(series._raw),'row_count':len(series._rows),'row_offsets':list(series._offsets),
      'missing_required_sessions':list(missing),'missing_reference_sessions':list(missing_ref)}

def validate_coverage(value):
    keys={'schema','member_pin','row_count','required_session_count','present_required_count','missing_required_count',
      'reference_session_count','present_reference_count','missing_reference_count','integer_volume_row_count','fractional_volume_row_count',
      'observed_date_coverage_complete','line_ending_evidence',*FALSE_FLAGS}
    require(type(value) is dict and set(value)==keys and value['schema']==SCHEMA+'-member-coverage'
      and all(value[key] is False for key in FALSE_FLAGS),'output');_checked_pin(value['member_pin'])
    for key in keys-{'schema','member_pin','observed_date_coverage_complete','line_ending_evidence',*FALSE_FLAGS}:
        require(type(value[key]) is int and value[key]>=0,'output')
    require(0<value['row_count']<=MAX_ROWS and 0<value['required_session_count']<=MAX_REQUIRED_SESSIONS
      and value['present_required_count']+value['missing_required_count']==value['required_session_count']
      and value['present_reference_count']+value['missing_reference_count']==value['reference_session_count']
      and value['reference_session_count']<=value['required_session_count']
      and value['present_required_count']<=value['row_count']
      and value['present_reference_count']<=value['present_required_count']
      and value['missing_reference_count']<=value['missing_required_count']
      and value['integer_volume_row_count']+value['fractional_volume_row_count']==value['row_count']
      and value['observed_date_coverage_complete'] is (value['missing_required_count']==0),'output')
    evidence=value['line_ending_evidence']
    lexical_keys={'schema','byte_count','LF_count','CRLF_count','bare_CR_count','ends_LF','ends_CRLF','physical_record_count',
      'unterminated_final_record','complete_final_record','final_record_field_count','line_endings_consistent','line_endings_supported'}
    require(type(evidence) is dict and set(evidence)==lexical_keys and evidence['schema']==SCHEMA+'-line-ending-evidence','output')
    for key in ('byte_count','LF_count','CRLF_count','bare_CR_count','physical_record_count','final_record_field_count'):
        require(type(evidence[key]) is int and 0<=evidence[key]<=value['member_pin']['byte_count'],'output')
    for key in ('ends_LF','ends_CRLF','unterminated_final_record','complete_final_record','line_endings_consistent','line_endings_supported'):
        require(type(evidence[key]) is bool,'output')
    require(evidence['byte_count']==value['member_pin']['byte_count'] and evidence['physical_record_count']==value['row_count']
      and evidence['line_endings_supported'] is True and evidence['bare_CR_count']==0
      and 0<=evidence['CRLF_count']<=evidence['LF_count']<=evidence['physical_record_count']
      and evidence['physical_record_count']==evidence['LF_count']+(0 if evidence['ends_LF'] else 1)
      and evidence['unterminated_final_record'] is (not evidence['ends_LF'])
      and evidence['complete_final_record'] is True and evidence['final_record_field_count']==6
      and evidence['line_endings_consistent'] is (evidence['CRLF_count']==0 or evidence['CRLF_count']==evidence['LF_count'])
      and (not evidence['ends_CRLF'] or evidence['ends_LF'] and evidence['CRLF_count']>0)
      and (evidence['CRLF_count']!=0 or evidence['ends_CRLF'] is False)
      and (not(evidence['ends_LF'] and evidence['LF_count']>0 and evidence['LF_count']==evidence['CRLF_count']) or evidence['ends_CRLF'] is True),'output')
    return value

ROLE_EVENTS={
 'spacunitseparation':(('ticker','current_common_primary'),('contraticker','prior_unit_counterparty')),
 'relation':(('ticker','issuer_primary_security'),('contraticker','related_security_counterparty')),
 'mergerfrom':(('ticker','merger_survivor_primary'),('contraticker','merger_non_survivor_counterparty')),
 'mergerto':(('ticker','merger_non_survivor_primary'),('contraticker','merger_survivor_counterparty')),
 'acquisitionstock':(('ticker','acquired_primary_security'),('contraticker','received_security_counterparty'))}
ROLE_PAIRS=tuple(sorted({('ticker_change','historical_ticker_from'),('ticker_change','historical_ticker_to'),
 ('original_binding','original_ticker_literal'),*((semantics.RULES[code][3],role) for code,rows in ROLE_EVENTS.items() for field,role in rows)}))

def checked_pin(value,maximum):
    require(type(value) is dict and set(value)=={'byte_count','sha256'} and type(value['byte_count']) is int
      and 0<value['byte_count']<=maximum and _hash(value['sha256']),'input');return value

def profile_record():
    return {'schema':SCHEMA,'N_DATA_pin':N_PIN,'N_source_pin':N_SOURCE_PIN,'M3_parser_reference':M3_SOURCE_PIN,
      'maximum_lead_records':MAX_LEADS,'maximum_transport_tokens':MAX_TOKENS,'maximum_member_bytes':MAX_MEMBER_BYTES,
      'maximum_member_rows':MAX_ROWS,'family_labels':list(FAMILIES),'symbol_role_labels':list(ROLES),'window_relation_labels':list(RELATIONS),
      'explicit_role_policy':{key:[list(pair) for pair in roles] for key,roles in ROLE_EVENTS.items()},
      'allowed_family_role_pairs':[list(pair) for pair in ROLE_PAIRS],
      'ticker_groups':'only_exact_N_paired_metadata_eligible_unresolved_groups_preserved_private',
      'E_exclusion':'global_five_diagnostic_symbols_and_their_standard_DELISTED_aliases_only_no_F_listing_lead_exclusion',
      'lead_records':'every_origin_case_role_and_row_preserved_transport_only_deduplicated_no_alias_or_instrument_inference',
      'safe_tokens':'exact_N_uppercase_alphanumeric_dot_hyphen_max64_no_double_dot_no_normalization',
      'transport':'A_Z_current_letter_slot_digit_first_only_fixed_legacy_archives_already_DELISTED_literal_only',
      'public_joint_matrix':'nonzero_fixed_family_role_cells_only_zero_cells_implicit_counts_not_security_rows',
      'parser_delta':'M3_OHLC_dates_order_separator_guards_unchanged_volume_finite_nonnegative_Decimal_not_integral_units',
      'numeric_encoding':'unchanged_bounded_fixed_decimal_no_rounding_normalization_or_precision_admission',
      'raw_retention':'all_original_bytes_offsets_terminators_and_opaque_rows_private_no_synthetic_union',
      'coverage':'each_member_and_each_case_separately_all_required_and_reference_missing_sets_retained',**_flags()}

def plan(n_value,*,deadline):
    budget(deadline)
    try:require(type(n_value) is dict and pin(canonical(n_value))==N_PIN,'input_pin')
    except (TypeError,ValueError,UnicodeError,RecursionError):raise Refused('input_pin') from None
    value=json.loads(canonical(n_value));require(set(value)=={'schema','DATA_pins','normative_policy_sha256','all_original_events',
      'cases','all_pair_evidence','inspection',*semantics.FALSE_FLAGS} and value['schema']==semantics.SCHEMA+'-private'
      and value['DATA_pins']=={'events':semantics.I_PIN,'ownership':semantics.M_PIN,'dictionary':semantics.J_PIN}
      and value['normative_policy_sha256']==sha(canonical(semantics.profile_record()))
      and all(value[key] is False for key in semantics.FALSE_FLAGS),'input')
    try:semantics.validate_summary(value['inspection'])
    except semantics.Refused:raise Refused('input') from None
    require(type(value['cases']) is list and len(value['cases'])==5 and type(value['all_original_events']) is list
      and len(value['all_original_events'])==33 and type(value['all_pair_evidence']) is list,'input')
    cases=[];searched=set()
    for ordinal,(case,(first,count),(unused,ref_count)) in enumerate(zip(value['cases'],semantics.GEOMETRY,semantics.original.GEOMETRY,strict=True)):
        budget(deadline);require(type(case) is dict and type(case.get('case_ordinal')) is int and case['case_ordinal']==ordinal
          and case['whole_binding_sha256']==semantics.original.WHOLes[ordinal] and case.get('identity_admitted') is False,'case_binding')
        icase=case['original_I_case'];mcase=case['original_M_case'];retained=icase['original_F_case'];binding=retained['binding']
        require(sha(canonical(binding))==case['whole_binding_sha256'] and binding==mcase['binding']
          and retained['original_row']==mcase['original_row'] and retained['current_candidate_rows']==mcase['current_candidate_rows'],'case_binding')
        try:semantics.original.original_proof(binding,retained['original_row'])
        except semantics.original.Refused:raise Refused('case_binding') from None
        require(type(retained.get('required_sessions')) is list and type(retained.get('potential_reference_sessions')) is list,'demand')
        required=_calendar(tuple(retained['required_sessions']));refs=_calendar(tuple(retained['potential_reference_sessions']),empty=True)
        require(len(required)==count and required[0]==first and required[-1]==semantics.LAST and len(refs)==ref_count
          and set(refs)<=set(required),'demand')
        demand=mcase['original_required_demand'];require(demand['required_price_first']==first and demand['required_price_last']==semantics.LAST
          and demand['whole_binding_sha256']==case['whole_binding_sha256'] and demand['membership_or_binding_end_used_as_price_end'] is False,'demand')
        diagnostic=binding['diagnostic_current_ticker'];require(safe_token(diagnostic),'case_binding')
        searched.update((diagnostic,diagnostic+'-DELISTED'))
        candidates=retained['candidates'];require(type(candidates) is list and len(candidates)<=14,'input')
        for candidate in candidates:
            require(type(candidate) is dict and all(key in candidate for key in ('archive','container_pin','member_name','member_pin','gap_geometry')),'input')
            checked_pin(candidate['container_pin'],64*1024*1024);checked_pin(candidate['member_pin'],MAX_MEMBER_BYTES)
        cases.append({'case_ordinal':ordinal,'whole_binding_sha256':case['whole_binding_sha256'],
          'required_sessions':list(required),'reference_sessions':list(refs),'original_ticker':retained['original_row']['ticker'],
          'current_candidate_tickers':[row['ticker'] for row in retained['current_candidate_rows']],
          'previously_E_searched_symbols':None,'prior_E_candidates':candidates,'lead_ordinals':[]})
    leads=[]
    def add(case_ordinal,family,role,origin,symbol,rows,pair_ordinal,session,unresolved=False):
        require(len(leads)<MAX_LEADS,'lead_bound');require(family in FAMILIES and role in ROLES and type(symbol) is str and len(symbol)<=2048,'event_binding')
        case=cases[case_ordinal];supported=bool(safe_token(symbol));excluded=symbol in searched
        relation='not_event_bound' if session is None else semantics.relation(session,case['required_sessions'][0],case['required_sessions'][-1])
        record={'lead_ordinal':len(leads),'case_ordinal':case_ordinal,'family':family,'symbol_role':role,'origin':origin,
          'source_row_ordinals':list(rows),'pair_ordinal':pair_ordinal,'raw_symbol':symbol,'supported':supported,'excluded_E':excluded,
          'unresolved_pair':bool(unresolved),'eligible':supported and not excluded and not unresolved,'window_relation':relation,
          'original_ticker_literal_match':symbol==case['original_ticker'],
          'current_candidate_ticker_literal_match':symbol in case['current_candidate_tickers'],'alias_or_identity_admitted':False}
        case['lead_ordinals'].append(record['lead_ordinal']);leads.append(record)
    events=value['all_original_events']
    for ordinal,event in enumerate(events):
        require(type(event) is dict and type(event.get('source_row_ordinal')) is int and event['source_row_ordinal']==ordinal
          and event.get('identity_or_action_applied') is False and type(event.get('case_ordinals')) is list
          and event['case_ordinals']==sorted(set(event['case_ordinals']))
          and all(type(case) is int and 0<=case<5 for case in event['case_ordinals']),'event_binding')
    unresolved=[]
    for pair_ordinal,group in enumerate(value['all_pair_evidence']):
        if group['family']!='ticker_change':continue
        require(type(group['case_ordinals']) is list and group['case_ordinals']==sorted(set(group['case_ordinals']))
          and all(type(case_ordinal) is int and 0<=case_ordinal<5 for case_ordinal in group['case_ordinals'])
          and group['state'] in semantics.PAIR_STATES and group['alias_or_identity_admitted'] is False
          and group['primary_is_asof_new_symbol_assumed'] is False,'pair_binding')
        if group['state']!='paired_metadata':unresolved.append(group)
        else:require(len(group['from_row_ordinals'])==len(group['to_row_ordinals'])==1,'pair_binding')
        for direction,role in (('from','historical_ticker_from'),('to','historical_ticker_to')):
            ordinals=group[direction+'_row_ordinals'];payloads=group[direction+'_payload']
            require(type(ordinals) is list and type(payloads) is list and len(ordinals)==len(payloads),'pair_binding')
            for source_ordinal,symbol in zip(ordinals,payloads,strict=True):
                require(type(source_ordinal) is int and 0<=source_ordinal<33,'pair_binding');event=events[source_ordinal];row=event['row'];rule=event['normative_rule']
                require(event['family']=='ticker_change' and event['rule_state']=='frozen_rule' and rule is not None
                  and rule['direction']==direction and rule['payload_field']=='contraticker' and row['contraticker']==symbol
                  and row['ticker']==group['primary_current_dataset_ticker'] and row['date']==group['effective_date']
                  and event['case_ordinals']==group['case_ordinals'],'pair_binding')
                if group['state']=='paired_metadata':require(safe_token(symbol),'pair_binding')
                for case_ordinal in group['case_ordinals']:
                    add(case_ordinal,'ticker_change',role,'N.pair_evidence.'+direction,symbol,[source_ordinal],pair_ordinal,row['date'],group['state']!='paired_metadata')
    for event in events:
        row=event['row'];code=row['action']
        if code not in ROLE_EVENTS or event['rule_state']!='frozen_rule':continue
        require(event['normative_rule'] is not None and event['family']==semantics.RULES[code][3]
          and event['normative_rule']['field_roles']==semantics.RULES[code][6],'event_binding')
        for field,role in ROLE_EVENTS[code]:
            for case_ordinal in event['case_ordinals']:
                add(case_ordinal,event['family'],role,'N.normative_event.'+field,row[field],[event['source_row_ordinal']],None,row['date'])
    for case in cases:
        case['previously_E_searched_symbols']=sorted(searched)
        if case['original_ticker'] not in searched:
            add(case['case_ordinal'],'original_binding','original_ticker_literal','original_F_case.original_row.ticker',case['original_ticker'],[],None,None)
    tokens=sorted({lead['raw_symbol'] for lead in leads if lead['eligible']});require(len(tokens)<=MAX_TOKENS,'token_bound')
    specs=[]
    for token in tokens:
        aliases=[token] if token.endswith('-DELISTED') else [token,token+'-DELISTED']
        specs.append({'token':token,'current_letter':token[0] if token[0] in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' else None,
          'member_aliases':[alias for alias in aliases if alias not in searched],
          'lead_links':[{'case_ordinal':lead['case_ordinal'],'lead_ordinal':lead['lead_ordinal']} for lead in leads if lead['eligible'] and lead['raw_symbol']==token]})
    public_cases=[]
    for case in cases:
        selected=[leads[index] for index in case['lead_ordinals']];joint=[]
        for family in FAMILIES:
            for role in ROLES:
                rows=[lead for lead in selected if lead['family']==family and lead['symbol_role']==role]
                if not rows:continue
                joint.append({'family':family,'symbol_role':role,'record_count':len(rows),
                  'original_ticker_match_count':sum(row['original_ticker_literal_match'] for row in rows),
                  'current_candidate_ticker_match_count':sum(row['current_candidate_ticker_literal_match'] for row in rows),
                  'supported_count':sum(row['supported'] for row in rows),'excluded_E_symbol_count':sum(row['excluded_E'] for row in rows),
                  'unresolved_pair_count':sum(row['unresolved_pair'] for row in rows),'eligible_count':sum(row['eligible'] for row in rows),
                  'window_relation_counts':{label:sum(row['window_relation']==label for row in rows) for label in RELATIONS}})
        public_cases.append({'case_ordinal':case['case_ordinal'],'required_session_count':len(case['required_sessions']),
          'reference_session_count':len(case['reference_sessions']),'prior_E_candidate_count':len(case['prior_E_candidates']),
          'lead_record_count':len(selected),'eligible_lead_count':sum(row['eligible'] for row in selected),'family_symbol_role_matrix':joint})
    public={'schema':SCHEMA+'-plan','input_N_pin':dict(N_PIN),'case_count':5,'lead_record_count':len(leads),
      'transport_token_count':len(tokens),'excluded_E_lead_count':sum(lead['excluded_E'] for lead in leads),
      'unsupported_lead_count':sum(not lead['supported'] for lead in leads),'unresolved_pair_lead_count':sum(lead['unresolved_pair'] for lead in leads),
      'eligible_lead_count':sum(lead['eligible'] for lead in leads),'cases':public_cases,**_flags()}
    private={'schema':SCHEMA+'-plan-private','input_N_pin':dict(N_PIN),'N_policy_sha256':value['normative_policy_sha256'],
      'cases':cases,'lead_records':leads,'transport_tokens':tokens,'transport_specs':specs,'unresolved_pair_evidence':unresolved}
    validate_plan_summary(public);budget(deadline);return public,private

def validate_plan_summary(value):
    keys={'schema','input_N_pin','case_count','lead_record_count','transport_token_count','excluded_E_lead_count','unsupported_lead_count',
      'unresolved_pair_lead_count','eligible_lead_count','cases',*FALSE_FLAGS}
    require(type(value) is dict and set(value)==keys and value['schema']==SCHEMA+'-plan' and value['input_N_pin']==N_PIN
      and type(value['case_count']) is int and value['case_count']==5 and type(value['cases']) is list and len(value['cases'])==5
      and all(value[key] is False for key in FALSE_FLAGS),'output')
    require(type(value['lead_record_count']) is int and 0<=value['lead_record_count']<=MAX_LEADS
      and type(value['transport_token_count']) is int and 0<=value['transport_token_count']<=MAX_TOKENS,'output')
    for key in ('excluded_E_lead_count','unsupported_lead_count','unresolved_pair_lead_count','eligible_lead_count'):
        require(type(value[key]) is int and 0<=value[key]<=value['lead_record_count'],'output')
    require(value['transport_token_count']<=value['eligible_lead_count'] and (value['transport_token_count']==0) is (value['eligible_lead_count']==0),'output')
    totals=Counter()
    for ordinal,(case,(required,refs)) in enumerate(zip(value['cases'],semantics.original.GEOMETRY,strict=True)):
        require(type(case) is dict and set(case)=={'case_ordinal','required_session_count','reference_session_count','prior_E_candidate_count',
          'lead_record_count','eligible_lead_count','family_symbol_role_matrix'} and type(case['case_ordinal']) is int and case['case_ordinal']==ordinal
          and type(case['required_session_count']) is int and case['required_session_count']==required
          and type(case['reference_session_count']) is int and case['reference_session_count']==refs
          and type(case['prior_E_candidate_count']) is int and 0<=case['prior_E_candidate_count']<=14
          and type(case['lead_record_count']) is int and 0<=case['lead_record_count']<=MAX_LEADS
          and type(case['eligible_lead_count']) is int and 0<=case['eligible_lead_count']<=case['lead_record_count']
          and type(case['family_symbol_role_matrix']) is list,'output')
        previous=(-1,-1);count=eligible=0
        for row in case['family_symbol_role_matrix']:
            keys={'family','symbol_role','record_count','original_ticker_match_count','current_candidate_ticker_match_count',
              'supported_count','excluded_E_symbol_count','unresolved_pair_count','eligible_count','window_relation_counts'}
            require(type(row) is dict and set(row)==keys and (row['family'],row['symbol_role']) in ROLE_PAIRS,'output')
            index=(FAMILIES.index(row['family']),ROLES.index(row['symbol_role']));require(previous<index,'output');previous=index
            n=row['record_count'];require(type(n) is int and 0<n<=MAX_LEADS,'output')
            require(all(type(row[key]) is int and 0<=row[key]<=n for key in keys-{'family','symbol_role','record_count','window_relation_counts'})
              and row['eligible_count']<=row['supported_count'] and row['eligible_count']+row['excluded_E_symbol_count']<=n
              and row['eligible_count']+row['unresolved_pair_count']<=n
              and row['original_ticker_match_count']<=row['supported_count']
              and max(0,row['supported_count']-row['excluded_E_symbol_count']-row['unresolved_pair_count'])<=row['eligible_count'],'output')
            rel=row['window_relation_counts'];require(type(rel) is dict and set(rel)==set(RELATIONS)
              and all(type(v) is int and 0<=v<=n for v in rel.values()) and sum(rel.values())==n,'output')
            count+=n;eligible+=row['eligible_count'];totals['excluded']+=row['excluded_E_symbol_count']
            totals['unsupported']+=n-row['supported_count'];totals['unresolved']+=row['unresolved_pair_count']
        require(count==case['lead_record_count'] and eligible==case['eligible_lead_count'],'output')
    require(sum(case['lead_record_count'] for case in value['cases'])==value['lead_record_count']
      and sum(case['eligible_lead_count'] for case in value['cases'])==value['eligible_lead_count']
      and totals['excluded']==value['excluded_E_lead_count'] and totals['unsupported']==value['unsupported_lead_count']
      and totals['unresolved']==value['unresolved_pair_lead_count'],'output')
    return value
