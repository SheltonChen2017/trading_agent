"""One frozen R298 launch, bounded observation and one aggregate result read.

The owner-authorized comparison uses a new control and the admitted plain-data
source. Old operational entrypoints and spent claims are never dispatched.
The outer observer retains actual exit and separate channels; native workers
authenticate inputs without credentials. Importing this file performs no work.
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
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_r298_plain_readiness as admitted
from scripts import observe_arv2_r298_plain_readiness as capture_support
from scripts import arv2_newrule_execution_environment as environment

SOURCE = ROOT / 'scripts/run_arv2_r298_plain_backtest.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_plain_backtest/R323-20261025-A'
PYTHON = admitted.frozen.PYTHON
SCHEMA = 'arv2-r298-plain-backtest-v1'
DEADLINE_SECONDS = 15120
MAX_OUTPUT = 128 * 1024
MAX_OBSERVER_OUTPUT = MAX_OUTPUT + 4096
MAX_PACKET = 640 * 1024
MAX_FILES = 1024
MAX_DISPATCHES = 300
NEW_PINS = {
    'scripts/run_arv2_r298_plain_readiness.py': 'ec7f08b6483dcac360f1cffdaa54c956f9b734543ab6f7a7579c84b7253d94e3',
    'scripts/observe_arv2_r298_plain_readiness.py': '9a90b60f82ce8996f8a8fb50c3af965b724332e835291c840dffd1264807ecab',
    'scripts/arv2_r298_plain_launch.py': 'c292e23de517713aa4f61e9b019d422d40dbd0a9d1b8a7e2c7650a0a8c802bb7',
    'scripts/arv2_r298_launch_admission.py': '009b18fb5ea52d59a19e4706d40b1a90d5f501f691fbd96fdb92caae4804ffcc',
    'research/analyst_revisions_v2_qc/newrule_plain_comparison.py': '7f6a23d157488ae5029510029811fced5c01a363bb5647a2667ed5fe8e92f407',
}
FALSE_FLAGS = {'point_in_time_proven': False, 'formal_identity_admitted': False,
               'formal_forward_ready': False, 'paper_or_live_ready': False}
canonical, parse, sha, metadata = admitted.canonical, admitted.parse, admitted.sha, admitted.metadata


class Refused(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Refused(code)


def remaining(deadline):
    value = deadline - time.monotonic()
    require(value > 0, 'deadline')
    return value


def finite(error):
    if type(error) is Refused and len(error.args) == 1 and type(error.args[0]) is str:
        return error.args[0] if re.fullmatch('[a-z_]{1,64}', error.args[0]) else 'refused'
    for name in ('arv2_r298_plain_launch', 'arv2_r298_launch_admission'):
        module = sys.modules.get('scripts.' + name)
        if module is not None and type(error) is vars(module).get('Refused'):
            method = vars(module).get('finite')
            if callable(method): return 'launch_' + method(error)
            values = BaseException.args.__get__(error)
            if len(values) == 1 and type(values[0]) is str and values[0] in module.FINITE:
                return 'launch_' + values[0]
    if isinstance(error, OSError):
        return 'os_error'
    return 'unknown_exception'


def pins():
    return {**admitted.selected_pins(), **NEW_PINS}


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH,
        'python': str(PYTHON), 'control': str(CONTROL), 'source_pins': pins(),
        'project_id': 38364439, 'attempt': 12, 'max_launches': 1,
        'max_dispatches': MAX_DISPATCHES, 'deadline_seconds': DEADLINE_SECONDS,
        'max_output': MAX_OUTPUT, 'max_observer_output': MAX_OBSERVER_OUTPUT,
        'max_public_packet': MAX_PACKET,
        'capacity_polls': 3, 'capacity_interval': 60,
        'status_polls': 240, 'status_interval': 60,
        'result_reads': 1, 'old_attempts_spent': True,
        'comparison_specification_sha256': 'ee8df6e992c0763c3448bd0f601f0cb789f8abe9bdc86497274163805a424a13',
        'readiness_exit': 0, 'readiness_head': '9d4725e78ce4baaa39fc080de54aba25ce69b56f',
        'readiness_report_sha256': 'a0ac64a13299e9fa2a37816a15394448bbec8236c9b6636bc379b00dece375e7',
        'readiness_report_bytes': 10684,
        'worker_credentials': False, 'source_uploads': 0, 'new_compiles': 0,
        'same_user_sandbox': False, 'continuous_integrity_proven': False,
        'uninterruptible_io_or_suspension_bounded': False, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head,
        'caller_sha256': args.caller_sha256, 'profile_sha256': sha(canonical(profile_record()))}


def preflight(args, deadline):
    require(not admitted.v5._under_test() and Path(__file__).absolute() == SOURCE
        and sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT, 'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and type(args.caller_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.caller_sha256), 'arguments')
    environment._require_environment()
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
        (['branch', '--show-current'], admitted.frozen.BRANCH),
        (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        require(admitted.v5._git(command, deadline).decode('ascii').strip() == expected, 'git_state')
    for name, pin in pins().items():
        require(pin != '0' * 64 and sha((ROOT / name).read_bytes()) == pin, 'source_pin')
    require(sha(SOURCE.read_bytes()) == args.caller_sha256, 'source_pin')
    blob = admitted.v5._git(['cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()],
                           deadline, 128 * 1024)
    require(sha(blob) == args.caller_sha256, 'source_pin')
    remaining(deadline)


class Store:
    """Exclusive immutable records, held directory and checked named metadata.

    Leaf descriptors close after verification to avoid an unbounded FD census
    over four hours of status observations. This is endpoint authentication.
    """
    def __init__(self):
        self.fd, self.chain, self.files = None, [], {}
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                here = Path(*CONTROL.parts[:index + 1])
                if here in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        require(here != CONTROL, 'claim_spent')
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
                self.chain.append((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
            self.fd = fd
            self.verify()
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self): return self
    def __exit__(self, *_): os.close(self.fd)

    def verify(self):
        other, chain = admitted._storage_module()._walk(CONTROL)
        try:
            held, named = os.fstat(self.fd), os.fstat(other)
            require(chain == tuple(self.chain) and metadata(held) == metadata(named)
                and held.st_uid == os.getuid() and stat.S_IMODE(held.st_mode) == 0o700
                and set(os.listdir(other)) == set(self.files) and len(self.files) <= MAX_FILES
                and held.st_nlink == 2 + len(self.files),
                'control_changed')
            for name, baseline in self.files.items():
                require(metadata(os.stat(name, dir_fd=other, follow_symlinks=False)) == baseline,
                        'control_changed')
        finally:
            os.close(other)

    def write(self, name, value):
        self.verify()
        require(type(name) is str and re.fullmatch('[a-z0-9-]{1,100}\\.json', name)
            and name not in self.files and len(self.files) < MAX_FILES, 'control_name')
        raw = canonical(value)
        require(0 < len(raw) <= MAX_PACKET, 'control_bound')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            view = memoryview(raw)
            while view:
                n = os.write(fd, view)
                require(n > 0, 'control_write')
                view = view[n:]
            os.fsync(fd)
            os.fsync(self.fd)
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == len(raw), 'control_write')
            os.lseek(fd, 0, os.SEEK_SET)
            reread = bytearray()
            while len(reread) <= len(raw):
                chunk = os.read(fd, min(65536, len(raw) + 1 - len(reread)))
                if not chunk: break
                reread.extend(chunk)
            require(bytes(reread) == raw and metadata(info) == metadata(os.fstat(fd)), 'control_changed')
            self.files[name] = metadata(info)
        finally:
            os.close(fd)
        self.verify()
        return {'byte_count': len(raw), 'sha256': sha(raw)}


def capture(command, environ, timeout, *, input_bytes=None, stdout_limit=MAX_OUTPUT, pass_fds=()):
    """Concurrent finite channels; reap only the child created here."""
    require(type(timeout) in (int, float) and math.isfinite(timeout) and 0 < timeout <= DEADLINE_SECONDS + 60,
            'capture_timeout')
    process = None
    output, errors, offset, bound = bytearray(), bytearray(), 0, None
    deadline, dispatched = time.monotonic() + timeout, capture_support.support._utc_now()
    actual = None
    try:
        process = subprocess.Popen(command, cwd=ROOT, env=environ, close_fds=True, pass_fds=pass_fds,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with selectors.DefaultSelector() as selection:
            for stream, target in ((process.stdout, output), (process.stderr, errors)):
                os.set_blocking(stream.fileno(), False)
                selection.register(stream, selectors.EVENT_READ, target)
            if input_bytes is not None:
                os.set_blocking(process.stdin.fileno(), False)
                if input_bytes: selection.register(process.stdin, selectors.EVENT_WRITE, None)
                else: process.stdin.close()
            while selection.get_map():
                if time.monotonic() >= deadline:
                    bound = 'deadline'; break
                for key, _ in selection.select(min(0.25, deadline - time.monotonic())):
                    if key.data is None:
                        try: offset += os.write(key.fd, input_bytes[offset:offset + 16384])
                        except BrokenPipeError: offset = len(input_bytes)
                        except BlockingIOError: continue
                        if offset == len(input_bytes):
                            selection.unregister(key.fileobj); key.fileobj.close()
                        continue
                    try: chunk = os.read(key.fd, 16384)
                    except BlockingIOError: continue
                    if not chunk:
                        selection.unregister(key.fileobj); continue
                    key.data.extend(chunk)
                    if len(output) > stdout_limit or len(errors) > 4096:
                        bound = 'channel_bound'; break
                if bound: break
        if bound is None:
            try: actual = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired: bound = 'deadline'
    except BaseException:
        bound = 'capture_failed'
    finally:
        if process is not None:
            try:
                if process.poll() is None: process.kill()
                actual = process.wait(timeout=5)
            except BaseException: actual, bound = None, 'reap_unknown'
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None: stream.close()
    record = {'actual_exit': actual, 'bound': bound, 'spawn_observed': process is not None,
        'dispatched_at': dispatched, 'completion_observed_at': capture_support.support._utc_now(),
        'stdout_bytes': len(output), 'stdout_sha256': sha(bytes(output)),
        'stderr_bytes': len(errors), 'stderr_sha256': sha(bytes(errors))}
    return bytes(output), bytes(errors), record


def native_profile(*, artifacts=False):
    base = ('(version 1)(allow default)(deny network*)'
        '(deny file-read* file-write* (subpath "/Users/sheltonchen/Library/Keychains"))'
        '(deny file-read* file-write* (subpath "/Library/Keychains"))'
        '(deny process-exec (literal "/usr/bin/security"))'
        f'(deny file-write* (require-all (require-not (subpath "{ROOT / ".pytest_cache"}"))'
        ' (require-not (literal "/dev/null"))))')
    if artifacts:
        base += f'(deny file-read* file-write* (subpath "{ROOT / "artifacts"}"))'
    else:
        base += ''.join(f'(deny file-read* (subpath "{path}"))' for path in admitted.OLD_CONTROLS)
    return base


def credential_shape():
    return capture_support._credential_handoff(os.environ)


def worker(args, deadline):
    require(type(args.control_fd) is int and args.control_fd > 2 and args.worker_index in (0, 1), 'worker_scope')
    fd, _ = admitted._storage_module()._walk(CONTROL)
    try:
        require(metadata(os.fstat(fd)) == metadata(os.fstat(args.control_fd)), 'worker_scope')
        source = os.open('worker-' + str(args.worker_index) + '-intent.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            raw = os.read(source, 65537)
            require(parse(raw) == {**binding(args), 'worker_index': args.worker_index}, 'worker_scope')
        finally: os.close(source)
    finally: os.close(fd)
    require(not {'QC_USER_ID', 'QC_API_TOKEN'} & set(os.environ), 'worker_credentials')
    from scripts import arv2_r298_launch_admission as admission
    packet = admission.admit(deadline)
    preflight(args, deadline)
    environment.require_safe_environment()
    return packet


def run_worker(args, directory, deadline, index):
    directory.write('worker-' + str(index) + '-intent.json', {**binding(args), 'worker_index': index})
    env = {key: value for key, value in os.environ.items() if key not in ('QC_USER_ID', 'QC_API_TOKEN')}
    command = ['/usr/bin/sandbox-exec', '-p', native_profile(), str(PYTHON), '-B', str(SOURCE), 'worker',
        '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
        '--control-fd', str(directory.fd), '--worker-index', str(index)]
    raw, errors, observed = capture(command, env, min(120, remaining(deadline)), stdout_limit=MAX_PACKET,
                                    pass_fds=(directory.fd,))
    directory.write('worker-' + str(index) + '-observed.json', observed)
    require(observed['actual_exit'] == 0 and observed['bound'] is None and not errors, 'admission_failed')
    value = parse(raw)
    require(set(value) == {'binding', 'packet'} and value['binding'] == binding(args), 'admission_packet')
    from scripts import arv2_r298_launch_admission as admission
    admission.validate_packet(value['packet'])
    return value['packet']


def run(args, deadline):
    credential_shape().clear()
    from scripts import arv2_r298_plain_launch as launch
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'attempt': 12, 'old_attempts_spent': True})
        state = {'stage': 'initial_admission', 'dispatch_count': 0, 'launch': None, 'terminal': None}
        runner = None
        try:
            packet = run_worker(args, directory, deadline, 0)
            environment.require_safe_environment()
            from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
            api = old._client()
            environment.require_safe_environment()

            def request(endpoint, payload):
                remaining(deadline)
                environment.require_safe_environment()
                require(endpoint in launch.PAYLOAD_KEYS and type(payload) is dict
                    and set(payload) == launch.PAYLOAD_KEYS[endpoint]
                    and type(payload['projectId']) is int and payload['projectId'] == 38364439
                    and state['dispatch_count'] < MAX_DISPATCHES
                    and type(api) is old.QuantConnectClient and api._base_url == old.API_BASE
                    and api._transport is old.coverage._bounded_transport and api._timeout == 30,
                    'request_scope')
                state['dispatch_count'] += 1
                return api.request(endpoint, payload)

            def journal(marker, event):
                remaining(deadline)
                directory.write(marker + '-' + event['event'].replace('_', '-') + '.json',
                                {**binding(args), **event})

            runner = launch.PlainLaunch(packet['projection_record'].encode('ascii'),
                tuple((name, text.encode('ascii')) for name, text in packet['source_pairs']),
                request=request, journal=journal)
            state['stage'] = 'launch'
            for index in range(3):
                if index:
                    require(remaining(deadline) > 60, 'deadline')
                    time.sleep(60)
                outcome = runner.launch_once()
                if outcome['state'] != 'wait': break
            else:
                result = {'terminal': 'capacity_wait', 'application_dispatch_count': state['dispatch_count'],
                          'launch': None, 'result': None, **FALSE_FLAGS}
                pin = directory.write('report.json', {**binding(args), 'result': result})
                return {'result': result, 'report': pin}
            state['launch'] = runner.launch_receipt
            state['stage'] = 'status'
            for index in range(240):
                if runner.terminal_receipt is not None: break
                require(remaining(deadline) > 60, 'deadline')
                time.sleep(60)
                runner.poll_status(index)
            require(runner.terminal_receipt is not None, 'status_budget')
            state['terminal'] = runner.terminal_receipt
            if state['terminal']['status'] != 'Completed.':
                result = {'terminal': 'runtime_error', 'application_dispatch_count': state['dispatch_count'],
                          'launch': runner.launch_receipt, 'result': runner.terminal_receipt, **FALSE_FLAGS}
            else:
                state['stage'] = 'result'
                accepted = runner.read_once()
                state['stage'] = 'final_admission'
                final_packet = run_worker(args, directory, deadline, 1)
                require(final_packet == packet, 'admission_changed')
                result = {'terminal': 'completed', 'application_dispatch_count': state['dispatch_count'],
                    'launch': runner.launch_receipt, 'result': accepted, **FALSE_FLAGS}
            preflight(args, deadline)
            pin = directory.write('report.json', {**binding(args), 'result': result})
            return {'result': result, 'report': pin}
        except BaseException as error:
            state['launch'] = runner.launch_receipt if runner is not None else None
            state['terminal'] = runner.terminal_receipt if runner is not None else None
            failed = {'failure_code': finite(error), 'state': state, 'provider_request_count': None,
                      'attempt_consumption': 'consumed_or_ambiguous_no_retry', **FALSE_FLAGS}
            try: directory.write('failure.json', {**binding(args), **failed})
            except BaseException: pass
            return {'failure': failed}


def validate_output(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit in (0, 2) and type(raw) is bytes
            and 0 < len(raw) <= MAX_OUTPUT, 'output')
    value = parse(raw)
    if set(value) == {'binding', 'preflight_failure'}:
        require(actual_exit == 2 and value['binding'] == binding(args)
            and type(value['preflight_failure']) is str
            and re.fullmatch('[a-z_]{1,80}', value['preflight_failure']), 'output')
        return value
    require(set(value) == {'binding', 'outcome'} and value['binding'] == binding(args), 'output')
    outcome = value['outcome']
    require(type(outcome) is dict, 'output')
    if 'failure' in outcome:
        require(actual_exit == 2 and set(outcome) == {'failure'}, 'output')
        failed = outcome['failure']
        require(set(failed) == {'failure_code', 'state', 'provider_request_count', 'attempt_consumption', *FALSE_FLAGS}
            and type(failed['failure_code']) is str and re.fullmatch('[a-z_]{1,80}', failed['failure_code'])
            and failed['provider_request_count'] is None
            and failed['attempt_consumption'] == 'consumed_or_ambiguous_no_retry'
            and all(failed[key] is False for key in FALSE_FLAGS), 'output')
        state = failed['state']
        require(type(state) is dict and set(state) == {'stage', 'dispatch_count', 'launch', 'terminal'}
            and state['stage'] in ('initial_admission', 'launch', 'status', 'result', 'final_admission')
            and type(state['dispatch_count']) is int and 0 <= state['dispatch_count'] <= MAX_DISPATCHES,
            'output')
        from scripts import arv2_r298_plain_launch as launch
        if state['launch'] is not None: launch.validate_launch_receipt(state['launch'])
        if state['terminal'] is not None:
            launch.validate_terminal_receipt(state['terminal'])
            require(state['launch'] is not None and all(state['terminal'][key] == item
                for key, item in state['launch'].items()), 'output')
    else:
        require(set(outcome) == {'result', 'report'} and type(outcome['result']) is dict, 'output')
        result = outcome['result']
        require(set(result) == {'terminal', 'application_dispatch_count', 'launch', 'result', *FALSE_FLAGS}
            and result['terminal'] in ('completed', 'runtime_error', 'capacity_wait')
            and type(result['application_dispatch_count']) is int and 0 <= result['application_dispatch_count'] <= MAX_DISPATCHES
            and all(result[key] is False for key in FALSE_FLAGS), 'output')
        report = canonical({**binding(args), 'result': result})
        require(outcome['report'] == {'byte_count': len(report), 'sha256': sha(report)}
            and actual_exit == (2 if result['terminal'] == 'runtime_error' else 0), 'output')
        from scripts import arv2_r298_plain_launch as launch
        if result['launch'] is not None:
            launch.validate_launch_receipt(result['launch'])
        if result['terminal'] == 'completed':
            require(result['launch'] is not None, 'output')
            launch.validate_result_receipt(result['result'])
            require(all(result['result'][key] == item for key, item in result['launch'].items()), 'output')
        elif result['terminal'] == 'runtime_error':
            require(result['launch'] is not None, 'output')
            launch.validate_terminal_receipt(result['result'])
            require(result['result']['status'] == 'Runtime Error'
                and all(result['result'][key] == item for key, item in result['launch'].items()), 'output')
        else:
            require(result['launch'] is None and result['result'] is None, 'output')
    return value


def observe(args):
    credentials, parent_env = {}, {}
    outer = {'schema': SCHEMA + '-observer', 'parent': None, 'validator': None,
             'output_authenticated': False, 'output': None, 'failure_code': None}
    try:
        credentials = credential_shape()
        runtime = Path(tempfile.mkdtemp(prefix='r323-observer-', dir=ROOT / '.pytest_cache'))
        safe = capture_support._environment(runtime)
        parent_env = capture_support._environment(runtime, credentials)
        raw, errors, observed = capture([str(PYTHON), '-B', str(SOURCE), 'run',
            '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256],
            parent_env, DEADLINE_SECONDS + 30)
        outer['parent'] = observed
        credentials.clear(); parent_env.clear()
        require(observed['bound'] is None and not errors and type(observed['actual_exit']) is int
                and observed['actual_exit'] in (0, 2), 'parent_failed')
        command = ['/usr/bin/sandbox-exec', '-p', native_profile(artifacts=True), str(PYTHON), '-B', str(SOURCE),
            'validate', '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
            '--actual-exit', str(observed['actual_exit'])]
        valid, stderr, checked = capture(command, safe, 20, input_bytes=raw)
        outer['validator'] = checked
        require(checked['actual_exit'] == 0 and checked['bound'] is None and not stderr, 'validator_failed')
        outer['output'] = parse(valid)
        outer['output_authenticated'] = True
        require(len(canonical(outer)) <= MAX_OBSERVER_OUTPUT, 'output_bound')
        return outer, observed['actual_exit']
    except BaseException as error:
        outer['failure_code'] = finite(error)
        return outer, 2
    finally:
        credentials.clear(); parent_env.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('observe', 'run', 'worker', 'validate'))
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--control-fd', type=int)
    parser.add_argument('--worker-index', type=int)
    parser.add_argument('--actual-exit', type=int)
    args = parser.parse_args(argv)
    if args.operation == 'observe':
        result, code = observe(args)
        sys.stdout.buffer.write(canonical(result))
        return code
    deadline = time.monotonic() + (120 if args.operation in ('worker', 'validate') else DEADLINE_SECONDS)
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args, deadline)
            environment._bootstrap_cli_logging()
            if args.operation == 'worker':
                payload, code = {'binding': binding(args), 'packet': worker(args, deadline)}, 0
            elif args.operation == 'validate':
                payload = validate_output(sys.stdin.buffer.read(MAX_OUTPUT + 1), args.actual_exit, args)
                code = 0
            else:
                outcome = run(args, deadline)
                payload = {'binding': binding(args), 'outcome': outcome}
                code = 2 if 'failure' in outcome or outcome.get('result', {}).get('terminal') == 'runtime_error' else 0
            raw = canonical(payload)
            require(len(raw) <= (MAX_PACKET if args.operation == 'worker' else MAX_OUTPUT), 'output_bound')
            sys.stdout.buffer.write(raw)
            return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'binding': binding(args), 'preflight_failure': finite(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
