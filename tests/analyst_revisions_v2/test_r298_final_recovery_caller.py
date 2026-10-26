"""Synthetic final-caller checks, launched under native remote/artifact denial."""
import copy
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import pytest

from scripts import run_arv2_r298_final_recovery as m
from scripts import read_arv2_r298_a2_stage as reader
from scripts import arv2_r298_final_recovery_remote as remote
from scripts import arv2_r298_recovery_evidence as evidence
from scripts import arv2_newrule_execution_environment as environment
from research.quantconnect import QuantConnectError


@pytest.fixture(autouse=True)
def private_tripwire(monkeypatch):
    hits = []
    def refuse(*args, **kwargs):
        hits.append('private-or-operational')
        raise AssertionError('synthetic seam was not replaced')
    for module, name in ((reader, '_read_documents'), (evidence, 'collect_documents'),
        (environment, 'guarded_client'), (m.previous, '_admission')):
        monkeypatch.setattr(module, name, refuse)
    yield
    assert hits == []


@pytest.fixture
def args():
    return SimpleNamespace(operation='recover', expected_head='a' * 40, caller_sha256='b' * 64,
        reader_head='c' * 40, reader_exit_code=0, reader_report_sha256='d' * 64,
        reader_claim_sha256='e' * 64, control_fd=None)


@pytest.fixture
def leaf(tmp_path, monkeypatch):
    root = tmp_path / 'root'
    (root / 'artifacts').mkdir(parents=True)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'CONTROL', root / 'artifacts' / 'recovery' / 'fixed')
    return m.CONTROL


def test_store_exclusive_retained_and_inherited(leaf):
    with m.Store(create=True) as store:
        pin = store.write('one.json', {'a': 1})
        raw, value = store.read('one.json')
        assert pin == {'sha256': m.sha(raw), 'byte_count': len(raw)} and value == {'a': 1}
        with m.Store(inherited=store.fd) as child:
            child.write('child.json', {})
        with pytest.raises(FileExistsError):
            store.write('one.json', {})
        with pytest.raises(m.Refused):
            m.Store(inherited=1)
    with pytest.raises(m.Refused, match='claim'):
        m.Store(create=True)
    assert (leaf / 'one.json').read_bytes() == b'{"a":1}\n'


@pytest.mark.parametrize('name', ['../a.json', 'a/b.json', 'a', '', 'a.json\n'])
def test_store_names(leaf, name):
    with m.Store(create=True) as store:
        with pytest.raises(m.Refused):
            store.write(name, {})


@pytest.mark.parametrize('mutation', ['mode', 'hardlink', 'symlink', 'noncanonical', 'duplicate', 'directory', 'replace_leaf'])
def test_store_hostile(leaf, mutation):
    with m.Store(create=True) as store:
        store.write('one.json', {'a': 1})
        path = leaf / 'one.json'
        if mutation == 'mode':
            path.chmod(0o644)
        elif mutation == 'hardlink':
            os.link(path, leaf / 'two.json')
        elif mutation == 'symlink':
            path.rename(leaf / 'two.json')
            path.symlink_to('two.json')
        elif mutation == 'noncanonical':
            path.write_bytes(b'{ "a": 1 }\n')
        elif mutation == 'duplicate':
            path.write_bytes(b'{"a":1,"a":2}\n')
        elif mutation == 'replace_leaf':
            leaf.rename(leaf.with_name('retained'))
            leaf.mkdir(mode=0o700)
        else:
            path.unlink()
            path.mkdir()
        with pytest.raises((m.Refused, m.previous.Refused, OSError)):
            store.read('one.json')


def test_profile_exact_no_retry():
    value = m.profile_record()
    assert value['attempt_id'] == value['candidate_attempt_ceiling'] == 3
    assert value['shared_look'] == value['development_look'] == 1
    assert value['compile_poll_limit'] == 20 and value['status_poll_limit'] == 1
    assert value['actual_reader_exit_zero_required'] and value['actual_parent_exit_zero_required']
    assert value['old_recovery_leaf_read'] is False and value['automatic_retry'] is False
    assert all(value[key] is False for key in m.FALSE_FLAGS)
    assert '(deny network*)' in m.SANDBOX and 'R298-20261024-A' in m.SANDBOX


