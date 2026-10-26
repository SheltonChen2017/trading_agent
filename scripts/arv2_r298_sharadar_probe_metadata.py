"""Two fixed metadata-only GETs explaining failed public-probe predicates.

A successfully authenticated observation can contain false/unknown predicates.
It is never metadata, identity, entitlement, price, NAV or strategy admission.
No filesystem, credential lookup, provider fallback or operational entry point.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlencode

import requests

from scripts import arv2_r298_sharadar_eligibility_observation as previous


SCHEMA = 'arv2-r298-sharadar-probe-metadata-v1'
EVENT_SCHEMA = SCHEMA + '-event'
ROLES = ('stocks_metadata', 'funds_metadata')
CAPTURE_NAMES = ('stocks-probe.csv', 'funds-probe.csv')
CAPTURE_BOUNDS = (65536, 65536)
BASE, META_FIELDS = previous.BASE, previous.META_FIELDS
ETF_TICKERS, REFERENCE_SESSION = previous.ETF_TICKERS, previous.REFERENCE_SESSION
PROBES = (('stocks', 'QCOM'),) + tuple(('funds', ticker) for ticker in ETF_TICKERS)
PREDICATES = ('table_expected', 'permaticker_format', 'figi_format', 'cusip_field_nonempty',
    'cusip_vocabulary_valid', 'mic_allowed', 'category_expected', 'currency_usd', 'isdelisted_shape',
    'first_price_date_canonical', 'last_price_date_canonical', 'lastupdated_canonical',
    'reference_interval_ordered', 'reference_interval_contains', 'same_table_permaticker_collision',
    'same_table_figi_collision', 'same_table_cusip_collision', 'cross_table_permaticker_collision',
    'cross_table_ticker_collision', 'cross_table_figi_collision', 'cross_table_cusip_collision')
COLLISIONS = frozenset(name for name in PREDICATES if name.endswith('_collision'))
FALSE_FLAGS = {**previous.FALSE_FLAGS, 'probe_metadata_admitted': False,
    's_failure_cause_authenticated': False, 'identity_predicates_required_true_for_observation': False}
FINITE = previous.FINITE | frozenset(('predicate_receipt', 'probe_shape'))
Refused, require, canonical, sha = previous.Refused, previous.require, previous.canonical, previous.sha
source, composer, identities = previous.source, previous.composer, previous.identities
configure_owned_session = previous.configure_owned_session
_session, _identity, _encodings, _budget = previous._session, previous._identity, previous._encodings, previous._budget


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def _query(role):
    require(type(role) is str and role in ROLES, 'role')
    return '/v1.0/data/tickers', {'table': role.split('_')[0],
        'ticker': 'QCOM' if role == 'stocks_metadata' else ','.join(ETF_TICKERS),
        'fields': ','.join(META_FIELDS), 'format': 'csv', 'limit': '100', 'skip': '0', 'sort': 'ticker.asc'}


def profile_record():
    return {'schema': SCHEMA, 'purpose': 'public_probe_field_predicate_matrix_not_identity_admission',
        'roles': list(ROLES), 'capture_names': list(CAPTURE_NAMES), 'capture_bounds': list(CAPTURE_BOUNDS),
        'queries': [{'role': role, 'endpoint': BASE + _query(role)[0], 'parameters': _query(role)[1]} for role in ROLES],
        'fields': list(META_FIELDS), 'fixed_probe_count': len(PROBES), 'probe_indices_only_in_receipt': True,
        'field_value_disclosure': 'UTF8_byte_count_canonical_hash_and_closed_state_only',
        'predicates': list(PREDICATES), 'collision_predicates_true_means_ambiguity': True,
        'collision_scope': 'only_the_two_returned_filtered_metadata_subsets_not_full_catalog',
        'field_hashes_are_canonical_string_hashes_not_raw_UTF8_hashes': True,
        'full_row_hash_not_reconstitutable_from_field_hashes': True,
        'metadata_limit': 100, 'metadata_limit_hit_refused': True,
        'maximum_application_dispatch_attempts': 2, 'provider_request_count': None,
        'maximum_events': 4, 'caller_joint_deadline_seconds': 300,
        'TLS_verify': True, 'redirects': False, 'compression': False, 'trust_env': False, 'retries': 0,
        'failed_body_read': False, 'decoded_secret_guard': True,
        'unknown_or_false_identity_is_valid_diagnostic_observation': True,
        'raw_rows_and_values_private_only': True, 'diagnostic_only': True, **FALSE_FLAGS}


def validate_event(value):
    require(type(value) is dict and set(value) == {'schema', 'event', 'role', 'application_attempt',
        'http_status', 'http_status_state'} and value['schema'] == EVENT_SCHEMA
        and type(value['event']) is str and value['event'] in ('intent', 'status')
        and type(value['role']) is str and value['role'] in ROLES
        and type(value['application_attempt']) is int and value['application_attempt'] == ROLES.index(value['role']) + 1, 'event')
    status, state = value['http_status'], value['http_status_state']
    require((value['event'] == 'intent' and status is None and state == 'not_observed')
        or (value['event'] == 'status' and ((type(status) is int and 100 <= status <= 599 and state == 'validated')
            or (status is None and state == 'unavailable'))), 'event')
    return dict(value)


def _event(journal, role, event, status=None):
    value = validate_event({'schema': EVENT_SCHEMA, 'event': event, 'role': role,
        'application_attempt': ROLES.index(role) + 1, 'http_status': status,
        'http_status_state': 'not_observed' if event == 'intent' else 'unavailable' if status is None else 'validated'})
    try: require(journal(role.replace('_', '-') + '-' + event, value) is None, 'journal')
    except Exception: raise Refused('journal') from None


def _rows(raw):
    try: return previous._rows(raw, META_FIELDS, 65536, 100)
    except Refused as error:
        if previous.finite(error) == 'price_census': raise Refused('metadata_limit') from None
        raise


def _canonical_date(value):
    try: previous._date(value, 'metadata_interval'); return True
    except Refused: return False


def _cusip_tokens(value): return set(identities._CUSIP_COLLISION_TOKEN.findall(value.upper()))


def _predicates(row, table, own, other):
    perma, figi, ticker = row['permaticker'], row['figi'], row['ticker']
    cusips = set(composer._sharadar_cusips(row['cusips']))
    exchanges = identities._STOCK_EXCHANGES if table == 'stocks' else identities._FUND_EXCHANGES
    mic = composer._SHARADAR_EXCHANGE_TO_MIC.get(row['exchange'].upper())
    if table == 'funds': mic = {'NYSEARCA': 'ARCX', 'NYSE ARCA': 'ARCX', 'BATS': 'BATS'}.get(row['exchange'].upper(), mic)
    first, last, updated = (_canonical_date(row[name]) for name in ('firstpricedate', 'lastpricedate', 'lastupdated'))
    return {'table_expected': row['table'] in (table, 'SEP' if table == 'stocks' else 'SFP'),
        'permaticker_format': identities._PERMANENT_ID.fullmatch(perma) is not None,
        'figi_format': identities._FIGI.fullmatch(figi) is not None,
        'cusip_field_nonempty': bool(row['cusips']), 'cusip_vocabulary_valid': bool(cusips),
        'mic_allowed': row['exchange'] in exchanges and type(mic) is str and re.fullmatch('[A-Z0-9]{4}', mic) is not None,
        'category_expected': row['category'].casefold() in (identities._COMMON_CATEGORIES if table == 'stocks' else {'etf'}),
        'currency_usd': row['currency'] == 'USD', 'isdelisted_shape': row['isdelisted'] in ('Y', 'N'),
        'first_price_date_canonical': first, 'last_price_date_canonical': last, 'lastupdated_canonical': updated,
        'reference_interval_ordered': row['firstpricedate'] <= row['lastpricedate'] if first and last else None,
        'reference_interval_contains': row['firstpricedate'] <= REFERENCE_SESSION <= row['lastpricedate'] if first and last else None,
        'same_table_permaticker_collision': any(item is not row and item['permaticker'] == perma for item in own) if perma else None,
        'same_table_figi_collision': any(item is not row and item['figi'] == figi for item in own) if figi else None,
        'same_table_cusip_collision': any(item is not row and cusips & _cusip_tokens(item['cusips']) for item in own) if cusips else None,
        'cross_table_permaticker_collision': any(item['permaticker'] == perma for item in other) if perma else None,
        'cross_table_ticker_collision': any(item['ticker'] == ticker for item in other),
        'cross_table_figi_collision': any(item['figi'] == figi for item in other) if figi else None,
        'cross_table_cusip_collision': any(cusips & _cusip_tokens(item['cusips']) for item in other) if cusips else None}


def _probe(index, table, ticker, own, other):
    candidates = [row for row in own if row['ticker'] == ticker]
    result = {'probe_index': index, 'candidate_count': len(candidates), 'candidate_ambiguous': len(candidates) > 1,
        'candidate_rows_sha256': sha(canonical(candidates)), 'fields': None, 'predicates': None,
        'failed_identity_predicate_count': None, 'unknown_predicate_count': None, 'collision_predicate_count': None}
    if len(candidates) == 1:
        row = candidates[0]
        result['fields'] = {name: {'type': 'str', 'state': 'empty' if not row[name] else 'nonempty',
            'utf8_byte_count': len(row[name].encode('utf-8')), 'value_sha256': sha(canonical(row[name]))} for name in META_FIELDS}
        predicates = _predicates(row, table, own, other)
        result['predicates'] = predicates
        result['failed_identity_predicate_count'] = sum(value is False for name, value in predicates.items() if name not in COLLISIONS)
        result['unknown_predicate_count'] = sum(value is None for value in predicates.values())
        result['collision_predicate_count'] = sum(predicates[name] is True for name in COLLISIONS)
    return result


def _receipt(captures):
    require(type(captures) is dict and set(captures) == set(CAPTURE_NAMES), 'capture')
    for name in CAPTURE_NAMES: require(type(captures[name]) is bytes and 0 < len(captures[name]) <= 65536, 'capture')
    stocks, funds = (_rows(captures[name]) for name in CAPTURE_NAMES)
    return {'schema': SCHEMA, 'status': 'probe_predicates_observed', 'reference_session': REFERENCE_SESSION,
        'capture_pins': {name: {'byte_count': len(captures[name]), 'sha256': sha(captures[name])} for name in CAPTURE_NAMES},
        'metadata_row_counts': {'stocks': len(stocks), 'funds': len(funds)},
        'unexpected_ticker_row_counts': {'stocks': sum(row['ticker'] != 'QCOM' for row in stocks),
            'funds': sum(row['ticker'] not in ETF_TICKERS for row in funds)},
        'probes': [_probe(index, table, ticker, stocks if table == 'stocks' else funds,
            funds if table == 'stocks' else stocks) for index, (table, ticker) in enumerate(PROBES)],
        'application_dispatch_attempts': 2, 'http_statuses': [200, 200], 'provider_request_count': None,
        'current_vintage_only': True, 'diagnostic_only': True, **FALSE_FLAGS}


def _hash(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate_receipt(value):
    fixed = {'schema': SCHEMA, 'status': 'probe_predicates_observed', 'reference_session': REFERENCE_SESSION,
        'application_dispatch_attempts': 2, 'http_statuses': [200, 200], 'provider_request_count': None,
        'current_vintage_only': True, 'diagnostic_only': True, **FALSE_FLAGS}
    variable = {'capture_pins', 'metadata_row_counts', 'unexpected_ticker_row_counts', 'probes'}
    require(type(value) is dict and set(value) == set(fixed) | variable
        and all(type(value[key]) is type(item) and value[key] == item for key, item in fixed.items())
        and all(type(status) is int for status in value['http_statuses']), 'predicate_receipt')
    pins = value['capture_pins']
    require(type(pins) is dict and set(pins) == set(CAPTURE_NAMES), 'predicate_receipt')
    for pin in pins.values():
        require(type(pin) is dict and set(pin) == {'byte_count', 'sha256'} and type(pin['byte_count']) is int
            and 0 < pin['byte_count'] <= 65536 and _hash(pin['sha256']), 'predicate_receipt')
    counts, unexpected = value['metadata_row_counts'], value['unexpected_ticker_row_counts']
    require(type(counts) is dict and set(counts) == {'stocks', 'funds'} and type(unexpected) is dict
        and set(unexpected) == set(counts) and all(type(counts[table]) is int and 0 <= counts[table] < 100
            and type(unexpected[table]) is int and 0 <= unexpected[table] <= counts[table] for table in counts), 'predicate_receipt')
    require(type(value['probes']) is list and len(value['probes']) == len(PROBES), 'predicate_receipt')
    sums = {'stocks': 0, 'funds': 0}
    for index, row in enumerate(value['probes']):
        table = PROBES[index][0]
        require(type(row) is dict and set(row) == {'probe_index', 'candidate_count', 'candidate_ambiguous',
            'candidate_rows_sha256', 'fields', 'predicates', 'failed_identity_predicate_count',
            'unknown_predicate_count', 'collision_predicate_count'} and type(row['probe_index']) is int
            and row['probe_index'] == index and type(row['candidate_count']) is int and 0 <= row['candidate_count'] <= counts[table]
            and type(row['candidate_ambiguous']) is bool and row['candidate_ambiguous'] is (row['candidate_count'] > 1)
            and _hash(row['candidate_rows_sha256']), 'predicate_receipt')
        sums[table] += row['candidate_count']
        if row['candidate_count'] != 1:
            require(all(row[name] is None for name in ('fields', 'predicates', 'failed_identity_predicate_count',
                'unknown_predicate_count', 'collision_predicate_count')), 'predicate_receipt')
            if row['candidate_count'] == 0:
                require(row['candidate_rows_sha256'] == sha(canonical([])), 'predicate_receipt')
            continue
        fields, predicates = row['fields'], row['predicates']
        require(type(fields) is dict and set(fields) == set(META_FIELDS)
            and type(predicates) is dict and set(predicates) == set(PREDICATES)
            and all(item is None or type(item) is bool for item in predicates.values()), 'predicate_receipt')
        for field in fields.values():
            require(type(field) is dict and set(field) == {'type', 'state', 'utf8_byte_count', 'value_sha256'}
                and field['type'] == 'str' and type(field['utf8_byte_count']) is int and 0 <= field['utf8_byte_count'] <= 2048
                and field['state'] == ('nonempty' if field['utf8_byte_count'] else 'empty') and _hash(field['value_sha256'])
                and (field['utf8_byte_count'] == 0) is (field['value_sha256'] == sha(canonical(''))), 'predicate_receipt')
        require(fields['ticker']['value_sha256'] == sha(canonical(PROBES[index][1]))
            and fields['ticker']['utf8_byte_count'] == len(PROBES[index][1]), 'predicate_receipt')
        nullable = (COLLISIONS - {'cross_table_ticker_collision'}) | {'reference_interval_ordered', 'reference_interval_contains'}
        require(all(type(predicates[name]) is bool for name in set(PREDICATES) - nullable), 'predicate_receipt')
        require(predicates['cusip_field_nonempty'] is (fields['cusips']['utf8_byte_count'] > 0), 'predicate_receipt')
        require((not predicates['figi_format'] or fields['figi']['utf8_byte_count'] == 12)
            and (not predicates['permaticker_format'] or 1 <= fields['permaticker']['utf8_byte_count'] <= 64)
            and (not predicates['cusip_vocabulary_valid'] or predicates['cusip_field_nonempty'])
            and (not predicates['mic_allowed'] or fields['exchange']['utf8_byte_count'] > 0)
            and (not predicates['category_expected'] or fields['category']['utf8_byte_count'] > 0), 'predicate_receipt')
        for name, field in (('first_price_date_canonical','firstpricedate'),
            ('last_price_date_canonical','lastpricedate'),('lastupdated_canonical','lastupdated')):
            require(not predicates[name] or fields[field]['utf8_byte_count'] == 10, 'predicate_receipt')
        for field, names in (('permaticker',('same_table_permaticker_collision','cross_table_permaticker_collision')),
            ('figi',('same_table_figi_collision','cross_table_figi_collision'))):
            for name in names:
                require((predicates[name] is None) is (fields[field]['utf8_byte_count'] == 0), 'predicate_receipt')
        for name in ('same_table_cusip_collision','cross_table_cusip_collision'):
            require((predicates[name] is None) is (not predicates['cusip_vocabulary_valid']), 'predicate_receipt')
        for name, field, allowed in (('currency_usd', 'currency', ('USD',)),
            ('table_expected', 'table', (table, 'SEP' if table == 'stocks' else 'SFP')),
            ('isdelisted_shape', 'isdelisted', ('Y', 'N'))):
            require(predicates[name] is (fields[field]['value_sha256'] in {sha(canonical(item)) for item in allowed}), 'predicate_receipt')
            for literal in allowed:
                if fields[field]['value_sha256'] == sha(canonical(literal)):
                    require(fields[field]['utf8_byte_count'] == len(literal), 'predicate_receipt')
        if not predicates['first_price_date_canonical'] or not predicates['last_price_date_canonical']:
            require(predicates['reference_interval_ordered'] is predicates['reference_interval_contains'] is None, 'predicate_receipt')
        else:
            require(type(predicates['reference_interval_ordered']) is bool and type(predicates['reference_interval_contains']) is bool
                and (predicates['reference_interval_contains'] is False or predicates['reference_interval_ordered'] is True), 'predicate_receipt')
        for key, count in (('failed_identity_predicate_count', sum(item is False for name, item in predicates.items() if name not in COLLISIONS)),
            ('unknown_predicate_count', sum(item is None for item in predicates.values())),
            ('collision_predicate_count', sum(predicates[name] is True for name in COLLISIONS))):
            require(type(row[key]) is int and row[key] == count, 'predicate_receipt')
    require(all(sums[table] + unexpected[table] == counts[table] for table in counts)
        and len(canonical(value)) <= 65536, 'predicate_receipt')
    return json.loads(canonical(value))


def validate_capture(receipt, captures):
    checked = validate_receipt(receipt); expected = _receipt(captures)
    require(canonical(checked) == canonical(expected), 'predicate_receipt')
    return validate_receipt(expected)


def capture_pins(receipt): return validate_receipt(receipt)['capture_pins']


def validate_events(receipt, events):
    validate_receipt(receipt)
    require(type(events) is list and len(events) == 4, 'event')
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
        previous._decoded_secret_guard(captures[name], key, role)
        _rows(captures[name])
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
