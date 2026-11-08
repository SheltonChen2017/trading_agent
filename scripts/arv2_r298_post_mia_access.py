"""Pure redaction of two supplied, fixed-project access responses.

The unchanged strict access policy is observed, never relaxed or converted to
an operational grant. No filesystem, credential, network or execution function
exists here. The caller owns request provenance and actual-exit authentication.
"""
from __future__ import annotations

import json
import re

from scripts import arv2_r298_collaborator_access as access


SCHEMA = 'arv2-r298-post-mia-access-observation-v1'
MAX_ROWS = 8
MAX_OUTPUT = 48 * 1024
ROW_FIELDS = ('owner', 'uid', 'name', 'publicId', 'codeSourceId', 'permission', 'liveControl', 'email')
PROJECT_FIELDS = ('projectId', 'organizationId', 'name', 'language', 'owner', 'ownerId', 'codeRunning', 'public')
TYPES = frozenset(('missing', 'null', 'bool', 'int', 'float', 'str', 'list', 'dict'))
FLAGS = frozenset(('true', 'false', 'missing', 'other'))
PERMISSIONS = frozenset(('write', 'read', 'missing', 'other'))
IDENTITY_FIELDS = ('name', 'publicId', 'codeSourceId')
FALSE_FLAGS = {'response_provenance_authenticated': False, 'privacy_proven': False,
    'edit_lock_proven': False, 'access_authorized': False, 'source_upload_authorized': False,
    'compile_authorized': False, 'backtest_authorized': False, 'operational_retry_authority': False,
    'strategy_result_accepted': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('scope_response', 'scope_project_shape', 'scope_project_id', 'scope_organization',
    'scope_name', 'scope_language', 'scope_owner', 'scope_owner_id', 'row_bound',
    'observation_shape', 'observation_bound'))


