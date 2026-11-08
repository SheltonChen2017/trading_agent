"""Injected A19 identity-only RAW-reference witness; never a price fallback.

The separately versioned projection preserves the quote-side execution policy
and instruments only the hard RAW-reference failure branch. The
outer caller owns private admission, credentials, claims, deadlines and actual
exit authentication.  Import performs no operation; journals retain finite
metadata and aggregate evidence, never source text or raw error messages.
"""
from __future__ import annotations

import json
import math
import re
import time

from scripts import arv2_r298_plain_launch as previous
from scripts import arv2_newrule_reference_identity_projection as projection
from scripts import arv2_r298_quote_execution_a16_remote as quote_parent
from scripts import arv2_newrule_reference_identity_response as response_projection
from scripts import arv2_r298_mia_access_representation as access


SCHEMA = 'arv2-r298-reference-identity-diagnostic-a19-v1'
PROJECT_ID, ATTEMPT = 38364439, 19
PROJECTION_SHA256 = '83255174a37e1aa69ec8436c2b77561c9988007e526d0ad2ced630826e10589f'
PROFILE_SHA256 = '86f12ed5705d2413575855e61d6b92ec2a02856b2a8cbe07dcc048b32ed7809d'
SOURCE_MANIFEST_SHA256 = '7a852d8e1d575843340cc87d4e1495133cf3a045702094c89b852b25360294a7'
OLD_PROJECTION_SHA256 = 'dc1db76b792ab1ac17879e87b3dcf1f544ca288f46a487d93b01b2eac4658e77'
OLD_SOURCE_MANIFEST_SHA256 = 'e8118198f92063743cdd52b8c55f155d38326f8e2e6b9d8069c29d8fb5525b61'
BACKTEST_NAME = 'ARV2 R298 REFERENCE IDENTITY DIAGNOSTIC R323 A19'
A18_ID = '78ba7a236450cdeffea5efe07d087637'
A18_NAME = 'ARV2 R298 RAW REFERENCE DIAGNOSTIC R323 A18'
A18_COMPILE_ID = 'ed8233767e663d42a2ea3c9d5590d8f5-e3908e134c5314de5875830686db3b0b'
A16_ID = '65a1d6698d182b11f2f4b60b7e31267b'
A16_NAME = 'ARV2 R298 QUOTE EXECUTION R323 A16'
A16_COMPILE_ID = 'e92504b34a73aa018748ff8c59e1e00f-3eb607058a468d1e6924c729550834a0'
A14_ID = '45ffd36c48e59adfbb212cfd3324dfeb'
A14_NAME = 'ARV2 R298 QUOTE DIAGNOSTIC R323 A14'
A14_COMPILE_ID = 'c8398c515fb7425391986ac7b3d84429-79837ae21b59dee4b69ddb000301b67d'
A12_ID = 'e5c358608fa75d62b3a26a1be26d301f'
CODE_SOURCE_ID = previous.ready.CODE_SOURCE_ID
RUNTIME_NAME = 'newrule_legacy_primitives.py'
EDIT_NAMES = (RUNTIME_NAME, 'main.py')
COMPILE_INTERVAL, COMPILE_POLLS = 1, 120
CAPACITY_INTERVAL, CAPACITY_POLLS = 60, 3
STATUS_INTERVAL, STATUS_POLLS = previous.STATUS_INTERVAL, previous.STATUS_POLLS
PENDING, TERMINAL = previous.PENDING, previous.TERMINAL
FALSE_FLAGS = dict(previous.FALSE_FLAGS)
MAX_RESPONSE_BYTES, MAX_ERROR_BYTES = 1024 * 1024, 32768
KNOWN_CODES = quote_parent.KNOWN_CODES | frozenset(projection.FAILURE_CODES)
PAYLOAD_KEYS = {**previous.PAYLOAD_KEYS,
    'projects/collaboration/lock/acquire': {'projectId', 'codeSourceId'},
    'files/update': {'projectId', 'name', 'content', 'codeSourceId'},
    'compile/create': {'projectId'}}
