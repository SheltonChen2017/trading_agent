"""Injected A11 plain-data source/compile recovery; no operational entrypoint.

The separately frozen caller authenticates new storage admission and supplies
the native worker's source-bound public projection packet. This is no replay of
A10. Only the functional plain-data successor is accepted. No capacity, launch,
result, delete, force-lock or arbitrary cloud-source operation is available.
"""
from __future__ import annotations

import hashlib
import json
import re

from scripts import arv2_r298_readiness_recovery_remote as predecessor
from scripts import arv2_r298_recovery_evidence as evidence

access = predecessor.access
PROJECT_ID = 38364439
ATTEMPT = 11
PROJECTION_SHA256 = '9dde39783bcb401d1f36aeb5beb1b1983882250b0472c2afd22dca1408c2a5f5'
PACKAGE_SHA256 = '1ab48d0b9c87710b05e109f234795a6bfbf5ea1b756664f8b58305dcb41173f2'
PROFILE_SHA256 = '89d6ac9bb0f1be8bd8f307f0b00d5725620e33b402fecb7ee2ff06daecc2106e'
ACTIVATION_SHA256 = 'ffdc80e1b6e76410ddd4840e5a21e49aea1dbdd5c735b6bcbd88bfe832e0233b'
CODE_SOURCE_ID = predecessor.CODE_SOURCE_ID
SOURCE_NAMES = frozenset(evidence.FILE_NAMES)
ENDPOINTS = predecessor.ENDPOINTS
LOCK_ENDPOINT = predecessor.LOCK_ENDPOINT
COLLABORATION_ENDPOINT = predecessor.COLLABORATION_ENDPOINT
RETAINED = predecessor.RETAINED_SOURCE_NAMES
DEFAULT_MAIN = predecessor.frozen.frozen.DEFAULT_MAIN
READY_SCHEMA = 'arv2-r298-plain-readiness-receipt-v1'
FALSE_FLAGS = {'backtest_created': False, 'capacity_observed': False,
               'launch_authorized': False, 'strategy_result_accepted': False,
               'formal_forward_ready': False, 'paper_or_live_ready': False}
_PAYLOAD_KEYS = {
    'projects/read': {'projectId'}, COLLABORATION_ENDPOINT: {'projectId'},
    LOCK_ENDPOINT: {'projectId', 'codeSourceId'},
    'backtests/list': {'projectId', 'includeStatistics'},
    'files/read': {'projectId', 'codeSourceId'},
    'files/create': {'projectId', 'name', 'content', 'codeSourceId'},
    'files/update': {'projectId', 'name', 'content', 'codeSourceId'},
    'compile/create': {'projectId'}, 'compile/read': {'projectId', 'compileId'},
}
FINITE = frozenset('binding source_packet source_inventory source_bytes source_hash old_sources '
    'callbacks journal marker endpoint payload lock history access observation response response_bound '
    'cloud_inventory cloud_content retained changed write_once inspect_once complete_once compile_once '
    'compile_state compile_id compile_poll ready_once ready_binding'.split())


class Refused(ValueError):
    """Finite source/readiness category, not provider text or inferred cause."""


def require(value, code):
    if not value:
        raise Refused(code)


def canonical(value):
    return predecessor._strict_canonical(value)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def finite(error):
    if type(error) is Refused and len(error.args) == 1 and type(error.args[0]) is str and error.args[0] in FINITE:
        return error.args[0]
    return 'unknown'


def validate_ready_receipt(value, *, expected_source_manifest_sha256):
    """Strict output-only shape/binding check; never substitutes for actual exit.

    The separately frozen caller supplies the manifest pin authenticated before
    contact. This function performs no source, artifact or provider operation.
    """
    require(type(expected_source_manifest_sha256) is str
            and re.fullmatch('[0-9a-f]{64}', expected_source_manifest_sha256), 'ready_binding')
    fields = {'schema', 'project_id', 'attempt', 'compile_id', 'projection_sha256',
              'source_manifest_sha256', 'state', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == fields
            and value['schema'] == READY_SCHEMA
            and type(value['project_id']) is int and value['project_id'] == PROJECT_ID
            and type(value['attempt']) is int and value['attempt'] == ATTEMPT
            and type(value['compile_id']) is str
            and re.fullmatch('[A-Za-z0-9_-]{1,128}', value['compile_id'])
            and value['projection_sha256'] == PROJECTION_SHA256
            and value['source_manifest_sha256'] == expected_source_manifest_sha256
            and value['state'] == 'compiled_exact_source_ready'
            and all(value[key] is False for key in FALSE_FLAGS), 'ready_binding')
    return json.loads(canonical(value))


