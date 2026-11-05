"""Synthetic metadata capture; no DATA, Keychain, provider, USB or QC access."""
import ast
import copy
import csv
import inspect
import io
from itertools import product
from pathlib import Path
import pickle
import time
from types import SimpleNamespace as NS
from urllib.parse import quote, quote_plus

import pytest
import requests

from scripts import arv2_r335_action_types as m

KEY = 'synthetic-SECRET+/"1234'
ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


def refused(code, call):
    with pytest.raises(m.Refused) as caught:
        call()
    assert m.finite(caught.value) == code and KEY not in str(caught.value)


def row(**changes):
    value = {'table': 'actiontypes', 'indicator': 'synthetic_event', 'isFilter': 'N',
        'isPrimaryKey': 'N', 'title': 'Synthetic title', 'description': 'Synthetic definition', 'unitType': 'text'}
    value.update(changes); return value


def csv_bytes(rows=(), header=m.FIELDS):
    stream = io.StringIO(newline=''); writer = csv.writer(stream, lineterminator='\n'); writer.writerow(header)
    logical = tuple(m.VARIANTS.get(name, name) for name in header)
    for value in rows:
        writer.writerow([value.get(name, '') for name in logical] if type(value) is dict else value)
    return stream.getvalue().encode('utf8')


@pytest.fixture
def plan():
    return m.plan_record()


@pytest.fixture
def transport(monkeypatch):
    state = NS(calls=[], events=[], retained=[], read=[], responses=[], raw=csv_bytes([row()]),
        status=200, headers={}, chunks=None, mutation=None, fail_request=False, fail_close=False,
        fail_retain=False, bad_pin=False, fail_journal=None)
    session = m.configure_owned_session(requests.Session())
    def get(self, endpoint, **kwargs):
        state.calls.append((endpoint, copy.deepcopy(kwargs)))
        if state.fail_request: raise RuntimeError(KEY)
        response = requests.Response(); response.status_code = state.status
        response.request = self.prepare_request(requests.Request('GET', endpoint, params=kwargs['params'], headers=kwargs['headers']))
        response.url = response.request.url; response.history = []; response.headers.update(state.headers); response.closed = False
        def content(chunk_size):
            state.read.append(True); yield from state.chunks if state.chunks is not None else (state.raw,)
        def close():
            response.closed = True
            if state.fail_close: raise RuntimeError(KEY)
        response.iter_content, response.close = content, close; state.responses.append(response)
        if state.mutation: state.mutation(self, response)
        return response
    monkeypatch.setattr(requests.Session, 'get', get)
    def journal(marker, event):
        if marker == state.fail_journal: raise RuntimeError(KEY)
        state.events.append((marker, copy.deepcopy(event)))
    def retain(ordinal, raw, metadata):
        state.retained.append((ordinal, raw, copy.deepcopy(metadata)))
        if state.fail_retain: raise RuntimeError(KEY)
        return {'byte_count': len(raw), 'sha256': '0' * 64} if state.bad_pin else m.pin(raw)
    state.session, state.journal, state.retain = session, journal, retain
    return state


def capture(plan, transport):
    return m.capture(plan, session=transport.session, api_key=KEY, journal=transport.journal,
        retain_response=transport.retain, deadline=time.monotonic() + 149)


