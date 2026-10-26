"""Public synthetic channels only; run with native network/private denial."""
import ast
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import observe_arv2_r298_plain_readiness as m


def args():
    return SimpleNamespace(expected_head='a' * 40, caller_sha256=m.CALLER_SHA256,
        observer_sha256='c' * 64)


def credentials():
    return {'QC_USER_ID': 'SYNTHETIC-USER', 'QC_API_TOKEN': 'SYNTHETIC-SECRET',
        'UNSAFE_EXTRA': 'SYNTHETIC-OTHER', 'PYTHONPATH': '/unsafe'}


def captured(stdout=b'', stderr=b'', actual_exit=0, bound=None):
    return m.Captured(stdout, stderr, actual_exit, bound, '2026-10-25T00:00:00Z',
        '2026-10-25T00:00:01Z', len(stdout), len(stderr), m.sha(stdout), m.sha(stderr), True)


def packet(actual_exit=0):
    return {'validated': True, 'actual_exit': actual_exit,
        'value': {'operation_completed': actual_exit == 0, 'test_finite_value': 'safe'}}


@pytest.fixture
def isolated_support(monkeypatch, tmp_path):
    monkeypatch.setattr(m.tempfile, 'mkdtemp', lambda **kwargs: str(tmp_path))
    return tmp_path


@pytest.fixture
def fake_preflight(monkeypatch, isolated_support):
    calls = []
    monkeypatch.setattr(m, '_preflight', lambda namespace, environment: calls.append((namespace, environment.copy())))
    return calls


@pytest.mark.parametrize('environment', [{}, {'QC_USER_ID': 'x'}, {'QC_API_TOKEN': 'x'},
    {'QC_USER_ID': '', 'QC_API_TOKEN': 'x'}, {'QC_USER_ID': ' ', 'QC_API_TOKEN': 'x'},
    {'QC_USER_ID': 'x', 'QC_API_TOKEN': '\n\t'}, {'QC_USER_ID': None, 'QC_API_TOKEN': 'x'},
    {'QC_USER_ID': 2, 'QC_API_TOKEN': 'x'}])
def test_missing_credentials_refuse_before_support_or_subprocess(monkeypatch, environment):
    monkeypatch.setattr(m, '_capture', lambda *a, **k: pytest.fail('subprocess created'))
    monkeypatch.setattr(m.tempfile, 'mkdtemp', lambda **k: pytest.fail('support allocated'))
    result, code = m.observe(args(), environ=environment)
    assert code == 2 and result['failure_code'] == 'credential_handoff_absent'
    assert not result['operational_child_dispatch_attempted'] and not result['validator_dispatched']
    assert result['attempt_consumption'] == 'no_child_dispatched' and result['parent'] is None


@pytest.mark.parametrize('actual_exit', [0, 2])
def test_one_parent_and_one_credential_free_validator(monkeypatch, fake_preflight, actual_exit):
    calls, parent_raw = [], b'SYNTHETIC RAW CHANNEL\n\n'
    def capture(command, **kwargs):
        calls.append((command.copy(), {**kwargs, 'environ': kwargs['environ'].copy()}))
        return (captured(parent_raw, actual_exit=actual_exit) if len(calls) == 1
            else captured(m.canonical(packet(actual_exit))))
    monkeypatch.setattr(m, '_capture', capture)
    original = credentials()
    result, code = m.observe(args(), environ=original)
    assert code == actual_exit and result['output_validated'] is True
    assert result['validated_output'] == packet(actual_exit)['value']
    assert result['source_binding'] == vars(args()) and len(calls) == len(fake_preflight) == 2
    assert result['attempt_consumption'] == 'consumed_or_ambiguous_no_retry'
    command, parent = calls[0]
    assert command == [str(m.PYTHON), '-B', str(m.CALLER), 'recover',
        '--expected-head', args().expected_head, '--caller-sha256', args().caller_sha256]
    assert parent['timeout'] == 930 and parent['environ']['QC_API_TOKEN'] == original['QC_API_TOKEN']
    assert not {'UNSAFE_EXTRA', 'PYTHONPATH'} & parent['environ'].keys()
    command, validator = calls[1]
    assert command == m._validator_command(args(), actual_exit)
    assert validator['timeout'] == 15 and validator['input_bytes'] == parent_raw
    assert validator['max_stdout'] == 135168
    assert not {'QC_USER_ID', 'QC_API_TOKEN'} & validator['environ'].keys()
    assert all(not {'QC_USER_ID', 'QC_API_TOKEN'} & item[1].keys() for item in fake_preflight)
    assert original == credentials()
    assert all(value.encode() not in m.canonical(result) for value in original.values())
    assert parent_raw not in m.canonical(result)