FINITE = previous.FINITE | frozenset(('prepare_once', 'old_source', 'edit_once',
    'lock_once', 'compile_once', 'compile_budget', 'compile_receipt', 'diagnostic_packet'))
canonical, sha = previous.canonical, previous.sha


class Refused(ValueError):
    """Finite category; no provider payload or authenticated cause claim."""


def require(value, code):
    if not value:
        raise Refused(code)


def _copy(value):
    return json.loads(canonical(value))


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    return previous.finite(error)


def profile_record():
    return {'schema': SCHEMA, 'project_id': PROJECT_ID, 'attempt': ATTEMPT,
        'projection_sha256': PROJECTION_SHA256, 'profile_sha256': PROFILE_SHA256,
        'source_manifest_sha256': SOURCE_MANIFEST_SHA256, 'backtest_name': BACKTEST_NAME,
        'a12_id': A12_ID, 'a14_id': A14_ID, 'a14_name': A14_NAME, 'a14_compile_id': A14_COMPILE_ID,
        'a16_id': A16_ID, 'a16_name': A16_NAME, 'a16_compile_id': A16_COMPILE_ID,
        'a18_id': A18_ID, 'a18_name': A18_NAME, 'a18_compile_id': A18_COMPILE_ID,
        'prior_projection_sha256': OLD_PROJECTION_SHA256,
        'prior_source_manifest_sha256': OLD_SOURCE_MANIFEST_SHA256,
        'execution_policy_changed': False, 'historical_a13_cause_known': False,
        'access_representation_schema': access.SCHEMA,
        'access_representation_policy': access.profile_record(),
        'execution_policy': quote_parent.projection.POLICY,
        'reference_diagnostic_policy': projection.policy_record(),
        'result_validator': 'unchanged_AST_parameterized_by_exact_new_profile',
        'source_edits': list(EDIT_NAMES), 'compile_creates': 1,
        'compile_interval': COMPILE_INTERVAL, 'compile_polls': COMPILE_POLLS,
        'capacity_interval': CAPACITY_INTERVAL, 'capacity_polls': CAPACITY_POLLS,
        'status_interval': STATUS_INTERVAL, 'status_polls': STATUS_POLLS,
        'backtest_creates': 1, 'aggregate_or_error_reads': 1,
        'diagnostic_only': True, 'accepted_risk_only': True,
        'comparison_requires_common_versioned_family': True,
        'source_diagnostic_only': True, 'selected_response_only_hash': True,
        'extra_history_probe_calls': 0, 'private_identity_witness_only': True,
        'backtest_read_wire_bound_unchanged': 16 * 1024 * 1024,
        'backtest_read_selected_bound': response_projection.MAX_SELECTED_BYTES,
        'whole_backtest_response_authenticated': False,
        'runtime_error_detail_read': 'exact_own_job_finite_error_projection_only',
        'new_failure_codes': list(projection.FAILURE_CODES), **FALSE_FLAGS}


