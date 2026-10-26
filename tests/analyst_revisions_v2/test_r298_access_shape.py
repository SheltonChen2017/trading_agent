"""Synthetic access-shape contract tests; native runner denies remote/private use."""
from contextlib import nullcontext
import copy
import json
import os
from types import SimpleNamespace

import pytest

from scripts import observe_arv2_r298_access_shape as module


@pytest.fixture
def scope(monkeypatch, tmp_path):
    assert tmp_path.is_relative_to(module.ROOT / '.pytest_cache')
    monkeypatch.setattr(module, 'CONTROL', tmp_path / 'shape' / 'once')
    monkeypatch.setattr(module, 'ORGANIZATION_SHA256', module.sha(b'a' * 32))
    return tmp_path


def project():
    return {'success': True, 'projects': [{'projectId': module.PROJECT,
        'organizationId': 'a' * 32, 'name': module.PROJECT_NAME, 'language': 'Py',
        'owner': True, 'ownerId': 12345, 'public': False, 'codeRunning': False,
        'collaborators': [{'owner': True, 'uid': 12345},
            {'owner': False, 'uid': 'mia-ai', 'publicId': 'mia-ai'}]}]}


def initial():
    return {**module.new_state(), 'stage': 'credentials'}


def test_multiple_collaborators_observed_without_acceptance(scope):
    result = module.project_observation(project())
    field = result['collaborators']
    assert field['present'] is True and field['json_type'] == 'array' and field['list_count'] == 2
    counts = field['entries']
    assert counts['dict'] == 2 and counts['non_dict'] == 0
    assert counts['owner_true'] == counts['owner_false'] == 1
    assert counts['uid_equals_owner_true'] == counts['uid_equality_unavailable'] == 1
    assert counts['uid_exact_mia_sentinel'] == counts['public_id_exact_mia_sentinel'] == 1
    assert tuple(counts[key] for key in module.JOINT_COUNTS) == (1, 1, 1, 1, 0)
    assert result['code_running']['value'] is False
    assert b'12345' not in module.canonical(result) and b'mia-ai' not in module.canonical(result)
    module._validate_observation(result)


@pytest.mark.parametrize('value,label', [(None, 'null'), (False, 'boolean'), (1, 'number'),
    (1.1, 'number'), ('secret', 'string'), ({'name': 'secret'}, 'object')])
def test_nonlist_shape_is_not_guessed_empty(scope, value, label):
    response = project()
    response['projects'][0]['collaborators'] = value
    field = module.project_observation(response)['collaborators']
    assert field == {'present': True, 'json_type': label, 'list_count': None, 'entries': None}
    assert b'secret' not in module.canonical(field)


def test_missing_field_distinct_from_null(scope):
    response = project()
    del response['projects'][0]['collaborators']
    assert module.project_observation(response)['collaborators'] == {
        'present': False, 'json_type': 'absent', 'list_count': None, 'entries': None}


@pytest.mark.parametrize('value,label', [(True, 'boolean'), (False, 'boolean'), (None, 'null'),
    ('secret', 'string'), (0, 'number'), (0.0, 'number'), ([], 'array'), ({}, 'object')])
def test_code_running_exact_type_never_coerced(scope, value, label):
    response = project()
    response['projects'][0]['codeRunning'] = value
    field = module.project_observation(response)['code_running']
    assert field['json_type'] == label and field['valid_boolean'] is (type(value) is bool)
    assert field['value'] is (value if type(value) is bool else None)


def test_aggregate_shapes_not_raw_rows(scope):
    response = project()
    response['projects'][0]['collaborators'] = [None, 'secret', 4, [], {},
        {'owner': None, 'uid': None}, {'owner': 'secret', 'uid': 54321, 'email': 'secret'},
        {'owner': 1, 'uid': 12345.0}, {'owner': False, 'uid': True},
        {'owner': True, 'uid': 12345, 'publicId': 'not-mia'}]
    result = module.project_observation(response)
    counts = result['collaborators']['entries']
    assert counts['dict'] == 6 and counts['non_dict'] == 4
    assert counts['owner_present'] == 5 and counts['owner_true'] == counts['owner_false'] == 1
    assert counts['uid_equals_owner_true'] == counts['uid_equals_owner_false'] == 1
    assert counts['uid_equality_unavailable'] == 4
    assert counts['uid_exact_mia_sentinel'] == counts['public_id_exact_mia_sentinel'] == 0
    assert all(raw not in module.canonical(result) for raw in (b'secret', b'12345', b'54321', b'not-mia'))
    module._validate_observation(result)


