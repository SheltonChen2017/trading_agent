"""Focused synthetic AA contract tests; no retained or production input reads."""
import copy
import inspect
import io
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import prepare_arv2_r298_all_routes_offline_v2 as m

ARGS = NS(expected_head='a' * 40, caller_sha256='b' * 64)


def refused(code, function):
    with pytest.raises(m.Refused) as caught:
        function()
    assert m.finite(caught.value) == code


def source_receipt():
    return {'schema': m.SCHEMA + '-retained-metadata-current-source',
        'files': {name: {**pin, 'current_metadata_sha256': 'd' * 64,
            'current_security_sha256': 'e' * 64} for name, pin in m.SOURCE_PINS.items()},
        'fresh_current_security_authenticated': True, 'fixed_retained_bytes_authenticated': True,
        'historical_metadata_preservation_proven': False, 'continuous_security_proven': False}


def actual(output=b'', *, exit=0, bound=None, errors=b''):
    return {'actual_exit': exit, 'bound': bound, 'spawn_observed': True,
        'dispatched_at': '2026-10-27T00:00:00Z', 'completion_observed_at': '2026-10-27T00:00:01Z',
        'stdout_bytes': len(output), 'stdout_sha256': m.sha(output),
        'stderr_bytes': len(errors), 'stderr_sha256': m.sha(errors)}


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('old operation, provider or actual private input called')
    for name in ('run', 'observe', 'run_worker', 'preflight'):
        monkeypatch.setattr(m.previous, name, deny)
    monkeypatch.setattr(m.previous.keychain, 'load_key', deny)
    monkeypatch.setattr(m.worker, '_load_plain', deny)
    monkeypatch.setattr(m.worker.previous, 'prepare', deny)


