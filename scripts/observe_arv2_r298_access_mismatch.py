"""One read-only current R298 collaborator-shape diagnostic after spent A9.

Only projects/read then projects/collaboration/read are dispatched. The frozen
R314 projector is reused as a pure component, never its entrypoint/control.
Current field types, hashes and fixed equalities are evidence, not a refreshed
allowlist or proof of the historical A9 response, privileges or a lease.
Separate exact committed one-shot authority is required. No upload, lock,
permission, compile, capacity or launch action is exposed; A1-A9 stay spent.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import observe_arv2_r298_lock_access as projection
from scripts import arv2_r298_collaborator_access as policy
from scripts.observe_arv2_r298_idleness import Refused, canonical, require, sha

SOURCE = ROOT / 'scripts/observe_arv2_r298_access_mismatch.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_access_mismatch/R321-20261024-A'
PYTHON = Path('/Users/sheltonchen/.venvs/trading_agent-py313/bin/python')
BRANCH = 'codex/strategy-analyst-revisions-v2'
SCHEMA = 'arv2-r298-access-mismatch-v1'
PROJECT = 38364439
ENDPOINTS = ('projects/read', 'projects/collaboration/read')
DEADLINE_SECONDS, MAX_OUTPUT = 60, 32768
OWNER_ROW_SHA256 = '707a30618e122e49fe6fa75364451b5b7c50e1019a68a89ffc0cd3ae3c8e0b78'
A5_ROW_SHA256 = 'f9a933141393262edb66e3e8248ed75ebf4518668039e1a27af6734f26f58b9d'
# Selected protocol/source/transport bindings, not whole-interpreter integrity.
SOURCE_PINS = {
    **projection.SOURCE_PINS,
    'scripts/observe_arv2_r298_lock_access.py': '9e573ba92f31921f8223ae8ff0d48ee82e38a90ef37d821158413a1852afbfc5',
    'scripts/arv2_r298_collaborator_access.py': '57333e2d6932f3b75bb42bc59214ebda2ce9afdf65b9054b7edc7ee5cbd37d93',
}
FALSE_FLAGS = {key: False for key in (
    'operational_retry_authority', 'collaborator_policy_accepted', 'project_ready',
    'point_in_time_proven', 'formal_forward_ready', 'paper_or_live_ready',
    'strategy_result_accepted', 'stored_record_proven', 'synthetic_entry_proven',
    'edit_lock_proven', 'privacy_verified', 'atomic_snapshot_proven',
    'a10_authorized', 'historical_a9_response_reconstructed')}


def remaining(deadline):
    left = deadline - time.monotonic()
    require(left > 0, 'deadline')
    return left


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': BRANCH, 'python': str(PYTHON),
        'control': str(CONTROL), 'project_id': PROJECT,
        'purpose': 'observe_current_post_a9_extra_row_predicates_without_policy_acceptance',
        'source_pins': dict(SOURCE_PINS), 'endpoints': list(ENDPOINTS),
        'max_application_dispatches': 2, 'deadline_seconds': DEADLINE_SECONDS,
        'max_output_bytes': MAX_OUTPUT, 'max_collaborators': projection.MAX_COLLABORATORS,
        'owner_row_sha256': OWNER_ROW_SHA256, 'a5_row_sha256': A5_ROW_SHA256,
        'a5_code_source_id_sha256': sha(canonical(projection.A5_CODE_SOURCE_ID)),
        'automatic_retry': False, 'prior_observers_and_a1_through_a9_remain_spent': True,
        'preclaim_credential_presence_required': True, 'sequential_reads_not_atomic': True,
        'actual_exit_required_externally': True, 'shared_look': 0,
        'development_look': 0, 'infrastructure_look': 0, **FALSE_FLAGS}


def binding(args):
    def checked(value, length):
        return value if type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) else None
    return {'schema': SCHEMA, 'expected_head': checked(args.expected_head, 40),
        'caller_sha256': checked(args.caller_sha256, 64),
        'profile_sha256': sha(canonical(profile_record())), 'project_id': PROJECT}


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
    require(projection.ENDPOINTS == ENDPOINTS and projection.PROJECT == PROJECT
        and policy.OWNER_ROW_SHA256 == OWNER_ROW_SHA256 and policy.A5_ROW_SHA256 == A5_ROW_SHA256
        and policy.A5_CODE_SOURCE_ID == projection.A5_CODE_SOURCE_ID, 'source')
    for relative, pin in SOURCE_PINS.items():
        require(projection._source_digest(ROOT / relative) == pin, 'source')
    require(projection._source_digest(SOURCE) == args.caller_sha256, 'source')
    from scripts import arv2_newrule_execution_environment as environment
    environment._require_environment()  # Names/shapes, no credential acquisition.
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


def require_credentials_present():
    """Presence-only preclaim guard; never returns/prints credential values."""
    for key in ('QC_USER_ID', 'QC_API_TOKEN'):
        value = os.environ.get(key)
        require(type(value) is str and bool(value.strip()), 'context')


def response_snapshot(value):
    """Strict memory-only JSON/scope/error check before the frozen projector."""
    try:
        return policy._response(value)
    except policy.AccessRefused as error:
        code = policy.finite_error(error)['code']
        mapping = {'json_shape': 'json', 'response_bound': 'bound',
            'response_refused': 'response_refused', 'project_id': 'project_id',
            'organization': 'organization'}
        raise Refused(mapping.get(code, 'response_shape')) from None


class Store:
    """Own exclusive leaf only, with retained held/named files and no cleanup.

    A partial claim is ambiguous/spent. Scoped checks are not native ACL/xattr
    authentication, whole-tree or continuous-integrity proof.
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
            require(projection._metadata(held) == projection._metadata(os.fstat(fd))
                and held.st_uid == os.getuid() and stat.S_IMODE(held.st_mode) == 0o700
                and set(os.listdir(fd)) == set(self.files), 'control_changed')
            for name, (file_fd, info, raw) in self.files.items():
                require(projection._metadata(os.fstat(file_fd)) == info == projection._metadata(
                    os.stat(name, dir_fd=self.fd, follow_symlinks=False)), 'control_changed')
                require(os.pread(file_fd, len(raw) + 1, 0) == raw, 'control_changed')
            require(projection._metadata(held) == projection._metadata(os.fstat(fd)), 'control_changed')
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
            self.files[name] = (fd, projection._metadata(info), raw)
        except BaseException:
            os.close(fd)
            raise
        os.fsync(self.fd)
        self.verify()
        return {'sha256': sha(raw), 'byte_count': len(raw)}


