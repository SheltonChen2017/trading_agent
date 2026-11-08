"""Injected R298 launch/result protocol for the exact section-322 plain source.

No client, credential, filesystem or operational action runs on import.  A new
frozen caller owns admission, claims, deadlines, actual exits and publication.
The earlier A11 source/compile operation remains spent; its compile is only an
exact dependency here.  Callback journals contain finite metadata, never raw
project responses, source text or licensed rows.
"""
from __future__ import annotations

import ast
import json
import math
import re
import time

from scripts import arv2_r298_plain_readiness_remote as ready
from research.analyst_revisions_v2_qc import newrule_comparison_submission as frozen


SCHEMA = 'arv2-r298-plain-launch-v1'
PROJECT_ID, ATTEMPT = 38364439, 12
COMPILE_ID = '5bd25474163eb6cf13a005139d1c4998-2a348312a9ff411534083f2012d355b5'
SOURCE_MANIFEST_SHA256 = '8dfc3d3e16c0f6b555c565d9cac5d4e86a2fe35d037f95538e2a7dfe70a7bfa9'
BACKTEST_NAME = 'ARV2 R298 NEWRULE SIX OFF 2021 OCT2026 R323 A12 9dde3978'
CAPACITY_INTERVAL, CAPACITY_POLLS = 60, 3
STATUS_INTERVAL, STATUS_POLLS = frozen.STATUS_INTERVAL, frozen.STATUS_POLLS
PENDING = frozenset(('In Queue...', 'In Progress...'))
TERMINAL = frozenset(('Completed.', 'Runtime Error'))
MAX_RESPONSE_BYTES = 1024 * 1024
FALSE_FLAGS = {'point_in_time_proven': False, 'formal_identity_admitted': False,
               'formal_forward_ready': False, 'paper_or_live_ready': False}
PAYLOAD_KEYS = {
    'projects/read': {'projectId'}, 'projects/collaboration/read': {'projectId'},
    'files/read': {'projectId', 'codeSourceId'}, 'compile/read': {'projectId', 'compileId'},
    'projects/nodes/read': {'projectId'},
    'backtests/list': {'projectId', 'includeStatistics'},
    'backtests/create': {'projectId', 'compileId', 'backtestName'},
    'backtests/read': {'projectId', 'backtestId'},
}
FINITE = frozenset(('binding', 'callbacks', 'clock', 'journal', 'marker', 'endpoint',
    'payload', 'response', 'response_bound', 'access', 'history', 'source_inventory',
    'source_bytes', 'source_hash', 'compile', 'capacity', 'capacity_budget', 'wait',
    'launch_once', 'launch_receipt', 'status_once', 'status_budget', 'status',
    'result_once', 'not_completed', 'result_identity', 'result_statistics', 'profile'))


class Refused(ValueError):
    """Finite local category, not a provider message or authenticated cause."""


def require(value, code):
    if not value:
        raise Refused(code)


canonical, sha = ready.canonical, ready.sha


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    if type(error) is ready.access.AccessRefused:
        return ready.access.finite_error(error)['code']
    if type(error) is frozen.NewruleSubmissionError:
        return frozen.finite_failure(error)
    return 'unknown'


def profile_record():
    return {'schema': SCHEMA, 'project_id': PROJECT_ID, 'attempt': ATTEMPT,
        'compile_id': COMPILE_ID, 'source_manifest_sha256': SOURCE_MANIFEST_SHA256,
        'projection_sha256': ready.PROJECTION_SHA256, 'profile_sha256': ready.PROFILE_SHA256,
        'package_sha256': ready.PACKAGE_SHA256, 'backtest_name': BACKTEST_NAME,
        'capacity_interval_seconds': CAPACITY_INTERVAL, 'capacity_poll_limit': CAPACITY_POLLS,
        'status_interval_seconds': STATUS_INTERVAL, 'status_poll_limit': STATUS_POLLS,
        'aggregate_reads': 1, 'max_response_bytes': MAX_RESPONSE_BYTES,
        'one_backtest_create': True, 'fast_terminal_create_accepted': True, **FALSE_FLAGS}


def _copy(value):
    return json.loads(canonical(value))


