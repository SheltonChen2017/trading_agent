"""Pure one-file R298 current-content reconciliation with injected read seams.

There is no transport, credential, filesystem, claim or CLI implementation.
A separate caller must bind expected_bytes to the exact public rendered
projection and authenticate each response's provenance and request scope.
Neither a match nor a placeholder proves A6's effect or unchanged history.
The in-memory one-use guard is not a durable claim or permission to contact QC.
"""
from __future__ import annotations

import hashlib
import json
import re

from scripts import arv2_r298_collaborator_access as access


SCHEMA = 'arv2-r298-file-effect-v1'
PROJECT_ID = 38364439
TARGET_NAME = 'accepted_risk_order_level_input_runtime.py'
PROJECTION_SHA256 = 'f67148cd717e207be9d44f088749c0443bb696d9c4f38f512eb6cbf483fd9662'
MAX_SOURCE_BYTES, MAX_RESPONSE_BYTES = 64000, 1024 * 1024
EXPECTED_SOURCE_BYTES = 23055
EXPECTED_SOURCE_SHA256 = 'c34e42d894dc88e74ce37899622a7f728bafdac9320ce2775736ba06b7ad463e'
MAX_COLLABORATORS = 8
READ_CONTEXT_SCHEMA = 'arv2-r298-read-context-v1'
ENDPOINTS = ('projects/read', 'projects/collaboration/read', 'files/read')
CLASSIFICATIONS = ('desired_source', 'permitted_placeholder', 'different_source')
STAGES = ('preflight', 'project', 'collaborators', 'files', 'complete')
FALSE_FLAGS = {
    'response_provenance_authenticated': False,
    'expected_source_authenticated': False,
    'unchanged_proven': False,
    'a6_effect_proven': False,
    'original_update_error_recovered': False,
    'atomic_snapshot_proven': False,
    'privacy_proven': False,
    'operational_retry_authority': False,
    'strategy_result_accepted': False,
    'write_access_policy_accepted': False,
    'whole_owner_row_continuity_proven': False,
}
FINITE_CODES = frozenset(('expected_source', 'callbacks', 'observer_used',
    'response_shape', 'response_bound', 'response_refused', 'file_inventory',
    'file_project', 'file_name', 'file_content', 'file_count', 'journal_failed',
    'journal_result', 'request_ambiguous', 'unknown', 'project_shape',
    'project_id', 'organization', 'project_name', 'language', 'owner', 'owner_id',
    'dedicated_rows', 'dedicated_owner', 'permissions', 'metadata_bound',
    'observation_shape')) | frozenset(
        'access_' + code for code in access.FINITE_CODES)
JSON_TYPES = ('absent', 'null', 'boolean', 'number', 'string', 'array', 'object')


class EffectRefused(ValueError):
    """Finite local refusal, never a provider body, source or account value."""


