"""Synthetic concrete-driver integration and new aggregate counter checks only."""
import ast
import copy
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import MethodType, SimpleNamespace as NS

import pytest

from research.analyst_revisions_v2_qc import newrule_common_price_comparison_runtime as m
from scripts import arv2_newrule_quote_execution_projection as quote
from tests.analyst_revisions_v2 import test_newrule_runtime_projection as old

D = Decimal


def refused(code, operation):
    with pytest.raises(m.Refused) as caught: operation()
    assert m.finite(caught.value) == code


def strategy(count=6, arm=0):
    value = old.profile(count, arm)
    value.update(package_sha256=m.monetary.native.PACKAGE_SHA256, lineage_sha256=m.LINEAGE_SHA256)
    value['candidate_id'] += '-quote-aware-v1'
    value.update(quote.policy_profile_fields())
    value['profile_sha256'] = m.digest({key: child for key, child in value.items() if key != 'profile_sha256'})
    return value


def profile(count=6, arm=0):
    return m.make_profile(strategy(count, arm), runtime_project_id=123,
        native_source_context_sha256=m.native_reader.SOURCE_CONTEXT_SHA256,
        vendor_source_context_sha256='b' * 64, source_pins={'source.py': 'a' * 64})


def common_result(expected):
    decisions, closes = len(expected['strategy_profile']['decision_sessions']), len(expected['strategy_profile']['evaluation_sessions'])
    return {'schema': m.RESULT_SCHEMA + '-source', 'common_profile_sha256': expected['profile_sha256'],
        **{key: expected[key] for key in ('strategy_profile_sha256', 'native_source_context_sha256',
            'vendor_source_context_sha256', 'monetary_policy_sha256')},
        'fresh_resolution_sha256': 'a' * 64, 'fund_translation_sha256': 'b' * 64,
        'ledger': {'schema': m.monetary.SCHEMA + '-ledger',
            'source_observation': {'schema': m.monetary.SCHEMA + '-source-observation',
                'specification_sha256': m.monetary.NATIVE_SPECIFICATION_SHA256,
                'binding_stream_sha256': m.monetary.native.BINDING_STREAM_SHA256,
                'native_receipt': {'byte_count': 100, 'sha256': 'c' * 64},
                'vendor_receipt': {'byte_count': 100, 'sha256': 'd' * 64},
                'lookup_counts': {prefix + '_' + name: (decisions if prefix == 'vendor' else 0)
                    for prefix in ('native', 'vendor') for name in ('identity_check_attempts',
                        'identity_check_completed', 'price_lookup_attempts', 'price_lookup_completed')},
                **m.monetary.FALSE_FLAGS},
            'counts': {'reference_batch_attempts': decisions, 'reference_batch_completed': decisions,
                'close_batch_attempts': closes, 'close_batch_completed': closes},
            'reference_path_sha256': 'e' * 64, 'authoritative_close_path_sha256': 'f' * 64,
            'unique_close_count': closes, 'engine_NAV_diagnostic_path_sha256': '0' * 64,
            'reference_QC_History_calls_by_component': 0, 'split_QC_History_calls_by_component': 0,
            **m.monetary.FALSE_FLAGS}}


def result_fixture():
    stats, _ = old.result_fixture()
    expected = profile()
    meta, months = (json.loads(stats[name]) for name in (old.runtime.META_STATISTIC, old.runtime.MONTHLY_STATISTIC))
    meta.update(schema=m.RESULT_SCHEMA, candidate_id=expected['candidate_id'],
        profile_sha256=expected['profile_sha256'], package_sha256=expected['package_sha256'],
        lineage_sha256=expected['lineage_sha256'], raw_reference_history_calls=0,
        common_price=common_result(expected), **m.FALSE_FLAGS)
    months.update(schema=m.MONTH_SCHEMA, candidate_id=expected['candidate_id'], profile_sha256=expected['profile_sha256'])
    return {m.META_STATISTIC: m.canonical(meta).decode(), m.MONTHLY_STATISTIC: m.canonical(months).decode()}, expected


