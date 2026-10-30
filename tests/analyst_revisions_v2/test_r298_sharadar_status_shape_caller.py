"""One-request W fixtures; native artifact/network denial required."""
import copy
import json
import os
import re
import time
from types import SimpleNamespace as NS

import pytest
import requests

from scripts import run_arv2_r298_sharadar_status_shape as m
from tests.analyst_revisions_v2._post_merge_pins import current_pin

KEY = 'synthetic-SECRET+/"1234'


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('old operation or actual credential access')
    for module in (m.frozen, m.previous):
        monkeypatch.setattr(module, 'run', deny)
        monkeypatch.setattr(module, 'observe', deny)
        monkeypatch.setattr(module, 'main', deny)
    monkeypatch.setattr(m.protocol, 'observe', deny)
    monkeypatch.setattr(m.protocol, '_fetch', deny)
    monkeypatch.setattr(m.keychain, 'load_key', deny)


@pytest.fixture
def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64)


@pytest.fixture
def control(tmp_path, monkeypatch):
    parent = tmp_path / 'own-parent'
    parent.mkdir(mode=0o700)
    path = parent / 'synthetic-w'
    monkeypatch.setattr(m, 'CONTROL', path)
    monkeypatch.setattr(m.security, 'snapshot', lambda fd: {'acl_empty': True, 'xattrs': {}})
    return path


@pytest.fixture
def transport(control, monkeypatch):
    body = json.dumps({'table': 'stocks', 'name': 'stocks.csv.zip', 'size': 1000000,
        'sizeLabel': '1.0 MB', 'modified': '2026-10-25T00:00:00+00:00'}).encode()
    state = NS(body=body, calls=[], keys=[], status=200, body_reads=0, closed=0,
        headers={}, fail_request=False, mutate=None, fail_postflight=False)
    def key(provider, *, timeout_seconds):
        assert provider == 'sharadar' and 0 < timeout_seconds <= 20
        assert sorted(path.name for path in control.iterdir()) == ['claim.json']
        state.keys.append(provider)
        return KEY
    def get(self, url, **kwargs):
        assert state.keys == ['sharadar'] and len(state.calls) == 0
        assert (control / 'stocks-status-intent.json').is_file()
        state.calls.append((url, copy.deepcopy(kwargs)))
        if state.fail_request:
            raise RuntimeError(KEY)
        response = requests.Response()
        response.status_code = state.status
        response.request = self.prepare_request(requests.Request('GET', url,
            params=kwargs['params'], headers=kwargs['headers']))
        response.url = response.request.url
        response.history = []
        response.headers.update(state.headers)
        def content(chunk_size):
            state.body_reads += 1
            yield state.body
        def close():
            state.closed += 1
        response.iter_content, response.close = content, close
        if state.mutate:
            state.mutate(self, response)
        return response
    def preflight(*unused):
        if state.fail_postflight:
            raise m.Refused('source_pin')
    monkeypatch.setattr(m.keychain, 'load_key', key)
    monkeypatch.setattr(requests.Session, 'get', get)
    monkeypatch.setattr(m, 'preflight', preflight)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    return state


def envelope(args, outcome):
    return m.canonical({'binding': m.binding(args), 'outcome': outcome})


def test_exact_one_request_claim_key_and_summary_only_publication(control, args, transport):
    outcome = m.run(args, time.monotonic() + 80)
    assert 'result' in outcome
    assert transport.keys == ['sharadar'] and len(transport.calls) == 1
    url, kwargs = transport.calls[0]
    assert url == m.ENDPOINT and kwargs['params'] == {'status': 'True', 'api_key': KEY}
    assert kwargs['allow_redirects'] is False and kwargs['verify'] is kwargs['stream'] is True
    assert kwargs['headers'] == {'Accept-Encoding': 'identity'}
    assert transport.body_reads == transport.closed == 1
    assert sorted(path.name for path in control.iterdir()) == [
        'claim.json', 'report.json', 'stocks-status-intent.json', 'stocks-status-status.json']
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in control.iterdir())
    assert control.stat().st_mode & 0o777 == 0o700
    public = envelope(args, outcome)
    assert KEY.encode() not in public and transport.body not in public
    assert m.validate_output(public, 0, args)
    with pytest.raises(m.Refused, match='claim_spent'):
        m.run(args, time.monotonic() + 80)
    assert len(transport.calls) == 1


