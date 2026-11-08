"""Pure public-calendar period contracts; no DATA, acquisition or QC operation."""
import ast
import copy
from datetime import date
import hashlib
import inspect
from pathlib import Path
import pytest
from scripts import arv2_r327_available_history_period as m
from research.analyst_revisions_v2_qc import accepted_risk_october_order_package as october
from research.analyst_revisions_v2_qc import newrule_comparison_qc_runtime as old
from research.analyst_revisions_v2_qc import newrule_native_price_book_runtime as native


@pytest.fixture(scope='module')
def axis():return october._sessions()


@pytest.fixture(scope='module')
def period(axis):return m.make_period(axis)


def fail(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def test_full_calendar_binding_precedes_new_period_geometry(axis,period):
    assert len(axis)==3466 and m.digest(list(axis))==m.FULL_AXIS_SHA256
    assert period['evaluation_first']=='2021-11-01' and period['evaluation_last']=='2026-10-13'
    assert period['first_reference_close']==axis[axis.index('2021-11-01')-1]=='2021-10-29'
    assert period['reference_and_valuation_price_sessions']==['2021-10-29',*period['evaluation_sessions']]
    assert period['reference_and_valuation_price_session_count']==period['evaluation_session_count']+1
    assert period['full_axis_count']==3466 and period['retained_stock_binding_count']==6151 and period['retained_own_fund_count']==8


@pytest.mark.parametrize('issue',('list','short','bool','oversize_string'))
def test_axis_types_and_bounds_refuse_before_derivation(axis,issue,monkeypatch):
    value=list(axis)
    if issue=='list':pass
    elif issue=='short':value=tuple(value[:-1])
    elif issue=='bool':value[100]=True;value=tuple(value)
    else:value[100]='2'*11;value=tuple(value)
    monkeypatch.setattr(m,'_weekly',lambda *_:pytest.fail('weekly derivation before full axis validation'))
    fail('axis_type',lambda:m.make_period(value))


@pytest.mark.parametrize('issue',('substitute','reorder','duplicate','last'))
def test_unchanged_count_is_insufficient_without_exact_full_axis_hash(axis,issue,monkeypatch):
    value=list(axis)
    if issue=='substitute':
        index=next(index for index in range(1,len(axis)) if (date.fromisoformat(axis[index])-date.fromisoformat(axis[index-1])).days>=3)
        value[index]=date.fromordinal(date.fromisoformat(axis[index]).toordinal()-1).isoformat()
    elif issue=='reorder':value[100],value[101]=value[101],value[100]
    elif issue=='duplicate':value[100]=value[101]
    else:value[-1]='2026-10-14'
    monkeypatch.setattr(m,'_weekly',lambda *_:pytest.fail('weekly derivation before exact full axis hash'))
    fail('axis_hash',lambda:m.make_period(tuple(value)))


def test_no_silent_shortening_or_mutation_of_old_runtime(axis,period):
    assert old.START_SESSION=='2021-01-04' and old.DECISION_CUTOFF=='2026-10-12' and old.END_SESSION=='2026-10-13'
    assert period['decision_sessions']==[session for session in old.weekly_axis(axis) if session>='2021-11-01']
    assert period['decision_sessions'][0]=='2021-11-01' and period['decision_sessions'][-1]=='2026-10-12'
    assert period['prior_candidate_accepted'] is False and period['runtime_projection_generated'] is False


def test_weekly_holiday_rule_uses_actual_source_calendar(period):
    assert '2022-01-18' in period['decision_sessions'] and '2022-01-17' not in period['decision_sessions']
    assert '2022-09-06' in period['decision_sessions'] and '2022-09-05' not in period['decision_sessions']
    keys=[date.fromisoformat(session).isocalendar()[:2] for session in period['decision_sessions']]
    assert len(keys)==len(set(keys))==period['decision_count']


def test_month_geometry_and_return_bases_derive_from_new_axis(period):
    sessions=period['evaluation_sessions'];covered=[]
    assert period['months'][0]['month']=='2021-11' and period['months'][-1]['month']=='2026-10'
    for index,row in enumerate(period['months']):
        selected=sessions[row['first_evaluation_index']:row['last_evaluation_index_exclusive']]
        assert selected[0]==row['first_session'] and selected[-1]==row['last_session']
        assert len(selected)==row['session_count'] and m.digest(selected)==row['sessions_sha256']
        assert {value[:7] for value in selected}=={row['month']} and row['month_ordinal']==index
        assert row['return_base']==('new_epoch_initial_cash_USD1000000' if index==0 else 'previous_month_authoritative_last_close_NAV')
        covered.extend(selected)
    assert covered==sessions and len(period['months'])==period['month_count']==len({session[:7] for session in sessions})


def test_all_six_cells_bind_one_new_epoch_window_cash_and_sources(period):
    cells=period['cells'];assert [(item['universe_count'],item['ar_percent']) for item in cells]==list(m.CELLS)
    assert len({item['candidate_id'] for item in cells})==6 and all(item['candidate_id'].startswith('arv2-r327-') for item in cells)
    keys=('research_epoch_id','evaluation_sessions_sha256','decision_sessions_sha256','source_policy_sha256','economics_policy_sha256','starting_cash_USD')
    assert all({key:item[key] for key in keys}=={key:period[key] for key in keys} for item in cells)
    assert all(item['own_funds']==list(m.OWN_FUNDS[:item['universe_count']]) for item in cells)
    assert period['starting_cash_USD']=='1000000' and period['research_epoch_id']==m.RESEARCH_EPOCH_ID


def test_original_hybrid_policy_is_fixed_without_EOD_or_price_selection(period):
    source=period['source_policy'];assert source['Sharadar_stock_count']==5636 and source['Sharadar_fund_count']==8
    assert source['native_stock_count']==5 and source['conditional_never_potential_stock_count']==510
    assert source['native_whole_binding_sha256s']==native.source_context()['specification']['selected_whole_binding_sha256s']
    assert source['native_specification_sha256']==native.source_context()['scope']['source_specification_sha256']
    assert source['stock_binding_count']==5636+5+510==6151
    assert source['EOD_crosswalk_used_as_source_selector'] is source['known_native_gap_resolved'] is False
    assert 'October21_2022' in source['known_native_gap']


def test_first_cash_CAGR_and_actual_NAV_labels_use_new_start(period):
    policy=period['economics_policy']
    assert policy['starting_cash_USD']=='1000000' and policy['initial_holdings']=='empty_all_stock_and_fund_positions'
    assert '2021Nov01' in policy['first_decision_sizing_NAV'] and '2021Jan04' not in m.canonical(policy).decode()
    assert period['elapsed_calendar_days']==(date(2026,10,13)-date(2021,11,1)).days and period['CAGR_year_days']=='365.25'
    assert policy['gross_target']=='0.98' and policy['aggregate_stock_target_cap']=='0.098' and policy['fee_bps']=='10'
    assert policy['whole_shares'] is policy['long_only'] is policy['sell_before_buy'] is policy['cash_bound_buys'] is True
    assert '09:20' in policy['snapshot_clock'] and '09:31' in policy['execution_clock']
    assert 'no_vendor_close' in policy['execution_quotes'] and 'actual_QC_cash' in policy['authoritative_NAV']


@pytest.mark.parametrize('issue',('count_bool','date','prior','cell','old_candidate','epoch','cash','source','ready','field','period_pin','profile_pin'))
def test_closed_period_tampering_refuses(axis,period,issue):
    value=copy.deepcopy(period)
    if issue=='count_bool':value['evaluation_session_count']=True
    elif issue=='date':value['evaluation_first']='2022-01-03'
    elif issue=='prior':value['first_reference_close']='2021-10-28'
    elif issue=='cell':value['cells'][3]['ar_percent']=100
    elif issue=='old_candidate':value['cells'][0]['candidate_id']='R298'
    elif issue=='epoch':value['research_epoch_id']='old-full-2021'
    elif issue=='cash':value['cells'][0]['starting_cash_USD']='100000'
    elif issue=='source':value['source_policy']['native_stock_count']=4
    elif issue=='ready':value['price_coverage_proven']=True
    elif issue=='field':value['unexpected_prices']={'synthetic':1}
    elif issue=='period_pin':value['period_sha256']='e'*64
    else:value['profile_sha256']='e'*64
    fail('record',lambda:m.validate_period(value,axis))


def test_record_roundtrip_bound_and_independent_copies(axis,period):
    assert len(m.canonical(period))<=m.MAX_RECORD_BYTES and m.validate_period(period,axis)==period
    checked=m.validate_period(period,axis);checked['cells'][0]['candidate_id']='changed'
    assert m.make_period(axis)==period and checked!=period
    seed=dict(period);pin=seed.pop('period_sha256');assert pin==m.digest(seed)
    assert all(period[key] is False for key in m.FALSE_FLAGS)


def test_no_acquisition_callback_or_old_global_mutation_surface():
    tree=ast.parse(inspect.getsource(m));modules=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):modules.extend(alias.name for alias in node.names)
        elif isinstance(node,ast.ImportFrom):modules.append(node.module)
    assert set(modules)=={'datetime','hashlib','json'}
    assert list(inspect.signature(m.make_period).parameters)==['full_axis']
    assert 'open(' not in inspect.getsource(m) and 'setattr(' not in inspect.getsource(m)


def test_selected_unchanged_economic_source_pins():
    root=Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
    assert all(hashlib.sha256((root/name).read_bytes()).hexdigest()==expected for name,expected in m.FROZEN_POLICY_PINS.items())
