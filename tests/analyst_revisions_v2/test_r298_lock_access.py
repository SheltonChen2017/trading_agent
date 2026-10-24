"""Synthetic post-A5 lock/access diagnostics; never live client/account tests.

The invoking runner must deny remote network, production artifacts and Keychain.
All filesystem fixtures stay beneath the designated root's .pytest_cache.
"""
from contextlib import nullcontext
import os
from types import SimpleNamespace

import pytest

from scripts import observe_arv2_r298_lock_access as module


@pytest.fixture
def scope(monkeypatch, tmp_path):
    assert tmp_path.is_relative_to(module.ROOT / '.pytest_cache')
    monkeypatch.setattr(module, 'CONTROL', tmp_path / 'records' / 'once')
    monkeypatch.setattr(module, 'ORGANIZATION_SHA256', module.sha(b'a' * 32))
    return tmp_path


def owner():
    return {'owner': True, 'uid': 12345, 'publicId': 'synthetic-owner',
        'name': 'Private owner name', 'email': 'private@example.invalid',
        'permission': 'write', 'liveControl': False}


def mia():
    return {'owner': False, 'uid': 54321, 'publicId': 'mia-ai', 'name': 'Mia',
        'permission': 'read', 'liveControl': False}


def project():
    return {'success': True, 'projects': [{'projectId': module.PROJECT,
        'organizationId': 'a' * 32, 'name': module.PROJECT_NAME, 'language': 'Py',
        'owner': True, 'ownerId': 12345, 'public': False, 'codeRunning': False,
        'collaborators': [owner(), mia()]}]}


def dedicated():
    return {'success': True, 'projectId': module.PROJECT, 'collaborators': [owner()],
        'userPermissions': 'write', 'userLiveControl': False}


def response(endpoint, _payload):
    return project() if endpoint == module.ENDPOINTS[0] else dedicated()


def initial():
    return {**module.new_state(), 'stage': 'credentials'}


def completed():
    return module.observe(response, lambda *_: None, initial(), float('inf'))


def test_per_row_finite_projection_keeps_relationships_not_values(scope):
    owner_id, observed = module.project_observation(project())
    rows = observed['collaborators']['records']
    assert owner_id == 12345
    assert observed['code_running']['value'] is False
    assert rows[0]['uid']['equals_project_owner'] is True
    assert rows[1]['uid']['equals_project_owner'] is False
    assert rows[0]['owner']['value'] is True and rows[1]['owner']['value'] is False
    assert rows[0]['public_id']['exact_mia_sentinel'] is False
    assert rows[1]['public_id']['exact_mia_sentinel'] is True
    assert rows[0]['name_exact_mia'] is False and rows[1]['name_exact_mia'] is True
    assert rows[0]['permission'] == 'write' and rows[1]['permission'] == 'read'
    assert rows[0]['row_sha256'] == module.sha(module.canonical(owner()))
    assert rows[1]['row_sha256'] == module.sha(module.canonical(mia()))
    raw = module.canonical(observed)
    assert all(secret not in raw for secret in (b'12345', b'54321', b'mia-ai',
        b'Private owner name', b'private@example.invalid', b'synthetic-owner'))
    module._validate_project(observed)


@pytest.mark.parametrize('row,label', [(None, 'null'), (False, 'boolean'),
    (4, 'number'), (4.5, 'number'), ('private-row', 'string'), ([], 'array')])
def test_nonobject_rows_are_hashed_without_invented_fields(scope, row, label):
    value = module.record_projection(row, 12345)
    assert value['json_type'] == label and value['row_sha256'] == module.sha(module.canonical(row))
    assert all(value[key] is None for key in ('owner', 'uid', 'public_id', 'name_exact_mia', 'live_control'))
    assert value['permission'] == 'unknown' and b'private-row' not in module.canonical(value)
    module._validate_records(module.collaborators_projection({'collaborators': [row]}, 12345))


@pytest.mark.parametrize('key', ['owner', 'liveControl'])
@pytest.mark.parametrize('value,label', [(True, 'boolean'), (False, 'boolean'),
    (None, 'null'), (1, 'number'), (0.0, 'number'), ('private-value', 'string'),
    ([], 'array'), ({}, 'object')])
def test_boolean_fields_are_exact_not_truthy(scope, key, value, label):
    field = module.record_projection({key: value}, 12345)[
        'owner' if key == 'owner' else 'live_control']
    assert field['json_type'] == label and field['valid_boolean'] is (type(value) is bool)
    assert field['value'] is (value if type(value) is bool else None)
    assert b'private-value' not in module.canonical(field)


@pytest.mark.parametrize('value,valid,equal', [(12345, True, True), (54321, True, False),
    (True, False, None), (False, False, None), (12345.0, False, None),
    (0, False, None), (-1, False, None), (None, False, None),
    ('12345', False, None), ('mia-ai', False, None), ([], False, None), ({}, False, None)])
def test_uid_equality_uses_exact_positive_integer(scope, value, valid, equal):
    field = module.record_projection({'uid': value}, 12345)['uid']
    assert field['valid_positive_integer'] is valid and field['equals_project_owner'] is equal
    assert b'12345' not in module.canonical(field)


@pytest.mark.parametrize('value,exact,bounded', [('mia-ai', True, True), ('MIA-AI', False, True),
    ('mia-ai ', False, False), ('', False, False), ('a' * 256, False, True),
    ('a' * 257, False, False), ('private\nvalue', False, False),
    ('é', False, False), (None, False, False), (True, False, False), (7, False, False)])
def test_public_sentinel_and_shape_are_not_identity_approval(scope, value, exact, bounded):
    result = module.record_projection({'publicId': value}, 12345)
    assert result['public_id']['exact_mia_sentinel'] is exact
    assert result['public_id']['bounded_nonempty_ascii'] is bounded
    assert b'mia-ai' not in module.canonical(result)


@pytest.mark.parametrize('value,expected', [('Mia', True), ('mia', False), ('Mia ', False),
    ('Private name', False), (None, False), (True, False), (['Mia'], False)])
def test_name_is_only_exact_mia_boolean(scope, value, expected):
    result = module.record_projection({'name': value}, 12345)
    assert result['name_exact_mia'] is expected
    assert b'Private name' not in module.canonical(result)


