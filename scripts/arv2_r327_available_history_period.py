"""Pure prospective available-history period; no source or execution authority.

The full genuine calendar is supplied by a separately authorized caller. Its
fixed content hash precedes every derived axis. This metadata contract neither
modifies a frozen runtime nor admits the retained prices or their missing cells.
"""
from datetime import date
import hashlib
import json

SCHEMA='arv2-r327-available-history-period-v1'
RESEARCH_EPOCH_ID='R327-20261027-available-history-v1'
FIRST,PRIOR,DECISION_CUTOFF,LAST='2021-11-01','2021-10-29','2026-10-12','2026-10-13'
PRIOR_CANDIDATE_FIRST='2021-01-04'
FULL_AXIS_COUNT=3466
FULL_AXIS_SHA256='4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585'
PACKAGE_SHA256='1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2'
LINEAGE_SHA256='e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9'
BINDING_STREAM_SHA256='73ba4ac73c0485b2d274c31b5ec740a97a64de27a4f6dfbfb9cb63bc8e7cd15f'
NATIVE_SPECIFICATION_SHA256='9da6813b4807d7ebf0ea32fddd38ab0740ff6c6edbc3bd05cdc5889775eb1f66'
NATIVE_WHOLE_BINDING_SHA256S=(
    '1e241c9aca6d79eef7020990ffa7bca14b8059a72e67bb42a767690ded624331',
    'b0147c90e6741dc9b7697b82cc1d1dc459a0de4445d54c540cdfa7e9319fdce8',
    'b44a76e5db7cedcfc5ddfa6671b6cb28feb306d434d8d3cda3710fb7e3fd61c9',
    'c15d10303e03ea8eb0ce007bed1db63bfc626337dcda2bd94798ef09a5c058f7',
    'f352b4d726b30dc4c0d9ac2b607d4c003dc8ebc4de2fc7442b97b6d8c3f1b986')
OWN_FUNDS=('SPY','QQQ','SOXX','XLV','REMX','XLE','XLI','XLF')
CELLS=((6,0),(6,100),(6,200),(8,0),(8,100),(8,200))
STARTING_CASH='1000000'
MAX_RECORD_BYTES=131072
FROZEN_POLICY_PINS={
    'research/analyst_revisions_v2_qc/newrule_comparison_targets.py':'30ed05cbc02bb0076d09c82467a32ad840ead87561f3e2a1ae1cc5a9ee65f29d',
    'research/analyst_revisions_v2_qc/newrule_comparison_qc_runtime.py':'674415b3179836a613afc6f7bdea23a966db21ab67221472fc5d87b4a742049d',
    'scripts/arv2_newrule_quote_execution_projection.py':'ebc6d921c5dbaa5e9bc83379ab45c167780fb87db8441dbd9d618b3efcb1715f',
    'research/analyst_revisions_v2_qc/newrule_common_price_qc_runtime.py':'e9c79d20429b9041874e615a1e6ee06824c640c635ebe75c3868b53018350c89'}
FALSE_FLAGS={'provider_contact':False,'credential_access':False,'QC_contact':False,'file_or_control_access':False,
    'genuine_calendar_authority_authenticated':False,'full_binding_inventory_freshly_authenticated':False,
    'source_grant_created':False,'price_input_admitted':False,'price_coverage_proven':False,
    'known_native_gap_resolved':False,'EOD_crosswalk_used_as_source_selector':False,
    'identities_or_source_assignments_changed':False,'conditional_never_is_unconditional':False,
    'prior_candidate_accepted':False,'runtime_projection_generated':False,'backtest_created':False,
    'new_launch_attempt_granted':False,'outcome_comparability_proven':False,
    'point_in_time_proven':False,'formal_identity_admitted':False,'formal_forward_epoch_assigned':False,
    'formal_forward_ready':False,'paper_or_live_ready':False}
FINITE=frozenset(('axis_type','axis_hash','axis_shape','period_geometry','weekly_geometry','monthly_geometry',
    'record_bound','record','unknown'))


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def finite(error):
    args=BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args)==1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


def digest(value):return hashlib.sha256(canonical(value)).hexdigest()


def source_policy():
    return {'schema':SCHEMA+'-original-source-policy','stock_binding_count':6151,'own_fund_count':8,
        'binding_stream_sha256':BINDING_STREAM_SHA256,'Sharadar_stock_count':5636,'Sharadar_fund_count':8,
        'native_stock_count':5,'conditional_never_potential_stock_count':510,
        'native_specification_sha256':NATIVE_SPECIFICATION_SHA256,
        'native_whole_binding_sha256s':list(NATIVE_WHOLE_BINDING_SHA256S),
        'assignment':'unchanged_original_AP_per_binding_Sharadar5636_native5_conditional510_same_all_six_cells',
        'stock_assignment_retention':'all6151_original_bindings_retained_no_price_or_EOD_source_stop_selection',
        'conditional_never':'requires_authenticated_membership_absence_and_empty_initial_runtime_any_unexpected_holding_stops',
        'source_containers':'unchanged_retained_AP_and_AR_vendor_DATA_and_QC_only_native_book',
        'first_reference_close':PRIOR,'last_valuation_close':LAST,
        'holding_lifetime':'neither_binding_membership_metadata_nor_last_price_date_ends_positive_holdings',
        'missing_mark':'finite_stop_no_stale_scalar_quote_engine_cache_or_other_source_substitution',
        'known_native_gap':'October21_2022_remains_inside_this_period_not_cleared_by_changing_start',
        'identity_and_history':'qualified_current_vintage_not_permanent_master_or_immutable_PIT',**FALSE_FLAGS}


