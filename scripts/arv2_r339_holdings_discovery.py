"""Pure bounded holdings-capability plan and supplied-response inspection.

No I/O, credential lookup, HTTP status handling, dispatch, pagination or data
retention occurs here. A separately frozen caller owns those operations and
must stop the remaining requests to a provider after its first refusal. A
successful sample never authenticates full historical holdings or readiness.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re

SCHEMA = 'arv2-r339-holdings-capability-v1'
FUNDS = ('SPY', 'QQQ', 'SOXX', 'XLV', 'REMX', 'XLE', 'XLI', 'XLF')
DATES = ('2021-10-29', '2026-10-12')
PROVIDERS = ('massive', 'fmp')
ENDPOINTS = {'massive': 'https://api.massive.com/etf-global/v1/constituents',
    'fmp': 'https://financialmodelingprep.com/stable/funds/disclosure-dates'}
MAX_REQUESTS, MAX_BODY, MAX_DEPTH, MAX_FMP_ROWS = 24, 1024 * 1024, 24, 512
MAX_STRING, MAX_NUMBER_CHARS, MAX_CREDENTIAL = 8192, 128, 512
IDENTIFIERS = ('constituent_ticker', 'figi', 'isin', 'sedol', 'us_code')
NUMBERS = ('weight', 'shares_held', 'market_value')
MASSIVE_TEXT = ('asset_class', 'constituent_name', 'country_of_exchange',
    'currency_traded', 'exchange', 'security_type')
MASSIVE_FIELDS = frozenset(('composite_ticker', 'effective_date', 'processed_date',
    'constituent_rank', *IDENTIFIERS, *NUMBERS, *MASSIVE_TEXT))
FALSE_FLAGS = {key: False for key in ('credential_persisted', 'response_body_persisted',
    'response_body_hash_persisted', 'licensed_rows_disclosed', 'identities_disclosed',
    'holdings_or_weights_captured', 'pagination_followed', 'full_fund_coverage_proven',
    'full_window_coverage_proven', 'daily_holdings_proven', 'publication_time_proven',
    'historical_version_or_availability_proven', 'point_in_time_proven',
    'source_or_processing_rights_granted', 'source_admission_granted',
    'permanent_security_master_proven', 'strategy_result_accepted', 'formal_forward_ready',
    'paper_or_live_ready', 'QC_contact', 'Safari_access', 'orders_submitted',
    'physical_request_count_measured')}
FINITE = frozenset(('request', 'credential', 'credential_echo', 'response_bound',
    'json', 'depth', 'schema', 'row_cap', 'date', 'identifier', 'number', 'output', 'unknown'))


class Refused(ValueError):
    """Finite predicate only, never provider text, a credential or a raw row."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
            allow_nan=False).encode('ascii')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise Refused('output') from None


def request_plan():
    """Fresh closed request metadata; credentials are never query members."""
    rows = []
    for fund in FUNDS:
        for day in DATES:
            rows.append({'ordinal': len(rows), 'provider': 'massive',
                'provider_ordinal': len(rows), 'fund': fund, 'effective_date': day,
                'path': '/etf-global/v1/constituents',
                'query': {'composite_ticker': fund, 'effective_date': day, 'limit': '1',
                    'sort': 'constituent_ticker.asc'}})
    for ordinal, fund in enumerate(FUNDS):
        rows.append({'ordinal': len(rows), 'provider': 'fmp',
            'provider_ordinal': ordinal, 'fund': fund, 'effective_date': None,
            'path': '/stable/funds/disclosure-dates', 'query': {'symbol': fund}})
    return tuple(rows)


def _request(value):
    require(type(value) is dict and type(value.get('ordinal')) is int
        and 0 <= value['ordinal'] < MAX_REQUESTS, 'request')
    expected = request_plan()[value['ordinal']]
    require(canonical(value) == canonical(expected), 'request')
    return expected


def _credential(value):
    require(type(value) is str and 8 <= len(value) <= MAX_CREDENTIAL
        and all(33 <= ord(char) <= 126 for char in value), 'credential')
    return value