class Refused(ValueError):
    """Closed scope/redaction refusal; never response or exception text."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    return 'unknown'


canonical, sha = access._canonical, access._sha


def profile_record():
    return {'schema': SCHEMA, 'project_id': access.PROJECT_ID,
        'project_name_sha256': sha(canonical(access.PROJECT_NAME)),
        'organization_sha256': access.ORGANIZATION_SHA256, 'owner_row_sha256': access.OWNER_ROW_SHA256,
        'a5_row_sha256': access.A5_ROW_SHA256,
        'known_a5_identifier_sha256': sha(canonical(access.A5_CODE_SOURCE_ID)),
        'strict_access_schema': access.SCHEMA, 'max_rows_per_view': MAX_ROWS,
        'max_response_bytes': access.MAX_RESPONSE_BYTES, 'max_output_bytes': MAX_OUTPUT,
        'row_field_types': list(ROW_FIELDS), 'identifier_value_hash_fields': list(IDENTITY_FIELDS),
        'known_mia_label_sha256': sha(canonical('Mia')),
        'known_mia_ai_label_sha256': sha(canonical('mia-ai')), **FALSE_FLAGS}


def _type(value, field=None):
    if field is not None:
        if field not in value:
            return 'missing'
        value = value[field]
    return {type(None): 'null', bool: 'bool', int: 'int', float: 'float',
        str: 'str', list: 'list', dict: 'dict'}[type(value)]


def _flag(value, field):
    if field not in value:
        return 'missing'
    return 'true' if value[field] is True else 'false' if value[field] is False else 'other'


def _permission(value, field):
    item = value.get(field)
    return 'missing' if field not in value else item if type(item) is str and item in ('read', 'write') else 'other'


def _snapshot(value):
    try:
        return access._response(value)
    except access.AccessRefused as error:
        code = access.finite_error(error)['code']
        raise Refused('scope_' + code if 'scope_' + code in FINITE else 'scope_response') from None


def _scope(project_packet, dedicated):
    projects = project_packet.get('projects')
    require(type(projects) is list and len(projects) == 1 and type(projects[0]) is dict, 'scope_project_shape')
    project = projects[0]
    require(type(project.get('projectId')) is int and project['projectId'] == access.PROJECT_ID, 'scope_project_id')
    organization = project.get('organizationId')
    require(type(organization) is str and re.fullmatch('[0-9a-f]{32}', organization)
        and sha(organization.encode('ascii')) == access.ORGANIZATION_SHA256, 'scope_organization')
    require(type(project.get('name')) is str and project['name'] == access.PROJECT_NAME, 'scope_name')
    require(type(project.get('language')) is str and project['language'] == 'Py', 'scope_language')
    require(project.get('owner') is True, 'scope_owner')
    owner_id = project.get('ownerId')
    require(type(owner_id) is int and 0 < owner_id < 2 ** 63, 'scope_owner_id')
    return project, owner_id


def _row(value, owner_id):
    is_row = type(value) is dict
    fields = value if is_row else {}
    digest = sha(canonical(value))
    return {'row_type': _type(value), 'row_sha256': digest,
        'field_types': {name: _type(fields, name) for name in ROW_FIELDS},
        'owner': _flag(fields, 'owner'), 'permission': _permission(fields, 'permission'),
        'live_control': _flag(fields, 'liveControl'),
        'uid_matches_project_owner': type(fields.get('uid')) is int and fields['uid'] == owner_id,
        'matches_known_owner_row': is_row and digest == access.OWNER_ROW_SHA256,
        'matches_known_a5_row': is_row and digest == access.A5_ROW_SHA256,
        'identifier_value_sha256': {name: sha(canonical(fields[name])) if name in fields else None
            for name in IDENTITY_FIELDS},
        'identifier_matches': {name: {'is_mia': type(fields.get(name)) is str and fields[name] == 'Mia',
            'is_mia_ai': type(fields.get(name)) is str and fields[name] == 'mia-ai',
            'is_a5': type(fields.get(name)) is str and fields[name] == access.A5_CODE_SOURCE_ID}
            for name in IDENTITY_FIELDS}}


def _view(packet, owner_id):
    rows = packet.get('collaborators')
    require(type(rows) is not list or len(rows) <= MAX_ROWS, 'row_bound')
    return {'container_type': _type(packet, 'collaborators'),
        'count': len(rows) if type(rows) is list else None,
        'rows': [_row(row, owner_id) for row in rows] if type(rows) is list else []}


def observe(project_response, dedicated_response):
    """Retain bounded observations even when the exact strict policy refuses."""
    project_packet, dedicated = _snapshot(project_response), _snapshot(dedicated_response)
    project, owner_id = _scope(project_packet, dedicated)
    general, specific = _view(project, owner_id), _view(dedicated, owner_id)
    failure = None
    try:
        access.verify_access(project_packet, dedicated)
    except access.AccessRefused as error:
        failure = access.finite_error(error)['code']
    result = {'schema': SCHEMA, 'project_id': access.PROJECT_ID,
        'organization_sha256': access.ORGANIZATION_SHA256,
        'project_response_sha256': sha(canonical(project_packet)),
        'dedicated_response_sha256': sha(canonical(dedicated)),
        'scope_bound': True, 'strict_policy_check': 'passed' if failure is None else 'refused',
        'access_failure_code': failure,
        'project': {'field_types': {name: _type(project, name) for name in PROJECT_FIELDS},
            'code_running': _flag(project, 'codeRunning'), 'public': _flag(project, 'public'),
            'owner': _flag(project, 'owner'), 'owner_id_positive_integer': True,
            'name_matches': True, 'language_matches': True, 'organization_matches': True},
        'general': general, 'dedicated': specific,
        'dedicated_permissions': {'permission_type': _type(dedicated, 'userPermissions'),
            'permission': _permission(dedicated, 'userPermissions'),
            'live_control_type': _type(dedicated, 'userLiveControl'),
            'live_control': _flag(dedicated, 'userLiveControl')}, **FALSE_FLAGS}
    return validate_observation(result)


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _types(value, names):
    require(type(value) is dict and set(value) == set(names)
        and all(type(item) is str and item in TYPES for item in value.values()), 'observation_shape')


def _validate_view(value):
    require(type(value) is dict and set(value) == {'container_type', 'count', 'rows'}
        and type(value['container_type']) is str and value['container_type'] in TYPES
        and type(value['rows']) is list, 'observation_shape')
    if value['container_type'] == 'list':
        require(type(value['count']) is int and 0 <= value['count'] <= MAX_ROWS
            and len(value['rows']) == value['count'], 'observation_shape')
    else:
        require(value['count'] is None and value['rows'] == [], 'observation_shape')
    for row in value['rows']:
        require(type(row) is dict and set(row) == {'row_type', 'row_sha256', 'field_types', 'owner',
            'permission', 'live_control', 'uid_matches_project_owner', 'matches_known_owner_row',
            'matches_known_a5_row', 'identifier_value_sha256', 'identifier_matches'} and type(row['row_type']) is str
            and row['row_type'] in TYPES - {'missing'} and _hash(row['row_sha256'])
            and type(row['owner']) is str and row['owner'] in FLAGS
            and type(row['permission']) is str and row['permission'] in PERMISSIONS
            and type(row['live_control']) is str and row['live_control'] in FLAGS
            and all(type(row[name]) is bool for name in ('uid_matches_project_owner',
                'matches_known_owner_row', 'matches_known_a5_row'))
            and row['matches_known_owner_row'] == (row['row_type'] == 'dict' and row['row_sha256'] == access.OWNER_ROW_SHA256)
            and row['matches_known_a5_row'] == (row['row_type'] == 'dict' and row['row_sha256'] == access.A5_ROW_SHA256),
            'observation_shape')
        _types(row['field_types'], ROW_FIELDS)
        matches = row['identifier_matches']
        hashes = row['identifier_value_sha256']
        require(type(matches) is dict and set(matches) == set(IDENTITY_FIELDS)
            and type(hashes) is dict and set(hashes) == set(IDENTITY_FIELDS), 'observation_shape')
        for name, item in matches.items():
            require(type(item) is dict and set(item) == {'is_mia', 'is_mia_ai', 'is_a5'}
                and all(type(flag) is bool for flag in item.values())
                and sum(item.values()) <= 1, 'observation_shape')
            require((row['field_types'][name] == 'missing' and hashes[name] is None)
                or (row['field_types'][name] != 'missing' and _hash(hashes[name])), 'observation_shape')
            for label, expected in (('is_mia', 'Mia'), ('is_mia_ai', 'mia-ai'),
                                   ('is_a5', access.A5_CODE_SOURCE_ID)):
                require(item[label] == (row['field_types'][name] == 'str'
                    and hashes[name] == sha(canonical(expected))), 'observation_shape')


def validate_observation(value):
    """Validate a finite supplied observation; never grant operational access."""
    try:
        raw = canonical(value)
    except access.AccessRefused:
        raise Refused('observation_shape') from None
    require(0 < len(raw) <= MAX_OUTPUT, 'observation_bound')
    value = json.loads(raw)
    require(type(value) is dict and set(value) == {'schema', 'project_id', 'organization_sha256',
        'project_response_sha256', 'dedicated_response_sha256', 'scope_bound', 'strict_policy_check',
        'access_failure_code', 'project', 'general', 'dedicated', 'dedicated_permissions'} | set(FALSE_FLAGS)
        and value['schema'] == SCHEMA and type(value['project_id']) is int
        and value['project_id'] == access.PROJECT_ID and value['organization_sha256'] == access.ORGANIZATION_SHA256
        and _hash(value['project_response_sha256']) and _hash(value['dedicated_response_sha256'])
        and value['scope_bound'] is True and all(value[key] is False for key in FALSE_FLAGS), 'observation_shape')
    failure = value['access_failure_code']
    require((failure is None and value['strict_policy_check'] == 'passed')
        or (type(failure) is str and failure in access.FINITE_CODES | {'unknown'}
            and value['strict_policy_check'] == 'refused'), 'observation_shape')
    project = value['project']
    require(type(project) is dict and set(project) == {'field_types', 'code_running', 'public', 'owner',
        'owner_id_positive_integer', 'name_matches', 'language_matches', 'organization_matches'}
        and type(project['code_running']) is str and project['code_running'] in FLAGS
        and type(project['public']) is str and project['public'] in FLAGS and project['owner'] == 'true'
        and all(project[name] is True for name in ('owner_id_positive_integer', 'name_matches',
            'language_matches', 'organization_matches')), 'observation_shape')
    _types(project['field_types'], PROJECT_FIELDS)
    _validate_view(value['general'])
    _validate_view(value['dedicated'])
    permissions = value['dedicated_permissions']
    require(type(permissions) is dict and set(permissions) == {'permission_type', 'permission',
        'live_control_type', 'live_control'} and type(permissions['permission_type']) is str
        and permissions['permission_type'] in TYPES and type(permissions['live_control_type']) is str
        and permissions['live_control_type'] in TYPES and type(permissions['permission']) is str
        and permissions['permission'] in PERMISSIONS and type(permissions['live_control']) is str
        and permissions['live_control'] in FLAGS, 'observation_shape')
    if failure is None:
        general, dedicated = value['general'], value['dedicated']
        require(project['code_running'] == 'false' and project['public'] in ('false', 'missing')
            and dedicated['count'] == 1 and general['count'] in (1, 2)
            and permissions['permission'] == 'write' and permissions['live_control'] == 'true',
            'observation_shape')
        owner = dedicated['rows'][0]
        require(owner['matches_known_owner_row'] is True and owner['uid_matches_project_owner'] is True
            and owner['owner'] == 'true' and owner['permission'] == 'write' and owner['live_control'] == 'true'
            and sum(row['matches_known_owner_row'] for row in general['rows']) == 1
            and all(row['matches_known_owner_row'] or row['matches_known_a5_row'] for row in general['rows']),
            'observation_shape')
    return value
