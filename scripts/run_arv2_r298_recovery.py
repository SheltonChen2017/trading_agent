"""One-use evidence and same-project R298 recovery, never an old begin replay.

Preparation is not execution authority. Each operation requires its separate
committed run decision; source/pin arguments are bindings, not authorization.
The external observer must retain actual exit 0 AND the matching finite output.
Partial claims remain consumed/ambiguous; no automatic resumption or cleanup.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
from scripts import run_arv2_newrule_recovery_continuation_v5 as v5

frozen, helpers = v5.frozen, v5.helpers
SOURCE = ROOT / 'scripts/run_arv2_r298_recovery.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_recovery/R298-20261024-A'
SCHEMA = 'arv2-r298-same-project-recovery-v1'
PROJECT = 38364439
DEADLINE_SECONDS = 300
MAX_BUNDLE = 4 * 1024 * 1024
MAX_OUTPUT = 24 * 1024
NEW_PINS = {
    'scripts/run_arv2_newrule_recovery_continuation_v5.py': 'ab82fc77986e7df072b39cc9011c8002cf58e3fee21f967cb891c6d3111250e0',
    'scripts/arv2_r298_recovery_evidence.py': 'dc41adea9285671d2c39a1ee0afbfa517a3641d9fdaa49a2ea77cc44c4d759d3',
    'scripts/arv2_r298_recovery_remote.py': '114645ff490246c61e1f79f0ef8b321b2eb77f06ef34e1be80e8b9964f4cd19a',
}
SANDBOX = ('(version 1)(allow default)(deny network*)'
    '(deny process-exec (literal "/usr/bin/security"))'
    '(deny file-write* (require-all '
    '(subpath "/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2/artifacts") '
    '(require-not (subpath "/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2/artifacts/analyst_revisions_v2/newrule_recovery/R298-20261024-A"))))')
FALSE_FLAGS = {'point_in_time_proven': False, 'formal_forward_ready': False,
               'paper_or_live_ready': False, 'strategy_result_accepted': False}
FINITE = frozenset(('source', 'context', 'arguments', 'control', 'control_changed',
    'json', 'bound', 'claim', 'evidence', 'child_failed', 'child_output', 'deadline',
    'input_admission', 'compile_failed', 'runtime_failed', 'compile_budget', 'journal', 'unknown_exception'))


class Refused(ValueError):
    pass


class RequestFailed(Refused):
    """Only caller-generated canonical finite failure observation bytes."""


def require(condition, code):
    if not condition:
        raise Refused(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('ascii') + b'\n'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'json')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(Refused('json')))
    require(type(value) is dict and canonical(value) == raw, 'json')
    return value


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'control': str(CONTROL),
        'branch': frozen.BRANCH, 'python': str(frozen.PYTHON), 'project_id': PROJECT,
        'family_sha256': v5.FAMILY_SHA256, 'admission_sha256': v5.ADMISSION_SHA256,
        'source_pins': dict(frozen.SOURCE_PINS), 'v5_pins': dict(v5.NEW_PINS),
        'frozen_caller_sha256': v5.FROZEN_CALLER_SHA256, 'new_pins': dict(NEW_PINS),
        'operations': ['evidence', 'recover'], 'deadline_seconds': DEADLINE_SECONDS,
        'compile_poll_limit': 20, 'compile_interval_seconds': 10,
        'status_poll_limit': 1, 'status_interval_seconds': 60,
        'max_bundle_bytes': MAX_BUNDLE, 'max_output_bytes': MAX_OUTPUT,
        'native_evidence_network_denial': True, 'fresh_package_admission_before_credentials': True,
        'evidence_sandbox_profile': SANDBOX,
        'original_attempt': 1, 'recovery_attempt': 2, 'recover_claim_shared_looks': 1,
        'recover_claim_development_looks': 1, 'candidate_attempt_ceiling': 3,
        'original_attempt_remains_spent': True, 'same_project_only': True,
        'stored_evidence_revalidation_native_network_denied': True,
        'actual_evidence_exit_zero_required_externally': True,
        'actual_recover_exit_zero_required_externally': True, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head,
        'caller_sha256': args.caller_sha256, 'profile_sha256': sha(canonical(profile_record())),
        'project_id': PROJECT}


def remaining(deadline):
    require(time.monotonic() < deadline, 'deadline')
    return deadline - time.monotonic()


def _preflight(args, deadline):
    require(not v5._under_test() and Path(__file__).absolute() == SOURCE
        and args.operation in ('evidence', 'recover', 'evidence-worker', 'evidence-check-worker'), 'context')
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == frozen.PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT, 'context')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and type(args.caller_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.caller_sha256), 'arguments')
    require((args.operation in ('recover', 'evidence-check-worker')) == (args.evidence_sha256 is not None)
        and args.operation.endswith('-worker') == (args.control_fd is not None), 'arguments')
    if args.evidence_sha256 is not None:
        require(type(args.evidence_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.evidence_sha256), 'arguments')
    name = 'scripts/arv2_newrule_execution_environment.py'
    require(helpers._source_digest(ROOT / name) == v5.NEW_PINS[name], 'source')
    from scripts import arv2_newrule_execution_environment as environment
    environment._require_environment()  # Before even the credential-free Git subprocess.
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
        (['branch', '--show-current'], frozen.BRANCH), (['rev-parse', 'HEAD'], args.expected_head),
        (['status', '--porcelain'], '')):
        require(v5._git(command, deadline).decode('ascii').strip() == expected, 'context')
    pins = {**frozen.SOURCE_PINS, **v5.NEW_PINS, **NEW_PINS,
        'scripts/run_arv2_newrule_comparison.py': v5.FROZEN_CALLER_SHA256}
    for relative, digest in pins.items():
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest)
            and digest != '0' * 64 and helpers._source_digest(ROOT / relative) == digest, 'source')
    require(helpers._source_digest(SOURCE) == args.caller_sha256, 'source')
    selected = args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()
    count = v5._git(['cat-file', '-s', selected], deadline).decode('ascii').strip()
    require(re.fullmatch('[1-9][0-9]{0,6}', count) and int(count) <= MAX_BUNDLE, 'source')
    raw = v5._git(['cat-file', 'blob', selected], deadline, int(count))
    require(len(raw) == int(count) and sha(raw) == args.caller_sha256
        and v5._git(['rev-parse', 'HEAD'], deadline).decode('ascii').strip() == args.expected_head
        and v5._git(['status', '--porcelain'], deadline) == b'', 'source')
    remaining(deadline)


def metadata(info):
    return tuple(getattr(info, key, None) for key in ('st_dev', 'st_ino', 'st_mode',
        'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags'))


class Store:
    """Own leaf only; exclusive files retained on every partial failure."""

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
                and metadata(held) == metadata(os.fstat(fd)), 'control')  # APFS entries, not POSIX subdirectories.
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
                and 0 < info.st_size <= MAX_BUNDLE, 'control')
            raw = bytearray()
            while len(raw) <= MAX_BUNDLE:
                chunk = os.read(fd, min(65536, MAX_BUNDLE + 1 - len(raw)))
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
        require(type(value) is dict and 0 < len(raw) <= MAX_BUNDLE, 'bound')
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


def _worker(args, deadline):
    from scripts import arv2_r298_recovery_evidence as evidence
    from scripts import arv2_newrule_execution_environment as environment
    environment.require_safe_environment()
    with Store(inherited=args.control_fd) as store:
        require(store.read('claim.json')[1] == binding(args), 'claim')
        store.write('evidence-start.json', binding(args))
        projected = evidence.reconstruct_projection()
        documents, inventory = evidence.collect_documents()
        report = evidence.validate_documents(documents, projected, inventory=inventory)
        remaining(deadline)
        pin = store.write('evidence.json', {**binding(args), 'report': report,
            'documents': documents, 'inventory': list(inventory)})
        return {'evidence': pin, 'attempt_claim_authenticated': True,
            'project_id': PROJECT, 'provider_request_count': None}


def _check_worker(args, deadline):
    """Revalidate only the new bundle; never call the old fixed collector again."""
    from scripts import arv2_r298_recovery_evidence as evidence
    from scripts import arv2_newrule_execution_environment as environment
    environment.require_safe_environment()
    with Store(inherited=args.control_fd) as store:
        require(store.read('recover-claim.json')[1] == {**binding(args),
            'evidence_sha256': args.evidence_sha256, 'attempt_id': 2,
            'shared_look': 1, 'development_look': 1}, 'claim')
        store.write('evidence-check-start.json', {**binding(args), 'evidence_sha256': args.evidence_sha256})
        raw, bundle = store.read('evidence.json')
        require(sha(raw) == args.evidence_sha256
            and set(bundle) == {*binding(args), 'report', 'documents', 'inventory'}, 'evidence')
        original = store.read('claim.json')[1]
        require(set(original) == set(binding(args)) and type(original['expected_head']) is str
            and re.fullmatch('[0-9a-f]{40}', original['expected_head'])
            and {key: bundle[key] for key in original} == original
            and {key: original[key] for key in original if key != 'expected_head'}
                == {key: binding(args)[key] for key in original if key != 'expected_head'}, 'evidence')
        require(store.read('evidence-parent-completed.json')[1] == {**original,
            'evidence': {'sha256': sha(raw), 'byte_count': len(raw)}}, 'evidence')
        projected = evidence.reconstruct_projection()
        report = evidence.validate_documents(bundle['documents'], projected, inventory=bundle['inventory'])
        require(canonical(report) == canonical(bundle['report']), 'evidence')
        organization = bundle['documents']['organization.json']['organization_id']
        require(type(organization) is str and re.fullmatch('[0-9a-f]{32}', organization), 'evidence')
        remaining(deadline)
        return {'organization_id': organization, 'evidence_sha256': sha(raw),
            'evidence_bytes': len(raw), 'report_sha256': sha(canonical(report))}


def _child(args, store, deadline, *, check=False):
    env = {key: value for key, value in os.environ.items() if key not in ('QC_USER_ID', 'QC_API_TOKEN')}
    command = ['/usr/bin/sandbox-exec', '-p', SANDBOX, str(frozen.PYTHON), '-B', str(SOURCE),
        'evidence-check-worker' if check else 'evidence-worker',
        '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
        '--control-fd', str(store.fd)]
    if check:
        command += ['--evidence-sha256', args.evidence_sha256]
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
            and payload['binding'] == binding(args)
            and payload['operation'] == ('evidence-check-worker' if check else 'evidence-worker')
            and payload['operation_completed'] is True and payload['schema'] == SCHEMA
            and all(payload[key] is False for key in FALSE_FLAGS), 'child_output')
        result = payload['result']
        if check:
            require(type(result) is dict and set(result) == {'organization_id', 'evidence_sha256',
                'evidence_bytes', 'report_sha256'} and result['evidence_sha256'] == args.evidence_sha256
                and type(result['organization_id']) is str and re.fullmatch('[0-9a-f]{32}', result['organization_id'])
                and type(result['evidence_bytes']) is int and 0 < result['evidence_bytes'] <= MAX_BUNDLE
                and type(result['report_sha256']) is str and re.fullmatch('[0-9a-f]{64}', result['report_sha256']), 'child_output')
            store.write('evidence-check-completed.json', {**binding(args),
                **{key: value for key, value in result.items() if key != 'organization_id'},
                'organization_id_sha256': sha(result['organization_id'].encode('ascii'))})
        else:
            # Only metadata crosses the worker boundary; the parent never parses its private bundle.
            require(type(result) is dict and set(result) == {'evidence', 'attempt_claim_authenticated',
                'project_id', 'provider_request_count'} and type(result['evidence']) is dict
                and set(result['evidence']) == {'sha256', 'byte_count'}
                and type(result['evidence']['sha256']) is str and re.fullmatch('[0-9a-f]{64}', result['evidence']['sha256'])
                and type(result['evidence']['byte_count']) is int and 0 < result['evidence']['byte_count'] <= MAX_BUNDLE
                and result['attempt_claim_authenticated'] is True and type(result['project_id']) is int
                and result['project_id'] == PROJECT and result['provider_request_count'] is None, 'child_output')
            store.write('evidence-parent-completed.json', {**binding(args), 'evidence': result['evidence']})
        return result
    finally:
        if process.poll() is None:
            process.kill()  # Only the child created above, never another lane.
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


def _admission(projected, deadline):
    from scripts import arv2_newrule_execution_environment as environment
    from scripts import arv2_newrule_storage_recovery_v4 as recovery
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission
    environment.require_safe_environment()
    value = frozen.prepared_input.october.load_october_order_input_package(frozen.PACKAGE,
        expected_package_sha256=frozen.PACKAGE_SHA256, lineage_path=frozen.LINEAGE,
        expected_lineage_sha256=frozen.LINEAGE_SHA256)
    plan = submission.load_family(value, expected_family_sha256=v5.FAMILY_SHA256,
        expected_new_source_pins=dict(frozen.NEW_SOURCE_PINS),
        expected_host_source_pins={name: frozen.SOURCE_PINS[name] for name in submission.HOST_SOURCE_NAMES})
    with submission._session(plan, v5.FAMILY_SHA256) as (directory, record):
        recovery.require_admission(directory, plan, record, v5.ADMISSION_SHA256)
        item = submission._cell(plan, record, 'R298', 1)[1]
        require(item.record_bytes == projected.record_bytes
            and item.profile_bytes == projected.profile_bytes
            and [(entry.project_path, entry.source_bytes) for entry in item.source_files]
                == [(entry.project_path, entry.source_bytes) for entry in projected.source_files], 'input_admission')
    environment.require_safe_environment()
    remaining(deadline)


def http_context(error, endpoint):
    """No exception stringification, trailing provider reason, or cause inference."""
    from research.quantconnect import QuantConnectError
    from research.analyst_revisions_v2_qc.six_universe_coverage_submission import CoverageQcSubmissionError
    result = {'category': 'unknown', 'http_status': None}
    if type(error) is CoverageQcSubmissionError:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] == 'coverage QC response status or byte bound changed':
            return {'category': 'status_or_bound_refusal', 'http_status': None}
    if type(error) is not QuantConnectError or type(endpoint) is not str:
        return result
    args = BaseException.args.__get__(error)
    if len(args) != 1 or type(args[0]) is not str or len(args[0]) > 4096:
        return result
    prefix = re.escape(endpoint)
    match = re.match(r'\A' + prefix + r' failed \(HTTP ([0-9]{3})\): ', args[0])
    category = 'http_failure'
    if match is None:
        match = re.fullmatch(prefix + r' returned a non-JSON body \(HTTP ([0-9]{3})\)', args[0])
        category = 'http_non_json'
    if match is not None and 100 <= int(match[1]) <= 599:
        return {'category': category, 'http_status': int(match[1])}
    return result


def _recover(args, store, deadline):
    from scripts import arv2_r298_recovery_evidence as evidence
    from scripts import arv2_r298_recovery_remote as remote
    from scripts import arv2_newrule_execution_environment as environment
    store.write('recover-claim.json', {**binding(args), 'evidence_sha256': args.evidence_sha256,
        'attempt_id': 2, 'shared_look': 1, 'development_look': 1})
    authenticated = _child(args, store, deadline, check=True)
    projected = evidence.reconstruct_projection()
    _admission(projected, deadline)  # Fresh generic package/lineage/D15 consumers, not a spent begin/reader.
    environment.require_safe_environment()
    client = environment.guarded_client()
    current, failure, dispatches = {}, {}, 0

    def journal(marker, event):
        remaining(deadline)
        require(type(marker) is str and re.fullmatch('[a-z0-9-]{1,80}', marker)
            and type(event) is dict and set(event) == {'event', 'endpoint', 'sha256'}
            and event['event'] in ('intent', 'observed') and event['endpoint'] in remote.ENDPOINTS
            and type(event['sha256']) is str and re.fullmatch('[0-9a-f]{64}', event['sha256']), 'journal')
        store.write('rpc-' + marker + '-' + event['event'] + '.json', {**binding(args), **event})
        if event['event'] == 'intent':
            current.update(marker=marker, endpoint=event['endpoint'])

    def request(endpoint, payload):
        nonlocal dispatches
        remaining(deadline)
        environment.require_safe_environment()
        require(current.get('endpoint') == endpoint and endpoint in remote.ENDPOINTS, 'journal')
        dispatches += 1  # Application dispatch, not measured server contact.
        try:
            return client.request(endpoint, payload)
        except Exception as error:
            observed = {'intent_marker': current['marker'],
                'endpoint': endpoint, 'application_dispatch_count': dispatches,
                **http_context(error, endpoint), 'provider_request_count': None}
            pin = store.write('rpc-' + current['marker'] + '-failure.json', {**binding(args), **observed})
            failure.update(observed, failure_file=pin)
            raise

    runner = remote.RemoteRecovery(projected, authenticated['organization_id'], request, journal)
    try:
        result = _workflow(runner, store, projected, deadline)
    except BaseException:
        if failure:
            raise RequestFailed(canonical(failure)) from None
        raise
    return {**result, 'application_dispatch_count': dispatches, 'provider_request_count': None}


def _workflow(runner, store, projected, deadline):
    initial = runner.inspect()
    store.write('initial-inventory.json', initial)
    completed = runner.complete(initial)
    store.write('completed-inventory.json', completed)
    compiled = runner.compile_once(completed)
    store.write('compile-receipt.json', compiled)
    for index in range(20):
        require(remaining(deadline) > 10, 'deadline')
        time.sleep(10)
        state = runner.poll_compile(compiled['compile_id'], index)
        store.write(f'compile-status-{index:02d}.json', state)
        require(state['state'] != 'BuildError', 'compile_failed')
        if state['state'] == 'BuildSuccess':
            break
    else:
        raise Refused('compile_budget')
    # Reserve the fixed non-busy-poll wait before dispatching a launch.
    _admission(projected, deadline)
    require(remaining(deadline) > 90, 'deadline')
    launched = runner.launch_once(compiled['compile_id'])
    store.write('launch-receipt.json', launched)
    if launched.get('state') == 'wait':
        _admission(projected, deadline)
        return {'terminal': 'capacity_wait', 'project_id': PROJECT, 'compile_id': compiled['compile_id']}
    require(remaining(deadline) > 60, 'deadline')
    time.sleep(60)
    status = runner.read_status(launched, 0)
    store.write('own-status.json', status)
    require(status['status'] != 'Runtime Error', 'runtime_failed')
    _admission(projected, deadline)
    return {'terminal': 'own_status_observed', 'launch': launched, 'status': status}


def failure_observation(error):
    if type(error) is not RequestFailed:
        return None
    args = BaseException.args.__get__(error)
    require(len(args) == 1 and type(args[0]) is bytes and len(args[0]) <= 2048, 'journal')
    value = parse(args[0])
    from scripts import arv2_r298_recovery_remote as remote
    require(set(value) == {'intent_marker', 'endpoint', 'application_dispatch_count',
        'category', 'http_status', 'provider_request_count', 'failure_file'}
        and type(value['intent_marker']) is str and re.fullmatch('[a-z0-9-]{1,80}', value['intent_marker'])
        and value['endpoint'] in remote.ENDPOINTS
        and type(value['application_dispatch_count']) is int and 1 <= value['application_dispatch_count'] <= 256
        and value['category'] in ('unknown', 'status_or_bound_refusal', 'http_failure', 'http_non_json')
        and (value['http_status'] is None or (type(value['http_status']) is int and 100 <= value['http_status'] <= 599))
        and value['provider_request_count'] is None
        and type(value['failure_file']) is dict and set(value['failure_file']) == {'sha256', 'byte_count'}
        and type(value['failure_file']['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['failure_file']['sha256'])
        and type(value['failure_file']['byte_count']) is int and 0 < value['failure_file']['byte_count'] <= MAX_BUNDLE, 'journal')
    return value


def finite_failure(error):
    if type(error) is RequestFailed:
        return 'remote_request_refused'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    for module_name, class_name in (('scripts.arv2_r298_recovery_evidence', 'EvidenceRefused'),
        ('scripts.arv2_r298_recovery_remote', 'RecoveryError')):
        module = sys.modules.get(module_name)
        if module is not None and type(error) is vars(module).get(class_name):
            return 'evidence' if class_name == 'EvidenceRefused' else 'remote_refused'
    return 'unknown_exception'


def _execute(args, deadline):
    _preflight(args, deadline)
    from scripts import arv2_newrule_execution_environment as environment
    environment.require_safe_environment()
    if args.operation == 'evidence-worker':
        return _worker(args, deadline)
    if args.operation == 'evidence-check-worker':
        return _check_worker(args, deadline)
    with Store(create=args.operation == 'evidence') as store:
        if args.operation == 'evidence':
            store.write('claim.json', binding(args))
            result = _child(args, store, deadline)
        else:
            result = _recover(args, store, deadline)
        _preflight(args, deadline)
        remaining(deadline)
        pin = store.write(args.operation + '-report.json', {**binding(args), 'result': result,
            'operation_completed': True, **FALSE_FLAGS})
        return {'report': pin, 'result': result}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('evidence', 'recover', 'evidence-worker', 'evidence-check-worker'))
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--evidence-sha256')
    parser.add_argument('--control-fd', type=int)
    args = parser.parse_args(argv)
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        with helpers._alarm(deadline):
            _preflight(args, deadline)
            from scripts import arv2_newrule_execution_environment as environment
            environment._bootstrap_cli_logging()
            result = _execute(args, deadline)
            payload = canonical({'schema': SCHEMA, 'operation': args.operation,
                'binding': binding(args), 'result': result, 'operation_completed': True, **FALSE_FLAGS})
            require(len(payload) <= MAX_OUTPUT, 'bound')
            print(payload.decode('ascii'))  # Exact canonical JSON + second LF.
            return 0
    except BaseException as error:
        try:
            observation = failure_observation(error)
        except BaseException:
            observation = None
        print(canonical({'schema': SCHEMA, 'operation': args.operation,
            'operation_completed': False, 'failure_code': finite_failure(error),
            'failure_observation': observation,
            'attempt_consumption': 'consumed_or_ambiguous_no_retry', **FALSE_FLAGS}).decode('ascii'))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
