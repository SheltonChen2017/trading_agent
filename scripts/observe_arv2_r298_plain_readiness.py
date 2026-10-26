"""One bounded external A11 capture and one native-denied output validator.

Only the fixed readiness caller may run. Credentials are inherited in memory,
never looked up or copied from arbitrary environment settings. Raw stdout and
stderr never print: only separately validated finite output and channel hashes
are returned. A failed or ambiguous dispatch never renews the A11 attempt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import tempfile
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import observe_arv2_r298_handoff_recovery as support

SCHEMA = 'arv2-r298-plain-readiness-observer-v1'
BRANCH = 'codex/strategy-analyst-revisions-v2'
PYTHON = Path('/Users/sheltonchen/.venvs/trading_agent-py313/bin/python')
SOURCE = ROOT / 'scripts/observe_arv2_r298_plain_readiness.py'
CALLER = ROOT / 'scripts/run_arv2_r298_plain_readiness.py'
CALLER_SHA256 = 'ec7f08b6483dcac360f1cffdaa54c956f9b734543ab6f7a7579c84b7253d94e3'
HELPER = ROOT / 'scripts/observe_arv2_r298_handoff_recovery.py'
HELPER_SHA256 = 'cfba31c04d5ff10f33779f1c497cefa3885d63b737f7c260bd9b41a27db6f55f'
TESTS = (ROOT / 'tests/analyst_revisions_v2/test_r298_plain_readiness_observer.py',
    ROOT / 'tests/analyst_revisions_v2/test_r298_plain_readiness_caller.py',
    ROOT / 'tests/analyst_revisions_v2/test_r298_plain_readiness_channels.py')
PARENT_SECONDS, VALIDATOR_SECONDS, GIT_SECONDS, REAP_SECONDS = 930, 15, 15, 5
MAX_STDOUT, MAX_STDERR, MAX_VALIDATOR, MAX_OUTPUT = 128 * 1024, 4096, 132 * 1024, 144 * 1024
SANDBOX = support.SANDBOX + '(deny file-read* file-write* (subpath "/Library/Keychains"))'
FINITE, ObserverError, Captured = support.FINITE, support.ObserverError, support.Captured
canonical, sha, require = support.canonical, support.sha, support.require
_credential_handoff, _environment, _source_bytes = support._credential_handoff, support._environment, support._source_bytes

VALIDATOR_CODE = '''import json,sys,time
from types import SimpleNamespace
try:
 from scripts import run_arv2_r298_plain_readiness as c
 raw=sys.stdin.buffer.read(131073)
 args=SimpleNamespace(operation="recover",expected_head=sys.argv[1],caller_sha256=sys.argv[2],control_fd=None,deadline=None)
 actual_exit=int(sys.argv[3])
 c._preflight(args,time.monotonic()+12)
 value=c.validate_output(raw,actual_exit,args)
 if "assistant.dispatch_fence" in sys.modules: raise ValueError()
 payload={"validated":True,"actual_exit":actual_exit,"value":value}
 encoded=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("ascii")+b"\\n"
 if len(encoded)>135168: raise ValueError()
 sys.stdout.buffer.write(encoded)
except BaseException:
 sys.stdout.buffer.write(b'{"validated":false}\\n')
 raise SystemExit(2)
'''


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': str(PYTHON),
        'caller': str(CALLER), 'caller_sha256': CALLER_SHA256, 'observer': str(SOURCE),
        'helper': str(HELPER), 'helper_sha256': HELPER_SHA256,
        'parent_seconds': PARENT_SECONDS, 'validator_seconds': VALIDATOR_SECONDS,
        'git_seconds': GIT_SECONDS, 'reap_seconds': REAP_SECONDS,
        'max_parent_stdout': MAX_STDOUT, 'max_stderr': MAX_STDERR, 'max_validator_stdout': MAX_VALIDATOR,
        'max_observer_output': MAX_OUTPUT, 'max_operational_dispatches': 1, 'max_validator_dispatches': 1,
        'credential_handoff_before_any_subprocess': True,
        'credential_lookup': 'inherited_existing_environment_only',
        'raw_channels_printed': False, 'output_leaf_reads': False,
        'validator_sandbox': SANDBOX, 'validator_code_sha256': sha(VALIDATOR_CODE.encode('ascii')),
        'source_only_preflight_before_and_after_parent': True,
        'post_dispatch_outcome': 'consumed_or_ambiguous_no_retry',
        'parent_seconds_scope': 'capture_only_excludes_bounded_git_validator_and_reap',
        'uninterruptible_io_or_host_suspension_bounded': False,
        'whole_interpreter_integrity': False, 'same_user_memory_sandbox': False,
        'capacity_or_launch_allowed': False}


PROFILE_SHA256 = sha(canonical(profile_record()))


def _capture(command, *, environ, timeout, input_bytes=None, max_stdout=MAX_STDOUT, popen=subprocess.Popen):
    """Bound both channels concurrently; terminate/reap only the created child."""
    require(type(command) is list and command and all(type(item) is str for item in command)
        and type(environ) is dict and type(timeout) in (int, float) and math.isfinite(timeout)
        and 0 < timeout <= PARENT_SECONDS and type(max_stdout) is int and 0 < max_stdout <= MAX_VALIDATOR
        and (input_bytes is None or type(input_bytes) is bytes and len(input_bytes) <= MAX_STDOUT), 'arguments')
    dispatched, deadline = support._utc_now(), time.monotonic() + timeout
    limits = {'stdout': max_stdout, 'stderr': MAX_STDERR}
    buffers = {key: bytearray() for key in limits}
    counts = dict.fromkeys(limits, 0)
    hashes = {key: hashlib.sha256() for key in limits}
    process = None
    selector = selectors.DefaultSelector()
    bound, actual_exit, offset, spawned = None, None, 0, False
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
            left = deadline - time.monotonic()
            if left <= 0:
                bound = 'deadline'
                break
            for key, _ in selector.select(min(0.1, left)):
                name, stream = key.data, key.fileobj
                if name == 'stdin':
                    try:
                        count = os.write(stream.fileno(), input_bytes[offset:offset + 16384])
                    except BrokenPipeError:
                        count, offset = 0, len(input_bytes)
                    except BlockingIOError:
                        continue
                    offset += count
                    if offset == len(input_bytes):
                        selector.unregister(stream); stream.close()
                else:
                    try:
                        raw = os.read(stream.fileno(), 16384)
                    except BlockingIOError:
                        continue
                    if not raw:
                        selector.unregister(stream); stream.close(); continue
                    counts[name] += len(raw)
                    hashes[name].update(raw)
                    buffers[name].extend(raw[:max(0, limits[name] - len(buffers[name]))])
                    if counts[name] > limits[name]:
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
                    process.kill()
                actual_exit = process.wait(timeout=REAP_SECONDS)
            except BaseException:
                bound, actual_exit = bound or 'reap_unknown', None
            for name in ('stdin', 'stdout', 'stderr'):
                stream = getattr(process, name, None)
                if stream is not None:
                    try: stream.close()
                    except BaseException: bound = bound or 'observer_io'
        selector.close()
    return Captured(bytes(buffers['stdout']), bytes(buffers['stderr']), actual_exit, bound,
        dispatched, support._utc_now(), counts['stdout'], counts['stderr'],
        hashes['stdout'].hexdigest(), hashes['stderr'].hexdigest(), spawned)


def _arguments(args):
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and type(args.caller_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.caller_sha256)
        and type(args.observer_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.observer_sha256), 'arguments')


def _git(arguments, environment):
    observed = _capture(['/usr/bin/git', *arguments], environ=environment, timeout=GIT_SECONDS)
    require(observed.bound is None and type(observed.actual_exit) is int
        and observed.actual_exit == 0 and not observed.stderr, 'git_state')
    return observed.stdout


def _preflight(args, environment):
    _arguments(args)
    require(type(CALLER_SHA256) is str and args.caller_sha256 == CALLER_SHA256, 'source_pin')
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable).absolute() == PYTHON and Path.cwd() == ROOT
        and Path(__file__).absolute() == SOURCE and ROOT.resolve() == ROOT, 'host')
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT) + '\n'),
        (['branch', '--show-current'], BRANCH + '\n'), (['rev-parse', 'HEAD'], args.expected_head + '\n'),
        (['status', '--porcelain', '--untracked-files=normal'], '')):
        require(_git(command, environment) == expected.encode('ascii'), 'git_state')
    for path, pin in ((SOURCE, args.observer_sha256), (CALLER, args.caller_sha256),
            (HELPER, HELPER_SHA256), *((path, None) for path in TESTS)):
        raw = _source_bytes(path)
        require(pin is None or sha(raw) == pin, 'source_pin')
        spec = args.expected_head + ':' + path.relative_to(ROOT).as_posix()
        size = _git(['cat-file', '-s', spec], environment)
        require(re.fullmatch(rb'[1-9][0-9]{0,6}\n', size) and int(size) == len(raw), 'source_pin')
        require(_git(['cat-file', 'blob', spec], environment) == raw, 'source_pin')
    require(_git(['rev-parse', 'HEAD'], environment) == (args.expected_head + '\n').encode('ascii')
        and _git(['status', '--porcelain', '--untracked-files=normal'], environment) == b'', 'git_state')


def _validator_command(args, actual_exit):
    return ['/usr/bin/sandbox-exec', '-p', SANDBOX, str(PYTHON), '-B', '-c', VALIDATOR_CODE,
        args.expected_head, args.caller_sha256, str(actual_exit)]


def _validated_packet(observed, actual_exit):
    require(observed.bound is None, 'validator_bound')
    require(not observed.stderr, 'validator_stderr')
    require(type(observed.actual_exit) is int and observed.actual_exit == 0, 'validator_refused')
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
    result = {'schema': SCHEMA, 'profile_sha256': PROFILE_SHA256, 'source_binding': None,
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
        directory = Path(tempfile.mkdtemp(prefix='a11-plain-observer-', dir=ROOT / '.pytest_cache'))
        safe_environment = _environment(directory)
        _preflight(args, safe_environment)
        child_environment = _environment(directory, credentials)
        result['operational_child_dispatch_attempted'] = True
        result['attempt_consumption'] = 'consumed_or_ambiguous_no_retry'
        observed = _capture([str(PYTHON), '-B', str(CALLER), 'recover', '--expected-head', args.expected_head,
            '--caller-sha256', args.caller_sha256], environ=child_environment, timeout=PARENT_SECONDS)
        result['parent'] = observed.metadata()
        child_environment.clear(); credentials.clear()
        require(observed.bound is None, 'parent_bound')
        require(not observed.stderr, 'parent_stderr')
        require(type(observed.actual_exit) is int and observed.actual_exit in (0, 2), 'parent_exit')
        _preflight(args, safe_environment)
        result['validator_dispatched'] = True
        validated = _capture(_validator_command(args, observed.actual_exit), environ=safe_environment,
            timeout=VALIDATOR_SECONDS, input_bytes=observed.stdout, max_stdout=MAX_VALIDATOR)
        result['validator'] = validated.metadata()
        result['validated_output'] = _validated_packet(validated, observed.actual_exit)
        result['output_validated'] = True
        require(len(canonical(result)) <= MAX_OUTPUT, 'validator_shape')
        return result, observed.actual_exit
    except BaseException as error:
        code = 'observer_refused'
        if type(error) is ObserverError:
            values = BaseException.args.__get__(error)
            if len(values) == 1 and type(values[0]) is str and values[0] in FINITE:
                code = values[0]
        result['failure_code'] = code
        result['output_validated'], result['validated_output'] = False, None
        return result, 2
    finally:
        if type(child_environment) is dict: child_environment.clear()
        if type(credentials) is dict: credentials.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--observer-sha256', required=True)
    args = parser.parse_args(argv)
    result, code = observe(args)
    sys.stdout.buffer.write(canonical(result))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
