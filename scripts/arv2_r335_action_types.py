"""One fixed metadata-dictionary HTTP capture, followed by pure validation.

Capture does not parse CSV. Its parent owns source/host/rights/claim/Keychain,
private persistence and the one later credential-free native validation worker.
No old private DATA, operation, price, QC, identifier or trading path exists.
"""
import csv
import hashlib
import io
import json
import math
import re
import time
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit

import requests
from requests.adapters import HTTPAdapter

SCHEMA = 'arv2-r335-action-types-v1'
PLAN_SCHEMA, EVENT_SCHEMA = SCHEMA + '-plan', SCHEMA + '-event'
ENDPOINT = 'https://api.sharadar.com/v1.0/data/descriptions'
QUERY = {'tablename': 'actiontypes', 'format': 'csv', 'limit': '1000', 'skip': '0', 'sort': 'indicator.asc'}
FIELDS = ('table', 'indicator', 'isFilter', 'isPrimaryKey', 'title', 'description', 'unitType')
VARIANTS = {'table': 'table', 'tablename': 'table', 'indicator': 'indicator',
    'isFilter': 'isFilter', 'isfilter': 'isFilter', 'isPrimaryKey': 'isPrimaryKey',
    'isprimarykey': 'isPrimaryKey', 'title': 'title', 'description': 'description',
    'unitType': 'unitType', 'unittype': 'unitType'}
MAX_BODY, ROW_LIMIT, MAX_FIELD = 512 * 1024, 1000, 16384
MAX_OBSERVATION_SECONDS, TIMEOUT = 150, 30
TRANSPORT_SOURCE_PIN = {'byte_count': 31621, 'sha256': '71417807bb3fc74dc58e8c53024d402a769165c275e2693b287a1561e3127216'}
FALSE_FLAGS = {'source_or_processing_rights_granted': False, 'point_in_time_proven': False,
    'historical_version_or_availability_proven': False, 'action_direction_interpreted': False,
    'identity_admitted': False, 'historical_ticker_continuity_proven': False,
    'terminal_payoff_proven': False, 'price_acquired': False, 'price_input_admitted': False,
    'source_assignment_changed': False, 'formal_forward_ready': False, 'paper_or_live_ready': False,
    'QC_contact': False, 'orders_submitted': False, 'credential_persisted': False,
    'licensed_rows_disclosed': False, 'physical_request_count_measured': False}
FINITE = frozenset(('plan', 'credential', 'session', 'deadline', 'journal', 'event', 'prepared_identity',
    'request_failed', 'http_status_unavailable', 'http_status', 'response_identity', 'response_headers',
    'response_encoding', 'response_bound', 'response_stream', 'response_close', 'credential_echo',
    'retention', 'aggregate_bound', 'changed', 'csv', 'header', 'row_cap', 'row_scope', 'receipt', 'private', 'unknown'))