@pytest.mark.parametrize('status', [401, 403, 429, 500, None, True])
def test_refused_or_invalid_status_never_reads_body_or_retries(control, args, transport, status):
    transport.status = status
    outcome = m.run(args, time.monotonic() + 80)
    failed = outcome['failure']
    assert len(transport.calls) == 1 and transport.body_reads == 0
    assert failed['failure_code'] == ('http_status_unavailable' if status is None or type(status) is bool else 'http_status')
    assert transport.closed == 1 and failed['state']['receipt'] is None
    assert m.validate_output(envelope(args, outcome), 2, args)


def test_request_ambiguity_retains_unknown_status_without_exception_text(control, args, transport):
    transport.fail_request = True
    outcome = m.run(args, time.monotonic() + 80)
    assert outcome['failure']['failure_code'] == 'request_failed'
    assert outcome['failure']['state']['http_events'][-1]['http_status'] is None
    assert KEY.encode() not in envelope(args, outcome)
    assert len(transport.calls) == 1 and m.validate_output(envelope(args, outcome), 2, args)


@pytest.mark.parametrize('fault', ['header_bound', 'stream_bound', 'encoding', 'request_url', 'response_url', 'history', 'header_echo'])
def test_response_transport_integrity_is_not_weakened(control, args, transport, fault):
    if fault == 'header_bound': transport.headers['Content-Length'] = '8193'
    elif fault == 'stream_bound': transport.body = b'X' * 8193
    elif fault == 'encoding': transport.headers['Content-Encoding'] = 'gzip'
    elif fault == 'request_url': transport.mutate = lambda session, response: setattr(response.request, 'url', 'https://example.invalid')
    elif fault == 'response_url': transport.mutate = lambda session, response: setattr(response, 'url', 'https://example.invalid')
    elif fault == 'history': transport.mutate = lambda session, response: setattr(response, 'history', [requests.Response()])
    else: transport.headers['X-Echo'] = KEY
    outcome = m.run(args, time.monotonic() + 80)
    assert 'failure' in outcome and outcome['failure']['state']['receipt'] is None
    assert len(transport.calls) == 1 and m.validate_output(envelope(args, outcome), 2, args)


@pytest.mark.parametrize('body', [b'<html>not JSON</html>', b'\xff', b'{"error":"subscription expired"}'])
def test_noncanonical_shape_is_diagnostic_not_raw_body_persistence(control, args, transport, body):
    transport.body = body
    outcome = m.run(args, time.monotonic() + 80)
    assert 'result' in outcome
    assert m.validate_output(envelope(args, outcome), 0, args)
    assert not any(path.suffix != '.json' for path in control.iterdir())
    assert all(path.read_bytes() != body for path in control.iterdir())
    assert all(outcome['result'][flag] is False for flag in m.FALSE_FLAGS)


@pytest.mark.parametrize('actual', [2, None, False, True, -1])
def test_actual_zero_is_mandatory_even_with_well_formed_report(control, args, transport, actual):
    outcome = m.run(args, time.monotonic() + 80)
    with pytest.raises(ValueError):
        m.validate_output(envelope(args, outcome), actual, args)


@pytest.mark.parametrize('fault', ['report', 'binding', 'event', 'flag', 'postcheck', 'receipt'])
def test_external_output_binding_and_refusal_flags(control, args, transport, fault):
    outcome = m.run(args, time.monotonic() + 80)
    packet = m.parse(envelope(args, outcome))
    if fault == 'report': packet['outcome']['report']['sha256'] = 'f' * 64
    elif fault == 'binding': packet['binding']['expected_head'] = 'f' * 40
    elif fault == 'event': packet['outcome']['result']['http_events'][-1]['http_status'] = 403
    elif fault == 'flag': packet['outcome']['result']['strategy_price_admitted'] = True
    elif fault == 'postcheck': packet['outcome']['result']['post_checks_complete'] = False
    else: packet['outcome']['result']['receipt']['unknown_field'] = True
    with pytest.raises(ValueError):
        m.validate_output(m.canonical(packet), 0, args)