@pytest.mark.parametrize('value,expected', [('read', 'read'), ('write', 'write'),
    ('READ', 'unknown'), ('admin', 'unknown'), ('write ', 'unknown'),
    (None, 'unknown'), (True, 'unknown'), (7, 'unknown'), ([], 'unknown')])
def test_permissions_are_finite(scope, value, expected):
    assert module.permission(value) == expected
    assert module.record_projection({'permission': value}, 12345)['permission'] == expected


def test_absent_and_null_are_distinct(scope):
    empty = module.record_projection({}, 12345)
    null = module.record_projection({'owner': None, 'uid': None, 'publicId': None, 'liveControl': None}, 12345)
    for key in ('owner', 'uid', 'public_id', 'live_control'):
        assert empty[key]['present'] is False and empty[key]['json_type'] == 'absent'
        assert null[key]['present'] is True and null[key]['json_type'] == 'null'
    assert module.collaborators_projection({}, 12345) == {
        'present': False, 'json_type': 'absent', 'count': None, 'records': None}


@pytest.mark.parametrize('value,label', [(None, 'null'), (False, 'boolean'), (1, 'number'),
    (1.0, 'number'), ('private-list', 'string'), ({}, 'object')])
def test_nonlist_field_is_not_guessed_empty(scope, value, label):
    field = module.collaborators_projection({'collaborators': value}, 12345)
    assert field == {'present': True, 'json_type': label, 'count': None, 'records': None}
    module._validate_records(field)


@pytest.mark.parametrize('count', [0, 1, 8])
def test_finite_collaborator_bounds(scope, count):
    field = module.collaborators_projection({'collaborators': [{}] * count}, 12345)
    assert field['count'] == count and len(field['records']) == count
    module._validate_records(field)


def test_excessive_collaborator_count_refuses(scope):
    with pytest.raises(module.Refused, match='bound'):
        module.collaborators_projection({'collaborators': [{}] * 9}, 12345)


@pytest.mark.parametrize('rows', [None, {}, [], [None], [{}, {}]])
def test_project_scope_exact_shape(scope, rows):
    with pytest.raises(module.Refused, match='project_shape'):
        module.project_observation({'projects': rows})


@pytest.mark.parametrize('key,value,reason', [('projectId', True, 'project_id'),
    ('projectId', 1, 'project_id'), ('organizationId', 'b' * 32, 'organization'),
    ('organizationId', None, 'organization'), ('name', 'other', 'name'),
    ('language', 'C#', 'language'), ('owner', 1, 'owner'), ('owner', False, 'owner'),
    ('ownerId', True, 'owner_id'), ('ownerId', 12345.0, 'owner_id'),
    ('ownerId', 0, 'owner_id'), ('ownerId', None, 'owner_id'), ('ownerId', 2 ** 63, 'owner_id')])
def test_project_binding_refuses_before_observation(scope, key, value, reason):
    packet = project()
    packet['projects'][0][key] = value
    with pytest.raises(module.Refused, match=reason): module.project_observation(packet)


@pytest.mark.parametrize('value', [True, 1, module.PROJECT + 1, str(module.PROJECT), None])
def test_dedicated_optional_project_id_must_match_exactly(scope, value):
    packet = dedicated()
    packet['projectId'] = value
    with pytest.raises(module.Refused, match='project_id'):
        module.dedicated_observation(packet, 12345)


def test_dedicated_missing_project_id_and_missing_fields_retained(scope):
    result = module.dedicated_observation({'success': True}, 12345)
    assert result['collaborators']['json_type'] == 'absent'
    assert result['user_permissions'] == 'unknown'
    assert result['user_live_control']['json_type'] == 'absent'
    module._validate_dedicated(result)


def test_multiset_equality_ignores_order_but_not_multiplicity(scope):
    _, first = module.project_observation(project())
    packet = dedicated()
    packet['collaborators'] = [mia(), owner()]
    second = module.dedicated_observation(packet, 12345)
    assert module.comparison(first, second)['row_hash_multiset_equal'] is True
    packet['collaborators'] = [owner(), owner()]
    second = module.dedicated_observation(packet, 12345)
    assert module.comparison(first, second)['row_hash_multiset_equal'] is False
    packet.pop('collaborators')
    assert module.comparison(first, module.dedicated_observation(packet, 12345)) == {
        'project_count': 2, 'dedicated_count': None, 'row_hash_multiset_equal': None,
        'project_true_owner_count': 1, 'dedicated_true_owner_count': None,
        'sole_owner_row_hash_equal': None}


def test_row_hash_tracks_unexposed_difference_without_disclosing_it(scope):
    first = owner()
    second = {**first, 'email': 'another-private@example.invalid'}
    left, right = module.record_projection(first, 12345), module.record_projection(second, 12345)
    assert left.pop('row_sha256') != right.pop('row_sha256')
    assert left == right and b'another-private' not in module.canonical(right)


def test_two_endpoint_order_and_intents_before_contact(scope):
    events, state = [], initial()
    def request(endpoint, payload):
        stage = 'project' if endpoint == module.ENDPOINTS[0] else 'collaborators'
        assert events[-1][0] == stage + '-intent.json'
        assert payload == {'projectId': module.PROJECT}
        events.append((endpoint, payload))
        return response(endpoint, payload)
    result = module.observe(request, lambda *item: events.append(item), state, float('inf'))
    assert [item[0] for item in events] == ['project-intent.json', module.ENDPOINTS[0],
        'project-observation.json', 'collaborators-intent.json', module.ENDPOINTS[1],
        'collaborators-observation.json']
    assert result['application_dispatch_count'] == 2 and result['provider_request_count'] is None
    assert result['comparison'] == {'project_count': 2, 'dedicated_count': 1, 'row_hash_multiset_equal': False,
        'project_true_owner_count': 1, 'dedicated_true_owner_count': 1, 'sole_owner_row_hash_equal': True}
    module._validate_result(result, True)
    with pytest.raises(module.Refused, match='dispatch'):
        module.observe(lambda *_: pytest.fail('repeat'), lambda *_: None, state, float('inf'))


