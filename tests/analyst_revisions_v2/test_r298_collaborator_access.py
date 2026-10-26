"""Pure synthetic access checks; native network/artifact/Keychain denial required."""
import copy
import sys
from types import SimpleNamespace

import pytest

from scripts import arv2_r298_collaborator_access as m


@pytest.fixture
def supplied(monkeypatch):
    owner = {'owner': True, 'uid': 123, 'name': 'Synthetic owner',
        'publicId': 'synthetic-owner', 'permission': 'write', 'liveControl': True}
    extra = {'owner': False, 'uid': None, 'name': m.A5_CODE_SOURCE_ID,
        'publicId': m.A5_CODE_SOURCE_ID, 'permission': 'write', 'liveControl': True,
        'synthetic-unreported-field': {'test-only': 1}}
    monkeypatch.setattr(m, 'ORGANIZATION_SHA256', m._sha(b'a' * 32))
    monkeypatch.setattr(m, 'OWNER_ROW_SHA256', m._sha(m._canonical(owner)))
    monkeypatch.setattr(m, 'A5_ROW_SHA256', m._sha(m._canonical(extra)))
    project = {'projectId': m.PROJECT_ID, 'organizationId': 'a' * 32,
        'name': m.PROJECT_NAME, 'language': 'Py', 'owner': True, 'ownerId': 123,
        'codeRunning': False, 'collaborators': [copy.deepcopy(owner), copy.deepcopy(extra)]}
    return SimpleNamespace(project={'success': True, 'projects': [project]},
        dedicated={'success': True, 'collaborators': [copy.deepcopy(owner)],
            'userPermissions': 'write', 'userLiveControl': True}, owner=owner, extra=extra)


def verify(supplied):
    return m.verify_access(supplied.project, supplied.dedicated)


@pytest.mark.parametrize('has_extra,reverse', [(False, False), (True, False), (True, True)])
def test_only_pinned_owner_with_optional_exact_observed_a5_row(supplied, has_extra, reverse):
    rows = [copy.deepcopy(supplied.owner)] + ([copy.deepcopy(supplied.extra)] if has_extra else [])
    supplied.project['projects'][0]['collaborators'] = list(reversed(rows)) if reverse else rows
    result = verify(supplied)
    assert result['matched_current_access_representation'] is True
    assert result['extra_kind'] == ('r314_observed_a5' if has_extra else 'none')
    assert result['extra_row_sha256'] == (m.A5_ROW_SHA256 if has_extra else None)
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    assert b'Synthetic owner' not in m._canonical(result) and b'test-only' not in m._canonical(result)


@pytest.mark.parametrize('key,value,code', [('projectId', True, 'project_id'),
    ('projectId', 1, 'project_id'), ('organizationId', 'b' * 32, 'organization'),
    ('organizationId', 'A' * 32, 'organization'), ('organizationId', None, 'organization'),
    ('name', 'different', 'name'), ('language', 'C#', 'language'), ('owner', 1, 'owner'),
    ('owner', False, 'owner'), ('ownerId', True, 'owner_id'), ('ownerId', 0, 'owner_id'),
    ('ownerId', 2 ** 63, 'owner_id'), ('ownerId', '123', 'owner_id'), ('ownerId', 123.0, 'owner_id'),
    ('codeRunning', 0, 'idle'), ('codeRunning', None, 'idle'), ('codeRunning', True, 'idle'),
    ('public', True, 'public_contradiction'), ('public', None, 'public_contradiction'),
    ('public', 0, 'public_contradiction')])
def test_positive_project_scope_and_contradictions(supplied, key, value, code):
    supplied.project['projects'][0][key] = value
    with pytest.raises(m.AccessRefused, match='^' + code + '$'): verify(supplied)


@pytest.mark.parametrize('key', ['projectId', 'organizationId', 'name', 'language', 'owner', 'ownerId', 'codeRunning'])
def test_project_binding_fields_are_mandatory(supplied, key):
    del supplied.project['projects'][0][key]
    with pytest.raises(m.AccessRefused): verify(supplied)


@pytest.mark.parametrize('rows', [None, {}, [], [None], [{}, {}]])
def test_exact_single_project_shape(supplied, rows):
    supplied.project['projects'] = rows
    with pytest.raises(m.AccessRefused, match='project_shape'): verify(supplied)


@pytest.mark.parametrize('which', ['project', 'dedicated'])
@pytest.mark.parametrize('key,value,code', [('projectId', True, 'project_id'),
    ('projectId', 1, 'project_id'), ('projectId', None, 'project_id'),
    ('organizationId', 'b' * 32, 'organization'), ('organizationId', 0, 'organization')])