@pytest.mark.parametrize('observed,code', [
    (captured(b'SYNTHETIC RAW', bound='deadline', actual_exit=-9), 'parent_bound'),
    (captured(b'SYNTHETIC RAW', bound='stdout_bound', actual_exit=-9), 'parent_bound'),
    (captured(b'SYNTHETIC RAW', stderr=b'SYNTHETIC SECRET'), 'parent_stderr'),
    (captured(actual_exit=1), 'parent_exit'), (captured(actual_exit=None), 'parent_exit'),
    (captured(actual_exit=False), 'parent_exit'), (captured(actual_exit=True), 'parent_exit')])
def test_parent_failure_preserves_safe_metadata_without_retry(monkeypatch, fake_preflight, observed, code):
    calls = []
    monkeypatch.setattr(m, '_capture', lambda *a, **k: (calls.append(1), observed)[1])
    result, exit_code = m.observe(args(), environ=credentials())
    assert exit_code == 2 and result['failure_code'] == code and len(calls) == 1
    assert result['parent'] == observed.metadata() and not result['validator_dispatched']
    assert result['attempt_consumption'] == 'consumed_or_ambiguous_no_retry'
    assert result['validated_output'] is None and b'SYNTHETIC' not in m.canonical(result)


@pytest.mark.parametrize('observed,code', [
    (captured(b'SYNTHETIC SECRET', bound='deadline'), 'validator_bound'),
    (captured(b'SYNTHETIC SECRET', stderr=b'SYNTHETIC SECRET'), 'validator_stderr'),
    (captured(b'SYNTHETIC SECRET', actual_exit=2), 'validator_refused'),
    (captured(b'SYNTHETIC SECRET', actual_exit=False), 'validator_refused'),
    (captured(b'SYNTHETIC SECRET'), 'validator_shape'),
    (captured(m.canonical({'validated': False})), 'validator_shape'),
    (captured(m.canonical(packet(2))), 'validator_shape'),
    (captured(m.canonical({**packet(), 'actual_exit': False})), 'validator_shape'),
    (captured(m.canonical({**packet(), 'unexpected': 1})), 'validator_shape'),
    (captured(m.canonical({**packet(), 'value': 'SYNTHETIC SECRET'})), 'validator_shape'),
    (captured(m.canonical(packet()) + b'garbage'), 'validator_shape'),
    (captured(b' ' + m.canonical(packet())), 'validator_shape')])
def test_invalid_validator_never_exposes_raw_or_retries(monkeypatch, fake_preflight, observed, code):
    calls = []
    def capture(*a, **k):
        calls.append(1)
        return captured(b'finite parent') if len(calls) == 1 else observed
    monkeypatch.setattr(m, '_capture', capture)
    result, exit_code = m.observe(args(), environ=credentials())
    assert exit_code == 2 and result['failure_code'] == code and len(calls) == 2
    assert not result['output_validated'] and result['validated_output'] is None
    assert b'SYNTHETIC' not in m.canonical(result)


def test_hostile_exception_never_formats(monkeypatch, fake_preflight):
    class Hostile(RuntimeError):
        def __str__(self):
            pytest.fail('stringified')
        def __repr__(self):
            pytest.fail('repr')
    def capture(*a, **k):
        raise Hostile('SYNTHETIC SECRET')
    monkeypatch.setattr(m, '_capture', capture)
    result, code = m.observe(args(), environ=credentials())
    assert code == 2 and result['failure_code'] == 'observer_refused'
    assert result['attempt_consumption'] == 'consumed_or_ambiguous_no_retry'
    assert b'SYNTHETIC' not in m.canonical(result)


def test_post_parent_source_change_refuses_before_validator(monkeypatch, isolated_support):
    events = []
    def preflight(*a):
        events.append('preflight')
        if len(events) == 3:
            raise m.ObserverError('git_state')
    def capture(*a, **k):
        events.append('parent')
        return captured(b'finite parent')
    monkeypatch.setattr(m, '_preflight', preflight)
    monkeypatch.setattr(m, '_capture', capture)
    result, code = m.observe(args(), environ=credentials())
    assert events == ['preflight', 'parent', 'preflight']
    assert code == 2 and result['failure_code'] == 'git_state'
    assert result['parent']['actual_exit'] == 0 and not result['validator_dispatched']
    assert result['validated_output'] is None