@pytest.mark.parametrize('count', [6, 8])
@pytest.mark.parametrize('arm', [0, 100, 200])
def test_common_profile_binds_separate_unchanged_quote_strategy_and_all_six_cells(count, arm):
    checked = profile(count, arm)
    assert m.validate_profile(checked) == checked
    assert checked['strategy_profile'] == strategy(count, arm)
    assert checked['candidate_id'].endswith('-quote-aware-v1-common-RAW-v1')
    assert all(checked[key] is False for key in m.FALSE_FLAGS)
    assert checked['frozen_quote_base_sha256'] == m.FROZEN_BASE_SHA256
    assert checked['strategy_profile']['source_pins'] != checked['source_pins']


@pytest.mark.parametrize('field,value', [('runtime_project_id', True), ('runtime_project_id', 0),
    ('native_source_context_sha256', 'x' * 64), ('monetary_policy_sha256', 'c' * 64),
    ('source_admission_granted', True), ('source_pins', {'../file.py': 'a' * 64})])
def test_profile_cannot_grant_source_authority_or_refresh_context_or_use_invalid_project(field, value):
    checked = profile(); checked[field] = value
    refused('source_pins' if field == 'source_pins' else 'profile', lambda: m.validate_profile(checked))


def test_new_aggregate_reader_accepts_honest_zero_reference_history_and_independent_source_counts():
    stats, expected = result_fixture()
    result = m.validate_result_statistics(stats, expected_profile=expected)
    assert result['meta']['raw_reference_history_calls'] == 0
    assert result['meta']['split_unit_history_calls'] == 302
    assert result['meta']['common_price']['ledger']['counts']['reference_batch_completed'] == 302
    assert result['meta']['source_admission_granted'] is False
    assert len(result['monthly']['months']) == 70
    result['meta']['common_price']['ledger']['counts']['reference_batch_completed'] = 0
    assert json.loads(stats[m.META_STATISTIC])['common_price']['ledger']['counts']['reference_batch_completed'] == 302


@pytest.mark.parametrize('mutation', ['fake_history', 'split_missing', 'source_failed_lookup', 'source_extra',
    'source_flag', 'close_missing', 'source_no_refs', 'source_wrong_context', 'source_false_native_count',
    'fractional_count', 'old_schema', 'old_month_schema', 'bad_order_fill', 'bad_month_NAV', 'bad_fee',
    'excess_native_lookup_count', 'excess_total_lookup_count', 'excess_vendor_budget'])
