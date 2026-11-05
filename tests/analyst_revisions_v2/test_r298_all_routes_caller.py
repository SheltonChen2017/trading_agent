"""Synthetic preparation orchestration, under native denial; no operations."""
import base64
import copy
import inspect
import io
import json
import os
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import prepare_arv2_r298_all_routes as m
from scripts import arv2_r298_launch_admission as old_admission
from tests.analyst_revisions_v2 import test_r298_sharadar_eligibility_v2_observation as fixture

KEY = fixture.KEY
ARGS = NS(expected_head='a' * 40, caller_sha256='b' * 64)


def refuse(code, function):
    with pytest.raises(m.Refused) as error:
        function()
    assert m.finite(error.value) == code


def actual(exit=0, bound=None, *, output=b'', errors=b''):
    return {'actual_exit': exit, 'bound': bound, 'spawn_observed': True,
        'dispatched_at': '2026-10-26T00:00:00Z', 'completion_observed_at': '2026-10-26T00:00:01Z',
        'stdout_bytes': len(output), 'stdout_sha256': m.sha(output),
        'stderr_bytes': len(errors), 'stderr_sha256': m.sha(errors)}


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('old operation or actual private input called')
    monkeypatch.setattr(m.previous, 'run', deny)
    monkeypatch.setattr(m.previous, 'observe', deny)
    monkeypatch.setattr(old_admission, 'admit', deny)
    monkeypatch.setattr(m.worker, '_load_plain', deny)


@pytest.fixture
def state(monkeypatch):
    transport = fixture.transport.__wrapped__(monkeypatch)
    state = NS(transport=transport, events=[], files={}, writes=[], worker_calls=0,
        fail_post=False, fail_report=False, worker_error=None, stores=0)
    monkeypatch.setattr(m, 'binding', lambda args: {'schema': m.SCHEMA,
        'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': 'c' * 64})
    def validate_summary(value):
        m.require(type(value) is dict and set(value) == {'schema', 'current_metadata', 'private_frame_byte_count',
            'private_frame_sha256'} and value['schema'] == 'synthetic-worker-summary'
            and type(value['private_frame_byte_count']) is int
            and value['private_frame_byte_count'] > 0
            and type(value['private_frame_sha256']) is str and len(value['private_frame_sha256']) == 64, 'summary')
        return copy.deepcopy(value)
    monkeypatch.setattr(m.worker, 'validate_summary', validate_summary)
    class MemoryStore:
        fd = 103
        def __init__(self):
            state.stores += 1
            m.require(state.stores == 1, 'claim_spent')
            self.files = state.files
            self.held = {}
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def verify(self): state.events.append('verify')
        def write(self, name, value):
            if name == 'report.json' and state.fail_report:
                raise m.Refused('control_write')
            return self.write_bytes(name, m.canonical(value), private=False)
        def write_bytes(self, name, raw, *, private):
            m.require(name not in self.files, 'control_name')
            self.files[name] = bytes(raw)
            self.held[name] = (100 + len(self.held), {})
            state.events.append('write:' + name)
            state.writes.append((name, bytes(raw), private))
            return {'byte_count': len(raw), 'sha256': m.sha(raw)}
    state.Store = MemoryStore
    monkeypatch.setattr(m, 'Store', MemoryStore)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: state.events.append('environment'))
    def key(*args, **kwargs):
        state.events.append('credential')
        assert 'claim.json' in state.files
        return KEY
    monkeypatch.setattr(m.keychain, 'load_key', key)
    def preflight(*args):
        state.events.append('postflight')
        if state.fail_post: raise m.Refused('source_pin')
    monkeypatch.setattr(m, 'preflight', preflight)
    state.private = {'synthetic_licensed_rows_private': ['PRIVATE-CAPTURE-ONLY']}
    state.private_raw = m.worker.canonical(state.private)
    state.summary = {'schema': 'synthetic-worker-summary', 'private_frame_byte_count': len(state.private_raw),
        'private_frame_sha256': m.sha(state.private_raw), 'current_metadata': {
            table: {'byte_count': len(state.transport.captures[name]), 'sha256': m.sha(state.transport.captures[name])}
            for table, name in zip(('stocks', 'funds'), m.BODY_NAMES[:2], strict=True)}}
    def worker(directory, buffers, args, deadline, observed_state):
        state.events.append('worker'); state.worker_calls += 1
        assert set(buffers) == set(m.BODY_NAMES) and all(name in state.files for name in m.BODY_NAMES)
        if state.worker_error: raise state.worker_error
        pins = {name: {'byte_count': len(buffers[name]), 'sha256': m.sha(buffers[name])}
            for name in m.BODY_NAMES[:2]}
        output = m.canonical({'summary': state.summary, 'private': state.private, 'capture_pins': pins})
        return copy.deepcopy(state.summary), state.private_raw, actual(output=output)
    state.fake_worker = worker
    state.real_invoke = m.invoke_worker
    monkeypatch.setattr(m, 'invoke_worker', worker)
    return state


