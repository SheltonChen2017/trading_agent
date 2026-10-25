"""Pure injected R298 A9 completion policy; no operational entrypoint.

A1-A8 remain spent. A separately frozen caller owns the A9 claim, response
evidence boundary, credentials, deadline, admission and actual-exit handling.
The exact A5 editing-environment label is retained, not renamed as an attempt.
Current access must still satisfy the unchanged owner/A5 whole-row pins; read
context, row counts and historical admission never replace that write gate.

Completion reads the full inventory before its first write and immediately
after every write. Each exact readback is the next prewrite observation with
no intervening request. This is not a continuous lease or atomic cloud view.
No target is written twice, including after ambiguous or refused dispatch.
"""
import json

from scripts import arv2_r298_access_recovery_remote as previous


post_mia, frozen, access = previous.post_mia, previous.frozen, previous.access
PROJECT_ID, PROJECT_NAME = previous.PROJECT_ID, previous.PROJECT_NAME
PROJECTION_SHA256 = previous.PROJECTION_SHA256
PROJECTION_CANDIDATE_ID = previous.PROJECTION_CANDIDATE_ID
SOURCE_NAMES, ORGANIZATION_SHA256 = previous.SOURCE_NAMES, previous.ORGANIZATION_SHA256
ATTEMPT = 9
BACKTEST_NAME = f'{PROJECT_NAME} A9 {PROJECTION_SHA256[:8]}'
CODE_SOURCE_ID = previous.CODE_SOURCE_ID
COLLABORATION_ENDPOINT, LOCK_ENDPOINT = previous.COLLABORATION_ENDPOINT, previous.LOCK_ENDPOINT
ENDPOINTS = previous.ENDPOINTS
MANUAL_BACKTEST_ID, MANUAL_BACKTEST_NAME = previous.MANUAL_BACKTEST_ID, previous.MANUAL_BACKTEST_NAME
RETAINED_SOURCE_NAMES = previous.RETAINED_SOURCE_NAMES
RecoveryError = previous.RecoveryError
_require, _canonical, _sha, _cloud_id = previous._require, previous._canonical, previous._sha, previous._cloud_id
_strict_canonical = previous._strict_canonical
_backtest_rows, _manual_backtest = previous._backtest_rows, previous._manual_backtest
code_running_observation = previous.code_running_observation
_validate_code_running = previous._validate_code_running
OWNERSHIP_PREDICATES = dict(previous.OWNERSHIP_PREDICATES)
FINITE_CODES = previous.FINITE_CODES | frozenset(('completion_used',
    'completion_stage', 'write_target_used', 'write_binding'))


def finite_error(error):
    code = 'unknown'
    if type(error) is RecoveryError:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE_CODES:
            code = args[0]
    return {'helper_code': code, 'predicate': OWNERSHIP_PREDICATES.get(code)}


class HandoffRecovery(previous.AccessRecovery):
    """Serialized injected seams only; no authorization from construction."""

    def __init__(self, projection, organization_sha256, request, journal, observe):
        super().__init__(projection, organization_sha256, request, journal, observe)
        self._inspection_snapshot = None
        self._completion_used = False
        self._write_ready = None
        self._written_targets = set()

    def inspect(self):
        inventory = super().inspect()
        self._inspection_snapshot = _strict_canonical(inventory)
        return inventory

    def _rpc(self, marker, endpoint, payload):
        _require(type(marker) is str and type(endpoint) is str, 'duplicate_or_endpoint')
        if endpoint in ('files/create', 'files/update'):
            _require(type(payload) is dict, 'write_binding')
            payload = json.loads(_strict_canonical(payload))
            _require(type(payload.get('name')) is str
                and payload['name'] in SOURCE_NAMES and type(payload.get('content')) is str
                and payload['content'].isascii()
                and payload['content'].encode('ascii') == self._sources[payload['name']], 'write_binding')
            name = payload['name']
            _require(name not in self._written_targets, 'write_target_used')
            _require(self._write_ready == (marker, endpoint, name), 'completion_stage')
            # Consume before intent/delegate: even journal/transport ambiguity
            # can never allow this target to be written again by this instance.
            self._written_targets.add(name)
            self._write_ready = None
        return super()._rpc(marker, endpoint, payload)

    def complete(self, original_inventory):
        """Complete only missing/permitted placeholders, then exact readback."""
        _require(not self._completion_used, 'completion_used')
        self._completion_used = True
        _require(self._inspection_snapshot is not None and self._lock_acquired,
            'completion_stage')
        original = _strict_canonical(original_inventory)
        _require(original == self._inspection_snapshot, 'inventory_changed')
        self._owned('complete')
        current = self._files('complete-before')
        _require(_strict_canonical(current) == original, 'inventory_changed')
        observed = {row['name']: row for row in current['files']}
        changes = [(index, name, raw) for index, (name, raw) in
            enumerate(sorted(self._sources.items())) if observed.get(name) != {
                'name': name, 'byte_count': len(raw), 'sha256': _sha(raw)}]
        if not changes:
            final = self._files('complete-final', complete=True)
            _require(_strict_canonical(final) == _strict_canonical(current), 'completion_readback')
            return final
        for position, (index, name, raw) in enumerate(changes):
            endpoint = 'files/update' if name in observed else 'files/create'
            marker = f'complete-write-{index:02d}'
            self._write_ready = (marker, endpoint, name)
            try:
                self._rpc(marker, endpoint,
                    {'projectId': PROJECT_ID, 'name': name, 'content': raw.decode('ascii')})
            finally:
                self._write_ready = None
            observed[name] = {'name': name, 'byte_count': len(raw), 'sha256': _sha(raw)}
            expected = {'project_id': PROJECT_ID, 'projection_sha256': PROJECTION_SHA256,
                'files': sorted(observed.values(), key=lambda row: row['name'])}
            # No other request separates this exact whole-inventory readback
            # from the next write. Last readback also requires all eleven files.
            current = self._files(f'complete-after-{index:02d}',
                complete=position == len(changes) - 1)
            _require(_strict_canonical(current) == _strict_canonical(expected), 'completion_readback')
        return current

    def launch_once(self, compile_id):
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
        """Only the exact manual sample plus own A9, one fixed status poll."""
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


OwnerRecovery = HandoffRecovery
