"""Synthetic representation checks; no real row, credential or operation."""
import copy
import itertools
import sys
from types import SimpleNamespace

import pytest

from scripts import arv2_r298_mia_access_representation as m


@pytest.fixture
def supplied(monkeypatch):
    owner = {'owner': True, 'uid': 123, 'name': 'Synthetic owner',
        'publicId': 'synthetic-owner', 'permission': 'write', 'liveControl': True}
    a5 = {'owner': False, 'uid': None, 'name': m.previous.A5_CODE_SOURCE_ID,
        'publicId': m.previous.A5_CODE_SOURCE_ID, 'permission': 'write',
        'liveControl': True, 'synthetic-extra': {'unreported': 1}}
    mia = {'owner': False, 'uid': None, 'name': 'Mia', 'publicId': 'synthetic-current-mia',
        'permission': 'write', 'liveControl': True, 'email': 'synthetic-not-real',
        'synthetic-extra': {'unreported': 2}}
    for target in (m, m.previous):
        monkeypatch.setattr(target, 'ORGANIZATION_SHA256', m.sha(b'a' * 32))
        monkeypatch.setattr(target, 'OWNER_ROW_SHA256', m.sha(m.canonical(owner)))
        monkeypatch.setattr(target, 'A5_ROW_SHA256', m.sha(m.canonical(a5)))
    monkeypatch.setattr(m, 'MIA_ROW_SHA256', m.sha(m.canonical(mia)))
    monkeypatch.setattr(m, 'MIA_PUBLIC_ID_SHA256', m.sha(m.canonical(mia['publicId'])))
    project = {'projectId': m.PROJECT_ID, 'organizationId': 'a' * 32,
        'name': m.PROJECT_NAME, 'language': 'Py', 'owner': True, 'ownerId': 123,
        'codeRunning': False, 'collaborators': [copy.deepcopy(owner), copy.deepcopy(a5), copy.deepcopy(mia)]}
    return SimpleNamespace(project={'success': True, 'projects': [project]},
        dedicated={'success': True, 'collaborators': [copy.deepcopy(owner)],
            'userPermissions': 'write', 'userLiveControl': True}, owner=owner, a5=a5, mia=mia)


def verify(supplied):
    return m.verify_access(supplied.project, supplied.dedicated)


@pytest.mark.parametrize('extras', [(), ('a5',), ('mia',), ('a5', 'mia')])
def test_closed_optional_full_rows_all_orders(supplied, extras):
    rows = [supplied.owner] + [getattr(supplied, name) for name in extras]
    for ordered in itertools.permutations(rows):
        supplied.project['projects'][0]['collaborators'] = copy.deepcopy(list(ordered))
        result = verify(supplied)
        assert result['matched_current_access_representation'] is True
        assert result['general_count'] == len(rows) and result['dedicated_count'] == 1
        assert result['observed_a5_row_sha256'] == (m.A5_ROW_SHA256 if 'a5' in extras else None)
        assert result['observed_mia_row_sha256'] == (m.MIA_ROW_SHA256 if 'mia' in extras else None)
        assert all(result[key] is False for key in m.FALSE_FLAGS)
        assert b'Synthetic owner' not in m.canonical(result)
        assert b'synthetic-current-mia' not in m.canonical(result)


def test_only_detached_mia_row_extracted_before_unchanged_old_verifier(supplied, monkeypatch):
    original = m.previous.verify_access
    before = copy.deepcopy((supplied.project, supplied.dedicated))
    calls = []
    def checked(project, dedicated):
        calls.append((copy.deepcopy(project), copy.deepcopy(dedicated)))
        assert project['projects'][0]['collaborators'] == [supplied.owner, supplied.a5]
        assert dedicated == supplied.dedicated
        return original(project, dedicated)
    monkeypatch.setattr(m.previous, 'verify_access', checked)
    result = verify(supplied)
    assert len(calls) == 1 and before == (supplied.project, supplied.dedicated)
    assert result['original_project_response_sha256'] == m.sha(m.canonical(supplied.project))
    assert result['original_dedicated_response_sha256'] == m.sha(m.canonical(supplied.dedicated))
    assert result['original_project_response_sha256'] != m.sha(m.canonical(calls[0][0]))


