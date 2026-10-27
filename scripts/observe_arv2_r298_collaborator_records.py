"""One bounded comparison of R298 project and dedicated collaborator records.

This reads only projects/read followed by projects/collaboration/read. It does
not declare entries stored/synthetic, authorize another attempt, change
permissions, acquire edit control or touch project files. Separate committed
one-shot authority is mandatory. Earlier observations remain spent.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.observe_arv2_r298_idleness import Refused, canonical, require, sha, typed_code_running
from scripts.observe_arv2_r298_access_shape import field_shape, _validate_field

SOURCE = ROOT / 'scripts/observe_arv2_r298_collaborator_records.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_collaborator_records/R312-20261024-A'
PYTHON = Path('/Users/sheltonchen/.venvs/trading_agent-py313/bin/python')
BRANCH = 'codex/strategy-analyst-revisions-v2'
SCHEMA = 'arv2-r298-collaborator-records-v1'
PROJECT = 38364439
PROJECT_NAME = 'ARV2 R298 NEWRULE SIX OFF 2021 OCT2026'
ORGANIZATION_SHA256 = 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
DEADLINE_SECONDS, MAX_OUTPUT, MAX_COLLABORATORS = 60, 24576, 8
ENDPOINTS = ('projects/read', 'projects/collaboration/read')
# Selected direct protocol/credential/transport pins, not whole-interpreter integrity.
SOURCE_PINS = {
    'scripts/observe_arv2_r298_access_shape.py': '30741256b41d145873f58c4b20824f8bf24ab1f949f0f1f966f66408179c3e83',
    'scripts/observe_arv2_r298_idleness.py': 'b2b62f12d669753e765c183a2811ba3a9353066e52e447c67d660577946c662a',
    'scripts/arv2_newrule_execution_environment.py': 'bacf030e82b309111d8e7788991880860620f6d876bbd750246345c95d7c3194',
    'research/quantconnect.py': '7a12fdb68194ee10f6e8c3d7c0fc49c08b34166d056bd5ea2a72937dd03be373',
    'research/analyst_revisions_v2_qc/newrule_comparison_submission.py': 'cfd2456f2835bb1a4d2c04d6bb60a633b537a2af276a478ad3bfa5f2bc348d4f',
    'research/analyst_revisions_v2_qc/six_universe_coverage_submission.py': 'e511e04eeadb5a667b7ecee361dcac3de31d6323a0d64b1ea0b42f2879aab62b',
    'research/analyst_revisions_v2_qc/formal_qc_transport.py': 'b8c332eda827aeaee23f0dbbddcc96dbd269c82c996812a8a31fe2a4fec62ac4',
}
FALSE_FLAGS = {'operational_retry_authority': False, 'collaborator_policy_accepted': False,
    'project_ready': False, 'point_in_time_proven': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False, 'strategy_result_accepted': False,
    'stored_record_proven': False, 'synthetic_entry_proven': False, 'edit_lock_proven': False}
JSON_TYPES = ('absent', 'null', 'boolean', 'number', 'string', 'array', 'object', 'invalid')
STAGES = ('preflight', 'claim', 'credentials', 'project', 'collaborators', 'postflight', 'report')
FINITE = frozenset(('arguments', 'context', 'source', 'deadline', 'claim', 'control',
    'control_changed', 'bound', 'json', 'dispatch', 'response_shape', 'response_refused',
    'project_shape', 'project_id', 'organization', 'name', 'language', 'owner', 'owner_id', 'private', 'client'))


def remaining(deadline):
    left = deadline - time.monotonic()
    require(left > 0, 'deadline')
    return left


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': str(PYTHON),
        'control': str(CONTROL), 'project_id': PROJECT, 'organization_sha256': ORGANIZATION_SHA256,
        'purpose': 'compare_project_metadata_with_dedicated_collaborator_records',
        'source_pins': dict(SOURCE_PINS), 'endpoints': list(ENDPOINTS), 'max_application_dispatches': 2,
        'deadline_seconds': DEADLINE_SECONDS, 'max_output_bytes': MAX_OUTPUT,
        'max_collaborators': MAX_COLLABORATORS, 'automatic_retry': False,
        'prior_observer_remains_spent': True, 'actual_exit_required_externally': True,
        'shared_look': 0, 'development_look': 0, 'infrastructure_look': 0, **FALSE_FLAGS}


def binding(args):
    # Invalid caller strings must never be echoed into finite failure evidence.
    def checked(value, length):
        return value if type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) else None
    return {'schema': SCHEMA, 'expected_head': checked(args.expected_head, 40),
        'caller_sha256': checked(args.caller_sha256, 64),
        'profile_sha256': sha(canonical(profile_record())), 'project_id': PROJECT}


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


def _git(arguments, deadline, limit=65536):
    child_env = {key: value for key, value in os.environ.items() if key not in ('QC_USER_ID', 'QC_API_TOKEN')}
    result = subprocess.run(['/usr/bin/git', *arguments], cwd=ROOT, stdin=subprocess.DEVNULL,
        capture_output=True, check=False, timeout=min(3, remaining(deadline)), env=child_env)
    require(type(result.returncode) is int and result.returncode == 0 and result.stderr == b''
        and type(result.stdout) is bytes and len(result.stdout) <= limit, 'context')
    return result.stdout


def _preflight(args, deadline):
    require('pytest' not in sys.modules and 'PYTEST_CURRENT_TEST' not in os.environ
        and not any(key.startswith('_pytest') for key in tuple(sys.modules)), 'context')
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE, 'context')
    require(binding(args)['expected_head'] is not None and binding(args)['caller_sha256'] is not None, 'arguments')
    for relative, pin in SOURCE_PINS.items():
        require(_source_digest(ROOT / relative) == pin, 'source')
    require(_source_digest(SOURCE) == args.caller_sha256, 'source')
    from scripts import arv2_newrule_execution_environment as environment
    environment._require_environment()  # Names/shapes only, not credential values.
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
    """Own exclusive leaf and retained held/named descriptors; no old controls.

    A partial claim consumes or ambiguously consumes use. No cleanup or retry.
    This is scoped checking, not continuous integrity or native ACL/xattr proof.
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
            held = os.fstat(self.fd)
            require(_metadata(held) == _metadata(os.fstat(fd)) and held.st_uid == os.getuid()
                and stat.S_IMODE(held.st_mode) == 0o700 and set(os.listdir(fd)) == set(self.files), 'control_changed')
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