@pytest.mark.parametrize('value', [None, True, False, 0, -1, 12345.0, '12345', [], {}])
def test_owner_id_must_be_exact_positive_integer_for_equality(scope, value):
    response = project()
    response['projects'][0]['ownerId'] = value
    result = module.project_observation(response)
    assert result['project_owner_id']['valid_positive_integer'] is False
    assert result['collaborators']['entries']['uid_equality_unavailable'] == 2
    module._validate_observation(result)


@pytest.mark.parametrize('field', ['uid', 'publicId'])
@pytest.mark.parametrize('value', ['MIA-AI', 'mia-ai ', 'mia', 'secret', None, True, 7, ['mia-ai']])
def test_mia_sentinel_exact_string_only(scope, field, value):
    response = project()
    response['projects'][0]['collaborators'] = [{field: value}]
    counts = module.project_observation(response)['collaborators']['entries']
    assert counts['uid_exact_mia_sentinel'] == counts['public_id_exact_mia_sentinel'] == 0


@pytest.mark.parametrize('count', [0, 1, 128])
def test_list_bounds(scope, count):
    response = project()
    response['projects'][0]['collaborators'] = [{}] * count
    result = module.project_observation(response)
    assert result['collaborators']['list_count'] == count
    module._validate_observation(result)


def test_excessive_list_refuses(scope):
    response = project()
    response['projects'][0]['collaborators'] = [{}] * 129
    with pytest.raises(module.Refused, match='bound'):
        module.project_observation(response)


@pytest.mark.parametrize('key,value,reason', [('projectId', True, 'project_id'),
    ('projectId', 1, 'project_id'), ('organizationId', 'b' * 32, 'organization'),
    ('organizationId', None, 'organization'), ('name', 'other', 'name'),
    ('language', 'C#', 'language'), ('owner', 1, 'owner'), ('owner', False, 'owner'),
    ('public', True, 'private'), ('public', None, 'private')])
def test_scope_still_refuses_before_shape(scope, key, value, reason):
    response = project()
    response['projects'][0][key] = value
    with pytest.raises(module.Refused, match=reason):
        module.project_observation(response)


@pytest.mark.parametrize('rows', [None, {}, [], [None], [{}, {}]])
def test_project_shape(rows):
    with pytest.raises(module.Refused, match='project_shape'):
        module.project_observation({'projects': rows})


def test_existing_private_absence_contract_not_changed(scope):
    response = project()
    del response['projects'][0]['public']
    assert module.project_observation(response)['code_running']['value'] is False


def test_single_dispatch_intent_before_contact(scope):
    events, state = [], initial()
    def request(endpoint, payload):
        assert events[-1][0] == 'project-intent.json'
        assert endpoint == 'projects/read' and payload == {'projectId': module.PROJECT}
        events.append((endpoint, payload))
        return project()
    result = module.observe(request, lambda *item: events.append(item), state, float('inf'))
    assert [item[0] for item in events] == ['project-intent.json', 'projects/read', 'project-observation.json']
    assert result['application_dispatch_count'] == 1 and result['provider_request_count'] is None
    with pytest.raises(module.Refused, match='dispatch'):
        module.observe(lambda *_: pytest.fail('repeat'), lambda *_: None, state, float('inf'))


def test_intent_failure_prevents_dispatch(scope):
    def write(*_):
        raise module.Refused('control')
    state = initial()
    with pytest.raises(module.Refused, match='control'):
        module.observe(lambda *_: pytest.fail('contact'), write, state, float('inf'))
    assert state['application_dispatch_count'] == 0


def test_deadline_after_intent_prevents_dispatch(scope, monkeypatch):
    ticks = iter((0, 2))
    monkeypatch.setattr(module.time, 'monotonic', lambda: next(ticks))
    state = initial()
    with pytest.raises(module.Refused, match='deadline'):
        module.observe(lambda *_: pytest.fail('contact'), lambda *_: None, state, 1)
    assert state['application_dispatch_count'] == 0


