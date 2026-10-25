"""One separately frozen R298 A11 plain-source-and-compile READINESS recovery.

A1-A10 remain spent. This additive attempt completes only the new exact plain-transport
eleven files and a single compile, authenticates final source/access/admission,
and stops ready for a separately authorized launch. It exposes no capacity,
backtest creation, status or result operation. Source arguments are bindings,
not authority. User readiness delegation/review waiver and clean run freeze
must precede use. Historical controls and operational entrypoints stay frozen.
"""
from __future__ import annotations

import argparse
import json
import math
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
from scripts import arv2_r298_plain_readiness_remote as remote
from scripts import prepare_arv2_newrule_plain_transport as prep
from scripts import arv2_newrule_plain_storage as storage
from scripts import run_arv2_r298_access_recovery as a6
from scripts import arv2_r298_plain_source_boundary as boundary
from scripts import arv2_r298_qc_response_evidence as response_evidence
from scripts import arv2_r298_qc_error_text as error_text

previous, v5, frozen, helpers = a3.previous, a3.v5, a3.frozen, a3.helpers
canonical, parse, sha, metadata = a3.canonical, a3.parse, a3.sha, a3.metadata
Refused, require, remaining = a3.Refused, a3.require, a3.remaining
SOURCE = ROOT / 'scripts/run_arv2_r298_plain_readiness.py'
CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_plain_readiness/R322-20261025-C'
SCHEMA = 'arv2-r298-plain-readiness-operation-v1'
PROJECT = remote.PROJECT_ID
DEADLINE_SECONDS, MAX_OUTPUT, MAX_DISPATCH = 900, 128 * 1024, 64
WORKER_MAX_OUTPUT = 640 * 1024
FALSE_FLAGS = dict(a3.FALSE_FLAGS)
FALSE_FLAGS.update(backtest_created=False, capacity_observed=False, launch_authorized=False)
WORKERS = ('admission-initial-worker', 'admission-final-worker')
STORAGE_CONTROL = ROOT / 'artifacts/analyst_revisions_v2/newrule_plain_storage/R322-20261025-B'
# These must be filled only from the actual successful D2 observation and its
# separately committed freeze. Placeholders deliberately refuse all operation.
STORAGE_FREEZE = {'actual_exit': None, 'expected_head': None, 'caller_sha256': None,
    'profile_sha256': None, 'source_manifest_sha256': None,
    'files': {'broker-report.json': None, 'worker-result.json': None,
        'organization-binding.json': None, storage.REPORT: None, storage.ADMISSION: None}}
RUNTIME = ROOT / '.pytest_cache/arv2-r298-plain-readiness'
NEW_PINS = {
    'scripts/arv2_r298_plain_readiness_remote.py': '5cd7b3209f499157c4e8d1f2d8ed9528008c2a90f3a8d7c8e404a831d5313564',
    'scripts/arv2_r298_plain_source_boundary.py': '3f0274b2ef618a1c6af8e6fb5c828a351d502c1cbfe2925b236f3bbf12ff9240',
    'scripts/prepare_arv2_newrule_plain_transport.py': '858d631f3aecd4107581ee768fbb606eb5f48addacbf0c1c43ecabf5b615158a',
    'scripts/arv2_newrule_plain_storage.py': 'b7be26c1bee3d9ff07b2daeb2c61d7731d85d0f54f7e1dd25978d81cce9de022',
    'scripts/run_arv2_plain_storage_publication.py': '0' * 64,
    'scripts/run_arv2_r298_handoff_recovery.py': '48dd4e68d08f900fb9648ee20fc5cdd558d9b9974f753c70188a7b2efb56cf74',
    'scripts/run_arv2_r298_access_recovery.py': '1e02200da124c4143437c022e9a29ff251d5d284ceb3158431187ded0686608e',
    'scripts/arv2_r298_handoff_recovery_remote.py': '4bd4be3c0fed06735dbeba67dce1e25ac3122ffaca6aeebec1588cf785db497c',
    'scripts/arv2_r298_readiness_recovery_remote.py': 'bdf8dba1c4df5394e8acdfe760b92767450390b2c33b017472f73c4d80f7a1cd',
    'scripts/observe_arv2_r298_access_mismatch.py': '0266745324e915b779bd9c50188fca28be880534bb7e5f4b322fb98d7acf3d78',
    'scripts/observe_arv2_r298_lock_access.py': '9e573ba92f31921f8223ae8ff0d48ee82e38a90ef37d821158413a1852afbfc5',
    'scripts/arv2_r298_qc_diagnostic_boundary.py': '483a1616c71e48c2b9a06e83ea49d225b1bfe838ea6b3ac032a716b751af4acc',
    'scripts/arv2_r298_qc_error_text.py': 'a0942586f49c7055d178e4ffc1d94ce8d7433e68812ef6527c54f21430d92ddb',
    'scripts/arv2_r298_qc_response_evidence.py': 'd8088312fac7879e3489780429c5a2e1247cd3a237ed6e331a51df134e0804f3',
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
    ROOT / 'artifacts/analyst_revisions_v2/newrule_readiness_recovery/R321-20261024-B',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_handoff_recovery/R320-20261024-B',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_access_mismatch/R321-20261024-A',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_diagnostic_recovery/R320-20261024-A',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_response_recovery/R319-20261024-A',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_access_recovery/R315-20261024-A',
    ROOT / 'artifacts/analyst_revisions_v2/newrule_file_effect/R316-20261024-A',
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
    '(deny file-read* file-write* (subpath "/Users/sheltonchen/Library/Keychains"))'
    '(deny file-read* file-write* (subpath "/Library/Keychains"))'
    + ''.join(f'(deny file-read* (subpath "{path}"))' for path in OLD_CONTROLS)
    + '(deny file-write* (require-all '
    f'(require-not (subpath "{CONTROL}")) '
    f'(require-not (subpath "{ROOT / ".pytest_cache"}")) '
    '(require-not (literal "/dev/null"))))')


