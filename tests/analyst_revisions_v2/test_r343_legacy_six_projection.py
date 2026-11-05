"""Native-denied public source reconstruction and synthetic October integration."""
import hashlib
import json
from pathlib import Path
import time
import ast
from types import SimpleNamespace
from decimal import Decimal,localcontext

import pytest

from scripts import arv2_r343_legacy_six_projection as m

ROOT = Path(__file__).resolve().parents[2]
QCOM_FIXTURE = 'SYNTHETIC-LOGICAL-QCOM-ID-NOT-A-PRIVATE-BINDING'


@pytest.fixture(scope='module')
def pairs():
    return tuple((name, (ROOT/'research/analyst_revisions_v2_qc'/name).read_bytes())
        for name in m.source_names())


@pytest.fixture(scope='module')
def historical_manifest():
    path = ROOT/'research/analyst_revisions_v2_qc/six_universe_qcom_score_floor1_candidates.json'
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '3fde7673114794db256336c7c738c185859dd46e3d9af0765aa1cd7d008e5b86'
    return json.loads(raw)


@pytest.fixture(scope='module')
def historical(pairs, historical_manifest):
    # Only the intermediate exclusion uses this symbol. Every final admitted
    # source has removed it; the real committed final file/profile pins prove
    # that fact without reading a licensed original security identifier.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(m.matched, 'QCOM_EXCLUSION_SECURITY_ID_SHA256', m.sha(QCOM_FIXTURE.encode()))
        return m.reconstruct_historical(pairs, qcom_security_id=QCOM_FIXTURE,
            manifest=historical_manifest, deadline=time.monotonic()+599)


def test_all_seven_historical_cloud_manifests_reconstruct_without_old_package(historical):
    cells = historical
    assert tuple(row[0] for row in cells) == m.AR_PERCENTS
    for _, sources, profile in cells:
        assert len(sources) == 17
        assert all(QCOM_FIXTURE.encode() not in raw for _, raw in sources)
        assert profile['coverage_policy_id'] == m.score_one.COVERAGE_POLICY_ID


@pytest.mark.parametrize('index', range(7))
def test_real_extended_flat_profiles_rebind_dates_and_preserve_economics(historical,index):
    percent, sources, original = historical[index]
    reporting = (ROOT/'research/analyst_revisions_v2_qc/legacy_six_october_reporting.py').read_bytes()
    activation = {'object_store_key':'arv2/preliminary-rating/27645603c1a6e0fc9fa81655/transport-manifest.json',
        'content_sha256':'70f64450a44bedfa8ea371ac74a00e2134045fb79b433b93f0114be652bc6147','byte_count':4631}
    buffers, profile = m._extend_cell(percent,sources,original,activation=activation,reporting_source=reporting)
    assert profile['research_epoch_id'] == m.EPOCH
    assert profile['candidate_id'] == f'R343-AR{percent:03d}'
    assert profile['evaluation_end_session'] == '2026-10-13'
    assert profile['decision_count'] == 302
    for key in ('target_gross_exposure','modeled_fee_bps_per_side','slippage_bps','admission_leverage',
            'maximum_stock_weight_change_fraction','coverage_policy_id','execution','whole_shares','sell_before_buy'):
        assert profile[key] == original[key]
    changed={key for key in original if profile[key] != original[key]}
    assert changed <= {'schema','profile_id','role','profile_sha256','evaluation_end_session',
        'decision_count','evaluation_session_count','evaluation_profile_id','evaluation_profile_sha256',
        'matched_baseline_profile_sha256','cap90_predecessor_profile_sha256','terminal_clock_rule',
        'target_path_schema','decision_target_schema','gate_profile_id','gate_profile_sha256'}, changed
    assert len(buffers) == 18


