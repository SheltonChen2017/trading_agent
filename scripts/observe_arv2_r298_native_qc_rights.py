"""One read-only current QC organization observation after fresh local input proof.

No creation, file/source upload, history, storage write, capacity or launch
exists in this contract. Raw credentials and account metadata never enter the
external report. Unknown tier or Storage Create remains unknown.
"""
from __future__ import annotations

import argparse
from collections import Counter
import http.client
import json
import logging
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

import requests

ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts import prepare_arv2_r298_native_price_specification as previous
from scripts import arv2_r298_ae_source_binding as anchor
from scripts import arv2_r298_all_route_worker_v2 as worker
from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission

admitted, environment, security = previous.admitted, previous.environment, previous.security
capture_support, capture, canonical, parse, sha, metadata = (
    previous.capture_support, previous.capture, previous.canonical, previous.parse, previous.sha, previous.metadata)
PYTHON = previous.PYTHON
SOURCE = ROOT / 'scripts/observe_arv2_r298_native_qc_rights.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_native_qc_rights/R326-20261027-AF'
SCHEMA = 'arv2-r298-native-qc-rights-observation-af-v1'
DEADLINE_SECONDS, SOURCE_SECONDS, HTTP_SECONDS, VALIDATOR_SECONDS = 600, 180, 90, 20
MAX_OUTPUT, MAX_FILES, MAX_BODY = 128 * 1024, 20, 1024 * 1024
MAX_CHILD = 16 * 1024
REFERENCE_PROJECT = 38364439
REFERENCE_NAME = 'ARV2 R298 NEWRULE SIX OFF 2021 OCT2026'
ORGANIZATION_SHA256 = 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
OWNER_ROW_SHA256 = '707a30618e122e49fe6fa75364451b5b7c50e1019a68a89ffc0cd3ae3c8e0b78'
AE_FACT_SHA256 = '7bb8c0ce079c85a2c41f20913a28cc9db4db1420402867cb57641b80db0436a4'
SPEC_SHA256 = '9da6813b4807d7ebf0ea32fddd38ab0740ff6c6edbc3bd05cdc5889775eb1f66'
AE_EVIDENCE_SHA256 = 'da5435a43b8f5d4a57487d67eb7066afbb3c368c31fcbbc8809464f20d208b70'
NEW_PINS = {
    'scripts/prepare_arv2_r298_native_price_specification.py': '501371b38ab01fd23262b13da9432b6356dfa65a93ef27132992947307884673',
    'scripts/arv2_r298_ae_source_binding.py': 'd67e13dfb73885a335345648a4149f1968b3ba2aebc26405ea409681a1be6bb1',
}
ROLES = ('authenticate', 'project', 'organization')
ENDPOINTS = {'authenticate': 'authenticate', 'project': 'projects/read', 'organization': 'organizations/read'}
PAID_TYPES = frozenset(('Quant Researcher', 'Team', 'Trading Firm', 'Institution'))
FALSE_FLAGS = {'projects_created': False, 'source_uploaded': False, 'files_read': False,
    'history_read': False, 'capacity_read': False, 'storage_write': False, 'storage_Create_proven': False,
    'organization_privacy_proven': False, 'current_project_privacy_proven': False,
    'source_cache_rights_granted': False, 'QC_data_acquired': False, 'QC_data_exported': False,
    'strategy_result_accepted': False, 'price_coverage_proven': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False, 'paper_or_live_ready': False,
    'old_controls_read': False, 'old_operational_entrypoint_called': False, 'new_paid_rights': False}
FINITE = frozenset(('deadline', 'host', 'arguments', 'git_state', 'source_pin', 'source_binding',
    'input', 'input_worker', 'inherited', 'worker_scope', 'worker_credentials', 'endpoint', 'request',
    'response', 'response_bound', 'http_status', 'http_refused', 'project', 'organization',
    'credential_handoff_absent', 'claim_spent', 'control_changed', 'control_name', 'control_bound',
    'control_write', 'capture_changed', 'capture_security', 'output', 'output_bound',
    'postflight', 'os_error', 'execution_environment_refused', 'unknown_exception',
    'transport_connect_timeout', 'transport_read_timeout', 'transport_tls', 'transport_proxy',
    'transport_redirect', 'transport_connection', 'transport_timeout', 'transport_request',
    'transport_os', 'transport_unknown'))


class Refused(ValueError):
    """Finite predicates only; no account response, credential or raw exception."""


def require(value, code):
    if not value: raise Refused(code)


def remaining(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline), 'deadline')
    value = deadline - time.monotonic()
    require(0 < value <= DEADLINE_SECONDS, 'deadline')
    return value


def finite(error):
    if type(error) is admitted.helpers.Deadline: return 'deadline'
    if type(error) is environment.EnvironmentRefused: return 'execution_environment_refused'
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown_exception'
    if isinstance(error, OSError): return 'os_error'
    return 'unknown_exception'


def pins():
    result = previous.pins()
    require(len(result) == 181, 'source_pin')
    for name, pin in NEW_PINS.items():
        require(name not in result or result[name] == pin, 'source_pin')
        require(type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin) and pin != '0' * 64, 'source_pin')
        result[name] = pin
    return result


def source_binding():
    fact, specification, evidence = anchor.observed_fact(), anchor.expected_specification(), anchor.expected_selection_evidence()
    require(sha(previous.diagnostic.canonical(fact)) == AE_FACT_SHA256
        and sha(previous.diagnostic.canonical(specification)) == SPEC_SHA256
        and sha(previous.diagnostic.canonical(evidence)) == AE_EVIDENCE_SHA256, 'source_binding')
    for name in ('producer', 'validator'):
        row = fact[name]
        require(type(row['actual_exit']) is int and row['actual_exit'] == 0
            and row['bound'] is None and row['spawn_observed'] is True
            and row['stderr_bytes'] == 0 and row['stderr_sha256'] == sha(b''), 'source_binding')
    previous._evidence(evidence)
    previous.diagnostic.validate_specification(specification)
    require(specification['selected_whole_binding_sha256s'] == evidence['selected_whole_binding_sha256s'],
        'source_binding')
    return specification


