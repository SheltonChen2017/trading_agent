"""Injected read-only reconciliation of one already failed A19 job.

No lock, write, creation, capacity, compile or launch operation is exposed.
Only an exact observed busy boolean may wait; every other current access gate
still refuses. The caller owns its new claim, source freeze, credentials,
deadline, actual exit and optional native private join. All old claims stay spent.
"""
from __future__ import annotations

import json
import math
import re
import time

from scripts import arv2_r298_reference_identity_remote as job_source
from scripts import arv2_r298_mia_access_representation as access
from scripts import arv2_newrule_reference_identity_response as selector


SCHEMA = 'arv2-r298-a19-error-reconciliation-v1'
PROJECT_ID = 38364439
BACKTEST_ID = 'b850c8193949015bc59c41d0e1434229'
COMPILE_ID = '95f2715b63dde55edbac79da7e88d3aa-f8d3daabe131b918cd28aeaab059b9b9'
BACKTEST_NAME = 'ARV2 R298 REFERENCE IDENTITY DIAGNOSTIC R323 A19'
PROJECTION_SHA256 = job_source.PROJECTION_SHA256
PROFILE_SHA256 = job_source.PROFILE_SHA256
SOURCE_MANIFEST_SHA256 = job_source.SOURCE_MANIFEST_SHA256
CODE_SOURCE_ID = job_source.CODE_SOURCE_ID
IDLE_POLLS, IDLE_INTERVAL = 3, 60
MAX_RESPONSE_BYTES = 1024 * 1024
PAYLOAD_KEYS = {'projects/read': {'projectId'},
    'projects/collaboration/read': {'projectId'},
    'backtests/list': {'projectId', 'includeStatistics'},
    'files/read': {'projectId', 'codeSourceId'},
    'compile/read': {'projectId', 'compileId'},
    'backtests/read': {'projectId', 'backtestId'}}
FALSE_FLAGS = {**job_source.FALSE_FLAGS, 'strategy_result_accepted': False,
    'family_comparable': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False}
FINITE = frozenset(('binding', 'callbacks', 'clock', 'wait', 'idle_budget', 'idle_shape',
    'not_ready', 'read_once', 'marker', 'payload', 'endpoint', 'journal', 'response',
    'response_bound', 'history', 'files', 'compile', 'terminal', 'receipt', 'source_pin'))
canonical, sha = job_source.canonical, job_source.sha


