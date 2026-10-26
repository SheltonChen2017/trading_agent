"""Synthetic X two-status protocol under native artifact/network denial."""
import ast
import copy
import inspect
import json
import os
import re
import time
from types import SimpleNamespace as NS

import pytest
import requests

from scripts import run_arv2_r298_sharadar_bulk_inventory as m

KEY = 'synthetic-SECRET+/"1234'


def body(table):
    return json.dumps({'table': table, 'files': [{'history': 'full',
        'historyLabel': 'Full History', 'name': table + '.csv.zip', 'size': 1000000,
        'sizeLabel': '1.0 MB', 'modified': '2026-10-25T00:00:00+00:00',
        'available': True}]}).encode()


@pytest.fixture(autouse=True)
def deny_old_operations(monkeypatch):
    def deny(*a, **k):
        raise AssertionError('old operation or credential access')
    for module in (m.frozen, m.frozen.frozen, m.previous):
        for name in ('run', 'observe', 'main'):
            monkeypatch.setattr(module, name, deny)
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
    path = parent / 'synthetic-x'
    monkeypatch.setattr(m, 'CONTROL', path)
    monkeypatch.setattr(m.security, 'snapshot', lambda fd: {'acl_empty': True, 'xattrs': {}})
    return path


@pytest.fixture
def transport(control, monkeypatch):
    state = NS(bodies=[body('stocks'), body('funds')], calls=[], keys=[],
        statuses=[200, 200], body_reads=0, closed=0, headers={},
        fail_request=None, mutate=None, postflight=False)
    def key(provider, *, timeout_seconds):
        assert provider == 'sharadar' and 0 < timeout_seconds <= 20
        assert sorted(p.name for p in control.iterdir()) == ['claim.json']
        state.keys.append(provider)
        return KEY
    def get(self, url, **kwargs):
        index = len(state.calls)
        assert state.keys == ['sharadar'] and index < 2
        assert (control / (('stocks', 'funds')[index] + '-status-intent.json')).is_file()
        if index:
            assert (control / 'stocks-status.body').read_bytes() == state.bodies[0]
        state.calls.append((url, copy.deepcopy(kwargs)))
        if state.fail_request == index:
            raise RuntimeError(KEY)
        response = requests.Response()
        response.status_code = state.statuses[index]
        response.request = self.prepare_request(requests.Request('GET', url,
            params=kwargs['params'], headers=kwargs['headers']))
        response.url, response.history = response.request.url, []
        response.headers.update(state.headers)
        def content(chunk_size):
            state.body_reads += 1
            yield state.bodies[index]
        def close():
            state.closed += 1
        response.iter_content, response.close = content, close
        if state.mutate:
            state.mutate(self, response)
        return response
    def preflight(*unused):
        if state.postflight:
            raise m.Refused('source_pin')
    monkeypatch.setattr(m.keychain, 'load_key', key)
    monkeypatch.setattr(requests.Session, 'get', get)
    monkeypatch.setattr(m, 'preflight', preflight)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    return state


def envelope(args, outcome):
    return m.canonical({'binding': m.binding(args), 'outcome': outcome})


def test_two_exact_requests_and_private_retention_before_next_role(control, args, transport):
    outcome = m.run(args, time.monotonic() + 110)
    assert 'result' in outcome
    assert len(transport.calls) == transport.body_reads == transport.closed == 2
    assert transport.keys == ['sharadar']
    for index, (url, kw) in enumerate(transport.calls):
        assert url == m.ENDPOINTS[index] and kw['params'] == {'status': 'True', 'api_key': KEY}
        assert kw['allow_redirects'] is False and kw['verify'] is kw['stream'] is True
        assert kw['headers'] == {'Accept-Encoding': 'identity'}
    assert len(list(control.iterdir())) == 8
    assert control.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in control.iterdir())
    public = envelope(args, outcome)
    assert KEY.encode() not in public and all(raw not in public for raw in transport.bodies)
    assert m.validate_output(public, 0, args)
    with pytest.raises(m.Refused, match='claim_spent'):
        m.run(args, time.monotonic() + 110)
    assert len(transport.calls) == 2


