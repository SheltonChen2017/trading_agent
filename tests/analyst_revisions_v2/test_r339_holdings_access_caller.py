"""Synthetic R339 access orchestration; no credentials or production DATA."""
import copy
from contextlib import ExitStack
import io
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import time
from types import SimpleNamespace as NS

import pytest
from scripts import arv2_r339_holdings_discovery as core
from scripts import probe_arv2_r339_holdings_access as m

SECRET = 'SYNTHETIC-PRIVATE-KEY-NEVER-RETAIN'


def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64,
        profile_sha256='c' * 64, actual_parent_exit=None)


def deadline(): return time.monotonic() + 60


def refuse(code, call):
    with pytest.raises(m.Refused) as caught: call()
    assert m.finite(caught.value) == code


def body(request, *, populated=False):
    if request['provider'] == 'massive':
        rows = [{'composite_ticker': request['fund'],
            'effective_date': request['effective_date']}] if populated else []
        return core.canonical({'status': 'OK', 'results': rows, 'count': len(rows)})
    return core.canonical([{'symbol': request['fund'], 'date': '2021-09-30',
        'year': 2021, 'quarter': 3}] if populated else [])


class Security:
    @staticmethod
    def snapshot(fd): return {'acl_empty': True, 'xattrs': {}}


class Credentials:
    class KeychainUnavailable(ValueError): pass

    def __init__(self, unavailable=()):
        self.lookups, self.unavailable = [], set(unavailable)

    def load_key(self, provider, *, timeout_seconds):
        assert 0 < timeout_seconds <= 20
        self.lookups.append(provider)
        if provider in self.unavailable: raise self.KeychainUnavailable('unavailable')
        return SECRET


class MemoryStore:
    def __init__(self): self.items, self.order = {}, []

    def verify(self): self.order.append('verify')

    def write(self, name, raw):
        assert name not in self.items
        assert type(raw) is bytes and SECRET.encode() not in raw
        self.items[name] = raw
        self.order.append(name)
        return m.pin(raw)


@pytest.fixture(autouse=True)
def reset_globals(monkeypatch):
    monkeypatch.setattr(m, 'DEADLINE_FIRED', False)
    monkeypatch.setattr(m, 'CLAIM_STATE', 'unallocated')
    monkeypatch.setattr(m, 'MODULES', {'core': core})
    monkeypatch.setattr(m, 'ENTRY_DEADLINE', deadline())
    if hasattr(m, 'PROGRESS'): monkeypatch.setattr(m, 'PROGRESS', None)


def observation(monkeypatch, *, populated=False, fail_ordinal=None,
        failure='status', unavailable=()):
    store, credentials, sent = MemoryStore(), Credentials(unavailable), []
    roles = {'core': core, 'credentials': credentials}
    def send(request, key, bound, row):
        assert key == SECRET and bound > time.monotonic()
        assert 'credential-' + request['provider'] + '-started.json' in store.items
        assert 'send-' + str(request['ordinal']) + '-started.json' in store.items
        assert request['ordinal'] not in sent
        sent.append(request['ordinal'])
        if request['ordinal'] == fail_ordinal:
            if failure == 'status':
                row['status_code'] = 403
                return 403, None
            if failure == 'transport': raise OSError(SECRET)
            if failure == 'deadline': raise m.RunDeadline()
            if failure == 'response':
                row['status_code'] = 200
                raise m.Refused('output')
            if failure == 'close':
                row['status_code'] = 403
                raise OSError(SECRET)
            if failure == 'wrong_date':
                row['status_code'] = 200
                return 200, core.canonical({'status': 'OK', 'results': [{
                    'composite_ticker': request['fund'], 'effective_date': '2021-10-28'}]})
            if failure == 'error_200':
                row['status_code'] = 200
                return 200, b'{"status":"ERROR","error":"private error"}'
            if failure == 'echo':
                row['status_code'] = 200
                return 200, core.canonical({'status': 'OK', 'results': [], 'request_id': SECRET})
        row['status_code'] = 200
        return 200, body(request, populated=populated)
    monkeypatch.setattr(m, 'request_once', send)
    result = m.observe(roles, store, args(), deadline())
    return result, store, credentials, sent


@pytest.mark.parametrize('populated', [False, True])
def test_real_helper_success_all24_and_one_keychain_lookup_each(monkeypatch, populated):
    result, store, credentials, sent = observation(monkeypatch, populated=populated)
    assert m.validate_result(result, args(), core) is result
    assert sent == list(range(24))
    assert credentials.lookups == ['massive', 'fmp']
    assert result['credential_lookup_attempts'] == {'massive': 1, 'fmp': 1}
    assert result['application_send_intents'] == 24
    assert result['provider_request_count'] is None
    assert {row['terminal'] for row in result['observations']} == {
        'valid_sample' if populated else 'valid_empty'}
    assert all(row['summary']['result_count'] == int(populated)
        for row in result['observations'])
    assert all(result[name] is False for name in m.FLAGS)
    serialized = m.canonical(result) + b''.join(store.items.values())
    assert SECRET.encode() not in serialized and b'private error' not in serialized
    assert not any(key in result for key in ('response_body_sha256', 'raw_body', 'rows'))