@pytest.mark.parametrize('kind', ['missing_owner', 'duplicate_owner', 'duplicate_a5',
    'duplicate_mia', 'unknown', 'four', 'empty', 'tuple', 'nonrow'])
def test_inventory_unknowns_duplicates_and_bounds_refuse(supplied, kind):
    rows = supplied.project['projects'][0]['collaborators']
    if kind == 'missing_owner': rows.pop(0)
    elif kind == 'duplicate_owner': rows[:] = [supplied.owner, supplied.owner]
    elif kind == 'duplicate_a5': rows[:] = [supplied.owner, supplied.a5, supplied.a5]
    elif kind == 'duplicate_mia': rows[:] = [supplied.owner, supplied.mia, supplied.mia]
    elif kind == 'unknown': rows[2] = {'name': 'Mia', 'uid': None}
    elif kind == 'four': rows.append(copy.deepcopy(supplied.mia))
    elif kind == 'empty': rows.clear()
    elif kind == 'tuple': supplied.project['projects'][0]['collaborators'] = tuple(rows)
    else: rows[2] = None
    with pytest.raises(m.AccessRefused): verify(supplied)


@pytest.mark.parametrize('mutation', ['known_fields_only', 'unknown_changed', 'unknown_added',
    'unknown_removed', 'public_id_changed', 'email_changed'])
def test_visible_field_equality_cannot_forge_complete_mia_pin(supplied, mutation):
    row = supplied.project['projects'][0]['collaborators'][2]
    if mutation == 'unknown_changed': row['synthetic-extra']['unreported'] = 3
    elif mutation == 'unknown_added': row['new-field'] = 'private-not-retained'
    elif mutation == 'public_id_changed': row['publicId'] = 'mia-ai'
    elif mutation == 'email_changed': row['email'] = 'different'
    else: row.pop('synthetic-extra')
    with pytest.raises(m.AccessRefused, match='^general_row_pin$'): verify(supplied)


@pytest.mark.parametrize('key,value', [('owner', True), ('owner', 0), ('uid', True),
    ('uid', 0), ('uid', ''), ('permission', 'read'), ('permission', 1),
    ('liveControl', False), ('liveControl', 1), ('name', 'mia-ai'), ('name', 1),
    ('publicId', None), ('codeSourceId', None), ('email', None), ('email', 1)])
def test_mia_explicit_shape_survives_mistaken_full_row_repin(supplied, monkeypatch, key, value):
    row = supplied.project['projects'][0]['collaborators'][2]
    row[key] = value
    monkeypatch.setattr(m, 'MIA_ROW_SHA256', m.sha(m.canonical(row)))
    with pytest.raises(m.AccessRefused, match='^mia_row_shape$'): verify(supplied)


@pytest.mark.parametrize('key', ['owner', 'uid', 'permission', 'liveControl', 'name', 'publicId', 'email'])
def test_mia_required_fields_cannot_disappear(supplied, monkeypatch, key):
    row = supplied.project['projects'][0]['collaborators'][2]
    row.pop(key)
    monkeypatch.setattr(m, 'MIA_ROW_SHA256', m.sha(m.canonical(row)))
    with pytest.raises(m.AccessRefused, match='^mia_row_shape$'): verify(supplied)


def test_mia_identifier_pin_independent_of_full_row_pin(supplied, monkeypatch):
    row = supplied.project['projects'][0]['collaborators'][2]
    row['publicId'] = 'mia-ai'
    monkeypatch.setattr(m, 'MIA_ROW_SHA256', m.sha(m.canonical(row)))
    with pytest.raises(m.AccessRefused, match='^mia_public_id_pin$'): verify(supplied)