@pytest.fixture
def reconciliation(tmp_path, monkeypatch, args):
    output = tmp_path / 'new-reader'
    output.mkdir(mode=0o700)
    monkeypatch.setattr(m, 'RECONCILIATION', output)
    monkeypatch.setattr(reader, 'OUTPUT', output)
    monkeypatch.setitem(m.NEW_PINS, 'scripts/read_arv2_r298_a2_stage.py', 'f' * 64)
    claim = {'schema': reader.SCHEMA, 'expected_head': args.reader_head,
        'reader_sha256': 'f' * 64, 'profile_sha256': m.sha(reader.canonical(reader.profile_record())),
        'old_binding': reader.old_binding(), 'attempt_consumed': True}
    raw = m.canonical(claim)
    report = {'schema': reader.SCHEMA, 'stage_authenticated': True, 'old_attempt_id': 2,
        'project_id': m.PROJECT, 'rpc_intent_count': 0, 'rpc_observed_count': 0,
        'rpc_failure_count': 0, 'last_recorded_marker': None, 'last_recorded_endpoint': None,
        'last_recorded_event': None, 'recorded_application_dispatch_count': None,
        'compile_id': None, 'backtest_id': None, 'recorded_status': None,
        'initial_inventory_recorded': False, 'completed_inventory_recorded': False,
        'rpc_markers': [], 'receipts_present': [], 'provider_request_count': None,
        'lost_cause_recovered': False, 'no_unjournaled_effects_proven': False,
        'operational_retry_authority': False, 'control_file_count': 8,
        'expected_head': args.reader_head, 'reader_sha256': 'f' * 64,
        'profile_sha256': claim['profile_sha256'], 'claim_sha256': m.sha(raw),
        'claim_bytes': len(raw), 'old_binding': reader.old_binding(), **m.FALSE_FLAGS}
    def publish():
        raw_claim, raw_report = m.canonical(claim), m.canonical(report)
        for name, payload in (('claim.json', raw_claim), ('report.json', raw_report)):
            path = output / name
            path.write_bytes(payload)
            path.chmod(0o600)
        args.reader_claim_sha256, args.reader_report_sha256 = m.sha(raw_claim), m.sha(raw_report)
    publish()
    return SimpleNamespace(output=output, claim=claim, report=report, publish=publish)


def test_reconciliation_exact_new_output_only(args, reconciliation):
    result = m._reconciliation(args, time.monotonic() + 10)
    assert result == {'reader_report_sha256': args.reader_report_sha256,
        'reader_claim_sha256': args.reader_claim_sha256, 'pre_mutation_prefix_authenticated': True}


@pytest.mark.parametrize('change', ['exit_nonzero', 'exit_bool', 'report_pin', 'claim_pin', 'head', 'source',
    'profile', 'old_binding', 'unknown_file', 'claim_extra', 'false_flag', 'mode'])
def test_reconciliation_bindings(args, reconciliation, change):
    if change == 'exit_nonzero':
        args.reader_exit_code = 2
    elif change == 'exit_bool':
        args.reader_exit_code = False
    elif change == 'report_pin':
        args.reader_report_sha256 = '0' * 64
    elif change == 'claim_pin':
        args.reader_claim_sha256 = '0' * 64
    elif change == 'head':
        args.reader_head = '0' * 40
    elif change in ('source', 'profile'):
        reconciliation.report['reader_sha256' if change == 'source' else 'profile_sha256'] = '0' * 64
        reconciliation.publish()
    elif change == 'old_binding':
        reconciliation.report['old_binding']['project_id'] += 1
        reconciliation.publish()
    elif change == 'unknown_file':
        (reconciliation.output / 'extra.json').write_bytes(b'{}\n')
    elif change == 'claim_extra':
        reconciliation.claim['extra'] = False
        reconciliation.publish()
    elif change == 'false_flag':
        reconciliation.report['strategy_result_accepted'] = True
        reconciliation.publish()
    else:
        (reconciliation.output / 'report.json').chmod(0o644)
    with pytest.raises((m.Refused, reader.Refused)):
        m._reconciliation(args, time.monotonic() + 10)


