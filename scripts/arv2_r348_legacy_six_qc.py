"""Injected first attempts for the six remaining prepared R343 plain arms.

This module is inert. The separately frozen caller must authenticate the A4
result and eight local DATA leaves before credentials or contact. Its source
pins, exclusive claims, native controls and actual-exit handling are external.
The AR100 project and four spent attempts are outside this allocation scope.
"""
from __future__ import annotations

import ast
import json
import re
import time

from scripts import arv2_r345_legacy_six_qc as base
from scripts import arv2_r347_legacy_six_qc as plain

SCHEMA = 'arv2-r348-legacy-six-qc-v1'
AR_PERCENTS = (80, 120, 140, 160, 180, 200)
CANDIDATES = tuple(f'R343-AR{value:03d}' for value in AR_PERCENTS)
ATTEMPT = 1
REFERENCE_PROJECT, REFERENCE_NAME = base.REFERENCE_PROJECT, base.REFERENCE_NAME
ORGANIZATION_SHA256 = base.ORGANIZATION_SHA256
ACTUAL_ACTIVATION = dict(plain.ACTUAL_ACTIVATION)
PLAIN_LOADER_PIN = dict(plain.PLAIN_LOADER_PIN)
COMPILE_POLLS, COMPILE_INTERVAL = base.COMPILE_POLLS, base.COMPILE_INTERVAL
CAPACITY_POLLS, CAPACITY_INTERVAL = base.CAPACITY_POLLS, base.CAPACITY_INTERVAL
STATUS_POLLS, STATUS_INTERVAL = base.STATUS_POLLS, base.STATUS_INTERVAL
PAYLOAD_KEYS = {name: set(keys) for name, keys in base.PAYLOAD_KEYS.items() if name != 'backtests/read'}
PAYLOAD_KEYS['object/properties'] = {'organizationId', 'key'}
FALSE_FLAGS = dict(plain.FALSE_FLAGS)
FINITE = base.FINITE | frozenset(('input_objects', 'source_context', 'initial_source'))
Refused, canonical, sha, require = base.Refused, base.canonical, base.sha, base.require
access_capacity = base.access_capacity


def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def _copy(value):
    return json.loads(canonical(value))


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def input_inventory(uploads):
    require(type(uploads) is tuple and len(uploads) == 6, 'input_objects')
    prefix = ACTUAL_ACTIVATION['object_store_key'].rsplit('/', 1)[0] + '/'
    descriptors, total = [], 0
    for index, (role, name, item) in enumerate(zip(plain.OBJECT_ROLES, plain.OBJECT_NAMES, uploads, strict=True)):
        require(type(item) is tuple and len(item) == 2 and type(item[0]) is dict
            and type(item[1]) is bytes, 'input_objects')
        descriptor, raw = item
        require(set(descriptor) == {'schema', 'role', 'ordinal', 'object_store_key', 'relative_path',
            'byte_count', 'content_sha256', 'record_count', 'compression', 'activation_manifest'}
            and descriptor.get('schema') == 'arv2-newrule-plain-upload-object-v1'
            and descriptor.get('role') == role and descriptor.get('relative_path') == name
            and descriptor.get('object_store_key') == prefix + name
            and type(descriptor.get('ordinal')) is int and descriptor['ordinal'] == 0
            and type(descriptor.get('record_count')) is int and descriptor['record_count'] > 0
            and type(descriptor.get('byte_count')) is int and 0 < len(raw) <= 32 * 1024 * 1024
            and descriptor['byte_count'] == len(raw) and descriptor.get('content_sha256') == sha(raw)
            and descriptor.get('compression') == 'identity'
            and descriptor.get('activation_manifest') is (index == 5), 'input_objects')
        if index == 5:
            require({key: descriptor[key] for key in ACTUAL_ACTIVATION} == ACTUAL_ACTIVATION, 'input_objects')
        total += len(raw); descriptors.append(_copy(descriptor))
    require(total <= 44 * 1024 * 1024, 'input_objects')
    return tuple(descriptors)


