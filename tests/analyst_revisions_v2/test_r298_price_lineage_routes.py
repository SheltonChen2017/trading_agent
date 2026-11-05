"""Synthetic qualified price locators; no provider, original source or QC use."""
import copy
import json
import pickle
import time

import pytest

from scripts import arv2_r298_price_lineage_routes as m
from tests.analyst_revisions_v2 import test_r298_sharadar_all_routes_v2 as fixture
from tests.analyst_revisions_v2 import test_r298_sharadar_eligibility_observation as metadata

PURE_JOIN = m.routes.join


@pytest.fixture(autouse=True)
def synthetic_counts_no_operations(monkeypatch):
    # Small supplied records exercise this policy. The real frozen AB metadata
    # validator retains its production6,151 contract and is tested separately.
    monkeypatch.setattr(m, 'EXPECTED_STOCKS', 2)
    monkeypatch.setattr(m.evidence, 'EXPECTED_STOCKS', 2)
    def deny(*args, **kwargs): raise AssertionError('old operation or route join invoked')
    monkeypatch.setattr(m.routes, 'join', deny)
    monkeypatch.setattr(m.routes.original, 'verify', deny)
    monkeypatch.setattr(m.routes.original.identity_join, 'join', deny)
    monkeypatch.setattr(m.demand, 'prepare', deny)
    for module in (m.routes.current.previous, m.routes.current.previous.previous):
        monkeypatch.setattr(module, 'observe', deny)
        monkeypatch.setattr(module, '_fetch', deny)


@pytest.fixture
def build(monkeypatch):
    def closed_synthetic_summary(value):
        expected = {'source_frame_pin', 'evidence_summary_sha256', 'private_frame_byte_count',
            'private_frame_sha256', 'cohorts'}
        m.require(type(value) is dict and set(value) == expected, 'demand_summary')
        return copy.deepcopy(value)
    monkeypatch.setattr(m, '_validate_demand_summary', closed_synthetic_summary)
    def make(data=None, *, potential=(True, True)):
        data = fixture.case() if data is None else data
        aa_summary, private = PURE_JOIN(*data, binding_contract=fixture.supplied.contract(data[0]))
        aa_raw = m.canonical(private.private_record())
        evidence_summary, _ = m.evidence.inspect(aa_raw, expected_summary=aa_summary)
        original = private.private_record()
        stocks = []
        for index, (item, active) in enumerate(zip(original['stocks'], potential, strict=True)):
            stocks.append({'binding_ordinal': index, 'security_id': item['binding']['security_id'],
                'binding_row_sha256': item['binding']['row_sha256'], 'route_disposition': item['disposition'],
                'route_reason': item['reason'], 'membership_interval_count': int(active),
                'membership_rows_sha256': 'a' * 64, 'potential_for_both_cohorts_all_AR_arms': active,
                'eligible_decision_count': 2 if active else 0, 'eligible_decisions_sha256': 'b' * 64,
                'first_eligible_decision': '2021-01-04' if active else None,
                'last_eligible_decision': '2026-10-12' if active else None,
                'required_price_start': '2020-12-31' if active else None,
                'required_price_end': '2026-10-13' if active else None,
                'binding_last_session_not_used_as_price_end': True,
                'zero_initial_runtime_condition_required_for_never_potential': not active})
        funds = [{'fund_ordinal': index, 'ticker': item['ticker'], 'route_disposition': item['disposition'],
            'route_reason': item['reason'], 'six_universe': item['ticker'] in m.demand.runtime.targets.cohort(6),
            'eight_universe': True, 'required_price_start': '2020-12-31', 'required_price_end': '2026-10-13'}
            for index, item in enumerate(original['funds'])]
        planned = {'schema': m.demand.PRIVATE_SCHEMA, 'source_frame_pin': evidence_summary['frame_pin'],
            'evidence_summary_sha256': m.sha(m.canonical(evidence_summary)),
            'binding_contract': original['binding_contract'], 'stocks': stocks, 'funds': funds}
        demand_raw = m.canonical(planned)
        demand_summary = {key: planned[key] for key in ('source_frame_pin', 'evidence_summary_sha256')}
        demand_summary.update(private_frame_byte_count=len(demand_raw), private_frame_sha256=m.sha(demand_raw),
            cohorts={str(count): {'potential_stock_count': sum(potential),
                'never_potential_stock_count': len(potential) - sum(potential)} for count in (6, 8)})
        stocks_raw = metadata.csv_bytes(m.routes.current.FIELDS, data[2])
        funds_raw = metadata.csv_bytes(m.routes.current.FIELDS, data[3])
        pins = {table: {'byte_count': len(raw), 'sha256': m.sha(raw)}
            for table, raw in (('stocks', stocks_raw), ('funds', funds_raw))}
        return [aa_raw, demand_raw, stocks_raw, funds_raw], {
            'aa_routing_summary': aa_summary, 'demand_summary': demand_summary, 'capture_pins': pins}
    return make


