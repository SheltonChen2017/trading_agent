"""Synthetic lifecycle/claim/process checks; native denial required externally."""
import copy
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_r298_plain_backtest as m
from scripts import arv2_r298_plain_launch as remote


@pytest.fixture
def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64, operation='run',
              control_fd=None, worker_index=None, actual_exit=None)


@pytest.fixture
def control(tmp_path, monkeypatch):
    root = tmp_path / 'parent'
    root.mkdir(mode=0o700)
    path = root / 'control'
    monkeypatch.setattr(m, 'CONTROL', path)
    return path


def test_store_exclusive_metadata_and_canonical_readback(control):
    with m.Store() as store:
        pin = store.write('claim.json', {'value': 1})
        assert pin == {'byte_count': len(m.canonical({'value': 1})),
                       'sha256': m.sha(m.canonical({'value': 1}))}
        store.verify()
        assert (control / 'claim.json').read_bytes() == m.canonical({'value': 1})
        assert (control / 'claim.json').stat().st_mode & 0o777 == 0o600
        with pytest.raises(m.Refused): store.write('claim.json', {'value': 1})
    with pytest.raises(m.Refused): m.Store()


@pytest.mark.parametrize('name', ['../escape.json', 'bad_name.json', 'x.txt', '/tmp/x.json'])
def test_store_names_cannot_escape(control, name):
    with m.Store() as store:
        with pytest.raises(m.Refused): store.write(name, {})


def test_store_detects_named_leaf_replacement(control):
    with m.Store() as store:
        store.write('claim.json', {'value': 1})
        os.chmod(control / 'claim.json', 0o640)
        with pytest.raises(m.Refused): store.verify()