def profile_record():
    specification = source_binding()
    return {'schema': SCHEMA, 'root': str(ROOT), 'branch': admitted.frozen.BRANCH,
        'source': str(SOURCE), 'python': str(PYTHON), 'control': str(CONTROL), 'source_pins': pins(),
        'purpose': 'one_current_read_only_owned_reference_and_same_organization_rights_observation',
        'AE_observed_fact_sha256': AE_FACT_SHA256, 'AE_specification_sha256': SPEC_SHA256,
        'selected_whole_binding_sha256s': specification['selected_whole_binding_sha256s'],
        'reference_project_id': REFERENCE_PROJECT, 'organization_sha256': ORGANIZATION_SHA256,
        'reference_owner_full_row_sha256': OWNER_ROW_SHA256,
        'exact_endpoints_in_order': [ENDPOINTS[role] for role in ROLES], 'request_limit_each': 1,
        'source_input_package_sha256': worker.previous.PACKAGE_SHA256,
        'source_input_lineage_sha256': worker.previous.LINEAGE_SHA256,
        'input_worker': 'fresh_genuine_all_five_transport_role_byte_inventories_manifest_axis_all_binding_semantics_6151_and_five_whole_hashes_no_TICKERS',
        'source_worker_native_all_network_denied_before_any_credential_handoff': True,
        'claim_and_each_intent_fsynced_before_dispatch': True,
        'three_fixed_HTTP_children_no_arbitrary_callback': True,
        'credential_handoff': 'existing_two_QC_environment_values_after_source_actual0_only_never_Keychain',
        'HTTP_children_native_all_artifact_denial_except_own_claim_and_intent': True,
        'HTTP_outbound_HTTPS_DNS_ports_not_domain_fence': True,
        'exact_TLS_verified_API_host_paths_and_prepared_request_required': True,
        'non200_numeric_status_only_failed_body_not_read': True,
        'transport_exception_type_is_diagnostic_not_authenticated_cause': True,
        'provider_request_count_unknown_not_dispatch_intent_count': True,
        'private_org_ID_only_internal_metadata_pipe_never_external_report': True,
        'SDK_organization_type_is_current_representation_not_billing_or_Storage_permission': True,
        'data_current_and_signedTime_are_observations_not_cloud_cache_or_paid_gate': True,
        'missing_unknown_permission_fields_remain_unknown': True,
        'new_project_phase_requires_separate_actual_rights_review_and_committed_contract': True,
        'source_seconds': SOURCE_SECONDS, 'HTTP_child_seconds': HTTP_SECONDS,
        'deadline_seconds': DEADLINE_SECONDS, 'validator_seconds': VALIDATOR_SECONDS,
        'maximum_response_body_bytes': MAX_BODY, 'maximum_child_bytes': MAX_CHILD,
        'maximum_external_bytes': MAX_OUTPUT, 'maximum_control_files': MAX_FILES,
        'deadline_host_suspension_uninterruptible_IO_qualification': True,
        'selected_pins_not_whole_interpreter_integrity': True,
        'actual_parent_exit_and_separate_native_validator_required': True, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256,
        'profile_sha256': sha(canonical(profile_record()))}

def preflight(args, deadline):
    require(not admitted.v5._under_test() and Path(__file__).absolute() == SOURCE
        and sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT, 'host')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and type(args.caller_sha256) is str and re.fullmatch('[0-9a-f]{64}', args.caller_sha256), 'arguments')
    if args.operation != 'run': environment._require_environment()
    for command, expected in ((['rev-parse', '--show-toplevel'], str(ROOT)),
        (['branch', '--show-current'], admitted.frozen.BRANCH), (['rev-parse', 'HEAD'], args.expected_head),
        (['status', '--porcelain'], '')):
        require(admitted.v5._git(command, deadline).decode('ascii').strip() == expected, 'git_state')
    for name, pin in pins().items():
        require(sha((ROOT / name).read_bytes()) == pin, 'source_pin')
    require(sha(SOURCE.read_bytes()) == args.caller_sha256, 'source_pin')
    committed = admitted.v5._git(['cat-file', 'blob', args.expected_head + ':'
        + SOURCE.relative_to(ROOT).as_posix()], deadline, MAX_OUTPUT)
    require(sha(committed) == args.caller_sha256, 'source_pin')
    remaining(deadline)


def security_snapshot(fd, *, source=False):
    try:
        return security.snapshot(fd)
    except security.Refusal:
        raise Refused('source_security' if source else 'capture_security') from None


class Store:
    """Only the new AF leaf and original descriptors; no old control reader."""
    def __init__(self):
        self.fd, self.chain, self.files, self.held = None, [], {}, {}
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index, part in enumerate(CONTROL.parts[1:], 1):
                path = Path(*CONTROL.parts[:index + 1])
                if path in (CONTROL.parent, CONTROL):
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd); os.fsync(fd)
                    except FileExistsError:
                        require(path != CONTROL, 'claim_spent')
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd); fd = nxt
                self.chain.append((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
            self.fd = fd
            self.directory_security = security_snapshot(fd)
            self.verify()
        except BaseException:
            os.close(fd)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        for fd, _ in self.held.values():
            os.close(fd)
        os.close(self.fd)

    def verify(self):
        other, chain = admitted._storage_module()._walk(CONTROL)
        try:
            require(chain == tuple(self.chain) and metadata(os.fstat(self.fd)) == metadata(os.fstat(other))
                and os.fstat(other).st_uid == os.getuid() and stat.S_IMODE(os.fstat(other).st_mode) == 0o700
                and set(os.listdir(other)) == set(self.files) and len(self.files) <= MAX_FILES
                and security_snapshot(self.fd) == self.directory_security, 'control_changed')
            for name, baseline in self.files.items():
                fd, snapshot = self.held[name]
                require(baseline == metadata(os.fstat(fd))
                    == metadata(os.stat(name, dir_fd=other, follow_symlinks=False))
                    and security_snapshot(fd) == snapshot, 'capture_changed')
        finally:
            os.close(other)

    @staticmethod
    def _read(fd, size, *, deadline=None):
        os.lseek(fd, 0, os.SEEK_SET)
        result = bytearray()
        while len(result) <= size:
            if deadline is not None:
                remaining(deadline)
            chunk = os.read(fd, min(65536, size + 1 - len(result)))
            if not chunk:
                break
            result.extend(chunk)
        return bytes(result)

    def write(self, name, value):
        return self.write_bytes(name, canonical(value), private=False)

    def write_bytes(self, name, raw, *, private):
        self.verify()
        require(type(name) is str and name not in self.files and len(self.files) < MAX_FILES
            and private is False and re.fullmatch(r'[a-z0-9-]{1,100}\.json', name), 'control_name')
        require(type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT, 'control_bound')
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        kept = False
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == 0, 'control_write')
            snapshot = security_snapshot(fd)
            view = memoryview(raw)
            while view:
                count = os.write(fd, view); require(count > 0, 'control_write'); view = view[count:]
            os.fsync(fd); os.fsync(self.fd)
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size == len(raw), 'control_write')
            require(self._read(fd, len(raw)) == raw and metadata(info) == metadata(os.fstat(fd))
                and security_snapshot(fd) == snapshot, 'capture_changed')
            self.files[name] = metadata(info); self.held[name] = (fd, snapshot); kept = True
        finally:
            if not kept:
                os.close(fd)
        self.verify()
        return {'byte_count': len(raw), 'sha256': sha(raw)}