def test_one_exact_public_query_transport_capture_then_separate_dictionary_validation(plan, transport):
    captured, opaque = capture(plan, transport)
    assert len(transport.calls) == len(transport.retained) == 1 and transport.responses[0].closed
    endpoint, kwargs = transport.calls[0]
    assert endpoint == 'https://api.sharadar.com/v1.0/data/descriptions'
    assert kwargs['params'] == {**m.QUERY, 'api_key': KEY}
    assert set(m.QUERY) == {'tablename', 'format', 'limit', 'skip', 'sort'}
    assert kwargs['allow_redirects'] is False and kwargs['verify'] is kwargs['stream'] is True
    assert kwargs['headers'] == {'Accept-Encoding': 'identity'} and 0 < kwargs['timeout'] <= 30
    assert captured['CSV_validation_complete'] is False and captured['provider_request_count'] is None
    assert captured['application_dispatch_attempts'] == 1 and captured['response_pin'] == m.pin(transport.raw)
    assert m.validate_events([value for _, value in transport.events], plan, captured)
    assert transport.events[-1][1]['terminal_state'] == 'captured_body'
    assert all(captured[key] is False for key in m.FALSE_FLAGS)
    result = m.validate_capture(plan, captured, opaque.body_bytes())
    assert result['CSV_validation_complete'] is True and result['row_count'] == result['primary_key_count'] == 1
    assert result['capture_receipt_sha256'] == m.sha(m.canonical(captured))
    assert m.validate_dictionary_receipt(result, plan, captured) == result
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    assert b'Synthetic definition' not in m.canonical(result) and KEY not in repr(result)
    with pytest.raises(TypeError): pickle.dumps(opaque)
    assert 'Synthetic definition' not in repr(opaque)


def test_capture_never_parses_CSV_and_bad_200_evidence_is_retained(plan, transport, monkeypatch):
    transport.raw = b'not a dictionary'
    def forbidden(*args): raise AssertionError('CSV parsing in credential-bearing capture')
    monkeypatch.setattr(m, '_parse_dictionary', forbidden)
    receipt, opaque = capture(plan, transport)
    assert receipt['CSV_validation_complete'] is False and opaque.body_bytes() == b'not a dictionary'
    assert transport.retained[0][1] == transport.raw


def test_external_raw_pin_is_checked_before_native_CSV_parse(plan, transport, monkeypatch):
    captured, _ = capture(plan, transport)
    def forbidden(*args): raise AssertionError('unpinned CSV parsed')
    monkeypatch.setattr(m, '_parse_dictionary', forbidden)
    refused('receipt', lambda: m.validate_capture(plan, captured, transport.raw + b' '))


@pytest.mark.parametrize('status', [301, 401, 403, 429, 500, 599])
def test_failed_HTTP_status_is_journaled_without_body_or_retry(plan, transport, status):
    transport.status = status; transport.fail_close = True
    refused('http_status', lambda: capture(plan, transport))
    assert len(transport.calls) == 1 and transport.read == transport.retained == []
    assert transport.events[-2][1]['http_status'] == status and transport.responses[0].closed
    assert m.validate_events([value for _, value in transport.events], plan)


@pytest.mark.parametrize('status', [True, False, None, 99, 600, '200'])
def test_unusable_status_is_unknown_not_zero(plan, transport, status):
    transport.status = status
    refused('http_status_unavailable', lambda: capture(plan, transport))
    assert not transport.read and not transport.retained
    assert transport.events[-1][1]['http_status'] is None


def test_request_exception_is_finite_and_never_retried(plan, transport):
    transport.fail_request = True
    refused('request_failed', lambda: capture(plan, transport))
    assert len(transport.calls) == 1 and KEY not in repr(transport.events)


def test_complete_body_survives_later_close_refusal(plan, transport):
    transport.fail_close = True
    refused('response_close', lambda: capture(plan, transport))
    assert transport.retained[0][1] == transport.raw
    assert transport.events[-1][1]['response_pin'] == m.pin(transport.raw)


@pytest.mark.parametrize('name', ['fields', 'from', 'to', 'years', 'status', 'indicator'])
def test_static_plan_has_no_query_expansion_or_bulk_fallback(plan, transport, name):
    plan['query'][name] = 'synthetic'
    refused('plan', lambda: capture(plan, transport))
    assert not transport.calls and not transport.events


@pytest.mark.parametrize('change', ['table', 'endpoint', 'limit', 'skip', 'sort', 'schema'])
def test_fixed_scope_cannot_be_replaced_by_caller(plan, transport, change):
    if change == 'table': plan['query']['tablename'] = 'actions'
    elif change == 'endpoint': plan['endpoint'] = 'https://synthetic.invalid/'
    elif change == 'schema': plan['schema'] = 'unknown'
    else: plan['query'][change] = 'other'
    refused('plan', lambda: capture(plan, transport))
    assert not transport.calls