@pytest.fixture
def state(monkeypatch):
    state = NS(events=[], files={}, stores=0, prepares=0, fail_stage=None,
        private={'rows': ['SYNTHETIC-PRIVATE-ONLY']}, body={name: ('synthetic-' + name).encode()
            for name in m.SOURCE_NAMES})
    state.private_raw = m.worker.canonical(state.private)
    state.summary = {'schema': 'synthetic-offline-v2-summary', 'current_metadata': {
        table: m.SOURCE_PINS[name] for table, name in zip(('stocks', 'funds'), m.SOURCE_NAMES, strict=True)},
        'private_frame_byte_count': len(state.private_raw), 'private_frame_sha256': m.sha(state.private_raw)}
    monkeypatch.setattr(m, 'binding', lambda args: {'schema': m.SCHEMA,
        'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256, 'profile_sha256': 'c' * 64})

    class MemoryStore:
        def __init__(self):
            state.stores += 1
            m.require(state.stores == 1, 'claim_spent')
        def __enter__(self): return self
        def __exit__(self, *_): state.events.append('store_close')
        def verify(self): state.events.append('store_verify')
        def write(self, name, value): return self.write_bytes(name, m.canonical(value), private=False)
        def write_bytes(self, name, raw, *, private):
            m.require(name not in state.files, 'control_name')
            state.events.append('write:' + name)
            if state.fail_stage == name:
                raise m.Refused('control_write')
            if private:
                assert name == m.PRIVATE_NAME and 'source_return' in state.events
            state.files[name] = bytes(raw)
            return {'byte_count': len(raw), 'sha256': m.sha(raw)}

    class MemoryGuard:
        def __init__(self, *, deadline): state.events.append('guard_construct')
        def __enter__(self):
            assert 'claim.json' in state.files and 'source-start.json' in state.files
            state.events.append('source_enter'); return self
        def __exit__(self, kind, *_):
            state.events.append('source_exit')
            if state.fail_stage == 'guard_return' and kind is None:
                raise m.Refused('source_changed')
            if kind is None: state.events.append('source_return')
        def read_once(self): state.events.append('source_read'); return state.body
        def receipt(self):
            state.events.append('source_verify')
            if state.fail_stage == 'source_receipt': raise m.Refused('source_changed')
            return source_receipt()

    def prepare(stocks, funds, *, deadline):
        state.prepares += 1; state.events.append('prepare')
        assert state.prepares == 1 and 'join-start.json' in state.files
        assert 'source_enter' in state.events and 'source_exit' not in state.events
        assert (stocks, funds) == tuple(state.body[name] for name in m.SOURCE_NAMES)
        assert 0 < deadline - time.monotonic() <= m.PREPARE_SECONDS
        if state.fail_stage == 'prepare': raise m.worker.Refused('original_catalog_count')
        return copy.deepcopy(state.summary), copy.deepcopy(state.private)

    def summary(value):
        m.require(type(value) is dict and set(value) == {'schema', 'current_metadata',
            'private_frame_byte_count', 'private_frame_sha256'} and value['schema'] ==
            'synthetic-offline-v2-summary', 'worker_binding')
        return copy.deepcopy(value)

    def preflight(*args):
        state.events.append('postflight')
        if state.fail_stage == 'postflight': raise m.Refused('source_pin')

    monkeypatch.setattr(m, 'Store', MemoryStore)
    monkeypatch.setattr(m, 'SourceGuard', MemoryGuard)
    monkeypatch.setattr(m.worker, 'prepare', prepare)
    monkeypatch.setattr(m.worker, 'validate_summary', summary)
    monkeypatch.setattr(m, 'preflight', preflight)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: state.events.append('safe_environment'))
    return state


def run():
    return m.run(ARGS, time.monotonic() + 100)


def test_exclusive_claim_and_both_start_markers_precede_single_prepare_and_normal_guards_precede_publication(state):
    outcome = run()
    assert set(outcome) == {'result', 'report'}
    ordered = ['write:claim.json', 'write:source-start.json', 'source_enter', 'source_read',
        'write:join-start.json', 'prepare', 'source_exit', 'source_return',
        'write:routes-private.json', 'postflight', 'write:report.json']
    assert [state.events.index(name) for name in ordered] == sorted(state.events.index(name) for name in ordered)
    assert state.prepares == 1 and state.files[m.PRIVATE_NAME] == state.private_raw
    assert state.events.count('safe_environment') == 6
    for name in ('source_enter', 'prepare', 'write:routes-private.json', 'postflight'):
        assert 'safe_environment' in state.events[:state.events.index(name)]
    assert b'SYNTHETIC-PRIVATE-ONLY' not in m.canonical(outcome)
    value = {'binding': m.binding(ARGS), 'outcome': outcome}
    assert m.validate_output(m.canonical(value), 0, ARGS) == value
    assert all(outcome['result'][flag] is False for flag in m.FALSE_FLAGS)


@pytest.mark.parametrize('failure', ['source_receipt', 'prepare', 'guard_return', 'routes-private.json',
    'postflight', 'report.json'])
def test_terminal_failure_consumes_claim_and_never_replays_or_publishes_before_guard_return(state, failure):
    state.fail_stage = failure
    outcome = run()
    failed = outcome['failure']
    assert failed['claim_consumed'] is True and state.stores == 1 and state.prepares <= 1
    assert all(failed[flag] is False for flag in m.FALSE_FLAGS)
    if failure in ('source_receipt', 'prepare', 'guard_return'):
        assert m.PRIVATE_NAME not in state.files
    value = {'binding': m.binding(ARGS), 'outcome': outcome}
    assert m.validate_output(m.canonical(value), 2, ARGS) == value
    refused('claim_spent', run)


@pytest.mark.parametrize('fault', ['hash', 'size', 'current_metadata', 'private_type'])
def test_summary_and_private_bindings_refuse_before_publication(state, fault):
    if fault == 'hash': state.summary['private_frame_sha256'] = 'f' * 64
    elif fault == 'size': state.summary['private_frame_byte_count'] += 1
    elif fault == 'current_metadata': state.summary['current_metadata']['funds'] = {'byte_count': 1, 'sha256': 'f' * 64}
    else: state.private = ['not a private route record']
    failed = run()['failure']
    assert failed['failure_code'] in ('private_binding', 'worker_binding')
    assert m.PRIVATE_NAME not in state.files


@pytest.mark.parametrize('fault', ['extra', 'missing', 'bytes_bool', 'wrong_sha', 'security_hash',
    'flags', 'extra_file', 'flag_type'])
def test_source_receipt_closed_pins_and_current_only_claims(fault):
    value = source_receipt()
    if fault == 'extra': value['rows'] = []
    elif fault == 'missing': del value['files'][m.SOURCE_NAMES[0]]
    elif fault == 'bytes_bool': value['files'][m.SOURCE_NAMES[0]]['byte_count'] = True
    elif fault == 'wrong_sha': value['files'][m.SOURCE_NAMES[0]]['sha256'] = 'f' * 64
    elif fault == 'security_hash': value['files'][m.SOURCE_NAMES[0]]['current_security_sha256'] = 'invalid'
    elif fault == 'flags': value['continuous_security_proven'] = True
    elif fault == 'flag_type': value['fresh_current_security_authenticated'] = 1
    else: value['files']['claim.json'] = value['files'][m.SOURCE_NAMES[0]]
    refused('source_receipt', lambda: m.validate_source_receipt(value))


@pytest.mark.parametrize('fault', ['actual2', 'actual_bool', 'report_sha', 'guard', 'private_pin',
    'flag', 'schema', 'extra_private', 'prepare_return', 'source_receipt'])
def test_public_success_needs_real_exit_both_guards_closed_binding_and_report_hash(state, fault):
    value = {'binding': m.binding(ARGS), 'outcome': run()}
    exit = 0
    result = value['outcome']['result']
    if fault == 'actual2': exit = 2
    elif fault == 'actual_bool': exit = False
    elif fault == 'report_sha': value['outcome']['report']['sha256'] = 'f' * 64
    elif fault == 'guard': result['source_guard_returned'] = False
    elif fault == 'prepare_return': result['direct_prepare_returned'] = False
    elif fault == 'source_receipt': result['source_receipt'] = None
    elif fault == 'private_pin': result['private_pin']['sha256'] = 'f' * 64
    elif fault == 'flag': result['point_in_time_proven'] = True
    elif fault == 'schema': result['schema'] = m.previous.SCHEMA
    else: result['private'] = {'rows': ['must never appear']}
    with pytest.raises(m.Refused): m.validate_output(m.canonical(value), exit, ARGS)


@pytest.mark.parametrize('fault', ['producer_nonzero', 'producer_bool', 'producer_timeout',
    'producer_noise', 'producer_binding', 'validator_nonzero', 'validator_bool', 'validator_noise', 'validator_binding'])
def test_no_data_observer_requires_exact_native_producer_and_separate_validator_actuals(state, monkeypatch, fault):
    value = {'binding': m.binding(ARGS), 'outcome': run()}
    raw = m.canonical(value)
    calls = []
    def capture(command, safe, timeout, **kwargs):
        calls.append((command, safe, timeout, kwargs))
        assert command[:2] == ['/usr/bin/sandbox-exec', '-p']
        assert '(deny network*)' in command[2] and '/usr/bin/security' in command[2]
        producer = len(calls) == 1
        errors = b'noise' if fault == ('producer_noise' if producer else 'validator_noise') else b''
        exit = (2 if fault == ('producer_nonzero' if producer else 'validator_nonzero') else
            False if fault == ('producer_bool' if producer else 'validator_bool') else 0)
        if fault == 'producer_nonzero' and not producer:
            # A real external validator refuses a success envelope paired
            # with observed producer exit2, rather than fabricating exit0.
            refused('output', lambda: m.validate_output(raw, 2, ARGS))
            exit = 2
        output = raw if not (fault == 'validator_binding' and not producer) else m.canonical({'wrong': 'metadata'})
        checked = actual(output, exit=exit, errors=errors,
            bound='deadline' if fault == 'producer_timeout' and producer else None)
        if fault == 'producer_binding' and producer: checked['stdout_sha256'] = 'f' * 64
        if not producer:
            assert kwargs['input_bytes'] == raw and timeout == m.VALIDATOR_SECONDS
        return output, errors, checked
    monkeypatch.setattr(m, 'capture', capture)
    outer, code = m.observe(ARGS)
    assert code == 2 and outer['output_authenticated'] is False
    assert len(calls) == (1 if fault.startswith('producer_') and fault != 'producer_nonzero' else 2)
    assert outer['failure_code'] in ('parent_failed', 'validator_failed')


def test_observer_authenticates_failure_without_reclassifying_it_success(state, monkeypatch):
    state.fail_stage = 'prepare'
    raw = m.canonical({'binding': m.binding(ARGS), 'outcome': run()})
    calls = []
    def capture(command, safe, timeout, **kwargs):
        calls.append(command)
        return raw, b'', actual(raw, exit=2 if len(calls) == 1 else 0)
    monkeypatch.setattr(m, 'capture', capture)
    outer, code = m.observe(ARGS)
    assert code == 2 and outer['output_authenticated'] is True and outer['failure_code'] is None
    assert outer['output']['outcome']['failure']['claim_consumed'] is True and len(calls) == 2


def test_observer_public_only_success_broker_never_opens_private_output(state, monkeypatch):
    value = {'binding': m.binding(ARGS), 'outcome': run()}; raw = m.canonical(value)
    calls = []
    def capture(command, safe, timeout, **kwargs):
        calls.append(command)
        return raw, b'', actual(raw)
    monkeypatch.setattr(m, 'capture', capture)
    outer, code = m.observe(ARGS)
    assert code == 0 and outer['output_authenticated'] is True and outer['output'] == value
    assert b'SYNTHETIC-PRIVATE-ONLY' not in m.canonical(outer)
    assert len(calls) == 2


def test_profile_frozen_sources_and_nonnested_native_scope_are_explicit(monkeypatch):
    monkeypatch.setattr(m.previous, 'pins', lambda: {'scripts/existing-' + str(i) + '.py': 'd' * 64 for i in range(164)})
    monkeypatch.setattr(m, 'NEW_PINS', {name: 'e' * 64 for name in m.NEW_PINS})
    profile = m.profile_record()
    assert len(profile['source_pins']) == 167 and profile['parent_seconds'] == 600
    assert profile['outer_seconds'] == 630 and profile['direct_prepare_seconds'] == 450
    assert profile['validator_seconds'] == 20 and profile['maximum_control_files'] == 12
    assert profile['one_native_producer_no_nested_sandbox_or_inner_child'] is True
    assert all(profile[flag] is False for flag in m.FALSE_FLAGS)
    producer, validator = m.native_profile(mode='producer'), m.native_profile(mode='validator')
    assert '(deny network*)' in producer and '(deny network*)' in validator
    assert '/usr/bin/security' in producer and 'Library/Keychains' in producer
    assert str(m.CONTROL) in producer and str(m.SOURCE_DIRECTORY / m.SOURCE_NAMES[0]) in producer
    assert str(m.ROOT / 'artifacts') in validator and str(m.SOURCE_DIRECTORY) not in validator
    assert 'R323-20261025-A11' not in producer and 'R297-20261013-D2' not in producer
    assert 'stocks-status.json' not in producer and 'funds-status.json' not in producer
    assert str(m.SOURCE_DIRECTORY / 'report.json') not in producer
    source = inspect.getsource(m)
    assert 'previous.run(' not in source and 'previous.observe(' not in source
    assert 'worker' not in inspect.signature(m.native_profile).parameters
    assert 'assistant.dispatch_fence' not in sys.modules


@pytest.mark.parametrize('fault', ['zero', 'placeholder', 'conflict', 'baseline_count'])
def test_unfrozen_or_conflicting_source_pin_map_refuses(fault, monkeypatch):
    baseline = {'scripts/existing-' + str(i) + '.py': 'd' * 64 for i in range(164)}
    monkeypatch.setattr(m.previous, 'pins', lambda: baseline)
    additions = {'scripts/new.py': 'e' * 64}
    if fault == 'zero': additions['scripts/new.py'] = '0' * 64
    elif fault == 'placeholder': additions['scripts/new.py'] = 'UNFROZEN'
    elif fault == 'conflict': additions['scripts/existing-1.py'] = 'f' * 64
    else: baseline.pop('scripts/existing-1.py')
    monkeypatch.setattr(m, 'NEW_PINS', additions)
    refused('source_pin', m.pins)


@pytest.fixture
def source_fixture(tmp_path, monkeypatch):
    root = tmp_path / 'synthetic-root'; root.mkdir(mode=0o755); root.chmod(0o755)
    source = root / 'artifacts/analyst_revisions_v2/newrule_all_routes/R326-20261026-Z'
    for part in (source.parent.parent.parent, source.parent.parent, source.parent, source):
        part.mkdir(mode=0o700)
    pins = {}
    for name in m.SOURCE_NAMES:
        raw = ('synthetic-full-current-data-' + name).encode()
        path = source / name; path.write_bytes(raw); path.chmod(0o600)
        pins[name] = {'byte_count': len(raw), 'sha256': m.sha(raw)}
    monkeypatch.setattr(m, 'ROOT', root); monkeypatch.setattr(m, 'SOURCE_DIRECTORY', source)
    monkeypatch.setattr(m, 'SOURCE_PINS', pins); monkeypatch.chdir(root)
    return NS(root=root, source=source, pins=pins)


def test_real_synthetic_source_guard_full_chain_both_held_files_one_read_and_normal_return(source_fixture):
    fixture = source_fixture
    with m.SourceGuard(deadline=time.monotonic() + 30) as guard:
        assert sum(row['leaf'] for row in guard.objects) == 2
        values = guard.read_once(); receipt = guard.receipt()
        assert set(values) == set(m.SOURCE_NAMES)
        assert all(m.sha(values[name]) == pin['sha256'] for name, pin in fixture.pins.items())
        refused('source_read_spent', guard.read_once)
        assert m.validate_source_receipt(receipt) == receipt
    assert guard.active is False and not guard.objects
    refused('source_state', guard.__enter__)


@pytest.mark.parametrize('change', ['content', 'mode', 'replace_name', 'extra_link', 'directory_mode'])
def test_real_synthetic_source_guard_detects_current_drift_without_repair(source_fixture, change):
    fixture = source_fixture
    with pytest.raises(m.Refused):
        with m.SourceGuard(deadline=time.monotonic() + 30) as guard:
            guard.read_once()
            path = fixture.source / m.SOURCE_NAMES[0]
            if change == 'content': path.write_bytes(b'changed')
            elif change == 'mode': path.chmod(0o644)
            elif change == 'extra_link': os.link(path, fixture.source / 'synthetic-extra-link')
            elif change == 'directory_mode': fixture.source.chmod(0o755)
            else:
                path.rename(fixture.source / 'synthetic-retained-old')
                path.write_bytes(b'changed'); path.chmod(0o600)
    assert guard.active is False and not guard.objects


def test_real_synthetic_source_guard_refuses_byte_pin_and_initial_symlink(source_fixture):
    fixture = source_fixture
    m.SOURCE_PINS[m.SOURCE_NAMES[0]]['sha256'] = 'f' * 64
    with m.SourceGuard(deadline=time.monotonic() + 30) as guard:
        refused('source_bytes', guard.read_once)
        refused('source_read_spent', guard.read_once)
    path = fixture.source / m.SOURCE_NAMES[0]
    path.rename(fixture.source / 'synthetic-retained-old')
    path.symlink_to(fixture.source / 'synthetic-retained-old')
    with pytest.raises(m.Refused):
        with m.SourceGuard(deadline=time.monotonic() + 30): pass


def test_real_new_control_store_is_exclusive_bounded_held_and_preserves_failure_leaf(tmp_path, monkeypatch):
    control = tmp_path / 'synthetic-AA-parent/synthetic-AA'
    monkeypatch.setattr(m, 'CONTROL', control)
    with m.Store() as store:
        pin = store.write('claim.json', {'synthetic': True})
        assert pin == {'byte_count': len(m.canonical({'synthetic': True})),
            'sha256': m.sha(m.canonical({'synthetic': True}))}
        private = b'synthetic-private-in-cache-only'
        private_pin = store.write_bytes(m.PRIVATE_NAME, private, private=True)
        assert private_pin == {'byte_count': len(private), 'sha256': m.sha(private)}
        held = store.held[m.PRIVATE_NAME][0]
        assert store._read(held, len(private)) == private
        refused('control_name', lambda: store.write('claim.json', {}))
        refused('control_name', lambda: store.write_bytes('stocks-metadata.csv', b'denied', private=True))
        refused('control_name', lambda: store.write('../elsewhere.json', {}))
        refused('control_bound', lambda: store.write_bytes('empty.json', b'', private=False))
        refused('claim_spent', m.Store)
        store.verify()
    assert control.is_dir() and {path.name for path in control.iterdir()} == {'claim.json', m.PRIVATE_NAME}
    with pytest.raises(OSError): os.fstat(held)


@pytest.mark.parametrize('change', ['content', 'mode', 'name', 'extra_name'])
def test_real_owned_control_detects_external_drift_without_cleanup(tmp_path, monkeypatch, change):
    control = tmp_path / 'synthetic-AA-parent/synthetic-AA'
    monkeypatch.setattr(m, 'CONTROL', control)
    with m.Store() as store:
        store.write('claim.json', {'synthetic': True})
        path = control / 'claim.json'
        if change == 'content': path.write_bytes(b'changed')
        elif change == 'mode': path.chmod(0o644)
        elif change == 'extra_name': (control / 'synthetic-unexpected').write_bytes(b'extra')
        else:
            path.rename(control / 'synthetic-retained-old')
            path.write_bytes(b'changed'); path.chmod(0o600)
        refused('control_changed' if change in ('extra_name', 'name') else 'capture_changed', store.verify)
    assert control.is_dir()


def test_real_selected_public_source_pin_closure_is_explicit_and_matches_without_refresh():
    pins = m.pins()
    assert len(pins) == 167
    for name, pin in pins.items():
        assert m.sha((m.ROOT / name).read_bytes()) == pin
    assert m.NEW_PINS['scripts/prepare_arv2_r298_all_routes.py'] == \
        '0b46e5048c86e764494106efd22b419c1c800401be207691274db5f8cae476d3'


def test_cli_parent_and_validator_use_alarm_and_preflight_before_any_operation(monkeypatch):
    events, stdout = [], io.BytesIO()
    class Alarm:
        def __init__(self, deadline):
            assert 0 < deadline - time.monotonic() <= m.DEADLINE_SECONDS
            events.append('alarm_construct')
        def __enter__(self): events.append('alarm_enter')
        def __exit__(self, *_): events.append('alarm_exit')
    monkeypatch.setattr(m.admitted.helpers, '_alarm', Alarm)
    monkeypatch.setattr(m, 'preflight', lambda *args: events.append('preflight'))
    monkeypatch.setattr(m.environment, '_bootstrap_cli_logging', lambda: events.append('logging'))
    monkeypatch.setattr(m, 'binding', lambda args: {'synthetic': True})
    def run(args, deadline):
        events.append('run'); return {'failure': {'synthetic': True}}
    monkeypatch.setattr(m, 'run', run)
    monkeypatch.setattr(m.sys, 'stdout', NS(buffer=stdout))
    assert m.main(['run', '--expected-head', ARGS.expected_head, '--caller-sha256', ARGS.caller_sha256]) == 2
    assert events == ['alarm_construct', 'alarm_enter', 'preflight', 'logging', 'run', 'alarm_exit']
    assert json.loads(stdout.getvalue()) == {'binding': {'synthetic': True},
        'outcome': {'failure': {'synthetic': True}}}


@pytest.mark.parametrize('deadline', [None, True, float('nan'), float('inf'), -1])
def test_invalid_deadline_refuses_before_source_or_claim_operations(deadline):
    refused('deadline', lambda: m.remaining(deadline))
    refused('deadline', lambda: m.SourceGuard(deadline=deadline))


@pytest.fixture
def public_preflight(monkeypatch):
    raw = m.SOURCE.read_bytes()
    args = NS(expected_head='a' * 40, caller_sha256=m.sha(raw))
    state = NS(raw=raw, args=args, calls=[], change=None)
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: False)
    monkeypatch.setattr(m.environment, '_require_environment', lambda: None)
    monkeypatch.setattr(m, 'pins', lambda: {m.SOURCE.relative_to(m.ROOT).as_posix():
        'f' * 64 if state.change == 'selected_pin' else m.sha(raw)})
    values = {('rev-parse', '--show-toplevel'): str(m.ROOT),
        ('branch', '--show-current'): m.admitted.frozen.BRANCH,
        ('rev-parse', 'HEAD'): args.expected_head, ('status', '--porcelain'): ''}
    def git(command, deadline, *args):
        state.calls.append(command)
        if command[0] == 'cat-file':
            return b'wrong committed source bytes' if state.change == 'committed_blob' else raw
        value = values[tuple(command)]
        if state.change == tuple(command): value = 'concurrent or mismatched synthetic state'
        return value.encode('ascii')
    monkeypatch.setattr(m.admitted.v5, '_git', git)
    return state


