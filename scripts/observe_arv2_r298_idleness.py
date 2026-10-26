"""One current R298 metadata observation, not recovery or a retry command.

This observes the state after the separately documented owner-session action;
there is no before measurement or causal claim. Preparation and source bindings
are not operational authority. A separate committed decision must bind this
source/profile/clean HEAD and externally observed exit plus output. A1/A2/A3
remain spent. No file, capacity, compile, launch or session-control API exists.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
SOURCE = ROOT / 'scripts/observe_arv2_r298_idleness.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_idleness/R311-20261024-A'
PYTHON = Path('/Users/sheltonchen/.venvs/trading_agent-py313/bin/python')
BRANCH = 'codex/strategy-analyst-revisions-v2'
SCHEMA = 'arv2-r298-idleness-observation-v1'
PROJECT = 38364439
PROJECT_NAME = 'ARV2 R298 NEWRULE SIX OFF 2021 OCT2026'
ORGANIZATION_SHA256 = 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
DEADLINE_SECONDS = 60
MAX_OUTPUT = 16 * 1024
ENDPOINTS = ('projects/read', 'backtests/list')
# Selected direct credential/transport boundaries only, not all import or
# interpreter integrity. No dependency pin is discovered/refreshed at runtime.
SOURCE_PINS = {
    'scripts/arv2_newrule_execution_environment.py': 'bacf030e82b309111d8e7788991880860620f6d876bbd750246345c95d7c3194',
    'research/quantconnect.py': '7a12fdb68194ee10f6e8c3d7c0fc49c08b34166d056bd5ea2a72937dd03be373',
    'research/analyst_revisions_v2_qc/newrule_comparison_submission.py': 'cfd2456f2835bb1a4d2c04d6bb60a633b537a2af276a478ad3bfa5f2bc348d4f',
    'research/analyst_revisions_v2_qc/six_universe_coverage_submission.py': 'e511e04eeadb5a667b7ecee361dcac3de31d6323a0d64b1ea0b42f2879aab62b',
    'research/analyst_revisions_v2_qc/formal_qc_transport.py': 'b8c332eda827aeaee23f0dbbddcc96dbd269c82c996812a8a31fe2a4fec62ac4',
}
FALSE_FLAGS = {'point_in_time_proven': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False, 'strategy_result_accepted': False,
    'operational_retry_authority': False}
STAGES = ('preflight', 'claim', 'credentials', 'project', 'backtests', 'postflight', 'report')
FINITE = frozenset(('arguments', 'context', 'source', 'deadline', 'claim', 'control',
    'control_changed', 'bound', 'json', 'dispatch', 'response_shape', 'response_refused',
    'project_shape', 'project_id', 'organization', 'name', 'language', 'owner',
    'private', 'collaborators', 'backtest_shape', 'backtest_count', 'backtest_project'))
STATUS_LABELS = ('In Queue...', 'In Progress...', 'Completed.', 'Runtime Error',
    'Cancelled', 'Canceled', 'Stopped')


class Refused(ValueError):
    """Fixed diagnostic category; never a remote body or exception message."""


def require(condition, code):
    if not condition:
        raise Refused(code)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
            ensure_ascii=True, allow_nan=False).encode('ascii') + b'\n'
    except (TypeError, ValueError, UnicodeError):
        raise Refused('json') from None


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def remaining(deadline):
    require(time.monotonic() < deadline, 'deadline')
    return deadline - time.monotonic()


def _metadata(info):
    return tuple(getattr(info, key, None) for key in ('st_dev', 'st_ino', 'st_mode',
        'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_flags'))


def _source_digest(path):
    require(path.is_relative_to(ROOT) and path.resolve() == path, 'source')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= 4 * 1024 * 1024, 'source')
        raw = bytearray()
        while len(raw) <= info.st_size:
            chunk = os.read(fd, min(65536, info.st_size + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        require(len(raw) == info.st_size and _metadata(info) == _metadata(os.fstat(fd))
            == _metadata(os.stat(path, follow_symlinks=False)), 'source')
        return sha(raw)
    finally:
        os.close(fd)


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': str(PYTHON),
        'control': str(CONTROL), 'project_id': PROJECT, 'organization_sha256': ORGANIZATION_SHA256,
        'purpose': 'current_idleness_after_separately_documented_owner_session_action',
        'source_pins': dict(SOURCE_PINS), 'endpoints': list(ENDPOINTS),
        'deadline_seconds': DEADLINE_SECONDS, 'max_application_dispatches': 2,
        'max_output_bytes': MAX_OUTPUT, 'automatic_retry': False,
        'before_measurement_available': False, 'causal_diagnosis': False,
        'actual_exit_zero_required_externally': True, 'a1_a2_a3_remain_spent': True,
        'shared_look': 0, 'development_look': 0, 'infrastructure_look': 0,
        **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head,
        'caller_sha256': args.caller_sha256, 'profile_sha256': sha(canonical(profile_record())),
        'project_id': PROJECT}


def _git(arguments, deadline, limit=65536):
    child_env = {key: value for key, value in os.environ.items()
        if key not in ('QC_USER_ID', 'QC_API_TOKEN')}
    result = subprocess.run(['/usr/bin/git', *arguments], cwd=ROOT,
        stdin=subprocess.DEVNULL, capture_output=True, check=False,
        timeout=min(3, remaining(deadline)), env=child_env)
    require(type(result.returncode) is int and result.returncode == 0
        and result.stderr == b'' and type(result.stdout) is bytes
        and len(result.stdout) <= limit, 'context')
    return result.stdout


def _preflight(args, deadline):
    require('pytest' not in sys.modules and 'PYTEST_CURRENT_TEST' not in os.environ
        and not any(key.startswith('_pytest') for key in tuple(sys.modules)), 'context')
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE, 'context')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and type(args.caller_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.caller_sha256), 'arguments')
    for relative, pin in SOURCE_PINS.items():
        require(_source_digest(ROOT / relative) == pin, 'source')
    require(_source_digest(SOURCE) == args.caller_sha256, 'source')
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts import arv2_newrule_execution_environment as environment
    environment._require_environment()  # Names/shapes only; no credential value access.
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
        (['branch', '--show-current'], BRANCH), (['rev-parse', 'HEAD'], args.expected_head),
        (['status', '--porcelain'], '')):
        require(_git(command, deadline).decode('ascii').strip() == expected, 'context')
    selected = args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()
    count = _git(['cat-file', '-s', selected], deadline).decode('ascii').strip()
    require(re.fullmatch('[1-9][0-9]{0,6}', count) and int(count) <= 1024 * 1024, 'source')
    raw = _git(['cat-file', 'blob', selected], deadline, int(count))
    require(len(raw) == int(count) and sha(raw) == args.caller_sha256, 'source')
    require(_git(['rev-parse', 'HEAD'], deadline).decode('ascii').strip() == args.expected_head
        and _git(['status', '--porcelain'], deadline) == b'', 'context')
    remaining(deadline)


@contextmanager
def alarm(deadline):
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'context')
    duration = remaining(deadline)
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_):
        raise Refused('deadline')
    signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, duration)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class Store:
    """Exclusive new claim leaf; retain every output descriptor through exit.

    Partial files/claims are retained on failure, not safely unspent. This is
    scoped held/named checking, not continuous or native ACL/xattr integrity.
    """

    def __init__(self):
        self.chain, self.files, self.fd = [], {}, None
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                here = Path(*CONTROL.parts[:index + 1])
                if here in (CONTROL.parent, CONTROL):
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
            self.verify()
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        for fd, _, _ in self.files.values():
            os.close(fd)
        os.close(self.fd)

    def verify(self):
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part, identity in zip(CONTROL.parts[1:], self.chain):
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
                require((os.fstat(fd).st_dev, os.fstat(fd).st_ino) == identity, 'control_changed')
            held, named = os.fstat(self.fd), os.fstat(fd)
            require(_metadata(held) == _metadata(named) and held.st_uid == os.getuid()
                and stat.S_IMODE(held.st_mode) == 0o700
                and set(os.listdir(fd)) == set(self.files), 'control_changed')
            for name, (file_fd, info, raw) in self.files.items():
                require(_metadata(os.fstat(file_fd)) == info == _metadata(os.stat(name,
                    dir_fd=self.fd, follow_symlinks=False)), 'control_changed')
                require(os.pread(file_fd, len(raw) + 1, 0) == raw, 'control_changed')
            require(_metadata(held) == _metadata(os.fstat(fd)), 'control_changed')
        finally:
            os.close(fd)

    def write(self, name, value):
        self.verify()
        require(type(name) is str and re.fullmatch(r'[a-z-]{1,64}\.json', name)
            and name not in self.files and len(self.files) < 8 and type(value) is dict, 'control')
        raw = canonical(value)
        require(0 < len(raw) <= MAX_OUTPUT, 'bound')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                require(count > 0, 'control')
                view = view[count:]
            os.fsync(fd)
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                and info.st_size == len(raw), 'control')
            self.files[name] = (fd, _metadata(info), raw)
        except BaseException:
            os.close(fd)
            raise
        os.fsync(self.fd)
        self.verify()
        return {'sha256': sha(raw), 'byte_count': len(raw)}


def typed_code_running(row):
    """Never serialize an unexpected scalar/container from the provider."""
    present = 'codeRunning' in row
    value = row.get('codeRunning')
    labels = {bool: 'boolean', type(None): 'null', str: 'string', int: 'number',
        float: 'number', list: 'array', dict: 'object'}
    return {'present': present, 'json_type': labels.get(type(value), 'invalid') if present else 'absent',
        'valid_boolean': present and type(value) is bool,
        'value': value if present and type(value) is bool else None}


def project_observation(response):
    rows = response.get('projects')
    require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'project_shape')
    row = rows[0]
    require(type(row.get('projectId')) is int and row['projectId'] == PROJECT, 'project_id')
    org = row.get('organizationId')
    require(type(org) is str and re.fullmatch('[0-9a-f]{32}', org)
        and sha(org.encode('ascii')) == ORGANIZATION_SHA256, 'organization')
    require(row.get('name') == PROJECT_NAME, 'name')
    require(row.get('language') == 'Py', 'language')
    require(row.get('owner') is True, 'owner')
    require(row.get('public', False) is False, 'private')
    collaborators = row.get('collaborators')
    require(type(collaborators) is list and len(collaborators) <= 1
        and all(type(item) is dict and item.get('owner') is True for item in collaborators), 'collaborators')
    field = typed_code_running(row)
    return {'code_running': field, 'idle_predicate_passed': field['valid_boolean'] and field['value'] is False}


def backtest_observation(response):
    rows = response.get('backtests')
    require(type(rows) is list and len(rows) <= 128 and all(type(row) is dict for row in rows), 'backtest_shape')
    require('count' not in response or (type(response['count']) is int
        and response['count'] == len(rows)), 'backtest_count')
    require('projectId' not in response or (type(response['projectId']) is int
        and response['projectId'] == PROJECT), 'backtest_project')
    labels = {key: 0 for key in (*STATUS_LABELS, 'unknown')}
    for row in rows:
        require('projectId' not in row or (type(row['projectId']) is int
            and row['projectId'] == PROJECT), 'backtest_project')
        status = row.get('status')
        labels[status if type(status) is str and status in STATUS_LABELS else 'unknown'] += 1
    return {'count': len(rows), 'status_counts': labels, 'zero_prior_backtests': len(rows) == 0}


def new_state():
    return {'stage': 'preflight', 'application_dispatch_count': 0, 'last_endpoint': None,
        'last_event': None, 'project_observation': None, 'backtest_observation': None}


def finite_failure(error, state):
    code = 'unknown_exception'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            code = args[0]
    return {'failure_code': code, **state, 'provider_request_count': None,
        'attempt_consumption': 'claim_may_be_consumed_no_retry', **FALSE_FLAGS}


def observe(request, write, state, deadline):
    """Injected synthetic seam; one fixed ordered pair, no production client."""
    require(state == {**new_state(), 'stage': 'credentials'}, 'dispatch')
    for endpoint, stage, payload, projector in (
        ('projects/read', 'project', {'projectId': PROJECT}, project_observation),
        ('backtests/list', 'backtests', {'projectId': PROJECT, 'includeStatistics': False}, backtest_observation)):
        remaining(deadline)
        require(state['application_dispatch_count'] < 2, 'dispatch')
        state.update(stage=stage, last_endpoint=endpoint, last_event='intent')
        write(stage + '-intent.json', {'endpoint': endpoint, 'payload_sha256': sha(canonical(payload))})
        state['application_dispatch_count'] += 1
        response = request(endpoint, payload)
        remaining(deadline)
        require(type(response) is dict, 'response_shape')
        raw = canonical(response)
        require(len(raw) <= 1024 * 1024, 'bound')
        state['last_event'] = 'response_received'
        require(response.get('success') is True, 'response_refused')
        result = projector(response)
        state['project_observation' if stage == 'project' else 'backtest_observation'] = result
        write(stage + '-observation.json', {'endpoint': endpoint, 'response_sha256': sha(raw), 'observation': result})
        state['last_event'] = 'observation_saved'
    return {**state, 'provider_request_count': None}


def _parse_envelope(raw, actual_exit, expected_exit):
    require(type(actual_exit) is int and actual_exit == expected_exit
        and type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT, 'bound')
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise Refused('json') from None
    require(type(value) is dict and canonical(value) == raw, 'json')
    return value


def _validate_project_result(project_result):
    require(type(project_result) is dict and set(project_result) == {'code_running', 'idle_predicate_passed'}
        and type(project_result['idle_predicate_passed']) is bool, 'response_shape')
    field = project_result['code_running']
    require(type(field) is dict and set(field) == {'present', 'json_type', 'valid_boolean', 'value'}
        and type(field['present']) is bool and type(field['valid_boolean']) is bool
        and type(field['json_type']) is str
        and field['json_type'] in ('absent', 'boolean', 'null', 'number', 'string', 'object', 'array', 'invalid')
        and (field['json_type'] != 'absent') is field['present']
        and (field['json_type'] == 'boolean') is field['valid_boolean']
        and ((field['valid_boolean'] and type(field['value']) is bool)
             or (not field['valid_boolean'] and field['value'] is None))
        and project_result['idle_predicate_passed'] is (field['valid_boolean'] and field['value'] is False), 'response_shape')


def _validate_backtest_result(backtest_result):
    require(type(backtest_result) is dict and set(backtest_result) == {'count', 'status_counts', 'zero_prior_backtests'}
        and type(backtest_result['count']) is int and 0 <= backtest_result['count'] <= 128
        and type(backtest_result['zero_prior_backtests']) is bool
        and backtest_result['zero_prior_backtests'] is (backtest_result['count'] == 0), 'response_shape')
    counts = backtest_result['status_counts']
    require(type(counts) is dict and set(counts) == set(STATUS_LABELS) | {'unknown'}
        and all(type(count) is int and 0 <= count <= 128 for count in counts.values())
        and sum(counts.values()) == backtest_result['count'], 'response_shape')


def validate_output(raw, actual_exit, args):
    """Pure external stdout validator; no report read or inferred process exit.

    Reconstruct the canonical report from the envelope and bind its pin. This
    does not reread its current filesystem bytes; that needs separate scope.
    """
    value = _parse_envelope(raw, actual_exit, 0)
    expected = binding(args)
    require(set(value) == set(expected) | set(FALSE_FLAGS) | {'observation_completed', 'report', 'result'}
        and all(type(value[key]) is type(item) and value[key] == item for key, item in expected.items())
        and all(value[key] is False for key in FALSE_FLAGS)
        and value['observation_completed'] is True, 'response_shape')
    pin = value['report']
    require(type(pin) is dict and set(pin) == {'sha256', 'byte_count'}
        and type(pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}', pin['sha256'])
        and type(pin['byte_count']) is int and 0 < pin['byte_count'] <= MAX_OUTPUT, 'response_shape')
    result = value['result']
    require(type(result) is dict and set(result) == set(new_state()) | {'provider_request_count'}
        and result['stage'] == 'backtests' and type(result['application_dispatch_count']) is int
        and result['application_dispatch_count'] == 2 and result['last_endpoint'] == 'backtests/list'
        and result['last_event'] == 'observation_saved' and result['provider_request_count'] is None, 'response_shape')
    _validate_project_result(result['project_observation'])
    _validate_backtest_result(result['backtest_observation'])
    report_raw = canonical({**expected, 'observation_completed': True,
        'result': result, **FALSE_FLAGS})
    require(pin == {'sha256': sha(report_raw), 'byte_count': len(report_raw)}, 'response_shape')
    return value


def validate_failure_output(raw, actual_exit):
    """Validate finite exit2 evidence, never promote it to accepted success."""
    value = _parse_envelope(raw, actual_exit, 2)
    require(set(value) == {'schema', 'project_id', 'observation_completed', 'failure_code',
        'provider_request_count', 'attempt_consumption'} | set(new_state()) | set(FALSE_FLAGS)
        and value['schema'] == SCHEMA and type(value['project_id']) is int and value['project_id'] == PROJECT
        and value['observation_completed'] is False and all(value[key] is False for key in FALSE_FLAGS)
        and type(value['failure_code']) is str and value['failure_code'] in FINITE | {'unknown_exception'}
        and value['provider_request_count'] is None
        and value['attempt_consumption'] == 'claim_may_be_consumed_no_retry', 'response_shape')
    stage, count = value['stage'], value['application_dispatch_count']
    endpoint, event = value['last_endpoint'], value['last_event']
    project_result, backtest_result = value['project_observation'], value['backtest_observation']
    require(type(stage) is str and stage in STAGES and type(count) is int and 0 <= count <= 2
        and (endpoint is None or (type(endpoint) is str and endpoint in ENDPOINTS))
        and (event is None or (type(event) is str and event in ('intent', 'response_received', 'observation_saved'))),
        'response_shape')
    if stage in ('preflight', 'claim', 'credentials'):
        require(count == 0 and endpoint is None and event is None
            and project_result is None and backtest_result is None, 'response_shape')
    elif stage == 'project':
        require(count in (0, 1) and endpoint == 'projects/read' and event is not None
            and backtest_result is None and (count == 1 or (event == 'intent' and project_result is None)), 'response_shape')
    else:
        require(count in (1, 2) and endpoint == 'backtests/list' and event is not None
            and project_result is not None and (count == 2 or (event == 'intent' and backtest_result is None)), 'response_shape')
        if stage in ('postflight', 'report'):
            require(count == 2 and event == 'observation_saved' and backtest_result is not None, 'response_shape')
    if project_result is not None:
        require(count >= 1 and not (stage == 'project' and event == 'intent'), 'response_shape')
        _validate_project_result(project_result)
    if backtest_result is not None:
        require(count == 2 and event != 'intent', 'response_shape')
        _validate_backtest_result(backtest_result)
    require(event != 'observation_saved' or
        (project_result is not None if endpoint == 'projects/read' else backtest_result is not None), 'response_shape')
    return value


def run(args):
    state, deadline = new_state(), time.monotonic() + DEADLINE_SECONDS
    try:
        with alarm(deadline):
            _preflight(args, deadline)
            from scripts import arv2_newrule_execution_environment as environment
            environment._bootstrap_cli_logging()
            state['stage'] = 'claim'
            with Store() as store:
                try:
                    store.write('claim.json', {**binding(args), 'observation_claim_consumed': True,
                        'shared_look': 0, 'development_look': 0, 'infrastructure_look': 0})
                    state['stage'] = 'credentials'
                    client = environment.guarded_client()
                    def request(endpoint, payload):
                        remaining(deadline)
                        require(endpoint in ENDPOINTS, 'dispatch')
                        environment.require_safe_environment()
                        return client.request(endpoint, payload)
                    result = observe(request, store.write, state, deadline)
                    state['stage'] = 'postflight'
                    _preflight(args, deadline)
                    environment.require_safe_environment()
                    state['stage'] = 'report'
                    pin = store.write('report.json', {**binding(args), 'observation_completed': True,
                        'result': result, **FALSE_FLAGS})
                    remaining(deadline)
                    store.verify()
                    output = {**binding(args), 'observation_completed': True, 'report': pin,
                        'result': result, **FALSE_FLAGS}
                except BaseException as error:
                    try:
                        store.write('failure.json', {'schema': SCHEMA, 'project_id': PROJECT,
                            'observation_completed': False, **finite_failure(error, state)})
                    except BaseException:
                        pass  # Preserve original finite failure; never repair a partial output.
                    raise
            raw = canonical(output)
            require(len(raw) <= MAX_OUTPUT, 'bound')
            sys.stdout.write(raw.decode('ascii'))
            sys.stdout.flush()
            return 0
    except BaseException as error:
        # Preserve finite current state even when report publication/postflight
        # fails. A report alone never overrides actual exit2/unknown exit.
        raw = canonical({'schema': SCHEMA, 'project_id': PROJECT,
            'observation_completed': False, **finite_failure(error, state)})
        sys.stdout.write(raw.decode('ascii'))
        sys.stdout.flush()
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    raise SystemExit(main())