def failure_evidence(row, kind):
    """Project known complete error tokens, including a bounded QC stack trace.

    Classification is diagnostic, not an authenticated root cause.  Multiple
    recognized codes remain unknown.  Private strings are never returned.
    """
    require(type(row) is dict and kind in ('compile_error', 'runtime_error'), 'response')
    if 'finite_projected_error' in row:
        require(kind == 'runtime_error', 'response')
        checked = response_projection.validate_failure_evidence(row['finite_projected_error'])
        _validate_failure(checked, kind)
        return _copy(checked)
    values = [row.get('error'), row.get('errorMessage')]
    extra = row.get('errors')
    if type(extra) is list and len(extra) <= 8:
        values.extend(extra)
    codes, categories, contexts = set(), set(), {}
    for value in values:
        if type(value) is not str:
            continue
        try:
            if not 0 < len(value.encode('utf-8')) <= MAX_ERROR_BYTES:
                continue
        except UnicodeError:
            continue
        for line in value.splitlines()[:512]:
            line = line.strip()
            context = projection.parse_failure_context(line)
            if context is not None:
                checked = projection.validate_failure_context(context)
                contexts[canonical(checked)] = checked
                codes.add(checked['predicate'])
            if line in KNOWN_CODES:
                codes.add(line)
            # Prefix required for tokens embedded in a longer stack line;
            # incidental source-code strings or partial code names do not match.
            for match in re.finditer(r'(?<![A-Za-z0-9_])(?:NewruleError|RuntimeError|Runtime Error)\s*:\s*([a-z_]{1,64})(?![A-Za-z0-9_])', line):
                if match.group(1) in KNOWN_CODES:
                    codes.add(match.group(1))
            for category in ('SyntaxError', 'IndentationError', 'ImportError', 'ModuleNotFoundError', 'NameError', 'TypeError'):
                if line.startswith(category + ': '):
                    categories.add(category)
    code = next(iter(codes)) if len(codes) == 1 else None
    context = next(iter(contexts.values())) if len(contexts) == 1 else None
    if context is not None and context['predicate'] != code:
        context = None
    return {'terminal_category': kind, 'known_runtime_code': code,
        'known_runtime_code_sha256': sha(code.encode('ascii')) if code else None,
        'python_error_category': next(iter(categories)) if len(categories) == 1 else None,
        'raw_error_retained': False, 'cause_authenticated': False, 'diagnostic_context': context}


def _validate_failure(value, kind):
    require(type(value) is dict and set(value) == {'terminal_category', 'known_runtime_code',
        'known_runtime_code_sha256', 'python_error_category', 'raw_error_retained', 'cause_authenticated', 'diagnostic_context'}
        and value['terminal_category'] == kind and value['raw_error_retained'] is False
        and value['cause_authenticated'] is False
        and value['python_error_category'] in (None, 'SyntaxError', 'IndentationError', 'ImportError',
            'ModuleNotFoundError', 'NameError', 'TypeError'), 'response')
    code = value['known_runtime_code']
    require((code is None and value['known_runtime_code_sha256'] is None)
        or (type(code) is str and code in KNOWN_CODES
            and value['known_runtime_code_sha256'] == sha(code.encode('ascii'))), 'response')
    if value['diagnostic_context'] is not None:
        context = projection.validate_failure_context(value['diagnostic_context'])
        require(code in projection.FAILURE_CODES and context['predicate'] == code, 'response')


def _binding():
    return {'schema': SCHEMA, 'candidate_id': 'R298', 'attempt': ATTEMPT,
        'project_id': PROJECT_ID, 'projection_sha256': PROJECTION_SHA256,
        'profile_sha256': PROFILE_SHA256, 'source_manifest_sha256': SOURCE_MANIFEST_SHA256,
        'package_sha256': previous.ready.PACKAGE_SHA256,
        'diagnostic_only': True, 'accepted_risk_only': True, **FALSE_FLAGS}


def validate_compile_receipt(value):
    expected = _binding()
    require(type(value) is dict and set(value) == set(expected) | {'compile_id'}
        and all(type(value[key]) is type(item) and value[key] == item for key, item in expected.items())
        and type(value['compile_id']) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', value['compile_id'])
        and value['compile_id'] not in (previous.COMPILE_ID, A14_COMPILE_ID, A16_COMPILE_ID, A18_COMPILE_ID), 'compile_receipt')
    return _copy(value)


def validate_launch_receipt(value):
    require(type(value) is dict and set(value) == set(_binding()) | {'compile_id', 'backtest_id', 'backtest_name'},
        'launch_receipt')
    validate_compile_receipt({key: item for key, item in value.items() if key not in ('backtest_id', 'backtest_name')})
    require(value['backtest_name'] == BACKTEST_NAME and type(value['backtest_name']) is str
        and type(value['backtest_id']) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', value['backtest_id'])
        and value['backtest_id'] not in (A12_ID, A14_ID, A16_ID, A18_ID, previous.ready.predecessor.MANUAL_BACKTEST_ID), 'launch_receipt')
    return _copy(value)


