"""Pure synthetic aggregate/profile seams; no control/private/QC operation."""
import copy
from contextlib import contextmanager
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from types import ModuleType,SimpleNamespace as NS

import pytest

from scripts import arv2_r348_legacy_result as m
from scripts import arv2_r343_legacy_six_projection as source_projection
from research.analyst_revisions_v2_qc import legacy_six_october_reporting as reporting
from .test_qc_relaxed_submission import order_fixture


def refused(code,operation):
    with pytest.raises(m.Refused) as caught:operation()
    assert caught.value.args==(code,)


def test_all_embedded_source_and_profile_pins_match_only_public_frozen_R346_fact():
    fact=json.loads((Path(__file__).resolve().parents[2]/'scripts/arv2_r346_preparation_result_fact.json').read_bytes())
    rows=fact['original_result']['report']['summary']['cells']
    assert len(m.FROZEN_CELLS)==len(rows)==7
    for row in rows:
        assert m.FROZEN_CELLS[row['candidate_id']]=={'profile_pin':row['unchanged_profile_pin'],
            'source_vector_pin':m.pin(m.canonical(row['source_files']))}


def test_unpinned_supplied_source_is_refused_before_any_code_execution(monkeypatch):
    monkeypatch.setattr(m.source_contract,'_cell',lambda record:(
        {'candidate_id':'R343-AR100','profile_pin':{'byte_count':1,'sha256':'a'*64},'sources':[]},{}))
    monkeypatch.setattr(m.projection,'_cloud_loader',lambda *a:
        (_ for _ in ()).throw(AssertionError('unbound supplied code executed')))
    refused('source',lambda:m._candidate({}))