def policy_comparison(result):
    """Derived finite predicates, NOT policy admission or automatic pin refresh."""
    def rows(observed):
        if observed is None or observed['collaborators']['json_type'] != 'array':
            return None
        output = []
        for row in observed['collaborators']['records']:
            shape = None
            if row['json_type'] == 'object':
                shape = {
                    'owner_exact_false': row['owner']['valid_boolean'] and row['owner']['value'] is False,
                    'uid_present_null': row['uid']['present'] and row['uid']['json_type'] == 'null',
                    'permission_exact_write': row['permission'] == 'write',
                    'live_control_exact_true': row['live_control']['valid_boolean'] and row['live_control']['value'] is True,
                    'name_equals_a5': row['name']['equals_a5_code_source_id'],
                    'public_id_equals_a5': row['public_id']['equals_a5_code_source_id'],
                    'code_source_id_absent': not row['code_source_id']['present'],
                }
            output.append({'row_sha256': row['row_sha256'],
                'equals_frozen_owner_row': row['row_sha256'] == OWNER_ROW_SHA256,
                'equals_frozen_a5_row': row['row_sha256'] == A5_ROW_SHA256,
                'equals_historical_d3_mia_row': row['row_equals_d3_mia'],
                'a5_extra_shape_predicates': shape,
                'all_a5_extra_shape_predicates': all(shape.values()) if shape is not None else None})
        return output
    return {'project_rows': rows(result['project_observation']),
        'dedicated_rows': rows(result['dedicated_observation'])}


def report(args, completed, result):
    return {**binding(args), 'observation_completed': completed, 'result': result,
        'comparison_to_frozen_policy': policy_comparison(result), **FALSE_FLAGS}