def test_optional_outer_scope_cannot_contradict_fixed_project(supplied, which, key, value, code):
    getattr(supplied, which)[key] = value
    with pytest.raises(m.AccessRefused, match=code): verify(supplied)


def test_matching_optional_scope_and_public_false_do_not_prove_privacy(supplied):
    for value in (supplied.project, supplied.dedicated):
        value.update(projectId=m.PROJECT_ID, organizationId='a' * 32)
    supplied.project['projects'][0]['public'] = False
    result = verify(supplied)
    assert result['privacy_proven'] is result['response_provenance_authenticated'] is False


@pytest.mark.parametrize('which', ['project', 'dedicated'])
@pytest.mark.parametrize('packet,code', [(None, 'response_shape'), ([], 'response_shape'),
    ({}, 'response_refused'), ({'success': 1}, 'response_refused'),
    ({'success': True, 'errors': ['secret']}, 'response_refused'),
    ({'success': True, 'errors': None}, 'response_refused'),
    ({'success': True, 'data': float('nan')}, 'json_shape'),
    ({'success': True, 'data': 's' * (1024 * 1024)}, 'response_bound')])
def test_response_shape_bounds_and_explicit_refusals(supplied, which, packet, code):
    setattr(supplied, which, packet)
    with pytest.raises(m.AccessRefused, match=code): verify(supplied)


@pytest.mark.parametrize('key,value', [('owner', False), ('owner', 1), ('uid', True),
    ('uid', 123.0), ('uid', 124), ('uid', None), ('permission', 'read'),
    ('permission', 1), ('liveControl', False), ('liveControl', 1)])
def test_dedicated_owner_positive_types_and_permissions(supplied, key, value):
    supplied.dedicated['collaborators'][0][key] = value
    with pytest.raises(m.AccessRefused, match='dedicated_owner'): verify(supplied)


@pytest.mark.parametrize('key,value', [('userPermissions', 'read'), ('userPermissions', True),
    ('userPermissions', None), ('userLiveControl', False), ('userLiveControl', 1), ('userLiveControl', None)])
def test_dedicated_current_user_permissions(supplied, key, value):
    supplied.dedicated[key] = value
    with pytest.raises(m.AccessRefused, match='dedicated_permissions'): verify(supplied)


@pytest.mark.parametrize('key', ['owner', 'uid', 'permission', 'liveControl'])
def test_dedicated_owner_required_fields(supplied, key):
    supplied.dedicated['collaborators'][0].pop(key)
    with pytest.raises(m.AccessRefused, match='dedicated_owner'): verify(supplied)


@pytest.mark.parametrize('rows', [None, [], {}, [None], [{}, {}]])
def test_dedicated_is_exactly_one_owner(supplied, rows):
    supplied.dedicated['collaborators'] = rows
    with pytest.raises(m.AccessRefused, match='dedicated_owner'): verify(supplied)


def test_changed_owner_row_refuses_even_when_both_views_match(supplied):
    supplied.dedicated['collaborators'][0]['unknown-private-field'] = 'changed'
    supplied.project['projects'][0]['collaborators'][0] = copy.deepcopy(supplied.dedicated['collaborators'][0])
    with pytest.raises(m.AccessRefused, match='owner_row_pin'): verify(supplied)


def test_changed_owner_id_and_uid_cannot_replace_pinned_identity(supplied):
    supplied.project['projects'][0]['ownerId'] = 124
    supplied.dedicated['collaborators'][0]['uid'] = 124
    supplied.project['projects'][0]['collaborators'][0]['uid'] = 124
    with pytest.raises(m.AccessRefused, match='owner_row_pin'): verify(supplied)


def test_general_owner_must_be_whole_row_identical(supplied):
    supplied.project['projects'][0]['collaborators'][0]['name'] = 'different'
    with pytest.raises(m.AccessRefused, match='owner_row_match'): verify(supplied)


@pytest.mark.parametrize('kind', ['absent', 'null', 'empty', 'nonobject', 'duplicate_owner',
    'owner_missing', 'three', 'both_extras'])
def test_closed_general_inventory(supplied, kind):
    project = supplied.project['projects'][0]
    if kind == 'absent': project.pop('collaborators')
    elif kind == 'null': project['collaborators'] = None
    elif kind == 'empty': project['collaborators'] = []
    elif kind == 'nonobject': project['collaborators'] = [supplied.owner, None]
    elif kind == 'duplicate_owner': project['collaborators'] = [supplied.owner, copy.deepcopy(supplied.owner)]
    elif kind == 'owner_missing': project['collaborators'] = [supplied.extra]
    else: project['collaborators'] = [supplied.owner, supplied.extra, copy.deepcopy(supplied.extra)]
    with pytest.raises(m.AccessRefused): verify(supplied)