def test_new_reader_preserves_all_terminal_geometry_fees_monthly_and_source_relationships(mutation):
    stats, expected = result_fixture()
    meta, months = (json.loads(stats[name]) for name in (m.META_STATISTIC, m.MONTHLY_STATISTIC))
    ledger = meta['common_price']['ledger']
    if mutation == 'fake_history': meta['raw_reference_history_calls'] = 302
    elif mutation == 'split_missing': meta['split_unit_history_calls'] = 301
    elif mutation == 'source_failed_lookup': ledger['source_observation']['lookup_counts']['vendor_price_lookup_completed'] -= 1
    elif mutation == 'source_extra': ledger['raw_prices'] = ['PRIVATE']
    elif mutation == 'source_flag': ledger['source_admission_granted'] = True
    elif mutation == 'close_missing': ledger['unique_close_count'] -= 1
    elif mutation == 'source_no_refs': ledger['counts']['reference_batch_completed'] = 0
    elif mutation == 'source_wrong_context': meta['common_price']['vendor_source_context_sha256'] = 'c' * 64
    elif mutation == 'source_false_native_count':
        for key in ledger['source_observation']['lookup_counts']: ledger['source_observation']['lookup_counts'][key] = 0
    elif mutation == 'fractional_count': ledger['counts']['reference_batch_attempts'] = True
    elif mutation == 'excess_vendor_budget':
        for name in ledger['source_observation']['lookup_counts']:
            ledger['source_observation']['lookup_counts'][name] = 300001 if name.startswith('vendor_') else 0
    elif mutation in ('excess_native_lookup_count', 'excess_total_lookup_count'):
        bound = (len(expected['strategy_profile']['decision_sessions']) + len(expected['strategy_profile']['evaluation_sessions']))
        for name in ledger['source_observation']['lookup_counts']:
            ledger['source_observation']['lookup_counts'][name] = (6 * bound if mutation == 'excess_native_lookup_count' else 256 * bound)
    elif mutation == 'old_schema': meta['schema'] = 'arv2-newrule-comparison-result-v1'
    elif mutation == 'old_month_schema': months['schema'] = 'arv2-newrule-monthly-return-v1'
    elif mutation == 'bad_order_fill': meta['fill_count'] += 1
    elif mutation == 'bad_month_NAV': months['months'][-1][2] = '100.000000'
    else: meta['account_aggregates']['total_engine_fees'] = '999'
    stats = {m.META_STATISTIC: m.canonical(meta).decode(), m.MONTHLY_STATISTIC: m.canonical(months).decode()}
    with pytest.raises(m.Refused): m.validate_result_statistics(stats, expected_profile=expected)


def test_reader_never_delegates_to_old_validator_with_fabricated_history_counts(monkeypatch):
    stats, expected = result_fixture()
    monkeypatch.setattr(m.base, 'validate_result_statistics', lambda *a, **k: pytest.fail('old validator called'))
    assert m.validate_result_statistics(stats, expected_profile=expected)['meta']['raw_reference_history_calls'] == 0


class Source:
    def require_identity(self, identity):
        assert identity in ('A', 'B') or identity.startswith('own-etf-')
    def session_close(self, session):
        return m.base.instant(datetime.fromisoformat(session + 'T16:00:00'))


class Ledger:
    def __init__(self): self.references, self.closes = [], []
    def reference_prices(self, prior, ids, holdings, symbols, *, now):
        self.references.append((prior, ids, holdings, symbols, now))
        return {identity: D('20') for identity in ids}
    def observe_close(self, session, **kwargs):
        self.closes.append((session, kwargs))
        return D('1234.56'), D('0.25')


@pytest.fixture
def driver(monkeypatch):
    value, algorithm, symbols = old.driver()
    value.__class__ = m.CommonPriceComparisonDriver
    value._common_source, value._common_ledger = Source(), Ledger()
    value._common_ready = True
    monkeypatch.setattr(value, '_common_guard', lambda: None)
    value._freeze_fund_translation()
    return NS(value=value, algorithm=algorithm, symbols=symbols)


def test_fund_bridge_is_bijective_price_only_and_reference_ensures_exact_original_subscriptions(driver):
    value, algorithm, symbols = driver.value, driver.algorithm, driver.symbols
    original_map = dict(value._symbol_by_security)
    algorithm.time = datetime(2026, 10, 12, 9, 20)
    algorithm.portfolio[symbols['A']].quantity = D(2)
    algorithm.portfolio[symbols['SPY']].quantity = D(3)
    fund_sid = symbols['SPY'].id
    result = value._reference_prices('2026-10-09', tuple(sorted(('A', 'B', fund_sid))))
    assert result == {'A': D(20), 'B': D(20), fund_sid: D(20)}
    prior, ids, holdings, actual_symbols, now = value._common_ledger.references[0]
    assert ids == tuple(sorted(('A', 'B', 'own-etf-SPY'))) and holdings == {'A': 2, 'own-etf-SPY': 3}
    assert actual_symbols['own-etf-SPY'] is symbols['SPY']
    assert value._symbol_by_security == original_map and value._reference_history_call_count == 0
    assert symbols['A'].id in value._active_dynamic_sids
    assert value._price_to_base['own-etf-SPY'] == fund_sid
    assert all(value._price_to_base[price_id] == sid for sid, price_id in value._base_to_price.items())


