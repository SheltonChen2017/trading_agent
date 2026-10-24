"""One separately authorized R298 A6 pinned-access recovery.

A1-A5 remain spent. This additive contract consumes only the one new expressly
authorized sixth attempt, never another allowance. Source-binding CLI arguments are not
authority: an exact owner decision/review waiver and clean committed run freeze
must precede use. No old control, observation or operational entrypoint is read
or invoked. Fresh family and D15 admission checks remain mandatory.
"""
from __future__ import annotations

import argparse
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
from scripts import run_arv2_r298_final_recovery as a3
from scripts import arv2_r298_access_recovery_remote as remote

previous, v5, frozen, helpers = a3.previous, a3.v5, a3.frozen, a3.helpers
canonical, parse, sha, metadata = a3.canonical, a3.parse, a3.sha, a3.metadata
Refused, require, remaining = a3.Refused, a3.require, a3.remaining
SOURCE = ROOT / 'scripts/run_arv2_r298_access_recovery.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_access_recovery/R315-20261024-A'
SCHEMA = 'arv2-r298-access-recovery-v1'
PROJECT = remote.PROJECT_ID
BACKTEST_NAME = f'{remote.PROJECT_NAME} A6 {remote.PROJECTION_SHA256[:8]}'
DEADLINE_SECONDS, MAX_OUTPUT, MAX_DISPATCH = 600, 24 * 1024, 64
FALSE_FLAGS = dict(a3.FALSE_FLAGS)
WORKERS = ('admission-initial-worker', 'admission-launch-worker', 'admission-final-worker')
NEW_PINS = {
    'scripts/run_arv2_r298_owner_recovery.py': '02a2464c3dc04eea24e75791e9f7f4d7d33cd6febacacad2b9443147e53a9a41',
    'scripts/arv2_r298_privacy_recovery_remote.py': '5be59e13e760c6e7deacdf5fe9296968ad40a3d4140a9e544ec3de7d41b6a5fd',
    'scripts/run_arv2_r298_privacy_recovery.py': '98ce1ee2a2d8a54523e383d9ca578575ad2c2510a171f2d772e2144de92d0e98',
    'scripts/arv2_r298_access_recovery_remote.py': '0659ddcadd0f2c138c08d88fd88ea3f436db8113ad9f0c646f980f0641db6709',
    'scripts/arv2_r298_collaborator_access.py': '57333e2d6932f3b75bb42bc59214ebda2ce9afdf65b9054b7edc7ee5cbd37d93',
    'scripts/run_arv2_r298_post_mia_recovery.py': '6c592c76e4b35b1b496907f532221c4f49a20ae536a387968fef873f2f362706',
    'scripts/arv2_r298_owner_recovery_remote.py': '570bdf830aa8b06e68c99a1c6a1c19662837d965e18c793a62e8ea965020b85b',
    'scripts/run_arv2_r298_final_recovery.py': 'ba555b6f639555285bb3022a8c53a963b80794b702377064d18762bb576cb783',
    'scripts/arv2_r298_final_recovery_remote.py': 'e9e0b9da61e04da7b6b97d30d95c2e51d00b25019098f51eef4d7930b41c60f5',
}
OLD_CONTROLS = (
    ROOT / 'artifacts/analyst_revisions_v2/newrule_privacy_recovery/R313-20261024-A',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_lock_access/R314-20261024-A',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_owner_recovery/R312-20261024-A',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_post_mia_recovery/R311-20261024-A',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_idleness/R311-20261024-A',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_access_shape/R312-20261024-A',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_collaborator_records/R312-20261024-A',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_recovery/R298-20261024-A',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_final_recovery/R310-20261024-A',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_reconciliation/R310-20261024-A',
)
SANDBOX = ('(version 1)(allow default)(deny network*)'
    '(deny process-exec (literal "/usr/bin/security"))'
    + ''.join(f'(deny file-read* (subpath "{path}"))' for path in OLD_CONTROLS)
    + '(deny file-write* (require-all '
    f'(subpath "{ROOT / "artifacts"}") '
    f'(require-not (subpath "{CONTROL}"))))')


FINITE = a3.FINITE | frozenset(('client',))


def finite_code(error):
    if type(error) is remote.RecoveryError:
        return 'remote_refused'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    return 'unknown_exception'