def check_object_metadata(response, descriptor, raw, ordinal):
    try:
        return plain.check_object_metadata(response, descriptor, raw, ordinal)
    except plain.Refused as error:
        code = plain.finite(error)
        raise Refused(code if code in FINITE else 'input_objects') from None


def validate_metadata_observation(value):
    try:
        return plain.validate_metadata_observation(value)
    except plain.Refused:
        raise Refused('shape') from None


validate_access_observation = validate_metadata_observation


def _plain_source(cell):
    selected, sources = base._cell(cell)
    require(selected['candidate_id'] in CANDIDATES and selected['ar_percent'] in AR_PERCENTS, 'scope')
    require(pin(sources['accepted_risk_order_level_input_runtime.py'].encode('ascii')) == PLAIN_LOADER_PIN,
            'source')
    tree = ast.parse(sources['main.py'])
    mapping = {'activation_manifest_key': 'object_store_key',
        'activation_manifest_sha256': 'content_sha256', 'activation_manifest_byte_count': 'byte_count'}
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and set(mapping) <= {keyword.arg for keyword in node.keywords}]
    require(len(calls) == 1, 'source')
    for keyword in calls[0].keywords:
        if keyword.arg in mapping:
            try:
                value = ast.literal_eval(keyword.value)
            except (ValueError, TypeError, SyntaxError):
                raise Refused('source') from None
            expected = ACTUAL_ACTIVATION[mapping[keyword.arg]]
            require(type(value) is type(expected) and value == expected, 'source')
    return selected, sources