STAGES = frozenset(('claim', 'admission_initial', 'credentials', 'construct', 'inspect',
    'complete', 'compile', 'compile_poll', 'ready', 'admission_final', 'report'))
FINITE = a3.FINITE | frozenset(('client', 'credential_handoff', 'storage_binding', 'public_packet'))
REMOTE_CODES = remote.FINITE | remote.predecessor.FINITE_CODES


def remaining(deadline):
    require(type(deadline) in (float, int) and math.isfinite(deadline)
        and 0 < deadline - time.monotonic() <= DEADLINE_SECONDS, 'deadline')
    return deadline - time.monotonic()


def helper_failure(error):
    if type(error) is remote.Refused:
        return {'helper_code': remote.finite(error), 'predicate': None}
    return remote.predecessor.finite_error(error)


def _storage_freeze():
    value = STORAGE_FREEZE
    require(type(value) is dict and set(value) == {'actual_exit', 'expected_head', 'caller_sha256',
        'profile_sha256', 'source_manifest_sha256', 'files'}
        and type(value['actual_exit']) is int and value['actual_exit'] == 0
        and type(value['expected_head']) is str and re.fullmatch('[0-9a-f]{40}', value['expected_head'])
        and all(a3._digest(value[name]) and value[name] != '0' * 64
            for name in ('caller_sha256', 'profile_sha256', 'source_manifest_sha256'))
        and type(value['files']) is dict and set(value['files']) == {'broker-report.json',
            'worker-result.json', 'organization-binding.json', storage.REPORT, storage.ADMISSION}, 'storage_binding')
    for pin in value['files'].values():
        require(type(pin) is dict and set(pin) == {'sha256', 'byte_count'}
            and a3._digest(pin['sha256']) and pin['sha256'] != '0' * 64
            and type(pin['byte_count']) is int and 0 < pin['byte_count'] <= 256 * 1024, 'storage_binding')
    return parse(canonical(value))


def finite_code(error):
    if type(error) is remote.Refused:
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
        and value['helper_code'] in (*REMOTE_CODES, 'unknown')
        and value['predicate'] == remote.predecessor.OWNERSHIP_PREDICATES.get(value['helper_code'])
        and value['last_stage'] in STAGES
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
        'files/read': {'codeSourceId'},
        'files/create': {'name', 'content', 'codeSourceId'},
        'files/update': {'name', 'content', 'codeSourceId'}, 'compile/create': set(),
        'compile/read': {'compileId'}, 'backtests/list': {'includeStatistics'},
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
        remote.predecessor._cloud_id(payload['compileId'])
    if 'includeStatistics' in payload:
        require(payload['includeStatistics'] is False, 'client')


class OwnerClient:
    """Exact supplied-source upload observation; no fallback or second update.

    Only the fixed input-runtime update uses the separately pinned diagnostic
    boundary. The same real client and unchanged bounded transport serve every
    other request. This object is serialized and private to one recovery.
    """
    __slots__ = ('__api', '__sink', '__target_used', '__boundary_code')

    def __init__(self, sink):
        from scripts import arv2_newrule_execution_environment as environment
        from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
        require(callable(sink), 'client')
        environment.require_safe_environment()
        api = old._client()
        environment.require_safe_environment()
        self._check(api)
        self.__api = api
        self.__sink, self.__target_used, self.__boundary_code = sink, False, None

    def __repr__(self):
        return '<PlainReadinessObservedR298Client>'

    @property
    def boundary_code(self):
        return self.__boundary_code

    @staticmethod
    def _check(api):
        from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
        require(type(api) is old.QuantConnectClient and type(api._base_url) is str
            and api._base_url == old.API_BASE
            and api._transport is old.coverage._bounded_transport
            and type(api._timeout) in (int, float) and api._timeout == 30, 'client')

    def request(self, endpoint, payload):
        from scripts import arv2_newrule_execution_environment as environment
        environment.require_safe_environment()
        self._check(self.__api)
        _validate_request(endpoint, payload)
        if endpoint == boundary.ENDPOINT and payload['name'] == boundary.TARGET_NAME:
            require(not self.__target_used, 'client')
            self.__target_used = True
            original = self.__api._transport
            observed = boundary.OneResponseBoundary(original, self.__sink)
            self.__api._transport = observed
            try:
                return observed.observed_request(self.__api, payload)
            except boundary.BoundaryError as error:
                self.__boundary_code = boundary.finite_error(error)['code']
                raise
            finally:
                self.__api._transport = original
        return self.__api.request(endpoint, payload)


def selected_pins():
    from scripts import run_arv2_plain_storage_publication as publication
    return {**a6.selected_pins(), **prep.selected_pins(), **publication.selected_pins(),
        **NEW_PINS, 'scripts/run_arv2_newrule_comparison.py': v5.FROZEN_CALLER_SHA256}