@pytest.mark.parametrize('key,value,code', [('projectId', True, 'project_id'),
    ('organizationId', 'b' * 32, 'organization'), ('name', 'other', 'name'),
    ('language', 'C#', 'language'), ('owner', 1, 'owner'), ('ownerId', True, 'owner_id'),
    ('ownerId', 124, 'dedicated_owner'), ('codeRunning', True, 'idle'),
    ('codeRunning', 0, 'idle'), ('public', True, 'public_contradiction')])
def test_old_project_scope_remains_strict(supplied, key, value, code):
    supplied.project['projects'][0][key] = value
    with pytest.raises(m.AccessRefused, match='^' + code + '$'): verify(supplied)


@pytest.mark.parametrize('field,value', [('userPermissions', 'read'), ('userLiveControl', False),
    ('collaborators', []), ('collaborators', [{'owner': True, 'uid': True}])])
def test_dedicated_response_is_not_filtered_or_relaxed(supplied, field, value):
    supplied.dedicated[field] = value
    with pytest.raises(m.AccessRefused): verify(supplied)


@pytest.mark.parametrize('key,value', [('uid', True), ('uid', 124), ('permission', 'read'),
    ('liveControl', False), ('owner', 1)])
def test_exact_dedicated_owner_fields_survive_new_general_view(supplied, key, value):
    supplied.dedicated['collaborators'][0][key] = value
    with pytest.raises(m.AccessRefused, match='^dedicated_owner$'): verify(supplied)


def test_full_owner_and_a5_pins_remain_required(supplied):
    supplied.project['projects'][0]['collaborators'][1]['synthetic-extra']['unreported'] = 0
    with pytest.raises(m.AccessRefused, match='^general_row_pin$'): verify(supplied)


def test_receipt_detached_redacted_and_not_operational_capability(supplied):
    first = verify(supplied)
    first['observed_mia_row_sha256'] = None
    assert verify(supplied)['observed_mia_row_sha256'] == m.MIA_ROW_SHA256
    supplied.project['projects'][0]['collaborators'][2]['email'] = 'changed'
    with pytest.raises(m.AccessRefused): verify(supplied)
    assert all(first[key] is False for key in m.FALSE_FLAGS)


def test_receipt_hostile_unknown_key_refuses_before_rehash(supplied):
    calls = []
    class Key:
        def __hash__(self):
            calls.append('hash')
            return 1
        def __eq__(self, other):
            calls.append('equal')
            return False
    value = verify(supplied)
    value[Key()] = 'private'
    calls.clear()
    with pytest.raises(m.AccessRefused, match='^receipt_shape$'): m.validate_receipt(value)
    assert calls == []


@pytest.mark.parametrize('key,value', [('uid', True), ('name', 'Mia'),
    ('permission', 'read'), ('codeSourceId', None)])
def test_new_contract_preserves_old_a5_explicit_shape_after_synthetic_repin(
        supplied, monkeypatch, key, value):
    row = supplied.project['projects'][0]['collaborators'][1]
    row[key] = value
    pin = m.sha(m.canonical(row))
    monkeypatch.setattr(m, 'A5_ROW_SHA256', pin)
    monkeypatch.setattr(m.previous, 'A5_ROW_SHA256', pin)
    with pytest.raises(m.AccessRefused, match='^extra_row_shape$'): verify(supplied)


@pytest.mark.parametrize('mutation', ['extra', 'boolean_count', 'count_mismatch', 'mia_pin',
    'authority', 'schema', 'owner_pin', 'nested_value'])
