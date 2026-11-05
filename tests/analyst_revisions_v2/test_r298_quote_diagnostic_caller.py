"""A13 synthetic caller tests; native denial required by the test runner."""
import copy
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_r298_quote_diagnostic as m
from scripts import arv2_r298_quote_diagnostic_remote as remote
from tests.analyst_revisions_v2 import test_quote_diagnostic_projection as projection_fixtures


@pytest.fixture(autouse=True)
def no_private_or_operational_fallback(monkeypatch):
    def fail(*_, **__): raise AssertionError('unmocked operational seam')
    for module, names in ((m.prior, ('main', 'run', 'observe', 'worker', 'run_worker')),
        (m.admitted, ('main', '_execute', '_recover', '_worker', 'authenticate_storage')),
        (m.admitted.prep, ('main', 'construct')), (m.admission, ('admit',))):
        for name in names:
            monkeypatch.setattr(module, name, fail)


@pytest.fixture
def args():
    return NS(expected_head='a' * 40, caller_sha256='b' * 64, operation='run',
              control_fd=None, worker_index=None, actual_exit=None)


@pytest.fixture
def control(tmp_path, monkeypatch):
    parent = tmp_path / 'parent'
    parent.mkdir(mode=0o700)
    target = parent / 'a13'
    monkeypatch.setattr(m, 'CONTROL', target)
    return target


@pytest.fixture(scope='module')
def projected():
    public = projection_fixtures.public.__wrapped__()
    result = projection_fixtures.build(public)
    return result


@pytest.fixture
def packet(projected, monkeypatch):
    record = projected.to_record()
    monkeypatch.setattr(m, 'PROJECTION_SHA256', projected.projection_sha256)
    monkeypatch.setattr(m, 'PROFILE_SHA256', record['profile_sha256'])
    monkeypatch.setattr(m, 'SOURCE_MANIFEST_SHA256', remote.SOURCE_MANIFEST_SHA256)
    return {'admission_authenticated': True, 'readiness_pin': m.admission.readiness_pin(),
        'storage_receipt': m.admitted._storage_receipt(),
        'projection_record': projected.record_bytes.decode('ascii'),
        'source_pairs': [[name, raw.decode('ascii')] for name, raw in projected.source_pairs]}


def compiled():
    return {**remote._binding(), 'compile_id': 'a13-synthetic-compile'}


def launched():
    return {**compiled(), 'backtest_id': 'a13-synthetic-backtest', 'backtest_name': remote.BACKTEST_NAME}


def terminal(status='Runtime Error'):
    base = compiled() if status == 'BuildError' else launched()
    return {**base, 'status': status, **({'failure_evidence': remote.failure_evidence(
        {}, 'compile_error' if status == 'BuildError' else 'runtime_error')} if status != 'Completed.' else {})}


def result_output(args, name='capacity_wait'):
    result = {'terminal': name, 'application_dispatch_count': 25,
        'compiled': compiled(), 'launch': None if name in ('capacity_wait', 'compile_error') else launched(),
        'result': terminal('BuildError') if name == 'compile_error' else terminal() if name == 'runtime_error' else None,
        **m.FALSE_FLAGS}
    raw = m.canonical({**m.binding(args), 'result': result})
    return {'binding': m.binding(args), 'outcome': {'result': result,
        'report': {'byte_count': len(raw), 'sha256': m.sha(raw)}}}


def test_new_protocol_has_distinct_unallocated_control_and_frozen_utility_reuse():
    assert m.CONTROL.name == 'R323-20261025-B'
    assert m.CONTROL != m.prior.CONTROL != m.admitted.CONTROL
    assert m.capture is m.prior.capture and m.credential_shape is m.prior.credential_shape
    assert m.NEW_PINS['scripts/run_arv2_r298_plain_backtest.py'] == '56b286ddff9ec934c9309e58753618264b089069b8de95436c900c9658a9e654'
    assert m.profile_record()['attempt'] == 13
    assert m.profile_record()['source_uploads'] == 2 and m.profile_record()['new_compiles'] == 1
    assert m.profile_record()['max_dispatches'] == 420 and m.MAX_FILES == 1024
    assert m.profile_record()['a12_control_read'] is False
    assert 'assistant.dispatch_fence' not in sys.modules