def _require(value, code):
    if not value:
        raise EffectRefused(code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def finite_error(error):
    code = 'unknown'
    if type(error) is EffectRefused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE_CODES:
            code = args[0]
    return {'code': code}


def _canonical(value):
    try:
        return access._canonical(value)
    except access.AccessRefused as error:
        raise EffectRefused('access_' + access.finite_error(error)['code']) from None


def _snapshot(value):
    _require(type(value) is dict, 'response_shape')
    raw = _canonical(value)  # Exact JSON types checked before serialization.
    _require(0 < len(raw) <= MAX_RESPONSE_BYTES, 'response_bound')
    return json.loads(raw)


def _accepted(value):
    copied = _snapshot(value)
    _require(copied.get('success') is True and ('errors' not in copied
        or (type(copied['errors']) is list and copied['errors'] == [])), 'response_refused')
    return copied


def _expected(expected_bytes):
    # The fixed digest/size bind this one rendered file. Authentication of
    # the full public projection/source closure remains the caller's duty.
    _require(type(expected_bytes) is bytes and 0 < len(expected_bytes) <= MAX_SOURCE_BYTES
        and expected_bytes.isascii() and expected_bytes not in (b'#', b'#\n')
        and len(expected_bytes) == EXPECTED_SOURCE_BYTES
        and _sha(expected_bytes) == EXPECTED_SOURCE_SHA256, 'expected_source')
    return {'byte_count': len(expected_bytes), 'sha256': _sha(expected_bytes)}


def _organization(value):
    _require(type(value) is str and re.fullmatch('[0-9a-f]{32}', value)
        and _sha(value.encode('ascii')) == access.ORGANIZATION_SHA256, 'organization')


def _optional_scope(packet):
    if 'projectId' in packet:
        _require(type(packet['projectId']) is int and packet['projectId'] == PROJECT_ID, 'project_id')
    if 'organizationId' in packet:
        _organization(packet['organizationId'])


def _field(packet, key):
    present = key in packet
    value = packet.get(key)
    kind = ('absent' if not present else {type(None): 'null', bool: 'boolean',
        int: 'number', float: 'number', str: 'string', list: 'array', dict: 'object'}[type(value)])
    return {'present': present, 'kind': kind,
        'count': len(value) if type(value) in (list, dict) else None,
        'boolean_value': value if type(value) is bool else None,
        'sha256': _sha(_canonical(value)) if present else None}


def verify_read_context(project_response, dedicated_response):
    """New current-owner READ policy, not the frozen A6 write-access policy.

    No idle, live-control, edit-lock or pinned general-extra requirement is
    used to authorize this one owner read. Exactly one typed dedicated owner
    must equal the project's ownerId and both permissions must permit reading.
    Other valid JSON metadata is bounded diagnostic information only. This
    does not prove whole-owner-row continuity or accept a new write policy.
    """
    project_packet, dedicated = _accepted(project_response), _accepted(dedicated_response)
    for packet in (project_packet, dedicated):
        _optional_scope(packet)
    projects = project_packet.get('projects')
    _require(type(projects) is list and len(projects) == 1 and type(projects[0]) is dict, 'project_shape')
    project = projects[0]
    _require(type(project.get('projectId')) is int and project['projectId'] == PROJECT_ID, 'project_id')
    _organization(project.get('organizationId'))
    _require(type(project.get('name')) is str and project['name'] == access.PROJECT_NAME, 'project_name')
    _require(type(project.get('language')) is str and project['language'] == 'Py', 'language')
    _require(project.get('owner') is True, 'owner')
    owner_id = project.get('ownerId')
    _require(type(owner_id) is int and 0 < owner_id < 2 ** 63, 'owner_id')
    rows = dedicated.get('collaborators')
    _require(type(rows) is list and 1 <= len(rows) <= MAX_COLLABORATORS
        and all(type(row) is dict and type(row.get('owner')) is bool for row in rows), 'dedicated_rows')
    owners = [row for row in rows if row['owner'] is True]
    _require(len(owners) == 1, 'dedicated_owner')
    owner = owners[0]
    _require(type(owner.get('uid')) is int and owner['uid'] == owner_id, 'dedicated_owner')
    _require(type(owner.get('permission')) is str and owner['permission'] in ('read', 'write')
        and type(dedicated.get('userPermissions')) is str
        and dedicated['userPermissions'] in ('read', 'write'), 'permissions')
    general = _field(project, 'collaborators')
    _require(general['kind'] != 'array' or general['count'] <= MAX_COLLABORATORS, 'metadata_bound')
    return {'schema': READ_CONTEXT_SCHEMA, 'project_id': PROJECT_ID,
        'organization_sha256': access.ORGANIZATION_SHA256,
        'dedicated_count': len(rows), 'dedicated_rows_sha256': _sha(_canonical(rows)),
        'owner_row_sha256': _sha(_canonical(owner)), 'owner_permission': owner['permission'],
        'requester_permission': dedicated['userPermissions'], 'general_collaborators': general,
        'code_running': _field(project, 'codeRunning'),
        'owner_live_control': _field(owner, 'liveControl'),
        'requester_live_control': _field(dedicated, 'userLiveControl'), **FALSE_FLAGS}


def profile_record():
    return {'schema': SCHEMA, 'project_id': PROJECT_ID, 'target_name': TARGET_NAME,
        'projection_sha256': PROJECTION_SHA256, 'endpoints': list(ENDPOINTS),
        'max_application_dispatches': 3, 'max_source_bytes': MAX_SOURCE_BYTES,
        'max_response_bytes': MAX_RESPONSE_BYTES, 'code_source_id_supplied': False,
        'expected_source_bytes': EXPECTED_SOURCE_BYTES, 'expected_source_sha256': EXPECTED_SOURCE_SHA256,
        'read_context_schema': READ_CONTEXT_SCHEMA, 'max_collaborators': MAX_COLLABORATORS,
        'expected_projection_binding_required_from_caller': True,
        'classifications': list(CLASSIFICATIONS), 'durable_claim_implemented': False,
        **FALSE_FLAGS}


def validate_file_response(response, expected_bytes):
    """Compare one supplied file; no response provenance or historical claim.

Valid JSON metadata not used by this contract is never emitted. Contradictory
    optional project/count fields refuse; the one row must name the exact file.
    Absent row projectId is not invented: the caller must authenticate request
    scope. Empty current content is valid different-source evidence.
"""
    _expected(expected_bytes)
    packet = _accepted(response)
    if 'projectId' in packet:
        _require(type(packet['projectId']) is int and packet['projectId'] == PROJECT_ID, 'file_project')
    if 'count' in packet:
        _require(type(packet['count']) is int and packet['count'] == 1, 'file_count')
    rows = packet.get('files')
    _require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict, 'file_inventory')
    row = rows[0]
    if 'projectId' in row:
        _require(type(row['projectId']) is int and row['projectId'] == PROJECT_ID, 'file_project')
    _require(type(row.get('name')) is str and row['name'] == TARGET_NAME, 'file_name')
    content = row.get('content')
    _require(type(content) is str and len(content) <= MAX_SOURCE_BYTES and content.isascii(), 'file_content')
    raw = content.encode('ascii')
    classification = ('desired_source' if raw == expected_bytes else
        'permitted_placeholder' if raw in (b'#', b'#\n') else 'different_source')
    return {'byte_count': len(raw), 'sha256': _sha(raw), 'classification': classification}


