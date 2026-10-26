"""Synthetic R321 only; runner denies network, artifacts and Keychain access."""
from contextlib import nullcontext
from copy import deepcopy
import json
import os
from types import SimpleNamespace

import pytest

from scripts import observe_arv2_r298_access_mismatch as module


@pytest.fixture
def scope(monkeypatch, tmp_path):
    assert tmp_path.is_relative_to(module.ROOT / '.pytest_cache')
    monkeypatch.setattr(module, 'CONTROL', tmp_path / 'records' / 'once')
    monkeypatch.setattr(module.projection, 'ORGANIZATION_SHA256', module.sha(b'a' * 32))
    return tmp_path


def owner():
    return {'owner': True, 'uid': 12345, 'publicId': 'private-owner-id',
        'name': 'Private owner name', 'email': 'private@example.invalid',
        'permission': 'write', 'liveControl': True}


def extra():
    return {'owner': False, 'uid': None, 'name': module.projection.A5_CODE_SOURCE_ID,
        'publicId': module.projection.A5_CODE_SOURCE_ID, 'permission': 'write',
        'liveControl': True, 'private-field': 'private-content'}


def project():
    return {'success': True, 'projects': [{'projectId': module.PROJECT,
        'organizationId': 'a' * 32, 'name': module.projection.PROJECT_NAME,
        'language': 'Py', 'owner': True, 'ownerId': 12345,
        'codeRunning': False, 'collaborators': [owner(), extra()]}]}


def dedicated():
    return {'success': True, 'projectId': module.PROJECT, 'collaborators': [owner()],
        'userPermissions': 'write', 'userLiveControl': True}


def response(endpoint, payload):
    assert payload == {'projectId': module.PROJECT}
    return project() if endpoint == module.ENDPOINTS[0] else dedicated()


def completed(packet=None):
    return module.projection.observe(lambda endpoint, payload: module.response_snapshot(
        packet if packet is not None and endpoint == module.ENDPOINTS[0] else response(endpoint, payload)),
        lambda *_: None, {**module.projection.new_state(), 'stage': 'credentials'}, float('inf'))


def args():
    return SimpleNamespace(expected_head='a' * 40, caller_sha256='b' * 64)


def envelope(result, complete=True):
    value = module.report(args(), complete, result)
    raw = module.canonical(value)
    return {**value, 'report': {'sha256': module.sha(raw), 'byte_count': len(raw)}}


def repin(value):
    raw = module.canonical({key: item for key, item in value.items() if key != 'report'})
    value['report'] = {'sha256': module.sha(raw), 'byte_count': len(raw)}
    return module.canonical(value)


def test_current_evidence_has_exact_shape_not_automatic_policy(scope):
    result = completed()
    value = module.policy_comparison(result)
    row = value['project_rows'][1]
    assert row['all_a5_extra_shape_predicates'] is True
    assert all(row['a5_extra_shape_predicates'].values())
    assert row['equals_frozen_a5_row'] is False  # Synthetic row never receives production acceptance.
    assert row['equals_frozen_owner_row'] is False
    assert row['equals_historical_d3_mia_row'] is False
    raw = module.canonical(envelope(result))
    assert all(secret not in raw for secret in (b'12345', b'private-owner-id',
        b'Private owner name', b'private@example.invalid', b'private-field', b'private-content',
        module.projection.A5_CODE_SOURCE_ID.encode()))
    checked = module.validate_output(raw, 0, args())
    assert all(checked[key] is False for key in module.FALSE_FLAGS)
    assert checked['result']['provider_request_count'] is None