def profile_record():
    return {'schema': SCHEMA, 'root': str(ROOT), 'control': str(CONTROL),
        'branch': frozen.BRANCH, 'python': str(frozen.PYTHON), 'project_id': PROJECT,
        'attempt_id': 11, 'additional_attempts': 1, 'ordinary_attempt_ceiling': 3,
        'owner_readiness_delegation_required': True,
        'independent_review_or_exact_waiver_required': True,
        'shared_look': 1, 'development_look': 1, 'source_pins': selected_pins(),
        'code_source_id': remote.CODE_SOURCE_ID,
        'purpose': 'plain_data_transport_exact_source_completion_and_compile_no_launch',
        'package_sha256': remote.PACKAGE_SHA256, 'projection_sha256': remote.PROJECTION_SHA256,
        'candidate_profile_sha256': remote.PROFILE_SHA256, 'activation_sha256': remote.ACTIVATION_SHA256,
        'storage_freeze': STORAGE_FREEZE, 'storage_control': str(STORAGE_CONTROL),
        'actual_storage_parent_exit_zero_required': True, 'old_d15_admits_new_objects': False,
        'recover_nonempty_credential_shape_before_control_claim': True,
        'credential_presence_proves_authentication': False, 'worker_credentials_allowed': False,
        'parent_private_row_parsing': False, 'worker_public_packet_only': True,
        'access_policy': 'arv2-r298-collaborator-access-v1',
        'owner_row_sha256': remote.access.OWNER_ROW_SHA256,
        'extra_row_sha256': remote.access.A5_ROW_SHA256,
        'old_mia_row_accepted': False, 'sharing_operation_allowed': False,
        'historical_or_global_privacy_proven': False,
        'edit_lock_is_continuous_ownership_proof': False,
        'worker_operations': list(WORKERS), 'native_sandbox': SANDBOX,
        'deadline_seconds': DEADLINE_SECONDS, 'max_application_dispatches': MAX_DISPATCH,
        'compile_poll_limit': 20, 'compile_interval_seconds': 10,
        'capacity_backtest_status_or_result_allowed': False, 'max_backtest_creates': 0,
        'final_fresh_access_source_compile_binding': True,
        'latest_access_snapshot_preserved_before_policy_gate': True,
        'max_output_bytes': MAX_OUTPUT, 'worker_max_output_bytes': WORKER_MAX_OUTPUT,
        'response_boundary_profile_sha256': sha(canonical(boundary.profile_record())),
        'response_evidence_profile_sha256': response_evidence.PROFILE_SHA256,
        'error_text_profile_sha256': error_text.PROFILE_SHA256,
        'source_policy_acceptance_preverified': False,
        'refused_diagnostic_stops_without_retry': True,
        'response_endpoint': boundary.ENDPOINT, 'response_target': boundary.TARGET_NAME,
        'response_source_sha256': boundary.SOURCE_SHA256,
        'response_journal_before_shared_parser': True, 'response_evidence_is_remote_effect_proof': False,
        'non_2xx_details_still_unknown_at_boundary': True,
        'actual_parent_exit_zero_required': True, 'old_controls_or_operational_entrypoints_allowed': False,
        'fresh_native_source_and_new_storage_admission_before_credentials_and_at_ready': True,
        'a1_through_a10_remain_spent': True,
        'automatic_retry': False, 'same_project_only': True, **FALSE_FLAGS}


def binding(args):
    return {'schema': SCHEMA, 'expected_head': args.expected_head,
        'caller_sha256': args.caller_sha256, 'profile_sha256': sha(canonical(profile_record())),
        'project_id': PROJECT}


def claim(args):
    return {**binding(args), 'attempt_id': 11, 'shared_look': 1, 'development_look': 1,
        'old_attempts_remain_spent': True}


def _response_record(args, observation):
    return {**binding(args), 'observation': {
        key: value for key, value in observation.items() if key != 'journal_pin'}, **FALSE_FLAGS}


def _validate_response(observation, *, args=None, published=False):
    """Finite projection and optional exact publication binding, never raw body."""
    if observation is None:
        return
    require(type(observation) is dict and set(observation) == {
        'project_id', 'endpoint', 'target_name', 'source_sha256',
        'boundary_profile_sha256', 'intent_marker', 'application_dispatch_count',
        'evidence', 'error_text', 'journal_pin'}, 'journal')
    require(type(observation['project_id']) is int and observation['project_id'] == PROJECT
        and observation['endpoint'] == boundary.ENDPOINT
        and observation['target_name'] == boundary.TARGET_NAME
        and observation['source_sha256'] == boundary.SOURCE_SHA256
        and observation['boundary_profile_sha256'] == sha(canonical(boundary.profile_record()))
        and observation['intent_marker'] == 'complete-write-02'
        and type(observation['application_dispatch_count']) is int
        and 1 <= observation['application_dispatch_count'] <= MAX_DISPATCH, 'journal')
    response_evidence.validate_evidence(observation['evidence'])
    _validate_error_binding(observation['evidence'], observation['error_text'])
    require(200 <= observation['evidence']['http_status'] < 300
        and len(canonical(observation['evidence'])) <= boundary.MAX_EVIDENCE_BYTES, 'journal')
    pin = observation['journal_pin']
    require(not published or pin is not None, 'journal')
    if pin is not None:
        require(type(pin) is dict and set(pin) == {'sha256', 'byte_count'}
            and a3._digest(pin['sha256']) and type(pin['byte_count']) is int
            and 0 < pin['byte_count'] <= MAX_OUTPUT, 'journal')
        if args is not None:
            raw = canonical(_response_record(args, observation))
            require(pin == {'sha256': sha(raw), 'byte_count': len(raw)}, 'journal')


def _validate_error_binding(evidence, diagnostic):
    """Bind both independent finite views to the same response and error item."""
    error_text.validate_error_text(diagnostic)
    require(all(diagnostic[key] == evidence[key] for key in
        ('http_status', 'body_byte_count', 'body_sha256'))
        and len(canonical(diagnostic)) <= error_text.MAX_OUTPUT_BYTES, 'journal')
    error_item = None
    expected_shape = 'response_shape'
    if evidence['outcome'] == 'object':
        fields = evidence['fields']
        errors = fields['errors']
        if fields['success']['boolean_value'] is False:
            expected_shape = 'error_shape'
        if (fields['success']['boolean_value'] is False and errors['json_type'] == 'array'
                and errors['count'] == 1 and len(errors['items']) == 1
                and errors['items'][0]['json_type'] == 'string'):
            error_item = errors['items'][0]
    if error_item is None:
        require(diagnostic['fallback_code'] == expected_shape, 'journal')
    require(diagnostic['error_string_byte_count'] == (None if error_item is None else
        error_item['string_utf8_byte_count']) and diagnostic['error_string_sha256'] ==
        (None if error_item is None else error_item['string_sha256']), 'journal')


