"""Injected, owner-authorized A4 recovery of the same R343-AR100 project.

No client, credential, file, network or operational entry point exists here.
The separately frozen caller owns current provenance, native controls, the
exclusive A4 claim and actual-exit evidence. The old three attempts remain
spent. Object properties are qualified metadata, never remote SHA attestation;
the exact prepared cloud loader must hash every input before it is consumed.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import time

from scripts import arv2_r345_legacy_six_qc_v3 as previous


SCHEMA = 'arv2-r347-legacy-six-qc-v1'
PROJECT = 39054561
CANDIDATE = 'R343-AR100'
ATTEMPT = 4
ORGANIZATION_SHA256 = previous.ORGANIZATION_SHA256
ACTUAL_PLAIN_PACKAGE_SHA256 = '1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2'
ACTUAL_ACTIVATION = {'object_store_key': 'arv2/newrule-plain-v1/95405d1b569d4bfeeb6c6d87/transport-manifest.json',
    'content_sha256': 'ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b', 'byte_count': 5901}
PLAIN_LOADER_PIN = {'byte_count': 16093, 'sha256': 'b3f48e1b1c6fc6cc665d9f8b475292260074feec5571eab6e8f0d1c1a091fd35'}
OBJECT_NAMES = ('evaluator-manifest.json', 'session_axis-0000.jsonl', 'memberships-0000.jsonl',
    'contributions-0000.jsonl', 'runtime_symbol_bindings-0000.jsonl', 'transport-manifest.json')
OBJECT_ROLES = ('evaluator_manifest', 'session_axis', 'memberships', 'contributions',
                'runtime_symbol_bindings', 'activation_manifest')
RECONCILIATION_PIN = {'byte_count': 7353, 'sha256': '9193129dc41eba2c7ee735e740b9310f69c14fca7a63e84e4eab7caa49307608'}
CONTEXT_MODE = 'fresh_A4_acquire_from_exact_owner_only_state'
CODE_SOURCE_ID = 'Codex R347 R343-AR100 A4'
OWNER_ROWS_PIN = {'byte_count': 266, 'sha256': '17629cbf0728da4646158efdc2251d502b969c112d962231105fe8b6b11c80af'}
INITIAL_INVENTORY_PIN = {'byte_count': 728, 'sha256': '82b9b3ea518911e7cbe57e2d270da0b6693d8ee1bbc5e758ad4a7d6fa743bb6c'}
PAYLOAD_KEYS = {key: set(value) for key, value in previous.PAYLOAD_KEYS.items()
                if key not in ('backtests/read', 'files/delete')}
PAYLOAD_KEYS.update({'object/properties': {'organizationId', 'key'},
    'projects/collaboration/lock/acquire': {'projectId', 'codeSourceId'}})
canonical, sha, require = previous.canonical, previous.sha, previous.require
Refused = previous.Refused
REFERENCE_PROJECT = previous.REFERENCE_PROJECT
COMPILE_POLLS, COMPILE_INTERVAL = previous.COMPILE_POLLS, previous.COMPILE_INTERVAL
CAPACITY_POLLS, CAPACITY_INTERVAL = previous.CAPACITY_POLLS, previous.CAPACITY_INTERVAL
STATUS_POLLS, STATUS_INTERVAL = 30, previous.STATUS_INTERVAL
access_capacity = previous.access_capacity
FINITE = previous.FINITE | frozenset(('reconciliation', 'input_objects', 'source_context', 'initial_source'))
FALSE_FLAGS = dict(previous.FALSE_FLAGS, remote_payload_sha256_attested=False,
    physical_request_count_measured=False, continuous_privacy_proven=False,
    exclusive_resource_lease=False, attempt_budget_reset=False)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def pin(raw):
    return {'byte_count': len(raw), 'sha256': sha(raw)}


def _copy(value):
    return json.loads(canonical(value))


def input_inventory(uploads):
    """Check the exact six supplied plaintext buffers, not their provenance."""
    require(type(uploads) is tuple and len(uploads) == 6, 'input_objects')
    prefix = ACTUAL_ACTIVATION['object_store_key'].rsplit('/', 1)[0] + '/'
    descriptors, total = [], 0
    for ordinal, (role, name, item) in enumerate(zip(OBJECT_ROLES, OBJECT_NAMES, uploads, strict=True)):
        require(type(item) is tuple and len(item) == 2 and type(item[0]) is dict
            and type(item[1]) is bytes, 'input_objects')
        descriptor, raw = item
        require(set(descriptor) == {'schema', 'role', 'ordinal', 'object_store_key', 'relative_path',
            'byte_count', 'content_sha256', 'record_count', 'compression', 'activation_manifest'}
            and descriptor.get('schema') == 'arv2-newrule-plain-upload-object-v1'
            and type(descriptor.get('record_count')) is int and descriptor['record_count'] > 0
            and type(descriptor.get('byte_count')) is int and 0 < len(raw) <= 32 * 1024 * 1024
            and descriptor['byte_count'] == len(raw) and descriptor.get('content_sha256') == sha(raw)
            and descriptor.get('object_store_key') == prefix + name
            and descriptor.get('relative_path') == name and descriptor.get('role') == role
            and type(descriptor.get('ordinal')) is int and descriptor['ordinal'] == 0
            and descriptor.get('compression') == 'identity'
            and descriptor.get('activation_manifest') is (ordinal == 5), 'input_objects')
        if ordinal == 5:
            require({key: descriptor[key] for key in ACTUAL_ACTIVATION} == ACTUAL_ACTIVATION,
                    'input_objects')
        descriptors.append(_copy(descriptor)); total += len(raw)
    require(total <= 44 * 1024 * 1024, 'input_objects')
    return tuple(descriptors)


def check_object_metadata(response, descriptor, raw, ordinal):
    """Fresh key/size/MD5 comparison only. Never download Object Store DATA."""
    previous._empty_errors(response)
    row = response.get('metadata')
    local_md5 = hashlib.md5(raw, usedforsecurity=False).hexdigest()
    require(type(row) is dict and row.get('key') == descriptor['object_store_key']
        and type(row.get('size')) is int and row['size'] == len(raw)
        and type(row.get('md5')) is str and re.fullmatch('[0-9a-fA-F]{32}', row['md5'])
        and row['md5'].casefold() == local_md5, 'input_objects')
    return {'ordinal': ordinal, 'key_sha256': sha(descriptor['object_store_key'].encode('ascii')),
        'byte_count': len(raw), 'local_payload_sha256': sha(raw), 'metadata_md5': local_md5,
        'verification': 'fresh_properties_key_size_MD5_only_runtime_SHA256_required',
        **FALSE_FLAGS}


def _plain_source(cell):
    value, sources = previous._cell(cell)
    require(value['candidate_id'] == CANDIDATE and value['ar_percent'] == 100, 'scope')
    require(pin(sources['accepted_risk_order_level_input_runtime.py'].encode('ascii')) == PLAIN_LOADER_PIN,
            'source')
    tree = ast.parse(sources['main.py'])
    mapping = {'activation_manifest_key': 'object_store_key',
        'activation_manifest_sha256': 'content_sha256', 'activation_manifest_byte_count': 'byte_count'}
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and set(mapping) <= {item.arg for item in node.keywords}]
    require(len(calls) == 1, 'source')
    for keyword in calls[0].keywords:
        if keyword.arg in mapping:
            try: actual = ast.literal_eval(keyword.value)
            except (ValueError, TypeError, SyntaxError): raise Refused('source') from None
            expected = ACTUAL_ACTIVATION[mapping[keyword.arg]]
            require(type(actual) is type(expected) and actual == expected, 'source')
    return value, sources


def current_fact(value):
    """Validate the exact original read-only observation, not a write permit."""
    if type(value) is dict:
        candidate = canonical(value)
        variants = (candidate, candidate + b'\n')
    else:
        require(type(value) is bytes, 'reconciliation'); variants = (value,)
    selected = [raw for raw in variants if pin(raw) == RECONCILIATION_PIN]
    require(len(selected) == 1, 'reconciliation')
    try: record = json.loads(selected[0])
    except (ValueError, UnicodeError, RecursionError): raise Refused('reconciliation') from None
    require(type(record) is dict and record.get('schema') == 'arv2-r347-current-project-state-fact-v1'
        and type(record.get('external_observation')) is dict
        and type(record['external_observation'].get('actual_exit')) is int
        and record['external_observation']['actual_exit'] == 0
        and type(record.get('original_envelope')) is dict
        and type(record['original_envelope'].get('result')) is dict, 'reconciliation')
    result = record['original_envelope']['result']
    require(result.get('schema') == 'arv2-r347-QC-readonly-plain-recovery-state-v1'
        and type(result.get('project_id')) is int and result['project_id'] == PROJECT
        and result.get('complete') is True and result.get('dedicated_owner_only') is True
        and result.get('current_editor_idle') is True and type(result.get('current_job_count')) is int
        and result['current_job_count'] == 0
        and result.get('empty_current_history') is True and result.get('whole_owner_row_agreement') is True
        and result.get('general_row_count') == result.get('dedicated_row_count') == 1
        and result.get('unrecognized_file_count') == 0 and result.get('source_file_count') == 5,
        'reconciliation')
    return selected[0], _copy(result)


def validate_metadata_observation(value):
    return previous.validate_metadata_observation(value)


validate_access_observation = validate_metadata_observation


class LegacySixQc(previous.LegacySixQc):
    """One additional A4; reused methods carry no old attempt authority."""
    def __init__(self, cell, uploads, *, organization_id, user_id, attempt, reconciliation_fact,
                 request, journal, clock=time.monotonic):
        self.cell, self.sources = _plain_source(cell)
        self._fact, self._observed = current_fact(reconciliation_fact)
        require(self._observed['general_rows_pin'] == OWNER_ROWS_PIN
            and self._observed['dedicated_rows_pin'] == OWNER_ROWS_PIN
            and self._observed['source_inventory_pin'] == INITIAL_INVENTORY_PIN, 'reconciliation')
        require(type(organization_id) is str and re.fullmatch('[0-9a-f]{32}', organization_id)
            and sha(organization_id.encode('ascii')) == ORGANIZATION_SHA256, 'organization')
        self.organization = organization_id
        self.user_id = previous._number(user_id)
        require(type(attempt) is int and attempt == ATTEMPT
            and all(callable(value) for value in (request, journal, clock)), 'arguments')
        input_inventory(uploads)
        self.uploads = tuple((_copy(descriptor), raw) for descriptor, raw in uploads)
        self.attempt, self.request, self.journal, self.clock = attempt, request, journal, clock
        self.candidate, self.project_id = CANDIDATE, PROJECT
        self.name = 'ARV2 LEGACY SIX R343-AR100 OCT2026'
        self.backtest_name = self.name + ' A4'
        self.code_source = CODE_SOURCE_ID
        self.compile_id = self.launch_receipt = self.terminal_receipt = None
        self._used, self._times = set(), {}
        self._count = self._compile_count = self._capacity_count = self._status_count = 0
        self._last_clock = None
        self._begun = self._source_context = self._launch_spent = self._result_spent = False
        self._compile_success = self._acquire_dispatched = self._acquire_ack = False
        self._file_dispatches = set()
        self._compile_dispatched = False
        self.launch_status = None
        self.last_request = self.last_failure = self.last_access_observation = None
        self._general_pin = dict(OWNER_ROWS_PIN)
        self._owner_row = None
        self.source_progress, self.metadata_admissions = [], []

    def _call(self, marker, endpoint, payload):
        require(type(endpoint) is str and endpoint in PAYLOAD_KEYS and type(payload) is dict, 'request')
        extra = endpoint in ('object/properties', 'projects/collaboration/lock/acquire') \
            or (endpoint == 'files/read' and marker == 'initial-plain-inventory')
        if not extra:
            if endpoint in ('files/create', 'files/update'):
                name = payload.get('name')
                require(type(name) is str and name in self.sources and name not in self._file_dispatches,
                        'source_changed')
                self._file_dispatches.add(name)
            if endpoint == 'compile/create':
                require(marker == 'a4-compile-create' and not self._compile_dispatched, 'compile')
                self._compile_dispatched = True
            value = super()._call(marker, endpoint, payload)
            if endpoint == 'backtests/create':
                row = value.get('backtest')
                if type(row) is dict and row.get('status') in previous.PENDING | previous.TERMINAL:
                    self.launch_status = row['status']
            return value
        require(type(marker) is str and re.fullmatch('[a-z0-9-]{1,100}', marker)
            and marker not in self._used and self._count < previous.MAX_DISPATCHES, 'request')
        if endpoint == 'object/properties':
            require(set(payload) == PAYLOAD_KEYS[endpoint] and payload['organizationId'] == self.organization
                and payload['key'] in {row['object_store_key'] for row, _ in self.uploads}, 'input_objects')
        elif endpoint == 'projects/collaboration/lock/acquire':
            require(marker == 'a4-lock-acquire' and self._acquire_dispatched and not self._acquire_ack
                and payload == {'projectId': PROJECT, 'codeSourceId': CODE_SOURCE_ID}, 'source_context')
        else:
            require(payload == {'projectId': PROJECT} and not self._source_context, 'source_context')
        self._used.add(marker); self._count += 1
        self.last_request = {'endpoint': endpoint, 'marker': marker, 'payload_sha256': sha(canonical(payload))}
        self.last_failure = {**self.last_request, 'stage': 'intent_or_request_unaccepted'}
        self._event(marker + '-intent', self.last_request)
        try: response = self.request(endpoint, _copy(payload))
        except Exception: raise Refused('request_ambiguous') from None
        raw = canonical(response); require(0 < len(raw) <= previous.MAX_RESPONSE, 'bound')
        self.last_failure = {**self.last_request, 'stage': 'response_unaccepted', **pin(raw)}
        self._event(marker + '-observed', {'endpoint': endpoint, **pin(raw)})
        previous._empty_errors(response); self.last_failure = None
        return _copy(response)

    def _access(self, prefix, *, transition=False):
        current_fact(self._fact)
        require(self.project_id == PROJECT and self.attempt == ATTEMPT and self.code_source == CODE_SOURCE_ID,
                'reconciliation')
        packet = self._call(prefix + '-project', 'projects/read', {'projectId': PROJECT})
        require('projectId' not in packet or type(packet['projectId']) is int and packet['projectId'] == PROJECT,
                'scope')
        self.last_access_observation = previous.validate_metadata_observation(previous.owned_access_observation(packet))
        self._event(prefix + '-owned-access-metadata', self.last_access_observation)
        rows = packet.get('projects')
        require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'project_identity')
        row = rows[0]
        require(type(row.get('projectId')) is int and row['projectId'] == PROJECT
            and row.get('name') == self.name and row.get('language') == 'Py', 'project_identity')
        require(row.get('organizationId') == self.organization, 'organization')
        require(row.get('owner') is True and type(row.get('ownerId')) is int
            and row['ownerId'] == self.user_id, 'owner')
        require(row.get('codeRunning') is False, 'idle')
        require('public' not in row or row['public'] is False, 'private')
        require(type(row.get('libraries')) is list and not row['libraries']
            and ('isLibrary' not in row or row['isLibrary'] is False), 'libraries')
        require('libraryIds' not in row or type(row['libraryIds']) is list and not row['libraryIds'], 'libraries')
        require('lastLiveDeployment' in row and row['lastLiveDeployment'] in (None, '')
            and type(row.get('leanEnvironment')) is int and row['leanEnvironment'] >= 0, 'live')
        for field in ('liveMode', 'liveRunning', 'live'):
            require(field not in row or row[field] is False, 'live')
        require('liveResults' not in row or type(row['liveResults']) is list and not row['liveResults'], 'live')
        general = row.get('collaborators')
        require(type(general) is list and len(general) == (2 if transition or self._source_context else 1)
            and all(type(item) is dict for item in general), 'collaborators')
        owners = [item for item in general if item.get('owner') is True]
        require(len(owners) == 1 and type(owners[0].get('uid')) is int and owners[0]['uid'] == self.user_id,
                'collaborators')
        dedicated = self._call(prefix + '-collaborators', 'projects/collaboration/read', {'projectId': PROJECT})
        require('projectId' not in dedicated or type(dedicated['projectId']) is int and dedicated['projectId'] == PROJECT,
                'scope')
        require('organizationId' not in dedicated or dedicated['organizationId'] == self.organization, 'scope')
        owner_rows = dedicated.get('collaborators')
        require(type(owner_rows) is list and pin(canonical(owner_rows)) == OWNER_ROWS_PIN
            and len(owner_rows) == 1 and canonical(owner_rows[0]) == canonical(owners[0])
            and owners[0].get('permission') == 'write' and owners[0].get('liveControl') is True
            and dedicated.get('userPermissions') == 'write' and dedicated.get('userLiveControl') is True,
            'collaborators')
        if transition:
            require(self._acquire_ack and not self._source_context and self._owner_row == canonical(owners[0]),
                    'source_context')
            extra_rows = [item for item in general if item is not owners[0]]
            extra_row = extra_rows[0]
            require(set(extra_row) == {'uid', 'owner', 'name', 'publicId', 'permission', 'liveControl',
                    'profileImage', 'email', 'bio'}
                and extra_row['uid'] is None and extra_row['owner'] is False
                and extra_row['name'] == CODE_SOURCE_ID and extra_row['permission'] == 'write'
                and extra_row['liveControl'] is True and type(extra_row['publicId']) is str
                and 0 < len(extra_row['publicId']) <= 1024
                and all(type(extra_row[key]) is str and len(extra_row[key]) <= 65536
                    for key in ('profileImage', 'email', 'bio'))
                and len(canonical(extra_row)) <= 65536, 'source_context')
            # The only admitted transition is the sole owner plus one context
            # created after our own ACK; the full observed vector is then fixed.
            self._general_pin = pin(canonical(general))
        else:
            require(pin(canonical(general)) == self._general_pin, 'collaborators')
        if self._owner_row is None: self._owner_row = canonical(owners[0])
        else: require(self._owner_row == canonical(owners[0]), 'collaborators')
        if self.launch_receipt is None and not self._launch_spent:
            self._history(prefix + '-privacy')
        else:
            require(row.get('public') is False, 'private')

    def _initial_inventory(self):
        value = self._call('initial-plain-inventory', 'files/read', {'projectId': PROJECT})
        rows, result = value.get('files'), {}
        require(type(rows) is list and len(rows) == 5, 'initial_source')
        vector = []
        for row in rows:
            require(type(row) is dict and type(row.get('projectId')) is int and row['projectId'] == PROJECT
                and type(row.get('name')) is str and row['name'] in self.sources
                and row['name'] not in result and type(row.get('content')) is str
                and row['content'].isascii() and 0 < len(row['content']) <= 64000, 'initial_source')
            result[row['name']] = row['content']
            vector.append({'project_path': row['name'], **pin(row['content'].encode('ascii'))})
        vector.sort(key=lambda item: item['project_path'])
        require(pin(canonical(vector)) == INITIAL_INVENTORY_PIN
            and canonical(vector) == canonical(self._observed['source_inventory']), 'initial_source')
        # Exactly the previously accepted modules, one-byte stub and default
        # main are admitted. Unknown edits are never overwritten.
        for name, text in result.items():
            require(text == self.sources[name] or (name == 'accepted_risk_order_level_input_runtime.py'
                and text == '#') or (name == 'main.py' and text == previous.DEFAULT_MAIN), 'initial_source')
        return result

    def _inputs(self, prefix):
        summaries = []
        for ordinal, (descriptor, raw) in enumerate(self.uploads):
            value = self._call(f'{prefix}-object-{ordinal}', 'object/properties',
                {'organizationId': self.organization, 'key': descriptor['object_store_key']})
            summaries.append(check_object_metadata(value, descriptor, raw, ordinal))
        self.metadata_admissions.append({'phase': prefix, 'objects': summaries})
        self._event(prefix + '-input-metadata', self.metadata_admissions[-1])

    @property
    def input_admission(self):
        """Last complete six-object metadata observation, never remote SHA proof."""
        return _copy(self.metadata_admissions[-1]['objects']) if self.metadata_admissions else None

    def begin_once(self):
        require(not self._begun, 'state'); self._begun = True
        self._call('begin-auth', 'authenticate', {})
        self._access('a4-initial')
        expected = self._initial_inventory()
        self._inputs('begin')
        observed = previous.capacity(self._call('a4-capacity', 'projects/nodes/read', {'projectId': PROJECT}))
        if observed['available_count'] == 0:
            return {'state': 'wait', 'capacity': observed, 'project_id': PROJECT}
        self._acquire_dispatched = True
        self._call('a4-lock-acquire', 'projects/collaboration/lock/acquire',
                   {'projectId': PROJECT, 'codeSourceId': CODE_SOURCE_ID})
        self._acquire_ack = True
        self._access('a4-controlled-transition', transition=True)
        self._source_context = True
        self._event('a4-source-context', {'mode': CONTEXT_MODE, 'general_rows_pin': self._general_pin,
            'code_source_sha256': sha(CODE_SOURCE_ID.encode('ascii')), 'exclusive_resource_lease': False})
        self._files('a4-post-context', expected)
        names = [name for name in sorted(self.sources) if name != 'main.py'] + ['main.py']
        for index, name in enumerate(names):
            self._access(f'a4-write-{index:02d}'); self._files(f'a4-write-{index:02d}', expected)
            target = self.sources[name]
            if expected.get(name) == target:
                progress = {'project_path': name, 'action': 'already_exact_skip', **pin(target.encode('ascii'))}
            else:
                endpoint = 'files/update' if name in expected else 'files/create'
                self._call(f'a4-write-{index:02d}-source', endpoint, {'projectId': PROJECT,
                    'name': name, 'content': target, 'codeSourceId': CODE_SOURCE_ID})
                expected[name] = target
                progress = {'project_path': name, 'action': endpoint, **pin(target.encode('ascii'))}
            self.source_progress.append(progress); self._event(f'a4-progress-{index:02d}', progress)
        self._access('a4-compile-preflight'); self._history('a4-compile-preflight')
        self._files('a4-compile-preflight', self.sources)
        result = self._call('a4-compile-create', 'compile/create', {'projectId': PROJECT})
        self.compile_id = previous._id(result.get('compileId'))
        require('projectId' not in result or type(result['projectId']) is int and result['projectId'] == PROJECT, 'scope')
        self._event('compile-created', {'project_id': PROJECT, 'compile_id': self.compile_id})
        return {'state': 'compiling', 'project_id': PROJECT, 'compile_id': self.compile_id}

    def launch_once(self):
        require(self._compile_success and not self._launch_spent and self.terminal_receipt is None
            and self._capacity_count < previous.CAPACITY_POLLS, 'state')
        now = self._now()
        require('capacity' not in self._times or now - self._times['capacity'] >= previous.CAPACITY_INTERVAL, 'wait')
        self._inputs(f'launch-{self._capacity_count}')
        result = super().launch_once()
        if result['state'] == 'launched':
            result['launch_status'] = self.launch_status
        return result

    def poll_status(self, index):
        require(type(index) is int and 0 <= index < STATUS_POLLS, 'status_budget')
        return super().poll_status(index)

    def read_statistics_once(self):
        raise Refused('scope')


def profile_record():
    return {'schema': SCHEMA, 'candidate_id': CANDIDATE, 'attempt': ATTEMPT,
        'project_id': PROJECT, 'reconciliation_pin': RECONCILIATION_PIN, 'context_mode': CONTEXT_MODE,
        'status': 'new_A4_contract_requires_separate_clean_run_freeze',
        'object_reads': 'properties_only_no_GET_or_download',
        'object_integrity': 'fresh_key_size_MD5_metadata_and_mandatory_cloud_runtime_SHA256',
        'actual_plain_package_sha256': ACTUAL_PLAIN_PACKAGE_SHA256,
        'actual_activation': dict(ACTUAL_ACTIVATION), 'plain_loader_pin': dict(PLAIN_LOADER_PIN),
        'owner_rows_pin': dict(OWNER_ROWS_PIN), 'initial_inventory_pin': dict(INITIAL_INVENTORY_PIN),
        'code_source_id': CODE_SOURCE_ID, 'source_file_dispatches_at_most_once': True,
        'already_exact_sources_skipped': True, 'main_last': True,
        'lock_acquire_calls': 1, 'lock_release_calls': 0, 'result_reads': 0,
        'compile_polls': COMPILE_POLLS, 'compile_interval': COMPILE_INTERVAL,
        'capacity_polls': CAPACITY_POLLS, 'capacity_interval': CAPACITY_INTERVAL,
        'status_polls': STATUS_POLLS, 'status_interval': STATUS_INTERVAL,
        'new_project_created': False, 'A1_A2_A3_remain_spent': True,
        'new_paper_live_authority': False, **FALSE_FLAGS}
