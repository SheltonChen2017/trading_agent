"""AP synthetic resolver-proof/representation/protocol checks; no real data or contact."""
import copy
import errno
import io
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS

import pytest
import requests

from scripts import run_arv2_r298_raw_price_acquisition_v3 as m


@pytest.fixture(autouse=True)
def synthetic_environment(monkeypatch):
    # Remove known handoff names without observing or serializing their values.
    for name in ('QC_USER_ID', 'QC_API_TOKEN', 'SHARADAR_API_KEY', 'MASSIVE_API_KEY',
            'POLYGON_API_KEY', 'EODHD_API_TOKEN', 'FMP_API_KEY'):
        monkeypatch.delenv(name, raising=False)


def session_records():
    evaluator = m.worker.previous.identity.evaluator
    axis = m.worker.previous.october._sessions()
    records = tuple({'schema': evaluator.SESSION_SCHEMA, 'session_index': index, 'session': day}
        for index, day in enumerate(axis))
    return records, axis


@pytest.fixture
def args(monkeypatch):
    monkeypatch.setattr(m, 'binding', lambda args: {'schema': 'synthetic', 'expected_head': args.expected_head,
        'caller_sha256': args.caller_sha256})
    return NS(expected_head='a' * 40, caller_sha256='b' * 64)


@pytest.fixture
def fixture(monkeypatch, tmp_path):
    real_fetch = m.fetch
    monkeypatch.setattr(m, '_security', lambda fd: ('synthetic-security',))
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    monkeypatch.setattr(m, 'headroom', lambda: None)
    monkeypatch.setattr(m, 'validate_source', lambda value: value)
    monkeypatch.setattr(m, 'REQUEST_COUNT', 3)
    monkeypatch.setattr(m, 'ORDER', (2, 0, 1))
    plan = {'schema': m.prices.PLAN_PRIVATE_SCHEMA, 'assignments': [], 'price_sessions': ['2021-01-04'],
        'full_axis_sha256': m.prices.FULL_AXIS_SHA256,
        'requests': [dict(ordinal=i, table='funds' if i == 2 else 'stocks', tickers=['SYN'],
            first='2020-12-31', last='2023-12-31' if i == 2 else '2021-12-31',
            parameters=m.prices._parameters(['SYN'], ('2020-12-31', '2023-12-31' if i == 2 else '2021-12-31')))
            for i in range(3)]}
    raw = m.canonical(plan)
    source = {'plan_pin': m.pin(raw), 'plan_summary': {'request_inventory_sha256': m.prices.digest(plan['requests']),
        'assignment_inventory_sha256': m.prices.digest([])}}
    fds = []
    for name in m.DATA_FILES:
        fd = os.open(tmp_path / name, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600); fds.append(fd)
    os.write(fds[0], raw)
    progress, contacts = [], []
    monkeypatch.setattr(m, 'emit', lambda value: progress.append(copy.deepcopy(value)))
    monkeypatch.setattr(m.time, 'sleep', lambda seconds: None)
    body = b'ticker,date,closeunadj,lastupdated\nSYN,2021-01-04,12.50,2026-10-13\n'
    def fetch(request, key, state, deadline):
        contacts.append(m.prices._request(request)['request_ordinal'])
        state.update(HTTP_status=200, HTTP_status_type='int'); return body
    monkeypatch.setattr(m, 'fetch', fetch)
    yield NS(plan=plan, source=source, fds=fds, progress=progress, contacts=contacts,
        body=body, deadline=time.monotonic() + 100, tmp=tmp_path, real_fetch=real_fetch)
    for fd in fds: os.close(fd)


def refuses(code, call):
    with pytest.raises(m.Refused) as caught: call()
    assert m.finite(caught.value) == code


def test_frozen_plan_and_original_source_pins_close_without_reading_data():
    selected = m.pins()
    assert len(selected) >= 183
    assert selected['scripts/arv2_r298_raw_price_acquisition.py'].startswith('229b3b')
    assert selected['scripts/arv2_keychain_connections.py'].startswith('bd9c086')
    for name, expected in selected.items(): assert m.sha((m.ROOT / name).read_bytes()) == expected
    assert m.ORDER[:2] == (1254, 1255) and m.ORDER[2:] == tuple(range(1254))
    assert m.DATA_PLAN['ac']['sha256'].startswith('4366e1e8')


def test_profile_is_finite_source_observation_not_admission():
    profile = m.profile_record()
    assert profile['keychain_lookups'] == 1 and profile['HTTP_retries'] == 0
    assert profile['request_count'] == 1256
    assert profile['CSV_semantics_only_in_separate_network_denied_worker_after_provider_actual_zero']
    assert profile['uncommitted_tail_inadmissible'] and not profile['cleanup_or_truncation']
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    assert len(m.canonical(profile)) < m.MAX_FRAME


@pytest.mark.parametrize('role', ('source', 'provider', 'authenticate', 'validate'))
def test_native_profiles_deny_keychain_and_limit_artifacts_and_network(role):
    value = m.native_profile(role)
    assert '(deny process-exec (literal "/usr/bin/security"))' in value
    assert '/Users/sheltonchen/Library/Keychains' in value and '/Library/Keychains' in value
    assert '(deny network*)' in value if role != 'provider' else 'remote tcp "*:443"' in value
    assert str(m.CONTROL) in value if role != 'validate' else '(deny file-read* (subpath' in value
    assert str(m.worker.previous.PACKAGE) in value if role == 'source' else str(m.worker.previous.PACKAGE) not in value
    assert m.DATA_PLAN['ac']['relative_path'] in value if role == 'source' else m.DATA_PLAN['ac']['relative_path'] not in value


def test_plan_pin_mismatch_refuses_before_requests(fixture):
    os.pwrite(fixture.fds[0], b'X', 0)
    refuses('plan', lambda: m.provider_observation(fixture.fds, fixture.source, 'synthetic-key', m._provider_state(), fixture.deadline))
    assert fixture.contacts == [] and os.fstat(fixture.fds[2]).st_size == 0