@pytest.mark.parametrize('stage,expected', [('project', 0), ('collaborators', 1)])
def test_failed_intent_prevents_corresponding_dispatch(scope, stage, expected):
    calls, state = [], initial()
    def request(endpoint, payload):
        calls.append(endpoint)
        return response(endpoint, payload)
    def write(name, _value):
        if name == stage + '-intent.json': raise module.Refused('control')
    with pytest.raises(module.Refused, match='control'):
        module.observe(request, write, state, float('inf'))
    assert len(calls) == state['application_dispatch_count'] == expected
    module._validate_result(module.finite_failure(module.Refused('control'), state), False)


@pytest.mark.parametrize('stage', ['project', 'collaborators'])
@pytest.mark.parametrize('packet,reason', [(None, 'response_shape'), ({'success': 1}, 'response_refused'),
    ({'success': False}, 'response_refused'), ({'secret': 'x' * 1048576}, 'bound'),
    ({'secret': float('nan')}, 'json')])
def test_invalid_response_has_no_retry(scope, stage, packet, reason):
    calls, state = [], initial()
    target = module.ENDPOINTS[0 if stage == 'project' else 1]
    def request(endpoint, payload):
        calls.append(endpoint)
        return packet if endpoint == target else response(endpoint, payload)
    with pytest.raises(module.Refused, match=reason):
        module.observe(request, lambda *_: None, state, float('inf'))
    assert len(calls) == state['application_dispatch_count'] == (1 if stage == 'project' else 2)
    module._validate_result(module.finite_failure(module.Refused(reason), state), False)


def test_transport_exception_retains_first_observation_not_exception(scope):
    state = initial()
    def request(endpoint, payload):
        if endpoint == module.ENDPOINTS[1]: raise RuntimeError('private body / token')
        return response(endpoint, payload)
    with pytest.raises(RuntimeError): module.observe(request, lambda *_: None, state, float('inf'))
    failure = module.finite_failure(RuntimeError('private body / token'), state)
    assert failure['project_observation'] is not None and failure['dedicated_observation'] is None
    assert failure['last_event'] == 'intent' and failure['application_dispatch_count'] == 2
    assert failure['failure_code'] == 'unknown_exception'
    assert b'private body' not in module.canonical(failure)
    module._validate_result(failure, False)


@pytest.fixture
def client_fixture(monkeypatch):
    from scripts import arv2_newrule_execution_environment as environment
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
    events = []
    api = object.__new__(old.QuantConnectClient)
    api._base_url, api._transport, api._timeout = old.API_BASE, old.coverage._bounded_transport, 30
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: events.append('environment'))
    def create():
        assert events == ['environment']
        events.append('construct')
        return api
    monkeypatch.setattr(old, '_client', create)
    def request(self, endpoint, payload):
        assert self is api and events[-1] == 'environment'
        events.append((endpoint, payload))
        return {'success': True}
    monkeypatch.setattr(old.QuantConnectClient, 'request', request)
    return old, environment, api, events


def test_readonly_client_exact_order_and_environment_guard(client_fixture):
    _, _, _, events = client_fixture
    client = module.ReadOnlyClient()
    assert events == ['environment', 'construct', 'environment']
    assert repr(client) == '<ReadOnlyR298LockAccessClient>'
    for endpoint in module.ENDPOINTS:
        assert client.request(endpoint, {'projectId': module.PROJECT}) == {'success': True}
    with pytest.raises(module.Refused, match='dispatch'):
        client.request(module.ENDPOINTS[1], {'projectId': module.PROJECT})
    assert sum(type(event) is tuple for event in events) == 2


@pytest.mark.parametrize('endpoint,payload', [('files/read', {'projectId': module.PROJECT}),
    ('projects/collaboration/delete', {'projectId': module.PROJECT}),
    ('projects/collaboration/read', {'projectId': module.PROJECT}),
    ('projects/read', {'projectId': True}), ('projects/read', {'projectId': module.PROJECT + 1}),
    ('projects/read', {'projectId': module.PROJECT, 'extra': 1}), ('projects/read', {}),
    ('projects/read', []), (None, {'projectId': module.PROJECT})])
def test_readonly_client_allowlist_before_dispatch(client_fixture, endpoint, payload):
    _, _, _, events = client_fixture
    client = module.ReadOnlyClient()
    with pytest.raises(module.Refused, match='dispatch'): client.request(endpoint, payload)
    assert not any(type(event) is tuple for event in events)


@pytest.mark.parametrize('field,value', [('_base_url', 'https://example.invalid'),
    ('_transport', object()), ('_timeout', 31)])
def test_client_transport_binding_rechecked_each_request(client_fixture, field, value):
    _, _, api, events = client_fixture
    client = module.ReadOnlyClient()
    setattr(api, field, value)
    with pytest.raises(module.Refused, match='client'):
        client.request(module.ENDPOINTS[0], {'projectId': module.PROJECT})
    assert not any(type(event) is tuple for event in events)


def test_client_exact_type_refuses_subclass(client_fixture, monkeypatch):
    old, _, api, _ = client_fixture
    class Derived(old.QuantConnectClient): pass
    api.__class__ = Derived
    with pytest.raises(module.Refused, match='client'): module.ReadOnlyClient()


def test_environment_refusal_before_client_construction(client_fixture, monkeypatch):
    _, environment, _, events = client_fixture
    def refuse(): raise RuntimeError('synthetic environment refusal')
    monkeypatch.setattr(environment, 'require_safe_environment', refuse)
    with pytest.raises(RuntimeError): module.ReadOnlyClient()
    assert events == []


def test_ambiguous_transport_consumes_dispatch(client_fixture, monkeypatch):
    old, _, _, events = client_fixture
    client = module.ReadOnlyClient()
    def refuse(*_):
        events.append('ambiguous')
        raise RuntimeError('synthetic transport refusal')
    monkeypatch.setattr(old.QuantConnectClient, 'request', refuse)
    with pytest.raises(RuntimeError): client.request(module.ENDPOINTS[0], {'projectId': module.PROJECT})
    with pytest.raises(module.Refused, match='dispatch'):
        client.request(module.ENDPOINTS[0], {'projectId': module.PROJECT})
    assert events.count('ambiguous') == 1


