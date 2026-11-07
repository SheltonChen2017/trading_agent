"""Injected, once-only QC protocol for one R343 legacy-six candidate.

This module has no client, credentials, filesystem, or command-line entry point.
A separately frozen caller authenticates the private preparation DATA, owns the
exclusive attempt claim, source inventory and native sandbox, and supplies the
bounded request and durable journal callbacks. These callbacks are interfaces,
not authority or proof of process isolation. No old operational caller is used.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time


SCHEMA = 'arv2-r345-legacy-six-qc-v1'
# Literal provenance: newrule_comparison_submission.REFERENCE_PROJECT and
# eight_universe_execution_stress_candidates.json's R281 project name.
REFERENCE_PROJECT = 37165262
REFERENCE_NAME = 'ARV2 EIGHT EXECUTION STRESS R281 2021 2025'
# Literal provenance: arv2_r298_collaborator_access.ORGANIZATION_SHA256.
ORGANIZATION_SHA256 = 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
PACKAGE_SHA256 = '411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad'
EPOCH = 'R343-legacy-six-QCOM-restored-through-2026Oct13-v1'
AR_PERCENTS = (80, 100, 120, 140, 160, 180, 200)
MAX_RESPONSE = 2 * 1024 * 1024
MAX_DISPATCHES = 1200
COMPILE_POLLS, COMPILE_INTERVAL = 30, 2
CAPACITY_POLLS, CAPACITY_INTERVAL = 3, 60
STATUS_POLLS, STATUS_INTERVAL = 240, 60
PENDING = frozenset(('In Queue...', 'In Progress...'))
TERMINAL = frozenset(('Completed.', 'Runtime Error'))
LEGACY_STATISTICS = ('ARV2_SIX_GATE_ORDER_META', 'ARV2_SIX_GATE_ORDER_AGGREGATES',
                     'ARV2_SIX_GATE_ORDER_DIAGNOSTICS')
PERIOD_STATISTIC = 'ARV2_R343_LEGACY_SIX_PERIODS'
PAYLOAD_KEYS = {
    'authenticate': set(), 'projects/read': {'projectId'},
    'projects/create': {'name', 'language', 'organizationId'},
    'projects/collaboration/read': {'projectId'},
    'projects/collaboration/lock/acquire': {'projectId', 'codeSourceId'},
    'projects/nodes/read': {'projectId'},
    'files/read': {'projectId', 'codeSourceId'},
    'files/create': {'projectId', 'name', 'content', 'codeSourceId'},
    'files/update': {'projectId', 'name', 'content', 'codeSourceId'},
    'files/delete': {'projectId', 'name', 'codeSourceId'},
    'compile/create': {'projectId'}, 'compile/read': {'projectId', 'compileId'},
    'backtests/list': {'projectId', 'includeStatistics'},
    'backtests/create': {'projectId', 'compileId', 'backtestName'},
    'backtests/read': {'projectId', 'backtestId'},
}
FALSE_FLAGS = {'point_in_time_proven': False, 'formal_identity_admitted': False,
               'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('arguments', 'shape', 'bound', 'response', 'request', 'request_ambiguous',
    'journal', 'clock', 'scope', 'owner', 'organization', 'private', 'idle', 'collaborators',
    'libraries', 'live', 'capacity', 'capacity_budget', 'wait', 'source', 'source_inventory',
    'source_changed', 'state', 'project_name', 'project_identity', 'lock', 'history',
    'compile', 'compile_budget', 'compile_failed', 'launch_identity', 'status',
    'status_budget', 'result', 'not_completed', 'statistics', 'unknown'))


class Refused(ValueError):
    """A finite refusal category, never a raw provider message."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    pending, count = [(value, 0)], 0
    while pending:
        item, depth = pending.pop(); count += 1
        require(depth <= 40 and count <= 100000, 'bound')
        kind = type(item)
        if kind is dict:
            require(all(type(key) is str for key in item), 'shape')
            pending.extend((child, depth + 1) for child in item.values())
        elif kind is list:
            pending.extend((child, depth + 1) for child in item)
        elif kind is float:
            require(math.isfinite(item), 'shape')
        else:
            require(kind in (str, int, bool, type(None)), 'shape')
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                          allow_nan=False).encode('ascii')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Refused('shape') from None


def sha(raw):
    require(type(raw) is bytes, 'shape')
    return hashlib.sha256(raw).hexdigest()