@pytest.mark.parametrize('index', [0, 1])
@pytest.mark.parametrize('status', [401, 403, 429, 500, None, True])
def test_failed_status_no_body_read_or_next_role(control, args, transport, index, status):
    transport.statuses[index] = status
    outcome = m.run(args, time.monotonic() + 110)
    assert len(transport.calls) == index + 1 and transport.body_reads == index
    assert transport.closed == index + 1
    failed = outcome['failure']
    assert failed['failure_code'] == ('http_status_unavailable' if status is None or type(status) is bool else 'http_status')
    assert len(failed['state']['captures']) == len(failed['state']['receipts']) == index
    assert m.validate_output(envelope(args, outcome), 2, args)


@pytest.mark.parametrize('index', [0, 1])
def test_request_ambiguity_no_raw_exception_or_retry(control, args, transport, index):
    transport.fail_request = index
    outcome = m.run(args, time.monotonic() + 110)
    assert outcome['failure']['failure_code'] == 'request_failed'
    assert outcome['failure']['state']['http_events'][-1]['http_status'] is None
    assert KEY.encode() not in envelope(args, outcome)
    assert len(transport.calls) == index + 1
    assert m.validate_output(envelope(args, outcome), 2, args)


@pytest.mark.parametrize('fault', ['header_bound', 'stream_bound', 'encoding', 'request_url', 'response_url', 'history', 'header_echo'])
def test_transport_integrity_is_not_relaxed(control, args, transport, fault):
    if fault == 'header_bound': transport.headers['Content-Length'] = '8193'
    elif fault == 'stream_bound': transport.bodies[0] = b'X' * 8193
    elif fault == 'encoding': transport.headers['Content-Encoding'] = 'gzip'
    elif fault == 'request_url': transport.mutate = lambda s, r: setattr(r.request, 'url', 'https://example.invalid')
    elif fault == 'response_url': transport.mutate = lambda s, r: setattr(r, 'url', 'https://example.invalid')
    elif fault == 'history': transport.mutate = lambda s, r: setattr(r, 'history', [requests.Response()])
    else: transport.headers['X-Echo'] = KEY
    outcome = m.run(args, time.monotonic() + 110)
    assert 'failure' in outcome and not outcome['failure']['state']['captures']
    assert len(transport.calls) == 1 and m.validate_output(envelope(args, outcome), 2, args)


def test_schema_refusal_retains_safe_body_before_refusing_no_next_request(control, args, transport):
    transport.bodies[0] = b'{"table":"stocks","unexpected":[]}'
    outcome = m.run(args, time.monotonic() + 110)
    state = outcome['failure']['state']
    assert (control / 'stocks-status.body').read_bytes() == transport.bodies[0]
    assert state['captures'] == {'stocks-status.body': {'byte_count': len(transport.bodies[0]),
        'sha256': m.sha(transport.bodies[0])}}
    assert not state['receipts'] and len(transport.calls) == 1
    assert m.validate_output(envelope(args, outcome), 2, args)


@pytest.mark.parametrize('raw', [b'not JSON', b'\xff', b'{"value":"synthetic-SECRET+/\\"1234"}',
    ('{"value":"' + ''.join('\\u%04x' % ord(char) for char in KEY) + '"}').encode()])
def test_unsafe_body_is_not_persisted(control, args, transport, raw):
    transport.bodies[0] = raw
    outcome = m.run(args, time.monotonic() + 110)
    assert 'failure' in outcome and not outcome['failure']['state']['captures']
    assert not (control / 'stocks-status.body').exists()
    assert m.validate_output(envelope(args, outcome), 2, args)


@pytest.mark.parametrize('actual', [2, None, False, True, -1])
def test_actual_zero_mandatory(control, args, transport, actual):
    outcome = m.run(args, time.monotonic() + 110)
    with pytest.raises(ValueError): m.validate_output(envelope(args, outcome), actual, args)


