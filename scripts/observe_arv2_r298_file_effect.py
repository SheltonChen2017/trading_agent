"""One read-only R298 target-file observation after the spent A6 write refusal.

No lock, file write, history, capacity, compile or launch endpoint is available.
A separate exact one-shot freeze and independent review or explicit scoped
waiver precede contact. A1-A6 stay spent. File equality is current observation,
not proof of A6 causality, continuous integrity, privacy or launch authority.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import observe_arv2_r298_lock_access as support
from scripts import run_arv2_r298_access_recovery as a6
from scripts import arv2_r298_file_effect as effect

Refused, require, canonical, sha = support.Refused, support.require, support.canonical, support.sha
_metadata, _source_digest, _git, alarm = support._metadata, support._source_digest, support._git, support.alarm
SOURCE = ROOT / 'scripts/observe_arv2_r298_file_effect.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_file_effect/R316-20261024-A'
PYTHON, BRANCH = support.PYTHON, support.BRANCH
SCHEMA = 'arv2-r298-file-effect-observation-v1'
PROJECT = 38364439
TARGET = 'accepted_risk_order_level_input_runtime.py'
PROJECTION_SHA256 = 'f67148cd717e207be9d44f088749c0443bb696d9c4f38f512eb6cbf483fd9662'
EXPECTED_SOURCE = {'byte_count': 23055, 'sha256': 'c34e42d894dc88e74ce37899622a7f728bafdac9320ce2775736ba06b7ad463e'}
DEADLINE_SECONDS, MAX_OUTPUT = 90, 24576
ENDPOINTS = ('projects/read', 'projects/collaboration/read', 'files/read')
PAYLOADS = ({'projectId': PROJECT}, {'projectId': PROJECT}, {'projectId': PROJECT, 'name': TARGET})
NEW_PINS = {
    'scripts/run_arv2_r298_access_recovery.py': '1e02200da124c4143437c022e9a29ff251d5d284ceb3158431187ded0686608e',
    'scripts/observe_arv2_r298_lock_access.py': '9e573ba92f31921f8223ae8ff0d48ee82e38a90ef37d821158413a1852afbfc5',
    'scripts/arv2_r298_file_effect.py': '088adbad3bccaac5b6bf1abe35e0b11ef6288ae4998e3783a3cfa08a514eb438',
}
FALSE_FLAGS = {'operational_retry_authority': False, 'collaborator_policy_accepted': False,
    'project_ready': False, 'point_in_time_proven': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False, 'strategy_result_accepted': False, 'a7_authorized': False,
    'privacy_verified': False, 'a6_effect_proven': False, 'original_update_error_recovered': False}
STAGES = ('preflight', 'claim', 'credentials', 'observe', 'postflight', 'report')
FINITE = frozenset(('arguments', 'context', 'source', 'deadline', 'claim', 'control',
    'control_changed', 'bound', 'json', 'dispatch', 'response_shape', 'client', 'remote_observation'))
FILE_NAMES = frozenset(('claim.json', 'report.json', 'failure.json',
    'project-intent.json', 'project-response.json', 'collaborators-intent.json',
    'collaborators-response.json', 'files-intent.json', 'files-response.json'))


def selected_pins():
    return {**a6.selected_pins(), **NEW_PINS}


def remaining(deadline):
    left = deadline - time.monotonic()
    require(left > 0, 'deadline')
    return left


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': str(PYTHON),
        'control': str(CONTROL), 'project_id': PROJECT, 'target_name': TARGET,
        'projection_sha256': PROJECTION_SHA256, 'expected_source': dict(EXPECTED_SOURCE),
        'purpose': 'observe_current_single_file_after_a6_ambiguous_update_not_replay_or_recovery',
        'source_pins': selected_pins(), 'endpoints': list(ENDPOINTS),
        'payloads': [dict(item) for item in PAYLOADS], 'max_application_dispatches': 3,
        'deadline_seconds': DEADLINE_SECONDS, 'request_timeout_seconds': 30,
        'max_output_bytes': MAX_OUTPUT, 'max_control_files': 8, 'automatic_retry': False,
        'a1_through_a6_and_all_old_observers_remain_spent': True,
        'sequential_reads_not_atomic': True, 'actual_exit_required_externally': True,
        'shared_look': 0, 'development_look': 0, 'infrastructure_look': 0, **FALSE_FLAGS}


def binding(args):
    def checked(value, length):
        return value if type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) else None
    return {'schema': SCHEMA, 'expected_head': checked(args.expected_head, 40),
        'caller_sha256': checked(args.caller_sha256, 64),
        'profile_sha256': sha(canonical(profile_record())), 'project_id': PROJECT}


def _preflight(args, deadline):
    require('pytest' not in sys.modules and 'PYTEST_CURRENT_TEST' not in os.environ
        and not any(key.startswith('_pytest') for key in tuple(sys.modules)), 'context')
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE, 'context')
    require(binding(args)['expected_head'] is not None and binding(args)['caller_sha256'] is not None, 'arguments')
    for relative, pin in selected_pins().items():
        require(_source_digest(ROOT / relative) == pin, 'source')
    require(_source_digest(SOURCE) == args.caller_sha256, 'source')
    from scripts import arv2_newrule_execution_environment as environment
    environment._require_environment()
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


def expected_source():
    # Public frozen source projection only: never a package/artifact/control read.
    from scripts import arv2_r298_recovery_evidence as evidence
    projected = evidence.reconstruct_projection()
    require(projected.projection_sha256 == PROJECTION_SHA256, 'source')
    matches = [item.source_bytes for item in projected.source_files if item.project_path == TARGET]
    require(len(matches) == 1 and type(matches[0]) is bytes
        and {'byte_count': len(matches[0]), 'sha256': sha(matches[0])} == EXPECTED_SOURCE, 'source')
    return matches[0]


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
        require(type(name) is str and name in FILE_NAMES
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


class ReadOnlyClient:
    """Exactly three ordered scoped reads, never a general operational client."""
    __slots__ = ('__api', '__next')

    def __init__(self):
        from scripts import arv2_newrule_execution_environment as environment
        environment.require_safe_environment()
        from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
        self.__api, self.__next = old._client(), 0
        environment.require_safe_environment()
        self.__check()

    def __repr__(self):
        return '<ReadOnlyR298FileEffectClient>'

    def __check(self):
        from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
        api = self.__api
        require(type(api) is old.QuantConnectClient and api._base_url == old.API_BASE
            and api._transport is old.coverage._bounded_transport
            and type(api._timeout) in (int, float) and api._timeout == 30, 'client')

    def request(self, endpoint, payload):
        from scripts import arv2_newrule_execution_environment as environment
        environment.require_safe_environment()
        self.__check()
        require(type(endpoint) is str and self.__next < 3 and endpoint == ENDPOINTS[self.__next]
            and type(payload) is dict and set(payload) == set(PAYLOADS[self.__next])
            and all(type(payload[key]) is type(item) and payload[key] == item
                for key, item in PAYLOADS[self.__next].items()), 'dispatch')
        self.__next += 1  # An ambiguous transport consumes its dispatch; never retry.
        return self.__api.request(endpoint, payload)


def finite_error(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    return 'unknown_exception'


def _validate_result(result):
    if result is not None:
        effect.validate_observation(result)
        require(result['expected_source'] == EXPECTED_SOURCE, 'source')


def validate_output(raw, actual_exit, args):
    """Pure once-only external check: actual exit plus finite output/report pin.

    Never reads an output leaf, and never turns diagnostic completion into
    recovery authority. Missing failure pin cannot exclude partial persistence.
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
        and set(value) == set(expected) | set(FALSE_FLAGS) |
            {'observation_completed', 'stage', 'failure_code', 'result', 'report'}
        and all(type(value[key]) is type(item) and value[key] == item for key, item in expected.items())
        and all(value[key] is False for key in FALSE_FLAGS)
        and type(value['stage']) is str and value['stage'] in STAGES
        and value['observation_completed'] is (actual_exit == 0), 'response_shape')
    _validate_result(value['result'])
    if actual_exit == 0:
        require(value['stage'] == 'report' and value['failure_code'] is None
            and type(value['result']) is dict and value['result']['observation_complete'] is True, 'response_shape')
    else:
        require(type(value['failure_code']) is str
            and value['failure_code'] in FINITE | {'unknown_exception'}, 'response_shape')
    if value['stage'] in ('preflight', 'claim', 'credentials'):
        require(value['result'] is None, 'response_shape')
    if value['stage'] in ('postflight', 'report'):
        require(type(value['result']) is dict and value['result']['observation_complete'] is True, 'response_shape')
    report_raw = canonical({key: item for key, item in value.items() if key != 'report'})
    pin = value['report']
    require((actual_exit == 2 and pin is None) or (type(pin) is dict and set(pin) == {'sha256', 'byte_count'}
        and type(pin['byte_count']) is int
        and pin == {'sha256': sha(report_raw), 'byte_count': len(report_raw)}), 'response_shape')
    return value