def _depth(raw):
    # Check nesting before json.loads; braces in strings do not add depth.
    depth, in_string, escaped = 0, False, False
    for char in raw:
        if in_string:
            if escaped: escaped = False
            elif char == 92: escaped = True
            elif char == 34: in_string = False
        elif char == 34: in_string = True
        elif char in (91, 123):
            depth += 1
            require(depth <= MAX_DEPTH, 'depth')
        elif char in (93, 125):
            depth -= 1
            require(depth >= 0, 'json')
    require(depth == 0 and not in_string, 'json')


def _number_literal(raw, *, integer):
    require(len(raw) <= MAX_NUMBER_CHARS, 'number')
    try:
        value = int(raw) if integer else Decimal(raw)
    except (ValueError, InvalidOperation, OverflowError):
        raise Refused('number') from None
    if not integer:
        require(value.is_finite() and abs(value.as_tuple().exponent) <= 1000, 'number')
    return value


def _echo(value, credential):
    if type(value) is str:
        require(credential not in value, 'credential_echo')
    elif type(value) is dict:
        for key, item in value.items():
            _echo(key, credential); _echo(item, credential)
    elif type(value) is list:
        for item in value: _echo(item, credential)


def _loads(raw, credential):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY, 'response_bound')
    credential = _credential(credential)
    require(credential.encode('ascii') not in raw
        and json.dumps(credential, ensure_ascii=True)[1:-1].encode('ascii') not in raw,
        'credential_echo')
    _depth(raw)
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'json')
            result[key] = value
        return result
    def invalid_constant(_): raise Refused('json')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
            parse_int=lambda item: _number_literal(item, integer=True),
            parse_float=lambda item: _number_literal(item, integer=False),
            parse_constant=invalid_constant)
    except Refused: raise
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise Refused('json') from None
    _echo(value, credential)
    return value


def _day(value):
    require(type(value) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value), 'date')
    try: parsed = date.fromisoformat(value)
    except ValueError: raise Refused('date') from None
    require(parsed.isoformat() == value, 'date')
    return value


def _text(value, maximum=MAX_STRING):
    require(type(value) is str and 0 < len(value) <= maximum
        and all(ord(char) >= 32 and not 127 <= ord(char) < 160
            and not 0xD800 <= ord(char) <= 0xDFFF for char in value), 'schema')


def _identifier(name, value):
    require(type(value) is str, 'identifier')
    patterns = {'figi': r'BBG[A-Z0-9]{9}', 'isin': r'[A-Z]{2}[A-Z0-9]{9}[0-9]',
        'sedol': r'[A-Z0-9]{7}', 'us_code': r'[A-Z0-9*@#]{9}',
        'constituent_ticker': r'[A-Za-z0-9][A-Za-z0-9.\-/:_]{0,63}'}
    require(re.fullmatch(patterns[name], value), 'identifier')


def _numeric(value):
    require(type(value) in (int, Decimal), 'number')
    if type(value) is Decimal:
        require(value.is_finite() and abs(value.as_tuple().exponent) <= 1000, 'number')
    else:
        require(value.bit_length() <= 426, 'number')


def _available(value):
    return value is not None and not (type(value) is str and value == '')


def _base(request):
    return {'schema': SCHEMA + '-response', 'request_ordinal': request['ordinal'],
        'provider': request['provider'], 'provider_ordinal': request['provider_ordinal'],
        'fund': request['fund'], 'requested_effective_date': request['effective_date'],
        'result_count': 0, 'date_count': 0, 'distinct_date_count': 0,
        'earliest_date': None, 'latest_date': None, 'processed_date_count': 0,
        'earliest_processed_date': None, 'latest_processed_date': None,
        'identifier_presence_counts': {name: 0 for name in IDENTIFIERS},
        'numeric_presence_counts': {name: 0 for name in NUMBERS},
        'fmp_year_count': 0, 'fmp_quarter_count': 0, 'next_page_present': False,
        'sample_or_disclosure_metadata_only': True, **FALSE_FLAGS}


