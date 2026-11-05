"""Synthetic ACTIONS boundary; network, DATA, USB and Keychains denied."""
import ast
import copy
import csv
import inspect
import io
from pathlib import Path
import pickle
import time
from types import SimpleNamespace as NS
from urllib.parse import quote, quote_plus

import pytest
import requests

from scripts import arv2_r335_sharadar_actions_v2 as m

KEY = 'synthetic-SECRET+/"1234'
ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


def refused(code, operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    assert m.finite(caught.value) == code
    assert KEY not in str(caught.value)


def csv_bytes(rows=(), *, fields=m.FIELDS):
    stream = io.StringIO(newline=''); writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(fields)
    for row in rows:
        writer.writerow([row[field] for field in fields] if type(row) is dict else row)
    return stream.getvalue().encode('utf8')


def action(*, ticker='SYN0', contra='SYN1', value='1', session='2024-01-02'):
    return {'date': session, 'action': 'uninterpreted_synthetic_event', 'ticker': ticker,
        'name': 'Synthetic issuer', 'value': value, 'contraticker': contra, 'contraname': 'Synthetic counterparty'}


@pytest.fixture
def plan():
    return {'schema': m.PLAN_SCHEMA, 'F_DATA_pin': dict(m.F_DATA_PIN), 'I_DATA_pin': dict(m.I_DATA_PIN),
        'explicit_tokens': ['SYN0', 'SYN1'], 'binding_lineage_sha256': 'a' * 64}


@pytest.fixture
def transport(monkeypatch):
    state = NS(calls=[], events=[], retained=[], responses=[], read=[], statuses={}, payloads={},
        headers={}, chunks=None, mutation=None, fail_request=None, fail_close=None,
        fail_retain=None, bad_retain_pin=False, fail_journal=None)
    session = m.configure_owned_session(requests.Session())
    def get(self, endpoint, **kwargs):
        ordinal = len(state.calls); state.calls.append((endpoint, copy.deepcopy(kwargs)))
        if state.fail_request == ordinal:
            raise RuntimeError(KEY)
        response = requests.Response(); response.status_code = state.statuses.get(ordinal, 200)
        response.request = self.prepare_request(requests.Request('GET', endpoint,
            params=kwargs['params'], headers=kwargs['headers']))
        response.url = response.request.url; response.history = []; response.headers.update(state.headers)
        response.closed = False
        token = kwargs['params'].get('contraticker')
        rows = [action()] if token is None else [action(ticker='OTHER', contra=token)]
        raw = state.payloads.get(ordinal, csv_bytes(rows))
        def content(chunk_size):
            state.read.append(ordinal)
            yield from state.chunks if state.chunks is not None else (raw,)
        def close():
            response.closed = True
            if state.fail_close == ordinal:
                raise RuntimeError(KEY)
        response.iter_content, response.close = content, close
        state.responses.append(response)
        if state.mutation is not None:
            state.mutation(self, response, ordinal)
        return response
    monkeypatch.setattr(requests.Session, 'get', get)
    def journal(marker, event):
        if marker == state.fail_journal:
            raise RuntimeError(KEY)
        state.events.append((marker, copy.deepcopy(event)))
    def retain(ordinal, raw, metadata):
        state.retained.append((ordinal, raw, copy.deepcopy(metadata)))
        if ordinal == state.fail_retain:
            raise RuntimeError(KEY)
        return {'byte_count': len(raw), 'sha256': '0' * 64} if state.bad_retain_pin else m.pin(raw)
    state.session, state.journal, state.retain = session, journal, retain
    return state


def observe(plan, transport):
    return m.observe(plan, session=transport.session, api_key=KEY, journal=transport.journal,
        retain_response=transport.retain, deadline=time.monotonic() + 299)


def test_fixed_documented_queries_counts_private_capture_and_false_flags(plan, transport):
    result, opaque = observe(plan, transport)
    assert result['application_dispatch_attempts'] == 3 and result['provider_request_count'] is None
    assert result['http_statuses'] == [200] * 3 and result['row_count_including_query_overlap'] == 3
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    assert len(transport.calls) == len(transport.retained) == 3 and len(transport.events) == 9
    assert all(response.closed for response in transport.responses)
    for ordinal, (endpoint, kwargs) in enumerate(transport.calls):
        assert endpoint == m.ENDPOINT
        assert kwargs['allow_redirects'] is False and kwargs['stream'] is kwargs['verify'] is True
        assert kwargs['headers'] == {'Accept-Encoding': 'identity'} and 0 < kwargs['timeout'] <= 30
        query = kwargs['params']
        assert query['api_key'] == KEY and query['from'] == m.FIRST and query['to'] == m.LAST
        assert query['fields'] == ','.join(m.FIELDS) and query['format'] == 'csv'
        assert query['skip'] == '0' and query['limit'] == '1000' and query['sort'] == 'date.asc'
        assert (query['ticker'] == 'SYN0,SYN1' and 'contraticker' not in query) if ordinal == 0 else (
            query['contraticker'] == plan['explicit_tokens'][ordinal - 1] and 'ticker' not in query)
    assert m.validate_capture(plan, result, opaque.bytes_tuple()) == result
    events = [row for _, row in transport.events]
    assert m.validate_events(events, plan, result) == events
    assert b'SYN0' not in m.canonical(result) and KEY not in repr(result)
    assert 'SYN' not in repr(opaque) and KEY not in repr(opaque)
    with pytest.raises(TypeError):
        pickle.dumps(opaque)


def test_retention_precedes_CSV_validation_and_preserves_bad_200_body(plan, transport):
    transport.payloads[1] = b'not-a-csv'
    refused('csv', lambda: observe(plan, transport))
    assert len(transport.calls) == len(transport.retained) == 2
    assert transport.retained[1][1] == b'not-a-csv'
    terminal = transport.events[-1][1]
    assert terminal['event'] == 'terminal' and terminal['terminal_state'] == 'refused'
    assert terminal['http_status'] == 200 and terminal['response_pin'] == m.pin(b'not-a-csv')
    assert m.validate_events([row for _, row in transport.events], plan)


def test_close_failure_preserves_complete_private_status200_evidence(plan, transport):
    transport.fail_close = 0
    refused('response_close', lambda: observe(plan, transport))
    assert len(transport.calls) == len(transport.retained) == 1 and transport.responses[0].closed
    assert transport.events[-1][1]['response_pin'] == m.pin(transport.retained[0][1])


@pytest.mark.parametrize('status', [301, 401, 403, 429, 500, 599])
def test_failed_status_is_journaled_before_any_body_and_prior_responses_survive(plan, transport, status):
    transport.statuses[1] = status; transport.fail_close = 1
    refused('http_status', lambda: observe(plan, transport))
    assert transport.read == [0] and [row[0] for row in transport.retained] == [0]
    assert len(transport.calls) == 2 and transport.responses[-1].closed
    assert transport.events[-2][1]['event'] == 'status'
    assert transport.events[-2][1]['http_status'] == status
    assert transport.events[-1][1]['response_pin'] is None
    assert m.validate_events([row for _, row in transport.events], plan)


@pytest.mark.parametrize('status', [True, False, None, '403', 99, 600])
def test_unknown_status_is_not_zero_or_a_failed_body_read(plan, transport, status):
    transport.statuses[0] = status
    refused('http_status_unavailable', lambda: observe(plan, transport))
    assert transport.read == transport.retained == [] and len(transport.calls) == 1
    assert transport.events[-1][1]['http_status'] is None
    assert transport.events[-1][1]['http_status_state'] == 'unavailable'


def test_request_exception_keeps_only_finite_unknown_status_and_no_retry(plan, transport):
    transport.fail_request = 0
    refused('request_failed', lambda: observe(plan, transport))
    assert len(transport.calls) == 1 and transport.retained == []
    assert [row['event'] for _, row in transport.events] == ['intent', 'status', 'terminal']
    assert KEY not in repr(transport.events)


@pytest.mark.parametrize('change', ['count', 'duplicate', 'order', 'token_path', 'extra', 'F_pin', 'I_pin', 'lineage'])
def test_closed_private_plan_refuses_scope_expansion_before_request(plan, transport, change):
    if change == 'count': plan['explicit_tokens'] = sorted('SYN' + str(index) for index in range(17))
    elif change == 'duplicate': plan['explicit_tokens'] = ['SYN0', 'SYN0']
    elif change == 'order': plan['explicit_tokens'].reverse()
    elif change == 'token_path': plan['explicit_tokens'] = ['../SYN0']
    elif change == 'extra': plan['from'] = '2000-01-01'
    elif change in ('F_pin', 'I_pin'): plan[change[0] + '_DATA_pin']['sha256'] = 'b' * 64
    else: plan['binding_lineage_sha256'] = True
    refused('plan', lambda: observe(plan, transport))
    assert transport.calls == transport.events == transport.retained == []


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
    refused('session', lambda: observe(plan, transport))
    assert transport.calls == transport.events == []


@pytest.mark.parametrize('change,code', [('host', 'prepared_identity'), ('path', 'prepared_identity'),
    ('query', 'prepared_identity'), ('request_body', 'prepared_identity'), ('request_header', 'prepared_identity'),
    ('redirect', 'response_identity'), ('response_url', 'prepared_identity'), ('compression', 'response_encoding'),
    ('length', 'response_bound'), ('short', 'response_bound'), ('chunk', 'response_stream'), ('oversize', 'response_bound')])
def test_response_transport_identity_and_bounds_refuse_without_retention(plan, transport, change, code):
    def mutate(session, response, ordinal):
        if change == 'host': response.request.url = response.request.url.replace('api.sharadar.com', 'synthetic.invalid')
        elif change == 'path': response.request.url = response.request.url.replace('/data/actions', '/data/stocks')
        elif change == 'query': response.request.url += '&extra=1'
        elif change == 'request_body': response.request.body = b'synthetic'
        elif change == 'request_header': response.request.headers['X-Extra'] = 'synthetic'
        elif change == 'redirect': response.history = [requests.Response()]
        elif change == 'response_url': response.url = response.url.replace('api.sharadar.com', 'synthetic.invalid')
    transport.mutation = mutate
    if change == 'compression': transport.headers['Content-Encoding'] = 'gzip'
    elif change == 'length': transport.headers['Content-Length'] = str(m.MAX_BODY + 1)
    elif change == 'short': transport.headers['Content-Length'] = '1'
    elif change == 'chunk': transport.chunks = ['not-bytes']
    elif change == 'oversize': transport.chunks = [b'x' * (m.MAX_BODY + 1)]
    refused(code, lambda: observe(plan, transport))
    assert len(transport.calls) == 1 and transport.responses[0].closed and not transport.retained
    if change in ('host', 'path', 'query', 'request_body', 'request_header', 'redirect', 'response_url'):
        assert transport.read == [] and transport.events[-1][1]['http_status'] is None


@pytest.mark.parametrize('form', ['literal', 'quoted', 'plus', 'lower_percent', 'json', 'header'])
def test_secret_echo_never_enters_private_retention_or_public_evidence(plan, transport, form):
    variants = {'literal': KEY.encode(), 'quoted': quote(KEY, safe='').encode(), 'plus': quote_plus(KEY, safe='').encode(),
        'lower_percent': m.re.sub(rb'%[0-9A-Fa-f]{2}', lambda match: match.group().lower(), quote(KEY, safe='').encode()),
        'json': m.json.dumps(KEY)[1:-1].encode()}
    if form == 'header': transport.headers['X-Debug'] = KEY
    else: transport.payloads[0] = csv_bytes([action()]) + variants[form]
    refused('credential_echo', lambda: observe(plan, transport))
    assert not transport.retained and KEY not in repr(transport.events)


@pytest.mark.parametrize('value', ['', '0', '-1.25', '+3', '1e-8', '1E+12', '.5', '12.'])
def test_nullable_finite_signed_decimal_event_values_are_uninterpreted(value):
    rows, counts = m.parse_response(csv_bytes([action(value=value)]), role='ticker_union',
        token='SYN0,SYN1', explicit_tokens=('SYN0', 'SYN1'))
    assert rows[0]['value'] == value and counts['row_count'] == 1


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Inf', '1_000', '1,000', '1e99999', ' 1'])
def test_nonfinite_or_malformed_numeric_event_values_refuse_without_coercion(value):
    refused('csv' if value.startswith(' ') else 'row_value', lambda: m.parse_response(csv_bytes([action(value=value)]),
        role='ticker_union', token='SYN0,SYN1', explicit_tokens=('SYN0', 'SYN1')))


def test_true_six_field_primary_key_retains_conflicting_value_and_distinct_contraname_rows():
    rows = [action(), action(), action(value='2'), {**action(), 'contraname': 'Different synthetic counterparty'}]
    parsed, counts = m.parse_response(csv_bytes(rows), role='ticker_union', token='SYN0,SYN1', explicit_tokens=('SYN0', 'SYN1'))
    assert parsed == rows and m.PRIMARY_FIELDS == ('date', 'action', 'ticker', 'name', 'contraticker', 'contraname')
    assert counts == {'row_count': 4, 'primary_key_count': 2, 'repeated_primary_key_row_count': 2,
        'conflicting_value_primary_key_count': 1}
    _, only_name = m.parse_response(csv_bytes([action(), rows[-1]]), role='ticker_union', token='SYN0,SYN1', explicit_tokens=('SYN0', 'SYN1'))
    assert only_name == {'row_count': 2, 'primary_key_count': 2, 'repeated_primary_key_row_count': 0,
        'conflicting_value_primary_key_count': 0}


@pytest.mark.parametrize('count', [0, 999, 1000])
def test_empty_rows_are_observation_but_row_limit_hit_is_completeness_stop(count):
    operation = lambda: m.parse_response(csv_bytes([action()] * count), role='ticker_union',
        token='SYN0,SYN1', explicit_tokens=('SYN0', 'SYN1'))
    if count == 1000: refused('row_cap', operation)
    else: assert operation()[1]['row_count'] == count


@pytest.mark.parametrize('change,code', [('wrong_filter', 'row_scope'), ('wrong_contra', 'row_scope'),
    ('early', 'row_date'), ('late', 'row_date'), ('malformed_date', 'row_date'), ('order', 'row_date'),
    ('header', 'csv'), ('extra', 'csv'), ('nul', 'csv'), ('invalid_utf8', 'csv')])
def test_action_filter_window_order_and_closed_seven_column_schema(change, code):
    rows = [action()]; role, token = 'ticker_union', 'SYN0,SYN1'
    if change == 'wrong_filter': rows[0]['ticker'] = 'OTHER'
    elif change == 'wrong_contra': role, token = 'contraticker_single', 'SYN0'
    elif change == 'early': rows[0]['date'] = '2023-10-31'
    elif change == 'late': rows[0]['date'] = '2026-10-14'
    elif change == 'malformed_date': rows[0]['date'] = '2024-1-2'
    elif change == 'order': rows = [action(session='2024-02-01'), action()]
    raw = csv_bytes(rows)
    if change == 'header': raw = raw.replace(b'action,', b'action,action,', 1)
    elif change == 'extra': raw += b'too,few,fields\n'
    elif change == 'nul': raw += b'\x00'
    elif change == 'invalid_utf8': raw += b'\xff'
    refused(code, lambda: m.parse_response(raw, role=role, token=token, explicit_tokens=('SYN0', 'SYN1')))


@pytest.mark.parametrize('kind', ['throw', 'bad_pin'])
def test_retention_failure_is_terminal_and_never_repeated(plan, transport, kind):
    if kind == 'throw': transport.fail_retain = 0
    else: transport.bad_retain_pin = True
    refused('retention', lambda: observe(plan, transport))
    assert len(transport.calls) == len(transport.retained) == 1


def test_retention_callback_cannot_change_the_expected_original_body_pin(plan, transport):
    def mutate(ordinal, raw, metadata):
        metadata['body_pin']['sha256'] = '0' * 64
        return metadata['body_pin']
    transport.retain = mutate
    refused('retention', lambda: observe(plan, transport))
    assert len(transport.calls) == 1


@pytest.mark.parametrize('marker,requests', [('request-00-intent', 0), ('request-00-status', 1), ('request-00-terminal', 1)])
def test_journal_failure_stops_before_any_later_request(plan, transport, marker, requests):
    transport.fail_journal = marker
    refused('journal', lambda: observe(plan, transport))
    assert len(transport.calls) == requests


def test_plan_mutation_during_transport_is_terminal_with_no_automatic_alias_expansion(plan, transport):
    transport.mutation = lambda *args: plan['explicit_tokens'].append('SYN2')
    refused('changed', lambda: observe(plan, transport))
    assert len(transport.calls) == 1 and not transport.retained


def test_aggregate_bound_spends_prefix_without_another_dispatch(plan, transport, monkeypatch):
    first = csv_bytes([action()]); second = csv_bytes([action(ticker='OTHER', contra='SYN0')])
    monkeypatch.setattr(m, 'MAX_AGGREGATE', len(first) + len(second))
    refused('aggregate_bound', lambda: observe(plan, transport))
    assert len(transport.calls) == len(transport.retained) == 2


@pytest.mark.parametrize('deadline', [float('nan'), float('inf'), True, -1, 0, '300'])
def test_bad_deadline_refuses_before_any_request(plan, transport, deadline):
    refused('deadline', lambda: m.observe(plan, session=transport.session, api_key=KEY,
        journal=transport.journal, retain_response=transport.retain, deadline=deadline))
    assert not transport.calls and not transport.events


@pytest.mark.parametrize('key', [None, True, '', 'short', ' synthetic-key', 'synthetic-key\n', 'é' * 20])
def test_bad_credential_never_reaches_events_or_request(plan, transport, key):
    refused('credential', lambda: m.observe(plan, session=transport.session, api_key=key,
        journal=transport.journal, retain_response=transport.retain, deadline=time.monotonic() + 299))
    assert not transport.calls and not transport.events


def test_receipt_counts_cannot_invent_primary_keys_or_conflicts(plan, transport):
    result, _ = observe(plan, transport)
    result['responses'][0]['conflicting_value_primary_key_count'] = 1
    refused('receipt', lambda: m.validate_receipt(result, plan))
    result['responses'][0]['conflicting_value_primary_key_count'] = 0
    result['responses'][0]['primary_key_count'] = 0
    result['responses'][0]['repeated_primary_key_row_count'] = 1
    refused('receipt', lambda: m.validate_receipt(result, plan))


@pytest.mark.parametrize('change', ['boolean_status', 'unknown', 'raw_row', 'count', 'plan', 'pin', 'events_order', 'events_status'])
def test_closed_receipts_and_events_refuse_false_success_or_raw_content(plan, transport, change):
    result, opaque = observe(plan, transport); events = [row for _, row in transport.events]
    if change == 'boolean_status': result['http_statuses'][0] = True
    elif change == 'unknown': result['source_granted'] = True
    elif change == 'raw_row': result['responses'][0]['raw'] = 'SYNTHETIC'
    elif change == 'count': result['application_dispatch_attempts'] = 2
    elif change == 'plan': result['plan_sha256'] = 'b' * 64
    elif change == 'pin': result['responses'][0]['body_pin']['sha256'] = '0' * 64
    elif change == 'events_order': events[0], events[1] = events[1], events[0]
    else: events[1]['http_status'] = 403
    if change.startswith('events'): refused('event', lambda: m.validate_events(events, plan, result))
    else:
        with pytest.raises(m.Refused): m.validate_capture(plan, result, opaque.bytes_tuple())


def test_maximum_sixteen_frozen_tokens_uses_exactly_seventeen_bounded_requests(plan, transport):
    plan['explicit_tokens'] = ['SYN' + str(index).zfill(2) for index in range(16)]
    transport.payloads[0] = csv_bytes([action(ticker='SYN00', contra='SYN01')])
    result, _ = observe(plan, transport)
    assert result['application_dispatch_attempts'] == len(transport.calls) == 17
    assert len(transport.events) == 51


def test_source_is_pure_and_fixed_session_guards_are_exact_frozen_copies():
    source = inspect.getsource(m); tree = ast.parse(source)
    forbidden = {'pathlib', 'os', 'subprocess', 'socket', 'scripts', 'research', 'keyring'}
    imported = {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert imported.isdisjoint(forbidden)
    old_raw = (ROOT / 'scripts/arv2_r298_sharadar_reference_observation.py').read_bytes()
    assert m.sha(old_raw) == '72329cc48ce39eb2ccc3d61bca8fc79624a685704f1fa7fd96c5198dd882950f'
    old_text = old_raw.decode(); old_tree = ast.parse(old_text)
    for name in ('configure_owned_session', '_session', '_encodings'):
        old_node = next(node for node in old_tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
        assert inspect.getsource(getattr(m, name)).strip() == ast.get_source_segment(old_text, old_node).strip()
    old_fetch = ast.get_source_segment(old_text, next(node for node in old_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == '_fetch'))
    current_fetch = inspect.getsource(m._fetch)
    first, last = '            headers = response.headers\n', '        _session(session); _budget(deadline)\n'
    assert old_fetch[old_fetch.index(first):old_fetch.index(last)] == current_fetch[current_fetch.index(first):current_fetch.index(last)]
    profile = m.profile_record()
    assert profile['maximum_observation_seconds'] == 300 and profile['retries'] == 0
    assert profile['row_limit'] == 1000 and profile['accepted_rows_strictly_less_than_limit'] is True
    assert all(profile[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('contra', ['lowercase', 'SYN0 SYN1', 'SYN0/SYN1', 'SYN0, SYN1', 'SYN0:legacy', 'émetteur'])
def test_returned_nonquery_contra_text_is_opaque_and_retained_verbatim(contra, plan, transport):
    raw = csv_bytes([action(contra=contra)])
    parsed, counts = m.parse_response(raw, role='ticker_union', token='SYN0,SYN1', explicit_tokens=('SYN0', 'SYN1'))
    assert parsed[0]['contraticker'] == contra and counts['row_count'] == 1
    transport.payloads[0] = raw
    receipt, opaque = observe(plan, transport)
    assert transport.retained[0][1] == opaque.bytes_tuple()[0] == raw
    assert len(transport.calls) == 3
    assert [kwargs['params'].get('contraticker') for _, kwargs in transport.calls] == [None, 'SYN0', 'SYN1']
    assert m.validate_capture(plan, receipt, opaque.bytes_tuple()) == receipt
    assert all(receipt[key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize('contra', ['SYN0 SYN1', 'syn0', 'SYN0/SYN1', 'OTHER'])
def test_scalar_contra_filter_still_requires_exact_unchanged_request_token(contra):
    refused('row_scope', lambda: m.parse_response(csv_bytes([action(contra=contra)]),
        role='contraticker_single', token='SYN0', explicit_tokens=('SYN0', 'SYN1')))


@pytest.mark.parametrize('contra', [' SYN0', 'SYN0 ', 'SYN0\nSYN1', 'SYN0\x7f', 'X' * (m.MAX_FIELD + 1)])
def test_opaque_metadata_keeps_all_existing_whitespace_control_and_length_guards(contra):
    refused('csv', lambda: m.parse_response(csv_bytes([action(contra=contra)]),
        role='ticker_union', token='SYN0,SYN1', explicit_tokens=('SYN0', 'SYN1')))


@pytest.mark.parametrize('ticker', ['OTHER', 'SYN0/SYN1', 'syn0'])
def test_primary_ticker_grammar_and_selected_query_membership_are_unchanged(ticker):
    refused('row_scope', lambda: m.parse_response(csv_bytes([action(ticker=ticker, contra='opaque other')]),
        role='ticker_union', token='SYN0,SYN1', explicit_tokens=('SYN0', 'SYN1')))


def test_response_metadata_never_relaxes_query_token_validation_or_reuses_old_plan_schema(plan, transport):
    plan['explicit_tokens'] = ['SYN0/SYN1']
    refused('plan', lambda: observe(plan, transport))
    plan['explicit_tokens'] = ['SYN0', 'SYN1']
    plan['schema'] = 'arv2-r335-sharadar-actions-v1-plan'
    refused('plan', lambda: observe(plan, transport))
    assert not transport.calls


def test_exact_bounded_inverse_restores_every_byte_of_frozen_v1():
    old = (ROOT / 'scripts/arv2_r335_sharadar_actions.py').read_bytes()
    current = (ROOT / 'scripts/arv2_r335_sharadar_actions_v2.py').read_bytes()
    assert len(old) == 31102 and m.sha(old) == '2d40d2c260a3fa2b484608df5ec43eaaad901848c345e1a60a215bf164c23d29'
    changes = [
        ('Bounded injected ACTIONS discovery; no source reads or operational caller.',
            'Bounded ACTIONS v2 preserves non-query contra text without alias admission.'),
        ('Corporate-action rows remain current-vintage observations, never identity,\nalias, payoff, price, source or trading admission.',
            'Returned non-query contra text stays opaque and verbatim under existing field\nbounds; it never creates a query token or alias. Corporate-action rows remain\ncurrent-vintage observations, never identity, payoff, price or trading admission.'),
        ("SCHEMA = 'arv2-r335-sharadar-actions-v1'", "SCHEMA = 'arv2-r335-sharadar-actions-v2'\nV1_SOURCE_PIN = {'byte_count': 31102, 'sha256': '2d40d2c260a3fa2b484608df5ec43eaaad901848c345e1a60a215bf164c23d29'}"),
        ("require(_ticker(row['ticker']) and (not row['contraticker'] or _ticker(row['contraticker']))", "require(_ticker(row['ticker'])"),
        ("        'primary_key_fields': list(PRIMARY_FIELDS),", "        'v1_source_pin': dict(V1_SOURCE_PIN),\n        'source_delta': 'only_returned_nonquery_contra_stock_ticker_grammar_removed',\n        'returned_contra_text': 'opaque_bounded_trim_control_checked_verbatim_never_split_normalized_aliased_or_queried',\n        'scalar_contra_filter': 'returned_contra_must_still_equal_exact_validated_request_token',\n        'primary_key_fields': list(PRIMARY_FIELDS),"),
    ]
    restored = current
    for before, after in reversed(changes):
        before, after = before.encode(), after.encode()
        assert restored.count(after) == 1
        restored = restored.replace(after, before, 1)
    assert restored == old
    assert m.profile_record()['v1_source_pin'] == {'byte_count': len(old), 'sha256': m.sha(old)}
    assert m.PLAN_SCHEMA == 'arv2-r335-sharadar-actions-v2-plan'
    assert m.EVENT_SCHEMA == 'arv2-r335-sharadar-actions-v2-event'