def _validate_known_row_facts(result):
    """Known historical hashes must not attest contradictory finite facts.

    Unknown hashes remain admissible diagnostic evidence, not policy matches.
    This checks internal evidence coherence only; no live row pin is refreshed.
    """
    compared = policy_comparison(result)
    for name, rows_key in (('project_observation', 'project_rows'),
        ('dedicated_observation', 'dedicated_rows')):
        observation, rows = result[name], compared[rows_key]
        if rows is None:
            continue
        for row, facts in zip(observation['collaborators']['records'], rows):
            if row['row_sha256'] == A5_ROW_SHA256:
                require(row['json_type'] == 'object'
                    and facts['all_a5_extra_shape_predicates'] is True, 'response_shape')
            if row['row_sha256'] == OWNER_ROW_SHA256:
                require(row['json_type'] == 'object', 'response_shape')
                require(row['owner']['valid_boolean'] is True and row['owner']['value'] is True
                    and row['uid']['present'] is True and row['uid']['valid_positive_integer'] is True
                    and row['uid']['equals_project_owner'] is True and row['permission'] == 'write'
                    and row['live_control']['valid_boolean'] is True
                    and row['live_control']['value'] is True, 'response_shape')


def validate_output(raw, actual_exit, args):
    """Authenticate only supplied finite bytes/actual exit; no report reread."""
    require(type(actual_exit) is int and actual_exit in (0, 2) and type(raw) is bytes
        and 0 < len(raw) <= MAX_OUTPUT, 'bound')
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise Refused('json') from None
    require(type(value) is dict and canonical(value) == raw, 'json')
    expected = binding(args)
    require(expected['expected_head'] is not None and expected['caller_sha256'] is not None
        and set(value) == set(expected) | set(FALSE_FLAGS) | {'observation_completed',
            'result', 'report', 'comparison_to_frozen_policy'}
        and all(type(value[key]) is type(item) and value[key] == item for key, item in expected.items())
        and all(value[key] is False for key in FALSE_FLAGS)
        and value['observation_completed'] is (actual_exit == 0), 'response_shape')
    projection._validate_result(value['result'], actual_exit == 0)
    _validate_known_row_facts(value['result'])
    require(canonical(value['comparison_to_frozen_policy']) == canonical(policy_comparison(value['result'])), 'response_shape')
    expected_raw = canonical({key: item for key, item in value.items() if key != 'report'})
    pin = value['report']
    require((actual_exit == 2 and pin is None) or (type(pin) is dict and set(pin) == {'sha256', 'byte_count'}
        and type(pin['byte_count']) is int
        and pin == {'sha256': sha(expected_raw), 'byte_count': len(expected_raw)}), 'response_shape')
    return value


def run(args):
    state, deadline, failure_pin = projection.new_state(), time.monotonic() + DEADLINE_SECONDS, None
    try:
        with projection.alarm(deadline):
            _preflight(args, deadline)
            require_credentials_present()  # Before claim or any private/control path.
            from scripts import arv2_newrule_execution_environment as environment
            environment._bootstrap_cli_logging()
            state['stage'] = 'claim'
            with Store() as store:
                try:
                    store.write('claim.json', {**binding(args), 'observation_claim_consumed': True,
                        'shared_look': 0, 'development_look': 0, 'infrastructure_look': 0})
                    state['stage'] = 'credentials'
                    client = projection.ReadOnlyClient()
                    def request(endpoint, payload):
                        remaining(deadline)
                        return response_snapshot(client.request(endpoint, payload))
                    result = projection.observe(request, store.write, state, deadline)
                    state['stage'] = 'postflight'
                    _preflight(args, deadline)
                    environment.require_safe_environment()
                    state['stage'] = 'report'
                    output = report(args, True, result)
                    pin = store.write('report.json', output)
                    remaining(deadline)
                    store.verify()
                    output = {**output, 'report': pin}
                except BaseException as error:
                    failure = report(args, False, projection.finite_failure(error, state))
                    try:
                        failure_pin = store.write('failure.json', failure)
                    except BaseException:
                        pass  # Preserve partial evidence; never a retry or cleanup.
                    raise
            raw = canonical(output)
            require(len(raw) <= MAX_OUTPUT, 'bound')
            sys.stdout.write(raw.decode('ascii'))
            sys.stdout.flush()
            return 0
    except BaseException as error:
        output = {**report(args, False, projection.finite_failure(error, state)), 'report': failure_pin}
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