@pytest.mark.parametrize('failure,terminal', [
    ('status', 'http_status'), ('transport', 'transport_refused'),
    ('response', 'response_refused'), ('close', 'response_refused'),
    ('wrong_date', 'schema_refused'), ('error_200', 'schema_refused'),
    ('echo', 'schema_refused')])
def test_provider_refusal_stops_only_its_remaining_requests(monkeypatch, failure, terminal):
    result, store, credentials, sent = observation(monkeypatch, fail_ordinal=0, failure=failure)
    m.validate_result(result, args(), core)
    assert sent == [0, *range(16, 24)]
    assert result['application_send_intents'] == 9
    assert result['observations'][0]['terminal'] == terminal
    assert all(row['terminal'] == 'skipped_after_provider_stop'
        and row['status_code'] is None and not row['send_intent_recorded']
        for row in result['observations'][1:16])
    assert all(row['terminal'] == 'valid_empty' for row in result['observations'][16:])
    assert credentials.lookups == ['massive', 'fmp']
    assert not any('send-' + str(i) + '-started.json' in store.items for i in range(1, 16))
    assert SECRET.encode() not in m.canonical(result)
    if failure in ('response', 'close'):
        assert result['observations'][0]['status_code'] == (200 if failure == 'response' else 403)


def test_mid_provider_failure_preserves_prior_observations_and_never_retries(monkeypatch):
    result, _, _, sent = observation(monkeypatch, populated=True, fail_ordinal=4)
    m.validate_result(result, args(), core)
    assert sent == [*range(5), *range(16, 24)]
    assert result['application_send_intents'] == 13
    assert [row['terminal'] for row in result['observations'][:5]] == ['valid_sample'] * 4 + ['http_status']
    assert all(row['terminal'] == 'skipped_after_provider_stop' for row in result['observations'][5:16])


@pytest.mark.parametrize('unavailable,send_count', [
    (('massive',), 8), (('fmp',), 16), (('massive', 'fmp'), 0)])
def test_keychain_refusal_no_send_intent_not_zero_contact_proof(monkeypatch, unavailable, send_count):
    result, store, credentials, sent = observation(monkeypatch, unavailable=unavailable)
    m.validate_result(result, args(), core)
    assert len(sent) == result['application_send_intents'] == send_count
    assert credentials.lookups == ['massive', 'fmp']
    assert result['provider_request_count'] is None
    for provider in unavailable:
        first = 0 if provider == 'massive' else 16
        assert result['observations'][first]['terminal'] == 'credentials_unavailable'
        assert 'send-' + str(first) + '-started.json' not in store.items


@pytest.mark.parametrize('key', ['', 'x' * 7, 'x' * (core.MAX_CREDENTIAL + 1), None, True])
def test_incompatible_credential_is_refused_before_send_marker(monkeypatch, key):
    credentials, store = Credentials(), MemoryStore()
    monkeypatch.setattr(credentials, 'load_key', lambda *a, **kw: key)
    def forbidden(*a): raise AssertionError('credential must refuse before dispatch')
    monkeypatch.setattr(m, 'request_once', forbidden)
    result = m.observe({'core': core, 'credentials': credentials}, store, args(), deadline())
    m.validate_result(result, args(), core)
    assert result['application_send_intents'] == 0
    assert not any(name.startswith('send-') for name in store.items)


def test_global_alarm_is_not_converted_to_provider_stop(monkeypatch):
    with pytest.raises(m.RunDeadline): observation(monkeypatch, fail_ordinal=0, failure='deadline')


class Response:
    def __init__(self, *, status=200, raw=b'[]', headers=None):
        self.status, self.raw, self.headers = status, raw, dict(headers or {})
        self.explicit_reads, self.closed, self.close_error = [], False, None

    def getheader(self, name, default=None): return self.headers.get(name, default)

    def read1(self, count):
        self.explicit_reads.append(count)
        answer, self.raw = self.raw[:count], self.raw[count:]
        return answer

    def close(self):
        self.closed = True
        if self.close_error is not None: raise self.close_error


@pytest.fixture
def transport(monkeypatch):
    state = NS(response=Response(headers={'Content-Type': 'application/json'}),
        connections=[], commands=[], tls=NS(check_hostname=True, verify_mode=ssl.CERT_REQUIRED,
            keylog_filename=None), tunnel=None, error=None)
    class Connection:
        def __init__(self, host, port, *, timeout, context):
            assert context is state.tls and 0 < timeout <= m.REQUEST_SECONDS
            self.host, self.port, self._tunnel_host, self.debuglevel = host, port, state.tunnel, 0
            self.closed = False
            state.connections.append(self)
        def request(self, method, target, *, headers):
            state.commands.append((method, target, dict(headers)))
            if state.error is not None: raise state.error
        def getresponse(self): return state.response
        def close(self): self.closed = True
    monkeypatch.setattr(m.ssl, 'create_default_context', lambda: state.tls)
    monkeypatch.setattr(m.http.client, 'HTTPSConnection', Connection)
    state.row = {'status_code': None}
    state.run = lambda ordinal=0: m.request_once(core.request_plan()[ordinal], SECRET,
        deadline(), state.row)
    return state