@pytest.fixture(scope='module')
def prepared(historical, pairs):
    activation = SimpleNamespace(object_store_key='arv2/preliminary-rating/27645603c1a6e0fc9fa81655/transport-manifest.json',
        content_sha256='70f64450a44bedfa8ea371ac74a00e2134045fb79b433b93f0114be652bc6147',byte_count=4631)
    wrapped = SimpleNamespace(package=SimpleNamespace(package_sha256=m.OCTOBER_PACKAGE,
        upload_objects=(activation,)),lineage_sha256=m.OCTOBER_LINEAGE)
    reporting = (ROOT/'research/analyst_revisions_v2_qc/legacy_six_october_reporting.py').read_bytes()
    axis = m.october._sessions()  # Pure fixed public calendar, no source payload.
    with pytest.MonkeyPatch.context() as patch:
        # Explicit authentic-loader seam only. Production rejects this fixture
        # without that seam; root's one-shot genuine loader proves real inputs.
        patch.setattr(m.october, 'require_october_order_input_package', lambda value: value if value is wrapped else None)
        patch.setattr(m, '_bindings', lambda values: QCOM_FIXTURE)
        patch.setattr(m, 'reconstruct_historical', lambda *a, **k: historical)
        result = m.prepare(wrapped,axis=axis,bindings=(),source_pairs=pairs,
            reporting_source=reporting,deadline=time.monotonic()+599)
    return result


def test_full_prepare_and_actual_summary_ABI(prepared):
    assert m.validate_summary(prepared['summary']) is prepared['summary']
    assert prepared['summary']['evaluation_count'] == 1451
    assert prepared['summary']['decision_count'] == 302
    assert [row['candidate_id'] for row in prepared['bundle']['cells']] == [f'R343-AR{n:03d}' for n in m.AR_PERCENTS]
    assert len(m.canonical(prepared['bundle'])) < 8*1024*1024
    assert QCOM_FIXTURE.encode() not in m.canonical(prepared)
    assert m.validate_bundle(prepared['bundle']) is prepared['bundle']


@pytest.mark.parametrize('fault',['profile','code','activation','profile_bool','extra'])
def test_private_prepared_buffers_rejoin_every_public_pin(prepared,fault):
    value=json.loads(m.canonical(prepared['bundle']))
    if fault=='profile':value['cells'][0]['profile']['slippage_bps']='5'
    elif fault=='code':value['cells'][0]['source_pairs'][0][1]+='\n'
    elif fault=='activation':value['activation']['byte_count']+=1
    elif fault=='profile_bool':value['cells'][0]['profile']=True
    else:value['cells'][0]['extra']=False
    with pytest.raises(m.Refused,match='^output$'):m.validate_bundle(value)


@pytest.mark.parametrize('mutation',['raw','manifest','qcom'])
def test_historical_inputs_are_not_accepted_by_name_or_count(pairs,historical_manifest,mutation):
    selected=list(pairs);manifest=json.loads(m.canonical(historical_manifest));identity=QCOM_FIXTURE
    if mutation=='raw':selected[0]=(selected[0][0],selected[0][1]+b'\n')
    elif mutation=='manifest':manifest['protocol']['formal_alpha']=True
    else:identity='NOT-THE-EXACT-LOGICAL-IDENTITY'
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(m.matched,'QCOM_EXCLUSION_SECURITY_ID_SHA256',m.sha(QCOM_FIXTURE.encode()))
        with pytest.raises(m.Refused,match='^(source_pin|historical|bindings)$'):
            m.reconstruct_historical(tuple(selected),qcom_security_id=identity,
                manifest=manifest,deadline=time.monotonic()+599)


@pytest.mark.parametrize('fault', ['extra','count_bool','eval_bool','decision_count','activation_bool','wrong_package',
    'flag','arm_bool','source_size_bool','source_sha','source_duplicate','profile_bool','old_profile','candidate','source_oversize','total_oversize'])
def test_closed_summary_rejects_forged_geometry_pins_and_flags(prepared,fault):
    value = json.loads(m.canonical(prepared['summary']))
    if fault == 'extra': value['approval'] = True
    elif fault == 'count_bool': value['cell_count'] = True
    elif fault == 'eval_bool': value['evaluation_count'] = True
    elif fault == 'decision_count': value['decision_count'] -= 1
    elif fault == 'activation_bool': value['activation']['byte_count'] = True
    elif fault == 'wrong_package': value['package_sha256'] = 'f'*64
    elif fault == 'flag': value['formal_identity_admitted'] = True
    elif fault == 'arm_bool': value['cells'][0]['ar_percent'] = True
    elif fault == 'source_size_bool': value['cells'][0]['sources'][0]['byte_count'] = True
    elif fault == 'source_sha': value['cells'][0]['sources'][0]['sha256'] = 'G'*64
    elif fault == 'source_duplicate': value['cells'][0]['sources'][0] = value['cells'][0]['sources'][1]
    elif fault == 'profile_bool': value['cells'][0]['profile_pin']['byte_count'] = True
    elif fault == 'old_profile': value['cells'][0]['original_profile_sha256'] = '0'*64
    elif fault == 'candidate': value['cells'][0]['candidate_id'] = 'R260'
    elif fault == 'source_oversize': value['cells'][0]['sources'][0]['byte_count'] = 64001
    else:
        for source in value['cells'][0]['sources']:
            if source['project_path'] != 'legacy_six_october_reporting.py': source['byte_count'] = 64000
    with pytest.raises(m.Refused,match='^output$'): m.validate_summary(value)