@pytest.mark.parametrize('response,reason', [(None, 'response_shape'), ({'success': 1}, 'response_refused'),
    ({'success': False}, 'response_refused'), ({'secret': 'x' * 1048576}, 'bound'),
    ({'secret': float('nan')}, 'json')])
def test_bad_response_single_attempt(scope, response, reason):
    state, calls = initial(), []
    def request(*_):
        calls.append(1)
        return response
    with pytest.raises(module.Refused, match=reason):
        module.observe(request, lambda *_: None, state, float('inf'))
    assert len(calls) == state['application_dispatch_count'] == 1


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
            return project()
        return SimpleNamespace(request=request)
    monkeypatch.setattr(environment, 'guarded_client', client)
    return SimpleNamespace(expected_head='a' * 40, caller_sha256='b' * 64), calls


def read_output(capsys, args, exit_code):
    raw = capsys.readouterr().out.encode('ascii')
    return module.validate_output(raw, exit_code, args)


def test_cli_success_observation_not_readiness(fake_run, capsys):
    args, calls = fake_run
    assert module.run(args) == 0
    value = read_output(capsys, args, 0)
    assert calls == ['client', 'projects/read']
    assert all(value[key] is False for key in module.FALSE_FLAGS)
    raw = (module.CONTROL / 'report.json').read_bytes()
    assert value['report'] == {'sha256': module.sha(raw), 'byte_count': len(raw)}
    assert len(list(module.CONTROL.iterdir())) == 4


def test_duplicate_claim_no_credentials_or_contact(fake_run, capsys):
    args, calls = fake_run
    assert module.run(args) == 0
    capsys.readouterr()
    assert module.run(args) == 2
    value = read_output(capsys, args, 2)
    assert value['result']['failure_code'] == 'claim' and value['report'] is None
    assert calls == ['client', 'projects/read']


@pytest.mark.parametrize('stage', ['preflight', 'credentials', 'project', 'postflight', 'report'])
def test_failure_bound_to_source_and_actual_exit(fake_run, capsys, monkeypatch, stage):
    from scripts import arv2_newrule_execution_environment as environment
    args, calls = fake_run
    def fail(*_):
        raise RuntimeError('never retain secret')
    if stage == 'preflight': monkeypatch.setattr(module, '_preflight', fail)
    elif stage == 'credentials': monkeypatch.setattr(environment, 'guarded_client', fail)
    elif stage == 'project': monkeypatch.setattr(environment, 'guarded_client', lambda: SimpleNamespace(request=fail))
    elif stage == 'postflight':
        seen = []
        def preflight(*_):
            seen.append(1)
            if len(seen) == 2: fail()
        monkeypatch.setattr(module, '_preflight', preflight)
    else:
        original = module.Store.write
        def write(self, name, value):
            result = original(self, name, value)
            if name == 'report.json': fail()
            return result
        monkeypatch.setattr(module.Store, 'write', write)
    assert module.run(args) == 2
    value = read_output(capsys, args, 2)
    assert value['result']['stage'] == stage and value['result']['failure_code'] == 'unknown_exception'
    assert b'never retain secret' not in module.canonical(value)
    assert value['report'] is None if stage == 'preflight' else value['report'] is not None
    with pytest.raises(module.Refused):
        module.validate_output(module.canonical(value), 0, args)


@pytest.mark.parametrize('actual_exit', [None, True, False, '0', 1, -9])
def test_external_actual_exit_is_exact(fake_run, capsys, actual_exit):
    args, _ = fake_run
    assert module.run(args) == 0
    value = read_output(capsys, args, 0)
    with pytest.raises(module.Refused):
        module.validate_output(module.canonical(value), actual_exit, args)


@pytest.mark.parametrize('failed', [False, True])
@pytest.mark.parametrize('changed', ['hash', 'length', 'missing', 'head', 'self', 'profile', 'project', 'flag'])
def test_external_binding_and_pin_are_load_bearing(fake_run, capsys, monkeypatch, failed, changed):
    from scripts import arv2_newrule_execution_environment as environment
    args, _ = fake_run
    if failed:
        def refuse(): raise module.Refused('owner')
        monkeypatch.setattr(environment, 'guarded_client', refuse)
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
    else: value['project_ready'] = True
    with pytest.raises(module.Refused):
        module.validate_output(module.canonical(value), code, args)