def validate_public_packet(record_bytes, source_pairs):
    """Authenticate metadata/public code emitted by the native admission worker.

    Never parses licensed rows or obtains private source data. Fixed projection
    digest binds every descriptor, profile, bridge and new object inventory.
    """
    require(type(record_bytes) is bytes and 0 < len(record_bytes) <= 128 * 1024
            and sha(record_bytes) == PROJECTION_SHA256, 'binding')
    try:
        record = json.loads(record_bytes.decode('ascii'))
    except (ValueError, UnicodeError):
        raise Refused('source_packet') from None
    require(type(record) is dict and canonical(record)[:-1] == record_bytes
            and record.get('schema') == 'arv2-r298-plain-projection-v1'
            and record.get('candidate_id') == 'R298'
            and record.get('package_sha256') == PACKAGE_SHA256
            and record.get('profile_sha256') == PROFILE_SHA256
            and record.get('activation_manifest_sha256') == ACTIVATION_SHA256, 'binding')
    require(type(source_pairs) is tuple and len(source_pairs) == 11, 'source_inventory')
    files, rows = {}, []
    for item in source_pairs:
        require(type(item) is tuple and len(item) == 2, 'source_packet')
        name, raw = item
        require(type(name) is str and name in SOURCE_NAMES and name not in files
                and type(raw) is bytes and raw.isascii() and 0 < len(raw) <= 64000, 'source_bytes')
        files[name] = raw
        rows.append({'project_path': name, 'byte_count': len(raw), 'content_sha256': sha(raw)})
    require(set(files) == SOURCE_NAMES and sum(map(len, files.values())) <= 448 * 1024
            and canonical(rows) == canonical(record.get('source_files')), 'source_hash')
    return record, files


