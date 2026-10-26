"""Pure prospectively frozen EXT26 account metrics; imports perform no I/O.

The caller must independently extract and retain native API evidence. Supplied
hash/shape bindings do not attest provider authenticity or prove extraction.
All account NAV, returns, variance, cost and turnover arithmetic is Fraction.
Statistical outputs use explicit Decimal precision50; no financial float is
used. This avoids potentially giant exact variance/turnover denominator dumps.
No raw market inputs, operator state, chart timestamp guessing, gap filling,
currency inference, independent sleeve P&L or strategy acceptance is provided.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction
import re

from . import extended_evidence as e

CALENDAR_SHA256 = '3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d'
INITIAL_NAV, PRECISION = Fraction(100000), 50
STATUSES = frozenset({'New', 'Submitted', 'PartiallyFilled', 'Filled', 'Canceled', 'None', 'Invalid', 'CancelPending', 'UpdateSubmitted'})
MetricsError = e.EvidenceError


def _fail(): raise MetricsError('invalid exact extended metrics or incomplete native observations')


def _exact(value):
    if type(value) is not e.JsonNumber or len(value.lexeme) > 1000: _fail()
    result = value.fraction()
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > 4096: _fail()
    return result


def _out(value):
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def _fill_price(value):
    """Native numeric price or explicitly derived exact event-weighted VWAP.

    The tagged rational is not a native wire-price observation and is allowed
    only for fill price; quantities, fees and NAV retain numeric-token rules.
    """
    if type(value) is e.JsonNumber:
        return _exact(value)
    if type(value) is not dict:
        _fail()
    e._closed(value, {'schema', 'numerator', 'denominator'})
    if value['schema'] != 'tpr-ext26-derived-fill-vwap-v1':
        _fail()
    for key in ('numerator', 'denominator'):
        token = value[key]
        if type(token) is not str or len(token) > 1000 or not re.fullmatch(r'[1-9][0-9]*', token):
            _fail()
    numerator, denominator = int(value['numerator']), int(value['denominator'])
    if max(numerator.bit_length(), denominator.bit_length()) > 4096:
        _fail()
    result = Fraction(numerator, denominator)
    if result.numerator != numerator or result.denominator != denominator:
        _fail()
    return result


def _decimal(value):
    return Decimal(value.numerator) / Decimal(value.denominator)


def _stat_text(value):
    with localcontext() as context:
        context.prec = PRECISION
        return str(_decimal(value))


def _calendar(raw):
    if e.digest(raw) != CALENDAR_SHA256: _fail()
    body = e.parse_json(raw)
    sessions = body.get('valuation_sessions')
    if (body.get('schema') != 'tpr-extended-calendar-v1' or body.get('study_id') != e.STUDY_ID
            or body.get('study_freeze_sha256') != e.FREEZE_SHA256 or type(sessions) is not list
            or len(sessions) != 1449 or sessions != sorted(set(sessions))
            or sessions[0] != '2021-01-04' or sessions[-1] != '2026-10-09'):
        _fail()
    return tuple(sessions)


def _series(raw, expected_hash, sessions):
    if e.digest(raw) != e._hash(expected_hash): _fail()
    rows = e.parse_json(raw)
    if type(rows) is not list or len(rows) != len(sessions): _fail()
    values = []
    for row, session in zip(rows, sessions):
        e._closed(row, {'session', 'nav'})
        if row['session'] != session: _fail()
        nav = _exact(row['nav'])
        if nav <= 0: _fail()
        values.append(nav)
    return tuple(values)


def _nav(values, sessions):
    previous, peak, worst, returns = INITIAL_NAV, INITIAL_NAV, Fraction(0), []
    year_base, annual, year = INITIAL_NAV, [], sessions[0][:4]
    for session, nav in zip(sessions, values):
        if session[:4] != year:
            annual.append({'year': year, 'return': _out(previous / year_base - 1), 'partial': False})
            year_base, year = previous, session[:4]
        returns.append(nav / previous - 1)
        peak = max(peak, nav)
        worst = max(worst, 1 - nav / peak)
        previous = nav
    annual.append({'year': year, 'return': _out(values[-1] / year_base - 1), 'partial': True})
    mean = sum(returns, Fraction(0)) / len(returns)
    variance = sum(((value - mean) ** 2 for value in returns), Fraction(0)) / (len(returns) - 1)
    elapsed = (date.fromisoformat(sessions[-1]) - date.fromisoformat(sessions[0])).days
    with localcontext() as context:
        context.prec = PRECISION
        standard_deviation = _decimal(variance).sqrt()
        volatility = standard_deviation * Decimal(252).sqrt()
        sharpe = None if variance == 0 else str(_decimal(mean) * Decimal(252).sqrt() / standard_deviation)
        cagr = (_decimal(values[-1] / INITIAL_NAV).ln() * Decimal('365.25') / Decimal(elapsed)).exp() - 1
    return {'observations': len(values), 'first_session': sessions[0], 'last_session': sessions[-1],
        'initial_nav_usd': _out(INITIAL_NAV), 'last_nav_usd': _out(values[-1]),
        'total_return': _out(values[-1] / INITIAL_NAV - 1), 'daily_close_max_drawdown': _out(worst),
        'mean_daily_return_decimal': _stat_text(mean), 'sample_daily_return_variance_decimal': _stat_text(variance),
        'annual_returns': annual, 'cagr_decimal': str(cagr), 'elapsed_calendar_days': elapsed,
        'annualized_volatility_decimal': str(volatility), 'sharpe_rf0_decimal': sharpe}


def nav_metrics(series_raw, calendar_raw, *, expected_series_sha256):
    """Require every frozen daily close; NAV tokens cannot be float/bool/string."""
    sessions = _calendar(calendar_raw)
    return _nav(_series(series_raw, expected_series_sha256, sessions), sessions)


def order_pages_identity(pages):
    """Exact ordered normalized-page hash; no claim of native completeness."""
    if type(pages) is not list or not 1 <= len(pages) <= 506 or any(type(raw) is not bytes for raw in pages): _fail()
    return e.digest(e.canonical({'schema': 'tpr-ext26-normalized-order-pages-v1', 'page_sha256': [e.digest(raw) for raw in pages]}))


def execution_metrics(orders_raw, series_raw, calendar_raw, *, expected_orders_sha256, expected_series_sha256,
                      expected_order_count=None):
    """Metrics from explicit reported order observations, never fee estimates.

    Each normalized row must preserve the actual native fields or null. A
    missing fee/currency or fill observation keeps full totals null; separately
    labeled known subtotals are not the run's complete costs or turnover.
    Gross turnover is absolute reported USD fill notional / prior-close NAV.
    A native order row is not invented to represent unobserved individual fills.
    ``requested_quantity`` means the actual reported native order Quantity in
    its observed share basis (possibly post-split), NOT original strategy intent
    without independent journal proof. Extraction must document that mapping.
    """
    sessions = _calendar(calendar_raw)
    nav = _series(series_raw, expected_series_sha256, sessions)
    if type(orders_raw) is list:
        if order_pages_identity(orders_raw) != e._hash(expected_orders_sha256): _fail()
        if type(expected_order_count) is not int or not 0 <= expected_order_count <= 50000: _fail()
        rows = []
        for index, raw in enumerate(orders_raw):
            page = e.parse_json(raw)
            if type(page) is not list or len(page) > 99 or index < len(orders_raw) - 1 and len(page) != 99: _fail()
            rows.extend(page)
    else:
        if e.digest(orders_raw) != e._hash(expected_orders_sha256): _fail()
        rows = e.parse_json(orders_raw)
    if type(rows) is not list or len(rows) > 50000: _fail()
    if expected_order_count is not None and (type(expected_order_count) is not int or len(rows) != expected_order_count): _fail()
    prior = dict(zip(sessions, (INITIAL_NAV, *nav[:-1])))
    ids, status_counts = set(), {status: 0 for status in sorted(STATUSES)}
    fees, turnover, underfill, overfill = Fraction(0), Fraction(0), Fraction(0), Fraction(0)
    missing_fees, missing_fills = 0, 0
    for row in rows:
        e._closed(row, {'order_id', 'session', 'status', 'requested_quantity', 'fill_quantity', 'fill_price',
            'fill_currency', 'reported_fee', 'fee_currency'})
        identity = e._integer(row['order_id'])
        if (identity in ids or type(row['session']) is not str or row['session'] not in prior
                or type(row['status']) is not str or row['status'] not in STATUSES): _fail()
        ids.add(identity); status_counts[row['status']] += 1
        requested = _exact(row['requested_quantity'])
        if requested.denominator != 1: _fail()
        filled = None if row['fill_quantity'] is None else _exact(row['fill_quantity'])
        if filled is not None:
            if filled.denominator != 1: _fail()
            if filled and (not requested or (filled > 0) != (requested > 0)): _fail()
            if abs(filled) > abs(requested): _fail()
            if row['status'] == 'PartiallyFilled' and not 0 < abs(filled) < abs(requested): _fail()
            if row['status'] == 'Filled' and abs(filled) != abs(requested): _fail()
            underfill += max(Fraction(0), abs(requested) - abs(filled))
            overfill += max(Fraction(0), abs(filled) - abs(requested))
        if row['reported_fee'] is None or row['fee_currency'] != 'USD':
            missing_fees += 1
            if row['reported_fee'] is not None and _exact(row['reported_fee']) < 0: _fail()
        else:
            fee = _exact(row['reported_fee'])
            if fee < 0: _fail()
            fees += fee
        if filled is None or (filled and (row['fill_price'] is None or row['fill_currency'] != 'USD')):
            missing_fills += 1
        elif filled:
            price = _fill_price(row['fill_price'])
            if price <= 0: _fail()
            turnover += abs(filled) * price / prior[row['session']]
        elif row['fill_price'] is not None:
            _fill_price(row['fill_price'])
        for key in ('fee_currency', 'fill_currency'):
            if row[key] is not None and (type(row[key]) is not str or not 0 < len(row[key]) <= 12): _fail()
    return {'order_count': len(rows), 'status_counts': status_counts, 'invalid_order_count': status_counts['Invalid'],
        'canceled_order_count': status_counts['Canceled'], 'missing_fee_or_currency_orders': missing_fees,
        'missing_fill_or_currency_orders': missing_fills, 'reported_usd_fee_subtotal': _out(fees),
        'complete_reported_fees_usd': None if missing_fees else _out(fees),
        'reported_gross_turnover_subtotal_decimal': _stat_text(turnover),
        'complete_reported_gross_turnover_decimal': None if missing_fills else _stat_text(turnover),
        'known_underfilled_shares': _out(underfill), 'known_overfilled_shares': _out(overfill),
        'independent_sleeve_pnl_observed': False}


def _binding(body, candidate, series_raw):
    e._closed(body, {'schema', 'candidate_id', 'project_id', 'compile_id', 'backtest_id', 'freeze_sha256',
        'config_sha256', 'source_hashes', 'input_hashes', 'series_sha256', 'native_backtest_projection_sha256',
        'order_collection_sha256', 'summary_aggregate_sha256', 'index_aggregate_sha256'})
    if (body['schema'] != 'tpr-ext26-metrics-binding-v1' or body['candidate_id'] != candidate
            or body['freeze_sha256'] != e.FREEZE_SHA256 or body['series_sha256'] != e.digest(series_raw)):
        _fail()
    e._integer(body['project_id']); e._id(body['compile_id']); e._id(body['backtest_id'])
    for key in ('config_sha256', 'series_sha256', 'native_backtest_projection_sha256', 'order_collection_sha256',
            'summary_aggregate_sha256', 'index_aggregate_sha256'): e._hash(body[key])
    for key in ('source_hashes', 'input_hashes'):
        if type(body[key]) is not dict or not 1 <= len(body[key]) <= 32: _fail()
        for name, identity in body[key].items(): e._id(name); e._hash(identity)
    if body['input_hashes'].get('calendar.json') != CALENDAR_SHA256 or 'preparation.json' not in body['input_hashes']: _fail()
    return body


def paired_metrics(on_raw, off_raw, calendar_raw, *, on_binding, off_binding):
    """Same dates, money anchors and conventions; no independent-alpha claim."""
    on_candidate = next(candidate for candidate, arm in e.CANDIDATES.items() if arm == 'tpr_on')
    off_candidate = next(candidate for candidate, arm in e.CANDIDATES.items() if arm == 'tpr_off')
    on = _binding(on_binding, on_candidate, on_raw); off = _binding(off_binding, off_candidate, off_raw)
    if e._integer(on['project_id']) == e._integer(off['project_id']) or on['backtest_id'] == off['backtest_id']: _fail()
    if on['input_hashes']['preparation.json'] != off['input_hashes']['preparation.json']: _fail()
    sessions = _calendar(calendar_raw)
    on_values, off_values = _series(on_raw, on['series_sha256'], sessions), _series(off_raw, off['series_sha256'], sessions)
    on_metrics, off_metrics = _nav(on_values, sessions), _nav(off_values, sessions)
    return {'schema': 'tpr-ext26-paired-metrics-v1', 'study_id': e.STUDY_ID, 'calendar_sha256': CALENDAR_SHA256,
        'methodology': {'initial_anchor': '100000 USD before first frozen session', 'daily_returns_include_first_session': True,
            'drawdown_includes_initial_anchor': True, 'cagr_elapsed': 'last session date minus first session date; 365.25 days/year',
            'volatility': 'sample daily-return variance, 252 sessions/year', 'sharpe': 'daily arithmetic mean, annualized sqrt252, risk-free0',
            'zero_variance_sharpe': None, 'statistics_decimal_precision': PRECISION, 'internal_statistic_arithmetic': 'exact Fraction',
            'annual2026': 'partial through2026-10-09'},
        'on': on_metrics, 'off': off_metrics, 'bindings': {'on': on, 'off': off},
        'return_difference': _out(on_values[-1] / INITIAL_NAV - off_values[-1] / INITIAL_NAV),
        'last_nav_difference_usd': _out(on_values[-1] - off_values[-1]),
        'provider_authenticity_attested': False, 'independent_sleeve_pnl_observed': False,
        'confirmatory_alpha': False, 'strategy_accepted': False, 'canonical_admission': False}


def compare_matched_input_chains(on_chains, off_chains):
    """Compare whole-run hash receipts only, with explicit absent observations.

    The actual extractor must separately bind these to each own project/job,
    source/config/attempt and compact-summary hash. This pure equality check
    does not reconstruct licensed inputs, attest PIT or establish causal alpha.
    """
    def count(value):
        if type(value) is int and 0 <= value <= 301: return value
        number = _exact(value)
        if number.denominator != 1 or not 0 <= number <= 301: _fail()
        return int(number)
    for chains in (on_chains, off_chains):
        e._closed(chains, {'SPY', 'QQQ', 'SOXX', 'XLV', 'REMX', 'XLE'})
        for sleeve in chains.values():
            e._closed(sleeve, {'membership', 'caps', 'selection', 'prior_marks'})
            for chain in sleeve.values():
                e._closed(chain, {'sha256', 'observed_decisions', 'unavailable_decisions', 'expected_decisions'})
                e._hash(chain['sha256'])
                if count(chain['expected_decisions']) != 301 or count(chain['observed_decisions']) + count(chain['unavailable_decisions']) != 301:
                    _fail()
    domains, mismatches = {}, []
    for sleeve in sorted(on_chains):
        domains[sleeve] = {}
        for domain in sorted(on_chains[sleeve]):
            on, off = on_chains[sleeve][domain], off_chains[sleeve][domain]
            equal = (on['sha256'] == off['sha256'] and count(on['observed_decisions']) == count(off['observed_decisions'])
                and count(on['unavailable_decisions']) == count(off['unavailable_decisions']))
            domains[sleeve][domain] = {'receipts_equal': equal, 'on_observed_decisions': count(on['observed_decisions']),
                'off_observed_decisions': count(off['observed_decisions']), 'on_unavailable_decisions': count(on['unavailable_decisions']),
                'off_unavailable_decisions': count(off['unavailable_decisions'])}
            if not equal: mismatches.append({'sleeve': sleeve, 'domain': domain})
    return {'matched_chain_receipts_equal': not mismatches, 'domains': domains, 'mismatches': mismatches,
        'expected_decisions': 301, 'all_domain_decisions_observed': all(row['on_observed_decisions'] == row['off_observed_decisions'] == 301
            for sleeve in domains.values() for row in sleeve.values()), 'independent_input_row_replay': False,
        'provider_authenticity_attested': False, 'point_in_time_verified': False, 'causal_alpha_established': False,
        'strategy_accepted': False, 'canonical_admission': False}