@pytest.mark.parametrize('fault', ['report', 'binding', 'event', 'flag', 'postcheck', 'receipt', 'capture', 'swap', 'extra'])
def test_external_binding_and_capture_receipt_integrity(control, args, transport, fault):
    outcome = m.run(args, time.monotonic() + 110)
    packet = m.parse(envelope(args, outcome))
    result = packet['outcome']['result']
    if fault == 'report': packet['outcome']['report']['sha256'] = 'f' * 64
    elif fault == 'binding': packet['binding']['expected_head'] = 'f' * 40
    elif fault == 'event': result['http_events'][-1]['http_status'] = 403
    elif fault == 'flag': result['strategy_price_admitted'] = True
    elif fault == 'postcheck': result['post_checks_complete'] = False
    elif fault == 'receipt': result['receipts'][0]['unknown_field'] = True
    elif fault == 'capture': result['captures']['stocks-status.body']['sha256'] = 'f' * 64
    elif fault == 'swap': result['receipts'].reverse()
    else: result['captures']['other.body'] = result['captures']['stocks-status.body']
    # Recompute report so the changed semantic field, not only report pin, is tested.
    if fault != 'report':
        report = m.canonical({**m.binding(args), 'result': result})
        packet['outcome']['report'] = {'byte_count': len(report), 'sha256': m.sha(report)}
    with pytest.raises(ValueError): m.validate_output(m.canonical(packet), 0, args)


def test_late_report_nonzero_never_accepted(control, args, transport, monkeypatch):
    actual = m.Store.write
    def late(self, name, value):
        pin = actual(self, name, value)
        if name == 'report.json': raise m.Refused('control_write')
        return pin
    monkeypatch.setattr(m.Store, 'write', late)
    outcome = m.run(args, time.monotonic() + 110)
    assert (control / 'report.json').is_file()
    assert m.validate_output(envelope(args, outcome), 2, args)
    with pytest.raises(ValueError): m.validate_output(envelope(args, outcome), 0, args)


def test_postflight_source_failure_retains_diagnostic_not_success(control, args, transport):
    transport.postflight = True
    outcome = m.run(args, time.monotonic() + 110)
    assert outcome['failure']['failure_code'] == 'source_pin'
    assert outcome['failure']['state']['stage'] == 'postflight'
    assert len(outcome['failure']['state']['receipts']) == 2
    assert not (control / 'report.json').exists()
    assert m.validate_output(envelope(args, outcome), 2, args)


def test_control_drift_and_unknown_private_names_refuse(control):
    with m.Store() as store:
        store.write('claim.json', {'synthetic': True})
        with pytest.raises(m.Refused, match='control_name'):
            store.write_bytes('other.body', b'raw', private=True)
        fd, _ = store.held['claim.json']
        info = os.fstat(fd); os.utime(fd, ns=(info.st_atime_ns, info.st_mtime_ns + 1))
        with pytest.raises(m.Refused): store.verify()


def test_selected_pins_and_native_output_policy():
    for name, pin in m.pins().items():
        assert re.fullmatch('[0-9a-f]{64}', pin) and pin != '0' * 64
        assert m.sha((m.ROOT / name).read_bytes()) == pin
    assert m.ROLES == ('stocks_status', 'funds_status') and m.CAPTURE_BOUNDS == (8192, 8192)
    assert m.profile_record()['price_rows_or_downloads_requested'] is False
    assert '(deny network*)' in m.native_profile() and str(m.ROOT / 'artifacts') in m.native_profile()


def test_shared_primitives_unchanged_and_source_compiles():
    def normalized(module, name):
        tree = ast.parse(module.SOURCE.read_bytes())
        node = next(n for n in tree.body if type(n) is ast.FunctionDef and n.name == name)
        return ast.dump(node, include_attributes=False)
    for name in ('preflight', 'remaining', 'native_profile', 'main'):
        assert normalized(m, name) == normalized(m.frozen, name)
    for name in ('__init__', '__enter__', '__exit__', 'verify', 'write', 'write_bytes', '_read'):
        assert inspect.getsource(getattr(m.Store, name)) == inspect.getsource(getattr(m.frozen.Store, name))
    compile(m.SOURCE.read_bytes(), str(m.SOURCE), 'exec')


def test_observer_bounds_and_validator(args, tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    (tmp_path / '.pytest_cache').mkdir()
    calls, raw = [], m.canonical({})
    def capture(argv, safe, seconds, **kw):
        calls.append((argv, seconds))
        assert not any('KEY' in key or 'TOKEN' in key for key in safe)
        if len(calls) == 1:
            assert seconds == 150
            return raw, b'', {'actual_exit': 2, 'bound': None}
        assert argv[:2] == ['/usr/bin/sandbox-exec', '-p'] and seconds == 20
        assert kw['input_bytes'] == raw
        return raw, b'', {'actual_exit': 0, 'bound': None}
    monkeypatch.setattr(m, 'capture', capture)
    value, code = m.observe(args)
    assert code == 2 and value['output_authenticated'] is True and len(calls) == 2