def run():
    return m.run(ARGS, time.monotonic() + 100)


def test_claim_precedes_credentials_exact_four_requests_private_output_and_zero_QC(state):
    outcome = run()
    assert set(outcome) == {'result', 'report'}
    assert state.events.index('write:claim.json') < state.events.index('credential') < state.events.index('worker')
    assert len(state.transport.calls) == 4 and state.transport.bodies == [0, 1, 2, 3]
    assert state.worker_calls == 1
    result = outcome['result']
    assert result['stage'] == 'postflight' and all(result[key] is False for key in m.FALSE_FLAGS)
    assert result['captures']['routes-private.json'] == {'byte_count': len(state.private_raw),
        'sha256': m.sha(state.private_raw)}
    assert b'PRIVATE-CAPTURE-ONLY' not in m.canonical(outcome) and KEY.encode() not in m.canonical(outcome)
    assert state.files['routes-private.json'] == state.private_raw
    assert all('/data/' in url and not any(word in url for word in ('quantconnect', 'prices'))
        for url, _ in state.transport.calls)
    for index, (_, kwargs) in enumerate(state.transport.calls):
        assert kwargs['params'] == {**m.observation._query(m.ROLES[index])[1], 'api_key': KEY}
    envelope = m.canonical({'binding': m.binding(ARGS), 'outcome': outcome})
    assert m.validate_output(envelope, 0, ARGS)['outcome'] == outcome


@pytest.mark.parametrize('role', m.ROLES)
def test_all_success_bodies_are_retained_before_any_semantic_refusal(state, monkeypatch, role):
    metadata = m.observation._metadata
    status = m.status_v2.inspect_body
    def reject_metadata(raw, table, maximum):
        if role == table + '_metadata': raise m.observation.Refused('csv_header')
        return metadata(raw, table, maximum)
    def reject_status(raw, *, api_key, table):
        if role == table + '_status': raise m.status_v2.Refused('file')
        return status(raw, api_key=api_key, table=table)
    monkeypatch.setattr(m.observation, '_metadata', reject_metadata)
    monkeypatch.setattr(m.status_v2, 'inspect_body', reject_status)
    outcome = run()
    assert set(outcome) == {'failure'} and outcome['failure']['claim_consumed'] is True
    assert len(state.transport.calls) == 4 and state.transport.bodies == [0, 1, 2, 3]
    assert all(name in state.files for name in m.BODY_NAMES)
    assert state.worker_calls == 0 and 'routes-private.json' not in state.files
    assert KEY.encode() not in m.canonical(outcome)


@pytest.mark.parametrize('index', range(4))
def test_numeric_HTTP_refusal_retains_prior_successes_never_reads_failed_body_or_retries(state, index):
    state.transport.statuses[index] = 403
    outcome = run()
    failure = outcome['failure']
    assert failure['failure_code'] == 'provider_http_status'
    assert len(state.transport.calls) == index + 1 and state.transport.bodies == list(range(index))
    assert failure['state']['http_events'][-1]['http_status'] == 403
    assert set(failure['state']['captures']) == set(m.BODY_NAMES[:index])
    assert state.worker_calls == 0 and all(response.closed for response in state.transport.responses)
    assert len(m._events(failure['state']['http_events'])) == 2 * (index + 1)


def test_credentials_fail_after_claim_before_any_request(state, monkeypatch):
    def fail(*args, **kwargs): raise m.keychain.KeychainUnavailable('never-rendered')
    monkeypatch.setattr(m.keychain, 'load_key', fail)
    outcome = run()
    assert outcome['failure']['failure_code'] == 'credentials_unavailable'
    assert outcome['failure']['state']['stage'] == 'credentials'
    assert 'claim.json' in state.files and not state.transport.calls