def economics_policy():
    return {'schema':SCHEMA+'-unchanged-economics','starting_cash_USD':STARTING_CASH,
        'initial_holdings':'empty_all_stock_and_fund_positions','initial_open_orders':'none',
        'first_decision_sizing_NAV':'USD1000000_initial_cash_at_2021Nov01_before_orders',
        'later_decision_sizing_NAV':'exact_immediately_prior_NYSE_after_close_authoritative_NAV',
        'snapshot_clock':'same_session_09:20_New_York_genuine_clock_confirmation',
        'execution_clock':'same_session_09:31_New_York_regular_hours_market_submission',
        'execution_quotes':'unchanged_genuine_current_signed_bid_ask_quotes_no_vendor_close_or_clock_bar_substitute',
        'rating_eligibility':'original_eligible_session_strictly_before_decision_session',
        'weekly_decision_rule':'first_actual_NYSE_session_in_each_ISO_week',
        'reference_prices':'immediately_prior_NYSE_RAW_USD_close_target_union_all_positive_holdings',
        'split_bridge':'unchanged_separate_pre0920_same_session_SplitOccurred_unit_factor',
        'authoritative_NAV':'actual_QC_cash_plus_actual_positive_whole_holdings_times_same_session_admitted_RAW_close',
        'cash_actions_fees':'actual_cash_corporate_actions_and_engine_fees_once_no_reinvestment_or_double_adjustment',
        'gross_target':'0.98','aggregate_stock_target_cap':'0.098','fee_bps':'10','slippage_model_bps':'0',
        'whole_shares':True,'long_only':True,'sell_before_buy':True,'cash_bound_buys':True,
        'terminal':'2026Oct13_valuation_only_no_forced_rebalance',
        'returns':'terminal_NAV_divided_by_new_epoch_initial_cash_minus_one',
        'CAGR':'365.25_over_calendar_days_2021Nov01_to2026Oct13',
        'drawdown':'actual_daily_authoritative_close_NAV_initial_peak_USD1000000',
        'frozen_economic_policy_source_pins':dict(FROZEN_POLICY_PINS),
        'scope':'metadata_contract_only_future_runtime_and_result_reader_must_match_this_period',**FALSE_FLAGS}


def profile_record():
    return {'schema':SCHEMA,'research_epoch_id':RESEARCH_EPOCH_ID,'evaluation_first':FIRST,'evaluation_last':LAST,
        'first_reference_close':PRIOR,'decision_cutoff':DECISION_CUTOFF,
        'full_axis_count':FULL_AXIS_COUNT,'full_axis_sha256':FULL_AXIS_SHA256,
        'package_sha256':PACKAGE_SHA256,'lineage_sha256':LINEAGE_SHA256,'cell_order':[list(cell) for cell in CELLS],
        'source_policy_sha256':digest(source_policy()),'economics_policy_sha256':digest(economics_policy()),
        'maximum_record_bytes':MAX_RECORD_BYTES,
        'owner_scope':'five_year_Sharadar_entitlement_use_existing_available_history_new_matched_evaluation',
        'prior_candidate':'2021Jan04_to2026Oct13_full_period_preserved_unadmitted_not_silently_shortened',
        'comparison':'six_vs_eight_and_AR0_100_200_share_new_epoch_window_sources_cash_and_economics',
        'old_result_comparison':'different_start_and_capital_epoch_require_explicit_qualification_not_direct_same_period_comparison',
        'calendar_authority':'caller_authenticates_genuine_source_this_helper_only_binds_exact_supplied_calendar_content',
        'metadata_only_no_runtime_global_mutation_or_acquisition_interface':True,**FALSE_FLAGS}


def _checked_axis(axis):
    require(type(axis) is tuple and len(axis)==FULL_AXIS_COUNT and all(type(value) is str and len(value)==10 for value in axis),'axis_type')
    # No period, weekly or monthly derivation precedes this full content pin.
    require(digest(list(axis))==FULL_AXIS_SHA256,'axis_hash')
    try:require(all(date.fromisoformat(value).isoformat()==value for value in axis),'axis_shape')
    except ValueError:raise Refused('axis_shape') from None
    require(axis==tuple(sorted(set(axis))) and axis[0]=='2013-01-02' and axis[-1]==LAST,'axis_shape')
    return axis


