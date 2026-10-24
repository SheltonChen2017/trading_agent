"""One third/final R298 same-project recovery, never a replay of A1 or A2.

Source bindings are not review or execution authority. The separately committed
decision must bind actual successful reconciliation-reader exit, output pins,
this exact source/profile/HEAD, and external actual parent exit/result handling.
No retry, resume, replacement project, next cell, or result acceptance exists.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_r298_recovery as previous

v5, frozen, helpers = previous.v5, previous.frozen, previous.helpers
canonical, parse, sha, metadata = previous.canonical, previous.parse, previous.sha, previous.metadata
SOURCE = ROOT / 'scripts/run_arv2_r298_final_recovery.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_final_recovery/R310-20261024-A'
RECONCILIATION = ROOT / 'artifacts/analyst_revisions_v2/newrule_reconciliation/R310-20261024-A'
SCHEMA = 'arv2-r298-final-recovery-v1'
PROJECT = 38364439
DEADLINE_SECONDS = 300
MAX_FILE = 4 * 1024 * 1024
MAX_OUTPUT = 24 * 1024
FALSE_FLAGS = dict(previous.FALSE_FLAGS)
WORKERS = ('reconciliation-check-worker', 'admission-initial-worker',
    'admission-launch-worker', 'admission-final-worker')
STAGES = frozenset(('claim', 'reconciliation', 'admission_initial', 'credentials',
    'construct', 'inspect', 'complete', 'compile', 'compile_poll', 'admission_launch',
    'launch', 'status_wait', 'status', 'admission_final', 'report'))
FINITE = frozenset(('source', 'context', 'arguments', 'control', 'control_changed',
    'json', 'bound', 'claim', 'reconciliation', 'child_failed', 'child_output', 'deadline',
    'input_admission', 'compile_failed', 'runtime_failed', 'compile_budget', 'journal'))
NEW_PINS = {
    'scripts/run_arv2_r298_recovery.py': 'c33a3b110072d072d9ef1b9272b128981e1115744caf9e980fd7df1d654b01e4',
    # Fixed reviewed/waived source bindings, never refreshed at run time.
    'scripts/read_arv2_r298_a2_stage.py': '3a73ad7f9d9ab08469592e8c856397bf312737872b0a22606c32371d77c4252a',
    'scripts/arv2_r298_final_recovery_remote.py': 'e9e0b9da61e04da7b6b97d30d95c2e51d00b25019098f51eef4d7930b41c60f5',
}
SANDBOX = ('(version 1)(allow default)(deny network*)'
    '(deny process-exec (literal "/usr/bin/security"))'
    '(deny file-read* (subpath "/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2/artifacts/analyst_revisions_v2/newrule_recovery/R298-20261024-A"))'
    '(deny file-write* (require-all '
    '(subpath "/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2/artifacts") '
    '(require-not (subpath "/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2/artifacts/analyst_revisions_v2/newrule_final_recovery/R310-20261024-A"))))')


class Refused(ValueError):
    pass


class ObservedFailure(Refused):
    """Only validated finite canonical context, never raw exceptions or responses."""


def require(condition, code):
    if not condition:
        raise Refused(code)


def remaining(deadline):
    require(time.monotonic() < deadline, 'deadline')
    return deadline - time.monotonic()


def _digest(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'control': str(CONTROL),
        'reconciliation': str(RECONCILIATION), 'branch': frozen.BRANCH,
        'python': str(frozen.PYTHON), 'project_id': PROJECT, 'attempt_id': 3,
        'candidate_attempt_ceiling': 3, 'shared_look': 1, 'development_look': 1,
        'family_sha256': v5.FAMILY_SHA256, 'admission_sha256': v5.ADMISSION_SHA256,
        'source_pins': dict(frozen.SOURCE_PINS), 'v5_pins': dict(v5.NEW_PINS),
        'previous_pins': dict(previous.NEW_PINS), 'new_pins': dict(NEW_PINS),
        'frozen_caller_sha256': v5.FROZEN_CALLER_SHA256,
        'worker_operations': list(WORKERS), 'native_sandbox': SANDBOX,
        'deadline_seconds': DEADLINE_SECONDS, 'compile_poll_limit': 20,
        'compile_interval_seconds': 10, 'status_poll_limit': 1,
        'status_interval_seconds': 60, 'max_output_bytes': MAX_OUTPUT,
        'actual_reader_exit_zero_required': True, 'actual_parent_exit_zero_required': True,
        'a1_a2_remain_spent': True, 'same_project_only': True,
        'old_recovery_leaf_read': False, 'automatic_retry': False, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head,
        'caller_sha256': args.caller_sha256, 'profile_sha256': sha(canonical(profile_record())),
        'project_id': PROJECT}


def claim(args):
    return {**binding(args), 'attempt_id': 3, 'shared_look': 1, 'development_look': 1,
        'reader_head': args.reader_head, 'reader_exit_code': args.reader_exit_code,
        'reader_report_sha256': args.reader_report_sha256,
        'reader_claim_sha256': args.reader_claim_sha256}


def _preflight(args, deadline):
    require(not v5._under_test() and Path(__file__).absolute() == SOURCE
        and args.operation in ('recover', *WORKERS), 'context')
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == frozen.PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT, 'context')
    require(all(type(value) is str and re.fullmatch('[0-9a-f]{40}', value)
        for value in (args.expected_head, args.reader_head)) and _digest(args.caller_sha256)
        and _digest(args.reader_report_sha256) and _digest(args.reader_claim_sha256)
        and type(args.reader_exit_code) is int and args.reader_exit_code == 0
        and (args.operation in WORKERS) == (args.control_fd is not None), 'arguments')
    if args.operation in WORKERS:
        require(not {'QC_USER_ID', 'QC_API_TOKEN'} & set(os.environ), 'context')
    name = 'scripts/arv2_newrule_execution_environment.py'
    require(helpers._source_digest(ROOT / name) == v5.NEW_PINS[name], 'source')
    from scripts import arv2_newrule_execution_environment as environment
    environment._require_environment()
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
        (['branch', '--show-current'], frozen.BRANCH), (['rev-parse', 'HEAD'], args.expected_head),
        (['status', '--porcelain'], '')):
        require(v5._git(command, deadline).decode('ascii').strip() == expected, 'context')
    pins = {**frozen.SOURCE_PINS, **v5.NEW_PINS, **previous.NEW_PINS, **NEW_PINS,
        'scripts/run_arv2_newrule_comparison.py': v5.FROZEN_CALLER_SHA256}
    for relative, digest in pins.items():
        require(_digest(digest) and digest != '0' * 64
            and helpers._source_digest(ROOT / relative) == digest, 'source')
    require(helpers._source_digest(SOURCE) == args.caller_sha256, 'source')
    selected = args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()
    count = v5._git(['cat-file', '-s', selected], deadline).decode('ascii').strip()
    require(re.fullmatch('[1-9][0-9]{0,6}', count) and int(count) <= MAX_FILE, 'source')
    raw = v5._git(['cat-file', 'blob', selected], deadline, int(count))
    require(len(raw) == int(count) and sha(raw) == args.caller_sha256
        and v5._git(['rev-parse', 'HEAD'], deadline).decode('ascii').strip() == args.expected_head
        and v5._git(['status', '--porcelain'], deadline) == b'', 'source')
    remaining(deadline)


class Store:
    """Fixed new leaf, full held/named metadata, exclusive durable files only."""

    def __init__(self, *, create=False, inherited=None):
        require(CONTROL.is_relative_to(ROOT / 'artifacts') and '..' not in CONTROL.parts, 'control')
        self.chain, self.fd = [], None
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                here = Path(*CONTROL.parts[:index + 1])
                if create and here in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        require(here != CONTROL, 'claim')
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
                info = os.fstat(fd)
                self.chain.append((info.st_dev, info.st_ino))
            self.fd = fd
            if inherited is not None:
                require(type(inherited) is int and inherited > 2
                    and metadata(os.fstat(inherited)) == metadata(os.fstat(fd)), 'claim')
            self.verify()
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        os.close(self.fd)

    def verify(self):
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part, identity in zip(CONTROL.parts[1:], self.chain):
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
                info = os.fstat(fd)
                require((info.st_dev, info.st_ino) == identity, 'control_changed')
            held, named = os.fstat(self.fd), os.fstat(fd)
            names = os.listdir(fd)
            require((held.st_dev, held.st_ino) == self.chain[-1]
                and metadata(held) == metadata(named) and held.st_uid == os.getuid()
                and stat.S_IMODE(held.st_mode) == 0o700 and len(names) <= 256
                and all(re.fullmatch('[a-zA-Z0-9_.-]+\\.json', name) for name in names)
                and held.st_nlink == 2 + len(names)
                and metadata(held) == metadata(os.fstat(fd)), 'control')
        finally:
            os.close(fd)

    def read(self, name):
        self.verify()
        require(type(name) is str and re.fullmatch('[a-zA-Z0-9_.-]+\\.json', name), 'control')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                and 0 < info.st_size <= MAX_FILE, 'control')
            raw = bytearray()
            while len(raw) <= MAX_FILE:
                chunk = os.read(fd, min(65536, MAX_FILE + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            require(len(raw) == info.st_size and metadata(info) == metadata(os.fstat(fd))
                == metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False)), 'control_changed')
        finally:
            os.close(fd)
        self.verify()
        return bytes(raw), parse(bytes(raw))

    def write(self, name, value):
        self.verify()
        require(type(name) is str and re.fullmatch('[a-zA-Z0-9_.-]+\\.json', name), 'control')
        raw = canonical(value)
        require(type(value) is dict and 0 < len(raw) <= MAX_FILE, 'bound')
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                require(count > 0, 'control')
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.fd)
        require(self.read(name)[0] == raw, 'control_changed')
        return {'sha256': sha(raw), 'byte_count': len(raw)}


def _reconciliation(args, deadline):
    """Read exactly the new two-file reader output, retaining all descriptors."""
    from scripts import read_arv2_r298_a2_stage as reader
    require(type(args.reader_exit_code) is int and args.reader_exit_code == 0, 'reconciliation')
    require(reader.OUTPUT == RECONCILIATION, 'source')
    with ExitStack() as stack:
        directory, chain = reader._open_directory(RECONCILIATION, stack)
        before = os.fstat(directory)
        require(before.st_uid == os.getuid() and stat.S_IMODE(before.st_mode) == 0o700
            and set(os.listdir(directory)) == {'claim.json', 'report.json'}, 'reconciliation')
        raw_claim, held_claim = reader._read_selected(directory, 'claim.json', stack)
        raw_report, held_report = reader._read_selected(directory, 'report.json', stack)
        require(sha(raw_claim) == args.reader_claim_sha256
            and sha(raw_report) == args.reader_report_sha256, 'reconciliation')
        expected = {'schema': reader.SCHEMA, 'expected_head': args.reader_head,
            'reader_sha256': NEW_PINS['scripts/read_arv2_r298_a2_stage.py'],
            'profile_sha256': sha(reader.canonical(reader.profile_record())),
            'old_binding': reader.old_binding(), 'attempt_consumed': True}
        require(raw_claim == canonical(expected), 'reconciliation')
        result = reader.validate_report(reader.parse(raw_report))
        require(all(result[key] == expected[key] for key in
            ('expected_head', 'reader_sha256', 'profile_sha256', 'old_binding'))
            and result['claim_sha256'] == sha(raw_claim) and result['claim_bytes'] == len(raw_claim), 'reconciliation')
        allowed = ['inspect-project', 'inspect-backtests', 'inspect-files',
            'complete-project', 'complete-backtests', 'complete-before']
        require(result['rpc_markers'] == allowed[:len(result['rpc_markers'])]
            and len(result['rpc_markers']) <= len(allowed)
            and result['compile_id'] is None and result['backtest_id'] is None
            and result['recorded_status'] is None and not result['completed_inventory_recorded']
            and set(result['receipts_present']) <= {'initial-inventory.json'}, 'reconciliation')
        reader._verify_chain(chain)
        for name, fd, meta in (held_claim, held_report):
            require(meta == metadata(os.fstat(fd)) == metadata(os.stat(name, dir_fd=directory,
                follow_symlinks=False)), 'control_changed')
        require(metadata(before) == metadata(os.fstat(directory))
            and set(os.listdir(directory)) == {'claim.json', 'report.json'}, 'control_changed')
    remaining(deadline)
    return {'reader_report_sha256': args.reader_report_sha256,
        'reader_claim_sha256': args.reader_claim_sha256, 'pre_mutation_prefix_authenticated': True}


def _worker(args, deadline):
    from scripts import arv2_r298_recovery_evidence as evidence
    from scripts import arv2_newrule_execution_environment as environment
    environment.require_safe_environment()
    with Store(inherited=args.control_fd) as store:
        require(store.read('claim.json')[1] == claim(args), 'claim')
        store.write(args.operation + '-start.json', claim(args))
        if args.operation == 'reconciliation-check-worker':
            result = _reconciliation(args, deadline)
        else:
            projected = evidence.reconstruct_projection()
            previous._admission(projected, deadline)
            result = {'admission_authenticated': True,
                'projection_sha256': projected.projection_sha256}
        remaining(deadline)
        return result


def _child(args, store, deadline, operation):
    require(operation in WORKERS, 'arguments')
    env = {key: value for key, value in os.environ.items() if key not in ('QC_USER_ID', 'QC_API_TOKEN')}
    command = ['/usr/bin/sandbox-exec', '-p', SANDBOX, str(frozen.PYTHON), '-B', str(SOURCE), operation,
        '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
        '--reader-head', args.reader_head, '--reader-exit-code', '0',
        '--reader-report-sha256', args.reader_report_sha256,
        '--reader-claim-sha256', args.reader_claim_sha256, '--control-fd', str(store.fd)]
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=(store.fd,))
    output, errors = bytearray(), bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            for stream, target in ((process.stdout, output), (process.stderr, errors)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, target)
            while selector.get_map():
                for key, _ in selector.select(min(0.5, remaining(deadline))):
                    chunk = os.read(key.fd, 4096)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        key.data.extend(chunk)
                        require(len(key.data) <= MAX_OUTPUT, 'child_output')
            code = process.wait(timeout=remaining(deadline))
        require(type(code) is int and code == 0 and not errors, 'child_failed')
        require(bytes(output).endswith(b'\n\n'), 'child_output')
        payload = parse(bytes(output[:-1]))
        require(set(payload) == {'schema', 'operation', 'binding', 'result', 'operation_completed', *FALSE_FLAGS}
            and payload['schema'] == SCHEMA and payload['binding'] == binding(args)
            and payload['operation'] == operation and payload['operation_completed'] is True
            and all(payload[key] is False for key in FALSE_FLAGS), 'child_output')
        result = payload['result']
        if operation == 'reconciliation-check-worker':
            expected = {'reader_report_sha256': args.reader_report_sha256,
                'reader_claim_sha256': args.reader_claim_sha256, 'pre_mutation_prefix_authenticated': True}
        else:
            from scripts import arv2_r298_final_recovery_remote as remote
            expected = {'admission_authenticated': True, 'projection_sha256': remote.PROJECTION_SHA256}
        require(type(result) is dict and canonical(result) == canonical(expected), 'child_output')
        store.write(operation + '-completed.json', {**binding(args), 'result': result})
        return result
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


def finite_code(error):
    from scripts import arv2_r298_final_recovery_remote as remote
    if type(error) is remote.RecoveryError:
        return 'remote_refused'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    return 'unknown_exception'


def _failure(error, state):
    from scripts import arv2_r298_final_recovery_remote as remote
    result = {'code': finite_code(error), **remote.finite_error(error),
        'last_stage': state['last_stage'], 'intent_marker': state['intent_marker'],
        'endpoint': state['endpoint'], 'last_event': state['last_event'],
        'application_dispatch_count': state['application_dispatch_count'],
        'category': state['category'], 'http_status': state['http_status'],
        'provider_request_count': None}
    _validate_failure(result)
    return result


def _validate_failure(value):
    from scripts import arv2_r298_final_recovery_remote as remote
    require(type(value) is dict and set(value) == {'code', 'helper_code', 'predicate',
        'last_stage', 'intent_marker', 'endpoint', 'last_event', 'application_dispatch_count',
        'category', 'http_status', 'provider_request_count'}, 'journal')
    require(value['code'] in (*FINITE, 'unknown_exception', 'remote_refused')
        and value['helper_code'] in (*remote.FINITE_CODES, 'unknown')
        and value['predicate'] == remote.OWNERSHIP_PREDICATES.get(value['helper_code'])
        and value['last_stage'] in STAGES
        and type(value['application_dispatch_count']) is int and 0 <= value['application_dispatch_count'] <= 60
        and value['category'] in ('unknown', 'status_or_bound_refusal', 'http_failure', 'http_non_json')
        and (value['http_status'] is None or (type(value['http_status']) is int and 100 <= value['http_status'] <= 599))
        and value['provider_request_count'] is None, 'journal')
    if value['intent_marker'] is None:
        require(value['endpoint'] is None and value['last_event'] is None
            and value['application_dispatch_count'] == 0, 'journal')
    else:
        require(type(value['intent_marker']) is str and re.fullmatch('[a-z0-9-]{1,80}', value['intent_marker'])
            and value['endpoint'] in remote.ENDPOINTS and value['last_event'] in ('intent', 'observed', 'failure'), 'journal')


def failure_observation(error):
    if type(error) is not ObservedFailure:
        return None
    args = BaseException.args.__get__(error)
    require(len(args) == 1 and type(args[0]) is bytes and len(args[0]) <= 2048, 'journal')
    result = parse(args[0])
    _validate_failure(result)
    return result


def _new_state():
    return {'last_stage': 'claim', 'intent_marker': None, 'endpoint': None, 'last_event': None,
        'application_dispatch_count': 0, 'category': 'unknown', 'http_status': None}


def _raise_observed(error, state, store, args):
    observation = _failure(error, state)
    # Even a failed receipt write must not erase finite in-memory context.
    try:
        store.write('failure.json', {**binding(args), 'observation': observation, **FALSE_FLAGS})
    except BaseException:
        pass
    raise ObservedFailure(canonical(observation)) from None


def _recover(args, store, deadline, *, state=None):
    from scripts import arv2_r298_recovery_evidence as evidence
    from scripts import arv2_r298_final_recovery_remote as remote
    from scripts import arv2_newrule_execution_environment as environment
    if state is None:
        state = _new_state()
    try:
        store.write('claim.json', claim(args))
        state['last_stage'] = 'reconciliation'
        _child(args, store, deadline, 'reconciliation-check-worker')
        projected = evidence.reconstruct_projection()
        state['last_stage'] = 'admission_initial'
        _child(args, store, deadline, 'admission-initial-worker')
        state['last_stage'] = 'credentials'
        environment.require_safe_environment()
        client = environment.guarded_client()

        def journal(marker, event):
            remaining(deadline)
            require(type(marker) is str and re.fullmatch('[a-z0-9-]{1,80}', marker)
                and type(event) is dict and set(event) == {'event', 'endpoint', 'sha256'}
                and event['event'] in ('intent', 'observed') and event['endpoint'] in remote.ENDPOINTS
                and _digest(event['sha256']), 'journal')
            store.write('rpc-' + marker + '-' + event['event'] + '.json', {**binding(args), **event})
            state.update(intent_marker=marker, endpoint=event['endpoint'], last_event=event['event'])

        def request(endpoint, payload):
            remaining(deadline)
            environment.require_safe_environment()
            require(state['endpoint'] == endpoint and state['last_event'] == 'intent'
                and endpoint in remote.ENDPOINTS and state['application_dispatch_count'] < 60, 'journal')
            state['application_dispatch_count'] += 1  # Application dispatch, not measured server contact.
            try:
                return client.request(endpoint, payload)
            except BaseException as error:
                state.update(previous.http_context(error, endpoint))
                state['last_event'] = 'failure'
                store.write('rpc-' + state['intent_marker'] + '-failure.json', {**binding(args),
                    'intent_marker': state['intent_marker'], 'endpoint': endpoint,
                    'application_dispatch_count': state['application_dispatch_count'],
                    'category': state['category'], 'http_status': state['http_status'],
                    'provider_request_count': None})
                raise

        state['last_stage'] = 'construct'
        runner = remote.FinalRecovery(projected, remote.ORGANIZATION_SHA256, request, journal)
        result = _workflow(args, runner, store, deadline, state)
        return {**result, 'application_dispatch_count': state['application_dispatch_count'],
            'provider_request_count': None}
    except BaseException as error:
        _raise_observed(error, state, store, args)


def _workflow(args, runner, store, deadline, state):
    state['last_stage'] = 'inspect'
    initial = runner.inspect()
    store.write('initial-inventory.json', initial)
    state['last_stage'] = 'complete'
    completed = runner.complete(initial)
    store.write('completed-inventory.json', completed)
    state['last_stage'] = 'compile'
    compiled = runner.compile_once(completed)
    store.write('compile-receipt.json', compiled)
    state['last_stage'] = 'compile_poll'
    for index in range(20):
        require(remaining(deadline) > 10, 'deadline')
        time.sleep(10)
        status = runner.poll_compile(compiled['compile_id'], index)
        store.write(f'compile-status-{index:02d}.json', status)
        require(status['state'] != 'BuildError', 'compile_failed')
        if status['state'] == 'BuildSuccess':
            break
    else:
        raise Refused('compile_budget')
    state['last_stage'] = 'admission_launch'
    _child(args, store, deadline, 'admission-launch-worker')
    require(remaining(deadline) > 90, 'deadline')
    state['last_stage'] = 'launch'
    launched = runner.launch_once(compiled['compile_id'])
    store.write('launch-receipt.json', launched)
    if launched.get('state') == 'wait':
        state['last_stage'] = 'admission_final'
        _child(args, store, deadline, 'admission-final-worker')
        return {'terminal': 'capacity_wait', 'project_id': PROJECT, 'compile_id': compiled['compile_id']}
    state['last_stage'] = 'status_wait'
    require(remaining(deadline) > 60, 'deadline')
    time.sleep(60)
    state['last_stage'] = 'status'
    status = runner.read_status(launched, 0)
    store.write('own-status.json', status)
    require(status['status'] != 'Runtime Error', 'runtime_failed')
    state['last_stage'] = 'admission_final'
    _child(args, store, deadline, 'admission-final-worker')
    return {'terminal': 'own_status_observed', 'launch': launched, 'status': status}


def _execute(args, deadline):
    _preflight(args, deadline)
    from scripts import arv2_newrule_execution_environment as environment
    environment.require_safe_environment()
    if args.operation in WORKERS:
        return _worker(args, deadline)
    with Store(create=True) as store:
        state = _new_state()
        try:
            result = _recover(args, store, deadline, state=state)
            state['last_stage'] = 'report'
            _preflight(args, deadline)
            remaining(deadline)
            pin = store.write('report.json', {**binding(args), 'result': result,
                'operation_completed': True, **FALSE_FLAGS})
            return {'report': pin, 'result': result}
        except BaseException as error:
            if type(error) is ObservedFailure:
                raise
            _raise_observed(error, state, store, args)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('recover', *WORKERS))
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--reader-head', required=True)
    parser.add_argument('--reader-report-sha256', required=True)
    parser.add_argument('--reader-claim-sha256', required=True)
    parser.add_argument('--reader-exit-code', required=True, type=int)
    parser.add_argument('--control-fd', type=int)
    args = parser.parse_args(argv)
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        with helpers._alarm(deadline):
            _preflight(args, deadline)
            from scripts import arv2_newrule_execution_environment as environment
            environment._bootstrap_cli_logging()
            result = _execute(args, deadline)
            payload = canonical({'schema': SCHEMA, 'operation': args.operation, 'binding': binding(args),
                'result': result, 'operation_completed': True, **FALSE_FLAGS})
            require(len(payload) <= MAX_OUTPUT, 'bound')
            print(payload.decode('ascii'))
            return 0
    except BaseException as error:
        try:
            observation = failure_observation(error)
        except BaseException:
            observation = None
        print(canonical({'schema': SCHEMA, 'operation': args.operation,
            'operation_completed': False, 'failure_code': observation['code'] if observation else finite_code(error),
            'failure_observation': observation, 'attempt_consumption': 'consumed_or_ambiguous_no_retry',
            **FALSE_FLAGS}).decode('ascii'))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