def _copy(value):
    return json.loads(canonical(value))


def _id(value):
    require(type(value) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', value), 'shape')
    return value


def _number(value):
    require(type(value) is int and 0 < value < 2**63, 'shape')
    return value


def _organization(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{32}', value)
            and sha(value.encode('ascii')) == ORGANIZATION_SHA256, 'organization')
    return value


def _empty_errors(response):
    require(type(response) is dict and response.get('success') is True
            and ('errors' not in response or (type(response['errors']) is list
                                            and not response['errors'])), 'response')


def _event(journal, marker, value):
    require(callable(journal) and journal(marker, _copy(value)) is None, 'journal')


def _read_call(request, journal, marker, endpoint, payload):
    require(callable(request), 'arguments')
    _event(journal, marker + '-intent', {'endpoint': endpoint, 'payload_sha256': sha(canonical(payload))})
    try:
        response = request(endpoint, _copy(payload))
    except Exception:
        raise Refused('request_ambiguous') from None
    raw = canonical(response)
    require(0 < len(raw) <= MAX_RESPONSE, 'bound')
    _event(journal, marker + '-observed', {'endpoint': endpoint, 'response_sha256': sha(raw),
                                         'response_bytes': len(raw)})
    _empty_errors(response)
    return _copy(response)


def capacity(response):
    """Pure current node census, not a lease or permission to cancel a job."""
    _empty_errors(response)
    nodes, auto = response.get('nodes'), response.get('autoSelectNode')
    require(type(nodes) is dict and type(auto) is bool, 'capacity')
    rows = nodes.get('backtest')
    require(type(rows) is list and len(rows) <= 64 and all(type(row) is dict
        and type(row.get('busy')) is bool and type(row.get('active')) is bool for row in rows), 'capacity')
    return {'node_count': len(rows), 'busy_count': sum(row['busy'] for row in rows),
        'selected_count': sum(row['active'] for row in rows), 'auto_select': auto,
        'available_count': sum(not row['busy'] and (auto or row['active']) for row in rows)}


def _project(packet, project_id, name, organization, user_id, *, idle, own_code_source=None):
    _empty_errors(packet)
    rows = packet.get('projects')
    require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'project_identity')
    row = rows[0]
    require(type(row.get('projectId')) is int and row['projectId'] == project_id
            and row.get('name') == name and row.get('language') == 'Py', 'project_identity')
    require(row.get('organizationId') == organization, 'organization')
    require(row.get('owner') is True and type(row.get('ownerId')) is int
            and row['ownerId'] == user_id, 'owner')
    if idle:
        require(row.get('public') is False, 'private')
        require(row.get('codeRunning') is False, 'idle')
        require('lastLiveDeployment' in row and row['lastLiveDeployment'] in (None, '')
            and type(row.get('leanEnvironment')) is int and row['leanEnvironment'] >= 0, 'live')
        require(row.get('isLibrary') is False and type(row.get('libraries')) is list
                and not row['libraries'], 'libraries')
    else:
        # A read of a fixed reference's organization/capacity does not mutate
        # that reference. Missing public is unknown, never private evidence.
        require('public' not in row or row['public'] is not True, 'private')
        require(type(row.get('codeRunning')) is bool, 'idle')
    for field in ('libraries', 'libraryIds'):
        if field in row:
            require(type(row[field]) is list and not row[field], 'libraries')
    for field in ('liveMode', 'liveRunning', 'live'):
        if field in row:
            require(row[field] is False, 'live')
    if 'liveResults' in row:
        require(type(row['liveResults']) is list and not row['liveResults'], 'live')
    collaborators = row.get('collaborators')
    require(type(collaborators) is list and 1 <= len(collaborators) <= 2
            and all(type(value) is dict for value in collaborators), 'collaborators')
    owners = [value for value in collaborators if value.get('owner') is True]
    require(len(owners) == 1 and type(owners[0].get('uid')) is int
            and owners[0]['uid'] == user_id, 'collaborators')
    for extra in collaborators:
        if extra is owners[0]:
            continue
        require(own_code_source is not None and extra.get('owner') is False
            and 'uid' in extra and extra['uid'] is None
            and extra.get('name') == extra.get('publicId') == own_code_source
            and extra.get('permission') == 'write' and extra.get('liveControl') is True,
            'collaborators')
    return row, owners[0]


