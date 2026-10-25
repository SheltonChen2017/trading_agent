"""Finite synthetic R321 capture tests; require native network/private denial."""
import io
from types import SimpleNamespace

import pytest

from scripts import run_arv2_r298_access_mismatch_observation as m


def args():
    return SimpleNamespace(expected_head='a' * 40, caller_sha256='b' * 64,
        runner_sha256='c' * 64)


def credentials():
    return {'QC_USER_ID': 'SYNTHETIC-USER', 'QC_API_TOKEN': 'SYNTHETIC-PRIVATE-TOKEN',
        'UNSAFE_EXTRA': 'SYNTHETIC-OTHER-SECRET', 'PYTHONPATH': '/unsafe'}


def captured(stdout=b'', stderr=b'', actual_exit=0, bound=None):
    return m.Captured(stdout, stderr, actual_exit, bound, '2026-10-25T00:00:00Z',
        '2026-10-25T00:00:01Z', len(stdout), len(stderr), m.sha(stdout), m.sha(stderr))


def validated(actual_exit=0):
    return {'validated': True, 'actual_exit': actual_exit,
        'value': {'observation_completed': actual_exit == 0, 'finite': 'synthetic'}}


@pytest.fixture
def fake_preflight(monkeypatch):
    calls = []
    monkeypatch.setattr(m, '_preflight', lambda a, e: calls.append((a, e.copy())))
    return calls


@pytest.mark.parametrize('environment', [{}, {'QC_USER_ID': 'x'}, {'QC_API_TOKEN': 'x'},
    {'QC_USER_ID': '', 'QC_API_TOKEN': 'x'}, {'QC_USER_ID': ' ', 'QC_API_TOKEN': 'x'},
    {'QC_USER_ID': 'x', 'QC_API_TOKEN': '\n\t'}, {'QC_USER_ID': None, 'QC_API_TOKEN': 'x'},
    {'QC_USER_ID': 2, 'QC_API_TOKEN': 'x'}])
def test_missing_credentials_never_allocate_or_dispatch(monkeypatch, environment):
    monkeypatch.setattr(m, '_capture', lambda *a, **k: pytest.fail('child dispatched'))
    monkeypatch.setattr(m.tempfile, 'mkdtemp', lambda *a, **k: pytest.fail('support allocated'))
    result, code = m.observe(args(), environ=environment)
    assert code == 2 and result['failure_code'] == 'credential_handoff_absent'
    assert result['observation_consumption'] == 'no_child_dispatched'
    assert not result['observation_child_dispatch_attempted'] and not result['validator_dispatched']


@pytest.mark.parametrize('actual_exit', [0, 2])
def test_single_readonly_child_then_credential_free_validator(monkeypatch, fake_preflight, actual_exit):
    calls = []
    raw = b'SYNTHETIC RAW CHANNEL NEVER PRINTED\n'
    def capture(command, **kwargs):
        calls.append((command.copy(), {**kwargs, 'environ': kwargs['environ'].copy()}))
        return captured(raw, actual_exit=actual_exit) if len(calls) == 1 else captured(m.canonical(validated(actual_exit)))
    monkeypatch.setattr(m, '_capture', capture)
    original = credentials()
    result, code = m.observe(args(), environ=original)
    assert code == actual_exit and result['output_validated']
    assert result['validated_output'] == validated(actual_exit)['value']
    assert result['source_binding'] == vars(args())
    assert result['observation_consumption'] == 'consumed_or_ambiguous_no_retry'
    assert len(calls) == len(fake_preflight) == 2
    command, parent = calls[0]
    validator_command, validator = calls[1]
    assert command == [str(m.PYTHON), '-B', str(m.CALLER), '--expected-head',
        'a' * 40, '--caller-sha256', 'b' * 64]
    assert parent['timeout'] == 75 and parent['environ']['QC_API_TOKEN'] == credentials()['QC_API_TOKEN']
    assert 'UNSAFE_EXTRA' not in parent['environ'] and 'PYTHONPATH' not in parent['environ']
    assert validator_command == m._validator_command(args(), actual_exit)
    assert validator['timeout'] == 15 and validator['input_bytes'] == raw
    assert not set(m.CREDENTIAL_NAMES) & set(validator['environ'])
    assert all(not set(m.CREDENTIAL_NAMES) & set(environment) for _, environment in fake_preflight)
    assert original == credentials()
    assert all(word not in m.canonical(result) for word in (raw, b'PRIVATE-TOKEN', b'SYNTHETIC-USER', b'OTHER-SECRET'))