def _access_record(args, observation):
    return {**binding(args), 'access': {key: value for key, value in observation.items()
        if key != 'journal_pin'}, **FALSE_FLAGS}


def _validate_access(value, *, args=None, published=False):
    if value is None:
        require(not published, 'journal')
        return
    require(type(value) is dict and set(value) == {'marker', 'application_dispatch_count',
        'observation', 'journal_pin'} and value['marker'] in
        ('inspect-access', 'complete-access', 'compile-access', 'ready-access')
        and type(value['application_dispatch_count']) is int
        and 2 <= value['application_dispatch_count'] <= MAX_DISPATCH, 'journal')
    remote.predecessor.validate_access_observation(value['observation'])
    require(value['observation']['stage'] == value['marker'].removesuffix('-access'), 'journal')
    require(len(canonical(value)) <= 34 * 1024, 'bound')
    pin = value['journal_pin']
    require(not published or pin is not None, 'journal')
    if pin is not None:
        require(type(pin) is dict and set(pin) == {'sha256', 'byte_count'}
            and a3._digest(pin['sha256']) and type(pin['byte_count']) is int
            and 0 < pin['byte_count'] <= MAX_OUTPUT, 'journal')
        if args is not None:
            raw = canonical(_access_record(args, value))
            require(pin == {'sha256': sha(raw), 'byte_count': len(raw)}, 'journal')


def _validate_access_context(value, count, failure=None):
    if value is None:
        return
    require(value['application_dispatch_count'] <= count, 'journal')
    if (failure is not None and value['application_dispatch_count'] == count
            and failure['last_event'] != 'intent'):
        require(failure['endpoint'] == 'projects/collaboration/read'
            and failure['intent_marker'] == value['marker'].removesuffix('-access') + '-collaborators'
            and failure['last_event'] == 'observed', 'journal')


def _validate_ready_access(value, code_running):
    """Success must cohere with the unchanged exact owner/A5 policy.

    Failure observations may retain unknown or contrary rows for diagnosis.
    Matching finite known-row hashes do not prove a continuous cloud lease.
    """
    packet = value['observation']
    project, dedicated = packet['project_observation'], packet['dedicated_observation']
    first, second = project['collaborators'], dedicated['collaborators']
    require(first['json_type'] == second['json_type'] == 'array', 'journal')
    owner, extra = remote.access.OWNER_ROW_SHA256, remote.access.A5_ROW_SHA256
    hashes = sorted(row['row_sha256'] for row in first['records'])
    require(hashes in ([owner], sorted((owner, extra)))
        and [row['row_sha256'] for row in second['records']] == [owner]
        and dedicated['user_permissions'] == 'write'
        and dedicated['user_live_control']['valid_boolean'] is True
        and dedicated['user_live_control']['value'] is True, 'journal')
    idle, public = project['code_running'], project['public']
    require(idle['valid_boolean'] is True and idle['value'] is False
        and (public['present'] is False or public['valid_boolean'] is True and public['value'] is False)
        and code_running == {'present': True, 'kind': 'boolean', 'boolean_value': idle['value']}, 'journal')


def _validate_boundary_code(value):
    require(value is None or (type(value) is str and value in boundary.FINITE_CODES), 'journal')


def _validate_response_context(observation, count, failure=None):
    if observation is None:
        return
    require(observation['application_dispatch_count'] <= count, 'journal')
    evidence = observation['evidence']
    if (observation['journal_pin'] is None or evidence['outcome'] != 'object'
            or evidence['fields']['success']['boolean_value'] is not True):
        require(observation['application_dispatch_count'] == count, 'journal')
    if failure is not None and observation['application_dispatch_count'] == count:
        # A later intent can precede a pre-dispatch deadline/environment refusal
        # without increasing the application count. An observed/failed dispatch
        # at this same count must instead be the exact captured target request.
        if failure['last_event'] != 'intent':
            require(failure['endpoint'] == boundary.ENDPOINT
                and failure['intent_marker'] == observation['intent_marker'], 'journal')
        if failure['last_event'] == 'failure':
            require(failure['http_status'] == observation['evidence']['http_status'], 'journal')


def _preflight(args, deadline):
    require(not v5._under_test() and Path(__file__).absolute() == SOURCE
        and args.operation in ('recover', *WORKERS), 'context')
    require(sys.platform == 'darwin' and os.name == 'posix' and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == frozen.PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT, 'context')
    require(type(args.expected_head) is str and re.fullmatch('[0-9a-f]{40}', args.expected_head)
        and a3._digest(args.caller_sha256)
        and (args.operation in WORKERS) == (args.control_fd is not None), 'arguments')
    if args.operation in WORKERS:
        require(type(args.control_fd) is int and args.control_fd > 2
            and type(args.deadline) is float and args.deadline == deadline
            and set(os.environ) <= {'PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'PYTHONPYCACHEPREFIX',
                'PYTHONDONTWRITEBYTECODE', 'XDG_CACHE_HOME', '__CF_USER_TEXT_ENCODING'}, 'context')
    else:
        require(args.deadline is None, 'arguments')
    _storage_freeze()
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
    remote.require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict,
        'project_shape')
    row = rows[0]
    remote.require(type(row.get('projectId')) is int and row['projectId'] == PROJECT,
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


def _worker_environment():
    """Allowlisted support settings only; never copy the parent environment."""
    RUNTIME.mkdir(mode=0o700, parents=False, exist_ok=True)
    info = RUNTIME.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == 0o700 and RUNTIME.resolve() == RUNTIME, 'context')
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'en_US.UTF-8',
        'TMPDIR': str(RUNTIME), 'PYTHONPYCACHEPREFIX': str(RUNTIME / 'pycache'),
        'PYTHONDONTWRITEBYTECODE': '1',
        'XDG_CACHE_HOME': str(RUNTIME / 'cache')}