@pytest.mark.parametrize('key,value,predicate', [
    ('owner', None, 'owner_exact_false'), ('owner', 0, 'owner_exact_false'),
    ('owner', True, 'owner_exact_false'), ('uid', 0, 'uid_present_null'),
    ('uid', '', 'uid_present_null'), ('permission', 'read', 'permission_exact_write'),
    ('permission', None, 'permission_exact_write'), ('liveControl', False, 'live_control_exact_true'),
    ('liveControl', 1, 'live_control_exact_true'), ('name', 'Mia', 'name_equals_a5'),
    ('name', None, 'name_equals_a5'), ('publicId', 'new-private-label', 'public_id_equals_a5'),
    ('publicId', None, 'public_id_equals_a5'), ('codeSourceId', None, 'code_source_id_absent'),
    ('codeSourceId', module.projection.A5_CODE_SOURCE_ID, 'code_source_id_absent')])
def test_each_changed_shape_field_is_visible_not_reinterpreted(scope, key, value, predicate):
    packet = project()
    packet['projects'][0]['collaborators'][1][key] = value
    row = module.policy_comparison(completed(packet))['project_rows'][1]
    assert row['a5_extra_shape_predicates'][predicate] is False
    assert row['all_a5_extra_shape_predicates'] is False


@pytest.mark.parametrize('key,predicate', [('owner', 'owner_exact_false'), ('uid', 'uid_present_null'),
    ('permission', 'permission_exact_write'), ('liveControl', 'live_control_exact_true'),
    ('name', 'name_equals_a5'), ('publicId', 'public_id_equals_a5')])
def test_missing_and_null_are_not_conflated(scope, key, predicate):
    packet = project()
    del packet['projects'][0]['collaborators'][1][key]
    result = completed(packet)
    assert module.policy_comparison(result)['project_rows'][1]['a5_extra_shape_predicates'][predicate] is False
    raw = module.canonical(envelope(result))
    module.validate_output(raw, 0, args())


@pytest.mark.parametrize('row', [None, False, 3, 'private-row', [], {}])
def test_unknown_extra_representations_are_diagnostic_not_accepted(scope, row):
    packet = project()
    packet['projects'][0]['collaborators'][1] = row
    value = module.policy_comparison(completed(packet))['project_rows'][1]
    assert value['all_a5_extra_shape_predicates'] is (False if type(row) is dict else None)
    assert value['equals_frozen_a5_row'] is False


def test_comparison_pins_are_fixed_and_never_refreshed(scope, monkeypatch):
    result = completed()
    owner_hash = result['project_observation']['collaborators']['records'][0]['row_sha256']
    extra_hash = result['project_observation']['collaborators']['records'][1]['row_sha256']
    assert not module.policy_comparison(result)['project_rows'][0]['equals_frozen_owner_row']
    # Synthetic equality fixture; production constants are never rewritten on disk.
    monkeypatch.setattr(module, 'OWNER_ROW_SHA256', owner_hash)
    monkeypatch.setattr(module, 'A5_ROW_SHA256', extra_hash)
    compared = module.policy_comparison(result)
    assert compared['project_rows'][0]['equals_frozen_owner_row'] is True
    assert compared['dedicated_rows'][0]['equals_frozen_owner_row'] is True
    assert compared['project_rows'][1]['equals_frozen_a5_row'] is True
    assert all(value is False for value in module.FALSE_FLAGS.values())


@pytest.mark.parametrize('value', [[], ['private-error'], None, 'private-error', True])
def test_nonempty_or_malformed_errors_refused_without_printing(value):
    packet = {'success': True, 'errors': value}
    if value == []:
        assert module.response_snapshot(packet) == packet
    else:
        with pytest.raises(module.Refused, match='response_refused'):
            module.response_snapshot(packet)


@pytest.mark.parametrize('key,value', [('projectId', 1), ('projectId', True),
    ('projectId', str(module.PROJECT)), ('organizationId', 'a' * 32),
    ('organizationId', None)])
def test_contradictory_top_scope_refused(key, value):
    with pytest.raises(module.Refused):
        module.response_snapshot({'success': True, key: value})


@pytest.mark.parametrize('value', [None, [], True, {'success': 1}, {'success': False},
    {'success': True, 'nested': (1, 2)}, {'success': True, 'nested': float('nan')},
    {'success': True, 3: 'bad-key'}])