def _dedicated(packet, project_id, user_id, general_owner):
    _empty_errors(packet)
    require('projectId' not in packet or (type(packet['projectId']) is int
            and packet['projectId'] == project_id), 'scope')
    rows = packet.get('collaborators')
    require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'collaborators')
    owner = rows[0]
    require(owner.get('owner') is True and type(owner.get('uid')) is int and owner['uid'] == user_id
        and owner.get('permission') == 'write' and owner.get('liveControl') is True
        and canonical(owner) == canonical(general_owner)
        and packet.get('userPermissions') == 'write' and packet.get('userLiveControl') is True,
        'collaborators')
    return sha(canonical(owner))


def access_capacity(request, *, user_id, journal):
    """Fixed reference, read-only. Never claims an exclusive resource lease.

    The returned organization ID is private orchestration data. A public caller
    must retain only ``public``; it must not print the entire return value.
    """
    _number(user_id)
    _read_call(request, journal, 'reference-auth', 'authenticate', {})
    packet = _read_call(request, journal, 'reference-project', 'projects/read', {'projectId': REFERENCE_PROJECT})
    rows = packet.get('projects')
    require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'project_identity')
    organization = _organization(rows[0].get('organizationId'))
    row, owner = _project(packet, REFERENCE_PROJECT, REFERENCE_NAME, organization, user_id, idle=False)
    dedicated = _read_call(request, journal, 'reference-collaborators', 'projects/collaboration/read',
                           {'projectId': REFERENCE_PROJECT})
    owner_pin = _dedicated(dedicated, REFERENCE_PROJECT, user_id, owner)
    observed = capacity(_read_call(request, journal, 'reference-capacity', 'projects/nodes/read',
                                  {'projectId': REFERENCE_PROJECT}))
    return {'organization_id': organization, 'public': {'schema': SCHEMA,
        'reference_project_id': REFERENCE_PROJECT, 'organization_sha256': ORGANIZATION_SHA256,
        'owner_row_sha256': owner_pin, 'reference_code_running': row['codeRunning'],
        'reference_privacy': 'explicit_private' if row.get('public') is False else 'unproven',
        'capacity': observed, **FALSE_FLAGS}}


def _cell(value):
    keys = {'ar_percent', 'candidate_id', 'profile_pin', 'sources', 'original_profile_sha256',
            'profile', 'source_pairs'}
    require(type(value) is dict and set(value) == keys, 'source')
    percent = value['ar_percent']
    require(type(percent) is int and percent in AR_PERCENTS
            and value['candidate_id'] == f'R343-AR{percent:03d}', 'source')
    require(type(value['original_profile_sha256']) is str
            and re.fullmatch('[0-9a-f]{64}', value['original_profile_sha256']), 'source')
    require(type(value['profile']) is dict and value['profile'].get('candidate_id') == value['candidate_id']
            and value['profile'].get('research_epoch_id') == EPOCH
            and value['profile'].get('source_package_sha256') == PACKAGE_SHA256, 'source')
    raw = canonical(value['profile'])
    require(value['profile_pin'] == {'byte_count': len(raw), 'sha256': sha(raw)}, 'source')
    require(type(value['sources']) is list and type(value['source_pairs']) is list
            and len(value['sources']) == len(value['source_pairs']) == 18, 'source')
    names, result = [], {}
    for row, pair in zip(value['sources'], value['source_pairs'], strict=True):
        require(type(row) is dict and set(row) == {'project_path', 'byte_count', 'sha256'}
            and type(pair) is list and len(pair) == 2 and pair[0] == row['project_path']
            and type(pair[0]) is str and re.fullmatch('[A-Za-z][A-Za-z0-9_]*[.]py', pair[0])
            and type(pair[1]) is str and pair[1].isascii(), 'source')
        name, text = pair
        require(name not in result and type(row['byte_count']) is int and 0 < len(text) <= 64000
            and row['byte_count'] == len(text) and sha(text.encode('ascii')) == row['sha256'], 'source')
        try:
            compile(text, name, 'exec')
        except (SyntaxError, ValueError, TypeError):
            raise Refused('source') from None
        names.append(name); result[name] = text
    require(names == sorted(names) and 'main.py' in result and 'legacy_six_october_reporting.py' in result
            and sum(len(text) for text in result.values()) + 32768 <= 448 * 1024, 'source')
    return _copy(value), result


