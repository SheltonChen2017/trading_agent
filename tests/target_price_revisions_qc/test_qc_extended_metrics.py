"""Synthetic exact account/control proofs; no actual outcomes or private I/O."""
from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction
import http.client
from pathlib import Path
import socket

import pytest

from research.target_price_revisions_qc import extended_evidence as e, extended_metrics as m, extended_operations as o

ON, OFF = tuple(e.CANDIDATES)


@pytest.fixture(autouse=True)
def deny_real_io(monkeypatch):
    def denied(*a, **kw): raise AssertionError('actual credential/private/network access denied')
    monkeypatch.setattr(o, 'credential', denied)
    monkeypatch.setattr(o, 'read_private', denied)
    monkeypatch.setattr(http.client, 'HTTPSConnection', denied)
    monkeypatch.setattr(socket.socket, 'connect', denied)


@pytest.fixture
def calendar():
    raw = (Path(__file__).resolve().parents[2] / 'research/target_price_revisions_qc/extended_calendar.json').read_bytes()
    assert e.digest(raw) == m.CALENDAR_SHA256
    return raw, tuple(e.parse_json(raw)['valuation_sessions'])


def series(calendar, value='100000'):
    return e.canonical([{'session': session, 'nav': e.JsonNumber(value)} for session in calendar[1]])


def exact(value): return Fraction(int(value['numerator']), int(value['denominator']))


def stat(value):
    with localcontext() as context:
        context.prec = 50
        return Decimal(value.numerator) / Decimal(value.denominator)


def binding(candidate, raw, project):
    return {'schema': 'tpr-ext26-metrics-binding-v1', 'candidate_id': candidate, 'project_id': project,
        'compile_id': 'synthetic-compile-' + str(project), 'backtest_id': 'synthetic-job-' + str(project),
        'freeze_sha256': e.FREEZE_SHA256, 'config_sha256': 'a' * 64, 'source_hashes': {'main.py': 'b' * 64},
        'input_hashes': {'calendar.json': m.CALENDAR_SHA256, 'preparation.json': 'c' * 64}, 'series_sha256': e.digest(raw),
        'native_backtest_projection_sha256': 'd' * 64, 'order_collection_sha256': 'e' * 64,
        'summary_aggregate_sha256': 'f' * 64, 'index_aggregate_sha256': '0' * 64}


def order(session, *, identity=1, quantity='10', filled='10', price='20', fee='0.10', currency='USD', status='Filled'):
    return {'order_id': identity, 'session': session, 'status': status, 'requested_quantity': e.JsonNumber(quantity),
        'fill_quantity': None if filled is None else e.JsonNumber(filled), 'fill_price': None if price is None else e.JsonNumber(price),
        'fill_currency': currency, 'reported_fee': None if fee is None else e.JsonNumber(fee), 'fee_currency': currency}


def execute(calendar, rows):
    raw, account = e.canonical(rows), series(calendar)
    return m.execution_metrics(raw, account, calendar[0], expected_orders_sha256=e.digest(raw), expected_series_sha256=e.digest(account))


def test_documented_native_none_status_is_retained_without_fill_success(calendar):
    result = execute(calendar, [order(calendar[1][0], status='None', filled=None, price=None, fee=None, currency=None)])
    assert result['status_counts']['None'] == 1 and result['status_counts']['Filled'] == 0
    assert result['complete_reported_fees_usd'] is None and result['complete_reported_gross_turnover_decimal'] is None


def test_exact_derived_nonterminating_vwap_changes_only_fill_price_boundary(calendar):
    row = order(calendar[1][0], quantity='3', filled='3')
    row['fill_price'] = {'schema': 'tpr-ext26-derived-fill-vwap-v1', 'numerator': '1', 'denominator': '3'}
    result = execute(calendar, [row])
    assert Decimal(result['complete_reported_gross_turnover_decimal']) == Decimal('0.00001')
    assert result['status_counts']['Filled'] == 1
    row['requested_quantity'] = dict(row['fill_price'])
    with pytest.raises(m.MetricsError): execute(calendar, [row])


@pytest.mark.parametrize('changes', [{'schema': 'native-price'}, {'numerator': '01'}, {'numerator': True},
    {'denominator': '0'}, {'denominator': '-3'}, {'numerator': '2', 'denominator': '6'}, {'extra': 'self-approved'}])