class Refused(ValueError):
    """Finite field predicate, never credentials, rows or exception text."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def _pin(value, code):
    require(type(value) is dict and set(value) == {'byte_count', 'sha256'}
        and type(value['byte_count']) is int and 0 < value['byte_count'] <= MAX_BODY
        and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']), code)
    return dict(value)


def plan_record():
    return {'schema': PLAN_SCHEMA, 'endpoint': ENDPOINT, 'query': dict(QUERY)}


def validate_plan(value):
    require(type(value) is dict and set(value) == {'schema', 'endpoint', 'query'}
        and type(value['schema']) is str and value['schema'] == PLAN_SCHEMA
        and type(value['endpoint']) is str and value['endpoint'] == ENDPOINT
        and type(value['query']) is dict and set(value['query']) == set(QUERY)
        and all(type(key) is str and type(item) is str for key, item in value['query'].items())
        and value['query'] == QUERY, 'plan')
    return json.loads(canonical(value))


# The fixed transport functions below are copied without execution/import from
# the frozen ACTIONS v2 source. Only _url's exact endpoint path is substituted.


def _budget(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline), 'deadline')
    remaining = deadline - time.monotonic()
    require(0 < remaining <= MAX_OBSERVATION_SECONDS, 'deadline')
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


def _url(value):
    require(type(value) is str and 0 < len(value) <= 32768 and value == value.strip()
        and '\\' not in value and not any(ord(char) < 32 for char in value), 'prepared_identity')
    try:
        parts = urlsplit(value)
        pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True,
            encoding='utf8', errors='strict')
        require(parts.scheme == 'https' and parts.netloc == 'api.sharadar.com'
            and parts.hostname == 'api.sharadar.com' and parts.username is parts.password is None
            and parts.port is None and parts.path == '/v1.0/data/descriptions' and not parts.fragment
            and re.search(r'%(?![0-9a-fA-F]{2})', parts.query) is None
            and len({key for key, _ in pairs}) == len(pairs), 'prepared_identity')
        return parts, tuple(sorted(pairs))
    except Refused:
        raise
    except Exception:
        raise Refused('prepared_identity') from None


def _identity(prepared, params):
    try:
        expected_parts, expected_query = _url(ENDPOINT + '?' + urlencode(params))
        parts, query = _url(prepared.url)
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


def _fetch(session, key, query, deadline, maximum, *, status_observer, body_observer):
    require(type(maximum) is int and 0 < maximum <= MAX_BODY, 'aggregate_bound')
    params = {**query, 'api_key': key}
    _session(session); _budget(deadline)
    try:
        intent = session.prepare_request(requests.Request('GET', ENDPOINT, params=params,
            headers={'Accept-Encoding': 'identity'}))
        _identity(intent, params)
    except Refused:
        raise
    except Exception:
        raise Refused('prepared_identity') from None
    response, complete = None, False
    try:
        try:
            response = session.get(ENDPOINT, params=params, timeout=_budget(deadline),
                allow_redirects=False, stream=True, verify=True, headers={'Accept-Encoding': 'identity'})
        except Exception:
            status_observer(None)
            raise Refused('request_failed') from None
        try:
            require(type(response) is requests.Response and response.history == [], 'response_identity')
            _identity(response.request, params)
            actual, actual_query = _url(response.url)
            expected, expected_query = _url(ENDPOINT + '?' + urlencode(params))
            require((actual.scheme, actual.netloc, actual.path, actual_query)
                == (expected.scheme, expected.netloc, expected.path, expected_query), 'response_identity')
        except Refused:
            status_observer(None)
            raise
        except Exception:
            status_observer(None)
            raise Refused('response_identity') from None
        try:
            numeric = response.status_code
        except Exception:
            numeric = None
        status = numeric if type(numeric) is int and 100 <= numeric <= 599 else None
        status_observer(status)
        require(status is not None, 'http_status_unavailable')
        require(status == 200, 'http_status')  # NEVER read a failed response body.
        try:
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
        # A later close or CSV refusal must not discard already authenticated
        # complete status200 bytes. This sink is private and owns persistence.
        body_observer(payload)
        complete = True
        return payload
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                if complete:
                    raise Refused('response_close') from None


def validate_event(value):
    keys = {'schema', 'event', 'role', 'request_ordinal', 'application_attempt', 'http_status',
        'http_status_state', 'terminal_state', 'failure_code', 'response_pin', 'CSV_validation_complete'}
    require(type(value) is dict and set(value) == keys and value['schema'] == EVENT_SCHEMA
        and value['event'] in ('intent', 'status', 'terminal') and value['role'] == 'actiontypes'
        and type(value['request_ordinal']) is int and value['request_ordinal'] == 0
        and type(value['application_attempt']) is int and value['application_attempt'] == 1
        and value['CSV_validation_complete'] is False, 'event')
    status, state = value['http_status'], value['http_status_state']
    require((type(status) is int and 100 <= status <= 599 and state == 'validated')
        or (status is None and state in ('not_observed', 'unavailable')), 'event')
    if value['event'] != 'terminal':
        require(value['terminal_state'] is value['failure_code'] is value['response_pin'] is None
            and (state == 'not_observed' if value['event'] == 'intent' else state != 'not_observed'), 'event')
    elif value['terminal_state'] == 'captured_body':
        require(status == 200 and value['failure_code'] is None, 'event'); _pin(value['response_pin'], 'event')
    else:
        require(value['terminal_state'] == 'refused' and state != 'not_observed'
            and type(value['failure_code']) is str and value['failure_code'] in FINITE, 'event')
        if value['response_pin'] is not None:
            require(status == 200, 'event'); _pin(value['response_pin'], 'event')
    return json.loads(canonical(value))


def _event(journal, event, *, status=None, terminal=None, code=None, body_pin=None):
    value = validate_event({'schema': EVENT_SCHEMA, 'event': event, 'role': 'actiontypes',
        'request_ordinal': 0, 'application_attempt': 1, 'http_status': status,
        'http_status_state': 'not_observed' if event == 'intent' else 'unavailable' if status is None else 'validated',
        'terminal_state': terminal, 'failure_code': code, 'response_pin': body_pin, 'CSV_validation_complete': False})
    try:
        journal('request-00-' + event, value)
    except Exception:
        raise Refused('journal') from None


def validate_events(events, plan, receipt=None):
    validate_plan(plan)
    require(type(events) is list and len(events) <= 3, 'event')
    checked, phase, status, stopped = [], 'intent', None, False
    for event in events:
        row = validate_event(event)
        require(not stopped, 'event')
        if phase == 'intent':
            require(row['event'] == 'intent', 'event'); phase = 'status_or_terminal'
        elif phase == 'status_or_terminal' and row['event'] == 'status':
            status = row['http_status']; phase = 'terminal'
        else:
            require(row['event'] == 'terminal' and row['http_status'] == status
                and (row['terminal_state'] == 'refused' if phase == 'status_or_terminal' else True), 'event')
            stopped = True; phase = row['terminal_state']
        checked.append(row)
    if receipt is not None:
        value = validate_capture_receipt(receipt, plan)
        require(len(checked) == 3 and phase == 'captured_body'
            and checked[-1]['response_pin'] == value['response_pin'], 'event')
    return checked


class PrivateCapture:
    __slots__ = ('_raw',)

    def __init__(self, raw):
        require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY, 'private'); self._raw = raw

    def __repr__(self):
        return '<PrivateActionTypesCapture metadata redacted; CSV not validated>'

    def __reduce_ex__(self, protocol):
        raise TypeError('private metadata cannot enter public serialization')

    def body_bytes(self):
        return self._raw


def validate_capture_receipt(value, plan=None):
    keys = {'schema', 'plan_sha256', 'application_dispatch_attempts', 'provider_request_count',
        'http_status', 'response_pin', 'CSV_validation_complete', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA + '-capture'
        and type(value['plan_sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['plan_sha256'])
        and type(value['application_dispatch_attempts']) is int and value['application_dispatch_attempts'] == 1
        and value['provider_request_count'] is None and type(value['http_status']) is int and value['http_status'] == 200
        and value['CSV_validation_complete'] is False and all(value[key] is False for key in FALSE_FLAGS), 'receipt')
    _pin(value['response_pin'], 'receipt')
    if plan is not None:
        require(value['plan_sha256'] == sha(canonical(validate_plan(plan))), 'receipt')
    return json.loads(canonical(value))


def capture(plan, *, session, api_key, journal, retain_response, deadline):
    checked = validate_plan(plan); frozen = canonical(checked); plan_sha = sha(frozen)
    require(type(api_key) is str and 8 <= len(api_key) <= 4096 and api_key.isascii()
        and all(33 <= ord(char) <= 126 for char in api_key), 'credential')
    require(callable(journal) and callable(retain_response), 'journal'); _session(session); _budget(deadline)
    status, retained, terminal_emitted = None, None, False
    _event(journal, 'intent')
    def status_observer(value):
        nonlocal status
        status = value; _event(journal, 'status', status=status)
    def body_observer(raw):
        nonlocal retained
        require(canonical(validate_plan(plan)) == frozen, 'changed'); _budget(deadline)
        expected = pin(raw)
        metadata = {'schema': SCHEMA + '-private-transport', 'plan_sha256': plan_sha,
            'request_ordinal': 0, 'role': 'actiontypes', 'http_status': 200,
            'body_pin': expected, 'CSV_validation_complete': False}
        try:
            returned = retain_response(0, raw, json.loads(canonical(metadata)))
            require(_pin(returned, 'retention') == expected, 'retention')
        except Refused:
            raise
        except Exception:
            raise Refused('retention') from None
        retained = expected; _budget(deadline)
    try:
        require(canonical(validate_plan(plan)) == frozen, 'changed')
        raw = _fetch(session, api_key, checked['query'], deadline, MAX_BODY,
            status_observer=status_observer, body_observer=body_observer)
        require(canonical(validate_plan(plan)) == frozen and retained == pin(raw), 'changed')
        _session(session); _budget(deadline)
        _event(journal, 'terminal', status=status, terminal='captured_body', body_pin=retained)
        terminal_emitted = True
        require(canonical(validate_plan(plan)) == frozen, 'changed'); _session(session); _budget(deadline)
        receipt = {'schema': SCHEMA + '-capture', 'plan_sha256': plan_sha,
            'application_dispatch_attempts': 1, 'provider_request_count': None, 'http_status': 200,
            'response_pin': retained, 'CSV_validation_complete': False, **FALSE_FLAGS}
        return validate_capture_receipt(receipt, checked), PrivateCapture(raw)
    except Exception as error:
        code = finite(error)
        if code != 'journal' and not terminal_emitted:
            _event(journal, 'terminal', status=status, terminal='refused', code=code, body_pin=retained)
        raise Refused(code) from None


def _parse_dictionary(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY, 'csv')
    try:
        text = raw.decode('utf-8-sig', errors='strict'); require('\x00' not in text, 'csv')
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        header = tuple(next(reader, ()))
        require(len(header) == len(FIELDS) and len(set(header)) == len(header)
            and all(name in VARIANTS for name in header), 'header')
        logical = tuple(VARIANTS[name] for name in header)
        require(len(set(logical)) == len(FIELDS) and set(logical) == set(FIELDS), 'header')
        rows, owners, empty_indicator, empty_description = [], {}, 0, 0
        flags = {name: dict.fromkeys(('Y', 'N', 'empty', 'other'), 0) for name in ('isFilter', 'isPrimaryKey')}
        for fields in reader:
            require(len(rows) + 1 < ROW_LIMIT, 'row_cap')
            require(len(fields) == len(FIELDS) and all(type(value) is str and len(value) <= MAX_FIELD for value in fields), 'csv')
            row = dict(zip(logical, fields, strict=True)); require(row['table'] == 'actiontypes', 'row_scope')
            primary = (row['table'], row['indicator'])
            owners.setdefault(primary, set()).add(tuple(row[name] for name in FIELDS if name not in ('table', 'indicator')))
            empty_indicator += row['indicator'] == ''; empty_description += row['description'] == ''
            for name in flags:
                value = row[name]; flags[name][value if value in ('Y', 'N') else 'empty' if value == '' else 'other'] += 1
            rows.append(dict(zip(header, fields, strict=True)))
        summary = {'original_header': list(header), 'row_count': len(rows), 'primary_key_count': len(owners),
            'repeated_primary_key_row_count': len(rows) - len(owners),
            'conflicting_definition_primary_key_count': sum(len(values) > 1 for values in owners.values()),
            'empty_indicator_count': empty_indicator, 'empty_description_count': empty_description,
            'filter_flag_counts': flags['isFilter'], 'primary_flag_counts': flags['isPrimaryKey']}
        return rows, summary
    except Refused:
        raise
    except (csv.Error, UnicodeError, ValueError, RecursionError):
        raise Refused('csv') from None


def validate_dictionary_receipt(value, plan=None, capture_receipt=None):
    keys = {'schema', 'plan_sha256', 'capture_receipt_sha256', 'response_pin', 'original_header',
        'row_count', 'primary_key_count', 'repeated_primary_key_row_count', 'conflicting_definition_primary_key_count',
        'empty_indicator_count', 'empty_description_count', 'filter_flag_counts', 'primary_flag_counts',
        'CSV_validation_complete', *FALSE_FLAGS}
    counts = ('row_count', 'primary_key_count', 'repeated_primary_key_row_count',
        'conflicting_definition_primary_key_count', 'empty_indicator_count', 'empty_description_count')
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA + '-validation'
        and all(type(value[name]) is str and re.fullmatch('[0-9a-f]{64}', value[name])
            for name in ('plan_sha256', 'capture_receipt_sha256'))
        and value['CSV_validation_complete'] is True and all(value[key] is False for key in FALSE_FLAGS)
        and all(type(value[name]) is int and value[name] >= 0 for name in counts)
        and value['row_count'] < ROW_LIMIT and value['primary_key_count'] <= value['row_count']
        and (value['primary_key_count'] > 0) is (value['row_count'] > 0)
        and value['repeated_primary_key_row_count'] == value['row_count'] - value['primary_key_count']
        and value['conflicting_definition_primary_key_count'] <= min(value['primary_key_count'], value['repeated_primary_key_row_count'])
        and value['empty_indicator_count'] <= value['row_count'] and value['empty_description_count'] <= value['row_count'], 'receipt')
    header = value['original_header']
    require(type(header) is list and len(header) == len(FIELDS)
        and all(type(name) is str and name in VARIANTS for name in header) and len(set(header)) == len(FIELDS)
        and {VARIANTS[name] for name in header} == set(FIELDS), 'receipt')
    _pin(value['response_pin'], 'receipt')
    for name in ('filter_flag_counts', 'primary_flag_counts'):
        flags = value[name]
        require(type(flags) is dict and set(flags) == {'Y', 'N', 'empty', 'other'}
            and all(type(count) is int and count >= 0 for count in flags.values())
            and sum(flags.values()) == value['row_count'], 'receipt')
    if plan is not None:
        require(value['plan_sha256'] == sha(canonical(validate_plan(plan))), 'receipt')
    if capture_receipt is not None:
        capture_value = validate_capture_receipt(capture_receipt, plan)
        require(value['capture_receipt_sha256'] == sha(canonical(capture_value))
            and value['response_pin'] == capture_value['response_pin'], 'receipt')
    return json.loads(canonical(value))


def validate_capture(plan, capture_receipt, raw):
    checked = validate_plan(plan); captured = validate_capture_receipt(capture_receipt, checked)
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY and pin(raw) == captured['response_pin'], 'receipt')
    _, summary = _parse_dictionary(raw)
    value = {'schema': SCHEMA + '-validation', 'plan_sha256': sha(canonical(checked)),
        'capture_receipt_sha256': sha(canonical(captured)), 'response_pin': pin(raw),
        'CSV_validation_complete': True, **summary, **FALSE_FLAGS}
    return validate_dictionary_receipt(value, checked, captured)


def profile_record():
    return {'schema': SCHEMA, 'plan': plan_record(), 'maximum_application_dispatch_attempts': 1,
        'provider_request_count': None, 'application_attempt_is_not_physical_wire_count': True,
        'maximum_body_bytes': MAX_BODY, 'row_limit': ROW_LIMIT, 'accepted_rows_strictly_less_than_limit': True,
        'field_variants': dict(VARIANTS), 'original_header_and_text_preserved': True,
        'text': 'bounded_opaque_UTF8_multiline_and_blank_no_ASCII_ticker_name_or_direction_inference',
        'duplicate_keys': 'table_and_indicator_all_rows_preserved_conflicting_definitions_counted_never_overwritten',
        'flag_columns': 'raw_text_preserved_Y_N_empty_other_counted_not_coerced',
        'capture': 'transport_only_private_status200_body_retained_before_close_never_CSV_success',
        'validation': 'separate_credential_free_native_worker_authenticates_body_pin_before_CSV',
        'TLS_verify': True, 'trust_environment': False, 'redirects': False, 'compression': False, 'retries': 0,
        'timeout_seconds': TIMEOUT, 'maximum_observation_seconds': MAX_OBSERVATION_SECONDS,
        'uninterruptible_IO_or_host_suspension_not_bounded': True,
        'transport_source_pin': dict(TRANSPORT_SOURCE_PIN), **FALSE_FLAGS}