@pytest.mark.parametrize('change', ['trust_env', 'verify', 'auth', 'proxy', 'header', 'hook', 'retry', 'callable'])
def test_unsafe_session_refuses_before_intent(plan, transport, change):
    session = transport.session
    if change == 'trust_env': session.trust_env = True
    elif change == 'verify': session.verify = False
    elif change == 'auth': session.auth = ('synthetic', 'synthetic')
    elif change == 'proxy': session.proxies['https'] = 'http://synthetic.invalid'
    elif change == 'header': session.headers['Authorization'] = 'synthetic'
    elif change == 'hook': session.hooks['response'] = []
    elif change == 'retry': session.adapters['https://'].max_retries = m.HTTPAdapter(max_retries=1).max_retries
    else: session.get = lambda *args, **kwargs: None
    refused('session', lambda: capture(plan, transport))
    assert not transport.calls and not transport.events


@pytest.mark.parametrize('change,code', [('host', 'prepared_identity'), ('path', 'prepared_identity'),
    ('query', 'prepared_identity'), ('body', 'prepared_identity'), ('header', 'prepared_identity'),
    ('redirect', 'response_identity'), ('compression', 'response_encoding'), ('length', 'response_bound'),
    ('chunk', 'response_stream'), ('oversize', 'response_bound')])
def test_transport_identity_and_byte_limits_are_not_metadata_waivers(plan, transport, change, code):
    def mutate(session, response):
        if change == 'host': response.request.url = response.request.url.replace('api.sharadar.com', 'synthetic.invalid')
        elif change == 'path': response.request.url = response.request.url.replace('/data/descriptions', '/data/actions')
        elif change == 'query': response.request.url += '&fields=indicator'
        elif change == 'body': response.request.body = b'synthetic'
        elif change == 'header': response.request.headers['X-Extra'] = 'synthetic'
        elif change == 'redirect': response.history = [requests.Response()]
    transport.mutation = mutate
    if change == 'compression': transport.headers['Content-Encoding'] = 'gzip'
    elif change == 'length': transport.headers['Content-Length'] = str(m.MAX_BODY + 1)
    elif change == 'chunk': transport.chunks = ['not-bytes']
    elif change == 'oversize': transport.chunks = [b'x' * (m.MAX_BODY + 1)]
    refused(code, lambda: capture(plan, transport))
    assert not transport.retained and transport.responses[0].closed and len(transport.calls) == 1


@pytest.mark.parametrize('form', ['literal', 'quoted', 'plus', 'json', 'header'])
def test_key_echo_never_enters_retention_or_receipt(plan, transport, form):
    variants = {'literal': KEY.encode(), 'quoted': quote(KEY, safe='').encode(),
        'plus': quote_plus(KEY, safe='').encode(), 'json': m.json.dumps(KEY)[1:-1].encode()}
    if form == 'header': transport.headers['X-Debug'] = KEY
    else: transport.raw += variants[form]
    refused('credential_echo', lambda: capture(plan, transport))
    assert not transport.retained and KEY not in repr(transport.events)


@pytest.mark.parametrize('choice', list(product((0, 1), repeat=4)))
def test_only_explicit_seven_logical_header_variants_are_accepted_and_original_is_preserved(choice):
    header = (('table', 'tablename')[choice[0]], 'indicator', ('isFilter', 'isfilter')[choice[1]],
        ('isPrimaryKey', 'isprimarykey')[choice[2]], 'title', 'description', ('unitType', 'unittype')[choice[3]])
    rows, summary = m._parse_dictionary(csv_bytes([row()], header))
    assert list(rows[0]) == list(header) and summary['original_header'] == list(header)
    assert rows[0][header[0]] == 'actiontypes' and summary['row_count'] == 1