@pytest.mark.parametrize('provider,ordinal', [('massive', 0), ('fmp', 16)])
def test_direct_tls_one_request_exact_origin_and_key_location(transport, provider, ordinal):
    request = core.request_plan()[ordinal]
    transport.response.raw = body(request)
    status, raw = transport.run(ordinal)
    assert status == transport.row['status_code'] == 200 and raw == body(request)
    assert len(transport.connections) == len(transport.commands) == 1
    connection = transport.connections[0]
    assert connection.host == m.ORIGINS[provider] and connection.port == 443 and connection.closed
    assert transport.response.closed
    method, target, headers = transport.commands[0]
    assert method == 'GET' and target.startswith(request['path'] + '?')
    assert headers['Accept-Encoding'] == 'identity'
    if provider == 'massive':
        assert headers['Authorization'] == 'Bearer ' + SECRET and SECRET not in target
    else:
        assert 'Authorization' not in headers and 'apikey=' + SECRET in target
    assert not any(key.lower() in ('cookie', 'proxy-authorization') for key in headers)


@pytest.mark.parametrize('status', [201, 301, 302, 401, 403, 429, 500, 599])
def test_non200_no_explicit_body_read_and_no_redirect(transport, status):
    transport.response.status = status
    transport.response.raw = SECRET.encode()
    transport.response.headers = {'Location': 'https://elsewhere.invalid/' + SECRET,
        'Content-Type': 'text/html', 'Content-Encoding': 'gzip'}
    assert transport.run() == (status, None)
    assert transport.row['status_code'] == status and transport.response.explicit_reads == []
    assert len(transport.commands) == 1
    assert transport.response.closed and transport.connections[0].closed


@pytest.mark.parametrize('status', [True, '403', None, 99, 600])
def test_invalid_status_finite_before_explicit_body(transport, status):
    transport.response.status = status
    refuse('output', transport.run)
    assert transport.row['status_code'] is None and transport.response.explicit_reads == []
    assert transport.response.closed and transport.connections[0].closed


@pytest.mark.parametrize('headers', [
    {'Content-Type': 'text/html'},
    {'Content-Type': 'application/json', 'Content-Encoding': 'gzip'},
    {'Content-Type': 'application/json', 'Content-Length': '0'},
    {'Content-Type': 'application/json', 'Content-Length': '-2'},
    {'Content-Type': 'application/json', 'Content-Length': '100000000'},
    {'Content-Type': 'application/json', 'Content-Length': '2.0'}])
def test_bad200_headers_preserve_status_before_body(transport, headers):
    transport.response.headers = headers
    refuse('output', transport.run)
    assert transport.row['status_code'] == 200 and transport.response.explicit_reads == []


@pytest.mark.parametrize('raw,length', [(b'', None), (b'[]', '3'), (b'x' * (m.MAX_BODY + 1), None)])
def test_empty_truncated_oversized_body_no_second_request(transport, raw, length):
    transport.response.raw = raw
    if length is not None: transport.response.headers['Content-Length'] = length
    refuse('output', transport.run)
    assert transport.row['status_code'] == 200 and len(transport.commands) == 1
    assert transport.response.closed and transport.connections[0].closed


@pytest.mark.parametrize('fault', ['hostname', 'verification', 'keylog', 'tunnel'])
def test_tls_tunnel_guards_before_dispatch(transport, fault):
    if fault == 'hostname': transport.tls.check_hostname = False
    elif fault == 'verification': transport.tls.verify_mode = ssl.CERT_NONE
    elif fault == 'keylog': transport.tls.keylog_filename = 'not-allowed'
    else: transport.tunnel = 'unapproved.invalid'
    refuse('environment', transport.run)
    assert transport.commands == []


def test_transport_exception_closes_own_connection_no_retry(transport):
    transport.error = RuntimeError(SECRET)
    with pytest.raises(RuntimeError): transport.run()
    assert len(transport.connections) == len(transport.commands) == 1
    assert transport.connections[0].closed


@pytest.fixture
def successful_result(monkeypatch):
    return observation(monkeypatch, populated=True)[0]


@pytest.mark.parametrize('change', ['extra', 'ready', 'count_bool', 'count_wrong', 'physical_zero',
    'lookup_zero', 'lookup_bool', 'row_extra', 'row_status_bool', 'row_ordinal_bool',
    'row_date', 'row_summary', 'valid_empty'])
