"""Supplied-byte conservative R337 price-grid coverage; no engine or returns.

The genuine rating package contains membership, ratings and original bindings,
not historical ETF/fundamental callbacks. This observer therefore checks a
necessary-condition superset, never fabricates actual targets, holdings or
orders. Missing required marks are retained as an authenticated INCOMPLETE
observation; corrupt source/grid bytes refuse instead of becoming absent data.
"""
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
import math
import re
import time

from scripts import arv2_r337_quarantine_preparation as archive
from research.analyst_revisions_v2_qc import newrule_common_price_format as fmt
from research.analyst_revisions_v2_qc import newrule_five_case_quarantine_targets as targets
from research.analyst_revisions_v2_qc import accepted_risk_preliminary_rating_evaluator as evaluator

SCHEMA='arv2-r338-quarantine-conservative-coverage-v1'
PRIVATE_SCHEMA=SCHEMA+'-private'
CATALOG_PIN={'byte_count':6924,'sha256':'bebe830cba48c6eafb0c99c8feb4251c59871bb7a52f054327076d946d81bc94'}
INPUT_BINDING_PIN={'byte_count':1302,'sha256':'9ab7beb55cd5e301237dca3b2231750ac494ae9de01e453817fa2a4c554f35a7'}
AXIS_SHA256='4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585'
AXIS_COUNT=3466
FIRST,PRIOR,CUTOFF,LAST='2021-11-01','2021-10-29','2026-10-12','2026-10-13'
EXPECTED_PRICE_SESSIONS,EXPECTED_DECISIONS=1243,259
CELLS=((6,0),(6,100),(6,200),(8,0),(8,100),(8,200))
MAX_SECONDS,MAX_MISSING_PAIRS,MAX_PRIVATE_BYTES,MAX_SUMMARY_BYTES=300,2654048,64*1024*1024,131072
DENSE_MASK,REFERENCE_MASK=1,2
FALSE_FLAGS={key:False for key in ('provider_contact','QC_contact','Safari_access','credential_access',
    'USB_read','old_control_read','old_operation_replayed','native_QC_identity_resolved','QC_types_fabricated',
    'historical_ETF_or_fundamental_callbacks_authenticated','actual_targets_proven','actual_holdings_path_proven',
    'actual_order_or_execution_quote_coverage_proven','actual_NAV_or_strategy_returns_computed',
    'membership_end_retires_holdings','binding_end_retires_holdings','missing_marks_drop_names',
    'stale_or_quote_substitution','quarantined_prices_consumed','conditional_never_is_unconditional',
    'source_admission_granted','price_input_admitted','complete_strategy_price_coverage_proven',
    'historical_identity_proven','permanent_security_master_proven','point_in_time_proven',
    'formal_forward_ready','paper_or_live_ready','strategy_result_accepted','new_launch_attempt_granted')}
FINITE=frozenset(('deadline','input_pin','input_binding','axis','manifest','memberships','catalog',
    'assignment','quarantine','conditional_demand','period','archive','grid','missing_bound','private_bound',
    'transport_nonce','input_shape','output','unknown'))


class Refused(ValueError):
    """Finite predicate only; no data, identifiers, prices or exception prose."""


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
    except (ValueError,TypeError,UnicodeError,RecursionError):raise Refused('output') from None


def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(raw):return {'byte_count':len(raw),'sha256':sha(raw)}
def digest(value):return sha(canonical(value))

def budget(deadline):
    require(type(deadline) in (int,float) and math.isfinite(deadline)
        and 0<deadline-time.monotonic()<=MAX_SECONDS,'deadline')


