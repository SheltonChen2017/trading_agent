"""Synthetic caller tests. Native launcher denies network, artifacts and Keychain."""
import copy
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import pytest

from scripts import run_arv2_r298_recovery as m
from scripts import arv2_r298_recovery_evidence as evidence
from scripts import arv2_r298_recovery_remote as remote
from scripts import arv2_newrule_execution_environment as environment
from research.quantconnect import QuantConnectError
from research.analyst_revisions_v2_qc.six_universe_coverage_submission import CoverageQcSubmissionError


@pytest.fixture(autouse=True)
def private_tripwire(monkeypatch):
    hits = []
    def refuse(*args, **kwargs):
        hits.append('private-or-operational')
        raise AssertionError('synthetic seam was not replaced')
    monkeypatch.setattr(evidence, 'collect_documents', refuse)
    monkeypatch.setattr(environment, 'guarded_client', refuse)
    monkeypatch.setattr(m.frozen.prepared_input.october, 'load_october_order_input_package', refuse)
    yield
    assert hits == []


@pytest.fixture
def args():
    return SimpleNamespace(operation='evidence', expected_head='a' * 40,
        caller_sha256='b' * 64, evidence_sha256=None, control_fd=None)


@pytest.fixture
def leaf(tmp_path, monkeypatch):
    root = tmp_path / 'root'
    parent = root / 'artifacts'
    parent.mkdir(parents=True)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'CONTROL', parent / 'recovery' / 'fixed')
    return m.CONTROL


def test_store_roundtrip_exclusive(leaf):
    with m.Store(create=True) as store:
        pin = store.write('one.json', {'a': 1})
        raw, value = store.read('one.json')
        assert value == {'a': 1} and pin == {'sha256': m.sha(raw), 'byte_count': len(raw)}
        with pytest.raises(FileExistsError):
            store.write('one.json', {'a': 2})
    with pytest.raises(m.Refused, match='claim'):
        m.Store(create=True)
    assert (leaf / 'one.json').read_bytes() == b'{"a":1}\n'


@pytest.mark.parametrize('name', ['../one.json', 'a/b.json', 'bad', '', 'a.json\n'])
def test_store_rejects_names(leaf, name):
    with m.Store(create=True) as store:
        with pytest.raises(m.Refused):
            store.write(name, {})


@pytest.mark.parametrize('mutation', ['mode', 'hardlink', 'symlink', 'noncanonical', 'duplicate', 'directory'])
def test_store_rejects_unsafe_files(leaf, mutation):
    with m.Store(create=True) as store:
        store.write('one.json', {'a': 1})
        name = leaf / 'one.json'
        if mutation == 'mode':
            name.chmod(0o644)
        elif mutation == 'hardlink':
            os.link(name, leaf / 'other.json')
        elif mutation == 'symlink':
            name.rename(leaf / 'other.json')
            name.symlink_to('other.json')
        elif mutation == 'noncanonical':
            name.write_bytes(b'{ "a": 1 }\n')
        elif mutation == 'duplicate':
            name.write_bytes(b'{"a":1,"a":2}\n')
        else:
            name.unlink()
            name.mkdir()
        with pytest.raises((m.Refused, OSError)):
            store.read('one.json')


def test_store_inherited_fd_binding_and_replacement(leaf):
    with m.Store(create=True) as store:
        with m.Store(inherited=store.fd) as child:
            child.write('child.json', {})
        with pytest.raises(m.Refused):
            m.Store(inherited=1)
        moved = leaf.with_name('moved')
        leaf.rename(moved)
        leaf.mkdir(mode=0o700)
        with pytest.raises(m.Refused):
            store.verify()


@pytest.mark.parametrize('raw', [b'{}', b'{}\n\n', b'[]\n', b'{"x":NaN}\n', b'{"x":1,"x":2}\n'])
def test_strict_parser(raw):
    with pytest.raises((m.Refused, ValueError)):
        m.parse(raw)


@pytest.mark.parametrize('message,expected', [
    ('files/create failed (HTTP 403): SECRET', ('http_failure', 403)),
    ('files/create failed (HTTP 200): token=SECRET', ('http_failure', 200)),
    ('files/create returned a non-JSON body (HTTP 502)', ('http_non_json', 502)),
    ('files/create failed (HTTP 099): SECRET', ('unknown', None)),
    ('files/create failed (HTTP 600): SECRET', ('unknown', None)),
    ('Xfiles/create failed (HTTP 403): SECRET', ('unknown', None)),
    ('files/update failed (HTTP 403): SECRET', ('unknown', None)),
    ('files/create returned a non-JSON body (HTTP 502) SECRET', ('unknown', None)),
    ('x' * 4097, ('unknown', None)),
])
def test_finite_http_context(message, expected):
    result = m.http_context(QuantConnectError(message), 'files/create')
    assert result == {'category': expected[0], 'http_status': expected[1]}
    assert 'SECRET' not in repr(result)


