"""Bounded external observer for the separately authorized ONE A9 recovery.

This observer reads existing inherited QC credential values only in memory and
refuses before any subprocess if they are absent. It never searches Keychain or
token files. It does not allocate the operational claim or renew spent attempts.
Once the sole operational child is dispatched, every ambiguous outcome remains
consumed/ambiguous. Only a separate native-denied child imports the operational
module to validate its captured finite output. Raw process channels never print.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import tempfile
import time


SCHEMA = 'arv2-r298-handoff-observer-v1'
ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
BRANCH = 'codex/strategy-analyst-revisions-v2'
PYTHON = Path('/Users/sheltonchen/.venvs/trading_agent-py313/bin/python')
SOURCE = ROOT / 'scripts/observe_arv2_r298_handoff_recovery.py'
CALLER = ROOT / 'scripts/run_arv2_r298_handoff_recovery.py'
TESTS = ROOT / 'tests/analyst_revisions_v2/test_r298_handoff_recovery_observer.py'
CALLER_TESTS = ROOT / 'tests/analyst_revisions_v2/test_r298_handoff_recovery.py'
MAX_CHANNEL = 128 * 1024
MAX_SOURCE = 128 * 1024
PARENT_SECONDS = 615
VALIDATOR_SECONDS = 15
GIT_SECONDS = 15
REAP_SECONDS = 5
PATH_VALUE = '/usr/bin:/bin:/usr/sbin:/sbin'
CREDENTIAL_NAMES = ('QC_USER_ID', 'QC_API_TOKEN')
FINITE = frozenset(('arguments', 'credential_handoff_absent', 'host', 'support_path',
    'git_state', 'source_pin', 'subprocess_refused', 'parent_bound', 'parent_stderr',
    'parent_exit', 'validator_bound', 'validator_stderr', 'validator_refused',
    'validator_shape', 'observer_refused'))
SANDBOX = ('(version 1)(allow default)(deny network*)'
    '(deny file-read* file-write* (subpath "' + str(ROOT / 'artifacts') + '"))'
    '(deny file-read* file-write* (subpath "/Users/sheltonchen/Library/Keychains"))'
    '(deny process-exec (literal "/usr/bin/security"))'
    '(deny file-write* (require-all (require-not (subpath "' + str(ROOT / '.pytest_cache') + '"))'
    ' (require-not (literal "/dev/null"))))')
VALIDATOR_CODE = '''import json,sys,time
from types import SimpleNamespace
try:
 from scripts import run_arv2_r298_handoff_recovery as c
 raw=sys.stdin.buffer.read(131073)
 args=SimpleNamespace(operation="recover",expected_head=sys.argv[1],caller_sha256=sys.argv[2],control_fd=None)
 actual_exit=int(sys.argv[3])
 c._preflight(args,time.monotonic()+12)
 value=c.validate_output(raw,actual_exit,args)
 if "assistant.dispatch_fence" in sys.modules: raise ValueError()
 payload={"validated":True,"actual_exit":actual_exit,"value":value}
 encoded=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("ascii")+b"\\n"
 if len(encoded)>131072: raise ValueError()
 sys.stdout.buffer.write(encoded)
except BaseException:
 sys.stdout.buffer.write(b'{"validated":false}\\n')
 raise SystemExit(2)
'''


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('ascii') + b'\n'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': str(PYTHON),
        'caller': str(CALLER), 'observer': str(SOURCE), 'parent_seconds': PARENT_SECONDS,
        'validator_seconds': VALIDATOR_SECONDS, 'git_seconds': GIT_SECONDS,
        'reap_seconds': REAP_SECONDS, 'max_channel_bytes': MAX_CHANNEL,
        'max_source_bytes': MAX_SOURCE, 'max_operational_dispatches': 1,
        'max_validator_dispatches': 1, 'credential_handoff_before_any_subprocess': True,
        'parent_seconds_scope': 'parent_capture_only_excludes_bounded_git_validator_and_reap_overhead',
        'post_parent_public_source_reauthentication': True,
        'validator_source_only_preflight_seconds': 12,
        'credential_lookup': 'inherited_existing_environment_only',
        'raw_channels_printed': False, 'output_leaf_reads': False,
        'validator_sandbox': SANDBOX, 'validator_code_sha256': sha(VALIDATOR_CODE.encode('ascii')),
        'post_spawn_outcome': 'consumed_or_ambiguous_no_retry',
        'same_user_memory_sandbox': False, 'whole_interpreter_integrity': False,
        'uninterruptible_io_or_host_suspension_bounded': False}


PROFILE_SHA256 = sha(canonical(profile_record()))


class ObserverError(RuntimeError):
    def __init__(self, code):
        super().__init__(code if type(code) is str and code in FINITE else 'observer_refused')


def require(condition, code):
    if not condition:
        raise ObserverError(code)


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


@dataclass(frozen=True, repr=False)
class Captured:
    stdout: bytes
    stderr: bytes
    actual_exit: int | None
    bound: str | None
    dispatched_at: str
    completion_observed_at: str
    stdout_observed_bytes: int
    stderr_observed_bytes: int
    stdout_sha256: str
    stderr_sha256: str
    spawned: bool = False

    def __repr__(self):
        return '<BoundedR298ProcessObservation>'

    def metadata(self):
        return {'actual_exit': self.actual_exit, 'bound': self.bound,
            'child_spawn_observed': self.spawned,
            'dispatched_at': self.dispatched_at,
            'completion_observed_at': self.completion_observed_at,
            'stdout_observed_bytes': self.stdout_observed_bytes,
            'stderr_observed_bytes': self.stderr_observed_bytes,
            'stdout_sha256': self.stdout_sha256, 'stderr_sha256': self.stderr_sha256,
            'channel_hash_scope': 'observed_bytes_not_unread_tail'}


def _capture(command, *, environ, timeout, input_bytes=None, popen=subprocess.Popen):
    """Synchronous bounded concurrent capture; injection seam is test-only.

    No detached promise/cache is used. Bytes are capped independently per channel;
    a bound stops this child's processing, not another lane's processes. Stream
    hash/count covers observed bytes only, not unread bytes after termination.
    """
    require(type(command) is list and command and all(type(item) is str for item in command)
        and type(environ) is dict and type(timeout) in (int, float) and 0 < timeout <= PARENT_SECONDS
        and (input_bytes is None or type(input_bytes) is bytes and len(input_bytes) <= MAX_CHANNEL), 'arguments')
    dispatched = _utc_now()
    deadline = time.monotonic() + timeout
    process = None
    selector = selectors.DefaultSelector()
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    counts = {'stdout': 0, 'stderr': 0}
    hashes = {name: hashlib.sha256() for name in buffers}
    bound, actual_exit, input_offset, spawned = None, None, 0, False
    try:
        process = popen(command, cwd=str(ROOT), env=environ,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
        spawned = True
        for name in buffers:
            stream = getattr(process, name)
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        if input_bytes is not None:
            os.set_blocking(process.stdin.fileno(), False)
            if input_bytes:
                selector.register(process.stdin, selectors.EVENT_WRITE, 'stdin')
            else:
                process.stdin.close()
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                bound = 'deadline'
                break
            for key, event in selector.select(min(0.1, remaining)):
                name, stream = key.data, key.fileobj
                if name == 'stdin':
                    try:
                        sent = os.write(stream.fileno(), input_bytes[input_offset:input_offset + 16384])
                    except BrokenPipeError:
                        sent = 0
                        input_offset = len(input_bytes)
                    except BlockingIOError:
                        continue
                    input_offset += sent
                    if input_offset == len(input_bytes):
                        selector.unregister(stream)
                        stream.close()
                else:
                    try:
                        chunk = os.read(stream.fileno(), 16384)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(stream)
                        stream.close()
                        continue
                    counts[name] += len(chunk)
                    hashes[name].update(chunk)
                    buffers[name].extend(chunk[:max(0, MAX_CHANNEL - len(buffers[name]))])
                    if counts[name] > MAX_CHANNEL:
                        bound = name + '_bound'
                        break
            if bound is not None:
                break
        if bound is None:
            try:
                actual_exit = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                bound = 'deadline'
    except BaseException:
        bound = 'observer_io'
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()  # Only the exact child object this call created.
                actual_exit = process.wait(timeout=REAP_SECONDS)
            except BaseException:
                bound = bound or 'reap_unknown'
                actual_exit = None
            for name in ('stdin', 'stdout', 'stderr'):
                stream = getattr(process, name, None)
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException:
                        bound = bound or 'observer_io'
        selector.close()
    return Captured(bytes(buffers['stdout']), bytes(buffers['stderr']), actual_exit,
        bound, dispatched, _utc_now(), counts['stdout'], counts['stderr'],
        hashes['stdout'].hexdigest(), hashes['stderr'].hexdigest(), spawned)


def _credential_handoff(environ):
    # No formatting, lengths, values or account identifiers enter a failure.
    values = tuple(environ.get(name) for name in CREDENTIAL_NAMES)
    require(all(type(value) is str and bool(value.strip()) for value in values),
        'credential_handoff_absent')
    return dict(zip(CREDENTIAL_NAMES, values))


def _environment(support, credentials=None):
    require(type(support) is type(ROOT) and support.is_relative_to(ROOT / '.pytest_cache')
        and support != ROOT / '.pytest_cache' and support.resolve() == support, 'support_path')
    result = {'PATH': PATH_VALUE, 'LANG': 'en_US.UTF-8', 'LC_ALL': 'en_US.UTF-8',
        'TMPDIR': str(support), 'TMP': str(support), 'TEMP': str(support),
        'XDG_CACHE_HOME': str(support), 'PYTHONPYCACHEPREFIX': str(support / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1'}
    if credentials is not None:
        require(type(credentials) is dict and set(credentials) == set(CREDENTIAL_NAMES), 'credential_handoff_absent')
        result.update(credentials)
    return result


def _arguments(args):
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and type(args.caller_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.caller_sha256)
        and type(args.observer_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.observer_sha256), 'arguments')


def _git(arguments, environment):
    observed = _capture(['/usr/bin/git', *arguments], environ=environment, timeout=GIT_SECONDS)
    require(observed.bound is None and observed.actual_exit == 0 and not observed.stderr, 'git_state')
    return observed.stdout


def _source_bytes(path):
    require(path.is_relative_to(ROOT) and path.resolve() == path, 'source_pin')
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_SOURCE
            and before.st_nlink == 1, 'source_pin')
        raw = bytearray()
        while len(raw) <= MAX_SOURCE:
            chunk = os.read(fd, min(16384, MAX_SOURCE + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(fd)
        named = os.stat(path, follow_symlinks=False)
        fields = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        require(len(raw) == before.st_size and all(getattr(before, field) == getattr(after, field)
            == getattr(named, field) for field in fields), 'source_pin')
        return bytes(raw)
    except ObserverError:
        raise
    except BaseException:
        raise ObserverError('source_pin') from None
    finally:
        if fd is not None:
            os.close(fd)


def _preflight(args, environment):
    _arguments(args)
    require(sys.platform == 'darwin' and os.name == 'posix'
        and sys.version_info[:2] == (3, 13) and Path(sys.executable).absolute() == PYTHON
        and Path.cwd() == ROOT and Path(__file__).absolute() == SOURCE
        and ROOT.resolve() == ROOT, 'host')
    require(_git(['rev-parse', '--show-toplevel'], environment) == (str(ROOT) + '\n').encode()
        and _git(['branch', '--show-current'], environment) == (BRANCH + '\n').encode()
        and _git(['rev-parse', 'HEAD'], environment) == (args.expected_head + '\n').encode()
        and _git(['status', '--porcelain', '--untracked-files=normal'], environment) == b'', 'git_state')
    for path, expected in ((SOURCE, args.observer_sha256), (CALLER, args.caller_sha256),
            (TESTS, None), (CALLER_TESTS, None)):
        raw = _source_bytes(path)
        require(expected is None or sha(raw) == expected, 'source_pin')
        relative = str(path.relative_to(ROOT))
        require(_git(['show', args.expected_head + ':' + relative], environment) == raw, 'source_pin')
    require(_git(['rev-parse', 'HEAD'], environment) == (args.expected_head + '\n').encode()
        and _git(['status', '--porcelain', '--untracked-files=normal'], environment) == b'', 'git_state')


def _validator_command(args, actual_exit):
    return ['/usr/bin/sandbox-exec', '-p', SANDBOX, str(PYTHON), '-B', '-c',
        VALIDATOR_CODE, args.expected_head, args.caller_sha256, str(actual_exit)]


def _validated_packet(observed, actual_exit):
    require(observed.bound is None, 'validator_bound')
    require(not observed.stderr, 'validator_stderr')
    require(observed.actual_exit == 0, 'validator_refused')
    try:
        value = json.loads(observed.stdout.decode('ascii'))
        require(type(value) is dict and set(value) == {'validated', 'actual_exit', 'value'}
            and value['validated'] is True and type(value['actual_exit']) is int
            and value['actual_exit'] == actual_exit and type(value['value']) is dict
            and canonical(value) == observed.stdout, 'validator_shape')
    except ObserverError:
        raise
    except BaseException:
        raise ObserverError('validator_shape') from None
    return value['value']


def observe(args, *, environ=None):
    """Synchronously dispatch at most one parent and at most one validator.

    Reinvoking this function is not retry authority: the committed caller's
    exclusive operational claim remains authoritative. The observer's pre-spawn
    credential check avoids falsely consuming a claim on a known empty handoff.
    """
    result = {'schema': SCHEMA, 'profile_sha256': PROFILE_SHA256,
        'source_binding': None,
        'operational_child_dispatch_attempted': False, 'validator_dispatched': False,
        'attempt_consumption': 'no_child_dispatched', 'parent': None, 'validator': None,
        'output_validated': False, 'validated_output': None, 'failure_code': None}
    credentials = child_environment = None
    try:
        credentials = _credential_handoff(os.environ if environ is None else environ)
        _arguments(args)
        result['source_binding'] = {'expected_head': args.expected_head,
            'caller_sha256': args.caller_sha256, 'observer_sha256': args.observer_sha256}
        require(ROOT.resolve() == ROOT and (ROOT / '.pytest_cache').resolve() == ROOT / '.pytest_cache', 'support_path')
        support = Path(tempfile.mkdtemp(prefix='a9-observer-', dir=ROOT / '.pytest_cache'))
        safe_environment = _environment(support)
        _preflight(args, safe_environment)
        child_environment = _environment(support, credentials)
        result['operational_child_dispatch_attempted'] = True
        result['attempt_consumption'] = 'consumed_or_ambiguous_no_retry'
        observed = _capture([str(PYTHON), '-B', str(CALLER), 'recover', '--expected-head',
            args.expected_head, '--caller-sha256', args.caller_sha256],
            environ=child_environment, timeout=PARENT_SECONDS)
        result['parent'] = observed.metadata()
        child_environment.clear()
        credentials.clear()
        require(observed.bound is None, 'parent_bound')
        require(not observed.stderr, 'parent_stderr')
        require(type(observed.actual_exit) is int and observed.actual_exit in (0, 2), 'parent_exit')
        _preflight(args, safe_environment)
        result['validator_dispatched'] = True
        validated = _capture(_validator_command(args, observed.actual_exit),
            environ=safe_environment, timeout=VALIDATOR_SECONDS, input_bytes=observed.stdout)
        result['validator'] = validated.metadata()
        result['validated_output'] = _validated_packet(validated, observed.actual_exit)
        result['output_validated'] = True
        return result, 0 if observed.actual_exit == 0 else 2
    except BaseException as error:
        code = 'observer_refused'
        if type(error) is ObserverError:
            args_tuple = BaseException.args.__get__(error)
            if len(args_tuple) == 1 and type(args_tuple[0]) is str and args_tuple[0] in FINITE:
                code = args_tuple[0]
        result['failure_code'] = code
        return result, 2
    finally:
        if type(child_environment) is dict:
            child_environment.clear()
        if type(credentials) is dict:
            credentials.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--observer-sha256', required=True)
    args = parser.parse_args(argv)
    result, exit_code = observe(args)
    sys.stdout.buffer.write(canonical(result))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
