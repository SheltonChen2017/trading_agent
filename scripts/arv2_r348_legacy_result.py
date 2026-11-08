"""Pure, source-bound validation of the extended legacy six-universe result.

No manifest/control file, credential, client or operation is used. Supplied
flat sources must match all eighteen external public pins before execution.
Private function-global copies reuse frozen structural parsers without changing
their historical windows, registries or module globals. Acceptance is bounded
research-result consistency, not immutable snapshot or formal/live admission.
"""
from datetime import date
from decimal import Decimal, DecimalException, localcontext
import hashlib
import json
import re
from types import FunctionType, SimpleNamespace

from scripts import arv2_r345_legacy_six_qc_v3 as source_contract
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_cap90_submission as cap
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as projection

SCHEMA='arv2-r348-legacy-six-result-validation-v1'
STATISTIC_NAMES=('ARV2_SIX_GATE_ORDER_META','ARV2_SIX_GATE_ORDER_AGGREGATES',
    'ARV2_SIX_GATE_ORDER_DIAGNOSTICS','ARV2_R343_LEGACY_SIX_PERIODS')
ACTUAL_PACKAGE='1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2'
ACTIVATION_SHA256='ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b'
COVERAGE_POLICY='all_six_minimum_mapping_cap_total_10pct_verified_names_3_positive_scores_1_v1'
TILT='accepted_risk_six_universe_order_tilt_qc_runtime'
BASE='accepted_risk_six_universe_order_qc_runtime'
DIAGNOSTICS='accepted_risk_matched_diagnostics'
REPORTER='legacy_six_october_reporting'
FLAGS={'point_in_time_proven':False,'formal_identity_admitted':False,'formal_forward_ready':False,
    'paper_or_live_ready':False,'independent_historical_snapshot_authenticated':False}
FINITE=frozenset(('statistics','source','profile','axis','aggregate','account','fees','diagnostics','periods','bound','unknown'))
# Derived once from the committed public R346 result fact c7b22..., never from
# the currently supplied private proposal or an automatically refreshed file.
FROZEN_CELLS={
 'R343-AR080': {'profile_pin': {'byte_count': 4170, 'sha256': '954480b3735279998731596aae8ff934c14a69e85bc7e058d66071fee73a3b0d'}, 'source_vector_pin': {'byte_count': 2775, 'sha256': '83b3f41b7543729481513dae516f855d957646ec197c8b46a1799f215f6f151b'}},
 'R343-AR100': {'profile_pin': {'byte_count': 4178, 'sha256': 'c8ecb6ba6feae4dddb1eb9c7d36c9c3d74c99e95d603f699687f970eb5b115d0'}, 'source_vector_pin': {'byte_count': 2775, 'sha256': '71857bac63298b6b9dd4221ffc180ca4a59f10574edd109220a335d9370a232c'}},
 'R343-AR120': {'profile_pin': {'byte_count': 4178, 'sha256': '55e15026208bc80be6a9f422339b4aa7db4dc7a3dc697eedd701d847aae392bc'}, 'source_vector_pin': {'byte_count': 2775, 'sha256': '3fa3f5fcbf0418a45377dc7434e8c8a2b19157974aa7ab1d568b7dabba3c073e'}},
 'R343-AR140': {'profile_pin': {'byte_count': 4178, 'sha256': 'a7f46e5dfdbf7a3e6187e30dd0e5d8e9509dd88654b687910faa96b9138d5ad2'}, 'source_vector_pin': {'byte_count': 2775, 'sha256': '8ecfe2e43bd211c2b22da3369b415806a2a5a99637408b221724395593bbfe80'}},
 'R343-AR160': {'profile_pin': {'byte_count': 4178, 'sha256': 'b39ca18b267510b607f59814c4391c49aee698c7fa47ff1474c3c63c83034f26'}, 'source_vector_pin': {'byte_count': 2775, 'sha256': '59b5b16816c1744ca1ea28591c4d9d5b75bb1d4aeb6b58124c7c6ce1afa69db6'}},
 'R343-AR180': {'profile_pin': {'byte_count': 4178, 'sha256': '93a3bb50badf25d7d0caa24e3dcbf8fd6a9e7ca629422250a45b99a2f6506df9'}, 'source_vector_pin': {'byte_count': 2775, 'sha256': 'b1d0d91c513829619362423365b7feeb5449ec85cd31804d0bfddb28c4e626ae'}},
 'R343-AR200': {'profile_pin': {'byte_count': 4178, 'sha256': 'e65e38ee378cbfb54adc53f929e95152fab5db34134150c884c7d684090d1c96'}, 'source_vector_pin': {'byte_count': 2775, 'sha256': '153811048e9b82b70a801f541eb4a9962308f76caeebac249b49047b9632f7b9'}},
}


class Refused(ValueError):pass


def require(value,code):
    if not value:raise Refused(code)


def canonical(value):
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
    except (TypeError,ValueError,UnicodeError,RecursionError):raise Refused('statistics') from None