def test_closed_receipt_cannot_gain_authority_or_ignore_fields(supplied, mutation):
    value = verify(supplied)
    if mutation == 'extra': value['raw'] = 'private'
    elif mutation == 'boolean_count': value['general_count'] = True
    elif mutation == 'count_mismatch': value['general_count'] = 2
    elif mutation == 'mia_pin': value['observed_mia_row_sha256'] = '0' * 64
    elif mutation == 'authority': value['operational_retry_authority'] = True
    elif mutation == 'schema': value['schema'] = m.previous.SCHEMA
    elif mutation == 'owner_pin': value['owner_row_sha256'] = '0' * 64
    else: value['observed_mia_row_sha256'] = {'private': 'ignored'}
    with pytest.raises(m.AccessRefused, match='^receipt_shape$'): m.validate_receipt(value)


@pytest.mark.parametrize('field', ['original_project_response_sha256',
    'original_dedicated_response_sha256'])
@pytest.mark.parametrize('value', [None, True, 0, 'A' * 64, '0' * 63, 'g' * 64])
def test_original_snapshot_pins_are_strict_lowercase_hashes(supplied, field, value):
    result = verify(supplied)
    result[field] = value
    with pytest.raises(m.AccessRefused, match='^receipt_shape$'): m.validate_receipt(result)


@pytest.mark.parametrize('kind', ['dict', 'list', 'str', 'int'])
def test_hostile_subclasses_refuse_without_hooks(supplied, kind):
    hits = []
    def hostile(*args, **kwargs):
        hits.append(True)
        raise AssertionError('private hook must not execute')
    class Dict(dict): items = values = __iter__ = hostile
    class List(list): __iter__ = __len__ = __getitem__ = hostile
    class String(str): __str__ = __repr__ = __iter__ = hostile
    class Integer(int): __int__ = __str__ = __repr__ = hostile
    supplied.project['projects'][0]['unknown'] = {
        'dict': Dict(), 'list': List(), 'str': String('private'), 'int': Integer(1)}[kind]
    with pytest.raises(m.AccessRefused, match='^json_shape$'): verify(supplied)
    assert hits == []


@pytest.mark.parametrize('packet,code', [(None, 'response_shape'), ({}, 'response_refused'),
    ({'success': True, 'errors': ['private']}, 'response_refused'),
    ({'success': True, 'unknown': float('nan')}, 'json_shape'),
    ({'success': True, 'unknown': 'x' * 1048576}, 'response_bound')])
def test_unchanged_snapshot_bounds_and_response_failure(supplied, packet, code):
    supplied.project = packet
    with pytest.raises(m.AccessRefused, match='^' + code + '$'): verify(supplied)


@pytest.mark.parametrize('code', sorted(m.FINITE_CODES))
def test_old_and_new_failure_predicates_are_closed(code):
    assert m.finite_error(m.AccessRefused(code)) == {'code': code}


def test_unknown_or_foreign_errors_never_expose_details():
    class Foreign(m.AccessRefused): pass
    for error in (ValueError('private'), Foreign('idle'), m.AccessRefused('private'),
            m.AccessRefused(), m.AccessRefused('idle', 'private')):
        assert m.finite_error(error) == {'code': 'unknown'}


def test_fixed_public_contract_without_real_rows_or_operational_entry():
    assert m.MIA_ROW_SHA256 == '710488e487086c93979cd034cf19a073d870e63cf92bdc7904cf2c97f5b0fcf2'
    assert m.MIA_PUBLIC_ID_SHA256 == '4802c36d758c1b43bbbd50cb3428192a80dc3ea0fee517416285436bdf6e6f14'
    assert m.PREVIOUS_SOURCE_SHA256 == '57333e2d6932f3b75bb42bc59214ebda2ce9afdf65b9054b7edc7ee5cbd37d93'
    assert m.AccessRefused is m.previous.AccessRefused
    profile = m.profile_record()
    assert profile['max_general_collaborators'] == 3
    assert profile['observation_report_bytes'] == 5271
    assert profile['observation_documentary_only'] is True
    assert profile['automatic_pin_refresh'] is False
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    assert not any(hasattr(m, key) for key in ('main', 'run', 'claim', 'request', 'launch', 'ATTEMPT'))
    assert 'assistant.dispatch_fence' not in sys.modules