def parse_response(request, raw, *, credential):
    """Inspect one HTTP-200 supplied body; retain no body, row or body hash."""
    request = _request(request); value = _loads(raw, credential); summary = _base(request)
    if request['provider'] == 'massive':
        require(type(value) is dict and {'status', 'results'} <= set(value)
            <= {'status', 'results', 'request_id', 'count', 'next_url'}
            and value['status'] == 'OK' and type(value['results']) is list, 'schema')
        rows = value['results']; require(len(rows) <= 1, 'row_cap')
        if 'count' in value and value['count'] is not None:
            require(type(value['count']) is int and value['count'] == len(rows), 'schema')
        if 'request_id' in value and _available(value['request_id']):
            if type(value['request_id']) is int:
                require(value['request_id'] > 0, 'schema')
            else: _text(value['request_id'], 256)
        if 'next_url' in value and _available(value['next_url']):
            _text(value['next_url']); summary['next_page_present'] = True
        for row in rows:
            require(type(row) is dict and {'composite_ticker', 'effective_date'} <= set(row)
                <= MASSIVE_FIELDS and row['composite_ticker'] == request['fund'], 'schema')
            require(_day(row['effective_date']) == request['effective_date'], 'date')
            for name in IDENTIFIERS:
                if name in row and _available(row[name]):
                    _identifier(name, row[name]); summary['identifier_presence_counts'][name] += 1
            for name in NUMBERS:
                if name in row and row[name] is not None:
                    _numeric(row[name]); summary['numeric_presence_counts'][name] += 1
            for name in MASSIVE_TEXT:
                if name in row and _available(row[name]): _text(row[name], 2048)
            if 'constituent_rank' in row and row['constituent_rank'] is not None:
                require(type(row['constituent_rank']) is int and 1 <= row['constituent_rank'] <= 1000000, 'schema')
            if 'processed_date' in row and _available(row['processed_date']):
                day = _day(row['processed_date']); summary['processed_date_count'] = 1
                summary['earliest_processed_date'] = summary['latest_processed_date'] = day
        summary['result_count'] = summary['date_count'] = summary['distinct_date_count'] = len(rows)
        if rows:
            summary['earliest_date'] = summary['latest_date'] = request['effective_date']
    else:
        require(type(value) is list, 'schema'); require(len(value) <= MAX_FMP_ROWS, 'row_cap')
        days = []
        for row in value:
            require(type(row) is dict and {'date', 'year', 'quarter'} <= set(row)
                <= {'date', 'year', 'quarter', 'symbol'}, 'schema')
            if 'symbol' in row: require(type(row['symbol']) is str and row['symbol'] == request['fund'], 'schema')
            days.append(_day(row['date']))
            require(type(row['year']) is int and 1 <= row['year'] <= 9999
                and type(row['quarter']) is int and 1 <= row['quarter'] <= 4, 'schema')
        summary['result_count'] = summary['date_count'] = len(days)
        summary['fmp_year_count'] = summary['fmp_quarter_count'] = len(days)
        summary['distinct_date_count'] = len(set(days))
        if days:
            summary['earliest_date'], summary['latest_date'] = min(days), max(days)
    return validate_summary(request, summary)