@pytest.fixture
def fake_run(scope, monkeypatch):
    from scripts import arv2_newrule_execution_environment as environment
    calls = []
    monkeypatch.setattr(module, '_preflight', lambda *_: None)
    monkeypatch.setattr(module, 'alarm', lambda *_: nullcontext())
    monkeypatch.setattr(environment, '_bootstrap_cli_logging', lambda: None)
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: None)
    def client():
        assert (module.CONTROL / 'claim.json').is_file()
        calls.append('client')
        def request(endpoint, payload):
            calls.append(endpoint)
            return response(endpoint, payload)
        return SimpleNamespace(request=request)
    monkeypatch.setattr(module, 'ReadOnlyClient', client)
    return SimpleNamespace(expected_head='a' * 40, caller_sha256='b' * 64), calls


def read_output(capsys, args, exit_code):
    captured = capsys.readouterr()
    assert captured.err == ''
    return module.validate_output(captured.out.encode('ascii'), exit_code, args)


def test_success_is_observation_only_and_report_pin_is_exact(fake_run, capsys):
    args, calls = fake_run
    assert module.run(args) == 0
    value = read_output(capsys, args, 0)
    assert calls == ['client', *module.ENDPOINTS]
    assert all(value[key] is False for key in module.FALSE_FLAGS)
    raw = (module.CONTROL / 'report.json').read_bytes()
    assert value['report'] == {'sha256': module.sha(raw), 'byte_count': len(raw)}
    assert set(path.name for path in module.CONTROL.iterdir()) == {'claim.json', 'project-intent.json',
        'project-observation.json', 'collaborators-intent.json', 'collaborators-observation.json', 'report.json'}
    assert b'Private owner name' not in raw and b'private@example.invalid' not in raw


def test_duplicate_claim_never_recontacts(fake_run, capsys):
    args, calls = fake_run
    assert module.run(args) == 0
    capsys.readouterr()
    assert module.run(args) == 2
    value = read_output(capsys, args, 2)
    assert value['result']['failure_code'] == 'claim' and value['report'] is None
    assert calls == ['client', *module.ENDPOINTS]


@pytest.mark.parametrize('stage', ['preflight', 'credentials', 'project', 'collaborators', 'postflight', 'report'])
def test_finite_failure_retains_stage_without_raw_error(fake_run, capsys, monkeypatch, stage):
    args, _ = fake_run
    def fail(*_): raise RuntimeError('never retain secret')
    if stage == 'preflight': monkeypatch.setattr(module, '_preflight', fail)
    elif stage == 'credentials': monkeypatch.setattr(module, 'ReadOnlyClient', fail)
    elif stage in ('project', 'collaborators'):
        def request(endpoint, payload):
            if endpoint == module.ENDPOINTS[0 if stage == 'project' else 1]: fail()
            return response(endpoint, payload)
        monkeypatch.setattr(module, 'ReadOnlyClient', lambda: SimpleNamespace(request=request))
    elif stage == 'postflight':
        seen = []
        def preflight(*_):
            seen.append(1)
            if len(seen) == 2: fail()
        monkeypatch.setattr(module, '_preflight', preflight)
    else:
        original = module.Store.write
        def write(self, name, value):
            pin = original(self, name, value)
            if name == 'report.json': fail()
            return pin
        monkeypatch.setattr(module.Store, 'write', write)
    assert module.run(args) == 2
    value = read_output(capsys, args, 2)
    assert value['result']['stage'] == stage and value['result']['failure_code'] == 'unknown_exception'
    assert b'never retain secret' not in module.canonical(value)
    assert (value['report'] is None) is (stage == 'preflight')
    if stage in ('postflight', 'report'):
        assert value['result']['dedicated_observation'] is not None
        assert value['result']['comparison']['row_hash_multiset_equal'] is False
    with pytest.raises(module.Refused): module.validate_output(module.canonical(value), 0, args)


def test_failure_publication_failure_retains_original_finite_context(fake_run, capsys, monkeypatch):
    args, _ = fake_run
    def request(endpoint, payload):
        if endpoint == module.ENDPOINTS[1]: raise module.Refused('response_refused')
        return response(endpoint, payload)
    monkeypatch.setattr(module, 'ReadOnlyClient', lambda: SimpleNamespace(request=request))
    original = module.Store.write
    def write(self, name, value):
        if name == 'failure.json': raise OSError('synthetic storage refusal')
        return original(self, name, value)
    monkeypatch.setattr(module.Store, 'write', write)
    assert module.run(args) == 2
    value = read_output(capsys, args, 2)
    assert value['report'] is None and value['result']['failure_code'] == 'response_refused'
    assert value['result']['application_dispatch_count'] == 2
    assert value['result']['project_observation'] is not None


@pytest.mark.parametrize('actual_exit', [None, True, False, '0', 1, -9])
def test_external_exit_requires_observed_exact_integer(fake_run, capsys, actual_exit):
    args, _ = fake_run
    assert module.run(args) == 0
    value = read_output(capsys, args, 0)
    with pytest.raises(module.Refused): module.validate_output(module.canonical(value), actual_exit, args)


@pytest.mark.parametrize('failed', [False, True])
@pytest.mark.parametrize('changed', ['hash', 'length', 'missing', 'head', 'self', 'profile', 'project', 'flag'])
def test_external_binding_and_report_pin_are_load_bearing(fake_run, capsys, monkeypatch, failed, changed):
    args, _ = fake_run
    if failed:
        def refuse(): raise module.Refused('owner')
        monkeypatch.setattr(module, 'ReadOnlyClient', refuse)
    code = 2 if failed else 0
    assert module.run(args) == code
    value = read_output(capsys, args, code)
    if changed == 'hash': value['report']['sha256'] = 'c' * 64
    elif changed == 'length': value['report']['byte_count'] += 1
    elif changed == 'missing': value.pop('report')
    elif changed == 'head': value['expected_head'] = 'c' * 40
    elif changed == 'self': value['caller_sha256'] = 'c' * 64
    elif changed == 'profile': value['profile_sha256'] = 'c' * 64
    elif changed == 'project': value['project_id'] = True
    else: value['edit_lock_proven'] = True
    with pytest.raises(module.Refused): module.validate_output(module.canonical(value), code, args)


@pytest.mark.parametrize('suffix', [b'\n', b' ', b'garbage'])
def test_outer_canonical_framing_is_exact(fake_run, capsys, suffix):
    args, _ = fake_run
    assert module.run(args) == 0
    value = read_output(capsys, args, 0)
    with pytest.raises(module.Refused): module.validate_output(module.canonical(value) + suffix, 0, args)