def _validate_failure(value):
    require(type(value) is dict and set(value) == {'code', 'helper_code', 'predicate',
        'last_stage', 'intent_marker', 'endpoint', 'last_event', 'application_dispatch_count',
        'category', 'http_status', 'provider_request_count'}, 'journal')
    require(value['code'] in (*FINITE, 'unknown_exception', 'remote_refused')
        and value['helper_code'] in (*remote.FINITE_CODES, 'unknown')
        and value['predicate'] == remote.OWNERSHIP_PREDICATES.get(value['helper_code'])
        and value['last_stage'] in a3.STAGES
        and type(value['application_dispatch_count']) is int
        and 0 <= value['application_dispatch_count'] <= MAX_DISPATCH
        and value['category'] in ('unknown', 'status_or_bound_refusal', 'http_failure', 'http_non_json')
        and (value['http_status'] is None or (type(value['http_status']) is int
            and 100 <= value['http_status'] <= 599))
        and value['provider_request_count'] is None, 'journal')
    if value['intent_marker'] is None:
        require(value['endpoint'] is None and value['last_event'] is None
            and value['application_dispatch_count'] == 0, 'journal')
    else:
        require(type(value['intent_marker']) is str
            and re.fullmatch('[a-z0-9-]{1,80}', value['intent_marker'])
            and value['endpoint'] in remote.ENDPOINTS
            and value['last_event'] in ('intent', 'observed', 'failure'), 'journal')


def _validate_request(endpoint, payload):
    """Exact fixed-project request shapes; no delete, force or alternative source."""
    require(type(endpoint) is str and endpoint in remote.ENDPOINTS
        and type(payload) is dict and type(payload.get('projectId')) is int
        and payload['projectId'] == PROJECT, 'client')
    extra = {
        'projects/read': set(), 'projects/collaboration/read': set(),
        'projects/collaboration/lock/acquire': {'codeSourceId'},
        'projects/nodes/read': set(), 'files/read': {'codeSourceId'},
        'files/create': {'name', 'content', 'codeSourceId'},
        'files/update': {'name', 'content', 'codeSourceId'}, 'compile/create': set(),
        'compile/read': {'compileId'}, 'backtests/list': {'includeStatistics'},
        'backtests/create': {'compileId', 'backtestName'},
    }
    require(set(payload) == {'projectId'} | extra[endpoint], 'client')
    if 'codeSourceId' in payload:
        require(type(payload['codeSourceId']) is str
            and payload['codeSourceId'] == remote.CODE_SOURCE_ID, 'client')
    if 'name' in payload:
        require(type(payload['name']) is str and payload['name'] in remote.SOURCE_NAMES
            and type(payload['content']) is str and payload['content'].isascii()
            and len(payload['content']) <= 64000, 'client')
    if 'compileId' in payload:
        remote._cloud_id(payload['compileId'])
    if 'backtestName' in payload:
        require(type(payload['backtestName']) is str and payload['backtestName'] == BACKTEST_NAME, 'client')
    if 'includeStatistics' in payload:
        require(payload['includeStatistics'] is False, 'client')


class OwnerClient:
    """Narrow new boundary; leaves the frozen environment allowlist unchanged."""
    __slots__ = ('__api',)

    def __init__(self):
        from scripts import arv2_newrule_execution_environment as environment
        from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
        environment.require_safe_environment()
        api = old._client()
        environment.require_safe_environment()
        self._check(api)
        self.__api = api

    def __repr__(self):
        return '<PinnedAccessR298Client>'

    @staticmethod
    def _check(api):
        from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
        require(type(api) is old.QuantConnectClient and api._base_url == old.API_BASE
            and api._transport is old.coverage._bounded_transport
            and type(api._timeout) in (int, float) and api._timeout == 30, 'client')

    def request(self, endpoint, payload):
        from scripts import arv2_newrule_execution_environment as environment
        environment.require_safe_environment()
        self._check(self.__api)
        _validate_request(endpoint, payload)
        return self.__api.request(endpoint, payload)