@pytest.mark.parametrize('value', [None, object(), SimpleNamespace(package=object())])
def test_fake_wrapper_never_passes_real_genuine_authority(value):
    with pytest.raises(m.Refused,match='^input$'):
        m.prepare(value,axis=(),bindings=(),source_pairs=(),reporting_source=b'',deadline=time.monotonic()+599)


@pytest.mark.parametrize('bad', [(), ('2021-01-04',), ('2021-01-04','2026-10-13')])
def test_full_axis_is_not_a_claimed_endpoint_pair(bad):
    with pytest.raises(m.Refused,match='^period$'): m._geometry(bad)


def test_geometry_actual_original_calendar_has_exact_extension():
    axis = m.october._sessions()
    sessions, decisions = m._geometry(axis)
    assert sessions[1254] == '2025-12-31' and sessions[-1] == '2026-10-13'
    assert len(decisions) == 302 and decisions[-1] == '2026-10-12'
    with pytest.raises(m.Refused,match='^period$'): m._geometry(tuple(reversed(axis)))


@pytest.mark.parametrize('bindings', [(), ({},)*6151])
def test_full_binding_stream_cannot_be_claimed_from_count(bindings):
    with pytest.raises(m.Refused,match='^bindings$'): m._bindings(bindings)


@pytest.mark.parametrize('index', range(7))
def test_unchanged_financial_modules_and_reached_emitted_report_hook(prepared,historical,index):
    cell = prepared['bundle']['cells'][index]
    sources = {name: raw for name,raw in cell['source_pairs']}
    old = dict(historical[index][1])
    for name in ('accepted_risk_order_level_core.py','accepted_risk_order_level_forced_exit.py',
            'accepted_risk_simulated_moo_executor.py','accepted_risk_preliminary_qc_figi.py',
            'accepted_risk_preliminary_rating_evaluator.py','accepted_risk_sequential_r055_score.py'):
        assert ast.dump(ast.parse(sources[name]),include_attributes=False) == ast.dump(ast.parse(old[name]),include_attributes=False)
    tree = ast.parse(sources['main.py'])
    function = next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='on_end_of_algorithm')
    events=[]; aggregate={'run_valid':True}; nav={'synthetic':'123'}
    driver=SimpleNamespace(on_end_of_algorithm=lambda: (events.append('legacy_validity'),aggregate)[1],
        _account_observations=nav,_evaluation_sessions=('synthetic-session',),_profile={'profile_sha256':'f'*64})
    def report(observations,**kwargs):
        assert events == ['legacy_validity'] and observations is nav
        assert kwargs['legacy_aggregate'] is aggregate
        assert kwargs['account_path_schema'] == 'arv2-six-universe-order-account-path-v1'
        assert kwargs['ar_percent'] == m.AR_PERCENTS[index]
        assert kwargs['source_profile_sha256'] == 'f'*64
        events.append('report');return {'bounded':True}
    namespace={'build_report':report,'canonical_report_bytes':lambda value:b'{}','STATISTIC_NAME':'PERIODS',
        'ACCOUNT_PATH_SCHEMA':'arv2-six-universe-order-account-path-v1'}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'actual-emitted-end-hook','exec'),namespace)
    algorithm=SimpleNamespace(_arv2_driver=driver,set_summary_statistic=lambda *args:events.append(('emit',args)))
    namespace['on_end_of_algorithm'](algorithm)
    assert events == ['legacy_validity','report',('emit',('PERIODS','{}'))]