def test_derived_vwap_requires_closed_canonical_positive_rational(calendar, changes):
    row = order(calendar[1][0])
    row['fill_price'] = {'schema': 'tpr-ext26-derived-fill-vwap-v1', 'numerator': '1', 'denominator': '3', **changes}
    with pytest.raises(m.MetricsError): execute(calendar, [row])


def test_flat_nav_complete_pair_has_zero_return_drawdown_and_null_sharpe(calendar):
    raw = series(calendar)
    result = m.paired_metrics(raw, raw, calendar[0], on_binding=binding(ON, raw, 101), off_binding=binding(OFF, raw, 102))
    assert result['on']['observations'] == 1449 and result['on']['sharpe_rf0_decimal'] is None
    assert exact(result['on']['total_return']) == exact(result['on']['daily_close_max_drawdown']) == 0
    assert Decimal(result['on']['cagr_decimal']) == Decimal(result['on']['annualized_volatility_decimal']) == 0
    assert result['on']['annual_returns'][-1]['year'] == '2026' and result['on']['annual_returns'][-1]['partial'] is True
    assert result['provider_authenticity_attested'] is result['confirmatory_alpha'] is result['strategy_accepted'] is False


def test_initial_anchor_and_daily_return_remain_exact(calendar):
    raw = series(calendar, '90000')
    result = m.nav_metrics(raw, calendar[0], expected_series_sha256=e.digest(raw))
    assert exact(result['total_return']) == -Fraction(1, 10)
    assert exact(result['daily_close_max_drawdown']) == Fraction(1, 10)
    assert Decimal(result['mean_daily_return_decimal']) == stat(-Fraction(1, 14490))
    returns = [-Fraction(1, 10)] + [Fraction(0)] * 1448
    mean = sum(returns) / len(returns)
    assert Decimal(result['sample_daily_return_variance_decimal']) == stat(sum((x - mean) ** 2 for x in returns) / 1448)
    assert result['elapsed_calendar_days'] == (m.date(2026, 10, 9) - m.date(2021, 1, 4)).days
    with localcontext() as context:
        context.prec = 50
        deviation = stat(sum((x - mean) ** 2 for x in returns) / 1448).sqrt()
        assert Decimal(result['annualized_volatility_decimal']) == deviation * Decimal(252).sqrt()
        assert Decimal(result['sharpe_rf0_decimal']) == stat(mean) * Decimal(252).sqrt() / deviation


def test_cagr_uses_actual_elapsed_session_dates_and36525_not_trading_years(calendar):
    raw = series(calendar, '200000'); result = m.nav_metrics(raw, calendar[0], expected_series_sha256=e.digest(raw))
    elapsed = (m.date(2026, 10, 9) - m.date(2021, 1, 4)).days
    with localcontext() as context:
        context.prec = 50
        expected = (Decimal(2).ln() * Decimal('365.25') / Decimal(elapsed)).exp() - 1
    assert Decimal(result['cagr_decimal']) == expected


def test_close_drawdown_uses_running_peak_not_terminal_return(calendar):
    rows = e.parse_json(series(calendar)); rows[1]['nav'] = e.JsonNumber('200000'); rows[2]['nav'] = e.JsonNumber('100000')
    raw = e.canonical(rows); result = m.nav_metrics(raw, calendar[0], expected_series_sha256=e.digest(raw))
    assert exact(result['daily_close_max_drawdown']) == Fraction(1, 2) and exact(result['total_return']) == 0


def test_high_precision_nav_token_survives_financial_math(calendar):
    text = '100000.123456789012345678901234567890'
    raw = series(calendar, text); result = m.nav_metrics(raw, calendar[0], expected_series_sha256=e.digest(raw))
    assert exact(result['last_nav_usd']) == Fraction(Decimal(text))
    assert exact(result['total_return']) == Fraction(Decimal(text)) / 100000 - 1


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'reversed', 'foreign', 'extra'])
def test_frozen_calendar_census_never_drops_or_fills_dates(calendar, change):
    rows = e.parse_json(series(calendar))
    if change == 'missing': rows.pop(10)
    elif change == 'duplicate': rows[10] = rows[9]
    elif change == 'reversed': rows.reverse()
    elif change == 'foreign': rows[10]['session'] = '2027-09-01'
    else: rows.append(rows[-1])
    raw = e.canonical(rows)
    with pytest.raises(m.MetricsError): m.nav_metrics(raw, calendar[0], expected_series_sha256=e.digest(raw))