def _storage_module():
    from scripts import run_arv2_plain_storage_publication as publication
    return publication


class AdmissionStore:
    """Read-only new storage leaf; retain checked descriptors until final verify."""
    def __init__(self):
        publication = _storage_module()
        require(publication.CONTROL == STORAGE_CONTROL, 'storage_binding')
        self.fd, self.chain = publication._walk(STORAGE_CONTROL)
        self.leaves = {}
        try:
            self.baseline = metadata(os.fstat(self.fd))
            self.verify()
        except BaseException:
            os.close(self.fd)
            raise

    def __enter__(self): return self

    def __exit__(self, *_):
        for fd, _, _ in self.leaves.values(): os.close(fd)
        os.close(self.fd)

    def verify(self):
        other, chain = _storage_module()._walk(STORAGE_CONTROL)
        try:
            held, named = os.fstat(self.fd), os.fstat(other)
            names = os.listdir(other)
            require(chain == self.chain and metadata(held) == metadata(named) == self.baseline
                and held.st_uid == os.getuid() and stat.S_IMODE(held.st_mode) == 0o700
                and held.st_nlink == 2 + len(names) and len(names) <= 128
                and all(type(name) is str and re.fullmatch('[a-z0-9-]+\\.json', name) for name in names), 'control_changed')
            for name, (fd, baseline, _) in self.leaves.items():
                require(metadata(os.fstat(fd)) == baseline
                    == metadata(os.stat(name, dir_fd=other, follow_symlinks=False)), 'control_changed')
            require(metadata(os.fstat(other)) == self.baseline, 'control_changed')
        finally:
            os.close(other)

    def names(self):
        self.verify()
        return tuple(os.listdir(self.fd))

    def read_raw(self, name):
        self.verify()
        require(type(name) is str and re.fullmatch('[a-z0-9-]+\\.json', name), 'control')
        if name in self.leaves:
            return self.leaves[name][2]
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                and 0 < info.st_size <= 256 * 1024, 'control')
            raw = bytearray()
            while len(raw) <= info.st_size:
                chunk = os.read(fd, min(65536, info.st_size + 1 - len(raw)))
                if not chunk: break
                raw.extend(chunk)
            require(len(raw) == info.st_size and metadata(info) == metadata(os.fstat(fd))
                == metadata(os.stat(name, dir_fd=self.fd, follow_symlinks=False)), 'control_changed')
            self.leaves[name] = fd, metadata(info), bytes(raw)
        except BaseException:
            os.close(fd)
            raise
        self.verify()
        return bytes(raw)

    def read(self, name): return parse(self.read_raw(name))


def _storage_receipt():
    frozen_storage = _storage_freeze()
    return {'schema': 'arv2-r298-plain-storage-consumption-v1',
        'actual_storage_exit': frozen_storage['actual_exit'],
        'storage_expected_head': frozen_storage['expected_head'],
        'storage_caller_sha256': frozen_storage['caller_sha256'],
        'storage_profile_sha256': frozen_storage['profile_sha256'],
        'storage_files': frozen_storage['files'], 'projection_sha256': remote.PROJECTION_SHA256,
        'package_sha256': remote.PACKAGE_SHA256, 'candidate_profile_sha256': remote.PROFILE_SHA256,
        'activation_sha256': remote.ACTIVATION_SHA256,
        'source_manifest_sha256': frozen_storage['source_manifest_sha256'],
        'fresh_source_authenticated': True, 'new_storage_authenticated': True,
        'historical_d15_reused': False, 'continuous_source_integrity_proven': False, **FALSE_FLAGS}