def test_store_detects_unowned_name(control):
    with m.Store() as store:
        fd = os.open(control / 'extra.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        with pytest.raises(m.Refused): store.verify()


@pytest.mark.parametrize('program,expected', [
    ("import sys;sys.stdout.write('okay')", (b'okay', b'', 0)),
    ("import sys;sys.stderr.write('synthetic');sys.exit(2)", (b'', b'synthetic', 2)),
])
def test_capture_real_separate_channels(tmp_path, program, expected):
    safe = m.capture_support._environment(tmp_path)
    raw, err, info = m.capture([str(m.PYTHON), '-B', '-c', program], safe, 5)
    assert (raw, err, info['actual_exit']) == expected
    assert info['bound'] is None and info['spawn_observed'] is True
    assert info['stdout_sha256'] == m.sha(raw) and info['stderr_sha256'] == m.sha(err)


def test_capture_finite_overflow_and_own_child_reap(tmp_path):
    safe = m.capture_support._environment(tmp_path)
    raw, err, info = m.capture([str(m.PYTHON), '-B', '-c',
        "import sys,time;sys.stdout.write('x'*10000);sys.stdout.flush();time.sleep(3)"],
        safe, 2, stdout_limit=1024)
    assert info['bound'] == 'channel_bound' and len(raw) <= 1024 + 16384
    assert type(info['actual_exit']) is int


def test_capture_deadline(tmp_path):
    raw, err, info = m.capture([str(m.PYTHON), '-B', '-c', 'import time;time.sleep(5)'],
        m.capture_support._environment(tmp_path), 0.08)
    assert info['bound'] == 'deadline' and info['actual_exit'] < 0


def test_capture_stdin_does_not_deadlock(tmp_path):
    payload = b'a' * 100000
    raw, err, info = m.capture([str(m.PYTHON), '-B', '-c',
        'import sys;data=sys.stdin.buffer.read();sys.stdout.write(str(len(data)))'],
        m.capture_support._environment(tmp_path), 5, input_bytes=payload)
    assert raw == b'100000' and not err and info['actual_exit'] == 0


@pytest.mark.parametrize('timeout', [True, 0, -1, float('inf'), float('nan'), 20000])
def test_capture_bad_budget_never_dispatches(timeout):
    with pytest.raises(m.Refused): m.capture(['not-executed'], {}, timeout)


def test_native_profiles_deny_network_credentials_and_validator_artifacts():
    normal, validator = m.native_profile(), m.native_profile(artifacts=True)
    for profile in (normal, validator):
        assert '(deny network*)' in profile
        assert '/Library/Keychains' in profile and '/usr/bin/security' in profile
    assert str(m.ROOT / 'artifacts') in validator
    assert str(m.admitted.CONTROL) not in normal  # new consumer may read pinned A11 report


@pytest.fixture
def workflow(control, monkeypatch):
    packet = {'synthetic': True}
    states = []
    class Runner:
        def __init__(self, record, sources, **kwargs):
            self.launch_receipt = self.terminal_receipt = None
            self.journal = kwargs['journal']
            states.append(self)
        def launch_once(self):
            self.launch_receipt = {'synthetic_id': 'owned'}
            self.journal('launch-receipt', {'event': 'launch_receipt', 'receipt': self.launch_receipt})
            self.terminal_receipt = {'status': 'Completed.'}
            return {'state': 'launched'}
        def poll_status(self, index): raise AssertionError('fast terminal must not poll')
        def read_once(self): return {'synthetic_accepted': True}
    packet = {'projection_record': '{}', 'source_pairs': []}
    monkeypatch.setattr(m, 'credential_shape', lambda: {'synthetic': 'synthetic'})
    monkeypatch.setattr(m, 'run_worker', lambda *a: copy.deepcopy(packet))
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    monkeypatch.setattr(remote.frozen, '_client', lambda: object())
    monkeypatch.setattr(remote, 'PlainLaunch', Runner)
    monkeypatch.setattr(m, 'preflight', lambda *a: None)
    return states, Runner


def test_run_claims_once_and_retains_fast_completed(control, workflow, args):
    result = m.run(args, time.monotonic() + 10)
    assert result['result']['terminal'] == 'completed'
    assert result['result']['launch'] == {'synthetic_id': 'owned'}
    assert (control / 'launch-receipt-launch-receipt.json').is_file()
    assert (control / 'claim.json').is_file()
    with pytest.raises(m.Refused): m.run(args, time.monotonic() + 10)


def test_runtime_error_retained_without_result_read(control, workflow, args, monkeypatch):
    states, Runner = workflow
    original = Runner.launch_once
    def failure(self):
        value = original(self)
        self.terminal_receipt = {'status': 'Runtime Error'}
        return value
    monkeypatch.setattr(Runner, 'launch_once', failure)
    monkeypatch.setattr(Runner, 'read_once', lambda _: pytest.fail('must not read failed result'))
    result = m.run(args, time.monotonic() + 10)
    assert result['result']['terminal'] == 'runtime_error'
    assert result['result']['result']['status'] == 'Runtime Error'


def test_failure_after_create_keeps_owned_identity(control, workflow, args, monkeypatch):
    _, Runner = workflow
    def lost(self):
        self.launch_receipt = {'synthetic_id': 'retained'}
        raise m.Refused('journal_failed')
    monkeypatch.setattr(Runner, 'launch_once', lost)
    result = m.run(args, time.monotonic() + 10)
    assert result['failure']['state']['launch'] == {'synthetic_id': 'retained'}
    assert result['failure']['failure_code'] == 'journal_failed'
    assert result['failure']['attempt_consumption'] == 'consumed_or_ambiguous_no_retry'


def test_final_admission_drift_refuses_after_result(control, workflow, args, monkeypatch):
    monkeypatch.setattr(m, 'run_worker', lambda *a: {'projection_record': '{}', 'source_pairs': [],
        **({'drift': True} if a[-1] == 1 else {})})
    result = m.run(args, time.monotonic() + 10)
    assert result['failure']['failure_code'] == 'admission_changed'
    assert not (control / 'report.json').exists()


@pytest.fixture
def wait_output(args):
    result = {'terminal': 'capacity_wait', 'application_dispatch_count': 18,
              'launch': None, 'result': None, **m.FALSE_FLAGS}
    report = m.canonical({**m.binding(args), 'result': result})
    return {'binding': m.binding(args), 'outcome': {'result': result,
        'report': {'byte_count': len(report), 'sha256': m.sha(report)}}}


def test_output_requires_external_actual_exit(args, wait_output):
    assert m.validate_output(m.canonical(wait_output), 0, args) == wait_output
    for actual in (True, False, None, '0', 2):
        with pytest.raises(m.Refused): m.validate_output(m.canonical(wait_output), actual, args)


@pytest.mark.parametrize('change', ['pin', 'head', 'flags', 'launch', 'count'])
def test_output_binding_and_wait_shape(args, wait_output, change):
    value = copy.deepcopy(wait_output)
    if change == 'pin': value['outcome']['report']['sha256'] = '0' * 64
    if change == 'head': value['binding']['expected_head'] = 'f' * 40
    if change == 'flags': value['outcome']['result']['formal_forward_ready'] = True
    if change == 'launch': value['outcome']['result']['launch'] = {}
    if change == 'count': value['outcome']['result']['application_dispatch_count'] = True
    with pytest.raises((m.Refused, remote.Refused)):
        m.validate_output(m.canonical(value), 0, args)


def test_import_does_not_construct_old_operational_stores():
    assert m.CONTROL != m.admitted.CONTROL
    assert m.NEW_PINS['scripts/run_arv2_r298_plain_readiness.py'] == m.capture_support.CALLER_SHA256
    assert 'assistant.dispatch_fence' not in sys.modules


@pytest.mark.parametrize('change', ['extra', 'raw', 'bool', 'negative', 'stage', 'launch', 'terminal'])
def test_failure_output_state_is_exact_finite_and_bound(args, change):
    state = {'stage': 'initial_admission', 'dispatch_count': 0, 'launch': None, 'terminal': None}
    failure = {'failure_code': 'admission_failed', 'state': state, 'provider_request_count': None,
               'attempt_consumption': 'consumed_or_ambiguous_no_retry', **m.FALSE_FLAGS}
    value = {'binding': m.binding(args), 'outcome': {'failure': failure}}
    assert m.validate_output(m.canonical(value), 2, args) == value
    if change == 'extra': state['extra'] = True
    if change == 'raw': state['raw_error'] = 'synthetic-sensitive-text'
    if change == 'bool': state['dispatch_count'] = True
    if change == 'negative': state['dispatch_count'] = -1
    if change == 'stage': state['stage'] = 'synthetic-sensitive-text'
    if change == 'launch': state['launch'] = {'raw': 'synthetic-sensitive-text'}
    if change == 'terminal': state['terminal'] = {'status': 'Completed.'}
    with pytest.raises((m.Refused, remote.Refused)):
        m.validate_output(m.canonical(value), 2, args)


def test_preclaim_refusal_is_finite_and_never_success(args):
    value = {'binding': m.binding(args), 'preflight_failure': 'source_pin'}
    assert m.validate_output(m.canonical(value), 2, args) == value
    with pytest.raises(m.Refused): m.validate_output(m.canonical(value), 0, args)
    value['preflight_failure'] = 'raw synthetic text'
    with pytest.raises(m.Refused): m.validate_output(m.canonical(value), 2, args)


@pytest.mark.parametrize('stage', ['credentials', 'support'])
def test_observer_preclaim_failure_is_finite_and_never_dispatches(args, monkeypatch, stage):
    def failure(*a, **kw): raise OSError('synthetic-sensitive-text-must-not-print')
    if stage == 'credentials': monkeypatch.setattr(m, 'credential_shape', failure)
    else:
        monkeypatch.setattr(m, 'credential_shape', lambda: {'QC_USER_ID': 'synthetic', 'QC_API_TOKEN': 'synthetic'})
        monkeypatch.setattr(m.tempfile, 'mkdtemp', failure)
    monkeypatch.setattr(m, 'capture', lambda *a, **kw: pytest.fail('no child allowed'))
    value, actual = m.observe(args)
    assert actual == 2 and value['parent'] is None and value['failure_code'] == 'os_error'
    assert 'synthetic-sensitive-text' not in json.dumps(value)
