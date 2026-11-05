"""Six fixed injected GETs: current catalog/size and early-price eligibility.

No credential lookup, filesystem, QC, bulk download or strategy capability.
Current metadata and one early-date observation are not PIT identity, paid-tier,
historical completeness, price admission or permission to continue a strategy.
"""
from __future__ import annotations

import csv
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import io
import json
import re
from urllib.parse import urlencode

import requests

from scripts import arv2_r298_sharadar_reference_observation as previous
from scripts import capture_arv2_sharadar_identities as identities
from research.analyst_revisions_v2_qc import newrule_comparison_targets as targets


SCHEMA = 'arv2-r298-sharadar-eligibility-observation-v1'
EVENT_SCHEMA = SCHEMA + '-event'
BASE, META_FIELDS, PRICE_FIELDS = previous.BASE, previous.META_FIELDS, previous.PRICE_FIELDS
REFERENCE_SESSION = '2020-12-31'
ETF_TICKERS = tuple(targets.UNIVERSES)
ROLES = ('stocks_metadata', 'funds_metadata', 'stocks_status', 'funds_status', 'stock_early', 'funds_early')
CAPTURE_NAMES = ('stocks-metadata.csv', 'funds-metadata.csv', 'stocks-status.json',
    'funds-status.json', 'stocks-prior.csv', 'funds-prior.csv')
CAPTURE_BOUNDS = (16 * 1024 * 1024, 16 * 1024 * 1024, 8192, 8192, 65536, 65536)
MAX_ROWS, MAX_FIELD = 100000, 2048
FALSE_FLAGS = {**previous.FALSE_FLAGS, 'paid_tier_proven': False,
    'metadata_universe_completeness_proven': False, 'common_price_package_admitted': False,
    'private_6151_catalog_joined': False, 'bulk_download_performed': False}
FINITE = previous.FINITE | frozenset(('role', 'metadata_table', 'metadata_limit', 'status_json',
    'metadata_route', 'metadata_collision', 'capture', 'probe_date',
    'csv_encoding', 'csv_header', 'csv_row_shape', 'csv_field_shape'))
Refused, require = previous.Refused, previous.require
canonical, sha = previous.canonical, previous.sha
configure_owned_session = previous.configure_owned_session
_session, _identity, _encodings, _budget = previous._session, previous._identity, previous._encodings, previous._budget
source, composer = previous.source, previous.composer


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def _query(role):
    require(type(role) is str and role in ROLES, 'role')
    if role.endswith('_metadata'):
        return '/v1.0/data/tickers', {'table': role.split('_')[0], 'fields': ','.join(META_FIELDS),
            'format': 'csv', 'limit': '100000', 'skip': '0', 'sort': 'ticker.asc'}
    table = 'stocks' if role in ('stocks_status', 'stock_early') else 'funds'
    if role.endswith('_status'):
        return '/v1.0/data/' + table, {'status': 'True'}
    return '/v1.0/data/' + table, {'ticker': 'QCOM' if role == 'stock_early' else ','.join(ETF_TICKERS),
        'from': REFERENCE_SESSION, 'to': REFERENCE_SESSION, 'fields': ','.join(PRICE_FIELDS),
        'format': 'csv', 'limit': '100', 'skip': '0', 'sort': 'ticker.asc'}


def profile_record():
    return {'schema': SCHEMA, 'purpose': 'current_routing_sizes_and_early_period_observation_only',
        'roles': list(ROLES), 'capture_names': list(CAPTURE_NAMES), 'capture_bounds': list(CAPTURE_BOUNDS),
        'queries': [{'role': role, 'endpoint': BASE + _query(role)[0], 'parameters': _query(role)[1]} for role in ROLES],
        'metadata_fields': list(META_FIELDS), 'price_fields': list(PRICE_FIELDS), 'metadata_limit': MAX_ROWS,
        'metadata_refuse_limit_hit': True, 'metadata_from_to_filters': False,
        'metadata_unrelated_missing_fields': 'count_only_not_blanket_refusal',
        'used_routes_require_unique_perma_ticker_and_no_cross_table_alias': True,
        'used_route_intervals_must_cover_prior_before_early_price_dispatch': True,
        'unrelated_malformed_CUSIP_tokens_can_refuse_used_route_collisions': True,
        'early_date': REFERENCE_SESSION, 'fund_probe_count': len(ETF_TICKERS),
        'maximum_application_dispatch_attempts': 6, 'provider_request_count': None,
        'maximum_events': 12, 'caller_joint_deadline_seconds': 600,
        'zero_early_rows_are_observed_absence_not_entitlement_failure': True,
        'TLS_verify': True, 'redirects': False, 'compression': False, 'trust_env': False, 'retries': 0,
        'failed_body_read': False, 'raw_success_bytes_private_only': True,
        'current_vintage_only': True, 'diagnostic_only': True, **FALSE_FLAGS}