def authenticate_storage(plain, projected, deadline):
    """Native worker only: current sources plus the exact successful NEW D2.

    Actual storage exit is an externally observed frozen fact, not inferred
    from report completion. No QC request, old claim or operational entrypoint.
    """
    publication = _storage_module()
    selected = _storage_freeze()
    require(prep.summary(plain, projected) == publication.EXPECTED
        and projected.projection_sha256 == remote.PROJECTION_SHA256, 'input_admission')
    selected_args = type('StorageArgs', (), {'expected_head': selected['expected_head'],
        'caller_sha256': selected['caller_sha256']})()
    expected_binding = publication.binding(selected_args)
    require(expected_binding['profile_sha256'] == selected['profile_sha256'], 'storage_binding')
    with AdmissionStore() as store:
        pinned = {}
        for name, pin in selected['files'].items():
            raw = store.read_raw(name)
            require(len(raw) == pin['byte_count'] and sha(raw) == pin['sha256'], 'input_admission')
            pinned[name] = parse(raw)
        broker = pinned['broker-report.json']
        result_fields = ('worker_result', 'summary', 'organization_binding', 'attempt_consumed',
            'organization_dispatches', 'storage_dispatches', 'worker_exit')
        require(set(broker) == set(expected_binding) | set(result_fields) | set(publication.FALSE_FLAGS)
            and canonical({key: broker[key] for key in expected_binding}) == canonical(expected_binding)
            and all(broker[key] is False for key in publication.FALSE_FLAGS), 'input_admission')
        result = {'complete': True, 'failure_code': None,
            'report': selected['files']['broker-report.json'], **{key: broker[key] for key in result_fields}}
        envelope = {'schema': publication.SCHEMA, 'operation': 'publish', 'binding': expected_binding,
            'complete': True, 'failure_code': None, 'result': result, **publication.FALSE_FLAGS}
        publication.validate_output(canonical(envelope) + b'\n', actual_exit=selected['actual_exit'], expected_binding=expected_binding)
        require(broker['organization_binding'] == selected['files']['organization-binding.json']
            and pinned['worker-result.json'] == {**expected_binding, 'result': broker['worker_result']}, 'input_admission')
        organization = publication.validate_organization_binding(pinned['organization-binding.json'], expected_binding)
        rows, payloads = storage._inventory(plain, remote.PACKAGE_SHA256, remote.ACTIVATION_SHA256)
        bound = storage._binding(remote.PACKAGE_SHA256, remote.ACTIVATION_SHA256, publication.PREPARATION_SHA256, rows)
        report = pinned[storage.REPORT]
        require(set(report) == set(bound) | {'stage', 'complete', 'failure_code', 'attempt_consumed',
            'attempted_request_count', 'attempted_request_count_lower_bound', 'dispatch_count_known',
            'requests', 'initial_states', 'published_indices', 'validated_indices', 'source_rechecks'} | set(storage.FLAGS)
            and canonical({key: report[key] for key in bound}) == canonical(bound)
            and report['complete'] is True and report['failure_code'] is None
            and report['attempt_consumed'] is True and report['stage'] == 'completed'
            and all(report[key] is value for key, value in storage.FLAGS.items()), 'input_admission')
        receipt = broker['worker_result']
        require(receipt['report_sha256'] == selected['files'][storage.REPORT]['sha256']
            and receipt['report_byte_count'] == selected['files'][storage.REPORT]['byte_count']
            and receipt['admission_sha256'] == selected['files'][storage.ADMISSION]['sha256']
            and receipt['admission_byte_count'] == selected['files'][storage.ADMISSION]['byte_count']
            and store.read(storage.CLAIM) == {**bound, 'attempt_consumed': True}, 'input_admission')
        expected_admission = {**bound, 'report_sha256': receipt['report_sha256'],
            'report_byte_count': receipt['report_byte_count'], 'validated_indices': list(range(6)), **storage.FLAGS}
        require(pinned[storage.ADMISSION] == expected_admission, 'input_admission')
        storage._census(store, report, bound, rows, payloads, organization, final=True)
        for entry in report['requests']:
            ordinal = entry['ordinal']
            intent = {key: entry[key] for key in ('ordinal', 'phase', 'endpoint', 'index', 'request_sha256')}
            observed = {'ordinal': ordinal, 'packet': {key: entry[key] for key in storage.PACKET_FIELDS}}
            require(store.read(f'broker-{ordinal:02d}-intent.json') == intent
                and store.read(f'broker-{ordinal:02d}-observed.json') == observed, 'input_admission')
        for name, pid_field in (('parent-claim.json', 'parent_pid'), ('worker-start.json', 'worker_pid')):
            value = store.read(name)
            fields = set(expected_binding) | {pid_field} | ({'attempt_consumed'} if pid_field == 'parent_pid' else set())
            require(set(value) == fields and type(value[pid_field]) is int and value[pid_field] > 0
                and canonical({key: value[key] for key in expected_binding}) == canonical(expected_binding)
                and (pid_field != 'parent_pid' or value['attempt_consumed'] is True), 'input_admission')
        for index, project in enumerate((publication.REFERENCE, PROJECT)):
            require(store.read(f'organization-{index}-intent.json') == {'endpoint': 'projects/read', 'project_id': project}, 'input_admission')
            value = store.read(f'organization-{index}-observed.json')
            require(set(value) == {'project_id', 'organization_sha256', 'response_sha256', 'scope_accepted'}
                and type(value['project_id']) is int and value['project_id'] == project
                and value['organization_sha256'] == remote.access.ORGANIZATION_SHA256
                and value['scope_accepted'] is True and a3._digest(value['response_sha256']), 'input_admission')
        publication.complete_census(store, broker['storage_dispatches'], final=True)
        source_manifest = remote.sha(remote.canonical({'project_id': PROJECT,
            'projection_sha256': remote.PROJECTION_SHA256,
            'files': [{'name': item.project_path, 'byte_count': len(item.source_bytes),
                'sha256': sha(item.source_bytes)} for item in sorted(projected.source_files, key=lambda item: item.project_path)]}))
        require(source_manifest == selected['source_manifest_sha256']
            == broker['summary']['project_source_manifest_sha256'], 'input_admission')
        store.verify()
        remaining(deadline)
    return _storage_receipt()


def _validate_worker_result(value):
    require(type(value) is dict and set(value) == {'admission_authenticated', 'storage_receipt',
        'projection_record', 'source_pairs'} and value['admission_authenticated'] is True
        and canonical(value['storage_receipt']) == canonical(_storage_receipt())
        and type(value['projection_record']) is str and value['projection_record'].isascii()
        and type(value['source_pairs']) is list and len(value['source_pairs']) == 11
        and len(canonical(value)) <= WORKER_MAX_OUTPUT, 'public_packet')
    pairs = []
    for item in value['source_pairs']:
        require(type(item) is list and len(item) == 2 and all(type(part) is str and part.isascii() for part in item), 'public_packet')
        pairs.append((item[0], item[1].encode('ascii')))
    record = value['projection_record'].encode('ascii')
    remote.validate_public_packet(record, tuple(pairs))
    return record, tuple(pairs)


def _worker(args, deadline):
    from scripts import arv2_newrule_execution_environment as environment
    environment.require_safe_environment()
    with Store(inherited=args.control_fd) as store:
        require(store.read('claim.json')[1] == claim(args), 'claim')
        store.write(args.operation + '-start.json', claim(args))
        plain, projected = prep.construct(deadline)
        storage_receipt = authenticate_storage(plain, projected, deadline)
        remaining(deadline)
        packet = {'admission_authenticated': True, 'storage_receipt': storage_receipt,
            'projection_record': projected.record_bytes.decode('ascii'),
            'source_pairs': [[item.project_path, item.source_bytes.decode('ascii')]
                             for item in projected.source_files]}
        _validate_worker_result(packet)
        return packet