def test_preflight_binds_exact_host_clean_root_branch_head_source_and_committed_blob(public_preflight):
    fixture = public_preflight
    m.preflight(fixture.args, time.monotonic() + 30)
    assert fixture.calls[:4] == [['rev-parse', '--show-toplevel'], ['branch', '--show-current'],
        ['rev-parse', 'HEAD'], ['status', '--porcelain']]
    assert fixture.calls[-1] == ['cat-file', 'blob', fixture.args.expected_head + ':'
        + m.SOURCE.relative_to(m.ROOT).as_posix()]


@pytest.mark.parametrize('change', [('rev-parse', '--show-toplevel'), ('branch', '--show-current'),
    ('rev-parse', 'HEAD'), ('status', '--porcelain'), 'selected_pin', 'caller_pin', 'committed_blob'])
def test_preflight_concurrent_git_or_source_mismatch_refuses_without_refresh(public_preflight, change):
    fixture = public_preflight; fixture.change = change
    if change == 'caller_pin': fixture.args.caller_sha256 = 'f' * 64
    refused('git_state' if type(change) is tuple else 'source_pin',
        lambda: m.preflight(fixture.args, time.monotonic() + 30))


def test_preflight_test_host_and_invalid_args_refuse_before_git(public_preflight, monkeypatch):
    fixture = public_preflight
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: True)
    refused('host', lambda: m.preflight(fixture.args, time.monotonic() + 30))
    assert fixture.calls == []
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: False)
    fixture.args.expected_head = 'not a frozen commit'
    refused('arguments', lambda: m.preflight(fixture.args, time.monotonic() + 30))
    assert fixture.calls == []