def selected_pins():
    return {**frozen.SOURCE_PINS, **v5.NEW_PINS, **previous.NEW_PINS,
        **a3.NEW_PINS, **NEW_PINS,
        'scripts/run_arv2_newrule_comparison.py': v5.FROZEN_CALLER_SHA256}


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'control': str(CONTROL),
        'branch': frozen.BRANCH, 'python': str(frozen.PYTHON), 'project_id': PROJECT,
        'attempt_id': 6, 'additional_attempts': 1, 'ordinary_attempt_ceiling': 3,
        'owner_additional_attempt_required': True, 'independent_review_or_exact_waiver_required': True,
        'shared_look': 1, 'development_look': 1, 'backtest_name': BACKTEST_NAME,
        'source_pins': selected_pins(), 'family_sha256': v5.FAMILY_SHA256,
        'manual_run_id': remote.MANUAL_BACKTEST_ID, 'manual_run_name': remote.MANUAL_BACKTEST_NAME,
        'code_source_id': remote.CODE_SOURCE_ID, 'manual_run_excluded_from_candidate': True,
        'spent_predecessor_contract': 'arv2-r298-privacy-recovery-v1',
        'privacy_boundary': 'authenticated_pinned_owner_org_and_dedicated_collaborator_acl',
        'access_policy': 'arv2-r298-collaborator-access-v1',
        'reused_environment_label': 'same_observed_a5_code_source_id_not_attempt_identity',
        'owner_row_sha256': remote.access.OWNER_ROW_SHA256,
        'extra_row_sha256': remote.access.A5_ROW_SHA256,
        'old_mia_row_accepted': False,
        'privacy_basis': 'documented_private_default_plus_no_sharing_operations',
        'external_manual_backtest_make_public_observation_required_before_freeze': True,
        'project_public_field_required': False, 'missing_public_means_private': False,
        'historical_or_global_privacy_proven': False, 'sharing_operation_allowed': False,
        'immediate_terminal_create_receipt_retained': True,
        'immediate_terminal_create_status_poll': False,
        'owner_exclusive_handoff_required': True, 'edit_lock_is_continuous_ownership_proof': False,
        'admission_sha256': v5.ADMISSION_SHA256, 'projection_sha256': remote.PROJECTION_SHA256,
        'worker_operations': list(WORKERS), 'native_sandbox': SANDBOX,
        'deadline_seconds': DEADLINE_SECONDS, 'max_application_dispatches': MAX_DISPATCH,
        'compile_poll_limit': 20, 'compile_interval_seconds': 10,
        'prelaunch_reserve_seconds': 90, 'status_poll_limit': 1, 'status_interval_seconds': 60,
        'max_output_bytes': MAX_OUTPUT, 'actual_parent_exit_zero_required': True,
        'prior_no_launch_evidence': 'section313_A5_finite_actual_exit_and_frozen_source_not_replayed',
        'old_a2_a3_reconciliation_control_reads': False,
        'fresh_family_and_d15_admission_reads': True, 'a1_a2_a3_a4_a5_remain_spent': True,
        'automatic_retry': False, 'same_project_only': True, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head,
        'caller_sha256': args.caller_sha256, 'profile_sha256': sha(canonical(profile_record())),
        'project_id': PROJECT}


def claim(args):
    return {**binding(args), 'attempt_id': 6, 'shared_look': 1, 'development_look': 1,
        'old_attempts_remain_spent': True}


def _preflight(args, deadline):
    require(not v5._under_test() and Path(__file__).absolute() == SOURCE
        and args.operation in ('recover', *WORKERS), 'context')
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == frozen.PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT, 'context')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and a3._digest(args.caller_sha256)
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
    for relative, digest in selected_pins().items():
        require(a3._digest(digest) and digest != '0' * 64
            and helpers._source_digest(ROOT / relative) == digest, 'source')
    require(helpers._source_digest(SOURCE) == args.caller_sha256, 'source')
    selected = args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()
    count = v5._git(['cat-file', '-s', selected], deadline).decode('ascii').strip()
    require(re.fullmatch('[1-9][0-9]{0,6}', count) and int(count) <= a3.MAX_FILE, 'source')
    raw = v5._git(['cat-file', 'blob', selected], deadline, int(count))
    require(len(raw) == int(count) and sha(raw) == args.caller_sha256
        and v5._git(['rev-parse', 'HEAD'], deadline).decode('ascii').strip() == args.expected_head
        and v5._git(['status', '--porcelain'], deadline) == b'', 'source')
    remaining(deadline)


class Store(a3.Store):
    """Fresh fixed leaf; inherited byte I/O has no old CONTROL reference."""

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
                and all(re.fullmatch(r'[a-zA-Z0-9_.-]+\.json', name) for name in names)
                and held.st_nlink == 2 + len(names)
                and metadata(held) == metadata(os.fstat(fd)), 'control')
        finally:
            os.close(fd)