def typed_boolean(row, key):
    return typed_code_running({'codeRunning': row[key]} if key in row else {})


def permission(value):
    return value if type(value) is str and value in ('read', 'write') else 'unknown'


def record_projection(row, owner_id):
    raw = canonical(row)
    kind = field_shape({'row': row}, 'row')['json_type']
    result = {'json_type': kind, 'row_sha256': sha(raw), 'owner': None, 'uid': None,
        'public_id': None, 'name_exact_mia': None, 'permission': 'unknown', 'live_control': None}
    if type(row) is not dict:
        return result
    uid, public_id = row.get('uid'), row.get('publicId')
    valid_uid = type(uid) is int and uid > 0
    result.update(owner=typed_boolean(row, 'owner'),
        uid={**field_shape(row, 'uid'), 'valid_positive_integer': valid_uid,
            'equals_project_owner': uid == owner_id if valid_uid else None},
        public_id={**field_shape(row, 'publicId'),
            'exact_mia_sentinel': type(public_id) is str and public_id == 'mia-ai',
            # Shape only, not a documented API identifier grammar or identity proof.
            'bounded_nonempty_ascii': type(public_id) is str and 1 <= len(public_id) <= 256
                and all(33 <= ord(character) <= 126 for character in public_id)},
        name_exact_mia=type(row.get('name')) is str and row['name'] == 'Mia',
        permission=permission(row.get('permission')), live_control=typed_boolean(row, 'liveControl'))
    return result


def collaborators_projection(response, owner_id):
    field = {**field_shape(response, 'collaborators'), 'count': None, 'records': None}
    rows = response.get('collaborators')
    if type(rows) is list:
        require(len(rows) <= MAX_COLLABORATORS, 'bound')
        field.update(count=len(rows), records=[record_projection(row, owner_id) for row in rows])
    return field