def test_store_claim_is_exclusive_canonical_and_held_named(control):
    with m.Store() as store:
        value = {'attempt': 13}
        assert store.write('claim.json', value) == {'sha256': m.sha(m.canonical(value)), 'byte_count': len(m.canonical(value))}
        assert (control / 'claim.json').read_bytes() == m.canonical(value)
        assert (control / 'claim.json').stat().st_mode & 0o777 == 0o600
        with pytest.raises(m.Refused): store.write('claim.json', value)
    with pytest.raises(m.Refused): m.Store()


@pytest.mark.parametrize('name', ['../escape.json', '/tmp/a.json', 'bad_name.json', 'x.txt', 'claim.json/x'])
def test_store_rejects_other_paths(control, name):
    with m.Store() as store:
        with pytest.raises(m.Refused): store.write(name, {})


@pytest.mark.parametrize('mutation', ['mode', 'new', 'replacement', 'inplace'])
def test_store_detects_endpoint_change(control, mutation):
    with m.Store() as store:
        store.write('claim.json', {'attempt': 13})
        target = control / 'claim.json'
        if mutation == 'mode': target.chmod(0o640)
        elif mutation == 'new': (control / 'extra.json').write_bytes(b'{}\n')
        elif mutation == 'replacement': target.unlink(); target.write_bytes(b'{}\n'); target.chmod(0o600)
        else: target.write_bytes(target.read_bytes())
        with pytest.raises(m.Refused): store.verify()


def test_public_packet_binds_native_admission_and_diagnostic_projection(packet):
    raw, pairs = m.validate_packet(packet)
    assert m.sha(raw) == m.PROJECTION_SHA256 and len(pairs) == 11
    assert b'synthetic licensed raw row' not in m.canonical(packet)


@pytest.mark.parametrize('change', ['extra', 'exit-bool', 'exit', 'report', 'storage', 'source',
    'source-order', 'projection', 'admission', 'tuple', 'opaque'])
def test_public_packet_tampering_refuses(packet, change):
    if change == 'extra': packet['raw_rows'] = []
    elif change == 'exit-bool': packet['readiness_pin']['actual_readiness_exit'] = False
    elif change == 'exit': packet['readiness_pin']['actual_readiness_exit'] = 2
    elif change == 'report': packet['readiness_pin']['sha256'] = 'f' * 64
    elif change == 'storage': packet['storage_receipt']['actual_storage_exit'] = 2
    elif change == 'source': packet['source_pairs'][0][1] += '\n'
    elif change == 'source-order': packet['source_pairs'].reverse()
    elif change == 'projection': packet['projection_record'] += '\n'
    elif change == 'admission': packet['admission_authenticated'] = 1
    elif change == 'tuple': packet['source_pairs'][0] = tuple(packet['source_pairs'][0])
    else: packet['source_pairs'][0][1] = object()
    with pytest.raises((ValueError, TypeError)):
        m.validate_packet(packet)


def test_native_worker_inherits_only_own_fd_and_authenticates_intent(control, packet, projected, args, monkeypatch):
    order = []
    for key in ('QC_USER_ID', 'QC_API_TOKEN'): monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(m, 'preflight', lambda *_: order.append('preflight'))
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: order.append('environment'))
    old_packet = {'readiness_pin': packet['readiness_pin'], 'storage_receipt': packet['storage_receipt']}
    monkeypatch.setattr(m.admission, 'admit', lambda deadline: order.append('admit') or old_packet)
    def build(value, **kwargs):
        assert value is old_packet and kwargs['expected_patcher_sha256'] == m.PATCHER_SHA256
        order.append('project')
        return projected
    monkeypatch.setattr(m.projection, 'build_projection', build)
    with m.Store() as store:
        args.worker_index, args.control_fd = 0, store.fd
        store.write('worker-0-intent.json', {**m.binding(args), 'worker_index': 0})
        assert m.worker(args, time.monotonic() + 100) == packet
        store.verify()
    assert order == ['admit', 'project', 'preflight', 'environment']


