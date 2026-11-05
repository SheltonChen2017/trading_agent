"""One read-only post-P current access observation; no mutation or launch.

Two fixed requests retain only a strict redacted projection and the exact
finite access predicate. A failed observation never grants recovery authority.
All previous controls and attempts remain spent and are not read here.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_r298_quote_diagnostic as prior
from scripts import run_arv2_r298_raw_reference_diagnostic as a17
from scripts import arv2_r298_collaborator_access as access
from scripts import arv2_r298_mia_access_representation as current_access
from scripts import arv2_newrule_execution_environment as environment

SOURCE = ROOT / 'scripts/observe_arv2_r298_post_phase_access.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_post_phase_access/R323-20261025-Q'
PYTHON = prior.PYTHON
SCHEMA = 'arv2-r298-post-phase-access-q-v1'
DEADLINE_SECONDS, MAX_OUTPUT, MAX_FILES = 120, 128 * 1024, 8
MAX_ROW_KEYS = 32
ENDPOINTS = ('projects/read', 'projects/collaboration/read')
HELPER_NAME = 'arv2_r298_post_mia_access'
NEW_PINS = {
    'scripts/run_arv2_r298_quote_diagnostic.py': '770ce5b92fcd46e862a40a763b492d6561b55a82b4e244242a900eda71509257',
    'scripts/arv2_r298_post_mia_access.py': '09705275244935bce92c096e18d3beaaedd3eed13ab31deb8ef8788fb9df8672',
    'scripts/observe_arv2_r298_post_mia_access.py': '11958e8387755871b78f7ee0f24d7f286811974a89350e19402e260debdf9b08',
    'scripts/run_arv2_r298_raw_reference_diagnostic.py': '1f2f88de601312c1e5ee16381a64fdd091ada2ea7ab2a0709a991bbc6b6d71ff',
    'scripts/observe_arv2_r298_post_mia_access_a17.py': '21c1f99db2b0ab3029ad3a1957eaf9cb122c76465ae22445c2ad2c6f6621580c',
    'scripts/arv2_r298_mia_access_representation.py': '18cfacf19757fd6359747f1c78b93e662daf7492ac658f48673dd4d628d56a04',
    'scripts/arv2_r298_reference_series_phase_projection.py': 'fa8aadb86b7129cdada420e48dd8b8a670be91b13325e2c73e76840db5216fb4',
    'scripts/arv2_r298_reference_series_phase_remote.py': '660d8f5f2ac8d0bf7f1382d2667db9a229c44ee47d47d96cd1408a927da182fd',
    'scripts/run_arv2_r298_reference_series_phase.py': '22b9886c23ad4a912d30672fdc8f0a105d486e56856f297bbf861f872ff8f113',
}
FALSE_FLAGS = {'access_policy_accepted': False, 'operational_retry_authority': False,
    'project_ready': False, 'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False, 'strategy_result_accepted': False}
FINITE = frozenset(('arguments', 'host', 'git_state', 'source_pin', 'deadline',
    'claim_spent', 'control_changed', 'control_name', 'control_bound', 'control_write',
    'request_scope', 'output', 'output_bound', 'parent_failed', 'validator_failed',
    'execution_environment_refused', 'credential_handoff', 'qc_client_refused',
    'qc_not_configured', 'row_fields', 'refused', 'os_error', 'unknown_exception'))
canonical, parse, sha, metadata = prior.canonical, prior.parse, prior.sha, prior.metadata
capture, credential_shape = prior.capture, prior.credential_shape


class Refused(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Refused(code)


def remaining(deadline):
    value = deadline - time.monotonic()
    require(value > 0, 'deadline')
    return value


def helper():
    from scripts import arv2_r298_post_mia_access as module
    return module


def finite(error):
    if type(error) is current_access.AccessRefused:
        return 'current_access_' + current_access.finite_error(error)['code']
    if type(error) is access.AccessRefused:
        return 'access_' + access.finite_error(error)['code']
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    module = sys.modules.get('scripts.' + HELPER_NAME)
    if module is not None and type(error) is vars(module).get('Refused'):
        return 'projection_' + module.finite(error)
    if type(error) is environment.EnvironmentRefused:
        return 'execution_environment_refused'
    qc = sys.modules.get('research.quantconnect')
    if qc is not None:
        if type(error) is vars(qc).get('QuantConnectError'): return 'qc_client_refused'
        if type(error) is vars(qc).get('QuantConnectNotConfigured'): return 'qc_not_configured'
    if isinstance(error, OSError):
        return 'os_error'
    return 'unknown_exception'


def pins():
    values = dict(a17.pins())
    for name, pin in NEW_PINS.items():
        require(name not in values or values[name] == pin, 'source_pin')
        values[name] = pin
    return values


def _finite_code(value):
    codes = FINITE | {'access_' + code for code in access.FINITE_CODES | {'unknown'}}
    codes |= {'current_access_' + code for code in current_access.FINITE_CODES | {'unknown'}}
    codes |= {'projection_' + code for code in helper().FINITE | {'unknown'}}
    return type(value) is str and value in codes


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': prior.admitted.frozen.BRANCH,
        'python': str(PYTHON), 'control': str(CONTROL), 'source_pins': pins(),
        'project_id': access.PROJECT_ID, 'purpose': 'current_post_P_access_row_field_drift_observation_only',
        'endpoints': list(ENDPOINTS), 'max_application_dispatches': 2,
        'deadline_seconds': DEADLINE_SECONDS, 'max_output': MAX_OUTPUT,
        'prior_attempts_spent': True, 'old_control_reads': False,
        'response_bodies_retained': False, 'actual_exit_required': True,
        'automatic_retry': False, 'lock_changes': 0, 'uploads': 0,
        'capacity_calls': 0, 'compiles': 0, 'backtests': 0,
        'p_spent': True, 'p_actual_exit': 2, 'p_control_read': False,
        'p_parent_stdout_bytes': 791,
        'p_parent_stdout_sha256': 'a0bc0cd0822bd906302ef46c4d7bbcf0632a73cacaf19e3a39e8f50b0fb3ccef',
        'p_freeze_head': 'd2abfec65f0b45fa783fd65abf5080ba734098dd',
        'p_facts_documentary_only': True,
        'p_failure_code': 'access_general_row_pin', 'p_failure_stage': 'prepare',
        'p_application_dispatch_count': 2, 'p_returned_response_count': 2,
        'p_source_writes': 0, 'p_compiles': 0, 'p_jobs': 0,
        'historical_p_cause_authenticated': False,
        'legacy_redaction_schema': helper().SCHEMA,
        'legacy_failure_field': 'legacy_access_failure_code',
        'current_policy_schema': current_access.SCHEMA,
        'current_policy_source_sha256': NEW_PINS['scripts/arv2_r298_mia_access_representation.py'],
        'current_policy_unchanged': True,
        'row_field_hash_names': list(helper().ROW_FIELDS),
        'full_row_keys_maximum': MAX_ROW_KEYS,
        'full_row_key_pattern': '[A-Za-z_][A-Za-z0-9_]{0,63}',
        'full_row_fields_retained': 'field_name_type_and_canonical_value_hash_only',
        'field_hash_inventory_reconstitutes_whole_row': False,
        'field_hash_inventory_authenticates_raw_wire': False,
        'new_full_row_pin_accepted': False,
        'known_h_mia_row_sha256': current_access.MIA_ROW_SHA256,
        'known_h_mia_public_id_sha256': current_access.MIA_PUBLIC_ID_SHA256,
        'h_original_email_value_hash_available': False,
        'h_report_documentary_only': True,
        'h_report_sha256': current_access.OBSERVATION_REPORT_SHA256,
        'access_policy_changed': False,
        'same_user_sandbox': False, 'continuous_integrity_proven': False,
        'uninterruptible_io_or_suspension_bounded': False, **FALSE_FLAGS}


def binding(args):
    def checked(value, length):
        return value if type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) else None
    return {'schema': SCHEMA, 'expected_head': checked(args.expected_head, 40),
        'caller_sha256': checked(args.caller_sha256, 64),
        'profile_sha256': sha(canonical(profile_record()))}


def preflight(args, deadline):
    require(not prior.admitted.v5._under_test() and Path(__file__).absolute() == SOURCE
        and sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT, 'host')
    require(binding(args)['expected_head'] is not None and binding(args)['caller_sha256'] is not None,
            'arguments')
    environment._require_environment()
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
        (['branch', '--show-current'], prior.admitted.frozen.BRANCH),
        (['rev-parse', 'HEAD'], args.expected_head), (['status', '--porcelain'], '')):
        require(prior.admitted.v5._git(command, deadline).decode('ascii').strip() == expected, 'git_state')
    for name, pin in pins().items():
        require(pin != '0' * 64 and sha((ROOT / name).read_bytes()) == pin, 'source_pin')
    require(sha(SOURCE.read_bytes()) == args.caller_sha256, 'source_pin')
    blob = prior.admitted.v5._git(['cat-file', 'blob', args.expected_head + ':' + SOURCE.relative_to(ROOT).as_posix()],
                                  deadline, MAX_OUTPUT)
    require(sha(blob) == args.caller_sha256, 'source_pin')
    remaining(deadline)


class Store:
    """Exclusive new leaf, immutable records and endpoint metadata checks."""
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
                os.close(fd); fd = nxt
                info = os.fstat(fd)
                self.chain.append((info.st_dev, info.st_ino))
            self.fd = fd
            self.verify()
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self): return self
    def __exit__(self, *_): os.close(self.fd)

    def verify(self):
        other, chain = prior.admitted._storage_module()._walk(CONTROL)
        try:
            held, named = os.fstat(self.fd), os.fstat(other)
            require(chain == tuple(self.chain) and metadata(held) == metadata(named)
                and held.st_uid == os.getuid() and stat.S_IMODE(held.st_mode) == 0o700
                and set(os.listdir(other)) == set(self.files) and len(self.files) <= MAX_FILES
                and held.st_nlink == 2 + len(self.files), 'control_changed')
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
        require(0 < len(raw) <= MAX_OUTPUT, 'control_bound')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            view = memoryview(raw)
            while view:
                n = os.write(fd, view)
                require(n > 0, 'control_write'); view = view[n:]
            os.fsync(fd); os.fsync(self.fd)
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


def _client():
    environment.require_safe_environment()
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
    api = old._client()
    require(type(api) is old.QuantConnectClient and api._base_url == old.API_BASE
        and api._transport is old.coverage._bounded_transport and api._timeout == 30, 'request_scope')
    environment.require_safe_environment()
    return api


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _known_h_fields(hashes):
    """Only public H policy values, never infer an unreported email value."""
    fixed = {'owner': False, 'uid': None, 'name': 'Mia', 'permission': 'write', 'liveControl': True}
    result = {name: hashes[name] == sha(access._canonical(item)) for name, item in fixed.items()}
    result['publicId'] = hashes['publicId'] == current_access.MIA_PUBLIC_ID_SHA256
    result['codeSourceId'] = hashes['codeSourceId'] is None
    result['email'] = None
    return {name: result[name] for name in helper().ROW_FIELDS}


def row_details(project_response, dedicated_response, observation):
    """Supplement H redaction with bounded field inventories, never values."""
    module = helper()
    project, dedicated = module._snapshot(project_response), module._snapshot(dedicated_response)
    scoped, _ = module._scope(project, dedicated)
    output = {}
    for name, packet in (('general', scoped), ('dedicated', dedicated)):
        rows = packet.get('collaborators')
        details = []
        if type(rows) is list:
            require(len(rows) <= module.MAX_ROWS, 'row_fields')
            for row in rows:
                fields = row if type(row) is dict else {}
                require(len(fields) <= MAX_ROW_KEYS and all(type(key) is str
                    and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,63}', key) for key in fields), 'row_fields')
                hashes = {field: sha(access._canonical(fields[field])) if field in fields else None
                    for field in module.ROW_FIELDS}
                details.append({'row_sha256': sha(access._canonical(row)),
                    'known_field_sha256': hashes, 'h_known_field_matches': _known_h_fields(hashes),
                    'matches_h_known_mia_row': sha(access._canonical(row)) == current_access.MIA_ROW_SHA256,
                    'fields': [{'name': key, 'type': module._type(fields[key]),
                        'value_sha256': sha(access._canonical(fields[key]))} for key in sorted(fields)]})
        output[name] = details
    return validate_row_details(output, observation)


def validate_row_details(value, observation):
    require(type(value) is dict and set(value) == {'general', 'dedicated'}, 'output')
    module = helper()
    for view in ('general', 'dedicated'):
        rows = value[view]
        public_rows = observation[view]['rows']
        require(type(rows) is list and len(rows) == len(public_rows), 'output')
        for row, public in zip(rows, public_rows, strict=True):
            require(type(row) is dict and set(row) == {'row_sha256', 'known_field_sha256',
                'h_known_field_matches', 'matches_h_known_mia_row', 'fields'}
                and row['row_sha256'] == public['row_sha256']
                and type(row['matches_h_known_mia_row']) is bool
                and row['matches_h_known_mia_row'] is (row['row_sha256'] == current_access.MIA_ROW_SHA256), 'output')
            hashes = row['known_field_sha256']
            require(type(hashes) is dict and set(hashes) == set(module.ROW_FIELDS), 'output')
            for name, digest in hashes.items():
                require((public['field_types'][name] == 'missing' and digest is None)
                    or (public['field_types'][name] != 'missing' and _hash(digest)), 'output')
                if name in module.IDENTITY_FIELDS:
                    require(digest == public['identifier_value_sha256'][name], 'output')
            matches = row['h_known_field_matches']
            require(type(matches) is dict and set(matches) == set(module.ROW_FIELDS)
                and all((matches[name] is None if name == 'email' else type(matches[name]) is bool)
                    for name in matches) and matches == _known_h_fields(hashes), 'output')
            fields = row['fields']
            require(type(fields) is list and len(fields) <= MAX_ROW_KEYS, 'output')
            names = []
            for field in fields:
                require(type(field) is dict and set(field) == {'name', 'type', 'value_sha256'}
                    and type(field['name']) is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,63}', field['name'])
                    and type(field['type']) is str and field['type'] in module.TYPES - {'missing'}
                    and _hash(field['value_sha256']), 'output')
                names.append(field['name'])
                if field['name'] in module.ROW_FIELDS:
                    require(field['type'] == public['field_types'][field['name']]
                        and field['value_sha256'] == hashes[field['name']], 'output')
            require(names == sorted(set(names)) and (public['row_type'] == 'dict' or fields == []), 'output')
            require(set(names) & set(module.ROW_FIELDS) == {name for name in module.ROW_FIELDS
                if public['field_types'][name] != 'missing'}, 'output')
    require(len(canonical(value)) <= MAX_OUTPUT, 'output_bound')
    return parse(canonical(value))


def run(args, deadline):
    credential_shape().clear()
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'read_only': True, 'prior_attempts_spent': True})
        state = {'stage': 'credentials', 'application_dispatch_count': 0,
                 'response_count': 0, 'last_endpoint': None, 'last_response_received': False}
        try:
            api, responses = _client(), []
            for index, endpoint in enumerate(ENDPOINTS):
                state['stage'] = 'project' if index == 0 else 'collaboration'
                remaining(deadline); environment.require_safe_environment()
                require(state['application_dispatch_count'] == index, 'request_scope')
                directory.write('request-' + str(index) + '-intent.json',
                    {**binding(args), 'endpoint': endpoint, 'project_id': access.PROJECT_ID})
                state['last_endpoint'], state['last_response_received'] = endpoint, False
                state['application_dispatch_count'] += 1
                response = api.request(endpoint, {'projectId': access.PROJECT_ID})
                state['response_count'] += 1; state['last_response_received'] = True
                raw = access._canonical(response)
                require(0 < len(raw) <= access.MAX_RESPONSE_BYTES, 'output_bound')
                directory.write('request-' + str(index) + '-observed.json',
                    {**binding(args), 'endpoint': endpoint, 'response_sha256': sha(raw),
                     'response_byte_count': len(raw)})
                responses.append(response)
            state['stage'] = 'projection'
            observation = helper().observe(*responses)
            details = row_details(*responses, observation)
            try:
                access.verify_access(*responses)
                access_code = None
            except access.AccessRefused as error:
                access_code = access.finite_error(error)['code']
                require(access_code in access.FINITE_CODES, 'output')
            require(observation['access_failure_code'] == access_code, 'output')
            try:
                current_access.verify_access(*responses)
                current_code = None
            except current_access.AccessRefused as error:
                current_code = current_access.finite_error(error)['code']
                require(current_code in current_access.FINITE_CODES, 'output')
            responses.clear()
            result = {'terminal': 'observed', 'application_dispatch_count': 2,
                'legacy_access_failure_code': access_code, 'current_failure_code': current_code,
                'current_policy_check': 'passed' if current_code is None else 'refused',
                'observation': observation, 'row_details': details, **FALSE_FLAGS}
            validate_result(result)
            state['stage'] = 'postflight'; preflight(args, deadline)
            state['stage'] = 'report'
            pin = directory.write('report.json', {**binding(args), 'result': result})
            return {'result': result, 'report': pin}
        except BaseException as error:
            failed = {'failure_code': finite(error), 'state': state,
                'attempt_consumption': 'consumed_or_ambiguous_no_retry', **FALSE_FLAGS}
            try: directory.write('failure.json', {**binding(args), **failed})
            except BaseException: pass
            return {'failure': failed}


def validate_result(result):
    require(type(result) is dict and set(result) == {'terminal', 'application_dispatch_count',
        'legacy_access_failure_code', 'current_failure_code', 'current_policy_check',
        'observation', 'row_details', *FALSE_FLAGS}
        and result['terminal'] == 'observed'
        and type(result['application_dispatch_count']) is int and result['application_dispatch_count'] == 2
        and (result['legacy_access_failure_code'] is None or type(result['legacy_access_failure_code']) is str
             and result['legacy_access_failure_code'] in access.FINITE_CODES)
        and ((result['current_failure_code'] is None and result['current_policy_check'] == 'passed')
            or (type(result['current_failure_code']) is str and result['current_failure_code'] in current_access.FINITE_CODES
                and result['current_policy_check'] == 'refused'))
        and all(result[key] is False for key in FALSE_FLAGS), 'output')
    helper().validate_observation(result['observation'])
    require(result['observation']['access_failure_code'] == result['legacy_access_failure_code'], 'output')
    validate_row_details(result['row_details'], result['observation'])
    if result['current_failure_code'] is None:
        observation = result['observation']
        project, general, dedicated = observation['project'], observation['general'], observation['dedicated']
        permissions = observation['dedicated_permissions']
        require(project['code_running'] == 'false' and project['public'] in ('missing', 'false')
            and general['container_type'] == dedicated['container_type'] == 'list'
            and type(general['count']) is int and 1 <= general['count'] <= 3 and dedicated['count'] == 1
            and permissions['permission_type'] == 'str' and permissions['permission'] == 'write'
            and permissions['live_control_type'] == 'bool' and permissions['live_control'] == 'true', 'output')
        owner = dedicated['rows'][0]
        require(owner['matches_known_owner_row'] is True and owner['uid_matches_project_owner'] is True
            and owner['field_types']['owner'] == 'bool' and owner['field_types']['uid'] == 'int'
            and owner['field_types']['permission'] == 'str' and owner['field_types']['liveControl'] == 'bool'
            and owner['owner'] == 'true' and owner['permission'] == 'write' and owner['live_control'] == 'true', 'output')
        digests = [row['row_sha256'] for row in general['rows']]
        require(len(set(digests)) == len(digests) and current_access.OWNER_ROW_SHA256 in digests
            and set(digests) <= {current_access.OWNER_ROW_SHA256, current_access.A5_ROW_SHA256,
                current_access.MIA_ROW_SHA256}, 'output')
        for row, details in zip(general['rows'], result['row_details']['general'], strict=True):
            if row['row_sha256'] == current_access.OWNER_ROW_SHA256:
                require(row['uid_matches_project_owner'] is True and row['owner'] == 'true'
                    and row['permission'] == 'write' and row['live_control'] == 'true', 'output')
            if row['row_sha256'] == current_access.MIA_ROW_SHA256:
                require(row['field_types']['owner'] == 'bool' and row['field_types']['uid'] == 'null'
                    and row['field_types']['name'] == row['field_types']['publicId'] == row['field_types']['email'] == 'str'
                    and row['field_types']['permission'] == 'str' and row['field_types']['liveControl'] == 'bool'
                    and row['field_types']['codeSourceId'] == 'missing' and row['owner'] == 'false'
                    and row['permission'] == 'write' and row['live_control'] == 'true'
                    and all(flag is True for name, flag in details['h_known_field_matches'].items() if name != 'email'), 'output')


def validate_output(raw, actual_exit, args):
    require(type(actual_exit) is int and actual_exit in (0, 2) and type(raw) is bytes
        and 0 < len(raw) <= MAX_OUTPUT, 'output')
    value = parse(raw)
    require(type(value) is dict and value.get('binding') == binding(args), 'output')
    if set(value) == {'binding', 'preflight_failure'}:
        require(actual_exit == 2 and _finite_code(value['preflight_failure']), 'output')
        return value
    require(set(value) == {'binding', 'outcome'} and type(value['outcome']) is dict, 'output')
    outcome = value['outcome']
    if set(outcome) == {'failure'}:
        failed = outcome['failure']
        require(actual_exit == 2 and type(failed) is dict
            and set(failed) == {'failure_code', 'state', 'attempt_consumption', *FALSE_FLAGS}
            and _finite_code(failed['failure_code'])
            and failed['attempt_consumption'] == 'consumed_or_ambiguous_no_retry'
            and all(failed[key] is False for key in FALSE_FLAGS), 'output')
        state = failed['state']
        require(type(state) is dict and set(state) == {'stage', 'application_dispatch_count',
            'response_count', 'last_endpoint', 'last_response_received'}
            and state['stage'] in ('credentials', 'project', 'collaboration', 'projection', 'postflight', 'report')
            and type(state['application_dispatch_count']) is int
            and 0 <= state['application_dispatch_count'] <= 2
            and type(state['response_count']) is int
            and 0 <= state['response_count'] <= state['application_dispatch_count']
            and type(state['last_response_received']) is bool
            and (state['last_endpoint'] is None or type(state['last_endpoint']) is str
                 and state['last_endpoint'] in ENDPOINTS), 'output')
        count = state['application_dispatch_count']
        require((count == 0 and state['response_count'] == 0 and state['last_endpoint'] is None
                 and state['last_response_received'] is False)
            or (count in (1, 2) and state['last_endpoint'] == ENDPOINTS[count - 1]
                and state['response_count'] == count - (not state['last_response_received'])), 'output')
        require((state['stage'] == 'credentials' and count == 0)
            or (state['stage'] == 'project' and count <= 1)
            or (state['stage'] == 'collaboration' and count in (1, 2))
            or (state['stage'] in ('projection', 'postflight', 'report')
                and count == state['response_count'] == 2), 'output')
    else:
        require(actual_exit == 0 and set(outcome) == {'result', 'report'}, 'output')
        validate_result(outcome['result'])
        report = canonical({**binding(args), 'result': outcome['result']})
        require(outcome['report'] == {'byte_count': len(report), 'sha256': sha(report)}, 'output')
    return value


def observe(args):
    credentials, parent_env = {}, {}
    outer = {'schema': SCHEMA + '-observer', 'parent': None, 'validator': None,
             'output_authenticated': False, 'output': None, 'failure_code': None}
    try:
        credentials = credential_shape()
        runtime = Path(tempfile.mkdtemp(prefix='r323-post-phase-', dir=ROOT / '.pytest_cache'))
        safe = prior.capture_support._environment(runtime)
        parent_env = prior.capture_support._environment(runtime, credentials)
        raw, errors, observed = capture([str(PYTHON), '-B', str(SOURCE), 'run',
            '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256],
            parent_env, DEADLINE_SECONDS + 30, stdout_limit=MAX_OUTPUT)
        outer['parent'] = observed
        credentials.clear(); parent_env.clear()
        require(observed['bound'] is None and not errors and type(observed['actual_exit']) is int
            and observed['actual_exit'] in (0, 2), 'parent_failed')
        command = ['/usr/bin/sandbox-exec', '-p', prior.native_profile(artifacts=True), str(PYTHON), '-B',
            str(SOURCE), 'validate', '--expected-head', args.expected_head,
            '--caller-sha256', args.caller_sha256, '--actual-exit', str(observed['actual_exit'])]
        valid, stderr, checked = capture(command, safe, 20, input_bytes=raw, stdout_limit=MAX_OUTPUT)
        outer['validator'] = checked
        require(type(checked['actual_exit']) is int and checked['actual_exit'] == 0
            and checked['bound'] is None and not stderr, 'validator_failed')
        outer['output'] = parse(valid); outer['output_authenticated'] = True
        require(len(canonical(outer)) <= MAX_OUTPUT + 4096, 'output_bound')
        return outer, observed['actual_exit']
    except BaseException as error:
        outer['failure_code'] = finite(error)
        return outer, 2
    finally:
        credentials.clear(); parent_env.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('observe', 'run', 'validate'))
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--actual-exit', type=int)
    args = parser.parse_args(argv)
    if args.operation == 'observe':
        result, code = observe(args)
        sys.stdout.buffer.write(canonical(result)); return code
    deadline = time.monotonic() + (20 if args.operation == 'validate' else DEADLINE_SECONDS)
    try:
        with prior.admitted.helpers._alarm(deadline):
            preflight(args, deadline); environment._bootstrap_cli_logging()
            if args.operation == 'validate':
                payload = validate_output(sys.stdin.buffer.read(MAX_OUTPUT + 1), args.actual_exit, args)
                code = 0
            else:
                outcome = run(args, deadline)
                payload = {'binding': binding(args), 'outcome': outcome}
                code = 2 if 'failure' in outcome else 0
            raw = canonical(payload)
            require(len(raw) <= MAX_OUTPUT, 'output_bound')
            sys.stdout.buffer.write(raw); return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'binding': binding(args), 'preflight_failure': finite(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