def test_http_context_exact_types_and_frozen_transport():
    class Hostile(QuantConnectError):
        def __str__(self):
            pytest.fail('stringified')
    assert m.http_context(Hostile('files/create failed (HTTP 403): X'), 'files/create')['http_status'] is None
    assert m.http_context(QuantConnectError(object()), 'files/create')['http_status'] is None
    assert m.http_context(QuantConnectError('x', 'y'), 'files/create')['http_status'] is None
    assert m.http_context(CoverageQcSubmissionError('coverage QC response status or byte bound changed'), 'files/create') == {
        'category': 'status_or_bound_refusal', 'http_status': None}


def test_profile_no_retry_and_false_flags():
    value = m.profile_record()
    assert value['compile_poll_limit'] == 20 and value['compile_interval_seconds'] == 10
    assert value['status_poll_limit'] == 1 and value['status_interval_seconds'] == 60
    assert value['actual_evidence_exit_zero_required_externally'] is True
    assert value['actual_recover_exit_zero_required_externally'] is True
    assert value['original_attempt'] == 1 and value['recovery_attempt'] == 2
    assert value['same_project_only'] is True and value['original_attempt_remains_spent'] is True
    assert all(value[key] is False for key in m.FALSE_FLAGS)
    assert 'network*' in m.SANDBOX and '/usr/bin/security' in m.SANDBOX


@pytest.mark.parametrize('error,code', [(m.Refused('source'), 'source'),
    (m.Refused('SECRET'), 'unknown_exception'), (ValueError('SECRET'), 'unknown_exception'),
    (remote.RecoveryError('SECRET'), 'remote_refused'), (evidence.EvidenceRefused('SECRET'), 'evidence')])
def test_finite_failure(error, code):
    assert m.finite_failure(error) == code


@pytest.fixture
def recovery(leaf, args, monkeypatch):
    args.operation = 'recover'
    projected = SimpleNamespace(record_bytes=b'exact', profile_bytes=b'profile', source_files=())
    documents = {'organization.json': {'organization_id': 'c' * 32}}
    report = {'attempt_claim_authenticated': True}
    bundle = {**m.binding(args), 'report': report, 'documents': documents, 'inventory': ['fixed.json']}
    with m.Store(create=True) as store:
        store.write('claim.json', m.binding(args))
        pin = store.write('evidence.json', bundle)
        store.write('evidence-parent-completed.json', {**m.binding(args), 'evidence': pin})
    args.evidence_sha256 = pin['sha256']
    state = SimpleNamespace(events=[], sleeps=[], compile_state='BuildSuccess', status='In Progress...', wait=False,
        request_error=None, deadline=1000, now=0, bundle=bundle, projected=projected, report=report)
    monkeypatch.setattr(m.time, 'monotonic', lambda: state.now)
    def sleep(seconds):
        state.sleeps.append(seconds)
        state.now += seconds
    monkeypatch.setattr(m.time, 'sleep', sleep)
    monkeypatch.setattr(evidence, 'reconstruct_projection', lambda: projected)
    def validate(documents, item, *, inventory):
        assert item is projected and inventory == ['fixed.json']
        state.events.append('validated')
        return report
    monkeypatch.setattr(evidence, 'validate_documents', validate)
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: None)
    def checked_child(supplied, store, deadline, *, check):
        assert check is True
        worker_args = copy.copy(supplied)
        worker_args.operation, worker_args.control_fd = 'evidence-check-worker', store.fd
        return m._check_worker(worker_args, deadline)
    monkeypatch.setattr(m, '_child', checked_child)
    def admission(item, deadline):
        assert item is projected and (leaf / 'recover-claim.json').exists()
        state.events.append('admission')
    monkeypatch.setattr(m, '_admission', admission)
    def client():
        assert state.events[-1] == 'admission'
        state.events.append('credentials')
        def request(endpoint, payload):
            if state.request_error:
                raise state.request_error
            return {'success': True}
        return SimpleNamespace(request=request)
    monkeypatch.setattr(environment, 'guarded_client', client)
    class Runner:
        def __init__(self, item, org, request, journal):
            assert item is projected and org == 'c' * 32
            self.request, self.journal = request, journal
        def inspect(self):
            state.events.append('inspect')
            self.journal('inspect-project', {'event': 'intent', 'endpoint': 'projects/read', 'sha256': 'd' * 64})
            self.request('projects/read', {'projectId': m.PROJECT})
            return {'files': []}
        def complete(self, inventory):
            state.events.append('complete')
            return inventory
        def compile_once(self, inventory):
            state.events.append('compile')
            return {'compile_id': 'own-compile'}
        def poll_compile(self, compile_id, index):
            assert compile_id == 'own-compile'
            state.events.append(('compile-poll', index))
            return {'state': state.compile_state}
        def launch_once(self, compile_id):
            assert compile_id == 'own-compile'
            state.events.append('launch')
            return {'state': 'wait'} if state.wait else {'backtest_id': 'own-run', 'status': 'In Queue...'}
        def read_status(self, receipt, index):
            assert receipt['backtest_id'] == 'own-run' and index == 0
            state.events.append('status')
            return {'status': state.status}
    monkeypatch.setattr(remote, 'RemoteRecovery', Runner)
    return state