def validate_event(value):
    require(type(value) is dict and set(value) == {'schema', 'event', 'role', 'application_attempt',
        'http_status', 'http_status_state'} and value['schema'] == EVENT_SCHEMA
        and type(value['event']) is str and value['event'] in ('intent', 'status')
        and type(value['role']) is str and value['role'] in ROLES
        and type(value['application_attempt']) is int
        and value['application_attempt'] == ROLES.index(value['role']) + 1, 'event')
    status, state = value['http_status'], value['http_status_state']
    require((value['event'] == 'intent' and status is None and state == 'not_observed')
        or (value['event'] == 'status' and ((type(status) is int and 100 <= status <= 599 and state == 'validated')
            or (status is None and state == 'unavailable'))), 'event')
    return dict(value)


def _event(journal, role, event, status=None):
    value = validate_event({'schema': EVENT_SCHEMA, 'event': event, 'role': role,
        'application_attempt': ROLES.index(role) + 1, 'http_status': status,
        'http_status_state': 'not_observed' if event == 'intent' else 'unavailable' if status is None else 'validated'})
    try:
        require(journal(role.replace('_', '-') + '-' + event, value) is None, 'journal')
    except Exception:
        raise Refused('journal') from None


def _rows(raw, fields, maximum, limit):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'csv')
    try:
        text = raw.decode('utf-8-sig', errors='strict')
        require('\x00' not in text, 'csv_encoding')
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        header = tuple(next(reader, ()))
        require(len(header) == len(fields) and set(header) == set(fields), 'csv_header')
        rows = []
        for values in reader:
            require(len(values) == len(fields), 'csv_row_shape')
            require(len(rows) < limit, 'metadata_limit' if limit == MAX_ROWS else 'price_census')
            require(all(value == value.strip() and len(value.encode('utf-8')) <= MAX_FIELD
                and not any(ord(char) < 0x20 or ord(char) == 0x7f for char in value) for value in values), 'csv_field_shape')
            rows.append(dict(zip(header, values, strict=True)))
        require(len(rows) < limit, 'metadata_limit' if limit == MAX_ROWS else 'price_census')
        return rows
    except Refused:
        raise
    except UnicodeError:
        raise Refused('csv_encoding') from None
    except (csv.Error, ValueError, RecursionError):
        raise Refused('csv_row_shape') from None


def _decoded_secret_guard(raw, key, role):
    """Catch CSV quote escaping and JSON Unicode escaping before persistence."""
    try:
        text = raw.decode('utf-8-sig', errors='strict')
        if role.endswith('_status'):
            value = json.loads(text)
            pending = [value]
            while pending:
                item = pending.pop()
                if type(item) is str:
                    require(key not in item, 'credential_echo')
                elif type(item) is dict:
                    pending.extend(item.keys()); pending.extend(item.values())
                elif type(item) is list:
                    pending.extend(item)
        else:
            for row in csv.reader(io.StringIO(text, newline=''), strict=True):
                require(all(key not in cell for cell in row), 'credential_echo')
    except Refused:
        raise
    except UnicodeError:
        raise Refused('status_json' if role.endswith('_status') else 'csv_encoding') from None
    except (csv.Error, ValueError, TypeError, RecursionError):
        raise Refused('status_json' if role.endswith('_status') else 'csv_row_shape') from None


def _date(value, code):
    require(type(value) is str and len(value) == 10, code)
    try: parsed = date.fromisoformat(value)
    except ValueError: raise Refused(code) from None
    require(parsed.isoformat() == value, code)
    return parsed