def test_postflight_failure_and_late_report_never_become_success(control, args, transport, monkeypatch):
    actual = m.Store.write
    def late(self, name, value):
        pin = actual(self, name, value)
        if name == 'report.json': raise m.Refused('control_write')
        return pin
    monkeypatch.setattr(m.Store, 'write', late)
    outcome = m.run(args, time.monotonic() + 80)
    assert (control / 'report.json').is_file()
    assert outcome['failure']['state']['stage'] == 'report'
    assert m.validate_output(envelope(args, outcome), 2, args)
    with pytest.raises(ValueError): m.validate_output(envelope(args, outcome), 0, args)


def test_control_drift_and_private_body_names_refuse(control):
    with m.Store() as store:
        store.write('claim.json', {'synthetic': True})
        with pytest.raises(m.Refused, match='control_name'):
            store.write_bytes('stocks-status.json', b'raw', private=True)
        fd, _ = store.held['claim.json']
        info = os.fstat(fd); os.utime(fd, ns=(info.st_atime_ns, info.st_mtime_ns + 1))
        with pytest.raises(m.Refused): store.verify()


def test_selected_source_pins_compile_and_output_sandbox():
    for name, pin in m.pins().items():
        assert re.fullmatch('[0-9a-f]{64}', pin) and pin != '0' * 64
        assert m.sha((m.ROOT / name).read_bytes()) == current_pin(name, pin)
    assert m.ROLES == ('stocks_status',) and m.CAPTURE_NAMES == m.CAPTURE_BOUNDS == ()
    assert m.profile_record()['raw_body_persisted'] is False
    assert '(deny network*)' in m.native_profile()
    assert str(m.ROOT / 'artifacts') in m.native_profile()
    compile(m.SOURCE.read_bytes(), str(m.SOURCE), 'exec')


def test_observer_outer_actual_exit_and_native_validator(args, tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    (tmp_path / '.pytest_cache').mkdir()
    calls = []
    raw = m.canonical({})
    def capture(argv, safe, seconds, **kwargs):
        calls.append((argv, safe, seconds, kwargs))
        assert not any('KEY' in key or 'TOKEN' in key for key in safe)
        if len(calls) == 1:
            assert seconds == 120
            return raw, b'', {'actual_exit': 2, 'bound': None}
        assert argv[:2] == ['/usr/bin/sandbox-exec', '-p'] and seconds == 20
        assert kwargs['input_bytes'] == raw
        return raw, b'', {'actual_exit': 0, 'bound': None}
    monkeypatch.setattr(m, 'capture', capture)
    value, code = m.observe(args)
    assert code == 2 and value['output_authenticated'] is True and len(calls) == 2


def test_unchanged_store_preflight_and_bounds_are_proven_primitives():
    import ast
    import inspect
    def normalized(module, name):
        # Source AST, not live callable: autouse denial deliberately replaces
        # the predecessor's operational main() with a nested failing fixture.
        tree = ast.parse(module.SOURCE.read_bytes())
        node = next(node for node in tree.body if type(node) is ast.FunctionDef and node.name == name)
        return ast.dump(node, include_attributes=False)
    for name in ('preflight', 'remaining', 'native_profile', 'main'):
        assert normalized(m, name) == normalized(m.frozen, name)
    # W deliberately removes capture_bytes and has no permitted private names;
    # the remaining storage primitives retain V's exact validated behavior.
    for name in ('__init__', '__enter__', '__exit__', 'verify', 'write', 'write_bytes', '_read'):
        left = inspect.getsource(getattr(m.Store, name))
        right = inspect.getsource(getattr(m.frozen.Store, name))
        assert left == right
    assert m.DEADLINE_SECONDS == 90 and m.MAX_FILES == 8
    assert m.CAPTURE_NAMES == () and not hasattr(m.Store, 'capture_bytes')