def _artifact_policy(leaves, *, package=None):
    directories = {ROOT / 'artifacts'}
    for path in [*leaves, *(() if package is None else (package,))]:
        directories.update(parent for parent in path.parents if ROOT / 'artifacts' == parent
            or ROOT / 'artifacts' in parent.parents)
    exceptions = ''.join(f'(require-not (literal "{path}"))' for path in sorted(directories | set(leaves)))
    subtree = '' if package is None else f'(require-not (subpath "{package}"))'
    return f'(deny file-read* (require-all (subpath "{ROOT / "artifacts"}") {subtree} {exceptions}))'



def _bootstrap_broker_logging():
    # The broker reads public metadata and the existing two-value handoff,
    # never input DATA. Native children receive independent clean environments.
    require('SSLKEYLOGFILE' not in os.environ
        and http.client.HTTPConnection.debuglevel == 0
        and http.client.HTTPSConnection.debuglevel == 0, 'execution_environment_refused')
    environment._logging_inventory()
    root = logging.root
    require(root.handlers == [] and root.filters == [] and root.level == logging.WARNING
        and root.disabled is False and root.propagate is True and root.parent is None
        and root.manager.disable == 0 and logging.lastResort is logging._defaultLastResort,
        'execution_environment_refused')
    environment._require_logging(prospective_root_sink=True)
    root.addHandler(logging.NullHandler())
    environment._require_logging()


def native_profile(mode):
    require(mode in ('source', 'http', 'validator'), 'arguments')
    base = '(version 1)(allow default)'
    if mode == 'http':
        base += ('(deny network-bind)(deny network-inbound)'
            '(deny network-outbound (require-all (require-not (remote tcp "*:443"))'
            ' (require-not (remote tcp "*:53")) (require-not (remote udp "*:53"))))')
    else: base += '(deny network*)'
    base += ''.join(f'(deny file-read* file-write* (subpath "{path}"))'
        for path in ('/Users/sheltonchen/Library/Keychains', '/Library/Keychains'))
    base += '(deny process-exec (literal "/usr/bin/security"))'
    base += (f'(deny file-write* (require-all (require-not (subpath "{ROOT / ".pytest_cache"}"))'
        ' (require-not (literal "/dev/null"))))')
    if mode == 'validator': return base + f'(deny file-read* (subpath "{ROOT / "artifacts"}"))'
    leaves = [CONTROL, CONTROL / 'claim.json',
        *(CONTROL / (role + '-intent.json') for role in ('source', *ROLES))]
    return base + _artifact_policy(
        leaves + ([worker.previous.LINEAGE] if mode == 'source' else []),
        package=worker.previous.PACKAGE if mode == 'source' else None)


def _inherited(args, role, raw):
    require(role in ('source', *ROLES) and type(raw) is bytes and len(raw) <= MAX_CHILD
        and all(type(fd) is int and fd > 2 for fd in (args.control_fd, args.claim_fd, args.intent_fd))
        and len({args.control_fd, args.claim_fd, args.intent_fd}) == 3, 'inherited')
    parent = os.fstat(args.control_fd)
    named = os.stat(CONTROL, follow_symlinks=False)
    require(metadata(parent) == metadata(named) and stat.S_ISDIR(parent.st_mode)
        and parent.st_uid == os.getuid() and stat.S_IMODE(parent.st_mode) == 0o700, 'inherited')
    security_snapshot(args.control_fd)
    for fd, name, expected in (
        (args.claim_fd, 'claim.json', {**binding(args), 'read_only': True, 'no_project_creation': True}),
        (args.intent_fd, role + '-intent.json', {**binding(args), 'role': role,
            'input_pin': {'byte_count': len(raw), 'sha256': sha(raw)}})):
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
            and 0 < info.st_size <= MAX_CHILD
            and metadata(info) == metadata(os.stat(name, dir_fd=args.control_fd, follow_symlinks=False)), 'inherited')
        snapshot = security_snapshot(fd)
        value = Store._read(fd, info.st_size)
        require(value == canonical(expected) and metadata(info) == metadata(os.fstat(fd))
            == metadata(os.stat(name, dir_fd=args.control_fd, follow_symlinks=False))
            and security_snapshot(fd) == snapshot, 'inherited')


def source_observation(deadline):
    """Fresh process-bound genuine package; no original TICKERS/control read."""
    require(not {'QC_USER_ID', 'QC_API_TOKEN'} & set(os.environ), 'worker_credentials')
    environment.require_safe_environment()
    plain = worker._load_plain(deadline)
    initial, record, selected, rows, public = worker._catalog(plain, deadline)
    specification = source_binding()
    wanted = specification['selected_whole_binding_sha256s']
    counts = dict.fromkeys(wanted, 0)
    for row in rows:
        remaining(deadline)
        pin = previous.diagnostic.digest(row)
        if pin in counts: counts[pin] += 1
    require(len(rows) == 6151 and all(value == 1 for value in counts.values()), 'input')
    worker._catalog_unchanged(plain, initial, record, selected, deadline)
    environment.require_safe_environment()
    result = {'schema': SCHEMA + '-input', 'input_binding': public,
        'specification_sha256': SPEC_SHA256, 'selected_whole_binding_sha256s': wanted,
        'full_binding_count': 6151, 'selected_exact_unique_count': 5,
        'same_process_genuine_plain_capability_checked': True, 'all_five_transport_role_byte_inventories_checked': True,
        'input_unchanged_checks_complete': True, 'old_controls_or_TICKERS_read': False}
    validate_source_observation(result)
    return result


def validate_source_observation(value):
    fields = {'schema', 'input_binding', 'specification_sha256', 'selected_whole_binding_sha256s',
        'full_binding_count', 'selected_exact_unique_count', 'same_process_genuine_plain_capability_checked',
        'all_five_transport_role_byte_inventories_checked', 'input_unchanged_checks_complete', 'old_controls_or_TICKERS_read'}
    require(type(value) is dict and set(value) == fields and value['schema'] == SCHEMA + '-input'
        and value['specification_sha256'] == SPEC_SHA256
        and value['selected_whole_binding_sha256s'] == source_binding()['selected_whole_binding_sha256s']
        and type(value['full_binding_count']) is int and value['full_binding_count'] == 6151
        and type(value['selected_exact_unique_count']) is int and value['selected_exact_unique_count'] == 5
        and value['same_process_genuine_plain_capability_checked'] is True
        and value['all_five_transport_role_byte_inventories_checked'] is True and value['input_unchanged_checks_complete'] is True
        and value['old_controls_or_TICKERS_read'] is False, 'input')
    worker.previous._validate_input(value['input_binding'])
    contract = previous.previous.source_binding()['aa_routing_summary']['binding_contract']
    require(value['input_binding']['binding_contract'] == contract
        and value['input_binding']['plain_package_sha256'] == previous.diagnostic.PACKAGE_SHA256
        and value['input_binding']['activation_manifest_sha256'] == previous.diagnostic.ACTIVATION_SHA256, 'input')
    return value