@pytest.mark.parametrize('field,value', [('expected_head', 'bad'), ('expected_head', True),
    ('caller_sha256', 'BAD'), ('observer_sha256', 'x' * 64)])
def test_arguments_refuse_before_allocation(monkeypatch, field, value):
    namespace = args()
    setattr(namespace, field, value)
    monkeypatch.setattr(m.tempfile, 'mkdtemp', lambda **k: pytest.fail('allocated'))
    result, code = m.observe(namespace, environ=credentials())
    assert code == 2 and result['failure_code'] == 'arguments'
    assert result['attempt_consumption'] == 'no_child_dispatched'


def prepared_state(monkeypatch):
    namespace = args()
    sources = {path.relative_to(m.ROOT).as_posix(): ('public synthetic ' + str(i)).encode()
        for i, path in enumerate((m.SOURCE, m.CALLER, m.HELPER, *m.TESTS))}
    namespace.observer_sha256 = m.sha(sources[m.SOURCE.relative_to(m.ROOT).as_posix()])
    namespace.caller_sha256 = m.sha(sources[m.CALLER.relative_to(m.ROOT).as_posix()])
    monkeypatch.setattr(m, 'CALLER_SHA256', namespace.caller_sha256)
    monkeypatch.setattr(m, 'HELPER_SHA256', m.sha(sources[m.HELPER.relative_to(m.ROOT).as_posix()]))
    monkeypatch.setattr(m, '_source_bytes', lambda path: sources[path.relative_to(m.ROOT).as_posix()])
    commands = []
    def git(command, environment):
        commands.append(command)
        for operation, value in ((['rev-parse', '--show-toplevel'], str(m.ROOT)),
            (['branch', '--show-current'], m.BRANCH), (['rev-parse', 'HEAD'], namespace.expected_head)):
            if command == operation:
                return (value + '\n').encode()
        if command[0] == 'status':
            return b''
        raw = sources[command[2].split(':', 1)[1]]
        return (str(len(raw)) + '\n').encode() if command[1] == '-s' else raw
    monkeypatch.setattr(m, '_git', git)
    return namespace, commands, sources, git


def test_preflight_exact_six_committed_sources_and_clean_state(monkeypatch, tmp_path):
    namespace, commands, sources, _ = prepared_state(monkeypatch)
    m._preflight(namespace, m._environment(tmp_path))
    assert len([command for command in commands if command[:2] == ['cat-file', 'blob']]) == 6
    assert commands[-2:] == [['rev-parse', 'HEAD'], ['status', '--porcelain', '--untracked-files=normal']]


@pytest.mark.parametrize('target', ['root', 'branch', 'head', 'status', 'size', 'blob', 'pin'])
def test_preflight_public_mismatch_refuses(monkeypatch, tmp_path, target):
    namespace, commands, sources, real_git = prepared_state(monkeypatch)
    def git(command, environment):
        reject = ((target == 'root' and command == ['rev-parse', '--show-toplevel'])
            or (target == 'branch' and command[0] == 'branch')
            or (target == 'head' and command == ['rev-parse', 'HEAD'])
            or (target == 'status' and command[0] == 'status')
            or (target == 'size' and command[:2] == ['cat-file', '-s'])
            or (target == 'blob' and command[:2] == ['cat-file', 'blob']))
        return b'mismatch\n' if reject else real_git(command, environment)
    monkeypatch.setattr(m, '_git', git)
    if target == 'pin':
        namespace.observer_sha256 = '0' * 64
    with pytest.raises(m.ObserverError):
        m._preflight(namespace, m._environment(tmp_path))


@pytest.mark.parametrize('value', [None, '', '0' * 64])
def test_unbound_or_wrong_frozen_caller_pin_refuses(monkeypatch, tmp_path, value):
    monkeypatch.setattr(m, 'CALLER_SHA256', value)
    namespace = SimpleNamespace(expected_head='a' * 40, caller_sha256='b' * 64, observer_sha256='c' * 64)
    monkeypatch.setattr(m, '_git', lambda *a: pytest.fail('Git before caller pin'))
    with pytest.raises(m.ObserverError, match='^source_pin$'):
        m._preflight(namespace, m._environment(tmp_path))