def _weekly(axis,first):
    selected=[];seen=set()
    for session in axis:
        if first<=session<=DECISION_CUTOFF:
            key=date.fromisoformat(session).isocalendar()[:2]
            if key not in seen:seen.add(key);selected.append(session)
    return tuple(selected)


def _months(sessions):
    result=[];position=0
    while position<len(sessions):
        first=position;label=sessions[position][:7]
        while position<len(sessions) and sessions[position][:7]==label:position+=1
        values=sessions[first:position]
        result.append({'month_ordinal':len(result),'month':label,'first_session':values[0],'last_session':values[-1],
            'first_evaluation_index':first,'last_evaluation_index_exclusive':position,'session_count':len(values),
            'sessions_sha256':digest(list(values)),
            'return_base':'new_epoch_initial_cash_USD1000000' if first==0 else 'previous_month_authoritative_last_close_NAV'})
    require(result and result[0]['month']==FIRST[:7] and result[-1]['month']==LAST[:7]
        and sum(row['session_count'] for row in result)==len(sessions),'monthly_geometry')
    return result


def make_period(full_axis):
    axis=_checked_axis(full_axis);positions={session:index for index,session in enumerate(axis)}
    require(FIRST in positions and PRIOR in positions and DECISION_CUTOFF in positions
        and positions[FIRST]>0 and axis[positions[FIRST]-1]==PRIOR
        and positions[DECISION_CUTOFF]+1==positions[LAST],'period_geometry')
    sessions=tuple(session for session in axis if FIRST<=session<=LAST)
    price_sessions=tuple(session for session in axis if PRIOR<=session<=LAST)
    decisions=_weekly(axis,FIRST);old_decisions=_weekly(axis,PRIOR_CANDIDATE_FIRST)
    require(sessions and sessions[0]==FIRST and sessions[-1]==LAST and price_sessions==(PRIOR,*sessions)
        and decisions and decisions[0]==FIRST and decisions[-1]==DECISION_CUTOFF
        and decisions==tuple(session for session in old_decisions if session>=FIRST),'weekly_geometry')
    months=_months(sessions);source=source_policy();economics=economics_policy();profile=profile_record()
    shared={'research_epoch_id':RESEARCH_EPOCH_ID,'evaluation_sessions_sha256':digest(list(sessions)),
        'decision_sessions_sha256':digest(list(decisions)),'source_policy_sha256':digest(source),
        'economics_policy_sha256':digest(economics),'starting_cash_USD':STARTING_CASH}
    cells=[{'cell_ordinal':ordinal,'candidate_id':f'arv2-r327-{size}-ar{arm}-2021Nov01-2026Oct13-v1',
        'universe_count':size,'ar_percent':arm,'own_funds':list(OWN_FUNDS[:size]),**shared}
        for ordinal,(size,arm) in enumerate(CELLS)]
    value={'schema':SCHEMA,**shared,'profile_sha256':digest(profile),'package_sha256':PACKAGE_SHA256,
        'lineage_sha256':LINEAGE_SHA256,'binding_stream_sha256':BINDING_STREAM_SHA256,
        'retained_stock_binding_count':6151,'retained_own_fund_count':8,'full_axis_count':len(axis),'full_axis_sha256':FULL_AXIS_SHA256,
        'evaluation_first':FIRST,'evaluation_last':LAST,'first_reference_close':PRIOR,'decision_cutoff':DECISION_CUTOFF,
        'evaluation_sessions':list(sessions),'evaluation_session_count':len(sessions),
        'reference_and_valuation_price_sessions':list(price_sessions),'reference_and_valuation_price_session_count':len(price_sessions),
        'reference_and_valuation_price_sessions_sha256':digest(list(price_sessions)),
        'decision_sessions':list(decisions),'decision_count':len(decisions),'months':months,'month_count':len(months),
        'elapsed_calendar_days':(date.fromisoformat(LAST)-date.fromisoformat(FIRST)).days,'CAGR_year_days':'365.25',
        'first_month_return_base':'new_epoch_initial_cash_USD1000000','later_month_return_base':'previous_month_authoritative_last_close_NAV',
        'source_policy':source,'economics_policy':economics,'cells':cells,
        'all_six_same_window_source_and_capital_epoch':True,'new_decisions_are_subset_of_preserved_prior_calendar':True,
        'full_original_calendar_verified_binding_inventory_retention_required':True,'metadata_contract_only':True,**FALSE_FLAGS}
    result={**value,'period_sha256':digest(value)}
    require(0<len(canonical(result))<=MAX_RECORD_BYTES,'record_bound')
    return result


def validate_period(value,full_axis):
    require(type(value) is dict,'record')
    try:raw=canonical(value)
    except (ValueError,TypeError,RecursionError):raise Refused('record') from None
    require(0<len(raw)<=MAX_RECORD_BYTES and raw==canonical(make_period(full_axis)),'record')
    return json.loads(raw)