def validate_terminal_receipt(value):
    require(type(value) is dict and type(value.get('status')) is str
        and value['status'] in TERMINAL | {'BuildError'}, 'status')
    bad = value['status'] != 'Completed.'
    extras = {'status', 'failure_evidence'} if bad else {'status'}
    receipt = {key: item for key, item in value.items() if key not in extras}
    (validate_compile_receipt if value['status'] == 'BuildError' else validate_launch_receipt)(receipt)
    require(set(value) == set(receipt) | extras, 'status')
    if bad:
        _validate_failure(value['failure_evidence'], 'compile_error' if value['status'] == 'BuildError' else 'runtime_error')
    return _copy(value)


def validate_result_receipt(value):
    extras = {'status', 'cell_completed', 'family_comparable', 'result_cell', 'statistics', 'expected_profile'}
    require(type(value) is dict and set(value) == set(_binding()) | {'compile_id', 'backtest_id', 'backtest_name'} | extras,
        'result_identity')
    validate_launch_receipt({key: item for key, item in value.items() if key not in extras})
    profile = value['expected_profile']
    require(value['status'] == 'Completed.' and value['cell_completed'] is True
        and value['family_comparable'] is False and type(value['result_cell']) is int and value['result_cell'] == 0
        and type(profile) is dict and profile.get('profile_sha256') == PROFILE_SHA256
        and previous.frozen.runtime.targets.digest({key: item for key, item in profile.items() if key != 'profile_sha256'}) == PROFILE_SHA256
        and type(value['statistics']) is dict and set(value['statistics']) == {'meta', 'monthly'}, 'result_identity')
    selected = {name: previous.frozen.runtime.targets.canonical(value['statistics'][key]).decode('ascii')
        for name, key in ((previous.frozen.runtime.META_STATISTIC, 'meta'), (previous.frozen.runtime.MONTHLY_STATISTIC, 'monthly'))}
    checked = previous.frozen.runtime.validate_result_statistics(selected, expected_profile=_copy(profile))
    require(canonical(checked) == canonical(value['statistics']), 'result_statistics')
    return _copy(value)