@pytest.mark.parametrize('mutation', ['count_bool', 'sum', 'owner_presence', 'owner_types', 'owner_true',
    'uid_sum', 'uid_number', 'uid_mia', 'public_mia', 'owner_id', 'field_missing', 'field_type',
    'code_coercion', 'code_presence', 'extra', 'nonarray', 'count_large'])
def test_shape_validator_rejects_incoherent_counts(scope, mutation):
    value = module.project_observation(project())
    field, owner = value['collaborators'], value['project_owner_id']
    counts = field['entries']
    if mutation == 'count_bool': field['list_count'] = True
    elif mutation == 'sum': counts['dict'] += 1
    elif mutation == 'owner_presence': counts['owner_present'] -= 1
    elif mutation == 'owner_types': counts['owner_types']['private'] = 0
    elif mutation == 'owner_true': counts['owner_true'] = 0
    elif mutation == 'uid_sum': counts['uid_equality_unavailable'] = 0
    elif mutation == 'uid_number': counts['uid_equals_owner_true'] = 2; counts['uid_equality_unavailable'] = 0
    elif mutation == 'uid_mia': counts['uid_exact_mia_sentinel'] = 2
    elif mutation == 'public_mia': counts['public_id_exact_mia_sentinel'] = 3
    elif mutation == 'owner_id': owner['valid_positive_integer'] = False
    elif mutation == 'field_missing': field['present'] = False
    elif mutation == 'field_type': field['json_type'] = 'secret'
    elif mutation == 'code_coercion': value['code_running']['value'] = 0
    elif mutation == 'code_presence': value['code_running']['present'] = False
    elif mutation == 'extra': counts['secret'] = 0
    elif mutation == 'nonarray': field['json_type'] = 'null'
    else: field['list_count'] = 129
    with pytest.raises(module.Refused):
        module._validate_observation(value)


@pytest.mark.parametrize('mutation', ['count', 'stage', 'event', 'endpoint', 'provider', 'observation'])
def test_result_validator_not_just_pin(scope, mutation):
    state = initial()
    result = module.observe(lambda *_: project(), lambda *_: None, state, float('inf'))
    if mutation == 'count': result['application_dispatch_count'] = 2
    elif mutation == 'stage': result['stage'] = 'credentials'
    elif mutation == 'event': result['last_event'] = 'intent'
    elif mutation == 'endpoint': result['last_endpoint'] = 'files/create'
    elif mutation == 'provider': result['provider_request_count'] = 0
    else: result['project_observation'] = None
    with pytest.raises(module.Refused):
        module._validate_result(result, True)


@pytest.mark.parametrize('suffix', [b'\n', b' ', b'garbage'])
def test_external_canonical_exact(fake_run, capsys, suffix):
    args, _ = fake_run
    assert module.run(args) == 0
    value = read_output(capsys, args, 0)
    with pytest.raises(module.Refused):
        module.validate_output(module.canonical(value) + suffix, 0, args)


@pytest.mark.parametrize('mutation', ['bytes', 'mode', 'replace', 'directory', 'foreign'])
def test_store_detects_change(scope, mutation):
    with module.Store() as store:
        store.write('claim.json', {'synthetic': True})
        target = module.CONTROL / 'claim.json'
        if mutation == 'bytes': target.write_bytes(b'bad')
        elif mutation == 'mode': target.chmod(0o644)
        elif mutation == 'replace': target.rename(module.CONTROL / 'moved.json'); target.write_bytes(b'bad')
        elif mutation == 'directory': module.CONTROL.rename(module.CONTROL.with_name('moved')); module.CONTROL.mkdir(mode=0o700)
        else: (module.CONTROL / 'foreign').write_bytes(b'bad')
        with pytest.raises(module.Refused, match='control_changed'):
            store.verify()


def test_store_symlink_parent_refuses(scope):
    elsewhere = scope / 'elsewhere'
    elsewhere.mkdir()
    module.CONTROL.parent.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(OSError): module.Store()
    assert list(elsewhere.iterdir()) == []