def _actual(value, raw, exit):
    fields = {'actual_exit', 'bound', 'spawn_observed', 'dispatched_at', 'completion_observed_at',
        'stdout_bytes', 'stdout_sha256', 'stderr_bytes', 'stderr_sha256'}
    require(type(value) is dict and set(value) == fields and type(value['actual_exit']) is int
        and value['actual_exit'] == exit and value['bound'] is None and value['spawn_observed'] is True
        and type(value['stdout_bytes']) is int and value['stdout_bytes'] == len(raw)
        and value['stdout_sha256'] == sha(raw) and type(value['stderr_bytes']) is int
        and value['stderr_bytes'] == 0 and value['stderr_sha256'] == sha(b'')
        and all(type(value[name]) is str and re.fullmatch(r'[0-9T:.Z+-]{20,40}', value[name])
            for name in ('dispatched_at', 'completion_observed_at')), 'output')


def _input_packet(value):
    require(type(value) is dict and set(value) == {'source', 'source_actual', 'organization_id'}, 'input')
    source = value['source']
    require(type(source) is dict and set(source) == {'binding', 'role', 'result'}
        and source['role'] == 'source', 'input')
    validate_source_observation(source['result'])
    _actual(value['source_actual'], canonical(source), 0)
    return source


def _shape(value):
    kind = type(value)
    return {type(None): 'null', bool: 'boolean', int: 'integer', float: 'number',
        str: 'string', dict: 'object', list: 'array'}.get(kind, 'invalid')


def _field_shapes(value, names):
    return {name: _shape(value[name]) if name in value else 'missing' for name in names}


def _organization(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{32}', value)
        and sha(value.encode('ascii')) == ORGANIZATION_SHA256, 'organization')
    return value


def _project(response, user_id):
    rows = response.get('projects')
    require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'project')
    row = rows[0]
    require(type(row.get('projectId')) is int and row['projectId'] == REFERENCE_PROJECT
        and row.get('name') == REFERENCE_NAME and row.get('language') == 'Py'
        and row.get('owner') is True and type(row.get('ownerId')) is int
        and str(row['ownerId']) == user_id, 'project')
    organization = _organization(row.get('organizationId'))
    collaborators = row.get('collaborators')
    require(type(collaborators) is list and len(collaborators) <= 16
        and all(type(item) is dict for item in collaborators), 'project')
    own = [item for item in collaborators if type(item.get('uid')) is int and str(item['uid']) == user_id]
    require(len(own) == 1 and own[0].get('owner') is True, 'project')
    require(sha(canonical(own[0])) == OWNER_ROW_SHA256, 'project')
    public = {'project_id': REFERENCE_PROJECT, 'organization_sha256': ORGANIZATION_SHA256,
        'owned_reference_matched': True, 'owner_id_sha256': sha(user_id.encode('ascii')),
        'owner_full_row_sha256': OWNER_ROW_SHA256,
        'collaborator_count': len(collaborators), 'owner_row_count': sum(item.get('owner') is True for item in collaborators),
        'own_row_shapes': _field_shapes(own[0], ('uid', 'owner', 'permission', 'liveControl', 'codeSourceId')),
        'own_permission': own[0].get('permission') if own[0].get('permission') in ('read', 'write') else None,
        'code_running_shape': _shape(row.get('codeRunning')),
        'code_running_observed': row.get('codeRunning') if type(row.get('codeRunning')) is bool else None,
        'public_field_shape': _shape(row['public']) if 'public' in row else 'missing',
        'public_field_observed': row.get('public') if type(row.get('public')) is bool else None,
        'private_default_is_documented_not_org_privacy_proof': True}
    return public, organization


def _org(response, organization, user_id):
    row = response.get('organization')
    require(type(row) is dict and row.get('id') == _organization(organization), 'organization')
    kind = row.get('type')
    recognized = kind if type(kind) is str and kind in PAID_TYPES | {'Free'} else None
    products = row.get('products')
    groups, item_shapes, item_total = [], {name: Counter() for name in ('productId', 'name', 'quantity', 'unitPrice', 'total')}, 0
    if type(products) is list:
        require(len(products) <= 64 and all(type(group) is dict for group in products), 'organization')
        for group in products:
            items = group.get('items')
            require(items is None or (type(items) is list and len(items) <= 128
                and all(type(item) is dict for item in items)), 'organization')
            groups.append({'group_name_shape': _shape(group.get('name')),
                'group_name_sha256': sha(group['name'].encode('utf-8')) if type(group.get('name')) is str else None,
                'item_count': len(items) if type(items) is list else None})
            for item in items or []:
                item_total += 1
                for key, field_shape in _field_shapes(item, tuple(item_shapes)).items(): item_shapes[key][field_shape] += 1
    data = row.get('data')
    current = data.get('current') if type(data) is dict else None
    signed = data.get('signedTime') if type(data) is dict else None
    members = row.get('members')
    own = []
    if type(members) is list:
        require(len(members) <= 256 and all(type(member) is dict for member in members), 'organization')
        own = [member for member in members if type(member.get('id')) is int and str(member['id']) == user_id]
        require(len(own) <= 1, 'organization')
    own_member = own[0] if own else {}
    return {'organization_sha256': ORGANIZATION_SHA256,
        'type_shape': _shape(kind), 'recognized_type': recognized,
        'type_sha256': sha(kind.encode('utf-8')) if type(kind) is str else None,
        'paid_tier_representation': recognized in PAID_TYPES if recognized is not None else None,
        'paid_billing_active_proven': False, 'Storage_Create_status': 'unknown_not_in_validated_SDK_model',
        'products_shape': _shape(products), 'product_group_count': len(products) if type(products) is list else None,
        'product_groups': groups, 'observed_product_item_count': item_total,
        'product_item_field_shape_counts': {key: dict(sorted(counts.items())) for key, counts in item_shapes.items()},
        'data_shape': _shape(data),
        'data_current_shape': _shape(current), 'data_current_observed': current if type(current) is bool else None,
        'signedTime_shape': _shape(signed),
        'signedTime_observed': signed if type(signed) is int and 0 <= signed < 2 ** 63 else None,
        'data_fields_are_not_paid_or_cloud_cache_permission': True,
        'members_shape': _shape(members), 'member_count': len(members) if type(members) is list else None,
        'own_member_count': len(own),
        'own_isAdmin_shape': _shape(own_member.get('isAdmin')),
        'own_isAdmin_observed': own_member.get('isAdmin') if type(own_member.get('isAdmin')) is bool else None,
        'own_permission_field_shapes': _field_shapes(own_member,
            ('isAdmin', 'permission', 'permissions', 'roles', 'storage', 'storagePermissions')),
        'member_and_project_metadata_do_not_establish_org_privacy': True}