@pytest.mark.parametrize('mode', ['fund_duplicate', 'fund_stock_collision', 'wrong_symbol_roundtrip'])
def test_fund_bridge_cannot_replace_identity_or_hide_collisions(driver, mode):
    value = driver.value
    if mode == 'fund_duplicate': value._etf_symbols['QQQ'] = value._etf_symbols['SPY']
    elif mode == 'fund_stock_collision': value._security_by_sid[value._etf_symbols['SPY'].id] = 'A'
    else: value._symbol_by_security[value._etf_symbols['SPY'].id] = value._etf_symbols['QQQ']
    refused('fund_translation', value._freeze_fund_translation)


def test_reference_cannot_drop_an_actual_positive_holding(driver):
    driver.algorithm.portfolio[driver.symbols['B']].quantity = D(1)
    refused('reference', lambda: driver.value._reference_prices('2026-10-09', ('A',)))
    assert not driver.value._common_ledger.references


@pytest.mark.parametrize('clock', ['09:31:00', '15:59:59'])
def test_close_never_uses_future_end_of_day_marks_intraday(driver, clock):
    driver.algorithm.time = datetime.fromisoformat('2026-10-13T' + clock)
    refused('close_clock', driver.value.on_after_close)
    assert not driver.value._common_ledger.closes and not driver.value._account_observations


def test_actual_close_uses_complete_held_census_cash_and_common_NAV_not_engine_NAV(driver, monkeypatch):
    value, algorithm, symbols = driver.value, driver.algorithm, driver.symbols
    algorithm.time = datetime(2026, 10, 13, 16)
    algorithm.portfolio[symbols['B']].quantity = D(7)
    algorithm.portfolio[symbols['XLF']].quantity = D(2)
    monkeypatch.setattr(value, '_portfolio_equity', lambda: D('99999999'))
    value.on_after_close()
    assert value._account_observations['2026-10-13'] == D('1234.56')
    assert value._gross_exposure_observations['2026-10-13'] == D('.25')
    session, call = value._common_ledger.closes[0]
    assert call['holdings'] == {'B': 7, 'own-etf-XLF': 2}
    assert call['cash'] == algorithm.portfolio.cash and call['engine_nav'] == D('99999999')
    assert not algorithm.submitted


def test_unreadable_engine_NAV_diagnostic_does_not_replace_or_veto_authoritative_NAV(driver, monkeypatch):
    driver.algorithm.time = datetime(2026, 10, 13, 16)
    def broken(): raise RuntimeError('PRIVATE')
    monkeypatch.setattr(driver.value, '_portfolio_equity', broken)
    driver.value.on_after_close()
    assert driver.value._common_ledger.closes[0][1]['engine_nav'] is None
    assert driver.value._account_observations['2026-10-13'] == D('1234.56')


def test_runtime_does_not_override_any_frozen_economic_or_intraday_method():
    owner = m.CommonPriceComparisonDriver
    allowed = {'__init__', 'initialize', '_reference_prices', 'on_after_close', 'on_end_of_algorithm'}
    assert {name for name in owner.__dict__ if callable(owner.__dict__[name])
        and hasattr(m.base.NewruleComparisonDriver, name)} == allowed
    for name in ('on_before_open', '_split_factors', 'on_splits', '_submit_market', 'on_order_event',
                 'on_after_open', 'on_data', 'configure_security'):
        assert getattr(owner, name) is getattr(m.base.NewruleComparisonDriver, name)
    raw = Path(m.__file__).read_bytes()
    tree = ast.parse(raw)
    assert not any(isinstance(node, ast.Attribute) and node.attr in
        ('set_market_price', 'set_holdings', 'get_file_path', 'history', 'read_bytes', 'save_bytes')
        for node in ast.walk(tree))