def test_fixed_funds_first_and_all_HTTP200_retained_before_semantics(fixture, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('CSV parser used by provider')
    monkeypatch.setattr(m.prices, 'analyze_response', forbidden)
    result = m.provider_observation(fixture.fds, fixture.source, 'synthetic-key', m._provider_state(), fixture.deadline)
    assert fixture.contacts == [2, 0, 1]
    assert result['application_dispatch_intents'] == result['completed_HTTP200_bodies'] == 3
    assert result['provider_request_count'] is None
    assert os.pread(fixture.fds[1], 10000, 0) == fixture.body * 3
    capture = [json.loads(line) for line in os.pread(fixture.fds[3], 10000, 0).splitlines()]
    assert [item['offset'] for item in capture] == [0, len(fixture.body), 2 * len(fixture.body)]
    assert [item['plan_ordinal'] for item in capture] == [2, 0, 1]
    assert fixture.progress[-1]['retained_corpus_bytes'] == 3 * len(fixture.body)


def test_first_fund_refusal_has_durable_intent_no_body_or_stock_request(fixture, monkeypatch):
    def refused(request, key, state, deadline):
        assert os.fstat(fixture.fds[2]).st_size > 0
        state.update(HTTP_status=403, HTTP_status_type='int'); raise m.Refused('http_refused')
    monkeypatch.setattr(m, 'fetch', refused)
    state = m._provider_state()
    refuses('http_refused', lambda: m.provider_observation(fixture.fds, fixture.source, 'synthetic-key', state, fixture.deadline))
    assert state['application_dispatch_intents'] == 1 and state['current_plan_ordinal'] == 2
    assert state['HTTP_status'] == 403 and state['completed_HTTP200_bodies'] == 0
    assert os.fstat(fixture.fds[1]).st_size == os.fstat(fixture.fds[3]).st_size == 0


def test_complete_offline_corpus_auth_checks_CSV_and_ranges(fixture):
    supplied = m.provider_observation(fixture.fds, fixture.source, 'synthetic-key', m._provider_state(), fixture.deadline)
    result = m.authenticate_observation(fixture.fds, fixture.source, supplied, fixture.deadline)
    assert result['request_count'] == 3 and result['observed_price_rows'] == 3
    assert result['absent_expected_cells'] == 0 and result['complete_contiguous_corpus_authenticated']
    assert result['corpus_pin'] == supplied['corpus_pin']


@pytest.mark.parametrize('kind', ('tail', 'body', 'range', 'dispatch', 'pin'))
def test_offline_auth_refuses_tail_corruption_gap_overlap_or_wrong_pin(fixture, kind):
    supplied = m.provider_observation(fixture.fds, fixture.source, 'synthetic-key', m._provider_state(), fixture.deadline)
    if kind == 'tail': os.write(fixture.fds[1], b'uncommitted')
    elif kind == 'body': os.pwrite(fixture.fds[1], b'X', 10)
    elif kind == 'pin': supplied['corpus_pin']['sha256'] = 'f' * 64
    else:
        fd = fixture.fds[3 if kind == 'range' else 2]
        raw = os.pread(fd, 10000, 0)
        changed = raw.replace(b'"offset":0', b'"offset":1', 1) if kind == 'range' else raw.replace(b'"plan_ordinal":2', b'"plan_ordinal":1', 1)
        assert len(changed) == len(raw); os.pwrite(fd, changed, 0)
        supplied['captures_pin' if kind == 'range' else 'dispatch_pin'] = m.pin(changed)
    with pytest.raises(m.Refused): m.authenticate_observation(fixture.fds, fixture.source, supplied, fixture.deadline)


def test_invalid_CSV_is_already_retained_when_offline_semantics_refuse(fixture, monkeypatch):
    monkeypatch.setattr(m, 'fetch', lambda request, key, state, deadline:
        (state.update(HTTP_status=200, HTTP_status_type='int') or b'not,a,valid,header\n'))
    supplied = m.provider_observation(fixture.fds, fixture.source, 'synthetic-key', m._provider_state(), fixture.deadline)
    assert os.fstat(fixture.fds[1]).st_size > 0 and supplied['completed_HTTP200_bodies'] == 3
    with pytest.raises(m.prices.Refused): m.authenticate_observation(fixture.fds, fixture.source, supplied, fixture.deadline)


def test_provider_refuses_corpus_bound_before_append(fixture, monkeypatch):
    monkeypatch.setattr(m, 'MAX_CORPUS', len(fixture.body) - 1)
    refuses('body_bound', lambda: m.provider_observation(fixture.fds, fixture.source, 'synthetic-key', m._provider_state(), fixture.deadline))
    assert os.fstat(fixture.fds[1]).st_size == 0


def test_partial_range_commit_preserves_uncommitted_tail_without_repair(fixture, monkeypatch):
    original = m._append
    def append(fd, item):
        if fd == fixture.fds[3]: raise m.Refused('journal')
        return original(fd, item)
    monkeypatch.setattr(m, '_append', append)
    refuses('journal', lambda: m.provider_observation(fixture.fds, fixture.source, 'synthetic-key', m._provider_state(), fixture.deadline))
    assert os.fstat(fixture.fds[1]).st_size == len(fixture.body)
    assert os.fstat(fixture.fds[3]).st_size == 0


class Response:
    def __init__(self, status, body, headers=None):
        self.status_code, self.body = status, body
        self.headers, self.history, self.reads = headers or {}, [], 0
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, chunk_size): self.reads += 1; yield self.body


@pytest.fixture
def transport_fixture(monkeypatch):
    state, response = m._provider_state(), Response(200, b'ticker,date,closeunadj,lastupdated\n')
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    def send(session, prepared, **kwargs):
        assert kwargs['allow_redirects'] is False and kwargs['stream'] is True and kwargs['verify'] is True
        assert kwargs['proxies'] == {} and 0 < kwargs['timeout'] <= 30
        response.url, response.request = prepared.url, prepared
        return response
    monkeypatch.setattr(m.OwnedSession, 'send', send)
    request = m.prices.PrivatePriceRequest({'schema': m.prices.REQUEST_SCHEMA, 'plan_sha256': 'a' * 64,
        'request_ordinal': 0, 'table': 'stocks', 'tickers': ['SYN'], 'endpoint': m.prices.ENDPOINTS['stocks'],
        'first': '2020-12-31', 'last': '2021-12-31',
        'parameters': m.prices._parameters(['SYN'], ('2020-12-31', '2021-12-31')),
        'expected_sessions': ['2021-01-04']})
    return NS(state=state, response=response, request=request, deadline=time.monotonic() + 50)