@pytest.mark.parametrize('observed', [captured(actual_exit=False), captured(actual_exit=2),
    captured(stderr=b'private'), captured(bound='deadline')])
def test_git_uses_same_strict_channels(monkeypatch, tmp_path, observed):
    monkeypatch.setattr(m, '_capture', lambda *a, **k: observed)
    with pytest.raises(m.ObserverError, match='^git_state$'):
        m._git(['status'], m._environment(tmp_path))


def child(code, tmp_path, **kwargs):
    return m._capture([str(m.PYTHON), '-B', '-c', code], environ=m._environment(tmp_path),
        timeout=kwargs.pop('timeout', 5), **kwargs)


def test_real_child_separate_channels_and_actual_exit(tmp_path):
    result = child("import sys;sys.stdout.buffer.write(b'public');sys.stderr.buffer.write(b'synthetic noise');sys.exit(2)", tmp_path)
    assert result.stdout == b'public' and result.stderr == b'synthetic noise'
    assert result.actual_exit == 2 and result.bound is None and result.spawned
    assert result.metadata()['stderr_sha256'] == m.sha(b'synthetic noise')
    assert 'synthetic noise' not in repr(result) and 'public' not in repr(result)


@pytest.mark.parametrize('count,limit,bound', [(131072, 131072, None),
    (131073, 131072, 'stdout_bound'), (135168, 135168, None), (135169, 135168, 'stdout_bound')])
def test_real_exact_parent_and_validator_stdout_bounds(tmp_path, count, limit, bound):
    result = child(f'import sys;sys.stdout.buffer.write(b"x"*{count})', tmp_path, max_stdout=limit)
    assert result.bound == bound and len(result.stdout) == min(count, limit)
    assert result.stdout_observed_bytes == count
    assert result.stdout_sha256 == m.sha(b'x' * count)


@pytest.mark.parametrize('count,bound', [(4096, None), (4097, 'stderr_bound')])
def test_real_stderr_exact_bound(tmp_path, count, bound):
    result = child(f'import sys;sys.stderr.buffer.write(b"x"*{count})', tmp_path)
    assert result.bound == bound and len(result.stderr) == min(count, 4096)
    assert result.stderr_observed_bytes == count


def test_real_stdin_concurrent_with_large_stdout(tmp_path):
    raw = b'public-data' * 10000
    result = child('import sys;data=sys.stdin.buffer.read();sys.stdout.buffer.write(data)', tmp_path, input_bytes=raw)
    assert result.actual_exit == 0 and result.bound is None and result.stdout == raw and not result.stderr


def test_real_empty_stdin_eof(tmp_path):
    result = child('import sys;assert sys.stdin.buffer.read()==b"";print("ok")', tmp_path, input_bytes=b'')
    assert result.actual_exit == 0 and result.stdout == b'ok\n' and result.bound is None


def test_real_deadline_kills_and_reaps_only_created_child(tmp_path):
    children = []
    def popen(*a, **k):
        process = subprocess.Popen(*a, **k)
        children.append(process)
        return process
    result = child('import time;time.sleep(5)', tmp_path, timeout=0.05, popen=popen)
    assert result.bound == 'deadline' and result.actual_exit == -9
    assert len(children) == 1 and children[0].poll() == -9


def test_spawn_failure_is_finite_and_not_falsely_spawned(tmp_path):
    def popen(*a, **k):
        raise RuntimeError('SYNTHETIC SECRET')
    result = child('pass', tmp_path, popen=popen)
    assert result.bound == 'observer_io' and result.actual_exit is None and not result.spawned
    assert b'SYNTHETIC' not in m.canonical(result.metadata())


@pytest.mark.parametrize('changes', [{'timeout': True}, {'timeout': float('inf')},
    {'timeout': float('nan')}, {'timeout': 0}, {'timeout': 931}, {'max_stdout': True},
    {'max_stdout': 135169}, {'input_bytes': b'x' * 131073}])
def test_invalid_capture_arguments_refuse_before_spawn(tmp_path, changes):
    kwargs = {'environ': m._environment(tmp_path), 'timeout': 1, **changes}
    with pytest.raises(m.ObserverError, match='^arguments$'):
        m._capture([str(m.PYTHON)], popen=lambda *a, **k: pytest.fail('spawned'), **kwargs)