def test_strict_response_snapshot_refuses_non_json_or_not_success(value):
    with pytest.raises(module.Refused): module.response_snapshot(value)


def test_snapshot_copies_caller_mutation():
    source = {'success': True, 'values': [{'x': 'private'}]}
    result = module.response_snapshot(source)
    source['values'][0]['x'] = 'changed'
    assert result['values'][0]['x'] == 'private'


@pytest.mark.parametrize('key', ['QC_USER_ID', 'QC_API_TOKEN'])
@pytest.mark.parametrize('value', [None, '', ' ', '\n\t'])
def test_preclaim_credentials_guard(scope, monkeypatch, key, value):
    monkeypatch.setenv('QC_USER_ID', 'synthetic-user')
    monkeypatch.setenv('QC_API_TOKEN', 'synthetic-token')
    if value is None: monkeypatch.delenv(key)
    else: monkeypatch.setenv(key, value)
    with pytest.raises(module.Refused, match='context'): module.require_credentials_present()
    assert not module.CONTROL.exists()


def test_preclaim_credentials_guard_returns_no_values(monkeypatch):
    monkeypatch.setenv('QC_USER_ID', 'synthetic-user')
    monkeypatch.setenv('QC_API_TOKEN', 'synthetic-token')
    assert module.require_credentials_present() is None


@pytest.mark.parametrize('actual_exit', [True, False, 1, 3, -9, None, '0'])
def test_actual_exit_is_external_exact_integer(scope, actual_exit):
    with pytest.raises(module.Refused):
        module.validate_output(module.canonical(envelope(completed())), actual_exit, args())


@pytest.mark.parametrize('mutation', ['schema', 'head', 'caller', 'profile', 'project', 'completed',
    'gate', 'unknown', 'pin', 'pin_size', 'predicate', 'predicate_type', 'owner_pin',
    'a5_pin', 'mia_pin', 'extra_comparison', 'raw_secret', 'request_count', 'provider_count'])
def test_finite_output_rejects_forgery_even_when_report_rehashed(scope, mutation):
    value = envelope(completed())
    compared = value['comparison_to_frozen_policy']['project_rows'][1]
    if mutation == 'schema': value['schema'] = module.projection.SCHEMA
    elif mutation == 'head': value['expected_head'] = 'c' * 40
    elif mutation == 'caller': value['caller_sha256'] = 'c' * 64
    elif mutation == 'profile': value['profile_sha256'] = 'c' * 64
    elif mutation == 'project': value['project_id'] += 1
    elif mutation == 'completed': value['observation_completed'] = False
    elif mutation == 'gate': value['a10_authorized'] = True
    elif mutation == 'unknown': value['unexpected'] = 'private-value'
    elif mutation == 'pin': value['report']['sha256'] = 'c' * 64
    elif mutation == 'pin_size': value['report']['byte_count'] = True
    elif mutation == 'predicate': compared['a5_extra_shape_predicates']['name_equals_a5'] = False
    elif mutation == 'predicate_type': compared['a5_extra_shape_predicates']['name_equals_a5'] = 1
    elif mutation == 'owner_pin': compared['equals_frozen_owner_row'] = True
    elif mutation == 'a5_pin': compared['equals_frozen_a5_row'] = True
    elif mutation == 'mia_pin': compared['equals_historical_d3_mia_row'] = True
    elif mutation == 'extra_comparison': compared['unknown'] = 'private-value'
    elif mutation == 'raw_secret': value['result']['private'] = 'raw-value'
    elif mutation == 'request_count': value['result']['application_dispatch_count'] = 1
    else: value['result']['provider_request_count'] = 2
    raw = module.canonical(value) if mutation in ('pin', 'pin_size') else repin(value)
    with pytest.raises(module.Refused): module.validate_output(raw, 0, args())