@pytest.mark.parametrize('status', (301, 302, 400, 401, 403, 429, 500, 503))
def test_failed_numeric_HTTP_never_reads_body(transport_fixture, status):
    v = transport_fixture; v.response.status_code = status
    refuses('http_refused', lambda: m.fetch(v.request, 'synthetic-key', v.state, v.deadline))
    assert v.response.reads == 0 and v.state['HTTP_status'] == status


@pytest.mark.parametrize('status', (True, '200', None, 99, 600))
def test_invalid_status_never_reads_body(transport_fixture, status):
    v = transport_fixture; v.response.status_code = status
    refuses('http_status', lambda: m.fetch(v.request, 'synthetic-key', v.state, v.deadline))
    assert v.response.reads == 0


def test_HTTP200_secret_echo_refuses_before_retention(transport_fixture):
    v = transport_fixture; v.response.body = b'echo synthetic-key'
    refuses('credential_echo', lambda: m.fetch(v.request, 'synthetic-key', v.state, v.deadline))


def test_HTTP200_CSV_quote_doubled_echo_refuses_before_any_corpus_range_commit(fixture, transport_fixture, monkeypatch):
    monkeypatch.setattr(m, 'fetch', fixture.real_fetch)
    transport_fixture.response.body = b'ticker,date,closeunadj,lastupdated\n"synthetic""key",2021-01-04,1,2026-10-13\n'
    state = m._provider_state()
    refuses('credential_echo', lambda: m.provider_observation(fixture.fds, fixture.source,
        'synthetic"key', state, fixture.deadline))
    assert state['application_dispatch_intents'] == 1 and state['HTTP_status'] == 200
    assert state['completed_HTTP200_bodies'] == state['retained_corpus_bytes'] == 0
    assert os.fstat(fixture.fds[1]).st_size == os.fstat(fixture.fds[3]).st_size == 0
    assert os.fstat(fixture.fds[2]).st_size > 0


@pytest.mark.parametrize('form', ('raw', 'URL', 'JSON', 'CSV', 'JSON_in_CSV'))
def test_finite_secret_encoding_inventory_preserves_old_forms_and_adds_CSV(transport_fixture, form):
    from urllib.parse import quote
    key = 'synthetic"key'
    v = transport_fixture
    variants = {'raw': key.encode('ascii'), 'URL': quote(key, safe='').encode('ascii'),
        'JSON': json.dumps(key)[1:-1].encode('ascii'), 'CSV': key.replace('"','""').encode('ascii'),
        'JSON_in_CSV': json.dumps(key)[1:-1].encode('ascii').replace(b'"',b'""')}
    v.response.body = b'prefix ' + variants[form] + b' suffix'
    refuses('credential_echo', lambda: m.fetch(v.request, key, v.state, v.deadline))
    assert set(m.transport._encodings(key)) <= set(m._secret_encodings(key))
    assert len(m._secret_encodings(key)) <= 2 * len(m.transport._encodings(key))


def test_HTTP200_bound_refuses(transport_fixture, monkeypatch):
    v = transport_fixture; monkeypatch.setattr(m, 'MAX_BODY', 2)
    refuses('body_bound', lambda: m.fetch(v.request, 'synthetic-key', v.state, v.deadline))


def test_HTTP200_transport_success_is_not_CSV_semantics(transport_fixture):
    v = transport_fixture; v.response.body = b'not CSV'
    assert m.fetch(v.request, 'synthetic-key', v.state, v.deadline) == b'not CSV'


def test_owned_session_disables_hidden_requests_redirect_body_read():
    response = NS(content=property(lambda self: (_ for _ in ()).throw(AssertionError('body'))))
    with m._session() as session:
        m._session_check(session)
        assert list(session.resolve_redirects(response, None, yield_requests=True)) == []
        assert session.adapters['https://'].max_retries.total == 0


def test_transport_cause_and_errno_are_finite(transport_fixture, monkeypatch):
    v = transport_fixture
    error = requests.exceptions.ConnectionError('do not disclose synthetic-secret')
    error.__cause__ = OSError(errno.ECONNREFUSED, 'private URL')
    monkeypatch.setattr(m.OwnedSession, 'send', lambda *args, **kwargs: (_ for _ in ()).throw(error))
    refuses('transport_connection', lambda: m.fetch(v.request, 'synthetic-key', v.state, v.deadline))
    assert v.state['OS_errno'] == errno.ECONNREFUSED and v.state['HTTP_status'] is None
    assert 'private' not in m.canonical(v.state).decode()


@pytest.mark.parametrize('error,expected', ((m.prices.Refused('header'), 'price_header'),
    (m.data_guard.Refused('byte_pin'), 'data_guard_byte_pin'),
    (m.worker.previous.Refused('catalog'), 'original_catalog')))
def test_source_and_CSV_finite_failure_categories_retained_without_raw_exception(error, expected):
    assert m.finite(error) == expected and expected in m.FINITE
    assert m.finite(ValueError('private URL token or row')) == 'unknown_exception'


def test_disk_and_FD_budgets_fail_before_any_store(monkeypatch):
    monkeypatch.setattr(m.resource, 'getrlimit', lambda kind: (64, 1024))
    refuses('descriptor_budget', m.headroom)
    monkeypatch.setattr(m.resource, 'getrlimit', lambda kind: (1024, 1024))
    monkeypatch.setattr(m.os, 'statvfs', lambda path: NS(f_bavail=1, f_frsize=4096))
    refuses('disk_headroom', m.headroom)


def test_external_validator_requires_actual_parent_exit_and_finite_preflight(args):
    raw = m.canonical({'binding': m.binding(args), 'preflight_failure': 'disk_headroom'}) + b'\n'
    assert m.validate_output(raw, 2, args)['preflight_failure'] == 'disk_headroom'
    for status in (0, None, True): refuses('output', lambda: m.validate_output(raw, status, args))
    refuses('output', lambda: m.validate_output(raw + b'trailing\n', 2, args))