def pin(raw):return {'byte_count':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def _statistic(text,name):
    maximum=16384 if name==STATISTIC_NAMES[2] else 8192
    require(type(text) is str and text.isascii() and 0<len(text)<=maximum,'statistics')
    def pairs(items):
        value={}
        for key,item in items:require(key not in value,'statistics');value[key]=item
        return value
    try:
        value=json.loads(text,object_pairs_hook=pairs,
            parse_constant=lambda _:(_ for _ in ()).throw(Refused('statistics')))
    except Refused:raise
    except (ValueError,RecursionError):raise Refused('statistics') from None
    require(type(value) is dict and canonical(value)==text.encode('ascii'),'statistics')
    return value


def _candidate(record):
    try:value,sources=source_contract._cell(record)
    except source_contract.Refused:raise Refused('source') from None
    expected=FROZEN_CELLS.get(value['candidate_id'])
    require(expected is not None and value['profile_pin']==expected['profile_pin']
        and pin(canonical(value['sources']))==expected['source_vector_pin'],'source')
    return value,sources


def _axis(sessions):
    require(type(sessions) is tuple and len(sessions)==1451
        and all(type(day) is str for day in sessions) and tuple(sorted(set(sessions)))==sessions
        and sessions[0]=='2021-01-04' and sessions[-1]=='2026-10-13'
        and all(day in sessions for day in ('2025-12-31','2026-09-25','2026-09-28')),'axis')
    try:parsed=tuple(date.fromisoformat(day) for day in sessions)
    except ValueError:raise Refused('axis') from None
    require(tuple(day.isoformat() for day in parsed)==sessions and all(day.weekday()<5 for day in parsed),'axis')
    weeks=[];seen=set()
    for day in parsed:
        week=day.isocalendar()[:2]
        if week not in seen:weeks.append(day.isoformat());seen.add(week)
    require(len(weeks)==302 and weeks[-1]=='2026-10-12','axis')
    return sessions


def _clone(function,updates):
    namespace=dict(function.__globals__);namespace.update(updates)
    result=FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    result.__kwdefaults__=None if function.__kwdefaults__ is None else dict(function.__kwdefaults__)
    return result


def _parse_common(statistics,row,runtime):
    """Private pure closures; no original module/registry global is changed."""
    projector=_clone(cap._project_aggregate,{'runtime':runtime})
    selected_cap=SimpleNamespace(**vars(cap));selected_cap._project_aggregate=projector
    bounded=_clone(adapter._bounded_order_base,{'cap':selected_cap})
    family={'package_sha256':ACTUAL_PACKAGE,'activation_manifest_sha256':ACTIVATION_SHA256}
    parser=_clone(adapter._parse_order_common,{'_candidate':lambda _:row,'_plan_manifest':lambda _:family,
        '_bounded_order_base':bounded})
    return parser(None,statistics,expected_geometry=None,decision_count=302,
        extra_meta_fields=frozenset(('matched_diagnostics_sha256',)),
        extra_aggregate_fields=frozenset(('comparison_arm','analyst_revision_economic_usage','coverage_policy_id')),
        result_transport='three_bounded_custom_summary_statistics',expected_meta_schema=row['meta_schema'])


def _decimal(text,code):
    require(type(text) is str and 0<len(text)<=256,'bound')
    try:value=Decimal(text)
    except DecimalException:raise Refused(code) from None
    require(value.is_finite(),'account' if code=='account' else code);return value


def _financial(aggregate,valid):
    account=aggregate['account'];execution=aggregate['execution']
    starting,ending,cumulative,drawdown,volatility=(_decimal(account[key],'account') for key in
        ('starting_equity','ending_equity','cumulative_return','maximum_drawdown','annualized_volatility'))
    require(starting>0 and ending>0 and cumulative>-1 and -1<drawdown<=0 and volatility>=0,'account')
    if account['zero_rate_sharpe'] is not None:_decimal(account['zero_rate_sharpe'],'account')
    with localcontext() as context:
        context.prec=96
        require(abs(ending/starting-1-cumulative)<=Decimal('1e-90'),'account')
    fees,actual,notional=(_decimal(execution[key],'fees') for key in
        ('modeled_fee_amount','actual_engine_fee_amount','total_filled_notional'))
    require(fees>=0 and actual>=0 and notional>=0,'fees')
    if valid:
        require(execution.get('fee_mismatch') is False and fees==actual
            and type(execution.get('modeled_fee_bps_per_side')) is int
            and execution['modeled_fee_bps_per_side']==10,'fees')
        # The frozen producer compares every actual fill fee to its modeled
        # fee. Its own run_valid also requires no mismatch; totals must agree.
        require(execution['submitted_rebalance_count']==execution['completed_rebalance_count']==302
            and execution['submitted_order_count']==execution['filled_order_count_sum']
            and execution['invalid_order_count_sum']==execution['canceled_order_count_sum']==0,'aggregate')


def _validate(statistics,candidate_record,evaluation_sessions):
    require(type(statistics) is dict and set(statistics) in (set(STATISTIC_NAMES[:3]),set(STATISTIC_NAMES)),'statistics')
    supplied={name:statistics[name] for name in statistics}
    decoded={name:_statistic(text,name) for name,text in supplied.items()}
    candidate,sources=_candidate(candidate_record)  # External pins precede ANY supplied-code exec.
    sessions=_axis(evaluation_sessions);profile=candidate['profile'];percent=candidate['ar_percent']
    with projection._cloud_loader(sources) as (load,_):
        tilt,base=load(TILT),load(BASE)
        actual_profile=tilt.require_tilt_profile()
        require(canonical(actual_profile)==canonical(profile)
            and (base.EVALUATION_START_SESSION,base.EVALUATION_END_SESSION,
                base.EXPECTED_SESSION_COUNT,base.EXPECTED_DECISION_COUNT)==('2021-01-04','2026-10-13',1451,302),'profile')
        row={'candidate_id':candidate['candidate_id'],'role':profile['role'],'profile_id':profile['profile_id'],
            'profile_sha256':profile['profile_sha256'],'tilt_fraction':profile['maximum_stock_weight_change_fraction'],
            'matched_baseline_profile_sha256':profile['matched_baseline_profile_sha256'],
            'meta_schema':tilt.TILT_META_SCHEMA,'summary_schema':tilt.TILT_SUMMARY_SCHEMA,
            'statistic_names':list(STATISTIC_NAMES[:3])}
        parsed=_parse_common(supplied,row,base)
        aggregate=decoded[STATISTIC_NAMES[1]];valid=parsed['run_valid']
        require(type(valid) is bool and aggregate.get('comparison_arm')==f'ar_on{percent}'
            and aggregate.get('analyst_revision_economic_usage')=='entry_count_and_weight'
            and aggregate.get('coverage_policy_id')==COVERAGE_POLICY,'aggregate')
        _financial(aggregate,valid)
        diagnostic=decoded[STATISTIC_NAMES[2]]
        require(diagnostic.get('arm')==f'ar_on{percent}'
            and parsed['meta'].get('matched_diagnostics_sha256')==pin(canonical(diagnostic))['sha256']
            and diagnostic.get('overall_cumulative_return')==aggregate['account']['cumulative_return'],'diagnostics')
        cloud_diagnostics=load(DIAGNOSTICS)
        try:
            # Check the actual arm FIRST, then normalize only a private copy
            # for the frozen label validator, as the score-floor-one study did.
            cloud_diagnostics.validate_report({**diagnostic,'arm':'ar_on100'},'ar_on100',0,
                reference_repair_enabled=True)
        except Exception:raise Refused('diagnostics') from None
        period=None
        if valid:
            require(set(supplied)==set(STATISTIC_NAMES),'periods')
            period=decoded[STATISTIC_NAMES[3]];reporter=load(REPORTER)
            try:reporter.validate_report(period,evaluation_sessions=sessions,ar_percent=percent,
                source_profile_sha256=profile['profile_sha256'],account_path_schema=base.ACCOUNT_PATH_SCHEMA,
                legacy_aggregate=aggregate)
            except Exception:raise Refused('periods') from None
        else:require(set(supplied)==set(STATISTIC_NAMES[:3]),'periods')
    selected=parsed['aggregates']
    result={'schema':SCHEMA,'candidate_id':candidate['candidate_id'],'ar_percent':percent,
        'accepted':valid,'run_valid':valid,'invalid_reason':None if valid else 'aggregate_run_valid_false',
        'account':selected['account'],'execution':selected['execution'],
        'cash_and_tracking':{key:aggregate[key] for key in ('minimum_end_day_cash','daily_cash_nonnegative',
            'settled_cash_nonnegative','maximum_gross_exposure','end_day_gross_at_most_one','target_tracking_valid')},
        'direct_stock_target_counts_by_sleeve':{row[0]:row[7] for row in selected['sleeve_diagnostics']['rows']},
        'diagnostic_summary':{key:diagnostic[key] for key in ('arm','slippage_bps_per_side','overall_cumulative_return',
            'source_snapshot_count','diagnostic_history_call_count','six_etf_panel_row_count',
            'closing_minute_reference_repair_count','closing_minute_reference_repair_session_count')},
        'periods':None if period is None else period['periods'],
        'statistics_pins':{name:pin(text.encode('ascii')) for name,text in supplied.items()},
        'source_profile_pin':candidate['profile_pin'],'source_vector_pin':pin(canonical(candidate['sources'])),
        'evaluation_session_count':len(sessions),'evaluation_sessions_sha256':pin(canonical(sessions))['sha256'],
        'validation':'supplied_statistic_consistency_and_exact_public_source_pins_not_current_QC_or_private_file_authentication',
        'subperiod_path_metrics_independently_recomputed':False,'preliminary':True,'backtest_only':True,**FLAGS}
    require(len(canonical(result))<=16*1024,'bound')
    return json.loads(canonical(result))


def validate_statistics(statistics,*,candidate_record,evaluation_sessions):
    """Validate supplied bounded statistics; perform no artifact or QC read."""
    try:return _validate(statistics,candidate_record,evaluation_sessions)
    except Refused:raise
    except (adapter.RelaxedQcSubmissionError,cap.Cap90QcSubmissionError):raise Refused('aggregate') from None
    except Exception:raise Refused('unknown') from None
