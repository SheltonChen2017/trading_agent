"""Injected A10 exact-source readiness recovery, never a backtest launcher.

A1-A9 and their controls remain spent. The separately frozen parent supplies
claim, deadline, admission, response handling and durable sinks. Current access
observations precede the unchanged strict owner/A5 policy, without refreshing
pins. Source completion and compile retain the frozen candidate/economics.
Ready means matching compiled source at bounded sequential checks, not a lease,
privacy proof, strategy acceptance, capacity observation or launch authority.
"""
import json
import re

from scripts import arv2_r298_handoff_recovery_remote as previous
from scripts import observe_arv2_r298_access_mismatch as diagnostic


post_mia, frozen, access = previous.post_mia, previous.frozen, previous.access
PROJECT_ID, PROJECT_NAME = previous.PROJECT_ID, previous.PROJECT_NAME
PROJECTION_SHA256, PROJECTION_CANDIDATE_ID = previous.PROJECTION_SHA256, previous.PROJECTION_CANDIDATE_ID
SOURCE_NAMES, ORGANIZATION_SHA256 = previous.SOURCE_NAMES, previous.ORGANIZATION_SHA256
ATTEMPT = 10
BACKTEST_NAME = None  # This contract has no launch name or backtest-create capability.
CODE_SOURCE_ID = previous.CODE_SOURCE_ID
COLLABORATION_ENDPOINT, LOCK_ENDPOINT = previous.COLLABORATION_ENDPOINT, previous.LOCK_ENDPOINT
ENDPOINTS = previous.ENDPOINTS - {'projects/nodes/read', 'backtests/create'}
MANUAL_BACKTEST_ID, MANUAL_BACKTEST_NAME = previous.MANUAL_BACKTEST_ID, previous.MANUAL_BACKTEST_NAME
RETAINED_SOURCE_NAMES = previous.RETAINED_SOURCE_NAMES
RecoveryError = previous.RecoveryError
_require, _canonical, _sha, _cloud_id = previous._require, previous._canonical, previous._sha, previous._cloud_id
_strict_canonical = previous._strict_canonical
_backtest_rows, _manual_backtest = previous._backtest_rows, previous._manual_backtest
code_running_observation = previous.code_running_observation
_validate_code_running = previous._validate_code_running
OWNERSHIP_PREDICATES = dict(previous.OWNERSHIP_PREDICATES)
FINITE_CODES = previous.FINITE_CODES | frozenset(('readiness_only', 'readiness_used',
    'readiness_compile_binding', 'readiness_manifest', 'access_observation', 'access_observation_sink'))
OWNED_STAGES = ('inspect', 'complete', 'compile', 'ready')
ACCESS_SCHEMA = 'arv2-r298-readiness-access-v1'
READY_SCHEMA = 'arv2-r298-readiness-receipt-v1'
SOURCE_MANIFEST_SHA256 = '1d2b2d763045256ac0613b07bb8097b92feb7915ea5c4da8ba6d24fbe7b9a453'
ACCESS_FALSE = {'collaborator_policy_accepted': False, 'privacy_verified': False,
    'synthetic_entry_proven': False, 'edit_lock_proven': False,
    'historical_a9_response_reconstructed': False, 'atomic_snapshot_proven': False}
READY_FALSE = {'backtest_created': False, 'capacity_observed': False,
    'launch_authorized': False, 'strategy_result_accepted': False}
MAX_ACCESS_BYTES = 32768


def finite_error(error):
    code = 'unknown'
    if type(error) is RecoveryError:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE_CODES:
            code = args[0]
    return {'helper_code': code, 'predicate': OWNERSHIP_PREDICATES.get(code)}


def _access_result(project, dedicated):
    return {'stage': 'collaborators', 'application_dispatch_count': 2,
        'last_event': 'observation_saved', 'last_endpoint': COLLABORATION_ENDPOINT,
        'project_observation': project, 'dedicated_observation': dedicated,
        'comparison': diagnostic.projection.comparison(project, dedicated),
        'provider_request_count': None}


def access_observation_record(stage, project_response, dedicated_response):
    """Memory-only projection. Never returns raw IDs, keys, rows or errors."""
    _require(type(stage) is str and stage in OWNED_STAGES, 'access_observation')
    try:
        project_packet = diagnostic.response_snapshot(project_response)
        dedicated_packet = diagnostic.response_snapshot(dedicated_response)
        owner_id, project = diagnostic.projection.project_observation(project_packet)
        dedicated = diagnostic.projection.dedicated_observation(dedicated_packet, owner_id)
        result = _access_result(project, dedicated)
        value = {'schema': ACCESS_SCHEMA, 'stage': stage, 'project_id': PROJECT_ID,
            'project_response_sha256': _sha(_strict_canonical(project_packet)),
            'dedicated_response_sha256': _sha(_strict_canonical(dedicated_packet)),
            'project_observation': project, 'dedicated_observation': dedicated,
            'comparison': result['comparison'],
            'comparison_to_frozen_policy': diagnostic.policy_comparison(result), **ACCESS_FALSE}
        return validate_access_observation(value)
    except diagnostic.Refused:
        raise RecoveryError('access_observation') from None