@pytest.mark.parametrize('parent,reason', [
    (captured(b'raw', actual_exit=-9, bound='deadline'), 'parent_bound'),
    (captured(b'raw', actual_exit=-9, bound='stdout_bound'), 'parent_bound'),
    (captured(b'raw', stderr=b'SYNTHETIC-SECRET'), 'parent_stderr'),
    (captured(b'raw', actual_exit=1), 'parent_exit'),
    (captured(b'raw', actual_exit=None), 'parent_exit'),
    (captured(b'raw', actual_exit=True), 'parent_exit')])
def test_parent_failure_is_terminal_without_validator(monkeypatch, fake_preflight, parent, reason):
    calls = []
    monkeypatch.setattr(m, '_capture', lambda *a, **k: calls.append(1) or parent)
    result, code = m.observe(args(), environ=credentials())
    assert code == 2 and result['failure_code'] == reason and len(calls) == 1
    assert result['observation_consumption'] == 'consumed_or_ambiguous_no_retry'
    assert not result['validator_dispatched'] and result['validated_output'] is None
    assert b'SYNTHETIC-SECRET' not in m.canonical(result)


@pytest.mark.parametrize('validator,reason', [
    (captured(b'SYNTHETIC-SECRET', actual_exit=-9, bound='deadline'), 'validator_bound'),
    (captured(b'SYNTHETIC-SECRET', stderr=b'SYNTHETIC-SECRET'), 'validator_stderr'),
    (captured(b'SYNTHETIC-SECRET', actual_exit=2), 'validator_refused'),
    (captured(b'SYNTHETIC-SECRET'), 'validator_shape'),
    (captured(m.canonical({'validated': False})), 'validator_shape'),
    (captured(m.canonical(validated(2))), 'validator_shape'),
    (captured(m.canonical(validated()) + b'trailing'), 'validator_shape')])
def test_validator_failure_never_retries_or_prints_raw(monkeypatch, fake_preflight, validator, reason):
    calls = []
    monkeypatch.setattr(m, '_capture', lambda *a, **k: calls.append(1) or (captured(b'parent') if len(calls) == 1 else validator))
    result, code = m.observe(args(), environ=credentials())
    assert code == 2 and result['failure_code'] == reason and len(calls) == 2
    assert not result['output_validated'] and result['validated_output'] is None
    assert b'SYNTHETIC-SECRET' not in m.canonical(result)


@pytest.mark.parametrize('field,value', [('expected_head', 'bad'), ('expected_head', True),
    ('caller_sha256', 'BAD'), ('runner_sha256', 'x' * 64)])
def test_invalid_source_binding_stops_before_support_or_subprocess(monkeypatch, field, value):
    namespace = args()
    setattr(namespace, field, value)
    monkeypatch.setattr(m, '_capture', lambda *a, **k: pytest.fail('subprocess'))
    monkeypatch.setattr(m.tempfile, 'mkdtemp', lambda *a, **k: pytest.fail('support'))
    result, code = m.observe(namespace, environ=credentials())
    assert code == 2 and result['failure_code'] == 'arguments'
    assert result['observation_consumption'] == 'no_child_dispatched'


def test_post_parent_change_refuses_before_validator(monkeypatch):
    events = []
    def preflight(a, e):
        events.append('preflight')
        if len(events) == 3:
            raise m.ObserverError('git_state')
    def capture(*a, **k):
        events.append('parent')
        return captured(b'private raw')
    monkeypatch.setattr(m, '_preflight', preflight)
    monkeypatch.setattr(m, '_capture', capture)
    result, code = m.observe(args(), environ=credentials())
    assert events == ['preflight', 'parent', 'preflight']
    assert code == 2 and result['failure_code'] == 'git_state'
    assert not result['validator_dispatched'] and not result['output_validated']
    assert result['parent']['stdout_sha256'] == m.sha(b'private raw')
    assert b'private raw' not in m.canonical(result)