def code_running_observation(response):
    rows = response.get('projects')
    remote._require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict,
        'project_shape')
    row = rows[0]
    remote._require(type(row.get('projectId')) is int and row['projectId'] == PROJECT,
        'owned_project_id')
    present = 'codeRunning' in row
    value = row.get('codeRunning')
    kind = ('missing' if not present else 'null' if value is None else
        {bool: 'boolean', int: 'integer', float: 'number', str: 'string',
         list: 'array', dict: 'object'}.get(type(value), 'unsupported'))
    return {'present': present, 'kind': kind,
        'boolean_value': value if type(value) is bool else None}


def _validate_code_running(value):
    require(type(value) is dict and set(value) == {'present', 'kind', 'boolean_value'}
        and type(value['present']) is bool and type(value['kind']) is str, 'journal')
    kind, boolean = value['kind'], value['boolean_value']
    require((kind == 'missing' and value['present'] is False and boolean is None)
        or (value['present'] is True and ((kind == 'boolean' and type(boolean) is bool)
        or (kind in ('null', 'integer', 'number', 'string', 'array', 'object', 'unsupported')
            and boolean is None))), 'journal')


def _worker(args, deadline):
    from scripts import arv2_r298_recovery_evidence as evidence
    from scripts import arv2_newrule_execution_environment as environment
    environment.require_safe_environment()
    with Store(inherited=args.control_fd) as store:
        require(store.read('claim.json')[1] == claim(args), 'claim')
        store.write(args.operation + '-start.json', claim(args))
        projected = evidence.reconstruct_projection()
        previous._admission(projected, deadline)
        remaining(deadline)
        return {'admission_authenticated': True, 'projection_sha256': projected.projection_sha256}


def _child(args, store, deadline, operation):
    require(operation in WORKERS, 'arguments')
    env = {key: value for key, value in os.environ.items() if key not in ('QC_USER_ID', 'QC_API_TOKEN')}
    command = ['/usr/bin/sandbox-exec', '-p', SANDBOX, str(frozen.PYTHON), '-B', str(SOURCE), operation,
        '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
        '--control-fd', str(store.fd)]
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
        result = {'admission_authenticated': True, 'projection_sha256': remote.PROJECTION_SHA256}
        require(type(payload['result']) is dict and canonical(payload['result']) == canonical(result), 'child_output')
        store.write(operation + '-completed.json', {**binding(args), 'result': result})
        return result
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


class ObservedFailure(Refused):
    """Finite canonical context only; never carries raw provider text."""


def _failure(error, state):
    result = {'code': finite_code(error), **remote.finite_error(error),
        'last_stage': state['last_stage'], 'intent_marker': state['intent_marker'],
        'endpoint': state['endpoint'], 'last_event': state['last_event'],
        'application_dispatch_count': state['application_dispatch_count'],
        'category': state['category'], 'http_status': state['http_status'],
        'provider_request_count': None}
    _validate_failure(result)
    observation = state.get('code_running')
    if observation is not None:
        _validate_code_running(observation)
    launch, status = state.get('launch_receipt'), state.get('status_receipt')
    _validate_receipts(launch, status)
    return {**result, 'code_running': observation,
        'launch_receipt': launch, 'status_receipt': status}


def failure_observation(error):
    if type(error) is not ObservedFailure:
        return None
    args = BaseException.args.__get__(error)
    require(len(args) == 1 and type(args[0]) is bytes and len(args[0]) <= 4096, 'journal')
    value = parse(args[0])
    extra = {'code_running', 'launch_receipt', 'status_receipt'}
    require(extra <= set(value), 'journal')
    _validate_failure({key: item for key, item in value.items() if key not in extra})
    if value['code_running'] is not None:
        _validate_code_running(value['code_running'])
    _validate_receipts(value['launch_receipt'], value['status_receipt'])
    return value


def _validate_receipts(launch, status):
    """Exact finite receipt identities only, including unsuccessful terminal states."""
    if launch is None:
        require(status is None, 'bound')
        return
    fields = {'project_id', 'compile_id', 'backtest_id', 'backtest_name', 'status', 'projection_sha256'}
    for value in (launch,) if status is None else (launch, status):
        require(type(value) is dict and set(value) == fields
            and type(value['project_id']) is int and value['project_id'] == PROJECT
            and value['projection_sha256'] == remote.PROJECTION_SHA256
            and value['backtest_name'] == BACKTEST_NAME
            and value['status'] in ('In Queue...', 'In Progress...', 'Completed.', 'Runtime Error'), 'bound')
        remote._cloud_id(value['compile_id'])
        remote._cloud_id(value['backtest_id'])
        require(value['backtest_id'] != remote.MANUAL_BACKTEST_ID, 'bound')
    if status is not None:
        require(canonical({**status, 'status': launch['status']}) == canonical(launch), 'bound')