@pytest.mark.parametrize('value', [True, '100000', None, 100000.0, e.JsonNumber('0'), e.JsonNumber('-1')])
def test_non_native_or_nonpositive_nav_is_not_money_authority(calendar, value):
    rows = e.parse_json(series(calendar)); rows[3]['nav'] = value
    if type(value) is float:
        with pytest.raises(e.EvidenceError): e.canonical(rows)
    else:
        raw = e.canonical(rows)
        with pytest.raises(m.MetricsError): m.nav_metrics(raw, calendar[0], expected_series_sha256=e.digest(raw))


def test_annual_returns_use_prior_year_last_close_and_mark_only2026_partial(calendar):
    rows = e.parse_json(series(calendar))
    for row in rows:
        if row['session'] >= '2022-01-03': row['nav'] = e.JsonNumber('110000')
    raw = e.canonical(rows); result = m.nav_metrics(raw, calendar[0], expected_series_sha256=e.digest(raw))
    annual = {row['year']: row for row in result['annual_returns']}
    assert exact(annual['2021']['return']) == 0 and exact(annual['2022']['return']) == Fraction(1, 10)
    assert all(not row['partial'] for row in result['annual_returns'][:-1])


@pytest.mark.parametrize('field,value', [('project_id', True), ('series_sha256', '0' * 64), ('candidate_id', OFF),
    ('native_backtest_projection_sha256', 'unknown')])
def test_pair_requires_closed_exact_candidate_source_bindings(calendar, field, value):
    raw = series(calendar); on = binding(ON, raw, 101); on[field] = value
    with pytest.raises(m.MetricsError): m.paired_metrics(raw, raw, calendar[0], on_binding=on, off_binding=binding(OFF, raw, 102))


def test_pair_refuses_same_job_or_mismatched_preparation(calendar):
    raw = series(calendar); on, off = binding(ON, raw, 101), binding(OFF, raw, 102)
    off['backtest_id'] = on['backtest_id']
    with pytest.raises(m.MetricsError): m.paired_metrics(raw, raw, calendar[0], on_binding=on, off_binding=off)
    off = binding(OFF, raw, 102); off['input_hashes']['preparation.json'] = '0' * 64
    with pytest.raises(m.MetricsError): m.paired_metrics(raw, raw, calendar[0], on_binding=on, off_binding=off)


def test_reported_execution_cost_turnover_and_underfill_are_exact(calendar):
    rows = [order(calendar[1][0], filled='5', fee='0.05', status='PartiallyFilled'),
        order(calendar[1][1], identity=2, quantity='-10', filled='-10', fee='0.10')]
    result = execute(calendar, rows)
    assert exact(result['complete_reported_fees_usd']) == Fraction(3, 20)
    assert Decimal(result['complete_reported_gross_turnover_decimal']) == Decimal('0.003')
    assert exact(result['known_underfilled_shares']) == 5 and result['order_count'] == 2


@pytest.mark.parametrize('missing', ['fee', 'currency', 'fill'])
def test_missing_native_fee_currency_fill_is_not_zero(calendar, missing):
    row = order(calendar[1][0])
    if missing == 'fee': row['reported_fee'] = None
    elif missing == 'currency': row['fee_currency'] = None; row['fill_currency'] = None
    else: row['fill_quantity'] = None
    result = execute(calendar, [row])
    if missing in ('fee', 'currency'): assert result['complete_reported_fees_usd'] is None
    if missing in ('fill', 'currency'): assert result['complete_reported_gross_turnover_decimal'] is None


def test_observed_zero_fill_and_zero_fee_are_explicit_not_missing(calendar):
    result = execute(calendar, [order(calendar[1][0], filled='0', price=None, fee='0', status='Canceled')])
    assert exact(result['complete_reported_fees_usd']) == Decimal(result['complete_reported_gross_turnover_decimal']) == 0
    assert result['canceled_order_count'] == 1 and exact(result['known_underfilled_shares']) == 10