@pytest.mark.parametrize('marker,endpoint', [('complete-write-00', 'files/create'), ('compile-create', 'compile/create'),
    ('launch-create', 'backtests/create'), ('inspect-files', 'files/read')])
def test_reconciliation_refuses_mutation_or_nonprefix(args, reconciliation, marker, endpoint):
    report = reconciliation.report
    report.update(rpc_intent_count=1, rpc_observed_count=1, rpc_markers=[marker],
        last_recorded_marker=marker, last_recorded_endpoint=endpoint, last_recorded_event='observed',
        control_file_count=10)
    reconciliation.publish()
    with pytest.raises(m.Refused, match='reconciliation'):
        m._reconciliation(args, time.monotonic() + 10)


@pytest.fixture
def workflow(args, leaf, monkeypatch):
    state = SimpleNamespace(events=[], sleeps=[], now=0, deadline=1000, compile='BuildSuccess',
        status='In Progress...', wait=False, error=None, request_error=None)
    monkeypatch.setattr(m.time, 'monotonic', lambda: state.now)
    def sleep(seconds):
        state.sleeps.append(seconds)
        state.now += seconds
    monkeypatch.setattr(m.time, 'sleep', sleep)
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: None)
    monkeypatch.setattr(evidence, 'reconstruct_projection', lambda: object())
    def child(supplied, store, deadline, operation):
        assert store.read('claim.json')[1] == m.claim(args)
        state.events.append(operation)
        store.write(operation + '-start.json', {})
        return {}
    monkeypatch.setattr(m, '_child', child)
    def client():
        assert state.events[-1] == 'admission-initial-worker'
        state.events.append('credentials')
        def request(endpoint, payload):
            if state.request_error:
                raise state.request_error
            return {'success': True}
        return SimpleNamespace(request=request)
    monkeypatch.setattr(environment, 'guarded_client', client)
    class Runner:
        def __init__(self, projected, org, request, journal):
            assert org == remote.ORGANIZATION_SHA256
            self.request, self.journal = request, journal
            if state.error:
                raise state.error
        def inspect(self):
            state.events.append('inspect')
            event = {'event': 'intent', 'endpoint': 'projects/read', 'sha256': '1' * 64}
            self.journal('inspect-project', event)
            self.request('projects/read', {'projectId': m.PROJECT})
            self.journal('inspect-project', {**event, 'event': 'observed'})
            return {'files': []}
        def complete(self, inventory):
            state.events.append('complete')
            return inventory
        def compile_once(self, inventory):
            state.events.append('compile')
            return {'compile_id': 'own-compile'}
        def poll_compile(self, compile_id, index):
            state.events.append(('compile-poll', index))
            return {'state': state.compile}
        def launch_once(self, compile_id):
            state.events.append('launch')
            return {'state': 'wait'} if state.wait else {'backtest_id': 'own-run'}
        def read_status(self, receipt, index):
            assert receipt['backtest_id'] == 'own-run' and index == 0
            state.events.append('status')
            return {'status': state.status}
    monkeypatch.setattr(remote, 'FinalRecovery', Runner)
    return state


def invoke(args, state):
    with m.Store(create=True) as store:
        return m._recover(args, store, state.deadline)


