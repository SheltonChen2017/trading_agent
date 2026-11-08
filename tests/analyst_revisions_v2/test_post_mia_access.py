"""Synthetic supplied metadata only; native artifact/network denial required."""
import copy
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r298_post_mia_access as m


@pytest.fixture
def supplied(monkeypatch):
    owner = {'owner': True, 'uid': 123, 'name': 'SYNTHETIC-OWNER-PRIVATE',
        'publicId': 'SYNTHETIC-PUBLIC-ID', 'permission': 'write', 'liveControl': True,
        'email': 'PRIVATE-EMAIL@example.invalid'}
    extra = {'owner': False, 'uid': None, 'name': m.access.A5_CODE_SOURCE_ID,
        'publicId': m.access.A5_CODE_SOURCE_ID, 'permission': 'write', 'liveControl': True,
        'hidden-private-field': 'SYNTHETIC-PRIVATE-VALUE'}
    monkeypatch.setattr(m.access, 'ORGANIZATION_SHA256', m.sha(b'a' * 32))
    monkeypatch.setattr(m.access, 'OWNER_ROW_SHA256', m.sha(m.canonical(owner)))
    monkeypatch.setattr(m.access, 'A5_ROW_SHA256', m.sha(m.canonical(extra)))
    project = {'projectId': m.access.PROJECT_ID, 'organizationId': 'a' * 32,
        'name': m.access.PROJECT_NAME, 'language': 'Py', 'owner': True, 'ownerId': 123,
        'codeRunning': False, 'collaborators': [copy.deepcopy(owner), copy.deepcopy(extra)]}
    return NS(project={'success': True, 'projects': [project]},
        dedicated={'success': True, 'collaborators': [copy.deepcopy(owner)],
            'userPermissions': 'write', 'userLiveControl': True}, owner=owner, extra=extra)


def observe(value):
    return m.observe(value.project, value.dedicated)


def test_bounded_success_is_observation_only_and_contains_no_raw_identifiers(supplied):
    before = copy.deepcopy((supplied.project, supplied.dedicated))
    result = observe(supplied)
    assert result['strict_policy_check'] == 'passed' and result['access_failure_code'] is None
    assert result['general']['count'] == 2 and result['dedicated']['count'] == 1
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    assert result['general']['rows'][0]['matches_known_owner_row'] is True
    assert result['general']['rows'][1]['matches_known_a5_row'] is True
    assert result['general']['rows'][1]['identifier_matches']['name']['is_a5'] is True
    assert result['dedicated']['rows'][0]['uid_matches_project_owner'] is True
    raw = m.canonical(result)
    for secret in (b'SYNTHETIC-', b'PRIVATE-EMAIL', b'@example.invalid', b'Codex ARV2', b'aaaaaaaaaaaaaaaa'):
        assert secret not in raw
    assert len(raw) <= m.MAX_OUTPUT and (supplied.project, supplied.dedicated) == before
    copied = m.validate_observation(result)
    copied['general']['rows'].clear()
    assert result['general']['count'] == len(result['general']['rows']) == 2


@pytest.mark.parametrize('field,bad,code', [('projectId', True, 'scope_project_id'),
    ('projectId', 1, 'scope_project_id'), ('organizationId', 'b' * 32, 'scope_organization'),
    ('name', 'OTHER-PRIVATE-NAME', 'scope_name'), ('language', 'C#', 'scope_language'),
    ('owner', False, 'scope_owner'), ('owner', 1, 'scope_owner'),
    ('ownerId', True, 'scope_owner_id'), ('ownerId', 0, 'scope_owner_id'), ('ownerId', 2**63, 'scope_owner_id')])
def test_scope_contradictions_fail_finitely_without_blessing_metadata(supplied, field, bad, code):
    supplied.project['projects'][0][field] = bad
    with pytest.raises(m.Refused) as error:
        observe(supplied)
    assert m.finite(error.value) == code


@pytest.mark.parametrize('which', ['project', 'dedicated'])
@pytest.mark.parametrize('key,bad,code', [('projectId', 1, 'scope_project_id'),
    ('organizationId', 'b' * 32, 'scope_organization')])
def test_optional_outer_scope_cannot_contradict_fixed_project(supplied, which, key, bad, code):
    getattr(supplied, which)[key] = bad
    with pytest.raises(m.Refused, match=code):
        observe(supplied)


@pytest.mark.parametrize('field,bad,flag,code', [('codeRunning', True, 'true', 'idle'),
    ('codeRunning', None, 'other', 'idle'), ('codeRunning', 0, 'other', 'idle'),
    ('public', True, 'true', 'public_contradiction'), ('public', 0, 'other', 'public_contradiction')])