def test_duplicate_order_and_boolean_fee_are_not_accepted(calendar):
    row = order(calendar[1][0])
    with pytest.raises(m.MetricsError): execute(calendar, [row, deepcopy(row)])
    row['reported_fee'] = True
    with pytest.raises(m.MetricsError): execute(calendar, [row])


def test_wrong_wire_hash_or_altered_calendar_refuses(calendar):
    raw = series(calendar)
    with pytest.raises(m.MetricsError): m.nav_metrics(raw, calendar[0], expected_series_sha256='0' * 64)
    with pytest.raises(m.MetricsError): m.nav_metrics(raw, calendar[0] + b' ', expected_series_sha256=e.digest(raw))


def test_paged_native_observations_keep_exact_independent_count_and_order_hash(calendar):
    account = series(calendar)
    rows = [order(calendar[1][0], identity=index + 1) for index in range(105)]
    pages = [e.canonical(rows[:99]), e.canonical(rows[99:])]
    result = m.execution_metrics(pages, account, calendar[0], expected_orders_sha256=m.order_pages_identity(pages),
        expected_series_sha256=e.digest(account), expected_order_count=105)
    assert result['order_count'] == 105 and exact(result['complete_reported_fees_usd']) == Fraction(21, 2)
    with pytest.raises(m.MetricsError): m.execution_metrics(pages[:1], account, calendar[0],
        expected_orders_sha256=m.order_pages_identity(pages[:1]), expected_series_sha256=e.digest(account), expected_order_count=105)
    with pytest.raises(m.MetricsError): m.execution_metrics(pages, account, calendar[0],
        expected_orders_sha256=m.order_pages_identity(pages), expected_series_sha256=e.digest(account))


def test_closed_chain_pair_reports_all_counts_and_never_upgrades_replay_or_causal_alpha():
    on = {sleeve: {domain: {'sha256': 'a' * 64, 'observed_decisions': 300, 'unavailable_decisions': 1,
        'expected_decisions': 301} for domain in ('membership', 'caps', 'selection', 'prior_marks')}
        for sleeve in ('SPY', 'QQQ', 'SOXX', 'XLV', 'REMX', 'XLE')}
    off = deepcopy(on); result = m.compare_matched_input_chains(on, off)
    assert result['matched_chain_receipts_equal'] is True and result['all_domain_decisions_observed'] is False
    assert result['domains']['SPY']['caps']['on_unavailable_decisions'] == 1
    assert result['independent_input_row_replay'] is result['point_in_time_verified'] is result['causal_alpha_established'] is False
    off['REMX']['selection']['sha256'] = 'b' * 64
    result = m.compare_matched_input_chains(on, off)
    assert result['mismatches'] == [{'sleeve': 'REMX', 'domain': 'selection'}]
    off['SPY']['caps']['observed_decisions'] = 301
    with pytest.raises(m.MetricsError): m.compare_matched_input_chains(on, off)


def test_closed_chain_comparison_rejects_boolean_count_and_signal_domain():
    rows = {sleeve: {domain: {'sha256': 'a' * 64, 'observed_decisions': 0, 'unavailable_decisions': 301,
        'expected_decisions': 301} for domain in ('membership', 'caps', 'selection', 'prior_marks')}
        for sleeve in ('SPY', 'QQQ', 'SOXX', 'XLV', 'REMX', 'XLE')}
    other = deepcopy(rows); other['SPY']['caps']['observed_decisions'] = False
    with pytest.raises(m.MetricsError): m.compare_matched_input_chains(rows, other)
    other = deepcopy(rows); other['SPY']['target_weights'] = other['SPY'].pop('selection')
    with pytest.raises(m.MetricsError): m.compare_matched_input_chains(rows, other)


@pytest.mark.parametrize('quantity,filled,status', [('10', '-5', 'PartiallyFilled'), ('-10', '5', 'PartiallyFilled'),
    ('10', '0', 'PartiallyFilled'), ('10', '10', 'PartiallyFilled'), ('10', '5', 'Filled'), ('0', '1', 'Filled'),
    ('10', '11', 'Canceled'), ('10', '0.5', 'PartiallyFilled')])
def test_contradictory_native_fill_direction_status_or_whole_share_basis_refuses(calendar, quantity, filled, status):
    with pytest.raises(m.MetricsError): execute(calendar, [order(calendar[1][0], quantity=quantity, filled=filled, status=status)])
