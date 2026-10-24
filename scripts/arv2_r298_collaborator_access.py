"""Pure, separately versioned R298 collaborator-access representation check.

This contract accepts only the current pinned owner, alone or alongside the
exact R314-observed A5 row. The latter is qualified access metadata, not proof
of a synthetic account, lease, privacy or privileges. Historical D3 Mia is not
an accepted extra in this version; its old acceptance remains in frozen A5.

Inputs are two supplied response objects. A future separately authorized
caller must authenticate their request/response provenance and exact project
scope. This module has no transport, credentials, filesystem, claim, retry,
lock, source-upload, compile or launch entrypoint. No attempt is authorized.
"""
from __future__ import annotations

import hashlib
import json
import math
import re


SCHEMA = 'arv2-r298-collaborator-access-v1'
PROJECT_ID = 38364439
PROJECT_NAME = 'ARV2 R298 NEWRULE SIX OFF 2021 OCT2026'
ORGANIZATION_SHA256 = 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
OWNER_ROW_SHA256 = '707a30618e122e49fe6fa75364451b5b7c50e1019a68a89ffc0cd3ae3c8e0b78'
A5_ROW_SHA256 = 'f9a933141393262edb66e3e8248ed75ebf4518668039e1a27af6734f26f58b9d'
A5_CODE_SOURCE_ID = 'Codex ARV2 R298 A5 20261024'
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_JSON_DEPTH, MAX_JSON_NODES = 128, 131072
FALSE_FLAGS = {
    'response_provenance_authenticated': False,
    'privacy_proven': False,
    'edit_lock_proven': False,
    'synthetic_entry_proven': False,
    'operational_retry_authority': False,
    'strategy_result_accepted': False,
}
FINITE_CODES = frozenset(('json_shape', 'response_shape', 'response_bound',
    'response_refused', 'project_shape', 'project_id', 'organization', 'name',
    'language', 'owner', 'public_contradiction', 'idle', 'owner_id',
    'dedicated_owner', 'dedicated_permissions', 'owner_row_pin',
    'general_collaborators', 'owner_row_match', 'extra_row_shape', 'extra_row_pin'))


class AccessRefused(ValueError):
    """Finite local predicate only; never raw response data or provider text."""


def _require(condition, code):
    if not condition:
        raise AccessRefused(code)


def _canonical(value):
    try:
        # Validate before encoding: JSON round trips otherwise silently turn
        # tuples and builtin subclasses into apparently exact list/scalar types.
        pending, nodes = [(value, 0)], 0
        while pending:
            current, depth = pending.pop()
            nodes += 1
            _require(depth <= MAX_JSON_DEPTH and nodes <= MAX_JSON_NODES, 'json_shape')
            kind = type(current)
            if kind is dict:
                _require(len(current) <= MAX_JSON_NODES - nodes - len(pending), 'json_shape')
                _require(all(type(key) is str for key in current), 'json_shape')
                pending.extend((item, depth + 1) for item in current.values())
            elif kind is list:
                _require(len(current) <= MAX_JSON_NODES - nodes - len(pending), 'json_shape')
                pending.extend((item, depth + 1) for item in current)
            elif kind is float:
                _require(math.isfinite(current), 'json_shape')
            else:
                _require(kind in (type(None), bool, int, str), 'json_shape')
        return json.dumps(value, sort_keys=True, ensure_ascii=True,
            separators=(',', ':'), allow_nan=False).encode('ascii') + b'\n'
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise AccessRefused('json_shape') from None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def finite_error(error):
    code = 'unknown'
    if type(error) is AccessRefused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE_CODES:
            code = args[0]
    return {'code': code}


def profile_record():
    return {'schema': SCHEMA, 'project_id': PROJECT_ID, 'project_name': PROJECT_NAME,
        'organization_sha256': ORGANIZATION_SHA256, 'owner_row_sha256': OWNER_ROW_SHA256,
        'a5_row_sha256': A5_ROW_SHA256, 'a5_code_source_id_sha256': _sha(_canonical(A5_CODE_SOURCE_ID)),
        'max_response_bytes': MAX_RESPONSE_BYTES, 'max_json_depth': MAX_JSON_DEPTH,
        'max_json_nodes': MAX_JSON_NODES, 'max_general_collaborators': 2,
        'exact_dedicated_collaborators': 1, 'historical_mia_accepted': False,
        'scope': 'pure_current_access_representation_only', **FALSE_FLAGS}