def test_exception_is_finite_and_child_environment_cleared(monkeypatch, fake_preflight):
    environments = []
    def capture(*a, **kwargs):
        environments.append(kwargs['environ'])
        raise RuntimeError('PRIVATE-EXCEPTION')
    monkeypatch.setattr(m, '_capture', capture)
    result, code = m.observe(args(), environ=credentials())
    assert code == 2 and result['failure_code'] == 'observer_refused'
    assert environments == [{}] and b'PRIVATE-EXCEPTION' not in m.canonical(result)


def public_fixture(monkeypatch):
    namespace = args()
    paths = (m.SOURCE, m.CALLER, m.HELPER, m.TESTS, m.CALLER_TESTS)
    sources = {str(path.relative_to(m.ROOT)): ('synthetic-' + str(n)).encode()
        for n, path in enumerate(paths)}
    namespace.runner_sha256 = m.sha(sources[str(m.SOURCE.relative_to(m.ROOT))])
    namespace.caller_sha256 = m.sha(sources[str(m.CALLER.relative_to(m.ROOT))])
    monkeypatch.setattr(m, 'HELPER_SHA256', m.sha(sources[str(m.HELPER.relative_to(m.ROOT))]))
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
        pytest.fail('unexpected git')
    monkeypatch.setattr(m, '_git', git)
    return namespace, commands, git


def test_preflight_exact_clean_head_five_committed_sources_and_hard_helper_pin(monkeypatch, tmp_path):
    namespace, commands, git = public_fixture(monkeypatch)
    m._preflight(namespace, m._environment(tmp_path))
    assert len([command for command in commands if command[0] == 'show']) == 5
    assert commands[-2:] == [['rev-parse', 'HEAD'], ['status', '--porcelain', '--untracked-files=normal']]


@pytest.mark.parametrize('field,value', [('platform', 'linux'), ('version_info', (3, 12)),
    ('executable', '/usr/bin/python3')])
def test_incompatible_host_refuses_before_git(monkeypatch, tmp_path, field, value):
    monkeypatch.setattr(m.sys, field, value)
    monkeypatch.setattr(m, '_git', lambda *a: pytest.fail('git before host acceptance'))
    with pytest.raises(m.ObserverError, match='^host$'):
        m._preflight(args(), m._environment(tmp_path))


@pytest.mark.parametrize('target', ['root', 'branch', 'head', 'status', 'blob'])
def test_public_state_mismatch_refuses(monkeypatch, tmp_path, target):
    namespace, commands, original = public_fixture(monkeypatch)
    def git(command, environment):
        bad = ((target == 'root' and command == ['rev-parse', '--show-toplevel'])
            or (target == 'branch' and command == ['branch', '--show-current'])
            or (target == 'head' and command == ['rev-parse', 'HEAD'])
            or (target == 'status' and command[0] == 'status')
            or (target == 'blob' and command[0] == 'show'))
        return b'mismatch\n' if bad else original(command, environment)
    monkeypatch.setattr(m, '_git', git)
    with pytest.raises(m.ObserverError):
        m._preflight(namespace, m._environment(tmp_path))


@pytest.mark.parametrize('target', ['runner_sha256', 'caller_sha256', 'helper'])
def test_explicit_pin_mismatch_refuses_matching_git_blob(monkeypatch, tmp_path, target):
    namespace, commands, original = public_fixture(monkeypatch)
    if target == 'helper':
        monkeypatch.setattr(m, 'HELPER_SHA256', '0' * 64)
    else:
        setattr(namespace, target, '0' * 64)
    with pytest.raises(m.ObserverError, match='^source_pin$'):
        m._preflight(namespace, m._environment(tmp_path))


def test_last_clean_head_check_detects_concurrency(monkeypatch, tmp_path):
    namespace, commands, original = public_fixture(monkeypatch)
    seen = []
    def git(command, environment):
        if command == ['rev-parse', 'HEAD']:
            seen.append(1)
            if len(seen) == 2:
                return b'0' * 40 + b'\n'
        return original(command, environment)
    monkeypatch.setattr(m, '_git', git)
    with pytest.raises(m.ObserverError, match='^git_state$'):
        m._preflight(namespace, m._environment(tmp_path))