def test_access_refusal_preserves_explicit_flag_and_exact_predicate(supplied, field, bad, flag, code):
    supplied.project['projects'][0][field] = bad
    result = observe(supplied)
    assert result['strict_policy_check'] == 'refused' and result['access_failure_code'] == code
    assert result['project']['code_running' if field == 'codeRunning' else 'public'] == flag
    assert all(result[name] is False for name in m.FALSE_FLAGS)


@pytest.mark.parametrize('field', ['codeRunning', 'public'])
def test_missing_flags_remain_missing_not_false(supplied, field):
    supplied.project['projects'][0].pop(field, None)
    result = observe(supplied)
    assert result['project']['code_running' if field == 'codeRunning' else 'public'] == 'missing'
    assert result['access_failure_code'] == ('idle' if field == 'codeRunning' else None)


@pytest.mark.parametrize('which', ['general', 'dedicated'])
def test_mia_rows_are_described_but_not_accepted_or_exposed(supplied, which):
    row = {'name': 'Mia', 'publicId': 'Mia', 'codeSourceId': 'Mia', 'owner': False,
        'uid': None, 'permission': 'read', 'liveControl': False, 'private-field': 'SECRET'}
    packet = supplied.project['projects'][0] if which == 'general' else supplied.dedicated
    packet['collaborators'].append(row)
    result = observe(supplied)
    assert result['strict_policy_check'] == 'refused'
    assert result[which]['rows'][-1]['identifier_matches'] == {
        key: {'is_mia': True, 'is_mia_ai': False, 'is_a5': False} for key in m.IDENTITY_FIELDS}
    assert result[which]['rows'][-1]['row_sha256'] == m.sha(m.canonical(row))
    assert b'SECRET' not in m.canonical(result) and b'"Mia"' not in m.canonical(result)


def test_public_mia_ai_actor_label_and_unknown_identifiers_are_hashed_without_acceptance(supplied):
    row = {'owner': False, 'name': 'Mia', 'publicId': 'mia-ai', 'codeSourceId': 'UNKNOWN-PRIVATE-LOCK',
        'permission': 'write', 'liveControl': True, 'uid': None}
    supplied.project['projects'][0]['collaborators'].append(row)
    result = observe(supplied)
    observed = result['general']['rows'][-1]
    assert result['strict_policy_check'] == 'refused'
    assert observed['identifier_matches']['publicId'] == {'is_mia': False, 'is_mia_ai': True, 'is_a5': False}
    assert observed['identifier_value_sha256'] == {name: m.sha(m.canonical(row[name])) for name in m.IDENTITY_FIELDS}
    assert b'UNKNOWN-PRIVATE-LOCK' not in m.canonical(result) and b'"mia-ai"' not in m.canonical(result)


def test_missing_identifier_is_distinct_from_present_null_value_hash(supplied):
    result = observe(supplied)
    assert result['general']['rows'][0]['field_types']['codeSourceId'] == 'missing'
    assert result['general']['rows'][0]['identifier_value_sha256']['codeSourceId'] is None
    supplied.project['projects'][0]['collaborators'][1]['codeSourceId'] = None
    changed = observe(supplied)['general']['rows'][1]
    assert changed['field_types']['codeSourceId'] == 'null'
    assert changed['identifier_value_sha256']['codeSourceId'] == m.sha(m.canonical(None))
    assert all(flag is False for flag in changed['identifier_matches']['codeSourceId'].values())


@pytest.mark.parametrize('change', ['missing-hash', 'present-hash', 'false-label', 'bool-label', 'uid-hash'])
def test_identifier_hashes_bind_presence_types_and_closed_label_flags(supplied, change):
    result = observe(supplied)
    row = result['general']['rows'][0]
    if change == 'missing-hash': row['identifier_value_sha256']['codeSourceId'] = 'a' * 64
    elif change == 'present-hash': row['identifier_value_sha256']['name'] = None
    elif change == 'false-label': row['identifier_matches']['name']['is_mia_ai'] = True
    elif change == 'bool-label': row['identifier_matches']['name']['is_mia_ai'] = 1
    else: row['identifier_value_sha256']['uid'] = 'a' * 64
    with pytest.raises(m.Refused, match='observation_shape'):
        m.validate_observation(result)