@pytest.mark.parametrize('key,value', [('owner', True), ('owner', 0), ('uid', 0), ('uid', ''),
    ('permission', 'read'), ('permission', 1), ('liveControl', False), ('liveControl', 1),
    ('name', 'Mia'), ('name', 'Codex ARV2 R298 A6 20261024'), ('name', None),
    ('publicId', 'mia-ai'), ('publicId', None), ('codeSourceId', None),
    ('codeSourceId', m.A5_CODE_SOURCE_ID)])
def test_extra_named_types_are_independent_of_full_row_pin(supplied, monkeypatch, key, value):
    extra = supplied.project['projects'][0]['collaborators'][1]
    extra[key] = value
    # Even a mistakenly repinned wrong row cannot bypass explicit field gates.
    monkeypatch.setattr(m, 'A5_ROW_SHA256', m._sha(m._canonical(extra)))
    with pytest.raises(m.AccessRefused, match='extra_row_shape'): verify(supplied)


@pytest.mark.parametrize('key', ['owner', 'uid', 'permission', 'liveControl', 'name', 'publicId'])
def test_extra_required_fields_cannot_disappear(supplied, monkeypatch, key):
    extra = supplied.project['projects'][0]['collaborators'][1]
    extra.pop(key)
    monkeypatch.setattr(m, 'A5_ROW_SHA256', m._sha(m._canonical(extra)))
    with pytest.raises(m.AccessRefused, match='extra_row_shape'): verify(supplied)


@pytest.mark.parametrize('mutation', ['unknown_value', 'unknown_new', 'unknown_removed', 'six_fields_only'])
def test_matching_known_fields_do_not_replace_whole_row_pin(supplied, mutation):
    extra = supplied.project['projects'][0]['collaborators'][1]
    if mutation == 'unknown_value': extra['synthetic-unreported-field']['test-only'] = 2
    elif mutation == 'unknown_new': extra['new-private-field'] = 'private'
    else: extra.pop('synthetic-unreported-field')
    with pytest.raises(m.AccessRefused, match='extra_row_pin'): verify(supplied)


def test_known_historical_mia_is_not_accepted_current_extra(supplied, monkeypatch):
    extra = supplied.project['projects'][0]['collaborators'][1]
    extra.update(name='Mia', publicId='synthetic-old-mia')
    monkeypatch.setattr(m, 'A5_ROW_SHA256', m._sha(m._canonical(extra)))
    with pytest.raises(m.AccessRefused, match='extra_row_shape'): verify(supplied)


def test_frozen_a5_pure_policy_reproduces_refusal_without_operational_replay(supplied):
    from scripts import arv2_r298_privacy_recovery_remote as frozen
    old = object.__new__(frozen.PrivacyRecovery)
    old._organization_sha256 = m.ORGANIZATION_SHA256
    calls = []
    def fake_rpc(marker, endpoint, payload):
        assert payload == {'projectId': m.PROJECT_ID}
        calls.append((marker, endpoint))
        if endpoint == 'projects/read': return copy.deepcopy(supplied.project)
        if endpoint == frozen.COLLABORATION_ENDPOINT: return copy.deepcopy(supplied.dedicated)
        raise AssertionError('No history, lock, files, compile or launch allowed in reproduction')
    old._rpc = fake_rpc
    with pytest.raises(frozen.RecoveryError, match='^project_mia_pin$'):
        old._owned('synthetic-only')
    assert [endpoint for _, endpoint in calls] == ['projects/read', 'projects/collaboration/read']
    assert verify(supplied)['extra_kind'] == 'r314_observed_a5'


def test_output_is_detached_and_inputs_are_not_mutated(supplied):
    before = copy.deepcopy((supplied.project, supplied.dedicated))
    first = verify(supplied)
    assert before == (supplied.project, supplied.dedicated)
    first['extra_kind'] = 'caller mutation'
    assert verify(supplied)['extra_kind'] == 'r314_observed_a5'
    supplied.project['projects'][0]['collaborators'][1]['name'] = 'changed'
    assert first['owner_row_sha256'] == m.OWNER_ROW_SHA256
    with pytest.raises(m.AccessRefused): verify(supplied)


@pytest.mark.parametrize('error', [ValueError('private data'), m.AccessRefused('private data'),
    m.AccessRefused(), m.AccessRefused('owner', 'private data')])
def test_failure_classification_never_echoes_unknown_details(error):
    assert m.finite_error(error) == {'code': 'unknown'}


@pytest.mark.parametrize('code', sorted(m.FINITE_CODES))
def test_finite_failure_codes(code):
    assert m.finite_error(m.AccessRefused(code)) == {'code': code}