def test_validator_has_native_denial_source_preflight_and_no_operation():
    command = m._validator_command(args(), 2)
    assert command[:3] == ['/usr/bin/sandbox-exec', '-p', m.SANDBOX]
    for token in ('(deny network*)', str(m.ROOT / 'artifacts'), '/Library/Keychains', '/usr/bin/security'):
        assert token in m.SANDBOX
    assert m.VALIDATOR_CODE.index('c._preflight(args,time.monotonic()+12)') < m.VALIDATOR_CODE.index('c.validate_output(raw,actual_exit,args)')
    assert 'c.run(' not in m.VALIDATOR_CODE and 'c.main(' not in m.VALIDATOR_CODE
    assert 'raw=sys.stdin.buffer.read(131073)' in m.VALIDATOR_CODE


def test_real_native_validator_uses_only_synthetic_module_and_preserves_exit(tmp_path):
    prelude = '''import sys,types,os
package=types.ModuleType("scripts")
caller=types.ModuleType("scripts.observe_arv2_r298_access_mismatch")
state=[]
def preflight(args,deadline):
 assert "QC_USER_ID" not in os.environ and "QC_API_TOKEN" not in os.environ
 assert set(vars(args))=={"expected_head","caller_sha256"}
 state.append("preflight")
def validate(raw,actual_exit,args):
 assert state==["preflight"] and raw==b"synthetic\\n" and actual_exit==2
 return {"observation_completed":False,"finite":"synthetic"}
caller._preflight=preflight
caller.validate_output=validate
package.observe_arv2_r298_access_mismatch=caller
sys.modules["scripts"]=package
sys.modules["scripts.observe_arv2_r298_access_mismatch"]=caller
'''
    command = m._validator_command(args(), 2)
    command[command.index('-c') + 1] = prelude + m.VALIDATOR_CODE
    observed = m._capture(command, environ=m._environment(tmp_path), timeout=15,
        input_bytes=b'synthetic\n')
    assert observed.actual_exit == 0 and observed.bound is None and observed.stderr == b''
    assert m._validated_packet(observed, 2) == {'observation_completed': False, 'finite': 'synthetic'}


def test_reused_capture_is_frozen_low_level_only_and_profile_bound():
    assert m.HELPER_SHA256 == 'cfba31c04d5ff10f33779f1c497cefa3885d63b737f7c260bd9b41a27db6f55f'
    assert m._capture is m.capture._capture and m._validated_packet is m.capture._validated_packet
    assert m.PROFILE_SHA256 == m.sha(m.canonical(m.profile_record()))
    assert m.profile_record()['max_observation_dispatches'] == 1
    assert m.profile_record()['upload_permission_compile_launch_allowed'] is False


def test_no_historical_entrypoint_or_preflight_is_reused(monkeypatch, fake_preflight):
    def forbidden(*a, **k):
        pytest.fail('historical operational entrypoint or preflight called')
    for name in ('observe', 'main', '_preflight'):
        monkeypatch.setattr(m.capture, name, forbidden)
    calls = []
    monkeypatch.setattr(m, '_capture', lambda *a, **k: calls.append(1) or
        (captured(b'parent') if len(calls) == 1 else captured(m.canonical(validated()))))
    result, code = m.observe(args(), environ=credentials())
    assert code == 0 and result['output_validated'] and len(calls) == 2


def test_real_cli_help_under_minimal_credential_free_environment(tmp_path):
    observed = m._capture([str(m.PYTHON), '-B', str(m.SOURCE), '--help'],
        environ=m._environment(tmp_path), timeout=5)
    assert observed.actual_exit == 0 and observed.bound is None and observed.stderr == b''
    assert b'--runner-sha256' in observed.stdout and b'--caller-sha256' in observed.stdout


def test_main_only_prints_finite_packet(monkeypatch):
    packet = {'finite': 'safe', 'actual_parent_exit': 2}
    monkeypatch.setattr(m, 'observe', lambda args: (packet, 2))
    output = io.BytesIO()
    monkeypatch.setattr(m.sys, 'stdout', SimpleNamespace(buffer=output))
    code = m.main(['--expected-head', 'a' * 40, '--caller-sha256', 'b' * 64,
        '--runner-sha256', 'c' * 64])
    assert code == 2 and output.getvalue() == m.canonical(packet)