class OwnedSession(requests.Session):
    def resolve_redirects(self, *args, **kwargs): return iter(())


def _session():
    session = OwnedSession()
    session.trust_env, session.auth, session.verify, session.cert, session.max_redirects = False, None, True, None, 0
    session.headers.clear(); session.cookies.clear(); session.proxies.clear(); session.params.clear()
    session.hooks = {'response': []}
    session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))
    return session


def _session_check(session, url):
    require(type(session) is OwnedSession and session.trust_env is False and session.auth is None
        and session.verify is True and session.cert is None and session.max_redirects == 0
        and dict(session.headers) == {} and not session.cookies and not session.proxies and not session.params
        and session.hooks == {'response': []} and session.get_adapter(url).max_retries.total == 0, 'request')


def transport_failure(error):
    kinds = ((requests.exceptions.ConnectTimeout, 'transport_connect_timeout'),
        (requests.exceptions.ReadTimeout, 'transport_read_timeout'), (requests.exceptions.SSLError, 'transport_tls'),
        (requests.exceptions.ProxyError, 'transport_proxy'), (requests.exceptions.TooManyRedirects, 'transport_redirect'),
        (requests.exceptions.ConnectionError, 'transport_connection'), (requests.exceptions.Timeout, 'transport_timeout'),
        (requests.exceptions.RequestException, 'transport_request'))
    for kind, code in kinds:
        if type(error) is kind: return code
    return 'transport_os' if isinstance(error, OSError) else 'transport_unknown'


def _decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'response'); result[key] = value
        return result
    try:
        require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY, 'response_bound')
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('response')))
        pending, count = [(value, 0)], 0
        while pending:
            item, depth = pending.pop(); count += 1
            require(depth <= 64 and count <= 65536, 'response_bound')
            if type(item) is dict: pending.extend((child, depth + 1) for child in item.values())
            elif type(item) is list: pending.extend((child, depth + 1) for child in item)
            elif type(item) is str: require(len(item) <= 65536, 'response_bound')
        require(type(value) is dict, 'response')
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('response') from None


def _fetch(api, role, payload, state, deadline):
    environment.require_safe_environment()
    require(role in ROLES and type(payload) is dict, 'endpoint')
    url = submission.API_BASE + '/' + ENDPOINTS[role]
    raw = canonical(payload)
    headers = submission.build_auth_headers(api._credentials, api._clock())
    require(type(headers) is dict and set(headers) == {'Authorization', 'Timestamp'}, 'request')
    headers.update({'Content-Type': 'application/json', 'Accept-Encoding': 'identity'})
    with _session() as session:
        _session_check(session, url)
        prepared = session.prepare_request(requests.Request('POST', url, data=raw, headers=headers))
        expected = {key.casefold(): value for key, value in headers.items()}
        expected['content-length'] = str(len(raw))
        require(prepared.method == 'POST' and prepared.url == url and prepared.body == raw
            and prepared.hooks == {'response': []}
            and {key.casefold(): value for key, value in prepared.headers.items()} == expected, 'request')
        state['request_dispatch_intent'] = True
        try:
            with session.send(prepared, timeout=min(30, remaining(deadline)),
                    allow_redirects=False, stream=True, verify=True, proxies={}) as response:
                status = response.status_code
                require(type(status) is int and 100 <= status <= 599, 'http_status')
                state['http_status'] = status
                environment.require_safe_environment(); _session_check(session, url)
                require(response.url == url and response.request is prepared and not response.history, 'response')
                if status != 200: raise Refused('http_refused')
                encoding, content_type = response.headers.get('Content-Encoding', 'identity'), response.headers.get('Content-Type', '')
                require(type(encoding) is str and encoding.casefold() == 'identity'
                    and type(content_type) is str and len(content_type) <= 100
                    and content_type.casefold().split(';')[0].strip() == 'application/json'
                    and not response.headers.get('Set-Cookie'), 'response')
                declared = response.headers.get('Content-Length')
                require(declared is None or (type(declared) is str and declared.isdecimal()
                    and len(declared) <= 10 and 0 < int(declared) <= MAX_BODY), 'response_bound')
                parts, count = [], 0
                for part in response.iter_content(chunk_size=65536, decode_unicode=False):
                    remaining(deadline)
                    require(type(part) is bytes, 'response')
                    count += len(part); require(count <= MAX_BODY, 'response_bound'); parts.append(part)
                require(count > 0 and (declared is None or int(declared) == count), 'response_bound')
                body = b''.join(parts)
                state['complete_body_pin'] = {'byte_count': len(body), 'sha256': sha(body)}
                value = _decode(body)
                require(value.get('success') is True and ('errors' not in value
                    or type(value['errors']) is list and value['errors'] == []), 'response')
                return value
        except Refused:
            raise
        except admitted.helpers.Deadline:
            raise
        except BaseException as error:
            raise Refused(transport_failure(error)) from None


def http_observation(role, packet, state, deadline):
    source = _input_packet(packet)
    require(source['binding'] == state['binding'], 'input')
    organization = packet['organization_id']
    require(organization is None if role != 'organization' else type(organization) is str, 'endpoint')
    if role == 'authenticate': payload = {}
    elif role == 'project': payload = {'projectId': REFERENCE_PROJECT}
    else: payload = {'organizationId': _organization(organization)}
    environment.require_safe_environment()
    api = submission._client()
    require(type(api) is submission.QuantConnectClient and api._base_url == submission.API_BASE
        and api._transport is submission.coverage._bounded_transport and api._timeout == 30, 'request')
    value = _fetch(api, role, payload, state, deadline)
    user_id = api._credentials.user_id
    require(type(user_id) is str and user_id.isdecimal() and 0 < int(user_id) < 2 ** 63, 'request')
    if role == 'authenticate': return {'authenticated': True}, None
    if role == 'project': return _project(value, user_id)
    return _org(value, organization, user_id), None