def test_closed_result_rejects_forged_counts_readiness_and_rows(successful_result, change):
    value = copy.deepcopy(successful_result)
    if change == 'extra': value['raw_body'] = SECRET
    elif change == 'ready': value['backtest_ready'] = True
    elif change == 'count_bool': value['application_send_intents'] = True
    elif change == 'count_wrong': value['application_send_intents'] = 23
    elif change == 'physical_zero': value['provider_request_count'] = 0
    elif change == 'lookup_zero': value['credential_lookup_attempts']['massive'] = 0
    elif change == 'lookup_bool': value['credential_lookup_attempts']['massive'] = True
    elif change == 'row_extra': value['observations'][0]['raw_error'] = SECRET
    elif change == 'row_status_bool': value['observations'][0]['status_code'] = True
    elif change == 'row_ordinal_bool': value['observations'][1]['ordinal'] = True
    elif change == 'row_date': value['observations'][0]['effective_date'] = '2021-10-28'
    elif change == 'row_summary': value['observations'][0]['summary']['result_count'] = 0
    else: value['observations'][0]['terminal'] = 'valid_empty'
    with pytest.raises((m.Refused, core.Refused)): m.validate_result(value, args(), core)


def test_result_cannot_resume_after_provider_stop(monkeypatch):
    value = observation(monkeypatch, fail_ordinal=0)[0]
    value['observations'][1]['terminal'] = 'transport_refused'
    value['observations'][1]['send_intent_recorded'] = True
    value['application_send_intents'] += 1
    refuse('output', lambda: m.validate_result(value, args(), core))


def wire(value): return m.canonical(value) + b'\n'


def success_packet(value):
    return {'binding': m.binding(args()), 'report_pin': m.pin(m.canonical(value)), 'result': value}


@pytest.fixture
def stdin_only(monkeypatch):
    calls = []
    monkeypatch.setattr(m, 'preflight', lambda *a: calls.append('preflight'))
    monkeypatch.setattr(m, 'bootstrap', lambda *a: {'core': core})
    def forbidden(*a, **kw): raise AssertionError('validator must not open control or provider')
    monkeypatch.setattr(m, 'Store', forbidden)
    monkeypatch.setattr(m, 'request_once', forbidden)
    return calls


def test_validator_stdin_only_success_still_all_readiness_false(stdin_only, successful_result):
    selected = args(); selected.actual_parent_exit = 0
    answer = m.validate_output(selected, wire(success_packet(successful_result)))
    assert answer['accepted'] is answer['output_authenticated'] is True
    assert all(answer['result'][key] is False for key in m.FLAGS)
    assert stdin_only == ['preflight']


@pytest.mark.parametrize('actual', [2, None, True, 1, -1])
def test_success_envelope_cannot_substitute_actual_exit0(stdin_only, successful_result, actual):
    selected = args(); selected.actual_parent_exit = actual
    refuse('output', lambda: m.validate_output(selected, wire(success_packet(successful_result))))


@pytest.mark.parametrize('corruption', ['pin', 'trailing', 'no_lf', 'duplicate', 'noncanonical', 'bad_binding'])
def test_validator_rejects_trailing_duplicate_binding_pin_corruption(stdin_only, successful_result, corruption):
    selected = args(); selected.actual_parent_exit = 0
    value = success_packet(successful_result)
    if corruption == 'pin': value['report_pin']['sha256'] = 'd' * 64
    elif corruption == 'bad_binding': value['binding']['expected_head'] = 'd' * 40
    raw = wire(value)
    if corruption == 'trailing': raw += b'\n'
    elif corruption == 'no_lf': raw = raw[:-1]
    elif corruption == 'duplicate': raw = b'{"binding":null,' + raw[1:]
    elif corruption == 'noncanonical': raw = json.dumps(value).encode() + b'\n'
    refuse('output', lambda: m.validate_output(selected, raw))


def fixture_root(tmp_path, monkeypatch):
    root = tmp_path / 'root'; root.mkdir(mode=0o755); root.chmod(0o755)
    artifacts = root / 'artifacts'; artifacts.mkdir(mode=0o700)
    lane = artifacts / 'analyst_revisions_v2'; lane.mkdir(mode=0o700)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'CONTROL', lane / 'holdings_discovery' / 'R339-synthetic')
    return root