def test_workflow_order_claim_and_single_status(args, leaf, workflow):
    result = invoke(args, workflow)
    assert workflow.events == ['reconciliation-check-worker', 'admission-initial-worker', 'credentials',
        'inspect', 'complete', 'compile', ('compile-poll', 0), 'admission-launch-worker',
        'launch', 'status', 'admission-final-worker']
    assert workflow.sleeps == [10, 60] and result['terminal'] == 'own_status_observed'
    assert result['application_dispatch_count'] == 1 and result['provider_request_count'] is None
    assert m.parse((leaf / 'claim.json').read_bytes())['attempt_id'] == 3
    with pytest.raises(m.Refused, match='claim'):
        invoke(args, workflow)


def test_capacity_wait_never_relaunches(args, workflow):
    workflow.wait = True
    assert invoke(args, workflow)['terminal'] == 'capacity_wait'
    assert workflow.sleeps == [10] and 'status' not in workflow.events
    assert workflow.events.count('launch') == 1


def test_completed_status_is_not_result_acceptance(args, workflow):
    workflow.status = 'Completed.'
    result = invoke(args, workflow)
    assert result['status']['status'] == 'Completed.'
    assert result['terminal'] == 'own_status_observed'
    assert 'strategy_result_accepted' not in result
    assert m.FALSE_FLAGS['strategy_result_accepted'] is False


@pytest.mark.parametrize('field,value,code', [('compile', 'BuildError', 'compile_failed'),
    ('status', 'Runtime Error', 'runtime_failed'), ('compile', 'Building', 'compile_budget')])
def test_failure_terminal_not_success(args, workflow, field, value, code):
    setattr(workflow, field, value)
    with pytest.raises(m.ObservedFailure) as caught:
        invoke(args, workflow)
    assert m.failure_observation(caught.value)['code'] == code
    if code != 'runtime_failed':
        assert 'launch' not in workflow.events
    if code == 'compile_budget':
        assert len(workflow.sleeps) == 20


def test_reserve_before_launch(args, workflow):
    workflow.deadline = 95
    with pytest.raises(m.ObservedFailure) as caught:
        invoke(args, workflow)
    assert m.failure_observation(caught.value)['code'] == 'deadline' and 'launch' not in workflow.events


@pytest.mark.parametrize('code', ['projection_binding', 'owned_owner', 'source_manifest_binding'])
def test_helper_finite_reason_survives(args, workflow, leaf, code):
    workflow.error = remote.RecoveryError(code)
    with pytest.raises(m.ObservedFailure) as caught:
        invoke(args, workflow)
    observation = m.failure_observation(caught.value)
    assert observation['helper_code'] == code and observation['last_stage'] == 'construct'
    assert observation['application_dispatch_count'] == 0 and observation['intent_marker'] is None
    assert m.parse((leaf / 'failure.json').read_bytes())['observation'] == observation


def test_request_context_survives_without_raw_text(args, workflow):
    workflow.request_error = QuantConnectError('projects/read failed (HTTP 403): SECRET')
    with pytest.raises(m.ObservedFailure) as caught:
        invoke(args, workflow)
    observation = m.failure_observation(caught.value)
    assert observation['http_status'] == 403 and observation['category'] == 'http_failure'
    assert observation['application_dispatch_count'] == 1 and observation['last_event'] == 'failure'
    assert 'SECRET' not in repr(observation)


def test_failed_failure_receipt_preserves_context(args, workflow, monkeypatch):
    workflow.error = remote.RecoveryError('owned_idle')
    original = m.Store.write
    def write(store, name, value):
        if name == 'failure.json':
            raise OSError('SECRET')
        return original(store, name, value)
    monkeypatch.setattr(m.Store, 'write', write)
    with pytest.raises(m.ObservedFailure) as caught:
        invoke(args, workflow)
    assert m.failure_observation(caught.value)['helper_code'] == 'owned_idle'


def test_hostile_exception_not_stringified(args, workflow):
    class Hostile(remote.RecoveryError):
        def __str__(self):
            pytest.fail('exception stringified')
    workflow.error = Hostile('SECRET')
    with pytest.raises(m.ObservedFailure) as caught:
        invoke(args, workflow)
    observation = m.failure_observation(caught.value)
    assert observation['helper_code'] == 'unknown' and 'SECRET' not in repr(observation)