def _validate_result(value):
    require(type(value) is dict and value.get('terminal') in
        ('capacity_wait', 'own_status_observed', 'create_terminal_observed'), 'bound')
    common = {'terminal', 'application_dispatch_count', 'provider_request_count', 'code_running'}
    require(type(value.get('application_dispatch_count')) is int
        and 1 <= value['application_dispatch_count'] <= MAX_DISPATCH
        and value.get('provider_request_count') is None, 'bound')
    _validate_code_running(value.get('code_running'))
    require(value['code_running'] == {'present': True, 'kind': 'boolean', 'boolean_value': False}, 'bound')
    if value['terminal'] == 'capacity_wait':
        require(set(value) == common | {'project_id', 'compile_id'}
            and type(value['project_id']) is int and value['project_id'] == PROJECT, 'bound')
        remote._cloud_id(value['compile_id'])
        return
    require(set(value) == common | {'launch', 'status'}, 'bound')
    launch, status = value['launch'], value['status']
    require(type(launch) is dict and type(status) is dict, 'bound')
    _validate_receipts(launch, status)
    if value['terminal'] == 'create_terminal_observed':
        require(launch['status'] == 'Completed.' and canonical(status) == canonical(launch), 'bound')
    else:
        require(launch['status'] in ('In Queue...', 'In Progress...')
            and status['status'] in ('In Queue...', 'In Progress...', 'Completed.'), 'bound')


def _safe_binding(args):
    if (type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
            and a3._digest(args.caller_sha256)):
        return binding(args)
    return None


def validate_output(raw, actual_exit, args):
    """Pure external envelope validation; separately require empty stderr.

    The report pin must bind the exact reconstructed canonical report, not just
    a plausible digest. This does not reread artifacts or establish actual exit;
    that fact must come from the bounded external process observer.
    """
    require(type(actual_exit) is int and actual_exit in (0, 2)
        and args.operation == 'recover' and _safe_binding(args) is not None, 'bound')
    require(type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT and raw.endswith(b'\n\n'), 'bound')
    value = parse(raw[:-1])
    common = {'schema', 'operation', 'binding', 'operation_completed', *FALSE_FLAGS}
    require(value.get('schema') == SCHEMA and value.get('operation') == 'recover'
        and type(value.get('binding')) is dict and canonical(value['binding']) == canonical(binding(args))
        and all(value.get(key) is False for key in FALSE_FLAGS), 'bound')
    if actual_exit == 0:
        require(set(value) == common | {'result'} and value['operation_completed'] is True
            and type(value['result']) is dict and set(value['result']) == {'report', 'result'}, 'bound')
        result, pin = value['result']['result'], value['result']['report']
        _validate_result(result)
        require(type(pin) is dict and set(pin) == {'sha256', 'byte_count'}
            and a3._digest(pin['sha256']) and type(pin['byte_count']) is int, 'bound')
        report = canonical({**binding(args), 'result': result, 'operation_completed': True, **FALSE_FLAGS})
        require(pin['sha256'] == sha(report) and pin['byte_count'] == len(report), 'bound')
    else:
        require(set(value) == common | {'failure_code', 'failure_observation', 'attempt_consumption'}
            and value['operation_completed'] is False
            and type(value['failure_code']) is str
            and value['failure_code'] in (*FINITE, 'unknown_exception', 'remote_refused')
            and value['attempt_consumption'] == 'consumed_or_ambiguous_no_retry', 'bound')
        if value['failure_observation'] is not None:
            observation = failure_observation(ObservedFailure(canonical(value['failure_observation'])))
            require(observation['code'] == value['failure_code'], 'bound')
    return value