SHAPES = frozenset(('null', 'boolean', 'integer', 'number', 'string', 'object', 'array', 'missing'))
PROJECT_FIELDS = frozenset(('project_id', 'organization_sha256', 'owned_reference_matched', 'owner_id_sha256',
    'owner_full_row_sha256',
    'collaborator_count', 'owner_row_count', 'own_row_shapes', 'own_permission', 'code_running_shape',
    'code_running_observed', 'public_field_shape', 'public_field_observed',
    'private_default_is_documented_not_org_privacy_proof'))
ORG_FIELDS = frozenset(('organization_sha256', 'type_shape', 'recognized_type', 'type_sha256',
    'paid_tier_representation', 'paid_billing_active_proven', 'Storage_Create_status', 'products_shape',
    'product_group_count', 'product_groups', 'observed_product_item_count', 'product_item_field_shape_counts',
    'data_shape', 'data_current_shape', 'data_current_observed', 'signedTime_shape', 'signedTime_observed',
    'data_fields_are_not_paid_or_cloud_cache_permission', 'members_shape', 'member_count', 'own_member_count',
    'own_isAdmin_shape', 'own_isAdmin_observed', 'own_permission_field_shapes',
    'member_and_project_metadata_do_not_establish_org_privacy'))


def _hash(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _optional_boolean(value): return value is None or type(value) is bool


def _shapes(value, keys):
    require(type(value) is dict and set(value) == set(keys)
        and all(type(kind) is str and kind in SHAPES for kind in value.values()), 'output')


def validate_observation(role, value):
    if role == 'authenticate':
        require(type(value) is dict and value == {'authenticated': True}, 'output')
    elif role == 'project':
        require(type(value) is dict and set(value) == PROJECT_FIELDS
            and type(value['project_id']) is int and value['project_id'] == REFERENCE_PROJECT
            and value['organization_sha256'] == ORGANIZATION_SHA256
            and value['owned_reference_matched'] is True and _hash(value['owner_id_sha256'])
            and value['owner_full_row_sha256'] == OWNER_ROW_SHA256
            and type(value['collaborator_count']) is int and 1 <= value['collaborator_count'] <= 16
            and type(value['owner_row_count']) is int and 1 <= value['owner_row_count'] <= value['collaborator_count']
            and value['own_permission'] in (None, 'read', 'write')
            and value['code_running_shape'] in SHAPES and _optional_boolean(value['code_running_observed'])
            and value['public_field_shape'] in SHAPES and _optional_boolean(value['public_field_observed'])
            and value['private_default_is_documented_not_org_privacy_proof'] is True, 'output')
        _shapes(value['own_row_shapes'], ('uid', 'owner', 'permission', 'liveControl', 'codeSourceId'))
    else:
        require(role == 'organization' and type(value) is dict and set(value) == ORG_FIELDS
            and value['organization_sha256'] == ORGANIZATION_SHA256
            and value['recognized_type'] in (None, 'Free', *sorted(PAID_TYPES))
            and (value['type_sha256'] is None or _hash(value['type_sha256']))
            and value['paid_tier_representation'] is (
                None if value['recognized_type'] is None else value['recognized_type'] in PAID_TYPES)
            and value['paid_billing_active_proven'] is False
            and value['Storage_Create_status'] == 'unknown_not_in_validated_SDK_model'
            and value['data_fields_are_not_paid_or_cloud_cache_permission'] is True
            and value['member_and_project_metadata_do_not_establish_org_privacy'] is True
            and all(value[name] in SHAPES for name in ('type_shape', 'products_shape', 'data_shape',
                'data_current_shape', 'signedTime_shape', 'members_shape', 'own_isAdmin_shape'))
            and all(_optional_boolean(value[name]) for name in ('data_current_observed', 'own_isAdmin_observed'))
            and (value['signedTime_observed'] is None or (type(value['signedTime_observed']) is int
                and 0 <= value['signedTime_observed'] < 2 ** 63))
            and (value['member_count'] is None or type(value['member_count']) is int
                and 0 <= value['member_count'] <= 256)
            and type(value['own_member_count']) is int and value['own_member_count'] in (0, 1)
            and type(value['product_groups']) is list and len(value['product_groups']) <= 64
            and (value['product_group_count'] is None or type(value['product_group_count']) is int
                and value['product_group_count'] == len(value['product_groups']))
            and type(value['observed_product_item_count']) is int
            and 0 <= value['observed_product_item_count'] <= 64 * 128, 'output')
        if value['recognized_type'] is not None:
            require(value['type_shape'] == 'string'
                and value['type_sha256'] == sha(value['recognized_type'].encode('utf-8')), 'output')
        require((value['members_shape'] == 'array') == (value['member_count'] is not None)
            and (value['member_count'] is not None or value['own_member_count'] == 0)
            and (value['products_shape'] == 'array') == (value['product_group_count'] is not None), 'output')
        for row in value['product_groups']:
            require(type(row) is dict and set(row) == {'group_name_shape', 'group_name_sha256', 'item_count'}
                and row['group_name_shape'] in SHAPES
                and (row['group_name_sha256'] is None or _hash(row['group_name_sha256']))
                and (row['item_count'] is None or type(row['item_count']) is int and 0 <= row['item_count'] <= 128), 'output')
        require(sum(row['item_count'] or 0 for row in value['product_groups'])
            == value['observed_product_item_count'], 'output')
        shapes = value['product_item_field_shape_counts']
        require(type(shapes) is dict and set(shapes) == {'productId', 'name', 'quantity', 'unitPrice', 'total'}, 'output')
        for counts in shapes.values():
            require(type(counts) is dict and all(key in SHAPES and type(count) is int and count > 0
                for key, count in counts.items()) and sum(counts.values()) == value['observed_product_item_count'], 'output')
        _shapes(value['own_permission_field_shapes'],
            ('isAdmin', 'permission', 'permissions', 'roles', 'storage', 'storagePermissions'))
    return value


def _validate_http_state(value, args):
    require(type(value) is dict and set(value) == {'binding', 'request_dispatch_intent', 'http_status', 'complete_body_pin'}
        and value['binding'] == binding(args) and type(value['request_dispatch_intent']) is bool
        and (value['http_status'] is None or type(value['http_status']) is int and 100 <= value['http_status'] <= 599), 'output')
    pin = value['complete_body_pin']
    if pin is not None:
        require(type(pin) is dict and set(pin) == {'byte_count', 'sha256'}
            and type(pin['byte_count']) is int and 0 < pin['byte_count'] <= MAX_BODY
            and _hash(pin['sha256']) and value['http_status'] == 200, 'output')
    if value['http_status'] is not None: require(value['request_dispatch_intent'] is True, 'output')


def validate_child(raw, actual, args, role):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_CHILD, 'output')
    exit = actual['actual_exit']
    require(type(exit) is int and exit in (0, 2), 'output')
    _actual(actual, raw, exit)
    value = parse(raw)
    require(type(value) is dict and value.get('binding') == binding(args) and value.get('role') == role, 'output')
    if 'failure_code' in value:
        require(exit == 2 and value['failure_code'] in FINITE
            and set(value) == ({'binding', 'role', 'failure_code'} if role == 'source' else
                {'binding', 'role', 'failure_code', 'state'}), 'output')
        if role != 'source': _validate_http_state(value['state'], args)
    elif role == 'source':
        require(exit == 0 and set(value) == {'binding', 'role', 'result'}, 'output')
        validate_source_observation(value['result'])
    else:
        require(exit == 0 and set(value) == {'binding', 'role', 'result', 'state', 'organization_id'}, 'output')
        _validate_http_state(value['state'], args)
        require(value['state']['request_dispatch_intent'] is True
            and value['state']['http_status'] == 200 and value['state']['complete_body_pin'] is not None, 'output')
        validate_observation(role, value['result'])
        require(_organization(value['organization_id']) if role == 'project'
            else value['organization_id'] is None, 'output')
    return value