@pytest.mark.parametrize('actual_exit', [0, 2])
def test_genuine_caller_import_and_environment_in_literal_validator(tmp_path, actual_exit):
    # Public-source import and genuine environment guard; source/Git preflight
    # and deep output semantics deliberately synthetic, never operational.
    prefix = '''from scripts import run_arv2_r298_plain_readiness as c
from scripts import arv2_newrule_execution_environment as e
import sys,time
e._require_environment()
assert 'QC_API_TOKEN' not in __import__('os').environ
def preflight(args, deadline):
 assert args.operation=='recover' and args.control_fd is None and args.deadline is None
 assert deadline>time.monotonic()
c._preflight=preflight
c.validate_output=lambda raw,actual,args:{'operation_completed':actual==0,'finite':'safe'}
'''
    command = [str(m.PYTHON), '-B', '-c', prefix + m.VALIDATOR_CODE,
        args().expected_head, args().caller_sha256, str(actual_exit)]
    result = m._capture(command, environ=m._environment(tmp_path), timeout=10,
        input_bytes=b'public synthetic', max_stdout=m.MAX_VALIDATOR)
    assert result.actual_exit == 0 and result.bound is None and result.stderr == b''
    assert m._validated_packet(result, actual_exit) == {'operation_completed': actual_exit == 0, 'finite': 'safe'}


def test_genuine_validator_rejects_opaque_parent_without_disclosure(tmp_path):
    prefix = '''from scripts import run_arv2_r298_plain_readiness as c
c._preflight=lambda args,deadline:None
'''
    result = m._capture([str(m.PYTHON), '-B', '-c', prefix + m.VALIDATOR_CODE,
        args().expected_head, args().caller_sha256, '2'], environ=m._environment(tmp_path),
        timeout=10, input_bytes=b'SYNTHETIC SECRET\n\n', max_stdout=m.MAX_VALIDATOR)
    assert result.actual_exit == 2 and result.stdout == b'{"validated":false}\n' and not result.stderr


def test_final_envelope_bound_inclusive_and_rejects_plus_one(monkeypatch, fake_preflight):
    monkeypatch.setattr(m, '_capture', lambda command, **k:
        captured(m.canonical(packet())) if command[0] == '/usr/bin/sandbox-exec' else captured(b'parent'))
    first, code = m.observe(args(), environ=credentials())
    assert code == 0
    length = len(m.canonical(first))
    monkeypatch.setattr(m, 'MAX_OUTPUT', length)
    exact, code = m.observe(args(), environ=credentials())
    assert code == 0 and len(m.canonical(exact)) == length
    monkeypatch.setattr(m, 'MAX_OUTPUT', length - 1)
    result, code = m.observe(args(), environ=credentials())
    assert code == 2 and result['failure_code'] == 'validator_shape' and result['validated_output'] is None


def test_main_emits_only_finite_observed_envelope(monkeypatch):
    class Output:
        buffer = io.BytesIO()
    output = Output()
    expected = {'schema': m.SCHEMA, 'failure_code': 'parent_stderr'}
    monkeypatch.setattr(m, 'observe', lambda namespace: (expected, 2))
    monkeypatch.setattr(m.sys, 'stdout', output)
    code = m.main(['--expected-head', args().expected_head, '--caller-sha256', args().caller_sha256,
        '--observer-sha256', args().observer_sha256])
    assert code == 2 and output.buffer.getvalue() == m.canonical(expected)


def test_profile_and_validator_remain_bounded_output_only():
    profile = m.profile_record()
    assert profile['max_operational_dispatches'] == profile['max_validator_dispatches'] == 1
    assert profile['max_observer_output'] == 147456 and not profile['output_leaf_reads']
    assert not profile['raw_channels_printed'] and not profile['capacity_or_launch_allowed']
    assert m.PROFILE_SHA256 == m.sha(m.canonical(profile))
    for fragment in ('deny network*', str(m.ROOT / 'artifacts'),
        '/Users/sheltonchen/Library/Keychains', '/Library/Keychains', '/usr/bin/security'):
        assert fragment in m.SANDBOX
    parsed = ast.parse(m.VALIDATOR_CODE)
    calls = [node.func.attr for node in ast.walk(parsed) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)]
    assert 'validate_output' in calls and '_preflight' in calls
    assert not {'recover', '_workflow', 'main', 'read_bytes', 'open'} & set(calls)
    compile(m.VALIDATOR_CODE, '<public-validator>', 'exec')