class PlainReadiness:
    """One bounded source/compile state machine with immutable input snapshots."""

    def __init__(self, record_bytes, source_pairs, *, request, journal, observe_access):
        record, sources = validate_public_packet(record_bytes, source_pairs)
        require(all(callable(value) for value in (request, journal, observe_access)), 'callbacks')
        original = evidence.reconstruct_projection()
        old = {item.project_path: item.source_bytes for item in original.source_files}
        require(all(sources[name] == old[name] for name in SOURCE_NAMES
                    if name not in ('main.py', 'accepted_risk_order_level_input_runtime.py')), 'old_sources')
        self._sources, self._old = sources, old
        self._request, self._journal, self._observe_access = request, journal, observe_access
        self._used, self._written = set(), set()
        self._lock = self._inspect_used = self._complete_used = self._compile_used = self._ready_used = False
        self._inspection = self._compiled = None
        self._write_ready = None
        self._acquire_ready = self._compile_dispatch_ready = False
        self._compile_read_ready = None
        self._poll_index = 0
        self._manifest = self._inventory({name: raw for name, raw in sources.items()})
        self._manifest_sha = sha(canonical(self._manifest))

    def _inventory(self, files):
        return {'project_id': PROJECT_ID, 'projection_sha256': PROJECTION_SHA256,
                'files': [{'name': name, 'byte_count': len(raw), 'sha256': sha(raw)}
                          for name, raw in sorted(files.items())]}

    def _event(self, marker, event, endpoint, raw):
        require(self._journal(marker, {'event': event, 'endpoint': endpoint, 'sha256': sha(raw)}) is None, 'journal')

    def _rpc(self, marker, endpoint, payload):
        require(type(marker) is str and re.fullmatch('[a-z0-9-]{1,80}', marker)
                and marker not in self._used, 'marker')
        require(type(endpoint) is str and endpoint in _PAYLOAD_KEYS, 'endpoint')
        require(type(payload) is dict and type(payload.get('projectId')) is int
                and payload['projectId'] == PROJECT_ID, 'payload')
        payload = json.loads(canonical(payload))
        if endpoint.startswith('files/'):
            require(self._lock, 'lock')
            require('codeSourceId' not in payload or payload['codeSourceId'] == CODE_SOURCE_ID, 'payload')
            payload['codeSourceId'] = CODE_SOURCE_ID
        require(set(payload) == _PAYLOAD_KEYS[endpoint], 'payload')
        if endpoint == 'backtests/list':
            require(payload['includeStatistics'] is False
                    and marker in {stage + '-backtests' for stage in ('inspect', 'complete', 'compile', 'ready')}, 'payload')
        if endpoint == LOCK_ENDPOINT:
            require(marker == 'inspect-lock' and self._inspect_used and not self._lock
                    and self._acquire_ready and payload['codeSourceId'] == CODE_SOURCE_ID, 'lock')
            self._acquire_ready = False
        if endpoint == 'compile/create':
            require(marker == 'compile-create' and self._compile_dispatch_ready
                    and self._compile_used and self._compiled is None, 'compile_once')
            self._compile_dispatch_ready = False
        if endpoint == 'compile/read':
            require(self._compiled is not None and self._compile_read_ready == (marker, payload['compileId'])
                    and payload['compileId'] == self._compiled['compile_id'], 'compile_id')
            self._compile_read_ready = None
        if endpoint in ('files/create', 'files/update'):
            name = payload['name']
            require(type(name) is str and name in self._sources
                    and type(payload['content']) is str and payload['content'].isascii()
                    and payload['content'].encode('ascii') == self._sources[name]
                    and self._write_ready == (marker, endpoint, name)
                    and name not in self._written, 'write_once')
            self._written.add(name)
            self._write_ready = None
        self._used.add(marker)
        raw = canonical(payload)
        self._event(marker, 'intent', endpoint, raw)
        response = self._request(endpoint, json.loads(raw))
        require(type(response) is dict, 'response')
        raw = canonical(response)
        require(len(raw) <= 1024 * 1024, 'response_bound')
        self._event(marker, 'observed', endpoint, raw)
        value = json.loads(raw)
        require(value.get('success') is True
                and ('errors' not in value or value['errors'] == []), 'response')
        return value

    def _owned(self, prefix):
        require(prefix in ('inspect', 'complete', 'compile', 'ready'), 'access')
        project = self._rpc(prefix + '-project', 'projects/read', {'projectId': PROJECT_ID})
        dedicated = self._rpc(prefix + '-collaborators', COLLABORATION_ENDPOINT, {'projectId': PROJECT_ID})
        packet = predecessor.access_observation_record(prefix, project, dedicated)
        require(self._observe_access(prefix + '-access', packet) is None, 'observation')
        access.verify_access(project, dedicated)  # Exact owner/known A5 rows, no pin refresh.
        history = self._rpc(prefix + '-backtests', 'backtests/list',
                            {'projectId': PROJECT_ID, 'includeStatistics': False})
        rows = predecessor._backtest_rows(history, 1, 'prior_backtests')
        require(predecessor._manual_backtest(rows[0]), 'history')

    def _files(self, marker, *, complete=False):
        rows = self._rpc(marker, 'files/read', {'projectId': PROJECT_ID}).get('files')
        require(type(rows) is list and len(rows) <= 11, 'cloud_inventory')
        files = {}
        for row in rows:
            require(type(row) is dict and type(row.get('projectId')) is int
                    and row['projectId'] == PROJECT_ID, 'cloud_inventory')
            name, text = row.get('name'), row.get('content')
            require(type(name) is str and name in SOURCE_NAMES and name not in files
                    and type(text) is str and text.isascii() and len(text) <= 64000, 'cloud_content')
            raw = text.encode('ascii')
            allowed_old = name in ('main.py', 'accepted_risk_order_level_input_runtime.py') and raw == self._old[name]
            placeholder = (name in ('main.py', 'accepted_risk_order_level_input_runtime.py')
                           and raw in (b'#', b'#\n')) or name == 'main.py' and raw == DEFAULT_MAIN
            require(raw == self._sources[name] or not complete and (allowed_old or placeholder), 'cloud_content')
            files[name] = raw
        require(not complete or set(files) == SOURCE_NAMES, 'cloud_inventory')
        return self._inventory(files)

    def inspect(self):
        require(not self._inspect_used, 'inspect_once')
        self._inspect_used = True
        self._owned('inspect')
        self._acquire_ready = True
        self._rpc('inspect-lock', LOCK_ENDPOINT, {'projectId': PROJECT_ID, 'codeSourceId': CODE_SOURCE_ID})
        self._lock = True
        current = self._files('inspect-files')
        rows = {row['name']: row for row in current['files']}
        require(all(rows.get(name) == {'name': name, 'byte_count': len(self._sources[name]),
                    'sha256': sha(self._sources[name])} for name in RETAINED), 'retained')
        self._inspection = canonical(current)
        return current

    def complete(self, original):
        require(not self._complete_used and self._lock and self._inspection is not None, 'complete_once')
        self._complete_used = True
        require(canonical(original) == self._inspection, 'changed')
        self._owned('complete')
        current = self._files('complete-before')
        require(canonical(current) == self._inspection, 'changed')
        seen = {row['name']: row for row in current['files']}
        changes = [(index, name, raw) for index, (name, raw) in enumerate(sorted(self._sources.items()))
                   if seen.get(name) != {'name': name, 'byte_count': len(raw), 'sha256': sha(raw)}]
        if not changes:
            return self._files('complete-final', complete=True)
        for position, (index, name, raw) in enumerate(changes):
            endpoint = 'files/update' if name in seen else 'files/create'
            marker = f'complete-write-{index:02d}'
            self._write_ready = marker, endpoint, name
            try:
                self._rpc(marker, endpoint, {'projectId': PROJECT_ID, 'name': name, 'content': raw.decode('ascii')})
            finally:
                self._write_ready = None
            seen[name] = {'name': name, 'byte_count': len(raw), 'sha256': sha(raw)}
            current = self._files(f'complete-after-{index:02d}', complete=position == len(changes) - 1)
            expected = {'project_id': PROJECT_ID, 'projection_sha256': PROJECTION_SHA256,
                        'files': sorted(seen.values(), key=lambda item: item['name'])}
            require(canonical(current) == canonical(expected), 'changed')
        return current

    def compile_once(self, completed):
        require(not self._compile_used and self._complete_used, 'compile_once')
        self._compile_used = True
        self._owned('compile')
        current = self._files('compile-files', complete=True)
        require(canonical(current) == canonical(completed) == canonical(self._manifest), 'changed')
        self._compile_dispatch_ready = True
        value = self._rpc('compile-create', 'compile/create', {'projectId': PROJECT_ID})
        require(type(value.get('projectId', PROJECT_ID)) is int
                and value.get('projectId', PROJECT_ID) == PROJECT_ID, 'compile_id')
        compile_id = predecessor._cloud_id(value.get('compileId'))
        self._compiled = {'project_id': PROJECT_ID, 'compile_id': compile_id,
                          'projection_sha256': PROJECTION_SHA256, 'source_manifest_sha256': self._manifest_sha}
        return json.loads(canonical(self._compiled))

    def _compile_state(self, compile_id, marker):
        require(self._compiled is not None and compile_id == self._compiled['compile_id'], 'compile_id')
        require((marker == 'ready-compile' and self._ready_used)
                or (0 < self._poll_index <= 20 and marker == f'compile-poll-{self._poll_index - 1:03d}'), 'compile_poll')
        self._compile_read_ready = marker, compile_id
        value = self._rpc(marker, 'compile/read', {'projectId': PROJECT_ID, 'compileId': compile_id})
        require(type(value.get('projectId', PROJECT_ID)) is int
                and value.get('projectId', PROJECT_ID) == PROJECT_ID and value.get('compileId') == compile_id
                and value.get('state') in ('InQueue', 'Building', 'BuildSuccess', 'BuildError'), 'compile_state')
        return value['state']

    def poll_compile(self, compile_id, index):
        require(type(index) is int and index == self._poll_index and index < 20, 'compile_poll')
        self._poll_index += 1
        return {'project_id': PROJECT_ID, 'compile_id': compile_id,
                'state': self._compile_state(compile_id, f'compile-poll-{index:03d}')}

    def ready_once(self, compiled):
        require(not self._ready_used and self._compiled is not None
                and canonical(compiled) == canonical(self._compiled), 'ready_once')
        self._ready_used = True
        require(self._compile_state(compiled['compile_id'], 'ready-compile') == 'BuildSuccess', 'compile_state')
        self._owned('ready')
        require(canonical(self._files('ready-files', complete=True)) == canonical(self._manifest), 'changed')
        value = {'schema': READY_SCHEMA, 'project_id': PROJECT_ID, 'attempt': ATTEMPT,
                'compile_id': compiled['compile_id'], 'projection_sha256': PROJECTION_SHA256,
                'source_manifest_sha256': self._manifest_sha, 'state': 'compiled_exact_source_ready', **FALSE_FLAGS}
        return validate_ready_receipt(value, expected_source_manifest_sha256=self._manifest_sha)
