"""Synthetic children only; run under native network/private-data denial."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import observe_arv2_r298_handoff_recovery as m


def args():
    return SimpleNamespace(expected_head='a' * 40, caller_sha256='b' * 64,
        observer_sha256='c' * 64)


def captured(stdout=b'', stderr=b'', actual_exit=0, bound=None):
    return m.Captured(stdout, stderr, actual_exit, bound, '2026-10-25T00:00:00Z',
        '2026-10-25T00:00:01Z', len(stdout), len(stderr), m.sha(stdout), m.sha(stderr))


@pytest.fixture
def fake_preflight(monkeypatch):
    calls = []
    monkeypatch.setattr(m, '_preflight', lambda namespace, environment: calls.append((namespace, environment.copy())))
    return calls


def credentials():
    return {'QC_USER_ID': 'SYNTHETIC-USER', 'QC_API_TOKEN': 'SYNTHETIC-PRIVATE-TOKEN',
        'UNSAFE_EXTRA': 'SYNTHETIC-OTHER-SECRET', 'PYTHONPATH': '/unsafe'}


def validator_packet(exit_code=0):
    return {'validated': True, 'actual_exit': exit_code,
        'value': {'operation_completed': exit_code == 0, 'test_finite_value': 'safe'}}


@pytest.mark.parametrize('environment', [{}, {'QC_USER_ID': 'x'}, {'QC_API_TOKEN': 'x'},
    {'QC_USER_ID': '', 'QC_API_TOKEN': 'x'}, {'QC_USER_ID': ' ', 'QC_API_TOKEN': 'x'},
    {'QC_USER_ID': 'x', 'QC_API_TOKEN': '\n\t'}, {'QC_USER_ID': None, 'QC_API_TOKEN': 'x'},
    {'QC_USER_ID': 2, 'QC_API_TOKEN': 'x'}])
def test_missing_handoff_stops_before_files_subprocess_or_claim(monkeypatch, environment):
    monkeypatch.setattr(m, '_capture', lambda *a, **k: pytest.fail('subprocess created'))
    monkeypatch.setattr(m.tempfile, 'mkdtemp', lambda *a, **k: pytest.fail('support allocated'))
    result, exit_code = m.observe(args(), environ=environment)
    assert exit_code == 2 and result['failure_code'] == 'credential_handoff_absent'
    assert result['operational_child_dispatch_attempted'] is False
    assert result['validator_dispatched'] is False and result['parent'] is None
    assert result['attempt_consumption'] == 'no_child_dispatched'


def test_concrete_posix_path_can_construct_strict_child_environment(tmp_path):
    environment = m._environment(tmp_path, {key: credentials()[key] for key in m.CREDENTIAL_NAMES})
    assert environment['QC_API_TOKEN'] == 'SYNTHETIC-PRIVATE-TOKEN'
    assert environment['LANG'] == environment['LC_ALL'] == 'en_US.UTF-8'
    assert environment['PATH'] == m.PATH_VALUE
    assert set(environment) == {'PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'TMP', 'TEMP',
        'XDG_CACHE_HOME', 'PYTHONPYCACHEPREFIX', 'PYTHONDONTWRITEBYTECODE', *m.CREDENTIAL_NAMES}


@pytest.mark.parametrize('support', [Path('/tmp'), m.ROOT / '.pytest_cache', Path('relative')])
def test_support_paths_never_escape_designated_root(support):
    with pytest.raises(m.ObserverError, match='^support_path$'):
        m._environment(support)


@pytest.mark.parametrize('actual_exit', [0, 2])
def test_exact_one_parent_then_one_credential_free_validator(monkeypatch, fake_preflight, actual_exit):
    calls, parent_raw = [], b'SYNTHETIC RAW CHANNEL NEVER PRINTED\n\n'
    def capture(command, **kwargs):
        calls.append((command.copy(), {**kwargs, 'environ': kwargs['environ'].copy()}))
        if len(calls) == 1:
            return captured(parent_raw, actual_exit=actual_exit)
        return captured(m.canonical(validator_packet(actual_exit)))
    monkeypatch.setattr(m, '_capture', capture)
    original_environment = credentials()
    result, code = m.observe(args(), environ=original_environment)
    assert code == actual_exit and result['output_validated'] is True
    assert result['validated_output'] == validator_packet(actual_exit)['value']
    assert result['operational_child_dispatch_attempted'] and result['validator_dispatched']
    assert result['attempt_consumption'] == 'consumed_or_ambiguous_no_retry'
    assert result['source_binding'] == vars(args())
    assert len(calls) == 2 and len(fake_preflight) == 2
    parent_command, parent = calls[0]
    validator_command, validator = calls[1]
    assert parent_command == [str(m.PYTHON), '-B', str(m.CALLER), 'recover',
        '--expected-head', 'a' * 40, '--caller-sha256', 'b' * 64]
    assert parent['timeout'] == 615 and parent['environ']['QC_API_TOKEN'] == 'SYNTHETIC-PRIVATE-TOKEN'
    assert 'UNSAFE_EXTRA' not in parent['environ'] and 'PYTHONPATH' not in parent['environ']
    assert validator_command == m._validator_command(args(), actual_exit)
    assert validator['timeout'] == 15 and validator['input_bytes'] == parent_raw
    assert not set(m.CREDENTIAL_NAMES) & set(validator['environ'])
    assert not set(m.CREDENTIAL_NAMES) & set(fake_preflight[0][1])
    assert original_environment == credentials()
    serialized = m.canonical(result)
    for forbidden in (b'PRIVATE-TOKEN', b'SYNTHETIC-USER', b'OTHER-SECRET', parent_raw):
        assert forbidden not in serialized


@pytest.mark.parametrize('parent,code', [
    (captured(b'SYNTHETIC-RAW', bound='deadline', actual_exit=-9), 'parent_bound'),
    (captured(b'SYNTHETIC-RAW', bound='stdout_bound', actual_exit=-9), 'parent_bound'),
    (captured(b'SYNTHETIC-RAW', stderr=b'SYNTHETIC-SECRET'), 'parent_stderr'),
    (captured(b'SYNTHETIC-RAW', actual_exit=1), 'parent_exit'),
    (captured(b'SYNTHETIC-RAW', actual_exit=None), 'parent_exit')])
def test_parent_refusal_never_invokes_validator_or_retries(monkeypatch, fake_preflight, parent, code):
    calls = []
    def capture(*a, **k):
        calls.append(1)
        return parent
    monkeypatch.setattr(m, '_capture', capture)
    result, exit_code = m.observe(args(), environ=credentials())
    assert exit_code == 2 and result['failure_code'] == code and len(calls) == 1
    assert result['attempt_consumption'] == 'consumed_or_ambiguous_no_retry'
    assert result['validator_dispatched'] is False and result['validated_output'] is None
    assert b'SYNTHETIC' not in m.canonical(result)


@pytest.mark.parametrize('validator,code', [
    (captured(b'SYNTHETIC-SECRET', bound='deadline', actual_exit=-9), 'validator_bound'),
    (captured(b'SYNTHETIC-SECRET', stderr=b'SYNTHETIC-SECRET'), 'validator_stderr'),
    (captured(b'SYNTHETIC-SECRET', actual_exit=2), 'validator_refused'),
    (captured(b'SYNTHETIC-SECRET'), 'validator_shape'),
    (captured(m.canonical({'validated': False})), 'validator_shape'),
    (captured(m.canonical(validator_packet(2))), 'validator_shape'),
    (captured(m.canonical(validator_packet()) + b'garbage'), 'validator_shape')])
def test_bad_validator_is_finite_and_never_retried(monkeypatch, fake_preflight, validator, code):
    calls = []
    def capture(*a, **k):
        calls.append(1)
        return captured(b'finite parent') if len(calls) == 1 else validator
    monkeypatch.setattr(m, '_capture', capture)
    result, exit_code = m.observe(args(), environ=credentials())
    assert exit_code == 2 and result['failure_code'] == code and len(calls) == 2
    assert result['output_validated'] is False and result['validated_output'] is None
    assert b'SYNTHETIC' not in m.canonical(result)


def test_unexpected_exception_is_not_interpolated(monkeypatch, fake_preflight):
    def capture(*a, **k):
        raise RuntimeError('SYNTHETIC SECRET')
    monkeypatch.setattr(m, '_capture', capture)
    result, code = m.observe(args(), environ=credentials())
    assert code == 2 and result['failure_code'] == 'observer_refused'
    assert result['attempt_consumption'] == 'consumed_or_ambiguous_no_retry'
    assert b'SYNTHETIC' not in m.canonical(result)


def test_concurrent_source_change_refuses_before_validator_import(monkeypatch):
    events = []
    def preflight(namespace, environment):
        events.append('preflight')
        assert not set(m.CREDENTIAL_NAMES) & set(environment)
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
    assert result['validator_dispatched'] is False and result['validated_output'] is None
    assert result['attempt_consumption'] == 'consumed_or_ambiguous_no_retry'
    assert result['parent']['stdout_sha256'] == m.sha(b'finite parent')
    assert result['parent']['actual_exit'] == 0
    assert b'finite parent' not in m.canonical(result)


@pytest.mark.parametrize('field,value', [('expected_head', 'bad'), ('expected_head', True),
    ('caller_sha256', 'BAD'), ('observer_sha256', 'x' * 64)])
def test_malformed_bindings_stop_before_any_subprocess(monkeypatch, field, value):
    namespace = args()
    setattr(namespace, field, value)
    monkeypatch.setattr(m, '_capture', lambda *a, **k: pytest.fail('subprocess created'))
    result, code = m.observe(namespace, environ=credentials())
    assert code == 2 and result['failure_code'] == 'arguments'
    assert result['attempt_consumption'] == 'no_child_dispatched'


def test_source_reader_rejects_symlink_and_oversize_and_accepts_exact_bytes(tmp_path):
    path = tmp_path / 'source.py'
    path.write_bytes(b'public fixture\n')
    assert m._source_bytes(path) == b'public fixture\n'
    link = tmp_path / 'link.py'
    link.symlink_to(path)
    with pytest.raises(m.ObserverError, match='^source_pin$'):
        m._source_bytes(link)
    path.write_bytes(b'x' * (m.MAX_SOURCE + 1))
    with pytest.raises(m.ObserverError, match='^source_pin$'):
        m._source_bytes(path)


def prepared_public_state(monkeypatch):
    namespace = args()
    sources = {str(path.relative_to(m.ROOT)): ('synthetic ' + str(index)).encode()
        for index, path in enumerate((m.SOURCE, m.CALLER, m.TESTS, m.CALLER_TESTS))}
    namespace.observer_sha256 = m.sha(sources[str(m.SOURCE.relative_to(m.ROOT))])
    namespace.caller_sha256 = m.sha(sources[str(m.CALLER.relative_to(m.ROOT))])
    monkeypatch.setattr(m, '_source_bytes', lambda path: sources[str(path.relative_to(m.ROOT))])
    commands = []
    def git(command, environment):
        commands.append(command)
        if command == ['rev-parse', '--show-toplevel']:
            return (str(m.ROOT) + '\n').encode()
        if command == ['branch', '--show-current']:
            return (m.BRANCH + '\n').encode()
        if command == ['rev-parse', 'HEAD']:
            return (namespace.expected_head + '\n').encode()
        if command == ['status', '--porcelain', '--untracked-files=normal']:
            return b''
        if command[0] == 'show':
            return sources[command[1].split(':', 1)[1]]
        pytest.fail('unexpected Git command')
    monkeypatch.setattr(m, '_git', git)
    return namespace, sources, commands, git


def test_preflight_pins_exact_clean_head_and_all_four_committed_sources(monkeypatch, tmp_path):
    namespace, sources, commands, git = prepared_public_state(monkeypatch)
    m._preflight(namespace, m._environment(tmp_path))
    assert len([item for item in commands if item[0] == 'show']) == 4
    assert commands[-2:] == [['rev-parse', 'HEAD'], ['status', '--porcelain', '--untracked-files=normal']]


@pytest.mark.parametrize('target', ['root', 'branch', 'head', 'status', 'blob'])
def test_public_git_mismatch_refuses_without_operational_dispatch(monkeypatch, tmp_path, target):
    namespace, sources, commands, real_git = prepared_public_state(monkeypatch)
    def git(command, environment):
        reject = ((target == 'root' and command == ['rev-parse', '--show-toplevel'])
            or (target == 'branch' and command == ['branch', '--show-current'])
            or (target == 'head' and command == ['rev-parse', 'HEAD'])
            or (target == 'status' and command[0] == 'status')
            or (target == 'blob' and command[0] == 'show'))
        return b'mismatch\n' if reject else real_git(command, environment)
    monkeypatch.setattr(m, '_git', git)
    with pytest.raises(m.ObserverError):
        m._preflight(namespace, m._environment(tmp_path))


@pytest.mark.parametrize('field', ['caller_sha256', 'observer_sha256'])
def test_cli_pin_mismatch_refuses_even_if_current_git_blob_matches(monkeypatch, tmp_path, field):
    namespace, sources, commands, git = prepared_public_state(monkeypatch)
    setattr(namespace, field, '0' * 64)
    with pytest.raises(m.ObserverError, match='^source_pin$'):
        m._preflight(namespace, m._environment(tmp_path))


def test_last_public_state_check_catches_concurrent_head_change(monkeypatch, tmp_path):
    namespace, sources, commands, real_git = prepared_public_state(monkeypatch)
    seen = []
    def git(command, environment):
        if command == ['rev-parse', 'HEAD']:
            seen.append(1)
            if len(seen) == 2:
                return b'0' * 40 + b'\n'
        return real_git(command, environment)
    monkeypatch.setattr(m, '_git', git)
    with pytest.raises(m.ObserverError, match='^git_state$'):
        m._preflight(namespace, m._environment(tmp_path))


def test_native_validator_contract_denies_sensitive_surfaces_and_does_not_invoke_recover():
    command = m._validator_command(args(), 2)
    assert command[:3] == ['/usr/bin/sandbox-exec', '-p', m.SANDBOX]
    assert '(deny network*)' in m.SANDBOX
    assert str(m.ROOT / 'artifacts') in m.SANDBOX and '/Library/Keychains' in m.SANDBOX
    assert '/usr/bin/security' in m.SANDBOX
    assert 'c.validate_output(raw,actual_exit,args)' in m.VALIDATOR_CODE
    assert m.VALIDATOR_CODE.index('c._preflight(args,time.monotonic()+12)') < m.VALIDATOR_CODE.index('c.validate_output(raw,actual_exit,args)')
    assert 'c.main(' not in m.VALIDATOR_CODE and 'c._execute(' not in m.VALIDATOR_CODE
    assert 'raw=sys.stdin.buffer.read(131073)' in m.VALIDATOR_CODE


def test_real_synthetic_child_captures_both_channels_and_stdin(tmp_path):
    code = 'import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data); sys.stderr.buffer.write(b"synthetic warning")'
    result = m._capture([sys.executable, '-B', '-c', code], environ=m._environment(tmp_path),
        timeout=5, input_bytes=b'synthetic payload')
    assert result.actual_exit == 0 and result.bound is None
    assert result.spawned is True
    assert result.stdout == b'synthetic payload' and result.stderr == b'synthetic warning'
    assert result.stdout_sha256 == hashlib.sha256(result.stdout).hexdigest()
    assert result.stdout_observed_bytes == len(result.stdout)
    assert 'synthetic payload' not in repr(result)


@pytest.mark.parametrize('channel', ['stdout', 'stderr'])
def test_real_synthetic_noise_child_is_bounded_killed_and_reaped(tmp_path, channel):
    processes = []
    def popen(*a, **k):
        process = subprocess.Popen(*a, **k)
        processes.append(process)
        return process
    code = f'import sys,time; sys.{channel}.buffer.write(b"x"*262144); sys.{channel}.flush(); time.sleep(10)'
    result = m._capture([sys.executable, '-B', '-c', code], environ=m._environment(tmp_path),
        timeout=5, popen=popen)
    assert result.bound == channel + '_bound'
    assert len(getattr(result, channel)) == m.MAX_CHANNEL
    assert getattr(result, channel + '_observed_bytes') > m.MAX_CHANNEL
    assert result.actual_exit is not None and processes[0].poll() is not None


def test_real_synthetic_sleeping_child_is_deadline_bounded_and_reaped(tmp_path):
    result = m._capture([sys.executable, '-B', '-c', 'import time; time.sleep(10)'],
        environ=m._environment(tmp_path), timeout=0.1)
    assert result.bound == 'deadline' and result.actual_exit is not None


def test_real_native_denied_validator_uses_no_credentials_and_preserves_failure_exit(tmp_path):
    # Supply a synthetic module in memory; no operational caller is imported.
    prelude = '''import sys,types,os
package=types.ModuleType("scripts")
caller=types.ModuleType("scripts.run_arv2_r298_handoff_recovery")
state=[]
def preflight(args,deadline):
 assert "QC_USER_ID" not in os.environ and "QC_API_TOKEN" not in os.environ
 assert args.operation=="recover" and args.control_fd is None
 state.append("preflight")
def validate(raw,actual_exit,args):
 assert state==["preflight"] and raw==b"synthetic\\n\\n" and actual_exit==2
 return {"operation_completed":False,"finite":"synthetic"}
caller._preflight=preflight
caller.validate_output=validate
package.run_arv2_r298_handoff_recovery=caller
sys.modules["scripts"]=package
sys.modules["scripts.run_arv2_r298_handoff_recovery"]=caller
'''
    command = m._validator_command(args(), 2)
    code_index = command.index('-c') + 1
    command[code_index] = prelude + m.VALIDATOR_CODE
    observed = m._capture(command, environ=m._environment(tmp_path), timeout=15,
        input_bytes=b'synthetic\n\n')
    assert observed.actual_exit == 0 and observed.bound is None and observed.stderr == b''
    value = m._validated_packet(observed, 2)
    assert value == {'operation_completed': False, 'finite': 'synthetic'}


def test_real_synthetic_early_stdin_close_does_not_deadlock(tmp_path):
    result = m._capture([sys.executable, '-B', '-c', 'print("finite")'],
        environ=m._environment(tmp_path), timeout=5, input_bytes=b'x' * m.MAX_CHANNEL)
    assert result.actual_exit == 0 and result.bound is None and result.stdout == b'finite\n'


def test_child_creation_failure_retains_no_exception_or_false_exit(tmp_path):
    def popen(*a, **k):
        raise OSError('SYNTHETIC PRIVATE FAILURE')
    result = m._capture([sys.executable], environ=m._environment(tmp_path), timeout=5, popen=popen)
    assert result.actual_exit is None and result.bound == 'observer_io'
    assert result.spawned is False
    assert result.stdout == result.stderr == b''
    assert b'SYNTHETIC' not in m.canonical(result.metadata())


def test_profile_is_fresh_and_bound():
    assert m.PROFILE_SHA256 == hashlib.sha256(m.canonical(m.profile_record())).hexdigest()
    profile = m.profile_record()
    profile['max_operational_dispatches'] = 200
    assert m.profile_record()['max_operational_dispatches'] == 1


def test_main_emits_only_finite_result_and_preserves_parent_failure_exit(monkeypatch):
    result = {'finite': 'validated_failure', 'actual_parent_exit': 2}
    monkeypatch.setattr(m, 'observe', lambda namespace: (result, 2))
    output = io.BytesIO()
    monkeypatch.setattr(m.sys, 'stdout', SimpleNamespace(buffer=output))
    exit_code = m.main(['--expected-head', 'a' * 40, '--caller-sha256', 'b' * 64,
        '--observer-sha256', 'c' * 64])
    assert exit_code == 2 and output.getvalue() == m.canonical(result)