def refused(code, callback):
    with pytest.raises(m.Refused) as error: callback()
    assert m.finite(error.value) == code


def prepare(build, data=None, **kwargs):
    inputs, options = build(data, **kwargs)
    return m.prepare(*inputs, **options)


def test_full_original_bindings_retained_and_all_potential_queries_use_identical_full_window(build):
    summary, private = prepare(build)
    record = private.private_record()
    assert [item['binding'] for item in record['stocks']] == fixture.case()[0]
    assert summary['disposition_counts'] == {'stocks': {'routed': 2}, 'funds': {'routed': 8}}
    assert summary['potential_stock_count'] == 2 and summary['conditional_never_potential_stock_count'] == 0
    assert len(private.query_routes()) == 10
    assert all(item['query_window'] == ['2020-12-31', '2026-10-13'] for item in private.query_routes())
    assert m.validate_private_record(record, expected_summary=summary) == record
    assert all(summary[key] is False for key in m.FALSE_FLAGS)
    for text in ('SYN1', 'BBG000000001', '000000001', 'NASDAQ', 'Synthetic', 'SPY'):
        assert text.encode() not in m.canonical(summary)


def test_functional_reporting_currency_is_not_EOD_currency_and_original_hashes_are_unchanged(build):
    data = fixture.case(); data[1][0]['currency'] = 'EUR'
    data[0][0] = fixture.supplied.binding(data[1][0], 2)
    summary, private = prepare(build, data)
    item = private.private_record()['stocks'][0]
    assert item['binding'] == data[0][0] and item['aa_reason'] == 'original_identity'
    assert item['disposition'] == 'routed' and item['route']['current_metadata_row']['currency'] == 'USD'
    assert item['observed_flags']['original_reporting_currency_not_usd'] is True
    assert summary['old_predicate_only_route_correction_count'] == 1
    assert summary['observation_flag_counts']['stocks']['original_reporting_currency_not_usd'] == 1


@pytest.mark.parametrize('field,value,flag', [('ticker', 'RENAMED1', 'current_ticker_differs'),
    ('exchange', 'NYSE', 'current_mic_differs'), ('exchange', 'OTC', 'current_exchange_outside_old_listing_vocabulary'),
    ('category', 'Preferred Stock', 'current_category_outside_old_common_vocabulary'),
    ('category', 'ETF', 'current_category_differs')])
def test_current_display_venue_category_do_not_replace_original_historical_class_or_QC_identity(build, field, value, flag):
    data = fixture.case(); data[2][0][field] = value
    summary, private = prepare(build, data)
    item = private.private_record()['stocks'][0]
    assert item['disposition'] == 'routed' and item['observed_flags'][flag] is True
    assert item['binding'] == data[0][0] and item['binding']['diagnostic_exchange_mic'] == 'XNAS'
    assert item['binding']['diagnostic_current_ticker'] == 'SYN1' and item['binding']['qc_security_id'] is None
    assert item['route']['security_id'] == item['binding']['security_id']
    assert item['query_window'] == ['2020-12-31', '2026-10-13']
    assert summary['old_predicate_only_route_correction_count'] == 1


@pytest.mark.parametrize('field,value,flag', [('lastpricedate', '2022-10-21', 'metadata_last_before_window_end'),
    ('firstpricedate', '2024-01-02', 'metadata_first_after_window_start'),
    ('lastupdated', 'bad', 'metadata_updated_unparseable'), ('lastpricedate', '', 'metadata_last_unparseable')])