def _pin(value,maximum):
    require(type(value) is dict and set(value)=={'byte_count','sha256'}
        and type(value['byte_count']) is int and 0<value['byte_count']<=maximum
        and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']) is not None,'output')
    return value


def profile_record():
    return {'schema':SCHEMA,'private_schema':PRIVATE_SCHEMA,'research_epoch_id':targets.RESEARCH_EPOCH_ID,
        'quarantine_catalog_pin':CATALOG_PIN,'input_binding_pin':INPUT_BINDING_PIN,
        'vendor_archive_pin':archive.ARCHIVE_PIN,'full_axis_count':AXIS_COUNT,'full_axis_sha256':AXIS_SHA256,
        'evaluation_first':FIRST,'first_reference':PRIOR,'last_close':LAST,'decision_cutoff':CUTOFF,
        'required_price_sessions':EXPECTED_PRICE_SESSIONS,'decision_count':EXPECTED_DECISIONS,
        'cells':[list(cell) for cell in CELLS],'maximum_seconds':MAX_SECONDS,
        'maximum_missing_pairs':MAX_MISSING_PAIRS,'maximum_private_bytes':MAX_PRIVATE_BYTES,
        'maximum_summary_bytes':MAX_SUMMARY_BYTES,'archive_authentication':'whole_pin_and_all73_header_ranges_before_any_price_row_parse',
        'source_bindings':'all_original6151_exact_whole_semantic_ID_assignments_plus8_fixed_fund_routes_retained',
        'stock_demand':'W5_membership_at_each_frozen_weekly_decision_first_prior_through_END_no_expiry_clip',
        'reference_demand':'prior_close_at_each_membership_eligible_decision_not_actual_selection',
        'fund_demand':'all8_funds_1243_price_sessions_six_cell_uses_first6_eight_cell_uses_all8',
        'quarantine':'same_exact5_denied_all6_cells_never_price_demand',
        'conditional':'any_W5_membership_eligible_conditional_binding_refuses_no_demand_relabel',
        'missing':'all_explicit_null_required_pairs_retained_compact_slot_session_mask_no_truncation',
        'masks':{'dense_possible_holding':DENSE_MASK,'potential_prior_reference':REFERENCE_MASK},
        'incomplete':'valid_authenticated_observation_not_a_required_coverage_pass_or_engine_gate_clearance',
        'private_digest_blinding':'mandatory_fresh_claim_bound_64_lowerhex_transport_nonce_private_only_before_evidence_hash',
        'grid':'real_unchanged_fmt_validate_shard_ALL71_months_ALL_cells_including_nonrequired',
        'deadline_qualification':'cooperative_checks_no_uninterruptible_IO_or_host_suspension_bound',**FALSE_FLAGS}


def _inputs(axis,bindings,membership_rows,manifest,input_binding,catalog_raw,deadline):
    budget(deadline)
    require(type(catalog_raw) is bytes and pin(catalog_raw)==CATALOG_PIN,'input_pin')
    require(type(input_binding) is dict and pin(canonical(input_binding))==INPUT_BINDING_PIN,'input_binding')
    require(type(axis) is tuple and len(axis)==AXIS_COUNT and digest(list(axis))==AXIS_SHA256,'axis')
    require(all(type(day) is str for day in axis) and axis==tuple(sorted(set(axis)))
        and axis[0]=='2013-01-02' and axis[-1]==LAST,'axis')
    try:require(all(date.fromisoformat(day).isoformat()==day for day in axis),'axis')
    except ValueError:raise Refused('axis') from None
    require(type(manifest) is dict and set(manifest)==set(evaluator._MANIFEST_FIELDS)
        and manifest['manifest_sha256']==input_binding['evaluator_manifest_sha256']
        and digest({key:value for key,value in manifest.items() if key not in ('manifest_id','manifest_sha256')})==manifest['manifest_sha256']
        and manifest['manifest_id']=='arv2-preliminary-rating-manifest-'+manifest['manifest_sha256'][:24], 'manifest')
    session_rows=tuple({'schema':evaluator.SESSION_SCHEMA,'session_index':index,'session':session}
        for index,session in enumerate(axis))
    require(type(manifest['session_axis_count']) is int and manifest['session_axis_count']==len(axis)
        and evaluator._stream_sha256(session_rows)==manifest['session_axis_sha256']==input_binding['session_axis_sha256']
        and input_binding['ordered_session_values_sha256']==AXIS_SHA256
        and input_binding['session_axis_count']==len(axis)
        and input_binding['first_session']==axis[0] and input_binding['last_session']==axis[-1],'manifest')
    require(type(membership_rows) in (list,tuple) and type(manifest['membership_row_count']) is int
        and len(membership_rows)==manifest['membership_row_count']
        and 0<len(membership_rows)<=evaluator.MAX_SECURITY_COUNT
        and evaluator._stream_sha256(tuple(membership_rows))==manifest['membership_rows_sha256'],'memberships')
    try:
        memberships=evaluator._parse_memberships(tuple(membership_rows),len(axis))
        expected=targets.make_quarantine_catalog(bindings)
        catalog=archive.loads(catalog_raw,65536)
        require(catalog==expected,'quarantine')
        targets.validate_quarantine_catalog(catalog,expected_sha256=CATALOG_PIN['sha256'])
    except Refused:raise
    except evaluator.PreliminaryRatingEvaluationError:raise Refused('memberships') from None
    except (targets.NewruleError,targets.policy.NewruleError,archive.Refused):raise Refused('quarantine') from None
    require(type(bindings) in (list,tuple) and len(bindings)==fmt.STOCK_COUNT,'catalog')
    contract=input_binding['binding_contract']
    require(type(contract) is dict and set(contract)=={'binding_count','binding_stream_sha256',
        'security_master_admission_sha256','admitted_mapping_inventory_sha256'}
        and type(contract['binding_count']) is int and contract['binding_count']==len(bindings)
        and contract['binding_stream_sha256']==fmt.BINDING_SHA256==targets.ORIGINAL_BINDING_STREAM_SHA256
        and contract['security_master_admission_sha256']==targets.ADMISSION_SHA256
        and all(row['admitted_mapping_count']==len(bindings)
            and row['admitted_mapping_inventory_sha256']==contract['admitted_mapping_inventory_sha256'] for row in bindings)
        and manifest['source_lineage_sha256s']['security_master_admission_sha256']==targets.ADMISSION_SHA256,'input_binding')
    ids={row['security_id'] for row in bindings}
    require(len(ids)==len(bindings) and all(row.security_id in ids for row in memberships),'memberships')
    budget(deadline)
    return memberships,catalog


def _axes(axis,vendor):
    positions={day:index for index,day in enumerate(axis)}
    require(FIRST in positions and PRIOR in positions and CUTOFF in positions
        and positions[FIRST]>0 and axis[positions[FIRST]-1]==PRIOR
        and positions[CUTOFF]+1==positions[LAST],'period')
    decisions=[];seen=set()
    for day in axis:
        if FIRST<=day<=CUTOFF:
            week=date.fromisoformat(day).isocalendar()[:2]
            if week not in seen:seen.add(week);decisions.append(day)
    price_axis=tuple(day for day in axis if PRIOR<=day<=LAST)
    require(len(decisions)==EXPECTED_DECISIONS and decisions[0]==FIRST and decisions[-1]==CUTOFF
        and len(price_axis)==EXPECTED_PRICE_SESSIONS and price_axis[0]==PRIOR and price_axis[-1]==LAST,'period')
    require(tuple(vendor['price_sessions'])==tuple(day for day in axis if fmt.FIRST<=day<=fmt.LAST),'axis')
    return positions,tuple(decisions),price_axis


def _demands(axis,bindings,memberships,vendor,catalog,deadline):
    positions,decisions,price_axis=_axes(axis,vendor)
    price_positions={day:index for index,day in enumerate(vendor['price_sessions'])}
    intervals=defaultdict(list)
    for row in memberships:intervals[row.security_id].append(row)
    denied=set(targets.denied_security_ids(catalog,expected_sha256=CATALOG_PIN['sha256']))
    require(len(vendor['assignments'])==fmt.STOCK_COUNT+fmt.FUND_COUNT,'assignment')
    native=[];records=[]
    for slot,(binding,assigned) in enumerate(zip(bindings,vendor['assignments'][:fmt.STOCK_COUNT],strict=True)):
        budget(deadline)
        require(assigned['binding_ordinal']==slot and assigned['whole_binding_sha256']==digest(binding)
            and assigned['semantic_binding_sha256']==binding['row_sha256']
            and assigned['security_id']==binding['security_id'],'assignment')
        eligible=tuple(day for day in decisions if any(row.first_session_index<=positions[day]<row.last_session_index_exclusive
            for row in intervals[binding['security_id']]))
        if assigned['role']==fmt.NATIVE:native.append(digest(binding))
        quarantined=binding['security_id'] in denied
        require(quarantined is (assigned['role']==fmt.NATIVE),'quarantine')
        require(assigned['role']!=fmt.CONDITIONAL or not eligible,'conditional_demand')
        require(assigned['role'] in (fmt.VENDOR,fmt.NATIVE,fmt.CONDITIONAL),'assignment')
        first=price_positions[axis[positions[eligible[0]]-1]] if eligible and not quarantined else None
        refs=[price_positions[axis[positions[day]-1]] for day in eligible] if not quarantined else []
        records.append({'source_slot':slot,'source_role':assigned['role'],'quarantined':quarantined,
            'eligible_decision_count':len(eligible),'first_price_session_index':first,
            'reference_price_session_indexes':refs})
    require(set(native)==set(targets.QUARANTINED_WHOLE_BINDING_SHA256S) and len(native)==5,'quarantine')
    for ordinal,ticker in enumerate(fmt.OWN_FUNDS):
        assigned=vendor['assignments'][fmt.STOCK_COUNT+ordinal]
        require(assigned['fund_ordinal']==ordinal and assigned['own_ETF']==ticker and assigned['role']==fmt.VENDOR,'assignment')
        records.append({'source_slot':fmt.STOCK_COUNT+ordinal,'source_role':fmt.VENDOR,'quarantined':False,
            'eligible_decision_count':len(decisions),'first_price_session_index':price_positions[PRIOR],
            'reference_price_session_indexes':[price_positions[axis[positions[day]-1]] for day in decisions]})
    return records,decisions,price_axis


def _empty_counts():
    return {'demanded_binding_count':0,'required_dense_cell_count':0,'valid_required_dense_cell_count':0,
        'missing_required_dense_cell_count':0,'potential_reference_cell_count':0,
        'valid_potential_reference_cell_count':0,'missing_potential_reference_cell_count':0}


def _add(target,source):
    for key in target:target[key]+=source[key]


def _prepare(archive_raw,catalog_raw,*,axis,bindings,membership_rows,evaluator_manifest,input_binding,transport_nonce,deadline):
    """Return complete diagnostic evidence, including INCOMPLETE price coverage."""
    budget(deadline)
    require(type(transport_nonce) is str and re.fullmatch('[0-9a-f]{64}',transport_nonce) is not None,
        'transport_nonce')
    memberships,catalog=_inputs(axis,bindings,membership_rows,evaluator_manifest,input_binding,catalog_raw,deadline)
    try:vendor,manifest,descriptors=archive.parse_archive(archive_raw,deadline=deadline)
    except archive.Refused as error:
        raise Refused('deadline' if archive.finite(error)=='deadline' else 'archive') from None
    records,decisions,price_axis=_demands(axis,bindings,memberships,vendor,catalog,deadline)
    refs=[frozenset(row['reference_price_session_indexes']) for row in records]
    counts=[_empty_counts() for _ in records]
    for row,result in zip(records,counts,strict=True):result['demanded_binding_count']=int(row['first_price_session_index'] is not None)
    missing=[];observed_valid=observed_null=0;grid_rows=0
    for ordinal,month in enumerate(manifest['months']):
        budget(deadline)
        descriptor=descriptors[f'month_{ordinal:03d}'];offset=descriptor['payload_offset']
        raw=archive_raw[offset:offset+descriptor['byte_count']]
        try:values=fmt.validate_shard(raw,catalog=vendor,summary=month,deadline=deadline)
        except fmt.Refused as error:
            raise Refused('deadline' if fmt.finite(error)=='deadline' else 'grid') from None
        sessions=month['session_indexes'];width=len(sessions)
        for slot_position,slot in enumerate(vendor['vendor_slots']):
            budget(deadline);record=records[slot];result=counts[slot]
            first=record['first_price_session_index']
            for session_position,index in enumerate(sessions):
                value=values[slot_position*width+session_position];grid_rows+=1
                observed_null+=value is None;observed_valid+=value is not None
                dense=first is not None and index>=first
                reference=index in refs[slot]
                require(not reference or dense,'output')
                if not dense:continue
                result['required_dense_cell_count']+=1
                result['potential_reference_cell_count']+=reference
                if value is None:
                    result['missing_required_dense_cell_count']+=1
                    result['missing_potential_reference_cell_count']+=reference
                    require(len(missing)<MAX_MISSING_PAIRS,'missing_bound')
                    missing.append([slot,index,DENSE_MASK|(REFERENCE_MASK if reference else 0)])
                else:
                    result['valid_required_dense_cell_count']+=1
                    result['valid_potential_reference_cell_count']+=reference
    require(grid_rows==manifest['row_count'] and observed_valid==manifest['valid_count']==fmt.OBSERVED_ROWS
        and observed_null==manifest['absent_count']==fmt.ABSENT_CELLS,'grid')
    missing.sort()
    stock=_empty_counts()
    for row in counts[:fmt.STOCK_COUNT]:_add(stock,row)
    funds=[]
    for size in (6,8):
        value=_empty_counts()
        for row in counts[fmt.STOCK_COUNT:fmt.STOCK_COUNT+size]:_add(value,row)
        funds.append(value)
    cells=[]
    for ordinal,(size,arm) in enumerate(CELLS):
        fund=funds[0 if size==6 else 1];combined=_empty_counts();_add(combined,stock);_add(combined,fund)
        cells.append({'cell_ordinal':ordinal,'universe_count':size,'ar_percent':arm,
            'stock':dict(stock),'fund':dict(fund),'combined':combined,
            'conservative_required_price_coverage_complete':combined['missing_required_dense_cell_count']==0})
    private={'schema':PRIVATE_SCHEMA,'research_epoch_id':targets.RESEARCH_EPOCH_ID,
        'transport_nonce':transport_nonce,
        'input_binding':json.loads(canonical(input_binding)),'quarantine_catalog_pin':dict(CATALOG_PIN),
        'vendor_archive_pin':dict(archive.ARCHIVE_PIN),'vendor_catalog_pin':{key:descriptors['catalog'][key] for key in ('byte_count','sha256')},
        'vendor_manifest_pin':{key:descriptors['manifest'][key] for key in ('byte_count','sha256')},
        'demand_records':records,'missing_required_pairs':missing,
        'missing_pair_layout':['source_slot','vendor_price_session_index','demand_mask'],
        'missing_reason':'authenticated_explicit_null','source_price_session_count':len(vendor['price_sessions']),
        **FALSE_FLAGS}
    private_raw=canonical(private);require(len(private_raw)<=MAX_PRIVATE_BYTES,'private_bound')
    summary={'schema':SCHEMA,'research_epoch_id':targets.RESEARCH_EPOCH_ID,'quarantine_policy_sha256':targets.quarantine_policy_sha256(),
        'input_binding_pin':dict(INPUT_BINDING_PIN),'quarantine_catalog_pin':dict(CATALOG_PIN),
        'vendor_archive_pin':dict(archive.ARCHIVE_PIN),'vendor_catalog_pin':private['vendor_catalog_pin'],
        'vendor_manifest_pin':private['vendor_manifest_pin'],'private_evidence_pin':pin(private_raw),
        'observation_complete':True,'all_71_months_and_all_rows_validated':True,
        'all_six_same_stock_superset':True,'empty_initial_holdings_and_frozen_runtime_conditions_required':True,
        'full_stock_binding_count':fmt.STOCK_COUNT,'own_fund_count':fmt.FUND_COUNT,
        'vendor_stock_count':fmt.VENDOR_COUNT,'quarantined_binding_count':5,'conditional_binding_count':fmt.CONDITIONAL_COUNT,
        'conditional_demand_count':0,'quarantined_demand_count':0,'month_count':fmt.MONTH_COUNT,
        'observed_grid_row_count':grid_rows,'observed_valid_cell_count':observed_valid,'observed_null_cell_count':observed_null,
        'W5_price_session_count':len(price_axis),'decision_count':len(decisions),
        'missing_pair_count':len(missing),'missing_reason_counts':{'authenticated_explicit_null':len(missing)},
        'conservative_required_price_coverage_complete':len(missing)==0,'cells':cells,**FALSE_FLAGS}
    validate_summary(summary);budget(deadline)
    return summary,private


def prepare(archive_raw,catalog_raw,*,axis,bindings,membership_rows,evaluator_manifest,input_binding,transport_nonce,deadline):
    """Finite boundary; a timer BaseException remains outside ordinary parsing."""
    try:
        return _prepare(archive_raw,catalog_raw,axis=axis,bindings=bindings,membership_rows=membership_rows,
            evaluator_manifest=evaluator_manifest,input_binding=input_binding,transport_nonce=transport_nonce,deadline=deadline)
    except Refused:raise
    except (KeyError,TypeError,ValueError,IndexError,OverflowError,RecursionError):
        raise Refused('input_shape') from None


def _counts(value,max_bindings):
    keys=set(_empty_counts())
    require(type(value) is dict and set(value)==keys and all(type(value[key]) is int and value[key]>=0 for key in keys),'output')
    require(value['demanded_binding_count']<=max_bindings
        and value['required_dense_cell_count']==value['valid_required_dense_cell_count']+value['missing_required_dense_cell_count']
        and value['potential_reference_cell_count']==value['valid_potential_reference_cell_count']+value['missing_potential_reference_cell_count']
        and value['potential_reference_cell_count']<=value['required_dense_cell_count']
        and value['valid_potential_reference_cell_count']<=value['valid_required_dense_cell_count']
        and value['missing_potential_reference_cell_count']<=value['missing_required_dense_cell_count']
        and value['required_dense_cell_count']<=value['demanded_binding_count']*EXPECTED_PRICE_SESSIONS
        and value['potential_reference_cell_count']<=value['demanded_binding_count']*EXPECTED_DECISIONS,'output')
    return value


def validate_summary(value):
    fixed={'full_stock_binding_count':fmt.STOCK_COUNT,'own_fund_count':fmt.FUND_COUNT,'vendor_stock_count':fmt.VENDOR_COUNT,
        'quarantined_binding_count':5,'conditional_binding_count':fmt.CONDITIONAL_COUNT,'conditional_demand_count':0,
        'quarantined_demand_count':0,'month_count':fmt.MONTH_COUNT,'observed_valid_cell_count':fmt.OBSERVED_ROWS,
        'observed_null_cell_count':fmt.ABSENT_CELLS,'W5_price_session_count':EXPECTED_PRICE_SESSIONS,'decision_count':EXPECTED_DECISIONS}
    pins=('input_binding_pin','quarantine_catalog_pin','vendor_archive_pin','vendor_catalog_pin','vendor_manifest_pin','private_evidence_pin')
    truths=('observation_complete','all_71_months_and_all_rows_validated','all_six_same_stock_superset',
        'empty_initial_holdings_and_frozen_runtime_conditions_required')
    keys={'schema','research_epoch_id','quarantine_policy_sha256','observed_grid_row_count','missing_pair_count',
        'missing_reason_counts','conservative_required_price_coverage_complete','cells',*pins,*truths,*fixed,*FALSE_FLAGS}
    require(type(value) is dict and set(value)==keys and value['schema']==SCHEMA
        and value['research_epoch_id']==targets.RESEARCH_EPOCH_ID
        and value['quarantine_policy_sha256']==targets.quarantine_policy_sha256()
        and all(value[key] is True for key in truths) and all(value[key] is False for key in FALSE_FLAGS)
        and all(type(value[key]) is int and value[key]==number for key,number in fixed.items()),'output')
    require(type(value['observed_grid_row_count']) is int and value['observed_grid_row_count']==fmt.OBSERVED_ROWS+fmt.ABSENT_CELLS
        and type(value['missing_pair_count']) is int and 0<=value['missing_pair_count']<=MAX_MISSING_PAIRS
        and value['missing_pair_count']<=value['observed_null_cell_count']
        and type(value['missing_reason_counts']) is dict
        and type(value['missing_reason_counts'].get('authenticated_explicit_null')) is int
        and value['missing_reason_counts']=={'authenticated_explicit_null':value['missing_pair_count']}
        and type(value['conservative_required_price_coverage_complete']) is bool
        and value['conservative_required_price_coverage_complete'] is (value['missing_pair_count']==0),'output')
    for key in pins:_pin(value[key],MAX_PRIVATE_BYTES if key=='private_evidence_pin' else 192*1024*1024)
    require(value['input_binding_pin']==INPUT_BINDING_PIN and value['quarantine_catalog_pin']==CATALOG_PIN
        and value['vendor_archive_pin']==archive.ARCHIVE_PIN,'output')
    require(type(value['cells']) is list and len(value['cells'])==len(CELLS),'output')
    for ordinal,(cell,(size,arm)) in enumerate(zip(value['cells'],CELLS,strict=True)):
        require(type(cell) is dict and set(cell)=={'cell_ordinal','universe_count','ar_percent','stock','fund','combined',
            'conservative_required_price_coverage_complete'} and type(cell['cell_ordinal']) is int and cell['cell_ordinal']==ordinal
            and type(cell['universe_count']) is int and cell['universe_count']==size
            and type(cell['ar_percent']) is int and cell['ar_percent']==arm,'output')
        stock=_counts(cell['stock'],fmt.VENDOR_COUNT);fund=_counts(cell['fund'],size);combined=_counts(cell['combined'],fmt.VENDOR_COUNT+size)
        require(fund['demanded_binding_count']==size and fund['required_dense_cell_count']==size*EXPECTED_PRICE_SESSIONS
            and fund['potential_reference_cell_count']==size*EXPECTED_DECISIONS
            and all(combined[key]==stock[key]+fund[key] for key in combined)
            and type(cell['conservative_required_price_coverage_complete']) is bool
            and cell['conservative_required_price_coverage_complete'] is (combined['missing_required_dense_cell_count']==0)
            and stock==value['cells'][0]['stock'],'output')
        if ordinal%3:require(cell['fund']==value['cells'][ordinal-1]['fund'],'output')
    six,eight=value['cells'][0],value['cells'][3]
    require(all(six['fund'][key]<=eight['fund'][key] for key in _empty_counts())
        and eight['combined']['missing_required_dense_cell_count']==value['missing_pair_count'],'output')
    require(len(canonical(value))<=MAX_SUMMARY_BYTES,'output');return value
