"""Frozen direct-Sharadar monthly source custody, never an empirical bundle."""
from __future__ import annotations

from calendar import monthrange
from datetime import date
import json
import re

from data.hashing import hash_payload

FIRST_DATE, LAST_DATE = '2022-01-03', '2026-08-31'
TABLES = ('stocks', 'daily')
FIELDS = {'stocks': ('ticker', 'date', 'open', 'high', 'low', 'close', 'volume', 'closeunadj', 'lastupdated'),
          'daily': ('ticker', 'date', 'marketcap', 'lastupdated')}
MONTHS = tuple((f'{year:04d}-{month:02d}', max(FIRST_DATE, f'{year:04d}-{month:02d}-01'),
                min(LAST_DATE, f'{year:04d}-{month:02d}-{monthrange(year, month)[1]:02d}'))
               for year in range(2022, 2027) for month in range(1, 13)
               if FIRST_DATE[:7] <= f'{year:04d}-{month:02d}' <= LAST_DATE[:7])
PAGE_LIMIT, PAGES_PER_PANEL = 10000, 64
MAXIMUM_REQUESTS = 56 * 2 * 64
MAXIMUM_BYTES, MAXIMUM_RAW_BYTES, MAXIMUM_ROWS = 8 * 1024 * 1024, 8 * 1024**3, 32000000
_DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}\Z')
_NUMBER = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z')


class NativeMarketInputError(ValueError):
    pass


def _require(value, code):
    if not value:
        raise NativeMarketInputError(code)


def page_request(table, month, page):
    _require(type(table) is str and table in TABLES and type(month) is str
             and type(page) is int and 0 <= page < PAGES_PER_PANEL, 'fixed_market_panel_required')
    matches = [bounds for bounds in MONTHS if bounds[0] == month]
    _require(len(matches) == 1, 'fixed_market_month_required')
    _, start, end = matches[0]
    return {'method': 'GET', 'url': 'https://api.sharadar.com/v1.0/data/' + table,
            'params': {'format': 'json', 'fields': ','.join(FIELDS[table]), 'from': start, 'to': end,
                       'limit': str(PAGE_LIMIT), 'offset': str(page * PAGE_LIMIT), 'sort': 'date.asc'},
            'authentication': 'x-api-key_header_not_recorded'}


def market_input_protocol():
    return {'schema': 'si-native-market-input-capture-protocol-v1', 'first_date': FIRST_DATE,
            'last_date': LAST_DATE, 'panels': [{'table': table, 'month': month,
                'initial_request': page_request(table, month, 0)} for month, _, _ in MONTHS for table in TABLES],
            'months': len(MONTHS), 'maximum_requests': MAXIMUM_REQUESTS,
            'maximum_pages_per_table_month': PAGES_PER_PANEL, 'page_limit': PAGE_LIMIT,
            'maximum_response_bytes': MAXIMUM_BYTES, 'maximum_total_raw_bytes': MAXIMUM_RAW_BYTES,
            'maximum_total_rows': MAXIMUM_ROWS, 'budget_reserve': 'whole_fixed_next_page_before_request',
            'pagination': 'offset0_then_exact10000_increments_only_after_full_previous_page',
            'termination': 'first_count_strictly_below10000_each_panel', 'sort': 'date.asc',
            'population': 'all_reported_no_ticker_current_active_or_financial_screen',
            'dates': 'scope_required_before_raw_hash_publication_and_financial_validation',
            'scope_refusal': 'no_raw_body_or_body_digest_when_any_date_scope_cannot_be_established',
            'numbers': 'exact_lexical_JSON_number_tokens_no_binary_float_or_normalization',
            'refusals': 'all_malformed_and_identifiable_duplicate_origins_private_no_alias_or_substitution',
            'duplicate_events': 'first_origin_plus_current_page_new_peers_no_quadratic_cumulative_copy',
            'credential': 'specifically_authorized_protected_sharadar_env_only_no_Keychain_fallback',
            'claim': 'one_global_protocol_claim_no_timestamp_head_or_panel_restart',
            'automatic_retries': 0, 'restart_or_resume': False, 'redirects': False, 'proxies': False,
            'source_only': True, 'data_or_fitness_admitted': False, 'signal_or_return_computed': False,
            'outcome_looks': 0, 'qc_attempts': 0, 'backtest_result_exists': False}


class NumberToken(str):
    """Retain exact JSON numeric spelling, not provider-quoted text."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'duplicate_source_JSON_key')
        result[key] = value
    return result


def decode_page(raw):
    _require(type(raw) is bytes and len(raw) <= MAXIMUM_BYTES, 'market_response_byte_bound')
    def nonfinite(_):
        raise NativeMarketInputError('nonfinite_source_JSON')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                           parse_float=NumberToken, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise NativeMarketInputError('source_UTF8_JSON_refused') from None
    _require(type(value) is dict and set(value) == {'count', 'data'}
             and type(value['count']) is int and 0 <= value['count'] <= PAGE_LIMIT
             and type(value['data']) is list and value['count'] == len(value['data']), 'source_page_envelope')
    return value['data']


def _canonical_date(value):
    if type(value) is not str or _DATE.fullmatch(value) is None:
        return None
    try:
        return value if date.fromisoformat(value).isoformat() == value else None
    except ValueError:
        return None


def verify_page_dates(rows, *, month):
    """Establish the entire response's date scope before retaining its bytes."""
    _, start, end = next(bounds for bounds in MONTHS if bounds[0] == month)
    for row in rows:
        raw_date = row.get('date') if type(row) is dict else None
        recognizable = _canonical_date(raw_date.strip()[:10]) if type(raw_date) is str else None
        _require(recognizable is not None, 'unrecognizable_source_price_date_refused')
        _require(FIRST_DATE <= recognizable <= LAST_DATE,
                 'protected_or_outside_global_price_date_refused')
        _require(start <= recognizable <= end, 'source_month_filter_refused')
        _require(_canonical_date(raw_date.strip()) is not None, 'unrecognizable_source_price_date_refused')


def inspect_page(rows, *, table, month, previous_date=None):
    """Return private source-key/refusal origins only, never normalized prices."""
    verify_page_dates(rows, month=month)
    observations = []
    for row_index, row in enumerate(rows):
        ticker = row.get('ticker') if type(row) is dict else None
        raw_date = row.get('date') if type(row) is dict else None
        at = _canonical_date(raw_date)
        grouping_date = _canonical_date(raw_date.strip()) if type(raw_date) is str else None
        grouping_ticker = ticker.strip() if type(ticker) is str else None
        slot = (grouping_ticker, grouping_date) if grouping_ticker and grouping_date else None
        reason = None
        if type(row) is not dict or set(row) != set(FIELDS[table]):
            reason = 'malformed_row_or_fields'
        elif (type(ticker) is not str or not ticker or ticker != ticker.strip() or len(ticker) > 128
              or any(not 33 <= ord(char) <= 126 for char in ticker) or at is None):
            reason = 'malformed_exact_source_key'
        elif _canonical_date(row['lastupdated']) is None:
            reason = 'malformed_lastupdated_metadata'
        else:
            financial = tuple(field for field in FIELDS[table] if field not in ('ticker', 'date', 'lastupdated'))
            if any(not (type(row[field]) is int or type(row[field]) is NumberToken
                        and _NUMBER.fullmatch(row[field]) is not None) for field in financial):
                reason = 'malformed_lexical_financial_token'
        if at is not None:
            _require(previous_date is None or previous_date <= at, 'source_date_sort_refused')
            previous_date = at
        observations.append((row_index, slot, reason))
    return tuple(observations), previous_date
