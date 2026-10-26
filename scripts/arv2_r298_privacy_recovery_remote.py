"""Pure one-additional-attempt R298 A5 access-control recovery policy.

A1-A4 remain spent. The separately frozen caller owns this additional attempt,
scope, claim, deadline, admission and actual-exit evidence. This is not a retry
entrypoint or a privacy attestation. QC's documented Project schema has no
public field: positive exact project and owner identities plus the dedicated
sole-owner collaborator ACL establish this bounded access-control gate.
An unexpected public field is checked only for contradiction; its absence or
false value is never proof of universal project/backtest privacy. External
scope evidence and the private-by-default product contract remain qualified.

The exact optional project-view Mia row and same dedicated owner are preserved.
One supported edit lock precedes source-tagged file operations, without claiming
a documented lease or continuous ownership. Stage checks and whole-inventory
readbacks are unchanged. Completed status is not strategy-evidence acceptance.
"""
import json
import re

from scripts import run_arv2_r298_post_mia_recovery as post_mia


frozen = post_mia.remote
PROJECT_ID = frozen.PROJECT_ID
PROJECT_NAME = frozen.PROJECT_NAME
PROJECTION_SHA256 = frozen.PROJECTION_SHA256
PROJECTION_CANDIDATE_ID = frozen.PROJECTION_CANDIDATE_ID
SOURCE_NAMES = frozen.SOURCE_NAMES
ORGANIZATION_SHA256 = frozen.ORGANIZATION_SHA256
BACKTEST_NAME = f'{PROJECT_NAME} A5 {PROJECTION_SHA256[:8]}'
ATTEMPT = 5
CODE_SOURCE_ID = 'Codex ARV2 R298 A5 20261024'
COLLABORATION_ENDPOINT = 'projects/collaboration/read'
LOCK_ENDPOINT = 'projects/collaboration/lock/acquire'
ENDPOINTS = frozen.ENDPOINTS | {COLLABORATION_ENDPOINT, LOCK_ENDPOINT}
MANUAL_BACKTEST_ID = 'bbd2202cc3000e8b1c14751bf088dd16'
MANUAL_BACKTEST_NAME = 'Casual Yellow Kangaroo'
MIA_ROW_SHA256 = '6e3fb9db0a3303a202fdebd062e91cd8a974ac564cab784dbccedc361477f44f'
RETAINED_SOURCE_NAMES = frozenset(('accepted_risk_order_level_core.py',
    'accepted_risk_order_level_forced_exit.py'))
RecoveryError = frozen.RecoveryError
_require, _canonical, _sha, _cloud_id = frozen._require, frozen._canonical, frozen._sha, frozen._cloud_id
code_running_observation = post_mia.code_running_observation
_validate_code_running = post_mia._validate_code_running

OWNERSHIP_PREDICATES = {**{key: value for key, value in frozen.OWNERSHIP_PREDICATES.items()
    if key != 'owned_private'},
    'owned_public_contradiction': 'unexpected_public_contradiction',
    'owned_owner_id': 'owner_id', 'dedicated_owner': 'dedicated_owner',
    'dedicated_permissions': 'dedicated_permissions',
    'project_owner_match': 'project_owner_match', 'project_mia_pin': 'project_mia_pin'}
FINITE_CODES = (frozen.FINITE_CODES - {'owned_private'}) | frozenset((*OWNERSHIP_PREDICATES,
    'request_payload', 'lock_required', 'lock_once', 'lock_refused', 'retained_source'))
_PAYLOAD_KEYS = {
    'projects/read': {'projectId'}, COLLABORATION_ENDPOINT: {'projectId'},
    LOCK_ENDPOINT: {'projectId', 'codeSourceId'},
    'backtests/list': {'projectId', 'includeStatistics'},
    'files/read': {'projectId', 'codeSourceId'},
    'files/create': {'projectId', 'name', 'content', 'codeSourceId'},
    'files/update': {'projectId', 'name', 'content', 'codeSourceId'},
    'compile/create': {'projectId'}, 'compile/read': {'projectId', 'compileId'},
    'projects/nodes/read': {'projectId'},
    'backtests/create': {'projectId', 'compileId', 'backtestName'},
}


def finite_error(error):
    """Fixed category only; never raw collaborator, account or provider text."""
    code = 'unknown'
    if type(error) is RecoveryError:
        args = BaseException.args.__get__(error)
        if (len(args) == 1 and type(args[0]) is str and len(args[0]) <= 96
                and args[0] in FINITE_CODES):
            code = args[0]
    return {'helper_code': code, 'predicate': OWNERSHIP_PREDICATES.get(code)}


def _project_binding(row):
    return ('projectId' not in row or
        (type(row['projectId']) is int and row['projectId'] == PROJECT_ID))


def _backtest_rows(response, count, code):
    rows = response.get('backtests')
    _require(type(rows) is list and len(rows) == count and _project_binding(response)
        and ('count' not in response or (type(response['count']) is int and response['count'] == count)), code)
    _require(all(type(row) is dict and _project_binding(row) for row in rows), code)
    return rows