def project_observation(response):
    rows = response.get('projects')
    require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'project_shape')
    row = rows[0]
    require(type(row.get('projectId')) is int and row['projectId'] == PROJECT, 'project_id')
    org = row.get('organizationId')
    require(type(org) is str and re.fullmatch('[0-9a-f]{32}', org)
        and sha(org.encode('ascii')) == ORGANIZATION_SHA256, 'organization')
    require(type(row.get('name')) is str and row['name'] == PROJECT_NAME, 'name')
    require(type(row.get('language')) is str and row['language'] == 'Py', 'language')
    require(row.get('owner') is True, 'owner')
    require(row.get('public', False) is False, 'private')
    owner_id = row.get('ownerId')
    require(type(owner_id) is int and owner_id > 0, 'owner_id')
    return owner_id, {'code_running': typed_boolean(row, 'codeRunning'),
        'collaborators': collaborators_projection(row, owner_id)}


def dedicated_observation(response, owner_id):
    require('projectId' not in response or (type(response['projectId']) is int
        and response['projectId'] == PROJECT), 'project_id')
    return {'collaborators': collaborators_projection(response, owner_id),
        'user_permissions': permission(response.get('userPermissions')),
        'user_live_control': typed_boolean(response, 'userLiveControl')}


def comparison(project, dedicated):
    first, second = project['collaborators'], dedicated['collaborators']
    equality = None
    if first['json_type'] == second['json_type'] == 'array':
        equality = sorted(row['row_sha256'] for row in first['records']) == sorted(
            row['row_sha256'] for row in second['records'])
    return {'project_count': first['count'], 'dedicated_count': second['count'],
        'row_hash_multiset_equal': equality}


class ReadOnlyClient:
    """Own two-endpoint boundary; the frozen general allowlist is unchanged."""
    __slots__ = ('__api', '__next')

    def __init__(self):
        from scripts import arv2_newrule_execution_environment as environment
        environment.require_safe_environment()
        from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
        self.__api, self.__next = old._client(), 0
        environment.require_safe_environment()
        self.__check()

    def __repr__(self):
        return '<ReadOnlyR298CollaboratorClient>'

    def __check(self):
        from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
        api = self.__api
        require(type(api) is old.QuantConnectClient and api._base_url == old.API_BASE
            and api._transport is old.coverage._bounded_transport and api._timeout == 30, 'client')

    def request(self, endpoint, payload):
        from scripts import arv2_newrule_execution_environment as environment
        environment.require_safe_environment()
        self.__check()
        require(type(endpoint) is str and self.__next < len(ENDPOINTS)
            and endpoint == ENDPOINTS[self.__next] and type(payload) is dict
            and set(payload) == {'projectId'} and type(payload['projectId']) is int
            and payload['projectId'] == PROJECT, 'dispatch')
        self.__next += 1  # Ambiguous transport consumes this dispatch; no retry.
        return self.__api.request(endpoint, payload)


def new_state():
    return {'stage': 'preflight', 'application_dispatch_count': 0, 'last_event': None,
        'last_endpoint': None, 'project_observation': None, 'dedicated_observation': None, 'comparison': None}


def finite_failure(error, state):
    code = 'unknown_exception'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            code = args[0]
    return {'failure_code': code, **state, 'provider_request_count': None,
        'attempt_consumption': 'claim_may_be_consumed_no_retry'}


def observe(request, write, state, deadline):
    require(state == {**new_state(), 'stage': 'credentials'}, 'dispatch')
    owner_id = None  # Never persisted or returned outside this memory-only comparison.
    for endpoint, stage in zip(ENDPOINTS, ('project', 'collaborators')):
        remaining(deadline)
        payload = {'projectId': PROJECT}
        state.update(stage=stage, last_endpoint=endpoint, last_event='intent')
        write(stage + '-intent.json', {'endpoint': endpoint, 'payload_sha256': sha(canonical(payload))})
        remaining(deadline)
        state['application_dispatch_count'] += 1
        response = request(endpoint, payload)
        remaining(deadline)
        require(type(response) is dict, 'response_shape')
        raw = canonical(response)
        require(len(raw) <= 1024 * 1024, 'bound')
        state['last_event'] = 'response_received'
        require(response.get('success') is True, 'response_refused')
        if stage == 'project':
            owner_id, result = project_observation(response)
            state['project_observation'] = result
        else:
            result = dedicated_observation(response, owner_id)
            state['dedicated_observation'] = result
            state['comparison'] = comparison(state['project_observation'], result)
        write(stage + '-observation.json', {'endpoint': endpoint, 'response_sha256': sha(raw), 'observation': result})
        state['last_event'] = 'observation_saved'
    return {**state, 'provider_request_count': None}