def _child(args, directory, role, packet, runtime, deadline, state, credentials=None):
    raw = b'' if packet is None else canonical(packet)
    require(type(raw) is bytes and len(raw) <= MAX_CHILD, 'input')
    directory.write(role + '-intent.json', {**binding(args), 'role': role,
        'input_pin': {'byte_count': len(raw), 'sha256': sha(raw)}})
    command = ['/usr/bin/sandbox-exec', '-p', native_profile('source' if role == 'source' else 'http'),
        str(PYTHON), '-B', str(SOURCE), 'source' if role == 'source' else 'http',
        '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256, '--role', role,
        '--control-fd', str(directory.fd), '--claim-fd', str(directory.held['claim.json'][0]),
        '--intent-fd', str(directory.held[role + '-intent.json'][0])]
    safe = capture_support._environment(runtime, credentials)
    output, errors, actual = capture(command, safe,
        min(SOURCE_SECONDS if role == 'source' else HTTP_SECONDS, remaining(deadline)),
        input_bytes=raw, stdout_limit=MAX_CHILD,
        pass_fds=(directory.fd, directory.held['claim.json'][0], directory.held[role + '-intent.json'][0]))
    state['children'].append({'role': role, 'actual': actual})
    directory.write(role + '-observed.json', {'role': role, 'actual': actual})
    require(not errors, 'input_worker' if role == 'source' else 'response')
    value = validate_child(output, actual, args, role)
    if 'failure_code' in value:
        if role != 'source': state['last_HTTP_state'] = value['state']
        raise Refused(value['failure_code']) from None
    return value, actual


def run(args, deadline):
    credentials = None
    with Store() as directory:
        directory.write('claim.json', {**binding(args), 'read_only': True, 'no_project_creation': True})
        state = {'stage': 'input', 'children': [], 'source': None, 'source_actual': None,
            'credential_handoff_complete': False, 'observations': [], 'last_HTTP_state': None}
        try:
            runtime = Path(tempfile.mkdtemp(prefix='r326-af-runtime-', dir=ROOT / '.pytest_cache'))
            source, source_actual = _child(args, directory, 'source', None, runtime, deadline, state)
            require(source['binding'] == binding(args), 'input')
            state['source'], state['source_actual'] = source, source_actual
            state['stage'] = 'credential_handoff'
            environment._require_logging()
            try:
                credentials = capture_support._credential_handoff(os.environ)
            except Exception:
                raise Refused('credential_handoff_absent') from None
            state['credential_handoff_complete'] = True
            organization = None
            for role in ROLES:
                remaining(deadline); state['stage'] = role
                packet = {'source': source, 'source_actual': source_actual,
                    'organization_id': organization if role == 'organization' else None}
                value, actual = _child(args, directory, role, packet, runtime, deadline, state, credentials)
                public = value['result']; validate_observation(role, public)
                state['observations'].append({'role': role, 'result': public, 'state': value['state'],
                    'actual': actual, 'internal_channel_authenticated_before_identifier_redaction': True})
                if role == 'project': organization = _organization(value['organization_id'])
            credentials.clear(); credentials = None
            state['stage'] = 'postflight'
            preflight(args, deadline); environment._require_logging(); directory.verify()
            result = {'schema': SCHEMA, **state, 'read_only_observation_complete': True,
                'source_input_actual_zero_before_credential_handoff': True,
                'application_HTTP_dispatch_intents': 3, 'provider_request_count': None,
                'private_identifier_not_in_report': True, 'post_checks_complete': True, **FALSE_FLAGS}
            validate_result(result, args)
            report = directory.write('report.json', {**binding(args), 'result': result})
            directory.verify()
            return {'result': result, 'report': report}
        except BaseException as error:
            failed = {'failure_code': finite(error), 'state': state, 'claim_consumed': True,
                'provider_request_count': None, **FALSE_FLAGS}
            try: directory.write('failure.json', {**binding(args), **failed})
            except BaseException: pass
            return {'failure': failed}
        finally:
            if type(credentials) is dict: credentials.clear()