def _route_quality(row, table):
    """Current row shape, not a security master or historical identity claim."""
    exchanges = identities._STOCK_EXCHANGES if table == 'stocks' else identities._FUND_EXCHANGES
    category = row['category'].casefold()
    categories = identities._COMMON_CATEGORIES if table == 'stocks' else {'etf'}
    mic = composer._SHARADAR_EXCHANGE_TO_MIC.get(row['exchange'].upper())
    if table == 'funds':
        mic = {'NYSEARCA': 'ARCX', 'NYSE ARCA': 'ARCX', 'BATS': 'BATS'}.get(row['exchange'].upper(), mic)
    return (identities._PERMANENT_ID.fullmatch(row['permaticker']) is not None
        and composer._TICKER.fullmatch(row['ticker']) is not None
        and identities._FIGI.fullmatch(row['figi']) is not None
        and bool(composer._sharadar_cusips(row['cusips']))
        and row['exchange'] in exchanges and type(mic) is str and re.fullmatch('[A-Z0-9]{4}', mic)
        and category in categories and row['currency'] == 'USD'
        and row['isdelisted'] in ('Y', 'N'))


def _metadata(raw, table, maximum):
    rows = _rows(raw, META_FIELDS, maximum, MAX_ROWS)
    require(all(row['table'] in (table, 'SEP' if table == 'stocks' else 'SFP') for row in rows), 'metadata_table')
    permas, tickers = Counter(row['permaticker'] for row in rows if row['permaticker']), Counter(row['ticker'] for row in rows if row['ticker'])
    missing = {field: sum(not row[field] for row in rows) for field in ('permaticker', 'figi', 'cusips', 'exchange', 'category', 'currency')}
    malformed_dates = 0
    for row in rows:
        for key in ('firstpricedate', 'lastpricedate', 'lastupdated'):
            if row[key]:
                try: _date(row[key], 'metadata_interval')
                except Refused: malformed_dates += 1
    summary = {'row_count': len(rows), 'duplicate_permaticker_count': sum(count > 1 for count in permas.values()),
        'duplicate_ticker_count': sum(count > 1 for count in tickers.values()), 'missing_field_counts': missing,
        'unsupported_or_incomplete_route_row_count': sum(not _route_quality(row, table) for row in rows),
        'invalid_nonempty_date_field_count': malformed_dates}
    return rows, summary, permas, tickers


def _status(raw, table):
    require(type(raw) is bytes and 0 < len(raw) <= 8192, 'status_json')
    def pairs(items):
        require(len({key for key, _ in items}) == len(items), 'status_json')
        return dict(items)
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(Refused('status_json')))
        require(type(value) is dict and set(value) == {'table', 'name', 'size', 'sizeLabel', 'modified'}
            and value['table'] == table and value['name'] == table + '.csv.zip'
            and type(value['size']) is int and 0 < value['size'] < 2**63
            and type(value['sizeLabel']) is str and 0 < len(value['sizeLabel']) <= 64
            and value['sizeLabel'].isascii() and not any(ord(c) < 0x20 for c in value['sizeLabel'])
            and type(value['modified']) is str and value['modified'].isascii()
            and 0 < len(value['modified']) <= 40, 'status_json')
        timestamp = datetime.fromisoformat(value['modified'].replace('Z', '+00:00'))
        require(timestamp.tzinfo is not None and timestamp.utcoffset() is not None, 'status_json')
    except Refused: raise
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError): raise Refused('status_json') from None
    return {'advertised_bulk_byte_count': value['size'], 'modified_value_sha256': sha(canonical(value['modified']))}


def _routes(stocks, funds):
    selected = []
    for ticker, table, own, other in [('QCOM', 'stocks', stocks, funds)] + [(ticker, 'funds', funds, stocks) for ticker in ETF_TICKERS]:
        candidates = [row for row in own if row['ticker'] == ticker]
        require(len(candidates) == 1, 'metadata_route')
        row = candidates[0]
        require(_route_quality(row, table), 'metadata_identity')
        require(sum(item['permaticker'] == row['permaticker'] for item in own) == 1
            and sum(item['figi'] == row['figi'] for item in own) == 1
            and not any(item['ticker'] == ticker or item['permaticker'] == row['permaticker']
                or (item['figi'] and item['figi'] == row['figi']) for item in other), 'metadata_collision')
        cusips = set(composer._sharadar_cusips(row['cusips']))
        require(not any(item is not row and cusips & set(identities._CUSIP_COLLISION_TOKEN.findall(item['cusips'].upper()))
            for item in own + other), 'metadata_collision')
        first, last = _date(row['firstpricedate'], 'metadata_interval'), _date(row['lastpricedate'], 'metadata_interval')
        require(first <= _date(REFERENCE_SESSION, 'probe_date') <= last, 'metadata_interval')
        _date(row['lastupdated'], 'metadata_interval')
        selected.append(row)
    require(len({row['permaticker'] for row in selected}) == len(selected)
        and len({row['figi'] for row in selected}) == len(selected), 'metadata_collision')
    return selected