@pytest.mark.parametrize('change', ('extra', 'count', 'physical', 'negative'))
def test_progress_closed_finite_and_request_count_unknown(change):
    value = m._progress(1, 1, 40)
    if change == 'extra': value['ticker'] = 'private'
    elif change == 'count': value['completed_HTTP200_bodies'] = 2
    elif change == 'physical': value['provider_request_count'] = 1
    else: value['retained_corpus_bytes'] = -1
    refuses('output', lambda: m.validate_progress(value))


def test_child_capture_real_tiny_process_frames_and_actual_exit(tmp_path, monkeypatch):
    progress = []; monkeypatch.setattr(m, 'emit', progress.append)
    raw = m.canonical(m._progress(1, 1, 8)) + b'\n' + m.canonical({'closed': True}) + b'\n'
    command = [sys.executable, '-B', '-c', 'import os;os.write(1,' + repr(raw) + ')']
    safe = {'PATH': '/usr/bin:/bin', 'TMPDIR': str(tmp_path), 'PYTHONPYCACHEPREFIX': str(tmp_path)}
    value, actual = m._capture_child(command, safe, b'{}', (), 5, progress=True)
    assert value == {'closed': True} and actual['actual_exit'] == 0 and actual['spawn_observed']
    assert len(progress) == 1 and actual['stdout_sha256'] == m.sha(raw)


@pytest.mark.parametrize('kind', ('noise', 'partial', 'timeout'))
def test_child_capture_reaps_only_own_child_and_retains_non_success_actual(tmp_path, kind):
    code = 'import os;os.write(2,b"noisy")' if kind == 'noise' else 'import os;os.write(1,b"partial")' if kind == 'partial' else 'import time;time.sleep(5)'
    safe = {'PATH': '/usr/bin:/bin', 'TMPDIR': str(tmp_path), 'PYTHONPYCACHEPREFIX': str(tmp_path)}
    value, actual = m._capture_child([sys.executable, '-B', '-c', code], safe, b'{}', (), .15 if kind == 'timeout' else 5)
    assert set(value) == {'capture_failure'} and actual['spawn_observed'] and type(actual['actual_exit']) is int
    if kind == 'timeout': assert actual['actual_exit'] != 0 and actual['bound'] == 'deadline'


def test_accept_child_requires_zero_actual_and_matching_binding(args):
    actual = {'actual_exit': 0, 'spawn_observed': True, 'bound': None, 'stdout_bytes': 3,
        'stdout_sha256': m.sha(b'{}\n'), 'stderr_bytes': 0, 'stderr_sha256': m.sha(b'')}
    value = {'binding': m.binding(args), 'role': 'source', 'result': {'test': True}}
    assert m._accept_child(value, actual, 'source', args) == {'test': True}
    for change in ('exit', 'binding', 'stderr'):
        a, v = copy.deepcopy(actual), copy.deepcopy(value)
        if change == 'exit': a['actual_exit'] = 2
        elif change == 'binding': v['binding']['expected_head'] = 'c' * 40
        else: a['stderr_bytes'] = 1
        with pytest.raises(m.Refused): m._accept_child(v, a, 'source', args)


@pytest.fixture
def pipeline(monkeypatch, tmp_path, args):
    control = tmp_path / 'parent' / 'AL'
    monkeypatch.setattr(m, 'CONTROL', control)
    monkeypatch.setattr(m, '_security', lambda fd: ('synthetic-security',))
    def walk(path):
        chain = tuple((os.stat(Path(*path.parts[:index + 1])).st_dev,
            os.stat(Path(*path.parts[:index + 1])).st_ino) for index in range(1, len(path.parts)))
        return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW), chain
    monkeypatch.setattr(m.admitted, '_storage_module', lambda: NS(_walk=walk))
    monkeypatch.setattr(m, 'headroom', lambda: None)
    monkeypatch.setattr(m, 'preflight', lambda *args: None)
    monkeypatch.setattr(m.environment, '_require_logging', lambda: None)
    monkeypatch.setattr(m, 'validate_source', lambda value: value)
    monkeypatch.setattr(m, 'REQUEST_COUNT', 2)
    monkeypatch.setattr(m, 'ORDER', (0, 1))
    source = {'plan_pin': m.pin(b'plan')}
    provider = {**m._provider_state(), 'application_dispatch_intents': 2, 'completed_HTTP200_bodies': 2,
        'retained_corpus_bytes': 8, 'current_plan_ordinal': 1, 'HTTP_status': 200, 'HTTP_status_type': 'int',
        'corpus_pin': m.pin(b'corpus!!'), 'dispatch_pin': m.pin(b'intents'), 'captures_pin': m.pin(b'captures'), 'provider_request_count': None}
    authentication = {'complete_contiguous_corpus_authenticated': True, 'all_CSV_schemas_validated': True,
        'request_count': 2, 'observed_price_rows': 0, 'absent_expected_cells': (5636 + 8) * m.prices.PRICE_SESSION_COUNT,
        'response_summary_stream_sha256': 'c' * 64,
        **{key: provider[key] for key in ('corpus_pin', 'dispatch_pin', 'captures_pin')}}
    progress = [m._progress(1, 1, 4), m._progress(2, 2, 8)]
    events = []
    def key(provider_name, *, timeout_seconds):
        assert events == ['source'] and provider_name == 'sharadar' and timeout_seconds <= 20
        events.append('keychain'); return 'synthetic-key'
    monkeypatch.setattr(m.keychain, 'load_key', key)
    def actual(value, prefix=b''):
        raw = prefix + m.canonical(value) + b'\n'
        return {'actual_exit': 0, 'spawn_observed': True, 'bound': None, 'stdout_bytes': len(raw),
            'stdout_sha256': m.sha(raw), 'stderr_bytes': 0, 'stderr_sha256': m.sha(b'')}
    def child(args, store, role, payload, runtime, deadline, *, key=None):
        assert 'claim.json' in store.held
        if role == 'source':
            assert events == [] and key is None
            m._write(store.held['plan-private.json']['fd'], b'plan'); store.refresh(('plan-private.json',))
        elif role == 'provider':
            assert events == ['source', 'keychain'] and key == 'synthetic-key'
        else: assert events == ['source', 'keychain', 'provider'] and key is None
        events.append(role)
        result = {'binding': m.binding(args), 'role': role,
            'result': {'source': source, 'provider': provider, 'authenticate': authentication}[role]}
        return result, actual(result, b''.join(m.canonical(value) + b'\n' for value in progress) if role == 'provider' else b'')
    monkeypatch.setattr(m, '_child', child)
    return NS(args=args, source=source, provider=provider, authentication=authentication,
        progress=progress, events=events, actual=actual, child=child, control=control)