def _validate_profile(profile):
    require(type(profile) is dict, 'profile')
    seed = dict(profile)
    supplied = seed.pop('profile_sha256', None)
    require(supplied == ready.PROFILE_SHA256 and frozen.runtime.targets.digest(seed) == supplied
            and profile.get('package_sha256') == ready.PACKAGE_SHA256
            and profile.get('universe_count') == 6 and profile.get('ar_percent') == 0, 'profile')
    return _copy(profile)


def _launch_binding():
    return {'schema': SCHEMA, 'candidate_id': 'R298', 'attempt': ATTEMPT,
        'project_id': PROJECT_ID, 'compile_id': COMPILE_ID, 'backtest_name': BACKTEST_NAME,
        'projection_sha256': ready.PROJECTION_SHA256, 'profile_sha256': ready.PROFILE_SHA256,
        'package_sha256': ready.PACKAGE_SHA256, 'source_manifest_sha256': SOURCE_MANIFEST_SHA256,
        **FALSE_FLAGS}


def validate_launch_receipt(value):
    """Pure identity/type check; the caller separately supplies actual exit."""
    expected = _launch_binding()
    require(type(value) is dict and set(value) == set(expected) | {'backtest_id'}
            and type(value['project_id']) is int and type(value['attempt']) is int
            and all(type(value[key]) is type(wanted) and value[key] == wanted for key, wanted in expected.items())
            and all(value[key] is False for key in FALSE_FLAGS)
            and type(value['backtest_id']) is str
            and re.fullmatch('[A-Za-z0-9_-]{1,128}', value['backtest_id'])
            and value['backtest_id'] != ready.predecessor.MANUAL_BACKTEST_ID, 'launch_receipt')
    return _copy(value)


def validate_terminal_receipt(value):
    require(type(value) is dict and type(value.get('status')) is str and value['status'] in TERMINAL, 'status')
    extras = {'status', 'failure_evidence'} if value['status'] == 'Runtime Error' else {'status'}
    launch = {key: item for key, item in value.items() if key not in extras}
    validate_launch_receipt(launch)
    require(set(value) == set(launch) | extras, 'status')
    if value['status'] == 'Runtime Error':
        evidence = value['failure_evidence']
        require(type(evidence) is dict and set(evidence) == {'terminal_category', 'known_runtime_code',
            'known_runtime_code_sha256', 'python_error_category', 'raw_error_retained', 'cause_authenticated'}
            and evidence['terminal_category'] == 'runtime_error' and evidence['raw_error_retained'] is False
            and evidence['cause_authenticated'] is False
            and evidence['python_error_category'] in (None, 'SyntaxError', 'IndentationError', 'ImportError',
                'ModuleNotFoundError', 'NameError', 'TypeError'), 'status')
        code = evidence['known_runtime_code']
        require((code is None and evidence['known_runtime_code_sha256'] is None)
            or (type(code) is str and code in frozen.FINITE_RUNTIME_CODES
                and evidence['known_runtime_code_sha256'] == sha(code.encode('ascii'))), 'status')
    return _copy(value)


def validate_result_receipt(value):
    """Revalidate finite statistics using the hash-bound public runtime profile."""
    extras = {'status', 'cell_completed', 'family_comparable', 'result_cell', 'statistics', 'expected_profile'}
    require(type(value) is dict and set(value) == set(_launch_binding()) | {'backtest_id'} | extras,
            'result_identity')
    validate_launch_receipt({key: item for key, item in value.items() if key not in extras})
    require(value['status'] == 'Completed.' and value['cell_completed'] is True
            and value['family_comparable'] is False and type(value['result_cell']) is int
            and value['result_cell'] == 1 and type(value['statistics']) is dict
            and set(value['statistics']) == {'meta', 'monthly'}, 'result_identity')
    profile = _validate_profile(value['expected_profile'])
    selected = {name: frozen.runtime.targets.canonical(value['statistics'][key]).decode('ascii')
                for name, key in ((frozen.runtime.META_STATISTIC, 'meta'),
                                  (frozen.runtime.MONTHLY_STATISTIC, 'monthly'))}
    result = frozen.runtime.validate_result_statistics(selected, expected_profile=profile)
    require(canonical(result) == canonical(value['statistics']), 'result_statistics')
    return _copy(value)


