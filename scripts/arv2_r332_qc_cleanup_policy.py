"""Pure, conservative selection for owner-directed Analyst QC recycling.

Inputs are supplied metadata, never credentials or project source. A positive
decision is a candidate classification, not a mutation capability: the caller
must re-read current project/history and compare the exact selected metadata
before one recoverable recycle operation. Unknown state preserves the project.
"""
import hashlib
import json
import re

SCHEMA = 'arv2-r332-qc-cleanup-policy-v1'
PROTECTED = frozenset((38522505, 38364439, 37165262, 36823601))
# A historical ID alone does not establish a project's current purpose. The
# compile/refusal projects without an exact current-name witness can qualify
# only through the independently checked no-successful-backtest criterion.
VERIFICATION_PROJECTS = ((37705240, 'ARV2 R284 PUBLIC SEVEN IDENTITY 20261007'),)
VERIFICATION_ONLY = frozenset(identity for identity, _ in VERIFICATION_PROJECTS)
COMPLETED = frozenset(('Completed.', 'Completed'))
TERMINAL = COMPLETED | frozenset(('Runtime Error', 'Runtime Error.', 'Stopped',
    'Stopped.', 'Cancelled', 'Cancelled.', 'Canceled', 'Canceled.',
    'Build Error', 'Build Error.', 'Compilation Error', 'Compilation Error.'))
FINITE = frozenset(('project_shape', 'project_id', 'project_name', 'record',
    'user_id', 'collaborators', 'libraries', 'history_shape', 'history_count',
    'history_row', 'history_duplicate', 'references'))
_LANE = re.compile(r'(?:^|[\s/_-])(?:ARV2|Analyst[ _-]+Revisions?)(?:$|[\s/_-])', re.I)
_OTHER_LANE = re.compile(r'insider|short[ _-]*interest|target[ _-]*price', re.I)