def _manual_backtest(row):
    return (row.get('backtestId') == MANUAL_BACKTEST_ID
        and row.get('name') == MANUAL_BACKTEST_NAME and row.get('status') == 'Completed.')


class PrivacyRecovery(post_mia.PostMiaRecovery):
    """Injected seams; owner-freed context is an external frozen prerequisite."""

    def __init__(self, projection, organization_sha256, request, journal, observe):
        super().__init__(projection, organization_sha256, request, journal, observe)
        self._acquire_ready = False
        self._lock_acquired = False

    def _rpc(self, marker, endpoint, payload):
        _require(type(marker) is str and re.fullmatch(r'[a-z0-9-]{1,96}', marker)
            and type(endpoint) is str and endpoint in ENDPOINTS and marker not in self._used,
            'duplicate_or_endpoint')
        _require(type(payload) is dict and type(payload.get('projectId')) is int
            and payload['projectId'] == PROJECT_ID, 'request_project')
        payload = json.loads(_canonical(payload))
        if endpoint.startswith('files/'):
            _require(self._lock_acquired, 'lock_required')
            _require('codeSourceId' not in payload or payload['codeSourceId'] == CODE_SOURCE_ID,
                'request_payload')
            payload['codeSourceId'] = CODE_SOURCE_ID
        _require(set(payload) == _PAYLOAD_KEYS[endpoint], 'request_payload')
        if endpoint == 'backtests/list':
            _require(payload['includeStatistics'] is False, 'request_payload')
        if endpoint == LOCK_ENDPOINT:
            _require(marker == 'inspect-lock' and self._acquire_ready and not self._lock_acquired,
                'lock_once')
            _require(payload['codeSourceId'] == CODE_SOURCE_ID, 'request_payload')
            self._acquire_ready = False  # Even a refused/ambiguous dispatch cannot reacquire.
        self._used.add(marker)
        raw = _canonical(payload)
        self._event(marker, 'intent', endpoint, _sha(raw))
        try:
            response = self._request(endpoint, json.loads(raw))
        except Exception:
            raise RecoveryError('request_ambiguous') from None
        _require(type(response) is dict, 'response_shape')
        raw = _canonical(response)
        _require(len(raw) <= 1024 * 1024, 'response_bound')
        self._event(marker, 'observed', endpoint, _sha(raw))
        response = json.loads(raw)
        _require(response.get('success') is True, 'response_refused')
        if endpoint == LOCK_ENDPOINT:
            _require('errors' not in response or (type(response['errors']) is list
                and response['errors'] == []), 'lock_refused')
        if endpoint == 'projects/read':
            observation = code_running_observation(response)
            _validate_code_running(observation)
            _require(self._observe(marker, observation) is None, 'journal_result')
        return response

    def _owned(self, prefix):
        rows = self._rpc(prefix + '-project', 'projects/read', {'projectId': PROJECT_ID}).get('projects')
        _require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'project_shape')
        row = rows[0]
        _require(type(row.get('projectId')) is int and row['projectId'] == PROJECT_ID, 'owned_project_id')
        organization = row.get('organizationId')
        _require(type(organization) is str and re.fullmatch(r'[0-9a-f]{32}', organization)
            and _sha(organization.encode('ascii')) == self._organization_sha256, 'owned_organization')
        _require(row.get('name') == PROJECT_NAME, 'owned_name')
        _require(row.get('language') == 'Py', 'owned_language')
        _require(row.get('owner') is True, 'owned_owner')
        _require('public' not in row or row['public'] is False, 'owned_public_contradiction')
        _require(row.get('codeRunning') is False, 'owned_idle')
        owner_id = row.get('ownerId')
        _require(type(owner_id) is int and 0 < owner_id <= 2 ** 63 - 1, 'owned_owner_id')
        dedicated = self._rpc(prefix + '-collaborators', COLLABORATION_ENDPOINT, {'projectId': PROJECT_ID})
        owners = dedicated.get('collaborators')
        _require(_project_binding(dedicated) and type(owners) is list and len(owners) == 1
            and type(owners[0]) is dict and owners[0].get('owner') is True
            and type(owners[0].get('uid')) is int and owners[0]['uid'] == owner_id
            and owners[0].get('permission') == 'write' and owners[0].get('liveControl') is True,
            'dedicated_owner')
        _require(dedicated.get('userPermissions') == 'write' and dedicated.get('userLiveControl') is True,
            'dedicated_permissions')
        collaborators = row.get('collaborators')
        _require(type(collaborators) is list and 1 <= len(collaborators) <= 2
            and all(type(item) is dict for item in collaborators), 'owned_collaborators')
        owner_bytes = _canonical(owners[0])
        matches = [item for item in collaborators if _canonical(item) == owner_bytes]
        _require(len(matches) == 1, 'project_owner_match')
        for item in collaborators:
            if _canonical(item) == owner_bytes:
                continue
            public_id = item.get('publicId')
            _require(item.get('name') == 'Mia' and item.get('owner') is False
                and 'uid' in item and item['uid'] is None and item.get('permission') == 'write'
                and item.get('liveControl') is True and type(public_id) is str
                and 0 < len(public_id) <= 256 and public_id.isascii() and public_id != 'mia-ai'
                and _sha(_canonical(item)) == MIA_ROW_SHA256, 'project_mia_pin')
        history = self._rpc(prefix + '-backtests', 'backtests/list',
            {'projectId': PROJECT_ID, 'includeStatistics': False})
        previous = _backtest_rows(history, 1, 'prior_backtests')
        _require(_manual_backtest(previous[0]), 'prior_backtests')

    def inspect(self):
        self._owned('inspect')
        self._acquire_ready = True
        self._rpc('inspect-lock', LOCK_ENDPOINT, {'projectId': PROJECT_ID, 'codeSourceId': CODE_SOURCE_ID})
        self._lock_acquired = True
        inventory = self._files('inspect-files')
        seen = {row['name']: row for row in inventory['files']}
        _require(all(seen.get(name) == {'name': name, 'byte_count': len(self._sources[name]),
            'sha256': _sha(self._sources[name])} for name in RETAINED_SOURCE_NAMES), 'retained_source')
        return inventory

    def launch_once(self, compile_id):
        """Retain the exact launched ID even for a fast terminal response.

        Runtime Error is evidence of a failed launch/run, not an accepted
        recovery. The outer caller must retain it and fail without retry.
        """
        _require(self._compile_state(compile_id, 'launch-compile') == 'BuildSuccess',
            'compile_not_ready')
        self._owned('launch')
        self._files('launch-files', complete=True)
        response = self._rpc('launch-capacity', 'projects/nodes/read', {'projectId': PROJECT_ID})
        nodes, auto = response.get('nodes'), response.get('autoSelectNode')
        _require(type(nodes) is dict and type(auto) is bool, 'capacity_shape')
        rows = nodes.get('backtest')
        _require(type(rows) is list and len(rows) <= 64 and all(type(row) is dict
            and type(row.get('busy')) is bool and type(row.get('active')) is bool
            for row in rows), 'capacity_nodes')
        available = sum(not row['busy'] and (auto or row['active']) for row in rows)
        if not available:
            return {'project_id': PROJECT_ID, 'state': 'wait', 'available_count': 0}
        row = self._rpc('launch-create', 'backtests/create', {'projectId': PROJECT_ID,
            'compileId': compile_id, 'backtestName': BACKTEST_NAME}).get('backtest')
        _require(type(row) is dict and type(row.get('projectId')) is int
            and row['projectId'] == PROJECT_ID and row.get('name') == BACKTEST_NAME
            and row.get('status') in ('In Queue...', 'In Progress...', 'Completed.',
                'Runtime Error'), 'created_backtest')
        backtest_id = _cloud_id(row.get('backtestId'))
        _require(backtest_id != MANUAL_BACKTEST_ID, 'created_backtest')
        return {'project_id': PROJECT_ID, 'compile_id': compile_id,
            'backtest_id': backtest_id, 'backtest_name': BACKTEST_NAME,
            'status': row['status'], 'projection_sha256': PROJECTION_SHA256}

    def read_status(self, launch_receipt, poll_index):
        """Only exact manual sample plus own A5; never filters unexpected runs."""
        _require(type(poll_index) is int and poll_index == 0, 'status_poll_index')
        _require(type(launch_receipt) is dict and set(launch_receipt) == {
            'project_id', 'compile_id', 'backtest_id', 'backtest_name', 'status', 'projection_sha256'}, 'launch_receipt')
        receipt = json.loads(_canonical(launch_receipt))
        _require(type(receipt['project_id']) is int and receipt['project_id'] == PROJECT_ID
            and receipt['projection_sha256'] == PROJECTION_SHA256 and receipt['backtest_name'] == BACKTEST_NAME
            and receipt['status'] in ('In Queue...', 'In Progress...', 'Completed.', 'Runtime Error'),
            'launch_receipt')
        _cloud_id(receipt['compile_id'])
        _cloud_id(receipt['backtest_id'])
        _require(receipt['backtest_id'] != MANUAL_BACKTEST_ID, 'launch_receipt')
        response = self._rpc('status-poll-000', 'backtests/list',
            {'projectId': PROJECT_ID, 'includeStatistics': False})
        rows = _backtest_rows(response, 2, 'status_inventory')
        manual = [row for row in rows if _manual_backtest(row)]
        own = [row for row in rows if row.get('backtestId') == receipt['backtest_id']
            and row.get('name') == BACKTEST_NAME
            and row.get('status') in ('In Queue...', 'In Progress...', 'Completed.', 'Runtime Error')]
        _require(len(manual) == len(own) == 1, 'backtest_status')
        return {**receipt, 'status': own[0]['status']}


# Preserve the caller's injected-policy interface without modifying old modules.
OwnerRecovery = PrivacyRecovery