@pytest.mark.parametrize('transform', [lambda raw: raw + b'\n', lambda raw: raw[:-1],
    lambda raw: b' ' + raw, lambda raw: b'', lambda raw: raw + b'{}',
    lambda raw: b'x' * (module.MAX_OUTPUT + 1)])
def test_output_exact_canonical_bound(scope, transform):
    with pytest.raises(module.Refused):
        module.validate_output(transform(module.canonical(envelope(completed()))), 0, args())


def test_failure_is_validated_but_never_success(scope):
    failure = module.projection.finite_failure(module.Refused('context'), module.projection.new_state())
    value = {**module.report(args(), False, failure), 'report': None}
    assert module.validate_output(module.canonical(value), 2, args())['observation_completed'] is False
    with pytest.raises(module.Refused): module.validate_output(module.canonical(value), 0, args())


@pytest.mark.parametrize('key,value', [('owner', True), ('uid', 12345),
    ('permission', 'read'), ('liveControl', False), ('name', 'different-private-name'),
    ('publicId', 'different-private-id'), ('codeSourceId', None)])
def test_known_a5_hash_cannot_attest_contradictory_shape(scope, key, value):
    packet = project()
    packet['projects'][0]['collaborators'][1][key] = value
    result = completed(packet)
    result['project_observation']['collaborators']['records'][1]['row_sha256'] = module.A5_ROW_SHA256
    result['comparison'] = module.projection.comparison(
        result['project_observation'], result['dedicated_observation'])
    # Rebuild both derived comparisons and report hash. A matching public pin
    # cannot coherently attest a different known typed shape.
    with pytest.raises(module.Refused, match='response_shape'):
        module.validate_output(module.canonical(envelope(result)), 0, args())


@pytest.mark.parametrize('key,value', [('owner', False), ('owner', 1), ('uid', None),
    ('uid', 54321), ('uid', 12345.0), ('permission', 'read'), ('liveControl', False)])
def test_known_owner_hash_cannot_attest_contradictory_shape(scope, key, value):
    packet = project()
    candidate = owner()
    candidate[key] = value
    packet['projects'][0]['collaborators'][1] = candidate
    result = completed(packet)
    result['project_observation']['collaborators']['records'][1]['row_sha256'] = module.OWNER_ROW_SHA256
    result['comparison'] = module.projection.comparison(
        result['project_observation'], result['dedicated_observation'])
    with pytest.raises(module.Refused, match='response_shape'):
        module.validate_output(module.canonical(envelope(result)), 0, args())


@pytest.mark.parametrize('pin', [module.A5_ROW_SHA256, module.OWNER_ROW_SHA256])
@pytest.mark.parametrize('row', [None, False, 'private-nonobject', []])
def test_known_row_hash_requires_object(scope, pin, row):
    packet = project()
    packet['projects'][0]['collaborators'][1] = row
    result = completed(packet)
    result['project_observation']['collaborators']['records'][1]['row_sha256'] = pin
    result['comparison'] = module.projection.comparison(
        result['project_observation'], result['dedicated_observation'])
    with pytest.raises(module.Refused, match='response_shape'):
        module.validate_output(module.canonical(envelope(result)), 0, args())


def test_known_hash_coherence_does_not_require_all_rows_match(scope):
    result = completed()
    first = result['project_observation']['collaborators']['records']
    second = result['dedicated_observation']['collaborators']['records']
    first[0]['row_sha256'] = second[0]['row_sha256'] = module.OWNER_ROW_SHA256
    first[1]['row_sha256'] = module.A5_ROW_SHA256
    result['comparison'] = module.projection.comparison(
        result['project_observation'], result['dedicated_observation'])
    module.validate_output(module.canonical(envelope(result)), 0, args())
    first[1]['row_sha256'] = 'd' * 64
    first[1]['live_control']['value'] = False
    result['comparison'] = module.projection.comparison(
        result['project_observation'], result['dedicated_observation'])
    checked = module.validate_output(module.canonical(envelope(result)), 0, args())
    assert checked['comparison_to_frozen_policy']['project_rows'][1]['equals_frozen_a5_row'] is False
    assert checked['collaborator_policy_accepted'] is False