@pytest.mark.parametrize('mutation', ['row_extra', 'row_hash', 'row_type', 'count_bool', 'count_large',
    'count_mismatch', 'absent_array', 'owner_value', 'owner_presence', 'uid_valid', 'uid_equality',
    'uid_number', 'public_exact', 'public_bounded', 'name_type', 'permission', 'live_value', 'nonobject'])
def test_row_validator_rejects_incoherent_finite_evidence(scope, mutation):
    field = module.collaborators_projection({'collaborators': [owner()]}, 12345)
    row = field['records'][0]
    if mutation == 'row_extra': row['email'] = 'secret'
    elif mutation == 'row_hash': row['row_sha256'] = 'bad'
    elif mutation == 'row_type': row['json_type'] = 'absent'
    elif mutation == 'count_bool': field['count'] = True
    elif mutation == 'count_large': field['count'] = 9
    elif mutation == 'count_mismatch': field['count'] = 0
    elif mutation == 'absent_array': field['present'] = False
    elif mutation == 'owner_value': row['owner']['value'] = 1
    elif mutation == 'owner_presence': row['owner']['present'] = False
    elif mutation == 'uid_valid': row['uid']['valid_positive_integer'] = 1
    elif mutation == 'uid_equality': row['uid']['equals_project_owner'] = None
    elif mutation == 'uid_number': row['uid']['json_type'] = 'string'
    elif mutation == 'public_exact': row['public_id']['exact_mia_sentinel'] = 1
    elif mutation == 'public_bounded': row['public_id']['json_type'] = 'null'
    elif mutation == 'name_type': row['name_exact_mia'] = 'Mia'
    elif mutation == 'permission': row['permission'] = 'admin'
    elif mutation == 'live_value': row['live_control']['value'] = 0
    else: row['json_type'] = 'null'
    with pytest.raises(module.Refused): module._validate_records(field)


@pytest.mark.parametrize('mutation', ['count', 'stage', 'event', 'endpoint', 'provider', 'project',
    'dedicated', 'comparison', 'comparison_bool', 'extra'])
def test_success_validator_checks_result_not_just_pin(scope, mutation):
    value = completed()
    if mutation == 'count': value['application_dispatch_count'] = True
    elif mutation == 'stage': value['stage'] = 'project'
    elif mutation == 'event': value['last_event'] = 'intent'
    elif mutation == 'endpoint': value['last_endpoint'] = 'files/create'
    elif mutation == 'provider': value['provider_request_count'] = 0
    elif mutation == 'project': value['project_observation'] = None
    elif mutation == 'dedicated': value['dedicated_observation'] = None
    elif mutation == 'comparison': value['comparison']['row_hash_multiset_equal'] = True
    elif mutation == 'comparison_bool': value['comparison']['dedicated_count'] = True
    else: value['private'] = 'secret'
    with pytest.raises(module.Refused): module._validate_result(value, True)


def test_same_row_hash_cannot_have_conflicting_projection(scope):
    packet = dedicated()
    packet['collaborators'] = [owner(), mia()]
    value = module.observe(lambda endpoint, _payload: project() if endpoint == module.ENDPOINTS[0]
        else packet, lambda *_: None, initial(), float('inf'))
    assert value['comparison']['row_hash_multiset_equal'] is True
    value['dedicated_observation']['collaborators']['records'][0]['owner']['value'] = False
    # The unchanged full-row hash still claims identical input, while this
    # finite owner projection now contradicts its matching project-view row.
    assert module.comparison(value['project_observation'], value['dedicated_observation'])[
        'row_hash_multiset_equal'] is True
    with pytest.raises(module.Refused): module._validate_result(value, True)


def test_intralist_repeated_row_hash_cannot_have_conflicting_projection(scope):
    first, second = project(), dedicated()
    first['projects'][0]['collaborators'] = [owner(), owner()]
    second['collaborators'] = [owner(), owner()]
    value = module.observe(lambda endpoint, _payload: first if endpoint == module.ENDPOINTS[0]
        else second, lambda *_: None, initial(), float('inf'))
    rows = value['project_observation']['collaborators']['records']
    assert rows[0]['row_sha256'] == rows[1]['row_sha256']
    rows[1]['live_control']['value'] = True
    with pytest.raises(module.Refused): module._validate_result(value, True)


@pytest.mark.parametrize('mutation', ['failure_code', 'stage', 'endpoint', 'count', 'event',
    'project', 'dedicated', 'provider', 'consumption'])
def test_preclaim_failure_validator_coherence(scope, mutation):
    result = module.finite_failure(module.Refused('source'), module.new_state())
    if mutation == 'failure_code': result['failure_code'] = 'raw secret'
    elif mutation == 'stage': result['stage'] = 'launch'
    elif mutation == 'endpoint': result['last_endpoint'] = module.ENDPOINTS[0]
    elif mutation == 'count': result['application_dispatch_count'] = 1
    elif mutation == 'event': result['last_event'] = 'intent'
    elif mutation == 'project': result['project_observation'] = module.project_observation(project())[1]
    elif mutation == 'dedicated': result['dedicated_observation'] = module.dedicated_observation(dedicated(), 12345)
    elif mutation == 'provider': result['provider_request_count'] = 0
    else: result['attempt_consumption'] = 'safe_to_retry'
    with pytest.raises(module.Refused): module._validate_result(result, False)


@pytest.mark.parametrize('mutation', ['bytes', 'mode', 'replace', 'directory', 'foreign'])
def test_store_detects_held_named_evidence_changes(scope, mutation):
    with module.Store() as store:
        store.write('claim.json', {'synthetic': True})
        target = module.CONTROL / 'claim.json'
        if mutation == 'bytes': target.write_bytes(b'bad')
        elif mutation == 'mode': target.chmod(0o644)
        elif mutation == 'replace': target.rename(module.CONTROL / 'moved.json'); target.write_bytes(b'bad')
        elif mutation == 'directory': module.CONTROL.rename(module.CONTROL.with_name('moved')); module.CONTROL.mkdir(mode=0o700)
        else: (module.CONTROL / 'foreign').write_bytes(b'bad')
        with pytest.raises(module.Refused, match='control_changed'): store.verify()