@pytest.fixture
def launch_setup(tmp_path, monkeypatch):
    root = fixture_root(tmp_path, monkeypatch)
    source = root / 'public.py'; source.write_bytes(b'public source\n')
    monkeypatch.setattr(m, 'SOURCE', source)
    selected = args(); selected.caller_sha256 = m.sha(source.read_bytes())
    state = NS(order=[], source_failure=False, held_read_failure=False, late_failure=False,
        credential=Credentials(), sent=[], selected=selected)
    class Held:
        def __init__(self, path, **kw):
            assert path == source
            self.expected = kw['expected']
        def __enter__(self): state.order.append('caller_hold'); return self
        def read(self):
            state.order.append('caller_read')
            if state.held_read_failure: raise m.Refused('source_pin')
            value = source.read_bytes()
            assert m.pin(value) == self.expected
            return value
        def __exit__(self, *a): state.order.append('caller_return')
    class SourceReturn:
        def __enter__(self): return self
        def __exit__(self, *a):
            state.order.append('source_return')
            if state.source_failure: raise m.Refused('changed')
    def bootstrap(stack, bound):
        stack.enter_context(SourceReturn())
        return {'security': Security, 'core': core, 'credentials': state.credential}
    def preflight(*a):
        state.order.append('preflight')
        if state.late_failure and (m.CONTROL / 'report.json').exists(): raise m.Refused('git_state')
    def send(request, key, bound, row):
        assert (m.CONTROL / 'claim.json').is_file()
        assert (m.CONTROL / 'observation-started.json').is_file()
        assert (m.CONTROL / ('send-' + str(request['ordinal']) + '-started.json')).is_file()
        state.sent.append(request['ordinal'])
        row['status_code'] = 200
        return 200, body(request)
    original_write = m.Store.write
    def write(store, name, raw):
        if name == 'report.json':
            assert 'source_return' in state.order and 'caller_return' in state.order
            assert SECRET.encode() not in raw
        state.order.append('write_' + name)
        return original_write(store, name, raw)
    monkeypatch.setattr(m, 'HeldFile', Held)
    monkeypatch.setattr(m, 'bootstrap', bootstrap)
    monkeypatch.setattr(m, 'preflight', preflight)
    monkeypatch.setattr(m, 'request_once', send)
    monkeypatch.setattr(m.Store, 'write', write)
    state.run = lambda: m.launch(selected, deadline())
    return state


def test_claim_markers_precede_contact_and_source_return_precedes_publish(launch_setup):
    answer = launch_setup.run()
    assert launch_setup.sent == list(range(24))
    assert launch_setup.credential.lookups == ['massive', 'fmp']
    assert m.CLAIM_STATE == 'consumed'
    order = launch_setup.order
    assert order.index('caller_hold') < order.index('caller_read') < order.index('write_claim.json')
    assert order.index('write_claim.json') < order.index('write_observation-started.json')
    assert order.index('write_observation-started.json') < order.index('write_credential-massive-started.json')
    assert order.index('source_return') < order.index('write_report.json')
    assert order.index('caller_return') < order.index('write_report.json')
    assert answer['report_pin'] == m.pin((m.CONTROL / 'report.json').read_bytes())
    assert set(p.name for p in m.CONTROL.iterdir()) == {
        'claim.json', 'observation-started.json', 'report.json',
        'credential-massive-started.json', 'credential-fmp-started.json',
        *('send-' + str(i) + '-started.json' for i in range(24))}


def test_same_held_caller_read_refusal_prevents_claim_lookup_and_contact(launch_setup):
    launch_setup.held_read_failure = True
    refuse('source_pin', launch_setup.run)
    assert launch_setup.order == ['preflight', 'caller_hold', 'caller_read', 'caller_return']
    assert not m.CONTROL.exists()
    assert launch_setup.sent == [] and launch_setup.credential.lookups == []
    assert m.CLAIM_STATE == 'unallocated'


def test_source_normal_return_failure_never_publishes_report(launch_setup):
    launch_setup.source_failure = True
    refuse('changed', launch_setup.run)
    assert (m.CONTROL / 'claim.json').is_file()
    assert not (m.CONTROL / 'report.json').exists()
    assert len(launch_setup.sent) == 24


def test_late_failure_may_leave_report_never_returns_success(launch_setup):
    launch_setup.late_failure = True
    refuse('git_state', launch_setup.run)
    assert (m.CONTROL / 'report.json').is_file()
    assert m.CLAIM_STATE == 'consumed'


def test_existing_claim_refuses_before_new_lookup_or_dispatch(launch_setup):
    launch_setup.run(); before = list(launch_setup.sent)
    refuse('claim_spent', launch_setup.run)
    assert launch_setup.sent == before
    assert launch_setup.credential.lookups == ['massive', 'fmp']
    assert m.CLAIM_STATE == 'consumed_or_unknown'


@pytest.mark.parametrize('change', ['mode', 'bytes', 'extra', 'security'])
def test_original_control_detects_metadata_content_and_security_change(tmp_path, monkeypatch, change):
    fixture_root(tmp_path, monkeypatch)
    state = NS(changed=False)
    class CurrentSecurity:
        @staticmethod
        def snapshot(fd): return {'changed': state.changed}
    with pytest.raises(m.Refused):
        with m.Store(CurrentSecurity) as store:
            store.write('claim.json', b'fixed-claim')
            if change == 'mode': (m.CONTROL / 'claim.json').chmod(0o644)
            elif change == 'bytes':
                with (m.CONTROL / 'claim.json').open('r+b') as handle: handle.write(b'changed!!!')
            elif change == 'extra': (m.CONTROL / 'unexpected').write_bytes(b'extra')
            else: state.changed = True
            store.verify()


@pytest.mark.parametrize('value', [True, float('inf'), float('nan')])
def test_parent_deadline_refuses_nonfinite_boolean_spent(value):
    refuse('deadline', lambda: m.budget(value))


@pytest.mark.parametrize('error,code', [
    (m.RunDeadline(), 'deadline'), (TimeoutError(SECRET), 'deadline'),
    (subprocess.TimeoutExpired('private', 1, output=SECRET), 'deadline'),
    (m.Refused('source_pin'), 'source_pin'), (m.Refused(SECRET), 'unknown'),
    (ValueError(SECRET), 'unknown')])