class Refused(ValueError):
    """Finite metadata refusal; do not render arbitrary input or exceptions."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _id(value):
    require(type(value) is int and 0 < value <= 2147483647, 'project_id')
    return value


def _identity(project):
    require(type(project) is dict, 'project_shape')
    project_id = _id(project.get('projectId'))
    name = project.get('name')
    require(type(name) is str and 0 < len(name) <= 240 and name.isascii()
        and all(32 <= ord(c) < 127 for c in name), 'project_name')
    return project_id, name


def ownership(project, record_bytes):
    """Require both a lane name and a separate exact project-ID record witness."""
    require(type(project) is dict, 'project_shape')
    project_id = _id(project.get('projectId'))
    name = project.get('name')
    require(type(name) is str and 0 < len(name) <= 4096, 'project_name')
    require(type(record_bytes) is bytes and 0 < len(record_bytes) <= 16 * 1024 * 1024, 'record')
    if name.casefold().startswith('recycle bin/') or _OTHER_LANE.search(name) or not _LANE.search(name):
        return False
    _identity(project)
    return re.search(rb'(?<![0-9])' + str(project_id).encode('ascii') + rb'(?![0-9])', record_bytes) is not None


def _library_ids(project):
    rows = project.get('libraries')
    require(type(rows) is list and len(rows) <= 1000, 'libraries')
    ids = []
    for row in rows:
        require(type(row) is dict, 'libraries')
        ids.append(_id(row.get('projectId')))
    require(len(ids) == len(set(ids)), 'libraries')
    return tuple(sorted(ids))


def referenced_project_ids(projects):
    """Transient reverse-library protection, without retaining other-lane rows."""
    require(type(projects) is list and len(projects) <= 10000, 'references')
    return frozenset(value for project in projects for value in _library_ids(project))


def project_summary(project, user_id):
    """A fixed metadata projection; never copies arbitrary or sensitive extras."""
    project_id, name = _identity(project)
    require(type(user_id) is int and user_id > 0, 'user_id')
    owner_id = project.get('ownerId')
    collaborators = project.get('collaborators')
    require(type(collaborators) is list and len(collaborators) <= 1000, 'collaborators')
    solo = True
    for row in collaborators:
        require(type(row) is dict, 'collaborators')
        # Unknown or different collaborators are preserved, including edit locks.
        if type(row.get('uid')) is not int or row['uid'] != user_id or row.get('owner') is not True:
            solo = False
    libraries = _library_ids(project)
    return {'project_id': project_id, 'name': name,
        'owner_current': project.get('owner') is True and type(owner_id) is int and owner_id == user_id,
        'idle': project.get('codeRunning') is False,
        'python': project.get('language') == 'Py',
        'sole_owner': solo, 'libraries': list(libraries),
        'library': project.get('isLibrary', False) is not False,
        'live_presence': 'lastLiveDeployment' not in project or 'leanEnvironment' not in project
            or project['lastLiveDeployment'] not in (None, '') or type(project['leanEnvironment']) is not int
            or project['leanEnvironment'] != 0}


def history_summary(history):
    """Only IDs/statuses cross the boundary; performance fields are untouched."""
    require(type(history) is dict and history.get('success') is True
        and ('errors' not in history or history['errors'] == []), 'history_shape')
    rows = history.get('backtests')
    require(type(rows) is list and len(rows) <= 10000, 'history_shape')
    require(type(history.get('count')) is int and history['count'] == len(rows), 'history_count')
    selected, seen = [], set()
    for row in rows:
        require(type(row) is dict, 'history_row')
        identity, status = row.get('backtestId'), row.get('status')
        require(type(identity) is str and re.fullmatch('[0-9a-f]{32}', identity) is not None
            and type(status) is str and 0 < len(status) <= 64, 'history_row')
        require(identity not in seen, 'history_duplicate')
        seen.add(identity)
        selected.append({'backtest_id': identity, 'status': status})
    selected.sort(key=lambda row: row['backtest_id'])
    return {'backtest_count': len(selected),
        'completed_count': sum(row['status'] in COMPLETED for row in selected),
        'all_terminal': all(row['status'] in TERMINAL for row in selected),
        'history_sha256': digest(selected)}


def decision(project, history, *, user_id, record_bytes, referenced_ids=frozenset()):
    """Return a finite candidate decision; unsafe/unknown state never deletes."""
    project_id, name = _identity(project)
    owned = ownership(project, record_bytes)
    result = {'project_id': project_id, 'name': name, 'lane_owned': owned,
        'eligible': False, 'reason': 'outside_lane',
        'verification_only': (project_id, name) in VERIFICATION_PROJECTS,
        'completed_count': None, 'backtest_count': None, 'history_sha256': None}
    if not owned:
        return result
    summary = project_summary(project, user_id)
    require(type(referenced_ids) is frozenset and all(type(value) is int for value in referenced_ids), 'references')
    for blocked, reason in (
        (project_id in PROTECTED, 'protected_dependency'),
        (project_id in referenced_ids, 'referenced_library'),
        (not summary['owner_current'], 'owner_unverified'),
        (not summary['idle'], 'active_or_unknown'),
        (not summary['python'], 'language_unverified'),
        (not summary['sole_owner'], 'collaborator_present'),
        (bool(summary['libraries']) or summary['library'], 'library_dependency'),
        (summary['live_presence'], 'live_metadata_present'),
    ):
        if blocked:
            result['reason'] = reason
            return result
    selected = history_summary(history)
    result.update({key: selected[key] for key in ('completed_count', 'backtest_count', 'history_sha256')})
    if not selected['all_terminal']:
        result['reason'] = 'nonterminal_or_unknown_history'
    elif result['verification_only']:
        result.update(eligible=True, reason='verification_only')
    elif selected['completed_count'] == 0:
        result.update(eligible=True, reason='no_successful_backtest')
    else:
        result['reason'] = 'successful_backtest_retained'
    return result