def test_exact_public_contract_pins_and_no_operational_interface():
    assert m.PROJECT_ID == 38364439 and m.PROJECT_NAME == 'ARV2 R298 NEWRULE SIX OFF 2021 OCT2026'
    assert m.OWNER_ROW_SHA256 == '707a30618e122e49fe6fa75364451b5b7c50e1019a68a89ffc0cd3ae3c8e0b78'
    assert m.A5_ROW_SHA256 == 'f9a933141393262edb66e3e8248ed75ebf4518668039e1a27af6734f26f58b9d'
    assert m.ORGANIZATION_SHA256 == 'a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880'
    assert m.A5_CODE_SOURCE_ID == 'Codex ARV2 R298 A5 20261024'
    profile = m.profile_record()
    assert profile['historical_mia_accepted'] is False
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    assert not any(hasattr(m, name) for name in ('main', 'run', 'request', 'claim', 'launch', 'ATTEMPT'))
    assert 'assistant.dispatch_fence' not in sys.modules


@pytest.mark.parametrize('location', ['projects_tuple', 'general_tuple', 'dedicated_tuple',
    'integer_key', 'boolean_key', 'string_subclass', 'integer_subclass', 'float_subclass',
    'dict_subclass', 'list_subclass'])
def test_exact_json_types_are_checked_before_lossy_encoding(supplied, location):
    class String(str): pass
    class Integer(int): pass
    class Float(float): pass
    class Dict(dict): pass
    class List(list): pass
    project = supplied.project['projects'][0]
    if location == 'projects_tuple': supplied.project['projects'] = tuple(supplied.project['projects'])
    elif location == 'general_tuple': project['collaborators'] = tuple(project['collaborators'])
    elif location == 'dedicated_tuple': supplied.dedicated['collaborators'] = tuple(supplied.dedicated['collaborators'])
    elif location == 'integer_key': project[1] = 'private'
    elif location == 'boolean_key': project[True] = 'private'
    elif location == 'string_subclass': project['name'] = String(project['name'])
    elif location == 'integer_subclass': project['projectId'] = Integer(m.PROJECT_ID)
    elif location == 'float_subclass': project['unknown-field'] = Float(1.25)
    elif location == 'dict_subclass': supplied.project['projects'][0] = Dict(project)
    else: project['collaborators'] = List(project['collaborators'])
    with pytest.raises(m.AccessRefused, match='^json_shape$'): verify(supplied)


@pytest.mark.parametrize('kind', ['dict', 'list', 'str', 'int'])
def test_hostile_subclass_hooks_are_not_called_before_refusal(supplied, kind):
    hits = []
    def hostile(*_args, **_kwargs):
        hits.append('called')
        raise AssertionError('private hook should not run')
    class Dict(dict):
        items = values = __iter__ = hostile
    class List(list):
        __iter__ = __len__ = __getitem__ = hostile
    class String(str):
        __str__ = __repr__ = __iter__ = hostile
    class Integer(int):
        __int__ = __str__ = __repr__ = hostile
    supplied.project['projects'][0]['unknown-field'] = {
        'dict': Dict(), 'list': List(), 'str': String('private'), 'int': Integer(1)}[kind]
    with pytest.raises(m.AccessRefused, match='^json_shape$'): verify(supplied)
    assert hits == []


@pytest.mark.parametrize('kind', ['cycle', 'depth', 'nodes', 'infinity'])
def test_recursive_json_shape_is_finite_and_bounded(supplied, monkeypatch, kind):
    if kind == 'cycle':
        value = []
        value.append(value)
    elif kind == 'depth':
        value = []
        for _ in range(m.MAX_JSON_DEPTH + 1): value = [value]
    elif kind == 'nodes':
        monkeypatch.setattr(m, 'MAX_JSON_NODES', 4)
        value = [None] * 5
    else: value = float('inf')
    supplied.project['projects'][0]['unknown-field'] = value
    with pytest.raises(m.AccessRefused, match='^json_shape$'): verify(supplied)


@pytest.mark.parametrize('container', ['list', 'dict'])
def test_preextension_bound_counts_already_pending_nodes(monkeypatch, container):
    monkeypatch.setattr(m, 'MAX_JSON_NODES', 10)
    observed = []
    def observed_float(value):
        observed.append(value)
        return True
    monkeypatch.setattr(m.math, 'isfinite', observed_float)
    branch = [0.5] * 8 if container == 'list' else {str(index): 0.5 for index in range(8)}
    with pytest.raises(m.AccessRefused, match='^json_shape$'):
        m._canonical([branch, branch])
    # Two containers are already pending. Refuse the next eight-value expansion
    # before traversing its scalar values, not only after exceeding the budget.
    assert observed == []