def test_finite_failures_do_not_stringify_secret_errors(error, code):
    assert m.finite(error) == code and SECRET not in m.finite(error)


@pytest.mark.parametrize('mode', ['launch', 'validate'])
def test_main_arms_mode_specific_alarm_before_scoped_operation(monkeypatch, mode):
    selected = args(); order = []
    command = ['caller', mode, '--expected-head', selected.expected_head,
        '--caller-sha256', selected.caller_sha256, '--profile-sha256', selected.profile_sha256]
    if mode == 'validate': command += ['--actual-parent-exit', '0']
    monkeypatch.setattr(m.sys, 'argv', command)
    monkeypatch.setattr(m.sys, 'stdin', NS(buffer=io.BytesIO(b'wire')))
    monkeypatch.setattr(m.signal, 'signal', lambda *a: order.append('signal'))
    monkeypatch.setattr(m.signal, 'setitimer', lambda alarm, seconds: order.append(('alarm', seconds)))
    monkeypatch.setattr(m, 'launch', lambda *a: (order.append('launch') or {'mode': mode}))
    monkeypatch.setattr(m, 'validate_output', lambda *a: (order.append('validate') or {'mode': mode}))
    assert m.main() == {'mode': mode}
    assert order[0] == 'signal' and order[1][0] == 'alarm' and order[2] == mode
    if mode == 'validate': assert order[1][1] == m.READER_SECONDS
    else: assert 0 < order[1][1] <= m.SECONDS