def invoke(args, state):
    with m.Store() as store:
        return m._recover(args, store, state.deadline)


def test_recover_order_and_one_status(leaf, args, recovery):
    result = invoke(args, recovery)
    assert recovery.events == ['validated', 'admission', 'credentials', 'inspect', 'complete', 'compile',
        ('compile-poll', 0), 'admission', 'launch', 'status', 'admission']
    assert recovery.sleeps == [10, 60] and result['terminal'] == 'own_status_observed'
    assert result['application_dispatch_count'] == 1 and result['provider_request_count'] is None
    claim = m.parse((leaf / 'recover-claim.json').read_bytes())
    assert claim['attempt_id'] == 2 and claim['shared_look'] == claim['development_look'] == 1
    with pytest.raises(FileExistsError):
        invoke(args, recovery)


@pytest.mark.parametrize('field,value', [('compile_state', 'BuildError'), ('status', 'Runtime Error')])
def test_terminal_failure_never_success(args, recovery, field, value):
    setattr(recovery, field, value)
    with pytest.raises(m.Refused, match='compile_failed|runtime_failed'):
        invoke(args, recovery)


def test_compile_poll_budget(args, recovery):
    recovery.compile_state = 'Building'
    with pytest.raises(m.Refused, match='compile_budget'):
        invoke(args, recovery)
    assert recovery.sleeps == [10] * 20 and 'launch' not in recovery.events


def test_deadline_before_launch(args, recovery):
    recovery.deadline = 90
    with pytest.raises(m.Refused, match='deadline'):
        invoke(args, recovery)
    assert 'launch' not in recovery.events


def test_capacity_wait_is_not_launch_or_retry(args, recovery):
    recovery.wait = True
    result = invoke(args, recovery)
    assert result['terminal'] == 'capacity_wait' and 'status' not in recovery.events
    assert recovery.sleeps == [10]


def test_completed_status_is_not_strategy_acceptance(args, recovery):
    recovery.status = 'Completed.'
    result = invoke(args, recovery)
    assert result['status']['status'] == 'Completed.'
    assert all(value is False for value in m.FALSE_FLAGS.values())


def test_numeric_http_context_is_retained_without_reason(leaf, args, recovery):
    recovery.request_error = QuantConnectError('projects/read failed (HTTP 403): SECRET')
    with pytest.raises(m.RequestFailed) as caught:
        invoke(args, recovery)
    raw = (leaf / 'rpc-inspect-project-failure.json').read_bytes()
    assert b'SECRET' not in raw
    value = m.parse(raw)
    assert value['http_status'] == 403 and value['application_dispatch_count'] == 1
    observation = m.failure_observation(caught.value)
    assert observation['failure_file'] == {'sha256': m.sha(raw), 'byte_count': len(raw)}
    assert observation['http_status'] == 403 and 'SECRET' not in repr(observation)
    assert 'complete' not in recovery.events


def test_external_evidence_pin_fails_before_credentials(args, recovery):
    args.evidence_sha256 = '0' * 64
    with pytest.raises(m.Refused, match='evidence'):
        invoke(args, recovery)
    assert recovery.events == []