def _raise_observed(error, state, store, args):
    observation = _failure(error, state)
    try:
        store.write('failure.json', {**binding(args), 'observation': observation, **FALSE_FLAGS})
    except BaseException:
        pass  # Retain finite in-memory evidence even if durable publication fails.
    raise ObservedFailure(canonical(observation)) from None


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
    if launched.get('state') != 'wait':
        _validate_receipts(launched, None)
        state['launch_receipt'] = launched
    store.write('launch-receipt.json', launched)
    if launched.get('state') == 'wait':
        state['last_stage'] = 'admission_final'
        _child(args, store, deadline, 'admission-final-worker')
        return {'terminal': 'capacity_wait', 'project_id': PROJECT, 'compile_id': compiled['compile_id']}
    require(launched['status'] != 'Runtime Error', 'runtime_failed')
    if launched['status'] == 'Completed.':
        state['status_receipt'] = launched
        state['last_stage'] = 'admission_final'
        _child(args, store, deadline, 'admission-final-worker')
        return {'terminal': 'create_terminal_observed', 'launch': launched, 'status': launched}
    state['last_stage'] = 'status_wait'
    require(remaining(deadline) > 60, 'deadline')
    time.sleep(60)
    state['last_stage'] = 'status'
    status = runner.read_status(launched, 0)
    _validate_receipts(launched, status)
    state['status_receipt'] = status
    store.write('own-status.json', status)
    require(status['status'] != 'Runtime Error', 'runtime_failed')
    state['last_stage'] = 'admission_final'
    _child(args, store, deadline, 'admission-final-worker')
    return {'terminal': 'own_status_observed', 'launch': launched, 'status': status}


def _recover(args, store, deadline, state):
    from scripts import arv2_r298_recovery_evidence as evidence
    from scripts import arv2_newrule_execution_environment as environment
    store.write('claim.json', claim(args))
    projected = evidence.reconstruct_projection()
    state['last_stage'] = 'admission_initial'
    _child(args, store, deadline, 'admission-initial-worker')
    state['last_stage'] = 'credentials'
    environment.require_safe_environment()
    client = OwnerClient()

    def journal(marker, event):
        remaining(deadline)
        require(type(marker) is str and re.fullmatch('[a-z0-9-]{1,80}', marker)
            and type(event) is dict and set(event) == {'event', 'endpoint', 'sha256'}
            and event['event'] in ('intent', 'observed') and event['endpoint'] in remote.ENDPOINTS
            and a3._digest(event['sha256']), 'journal')
        store.write('rpc-' + marker + '-' + event['event'] + '.json', {**binding(args), **event})
        state.update(intent_marker=marker, endpoint=event['endpoint'], last_event=event['event'])

    def request(endpoint, payload):
        remaining(deadline)
        environment.require_safe_environment()
        require(state['endpoint'] == endpoint and state['last_event'] == 'intent'
            and endpoint in remote.ENDPOINTS and state['application_dispatch_count'] < MAX_DISPATCH, 'journal')
        state['application_dispatch_count'] += 1  # Not measured provider contact.
        try:
            return client.request(endpoint, payload)
        except BaseException as error:
            state.update(previous.http_context(error, endpoint))
            state['last_event'] = 'failure'
            store.write('rpc-' + state['intent_marker'] + '-failure.json', {**binding(args),
                'intent_marker': state['intent_marker'], 'endpoint': endpoint,
                'application_dispatch_count': state['application_dispatch_count'],
                'category': state['category'], 'http_status': state['http_status'], 'provider_request_count': None})
            raise

    def observe(marker, observation):
        require(state['endpoint'] == 'projects/read' and state['intent_marker'] == marker
            and state['last_event'] == 'observed', 'journal')
        _validate_code_running(observation)
        state['code_running'] = parse(canonical(observation))
        store.write('idle-' + marker + '.json', {**binding(args), 'observation': observation})

    state['last_stage'] = 'construct'
    runner = remote.OwnerRecovery(projected, remote.ORGANIZATION_SHA256, request, journal, observe)
    result = _workflow(args, runner, store, deadline, state)
    return {**result, 'application_dispatch_count': state['application_dispatch_count'],
        'provider_request_count': None, 'code_running': state['code_running']}


def _execute(args, deadline):
    _preflight(args, deadline)
    from scripts import arv2_newrule_execution_environment as environment
    environment.require_safe_environment()
    if args.operation in WORKERS:
        return _worker(args, deadline)
    with Store(create=True) as store:
        state = {**a3._new_state(), 'code_running': None}
        try:
            result = _recover(args, store, deadline, state)
            state['last_stage'] = 'report'
            _preflight(args, deadline)
            remaining(deadline)
            pin = store.write('report.json', {**binding(args), 'result': result,
                'operation_completed': True, **FALSE_FLAGS})
            return {'report': pin, 'result': result}
        except BaseException as error:
            _raise_observed(error, state, store, args)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('recover', *WORKERS))
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
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
        print(canonical({'schema': SCHEMA, 'operation': args.operation, 'binding': _safe_binding(args),
            'operation_completed': False, 'failure_code': observation['code'] if observation else finite_code(error),
            'failure_observation': observation, 'attempt_consumption': 'consumed_or_ambiguous_no_retry',
            **FALSE_FLAGS}).decode('ascii'))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