class LegacySixQc(base.LegacySixQc):
    """A1 only: fresh own allocation, controlled context, eighteen exact files."""
    def __init__(self, cell, uploads, *, organization_id, user_id, attempt,
                 request, journal, clock=time.monotonic):
        self.cell, self.sources = _plain_source(cell)
        require(type(organization_id) is str and re.fullmatch('[0-9a-f]{32}', organization_id)
            and sha(organization_id.encode('ascii')) == ORGANIZATION_SHA256, 'organization')
        self.organization, self.user_id = organization_id, base._number(user_id)
        require(type(attempt) is int and attempt == ATTEMPT
            and all(callable(value) for value in (request, journal, clock)), 'arguments')
        input_inventory(uploads)
        self.uploads = tuple((_copy(row), raw) for row, raw in uploads)
        self.attempt, self.request, self.journal, self.clock = attempt, request, journal, clock
        self.candidate = self.cell['candidate_id']
        self.name = f'ARV2 LEGACY SIX {self.candidate} OCT2026'
        self.backtest_name = f'{self.name} A1'
        self.code_source = f'Codex R348 {self.candidate} A1'
        self.project_id = self.compile_id = self.launch_receipt = self.terminal_receipt = None
        self._used, self._times, self._listed_ids = set(), {}, set()
        self._count = self._compile_count = self._capacity_count = self._status_count = 0
        self._last_clock = None
        self._begun = self._lock = self._launch_spent = self._result_spent = False
        self._compile_success = self._acquire_dispatched = self._acquire_ack = False
        self._allocation = self._owner_raw = self._general_pin = None
        self._file_dispatches = set()
        self._compile_dispatched = self._notebook_deleted = False
        self.launch_status = None
        self.last_request = self.last_failure = self.last_access_observation = None
        self.source_progress, self.metadata_admissions = [], []

    def _call(self, marker, endpoint, payload):
        require(type(endpoint) is str and endpoint in PAYLOAD_KEYS and type(payload) is dict, 'request')
        extra = endpoint == 'object/properties' or (endpoint == 'files/read' and marker == 'created-initial-files')
        if not extra:
            if endpoint in ('files/create', 'files/update'):
                name = payload.get('name')
                require(type(name) is str and name in self.sources and name not in self._file_dispatches,
                        'source_changed')
                self._file_dispatches.add(name)
            if endpoint == 'files/delete':
                require(marker == 'delete-default-notebook' and not self._notebook_deleted
                    and payload.get('name') == 'research.ipynb', 'scope')
                self._notebook_deleted = True
            if endpoint == 'projects/collaboration/lock/acquire':
                require(self._acquire_dispatched and not self._acquire_ack, 'source_context')
            if endpoint == 'compile/create':
                require(marker == 'compile-create' and not self._compile_dispatched, 'compile')
                self._compile_dispatched = True
            result = super()._call(marker, endpoint, payload)
            if endpoint == 'backtests/create':
                row = result.get('backtest')
                if type(row) is dict and row.get('status') in base.PENDING | base.TERMINAL:
                    self.launch_status = row['status']
            return result
        require(type(marker) is str and re.fullmatch('[a-z0-9-]{1,100}', marker)
            and marker not in self._used and self._count < base.MAX_DISPATCHES, 'request')
        if endpoint == 'object/properties':
            require(set(payload) == PAYLOAD_KEYS[endpoint] and payload['organizationId'] == self.organization
                and payload['key'] in {row['object_store_key'] for row, _ in self.uploads}, 'input_objects')
        else:
            self._require_allocation()
            require(payload == {'projectId': self.project_id} and not self._lock, 'source_context')
        self._used.add(marker); self._count += 1
        self.last_request = {'endpoint': endpoint, 'marker': marker, 'payload_sha256': sha(canonical(payload))}
        self.last_failure = {**self.last_request, 'stage': 'intent_or_request_unaccepted'}
        self._event(marker + '-intent', self.last_request)
        try:
            response = self.request(endpoint, _copy(payload))
        except Exception:
            raise Refused('request_ambiguous') from None
        raw = canonical(response); require(0 < len(raw) <= base.MAX_RESPONSE, 'bound')
        self.last_failure = {**self.last_request, 'stage': 'response_unaccepted',
                             'response_bytes': len(raw), 'response_sha256': sha(raw)}
        self._event(marker + '-observed', {'endpoint': endpoint, **pin(raw)})
        base._empty_errors(response); self.last_failure = None
        return _copy(response)

    def _require_allocation(self):
        super()._require_allocation()
        require(self.candidate in CANDIDATES and self.attempt == ATTEMPT
            and self.name == f'ARV2 LEGACY SIX {self.candidate} OCT2026'
            and self.code_source == f'Codex R348 {self.candidate} A1'
            and type(self.project_id) is int and 0 < self.project_id < 2**63
            and self.project_id not in self._listed_ids | {REFERENCE_PROJECT, plain.PROJECT}, 'scope')

    def _access(self, prefix, *, transition=False):
        self._require_allocation()
        packet = self._call(prefix + '-project', 'projects/read', {'projectId': self.project_id})
        require('projectId' not in packet or type(packet['projectId']) is int
            and packet['projectId'] == self.project_id, 'scope')
        self.last_access_observation = validate_metadata_observation(plain.previous.owned_access_observation(packet))
        self._event(prefix + '-owned-access-metadata', self.last_access_observation)
        rows = packet.get('projects')
        require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'project_identity')
        row = rows[0]
        require(type(row.get('projectId')) is int and row['projectId'] == self.project_id
            and row.get('name') == self.name and row.get('language') == 'Py', 'project_identity')
        require(row.get('organizationId') == self.organization, 'organization')
        require(row.get('owner') is True and type(row.get('ownerId')) is int
            and row['ownerId'] == self.user_id, 'owner')
        require(row.get('codeRunning') is False, 'idle')
        require('public' not in row or row['public'] is False, 'private')
        require(type(row.get('libraries')) is list and not row['libraries']
            and ('isLibrary' not in row or row['isLibrary'] is False)
            and ('libraryIds' not in row or type(row['libraryIds']) is list and not row['libraryIds']), 'libraries')
        require('lastLiveDeployment' in row and row['lastLiveDeployment'] in (None, '')
            and type(row.get('leanEnvironment')) is int and row['leanEnvironment'] >= 0, 'live')
        for field in ('liveMode', 'liveRunning', 'live'):
            require(field not in row or row[field] is False, 'live')
        require('liveResults' not in row or type(row['liveResults']) is list and not row['liveResults'], 'live')
        general = row.get('collaborators')
        require(type(general) is list and len(general) == (2 if transition or self._lock else 1)
            and all(type(item) is dict for item in general), 'collaborators')
        owners = [item for item in general if item.get('owner') is True]
        require(len(owners) == 1 and type(owners[0].get('uid')) is int and owners[0]['uid'] == self.user_id,
                'collaborators')
        dedicated = self._call(prefix + '-collaborators', 'projects/collaboration/read',
                               {'projectId': self.project_id})
        require('organizationId' not in dedicated or dedicated['organizationId'] == self.organization, 'scope')
        base._dedicated(dedicated, self.project_id, self.user_id, owners[0])
        owner_raw = canonical(owners[0])
        if self._owner_raw is None:
            self._owner_raw, self._general_pin = owner_raw, pin(canonical(general))
        require(self._owner_raw == owner_raw, 'collaborators')
        if transition:
            require(self._acquire_ack and not self._lock, 'source_context')
            extra = [item for item in general if item is not owners[0]][0]
            require(set(extra) == {'uid', 'owner', 'name', 'publicId', 'permission', 'liveControl',
                'profileImage', 'email', 'bio'} and extra['uid'] is None and extra['owner'] is False
                and extra['name'] == self.code_source and extra['permission'] == 'write'
                and extra['liveControl'] is True and type(extra['publicId']) is str
                and 0 < len(extra['publicId']) <= 1024
                and all(type(extra[key]) is str and len(extra[key]) <= 65536
                    for key in ('profileImage', 'email', 'bio')) and len(canonical(extra)) <= 65536, 'source_context')
            self._general_pin = pin(canonical(general))
        else:
            require(pin(canonical(general)) == self._general_pin, 'collaborators')
        if self.launch_receipt is None and not self._launch_spent:
            self._history(prefix + '-privacy')
        else:
            require(row.get('public') is False, 'private')

    def _initial_files(self):
        packet = self._call('created-initial-files', 'files/read', {'projectId': self.project_id})
        rows, initial = packet.get('files'), {}
        require(type(rows) is list and 1 <= len(rows) <= 2, 'initial_source')
        for row in rows:
            require(type(row) is dict and type(row.get('projectId')) is int
                and row['projectId'] == self.project_id and row.get('name') in ('main.py', 'research.ipynb')
                and row['name'] not in initial and type(row.get('content')) is str
                and row['content'].isascii() and 0 < len(row['content']) <= 262144, 'initial_source')
            initial[row['name']] = row['content']
        require(initial.get('main.py') in (plain.previous.DEFAULT_MAIN, '#', '#\n'), 'initial_source')
        self._event('new-allocation-initial-inventory', {'files': [
            {'project_path': name, **pin(raw.encode('ascii'))} for name, raw in sorted(initial.items())]})
        return initial

    def _inputs(self, prefix):
        observations = []
        for index, (descriptor, raw) in enumerate(self.uploads):
            response = self._call(f'{prefix}-object-{index}', 'object/properties',
                {'organizationId': self.organization, 'key': descriptor['object_store_key']})
            observations.append(check_object_metadata(response, descriptor, raw, index))
        self.metadata_admissions.append({'phase': prefix, 'objects': observations})
        self._event(prefix + '-input-metadata', self.metadata_admissions[-1])

    @property
    def input_admission(self):
        return _copy(self.metadata_admissions[-1]['objects']) if self.metadata_admissions else None

    def begin_once(self):
        require(not self._begun, 'state'); self._begun = True
        self._call('begin-auth', 'authenticate', {})
        listing = self._call('begin-names', 'projects/read', {}).get('projects')
        require(type(listing) is list and len(listing) <= 1000 and all(type(row) is dict
            and type(row.get('name')) is str and row['name'] != self.name
            and type(row.get('projectId')) is int and 0 < row['projectId'] < 2**63 for row in listing), 'project_name')
        self._listed_ids = {row['projectId'] for row in listing}
        require(len(self._listed_ids) == len(listing), 'project_identity')
        packet = self._call('begin-reference', 'projects/read', {'projectId': REFERENCE_PROJECT})
        base._project(packet, REFERENCE_PROJECT, REFERENCE_NAME, self.organization, self.user_id, idle=False)
        capacity = base.capacity(self._call('begin-capacity', 'projects/nodes/read', {'projectId': REFERENCE_PROJECT}))
        if capacity['available_count'] == 0:
            return {'state': 'wait', 'capacity': capacity, 'project_id': None}
        self._inputs('begin')
        self._call('begin-create', 'projects/create',
                   {'name': self.name, 'language': 'Py', 'organizationId': self.organization})
        self._require_allocation(); self._access('created')
        initial = self._initial_files()
        self._acquire_dispatched = True
        self._call('begin-lock', 'projects/collaboration/lock/acquire',
                   {'projectId': self.project_id, 'codeSourceId': self.code_source})
        self._acquire_ack = True
        self._access('controlled-transition', transition=True); self._lock = True
        self._event('source-context-created', {'project_id': self.project_id,
            'code_source_sha256': sha(self.code_source.encode('ascii')),
            'general_rows_pin': self._general_pin, 'exclusive_resource_lease': False})
        self._files('locked-initial', initial)
        expected = dict(initial)
        if 'research.ipynb' in expected:
            self._access('notebook-preflight'); self._files('notebook-preflight', expected)
            self._call('delete-default-notebook', 'files/delete', {'projectId': self.project_id,
                'name': 'research.ipynb', 'codeSourceId': self.code_source})
            del expected['research.ipynb']
        names = [name for name in sorted(self.sources) if name != 'main.py'] + ['main.py']
        for index, name in enumerate(names):
            self._access(f'write-{index:02d}'); self._files(f'write-{index:02d}', expected)
            self._call(f'write-{index:02d}-source', 'files/update' if name in expected else 'files/create',
                {'projectId': self.project_id, 'name': name, 'content': self.sources[name],
                 'codeSourceId': self.code_source})
            expected[name] = self.sources[name]
            progress = {'project_path': name, 'action': 'written', **pin(self.sources[name].encode('ascii'))}
            self.source_progress.append(progress); self._event(f'progress-{index:02d}', progress)
        self._access('compiled-preflight'); self._history('compiled-preflight')
        self._files('compiled-preflight', self.sources)
        result = self._call('compile-create', 'compile/create', {'projectId': self.project_id})
        self.compile_id = base._id(result.get('compileId'))
        require('projectId' not in result or type(result['projectId']) is int
            and result['projectId'] == self.project_id, 'scope')
        self._event('compile-created', {'project_id': self.project_id, 'compile_id': self.compile_id})
        return {'state': 'compiling', 'project_id': self.project_id, 'compile_id': self.compile_id}

    def launch_once(self):
        require(self._compile_success and not self._launch_spent and self.terminal_receipt is None
            and self._capacity_count < CAPACITY_POLLS, 'state')
        now = self._now()
        require('capacity' not in self._times or now - self._times['capacity'] >= CAPACITY_INTERVAL, 'wait')
        self._inputs(f'launch-{self._capacity_count}')
        result = super().launch_once()
        if result['state'] == 'launched':
            result['launch_status'] = self.launch_status
        return result

    def read_statistics_once(self):
        raise Refused('scope')


def profile_record():
    return {'schema': SCHEMA, 'candidate_ids': list(CANDIDATES), 'attempt': ATTEMPT,
        'new_projects_only': True, 'AR100_and_A4_replay_permitted': False,
        'prior_A4_result_acceptance_external_required': True,
        'maximum_attempts_per_candidate': 3, 'automatic_retry_permitted': False,
        'source_file_count': 18, 'main_last': True, 'lock_release_calls': 0,
        'object_policy': 'fresh_properties_key_size_MD5_only_runtime_SHA256_required_no_GET_or_set',
        'optional_notebook_delete': 'only_initial_observed_rechecked_new_own_allocation_research.ipynb_once',
        'privacy_policy': 'new_allocation_current_owner_only_empty_history_explicit_contradictions_refuse',
        'source_context_policy': 'own_ACK_one_technical_row_transition_then_exact_full_vector_pin',
        'result_reads': 0, 'compile_polls': COMPILE_POLLS, 'compile_interval': COMPILE_INTERVAL,
        'capacity_polls': CAPACITY_POLLS, 'capacity_interval': CAPACITY_INTERVAL,
        'status_polls': STATUS_POLLS, 'status_interval': STATUS_INTERVAL,
        **FALSE_FLAGS}