def test_admission_failure_precedes_credentials(args, recovery, monkeypatch):
    monkeypatch.setattr(m, '_admission', lambda *a: (_ for _ in ()).throw(m.Refused('input_admission')))
    with pytest.raises(m.Refused, match='input_admission'):
        invoke(args, recovery)
    assert recovery.events == ['validated']


def test_worker_claim_precedes_once_only_collector(leaf, args, monkeypatch):
    args.operation = 'evidence-worker'
    events = []
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: None)
    monkeypatch.setattr(evidence, 'reconstruct_projection', lambda: events.append('projection') or object())
    def collector():
        assert (leaf / 'claim.json').exists() and (leaf / 'evidence-start.json').exists()
        events.append('collect')
        return {'fixed': {}}, ['fixed']
    monkeypatch.setattr(evidence, 'collect_documents', collector)
    monkeypatch.setattr(evidence, 'validate_documents', lambda *a, **kw: {'safe': True})
    with m.Store(create=True) as store:
        store.write('claim.json', m.binding(args))
        args.control_fd = store.fd
        value = m._worker(args, m.time.monotonic() + 10)
        assert value['evidence']['sha256'] == m.sha(store.read('evidence.json')[0])
        with pytest.raises(FileExistsError):
            m._worker(args, m.time.monotonic() + 10)
    assert events == ['projection', 'collect']


def test_pytest_operational_preflight_refuses(args):
    with pytest.raises(m.Refused, match='context'):
        m._preflight(args, m.time.monotonic() + 10)