def test_claim_then_source_zero_then_one_keychain_then_provider_then_offline_auth(pipeline):
    outcome = m.run(pipeline.args, time.monotonic() + 100)
    assert set(outcome) == {'result', 'report'}, outcome
    assert pipeline.events == ['source', 'keychain', 'provider', 'authenticate']
    assert (pipeline.control / 'claim.json').exists() and (pipeline.control / 'report.json').exists()
    assert all(outcome['result'][key] is False for key in m.FALSE_FLAGS)
    raw = b''.join(m.canonical(value) + b'\n' for value in pipeline.progress)
    raw += m.canonical({'binding': m.binding(pipeline.args), 'outcome': outcome}) + b'\n'
    assert m.validate_output(raw, 0, pipeline.args)['outcome'] == outcome


def test_source_nonzero_preserves_claim_and_never_inspects_credentials(pipeline, monkeypatch):
    def child(args, store, role, *rest, **kwargs):
        assert role == 'source' and 'claim.json' in store.held
        value = {'binding': m.binding(args), 'role': role, 'failure_code': 'input', 'provider_state': None}
        actual = pipeline.actual(value); actual['actual_exit'] = 2
        return value, actual
    monkeypatch.setattr(m, '_child', child)
    outcome = m.run(pipeline.args, time.monotonic() + 100)
    assert outcome['failure']['failure_code'] == 'input'
    assert pipeline.events == [] and outcome['failure']['state']['source_actual']['actual_exit'] == 2
    assert outcome['failure']['state']['credential_handoff_complete'] is False
    assert (pipeline.control / 'failure.json').exists()
    raw = m.canonical({'binding': m.binding(pipeline.args), 'outcome': outcome}) + b'\n'
    assert m.validate_output(raw, 2, pipeline.args)['outcome'] == outcome
    outcome['failure']['state']['child_packets']['source']['failure_code'] = 'source_binding'
    raw = m.canonical({'binding': m.binding(pipeline.args), 'outcome': outcome}) + b'\n'
    refuses('output', lambda: m.validate_output(raw, 2, pipeline.args))


@pytest.mark.parametrize('role', ('provider', 'authenticate'))
def test_exact_failed_child_packet_and_HTTP_state_bound_to_actual_stdout(pipeline, monkeypatch, role):
    original = pipeline.child
    def child(args, store, requested, payload, *rest, **kwargs):
        if requested != role: return original(args, store, requested, payload, *rest, **kwargs)
        failed_state = {**m._provider_state(), 'application_dispatch_intents': 2, 'completed_HTTP200_bodies': 1,
            'retained_corpus_bytes': 4, 'current_plan_ordinal': 1, 'HTTP_status': 403, 'HTTP_status_type': 'int'} if role == 'provider' else None
        value = {'binding': m.binding(args), 'role': role, 'failure_code': 'http_refused' if role == 'provider' else 'csv',
            'provider_state': failed_state}
        prefix = b''.join(m.canonical(value) + b'\n' for value in (pipeline.progress[:1] if role == 'provider' else []))
        actual = pipeline.actual(value, prefix); actual['actual_exit'] = 2
        return value, actual
    monkeypatch.setattr(m, '_child', child)
    outcome = m.run(pipeline.args, time.monotonic() + 100)
    assert 'failure' in outcome
    prefix = b''.join(m.canonical(value) + b'\n' for value in (pipeline.progress[:1] if role == 'provider' else pipeline.progress))
    raw = prefix + m.canonical({'binding': m.binding(pipeline.args), 'outcome': outcome}) + b'\n'
    assert m.validate_output(raw, 2, pipeline.args)['outcome'] == outcome
    altered = copy.deepcopy(outcome)
    altered['failure']['state']['child_packets'][role]['failure_code'] = 'input'
    if role == 'provider':
        altered['failure']['state']['child_packets'][role]['provider_state']['HTTP_status'] = 429
        altered['failure']['state']['provider_failure_state']['HTTP_status'] = 429
    raw = prefix + m.canonical({'binding': m.binding(pipeline.args), 'outcome': altered}) + b'\n'
    refuses('output', lambda: m.validate_output(raw, 2, pipeline.args))


def test_malformed_worker_packet_is_hash_only_capture_failure_not_raw_external_evidence(args):
    raw = {'binding': m.binding(args), 'role': 'provider', 'licensed_rows': ['never disclose']}
    closed = m._safe_child_packet(raw, args, 'provider', {})
    assert closed == {'capture_failure': 'worker_packet'}
    assert b'licensed' not in m.canonical(closed)


@pytest.mark.parametrize('stage', ('source', 'provider', 'authenticate', 'progress', 'report', 'exit'))
def test_external_validator_rejects_success_source_output_pin_or_actual_exit_mismatch(pipeline, stage):
    outcome = m.run(pipeline.args, time.monotonic() + 100)
    assert 'result' in outcome
    if stage in ('source', 'provider', 'authenticate'):
        key = {'source': 'source_actual', 'provider': 'provider_actual', 'authenticate': 'authentication_actual'}[stage]
        outcome['result'][key]['stdout_sha256'] = 'd' * 64
        outcome['report'] = m.pin(m.canonical({**m.binding(pipeline.args), 'result': outcome['result']}))
    elif stage == 'report': outcome['report']['sha256'] = 'd' * 64
    values = copy.deepcopy(pipeline.progress)
    if stage == 'progress': values[0]['retained_corpus_bytes'] += 1
    raw = b''.join(m.canonical(value) + b'\n' for value in values)
    raw += m.canonical({'binding': m.binding(pipeline.args), 'outcome': outcome}) + b'\n'
    refuses('output', lambda: m.validate_output(raw, 2 if stage == 'exit' else 0, pipeline.args))