@pytest.mark.parametrize('bad', ['wrong-fd', 'wrong-index', 'bool-index', 'missing-intent', 'wrong-binding', 'credentials'])
def test_worker_refuses_scope_before_private_admission(control, args, monkeypatch, bad):
    for key in ('QC_USER_ID', 'QC_API_TOKEN'): monkeypatch.delenv(key, raising=False)
    with m.Store() as store:
        args.worker_index, args.control_fd = 0, store.fd
        if bad == 'wrong-fd': args.control_fd = -1
        elif bad == 'wrong-index': args.worker_index = 2
        elif bad == 'bool-index': args.worker_index = False
        if bad != 'missing-intent':
            store.write('worker-0-intent.json', {**m.binding(args), 'worker_index': 1 if bad == 'wrong-binding' else 0})
        if bad == 'credentials': monkeypatch.setenv('QC_API_TOKEN', 'synthetic-only')
        with pytest.raises((m.Refused, OSError)):
            m.worker(args, time.monotonic() + 100)


def test_capture_inherits_native_denial_and_passes_only_the_own_directory_fd(control, tmp_path):
    with m.Store() as store:
        body = {'synthetic': True}
        store.write('worker-0-intent.json', body)
        code = ('import hashlib,os,sys;fd=int(sys.argv[1]);'
            'leaf=os.open("worker-0-intent.json",os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd);'
            'raw=os.read(leaf,65536);os.close(leaf);'
            'sys.stdout.write(hashlib.sha256(raw).hexdigest())')
        # The test process is already under native network/artifact denial;
        # its tiny synthetic child inherits it. Production's parent is outside
        # that test sandbox and applies the explicit native worker profile.
        raw, stderr, observed = m.capture([str(m.PYTHON), '-B', '-c', code, str(store.fd)],
            m.capture_support._environment(tmp_path), 5, stdout_limit=1024, pass_fds=(store.fd,))
        assert observed['actual_exit'] == 0 and observed['bound'] is None and not stderr
        assert raw.decode('ascii') == m.sha(m.canonical(body))
        store.verify()


@pytest.mark.parametrize('actual', [0, False, None, 2])
def test_worker_dispatch_strips_credentials_binds_fd_and_requires_actual_zero(control, args, packet, monkeypatch, actual):
    calls = []
    monkeypatch.setenv('QC_USER_ID', 'synthetic-user')
    monkeypatch.setenv('QC_API_TOKEN', 'synthetic-token')
    def capture(command, env, timeout, **kwargs):
        calls.append(command)
        assert 'worker' in command and command[0] == '/usr/bin/sandbox-exec'
        assert not {'QC_USER_ID', 'QC_API_TOKEN'} & set(env)
        assert kwargs['pass_fds'] == (store.fd,) and kwargs['stdout_limit'] == m.MAX_PACKET
        assert timeout <= 120
        return m.canonical({'binding': m.binding(args), 'packet': packet}), b'', {'actual_exit': actual, 'bound': None}
    monkeypatch.setattr(m, 'capture', capture)
    with m.Store() as store:
        if type(actual) is int and actual == 0:
            assert m.run_worker(args, store, time.monotonic() + 100, 0) == packet
        else:
            with pytest.raises(m.Refused, match='admission_failed'):
                m.run_worker(args, store, time.monotonic() + 100, 0)
        with pytest.raises(m.Refused): m.run_worker(args, store, time.monotonic() + 100, 0)
    assert len(calls) == 1