def run(args):
    stage, result, failure_pin = 'preflight', None, None
    deadline = time.monotonic() + DEADLINE_SECONDS
    def report(completed, error=None):
        return {**binding(args), 'observation_completed': completed, 'stage': stage,
            'failure_code': None if error is None else finite_error(error), 'result': result, **FALSE_FLAGS}
    try:
        with alarm(deadline):
            _preflight(args, deadline)
            source = expected_source()
            remaining(deadline)
            from scripts import arv2_newrule_execution_environment as environment
            environment._bootstrap_cli_logging()
            stage = 'claim'
            with Store() as store:
                try:
                    store.write('claim.json', {**binding(args), 'observation_claim_consumed': True,
                        'shared_look': 0, 'development_look': 0, 'infrastructure_look': 0})
                    stage = 'credentials'
                    client = ReadOnlyClient()
                    def request(endpoint, payload):
                        remaining(deadline)
                        return client.request(endpoint, payload)
                    def journal(marker, event):
                        remaining(deadline)
                        require(type(marker) is str and marker in ('read-project', 'read-collaborators', 'read-files')
                            and type(event) is dict and event.get('event') in ('intent', 'observed'), 'dispatch')
                        suffix = 'intent' if event['event'] == 'intent' else 'response'
                        store.write(marker.removeprefix('read-') + '-' + suffix + '.json', event)
                    stage = 'observe'
                    result = effect.FileEffectObserver(source).observe(request, journal)
                    _validate_result(result)
                    require(result['observation_complete'] is True, 'remote_observation')
                    stage = 'postflight'
                    _preflight(args, deadline)
                    environment.require_safe_environment()
                    stage = 'report'
                    output = report(True)
                    pin = store.write('report.json', output)
                    remaining(deadline)
                    store.verify()
                    output = {**output, 'report': pin}
                except BaseException as error:
                    try:
                        failure_pin = store.write('failure.json', report(False, error))
                    except BaseException:
                        pass  # Retain partial evidence; never cleanup or retry.
                    raise
            raw = canonical(output)
            require(len(raw) <= MAX_OUTPUT, 'bound')
            sys.stdout.write(raw.decode('ascii'))
            sys.stdout.flush()
            return 0
    except BaseException as error:
        output = {**report(False, error), 'report': failure_pin}
        sys.stdout.write(canonical(output).decode('ascii'))
        sys.stdout.flush()
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    raise SystemExit(main())
