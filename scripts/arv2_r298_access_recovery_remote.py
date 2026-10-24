"""Pure separately authorized R298 A6 access-representation recovery helper.

A1-A5 remain spent. The new caller owns the single A6 claim, reconciliation,
deadline, source/admission bindings and actual-exit handling. This module has
injected request/journal seams only, not operational or retry authority.

The exact A5 codeSourceId is deliberately retained as the editing environment
label. It is NOT the attempt identity: A6 has a separate name, caller and claim.
Current access checks use the separately pinned owner/A5-row policy; old Mia
is no longer an admissible extra. Whole-row drift refuses without pin refresh.
No access check proves privacy, a synthetic account, a lease or strategy value.
Frozen projection, source completion, manual history and compile rules remain.
"""
import json
import re

from scripts import arv2_r298_privacy_recovery_remote as previous
from scripts import arv2_r298_collaborator_access as access


post_mia = previous.post_mia
frozen = previous.frozen
PROJECT_ID = frozen.PROJECT_ID
PROJECT_NAME = frozen.PROJECT_NAME
PROJECTION_SHA256 = frozen.PROJECTION_SHA256
PROJECTION_CANDIDATE_ID = frozen.PROJECTION_CANDIDATE_ID
SOURCE_NAMES = frozen.SOURCE_NAMES
ORGANIZATION_SHA256 = frozen.ORGANIZATION_SHA256
BACKTEST_NAME = f'{PROJECT_NAME} A6 {PROJECTION_SHA256[:8]}'
ATTEMPT = 6
CODE_SOURCE_ID = 'Codex ARV2 R298 A5 20261024'
COLLABORATION_ENDPOINT = 'projects/collaboration/read'
LOCK_ENDPOINT = 'projects/collaboration/lock/acquire'
ENDPOINTS = frozen.ENDPOINTS | {COLLABORATION_ENDPOINT, LOCK_ENDPOINT}
MANUAL_BACKTEST_ID = 'bbd2202cc3000e8b1c14751bf088dd16'
MANUAL_BACKTEST_NAME = 'Casual Yellow Kangaroo'
# Historical reference only; never an accepted extra in this A6 policy.
MIA_ROW_SHA256 = '6e3fb9db0a3303a202fdebd062e91cd8a974ac564cab784dbccedc361477f44f'
RETAINED_SOURCE_NAMES = frozenset(('accepted_risk_order_level_core.py',
    'accepted_risk_order_level_forced_exit.py'))
RecoveryError = frozen.RecoveryError
_require, _canonical, _sha, _cloud_id = frozen._require, frozen._canonical, frozen._sha, frozen._cloud_id
code_running_observation = previous.code_running_observation
_validate_code_running = previous._validate_code_running

OWNERSHIP_PREDICATES = {**previous.OWNERSHIP_PREDICATES,
    **{'access_' + code: code for code in access.FINITE_CODES}}
FINITE_CODES = previous.FINITE_CODES | frozenset('access_' + code for code in access.FINITE_CODES)
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


def _strict_canonical(value):
    try:
        return access._canonical(value)
    except access.AccessRefused as error:
        code = access.finite_error(error)['code']
        _require(code in access.FINITE_CODES, 'response_shape')
        raise RecoveryError('access_' + code) from None


class AccessRecovery(previous.PrivacyRecovery):
    """Injected seams; owner-freed context is an external frozen prerequisite."""

    def _rpc(self, marker, endpoint, payload):
        _require(type(marker) is str and re.fullmatch(r'[a-z0-9-]{1,96}', marker)
            and type(endpoint) is str and endpoint in ENDPOINTS and marker not in self._used,
            'duplicate_or_endpoint')
        _require(type(payload) is dict and type(payload.get('projectId')) is int
            and payload['projectId'] == PROJECT_ID, 'request_project')
        payload = json.loads(_strict_canonical(payload))
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
        raw = _strict_canonical(payload)
        self._event(marker, 'intent', endpoint, _sha(raw))
        try:
            response = self._request(endpoint, json.loads(raw))
        except Exception:
            raise RecoveryError('request_ambiguous') from None
        _require(type(response) is dict, 'response_shape')
        raw = _strict_canonical(response)
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
        _require(self._organization_sha256 == access.ORGANIZATION_SHA256, 'organization_pin')
        project = self._rpc(prefix + '-project', 'projects/read', {'projectId': PROJECT_ID})
        dedicated = self._rpc(prefix + '-collaborators', COLLABORATION_ENDPOINT, {'projectId': PROJECT_ID})
        try:
            access.verify_access(project, dedicated)
        except access.AccessRefused as error:
            code = access.finite_error(error)['code']
            _require(code in access.FINITE_CODES, 'response_shape')
            raise RecoveryError('access_' + code) from None
        history = self._rpc(prefix + '-backtests', 'backtests/list',
            {'projectId': PROJECT_ID, 'includeStatistics': False})
        previous_rows = _backtest_rows(history, 1, 'prior_backtests')
        _require(_manual_backtest(previous_rows[0]), 'prior_backtests')

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
        """Only exact manual sample plus own A6; never filters unexpected runs."""
        _require(type(poll_index) is int and poll_index == 0, 'status_poll_index')
        _require(type(launch_receipt) is dict and set(launch_receipt) == {
            'project_id', 'compile_id', 'backtest_id', 'backtest_name', 'status', 'projection_sha256'}, 'launch_receipt')
        receipt = json.loads(_strict_canonical(launch_receipt))
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
OwnerRecovery = AccessRecovery