@pytest.fixture
def workflow(control, args, monkeypatch):
    events = []
    packet = {'projection_record': '{}', 'source_pairs': []}
    class Runner:
        def __init__(self, record, sources, *, request, journal):
            self.compile_receipt = self.launch_receipt = self.terminal_receipt = None
            self.request, self.journal = request, journal
            self.mode = 'completed'
            self.polls = []
            events.append('runner')
        def prepare_once(self):
            events.append('prepare')
            self.compile_receipt = compiled()
            self.journal('compile-receipt', {'event': 'compile_receipt', 'receipt': self.compile_receipt})
            return self.compile_receipt
        def poll_compile(self, index):
            self.polls.append(index)
            events.append('compile')
            return {**self.compile_receipt, 'state': 'BuildSuccess'}
        def launch_once(self):
            events.append('launch')
            self.launch_receipt = launched()
            self.terminal_receipt = terminal('Completed.')
            return {'state': 'launched'}
        def poll_status(self, index): raise AssertionError('fast terminal must not poll')
        def read_once(self): events.append('read'); return {'synthetic_result': True}
        def read_failure_once(self): events.append('failure-detail'); return self.terminal_receipt
    def worker(args, store, deadline, index):
        assert (control / 'claim.json').is_file()
        events.append('worker-' + str(index))
        return copy.deepcopy(packet)
    def client(): events.append('credentials'); return object()
    monkeypatch.setattr(m, 'credential_shape', lambda: {})
    monkeypatch.setattr(m, 'run_worker', worker)
    monkeypatch.setattr(remote, 'QuoteDiagnostic', Runner)
    monkeypatch.setattr(remote.previous.frozen, '_client', client)
    monkeypatch.setattr(m, 'preflight', lambda *_: None)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    monkeypatch.setattr(m.time, 'sleep', lambda seconds: events.append(('sleep', seconds)))
    return NS(events=events, Runner=Runner)


def test_workflow_claim_before_admission_before_credentials_and_final_recheck(control, args, workflow):
    result = m.run(args, time.monotonic() + 500)
    assert result['result']['terminal'] == 'completed'
    assert workflow.events == ['worker-0', 'credentials', 'runner', 'prepare', ('sleep', 1),
        'compile', 'launch', 'read', 'worker-1']
    assert (control / 'compile-receipt-compile-receipt.json').is_file()
    assert (control / 'report.json').is_file()
    with pytest.raises(m.Refused): m.run(args, time.monotonic() + 500)


def test_compile_failure_has_no_capacity_launch_or_aggregate(control, args, workflow, monkeypatch):
    def poll(self, index):
        self.terminal_receipt = terminal('BuildError')
        return {**self.compile_receipt, 'state': 'BuildError'}
    monkeypatch.setattr(workflow.Runner, 'poll_compile', poll)
    result = m.run(args, time.monotonic() + 500)
    assert result['result']['terminal'] == 'compile_error'
    assert result['result']['launch'] is None
    assert 'launch' not in workflow.events and 'read' not in workflow.events
    assert 'failure-detail' not in workflow.events


def test_compile_budget_is_spent_without_repeated_prepare(control, args, workflow, monkeypatch):
    monkeypatch.setattr(workflow.Runner, 'poll_compile', lambda self, index: {**self.compile_receipt, 'state': 'Building'})
    result = m.run(args, time.monotonic() + 500)
    assert result['failure']['failure_code'] == 'compile_budget'
    assert workflow.events.count('prepare') == 1
    assert workflow.events.count(('sleep', 1)) == 120
    assert 'launch' not in workflow.events


def test_runtime_failure_reads_only_error_detail_without_restart(control, args, workflow, monkeypatch):
    original = workflow.Runner.launch_once
    def create(self):
        value = original(self)
        self.terminal_receipt = terminal()
        return value
    monkeypatch.setattr(workflow.Runner, 'launch_once', create)
    result = m.run(args, time.monotonic() + 500)
    assert result['result']['terminal'] == 'runtime_error'
    assert workflow.events.count('launch') == 1 and 'read' not in workflow.events
    assert workflow.events.count('failure-detail') == 1