def reconcile(project_response, dedicated_response, file_response, expected_bytes):
    """Pure supplied-object classifier; no request, journal or claim invocation."""
    _expected(expected_bytes)
    verify_read_context(project_response, dedicated_response)
    return validate_file_response(file_response, expected_bytes)


class FileEffectObserver:
    """Three fixed reads once per object; caller owns durable claim/deadline.

    request(endpoint, payload) and journal(marker, event) are supplied seams.
    The journal must return None. No request follows a journal refusal.
    A dispatched call is counted before invocation, even if it raises.
    A callback can do arbitrary things: this class is not a sandbox or a
    standalone security boundary. Current reads do not recreate A6's error.
    """

    def __init__(self, expected_bytes):
        self._expected = _expected(expected_bytes)
        self._expected_bytes = expected_bytes  # Exact immutable bytes only.
        self._used = False

    @staticmethod
    def _journal(journal, marker, event):
        try:
            value = journal(marker, event)
        except Exception:
            raise EffectRefused('journal_failed') from None
        _require(value is None, 'journal_result')

    def observe(self, request, journal):
        _require(not self._used, 'observer_used')
        self._used = True  # Even invalid callbacks do not renew this instance.
        result = {'schema': SCHEMA, 'project_id': PROJECT_ID, 'target_name': TARGET_NAME,
            'projection_sha256': PROJECTION_SHA256, 'expected_source': dict(self._expected),
            'observation_complete': False, 'file_observation': None, 'failure_code': None,
            'read_context': None,
            'stage': 'preflight', 'last_endpoint': None, 'last_event': None,
            'application_dispatch_count': 0, 'provider_request_count': None, **FALSE_FLAGS}
        packets = []
        try:
            _require(callable(request) and callable(journal), 'callbacks')
            for index, (endpoint, stage) in enumerate(zip(ENDPOINTS, STAGES[1:4])):
                if index == 2:
                    result['read_context'] = verify_read_context(packets[0], packets[1])
                payload = {'projectId': PROJECT_ID}
                if index == 2:
                    payload['name'] = TARGET_NAME
                marker = 'read-' + stage
                result.update(stage=stage, last_endpoint=endpoint, last_event='intent')
                self._journal(journal, marker, {'event': 'intent', 'endpoint': endpoint,
                    'payload_sha256': _sha(_canonical(payload))})
                result['application_dispatch_count'] += 1
                try:
                    response = request(endpoint, payload)
                except Exception:
                    raise EffectRefused('request_ambiguous') from None
                result['last_event'] = 'response_received'
                copied = _accepted(response)
                # Snapshot immediately, before any subsequent callback can
                # mutate an earlier response's caller-owned nested objects.
                packets.append(copied)
                self._journal(journal, marker, {'event': 'observed', 'endpoint': endpoint,
                    'response_sha256': _sha(_canonical(copied))})
                result['last_event'] = 'observed'
            result['file_observation'] = validate_file_response(packets[2], self._expected_bytes)
            result.update(observation_complete=True, stage='complete')
        except Exception as error:
            result['failure_code'] = finite_error(error)['code']
        return result


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _validate_field(value):
    _require(type(value) is dict and set(value) == {'present', 'kind', 'count', 'boolean_value', 'sha256'},
        'observation_shape')
    _require(type(value['present']) is bool and value['kind'] in JSON_TYPES
        and (value['kind'] == 'absent') is (not value['present']), 'observation_shape')
    kind = value['kind']
    _require((_hash(value['sha256']) if value['present'] else value['sha256'] is None), 'observation_shape')
    if kind in ('array', 'object'):
        _require(type(value['count']) is int and 0 <= value['count'] <= access.MAX_JSON_NODES, 'observation_shape')
    else:
        _require(value['count'] is None, 'observation_shape')
    if kind == 'boolean':
        _require(type(value['boolean_value']) is bool
            and value['sha256'] == _sha(_canonical(value['boolean_value'])), 'observation_shape')
    else:
        _require(value['boolean_value'] is None, 'observation_shape')
    if kind == 'null':
        _require(value['sha256'] == _sha(_canonical(None)), 'observation_shape')
    for known, known_kind in ((None, 'null'), (True, 'boolean'), (False, 'boolean')):
        if value['sha256'] == _sha(_canonical(known)):
            _require(kind == known_kind, 'observation_shape')