def test_fresh_public_source_bootstrap_exact_three_roles_no_old_operators():
    root = Path(__file__).resolve().parents[2]
    program = """
from contextlib import ExitStack
import sys,time
sys.path.insert(0,ROOT)
from scripts import probe_arv2_r339_holdings_access as m
with ExitStack() as stack:
 roles=m.bootstrap(stack,time.monotonic()+60)
 assert set(roles)=={'security','credentials','core'}
 assert len(m.SOURCE_PINS)==3
 assert m.pin(m.canonical(roles['core'].profile_record()))==m.CORE_PROFILE_PIN
 assert roles['core'].request_plan()[0]['fund']=='SPY'
 assert len(roles['core'].request_plan())==24
 assert all(type(v).__name__=='module' for v in roles.values())
 assert not any(n=='AlgorithmImports' or n=='assistant.dispatch_fence' or n.startswith(('QuantConnect','quantconnect','qc.client')) for n in sys.modules)
 assert not any('run_arv2_' in n or 'prepare_arv2_' in n for n in sys.modules)
print('BOOTSTRAP_OK')
"""
    program = 'ROOT=' + repr(str(root)) + '\n' + program
    support = root / '.pytest_cache' / 'r339-caller-author'
    env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C',
        'TMPDIR': str(support / 'tmp'), 'PYTHONPYCACHEPREFIX': str(support / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}
    row = subprocess.run([m.PYTHON, '-I', '-B', '-c', program], cwd=root, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    assert row.returncode == 0, row.stderr.decode('ascii', errors='replace')
    assert row.stdout == b'BOOTSTRAP_OK\n' and row.stderr == b''


def test_profile_scope_no_operational_or_formal_success_claim():
    profile = m.profile_record()
    assert profile['maximum_application_send_intents'] == 24
    assert profile['credential_lookups'] == {'massive': 1, 'fmp': 1}
    assert profile['provider_request_count'] is None
    assert profile['native_parent_policy_sha256'] == m.sha(m.native_profile().encode())
    assert all(profile[name] is False for name in m.FLAGS)
    native = m.native_profile()
    assert '(deny network-inbound)' in native and '(deny network*)' not in native
    assert '/Volumes' in native and '/Library/Keychains' in native
    assert str(m.CONTROL) in native and str(m.ROOT / 'artifacts') in native


@pytest.mark.parametrize('failure,code', [('wrong_date', 'date'), ('error_200', 'schema'),
    ('echo', 'credential_echo'), ('response', 'output'), ('transport', 'unknown'), ('close', 'unknown')])
def test_exact_finite_failure_cause_survives_without_error_text(monkeypatch, failure, code):
    result, _, _, _ = observation(monkeypatch, fail_ordinal=0, failure=failure)
    assert result['observations'][0]['failure_code'] == code
    assert result['observations'][1]['failure_code'] == 'previous_provider_stop'
    assert SECRET.encode() not in m.canonical(result)
    m.validate_result(result, args(), core)


@pytest.mark.parametrize('status', [200, 403])
def test_response_close_exception_preserves_status_and_still_closes_connection(transport, status):
    transport.response.status = status
    transport.response.close_error = OSError(SECRET)
    with pytest.raises(OSError): transport.run()
    assert transport.row['status_code'] == status
    assert transport.connections[0].closed and transport.response.closed
    assert len(transport.commands) == 1


@pytest.mark.parametrize('status', [None, 200, 403])
def test_mid_dispatch_deadline_progress_preserves_measured_status(monkeypatch, stdin_only, status):
    store, credentials = MemoryStore(), Credentials()
    def send(request, key, bound, row):
        row['status_code'] = status
        raise m.RunDeadline()
    monkeypatch.setattr(m, 'request_once', send)
    with pytest.raises(m.RunDeadline):
        m.observe({'core': core, 'credentials': credentials}, store, args(), deadline())
    partial = copy.deepcopy(m.PROGRESS)
    assert partial['protocol_complete'] is False
    assert partial['application_send_intents'] == 1
    assert partial['credential_lookup_attempts'] == {'massive': 1, 'fmp': 0}
    assert partial['observations'][0]['status_code'] == status
    assert partial['observations'][0]['send_intent_recorded'] is True
    assert all(row['terminal'] == 'not_attempted' for row in partial['observations'][1:])
    m.validate_result(partial, args(), core, complete=False)
    selected = args(); selected.actual_parent_exit = 2
    failed = {'binding': m.binding(selected), 'failure_code': 'deadline', 'claim_state': 'consumed',
        'progress': partial, **m.FLAGS}
    answer = m.validate_output(selected, wire(failed))
    assert answer['accepted'] is False and answer['output_authenticated'] is True
    assert answer['failure']['progress']['observations'][0]['status_code'] == status


@pytest.mark.parametrize('code', ['deadline', 'source_pin', 'control', 'unknown'])
def test_exit2_failure_only_authenticates_as_failure(stdin_only, code):
    selected = args(); selected.actual_parent_exit = 2
    value = {'binding': m.binding(selected), 'failure_code': code,
        'claim_state': 'unallocated', 'progress': None, **m.FLAGS}
    answer = m.validate_output(selected, wire(value))
    assert answer['accepted'] is False and answer['output_authenticated'] is True
    assert answer['failure']['failure_code'] == code
    selected.actual_parent_exit = 0
    refuse('output', lambda: m.validate_output(selected, wire(value)))


def test_late_failure_preserves_all_observed_statuses_as_failure(launch_setup, monkeypatch):
    launch_setup.late_failure = True
    refuse('git_state', launch_setup.run)
    progress = copy.deepcopy(m.PROGRESS)
    assert progress['protocol_complete'] is True and progress['application_send_intents'] == 24
    assert all(row['status_code'] == 200 for row in progress['observations'])
    selected = copy.deepcopy(launch_setup.selected); selected.actual_parent_exit = 2
    monkeypatch.setattr(m, 'preflight', lambda *a: None)
    monkeypatch.setattr(m, 'bootstrap', lambda *a: {'core': core})
    value = {'binding': m.binding(selected), 'failure_code': 'git_state',
        'claim_state': 'consumed', 'progress': progress, **m.FLAGS}
    answer = m.validate_output(selected, wire(value))
    assert answer['accepted'] is False and answer['output_authenticated'] is True
    assert answer['failure']['progress']['application_send_intents'] == 24


@pytest.mark.parametrize('value', [-1, 0])
def test_spent_deadline_raises_non_swallowable_alarm(value):
    with pytest.raises(m.RunDeadline): m.budget(value)
    assert m.DEADLINE_FIRED is True


@pytest.mark.parametrize('change,code', [('platform', 'host'), ('isolated', 'host'),
    ('dirty', 'git_state'), ('head', 'git_state'), ('stderr', 'git_state'),
    ('source', 'source_pin'), ('blob', 'source_pin'), ('profile', 'source_pin'),
    ('keylog', 'environment')])
def test_preflight_exact_host_clean_git_self_blob_profile(tmp_path, monkeypatch, change, code):
    root = fixture_root(tmp_path, monkeypatch)
    source = root / 'probe.py'; raw = b'# synthetic public source\n'; source.write_bytes(raw)
    monkeypatch.setattr(m, 'SOURCE', source); monkeypatch.setattr(m, '__file__', str(source))
    monkeypatch.chdir(root)
    monkeypatch.setattr(m, 'sys', NS(platform='darwin', version_info=(3, 13, 0),
        executable=m.PYTHON, dont_write_bytecode=True, flags=NS(isolated=1)))
    for name in ('SSLKEYLOGFILE', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'PYTHONPATH'):
        monkeypatch.delenv(name, raising=False)
    selected = args()
    selected.caller_sha256 = m.sha(raw)
    selected.profile_sha256 = m.sha(m.canonical(m.profile_record()))
    calls = []
    def git(command, **kwargs):
        assert command[0] == '/usr/bin/git' and kwargs['cwd'] == root
        assert kwargs['stdin'] is subprocess.DEVNULL
        assert SECRET not in repr(kwargs['env'])
        calls.append(command[1:])
        operation = command[1:]
        result = {('rev-parse', '--show-toplevel'): str(root).encode(),
            ('branch', '--show-current'): m.BRANCH.encode(),
            ('rev-parse', 'HEAD'): selected.expected_head.encode(),
            ('status', '--porcelain'): b''}
        stdout = raw if operation[:2] == ['cat-file', 'blob'] else result[tuple(operation)]
        if change == 'dirty' and operation == ['status', '--porcelain']: stdout = b' M unrelated.py'
        if change == 'head' and operation == ['rev-parse', 'HEAD']: stdout = b'd' * 40
        if change == 'blob' and operation[:2] == ['cat-file', 'blob']: stdout = b'other blob'
        return NS(returncode=0, stdout=stdout,
            stderr=b'unexpected stderr' if change == 'stderr' else b'')
    monkeypatch.setattr(m.subprocess, 'run', git)
    if change == 'platform': monkeypatch.setattr(m.sys, 'platform', 'win32')
    elif change == 'isolated': monkeypatch.setattr(m.sys, 'flags', NS(isolated=0))
    elif change == 'source': selected.caller_sha256 = 'd' * 64
    elif change == 'profile': selected.profile_sha256 = 'd' * 64
    elif change == 'keylog': monkeypatch.setenv('SSLKEYLOGFILE', 'forbidden')
    refuse(code, lambda: m.preflight(selected, deadline()))


def test_held_public_bytes_pin_and_named_endpoint_change(tmp_path):
    path = tmp_path / 'public.py'; raw = b'public baseline'; path.write_bytes(raw)
    with m.HeldFile(path, maximum=100, expected=m.pin(raw), deadline=deadline()) as held:
        assert held.read() == raw
    def wrong_pin():
        with m.HeldFile(path, maximum=100, expected=m.pin(b'wrong'), deadline=deadline()) as held:
            held.read()
    refuse('source_pin', wrong_pin)
    with pytest.raises(m.Refused):
        with m.HeldFile(path, maximum=100, expected=m.pin(raw), deadline=deadline()) as held:
            path.unlink(); path.write_bytes(raw); held.verify()


def test_final_core_and_selected_source_pins():
    assert m.CORE_PROFILE_PIN == {'byte_count': 7804,
        'sha256': '5bdf06835bafac283ffbcb707c99fac4863de851144b34eab1723c55ae4dd2b3'}
    assert m.pin(core.canonical(core.profile_record())) == m.CORE_PROFILE_PIN
    assert m.SOURCE_PINS['scripts/arv2_r339_holdings_discovery.py'] == (
        'ac23cea52e749d1400cf2d52654b8f593a81dd6b0add42d006284d7360057600')
    assert len(m.SOURCE_PINS) == 3


@pytest.mark.parametrize('bad', [
    {'expected_head': None}, {'expected_head': 'a' * 39},
    {'caller_sha256': True}, {'caller_sha256': 'A' * 64},
    {'profile_sha256': 'c' * 63}])
def test_invalid_cli_source_bindings_refuse_before_claim(bad):
    selected = args()
    for key, value in bad.items(): setattr(selected, key, value)
    refuse('arguments', lambda: m.binding(selected))
    assert m.CLAIM_STATE == 'unallocated'


@pytest.mark.parametrize('kind,code', [('ValueError', 'unknown'), ('TimeoutError', 'deadline')])
def test_real_synthetic_child_failure_stdout_is_finite_redacted_and_exit2(kind, code):
    root = Path(__file__).resolve().parents[2]
    program = """
import json,sys
from pathlib import Path
source=Path(SOURCE).read_bytes()
needle=b"if __name__=='__main__':"
assert source.count(needle)==1
override=("def launch(*args):\\n raise "+KIND+"("+repr(SECRET)+")\\n\\n").encode('ascii')
synthetic=source.replace(needle,override+needle)
sys.argv=['synthetic','launch','--expected-head','a'*40,
 '--caller-sha256','b'*64,'--profile-sha256','c'*64]
namespace={'__name__':'__main__','__file__':SOURCE}
exec(compile(synthetic,SOURCE,'exec'),namespace)
"""
    program = ('SOURCE=' + repr(str(m.SOURCE)) + '\nKIND=' + repr(kind)
        + '\nSECRET=' + repr(SECRET) + '\n' + program)
    support = root / '.pytest_cache' / 'r339-caller-author'
    env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C',
        'TMPDIR': str(support / 'tmp'), 'PYTHONPYCACHEPREFIX': str(support / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}
    row = subprocess.run([m.PYTHON, '-I', '-B', '-c', program], cwd=root, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    assert row.returncode == 2 and row.stderr == b''
    assert SECRET.encode() not in row.stdout
    value = json.loads(row.stdout)
    assert wire(value) == row.stdout and value['failure_code'] == code
    assert value['progress'] is None and value['claim_state'] == 'unallocated'
    assert all(value[name] is False for name in m.FLAGS)


def test_final_held_caller_bytes_and_profile():
    assert m.pin(m.SOURCE.read_bytes()) == {'byte_count': 30657,
        'sha256': 'c81f4abde82ea60b51f34f0d7aa3eb5fe65e00f7be04c5b90d95ed2b7fdbacd6'}
    assert m.pin(m.canonical(m.profile_record())) == {'byte_count': 2689,
        'sha256': 'b5ae2f90a490f34cc8c7da5488f89017841db8e1eead858cf2c654ad02f199a8'}