@pytest.fixture
def source_context(args, monkeypatch):
    raw = b'public synthetic final caller\n'
    args.caller_sha256 = m.sha(raw)
    monkeypatch.setitem(m.NEW_PINS, 'scripts/read_arv2_r298_a2_stage.py', '1' * 64)
    monkeypatch.setitem(m.NEW_PINS, 'scripts/arv2_r298_final_recovery_remote.py', '2' * 64)
    pins = {**m.frozen.SOURCE_PINS, **m.v5.NEW_PINS, **m.previous.NEW_PINS, **m.NEW_PINS,
        'scripts/run_arv2_newrule_comparison.py': m.v5.FROZEN_CALLER_SHA256}
    state = SimpleNamespace(events=[], wrong_pin=None, dirty=False, bad_blob=False)
    monkeypatch.setattr(m.v5, '_under_test', lambda: False)
    monkeypatch.setattr(environment, '_require_environment', lambda: state.events.append('environment'))
    def digest(path):
        state.events.append(('digest', path))
        if str(path) == state.wrong_pin:
            return '0' * 64
        return args.caller_sha256 if path == m.SOURCE else pins[path.relative_to(m.ROOT).as_posix()]
    monkeypatch.setattr(m.helpers, '_source_digest', digest)
    def git(command, deadline, limit=65536):
        assert 'environment' in state.events
        state.events.append(('git', command))
        if command == ['rev-parse', '--show-toplevel']:
            return (str(m.ROOT) + '\n').encode()
        if command == ['branch', '--show-current']:
            return (m.frozen.BRANCH + '\n').encode()
        if command == ['rev-parse', 'HEAD']:
            return (args.expected_head + '\n').encode()
        if command == ['status', '--porcelain']:
            return b' M file\n' if state.dirty else b''
        if command[:2] == ['cat-file', '-s']:
            return str(len(raw)).encode()
        if command[:2] == ['cat-file', 'blob']:
            return raw + b'x' if state.bad_blob else raw
        pytest.fail('unexpected git')
    monkeypatch.setattr(m.v5, '_git', git)
    return state


def test_preflight_all_selected_source_pins(args, source_context):
    m._preflight(args, time.monotonic() + 30)
    checked = {str(row[1]) for row in source_context.events if isinstance(row, tuple) and row[0] == 'digest'}
    assert all(str(m.ROOT / name) in checked for name in m.NEW_PINS)
    assert all(str(m.ROOT / name) in checked for name in m.previous.NEW_PINS)
    assert all(str(m.ROOT / name) in checked for name in m.frozen.SOURCE_PINS)


@pytest.mark.parametrize('which', ['reader', 'remote', 'old_caller', 'environment', 'caller', 'dirty', 'blob'])
def test_preflight_source_changes_refused(args, source_context, which):
    if which == 'dirty':
        source_context.dirty = True
    elif which == 'blob':
        source_context.bad_blob = True
    else:
        source_context.wrong_pin = str(m.SOURCE if which == 'caller' else m.ROOT / {
            'reader': 'scripts/read_arv2_r298_a2_stage.py',
            'remote': 'scripts/arv2_r298_final_recovery_remote.py',
            'old_caller': 'scripts/run_arv2_r298_recovery.py',
            'environment': 'scripts/arv2_newrule_execution_environment.py'}[which])
    with pytest.raises(m.Refused):
        m._preflight(args, time.monotonic() + 30)


@pytest.mark.parametrize('field,value', [('expected_head', 'bad'), ('caller_sha256', 'bad'),
    ('reader_head', 'bad'), ('reader_report_sha256', 'bad'), ('reader_claim_sha256', 'bad'),
    ('reader_exit_code', 2), ('reader_exit_code', False), ('control_fd', 3), ('operation', 'begin')])
def test_preflight_argument_contract(args, source_context, field, value):
    setattr(args, field, value)
    with pytest.raises(m.Refused):
        m._preflight(args, time.monotonic() + 30)


