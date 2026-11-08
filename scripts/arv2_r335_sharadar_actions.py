"""Bounded injected ACTIONS discovery; no source reads or operational caller.

The parent authenticates the fixed F data and original binding lineage before
supplying a plan. Only an owned requests Session and an in-memory key are used.
Successful HTTP bodies are handed to the private retention sink before CSV
validation; failed HTTP bodies are never read. Events and returned receipts
contain only counts, byte pins, request ordinals and finite status information.
Corporate-action rows remain current-vintage observations, never identity,
alias, payoff, price, source or trading admission.
"""
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import math
import re
import time
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit

import requests
from requests.adapters import HTTPAdapter

SCHEMA = 'arv2-r335-sharadar-actions-v1'
PLAN_SCHEMA, EVENT_SCHEMA = SCHEMA + '-plan', SCHEMA + '-event'
ENDPOINT = 'https://api.sharadar.com/v1.0/data/actions'
FIRST, LAST = '2023-11-01', '2026-10-13'
FIELDS = ('date', 'action', 'ticker', 'name', 'value', 'contraticker', 'contraname')
PRIMARY_FIELDS = ('date', 'action', 'ticker', 'name', 'contraticker', 'contraname')
F_DATA_PIN = {'byte_count': 87170, 'sha256': '0e41dca1d48955f83bcd5dcb2ae6192d85d9cf9f9ff40593bceeb0b5a601ccab'}
I_DATA_PIN = {'byte_count': 4984462, 'sha256': 'c85ae5ddf2e918d194f6aa2939ee1249229d0989f75c334ef92ea793b61b711d'}
MAX_TOKENS, MAX_REQUESTS, ROW_LIMIT = 16, 17, 1000
MAX_BODY, MAX_AGGREGATE, MAX_FIELD = 4 * 1024 * 1024, 16 * 1024 * 1024, 2048
MAX_OBSERVATION_SECONDS, TIMEOUT = 300, 30
FALSE_FLAGS = {'source_or_processing_rights_granted': False, 'identity_admitted': False,
    'historical_ticker_continuity_proven': False, 'corporate_action_semantics_interpreted': False,
    'terminal_payoff_proven': False, 'new_aliases_generated': False, 'price_acquired': False,
    'price_input_admitted': False, 'source_assignment_changed': False, 'point_in_time_proven': False,
    'permanent_security_master_proven': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False, 'QC_contact': False, 'orders_submitted': False,
    'credential_persisted': False, 'licensed_rows_disclosed': False,
    'physical_request_count_measured': False}
FINITE = frozenset(('plan', 'credential', 'session', 'deadline', 'journal', 'event',
    'prepared_identity', 'request_failed', 'http_status_unavailable', 'http_status',
    'response_identity', 'response_headers', 'response_encoding', 'response_bound',
    'response_stream', 'response_close', 'credential_echo', 'retention', 'csv', 'row_cap',
    'row_scope', 'row_date', 'row_value', 'changed', 'receipt', 'private', 'aggregate_bound', 'unknown'))


