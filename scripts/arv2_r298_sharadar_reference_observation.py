"""Two bounded injected Sharadar GETs for current-vintage series existence.

No secret lookup, filesystem, operational entry point, retry, QC or strategy
capability is present. The native caller owns private authentication, claim,
credentials, persistence, deadline and actual-exit evidence. A vendor row is
not an admissible strategy price or historical ticker/security-master proof.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, quote_plus, urlencode

import requests
from requests.adapters import HTTPAdapter

from scripts import capture_arv2_sharadar as source
from scripts import build_arv2_preopen_input as composer
from scripts import arv2_r298_sharadar_reference_binding as binding


SCHEMA = 'arv2-r298-sharadar-reference-observation-v1'
EVENT_SCHEMA = SCHEMA + '-event'
BASE = 'https://api.sharadar.com'
META_FIELDS = ('table', 'ticker', 'permaticker', 'exchange', 'isdelisted', 'category',
    'cusips', 'figi', 'currency', 'firstpricedate', 'lastpricedate', 'lastupdated')
PRICE_FIELDS = ('ticker', 'date', 'closeunadj', 'lastupdated')
MAX_META, MAX_PRICE, MAX_FIELD = 64 * 1024, 8 * 1024, 2048
TIMEOUT = 30
FALSE_FLAGS = {'strategy_price_admitted': False, 'strategy_nav_admitted': False,
    'price_used': False, 'strategy_continued': False, 'formal_source_admitted': False,
    'point_in_time_proven': False, 'permanent_identity_authenticated': False,
    'historical_exchange_ticker_authenticated': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False, 'credential_persisted': False, 'raw_rows_disclosed': False,
    'raw_route_disclosed': False, 'raw_price_disclosed': False, 'qc_contact': False,
    'orders_submitted': False, 'physical_request_count_measured': False}
FINITE = frozenset(('packet', 'credential', 'session', 'deadline', 'journal', 'event',
    'prepared_identity', 'request_failed', 'http_status', 'http_status_unavailable',
    'response_identity', 'response_headers', 'response_encoding', 'response_bound',
    'response_stream', 'response_close', 'credential_echo', 'csv', 'metadata_census',
    'metadata_identity', 'metadata_currency', 'metadata_interval', 'price_census',
    'price_identity', 'price_value', 'changed', 'receipt'))


class Refused(ValueError):
    pass


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def sha(raw): return hashlib.sha256(raw).hexdigest()


def profile_record():
    return {'schema': SCHEMA, 'reference_session': binding.REFERENCE_SESSION,
        'metadata_endpoint': BASE + '/v1.0/data/tickers', 'metadata_fields': list(META_FIELDS),
        'metadata_query': {'table': 'stocks', 'permaticker': 'authenticated_private_packet',
            'format': 'csv', 'limit': '2', 'skip': '0', 'sort': 'ticker.asc'},
        'metadata_from_or_to_filter': False, 'metadata_table_aliases': ['stocks', 'SEP'],
        'price_endpoint': BASE + '/v1.0/data/stocks', 'price_fields': list(PRICE_FIELDS),
        'price_ticker': 'validated_current_price_table_metadata_row_not_original_SF1_ticker',
        'price_query': {'from': binding.REFERENCE_SESSION, 'to': binding.REFERENCE_SESSION,
            'format': 'csv', 'limit': '2', 'skip': '0', 'sort': 'date.asc'},
        'metadata_maximum_bytes': MAX_META, 'price_maximum_bytes': MAX_PRICE,
        'maximum_application_dispatch_attempts': 2, 'provider_request_count': None,
        'application_intent_can_precede_failed_journal_or_presend_budget': True,
        'application_attempt_is_not_physical_wire_count': True,
        'tls_verify': True, 'redirects': False, 'compression': False,
        'trust_environment': False, 'retries': 0, 'response_failed_body_read': False,
        'failed_payloads_retained': False, 'successful_payloads_returned_only_after_validation': True,
        'journal_events_maximum': 4, 'journal_before_status_refusal': True,
        'zero_or_one_price_rows': True, 'positive_finite_closeunadj_only': True,
        'current_vintage_only': True, 'diagnostic_only': True, **FALSE_FLAGS}


def _packet(packet):
    try:
        return binding.validate_packet(packet)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise Refused('packet') from None


def _budget(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline), 'deadline')
    remaining = deadline - time.monotonic()
    require(remaining > 0, 'deadline')
    return min(TIMEOUT, remaining)


def configure_owned_session(session):
    """Configure only a caller-created exact Session; never acquire a key."""
    require(type(session) is requests.Session and not any(callable(value) for value in session.__dict__.values()), 'session')
    session.trust_env, session.verify, session.auth, session.cert = False, True, None, None
    session.proxies.clear(); session.params.clear(); session.cookies.clear()
    session.headers.clear(); session.hooks.clear(); session.adapters.clear()
    session.mount('https://', HTTPAdapter(max_retries=0))
    _session(session)
    return session


def _session(session):
    require(type(session) is requests.Session and session.trust_env is False and session.verify is True
        and session.auth is None and session.cert is None and not session.proxies
        and not session.params and not session.cookies and not session.headers and not session.hooks
        and not any(callable(value) for value in session.__dict__.values())
        and set(session.adapters) == {'https://'}, 'session')
    adapter = session.adapters['https://']
    require(type(adapter) is HTTPAdapter and type(adapter.max_retries.total) is int
        and adapter.max_retries.total == 0
        and not any(callable(value) for value in adapter.__dict__.values()), 'session')


def validate_event(value):
    fields = {'schema', 'event', 'role', 'application_attempt', 'http_status', 'http_status_state'}
    require(type(value) is dict and set(value) == fields and value['schema'] == EVENT_SCHEMA
        and type(value['event']) is str and value['event'] in ('intent', 'status')
        and type(value['role']) is str and value['role'] in ('metadata', 'price')
        and type(value['application_attempt']) is int and value['application_attempt'] ==
            (1 if value['role'] == 'metadata' else 2), 'event')
    status, state = value['http_status'], value['http_status_state']
    if value['event'] == 'intent':
        require(status is None and state == 'not_observed', 'event')
    else:
        require((type(status) is int and 100 <= status <= 599 and state == 'validated')
            or (status is None and state == 'unavailable'), 'event')
    return dict(value)


def _event(journal, role, event, status=None):
    row = validate_event({'schema': EVENT_SCHEMA, 'event': event, 'role': role,
        'application_attempt': 1 if role == 'metadata' else 2, 'http_status': status,
        'http_status_state': 'not_observed' if event == 'intent' else 'unavailable' if status is None else 'validated'})
    try:
        journal(role + '-' + event, row)
    except Exception:
        raise Refused('journal') from None


def _identity(prepared, endpoint, params):
    try:
        expected_parts, expected_query = source._parse_url(endpoint + '?' + urlencode(params), provider=True)
        parts, query = source._parse_url(prepared.url, provider=True)
        require(type(prepared) is requests.PreparedRequest and prepared.method == 'GET'
            and type(prepared.method) is str and prepared.body is None
            and parts.scheme == expected_parts.scheme and parts.netloc == expected_parts.netloc
            and parts.path == expected_parts.path and query == expected_query
            and dict(prepared.headers) == {'Accept-Encoding': 'identity'}, 'prepared_identity')
    except Refused:
        raise
    except Exception:
        raise Refused('prepared_identity') from None


def _encodings(key):
    variants = {key.encode('ascii'), quote(key, safe='').encode('ascii'),
        quote_plus(key, safe='').encode('ascii'), json.dumps(key, ensure_ascii=True)[1:-1].encode('ascii')}
    variants.update(re.sub(rb'%[0-9A-Fa-f]{2}', lambda match: match.group().lower(), raw)
        for raw in tuple(variants))
    return tuple(raw for raw in variants if raw)


def _fetch(session, key, role, query, journal, deadline):
    endpoint = BASE + ('/v1.0/data/tickers' if role == 'metadata' else '/v1.0/data/stocks')
    maximum = MAX_META if role == 'metadata' else MAX_PRICE
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


def _rows(payload, fields, maximum):
    require(type(payload) is bytes and 0 < len(payload) <= maximum, 'csv')
    try:
        text = payload.decode('utf-8-sig', errors='strict')
        require('\x00' not in text, 'csv')
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        header = tuple(next(reader, ()))
        require(len(header) == len(fields) and set(header) == set(fields), 'csv')
        rows = []
        for values in reader:
            require(len(rows) < 2 and len(values) == len(fields)
                and all(type(value) is str and len(value) <= MAX_FIELD
                    and value == value.strip() and not any(ord(char) < 0x20 or ord(char) == 0x7f for char in value)
                    for value in values), 'csv')
            rows.append(dict(zip(header, values, strict=True)))
    except Refused:
        raise
    except (csv.Error, UnicodeError, ValueError, RecursionError):
        raise Refused('csv') from None
    return rows


def _date(value, code):
    require(type(value) is str and len(value) == 10, code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise Refused(code) from None
    require(parsed.isoformat() == value, code)
    return parsed


def _metadata(payload, packet):
    rows = _rows(payload, META_FIELDS, MAX_META)
    require(len(rows) == 1, 'metadata_census')
    row = rows[0]
    try:
        cusips = composer._sharadar_cusips(row['cusips'])
        mic = composer._SHARADAR_EXCHANGE_TO_MIC.get(row['exchange'].upper())
        common = row['category'].casefold() in composer._ALLOWED_COMMON_STOCK_CATEGORIES
    except Exception:
        raise Refused('metadata_identity') from None
    require(row['table'] in ('stocks', 'SEP') and row['permaticker'] == packet['permaticker']
        and row['figi'] == packet['expected_composite_figi'] and mic == packet['exchange_mic']
        and common and tuple(cusips) == tuple(packet['original_cusips'])
        and composer._TICKER.fullmatch(row['ticker']) is not None
        and row['isdelisted'] in ('Y', 'N'), 'metadata_identity')
    require(row['currency'] == 'USD', 'metadata_currency')
    first, last = _date(row['firstpricedate'], 'metadata_interval'), _date(row['lastpricedate'], 'metadata_interval')
    reference = _date(binding.REFERENCE_SESSION, 'metadata_interval')
    require(first <= reference <= last, 'metadata_interval')
    _date(row['lastupdated'], 'metadata_interval')
    return row


def _price(payload, ticker):
    rows = _rows(payload, PRICE_FIELDS, MAX_PRICE)
    require(len(rows) <= 1, 'price_census')
    if not rows: return 0
    row = rows[0]
    require(row['ticker'] == ticker and row['date'] == binding.REFERENCE_SESSION, 'price_identity')
    _date(row['lastupdated'], 'price_identity')
    raw = row['closeunadj']
    require(type(raw) is str and len(raw) <= 128
        and re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', raw), 'price_value')
    try:
        parsed = Decimal(raw)
    except InvalidOperation:
        raise Refused('price_value') from None
    require(parsed.is_finite() and parsed > 0, 'price_value')
    return 1


class PrivateCapture:
    __slots__ = ('_metadata', '_price')
    def __init__(self, metadata, price): self._metadata, self._price = metadata, price
    def bytes_pair(self): return self._metadata, self._price
    def __repr__(self): return '<PrivateCapture redacted; caller-owned persistence only>'
    def __reduce_ex__(self, protocol): raise TypeError('private capture must not be serialized')


def _receipt(packet, metadata, raw_meta, raw_price):
    count = _price(raw_price, metadata['ticker'])
    return {'schema': SCHEMA, 'status': 'vendor_row_observed' if count else 'vendor_row_absent',
        'reference_session': binding.REFERENCE_SESSION, 'private_packet_sha256': binding.packet_digest(packet),
        'identity_sha256': binding.IDENTITY_SHA256, 'source_row_sha256': binding.SOURCE_ROW_SHA256,
        'whole_binding_row_sha256': binding.BINDING_ROW_SHA256, 'context_sha256': binding.CONTEXT_SHA256,
        'metadata_csv_sha256': sha(raw_meta), 'metadata_csv_byte_count': len(raw_meta),
        'price_csv_sha256': sha(raw_price), 'price_csv_byte_count': len(raw_price),
        'metadata_row_count': 1, 'price_row_count': count,
        'metadata_identity_matched': True, 'currency_usd': True, 'metadata_interval_covers_reference': True,
        'current_vendor_series_locator_sha256': sha(canonical({'schema': SCHEMA + '-locator', 'ticker': metadata['ticker']})),
        'application_dispatch_attempts': 2, 'http_statuses': [200, 200], 'provider_request_count': None,
        'unadjusted_close_positive_finite': bool(count), 'current_vintage_only': True,
        'diagnostic_only': True, **FALSE_FLAGS}


def validate_receipt(value):
    fixed = {'schema': SCHEMA, 'reference_session': binding.REFERENCE_SESSION,
        'identity_sha256': binding.IDENTITY_SHA256, 'source_row_sha256': binding.SOURCE_ROW_SHA256,
        'whole_binding_row_sha256': binding.BINDING_ROW_SHA256, 'context_sha256': binding.CONTEXT_SHA256,
        'metadata_row_count': 1, 'metadata_identity_matched': True, 'currency_usd': True,
        'metadata_interval_covers_reference': True, 'application_dispatch_attempts': 2,
        'http_statuses': [200, 200], 'provider_request_count': None,
        'current_vintage_only': True, 'diagnostic_only': True, **FALSE_FLAGS}
    variable = {'status', 'private_packet_sha256', 'metadata_csv_sha256', 'metadata_csv_byte_count',
        'price_csv_sha256', 'price_csv_byte_count', 'price_row_count',
        'current_vendor_series_locator_sha256', 'unadjusted_close_positive_finite'}
    require(type(value) is dict and all(type(key) is str for key in value)
        and set(value) == set(fixed) | variable, 'receipt')
    require(all(type(value[key]) is type(item) and value[key] == item for key, item in fixed.items()), 'receipt')
    require(type(value['http_statuses']) is list and all(type(item) is int for item in value['http_statuses']), 'receipt')
    for key in ('private_packet_sha256', 'metadata_csv_sha256', 'price_csv_sha256', 'current_vendor_series_locator_sha256'):
        require(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key]), 'receipt')
    require(type(value['metadata_csv_byte_count']) is int and 0 < value['metadata_csv_byte_count'] <= MAX_META
        and type(value['price_csv_byte_count']) is int and 0 < value['price_csv_byte_count'] <= MAX_PRICE
        and type(value['price_row_count']) is int and value['price_row_count'] in (0, 1)
        and type(value['status']) is str and value['status'] ==
            ('vendor_row_observed' if value['price_row_count'] else 'vendor_row_absent')
        and value['unadjusted_close_positive_finite'] is bool(value['price_row_count']), 'receipt')
    return json.loads(canonical(value))


def capture_pins(receipt):
    value = validate_receipt(receipt)
    return {'metadata.csv': {'byte_count': value['metadata_csv_byte_count'], 'sha256': value['metadata_csv_sha256']},
        'price.csv': {'byte_count': value['price_csv_byte_count'], 'sha256': value['price_csv_sha256']}}


def validate_events(receipt, events):
    validate_receipt(receipt)
    require(type(events) is list and len(events) == 4, 'event')
    checked = [validate_event(value) for value in events]
    for value, (role, event) in zip(checked, (('metadata', 'intent'), ('metadata', 'status'),
            ('price', 'intent'), ('price', 'status')), strict=True):
        require(value['role'] == role and value['event'] == event
            and value['http_status'] == (None if event == 'intent' else 200), 'event')
    return [dict(value) for value in checked]


def validate_capture(packet, receipt, metadata_csv, price_csv):
    """Pure byte/identity validation, not authentication of physical requests."""
    checked = _packet(packet)
    supplied = validate_receipt(receipt)
    metadata = _metadata(metadata_csv, checked)
    expected = _receipt(checked, metadata, metadata_csv, price_csv)
    require(canonical(supplied) == canonical(expected), 'receipt')
    return validate_receipt(expected)


def observe(packet, *, session, api_key, journal, deadline):
    checked = _packet(packet)
    packet_pin = binding.packet_digest(checked)
    require(callable(journal), 'journal')
    try:
        key = source._validated_api_key(api_key, synthetic=False)
    except Exception:
        raise Refused('credential') from None
    _session(session); _budget(deadline)
    metadata_query = {'table': 'stocks', 'permaticker': checked['permaticker'],
        'fields': ','.join(META_FIELDS), 'format': 'csv', 'limit': '2', 'skip': '0', 'sort': 'ticker.asc'}
    raw_meta = _fetch(session, key, 'metadata', metadata_query, journal, deadline)
    metadata = _metadata(raw_meta, checked)
    require(binding.packet_digest(_packet(packet)) == packet_pin, 'changed')
    price_query = {'ticker': metadata['ticker'], 'from': binding.REFERENCE_SESSION, 'to': binding.REFERENCE_SESSION,
        'fields': ','.join(PRICE_FIELDS), 'format': 'csv', 'limit': '2', 'skip': '0', 'sort': 'date.asc'}
    raw_price = _fetch(session, key, 'price', price_query, journal, deadline)
    _price(raw_price, metadata['ticker'])
    require(binding.packet_digest(_packet(packet)) == packet_pin, 'changed')
    result = _receipt(checked, metadata, raw_meta, raw_price)
    result = validate_capture(checked, result, raw_meta, raw_price)
    _session(session); _budget(deadline)
    return result, PrivateCapture(raw_meta, raw_price)