def test_current_metadata_dates_are_observations_never_query_or_holdings_endpoints(build, field, value, flag):
    data = fixture.case(); data[2][0][field] = value
    summary, private = prepare(build, data)
    item = private.private_record()['stocks'][0]
    assert item['disposition'] == 'routed' and item['observed_flags'][flag] is True
    assert item['query_window'] == ['2020-12-31', '2026-10-13']
    assert summary['price_coverage_proven'] is summary['price_input_admitted'] is False


@pytest.mark.parametrize('kind', ['first', 'last', 'evidence', 'old_class', 'old_MIC'])
def test_original_constructor_class_evidence_and_rawdate_consistency_are_not_waived(build, kind):
    data = fixture.case()
    if kind == 'first': data[1][0]['firstpricedate'] = '2020-01-02'; data[0][0] = fixture.supplied.binding(data[1][0], 2)
    elif kind == 'last': data[1][0]['lastpricedate'] = '2025-12-31'; data[0][0] = fixture.supplied.binding(data[1][0], 2)
    elif kind == 'old_class':
        data[1][0]['category'] = 'Preferred Stock'; data[0][0] = fixture.supplied.binding(data[1][0], 2)
    else:
        data[0][0]['identity_evidence_sha256' if kind == 'evidence' else 'diagnostic_exchange_mic'] = 'c' * 64 if kind == 'evidence' else 'XNYS'
        seed = dict(data[0][0]); seed.pop('row_sha256')
        data[0][0]['row_sha256'] = m.sha(m.routes.original.identity_join.figi._canonical(seed))
    summary, private = prepare(build, data)
    assert summary['refusal_counts']['stocks'] == {'original_identity': 1}
    refused('routes_incomplete', private.query_routes)


@pytest.mark.parametrize('field,value,reason', [('figi', 'BBG999999999', 'identity_missing'),
    ('permaticker', '9999', 'identity_missing'), ('currency', 'EUR', 'price_currency'),
    ('ticker', 'bad/ticker', 'price_ticker'), ('cusips', '000000001;OTHER', 'vocabulary'),
    ('cusips', 'ABCDEF123', 'original_vocabulary_not_retained')])
def test_identity_FIGI_price_currency_and_complete_vocabulary_stay_closed_refusals(build, field, value, reason):
    data = fixture.case(); data[2][0][field] = value
    summary, private = prepare(build, data)
    assert summary['refusal_counts']['stocks'] == {reason: 1}
    refused('routes_incomplete', private.query_routes)


@pytest.mark.parametrize('kind', ['figi', 'perma', 'ticker', 'later_token', 'cross_token', 'poison'])
def test_full_catalog_global_collisions_include_unreturned_candidate_rows_and_later_tokens(build, kind):
    data = fixture.case(); extra = metadata.metadata('OTHER', 99, fund=kind == 'cross_token')
    if kind in ('figi', 'perma', 'ticker'):
        field = {'figi': 'figi', 'perma': 'permaticker', 'ticker': 'ticker'}[kind]
        extra[field] = data[2][0][field]
    else:
        data[2][0]['cusips'] += ' ABCDEF123'
        extra['cusips'] = 'ABCDEF123;INVALID' if kind == 'poison' else extra['cusips'] + ' ABCDEF123'
    (data[3] if kind == 'cross_token' else data[2]).append(extra)
    summary, private = prepare(build, data)
    assert summary['refusal_counts']['stocks'] == {'global_collision': 1}
    refused('routes_incomplete', private.query_routes)


def test_all_original_CUSIP_tokens_required_not_one_matching_seed(build):
    data = fixture.case(); data[1][0]['cusips'] = '000000001,ABCDEF123'
    data[0][0] = fixture.supplied.binding(data[1][0], 2)
    summary, private = prepare(build, data)
    assert summary['refusal_counts']['stocks'] == {'original_vocabulary_not_retained': 1}


def test_conditional_never_potential_identity_is_retained_without_price_based_row_drop(build):
    data = fixture.case(); data[2][1]['figi'] = 'BBG999999999'
    summary, private = prepare(build, data, potential=(True, False))
    rows = private.private_record()['stocks']
    assert len(rows) == 2 and rows[1]['binding'] == data[0][1]
    assert rows[1]['disposition'] == 'conditional_never_potential' and rows[1]['reason'] == 'identity_missing'
    assert rows[1]['query_window'] is None and rows[1]['route'] is None
    assert len(private.query_routes()) == 9
    assert summary['potential_stock_count'] == summary['conditional_never_potential_stock_count'] == 1