def _organization(value):
    _require(type(value) is str and re.fullmatch('[0-9a-f]{32}', value)
        and _sha(value.encode('ascii')) == ORGANIZATION_SHA256, 'organization')


def _optional_scope(response):
    if 'projectId' in response:
        _require(type(response['projectId']) is int and response['projectId'] == PROJECT_ID, 'project_id')
    if 'organizationId' in response:
        _organization(response['organizationId'])


def _response(value):
    _require(type(value) is dict, 'response_shape')
    raw = _canonical(value)
    _require(0 < len(raw) <= MAX_RESPONSE_BYTES, 'response_bound')
    # This memory-only snapshot is independent of caller-owned nested objects.
    copied = json.loads(raw)
    _require(copied.get('success') is True and ('errors' not in copied
        or (type(copied['errors']) is list and copied['errors'] == [])), 'response_refused')
    _optional_scope(copied)
    return copied


def verify_access(project_response, dedicated_response):
    """Check supplied current representations, without acting on the result.

    Missing dedicated project IDs remain absent, not invented. Exact request
    scope and provenance belong to a future caller; owner equality cannot prove
    which endpoint produced an unauthenticated object. Hash pins are fixed
    here, not supplied by callers or refreshed from a response.
    """
    project_packet, dedicated = _response(project_response), _response(dedicated_response)
    projects = project_packet.get('projects')
    _require(type(projects) is list and len(projects) == 1 and type(projects[0]) is dict, 'project_shape')
    project = projects[0]
    _require(type(project.get('projectId')) is int and project['projectId'] == PROJECT_ID, 'project_id')
    _organization(project.get('organizationId'))
    _require(type(project.get('name')) is str and project['name'] == PROJECT_NAME, 'name')
    _require(type(project.get('language')) is str and project['language'] == 'Py', 'language')
    _require(project.get('owner') is True, 'owner')
    # Absence/false is not privacy proof; contradictory values still refuse.
    _require('public' not in project or project['public'] is False, 'public_contradiction')
    _require(project.get('codeRunning') is False, 'idle')
    owner_id = project.get('ownerId')
    _require(type(owner_id) is int and 0 < owner_id < 2 ** 63, 'owner_id')

    owners = dedicated.get('collaborators')
    _require(type(owners) is list and len(owners) == 1 and type(owners[0]) is dict, 'dedicated_owner')
    owner = owners[0]
    _require(owner.get('owner') is True and type(owner.get('uid')) is int and owner['uid'] == owner_id
        and type(owner.get('permission')) is str and owner['permission'] == 'write'
        and owner.get('liveControl') is True, 'dedicated_owner')
    _require(type(dedicated.get('userPermissions')) is str and dedicated['userPermissions'] == 'write'
        and dedicated.get('userLiveControl') is True, 'dedicated_permissions')
    owner_bytes = _canonical(owner)
    _require(_sha(owner_bytes) == OWNER_ROW_SHA256, 'owner_row_pin')

    collaborators = project.get('collaborators')
    _require(type(collaborators) is list and 1 <= len(collaborators) <= 2
        and all(type(row) is dict for row in collaborators), 'general_collaborators')
    matching = [row for row in collaborators if _canonical(row) == owner_bytes]
    _require(len(matching) == 1, 'owner_row_match')
    extra_pin = None
    for row in collaborators:
        if _canonical(row) == owner_bytes:
            continue
        _require(row.get('owner') is False and 'uid' in row and row['uid'] is None
            and type(row.get('permission')) is str and row['permission'] == 'write'
            and row.get('liveControl') is True
            and type(row.get('name')) is str and row['name'] == A5_CODE_SOURCE_ID
            and type(row.get('publicId')) is str and row['publicId'] == A5_CODE_SOURCE_ID
            and 'codeSourceId' not in row, 'extra_row_shape')
        extra_pin = _sha(_canonical(row))
        # The real observed row includes unreported fields. Pin the WHOLE row;
        # six matching visible fields, or a newly matching name, are insufficient.
        _require(extra_pin == A5_ROW_SHA256, 'extra_row_pin')

    return {'schema': SCHEMA, 'project_id': PROJECT_ID, 'organization_sha256': ORGANIZATION_SHA256,
        'owner_row_sha256': OWNER_ROW_SHA256, 'general_count': len(collaborators), 'dedicated_count': 1,
        'extra_kind': 'r314_observed_a5' if extra_pin is not None else 'none',
        'extra_row_sha256': extra_pin, 'matched_current_access_representation': True, **FALSE_FLAGS}