def _prices(raw, expected):
    rows = _rows(raw, PRICE_FIELDS, 65536, 100)
    seen = set()
    for row in rows:
        require(row['ticker'] in expected and row['ticker'] not in seen
            and row['date'] == REFERENCE_SESSION, 'price_identity')
        seen.add(row['ticker']); _date(row['lastupdated'], 'price_identity')
        value = row['closeunadj']
        require(len(value) <= 128 and re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', value), 'price_value')
        try: number = Decimal(value)
        except InvalidOperation: raise Refused('price_value') from None
        require(number.is_finite() and number > 0, 'price_value')
    return {'expected_symbol_count': len(expected), 'observed_row_count': len(rows),
        'missing_symbol_count': len(expected) - len(rows), 'positive_finite_row_count': len(rows)}


def _receipt(captures):
    require(type(captures) is dict and set(captures) == set(CAPTURE_NAMES), 'capture')
    for name, maximum in zip(CAPTURE_NAMES, CAPTURE_BOUNDS, strict=True):
        require(type(captures[name]) is bytes and 0 < len(captures[name]) <= maximum, 'capture')
    stocks, stock_summary, stock_permas, stock_tickers = _metadata(captures[CAPTURE_NAMES[0]], 'stocks', CAPTURE_BOUNDS[0])
    funds, fund_summary, fund_permas, fund_tickers = _metadata(captures[CAPTURE_NAMES[1]], 'funds', CAPTURE_BOUNDS[1])
    routes = _routes(stocks, funds)
    return {'schema': SCHEMA, 'status': 'eligibility_observed', 'early_session': REFERENCE_SESSION,
        'capture_pins': {name: {'byte_count': len(captures[name]), 'sha256': sha(captures[name])} for name in CAPTURE_NAMES},
        'metadata': {'stocks': stock_summary, 'funds': fund_summary},
        'cross_table_permaticker_count': len(set(stock_permas) & set(fund_permas)),
        'cross_table_ticker_count': len(set(stock_tickers) & set(fund_tickers)),
        'used_probe_metadata_row_count': len(routes), 'used_probe_route_inventory_sha256': sha(canonical(routes)),
        'bulk_status': {'stocks': _status(captures[CAPTURE_NAMES[2]], 'stocks'), 'funds': _status(captures[CAPTURE_NAMES[3]], 'funds')},
        'early_prices': {'stocks': _prices(captures[CAPTURE_NAMES[4]], ('QCOM',)),
            'funds': _prices(captures[CAPTURE_NAMES[5]], ETF_TICKERS)},
        'application_dispatch_attempts': 6, 'http_statuses': [200] * 6, 'provider_request_count': None,
        'current_vintage_only': True, 'diagnostic_only': True, **FALSE_FLAGS}


def validate_receipt(value):
    fixed = {'schema': SCHEMA, 'status': 'eligibility_observed', 'early_session': REFERENCE_SESSION,
        'used_probe_metadata_row_count': 1 + len(ETF_TICKERS), 'application_dispatch_attempts': 6, 'http_statuses': [200] * 6,
        'provider_request_count': None, 'current_vintage_only': True, 'diagnostic_only': True, **FALSE_FLAGS}
    variable = {'capture_pins', 'metadata', 'cross_table_permaticker_count', 'cross_table_ticker_count',
        'used_probe_route_inventory_sha256', 'bulk_status', 'early_prices'}
    require(type(value) is dict and set(value) == set(fixed) | variable
        and all(type(value[key]) is type(item) and value[key] == item for key, item in fixed.items())
        and all(type(status) is int for status in value['http_statuses']), 'receipt')
    require(type(value['capture_pins']) is dict and set(value['capture_pins']) == set(CAPTURE_NAMES), 'receipt')
    for name, bound in zip(CAPTURE_NAMES, CAPTURE_BOUNDS, strict=True):
        pin = value['capture_pins'][name]
        require(type(pin) is dict and set(pin) == {'byte_count', 'sha256'} and type(pin['byte_count']) is int
            and 0 < pin['byte_count'] <= bound and _hash(pin['sha256']), 'receipt')
    require(_hash(value['used_probe_route_inventory_sha256']) and type(value['metadata']) is dict
        and set(value['metadata']) == {'stocks', 'funds'}, 'receipt')
    for table in ('stocks', 'funds'):
        row = value['metadata'][table]
        fields = {'row_count', 'duplicate_permaticker_count', 'duplicate_ticker_count',
            'unsupported_or_incomplete_route_row_count', 'invalid_nonempty_date_field_count', 'missing_field_counts'}
        require(type(row) is dict and set(row) == fields and type(row['row_count']) is int
            and (1 if table == 'stocks' else len(ETF_TICKERS)) <= row['row_count'] < MAX_ROWS, 'receipt')
        for key in fields - {'row_count', 'missing_field_counts'}:
            require(type(row[key]) is int and 0 <= row[key] <= row['row_count'] * (3 if key == 'invalid_nonempty_date_field_count' else 1), 'receipt')
        require(row['duplicate_permaticker_count'] <= row['row_count'] // 2
            and row['duplicate_ticker_count'] <= row['row_count'] // 2, 'receipt')
        missing = row['missing_field_counts']
        require(type(missing) is dict and set(missing) == {'permaticker', 'figi', 'cusips', 'exchange', 'category', 'currency'}
            and all(type(count) is int and 0 <= count <= row['row_count'] for count in missing.values()), 'receipt')
    for key in ('cross_table_permaticker_count', 'cross_table_ticker_count'):
        require(type(value[key]) is int and 0 <= value[key] <= min(value['metadata'][table]['row_count'] for table in ('stocks', 'funds')), 'receipt')
    require(type(value['bulk_status']) is dict and set(value['bulk_status']) == {'stocks', 'funds'}
        and type(value['early_prices']) is dict and set(value['early_prices']) == {'stocks', 'funds'}, 'receipt')
    for table, count in (('stocks', 1), ('funds', len(ETF_TICKERS))):
        status, prices = value['bulk_status'][table], value['early_prices'][table]
        require(type(status) is dict and set(status) == {'advertised_bulk_byte_count', 'modified_value_sha256'}
            and type(status['advertised_bulk_byte_count']) is int and 0 < status['advertised_bulk_byte_count'] < 2**63
            and _hash(status['modified_value_sha256']), 'receipt')
        require(type(prices) is dict and set(prices) == {'expected_symbol_count', 'observed_row_count',
            'missing_symbol_count', 'positive_finite_row_count'} and type(prices['expected_symbol_count']) is int
            and prices['expected_symbol_count'] == count and type(prices['observed_row_count']) is int
            and 0 <= prices['observed_row_count'] <= count
            and type(prices['missing_symbol_count']) is int and prices['missing_symbol_count'] == count - prices['observed_row_count']
            and type(prices['positive_finite_row_count']) is int and prices['positive_finite_row_count'] == prices['observed_row_count'], 'receipt')
    require(len(canonical(value)) <= 32768, 'receipt')
    return json.loads(canonical(value))


def _hash(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate_capture(receipt, captures):
    checked = validate_receipt(receipt)
    expected = _receipt(captures)
    require(canonical(checked) == canonical(expected), 'receipt')
    return validate_receipt(expected)


def capture_pins(receipt): return validate_receipt(receipt)['capture_pins']


def validate_events(receipt, events):
    validate_receipt(receipt)
    require(type(events) is list and len(events) == 12, 'event')
    checked = [validate_event(value) for value in events]
    for value, (role, event) in zip(checked, ((role, event) for role in ROLES for event in ('intent', 'status')), strict=True):
        require(value['role'] == role and value['event'] == event
            and value['http_status'] == (None if event == 'intent' else 200), 'event')
    return checked


class PrivateCapture:
    __slots__ = ('_captures',)
    def __init__(self, captures): self._captures = dict(captures)
    def bytes_by_name(self): return dict(self._captures)
    def __repr__(self): return '<PrivateCapture redacted; no serialization>'
    def __reduce_ex__(self, protocol): raise TypeError('private capture must not be serialized')


def observe(*, session, api_key, journal, deadline):
    require(callable(journal), 'journal')
    try: key = source._validated_api_key(api_key, synthetic=False)
    except Exception: raise Refused('credential') from None
    _session(session); _budget(deadline)
    captures = {}
    for role, name in zip(ROLES, CAPTURE_NAMES, strict=True):
        captures[name] = _fetch(session, key, role, journal, deadline)
        _decoded_secret_guard(captures[name], key, role)
        if role == 'stocks_metadata':
            _metadata(captures[name], 'stocks', CAPTURE_BOUNDS[0])
        elif role == 'funds_metadata':
            stocks = _metadata(captures[CAPTURE_NAMES[0]], 'stocks', CAPTURE_BOUNDS[0])[0]
            funds = _metadata(captures[name], 'funds', CAPTURE_BOUNDS[1])[0]
            _routes(stocks, funds)
        elif role.endswith('_status'):
            _status(captures[name], role.split('_')[0])
        else:
            _prices(captures[name], ('QCOM',) if role == 'stock_early' else ETF_TICKERS)
    result = validate_receipt(_receipt(captures))
    _session(session); _budget(deadline)
    return result, PrivateCapture(captures)


def _fetch(session, key, role, journal, deadline):
    path, query = _query(role)
    endpoint = BASE + path
    maximum = CAPTURE_BOUNDS[ROLES.index(role)]
    params = {**query, 'api_key': key}
    _session(session); _budget(deadline)
    try:
        intent = session.prepare_request(requests.Request('GET', endpoint, params=params,
            headers={'Accept-Encoding': 'identity'}))
        _identity(intent, endpoint, params)
    except Refused:
        raise
    except Exception:
        raise Refused('prepared_identity') from None
    _event(journal, role, 'intent')
    response, complete = None, False
    try:
        try:
            # This is application dispatch-attempt accounting, not a physical
            # provider-request counter. An exception does not prove no contact.
            response = session.get(endpoint, params=params, timeout=_budget(deadline),
                allow_redirects=False, stream=True, verify=True, headers={'Accept-Encoding': 'identity'})
        except Exception:
            _event(journal, role, 'status')
            raise Refused('request_failed') from None
        try:
            numeric = response.status_code
        except Exception:
            numeric = None
        status = numeric if type(numeric) is int and 100 <= numeric <= 599 else None
        _event(journal, role, 'status', status)
        require(status is not None, 'http_status_unavailable')
        require(status == 200, 'http_status')  # NEVER inspect a failed body.
        try:
            require(type(response) is requests.Response and response.history == [], 'response_identity')
            _identity(response.request, endpoint, params)
            parts, query_pairs = source._parse_url(response.url, provider=True)
            expected, expected_pairs = source._parse_url(endpoint + '?' + urlencode(params), provider=True)
            require(parts.scheme == expected.scheme and parts.netloc == expected.netloc
                and parts.path == expected.path and query_pairs == expected_pairs, 'response_identity')
            headers = response.headers
            require(len(headers) <= 64, 'response_headers')
            for name, value in headers.items():
                require(type(name) is str and type(value) is str and len(name) <= 128 and len(value) <= 8192,
                    'response_headers')
                require(not any(secret in (name + ':' + value).encode('utf-8') for secret in _encodings(key)), 'credential_echo')
            encoding = headers.get('Content-Encoding')
            require(encoding is None or (type(encoding) is str and encoding.casefold() == 'identity'), 'response_encoding')
            length = headers.get('Content-Length')
            require(length is None or (type(length) is str and length.isascii() and length.isdecimal()
                and 0 < len(length) <= 10 and 0 < int(length) <= maximum), 'response_bound')
            chunks, count = [], 0
            for chunk in response.iter_content(chunk_size=8192):
                _budget(deadline)
                require(type(chunk) is bytes, 'response_stream')
                count += len(chunk)
                require(count <= maximum, 'response_bound')
                chunks.append(chunk)
            payload = b''.join(chunks)
            require(payload and (length is None or len(payload) == int(length)), 'response_bound')
            require(not any(secret in payload for secret in _encodings(key)), 'credential_echo')
        except Refused:
            raise
        except Exception:
            raise Refused('response_identity') from None
        _session(session); _budget(deadline)
        complete = True
        return payload
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                if complete: raise Refused('response_close') from None