def test_empty_list_error_is_replaced_by_bounded_detail_context(control, args, workflow, monkeypatch):
    original = workflow.Runner.launch_once
    def create(self):
        value = original(self)
        self.terminal_receipt = terminal()
        assert self.terminal_receipt['failure_evidence']['known_runtime_code'] is None
        return value
    def detail(self):
        workflow.events.append('failure-detail')
        self.terminal_receipt = {**self.launch_receipt, 'status': 'Runtime Error',
            'failure_evidence': remote.failure_evidence({'error': 'NewruleError: '
                'execution_price_end_not_current|cache=quote_bar|trade=fresh_non_fill_forward'
                '|quote=stale|price_trade=equal'}, 'runtime_error')}
        return self.terminal_receipt
    monkeypatch.setattr(workflow.Runner, 'launch_once', create)
    monkeypatch.setattr(workflow.Runner, 'read_failure_once', detail)
    outcome = m.run(args, time.monotonic() + 500)
    evidence = outcome['result']['result']['failure_evidence']
    assert outcome['result']['terminal'] == 'runtime_error'
    assert evidence['known_runtime_code'] == 'execution_price_end_not_current'
    assert evidence['diagnostic_context']['cache_class'] == 'quote_bar'
    assert evidence['diagnostic_context']['trade_bar'] == 'fresh_non_fill_forward'
    assert evidence['raw_error_retained'] is evidence['cause_authenticated'] is False
    assert workflow.events.count('failure-detail') == 1 and 'read' not in workflow.events
    envelope = {'binding': m.binding(args), 'outcome': outcome}
    assert m.validate_output(m.canonical(envelope), 2, args) == envelope


def test_error_detail_refusal_keeps_original_terminal_and_does_not_retry(control, args, workflow, monkeypatch):
    original = workflow.Runner.launch_once
    def create(self):
        value = original(self)
        self.terminal_receipt = terminal()
        return value
    def detail(self):
        workflow.events.append('failure-detail')
        raise m.Refused('diagnostic_detail_refused')
    monkeypatch.setattr(workflow.Runner, 'launch_once', create)
    monkeypatch.setattr(workflow.Runner, 'read_failure_once', detail)
    outcome = m.run(args, time.monotonic() + 500)
    assert outcome['failure']['failure_code'] == 'diagnostic_detail_refused'
    assert outcome['failure']['state']['stage'] == 'failure_detail'
    assert outcome['failure']['state']['terminal'] == terminal()
    assert workflow.events.count('failure-detail') == 1 and 'read' not in workflow.events
    envelope = {'binding': m.binding(args), 'outcome': outcome}
    assert m.validate_output(m.canonical(envelope), 2, args) == envelope


def test_capacity_wait_is_three_observations_no_job(control, args, workflow, monkeypatch):
    monkeypatch.setattr(workflow.Runner, 'launch_once', lambda self: {'state': 'wait'})
    result = m.run(args, time.monotonic() + 500)
    assert result['result']['terminal'] == 'capacity_wait'
    assert result['result']['launch'] is None
    assert workflow.events.count(('sleep', 60)) == 2
    assert 'read' not in workflow.events


def test_failure_after_compile_creation_retains_identity(control, args, workflow, monkeypatch):
    def prepare(self):
        self.compile_receipt = compiled()
        raise m.Refused('journal_failed')
    monkeypatch.setattr(workflow.Runner, 'prepare_once', prepare)
    result = m.run(args, time.monotonic() + 500)
    assert result['failure']['state']['compiled'] == compiled()
    assert result['failure']['state']['launch'] is None


@pytest.mark.parametrize('name,actual', [('capacity_wait', 0), ('compile_error', 2), ('runtime_error', 2)])
def test_output_authenticates_report_pin_and_actual_exit(args, name, actual):
    value = result_output(args, name)
    assert m.validate_output(m.canonical(value), actual, args) == value
    for bad in (True, False, None, '0', 2 if actual == 0 else 0):
        with pytest.raises(m.Refused): m.validate_output(m.canonical(value), bad, args)