def test_sixteen_rich_rows_fit_bound_without_raw_fields(scope):
    first, second = project(), dedicated()
    first['projects'][0]['collaborators'] = [dict(extra(), name='private-' + str(n)) for n in range(8)]
    second['collaborators'] = deepcopy(first['projects'][0]['collaborators'])
    result = module.projection.observe(lambda endpoint, _: first if endpoint == module.ENDPOINTS[0] else second,
        lambda *_: None, {**module.projection.new_state(), 'stage': 'credentials'}, float('inf'))
    raw = module.canonical(envelope(result))
    assert len(raw) <= module.MAX_OUTPUT
    assert b'private-' not in raw
    module.validate_output(raw, 0, args())


@pytest.fixture
def runnable(scope, monkeypatch):
    from scripts import arv2_newrule_execution_environment as environment
    events = []
    monkeypatch.setattr(module, '_preflight', lambda *_: events.append('preflight'))
    monkeypatch.setattr(module.projection, 'alarm', lambda _: nullcontext())
    monkeypatch.setenv('QC_USER_ID', 'synthetic-user')
    monkeypatch.setenv('QC_API_TOKEN', 'synthetic-token')
    monkeypatch.setattr(environment, '_bootstrap_cli_logging', lambda: events.append('bootstrap'))
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: events.append('environment'))
    class FakeClient:
        def __init__(self):
            assert (module.CONTROL / 'claim.json').is_file()
            events.append('client')
        def request(self, endpoint, payload):
            events.append(endpoint)
            return response(endpoint, payload)
    monkeypatch.setattr(module.projection, 'ReadOnlyClient', FakeClient)
    return events


def test_run_claim_before_client_exact_two_requests_no_old_control(runnable, capsys):
    assert module.run(args()) == 0
    checked = module.validate_output(capsys.readouterr().out.encode(), 0, args())
    assert runnable == ['preflight', 'bootstrap', 'client', *module.ENDPOINTS, 'preflight', 'environment']
    assert checked['result']['application_dispatch_count'] == 2
    assert set(path.name for path in module.CONTROL.iterdir()) == {'claim.json', 'project-intent.json',
        'project-observation.json', 'collaborators-intent.json', 'collaborators-observation.json', 'report.json'}


def test_old_operational_entrypoints_are_never_called(runnable, monkeypatch, capsys):
    def forbidden(*_, **__):
        pytest.fail('spent operational entrypoint called')
    for name in ('run', 'Store', '_preflight', 'main'):
        monkeypatch.setattr(module.projection, name, forbidden)
    assert module.run(args()) == 0
    module.validate_output(capsys.readouterr().out.encode(), 0, args())


def test_success_true_with_errors_is_refused_before_projector(runnable, monkeypatch, capsys):
    class Contradictory:
        def request(self, *_):
            packet = project()
            packet['errors'] = ['private-refusal']
            return packet
    monkeypatch.setattr(module.projection, 'ReadOnlyClient', Contradictory)
    assert module.run(args()) == 2
    raw = capsys.readouterr().out.encode()
    value = module.validate_output(raw, 2, args())
    assert value['result']['failure_code'] == 'response_refused'
    assert value['result']['application_dispatch_count'] == 1
    assert value['result']['project_observation'] is None
    assert b'private-refusal' not in raw


def test_run_preclaim_guard_is_load_bearing(runnable, monkeypatch, capsys):
    monkeypatch.delenv('QC_API_TOKEN')
    assert module.run(args()) == 2
    checked = module.validate_output(capsys.readouterr().out.encode(), 2, args())
    assert not module.CONTROL.exists()
    assert runnable == ['preflight']
    assert checked['result']['application_dispatch_count'] == 0