def test_late_parent_postcheck_failure_never_accepts_report_or_retries(pipeline, monkeypatch):
    monkeypatch.setattr(m, 'preflight', lambda *args: (_ for _ in ()).throw(m.Refused('postflight')))
    outcome = m.run(pipeline.args, time.monotonic() + 100)
    assert outcome['failure']['failure_code'] == 'postflight'
    assert outcome['failure']['state']['authentication'] is not None
    assert not (pipeline.control / 'report.json').exists()
    assert pipeline.events == ['source', 'keychain', 'provider', 'authenticate']
    raw = b''.join(m.canonical(value) + b'\n' for value in pipeline.progress)
    raw += m.canonical({'binding': m.binding(pipeline.args), 'outcome': outcome}) + b'\n'
    assert m.validate_output(raw, 2, pipeline.args)['outcome']['failure']['claim_consumed']
    refuses('output', lambda: m.validate_output(raw, 0, pipeline.args))


def test_second_claim_never_reuses_or_repairs_existing_leaf(pipeline):
    assert 'result' in m.run(pipeline.args, time.monotonic() + 100)
    refuses('claim_spent', lambda: m.run(pipeline.args, time.monotonic() + 100))


def test_private_store_refuses_named_replacement_and_preserves_both_original_and_new(pipeline):
    with m.Store() as store:
        store.create('plan-private.json', b'original')
        path = pipeline.control / 'plan-private.json'
        path.rename(pipeline.control / 'old')
        path.write_bytes(b'changed')
        refuses('control_changed', store.verify)
        assert (pipeline.control / 'old').read_bytes() == b'original'


def test_inherited_start_marker_consumes_exact_scope_once(pipeline, monkeypatch):
    deadline = time.monotonic() + 100
    with m.Store() as store:
        store.write('claim.json', m.binding(pipeline.args))
        for name in m.DATA_FILES: store.create(name)
        packet = m.canonical({})
        store.write('source-intent.json', {**m.binding(pipeline.args), 'role': 'source', 'input_pin': m.pin(packet)})
        started = store.create('source-started.json')
        args = NS(**vars(pipeline.args), control_fd=store.fd, claim_fd=store.held['claim.json']['fd'],
            intent_fd=store.held['source-intent.json']['fd'], started_fd=started,
            data_fds=tuple(store.held[name]['fd'] for name in m.DATA_FILES))
        m._inherited(args, 'source', packet, deadline)
        assert os.fstat(started).st_size > 0
        refuses('worker_scope', lambda: m._inherited(args, 'source', packet, deadline))