class QuoteDiagnostic:
    """One accepted-risk execution lifecycle; name retained for caller compatibility."""

    def __init__(self, record_bytes, source_pairs, *, request, journal, clock=time.monotonic):
        require(PROJECTION_SHA256 != '0' * 64 and PROFILE_SHA256 != '0' * 64, 'binding')
        record, profile, pairs = projection.validate_public_projection(record_bytes, source_pairs,
            expected_projection_sha256=PROJECTION_SHA256, expected_profile_sha256=PROFILE_SHA256)
        require(all(callable(value) for value in (request, journal, clock)), 'callbacks')
        self._sources, self._profile = dict(pairs), _copy(profile)
        manifest = self._manifest(self._sources, PROJECTION_SHA256)
        require(sha(canonical(manifest)) == SOURCE_MANIFEST_SHA256, 'source_hash')
        self._request, self._journal, self._clock = request, journal, clock
        self._used, self._permit, self._written = set(), None, set()
        self._prepared = self._locked = self._compile_spent = self._create_spent = self._read_spent = False
        self._compile = self._launch = self._terminal = None
        self._compile_state = None
        self._compile_count = self._capacity_count = self._status_count = 0
        self._compile_time = self._capacity_time = self._status_time = self._last_clock = None

    @property
    def compile_receipt(self): return _copy(self._compile) if self._compile else None
    @property
    def launch_receipt(self): return _copy(self._launch) if self._launch else None
    @property
    def terminal_receipt(self): return _copy(self._terminal) if self._terminal else None

    @staticmethod
    def _manifest(files, digest):
        return {'project_id': PROJECT_ID, 'projection_sha256': digest,
            'files': [{'name': name, 'byte_count': len(raw), 'sha256': sha(raw)} for name, raw in sorted(files.items())]}

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
        try: return self._rpc(marker, endpoint, payload)
        finally: self._permit = None

    def _rpc(self, marker, endpoint, payload):
        require(type(marker) is str and re.fullmatch('[a-z0-9-]{1,80}', marker) and marker not in self._used, 'marker')
        require(type(endpoint) is str and endpoint in PAYLOAD_KEYS, 'endpoint')
        require(type(payload) is dict and set(payload) == PAYLOAD_KEYS[endpoint]
            and type(payload.get('projectId')) is int and payload['projectId'] == PROJECT_ID, 'payload')
        raw = canonical(payload)
        require(self._permit == (marker, endpoint, raw), 'payload')
        if 'codeSourceId' in payload: require(payload['codeSourceId'] == CODE_SOURCE_ID, 'payload')
        if 'includeStatistics' in payload: require(payload['includeStatistics'] is False, 'payload')
        if 'compileId' in payload:
            require(self._compile is not None and payload['compileId'] == self._compile['compile_id'], 'compile')
        if endpoint == 'projects/collaboration/lock/acquire':
            require(self._prepared and not self._locked and marker == 'prepare-lock', 'lock_once')
        if endpoint == 'files/update':
            require(self._locked and payload['name'] in EDIT_NAMES and payload['name'] not in self._written
                and type(payload['content']) is str and payload['content'].encode('ascii') == self._sources[payload['name']], 'edit_once')
            self._written.add(payload['name'])
        if endpoint == 'compile/create':
            require(self._compile_spent and self._compile is None and marker == 'prepare-compile-create'
                and self._written == set(EDIT_NAMES), 'compile_once')
        if endpoint == 'backtests/create':
            require(self._create_spent and self._launch is None and marker == 'launch-create'
                and payload['backtestName'] == BACKTEST_NAME, 'launch_once')
        if endpoint == 'backtests/read':
            require(self._read_spent and self._launch is not None and payload['backtestId'] == self._launch['backtest_id'], 'result_once')
        self._used.add(marker)
        self._event(marker, {'event': 'intent', 'endpoint': endpoint, 'sha256': sha(raw)})
        value = self._request(endpoint, _copy(payload))
        require(type(value) is dict, 'response')
        if endpoint == 'backtests/read':
            require(self._launch is not None and self._compile is not None
                and self._terminal is not None
                and self._terminal['status'] in ('Runtime Error', 'Completed.'), 'result_identity')
            response_projection.validate_selected(value, project_id=PROJECT_ID,
                backtest_id=self._launch['backtest_id'], backtest_name=BACKTEST_NAME,
                compile_id=self._compile['compile_id'],
                mode='error' if self._terminal['status'] == 'Runtime Error' else 'completed')
        raw = canonical(value)
        require(len(raw) <= MAX_RESPONSE_BYTES, 'response_bound')
        value = json.loads(raw)
        good = value.get('success') is True and ('errors' not in value or value['errors'] == [])
        if good and endpoint == 'compile/create': self._accept_compile(value)
        if good and endpoint == 'backtests/create': self._accept_created(value.get('backtest'))
        self._event(marker, {'event': 'observed', 'endpoint': endpoint, 'sha256': sha(raw)})
        require(good, 'response')
        return value

    def _access(self, prefix):
        project = self._call(prefix + '-project', 'projects/read', {'projectId': PROJECT_ID})
        dedicated = self._call(prefix + '-collaborators', 'projects/collaboration/read', {'projectId': PROJECT_ID})
        checked = access.verify_access(project, dedicated)
        self._event(prefix + '-access', {'event': 'access', 'observation': checked})

    def _history(self, prefix, *, own=False):
        value = self._call(prefix + '-history', 'backtests/list', {'projectId': PROJECT_ID, 'includeStatistics': False})
        rows = previous.ready.predecessor._backtest_rows(value, 6 if own else 5, 'prior_backtests')
        manual = [row for row in rows if previous.ready.predecessor._manual_backtest(row)]
        a12 = [row for row in rows if row.get('backtestId') == A12_ID
            and row.get('name') == previous.BACKTEST_NAME and row.get('status') == 'Runtime Error'
            and ('compileId' not in row or row['compileId'] == previous.COMPILE_ID)]
        a14 = [row for row in rows if row.get('backtestId') == A14_ID
            and row.get('name') == A14_NAME and row.get('status') == 'Runtime Error'
            and ('compileId' not in row or row['compileId'] == A14_COMPILE_ID)]
        a16 = [row for row in rows if row.get('backtestId') == A16_ID
            and row.get('name') == A16_NAME and row.get('status') == 'Runtime Error'
            and ('compileId' not in row or row['compileId'] == A16_COMPILE_ID)]
        a18 = [row for row in rows if row.get('backtestId') == A18_ID
            and row.get('name') == A18_NAME and row.get('status') == 'Runtime Error'
            and ('compileId' not in row or row['compileId'] == A18_COMPILE_ID)]
        require(len(manual) == len(a12) == len(a14) == len(a16) == len(a18) == 1, 'history')
        rest = [row for row in rows if row is not manual[0] and row is not a12[0]
            and row is not a14[0] and row is not a16[0] and row is not a18[0]]
        require(len(rest) == (1 if own else 0), 'history')
        if not own: return None
        row = rest[0]
        require(self._launch is not None and row.get('backtestId') == self._launch['backtest_id']
            and row.get('name') == BACKTEST_NAME and type(row.get('status')) is str and row['status'] in PENDING | TERMINAL
            and ('compileId' not in row or row['compileId'] == self._compile['compile_id']), 'status')
        return row

    def _files(self, prefix, *, expected=None, old=False):
        rows = self._call(prefix + '-files', 'files/read', {'projectId': PROJECT_ID, 'codeSourceId': CODE_SOURCE_ID}).get('files')
        require(type(rows) is list and len(rows) == 11, 'source_inventory')
        files = {}
        for row in rows:
            require(type(row) is dict and type(row.get('projectId')) is int and row['projectId'] == PROJECT_ID, 'source_inventory')
            name, text = row.get('name'), row.get('content')
            require(type(name) is str and name in self._sources and name not in files
                and type(text) is str and text.isascii() and len(text) <= 64000, 'source_bytes')
            files[name] = text.encode('ascii')
        require(set(files) == set(self._sources), 'source_inventory')
        if old:
            require(sha(canonical(self._manifest(files, OLD_PROJECTION_SHA256))) == OLD_SOURCE_MANIFEST_SHA256,
                'old_source')
            require(all(files[name] == self._sources[name] for name in files if name not in EDIT_NAMES), 'old_source')
        else:
            require(files == (self._sources if expected is None else expected), 'source_hash')
        return files

    def prepare_once(self):
        require(not self._prepared, 'prepare_once')
        self._prepared = True
        self._access('prepare-before')
        self._history('prepare-before')
        old = self._files('prepare-before', old=True)
        self._call('prepare-lock', 'projects/collaboration/lock/acquire', {'projectId': PROJECT_ID, 'codeSourceId': CODE_SOURCE_ID})
        self._locked = True
        self._access('prepare-locked')
        self._history('prepare-locked')
        require(self._files('prepare-locked', old=True) == old, 'old_source')
        for index, name in enumerate(EDIT_NAMES):
            self._call(f'prepare-write-{index:02d}', 'files/update',
                {'projectId': PROJECT_ID, 'name': name, 'content': self._sources[name].decode('ascii'), 'codeSourceId': CODE_SOURCE_ID})
            old[name] = self._sources[name]
            self._files(f'prepare-after-{index:02d}', expected=old)
        self._access('prepare-compile')
        self._history('prepare-compile')
        self._files('prepare-compile')
        self._compile_spent = True
        self._call('prepare-compile-create', 'compile/create', {'projectId': PROJECT_ID})
        return self.compile_receipt

    def _accept_compile(self, row):
        require(type(row.get('projectId', PROJECT_ID)) is int and row.get('projectId', PROJECT_ID) == PROJECT_ID, 'compile_receipt')
        self._compile = validate_compile_receipt({**_binding(), 'compile_id': row.get('compileId')})
        self._event('compile-receipt', {'event': 'compile_receipt', 'receipt': self._compile})

    def _compile_read(self, prefix):
        value = self._call(prefix + '-compile', 'compile/read', {'projectId': PROJECT_ID, 'compileId': self._compile['compile_id']})
        require(type(value.get('projectId', PROJECT_ID)) is int and value.get('projectId', PROJECT_ID) == PROJECT_ID
            and value.get('compileId') == self._compile['compile_id']
            and type(value.get('state')) is str and value['state'] in ('InQueue', 'Building', 'BuildSuccess', 'BuildError'), 'compile')
        return value

    def poll_compile(self, index):
        require(self._compile is not None and self._compile_state not in ('BuildSuccess', 'BuildError'), 'compile_once')
        require(type(index) is int and index == self._compile_count and index < COMPILE_POLLS, 'compile_budget')
        now = self._now()
        require(self._compile_time is None or now - self._compile_time >= COMPILE_INTERVAL, 'wait')
        self._compile_count += 1
        self._compile_time = now
        value = self._compile_read(f'compile-{index:03d}')
        self._compile_state = value['state']
        if value['state'] == 'BuildError': self._set_terminal(value, compile_error=True)
        return {**self._compile, 'state': value['state']}

    def _fresh(self, prefix, *, own=False):
        self._access(prefix)
        row = self._history(prefix, own=own)
        if own: require(self._terminal is not None and row['status'] == self._terminal['status'], 'status')
        self._files(prefix)
        require(self._compile_read(prefix)['state'] == 'BuildSuccess', 'compile')

    def launch_once(self):
        require(self._compile_state == 'BuildSuccess' and not self._create_spent and self._launch is None, 'launch_once')
        require(self._capacity_count < CAPACITY_POLLS, 'capacity_budget')
        now = self._now()
        require(self._capacity_time is None or now - self._capacity_time >= CAPACITY_INTERVAL, 'wait')
        index = self._capacity_count
        self._capacity_count += 1
        self._capacity_time = now
        prefix = f'launch-{index:03d}'
        self._fresh(prefix)
        capacity = previous.frozen._capacity(self._call(prefix + '-capacity', 'projects/nodes/read', {'projectId': PROJECT_ID}))
        self._event(prefix + '-capacity-valid', {'event': 'capacity', 'capacity': capacity})
        if capacity['available_count'] == 0: return {'state': 'wait', 'capacity': capacity, 'observation': index + 1}
        self._create_spent = True
        self._call('launch-create', 'backtests/create', {'projectId': PROJECT_ID,
            'compileId': self._compile['compile_id'], 'backtestName': BACKTEST_NAME})
        return {'state': 'launched', 'launch_receipt': self.launch_receipt,
            'terminal_receipt': self.terminal_receipt, 'capacity': capacity}

    def _accept_created(self, row):
        require(type(row) is dict and type(row.get('projectId')) is int and row['projectId'] == PROJECT_ID
            and row.get('name') == BACKTEST_NAME and ('compileId' not in row or row['compileId'] == self._compile['compile_id']), 'launch_receipt')
        self._launch = validate_launch_receipt({**self._compile, 'backtest_id': row.get('backtestId'), 'backtest_name': BACKTEST_NAME})
        self._event('launch-receipt', {'event': 'launch_receipt', 'receipt': self._launch})
        require(type(row.get('status')) is str and row['status'] in PENDING | TERMINAL, 'status')
        if row['status'] in TERMINAL: self._set_terminal(row)

    def _set_terminal(self, row, *, compile_error=False):
        status = 'BuildError' if compile_error else row['status']
        receipt = self._compile if compile_error else self._launch
        self._terminal = {**receipt, 'status': status}
        if status != 'Completed.':
            self._terminal['failure_evidence'] = failure_evidence(row, 'compile_error' if compile_error else 'runtime_error')
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
        if row['status'] in TERMINAL: self._set_terminal(row)
        return {**self._launch, 'status': row['status'], 'terminal': row['status'] in TERMINAL,
            'failure_evidence': self._terminal.get('failure_evidence') if self._terminal else None}

    def read_once(self):
        require(not self._read_spent, 'result_once')
        require(self._terminal is not None and self._terminal['status'] == 'Completed.', 'not_completed')
        self._read_spent = True
        self._fresh('result', own=True)
        row = self._call('result-aggregate', 'backtests/read',
            {'projectId': PROJECT_ID, 'backtestId': self._launch['backtest_id']}).get('backtest')
        require(type(row) is dict and type(row.get('projectId')) is int and row['projectId'] == PROJECT_ID
            and row.get('backtestId') == self._launch['backtest_id'] and row.get('name') == BACKTEST_NAME
            and row.get('status') == 'Completed.'
            and ('compileId' not in row or row['compileId'] == self._compile['compile_id']), 'result_identity')
        stats = row.get('statistics')
        require(type(stats) is dict, 'result_statistics')
        selected = {name: stats.get(name) for name in (previous.frozen.runtime.META_STATISTIC, previous.frozen.runtime.MONTHLY_STATISTIC)}
        require(all(type(value) is str and value.isascii() and 0 < len(value) <= previous.frozen.runtime.MAX_STATISTIC_BYTES
            for value in selected.values()), 'result_statistics')
        checked = previous.frozen.runtime.validate_result_statistics(selected, expected_profile=_copy(self._profile))
        result = {**self._launch, 'status': 'Completed.', 'cell_completed': True, 'family_comparable': False,
            'result_cell': 0, 'statistics': checked, 'expected_profile': _copy(self._profile)}
        validate_result_receipt(result)
        self._event('result-receipt', {'event': 'result_receipt', 'receipt': result})
        return _copy(result)

    def read_failure_once(self):
        """Read only this job's error projection, sharing the one-read budget.

        QC's list endpoint need not contain error details.  No statistic,
        chart, row, log or raw error string is retained from this response.
        """
        require(not self._read_spent, 'result_once')
        require(self._terminal is not None and self._terminal['status'] == 'Runtime Error', 'status')
        self._read_spent = True
        self._fresh('failure', own=True)
        row = self._call('failure-detail', 'backtests/read',
            {'projectId': PROJECT_ID, 'backtestId': self._launch['backtest_id']}).get('backtest')
        require(type(row) is dict and type(row.get('projectId')) is int and row['projectId'] == PROJECT_ID
            and row.get('backtestId') == self._launch['backtest_id'] and row.get('name') == BACKTEST_NAME
            and row.get('status') == 'Runtime Error'
            and ('compileId' not in row or row['compileId'] == self._compile['compile_id']), 'result_identity')
        earlier = self._terminal['failure_evidence']
        merged = failure_evidence(row, 'runtime_error')
        for key in ('known_runtime_code', 'diagnostic_context', 'python_error_category'):
            before, after = earlier[key], merged[key]
            require(before is None or after is None or canonical(before) == canonical(after), 'response')
            if after is None:
                merged[key] = _copy(before)
        code = merged['known_runtime_code']
        merged['known_runtime_code_sha256'] = sha(code.encode('ascii')) if code else None
        terminal = {**self._launch, 'status': 'Runtime Error', 'failure_evidence': merged}
        validate_terminal_receipt(terminal)
        self._terminal = terminal
        self._event('diagnostic-failure-receipt', {'event': 'terminal_receipt', 'receipt': terminal})
        return self.terminal_receipt