def profile_record():
    return {'schema': SCHEMA, 'reference_project_id': REFERENCE_PROJECT,
        'reference_name': REFERENCE_NAME, 'organization_sha256': ORGANIZATION_SHA256,
        'candidate_ids': [f'R343-AR{p:03d}' for p in AR_PERCENTS], 'pilot': 'R343-AR100',
        'source_files': 18, 'main_uploaded_last': True, 'maximum_attempts_per_candidate': 3,
        'compile_polls': COMPILE_POLLS, 'compile_interval': COMPILE_INTERVAL,
        'capacity_polls': CAPACITY_POLLS, 'capacity_interval': CAPACITY_INTERVAL,
        'status_polls': STATUS_POLLS, 'status_interval': STATUS_INTERVAL,
        'result_reads': 1, 'max_response_bytes': MAX_RESPONSE,
        'statistic_names': [*LEGACY_STATISTICS, PERIOD_STATISTIC],
        'privacy_requires_explicit_false': True, 'input_publication_external': True,
        'claims_native_isolation_and_actual_exits_external': True, **FALSE_FLAGS}


class LegacySixQc:
    """One candidate's fresh own project and at most one backtest creation.

    No retry exists here. The caller must establish the numbered attempt and
    previous failed-attempt accounting before construction. This object never
    repairs an old project, silently substitutes source, or changes economics.
    """
    def __init__(self, cell, *, organization_id, user_id, attempt, request, journal,
                 clock=time.monotonic):
        self.cell, self.sources = _cell(cell)
        self.organization = _organization(organization_id)
        self.user_id = _number(user_id)
        require(type(attempt) is int and 1 <= attempt <= 3
            and all(callable(value) for value in (request, journal, clock)), 'arguments')
        self.attempt, self.request, self.journal, self.clock = attempt, request, journal, clock
        self.candidate = self.cell['candidate_id']
        self.name = f'ARV2 LEGACY SIX {self.candidate} OCT2026'
        self.backtest_name = f'{self.name} A{attempt}'
        self.code_source = f'Codex R345 {self.candidate} A{attempt}'
        self.project_id = self.compile_id = self.launch_receipt = self.terminal_receipt = None
        self._used, self._times = set(), {}
        self._count = self._compile_count = self._capacity_count = self._status_count = 0
        self._last_clock = None
        self._begun = self._lock = self._launch_spent = self._result_spent = False
        self._compile_success = False
        self.last_request = self.last_failure = None

    def _now(self):
        value = self.clock()
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0
            and (self._last_clock is None or value >= self._last_clock), 'clock')
        self._last_clock = value
        return value

    def _event(self, marker, value):
        _event(self.journal, marker, value)

    def _call(self, marker, endpoint, payload):
        require(type(marker) is str and re.fullmatch('[a-z0-9-]{1,100}', marker)
            and marker not in self._used and self._count < MAX_DISPATCHES, 'request')
        require(type(endpoint) is str and endpoint in PAYLOAD_KEYS and type(payload) is dict, 'request')
        require(set(payload) == PAYLOAD_KEYS[endpoint]
            or (endpoint == 'projects/read' and marker == 'begin-names' and payload == {}), 'request')
        if 'projectId' in payload:
            require(type(payload['projectId']) is int and payload['projectId'] in (
                (REFERENCE_PROJECT,) if marker in ('begin-reference', 'begin-capacity')
                else (self.project_id,)), 'scope')
        if 'codeSourceId' in payload:
            require(payload['codeSourceId'] == self.code_source, 'lock')
        if endpoint.startswith('files/'):
            require(self._lock, 'lock')
            if 'name' in payload:
                require(payload['name'] in self.sources or (endpoint == 'files/delete'
                    and payload['name'] == 'research.ipynb'), 'source')
            if 'content' in payload:
                require(payload['content'] == self.sources[payload['name']], 'source')
        if endpoint == 'projects/create':
            require(payload == {'name': self.name, 'language': 'Py', 'organizationId': self.organization}
                    and marker == 'begin-create' and self.project_id is None, 'scope')
        if endpoint == 'projects/collaboration/lock/acquire':
            require(marker == 'begin-lock' and not self._lock, 'lock')
        if 'includeStatistics' in payload:
            require(payload['includeStatistics'] is False, 'request')
        if 'compileId' in payload:
            require(payload['compileId'] == self.compile_id, 'compile')
        if endpoint == 'backtests/create':
            require(marker == 'launch-create' and self._launch_spent and self.launch_receipt is None
                and payload['backtestName'] == self.backtest_name, 'state')
        if endpoint == 'backtests/read':
            require(marker == 'result-read' and self._result_spent and self.launch_receipt is not None
                and payload['backtestId'] == self.launch_receipt['backtest_id'], 'state')
        self._used.add(marker); self._count += 1
        self.last_request = {'endpoint': endpoint, 'marker': marker,
                             'payload_sha256': sha(canonical(payload))}
        self.last_failure = {**self.last_request, 'stage': 'intent_or_request_unaccepted'}
        self._event(marker + '-intent', {'endpoint': endpoint, 'payload_sha256': sha(canonical(payload))})
        try:
            response = self.request(endpoint, _copy(payload))
        except Exception:
            raise Refused('request_ambiguous') from None
        # Preserve a well-typed observed allocation identity before any later
        # response or journal validation can fail. This is not acceptance.
        if endpoint == 'projects/create' and type(response) is dict:
            rows = response.get('projects')
            if type(rows) is list and len(rows) == 1 and type(rows[0]) is dict:
                identity = rows[0].get('projectId')
                if type(identity) is int and 0 < identity < 2**63:
                    self.project_id = identity
                    self._event('project-created', {'project_id': identity, 'candidate_id': self.candidate})
        if endpoint == 'backtests/create' and type(response) is dict:
            row = response.get('backtest')
            if type(row) is dict and type(row.get('backtestId')) is str \
                    and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', row['backtestId']):
                self.launch_receipt = {'candidate_id': self.candidate, 'attempt': self.attempt,
                    'project_id': self.project_id, 'compile_id': self.compile_id,
                    'backtest_id': row['backtestId'], 'backtest_name': self.backtest_name}
                self._event('backtest-created', self.launch_receipt)
        raw = canonical(response)
        require(0 < len(raw) <= MAX_RESPONSE, 'bound')
        self.last_failure = {**self.last_request, 'stage': 'response_unaccepted',
                             'response_sha256': sha(raw), 'response_bytes': len(raw)}
        self._event(marker + '-observed', {'endpoint': endpoint, 'response_sha256': sha(raw),
                                         'response_bytes': len(raw)})
        _empty_errors(response)
        self.last_failure = None
        return _copy(response)

    def _access(self, prefix):
        packet = self._call(prefix + '-project', 'projects/read', {'projectId': self.project_id})
        _, owner = _project(packet, self.project_id, self.name, self.organization, self.user_id,
                            idle=True, own_code_source=self.code_source if self._lock else None)
        dedicated = self._call(prefix + '-collaborators', 'projects/collaboration/read',
                               {'projectId': self.project_id})
        _dedicated(dedicated, self.project_id, self.user_id, owner)

    def _history(self, prefix, *, own=False):
        value = self._call(prefix + '-history', 'backtests/list',
                           {'projectId': self.project_id, 'includeStatistics': False})
        require('projectId' not in value or (type(value['projectId']) is int
            and value['projectId'] == self.project_id), 'scope')
        rows = value.get('backtests')
        require(type(rows) is list and len(rows) == (1 if own else 0)
            and ('count' not in value or (type(value['count']) is int and value['count'] == len(rows))), 'history')
        if not own:
            return None
        row = rows[0]
        require(type(row) is dict and self.launch_receipt is not None
            and row.get('backtestId') == self.launch_receipt['backtest_id']
            and row.get('name') == self.backtest_name
            and ('projectId' not in row or (type(row['projectId']) is int and row['projectId'] == self.project_id))
            and ('compileId' not in row or row['compileId'] == self.compile_id)
            and row.get('status') in PENDING | TERMINAL, 'status')
        return row

    def _files(self, prefix, expected=None):
        value = self._call(prefix + '-files', 'files/read',
                           {'projectId': self.project_id, 'codeSourceId': self.code_source})
        rows = value.get('files')
        require(type(rows) is list and len(rows) <= 20, 'source_inventory')
        seen = {}
        for row in rows:
            require(type(row) is dict and type(row.get('projectId')) is int
                and row['projectId'] == self.project_id and type(row.get('name')) is str
                and row['name'] not in seen and type(row.get('content')) is str, 'source_inventory')
            seen[row['name']] = row['content']
        if expected is not None:
            require(set(seen) == set(expected) and all(seen[name] == text for name, text in expected.items()),
                    'source_changed')
        return seen

    def begin_once(self):
        require(not self._begun, 'state')
        self._begun = True
        self._call('begin-auth', 'authenticate', {})
        listing = self._call('begin-names', 'projects/read', {}).get('projects')
        require(type(listing) is list and len(listing) <= 1000 and all(type(row) is dict
            and type(row.get('name')) is str and row['name'] != self.name for row in listing), 'project_name')
        value = self._call('begin-reference', 'projects/read', {'projectId': REFERENCE_PROJECT})
        _project(value, REFERENCE_PROJECT, REFERENCE_NAME, self.organization, self.user_id, idle=False)
        observed = capacity(self._call('begin-capacity', 'projects/nodes/read', {'projectId': REFERENCE_PROJECT}))
        if observed['available_count'] == 0:
            return {'state': 'wait', 'capacity': observed, 'project_id': None}
        packet = self._call('begin-create', 'projects/create',
            {'name': self.name, 'language': 'Py', 'organizationId': self.organization})
        require(self.project_id is not None, 'project_identity')
        rows = packet.get('projects')
        require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict
            and type(rows[0].get('projectId')) is int and rows[0]['projectId'] == self.project_id,
            'project_identity')
        for field, wanted in (('name', self.name), ('organizationId', self.organization), ('language', 'Py')):
            require(field not in rows[0] or rows[0][field] == wanted, 'project_identity')
        self._access('created')
        self._history('created')
        self._call('begin-lock', 'projects/collaboration/lock/acquire',
                   {'projectId': self.project_id, 'codeSourceId': self.code_source})
        self._lock = True
        self._access('locked')
        initial = self._files('initial')
        require(set(initial) <= {'main.py', 'research.ipynb'}, 'source_inventory')
        expected = dict(initial)
        if 'research.ipynb' in expected:
            self._call('delete-default-notebook', 'files/delete',
                {'projectId': self.project_id, 'name': 'research.ipynb', 'codeSourceId': self.code_source})
            del expected['research.ipynb']
        names = [name for name in sorted(self.sources) if name != 'main.py'] + ['main.py']
        for index, name in enumerate(names):
            self._access(f'write-{index:02d}')
            self._files(f'write-{index:02d}', expected)
            self._call(f'write-{index:02d}-source', 'files/update' if name in expected else 'files/create',
                {'projectId': self.project_id, 'name': name, 'content': self.sources[name],
                 'codeSourceId': self.code_source})
            expected[name] = self.sources[name]
        self._access('compiled-preflight')
        self._history('compiled-preflight')
        self._files('compiled-preflight', self.sources)
        result = self._call('compile-create', 'compile/create', {'projectId': self.project_id})
        self.compile_id = _id(result.get('compileId'))
        require('projectId' not in result or (type(result['projectId']) is int
                and result['projectId'] == self.project_id), 'scope')
        self._event('compile-created', {'project_id': self.project_id, 'compile_id': self.compile_id})
        return {'state': 'compiling', 'project_id': self.project_id, 'compile_id': self.compile_id}

    def poll_compile(self, index):
        require(self.compile_id is not None and not self._compile_success and self.terminal_receipt is None
            and type(index) is int and index == self._compile_count and index < COMPILE_POLLS, 'compile_budget')
        now = self._now()
        require('compile' not in self._times or now - self._times['compile'] >= COMPILE_INTERVAL, 'wait')
        self._times['compile'] = now; self._compile_count += 1
        value = self._call(f'compile-{index:03d}', 'compile/read',
                           {'projectId': self.project_id, 'compileId': self.compile_id})
        state = value.get('state')
        require(value.get('compileId') == self.compile_id
            and ('projectId' not in value or (type(value['projectId']) is int and value['projectId'] == self.project_id))
            and state in ('InQueue', 'Building', 'BuildSuccess', 'BuildError'), 'compile')
        self._compile_success = state == 'BuildSuccess'
        if state == 'BuildError':
            self.terminal_receipt = {'candidate_id': self.candidate, 'attempt': self.attempt,
                'project_id': self.project_id, 'compile_id': self.compile_id, 'status': 'BuildError'}
            self._event('compile-terminal', self.terminal_receipt)
        return {'state': state, 'project_id': self.project_id, 'compile_id': self.compile_id}

    def launch_once(self):
        require(self._compile_success and not self._launch_spent and self.terminal_receipt is None
            and self._capacity_count < CAPACITY_POLLS, 'state')
        now = self._now()
        require('capacity' not in self._times or now - self._times['capacity'] >= CAPACITY_INTERVAL, 'wait')
        self._times['capacity'] = now; index = self._capacity_count; self._capacity_count += 1
        prefix = f'launch-{index:03d}'
        self._access(prefix); self._history(prefix); self._files(prefix, self.sources)
        compile_row = self._call(prefix + '-compile', 'compile/read',
            {'projectId': self.project_id, 'compileId': self.compile_id})
        require(compile_row.get('compileId') == self.compile_id and compile_row.get('state') == 'BuildSuccess'
            and ('projectId' not in compile_row or (type(compile_row['projectId']) is int
                and compile_row['projectId'] == self.project_id)), 'compile')
        observed = capacity(self._call(prefix + '-capacity', 'projects/nodes/read', {'projectId': self.project_id}))
        if observed['available_count'] == 0:
            return {'state': 'wait', 'capacity': observed}
        self._launch_spent = True
        value = self._call('launch-create', 'backtests/create', {'projectId': self.project_id,
            'compileId': self.compile_id, 'backtestName': self.backtest_name}).get('backtest')
        require(type(value) is dict and self.launch_receipt is not None
            and type(value.get('projectId')) is int and value['projectId'] == self.project_id
            and value.get('name') == self.backtest_name
            and ('compileId' not in value or value['compileId'] == self.compile_id)
            and value.get('status') in PENDING | TERMINAL, 'launch_identity')
        if value['status'] in TERMINAL:
            self._terminal(value)
        return {'state': 'launched', 'launch_receipt': _copy(self.launch_receipt), 'capacity': observed,
                'terminal_receipt': _copy(self.terminal_receipt)}

    def _terminal(self, row):
        self.terminal_receipt = {**self.launch_receipt, 'status': row['status']}
        self._event('backtest-terminal', self.terminal_receipt)

    def poll_status(self, index):
        require(self.launch_receipt is not None and self.terminal_receipt is None
            and type(index) is int and index == self._status_count and index < STATUS_POLLS, 'status_budget')
        now = self._now()
        require('status' not in self._times or now - self._times['status'] >= STATUS_INTERVAL, 'wait')
        self._times['status'] = now; self._status_count += 1
        row = self._history(f'status-{index:03d}', own=True)
        if row['status'] in TERMINAL:
            self._terminal(row)
        return {'status': row['status'], 'terminal': row['status'] in TERMINAL,
                'launch_receipt': _copy(self.launch_receipt)}

    def read_statistics_once(self):
        require(not self._result_spent and self.terminal_receipt is not None
            and self.terminal_receipt['status'] == 'Completed.', 'not_completed')
        self._result_spent = True
        self._access('result'); row = self._history('result', own=True)
        require(row['status'] == 'Completed.', 'not_completed')
        self._files('result', self.sources)
        value = self._call('result-read', 'backtests/read', {'projectId': self.project_id,
            'backtestId': self.launch_receipt['backtest_id']}).get('backtest')
        require(type(value) is dict and value.get('projectId') == self.project_id
            and type(value.get('projectId')) is int and value.get('backtestId') == self.launch_receipt['backtest_id']
            and value.get('name') == self.backtest_name and value.get('status') == 'Completed.'
            and ('compileId' not in value or value['compileId'] == self.compile_id), 'result')
        statistics = value.get('statistics')
        require(type(statistics) is dict, 'statistics')
        names = [name for name in statistics if type(name) is str and name.startswith('ARV2_')]
        permitted = set(LEGACY_STATISTICS) | {PERIOD_STATISTIC}
        require(set(names) in (set(LEGACY_STATISTICS), permitted), 'statistics')
        retained = {}
        for name in names:
            text = statistics[name]
            limit = 16384 if name.endswith('DIAGNOSTICS') else 8192
            require(type(text) is str and text.isascii() and 0 < len(text) <= limit, 'statistics')
            retained[name] = text
        # Publish original bounded strings before parsing. The caller supplies
        # R343's exact semantic parser; this method never declares run_valid.
        self._event('result-statistics', {'launch_receipt': self.launch_receipt, 'statistics': retained})
        return {'launch_receipt': _copy(self.launch_receipt), 'statistics': retained,
                'semantic_validation': 'required', **FALSE_FLAGS}
