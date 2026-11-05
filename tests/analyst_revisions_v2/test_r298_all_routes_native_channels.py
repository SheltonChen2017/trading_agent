"""Real native-denied tiny children; only synthetic in-cache descriptors.

These tests exercise transport and inherited-control mechanics. They never
invoke a production preflight, source reader, provider caller or join worker.
Darwin refuses nested sandbox_apply, so their native harness must compile the
actual worker policy outside pytest, add all-artifact denial, and bind its
SHA256 in ARV2_NATIVE_WORKER_PROFILE_SHA256. Tiny children inherit that policy.
"""
import errno
import json
import os
import signal
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import prepare_arv2_r298_all_routes as m


NONCE = 'synthetic-native-channel-nonce'
BINDING = {'schema': 'synthetic-native-control-only', 'nonce': NONCE}
INPUT = b'synthetic-channel-input\n'
NATIVE = sys.platform == 'darwin' and os.name == 'posix'
pytestmark = pytest.mark.skipif(not NATIVE, reason='Darwin sandbox-exec/POSIX descriptor test')


@pytest.fixture(autouse=True)
def no_operational_calls(monkeypatch):
    assert os.environ.get('ARV2_NATIVE_WORKER_PROFILE_SHA256') == m.sha(
        m.native_profile(worker_mode=True).encode('utf-8')), 'actual worker native-policy harness required'
    def deny(*args, **kwargs):
        raise AssertionError('production operation forbidden in synthetic native-channel test')
    monkeypatch.setattr(m, 'preflight', deny)
    monkeypatch.setattr(m, 'run', deny)
    monkeypatch.setattr(m, 'observe', deny)
    monkeypatch.setattr(m.worker, 'prepare', deny)
    monkeypatch.setattr(m.worker, '_load_plain', deny)
    monkeypatch.setattr(m.keychain, 'load_key', deny)
    monkeypatch.setattr(m.previous, 'run', deny)
    monkeypatch.setattr(m.previous, 'observe', deny)


@pytest.fixture
def synthetic_controls(tmp_path):
    assert tmp_path.is_relative_to(m.ROOT / '.pytest_cache') and tmp_path.resolve() == tmp_path
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    descriptors = []
    try:
        for name, value in (
            ('claim.json', {**BINDING, 'local_only': True, 'old_controls_spent': True}),
            ('join-start.json', {**BINDING, 'stage': 'native-all-binding-join'}),
        ):
            fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                dir_fd=directory)
            descriptors.append(fd)
            raw = m.canonical(value)
            assert os.write(fd, raw) == len(raw)
            os.fsync(fd)
            os.fchmod(fd, 0o600)
        os.fsync(directory)
        yield NS(path=tmp_path, directory=directory, claim=descriptors[0], marker=descriptors[1],
            fds=tuple((*descriptors, directory)))
    finally:
        for fd in (*descriptors, directory):
            os.close(fd)


def child_environment(path):
    assert path.is_relative_to(m.ROOT / '.pytest_cache') and path.resolve() == path
    value = m.capture_support._environment(path)
    value['PYTHONNOUSERSITE'] = '1'
    assert not any('KEY' in name or 'TOKEN' in name or 'SECRET' in name for name in value)
    return value


def native_command(code, *arguments):
    # The outer native harness compiles actual worker policy plus stronger
    # all-artifact denial. Every child inherits it; no nested sandbox_apply.
    # Cache-only CONTROL bindings are supplied inside the synthetic child.
    return [str(m.PYTHON), '-B', '-c', code, *(str(value) for value in arguments)]


INHERITED_CHILD = r'''
import errno,json,os,socket,sys,time
from pathlib import Path
from types import SimpleNamespace as NS
from scripts import prepare_arv2_r298_all_routes as m
nonce = 'synthetic-native-channel-nonce'
binding = {'schema': 'synthetic-native-control-only', 'nonce': nonce}
m.CONTROL = Path(sys.argv[1])
m.binding = lambda args: dict(binding)
def denied(*args, **kwargs): raise AssertionError('production operation forbidden')
for name in ('preflight', 'run', 'observe', 'run_worker'):
    setattr(m, name, denied)
m.worker.prepare = denied
m.worker._load_plain = denied
m.keychain.load_key = denied
args = NS(claim_fd=int(sys.argv[2]), marker_fd=int(sys.argv[3]), directory_fd=int(sys.argv[4]))
try:
    m._inherited(args, time.monotonic() + 20)
    raw = sys.stdin.buffer.read(33)
    assert raw == b'synthetic-channel-input\n'
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as network:
        network.settimeout(0.2)
        try:
            network.connect(('203.0.113.1', 443))
        except OSError as error:
            assert error.errno in (errno.EPERM, errno.EACCES)
            denied_errno = error.errno
        else:
            raise AssertionError('native network denial absent')
    m._inherited(args, time.monotonic() + 20)
    output = {'nonce': nonce, 'stdin_sha256': m.sha(raw), 'network_denied_errno': denied_errno,
        'fds': [args.claim_fd, args.marker_fd, args.directory_fd],
        'inheritable': [os.get_inheritable(fd) for fd in (args.claim_fd,args.marker_fd,args.directory_fd)],
        'metadata': [list(m.metadata(os.fstat(fd))) for fd in
            (args.claim_fd,args.marker_fd,args.directory_fd)]}
except m.Refused as error:
    sys.stdout.buffer.write(m.canonical({'nonce': nonce, 'refused': m.finite(error)}))
    raise SystemExit(2)
sys.stdout.buffer.write(m.canonical(output))
'''