def validate_access_observation(value):
    """Validate supplied finite metadata; this never admits a collaborator."""
    _require(type(value) is dict and set(value) == {'schema', 'stage', 'project_id',
        'project_response_sha256', 'dedicated_response_sha256', 'project_observation',
        'dedicated_observation', 'comparison', 'comparison_to_frozen_policy'} | set(ACCESS_FALSE),
        'access_observation')
    raw = _strict_canonical(value)
    _require(len(raw) <= MAX_ACCESS_BYTES, 'access_observation')
    value = json.loads(raw)
    _require(value['schema'] == ACCESS_SCHEMA and type(value['stage']) is str
        and value['stage'] in OWNED_STAGES and type(value['project_id']) is int
        and value['project_id'] == PROJECT_ID and all(value[key] is False for key in ACCESS_FALSE),
        'access_observation')
    for key in ('project_response_sha256', 'dedicated_response_sha256'):
        _require(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key]), 'access_observation')
    try:
        result = _access_result(value['project_observation'], value['dedicated_observation'])
        diagnostic.projection._validate_result(result, True)
        diagnostic._validate_known_row_facts(result)
        _require(_strict_canonical(value['comparison']) == _strict_canonical(result['comparison'])
            and _strict_canonical(value['comparison_to_frozen_policy']) ==
            _strict_canonical(diagnostic.policy_comparison(result)), 'access_observation')
    except (diagnostic.Refused, KeyError, TypeError):
        raise RecoveryError('access_observation') from None
    return value


def validate_ready_receipt(value):
    keys = {'schema', 'project_id', 'attempt', 'compile_id', 'projection_sha256',
        'source_manifest_sha256', 'state'} | set(READY_FALSE)
    _require(type(value) is dict and set(value) == keys, 'readiness_compile_binding')
    value = json.loads(_strict_canonical(value))
    _require(value['schema'] == READY_SCHEMA and type(value['project_id']) is int
        and value['project_id'] == PROJECT_ID and type(value['attempt']) is int
        and value['attempt'] == ATTEMPT and value['projection_sha256'] == PROJECTION_SHA256
        and value['state'] == 'compiled_exact_source_ready'
        and type(value['source_manifest_sha256']) is str
        and value['source_manifest_sha256'] == SOURCE_MANIFEST_SHA256
        and all(value[key] is False for key in READY_FALSE), 'readiness_compile_binding')
    _cloud_id(value['compile_id'])
    return value


class ReadinessRecovery(previous.HandoffRecovery):
    """Exact source completion/compile only; no launch-capable fallback path."""

    def __init__(self, projection, organization_sha256, request, journal, observe, access_observation):
        _require(callable(access_observation), 'callbacks')
        super().__init__(projection, organization_sha256, request, journal, observe)
        self._access_observation = access_observation
        self._compiled_receipt = None
        self._readiness_used = False

    def _rpc(self, marker, endpoint, payload):
        _require(type(endpoint) is str and endpoint in ENDPOINTS, 'readiness_only')
        if endpoint == 'backtests/list':
            _require(type(marker) is str and marker in {
                prefix + '-backtests' for prefix in OWNED_STAGES}, 'readiness_only')
        return super()._rpc(marker, endpoint, payload)

    def _owned(self, prefix):
        _require(type(prefix) is str and prefix in OWNED_STAGES, 'readiness_only')
        _require(self._organization_sha256 == access.ORGANIZATION_SHA256, 'organization_pin')
        project = self._rpc(prefix + '-project', 'projects/read', {'projectId': PROJECT_ID})
        dedicated = self._rpc(prefix + '-collaborators', COLLABORATION_ENDPOINT, {'projectId': PROJECT_ID})
        observation = access_observation_record(prefix, project, dedicated)
        try:
            result = self._access_observation(prefix + '-access', observation)
        except Exception:
            raise RecoveryError('access_observation_sink') from None
        _require(result is None, 'access_observation_sink')
        try:
            access.verify_access(project, dedicated)  # Unchanged exact owner/A5 gate.
        except access.AccessRefused as error:
            code = access.finite_error(error)['code']
            _require(code in access.FINITE_CODES, 'response_shape')
            raise RecoveryError('access_' + code) from None
        history = self._rpc(prefix + '-backtests', 'backtests/list',
            {'projectId': PROJECT_ID, 'includeStatistics': False})
        rows = _backtest_rows(history, 1, 'prior_backtests')
        _require(_manual_backtest(rows[0]), 'prior_backtests')

    def compile_once(self, completed_inventory):
        _require(self._compiled_receipt is None, 'readiness_compile_binding')
        compiled = super().compile_once(completed_inventory)
        self._compiled_receipt = _strict_canonical(compiled)
        return json.loads(self._compiled_receipt)

    def ready_once(self, compiled_receipt):
        _require(not self._readiness_used, 'readiness_used')
        self._readiness_used = True  # Ambiguous failure never permits another check.
        _require(self._compiled_receipt is not None and
            _strict_canonical(compiled_receipt) == self._compiled_receipt, 'readiness_compile_binding')
        compiled = json.loads(self._compiled_receipt)
        compile_id = compiled['compile_id']
        _require(self._compile_state(compile_id, 'ready-compile') == 'BuildSuccess', 'compile_not_ready')
        self._owned('ready')
        inventory = self._files('ready-files', complete=True)
        _require(_sha(_strict_canonical(inventory)) == compiled['source_manifest_sha256'], 'readiness_manifest')
        return validate_ready_receipt({'schema': READY_SCHEMA, 'project_id': PROJECT_ID,
            'attempt': ATTEMPT, 'compile_id': compile_id, 'projection_sha256': PROJECTION_SHA256,
            'source_manifest_sha256': compiled['source_manifest_sha256'],
            'state': 'compiled_exact_source_ready', **READY_FALSE})

    def launch_once(self, *_args, **_kwargs):
        raise RecoveryError('readiness_only')

    def read_status(self, *_args, **_kwargs):
        raise RecoveryError('readiness_only')


OwnerRecovery = ReadinessRecovery