def _validate_boolean(value):
    _validate_field(value, ('valid_boolean', 'value'))
    require(type(value['valid_boolean']) is bool and value['valid_boolean'] is (value['json_type'] == 'boolean')
        and ((value['valid_boolean'] and type(value['value']) is bool)
            or (not value['valid_boolean'] and value['value'] is None)), 'response_shape')


def _require_consistent_record_projections(records):
    # One ownerId is used for both endpoint views. An identical canonical raw
    # record hash cannot legitimately produce contradictory finite projections.
    seen = {}
    for row in records:
        digest, projected = row['row_sha256'], canonical(row)
        require(digest not in seen or seen[digest] == projected, 'response_shape')
        seen[digest] = projected


def _validate_records(field):
    _validate_field(field, ('count', 'records'))
    if field['json_type'] != 'array':
        require(field['count'] is None and field['records'] is None, 'response_shape')
        return
    require(type(field['count']) is int and 0 <= field['count'] <= MAX_COLLABORATORS
        and type(field['records']) is list and len(field['records']) == field['count'], 'response_shape')
    keys = {'json_type', 'row_sha256', 'owner', 'uid', 'public_id', 'name_exact_mia', 'permission', 'live_control'}
    for row in field['records']:
        require(type(row) is dict and set(row) == keys and type(row['json_type']) is str
            and row['json_type'] in JSON_TYPES and row['json_type'] not in ('absent', 'invalid')
            and type(row['row_sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['row_sha256']), 'response_shape')
        require(type(row['permission']) is str and row['permission'] in ('read', 'write', 'unknown'), 'response_shape')
        if row['json_type'] != 'object':
            require(all(row[key] is None for key in ('owner', 'uid', 'public_id', 'name_exact_mia', 'live_control'))
                and row['permission'] == 'unknown', 'response_shape')
            continue
        _validate_boolean(row['owner'])
        _validate_boolean(row['live_control'])
        require(type(row['name_exact_mia']) is bool, 'response_shape')
        uid = row['uid']
        _validate_field(uid, ('valid_positive_integer', 'equals_project_owner'))
        require(type(uid['valid_positive_integer']) is bool
            and (not uid['valid_positive_integer'] or uid['json_type'] == 'number')
            and ((uid['valid_positive_integer'] and type(uid['equals_project_owner']) is bool)
                or (not uid['valid_positive_integer'] and uid['equals_project_owner'] is None)), 'response_shape')
        public = row['public_id']
        _validate_field(public, ('exact_mia_sentinel', 'bounded_nonempty_ascii'))
        require(type(public['exact_mia_sentinel']) is bool and type(public['bounded_nonempty_ascii']) is bool
            and (not public['bounded_nonempty_ascii'] or public['json_type'] == 'string')
            and (not public['exact_mia_sentinel'] or public['bounded_nonempty_ascii']), 'response_shape')
    _require_consistent_record_projections(field['records'])


def _validate_project(value):
    require(type(value) is dict and set(value) == {'code_running', 'collaborators'}, 'response_shape')
    _validate_boolean(value['code_running'])
    _validate_records(value['collaborators'])


def _validate_dedicated(value):
    require(type(value) is dict and set(value) == {'collaborators', 'user_permissions', 'user_live_control'}
        and type(value['user_permissions']) is str and value['user_permissions'] in ('read', 'write', 'unknown'), 'response_shape')
    _validate_boolean(value['user_live_control'])
    _validate_records(value['collaborators'])


def _validate_result(result, completed):
    extra = set() if completed else {'failure_code', 'attempt_consumption'}
    require(type(result) is dict and set(result) == set(new_state()) | {'provider_request_count'} | extra
        and type(result['stage']) is str and result['stage'] in STAGES
        and type(result['application_dispatch_count']) is int and 0 <= result['application_dispatch_count'] <= 2
        and result['provider_request_count'] is None, 'response_shape')
    if not completed:
        require(type(result['failure_code']) is str and result['failure_code'] in FINITE | {'unknown_exception'}
            and result['attempt_consumption'] == 'claim_may_be_consumed_no_retry', 'response_shape')
    stage, event, count = result['stage'], result['last_event'], result['application_dispatch_count']
    project, dedicated, compared = result['project_observation'], result['dedicated_observation'], result['comparison']
    if stage in ('preflight', 'claim', 'credentials'):
        require(not completed and count == 0 and event is None and result['last_endpoint'] is None
            and project is None and dedicated is None and compared is None, 'response_shape')
    else:
        require(type(event) is str and event in ('intent', 'response_received', 'observation_saved'), 'response_shape')
        if stage == 'project':
            require(not completed and result['last_endpoint'] == ENDPOINTS[0] and count in (0, 1)
                and dedicated is None and compared is None
                and (count == 1 or (event == 'intent' and project is None)), 'response_shape')
        else:
            require(result['last_endpoint'] == ENDPOINTS[1] and count in (1, 2) and project is not None
                and (count == 2 or (event == 'intent' and dedicated is None)), 'response_shape')
            if stage in ('postflight', 'report') or completed:
                require(count == 2 and event == 'observation_saved' and dedicated is not None, 'response_shape')
            if completed:
                require(stage == 'collaborators', 'response_shape')
        if event == 'observation_saved':
            require((project if stage == 'project' else dedicated) is not None, 'response_shape')
    if project is not None:
        require(count >= 1 and not (stage == 'project' and event == 'intent'), 'response_shape')
        _validate_project(project)
    if dedicated is not None:
        require(count == 2 and event != 'intent' and project is not None, 'response_shape')
        _validate_dedicated(dedicated)
        _require_consistent_record_projections((project['collaborators']['records'] or [])
            + (dedicated['collaborators']['records'] or []))
        require(type(compared) is dict and set(compared) == {'project_count', 'dedicated_count', 'row_hash_multiset_equal'}
            and canonical(compared) == canonical(comparison(project, dedicated)), 'response_shape')
    else:
        require(compared is None, 'response_shape')


def validate_output(raw, actual_exit, args):
    """Validate actual exit, exact finite envelope and reconstructed report pin.

    No report filesystem read occurs. A missing failure pin cannot exclude
    partial persistence, and never grants replay or operational authority.
    """
    require(type(actual_exit) is int and actual_exit in (0, 2) and type(raw) is bytes
        and 0 < len(raw) <= MAX_OUTPUT, 'bound')
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise Refused('json') from None
    require(type(value) is dict and canonical(value) == raw, 'json')
    expected = binding(args)
    require(expected['expected_head'] is not None and expected['caller_sha256'] is not None
        and set(value) == set(expected) | set(FALSE_FLAGS) | {'observation_completed', 'result', 'report'}
        and all(type(value[key]) is type(item) and value[key] == item for key, item in expected.items())
        and all(value[key] is False for key in FALSE_FLAGS)
        and value['observation_completed'] is (actual_exit == 0), 'response_shape')
    _validate_result(value['result'], actual_exit == 0)
    report = {key: item for key, item in value.items() if key != 'report'}
    expected_raw = canonical(report)
    pin = value['report']
    require((actual_exit == 2 and pin is None) or (type(pin) is dict and set(pin) == {'sha256', 'byte_count'}
        and type(pin['byte_count']) is int
        and pin == {'sha256': sha(expected_raw), 'byte_count': len(expected_raw)}), 'response_shape')
    return value


def run(args):
    state, deadline, failure_pin = new_state(), time.monotonic() + DEADLINE_SECONDS, None
    def report(completed, result):
        return {**binding(args), 'observation_completed': completed, 'result': result, **FALSE_FLAGS}
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
                    client = ReadOnlyClient()
                    def request(endpoint, payload):
                        remaining(deadline)
                        return client.request(endpoint, payload)
                    result = observe(request, store.write, state, deadline)
                    state['stage'] = 'postflight'
                    _preflight(args, deadline)
                    environment.require_safe_environment()
                    state['stage'] = 'report'
                    output = report(True, result)
                    pin = store.write('report.json', output)
                    remaining(deadline)
                    store.verify()
                    output = {**output, 'report': pin}
                except BaseException as error:
                    failure = report(False, finite_failure(error, state))
                    try:
                        failure_pin = store.write('failure.json', failure)
                    except BaseException:
                        pass  # Preserve partial evidence and original finite failure.
                    raise
            raw = canonical(output)
            require(len(raw) <= MAX_OUTPUT, 'bound')
            sys.stdout.write(raw.decode('ascii'))
            sys.stdout.flush()
            return 0
    except BaseException as error:
        output = {**report(False, finite_failure(error, state)), 'report': failure_pin}
        raw = canonical(output)
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