@pytest.mark.parametrize('name', ['../bad.json', 'bad.txt', '', 'UPPER.json'])
def test_store_names(scope, name):
    with module.Store() as store:
        with pytest.raises(module.Refused): store.write(name, {})


def test_existing_and_expired_alarm_do_not_replace_handler():
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


def test_preflight_valid_synthetic(preflight_fixture):
    module._preflight(preflight_fixture, float('inf'))


@pytest.mark.parametrize('path', list(module.SOURCE_PINS) + ['self'])
def test_each_pin_load_bearing(preflight_fixture, monkeypatch, path):
    original = module._source_digest
    bad = module.SOURCE if path == 'self' else module.ROOT / path
    monkeypatch.setattr(module, '_source_digest', lambda target: '0' * 64 if target == bad else original(target))
    with pytest.raises(module.Refused, match='source'): module._preflight(preflight_fixture, float('inf'))


@pytest.mark.parametrize('command', [('rev-parse', '--show-toplevel'), ('branch', '--show-current'),
    ('rev-parse', 'HEAD'), ('status', '--porcelain'), ('cat-file', '-s'), ('cat-file', 'blob')])
def test_each_git_context_check_load_bearing(preflight_fixture, monkeypatch, command):
    original = module._git
    monkeypatch.setattr(module, '_git', lambda values, deadline, limit=65536:
        b'bad' if tuple(values[:2]) == command else original(values, deadline, limit))
    with pytest.raises(module.Refused): module._preflight(preflight_fixture, float('inf'))


@pytest.mark.parametrize('key,value', [('platform', 'win32'), ('version_info', (3, 12)), ('executable', '/usr/bin/python3')])
def test_host_exact(preflight_fixture, key, value):
    setattr(module.sys, key, value)
    with pytest.raises(module.Refused, match='context'): module._preflight(preflight_fixture, float('inf'))


def test_profile_is_diagnostic_only():
    profile = module.profile_record()
    assert profile['endpoint'] == 'projects/read' and profile['max_application_dispatches'] == 1
    assert profile['deadline_seconds'] == 60 and profile['prior_observer_remains_spent'] is True
    assert all(profile[key] is False for key in module.FALSE_FLAGS)
    assert len(profile['source_pins']) == 6


def test_invalid_args_never_echoed():
    result = module.binding(SimpleNamespace(expected_head='private input', caller_sha256='secret'))
    assert result['expected_head'] is None and result['caller_sha256'] is None
    assert b'private input' not in module.canonical(result) and b'secret' not in module.canonical(result)


@pytest.mark.parametrize('entry,expected', [
    ({'owner': True, 'uid': 12345}, (1, 0, 0, 0, 0)),
    ({'owner': False, 'uid': 'mia-ai'}, (0, 1, 0, 0, 0)),
    ({'owner': False, 'uid': 54321, 'publicId': 'mia-ai'}, (0, 0, 1, 0, 0)),
    ({'owner': False, 'uid': 'mia-ai', 'publicId': 'mia-ai'}, (0, 1, 1, 1, 0)),
    ({'owner': True, 'uid': 'mia-ai', 'publicId': 'mia-ai'}, (0, 0, 0, 0, 1)),
    ({'owner': True, 'uid': 12345, 'publicId': 'mia-ai'}, (1, 0, 0, 0, 1)),
    ({'owner': True, 'uid': 'mia-ai'}, (0, 0, 0, 0, 1)),
    ({'owner': 1, 'uid': 12345, 'publicId': 'mia-ai'}, (0, 0, 0, 0, 0)),
    ({'owner': 0, 'uid': 'mia-ai', 'publicId': 'mia-ai'}, (0, 0, 0, 0, 0)),
    ({'uid': 'mia-ai', 'publicId': 'mia-ai'}, (0, 0, 0, 0, 0)),
    ({'owner': True, 'uid': True}, (0, 0, 0, 0, 0)),
    ({'owner': True, 'uid': 12345.0}, (0, 0, 0, 0, 0)),
])
def test_joint_counts_bind_only_exact_same_entry(scope, entry, expected):
    response = project()
    response['projects'][0]['collaborators'] = [entry]
    value = module.project_observation(response)
    counts = value['collaborators']['entries']
    assert tuple(counts[key] for key in module.JOINT_COUNTS) == expected
    module._validate_observation(value)
    assert b'12345' not in module.canonical(value) and b'mia-ai' not in module.canonical(value)