def test_store_parent_symlink_refuses(scope):
    elsewhere = scope / 'elsewhere'
    elsewhere.mkdir()
    module.CONTROL.parent.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(OSError): module.Store()
    assert list(elsewhere.iterdir()) == []


@pytest.mark.parametrize('name', ['../bad.json', 'bad.txt', '', 'UPPER.json'])
def test_store_name_allowlist(scope, name):
    with module.Store() as store:
        with pytest.raises(module.Refused): store.write(name, {})


def test_store_exact_once_file_and_count_bound(scope):
    with module.Store() as store:
        store.write('claim.json', {})
        with pytest.raises(module.Refused): store.write('claim.json', {})
        for name in ('a', 'b', 'c', 'd', 'e', 'f', 'g'): store.write(name + '.json', {})
        with pytest.raises(module.Refused): store.write('h.json', {})


def test_preflight_refuses_pytest_before_claim(scope):
    with pytest.raises(module.Refused, match='context'):
        module._preflight(SimpleNamespace(expected_head='a' * 40, caller_sha256='b' * 64), float('inf'))
    assert not module.CONTROL.exists()


@pytest.fixture
def preflight_fixture(monkeypatch):
    from scripts import arv2_newrule_execution_environment as environment
    raw = b'synthetic public source'
    args = SimpleNamespace(expected_head='a' * 40, caller_sha256=module.sha(raw))
    monkeypatch.setattr(module, 'sys', SimpleNamespace(modules={}, platform='darwin',
        version_info=(3, 13), executable=str(module.PYTHON)))
    monkeypatch.setattr(module, 'os', SimpleNamespace(**{**vars(os), 'environ': {}}))
    monkeypatch.setattr(environment, '_require_environment', lambda: None)
    def digest(path):
        return args.caller_sha256 if path == module.SOURCE else module.SOURCE_PINS[path.relative_to(module.ROOT).as_posix()]
    monkeypatch.setattr(module, '_source_digest', digest)
    def git(command, deadline, limit=65536):
        if command == ['rev-parse', '--show-toplevel']: return str(module.ROOT).encode()
        if command == ['branch', '--show-current']: return module.BRANCH.encode()
        if command == ['rev-parse', 'HEAD']: return args.expected_head.encode()
        if command == ['status', '--porcelain']: return b''
        if command[:2] == ['cat-file', '-s']: return str(len(raw)).encode()
        if command[:2] == ['cat-file', 'blob']: return raw
        pytest.fail('unexpected git')
    monkeypatch.setattr(module, '_git', git)
    return args


def test_preflight_accepts_synthetic_exact_context(preflight_fixture):
    module._preflight(preflight_fixture, float('inf'))


@pytest.mark.parametrize('path', list(module.SOURCE_PINS) + ['self'])
def test_each_selected_pin_is_load_bearing(preflight_fixture, monkeypatch, path):
    original = module._source_digest
    bad = module.SOURCE if path == 'self' else module.ROOT / path
    monkeypatch.setattr(module, '_source_digest', lambda target: '0' * 64 if target == bad else original(target))
    with pytest.raises(module.Refused, match='source'): module._preflight(preflight_fixture, float('inf'))


@pytest.mark.parametrize('command', [('rev-parse', '--show-toplevel'), ('branch', '--show-current'),
    ('rev-parse', 'HEAD'), ('status', '--porcelain'), ('cat-file', '-s'), ('cat-file', 'blob')])
def test_each_git_context_check_is_load_bearing(preflight_fixture, monkeypatch, command):
    original = module._git
    monkeypatch.setattr(module, '_git', lambda values, deadline, limit=65536:
        b'bad' if tuple(values[:2]) == command else original(values, deadline, limit))
    with pytest.raises(module.Refused): module._preflight(preflight_fixture, float('inf'))


@pytest.mark.parametrize('key,value', [('platform', 'win32'), ('version_info', (3, 12)),
    ('executable', '/usr/bin/python3')])
def test_host_exact(preflight_fixture, key, value):
    setattr(module.sys, key, value)
    with pytest.raises(module.Refused, match='context'): module._preflight(preflight_fixture, float('inf'))


def test_existing_and_expired_alarm_preserve_handler():
    previous = module.signal.getsignal(module.signal.SIGALRM)
    with pytest.raises(module.Refused, match='deadline'):
        with module.alarm(0): pytest.fail('expired')
    assert module.signal.getsignal(module.signal.SIGALRM) == previous
    module.signal.setitimer(module.signal.ITIMER_REAL, 30)
    try:
        with pytest.raises(module.Refused, match='context'):
            with module.alarm(module.time.monotonic() + 1): pytest.fail('existing timer')
    finally:
        module.signal.setitimer(module.signal.ITIMER_REAL, 0)
    assert module.signal.getsignal(module.signal.SIGALRM) == previous


def test_alarm_fires_and_restores():
    previous = module.signal.getsignal(module.signal.SIGALRM)
    with pytest.raises(module.Refused, match='deadline'):
        with module.alarm(module.time.monotonic() + 0.01): module.time.sleep(0.05)
    assert module.signal.getsignal(module.signal.SIGALRM) == previous
    assert module.signal.getitimer(module.signal.ITIMER_REAL) == (0.0, 0.0)


def test_profile_remains_readonly_and_no_gate_is_accepted():
    profile = module.profile_record()
    assert profile['endpoints'] == list(module.ENDPOINTS) and profile['max_application_dispatches'] == 2
    assert profile['deadline_seconds'] == 60 and profile['max_collaborators'] == 8
    assert profile['automatic_retry'] is False and profile['prior_observers_and_a1_through_a5_remain_spent'] is True
    assert all(profile[key] is False for key in module.FALSE_FLAGS)
    assert len(profile['source_pins']) == 9
    assert all(profile[key] == 0 for key in ('shared_look', 'development_look', 'infrastructure_look'))


def test_invalid_bindings_never_echoed():
    result = module.binding(SimpleNamespace(expected_head='private input', caller_sha256='secret'))
    assert result['expected_head'] is None and result['caller_sha256'] is None
    assert b'private input' not in module.canonical(result) and b'secret' not in module.canonical(result)


@pytest.mark.parametrize('field,output', [('name', 'name'), ('publicId', 'public_id'),
    ('codeSourceId', 'code_source_id')])