def validate_summary(request, summary):
    request = _request(request); base = _base(request)
    require(type(summary) is dict and set(summary) == set(base), 'output')
    varying = {'result_count', 'date_count', 'distinct_date_count', 'earliest_date', 'latest_date',
        'processed_date_count', 'earliest_processed_date', 'latest_processed_date',
        'identifier_presence_counts', 'numeric_presence_counts', 'fmp_year_count', 'fmp_quarter_count',
        'next_page_present'}
    require(canonical({key: value for key, value in summary.items() if key not in varying})
        == canonical({key: value for key, value in base.items() if key not in varying}), 'output')
    maximum = 1 if request['provider'] == 'massive' else MAX_FMP_ROWS
    for name in ('result_count', 'date_count', 'distinct_date_count', 'processed_date_count',
            'fmp_year_count', 'fmp_quarter_count'):
        require(type(summary[name]) is int and 0 <= summary[name] <= maximum, 'output')
    require(summary['date_count'] == summary['result_count']
        and 0 <= summary['distinct_date_count'] <= summary['date_count']
        and (summary['distinct_date_count'] == 0) == (summary['date_count'] == 0)
        and type(summary['next_page_present']) is bool, 'output')
    for prefix, count in (('', summary['date_count']), ('processed_', summary['processed_date_count'])):
        first, last = summary['earliest_' + prefix + 'date'], summary['latest_' + prefix + 'date']
        if count == 0: require(first is None and last is None, 'output')
        else:
            try: _day(first); _day(last)
            except Refused: raise Refused('output') from None
            require(first <= last and (count != 1 or first == last), 'output')
            if not prefix:
                require((first == last) == (summary['distinct_date_count'] == 1), 'output')
    for key, names in (('identifier_presence_counts', IDENTIFIERS), ('numeric_presence_counts', NUMBERS)):
        counts = summary[key]
        require(type(counts) is dict and set(counts) == set(names)
            and all(type(number) is int and 0 <= number <= summary['result_count'] for number in counts.values()), 'output')
    if request['provider'] == 'massive':
        require(summary['date_count'] == summary['distinct_date_count']
            and summary['processed_date_count'] <= summary['result_count']
            and summary['fmp_year_count'] == summary['fmp_quarter_count'] == 0
            and (summary['date_count'] == 0 or summary['earliest_date'] == summary['latest_date']
                == request['effective_date']), 'output')
    else:
        require(summary['processed_date_count'] == 0 and not summary['next_page_present']
            and summary['fmp_year_count'] == summary['fmp_quarter_count'] == summary['result_count']
            and not any(summary['identifier_presence_counts'].values())
            and not any(summary['numeric_presence_counts'].values()), 'output')
    return json.loads(canonical(summary))


def profile_record():
    return {'schema': SCHEMA, 'funds': list(FUNDS), 'massive_dates': list(DATES),
        'endpoints': dict(ENDPOINTS), 'request_plan': list(request_plan()),
        'maximum_dispatches': MAX_REQUESTS, 'maximum_body_bytes': MAX_BODY,
        'maximum_JSON_depth': MAX_DEPTH, 'maximum_fmp_rows': MAX_FMP_ROWS,
        'maximum_numeric_literal_characters': MAX_NUMBER_CHARS, 'maximum_numeric_exponent_magnitude': 1000,
        'credential_echo': 'refuse_raw_or_JSON_escaped_key_in_any_decoded_key_or_string_no_key_retention',
        'provider_stops': 'caller_stops_remaining_same_provider_after_first_credential_transport_non200_or_schema_refusal_other_provider_may_continue',
        'massive': 'exact_fund_and_effective_date_limit1_sample_only_next_url_presence_never_follow_or_persist',
        'massive_optional_fields': 'diagnostic_policy_null_or_empty_identifiers_processed_date_text_and_next_url_are_unavailable_null_numbers_rank_count_are_unavailable_row_is_not_dropped_invalid_nonempty_fields_still_refuse',
        'massive_request_id': 'string_or_positive_exact_nonbool_integer_per_official_spec_and_sample_null_or_empty_unavailable_never_emitted',
        'fmp': 'closed_date_year_quarter_optional_matching_symbol_rows_date_range_counts_only_no_holdings_or_daily_equivalence',
        'year_quarter': 'independently_validated_integer_metadata_no_inferred_report_or_filing_availability_semantics',
        'output': 'closed_count_presence_and_date_summaries_only_no_response_hash_rows_identities_weights_URLs_or_error_text',
        'input': 'supplied_HTTP200_bytes_only_caller_owns_status_headers_host_rights_claim_deadlines_credentials_and_finite_actual_exit',
        'official_sources': ['https://massive.com/docs/rest/partners/etf-global/constituents',
            'https://site.financialmodelingprep.com/developer/docs/stable/disclosures-dates',
            'https://site.financialmodelingprep.com/developer/docs'],
        **FALSE_FLAGS}