@pytest.mark.parametrize('mode', ['postflight', 'report', 'worker'])
def test_late_failure_is_non_success_even_if_private_file_or_matching_summary_exists(state, mode):
    if mode == 'postflight': state.fail_post = True
    elif mode == 'report': state.fail_report = True
    else: state.worker_error = m.Refused('worker_failed')
    outcome = run()
    assert set(outcome) == {'failure'} and state.worker_calls == 1
    if mode != 'worker': assert state.files['routes-private.json'] == state.private_raw
    assert 'report.json' not in state.files
    envelope = m.canonical({'binding': m.binding(ARGS), 'outcome': outcome})
    assert m.validate_output(envelope, 2, ARGS)['outcome'] == outcome
    refuse('output', lambda: m.validate_output(envelope, 0, ARGS))


@pytest.mark.parametrize('change', ['private_pin', 'capture_pin', 'summary', 'trailing', 'duplicate', 'constant'])
def test_worker_frame_requires_closed_summary_exact_private_hash_and_capture_binding(state, change):
    pins = {name: {'byte_count': index + 10, 'sha256': 'd' * 64} for index, name in enumerate(m.BODY_NAMES[:2])}
    packet = {'summary': copy.deepcopy(state.summary), 'private': copy.deepcopy(state.private), 'capture_pins': pins}
    packet['summary']['current_metadata'] = dict(zip(('stocks', 'funds'), pins.values(), strict=True))
    expected = copy.deepcopy(pins)
    if change == 'private_pin': packet['summary']['private_frame_sha256'] = 'e' * 64
    elif change == 'capture_pin': packet['capture_pins'][m.BODY_NAMES[0]]['sha256'] = 'e' * 64
    elif change == 'summary': packet['summary']['authorized'] = True
    raw = m.canonical(packet)
    if change == 'trailing': raw += b'\n'
    elif change == 'duplicate': raw = b'{"summary":{},"summary":{}}'
    elif change == 'constant': raw = b'{"summary":NaN}'
    with pytest.raises(m.Refused): m.worker_packet(raw, expected)


@pytest.mark.parametrize('terminal', [actual(2), actual(None), actual(0, 'timeout'), actual(False)])
def test_worker_actual_exit_must_be_exact_success_integer_and_unambiguous(state, monkeypatch, terminal):
    directory = state.Store(); directory.write('claim.json', {'synthetic': True})
    buffers = {name: state.transport.captures[name] for name in m.BODY_NAMES}
    def capture(*args, **kwargs): return m.canonical({}), b'', terminal
    monkeypatch.setattr(m, 'capture', capture)
    with pytest.raises(m.Refused):
        state.real_invoke(directory, buffers, ARGS, time.monotonic() + 100,
            {'worker_actual': None, 'worker_failure_code': None})
    assert 'join-start.json' in state.files


def test_persistent_worker_start_precedes_single_inherited_FD_dispatch_no_private_stdout(state, monkeypatch):
    directory = state.Store(); directory.write('claim.json', {'synthetic': True})
    buffers = {name: state.transport.captures[name] for name in m.BODY_NAMES}
    calls = []
    def capture(command, safe, timeout, **kwargs):
        calls.append(command)
        assert 'join-start.json' in state.files and 'worker' in command
        assert kwargs['pass_fds'] == (directory.held['claim.json'][0], directory.held['join-start.json'][0], directory.fd)
        value = m._json_private(kwargs['input_bytes'], m.MAX_WORKER_INPUT)
        assert set(value) == {'stocks', 'funds', 'capture_pins'}
        assert base64.b64decode(value['stocks']) == buffers[m.BODY_NAMES[0]]
        packet = {'summary': state.summary, 'private': state.private, 'capture_pins': value['capture_pins']}
        output = m.canonical(packet)
        return output, b'', actual(output=output)
    monkeypatch.setattr(m, 'capture', capture)
    summary, raw, observed = state.real_invoke(directory, buffers, ARGS, time.monotonic() + 100,
        {'worker_actual': None, 'worker_failure_code': None})
    assert summary == state.summary and raw == state.private_raw and observed['actual_exit'] == 0
    assert len(calls) == 1
    refuse('control_name', lambda: state.real_invoke(directory, buffers, ARGS, time.monotonic() + 100,
        {'worker_actual': None, 'worker_failure_code': None}))
    assert len(calls) == 1