@pytest.mark.parametrize('value', [module.A5_CODE_SOURCE_ID, 'Mia', 'mia-ai',
    'unrecognized private value', None, False, True, 12345, 1.25, [], {'secret-key': 'secret-value'}])
def test_known_field_hashes_and_exact_a5_relation(scope, field, output, value):
    result = module.record_projection({field: value}, 12345)
    item = result[output]
    assert item['present'] is True
    assert item['value_sha256'] == module.sha(module.canonical(value))
    assert item['equals_a5_code_source_id'] is (type(value) is str and value == module.A5_CODE_SOURCE_ID)
    module._validate_records(module.collaborators_projection({'collaborators': [{field: value}]}, 12345))
    raw = module.canonical(result)
    assert all(secret not in raw for secret in (module.A5_CODE_SOURCE_ID.encode('ascii'),
        b'unrecognized private value', b'secret-key', b'secret-value'))


@pytest.mark.parametrize('field,output', [('name', 'name'), ('publicId', 'public_id'),
    ('codeSourceId', 'code_source_id')])
def test_absent_known_fields_have_no_value_digest(scope, field, output):
    result = module.record_projection({}, 12345)[output]
    assert result['present'] is False and result['value_sha256'] is None
    assert result['equals_a5_code_source_id'] is False


@pytest.mark.parametrize('key', ['name', 'public_id', 'code_source_id'])
@pytest.mark.parametrize('mutation', ['match_false', 'match_type', 'match_wrong_hash',
    'match_wrong_json_type', 'absent_hash', 'null_wrong_hash', 'boolean_wrong_hash', 'invalid_type'])
def test_hashed_field_validator_rejects_false_equivalence(scope, key, mutation):
    source_key = {'name': 'name', 'public_id': 'publicId', 'code_source_id': 'codeSourceId'}[key]
    field = module.collaborators_projection({'collaborators': [{source_key: module.A5_CODE_SOURCE_ID}]}, 12345)
    item = field['records'][0][key]
    if mutation == 'match_false': item['equals_a5_code_source_id'] = False
    elif mutation == 'match_type': item['equals_a5_code_source_id'] = 1
    elif mutation == 'match_wrong_hash': item['value_sha256'] = 'a' * 64
    elif mutation == 'match_wrong_json_type': item['json_type'] = 'number'
    elif mutation == 'absent_hash': item.update(present=False, json_type='absent', equals_a5_code_source_id=False)
    elif mutation == 'null_wrong_hash': item.update(json_type='null', value_sha256='a' * 64, equals_a5_code_source_id=False)
    elif mutation == 'boolean_wrong_hash': item.update(json_type='boolean', value_sha256='a' * 64, equals_a5_code_source_id=False)
    else: item.update(json_type='invalid', value_sha256='a' * 64, equals_a5_code_source_id=False)
    with pytest.raises(module.Refused, match='response_shape'): module._validate_records(field)


@pytest.mark.parametrize('mutation', ['name_mia_claim', 'name_mia_denial', 'public_mia_claim',
    'public_mia_denial', 'd3_claim', 'd3_denial', 'permission_type', 'permission_absence'])
def test_special_equality_flags_and_permission_shapes_are_bound(scope, mutation):
    field = module.collaborators_projection({'collaborators': [mia()]}, 12345)
    row = field['records'][0]
    if mutation == 'name_mia_claim': row['name']['value_sha256'] = 'a' * 64
    elif mutation == 'name_mia_denial': row['name_exact_mia'] = False
    elif mutation == 'public_mia_claim': row['public_id']['value_sha256'] = 'a' * 64
    elif mutation == 'public_mia_denial': row['public_id']['exact_mia_sentinel'] = False
    elif mutation == 'd3_claim': row['row_equals_d3_mia'] = True
    elif mutation == 'd3_denial': row['row_sha256'] = module.D3_MIA_ROW_SHA256
    elif mutation == 'permission_type': row['permission_shape']['json_type'] = 'number'
    else: row['permission_shape'].update(present=False, json_type='absent')
    with pytest.raises(module.Refused): module._validate_records(field)


def test_d3_whole_row_hash_equality_is_derived_not_asserted(scope, monkeypatch):
    pin = module.sha(module.canonical(mia()))
    monkeypatch.setattr(module, 'D3_MIA_ROW_SHA256', pin)
    exact = module.record_projection(mia(), 12345)
    changed = module.record_projection({**mia(), 'unreported-key': 1}, 12345)
    assert exact['row_equals_d3_mia'] is True and changed['row_equals_d3_mia'] is False
    module._validate_records(module.collaborators_projection({'collaborators': [mia()]}, 12345))


@pytest.mark.parametrize('value', [True, False, None, 'private', 0, [], {}])
def test_project_public_field_is_typed_diagnostic_not_missing_private_default(scope, value):
    packet = project()
    packet['projects'][0]['public'] = value
    _, result = module.project_observation(packet)
    assert result['public']['present'] is True
    assert result['public']['valid_boolean'] is (type(value) is bool)
    assert result['public']['value'] is (value if type(value) is bool else None)
    module._validate_project(result)
    packet['projects'][0].pop('public')
    _, result = module.project_observation(packet)
    assert result['public'] == {'present': False, 'json_type': 'absent', 'valid_boolean': False, 'value': None}
    assert module.FALSE_FLAGS['privacy_verified'] is False


@pytest.mark.parametrize('project_rows,dedicated_rows,first_count,second_count,equal', [
    ([owner(), mia()], [owner()], 1, 1, True),
    ([owner()], [{**owner(), 'email': 'changed'}], 1, 1, False),
    ([owner(), owner()], [owner()], 2, 1, None),
    ([owner()], [mia()], 1, 0, None),
    ([mia()], [owner()], 0, 1, None),
    ([], [], 0, 0, None),
    ([{'owner': 1}], [owner()], 0, 1, None),
])
def test_sole_true_owner_equivalence_is_exact_not_count_only(scope, project_rows, dedicated_rows,
        first_count, second_count, equal):
    first, second = project(), dedicated()
    first['projects'][0]['collaborators'] = project_rows
    second['collaborators'] = dedicated_rows
    _, observed = module.project_observation(first)
    compared = module.comparison(observed, module.dedicated_observation(second, 12345))
    assert compared['project_true_owner_count'] == first_count
    assert compared['dedicated_true_owner_count'] == second_count
    assert compared['sole_owner_row_hash_equal'] is equal