def test_joint_counts_do_not_join_different_rows(scope):
    response = project()
    response['projects'][0]['collaborators'] = [
        {'owner': False, 'uid': 'mia-ai'}, {'owner': False, 'publicId': 'mia-ai'},
        {'owner': True, 'uid': 12345}]
    value = module.project_observation(response)
    counts = value['collaborators']['entries']
    assert tuple(counts[key] for key in module.JOINT_COUNTS) == (1, 1, 1, 0, 0)
    module._validate_observation(value)


def test_joint_counts_distinguish_owner_and_nonowner_sentinels(scope):
    response = project()
    response['projects'][0]['collaborators'] = [
        {'owner': False, 'uid': 'mia-ai'}, {'owner': True, 'publicId': 'mia-ai'}]
    value = module.project_observation(response)
    counts = value['collaborators']['entries']
    assert tuple(counts[key] for key in module.JOINT_COUNTS) == (0, 1, 0, 0, 1)
    module._validate_observation(value)


@pytest.mark.parametrize('field,value', [
    ('owner_true_uid_equals_owner', 2), ('owner_false_uid_exact_mia', 2),
    ('owner_false_public_id_exact_mia', 2), ('owner_false_both_exact_mia', 0),
    ('owner_false_both_exact_mia', 2), ('owner_true_either_exact_mia', 1),
    ('owner_true_uid_equals_owner', True), ('owner_false_uid_exact_mia', -1),
])
def test_joint_count_validator_enforces_aggregate_coherence(scope, field, value):
    result = module.project_observation(project())
    result['collaborators']['entries'][field] = value
    with pytest.raises(module.Refused): module._validate_observation(result)


def test_profile_binds_joint_observation_fields():
    assert module.profile_record()['finite_joint_count_fields'] == list(module.JOINT_COUNTS)


def test_direct_cli_help_with_minimal_environment(scope):
    # Native parent sandbox is inherited. --help exits before operational run.
    child_env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C',
        'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(scope),
        'XDG_CACHE_HOME': str(scope), 'PYTHONPYCACHEPREFIX': str(scope / 'pycache')}
    result = module.subprocess.run([str(module.PYTHON), '-B', str(module.SOURCE), '--help'],
        cwd=module.ROOT, env=child_env, stdin=module.subprocess.DEVNULL,
        capture_output=True, timeout=5, check=False)
    assert result.returncode == 0 and result.stderr == b''
    assert b'--expected-head' in result.stdout and b'--caller-sha256' in result.stdout
    assert len(result.stdout) < 4096
    assert not module.CONTROL.exists()


@pytest.mark.parametrize('code', ['arguments', 'context', 'source', 'deadline', 'claim'])
def test_preclaim_finite_failures_validate_without_invented_persistence(scope, code):
    args = SimpleNamespace(expected_head='a' * 40, caller_sha256='b' * 64)
    state = module.new_state()
    value = {**module.binding(args), 'observation_completed': False,
        'result': module.finite_failure(module.Refused(code), state),
        'report': None, **module.FALSE_FLAGS}
    assert module.validate_output(module.canonical(value), 2, args) == value


@pytest.mark.parametrize('mutation', ['failure_code', 'stage', 'endpoint', 'count', 'event',
    'observation', 'provider', 'consumption'])
def test_failure_validator_coherence(scope, mutation):
    result = module.finite_failure(module.Refused('source'), module.new_state())
    if mutation == 'failure_code': result['failure_code'] = 'raw secret'
    elif mutation == 'stage': result['stage'] = 'launch'
    elif mutation == 'endpoint': result['last_endpoint'] = module.ENDPOINT
    elif mutation == 'count': result['application_dispatch_count'] = 1
    elif mutation == 'event': result['last_event'] = 'intent'
    elif mutation == 'observation': result['project_observation'] = module.project_observation(project())
    elif mutation == 'provider': result['provider_request_count'] = 0
    else: result['attempt_consumption'] = 'safe_to_retry'
    with pytest.raises(module.Refused): module._validate_result(result, False)