def run_inherited(controls, *, claim=None, marker=None, directory=None):
    selected = (controls.claim if claim is None else claim,
        controls.marker if marker is None else marker,
        controls.directory if directory is None else directory)
    passed = tuple(dict.fromkeys(selected))
    return m.capture(native_command(INHERITED_CHILD, controls.path, *selected),
        child_environment(controls.path), 30, input_bytes=INPUT, stdout_limit=4096, pass_fds=passed)


def test_actual_native_policy_tiny_child_inherits_exact_three_full_metadata_controls_and_denies_network(
        synthetic_controls):
    controls = synthetic_controls
    before = [list(m.metadata(os.fstat(fd))) for fd in controls.fds]
    output, errors, actual = run_inherited(controls)
    assert errors == b'' and actual['actual_exit'] == 0 and actual['bound'] is None
    assert actual['spawn_observed'] is True and actual['stdout_bytes'] == len(output)
    assert actual['stdout_sha256'] == m.sha(output) and actual['stderr_bytes'] == 0
    assert actual['stderr_sha256'] == m.sha(b'')
    value = json.loads(output)
    assert value == {'nonce': NONCE, 'stdin_sha256': m.sha(INPUT),
        'network_denied_errno': value['network_denied_errno'], 'fds': list(controls.fds),
        'inheritable': [True, True, True], 'metadata': before}
    assert value['network_denied_errno'] in (errno.EPERM, errno.EACCES)
    assert [list(m.metadata(os.fstat(fd))) for fd in controls.fds] == before
    assert 'assistant.dispatch_fence' not in sys.modules


@pytest.mark.parametrize('change', ['tampered_marker', 'tampered_claim', 'wrong_mode',
    'replaced_marker', 'duplicate_fd', 'wrong_directory'])
def test_real_child_refuses_changed_synthetic_named_control_or_descriptor(synthetic_controls, change):
    controls = synthetic_controls
    extra_fd = None
    kwargs = {}
    try:
        if change in ('tampered_marker', 'tampered_claim'):
            fd = controls.marker if change == 'tampered_marker' else controls.claim
            os.lseek(fd, 0, os.SEEK_SET)
            # Same length, altered content: payload identity must also bind.
            assert os.write(fd, b'{"s') == 3
            os.fsync(fd)
        elif change == 'wrong_mode':
            os.fchmod(controls.marker, 0o644)
        elif change == 'replaced_marker':
            old = controls.path / 'join-start.json'
            os.rename(old, controls.path / 'synthetic-retained-marker.json')
            extra_fd = os.open(old, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.write(extra_fd, m.canonical({**BINDING, 'stage': 'native-all-binding-join'}))
            os.fsync(extra_fd)
        elif change == 'duplicate_fd':
            kwargs['marker'] = controls.claim
        else:
            other = controls.path / 'synthetic-other-directory'
            other.mkdir(mode=0o700)
            extra_fd = os.open(other, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            kwargs['directory'] = extra_fd
        output, errors, actual = run_inherited(controls, **kwargs)
        assert errors == b'' and actual['actual_exit'] == 2 and actual['bound'] is None
        assert actual['stdout_bytes'] == len(output) and actual['stdout_sha256'] == m.sha(output)
        assert json.loads(output) == {'nonce': NONCE, 'refused': 'worker_binding'}
    finally:
        if extra_fd is not None:
            os.close(extra_fd)


def assert_own_child_killed_and_reaped(output, actual, bound):
    first, separator, _ = output.partition(b'\n')
    assert separator and first.startswith(b'PID:')
    pid = int(first.removeprefix(b'PID:'))
    assert pid > 1 and pid != os.getpid()
    assert actual['spawn_observed'] is True and actual['bound'] == bound
    assert actual['actual_exit'] == -signal.SIGKILL
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.parametrize('channel', ['stdout', 'stderr'])
def test_real_noisy_child_is_channel_bounded_killed_and_reaped(tmp_path, channel):
    descriptor = 1 if channel == 'stdout' else 2
    code = ('import os\nos.write(1, ("PID:"+str(os.getpid())+"\\n").encode())\n'
        'while True: os.write(' + str(descriptor) + ', b"synthetic-noise" * 2048)\n')
    output, errors, actual = m.capture(native_command(code), child_environment(tmp_path),
        10, stdout_limit=128)
    assert_own_child_killed_and_reaped(output, actual, 'channel_bound')
    assert len(output) <= 128 + 16384 and len(errors) <= 4096 + 16384
    assert actual['stdout_bytes'] == len(output) and actual['stdout_sha256'] == m.sha(output)
    assert actual['stderr_bytes'] == len(errors) and actual['stderr_sha256'] == m.sha(errors)
    assert (len(output) > 128) if channel == 'stdout' else (len(errors) > 4096)


def test_real_slow_child_is_deadline_killed_and_reaped(tmp_path):
    code = ('import os,time\nos.write(1, ("PID:"+str(os.getpid())+"\\n").encode())\n'
        'time.sleep(60)\n')
    started = time.monotonic()
    output, errors, actual = m.capture(native_command(code), child_environment(tmp_path),
        1, input_bytes=b'', stdout_limit=128)
    elapsed = time.monotonic() - started
    assert_own_child_killed_and_reaped(output, actual, 'deadline')
    assert errors == b'' and 0.5 <= elapsed <= 8
    assert actual['stdout_bytes'] == len(output) and actual['stdout_sha256'] == m.sha(output)