@pytest.mark.parametrize('header', [('table', 'tablename', *m.FIELDS[2:]),
    ('table', 'indicator', 'isFilter', 'isfilter', 'title', 'description', 'unitType'),
    ('table', 'indicator', 'isFilter', 'isPrimaryKey', 'title', 'description', 'unknown'),
    (*m.FIELDS, 'extra'), m.FIELDS[:-1], ('table', 'indicator', 'isFilter', 'isPrimaryKey', 'title', 'title', 'unitType')])
def test_ambiguous_missing_or_extra_logical_headers_refuse(header):
    refused('header', lambda: m._parse_dictionary(csv_bytes([], header)))


def test_opaque_Unicode_multiline_whitespace_blank_and_unknown_flag_metadata_is_preserved():
    value = row(indicator='', title='  émetteur  ', description='line one\n第二行\r\n\tline three',
        unitType='', isFilter='', isPrimaryKey='unknown')
    rows, summary = m._parse_dictionary(csv_bytes([value]))
    assert rows == [value] and summary['empty_indicator_count'] == 1 and summary['empty_description_count'] == 0
    assert summary['filter_flag_counts'] == {'Y': 0, 'N': 0, 'empty': 1, 'other': 0}
    assert summary['primary_flag_counts'] == {'Y': 0, 'N': 0, 'empty': 0, 'other': 1}


def test_duplicate_primary_keys_and_conflicting_definitions_are_all_retained():
    values = [row(), row(), row(description='Different definition')]
    rows, summary = m._parse_dictionary(csv_bytes(values))
    assert rows == values and summary['row_count'] == 3 and summary['primary_key_count'] == 1
    assert summary['repeated_primary_key_row_count'] == 2 and summary['conflicting_definition_primary_key_count'] == 1


@pytest.mark.parametrize('count', [0, 999, 1000])
def test_cap_hit_is_a_completeness_stop_with_no_pagination(count):
    call = lambda: m._parse_dictionary(csv_bytes([row()] * count))
    if count == 1000: refused('row_cap', call)
    else: assert call()[1]['row_count'] == count


@pytest.mark.parametrize('value', ['actions', '', ' actiontypes', 'ActionTypes'])
def test_exact_dictionary_table_filter_membership_is_not_relaxed(value):
    refused('row_scope', lambda: m._parse_dictionary(csv_bytes([row(table=value)])))


@pytest.mark.parametrize('kind', ['nul', 'utf8', 'shape', 'field_bound'])
def test_malformed_or_oversized_CSV_remains_a_finite_stop(kind):
    raw = csv_bytes([row()])
    if kind == 'nul': raw += b'\x00'
    elif kind == 'utf8': raw += b'\xff'
    elif kind == 'shape': raw += b'too,few\n'
    else: raw = csv_bytes([row(description='x' * (m.MAX_FIELD + 1))])
    refused('csv', lambda: m._parse_dictionary(raw))


@pytest.mark.parametrize('marker,dispatches', [('request-00-intent', 0), ('request-00-status', 1), ('request-00-terminal', 1)])
def test_failed_journal_stops_and_never_claims_validation(plan, transport, marker, dispatches):
    transport.fail_journal = marker
    refused('journal', lambda: capture(plan, transport))
    assert len(transport.calls) == dispatches


@pytest.mark.parametrize('change,code', [('plan', 'plan'), ('session', 'session'), ('deadline', 'deadline')])
def test_late_refusal_keeps_committed_transport_terminal_without_second_journal(plan, transport, monkeypatch, change, code):
    original_journal, original_budget, expired = transport.journal, m._budget, [False]
    def budget(deadline):
        if expired[0]: raise m.Refused('deadline')
        return original_budget(deadline)
    monkeypatch.setattr(m, '_budget', budget)
    def journal(marker, event):
        original_journal(marker, event)
        if marker == 'request-00-terminal':
            if change == 'plan': plan['query']['sort'] = 'other'
            elif change == 'session': transport.session.verify = False
            else: expired[0] = True
    transport.journal = journal
    refused(code, lambda: capture(plan, transport))
    assert len(transport.calls) == len(transport.retained) == 1
    assert [marker for marker, _ in transport.events] == ['request-00-intent', 'request-00-status', 'request-00-terminal']
    assert transport.events[-1][1]['terminal_state'] == 'captured_body'
    assert m.validate_events([value for _, value in transport.events], m.plan_record())