@pytest.mark.parametrize('endpoint', list(module.ENDPOINTS))
def test_request_refusal_consumes_dispatch_without_retry(runnable, monkeypatch, capsys, endpoint):
    class Failing:
        def request(self, current, payload):
            runnable.append(current)
            if current == endpoint: return {'success': False, 'errors': ['private-error']}
            return response(current, payload)
    monkeypatch.setattr(module.projection, 'ReadOnlyClient', Failing)
    assert module.run(args()) == 2
    output = capsys.readouterr().out.encode()
    checked = module.validate_output(output, 2, args())
    assert checked['result']['application_dispatch_count'] == module.ENDPOINTS.index(endpoint) + 1
    assert runnable.count(endpoint) == 1 and b'private-error' not in output
    assert checked['result']['failure_code'] == 'response_refused'


def test_postflight_failure_preserves_completed_metadata_not_success(runnable, monkeypatch, capsys):
    calls = []
    def preflight(*_):
        calls.append(1)
        if len(calls) == 2: raise module.Refused('source')
    monkeypatch.setattr(module, '_preflight', preflight)
    assert module.run(args()) == 2
    checked = module.validate_output(capsys.readouterr().out.encode(), 2, args())
    assert checked['result']['stage'] == 'postflight'
    assert checked['result']['application_dispatch_count'] == 2
    assert checked['result']['failure_code'] == 'source'


def test_duplicate_claim_never_reuses_old_attempt(runnable, capsys):
    assert module.run(args()) == 0
    capsys.readouterr()
    prior = tuple(runnable)
    assert module.run(args()) == 2
    checked = module.validate_output(capsys.readouterr().out.encode(), 2, args())
    assert checked['result']['failure_code'] == 'claim'
    assert runnable[len(prior):] == ['preflight', 'bootstrap']


@pytest.mark.parametrize('mutation', ['bytes', 'mode', 'replace', 'directory', 'foreign'])
def test_store_held_named_integrity(scope, mutation):
    with module.Store() as store:
        store.write('claim.json', {'synthetic': True})
        target = module.CONTROL / 'claim.json'
        if mutation == 'bytes': target.write_bytes(b'bad')
        elif mutation == 'mode': target.chmod(0o644)
        elif mutation == 'replace': target.rename(module.CONTROL / 'moved.json'); target.write_bytes(b'bad')
        elif mutation == 'directory': module.CONTROL.rename(module.CONTROL.with_name('moved')); module.CONTROL.mkdir(mode=0o700)
        else: (module.CONTROL / 'foreign').write_bytes(b'bad')
        with pytest.raises(module.Refused, match='control_changed'): store.verify()


@pytest.mark.parametrize('name', ['../bad.json', 'bad.txt', '', 'UPPER.json'])
def test_store_name_restriction(scope, name):
    with module.Store() as store:
        with pytest.raises(module.Refused): store.write(name, {})


def test_store_duplicate_bound_and_symlink(scope):
    with module.Store() as store:
        store.write('claim.json', {})
        with pytest.raises(module.Refused): store.write('claim.json', {})
        for name in ('a', 'b', 'c', 'd', 'e', 'f', 'g'): store.write(name + '.json', {})
        with pytest.raises(module.Refused): store.write('h.json', {})
    with pytest.raises(module.Refused, match='claim'): module.Store()


def test_store_parent_symlink_refused(scope):
    elsewhere = scope / 'elsewhere'
    elsewhere.mkdir()
    module.CONTROL.parent.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(OSError): module.Store()
    assert list(elsewhere.iterdir()) == []