def test_main_finite_failure_no_exception_text(args, monkeypatch, capsys):
    monkeypatch.setattr(m, '_preflight', lambda *a: (_ for _ in ()).throw(ValueError('SECRET')))
    assert m.main(['evidence', '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256]) == 2
    output = capsys.readouterr().out
    assert output.endswith('\n\n') and 'SECRET' not in output
    value = m.parse(output[:-1].encode())
    assert value['operation_completed'] is False and value['failure_code'] == 'unknown_exception'


def test_main_success_double_lf_and_false_flags(args, monkeypatch, capsys):
    monkeypatch.setattr(m, '_preflight', lambda *a: None)
    monkeypatch.setattr(environment, '_bootstrap_cli_logging', lambda: None)
    monkeypatch.setattr(m, '_execute', lambda *a: {'safe': True})
    assert m.main(['evidence', '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256]) == 0
    output = capsys.readouterr().out
    assert output.endswith('\n\n')
    value = m.parse(output[:-1].encode())
    assert all(value[key] is False for key in m.FALSE_FLAGS)


def test_postflight_failure_does_not_publish_success_report(leaf, args, monkeypatch):
    calls = []
    def preflight(*a):
        calls.append(1)
        if len(calls) == 2:
            raise m.Refused('source')
    monkeypatch.setattr(m, '_preflight', preflight)
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: None)
    monkeypatch.setattr(m, '_child', lambda *a: {'safe': True})
    with pytest.raises(m.Refused, match='source'):
        m._execute(args, m.time.monotonic() + 20)
    assert (leaf / 'claim.json').exists() and not (leaf / 'evidence-report.json').exists()


@pytest.fixture
def source_context(args, monkeypatch):
    raw = b'public synthetic caller\n'
    args.caller_sha256 = m.sha(raw)
    pins = {**m.frozen.SOURCE_PINS, **m.v5.NEW_PINS, **m.NEW_PINS,
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


def test_preflight_validates_all_selected_sources(args, source_context):
    m._preflight(args, time.monotonic() + 30)
    checked = {str(row[1]) for row in source_context.events if isinstance(row, tuple) and row[0] == 'digest'}
    assert all(str(m.ROOT / name) in checked for name in m.NEW_PINS)
    assert all(str(m.ROOT / name) in checked for name in m.frozen.SOURCE_PINS)


@pytest.mark.parametrize('which', ['evidence', 'remote', 'environment', 'caller', 'dirty', 'blob'])
def test_preflight_refuses_binding_change(args, source_context, which):
    if which == 'dirty':
        source_context.dirty = True
    elif which == 'blob':
        source_context.bad_blob = True
    else:
        source_context.wrong_pin = str(m.SOURCE if which == 'caller' else m.ROOT / {
            'evidence': 'scripts/arv2_r298_recovery_evidence.py',
            'remote': 'scripts/arv2_r298_recovery_remote.py',
            'environment': 'scripts/arv2_newrule_execution_environment.py'}[which])
    with pytest.raises(m.Refused):
        m._preflight(args, time.monotonic() + 30)


@pytest.mark.parametrize('field,value', [('expected_head', 'bad'), ('caller_sha256', 'bad'),
    ('evidence_sha256', 'a' * 64), ('control_fd', 3), ('operation', 'begin')])
def test_preflight_argument_contract(args, source_context, field, value):
    setattr(args, field, value)
    with pytest.raises(m.Refused):
        m._preflight(args, time.monotonic() + 30)


@pytest.mark.parametrize('check', [False, True])
@pytest.mark.parametrize('scenario', ['ok', 'stderr', 'overflow', 'malformed', 'trailing', 'exit', 'timeout'])
def test_real_synthetic_child_fd_denial_bounds_kill_reap(leaf, args, monkeypatch, scenario, check):
    actual_popen = subprocess.Popen
    processes, commands = [], []
    with m.Store(create=True) as store:
        pin = store.write('evidence.json', {'synthetic': True})
        result = {'evidence': pin, 'attempt_claim_authenticated': True,
            'project_id': m.PROJECT, 'provider_request_count': None}
        if check:
            args.operation, args.evidence_sha256 = 'recover', pin['sha256']
            result = {'organization_id': 'c' * 32, 'evidence_sha256': pin['sha256'],
                'evidence_bytes': pin['byte_count'], 'report_sha256': 'd' * 64}
        payload = m.canonical({'schema': m.SCHEMA,
            'operation': 'evidence-check-worker' if check else 'evidence-worker', 'binding': m.binding(args),
            'operation_completed': True, 'result': result, **m.FALSE_FLAGS}) + b'\n'
        script = ('import os,socket,sys,time\n'
            f'assert os.fstat({store.fd}).st_ino == {os.fstat(store.fd).st_ino}\n'
            's=socket.socket()\n'
            'try:\n s.bind(("127.0.0.1",0))\n'
            'except PermissionError:\n pass\n'
            'else:\n raise RuntimeError("network not denied")\n')
        if scenario == 'timeout':
            script += 'time.sleep(20)\n'
        elif scenario == 'overflow':
            script += f'os.write(1,b"x"*{m.MAX_OUTPUT + 100})\n'
        elif scenario == 'malformed':
            script += 'os.write(1,b"{}\\n")\n'
        elif scenario == 'trailing':
            script += f'os.write(1,{payload!r}+b"trailing")\n'
        else:
            script += f'os.write(1,{payload!r})\n'
            if scenario == 'stderr':
                script += 'os.write(2,b"synthetic noise")\n'
            if scenario == 'exit':
                script += 'sys.exit(2)\n'
        def spawn(command, **kwargs):
            commands.append(command)
            assert command[:3] == ['/usr/bin/sandbox-exec', '-p', m.SANDBOX]
            assert command[3:6] == [str(m.frozen.PYTHON), '-B', str(m.SOURCE)]
            assert kwargs['pass_fds'] == (store.fd,)
            assert 'QC_USER_ID' not in kwargs['env'] and 'QC_API_TOKEN' not in kwargs['env']
            # Only the synthetic subprocess seam is replaced, never production code or pins.
            safe_env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR', 'PYTHONPYCACHEPREFIX')}
            kwargs['env'] = safe_env
            # macOS refuses nested sandbox_apply. The test process is already
            # natively denied; its real child inherits that denial. We check
            # the production sandbox command above but replace the nested
            # launcher only for this tiny synthetic subprocess.
            process = actual_popen(command[3:5] + ['-c', script], **kwargs)
            processes.append(process)
            return process
        monkeypatch.setattr(m.subprocess, 'Popen', spawn)
        if scenario == 'ok':
            assert m._child(args, store, time.monotonic() + 5, check=check) == result
        else:
            with pytest.raises(m.Refused):
                m._child(args, store, time.monotonic() + (0.2 if scenario == 'timeout' else 5), check=check)
        assert len(processes) == 1 and processes[0].poll() is not None
        completion = leaf / ('evidence-check-completed.json' if check else 'evidence-parent-completed.json')
        assert completion.exists() is (scenario == 'ok')
        if scenario == 'ok' and check:
            assert b'c' * 32 not in completion.read_bytes()


def test_safe_request_failure_reaches_outer_envelope(args, monkeypatch, capsys):
    value = {'intent_marker': 'inspect-project', 'endpoint': 'projects/read', 'application_dispatch_count': 1,
        'category': 'http_failure', 'http_status': 403, 'provider_request_count': None,
        'failure_file': {'sha256': 'c' * 64, 'byte_count': 300}}
    monkeypatch.setattr(m, '_preflight', lambda *a: None)
    monkeypatch.setattr(environment, '_bootstrap_cli_logging', lambda: None)
    monkeypatch.setattr(m, '_execute', lambda *a: (_ for _ in ()).throw(m.RequestFailed(m.canonical(value))))
    assert m.main(['evidence', '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256]) == 2
    output = m.parse(capsys.readouterr().out[:-1].encode())
    assert output['failure_observation'] == value and output['operation_completed'] is False


def test_recover_parent_does_not_read_bundle(leaf, args, recovery, monkeypatch):
    def child(supplied, store, deadline, *, check):
        assert check is True and (leaf / 'recover-claim.json').exists()
        recovery.events.append('validated')
        return {'organization_id': 'c' * 32}
    monkeypatch.setattr(m, '_child', child)
    original = m.Store.read
    def read(store, name):
        assert name not in ('evidence.json', 'claim.json', 'evidence-parent-completed.json')
        return original(store, name)
    monkeypatch.setattr(m.Store, 'read', read)
    assert invoke(args, recovery)['terminal'] == 'own_status_observed'


def test_stored_bundle_check_is_once_only_no_collector(leaf, args, recovery):
    with m.Store() as store:
        store.write('recover-claim.json', {**m.binding(args), 'evidence_sha256': args.evidence_sha256,
            'attempt_id': 2, 'shared_look': 1, 'development_look': 1})
        worker_args = copy.copy(args)
        worker_args.operation, worker_args.control_fd = 'evidence-check-worker', store.fd
        result = m._check_worker(worker_args, recovery.deadline)
        assert result['organization_id'] == 'c' * 32 and result['evidence_sha256'] == args.evidence_sha256
        with pytest.raises(FileExistsError):
            m._check_worker(worker_args, recovery.deadline)
    assert recovery.events == ['validated']


@pytest.mark.parametrize('mismatch', [None, 'record', 'profile', 'source'])
def test_fresh_input_family_admission_exact_projection(monkeypatch, mismatch):
    from scripts import arv2_newrule_storage_recovery_v4 as admission
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission
    events = []
    item = SimpleNamespace(record_bytes=b'row', profile_bytes=b'profile',
        source_files=(SimpleNamespace(project_path='main.py', source_bytes=b'exact'),))
    supplied = copy.deepcopy(item)
    if mismatch == 'record':
        supplied.record_bytes = b'other'
    elif mismatch == 'profile':
        supplied.profile_bytes = b'other'
    elif mismatch == 'source':
        supplied.source_files[0].source_bytes = b'other'
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: events.append('environment'))
    def load_package(path, **kwargs):
        assert path == m.frozen.PACKAGE
        assert kwargs == {'expected_package_sha256': m.frozen.PACKAGE_SHA256,
            'lineage_path': m.frozen.LINEAGE, 'expected_lineage_sha256': m.frozen.LINEAGE_SHA256}
        events.append('package')
        return 'synthetic-value'
    monkeypatch.setattr(m.frozen.prepared_input.october, 'load_october_order_input_package', load_package)
    def load_family(value, **kwargs):
        assert value == 'synthetic-value' and kwargs['expected_family_sha256'] == m.v5.FAMILY_SHA256
        assert kwargs['expected_new_source_pins'] == dict(m.frozen.NEW_SOURCE_PINS)
        assert kwargs['expected_host_source_pins'] == {name: m.frozen.SOURCE_PINS[name] for name in submission.HOST_SOURCE_NAMES}
        events.append('family')
        return 'synthetic-plan'
    monkeypatch.setattr(submission, 'load_family', load_family)
    @contextmanager
    def session(plan, digest):
        assert plan == 'synthetic-plan' and digest == m.v5.FAMILY_SHA256
        events.append('held-session')
        yield 'directory', 'record'
    monkeypatch.setattr(submission, '_session', session)
    def require_admission(directory, plan, record, pin):
        assert (directory, plan, record, pin) == ('directory', 'synthetic-plan', 'record', m.v5.ADMISSION_SHA256)
        events.append('admission')
    monkeypatch.setattr(admission, 'require_admission', require_admission)
    monkeypatch.setattr(submission, '_cell', lambda *a: (None, item, None))
    if mismatch:
        with pytest.raises(m.Refused, match='input_admission'):
            m._admission(supplied, time.monotonic() + 30)
    else:
        m._admission(supplied, time.monotonic() + 30)
    assert events[:5] == ['environment', 'package', 'family', 'held-session', 'admission']