@pytest.mark.parametrize('kind', ['throw', 'pin'])
def test_retention_failure_is_terminal(plan, transport, kind):
    transport.fail_retain = kind == 'throw'; transport.bad_pin = kind == 'pin'
    refused('retention', lambda: capture(plan, transport))
    assert len(transport.calls) == 1


@pytest.mark.parametrize('change', ['CSV_success', 'pin', 'plan', 'dispatch_count', 'extra', 'flag'])
def test_capture_receipt_cannot_be_upgraded_to_dictionary_or_authority(plan, transport, change):
    captured, _ = capture(plan, transport)
    if change == 'CSV_success': captured['CSV_validation_complete'] = True
    elif change == 'pin': captured['response_pin']['sha256'] = 'b' * 64
    elif change == 'plan': captured['plan_sha256'] = 'c' * 64
    elif change == 'dispatch_count': captured['application_dispatch_attempts'] = True
    elif change == 'extra': captured['rows'] = []
    else: captured['identity_admitted'] = True
    refused('receipt', lambda: m.validate_capture(plan, captured, transport.raw))


@pytest.mark.parametrize('change', ['count_bool', 'false_conflict', 'empty_primary', 'flag_sum', 'header_extra', 'unhashable_header', 'extra', 'authority'])
def test_closed_dictionary_receipt_refuses_false_counts_headers_or_admission(plan, transport, change):
    captured, _ = capture(plan, transport); result = m.validate_capture(plan, captured, transport.raw)
    if change == 'count_bool': result['row_count'] = True
    elif change == 'false_conflict': result['conflicting_definition_primary_key_count'] = 1
    elif change == 'empty_primary': result['primary_key_count'] = 0
    elif change == 'flag_sum': result['filter_flag_counts']['Y'] = 1
    elif change == 'header_extra': result['original_header'][-1] = 'extra'
    elif change == 'unhashable_header': result['original_header'][-1] = []
    elif change == 'extra': result['raw_dictionary'] = 'synthetic'
    else: result['point_in_time_proven'] = True
    refused('receipt', lambda: m.validate_dictionary_receipt(result, plan, captured))


def test_seven_transport_helpers_have_exact_bounded_inverse_to_frozen_source():
    old_raw = (ROOT / 'scripts/arv2_r335_sharadar_actions_v2.py').read_bytes()
    assert m.pin(old_raw) == m.TRANSPORT_SOURCE_PIN
    text = old_raw.decode(); tree = ast.parse(text)
    for name in ('_budget', 'configure_owned_session', '_session', '_url', '_identity', '_encodings', '_fetch'):
        original = ast.get_source_segment(text, next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name))
        current = inspect.getsource(getattr(m, name)).strip()
        if name == '_url':
            assert current.count("'/v1.0/data/descriptions'") == 1
            current = current.replace("'/v1.0/data/descriptions'", "'/v1.0/data/actions'", 1)
        assert current == original
    source_tree = ast.parse(inspect.getsource(m))
    imports = {alias.name.split('.')[0] for node in ast.walk(source_tree) if isinstance(node, ast.Import) for alias in node.names}
    imports |= {node.module.split('.')[0] for node in ast.walk(source_tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert imports.isdisjoint({'scripts', 'research', 'os', 'pathlib', 'subprocess', 'socket', 'keyring'})
    profile = m.profile_record()
    assert profile['maximum_application_dispatch_attempts'] == 1 and profile['maximum_body_bytes'] == 512 * 1024
    assert profile['maximum_observation_seconds'] == 150 and profile['retries'] == 0
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