@pytest.mark.parametrize('index', range(7))
def test_invalid_run_stays_completed_with_only_its_legacy_statistics(prepared,index):
    # build_report refuses run_valid=false. Unguarded, that refusal would turn a
    # Completed invalid run into a Runtime Error the result reader may not open.
    sources = {name: raw for name,raw in prepared['bundle']['cells'][index]['source_pairs']}
    tree = ast.parse(sources['main.py'])
    function = next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='on_end_of_algorithm')
    events=[]
    driver=SimpleNamespace(on_end_of_algorithm=lambda: (events.append('legacy_validity'),{'run_valid':False})[1],
        _account_observations={},_evaluation_sessions=(),_profile={'profile_sha256':'f'*64})
    def refuse(*_args,**_kwargs):
        raise AssertionError('an invalid run must not reach the period report')
    namespace={'build_report':refuse,'canonical_report_bytes':refuse,'STATISTIC_NAME':'PERIODS','ACCOUNT_PATH_SCHEMA':'unused'}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'actual-emitted-end-hook','exec'),namespace)
    algorithm=SimpleNamespace(_arv2_driver=driver,set_summary_statistic=lambda *args:events.append(('emit',args)))
    namespace['on_end_of_algorithm'](algorithm)
    assert events == ['legacy_validity']


def test_caller_inventory_pins_the_current_projection_and_reporting_bytes():
    # The caller cannot import off Darwin, so read its pin as text. A projection
    # edit without a repin would otherwise surface only at the one-use prepare.
    raw = (ROOT/'scripts/arv2_r343_legacy_six_source_pins.json').read_bytes()
    caller = (ROOT/'scripts/prepare_arv2_r343_legacy_six.py').read_text(encoding='ascii')
    assert f"INVENTORY_SHA256 = '{hashlib.sha256(raw).hexdigest()}'" in caller
    files = json.loads(raw)['files']
    for relative in ('scripts/arv2_r343_legacy_six_projection.py',
            'research/analyst_revisions_v2_qc/legacy_six_october_reporting.py'):
        data = (ROOT/relative).read_bytes()
        assert files[relative] == {'byte_count':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def test_actual_six_year_diagnostic_validator_and_Decimal96_transport(prepared):
    sources={name:raw for name,raw in prepared['bundle']['cells'][0]['source_pairs']}
    axis=m.october._sessions();sessions,decisions=m._geometry(axis)
    with m.relaxed._cloud_loader(sources) as (load,_):
        diag=load('accepted_risk_matched_diagnostics');base=load(m.ORDER[:-3])
        with localcontext() as arithmetic:
            arithmetic.prec=96
            nav={day:Decimal('1000000')+Decimal(i)/10 for i,day in enumerate(sessions)}
            annual=diag.annual_accounts(nav)
            metrics=base._population_metrics(tuple(sorted(nav.items())))
            years=sorted({day[:4] for day in decisions})
            rows=[]
            for year in years:
                count=sum(day.startswith(year) for day in decisions)
                fallback=Decimal(count)*Decimal('.98')/6
                for universe in base._gate.UNIVERSE_IDS:
                    rows.append([year,universe,count,count,count*10,count*10,base._decimal_text(fallback)])
            report={'schema':diag.REFERENCE_REPAIR_SCHEMA,'arm':'ar_on80','slippage_bps_per_side':0,
                'overall_cumulative_return':metrics['cumulative_return'],
                'annual_account_fields':diag.ANNUAL_FIELDS,
                'annual_account_rows':[[row[field] for field in diag.ANNUAL_FIELDS] for row in annual],
                'membership_cap_path_sha256':'a'*64,'source_snapshot_count':302,'diagnostic_history_call_count':1,
                'etf_daily_panel_sha256':'b'*64,'six_etf_panel_row_count':8706,
                'year_universe_fields':diag.UNIVERSE_FIELDS,'year_universe_rows':rows,
                'universe_realized_profit_attributed':False,'all_stock_price_equality_proved':False,
                'minute_execution_price_equality_proved':False,'daily_price_normalization':'RAW','fill_forward':False,
                'closing_minute_reference_repair_count':0,'closing_minute_reference_repair_session_count':0,
                'closing_minute_reference_repair_path_sha256':base._sha([])}
        assert diag.validate_report(report,arm='ar_on80',slippage_bps=0,reference_repair_enabled=True) is True
        assert len(base._canonical(report)) <= 8192