@pytest.fixture
def fixture(monkeypatch):
    # Actual frozen structural parsers and period validation are exercised.
    # Only the source authentication/cloud-module boundary is explicitly
    # synthetic: the test never fabricates a genuine package/capability.
    full_axis=source_projection.october._sessions();sessions,decisions=source_projection._geometry(full_axis)
    aggregate,row,meta=order_fixture()
    profile={'role':'synthetic-role','profile_id':'synthetic-profile','profile_sha256':'a'*64,
        'maximum_stock_weight_change_fraction':'1.00','matched_baseline_profile_sha256':'b'*64}
    runtime=NS(EVALUATION_START_SESSION='2021-01-04',EVALUATION_END_SESSION='2026-10-13',
        EXPECTED_SESSION_COUNT=1451,EXPECTED_DECISION_COUNT=302,
        ACCOUNT_PATH_SCHEMA=m.cap.runtime.ACCOUNT_PATH_SCHEMA,_forced=m.cap.runtime._forced)
    observations=tuple((session,Decimal('1000000')) for session in sessions)
    aggregate.update(schema='synthetic-extended-summary',role=profile['role'],profile_id=profile['profile_id'],
        profile_sha256=profile['profile_sha256'],maximum_stock_weight_change_fraction='1.00',
        matched_baseline_profile_sha256='b'*64,comparison_arm='ar_on100',
        analyst_revision_economic_usage='entry_count_and_weight',coverage_policy_id=m.COVERAGE_POLICY)
    aggregate['account']=reporting._population_metrics(observations)
    aggregate['account_observation_path_sha256']=reporting._path_sha256(runtime.ACCOUNT_PATH_SCHEMA,observations)
    aggregate['execution'].update(decision_count=302,submitted_rebalance_count=302,completed_rebalance_count=302,
        submitted_order_count=302,filled_order_count_sum=302,modeled_fee_amount='10',actual_engine_fee_amount='10',
        total_filled_notional='10000',modeled_fee_bps_per_side=10,fee_mismatch=False)
    aggregate['fallback_counts']={'PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK':1812}
    for sleeve in aggregate['sleeve_diagnostics']['rows']:
        sleeve[2]=302;sleeve[10]={'KNOWN_MARKET_CAP_NAME_COUNT_BELOW_MINIMUM':302}
        sleeve[11]={'PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK':302}
    # The unchanged public R343 projection transforms the diagnostic validator's
    # historical literals to its declared six-year geometry, not its economics.
    root=Path(__file__).resolve().parents[2]
    raw=(root/'research/analyst_revisions_v2_qc/accepted_risk_matched_diagnostics.py').read_bytes()
    extended=source_projection._period_source('accepted_risk_matched_diagnostics.py',raw,
        percent=100,old_id='R261',activation={})
    diagnostics=ModuleType('synthetic_extended_diagnostics')
    exec(compile(extended,'<synthetic-public-diagnostics>','exec'),diagnostics.__dict__)
    annual=diagnostics.annual_accounts(dict(observations))
    years=tuple(sorted({session[:4] for session in sessions}))
    report={'schema':diagnostics.REFERENCE_REPAIR_SCHEMA,'arm':'ar_on100','slippage_bps_per_side':0,
        'overall_cumulative_return':'0','annual_account_fields':list(diagnostics.ANNUAL_FIELDS),
        'annual_account_rows':[[item[field] for field in diagnostics.ANNUAL_FIELDS] for item in annual],
        'membership_cap_path_sha256':'c'*64,'source_snapshot_count':302,'diagnostic_history_call_count':1,
        'etf_daily_panel_sha256':'d'*64,'six_etf_panel_row_count':8706,
        'year_universe_fields':list(diagnostics.UNIVERSE_FIELDS),
        'year_universe_rows':[[year,ticker,sum(day.startswith(year) for day in decisions),0,0,0,'0']
            for year in years for ticker in m.cap._UNIVERSES],
        'universe_realized_profit_attributed':False,'all_stock_price_equality_proved':False,
        'minute_execution_price_equality_proved':False,'daily_price_normalization':'RAW','fill_forward':False,
        'closing_minute_reference_repair_count':0,'closing_minute_reference_repair_session_count':0,
        'closing_minute_reference_repair_path_sha256':m.pin(b'[]')['sha256']}
    period=reporting.build_report(dict(observations),evaluation_sessions=sessions,ar_percent=100,
        source_profile_sha256=profile['profile_sha256'],account_path_schema=runtime.ACCOUNT_PATH_SCHEMA,
        legacy_aggregate=aggregate)
    meta.update(schema='synthetic-extended-meta',role=profile['role'],profile_id=profile['profile_id'],
        profile_sha256=profile['profile_sha256'],package_sha256=m.ACTUAL_PACKAGE,
        activation_manifest_sha256=m.ACTIVATION_SHA256,aggregate_schema=aggregate['schema'],
        result_transport='three_bounded_custom_summary_statistics',matched_diagnostics_sha256=m.pin(m.canonical(report))['sha256'])
    row.update(meta_schema=meta['schema'],summary_schema=aggregate['schema'])
    tilt=NS(require_tilt_profile=lambda:copy.deepcopy(profile),TILT_META_SCHEMA=meta['schema'],TILT_SUMMARY_SCHEMA=aggregate['schema'])
    modules={m.TILT:tilt,m.BASE:runtime,m.DIAGNOSTICS:diagnostics,m.REPORTER:reporting}
    @contextmanager
    def cloud_loader(sources):yield lambda name:modules[name],modules
    candidate={'candidate_id':'R343-AR100','ar_percent':100,'profile':profile,
        'profile_pin':m.pin(m.canonical(profile)),'sources':[]}
    monkeypatch.setattr(m,'_candidate',lambda record:(copy.deepcopy(candidate),{}))
    monkeypatch.setattr(m.projection,'_cloud_loader',cloud_loader)
    stats={m.STATISTIC_NAMES[0]:m.canonical(meta).decode('ascii'),
        m.STATISTIC_NAMES[1]:m.canonical(aggregate).decode('ascii'),
        m.STATISTIC_NAMES[2]:m.canonical(report).decode('ascii'),
        m.STATISTIC_NAMES[3]:m.canonical(period).decode('ascii')}
    value={'statistics':stats,'aggregate':aggregate,'meta':meta,'diagnostic':report,'period':period,
        'candidate':candidate,'sessions':sessions,'runtime':runtime,'row':row}
    refresh(value)
    return value


def refresh(value,*,period_digest=True):
    aggregate=value['aggregate'];meta=value['meta'];report=value['diagnostic'];period=value['period']
    raw=m.canonical(aggregate);meta['aggregate_sha256']=m.pin(raw)['sha256']
    meta['matched_diagnostics_sha256']=m.pin(m.canonical(report))['sha256']
    if period_digest:period['legacy_aggregate_sha256']=m.pin(raw)['sha256']
    for name,record in zip(m.STATISTIC_NAMES,(meta,aggregate,report,period),strict=True):
        value['statistics'][name]=m.canonical(record).decode('ascii')


def validate(value):return m.validate_statistics(value['statistics'],candidate_record=value['candidate'],evaluation_sessions=value['sessions'])


def test_valid_new_geometry_reuses_real_parsers_without_old_manifest_IO_or_global_mutation(fixture,monkeypatch):
    original_bounded=m.adapter._bounded_order_base
    original_projector=m.cap._project_aggregate
    def forbidden(*args):raise AssertionError('historical manifest IO')
    monkeypatch.setattr(m.adapter,'_candidate',forbidden);monkeypatch.setattr(m.adapter,'_plan_manifest',forbidden)
    result=validate(fixture)
    assert result['accepted'] is result['run_valid'] is True
    assert result['evaluation_session_count']==1451 and result['account']['observation_count']==1451
    assert result['execution']['completed_rebalance_count']==302 and len(result['periods'])==5
    assert len(m.canonical(result))<=16384 and 'aggregates' not in result and 'diagnostics' not in result
    assert result['subperiod_path_metrics_independently_recomputed'] is result['paper_or_live_ready'] is False
    assert m.adapter._bounded_order_base is original_bounded and m.cap._project_aggregate is original_projector
    assert original_projector.__globals__['runtime'] is m.cap.runtime