def _validate_context(value):
    keys = {'schema', 'project_id', 'organization_sha256', 'dedicated_count',
        'dedicated_rows_sha256', 'owner_row_sha256', 'owner_permission', 'requester_permission',
        'general_collaborators', 'code_running', 'owner_live_control', 'requester_live_control'} | set(FALSE_FLAGS)
    _require(type(value) is dict and set(value) == keys and value['schema'] == READ_CONTEXT_SCHEMA
        and type(value['project_id']) is int and value['project_id'] == PROJECT_ID
        and value['organization_sha256'] == access.ORGANIZATION_SHA256
        and type(value['dedicated_count']) is int and 1 <= value['dedicated_count'] <= MAX_COLLABORATORS
        and _hash(value['dedicated_rows_sha256']) and _hash(value['owner_row_sha256'])
        and value['owner_permission'] in ('read', 'write') and value['requester_permission'] in ('read', 'write')
        and all(value[key] is False for key in FALSE_FLAGS), 'observation_shape')
    for key in ('general_collaborators', 'code_running', 'owner_live_control', 'requester_live_control'):
        _validate_field(value[key])
    general = value['general_collaborators']
    _require(general['kind'] != 'array' or general['count'] <= MAX_COLLABORATORS, 'observation_shape')


def _validate_file(value):
    _require(type(value) is dict and set(value) == {'byte_count', 'sha256', 'classification'}
        and type(value['byte_count']) is int and 0 <= value['byte_count'] <= MAX_SOURCE_BYTES
        and _hash(value['sha256']) and value['classification'] in CLASSIFICATIONS, 'observation_shape')
    pair = (value['byte_count'], value['sha256'])
    desired = pair == (EXPECTED_SOURCE_BYTES, EXPECTED_SOURCE_SHA256)
    placeholder = pair in tuple((len(raw), _sha(raw)) for raw in (b'#', b'#\n'))
    _require((value['classification'] == 'desired_source') is desired
        and (value['classification'] == 'permitted_placeholder') is placeholder, 'observation_shape')


def validate_observation(value):
    """Check finite output coherence only; never authenticate its provenance."""
    _canonical(value)  # Reject normalized subclasses/tuples even in unused fields.
    keys = {'schema', 'project_id', 'target_name', 'projection_sha256', 'expected_source',
        'observation_complete', 'file_observation', 'failure_code', 'read_context',
        'stage', 'last_endpoint', 'last_event', 'application_dispatch_count', 'provider_request_count'} | set(FALSE_FLAGS)
    _require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
        and type(value['project_id']) is int and value['project_id'] == PROJECT_ID
        and value['target_name'] == TARGET_NAME and value['projection_sha256'] == PROJECTION_SHA256
        and type(value['expected_source']) is dict and set(value['expected_source']) == {'byte_count', 'sha256'}
        and type(value['expected_source']['byte_count']) is int
        and value['expected_source']['byte_count'] == EXPECTED_SOURCE_BYTES
        and value['expected_source']['sha256'] == EXPECTED_SOURCE_SHA256
        and type(value['observation_complete']) is bool and value['stage'] in STAGES
        and type(value['application_dispatch_count']) is int and 0 <= value['application_dispatch_count'] <= 3
        and value['provider_request_count'] is None
        and all(value[key] is False for key in FALSE_FLAGS), 'observation_shape')
    count, stage = value['application_dispatch_count'], value['stage']
    complete = value['observation_complete']
    if complete:
        _require(stage == 'complete' and count == 3 and value['failure_code'] is None
            and value['last_endpoint'] == ENDPOINTS[2] and value['last_event'] == 'observed', 'observation_shape')
        _validate_file(value['file_observation'])
        _validate_context(value['read_context'])
        return None
    _require(type(value['failure_code']) is str and value['failure_code'] in FINITE_CODES
        and value['failure_code'] != 'observer_used' and value['file_observation'] is None
        and stage != 'complete', 'observation_shape')
    if stage == 'preflight':
        _require(count == 0 and value['last_endpoint'] is None and value['last_event'] is None
            and value['read_context'] is None, 'observation_shape')
        return None
    index = STAGES.index(stage)
    _require(value['last_endpoint'] == ENDPOINTS[index - 1]
        and value['last_event'] in ('intent', 'response_received', 'observed')
        and count in (index - 1, index)
        and (value['last_event'] == 'intent' or count == index), 'observation_shape')
    if stage == 'files':
        _validate_context(value['read_context'])
    else:
        _require(value['read_context'] is None, 'observation_shape')
    if value['failure_code'] == 'request_ambiguous':
        _require(count == index and value['last_event'] == 'intent', 'observation_shape')