@pytest.mark.parametrize('change', ['pin', 'binding', 'flags', 'count', 'compile', 'launch', 'terminal'])
def test_output_cannot_promote_corrupt_result_metadata(args, change):
    value = result_output(args)
    if change == 'pin': value['outcome']['report']['sha256'] = 'f' * 64
    elif change == 'binding': value['binding']['expected_head'] = 'f' * 40
    elif change == 'flags': value['outcome']['result']['paper_or_live_ready'] = True
    elif change == 'count': value['outcome']['result']['application_dispatch_count'] = True
    elif change == 'compile': value['outcome']['result']['compiled']['attempt'] = 12
    elif change == 'launch': value['outcome']['result']['launch'] = launched()
    else: value['outcome']['result']['terminal'] = 'completed'
    with pytest.raises((m.Refused, remote.Refused)):
        m.validate_output(m.canonical(value), 0, args)


def failure_output(args):
    return {'binding': m.binding(args), 'outcome': {'failure': {'failure_code': 'admission_failed',
        'state': {'stage': 'initial_admission', 'dispatch_count': 0, 'compiled': None, 'launch': None, 'terminal': None},
        'provider_request_count': None, 'attempt_consumption': 'consumed_or_ambiguous_no_retry', **m.FALSE_FLAGS}}}


@pytest.mark.parametrize('change', ['none', 'extra', 'bad-stage', 'bool-count', 'negative', 'raw', 'launch', 'terminal'])
def test_failure_state_is_exact_finite_and_binds_any_identity(args, change):
    value = failure_output(args)
    state = value['outcome']['failure']['state']
    if change == 'none': state = None; value['outcome']['failure']['state'] = state
    elif change == 'extra': state['raw_error'] = 'not permitted'
    elif change == 'bad-stage': state['stage'] = 'arbitrary'
    elif change == 'bool-count': state['dispatch_count'] = False
    elif change == 'negative': state['dispatch_count'] = -1
    elif change == 'raw': state['compiled'] = {'raw': 'not permitted'}
    elif change == 'launch': state['launch'] = launched()
    else: state['terminal'] = terminal()
    with pytest.raises((m.Refused, remote.Refused)):
        m.validate_output(m.canonical(value), 2, args)


def test_projection_refusal_without_public_finite_method_cannot_break_failure_handler():
    assert m.finite(m.projection.Refused('untrusted dynamic words')) == 'projection_refused'


@pytest.mark.parametrize('stage', ['credential', 'support'])
def test_observer_setup_failure_is_finite_and_does_not_spawn(args, monkeypatch, stage):
    def fail(*_, **__): raise m.Refused('synthetic_setup')
    monkeypatch.setattr(m, 'capture', lambda *a, **k: pytest.fail('capture after setup refusal'))
    monkeypatch.setattr(m, 'credential_shape', fail if stage == 'credential' else lambda: {})
    if stage == 'support': monkeypatch.setattr(m.tempfile, 'mkdtemp', fail)
    result, actual = m.observe(args)
    assert actual == 2 and result['failure_code'] == 'synthetic_setup'
    assert result['parent'] is result['validator'] is None and result['output_authenticated'] is False


def test_native_profile_denies_old_a12_control_and_output_validator_artifacts():
    for artifacts in (False, True):
        text = m.native_profile(artifacts=artifacts)
        assert '(deny network*)' in text and '/usr/bin/security' in text
        assert str(m.prior.CONTROL) in text
        if artifacts: assert str(m.ROOT / 'artifacts') in text


def test_output_preclaim_refusal_requires_actual_nonzero(args):
    value = {'binding': m.binding(args), 'preflight_failure': 'source_pin'}
    assert m.validate_output(m.canonical(value), 2, args) == value
    with pytest.raises(m.Refused): m.validate_output(m.canonical(value), 0, args)