@pytest.mark.parametrize('value', [None, 0, 1, 2, True])
def test_direct_worker_cannot_replace_inherited_claim_marker_directory_with_stdin(value):
    args = NS(claim_fd=value, marker_fd=value, directory_fd=value)
    refuse('worker_binding', lambda: m._inherited(args, time.monotonic() + 100))


@pytest.mark.parametrize('change', ['none', 'wrong_mode', 'wrong_payload', 'duplicate_fd', 'replaced_name'])
def test_inherited_descriptors_match_exact_private_named_claim_and_start_marker(monkeypatch, tmp_path, change):
    monkeypatch.setattr(m, 'CONTROL', tmp_path)
    monkeypatch.setattr(m, 'binding', lambda args: {'schema': 'synthetic-inherited-claim'})
    monkeypatch.setattr(m.admitted, '_storage_module', lambda: NS(
        _walk=lambda path: (os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY), ())))
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    claim = os.open(tmp_path / 'claim.json', os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    marker = os.open(tmp_path / 'join-start.json', os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        claimed = {**m.binding(ARGS), 'local_only': True, 'old_controls_spent': change != 'wrong_payload'}
        os.write(claim, m.canonical(claimed))
        os.write(marker, m.canonical({**m.binding(ARGS), 'stage': 'native-all-binding-join'}))
        if change == 'wrong_mode': os.fchmod(claim, 0o644)
        if change == 'replaced_name':
            os.rename(tmp_path / 'claim.json', tmp_path / 'replaced-synthetic-claim.json')
            replacement = os.open(tmp_path / 'claim.json', os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            os.write(replacement, m.canonical(claimed)); os.close(replacement)
        args = NS(claim_fd=claim, marker_fd=claim if change == 'duplicate_fd' else marker, directory_fd=directory)
        if change == 'none': m._inherited(args, time.monotonic() + 100)
        else: refuse('worker_binding', lambda: m._inherited(args, time.monotonic() + 100))
    finally:
        for descriptor in (claim, marker, directory): os.close(descriptor)


def test_worker_dispatch_authenticates_inherited_identity_before_and_after_one_prepare(state, monkeypatch):
    inherited, prepared = [], []
    monkeypatch.setattr(m, '_inherited', lambda args, deadline: inherited.append('checked'))
    def prepare(stocks, funds, *, deadline):
        prepared.append((stocks, funds)); return state.summary, state.private
    monkeypatch.setattr(m.worker, 'prepare', prepare)
    raws = [state.transport.captures[name] for name in m.BODY_NAMES[:2]]
    packet = dict(zip(('stocks', 'funds'), (base64.b64encode(raw).decode('ascii') for raw in raws), strict=True))
    packet['capture_pins'] = {name: {'byte_count': len(raw), 'sha256': m.sha(raw)}
        for name, raw in zip(m.BODY_NAMES[:2], raws, strict=True)}
    monkeypatch.setattr(m.sys, 'stdin', NS(buffer=io.BytesIO(m.canonical(packet))))
    output = m.run_worker(ARGS, time.monotonic() + 100)
    assert inherited == ['checked', 'checked'] and prepared == [tuple(raws)]
    assert output == {'summary': state.summary, 'private': state.private, 'capture_pins': packet['capture_pins']}


@pytest.mark.parametrize('change', ['parent_nonzero', 'parent_bool', 'parent_timeout', 'validator_nonzero',
    'validator_bool', 'validator_stderr'])
def test_observer_requires_actual_parent_and_native_validator_success(state, monkeypatch, change):
    calls = []
    def capture(command, safe, timeout, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            terminal = actual(2 if change == 'parent_nonzero' else False if change == 'parent_bool' else 0,
                'timeout' if change == 'parent_timeout' else None)
            return m.canonical({'binding': m.binding(ARGS), 'preflight_failure': 'source_pin'}), b'', terminal
        terminal = actual(2 if change == 'validator_nonzero' else False if change == 'validator_bool' else 0)
        return m.canonical({'binding': m.binding(ARGS), 'preflight_failure': 'source_pin'}), b'noise' if change == 'validator_stderr' else b'', terminal
    monkeypatch.setattr(m, 'capture', capture)
    value, code = m.observe(ARGS)
    if change == 'parent_nonzero':
        assert code == 2 and value['parent']['actual_exit'] == 2
        assert value['output_authenticated'] is True and len(calls) == 2
        return  # Authenticated failure remains failure, never exit0.
    assert code == 2 and value['output_authenticated'] is False
    assert value['failure_code'] in ('parent_failed', 'validator_failed')
    assert len(calls) <= 2


def test_actual_exit_and_report_pin_are_both_required_for_output_success(state):
    outcome = run(); packet = {'binding': m.binding(ARGS), 'outcome': outcome}
    refuse('output', lambda: m.validate_output(m.canonical(packet), 2, ARGS))
    packet['outcome']['report']['sha256'] = 'f' * 64
    refuse('output', lambda: m.validate_output(m.canonical(packet), 0, ARGS))


@pytest.mark.parametrize('change', ['summary_metadata', 'worker_stdout_zero'])
def test_success_rejects_metadata_mismatch_or_impossible_empty_worker_frame_even_with_repinned_report(state, change):
    outcome = run()
    if change == 'summary_metadata':
        outcome['result']['summary']['current_metadata']['stocks']['sha256'] = 'f' * 64
    else:
        outcome['result']['worker_actual']['stdout_bytes'] = 0
        outcome['result']['worker_actual']['stdout_sha256'] = m.sha(b'')
    report = m.canonical({**m.binding(ARGS), 'result': outcome['result']})
    outcome['report'] = {'byte_count': len(report), 'sha256': m.sha(report)}
    with pytest.raises(m.Refused):
        m.validate_output(m.canonical({'binding': m.binding(ARGS), 'outcome': outcome}), 0, ARGS)


def test_failure_status_receipt_remains_bound_to_its_retained_body_pin(state):
    state.fail_post = True
    outcome = run()
    outcome['failure']['state']['captures']['stocks-status.json']['sha256'] = 'f' * 64
    with pytest.raises(m.Refused):
        m.validate_output(m.canonical({'binding': m.binding(ARGS), 'outcome': outcome}), 2, ARGS)


def test_profile_and_native_policy_have_only_fixed_metadata_roles_and_literal_source_scope(monkeypatch):
    monkeypatch.setattr(m, 'NEW_PINS', {name: 'e' * 64 for name in m.NEW_PINS})
    monkeypatch.setattr(m.pin_contract, 'pins', lambda: {})
    profile = m.profile_record()
    assert profile['roles'] == list(m.ROLES) and len(m.ROLES) == 4
    assert profile['maximum_application_dispatch_attempts'] == 4 and profile['provider_request_count'] is None
    assert all('ticker' not in query['parameters'] and 'from' not in query['parameters']
        for query in profile['queries'])
    assert set(profile['source_pins']) == set(m.NEW_PINS)
    assert all(value == 'e' * 64 for value in profile['source_pins'].values())
    policy, validator = m.native_profile(worker_mode=True), m.native_profile()
    assert '(deny network*)' in policy and '(deny network*)' in validator
    assert '/usr/bin/security' in policy and 'Library/Keychains' in policy
    assert str(m.ROOT / 'artifacts') in validator
    assert 'claim.json' in policy and 'join-start.json' in policy
    assert 'manifest.json' in policy and '01-tickers-years-full.zip' in policy
    assert '(require-not (subpath ' in policy and str(m.worker.PACKAGE) in policy
    assert 'R323-20261025-A11' not in policy and 'R297-20261013-D2' not in policy
    source = inspect.getsource(m)
    assert 'admitted.admit(' not in source and 'previous.run(' not in source and 'previous.observe(' not in source
    assert 'assistant.dispatch_fence' not in sys.modules


def test_placeholder_or_conflicting_selected_pins_refuse_before_source_use(monkeypatch):
    monkeypatch.setattr(m.pin_contract, 'pins', lambda: {})
    monkeypatch.setattr(m, 'NEW_PINS', {'scripts/new.py': 'UNFROZEN'})
    refuse('source_pin', m.pins)
    monkeypatch.setattr(m, 'NEW_PINS', {'scripts/new.py': 'a' * 64})
    monkeypatch.setattr(m.pin_contract, 'pins', lambda: {'scripts/new.py': 'b' * 64})
    refuse('source_pin', m.pins)