def test_preflight_worker_refuses_credentials(args, source_context, monkeypatch):
    args.operation, args.control_fd = 'admission-initial-worker', 3
    monkeypatch.setenv('QC_API_TOKEN', 'synthetic-token')
    with pytest.raises(m.Refused, match='context'):
        m._preflight(args, time.monotonic() + 30)


def cli(args):
    return ['recover', '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
        '--reader-head', args.reader_head, '--reader-report-sha256', args.reader_report_sha256,
        '--reader-claim-sha256', args.reader_claim_sha256, '--reader-exit-code', '0']


def test_main_failure_redacted_double_lf(args, monkeypatch, capsys):
    monkeypatch.setattr(m, '_preflight', lambda *a: (_ for _ in ()).throw(ValueError('SECRET')))
    assert m.main(cli(args)) == 2
    output = capsys.readouterr().out
    assert output.endswith('\n\n') and 'SECRET' not in output
    value = m.parse(output[:-1].encode())
    assert value['operation_completed'] is False and value['failure_code'] == 'unknown_exception'


def test_main_success_double_lf_and_flags(args, monkeypatch, capsys):
    monkeypatch.setattr(m, '_preflight', lambda *a: None)
    monkeypatch.setattr(environment, '_bootstrap_cli_logging', lambda: None)
    monkeypatch.setattr(m, '_execute', lambda *a: {'safe': True})
    assert m.main(cli(args)) == 0
    output = capsys.readouterr().out
    assert output.endswith('\n\n')
    value = m.parse(output[:-1].encode())
    assert all(value[key] is False for key in m.FALSE_FLAGS)


def test_postflight_failure_no_success_report(args, leaf, monkeypatch):
    calls = []
    def preflight(*a):
        calls.append(1)
        if len(calls) == 2:
            raise m.Refused('source')
    monkeypatch.setattr(m, '_preflight', preflight)
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: None)
    def recover(args, store, deadline, *, state):
        store.write('claim.json', m.claim(args))
        state.update(intent_marker='status-poll-000', endpoint='backtests/list',
            last_event='observed', application_dispatch_count=12)
        return {'terminal': 'fixture'}
    monkeypatch.setattr(m, '_recover', recover)
    with pytest.raises(m.ObservedFailure) as caught:
        m._execute(args, time.monotonic() + 30)
    observed = m.failure_observation(caught.value)
    assert observed['code'] == 'source' and observed['last_stage'] == 'report'
    assert observed['application_dispatch_count'] == 12 and observed['intent_marker'] == 'status-poll-000'
    assert (leaf / 'claim.json').exists() and not (leaf / 'report.json').exists()


def test_finite_helper_context_reaches_parent_envelope(args, workflow, monkeypatch, capsys):
    state = {'last_stage': 'inspect', 'intent_marker': 'inspect-project', 'endpoint': 'projects/read',
        'last_event': 'observed', 'application_dispatch_count': 1, 'category': 'unknown', 'http_status': None}
    value = m._failure(remote.RecoveryError('owned_owner'), state)
    monkeypatch.setattr(m, '_preflight', lambda *a: None)
    monkeypatch.setattr(environment, '_bootstrap_cli_logging', lambda: None)
    monkeypatch.setattr(m, '_execute', lambda *a: (_ for _ in ()).throw(m.ObservedFailure(m.canonical(value))))
    assert m.main(cli(args)) == 2
    output = m.parse(capsys.readouterr().out[:-1].encode())
    assert output['failure_observation'] == value and output['failure_code'] == 'remote_refused'


@pytest.mark.parametrize('operation', m.WORKERS)
def test_worker_exclusive_markers(args, leaf, monkeypatch, operation):
    args.operation = operation
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: None)
    monkeypatch.setattr(m, '_reconciliation', lambda *a: {'checked': True})
    projected = SimpleNamespace(projection_sha256=remote.PROJECTION_SHA256)
    monkeypatch.setattr(evidence, 'reconstruct_projection', lambda: projected)
    monkeypatch.setattr(m.previous, '_admission', lambda item, deadline: None)
    with m.Store(create=True) as store:
        store.write('claim.json', m.claim(args))
        args.control_fd = store.fd
        m._worker(args, time.monotonic() + 10)
        with pytest.raises(FileExistsError):
            m._worker(args, time.monotonic() + 10)