def test_changed_full_row_hash_not_visible_fields_remains_refused(supplied):
    supplied.project['projects'][0]['collaborators'][1]['unreported'] = 'SECRET'
    result = observe(supplied)
    assert result['access_failure_code'] == 'extra_row_pin'
    assert result['general']['rows'][1]['matches_known_a5_row'] is False
    assert result['general']['rows'][1]['identifier_matches']['name']['is_a5'] is True


@pytest.mark.parametrize('which', ['general', 'dedicated'])
@pytest.mark.parametrize('rows', [None, {}, 'PRIVATE-TEXT', [], [None], ['PRIVATE-ROW']])
def test_wrong_collaborator_shapes_are_redacted_without_silent_zero_count(supplied, which, rows):
    packet = supplied.project['projects'][0] if which == 'general' else supplied.dedicated
    packet['collaborators'] = rows
    result = observe(supplied)
    assert result['strict_policy_check'] == 'refused'
    assert result[which]['count'] == (len(rows) if type(rows) is list else None)
    assert b'PRIVATE-' not in m.canonical(result)


@pytest.mark.parametrize('which', ['general', 'dedicated'])
def test_ninth_row_refuses_before_access_policy_or_unbounded_census(supplied, which, monkeypatch):
    packet = supplied.project['projects'][0] if which == 'general' else supplied.dedicated
    packet['collaborators'] = [{}] * 9
    monkeypatch.setattr(m.access, 'verify_access', lambda *args: pytest.fail('policy after row bound'))
    with pytest.raises(m.Refused, match='row_bound'):
        observe(supplied)


@pytest.mark.parametrize('code', sorted(m.access.FINITE_CODES))
def test_every_exact_foreign_access_refusal_code_is_retained(supplied, monkeypatch, code):
    def refuse(*args):
        raise m.access.AccessRefused(code)
    monkeypatch.setattr(m.access, 'verify_access', refuse)
    result = observe(supplied)
    assert result['access_failure_code'] == code and result['strict_policy_check'] == 'refused'


@pytest.mark.parametrize('args', [(), ('not-in-inventory',), ('idle', 'extra'), (True,), (object(),)])
def test_malformed_exception_arguments_stay_unknown_without_stringification(supplied, monkeypatch, args):
    class Hostile(m.access.AccessRefused):
        def __str__(self):
            pytest.fail('raw exception rendered')
    def refuse(*unused):
        raise Hostile(*args)
    monkeypatch.setattr(m.access, 'verify_access', refuse)
    assert observe(supplied)['access_failure_code'] == 'unknown'


def test_ordinary_scope_response_rejection_never_formats_hostile_objects(supplied):
    class Hostile:
        def __str__(self):
            pytest.fail('hostile value rendered')
        def __deepcopy__(self, memo):
            pytest.fail('hostile value copied')
    supplied.project['private'] = Hostile()
    with pytest.raises(m.Refused, match='scope_response'):
        observe(supplied)


@pytest.mark.parametrize('change', ['extra', 'project', 'flag', 'failure', 'scope', 'row-sha',
    'row-count', 'row-bool', 'type', 'identifier', 'passed-running'])
def test_output_validator_refuses_extra_raw_data_or_type_aliases(supplied, change):
    result = observe(supplied)
    if change == 'extra': result['raw_rows'] = []
    elif change == 'project': result['project_id'] = True
    elif change == 'flag': result['access_authorized'] = 0
    elif change == 'failure': result['access_failure_code'] = 'idle'
    elif change == 'scope': result['scope_bound'] = 1
    elif change == 'row-sha': result['general']['rows'][0]['row_sha256'] = 'a' * 64
    elif change == 'row-count': result['general']['count'] = True
    elif change == 'row-bool': result['general']['rows'][0]['uid_matches_project_owner'] = 1
    elif change == 'type': result['project']['field_types']['owner'] = 'PRIVATE-TYPE'
    elif change == 'identifier': result['general']['rows'][0]['identifier_matches']['name']['is_mia'] = 'true'
    else: result['project']['code_running'] = 'true'
    with pytest.raises(m.Refused):
        m.validate_observation(result)


def test_profile_and_observer_have_no_operational_entrypoint_or_filesystem(supplied, monkeypatch):
    assert not hasattr(m, 'main') and not hasattr(m, 'Store')
    monkeypatch.setattr(Path, 'read_bytes', lambda *args: pytest.fail('filesystem read'))
    profile = m.profile_record()
    assert profile['max_rows_per_view'] == 8 and all(profile[name] is False for name in m.FALSE_FLAGS)
    assert b'Codex ARV2' not in m.canonical(profile) and b'SYNTHETIC-' not in m.canonical(profile)
    assert observe(supplied)['project_id'] == m.access.PROJECT_ID