def _child(args, store, deadline, operation):
    require(operation in WORKERS, 'arguments')
    env = _worker_environment()
    command = ['/usr/bin/sandbox-exec', '-p', SANDBOX, str(frozen.PYTHON), '-B', str(SOURCE), operation,
        '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256,
        '--control-fd', str(store.fd), '--deadline', str(deadline)]
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
                        require(len(key.data) <= WORKER_MAX_OUTPUT, 'child_output')
            code = process.wait(timeout=remaining(deadline))
        require(type(code) is int and code == 0 and not errors, 'child_failed')
        require(bytes(output).endswith(b'\n\n'), 'child_output')
        payload = parse(bytes(output[:-1]))
        require(set(payload) == {'schema', 'operation', 'binding', 'result', 'operation_completed', *FALSE_FLAGS}
            and payload['schema'] == SCHEMA and payload['binding'] == binding(args)
            and payload['operation'] == operation and payload['operation_completed'] is True
            and all(payload[key] is False for key in FALSE_FLAGS), 'child_output')
        result = payload['result']
        _validate_worker_result(result)
        store.write(operation + '-completed.json', {**binding(args),
            'storage_receipt': result['storage_receipt'], 'public_packet_sha256': sha(canonical(result)),
            'public_packet_byte_count': len(canonical(result)), 'actual_worker_exit': code})
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
    result = {'code': finite_code(error), **helper_failure(error),
        'last_stage': state['last_stage'], 'intent_marker': state['intent_marker'],
        'endpoint': state['endpoint'], 'last_event': state['last_event'],
        'application_dispatch_count': state['application_dispatch_count'],
        'category': state['category'], 'http_status': state['http_status'],
        'provider_request_count': None}
    _validate_failure(result)
    observation = state.get('code_running')
    if observation is not None:
        _validate_code_running(observation)
    access = state.get('access_observation')
    _validate_access(access)
    _validate_access_context(access, result['application_dispatch_count'], result)
    response = state.get('response_observation')
    _validate_response(response)
    _validate_response_context(response, result['application_dispatch_count'], result)
    boundary_code = state.get('response_boundary_code')
    _validate_boundary_code(boundary_code)
    return {**result, 'code_running': observation,
        'access_observation': access,
        'response_observation': response, 'response_boundary_code': boundary_code}


def failure_observation(error):
    if type(error) is not ObservedFailure:
        return None
    args = BaseException.args.__get__(error)
    require(len(args) == 1 and type(args[0]) is bytes and len(args[0]) <= MAX_OUTPUT, 'journal')
    value = parse(args[0])
    extra = {'code_running', 'access_observation',
        'response_observation', 'response_boundary_code'}
    require(extra <= set(value), 'journal')
    _validate_failure({key: item for key, item in value.items() if key not in extra})
    if value['code_running'] is not None:
        _validate_code_running(value['code_running'])
    _validate_access(value['access_observation'])
    _validate_access_context(value['access_observation'], value['application_dispatch_count'], value)
    _validate_response(value['response_observation'])
    _validate_response_context(value['response_observation'], value['application_dispatch_count'], value)
    _validate_boundary_code(value['response_boundary_code'])
    return value


def _validate_result(value):
    require(type(value) is dict and set(value) == {'terminal', 'ready_receipt',
        'application_dispatch_count', 'provider_request_count', 'code_running',
        'response_observation', 'access_observation', 'storage_receipt'}
        and value['terminal'] == 'ready_for_backtest'
        and type(value['application_dispatch_count']) is int
        and 1 <= value['application_dispatch_count'] <= MAX_DISPATCH
        and value['provider_request_count'] is None, 'bound')
    _validate_code_running(value['code_running'])
    require(value['code_running'] == {'present': True, 'kind': 'boolean', 'boolean_value': False}, 'bound')
    require(canonical(value['storage_receipt']) == canonical(_storage_receipt())
        and len(canonical(value)) <= MAX_OUTPUT, 'bound')
    remote.validate_ready_receipt(value['ready_receipt'],
        expected_source_manifest_sha256=_storage_freeze()['source_manifest_sha256'])
    _validate_response(value['response_observation'], published=True)
    _validate_response_context(value['response_observation'], value['application_dispatch_count'])
    if value['response_observation'] is not None:
        evidence = value['response_observation']['evidence']
        require(evidence['outcome'] == 'object'
            and evidence['fields']['success']['boolean_value'] is True, 'bound')
    _validate_access(value['access_observation'], published=True)
    require(value['access_observation'] is not None
        and value['access_observation']['marker'] == 'ready-access'
        and value['access_observation']['application_dispatch_count'] <= value['application_dispatch_count'], 'bound')
    _validate_ready_access(value['access_observation'], value['code_running'])


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
        _validate_response(result['response_observation'], args=args, published=True)
        _validate_access(result['access_observation'], args=args, published=True)
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
            _validate_response(observation['response_observation'], args=args)
            _validate_access(observation['access_observation'], args=args)
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
    state['last_stage'] = 'ready'
    ready = runner.ready_once(compiled)
    remote.validate_ready_receipt(ready,
        expected_source_manifest_sha256=_storage_freeze()['source_manifest_sha256'])
    store.write('ready-receipt.json', ready)
    state['last_stage'] = 'admission_final'
    final = _child(args, store, deadline, 'admission-final-worker')
    _validate_worker_result(final)
    return {'terminal': 'ready_for_backtest', 'ready_receipt': ready,
        'storage_receipt': final['storage_receipt']}