@pytest.mark.parametrize('failure', (None, 'whole_binding', 'guard_exit', 'catalog_end'))
def test_genuine_catalog_and_all_binding_equality_guard_return_precede_plan_publication(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    events = []
    rows = [{'original_binding': index} for index in range(6151)]
    current = {'stocks': [{'binding': copy.deepcopy(row)} for row in rows]}
    if failure == 'whole_binding': current['stocks'][42]['binding']['original_binding'] = -1
    public = {'binding_contract': {'synthetic': True}}
    expected = {'binding_contract': public['binding_contract']}
    monkeypatch.setattr(m.ac_anchor, 'expected_summary', lambda: expected)
    monkeypatch.setattr(m.prices, 'AC_SUMMARY_SHA256', m.prices.digest(expected))
    monkeypatch.setattr(m.ac_anchor, 'observed_fact', lambda: {'private_file': m.DATA_PLAN['ac'],
        'producer': {'actual_exit': 0, 'bound': None}, 'validator': {'actual_exit': 0, 'bound': None}})
    monkeypatch.setattr(m.worker, '_load_plain', lambda deadline: events.append('load') or 'plain')
    records, axis = session_records()
    monkeypatch.setattr(m.worker, '_catalog', lambda plain, deadline: ('initial', 'record', {'session_axis': list(records)}, rows, public))
    def unchanged(*args):
        events.append('catalog-end')
        if failure == 'catalog_end': raise m.Refused('input')
    monkeypatch.setattr(m.worker, '_catalog_unchanged', unchanged)
    class Guard:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): events.append('guard-enter'); return self
        def read_all_once(self): events.append('read-once'); return {'ac': b'synthetic-only'}
        def verify(self): events.append('guard-verify')
        def __exit__(self, *args):
            events.append('guard-return')
            if failure == 'guard_exit': raise m.Refused('source_binding')
    monkeypatch.setattr(m.data_guard, 'FixedDataGuard', Guard)
    monkeypatch.setattr(m.prices, '_source_ac', lambda *args: current)
    monkeypatch.setattr(m.previous, 'source_binding', lambda: {'synthetic-spec': True})
    def prepare(*args, **kwargs):
        # Real frozen parser output is mandatory: this fixture does not replace
        # its schema/index/order/date validation with a synthetic string axis.
        assert kwargs['session_axis'] == axis and type(kwargs['session_axis']) is tuple
        assert m.prices._axis(kwargs['session_axis']) == [day for day in axis if m.prices.FIRST <= day <= m.prices.LAST]
        events.append('plan-memory')
        return {'synthetic-summary': True}, NS(_raw=b'private-plan')
    monkeypatch.setattr(m.prices, 'prepare_plan', prepare)
    fd = os.open(tmp_path / 'plan', os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    try:
        if failure:
            with pytest.raises(m.Refused): m.source_observation(fd, time.monotonic() + 20)
            assert os.fstat(fd).st_size == 0
            if failure == 'whole_binding': assert 'plan-memory' not in events
        else:
            observed = m.source_observation(fd, time.monotonic() + 20)
            assert observed['all_6151_full_bindings_equal'] and observed['source_guard_normal_return']
            assert os.pread(fd, 100, 0) == b'private-plan'
            assert events == ['load', 'guard-enter', 'read-once', 'plan-memory', 'catalog-end', 'guard-verify', 'guard-return']
    finally: os.close(fd)


def test_real_record_parser_recovers_full_public_axis_and_old_shape_reproduces_refusal():
    records, axis = session_records()
    assert len(records) == len(axis) == 3466
    assert m.prices.digest(list(axis)) == m.prices.FULL_AXIS_SHA256
    with pytest.raises(m.prices.Refused) as original:
        m.prices._axis(list(records))
    assert m.prices.finite(original.value) == 'axis'
    parsed = m.worker.previous.identity.evaluator._parse_sessions(tuple(records))
    assert parsed == axis
    selected = m.prices._axis(parsed)
    assert len(selected) == 1452 and selected[0] == '2020-12-31' and selected[-1] == '2026-10-13'


@pytest.mark.parametrize('mutation', ('schema', 'extra', 'index', 'boolean_index', 'order', 'duplicate', 'date', 'string'))
def test_real_record_parser_refuses_malformed_indices_order_or_schema(mutation):
    records, _ = session_records(); changed = copy.deepcopy(list(records)); index = 300
    if mutation == 'schema': changed[index]['schema'] = 'invented-schema'
    elif mutation == 'extra': changed[index]['unexpected'] = 'field'
    elif mutation == 'index': changed[index]['session_index'] += 1
    elif mutation == 'boolean_index': changed[index]['session_index'] = True
    elif mutation == 'order': changed[index]['session'], changed[index+1]['session'] = changed[index+1]['session'], changed[index]['session']
    elif mutation == 'duplicate': changed[index]['session'] = changed[index-1]['session']
    elif mutation == 'date': changed[index]['session'] = '2021-13-99'
    else: changed[index] = changed[index]['session']
    with pytest.raises(m.worker.previous.identity.evaluator._Error):
        m.worker.previous.identity.evaluator._parse_sessions(tuple(changed))


@pytest.mark.parametrize('mutation', ('count', 'hash'))
def test_parser_compatible_nonfrozen_axis_still_refused_by_unchanged_planner(mutation):
    records, _ = session_records(); changed = copy.deepcopy(list(records)); index = 300
    if mutation == 'count':
        changed.pop(index)
        for ordinal, row in enumerate(changed): row['session_index'] = ordinal
    else:
        # A valid ISO date between neighbors passes representation parsing but
        # is not the committed independent full NYSE axis.
        from datetime import date, timedelta
        left, right = date.fromisoformat(changed[index-1]['session']), date.fromisoformat(changed[index+1]['session'])
        candidates = [left + timedelta(days=offset) for offset in range(1, (right-left).days)]
        candidate = next((day for day in candidates if day.isoformat() != changed[index]['session']), None)
        if candidate is None:
            # A weekend gap is guaranteed elsewhere in this complete calendar.
            index = next(i for i in range(2,len(changed)-2) if (date.fromisoformat(changed[i+1]['session']) - date.fromisoformat(changed[i-1]['session'])).days > 2)
            left = date.fromisoformat(changed[index-1]['session'])
            candidate = left + timedelta(days=1)
            if candidate.isoformat() == changed[index]['session']: candidate += timedelta(days=1)
        changed[index]['session'] = candidate.isoformat()
    parsed = m.worker.previous.identity.evaluator._parse_sessions(tuple(changed))
    with pytest.raises(m.prices.Refused) as caught: m.prices._axis(parsed)
    assert m.prices.finite(caught.value) == 'axis'


def test_AP_difference_preserves_AM_bodies_except_exact_preflight_egress_and_encoding_delta():
    import ast
    from scripts import run_arv2_r298_raw_price_acquisition_v2 as base
    old = (m.ROOT / 'scripts/run_arv2_r298_raw_price_acquisition_v2.py').read_bytes()
    assert m.sha(old) == '88a1c9df85f29655d8069826ad3b22453023776299306f6ed192bbf64c427334'
    assert m.NEW_PINS['scripts/run_arv2_r298_raw_price_acquisition_v2.py'] == m.sha(old)
    assert m.CONTROL.name == 'R326-20261027-AP'
    assert m.ORDER == (1254,1255,*range(1254)) and m.REQUEST_COUNT == 1256
    assert m.NEW_PINS['scripts/arv2_r298_raw_price_acquisition.py'].startswith('229b3b')
    assert len(m.pins()) == 191 and m.FINITE == base.FINITE | {'public_CA'}
    assert m.FALSE_FLAGS == {**{key:value for key,value in base.FALSE_FLAGS.items()
        if key != 'credentials_persisted'}, 'recognized_credential_encodings_retained': False}
    assert m.NEW_PINS == {**base.NEW_PINS,
        'scripts/run_arv2_r298_raw_price_acquisition_v2.py': m.sha(old),
        'scripts/diagnose_arv2_r298_public_transport.py': 'ccaf46bfabcd7a4f0598bd04cd5d27126467ab5aea18cea5a6c2c919e989194c',
        'scripts/diagnose_arv2_r298_public_transport_v2.py': 'cd7fe6608ba4b56a748efe8fc1f738d94d6dbfd02da6f724b57644118db4d57d',
        'scripts/arv2_r298_ao_source_binding.py': '908d4b8143d2d981f638df93fb6f1f3956a6d0902ab104388b2dd6b5dfc0de2c'}
    original, updated = ast.parse(old), ast.parse(m.SOURCE.read_bytes())
    old_nodes = {node.name: node for node in original.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    new_nodes = {node.name: node for node in updated.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    assert set(new_nodes) == set(old_nodes) | {'transport_binding', '_public_CA_precheck', '_secret_encodings'}
    class Normalize(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) is str:
                node.value = node.value.replace('r326-ap-runtime-', 'r326-am-runtime-').replace(
                    ' (require-not (literal "/private/var/run/mDNSResponder"))', '')
            return node
        def visit_Expr(self, node):
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) \
                    and node.value.func.id in ('transport_binding', '_public_CA_precheck'):
                return None
            return self.generic_visit(node)
        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == '_secret_encodings':
                node.func = ast.Attribute(value=ast.Name(id='transport',ctx=ast.Load()), attr='_encodings',ctx=ast.Load())
            return self.generic_visit(node)
    for name, node in old_nodes.items():
        if name == 'profile_record': continue  # The new public proof/profile is separately tested below.
        normalized = Normalize().visit(copy.deepcopy(new_nodes[name]))
        assert ast.dump(normalized, include_attributes=False) == ast.dump(node, include_attributes=False), name
    old_assigns = {node.targets[0].id: node for node in original.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    new_assigns = {node.targets[0].id: node for node in updated.body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    for name, node in old_assigns.items():
        if name not in ('SOURCE', 'CONTROL', 'SCHEMA', 'NEW_PINS', 'FINITE', 'FALSE_FLAGS'):
            assert ast.dump(node, include_attributes=False) == ast.dump(new_assigns[name], include_attributes=False), name


def test_only_provider_gets_exact_observed_resolver_literal_no_netsrc_or_other_fence_change():
    from scripts import run_arv2_r298_raw_price_acquisition_v2 as base
    addition = ' (require-not (literal "/private/var/run/mDNSResponder"))'
    current = m.native_profile('provider')
    assert current.count(addition) == 1 and 'com.apple.netsrc' not in current
    # Scope paths necessarily change to the new AP claim. Every other policy
    # byte remains the fixed AM policy after removing the sole resolver clause.
    assert current.replace(addition, '').replace('R326-20261027-AP','R326-20261027-AM') == base.native_profile('provider')
    for role in ('source', 'authenticate', 'validate'):
        value = m.native_profile(role)
        assert addition not in value and '(deny network*)' in value
        assert value.replace('R326-20261027-AP','R326-20261027-AM') == base.native_profile(role)


def test_public_transport_binding_is_exact_observation_not_access_or_data_admission():
    result = m.transport_binding()
    assert result['observed_fact_sha256'] == m.AO_FACT_SHA256
    assert result['source_sha256'] == m.NEW_PINS['scripts/diagnose_arv2_r298_public_transport_v2.py']
    assert result['credential_free_transport_observed'] is True
    assert all(result[key] is False for key in ('data_endpoint_or_entitlement_proven',
        'historical_AM_cause_proven', 'fresh_operation_granted'))


@pytest.mark.parametrize('field', ('producer_exit', 'validator_exit', 'child_exit_bool', 'child_bound',
    'parent_output', 'child_output', 'source', 'profile', 'head', 'report', 'policy', 'exception', 'grant'))
def test_each_public_fact_component_remains_binding_even_if_digest_is_recomputed(monkeypatch, field):
    fact = m.transport_anchor.observed_fact()
    if field == 'producer_exit': fact['producer']['actual_exit'] = 2
    elif field == 'validator_exit': fact['validator']['actual_exit'] = 2
    elif field == 'child_exit_bool': fact['child']['actual_exit'] = False
    elif field == 'child_bound': fact['child']['bound'] = 'deadline'
    elif field == 'parent_output': fact['producer']['stdout_sha256'] = 'e' * 64
    elif field == 'child_output': fact['child']['stdout_bytes'] += 1
    elif field == 'source': fact['caller_sha256'] = 'e' * 64
    elif field == 'profile': fact['profile_sha256'] = 'e' * 64
    elif field == 'head': fact['expected_head'] = 'e' * 40
    elif field == 'report': fact['report']['sha256'] = 'e' * 64
    elif field == 'policy': fact['verified_policy_sha256'] = 'e' * 64
    elif field == 'exception': fact['only_policy_exception'] = '/private/var/run/other'
    else: fact['fresh_operation_granted'] = True
    monkeypatch.setattr(m.transport_anchor, 'observed_fact', lambda: copy.deepcopy(fact))
    monkeypatch.setattr(m, 'AO_FACT_SHA256', m.prices.digest(fact))
    refuses('source_binding', m.transport_binding)


def test_changed_observed_fact_cannot_refresh_its_own_frozen_pin(monkeypatch):
    fact = m.transport_anchor.observed_fact(); fact['DNS']['ordered_inventory_sha256'] = 'e' * 64
    monkeypatch.setattr(m.transport_anchor, 'observed_fact', lambda: fact)
    refuses('source_binding', m.transport_binding)


def test_public_CA_precheck_uses_exact_supplied_pinned_reader_bytes_before_any_use(monkeypatch):
    raw = b'synthetic public CA bytes only'
    monkeypatch.setattr(m.public_transport, 'CA_BYTES', len(raw))
    monkeypatch.setattr(m.public_transport, 'CA_SHA256', m.sha(raw))
    monkeypatch.setattr(m.public_transport, '_ca_bytes', lambda: raw)
    m._public_CA_precheck()
    monkeypatch.setattr(m.public_transport, '_ca_bytes', lambda: raw[:-1] + b'X')
    refuses('public_CA', m._public_CA_precheck)


@pytest.mark.parametrize('stop', ('fact', 'CA'))
def test_public_proof_and_CA_refusal_precede_private_source_credentials_or_environment(monkeypatch, stop):
    events = []
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: False)
    def fact():
        events.append('fact')
        if stop == 'fact': raise m.Refused('source_binding')
    def ca(): events.append('CA'); raise m.Refused('public_CA')
    monkeypatch.setattr(m, 'transport_binding', fact)
    monkeypatch.setattr(m, '_public_CA_precheck', ca)
    monkeypatch.setattr(m.environment, '_require_environment', lambda: events.append('environment'))
    monkeypatch.setattr(m.admitted.v5, '_git', lambda *args, **kwargs: (_ for _ in ()).throw(m.Refused('git_state')))
    args = NS(expected_head='a' * 40, caller_sha256='b' * 64)
    refuses('source_binding' if stop == 'fact' else 'public_CA', lambda: m.preflight(args, time.monotonic()+20))
    assert events == (['fact'] if stop == 'fact' else ['fact','CA'])


def test_new_module_has_no_old_operational_or_QC_call_and_no_serialized_key():
    raw = Path(m.__file__).read_text()
    assert 'keychain.load_key(\'sharadar\'' in raw
    assert 'worker._catalog_unchanged' in raw and "guard.read_all_once()['ac']" in raw
    assert "[item['binding'] for item in current['stocks']] == rows" in raw
    assert 'setrlimit' not in raw and 'os.truncate' not in raw and 'os.unlink' not in raw
    assert 'previous.run(' not in raw and 'prices.analyze_response' in raw
    assert "'source_actual'" in raw and "'provider_actual'" in raw
    assert 'assistant.dispatch_fence' not in sys.modules