def _validate_state(value, args, *, success=False):
    require(type(value) is dict and set(value) == {'stage', 'children', 'source', 'source_actual',
        'credential_handoff_complete', 'observations', 'last_HTTP_state'}
        and value['stage'] in ('input', 'credential_handoff', *ROLES, 'postflight')
        and type(value['children']) is list and len(value['children']) <= 4
        and type(value['credential_handoff_complete']) is bool
        and type(value['observations']) is list and len(value['observations']) <= 3, 'output')
    for index, child in enumerate(value['children']):
        require(type(child) is dict and set(child) == {'role', 'actual'}
            and child['role'] == ('source', *ROLES)[index] and type(child['actual']) is dict, 'output')
        actual = child['actual']
        require(set(actual) == {'actual_exit', 'bound', 'spawn_observed', 'dispatched_at',
            'completion_observed_at', 'stdout_bytes', 'stdout_sha256', 'stderr_bytes', 'stderr_sha256'}
            and (actual['actual_exit'] is None or type(actual['actual_exit']) is int)
            and (actual['bound'] is None or actual['bound'] in ('deadline', 'stdout_bound', 'stderr_bound'))
            and type(actual['spawn_observed']) is bool
            and all(type(actual[key]) is int and actual[key] >= 0 for key in ('stdout_bytes', 'stderr_bytes'))
            and all(_hash(actual[key]) for key in ('stdout_sha256', 'stderr_sha256'))
            and all(type(actual[key]) is str and len(actual[key]) <= 64
                for key in ('dispatched_at', 'completion_observed_at')), 'output')
    source = value['source']
    if source is not None:
        require(type(source) is dict and set(source) == {'binding', 'role', 'result'}
            and source['binding'] == binding(args) and source['role'] == 'source', 'output')
        validate_source_observation(source['result'])
        _actual(value['source_actual'], canonical(source), 0)
        require(value['children'] and value['children'][0]['actual'] == value['source_actual'], 'output')
    else:
        require(value['source_actual'] is None and value['credential_handoff_complete'] is False
            and value['observations'] == [] and len(value['children']) <= 1, 'output')
    if value['credential_handoff_complete']: require(source is not None, 'output')
    for index, observed in enumerate(value['observations']):
        require(type(observed) is dict and set(observed) == {'role', 'result', 'state', 'actual',
            'internal_channel_authenticated_before_identifier_redaction'}
            and observed['role'] == ROLES[index]
            and observed['internal_channel_authenticated_before_identifier_redaction'] is True
            and value['credential_handoff_complete'] is True
            and len(value['children']) > index + 1
            and observed['actual'] == value['children'][index + 1]['actual'], 'output')
        validate_observation(observed['role'], observed['result'])
        _validate_http_state(observed['state'], args)
        require(observed['state']['request_dispatch_intent'] is True
            and observed['state']['http_status'] == 200 and observed['state']['complete_body_pin'] is not None
            and type(observed['actual']['actual_exit']) is int and observed['actual']['actual_exit'] == 0
            and observed['actual']['bound'] is None and observed['actual']['spawn_observed'] is True
            and observed['actual']['stderr_bytes'] == 0 and observed['actual']['stderr_sha256'] == sha(b''), 'output')
    if value['last_HTTP_state'] is not None: _validate_http_state(value['last_HTTP_state'], args)
    if success:
        require(value['stage'] == 'postflight' and len(value['children']) == 4
            and len(value['observations']) == 3 and value['last_HTTP_state'] is None, 'output')


def validate_result(value, args):
    state_names = {'stage', 'children', 'source', 'source_actual', 'credential_handoff_complete',
        'observations', 'last_HTTP_state'}
    require(type(value) is dict and set(value) == {'schema', *state_names, 'read_only_observation_complete',
        'source_input_actual_zero_before_credential_handoff', 'application_HTTP_dispatch_intents',
        'provider_request_count', 'private_identifier_not_in_report', 'post_checks_complete', *FALSE_FLAGS}
        and value['schema'] == SCHEMA and value['read_only_observation_complete'] is True
        and value['source_input_actual_zero_before_credential_handoff'] is True
        and type(value['application_HTTP_dispatch_intents']) is int and value['application_HTTP_dispatch_intents'] == 3
        and value['provider_request_count'] is None and value['private_identifier_not_in_report'] is True
        and value['post_checks_complete'] is True and all(value[key] is False for key in FALSE_FLAGS), 'output')
    _validate_state({key: value[key] for key in state_names}, args, success=True)


def validate_output(raw, actual_exit, args):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_OUTPUT
        and type(actual_exit) is int and actual_exit in (0, 2), 'output')
    value = parse(raw)
    require(type(value) is dict and value.get('binding') == binding(args), 'output')
    if set(value) == {'binding', 'preflight_failure'}:
        require(actual_exit == 2 and value['preflight_failure'] in FINITE, 'output'); return value
    require(set(value) == {'binding', 'outcome'} and type(value['outcome']) is dict, 'output')
    outcome = value['outcome']
    if set(outcome) == {'failure'}:
        failed = outcome['failure']
        require(actual_exit == 2 and type(failed) is dict and set(failed) == {
            'failure_code', 'state', 'claim_consumed', 'provider_request_count', *FALSE_FLAGS}
            and failed['failure_code'] in FINITE and failed['claim_consumed'] is True
            and failed['provider_request_count'] is None and all(failed[key] is False for key in FALSE_FLAGS), 'output')
        _validate_state(failed['state'], args)
    else:
        require(actual_exit == 0 and set(outcome) == {'result', 'report'}, 'output')
        validate_result(outcome['result'], args)
        report = canonical({**binding(args), 'result': outcome['result']})
        require(outcome['report'] == {'byte_count': len(report), 'sha256': sha(report)}, 'output')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('run', 'source', 'http', 'validate'))
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--caller-sha256', required=True)
    parser.add_argument('--role', choices=('source', *ROLES))
    parser.add_argument('--control-fd', type=int)
    parser.add_argument('--claim-fd', type=int)
    parser.add_argument('--intent-fd', type=int)
    parser.add_argument('--actual-exit', type=int)
    args = parser.parse_args(argv)
    seconds = {'run': DEADLINE_SECONDS, 'source': SOURCE_SECONDS, 'http': HTTP_SECONDS,
        'validate': VALIDATOR_SECONDS}[args.operation]
    deadline = time.monotonic() + seconds
    try:
        with admitted.helpers._alarm(deadline):
            preflight(args, deadline)
            if args.operation == 'run':
                _bootstrap_broker_logging()
                outcome = run(args, deadline)
                value = {'binding': binding(args), 'outcome': outcome}
                code = 2 if 'failure' in outcome else 0
            else:
                environment._bootstrap_cli_logging()
                if args.operation == 'validate':
                    raw = sys.stdin.buffer.read(MAX_OUTPUT + 1)
                    value = validate_output(raw, args.actual_exit, args)
                    sys.stdout.buffer.write(raw); return 0
                raw = sys.stdin.buffer.read(MAX_CHILD + 1)
                role = args.role
                _inherited(args, role, raw)
                state = {'binding': binding(args), 'request_dispatch_intent': False,
                    'http_status': None, 'complete_body_pin': None}
                try:
                    if args.operation == 'source':
                        require(role == 'source' and raw == b'', 'worker_scope')
                        result = source_observation(deadline)
                        value = {'binding': binding(args), 'role': role, 'result': result}
                    else:
                        require(role in ROLES, 'worker_scope')
                        packet = parse(raw)
                        result, organization = http_observation(role, packet, state, deadline)
                        validate_observation(role, result)
                        value = {'binding': binding(args), 'role': role, 'result': result,
                            'state': state, 'organization_id': organization}
                    preflight(args, deadline); environment.require_safe_environment()
                    code = 0
                except BaseException as error:
                    value = {'binding': binding(args), 'role': role, 'failure_code': finite(error)}
                    if args.operation == 'http': value['state'] = state
                    code = 2
            raw = canonical(value)
            require(len(raw) <= (MAX_OUTPUT if args.operation == 'run' else MAX_CHILD), 'output_bound')
            sys.stdout.buffer.write(raw)
            return code
    except BaseException as error:
        sys.stdout.buffer.write(canonical({'binding': binding(args), 'preflight_failure': finite(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