def _recover(args, store, deadline, state):
    from scripts import arv2_newrule_execution_environment as environment
    store.write('claim.json', claim(args))
    state['last_stage'] = 'admission_initial'
    supplied = _child(args, store, deadline, 'admission-initial-worker')
    projection_record, source_pairs = _validate_worker_result(supplied)
    state['last_stage'] = 'credentials'
    environment.require_safe_environment()

    def save_response(snapshot):
        remaining(deadline)
        require(type(snapshot) is bytes and 0 < len(snapshot) <= boundary.MAX_EVIDENCE_BYTES
            and state.get('response_observation') is None
            and state['endpoint'] == boundary.ENDPOINT and state['last_event'] == 'intent', 'journal')
        projected_response = parse(snapshot)
        require(type(projected_response) is dict and set(projected_response) ==
            {'evidence', 'error_text'}, 'journal')
        response_evidence.validate_evidence(projected_response['evidence'])
        _validate_error_binding(projected_response['evidence'], projected_response['error_text'])
        observation = {'project_id': PROJECT, 'endpoint': boundary.ENDPOINT,
            'target_name': boundary.TARGET_NAME, 'source_sha256': boundary.SOURCE_SHA256,
            'boundary_profile_sha256': sha(canonical(boundary.profile_record())),
            'intent_marker': state['intent_marker'],
            'application_dispatch_count': state['application_dispatch_count'],
            'evidence': projected_response['evidence'], 'error_text': projected_response['error_text'],
            'journal_pin': None}
        _validate_response(observation)
        # Preserve only finite immutable input in memory before publication;
        # a failed fsync/write cannot erase the observed refusal from exit2.
        state['response_observation'] = parse(canonical(observation))
        pin = store.write('input-runtime-response.json', _response_record(args, observation))
        state['response_observation']['journal_pin'] = pin
        _validate_response(state['response_observation'], args=args, published=True)
        remaining(deadline)

    client = OwnerClient(save_response)

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
            response = client.request(endpoint, payload)
            if endpoint == 'projects/read':
                state['code_running'] = code_running_observation(response)
            return response
        except BaseException as error:
            state.update(previous.http_context(error, endpoint))
            state['response_boundary_code'] = client.boundary_code
            observed = state.get('response_observation')
            if observed is not None and observed['application_dispatch_count'] == state['application_dispatch_count']:
                state['http_status'] = observed['evidence']['http_status']
                state['category'] = ('http_failure' if client.boundary_code == 'shared_request_refused'
                    else 'http_non_json' if client.boundary_code == 'response_not_object' else 'unknown')
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

    def observe_access(marker, packet):
        remaining(deadline)
        require(marker in ('inspect-access', 'complete-access', 'compile-access', 'ready-access')
            and state['endpoint'] == 'projects/collaboration/read'
            and state['last_event'] == 'observed'
            and state['intent_marker'] == marker.removesuffix('-access') + '-collaborators', 'journal')
        remote.predecessor.validate_access_observation(packet)
        observed = {'marker': marker, 'application_dispatch_count': state['application_dispatch_count'],
            'observation': packet, 'journal_pin': None}
        _validate_access(observed)
        # Preserve the latest safe snapshot before a publication failure or policy refusal.
        state['access_observation'] = parse(canonical(observed))
        pin = store.write(marker + '.json', _access_record(args, observed))
        state['access_observation']['journal_pin'] = pin
        _validate_access(state['access_observation'], args=args, published=True)

    state['last_stage'] = 'construct'
    runner = remote.PlainReadiness(projection_record, source_pairs, request=request,
        journal=journal, observe_access=observe_access)
    result = _workflow(args, runner, store, deadline, state)
    return {**result, 'application_dispatch_count': state['application_dispatch_count'],
        'provider_request_count': None, 'code_running': state['code_running'],
        'response_observation': state.get('response_observation'),
        'access_observation': state.get('access_observation')}


def _require_credential_handoff():
    """Presence only, before own control/private access; not authentication.

    The external observer must also check its exact child environment before
    dispatch. This guard never renews a consumed claim or prints a value,
    credential length, source, lookup detail or account identifier.
    """
    for name in ('QC_USER_ID', 'QC_API_TOKEN'):
        value = os.environ.get(name)
        require(type(value) is str and bool(value.strip()), 'credential_handoff')


def _execute(args, deadline):
    _preflight(args, deadline)
    from scripts import arv2_newrule_execution_environment as environment
    environment.require_safe_environment()
    if args.operation in WORKERS:
        return _worker(args, deadline)
    _require_credential_handoff()
    with Store(create=True) as store:
        state = {**a3._new_state(), 'code_running': None,
            'response_observation': None, 'response_boundary_code': None, 'access_observation': None}
        try:
            result = _recover(args, store, deadline, state)
            state['last_stage'] = 'report'
            _preflight(args, deadline)
            _validate_result(result)
            _validate_response(result['response_observation'], args=args, published=True)
            _validate_access(result['access_observation'], args=args, published=True)
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
    parser.add_argument('--deadline', type=float)
    args = parser.parse_args(argv)
    deadline = args.deadline if args.operation in WORKERS else time.monotonic() + DEADLINE_SECONDS
    try:
        with helpers._alarm(deadline):
            _preflight(args, deadline)
            from scripts import arv2_newrule_execution_environment as environment
            environment._bootstrap_cli_logging()
            result = _execute(args, deadline)
            payload = canonical({'schema': SCHEMA, 'operation': args.operation, 'binding': binding(args),
                'result': result, 'operation_completed': True, **FALSE_FLAGS})
            require(len(payload) <= (WORKER_MAX_OUTPUT if args.operation in WORKERS else MAX_OUTPUT), 'bound')
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