@pytest.mark.parametrize('kind', ['AA_pin', 'AB_pin', 'AB_source', 'AB_identity', 'AB_flag', 'AB_count', 'metadata_pin', 'metadata_rows'])
def test_all_four_supplied_sources_and_full_AB_original_binding_join_are_mandatory(build, kind):
    inputs, options = build()
    if kind == 'AA_pin': inputs[0] += b' '
    elif kind == 'AB_pin': inputs[1] += b' '
    elif kind.startswith('AB_'):
        planned = json.loads(inputs[1])
        if kind == 'AB_source': planned['source_frame_pin']['sha256'] = 'f' * 64
        elif kind == 'AB_identity': planned['stocks'][0]['binding_row_sha256'] = 'f' * 64
        elif kind == 'AB_flag': planned['stocks'][0]['potential_for_both_cohorts_all_AR_arms'] = 1
        else: options['demand_summary']['cohorts']['8']['potential_stock_count'] = 1
        inputs[1] = m.canonical(planned)
        options['demand_summary'].update(private_frame_byte_count=len(inputs[1]), private_frame_sha256=m.sha(inputs[1]))
    elif kind == 'metadata_pin': options['capture_pins']['stocks']['sha256'] = 'f' * 64
    else:
        inputs[2] = inputs[2].replace(b'SYN1', b'OTHER')
        options['capture_pins']['stocks'] = {'byte_count': len(inputs[2]), 'sha256': m.sha(inputs[2])}
    with pytest.raises(m.Refused): m.prepare(*inputs, **options)


def test_private_output_is_opaque_immutable_and_strictly_bound_to_qualified_summary(build):
    summary, private = prepare(build)
    assert m.validate_summary(summary) == summary
    assert m.validate_private_record(private.private_record(), expected_summary=summary) == private.private_record()
    changed = private.private_record(); changed['stocks'][0]['route']['current_metadata_row']['currency'] = 'EUR'
    refused('private_record', lambda: m.validate_private_record(changed, expected_summary=summary))
    assert 'SYN1' not in repr(private)
    with pytest.raises(TypeError): json.dumps(private)
    with pytest.raises(TypeError): pickle.dumps(private)
    with pytest.raises(TypeError): private._raw = b'changed'


@pytest.mark.parametrize('kind', ['ready', 'false_flag', 'unknown_observation', 'count_bool', 'ghost_refusal', 'correction_count'])
def test_closed_summary_cannot_upgrade_price_admission_or_invent_diagnostics(build, kind):
    summary, _ = prepare(build)
    if kind == 'ready': summary['ready'] = True
    elif kind == 'false_flag': summary['price_coverage_proven'] = True
    elif kind == 'unknown_observation': summary['observation_flag_counts']['stocks']['RAW_TICKER'] = 1
    elif kind == 'count_bool': summary['potential_stock_count'] = True
    elif kind == 'ghost_refusal': summary['refusal_counts']['stocks']['identity_missing'] = 1
    else: summary['old_predicate_only_route_correction_count'] = 3
    refused('summary', lambda: m.validate_summary(summary))


def test_deadline_and_incremental_output_graph_bound(build, monkeypatch):
    inputs, options = build()
    refused('deadline', lambda: m.prepare(*inputs, **options, deadline=time.monotonic() - 1))
    monkeypatch.setattr(m, 'MAX_PRIVATE_BYTES', 4096)
    refused('private_bound', lambda: m.prepare(*inputs, **options))


def test_real_frozen_AB_validator_is_not_replaced_in_production_and_policy_has_exact_field_roles():
    refused('demand_summary', lambda: m._validate_demand_summary({}))
    profile = m.profile_record()
    assert 'functional_reporting_vs_stocks_funds_EOD_price_currency_no_FX' in profile['currency_field_roles']
    assert 'except_SF1_USD' in profile['original_identity_policy']
    assert 'not_clipped' in profile['potential_queries']
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
