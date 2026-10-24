"""One read-only R298 collaborator-shape diagnosis; never recovery authority.

R311's earlier observation remains spent. This different diagnostic makes one
projects/read request, after its own exclusive claim, to explain the shape of
the field that R311 refused. It neither accepts collaborators nor changes them.
No private source files, capacity, uploads, compile or launch are inspected.
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

SOURCE = ROOT / 'scripts/observe_arv2_r298_access_shape.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_access_shape/R312-20261024-A'
PYTHON = Path('/Users/sheltonchen/.venvs/trading_agent-py313/bin/python')
BRANCH = 'codex/strategy-analyst-revisions-v2'
SCHEMA = 'arv2-r298-access-shape-v1'
PROJECT = 38364439
PROJECT_NAME = 'ARV2 R298 NEWRULE SIX OFF 2021 OCT2026'
ORGANIZATION_SHA256 = 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
DEADLINE_SECONDS, MAX_OUTPUT, MAX_COLLABORATORS = 60, 16384, 128
ENDPOINT = 'projects/read'
# Selected direct protocol/credential/transport pins, not whole-interpreter integrity.
SOURCE_PINS = {
    'scripts/observe_arv2_r298_idleness.py': 'b2b62f12d669753e765c183a2811ba3a9353066e52e447c67d660577946c662a',
    'scripts/arv2_newrule_execution_environment.py': 'bacf030e82b309111d8e7788991880860620f6d876bbd750246345c95d7c3194',
    'research/quantconnect.py': '7a12fdb68194ee10f6e8c3d7c0fc49c08b34166d056bd5ea2a72937dd03be373',
    'research/analyst_revisions_v2_qc/newrule_comparison_submission.py': 'cfd2456f2835bb1a4d2c04d6bb60a633b537a2af276a478ad3bfa5f2bc348d4f',
    'research/analyst_revisions_v2_qc/six_universe_coverage_submission.py': 'e511e04eeadb5a667b7ecee361dcac3de31d6323a0d64b1ea0b42f2879aab62b',
    'research/analyst_revisions_v2_qc/formal_qc_transport.py': 'b8c332eda827aeaee23f0dbbddcc96dbd269c82c996812a8a31fe2a4fec62ac4',
}
FALSE_FLAGS = {'operational_retry_authority': False, 'collaborator_policy_accepted': False,
    'project_ready': False, 'point_in_time_proven': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False, 'strategy_result_accepted': False}
JSON_TYPES = ('absent', 'null', 'boolean', 'number', 'string', 'array', 'object', 'invalid')
JOINT_COUNTS = ('owner_true_uid_equals_owner', 'owner_false_uid_exact_mia',
    'owner_false_public_id_exact_mia', 'owner_false_both_exact_mia', 'owner_true_either_exact_mia')
STAGES = ('preflight', 'claim', 'credentials', 'project', 'postflight', 'report')
FINITE = frozenset(('arguments', 'context', 'source', 'deadline', 'claim', 'control',
    'control_changed', 'bound', 'json', 'dispatch', 'response_shape', 'response_refused',
    'project_shape', 'project_id', 'organization', 'name', 'language', 'owner', 'private'))


def remaining(deadline):
    left = deadline - time.monotonic()
    require(left > 0, 'deadline')
    return left


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': str(PYTHON),
        'control': str(CONTROL), 'project_id': PROJECT, 'organization_sha256': ORGANIZATION_SHA256,
        'purpose': 'finite_collaborator_shape_after_spent_idleness_refusal',
        'source_pins': dict(SOURCE_PINS), 'endpoint': ENDPOINT, 'max_application_dispatches': 1,
        'deadline_seconds': DEADLINE_SECONDS, 'max_output_bytes': MAX_OUTPUT,
        'max_collaborators': MAX_COLLABORATORS, 'automatic_retry': False,
        'finite_joint_count_fields': list(JOINT_COUNTS),
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
            and name not in self.files and len(self.files) < 6 and type(value) is dict, 'control')
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


def field_shape(row, key):
    present = key in row
    kind = {type(None): 'null', bool: 'boolean', int: 'number', float: 'number',
        str: 'string', list: 'array', dict: 'object'}.get(type(row.get(key)), 'invalid')
    return {'present': present, 'json_type': kind if present else 'absent'}


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
    owner_shape = {**field_shape(row, 'ownerId'), 'valid_positive_integer': type(owner_id) is int and owner_id > 0}
    field = {**field_shape(row, 'collaborators'), 'list_count': None, 'entries': None}
    collaborators = row.get('collaborators')
    if type(collaborators) is list:
        require(len(collaborators) <= MAX_COLLABORATORS, 'bound')
        counts = {'dict': 0, 'non_dict': 0, 'owner_present': 0, 'owner_true': 0, 'owner_false': 0,
            'owner_types': dict.fromkeys(JSON_TYPES, 0), 'uid_types': dict.fromkeys(JSON_TYPES, 0),
            'uid_equals_owner_true': 0, 'uid_equals_owner_false': 0, 'uid_equality_unavailable': 0,
            'uid_exact_mia_sentinel': 0, 'public_id_exact_mia_sentinel': 0,
            **dict.fromkeys(JOINT_COUNTS, 0)}
        for item in collaborators:
            if type(item) is not dict:
                counts['non_dict'] += 1
                continue
            counts['dict'] += 1
            shape = field_shape(item, 'owner')
            counts['owner_present'] += int(shape['present'])
            counts['owner_types'][shape['json_type']] += 1
            counts['owner_true'] += int(item.get('owner') is True)
            counts['owner_false'] += int(item.get('owner') is False)
            counts['uid_types'][field_shape(item, 'uid')['json_type']] += 1
            uid = item.get('uid')
            # Public API example sentinel only, not a verified role or authority.
            uid_mia = type(uid) is str and uid == 'mia-ai'
            counts['uid_exact_mia_sentinel'] += int(uid_mia)
            public_id = item.get('publicId')
            public_mia = type(public_id) is str and public_id == 'mia-ai'
            counts['public_id_exact_mia_sentinel'] += int(public_mia)
            label = 'unavailable'
            if owner_shape['valid_positive_integer'] and type(uid) is int and uid > 0:
                label = 'true' if uid == owner_id else 'false'
            counts['uid_equality_unavailable' if label == 'unavailable' else 'uid_equals_owner_' + label] += 1
            owner_true, owner_false = item.get('owner') is True, item.get('owner') is False
            counts['owner_true_uid_equals_owner'] += int(owner_true and label == 'true')
            counts['owner_false_uid_exact_mia'] += int(owner_false and uid_mia)
            counts['owner_false_public_id_exact_mia'] += int(owner_false and public_mia)
            counts['owner_false_both_exact_mia'] += int(owner_false and uid_mia and public_mia)
            counts['owner_true_either_exact_mia'] += int(owner_true and (uid_mia or public_mia))
        field.update(list_count=len(collaborators), entries=counts)
    return {'code_running': typed_code_running(row), 'project_owner_id': owner_shape, 'collaborators': field}


def new_state():
    return {'stage': 'preflight', 'application_dispatch_count': 0, 'last_event': None,
        'last_endpoint': None, 'project_observation': None}


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
    remaining(deadline)
    payload = {'projectId': PROJECT}
    state.update(stage='project', last_endpoint=ENDPOINT, last_event='intent')
    write('project-intent.json', {'endpoint': ENDPOINT, 'payload_sha256': sha(canonical(payload))})
    remaining(deadline)
    state['application_dispatch_count'] = 1
    response = request(ENDPOINT, payload)
    remaining(deadline)
    require(type(response) is dict, 'response_shape')
    raw = canonical(response)
    require(len(raw) <= 1024 * 1024, 'bound')
    state['last_event'] = 'response_received'
    require(response.get('success') is True, 'response_refused')
    result = project_observation(response)
    state['project_observation'] = result
    write('project-observation.json', {'endpoint': ENDPOINT, 'response_sha256': sha(raw), 'observation': result})
    state['last_event'] = 'observation_saved'
    return {**state, 'provider_request_count': None}


def _validate_field(value, extra=()):
    require(type(value) is dict and set(value) == {'present', 'json_type'} | set(extra)
        and type(value['present']) is bool and type(value['json_type']) is str
        and value['json_type'] in JSON_TYPES
        and value['present'] is (value['json_type'] != 'absent'), 'response_shape')


def _validate_observation(value):
    require(type(value) is dict and set(value) == {'code_running', 'project_owner_id', 'collaborators'}, 'response_shape')
    code = value['code_running']
    _validate_field(code, ('valid_boolean', 'value'))
    require(type(code['valid_boolean']) is bool and code['valid_boolean'] is (code['json_type'] == 'boolean')
        and ((code['valid_boolean'] and type(code['value']) is bool)
            or (not code['valid_boolean'] and code['value'] is None)), 'response_shape')
    owner = value['project_owner_id']
    _validate_field(owner, ('valid_positive_integer',))
    require(type(owner['valid_positive_integer']) is bool
        and (not owner['valid_positive_integer'] or owner['json_type'] == 'number'), 'response_shape')
    field = value['collaborators']
    _validate_field(field, ('list_count', 'entries'))
    if field['json_type'] != 'array':
        require(field['list_count'] is None and field['entries'] is None, 'response_shape')
        return
    count, entries = field['list_count'], field['entries']
    keys = {'dict', 'non_dict', 'owner_present', 'owner_true', 'owner_false', 'owner_types',
        'uid_types', 'uid_equals_owner_true', 'uid_equals_owner_false', 'uid_equality_unavailable',
        'uid_exact_mia_sentinel', 'public_id_exact_mia_sentinel'} | set(JOINT_COUNTS)
    require(type(count) is int and 0 <= count <= MAX_COLLABORATORS
        and type(entries) is dict and set(entries) == keys, 'response_shape')
    for key in keys - {'owner_types', 'uid_types'}:
        require(type(entries[key]) is int and 0 <= entries[key] <= count, 'response_shape')
    for key in ('owner_types', 'uid_types'):
        values = entries[key]
        require(type(values) is dict and set(values) == set(JSON_TYPES)
            and all(type(item) is int and 0 <= item <= count for item in values.values())
            and sum(values.values()) == entries['dict'], 'response_shape')
    require(entries['dict'] + entries['non_dict'] == count
        and entries['owner_present'] == entries['dict'] - entries['owner_types']['absent']
        and entries['owner_true'] + entries['owner_false'] == entries['owner_types']['boolean']
        and entries['uid_equals_owner_true'] + entries['uid_equals_owner_false']
            + entries['uid_equality_unavailable'] == entries['dict']
        and entries['uid_equals_owner_true'] + entries['uid_equals_owner_false'] <= entries['uid_types']['number']
        and entries['uid_exact_mia_sentinel'] <= entries['uid_types']['string']
        and entries['public_id_exact_mia_sentinel'] <= entries['dict']
        and (owner['valid_positive_integer'] or entries['uid_equality_unavailable'] == entries['dict']), 'response_shape')
    owner_uid = entries['owner_true_uid_equals_owner']
    false_uid, false_public = entries['owner_false_uid_exact_mia'], entries['owner_false_public_id_exact_mia']
    false_both, true_either = entries['owner_false_both_exact_mia'], entries['owner_true_either_exact_mia']
    false_union = false_uid + false_public - false_both
    require(owner_uid <= min(entries['owner_true'], entries['uid_equals_owner_true'])
        and false_uid <= min(entries['owner_false'], entries['uid_exact_mia_sentinel'])
        and false_public <= min(entries['owner_false'], entries['public_id_exact_mia_sentinel'])
        and false_both <= min(false_uid, false_public)
        and false_union <= entries['owner_false']
        and true_either <= entries['owner_true']
        and true_either + false_union <= entries['uid_exact_mia_sentinel'] + entries['public_id_exact_mia_sentinel']
        and true_either <= entries['uid_exact_mia_sentinel'] - false_uid
            + entries['public_id_exact_mia_sentinel'] - false_public, 'response_shape')


def _validate_result(result, completed):
    extra = set() if completed else {'failure_code', 'attempt_consumption'}
    require(type(result) is dict and set(result) == set(new_state()) | {'provider_request_count'} | extra
        and type(result['stage']) is str and result['stage'] in STAGES
        and type(result['application_dispatch_count']) is int and result['application_dispatch_count'] in (0, 1)
        and result['provider_request_count'] is None, 'response_shape')
    if not completed:
        require(type(result['failure_code']) is str and result['failure_code'] in FINITE | {'unknown_exception'}
            and result['attempt_consumption'] == 'claim_may_be_consumed_no_retry', 'response_shape')
    stage, event, count = result['stage'], result['last_event'], result['application_dispatch_count']
    observation = result['project_observation']
    if stage in ('preflight', 'claim', 'credentials'):
        require(not completed and count == 0 and event is None and result['last_endpoint'] is None
            and observation is None, 'response_shape')
    else:
        require(result['last_endpoint'] == ENDPOINT and type(event) is str
            and event in ('intent', 'response_received', 'observation_saved')
            and (count == 1 or (event == 'intent' and observation is None)), 'response_shape')
        if stage in ('postflight', 'report') or completed:
            require(count == 1 and event == 'observation_saved' and observation is not None, 'response_shape')
        if completed:
            require(stage == 'project', 'response_shape')
        if event == 'observation_saved':
            require(observation is not None, 'response_shape')
    if observation is not None:
        require(count == 1 and event != 'intent', 'response_shape')
        _validate_observation(observation)


def validate_output(raw, actual_exit, args):
    """Pure stdout validation: exact observed exit, binding, schema and report pin.

    A failure can lack a durable report if claim/publication itself failed. Its
    finite envelope is still source-bound, but report=None supplies no authenticated
    report pin; partial writes can still exist and remain spent/ambiguous.
    This reconstructs report bytes; it does not reread filesystem evidence.
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
                    client = environment.guarded_client()
                    def request(endpoint, payload):
                        remaining(deadline)
                        require(endpoint == ENDPOINT and payload == {'projectId': PROJECT}, 'dispatch')
                        environment.require_safe_environment()
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