@pytest.mark.parametrize('key,value', [('project_true_owner_count', True),
    ('dedicated_true_owner_count', 0), ('sole_owner_row_hash_equal', False)])
def test_owner_comparison_output_cannot_be_fabricated(scope, key, value):
    observed = completed()
    observed['comparison'][key] = value
    with pytest.raises(module.Refused): module._validate_result(observed, True)


def test_cross_view_field_hash_type_conflict_rejected_even_when_row_hashes_differ(scope):
    observed = completed()
    item = observed['dedicated_observation']['collaborators']['records'][0]
    item['row_sha256'] = 'd' * 64
    # Unknown plaintext digest is equal in the project owner name. A second
    # view cannot claim that same canonical value was instead an array.
    item['name']['json_type'] = 'array'
    observed['comparison'] = module.comparison(observed['project_observation'], observed['dedicated_observation'])
    with pytest.raises(module.Refused): module._validate_result(observed, True)


def test_a5_shaped_nonowner_is_only_diagnostic_and_uid_null_retained(scope):
    row = {'owner': False, 'uid': None, 'name': module.A5_CODE_SOURCE_ID,
        'publicId': module.A5_CODE_SOURCE_ID, 'codeSourceId': module.A5_CODE_SOURCE_ID,
        'permission': 'write', 'liveControl': True, 'unreported-private-key': 'private-value'}
    projected = module.record_projection(row, 12345)
    assert projected['uid']['json_type'] == 'null' and projected['uid']['equals_project_owner'] is None
    assert projected['name']['equals_a5_code_source_id'] is True
    assert projected['name_exact_mia'] is False and projected['row_equals_d3_mia'] is False
    assert projected['public_id']['bounded_nonempty_ascii'] is False  # Spaces, not an invented identifier grammar.
    module._validate_records(module.collaborators_projection({'collaborators': [row]}, 12345))
    raw = module.canonical(projected)
    assert b'unreported-private-key' not in raw and b'private-value' not in raw
    assert module.FALSE_FLAGS['synthetic_entry_proven'] is False


def test_both_eight_row_views_fit_fixed_output_bound(scope):
    first, second = project(), dedicated()
    rows = [{**owner(), 'uid': 100 + index, 'name': 'private-name-' + str(index),
        'codeSourceId': 'private-code-' + str(index), 'unknown-private-key': 'secret' * 10}
        for index in range(8)]
    first['projects'][0]['collaborators'] = rows
    second['collaborators'] = list(reversed(rows))
    result = module.observe(lambda endpoint, _payload: first if endpoint == module.ENDPOINTS[0]
        else second, lambda *_: None, initial(), float('inf'))
    args = SimpleNamespace(expected_head='a' * 40, caller_sha256='b' * 64)
    report = {**module.binding(args), 'observation_completed': True, 'result': result, **module.FALSE_FLAGS}
    report_raw = module.canonical(report)
    raw = module.canonical({**report, 'report': {'sha256': module.sha(report_raw), 'byte_count': len(report_raw)}})
    assert 0 < len(raw) <= module.MAX_OUTPUT == 24576
    module.validate_output(raw, 0, args)
    assert b'unknown-private-key' not in raw and b'private-name-' not in raw


def test_consumed_a5_pins_and_literal_are_selected_not_operational_imports():
    assert module.A5_CODE_SOURCE_ID == 'Codex ARV2 R298 A5 20261024'
    assert module.SOURCE_PINS['scripts/arv2_r298_privacy_recovery_remote.py'] == '5be59e13e760c6e7deacdf5fe9296968ad40a3d4140a9e544ec3de7d41b6a5fd'
    assert module.SOURCE_PINS['scripts/run_arv2_r298_privacy_recovery.py'] == '98ce1ee2a2d8a54523e383d9ca578575ad2c2510a171f2d772e2144de92d0e98'
    assert module.D3_MIA_ROW_SHA256 == '6e3fb9db0a3303a202fdebd062e91cd8a974ac564cab784dbccedc361477f44f'
    assert module.ENDPOINTS == ('projects/read', 'projects/collaboration/read')
    assert str(module.CONTROL).endswith('/newrule_lock_access/R314-20261024-A')


def test_a5_public_id_full_envelope_validation_does_not_invent_identifier_grammar(scope):
    first, second = project(), dedicated()
    first['projects'][0]['collaborators'].append({'owner': False, 'uid': None,
        'publicId': module.A5_CODE_SOURCE_ID, 'name': module.A5_CODE_SOURCE_ID,
        'codeSourceId': module.A5_CODE_SOURCE_ID, 'permission': 'write', 'liveControl': True})
    result = module.observe(lambda endpoint, _payload: first if endpoint == module.ENDPOINTS[0]
        else second, lambda *_: None, initial(), float('inf'))
    args = SimpleNamespace(expected_head='a' * 40, caller_sha256='b' * 64)
    report = {**module.binding(args), 'observation_completed': True, 'result': result, **module.FALSE_FLAGS}
    report_raw = module.canonical(report)
    raw = module.canonical({**report, 'report': {'sha256': module.sha(report_raw), 'byte_count': len(report_raw)}})
    value = module.validate_output(raw, 0, args)
    observed = value['result']['project_observation']['collaborators']['records'][-1]
    assert observed['public_id']['equals_a5_code_source_id'] is True
    assert observed['public_id']['bounded_nonempty_ascii'] is False
    assert value['collaborator_policy_accepted'] is value['edit_lock_proven'] is False


def test_direct_help_minimal_environment_without_operational_entry(scope):
    # Native parent sandbox is inherited; --help exits before run/claim/credentials.
    child_env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C',
        'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(scope),
        'XDG_CACHE_HOME': str(scope), 'PYTHONPYCACHEPREFIX': str(scope / 'pycache')}
    result = module.subprocess.run([str(module.PYTHON), '-B', str(module.SOURCE), '--help'],
        cwd=module.ROOT, env=child_env, stdin=module.subprocess.DEVNULL,
        capture_output=True, timeout=5, check=False)
    assert result.returncode == 0 and result.stderr == b''
    assert b'--expected-head' in result.stdout and b'--caller-sha256' in result.stdout
    assert len(result.stdout) < 4096 and not module.CONTROL.exists()