@pytest.fixture
def preflight_fixture(monkeypatch):
    from scripts import arv2_newrule_execution_environment as environment
    raw = b'synthetic public source'
    bound = SimpleNamespace(expected_head='a' * 40, caller_sha256=module.sha(raw))
    monkeypatch.setattr(module, 'sys', SimpleNamespace(modules={}, platform='darwin',
        version_info=(3, 13), executable=str(module.PYTHON)))
    monkeypatch.setattr(module, 'os', SimpleNamespace(**{**vars(os), 'environ': {}}))
    monkeypatch.setattr(environment, '_require_environment', lambda: None)
    monkeypatch.setattr(module.projection, '_source_digest', lambda path:
        bound.caller_sha256 if path == module.SOURCE else module.SOURCE_PINS[path.relative_to(module.ROOT).as_posix()])
    def git(command, deadline, limit=65536):
        if command == ['rev-parse', '--show-toplevel']: return str(module.ROOT).encode()
        if command == ['branch', '--show-current']: return module.BRANCH.encode()
        if command == ['rev-parse', 'HEAD']: return bound.expected_head.encode()
        if command == ['status', '--porcelain']: return b''
        if command[:2] == ['cat-file', '-s']: return str(len(raw)).encode()
        if command[:2] == ['cat-file', 'blob']: return raw
        pytest.fail('unexpected git')
    monkeypatch.setattr(module, '_git', git)
    return bound


def test_preflight_synthetic_exact_context(preflight_fixture):
    module._preflight(preflight_fixture, float('inf'))


@pytest.mark.parametrize('path', list(module.SOURCE_PINS) + ['self'])
def test_each_selected_pin_load_bearing(preflight_fixture, monkeypatch, path):
    original = module.projection._source_digest
    bad = module.SOURCE if path == 'self' else module.ROOT / path
    monkeypatch.setattr(module.projection, '_source_digest', lambda target:
        '0' * 64 if target == bad else original(target))
    with pytest.raises(module.Refused, match='source'): module._preflight(preflight_fixture, float('inf'))


@pytest.mark.parametrize('command', [('rev-parse', '--show-toplevel'), ('branch', '--show-current'),
    ('rev-parse', 'HEAD'), ('status', '--porcelain'), ('cat-file', '-s'), ('cat-file', 'blob')])
def test_git_context_checks_load_bearing(preflight_fixture, monkeypatch, command):
    original = module._git
    monkeypatch.setattr(module, '_git', lambda values, deadline, limit=65536:
        b'bad' if tuple(values[:2]) == command else original(values, deadline, limit))
    with pytest.raises(module.Refused): module._preflight(preflight_fixture, float('inf'))


@pytest.mark.parametrize('key,value', [('platform', 'win32'), ('version_info', (3, 12)),
    ('executable', '/usr/bin/python3')])
def test_exact_host(preflight_fixture, key, value):
    setattr(module.sys, key, value)
    with pytest.raises(module.Refused, match='context'): module._preflight(preflight_fixture, float('inf'))


def test_pytest_preflight_refuses_before_control(scope):
    with pytest.raises(module.Refused, match='context'): module._preflight(args(), float('inf'))
    assert not module.CONTROL.exists()


def test_profile_new_control_readonly_fixed_pins():
    value = module.profile_record()
    assert value['endpoints'] == list(module.ENDPOINTS)
    assert value['max_application_dispatches'] == 2 and value['deadline_seconds'] == 60
    assert value['prior_observers_and_a1_through_a9_remain_spent'] is True
    assert value['preclaim_credential_presence_required'] is True
    assert value['automatic_retry'] is False and len(module.SOURCE_PINS) == 11
    assert value['owner_row_sha256'] == module.policy.OWNER_ROW_SHA256
    assert value['a5_row_sha256'] == module.policy.A5_ROW_SHA256
    assert module.CONTROL != module.projection.CONTROL
    assert all(value[key] is False for key in module.FALSE_FLAGS)
    assert all(value[key] == 0 for key in ('shared_look', 'development_look', 'infrastructure_look'))


def test_invalid_bindings_never_echo():
    value = module.binding(SimpleNamespace(expected_head='private input', caller_sha256='secret'))
    assert value['expected_head'] is None and value['caller_sha256'] is None
    assert b'private input' not in module.canonical(value) and b'secret' not in module.canonical(value)