class Refused(ValueError):
    """Finite predicate only; never forward a provider, key, row or URL."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def _pin(value, maximum, code):
    require(type(value) is dict and set(value) == {'byte_count', 'sha256'}
        and type(value['byte_count']) is int and 0 < value['byte_count'] <= maximum
        and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']), code)
    return dict(value)


def _ticker(value):
    return type(value) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,63}', value) is not None and '..' not in value


def validate_plan(value):
    require(type(value) is dict and set(value) == {'schema', 'F_DATA_pin', 'I_DATA_pin',
        'explicit_tokens', 'binding_lineage_sha256'} and value['schema'] == PLAN_SCHEMA
        and value['F_DATA_pin'] == F_DATA_PIN and value['I_DATA_pin'] == I_DATA_PIN
        and type(value['explicit_tokens']) is list and 1 <= len(value['explicit_tokens']) <= MAX_TOKENS
        and all(_ticker(token) for token in value['explicit_tokens'])
        and value['explicit_tokens'] == sorted(set(value['explicit_tokens']))
        and type(value['binding_lineage_sha256']) is str
        and re.fullmatch('[0-9a-f]{64}', value['binding_lineage_sha256']), 'plan')
    _pin(value['F_DATA_pin'], 8 * 1024 * 1024, 'plan')
    _pin(value['I_DATA_pin'], 8 * 1024 * 1024, 'plan')
    return json.loads(canonical(value))


def request_plan(value):
    checked = validate_plan(value)
    tokens = checked['explicit_tokens']
    return tuple((index, 'ticker_union' if index == 0 else 'contraticker_single',
        ','.join(tokens) if index == 0 else tokens[index - 1]) for index in range(len(tokens) + 1))


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
            and parts.port is None and parts.path == '/v1.0/data/actions' and not parts.fragment
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


def validate_event(value):
    fields = {'schema', 'event', 'role', 'request_ordinal', 'application_attempt', 'http_status',
        'http_status_state', 'terminal_state', 'failure_code', 'response_pin', 'row_count'}
    require(type(value) is dict and set(value) == fields and value['schema'] == EVENT_SCHEMA
        and value['event'] in ('intent', 'status', 'terminal')
        and type(value['request_ordinal']) is int and 0 <= value['request_ordinal'] < MAX_REQUESTS
        and value['role'] == ('ticker_union' if value['request_ordinal'] == 0 else 'contraticker_single')
        and type(value['application_attempt']) is int
        and value['application_attempt'] == value['request_ordinal'] + 1, 'event')
    status, state = value['http_status'], value['http_status_state']
    require((type(status) is int and 100 <= status <= 599 and state == 'validated')
        or (status is None and state in ('not_observed', 'unavailable')), 'event')
    if value['event'] != 'terminal':
        require(value['terminal_state'] is value['failure_code'] is value['response_pin'] is value['row_count'] is None
            and (state == 'not_observed' if value['event'] == 'intent' else state != 'not_observed'), 'event')
    elif value['terminal_state'] == 'validated_body':
        require(status == 200 and value['failure_code'] is None
            and type(value['row_count']) is int and 0 <= value['row_count'] < ROW_LIMIT, 'event')
        _pin(value['response_pin'], MAX_BODY, 'event')
    else:
        require(value['terminal_state'] == 'refused' and state != 'not_observed'
            and type(value['failure_code']) is str and value['failure_code'] in FINITE
            and value['row_count'] is None, 'event')
        if value['response_pin'] is not None:
            require(status == 200, 'event'); _pin(value['response_pin'], MAX_BODY, 'event')
    return json.loads(canonical(value))


def _event(journal, ordinal, role, event, *, status=None, terminal=None, code=None, body_pin=None, rows=None):
    value = validate_event({'schema': EVENT_SCHEMA, 'event': event, 'role': role,
        'request_ordinal': ordinal, 'application_attempt': ordinal + 1, 'http_status': status,
        'http_status_state': 'not_observed' if event == 'intent' else 'unavailable' if status is None else 'validated',
        'terminal_state': terminal, 'failure_code': code, 'response_pin': body_pin, 'row_count': rows})
    try:
        journal('request-' + format(ordinal, '02d') + '-' + event, value)
    except Exception:
        raise Refused('journal') from None


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


def parse_response(raw, *, role, token, explicit_tokens):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY and role in ('ticker_union', 'contraticker_single')
        and type(explicit_tokens) is tuple and 1 <= len(explicit_tokens) <= MAX_TOKENS
        and all(_ticker(item) for item in explicit_tokens)
        and explicit_tokens == tuple(sorted(set(explicit_tokens)))
        and token == (','.join(explicit_tokens) if role == 'ticker_union' else token)
        and (role == 'ticker_union' or token in explicit_tokens), 'csv')
    try:
        text = raw.decode('utf-8-sig', errors='strict'); require('\x00' not in text, 'csv')
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        header = tuple(next(reader, ())); require(len(header) == len(FIELDS) and set(header) == set(FIELDS), 'csv')
        rows, previous, owners = [], None, {}
        for fields in reader:
            require(len(rows) + 1 < ROW_LIMIT, 'row_cap')
            require(len(fields) == len(FIELDS) and all(type(value) is str and len(value) <= MAX_FIELD
                and value == value.strip() and not any(ord(char) < 32 or ord(char) == 127 for char in value)
                for value in fields), 'csv')
            row = dict(zip(header, fields, strict=True))
            session = row['date']
            try:
                require(type(session) is str and date.fromisoformat(session).isoformat() == session
                    and FIRST <= session <= LAST and (previous is None or previous <= session), 'row_date')
            except ValueError:
                raise Refused('row_date') from None
            require(_ticker(row['ticker']) and (not row['contraticker'] or _ticker(row['contraticker']))
                and (row['ticker'] in explicit_tokens if role == 'ticker_union' else row['contraticker'] == token)
                and 0 < len(row['action']) <= 128 and row['action'].isascii()
                and row['name'], 'row_scope')
            if row['value']:
                require(len(row['value']) <= 128 and re.fullmatch(
                    r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]{1,4})?', row['value']), 'row_value')
                try:
                    require(Decimal(row['value']).is_finite(), 'row_value')
                except InvalidOperation:
                    raise Refused('row_value') from None
            primary = tuple(row[field] for field in PRIMARY_FIELDS)
            owners.setdefault(primary, set()).add(row['value'])
            rows.append(row); previous = session
        return rows, {'row_count': len(rows), 'primary_key_count': len(owners),
            'repeated_primary_key_row_count': len(rows) - len(owners),
            'conflicting_value_primary_key_count': sum(len(values) > 1 for values in owners.values())}
    except Refused:
        raise
    except (UnicodeError, csv.Error, ValueError, RecursionError):
        raise Refused('csv') from None


class PrivateCapture:
    """Original successful HTTP bodies; explicit access remains private."""
    __slots__ = ('_bodies',)

    def __init__(self, bodies):
        require(type(bodies) is tuple and 2 <= len(bodies) <= MAX_REQUESTS
            and all(type(raw) is bytes and 0 < len(raw) <= MAX_BODY for raw in bodies)
            and sum(map(len, bodies)) <= MAX_AGGREGATE, 'private')
        self._bodies = bodies

    def __repr__(self):
        return '<PrivateSharadarActionsCapture rows redacted; no admission>'

    def __reduce_ex__(self, protocol):
        raise TypeError('private corporate-action rows cannot enter public serialization')

    def bytes_tuple(self):
        return self._bodies


def validate_receipt(value, plan=None):
    keys = {'schema', 'plan_sha256', 'F_DATA_pin', 'I_DATA_pin', 'binding_lineage_sha256',
        'explicit_token_count', 'application_dispatch_attempts', 'provider_request_count', 'http_statuses',
        'responses', 'retained_success_body_bytes', 'row_count_including_query_overlap',
        'all_response_bodies_validated', 'complete_request_plan', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA + '-receipt'
        and type(value['plan_sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['plan_sha256'])
        and value['F_DATA_pin'] == F_DATA_PIN and value['I_DATA_pin'] == I_DATA_PIN
        and type(value['binding_lineage_sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['binding_lineage_sha256'])
        and type(value['explicit_token_count']) is int and 1 <= value['explicit_token_count'] <= MAX_TOKENS
        and type(value['application_dispatch_attempts']) is int
        and value['application_dispatch_attempts'] == value['explicit_token_count'] + 1
        and value['provider_request_count'] is None and type(value['http_statuses']) is list
        and len(value['http_statuses']) == value['application_dispatch_attempts']
        and all(type(status) is int and status == 200 for status in value['http_statuses'])
        and type(value['responses']) is list and len(value['responses']) == value['application_dispatch_attempts']
        and value['all_response_bodies_validated'] is value['complete_request_plan'] is True
        and all(value[key] is False for key in FALSE_FLAGS), 'receipt')
    for ordinal, row in enumerate(value['responses']):
        require(type(row) is dict and set(row) == {'request_ordinal', 'role', 'body_pin', 'row_count',
            'primary_key_count', 'repeated_primary_key_row_count', 'conflicting_value_primary_key_count'}
            and type(row['request_ordinal']) is int and row['request_ordinal'] == ordinal
            and row['role'] == ('ticker_union' if ordinal == 0 else 'contraticker_single')
            and all(type(row[key]) is int and row[key] >= 0 for key in ('row_count', 'primary_key_count',
                'repeated_primary_key_row_count', 'conflicting_value_primary_key_count'))
            and row['row_count'] < ROW_LIMIT and row['primary_key_count'] <= row['row_count']
            and (row['primary_key_count'] > 0) is (row['row_count'] > 0)
            and row['repeated_primary_key_row_count'] == row['row_count'] - row['primary_key_count']
            and row['conflicting_value_primary_key_count']
                <= min(row['primary_key_count'], row['repeated_primary_key_row_count']), 'receipt')
        _pin(row['body_pin'], MAX_BODY, 'receipt')
    require(type(value['retained_success_body_bytes']) is int and 0 < value['retained_success_body_bytes'] <= MAX_AGGREGATE
        and value['retained_success_body_bytes'] == sum(row['body_pin']['byte_count'] for row in value['responses'])
        and type(value['row_count_including_query_overlap']) is int
        and value['row_count_including_query_overlap'] == sum(row['row_count'] for row in value['responses']), 'receipt')
    if plan is not None:
        checked = validate_plan(plan)
        require(value['plan_sha256'] == sha(canonical(checked))
            and value['explicit_token_count'] == len(checked['explicit_tokens'])
            and value['binding_lineage_sha256'] == checked['binding_lineage_sha256'], 'receipt')
    return json.loads(canonical(value))


def validate_events(events, plan, receipt=None):
    """Check a complete success trace or a finite partial/refused prefix.

    An intent may precede local preparation/deadline refusal without a status
    event; it is never evidence that a physical request was or was not sent.
    """
    sequence = request_plan(plan)
    require(type(events) is list and len(events) <= 3 * len(sequence), 'event')
    checked, ordinal, phase, last_status, stopped = [], 0, 'intent', None, False
    for event in events:
        row = validate_event(event)
        require(not stopped and ordinal < len(sequence) and row['request_ordinal'] == ordinal
            and row['role'] == sequence[ordinal][1], 'event')
        if phase == 'intent':
            require(row['event'] == 'intent', 'event'); phase = 'status_or_terminal'
        elif phase == 'status_or_terminal' and row['event'] == 'status':
            last_status = row['http_status']; phase = 'terminal'
        else:
            require(row['event'] == 'terminal'
                and (row['terminal_state'] == 'refused' if phase == 'status_or_terminal' else True)
                and row['http_status'] == last_status, 'event')
            if row['terminal_state'] == 'refused':
                stopped = True
            else:
                ordinal += 1; phase = 'intent'; last_status = None
        checked.append(row)
    if receipt is not None:
        result = validate_receipt(receipt, plan)
        require(not stopped and ordinal == len(sequence) and phase == 'intent'
            and len(checked) == 3 * len(sequence), 'event')
        for row in checked:
            if row['event'] == 'terminal':
                summary = result['responses'][row['request_ordinal']]
                require(row['response_pin'] == summary['body_pin'] and row['row_count'] == summary['row_count'], 'event')
    return checked


def observe(plan, *, session, api_key, journal, retain_response, deadline):
    checked = validate_plan(plan); frozen = canonical(checked); plan_sha = sha(frozen)
    require(type(api_key) is str and 8 <= len(api_key) <= 4096 and api_key.isascii()
        and all(33 <= ord(char) <= 126 for char in api_key), 'credential')
    require(callable(journal) and callable(retain_response), 'journal')
    _session(session); _budget(deadline)
    bodies, responses = [], []
    for ordinal, role, token in request_plan(checked):
        require(canonical(validate_plan(plan)) == frozen, 'changed'); _session(session); _budget(deadline)
        require(sum(map(len, bodies)) < MAX_AGGREGATE, 'aggregate_bound')
        _event(journal, ordinal, role, 'intent')
        status, retained = None, None
        def status_observer(value):
            nonlocal status
            status = value
            _event(journal, ordinal, role, 'status', status=status)
        def body_observer(raw):
            nonlocal retained
            require(canonical(validate_plan(plan)) == frozen, 'changed'); _budget(deadline)
            expected = pin(raw)
            transport = {'schema': SCHEMA + '-private-transport', 'plan_sha256': plan_sha,
                'request_ordinal': ordinal, 'role': role, 'query_token': token,
                'http_status': 200, 'body_pin': expected, 'CSV_validation_complete': False}
            try:
                returned = retain_response(ordinal, raw, json.loads(canonical(transport)))
                require(_pin(returned, MAX_BODY, 'retention') == expected, 'retention')
            except Refused:
                raise
            except Exception:
                raise Refused('retention') from None
            retained = expected; _budget(deadline)
        try:
            require(canonical(validate_plan(plan)) == frozen, 'changed')
            query = {'ticker' if ordinal == 0 else 'contraticker': token,
                'from': FIRST, 'to': LAST, 'fields': ','.join(FIELDS), 'format': 'csv',
                'skip': '0', 'limit': str(ROW_LIMIT), 'sort': 'date.asc'}
            raw = _fetch(session, api_key, query, deadline, min(MAX_BODY, MAX_AGGREGATE - sum(map(len, bodies))),
                status_observer=status_observer, body_observer=body_observer)
            require(canonical(validate_plan(plan)) == frozen, 'changed'); _budget(deadline)
            expected = pin(raw)
            require(retained == expected, 'retention')
            _, counts = parse_response(raw, role=role, token=token, explicit_tokens=tuple(checked['explicit_tokens']))
            require(canonical(validate_plan(plan)) == frozen, 'changed'); _session(session); _budget(deadline)
            responses.append({'request_ordinal': ordinal, 'role': role, 'body_pin': expected, **counts}); bodies.append(raw)
            _event(journal, ordinal, role, 'terminal', status=status, terminal='validated_body', body_pin=expected, rows=counts['row_count'])
        except Exception as error:
            code = finite(error)
            if code != 'journal':
                _event(journal, ordinal, role, 'terminal', status=status, terminal='refused', code=code, body_pin=retained)
            raise Refused(code) from None
    require(canonical(validate_plan(plan)) == frozen, 'changed'); _session(session); _budget(deadline)
    receipt = {'schema': SCHEMA + '-receipt', 'plan_sha256': plan_sha,
        'F_DATA_pin': checked['F_DATA_pin'], 'I_DATA_pin': checked['I_DATA_pin'],
        'binding_lineage_sha256': checked['binding_lineage_sha256'], 'explicit_token_count': len(checked['explicit_tokens']),
        'application_dispatch_attempts': len(responses), 'provider_request_count': None,
        'http_statuses': [200] * len(responses), 'responses': responses,
        'retained_success_body_bytes': sum(map(len, bodies)),
        'row_count_including_query_overlap': sum(row['row_count'] for row in responses),
        'all_response_bodies_validated': True, 'complete_request_plan': True, **FALSE_FLAGS}
    return validate_receipt(receipt, checked), PrivateCapture(tuple(bodies))


def validate_capture(plan, receipt, bodies):
    checked = validate_plan(plan); original = validate_receipt(receipt)
    require(type(bodies) is tuple and len(bodies) == len(request_plan(checked))
        and original['plan_sha256'] == sha(canonical(checked))
        and original['binding_lineage_sha256'] == checked['binding_lineage_sha256'], 'receipt')
    rows = []
    for (ordinal, role, token), raw in zip(request_plan(checked), bodies, strict=True):
        require(type(raw) is bytes and pin(raw) == original['responses'][ordinal]['body_pin'], 'receipt')
        _, counts = parse_response(raw, role=role, token=token, explicit_tokens=tuple(checked['explicit_tokens']))
        rows.append({'request_ordinal': ordinal, 'role': role, 'body_pin': pin(raw), **counts})
    require(rows == original['responses'], 'receipt')
    return original


def profile_record():
    return {'schema': SCHEMA, 'plan_schema': PLAN_SCHEMA, 'event_schema': EVENT_SCHEMA,
        'endpoint': ENDPOINT, 'fields': list(FIELDS), 'first': FIRST, 'last': LAST,
        'F_DATA_pin': dict(F_DATA_PIN), 'I_DATA_pin': dict(I_DATA_PIN),
        'maximum_explicit_tokens': MAX_TOKENS, 'maximum_application_dispatch_attempts': MAX_REQUESTS,
        'request_sequence': 'one_documented_comma_ticker_union_then_each_scalar_contraticker_same_fixed_tokens',
        'maximum_response_bytes': MAX_BODY, 'maximum_aggregate_retained_bytes': MAX_AGGREGATE,
        'row_limit': ROW_LIMIT, 'accepted_rows_strictly_less_than_limit': True,
        'pagination': False, 'recursion_or_new_aliases': False, 'retries': 0,
        'timeout_seconds': TIMEOUT, 'maximum_observation_seconds': MAX_OBSERVATION_SECONDS,
        'deadline_qualification': 'cannot_interrupt_uninterruptible_native_IO_or_host_suspension',
        'tls_verify': True, 'trust_environment': False, 'redirects': False, 'compression': False,
        'status_identity': 'exact_response_request_and_URL_before_numeric_status_before_failed_body_refusal',
        'retention': 'complete_status200_transport_and_secret_echo_checks_before_private_sink_before_CSV_parse',
        'retention_is_CSV_acceptance': False, 'journal_events_per_request': 3,
        'provider_request_count': None, 'application_attempt_is_not_physical_wire_count': True,
        'application_intent_can_precede_failed_journal_or_presend_budget': True,
        'row_semantics': 'uninterpreted_action_and_nullable_finite_signed_numeric_value_current_vintage_only',
        'primary_key_fields': list(PRIMARY_FIELDS),
        'duplicates': 'all_rows_retained_including_query_overlap_and_same_six_field_primary_key_conflicting_values',
        'external_obligations': 'authenticate_F_and_original_binding_lineage_current_rights_claim_host_source_and_plan_freeze',
        **FALSE_FLAGS}