def _profile(sources, record):
    """Read the literal already bound by the authenticated public main hash."""
    try:
        calls = [node for node in ast.walk(ast.parse(sources['main.py']))
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                 and node.func.id == 'NewruleComparisonDriver']
        require(len(calls) == 1, 'profile')
        values = [item.value for item in calls[0].keywords if item.arg == 'profile']
        require(len(values) == 1, 'profile')
        profile = ast.literal_eval(values[0])
        require(type(profile) is dict, 'profile')
        seed = dict(profile)
        supplied = seed.pop('profile_sha256', None)
        require(supplied == record['profile_sha256'] == ready.PROFILE_SHA256
                and frozen.runtime.targets.digest(seed) == supplied
                and profile.get('package_sha256') == ready.PACKAGE_SHA256
                and profile.get('universe_count') == 6 and profile.get('ar_percent') == 0,
                'profile')
        return _validate_profile(profile)
    except (SyntaxError, ValueError, TypeError, KeyError, RecursionError):
        raise Refused('profile') from None


class PlainLaunch:
    """One create, bounded capacity/status observations and one aggregate read.

    ``launch_once`` can return ``state=wait`` at most three times, at least
    sixty seconds apart.  It never creates a job until its complete current
    access/history/source/compile gates and a fresh capacity read pass.
    """

    def __init__(self, record_bytes, source_pairs, *, request, journal, clock=time.monotonic):
        record, sources = ready.validate_public_packet(record_bytes, source_pairs)
        require(all(callable(value) for value in (request, journal, clock)), 'callbacks')
        self._profile = _profile(sources, record)
        self._sources = dict(sources)
        manifest = {'project_id': PROJECT_ID, 'projection_sha256': ready.PROJECTION_SHA256,
                    'files': [{'name': name, 'byte_count': len(raw), 'sha256': sha(raw)}
                              for name, raw in sorted(sources.items())]}
        require(sha(canonical(manifest)) == SOURCE_MANIFEST_SHA256, 'source_hash')
        self._request, self._journal, self._clock = request, journal, clock
        self._used, self._permit = set(), None
        self._capacity_count = self._status_count = 0
        self._capacity_time = self._status_time = None
        self._last_clock = None
        self._create_spent = self._read_spent = False
        self._launch = self._terminal = None

    @property
    def launch_receipt(self):
        return _copy(self._launch) if self._launch is not None else None

    @property
    def terminal_receipt(self):
        return _copy(self._terminal) if self._terminal is not None else None

    def _now(self):
        value = self._clock()
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0
                and (self._last_clock is None or value >= self._last_clock), 'clock')
        self._last_clock = value
        return value

    def _event(self, marker, value):
        require(self._journal(marker, _copy(value)) is None, 'journal')

    def _call(self, marker, endpoint, payload):
        self._permit = (marker, endpoint, canonical(payload))
        try:
            return self._rpc(marker, endpoint, payload)
        finally:
            self._permit = None

    def _rpc(self, marker, endpoint, payload):
        require(type(marker) is str and re.fullmatch('[a-z0-9-]{1,80}', marker)
                and marker not in self._used, 'marker')
        require(type(endpoint) is str and endpoint in PAYLOAD_KEYS, 'endpoint')
        require(type(payload) is dict and set(payload) == PAYLOAD_KEYS[endpoint]
                and type(payload.get('projectId')) is int and payload['projectId'] == PROJECT_ID,
                'payload')
        raw = canonical(payload)
        require(self._permit == (marker, endpoint, raw), 'payload')
        if 'codeSourceId' in payload:
            require(payload['codeSourceId'] == ready.CODE_SOURCE_ID, 'payload')
        if 'compileId' in payload:
            require(payload['compileId'] == COMPILE_ID, 'payload')
        if 'includeStatistics' in payload:
            require(payload['includeStatistics'] is False, 'payload')
        if endpoint == 'backtests/create':
            require(self._create_spent and self._launch is None and marker == 'launch-create'
                    and payload['backtestName'] == BACKTEST_NAME, 'launch_once')
        if endpoint == 'backtests/read':
            require(self._read_spent and self._launch is not None
                    and payload['backtestId'] == self._launch['backtest_id'], 'result_once')
        self._used.add(marker)
        self._event(marker, {'event': 'intent', 'endpoint': endpoint, 'sha256': sha(raw)})
        response = self._request(endpoint, _copy(payload))
        require(type(response) is dict, 'response')
        raw = canonical(response)
        require(len(raw) <= MAX_RESPONSE_BYTES, 'response_bound')
        value = json.loads(raw)
        require(value.get('success') is True
                and ('errors' not in value or value['errors'] == []), 'response')
        if endpoint == 'backtests/create':
            # Retain identity before any later journal publication can fail.
            self._accept_created(value.get('backtest'))
        self._event(marker, {'event': 'observed', 'endpoint': endpoint, 'sha256': sha(raw)})
        return value

    def _access(self, prefix):
        project = self._call(prefix + '-project', 'projects/read', {'projectId': PROJECT_ID})
        dedicated = self._call(prefix + '-collaborators', 'projects/collaboration/read', {'projectId': PROJECT_ID})
        observation = ready.access.verify_access(project, dedicated)
        self._event(prefix + '-access', {'event': 'access', 'observation': observation})

    def _history(self, prefix, *, own=False):
        value = self._call(prefix + '-history', 'backtests/list',
                           {'projectId': PROJECT_ID, 'includeStatistics': False})
        rows = ready.predecessor._backtest_rows(value, 2 if own else 1, 'prior_backtests')
        manuals = [row for row in rows if ready.predecessor._manual_backtest(row)]
        require(len(manuals) == 1, 'history')
        if not own:
            return None
        other = [row for row in rows if row is not manuals[0]]
        require(len(other) == 1, 'history')
        row = other[0]
        require(self._launch is not None and row.get('backtestId') == self._launch['backtest_id']
                and row.get('name') == BACKTEST_NAME
                and ('compileId' not in row or row['compileId'] == COMPILE_ID)
                and type(row.get('status')) is str and row['status'] in PENDING | TERMINAL,
                'status')
        return row

    def _files(self, prefix):
        value = self._call(prefix + '-files', 'files/read',
                           {'projectId': PROJECT_ID, 'codeSourceId': ready.CODE_SOURCE_ID})
        rows, seen = value.get('files'), set()
        require(type(rows) is list and len(rows) == 11, 'source_inventory')
        for row in rows:
            require(type(row) is dict and type(row.get('projectId')) is int
                    and row['projectId'] == PROJECT_ID, 'source_inventory')
            name, text = row.get('name'), row.get('content')
            require(type(name) is str and name in self._sources and name not in seen
                    and type(text) is str and text.isascii() and len(text) <= 64000,
                    'source_bytes')
            require(text.encode('ascii') == self._sources[name], 'source_hash')
            seen.add(name)
        require(seen == set(self._sources), 'source_inventory')

    def _compile(self, prefix):
        value = self._call(prefix + '-compile', 'compile/read',
                           {'projectId': PROJECT_ID, 'compileId': COMPILE_ID})
        require(type(value.get('projectId', PROJECT_ID)) is int
                and value.get('projectId', PROJECT_ID) == PROJECT_ID
                and value.get('compileId') == COMPILE_ID and value.get('state') == 'BuildSuccess', 'compile')

    def _fresh(self, prefix, *, own=False):
        self._access(prefix)
        row = self._history(prefix, own=own)
        if own:
            require(self._terminal is not None and row['status'] == self._terminal['status'], 'status')
        self._files(prefix)
        self._compile(prefix)

    def launch_once(self):
        require(not self._create_spent and self._launch is None, 'launch_once')
        require(self._capacity_count < CAPACITY_POLLS, 'capacity_budget')
        now = self._now()
        require(self._capacity_time is None or now - self._capacity_time >= CAPACITY_INTERVAL, 'wait')
        index = self._capacity_count
        self._capacity_count += 1
        self._capacity_time = now
        prefix = f'launch-{index:03d}'
        self._fresh(prefix)
        capacity = frozen._capacity(self._call(prefix + '-capacity', 'projects/nodes/read', {'projectId': PROJECT_ID}))
        self._event(prefix + '-capacity-valid', {'event': 'capacity', 'capacity': capacity})
        if capacity['available_count'] == 0:
            return {'state': 'wait', 'capacity': capacity, 'observation': index + 1}
        self._create_spent = True
        self._call('launch-create', 'backtests/create',
                   {'projectId': PROJECT_ID, 'compileId': COMPILE_ID, 'backtestName': BACKTEST_NAME})
        return {'state': 'launched', 'launch_receipt': self.launch_receipt,
                'terminal_receipt': self.terminal_receipt, 'capacity': capacity}

    def _accept_created(self, row):
        require(type(row) is dict and type(row.get('projectId')) is int
                and row['projectId'] == PROJECT_ID and row.get('name') == BACKTEST_NAME
                and ('compileId' not in row or row['compileId'] == COMPILE_ID), 'launch_receipt')
        identity = row.get('backtestId')
        require(type(identity) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', identity)
                and identity != ready.predecessor.MANUAL_BACKTEST_ID, 'launch_receipt')
        self._launch = validate_launch_receipt({**_launch_binding(), 'backtest_id': identity})
        self._event('launch-receipt', {'event': 'launch_receipt', 'receipt': self._launch})
        require(type(row.get('status')) is str and row['status'] in PENDING | TERMINAL, 'launch_receipt')
        if row['status'] in TERMINAL:
            self._set_terminal(row)

    def _set_terminal(self, row):
        self._terminal = {**self._launch, 'status': row['status']}
        if row['status'] == 'Runtime Error':
            self._terminal['failure_evidence'] = frozen._failure_evidence(row, 'runtime_error')
        validate_terminal_receipt(self._terminal)
        self._event('terminal-receipt', {'event': 'terminal_receipt', 'receipt': self._terminal})

    def poll_status(self, index):
        require(self._launch is not None and self._terminal is None, 'status_once')
        require(type(index) is int and index == self._status_count and index < STATUS_POLLS, 'status_budget')
        now = self._now()
        require(self._status_time is None or now - self._status_time >= STATUS_INTERVAL, 'wait')
        self._status_count += 1
        self._status_time = now
        row = self._history(f'status-{index:03d}', own=True)
        if row['status'] in TERMINAL:
            self._set_terminal(row)
        return {**self._launch, 'status': row['status'], 'terminal': row['status'] in TERMINAL,
                'failure_evidence': self._terminal.get('failure_evidence') if self._terminal else None}

    def read_once(self):
        require(not self._read_spent, 'result_once')
        require(self._terminal is not None and self._terminal['status'] == 'Completed.', 'not_completed')
        self._read_spent = True
        self._fresh('result', own=True)
        row = self._call('result-aggregate', 'backtests/read',
                         {'projectId': PROJECT_ID, 'backtestId': self._launch['backtest_id']}).get('backtest')
        require(type(row) is dict and type(row.get('projectId')) is int
                and row['projectId'] == PROJECT_ID and row.get('backtestId') == self._launch['backtest_id']
                and row.get('name') == BACKTEST_NAME and row.get('status') == 'Completed.'
                and ('compileId' not in row or row['compileId'] == COMPILE_ID), 'result_identity')
        stats = row.get('statistics')
        require(type(stats) is dict, 'result_statistics')
        selected = {key: stats.get(key) for key in (frozen.runtime.META_STATISTIC, frozen.runtime.MONTHLY_STATISTIC)}
        require(all(type(value) is str and value.isascii() and 0 < len(value) <= frozen.runtime.MAX_STATISTIC_BYTES
                    for value in selected.values()), 'result_statistics')
        validated = frozen.runtime.validate_result_statistics(selected, expected_profile=_copy(self._profile))
        result = {**self._launch, 'status': 'Completed.', 'cell_completed': True,
                  'family_comparable': False, 'result_cell': 1, 'statistics': validated,
                  'expected_profile': _copy(self._profile)}
        validate_result_receipt(result)
        self._event('result-receipt', {'event': 'result_receipt', 'receipt': result})
        return _copy(result)