def test_invalid_completed_triple_is_retained_as_not_accepted_not_a_missing_period_success(fixture):
    fixture['aggregate']['run_valid']=False;fixture['aggregate']['execution']['run_valid']=False
    fixture['aggregate']['execution']['execution_failure']=True;refresh(fixture)
    fixture['statistics'].pop(m.STATISTIC_NAMES[3])
    result=validate(fixture)
    assert result['accepted'] is result['run_valid'] is False and result['periods'] is None
    assert result['invalid_reason']=='aggregate_run_valid_false' and len(result['statistics_pins'])==3


@pytest.mark.parametrize('fault,code',[('old_package','aggregate'),('old_activation','aggregate'),
    ('census','aggregate'),('rebalance','aggregate'),('fills','aggregate'),('canceled','aggregate'),
    ('invalid','aggregate'),('cash','aggregate'),('tracking','aggregate'),('tilt','aggregate'),
    ('coverage','aggregate'),('arm','aggregate'),('fees','fees'),('account','account'),
    ('diag_arm','diagnostics'),('diag_year','diagnostics'),('diag_count','diagnostics'),
    ('period_end','periods'),('period_flags','periods'),('period_missing','periods')])
def test_rehashed_bad_evidence_still_refuses_at_semantic_gate(fixture,fault,code):
    a=fixture['aggregate'];d=fixture['diagnostic'];p=fixture['period'];meta=fixture['meta']
    if fault=='old_package':meta['package_sha256']='411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad'
    elif fault=='old_activation':meta['activation_manifest_sha256']='0'*64
    elif fault=='census':a['account']['observation_count']=1255
    elif fault=='rebalance':a['execution']['completed_rebalance_count']=301
    elif fault=='fills':a['execution']['filled_order_count_sum']=301
    elif fault=='canceled':a['execution']['canceled_order_count_sum']=1
    elif fault=='invalid':a['execution']['invalid_order_count_sum']=1
    elif fault=='cash':a['minimum_end_day_cash']='-1'
    elif fault=='tracking':a['execution']['mean_target_weight_l1_error']='0.03'
    elif fault=='tilt':a['maximum_stock_weight_change_fraction']='0.80'
    elif fault=='coverage':a['coverage_policy_id']='other'
    elif fault=='arm':a['comparison_arm']='ar_on200'
    elif fault=='fees':a['execution']['actual_engine_fee_amount']='11'
    elif fault=='account':a['account']['ending_equity']='1000001'
    elif fault=='diag_arm':d['arm']='ar_on200'
    elif fault=='diag_year':d['annual_account_rows'].pop()
    elif fault=='diag_count':d['source_snapshot_count']=261
    elif fault=='period_end':p['periods'][-1]['last_session']='2026-10-12'
    elif fault=='period_flags':p['formal']=True
    refresh(fixture)
    if fault=='period_missing':fixture['statistics'].pop(m.STATISTIC_NAMES[3])
    refused(code,lambda:validate(fixture))


@pytest.mark.parametrize('fault',['extra','bad_json','noncanonical','duplicate','oversize','nonstr'])
def test_selected_statistic_transport_is_closed_before_any_source_load(fixture,monkeypatch,fault):
    name=m.STATISTIC_NAMES[0]
    if fault=='extra':fixture['statistics']['ARV2_UNREQUESTED']='{}'
    elif fault=='bad_json':fixture['statistics'][name]='not json'
    elif fault=='noncanonical':fixture['statistics'][name]+='\n'
    elif fault=='duplicate':fixture['statistics'][name]='{"x":1,"x":1}'
    elif fault=='oversize':fixture['statistics'][name]='x'*8193
    else:fixture['statistics'][name]=True
    monkeypatch.setattr(m,'_candidate',lambda *a:(_ for _ in ()).throw(AssertionError('source phase reached')))
    refused('statistics',lambda:validate(fixture))


def test_wrong_supplied_axis_or_changed_actual_profile_is_not_trusted(fixture,monkeypatch):
    fixture['sessions']=fixture['sessions'][:-1]
    refused('axis',lambda:validate(fixture))


def test_diagnostic_arm_normalization_does_not_mutate_authenticated_report(fixture):
    before=fixture['statistics'][m.STATISTIC_NAMES[2]]
    assert validate(fixture)['accepted'] is True
    assert fixture['statistics'][m.STATISTIC_NAMES[2]]==before