class Refused(ValueError):
    """Closed predicate, never a provider message or private source row."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    return 'unknown'


def _copy(value):
    return json.loads(canonical(value))


def profile_record():
    return {'schema': SCHEMA, **_binding(), 'idle_observations': IDLE_POLLS,
        'idle_interval': IDLE_INTERVAL, 'wait_only_exact_code_running_true': True,
        'dedicated_non_idle_precheck': True, 'source_files': 11,
        'source_history_compile_checks': ['before_error_read', 'after_error_read'],
        'error_reads': 1, 'wire_bound_unchanged': 16 * 1024 * 1024,
        'selected_bound': selector.MAX_SELECTED_BYTES, 'complete_body_authenticated': False,
        'old_a19_control_read': False, 'new_job_created': False,
        'source_mutations': 0, 'lock_changes': 0, 'capacity_requests': 0,
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}


def _binding():
    return {'schema': SCHEMA, 'project_id': PROJECT_ID,
        'projection_sha256': PROJECTION_SHA256, 'profile_sha256': PROFILE_SHA256,
        'source_manifest_sha256': SOURCE_MANIFEST_SHA256,
        'compile_id': COMPILE_ID, 'backtest_id': BACKTEST_ID, 'backtest_name': BACKTEST_NAME}


def validate_terminal_receipt(value):
    job_source.validate_terminal_receipt(value)
    expected = {**job_source._binding(), 'compile_id': COMPILE_ID,
        'backtest_id': BACKTEST_ID, 'backtest_name': BACKTEST_NAME, 'status': 'Runtime Error'}
    require(all(type(value[key]) is type(item) and value[key] == item
        for key, item in expected.items()), 'terminal')
    return _copy(value)


def validate_receipt(value):
    expected = _binding()
    extras = {'terminal', 'fixed_source_checks_before', 'fixed_source_checks_after',
        'access_observation_index', 'error_reads', 'diagnostic_only', 'result_cell', *FALSE_FLAGS}
    require(type(value) is dict and all(type(key) is str for key in value)
        and set(value) == set(expected) | extras
        and all(type(value[key]) is type(item) and value[key] == item for key, item in expected.items())
        and value['fixed_source_checks_before'] is True and value['fixed_source_checks_after'] is True
        and type(value['access_observation_index']) is int and 0 <= value['access_observation_index'] < IDLE_POLLS
        and type(value['error_reads']) is int and value['error_reads'] == 1
        and value['diagnostic_only'] is True and type(value['result_cell']) is int and value['result_cell'] == 0
        and all(value[key] is False for key in FALSE_FLAGS), 'receipt')
    validate_terminal_receipt(value['terminal'])
    return _copy(value)


def _dedicated_precheck(project_response, dedicated_response):
    """Check predicates ordered after idle in the frozen verifier, unmodified.

    An exact busy flag is never rewritten or converted to a real permit. This
    precheck merely prevents busy+unauthorized metadata from getting a wait.
    The complete unchanged access verifier still processes both responses.
    """
    packet = access.previous._response(project_response)
    dedicated = access.previous._response(dedicated_response)
    projects = packet.get('projects')
    access.require(type(projects) is list and len(projects) == 1 and type(projects[0]) is dict, 'project_shape')
    project = projects[0]
    owner_id = project.get('ownerId')
    access.require(type(owner_id) is int and 0 < owner_id < 2**63, 'owner_id')
    rows = dedicated.get('collaborators')
    access.require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'dedicated_owner')
    owner = rows[0]
    access.require(owner.get('owner') is True and type(owner.get('uid')) is int and owner['uid'] == owner_id
        and type(owner.get('permission')) is str and owner['permission'] == 'write'
        and owner.get('liveControl') is True, 'dedicated_owner')
    access.require(type(dedicated.get('userPermissions')) is str and dedicated['userPermissions'] == 'write'
        and dedicated.get('userLiveControl') is True, 'dedicated_permissions')
    access.require(access.sha(access.canonical(owner)) == access.OWNER_ROW_SHA256, 'owner_row_pin')
    return packet, dedicated, project


class ErrorReconciliation:
    """Pure injected protocol; a matching object itself grants no authority."""

    def __init__(self, record_bytes, source_pairs, *, request, journal, clock=time.monotonic):
        job_source.projection.validate_public_projection(record_bytes, source_pairs,
            expected_projection_sha256=PROJECTION_SHA256, expected_profile_sha256=PROFILE_SHA256)
        require(all(callable(item) for item in (request, journal, clock)), 'callbacks')
        self._sources = dict(source_pairs)
        manifest = job_source.QuoteDiagnostic._manifest(self._sources, PROJECTION_SHA256)
        require(sha(canonical(manifest)) == SOURCE_MANIFEST_SHA256, 'source_pin')
        self._request, self._journal, self._clock = request, journal, clock
        self._used, self._permit = set(), None
        self._polls, self._last_poll, self._last_clock = 0, None, None
        self._ready, self._read_spent, self._detail_dispatched, self._terminal = False, False, False, None

    @property
    def terminal_receipt(self):
        return None if self._terminal is None else _copy(self._terminal)

    def _event(self, marker, value):
        require(self._journal(marker, _copy(value)) is None, 'journal')

    def _now(self):
        value = self._clock()
        require(type(value) in (int, float) and 0 <= value <= 1e100 and math.isfinite(value)
            and (self._last_clock is None or value >= self._last_clock), 'clock')
        self._last_clock = value
        return value

    def _call(self, marker, endpoint, payload):
        require(type(marker) is str and re.fullmatch('[a-z0-9-]{1,80}', marker)
            and marker not in self._used, 'marker')
        require(type(endpoint) is str and endpoint in PAYLOAD_KEYS, 'endpoint')
        require(type(payload) is dict and set(payload) == PAYLOAD_KEYS[endpoint]
            and type(payload.get('projectId')) is int and payload['projectId'] == PROJECT_ID, 'payload')
        if 'codeSourceId' in payload: require(payload['codeSourceId'] == CODE_SOURCE_ID, 'payload')
        if 'includeStatistics' in payload: require(payload['includeStatistics'] is False, 'payload')
        if 'compileId' in payload: require(payload['compileId'] == COMPILE_ID, 'payload')
        if 'backtestId' in payload:
            require(self._read_spent and not self._detail_dispatched and marker == 'error-detail'
                and self._permit == (marker, endpoint, BACKTEST_ID)
                and payload['backtestId'] == BACKTEST_ID, 'read_once')
            self._permit = None
            self._detail_dispatched = True
        self._used.add(marker)
        self._event(marker, {'event': 'intent', 'endpoint': endpoint, 'sha256': sha(canonical(payload))})
        value = self._request(endpoint, _copy(payload))
        require(type(value) is dict, 'response')
        if endpoint == 'backtests/read':
            selector.validate_selected(value, project_id=PROJECT_ID, backtest_id=BACKTEST_ID,
                backtest_name=BACKTEST_NAME, compile_id=COMPILE_ID, mode='error')
        raw = access.canonical(value)
        require(0 < len(raw) <= MAX_RESPONSE_BYTES, 'response_bound')
        value = json.loads(raw)
        require(value.get('success') is True and ('errors' not in value
            or (type(value['errors']) is list and value['errors'] == [])), 'response')
        self._event(marker, {'event': 'observed', 'endpoint': endpoint, 'sha256': sha(raw)})
        return value

    def poll_idle(self, index):
        require(not self._ready and not self._read_spent and type(index) is int
            and index == self._polls and index < IDLE_POLLS, 'idle_budget')
        now = self._now()
        require(self._last_poll is None or now - self._last_poll >= IDLE_INTERVAL, 'wait')
        self._polls += 1
        self._last_poll = now
        prefix = f'idle-{index:02d}'
        project = self._call(prefix + '-project', 'projects/read', {'projectId': PROJECT_ID})
        dedicated = self._call(prefix + '-collaborators', 'projects/collaboration/read', {'projectId': PROJECT_ID})
        project, dedicated, row = _dedicated_precheck(project, dedicated)
        try:
            checked = access.verify_access(project, dedicated)
        except access.AccessRefused as error:
            if access.finite_error(error)['code'] != 'idle':
                raise
            require(type(row.get('codeRunning')) is bool and row['codeRunning'] is True, 'idle_shape')
            result = {'state': 'wait', 'observation_index': index, 'code_running': True,
                'all_non_idle_predicates_checked': True}
            self._event(prefix + '-access', {'event': 'idle', 'observation': result})
            return result
        self._ready = True
        result = {'state': 'ready', 'observation_index': index, 'code_running': False, 'access': checked}
        self._event(prefix + '-access', {'event': 'idle', 'observation': result})
        return result

    def _history(self, prefix):
        value = self._call(prefix + '-history', 'backtests/list', {'projectId': PROJECT_ID, 'includeStatistics': False})
        rows = job_source.previous.ready.predecessor._backtest_rows(value, 6, 'prior_backtests')
        expected = ((job_source.previous.ready.predecessor.MANUAL_BACKTEST_ID,
            job_source.previous.ready.predecessor.MANUAL_BACKTEST_NAME, 'Completed.', None),
            (job_source.A12_ID, job_source.previous.BACKTEST_NAME, 'Runtime Error', job_source.previous.COMPILE_ID),
            (job_source.A14_ID, job_source.A14_NAME, 'Runtime Error', job_source.A14_COMPILE_ID),
            (job_source.A16_ID, job_source.A16_NAME, 'Runtime Error', job_source.A16_COMPILE_ID),
            (job_source.A18_ID, job_source.A18_NAME, 'Runtime Error', job_source.A18_COMPILE_ID),
            (BACKTEST_ID, BACKTEST_NAME, 'Runtime Error', COMPILE_ID))
        seen = set()
        for identity, name, status, compile_id in expected:
            matches = [row for row in rows if type(row.get('backtestId')) is str and row['backtestId'] == identity
                and type(row.get('name')) is str and row['name'] == name
                and type(row.get('status')) is str and row['status'] == status
                and (compile_id is None or 'compileId' not in row
                    or (type(row['compileId']) is str and row['compileId'] == compile_id))]
            require(len(matches) == 1 and identity not in seen, 'history')
            seen.add(identity)

    def _access(self, prefix):
        project = self._call(prefix + '-project', 'projects/read', {'projectId': PROJECT_ID})
        dedicated = self._call(prefix + '-collaborators', 'projects/collaboration/read', {'projectId': PROJECT_ID})
        project, dedicated, _ = _dedicated_precheck(project, dedicated)
        checked = access.verify_access(project, dedicated)
        self._event(prefix + '-access', {'event': 'access', 'observation': checked})

    def _files(self, prefix):
        rows = self._call(prefix + '-files', 'files/read', {'projectId': PROJECT_ID, 'codeSourceId': CODE_SOURCE_ID}).get('files')
        require(type(rows) is list and len(rows) == 11, 'files')
        files = {}
        for row in rows:
            require(type(row) is dict and type(row.get('projectId')) is int and row['projectId'] == PROJECT_ID
                and type(row.get('name')) is str and row['name'] in self._sources and row['name'] not in files
                and type(row.get('content')) is str and len(row['content']) <= 64000
                and row['content'].isascii(), 'files')
            files[row['name']] = row['content'].encode('ascii')
        require(files == self._sources, 'files')

    def _compile(self, prefix):
        value = self._call(prefix + '-compile', 'compile/read', {'projectId': PROJECT_ID, 'compileId': COMPILE_ID})
        require(('projectId' not in value or (type(value['projectId']) is int and value['projectId'] == PROJECT_ID))
            and type(value.get('compileId')) is str and value['compileId'] == COMPILE_ID
            and type(value.get('state')) is str and value['state'] == 'BuildSuccess', 'compile')

    def _fixed(self, prefix):
        self._access(prefix)
        self._history(prefix)
        self._files(prefix)
        self._compile(prefix)

    def read_once(self):
        require(self._ready and not self._read_spent, 'read_once')
        self._read_spent = True
        self._fixed('before')
        self._permit = ('error-detail', 'backtests/read', BACKTEST_ID)
        try:
            value = self._call('error-detail', 'backtests/read', {'projectId': PROJECT_ID, 'backtestId': BACKTEST_ID})
        finally:
            self._permit = None
        self._terminal = validate_terminal_receipt({**job_source._binding(),
            'compile_id': COMPILE_ID, 'backtest_id': BACKTEST_ID, 'backtest_name': BACKTEST_NAME,
            'status': 'Runtime Error', 'failure_evidence': value['backtest']['finite_projected_error']})
        self._event('retained-error', {'event': 'terminal_receipt', 'receipt': self._terminal})
        self._fixed('after')
        result = {**_binding(), 'terminal': self._terminal, 'fixed_source_checks_before': True,
            'fixed_source_checks_after': True, 'access_observation_index': self._polls - 1,
            'error_reads': 1, 'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}
        checked = validate_receipt(result)
        self._event('reconciliation', {'event': 'receipt', 'receipt': checked})
        return checked