@pytest.mark.parametrize('operation', ['reconciliation-check-worker', 'admission-launch-worker'])
@pytest.mark.parametrize('kind', ['normal', 'nonzero', 'noise', 'stderr', 'trailing', 'oversize', 'timeout',
    'binding', 'false_flag', 'bad_result'])
def test_real_child_channel_and_reap(args, leaf, monkeypatch, tmp_path, kind, operation):
    result = ({'reader_report_sha256': args.reader_report_sha256,
        'reader_claim_sha256': args.reader_claim_sha256, 'pre_mutation_prefix_authenticated': True}
        if operation == 'reconciliation-check-worker' else
        {'admission_authenticated': True, 'projection_sha256': remote.PROJECTION_SHA256})
    envelope = {'schema': m.SCHEMA, 'operation': operation, 'binding': m.binding(args),
        'result': copy.deepcopy(result), 'operation_completed': True, **m.FALSE_FLAGS}
    if kind == 'binding':
        envelope['binding']['project_id'] += 1
    elif kind == 'false_flag':
        envelope['strategy_result_accepted'] = True
    elif kind == 'bad_result':
        envelope['result']['unexpected'] = True
    raw = m.canonical(envelope) + b'\n'
    if kind == 'noise':
        raw = b'noise' + raw
    elif kind == 'trailing':
        raw += b'x'
    elif kind == 'oversize':
        raw = b'x' * (m.MAX_OUTPUT + 1)
    processes = []
    real_popen = subprocess.Popen
    synthetic_env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'en_US.UTF-8',
        'TMPDIR': str(tmp_path), 'TMP': str(tmp_path), 'TEMP': str(tmp_path),
        'XDG_CACHE_HOME': str(tmp_path), 'PYTHONPYCACHEPREFIX': str(tmp_path / 'cache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'QC_USER_ID': 'synthetic-user', 'QC_API_TOKEN': 'synthetic-token'}
    monkeypatch.setattr(m.os, 'environ', synthetic_env)
    def launch(command, **kwargs):
        assert command[:3] == ['/usr/bin/sandbox-exec', '-p', m.SANDBOX]
        assert '--control-fd' in command and kwargs['pass_fds']
        assert not {'QC_USER_ID', 'QC_API_TOKEN'} & set(kwargs['env'])
        fd = kwargs['pass_fds'][0]
        # Parent pytest already supplies native denial; nested sandbox-exec is
        # unavailable on Darwin. Only this tiny fixture replaces that launcher.
        code = ('import os,socket,time\n'
            f'os.fstat({fd})\n'
            'try:\n socket.socket().bind(("127.0.0.1",0))\n'
            'except PermissionError:\n pass\n'
            'else:\n raise RuntimeError("native network denial missing")\n'
            + ('time.sleep(30)\n' if kind == 'timeout' else '')
            + f'os.write(1,{raw!r})\n'
            + ('os.write(2,b"finite-noise")\n' if kind == 'stderr' else '')
            + ('raise SystemExit(2)\n' if kind == 'nonzero' else ''))
        process = real_popen([str(m.frozen.PYTHON), '-B', '-c', code], **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(m.subprocess, 'Popen', launch)
    with m.Store(create=True) as store:
        if kind == 'normal':
            assert m._child(args, store, time.monotonic() + 5, operation) == result
        else:
            with pytest.raises((m.Refused, m.previous.Refused, ValueError)):
                m._child(args, store, time.monotonic() + (0.2 if kind == 'timeout' else 5), operation)
    assert len(processes) == 1 and processes[0].poll() is not None
    assert processes[0].stdout.closed and processes[0].stderr.closed
