"""Synthetic-only observer tests; native runner denies network/artifact access."""
from contextlib import nullcontext
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import observe_arv2_r298_idleness as module


@pytest.fixture
def scope(monkeypatch, tmp_path):
    # Only synthetic in-root fixtures; never inherited credentials or outputs.
    assert tmp_path.is_relative_to(module.ROOT / '.pytest_cache')
    monkeypatch.setattr(module, 'CONTROL', tmp_path / 'idleness' / 'once')
    monkeypatch.setattr(module, 'ORGANIZATION_SHA256', module.sha(b'a' * 32))
    return tmp_path


def project(value=False):
    return {'success': True, 'projects': [{'projectId': module.PROJECT,
        'organizationId': 'a' * 32, 'name': module.PROJECT_NAME, 'language': 'Py',
        'owner': True, 'public': False, 'codeRunning': value, 'collaborators': []}]}


def backtests(rows=None):
    rows = [] if rows is None else rows
    return {'success': True, 'projectId': module.PROJECT, 'count': len(rows), 'backtests': rows}


def initial():
    return {**module.new_state(), 'stage': 'credentials'}


@pytest.mark.parametrize('value,label,valid', [(True, 'boolean', True), (False, 'boolean', True),
    (None, 'null', False), ('secret-shaped-opaque', 'string', False), (0, 'number', False),
    (1, 'number', False), (0.0, 'number', False), ([], 'array', False), ({}, 'object', False)])
def test_exact_type_never_coerces_or_exposes_unexpected_value(value, label, valid):
    result = module.typed_code_running({'codeRunning': value})
    assert result == {'present': True, 'json_type': label, 'valid_boolean': valid,
        'value': value if valid else None}
    assert b'secret-shaped-opaque' not in module.canonical(result)


def test_missing_is_distinct_from_null():
    assert module.typed_code_running({}) == {'present': False, 'json_type': 'absent',
        'valid_boolean': False, 'value': None}
    assert module.typed_code_running({}) != module.typed_code_running({'codeRunning': None})


def test_hostile_code_value_never_rendered():
    class Hostile:
        def __str__(self):
            pytest.fail('opaque string conversion')
        def __repr__(self):
            pytest.fail('opaque repr conversion')
        def __bool__(self):
            pytest.fail('opaque truth conversion')
    assert module.typed_code_running({'codeRunning': Hostile()})['json_type'] == 'invalid'


@pytest.mark.parametrize('value,passed', [(False, True), (True, False), (None, False), (0, False), ('false', False)])
def test_project_diagnostic_retains_nonidle_without_relaxing_boolean(scope, value, passed):
    result = module.project_observation(project(value))
    assert result['idle_predicate_passed'] is passed


@pytest.mark.parametrize('key,value,code', [('projectId', True, 'project_id'), ('projectId', 1, 'project_id'),
    ('organizationId', 'b' * 32, 'organization'), ('organizationId', None, 'organization'),
    ('name', 'another lane', 'name'), ('language', 'C#', 'language'), ('owner', 1, 'owner'),
    ('owner', False, 'owner'), ('public', True, 'private'), ('public', None, 'private'),
    ('collaborators', None, 'collaborators'), ('collaborators', [{}, {}], 'collaborators'),
    ('collaborators', [{'owner': False}], 'collaborators'), ('collaborators', [{'owner': 1}], 'collaborators')])
def test_ownership_refusals(scope, key, value, code):
    response = project()
    response['projects'][0][key] = value
    with pytest.raises(module.Refused, match=code):
        module.project_observation(response)


@pytest.mark.parametrize('rows', [None, {}, [], [None], [{}, {}]])
def test_project_shape_refusals(rows):
    with pytest.raises(module.Refused, match='project_shape'):
        module.project_observation({'projects': rows})


def test_private_absence_preserves_existing_contract(scope):
    response = project()
    del response['projects'][0]['public']
    assert module.project_observation(response)['idle_predicate_passed'] is True


def test_exact_owner_collaborator_allowed(scope):
    response = project()
    response['projects'][0]['collaborators'] = [{'owner': True}]
    assert module.project_observation(response)['idle_predicate_passed'] is True


@pytest.mark.parametrize('status', [*module.STATUS_LABELS, 'provider secret', None, {}, 0])
def test_backtests_only_finite_status_counts(status):
    result = module.backtest_observation(backtests([{'projectId': module.PROJECT, 'status': status,
        'name': 'never retained', 'statistics': {'secret': 'never retained'}}]))
    assert result['count'] == 1 and result['zero_prior_backtests'] is False
    expected = status if type(status) is str and status in module.STATUS_LABELS else 'unknown'
    assert result['status_counts'][expected] == 1
    assert b'never retained' not in module.canonical(result)
    assert b'provider secret' not in module.canonical(result)


@pytest.mark.parametrize('response,code', [({'backtests': None}, 'backtest_shape'),
    ({'backtests': [{}] * 129}, 'backtest_shape'), ({'backtests': [None]}, 'backtest_shape'),
    ({'backtests': [], 'count': True}, 'backtest_count'), ({'backtests': [], 'count': 1}, 'backtest_count'),
    ({'backtests': [], 'projectId': 1}, 'backtest_project'),
    ({'backtests': [{'projectId': True}]}, 'backtest_project')])
def test_backtests_shape_refuses(response, code):
    with pytest.raises(module.Refused, match=code):
        module.backtest_observation(response)


def test_ordered_pair_intents_precede_dispatch_and_no_rows_returned(scope):
    events, state = [], initial()
    def request(endpoint, payload):
        assert events[-1][0].endswith('-intent.json')
        events.append((endpoint, copy.deepcopy(payload)))
        return project(True) if endpoint == 'projects/read' else backtests()
    result = module.observe(request, lambda name, value: events.append((name, value)), state, float('inf'))
    assert [event[0] for event in events] == ['project-intent.json', 'projects/read',
        'project-observation.json', 'backtests-intent.json', 'backtests/list', 'backtests-observation.json']
    assert events[4][1] == {'projectId': module.PROJECT, 'includeStatistics': False}
    assert result['application_dispatch_count'] == 2 and result['provider_request_count'] is None
    assert result['project_observation']['code_running']['value'] is True
    assert result['backtest_observation']['zero_prior_backtests'] is True
    assert b'organizationId' not in module.canonical(result)


def test_observer_state_cannot_be_reused(scope):
    state = initial()
    request = lambda endpoint, payload: project() if endpoint == 'projects/read' else backtests()
    module.observe(request, lambda *_: None, state, float('inf'))
    with pytest.raises(module.Refused, match='dispatch'):
        module.observe(lambda *_: pytest.fail('replayed'), lambda *_: None, state, float('inf'))


def test_failed_intent_prevents_dispatch(scope):
    state = initial()
    def write(*_):
        raise module.Refused('control')
    with pytest.raises(module.Refused, match='control'):
        module.observe(lambda *_: pytest.fail('request after intent failure'), write, state, float('inf'))
    assert state['application_dispatch_count'] == 0 and state['last_event'] == 'intent'


@pytest.mark.parametrize('response,code', [(None, 'response_shape'), ({'success': False}, 'response_refused'),
    ({'success': 1}, 'response_refused'), ({'success': True, 'extra': 'x' * (1024 * 1024)}, 'bound'),
    ({'success': True, 'extra': float('nan')}, 'json')])
def test_bad_response_has_finite_failure_and_no_second_dispatch(scope, response, code):
    state, calls = initial(), []
    def request(*_):
        calls.append(1)
        return response
    with pytest.raises(module.Refused, match=code):
        module.observe(request, lambda *_: None, state, float('inf'))
    assert len(calls) == 1 and state['application_dispatch_count'] == 1


def test_expired_deadline_prevents_intent_or_contact(scope):
    with pytest.raises(module.Refused, match='deadline'):
        module.observe(lambda *_: pytest.fail('contact'), lambda *_: pytest.fail('write'), initial(), 0)


def test_late_second_failure_retains_project_observation(scope):
    state = initial()
    def request(endpoint, payload):
        if endpoint == 'projects/read':
            return project(True)
        raise RuntimeError('raw secret')
    with pytest.raises(RuntimeError) as caught:
        module.observe(request, lambda *_: None, state, float('inf'))
    value = module.finite_failure(caught.value, state)
    assert value['project_observation']['code_running']['value'] is True
    assert value['application_dispatch_count'] == 2 and value['last_endpoint'] == 'backtests/list'
    assert value['failure_code'] == 'unknown_exception' and b'raw secret' not in module.canonical(value)


@pytest.mark.parametrize('error,code', [(module.Refused('owner'), 'owner'),
    (module.Refused('unregistered private'), 'unknown_exception'),
    (ValueError('owner'), 'unknown_exception'), (KeyboardInterrupt(), 'unknown_exception')])
def test_exact_failure_type_allowlist(error, code):
    assert module.finite_failure(error, module.new_state())['failure_code'] == code


def test_store_claim_is_exclusive_and_persists(scope):
    with module.Store() as store:
        pin = store.write('claim.json', {'claim': True})
        raw = (module.CONTROL / 'claim.json').read_bytes()
        assert pin == {'sha256': module.sha(raw), 'byte_count': len(raw)}
        assert (module.CONTROL / 'claim.json').stat().st_mode & 0o777 == 0o600
    with pytest.raises(module.Refused, match='claim'):
        module.Store()
    assert (module.CONTROL / 'claim.json').read_bytes() == raw


@pytest.mark.parametrize('name', ['../bad.json', 'bad.txt', '', 'UPPER.json'])
def test_store_name_bound(scope, name):
    with module.Store() as store:
        with pytest.raises(module.Refused, match='control'):
            store.write(name, {})


def test_store_duplicate_and_foreign_entry_refuse(scope):
    with module.Store() as store:
        store.write('claim.json', {'claim': True})
        with pytest.raises(module.Refused, match='control'):
            store.write('claim.json', {'claim': False})
        (module.CONTROL / 'foreign').write_bytes(b'x')
        with pytest.raises(module.Refused, match='control_changed'):
            store.verify()


@pytest.mark.parametrize('mutation', ['bytes', 'mode', 'replace', 'directory'])
def test_store_held_named_changes_refuse(scope, mutation):
    with module.Store() as store:
        store.write('claim.json', {'claim': True})
        target = module.CONTROL / 'claim.json'
        if mutation == 'bytes':
            target.write_bytes(b'not the same')
        elif mutation == 'mode':
            target.chmod(0o644)
        elif mutation == 'replace':
            target.rename(module.CONTROL / 'moved.json')
            target.write_bytes(b'new')
        else:
            module.CONTROL.rename(module.CONTROL.with_name('moved'))
            module.CONTROL.mkdir(mode=0o700)
        with pytest.raises(module.Refused, match='control_changed'):
            store.verify()


def test_store_symlink_parent_refuses(scope):
    elsewhere = scope / 'elsewhere'
    elsewhere.mkdir()
    module.CONTROL.parent.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(OSError):
        module.Store()
    assert list(elsewhere.iterdir()) == []


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
            return project(True) if endpoint == 'projects/read' else backtests()
        return SimpleNamespace(request=request)
    monkeypatch.setattr(environment, 'guarded_client', client)
    return SimpleNamespace(expected_head='a' * 40, caller_sha256='b' * 64), calls


def test_cli_success_is_observation_not_readiness(fake_run, capsys):
    args, calls = fake_run
    assert module.run(args) == 0
    raw = capsys.readouterr().out.encode('ascii')
    value = json.loads(raw)
    assert module.canonical(value) == raw and len(raw) <= module.MAX_OUTPUT
    assert value['observation_completed'] is True
    assert module.validate_output(raw, 0, args) == value
    assert all(value[key] is False for key in module.FALSE_FLAGS)
    assert calls == ['client', 'projects/read', 'backtests/list']
    report = (module.CONTROL / 'report.json').read_bytes()
    assert value['report'] == {'sha256': module.sha(report), 'byte_count': len(report)}
    assert len(list(module.CONTROL.iterdir())) == 6


def test_duplicate_cli_claim_blocks_credentials(fake_run, capsys):
    args, calls = fake_run
    assert module.run(args) == 0
    capsys.readouterr()
    assert module.run(args) == 2
    value = json.loads(capsys.readouterr().out)
    assert value['failure_code'] == 'claim'
    assert calls == ['client', 'projects/read', 'backtests/list']


@pytest.mark.parametrize('stage', ['postflight', 'report'])
def test_late_failure_has_nonzero_and_finite_preserved_evidence(fake_run, monkeypatch, capsys, stage):
    args, _ = fake_run
    if stage == 'postflight':
        count = []
        def preflight(*_):
            count.append(1)
            if len(count) == 2:
                raise module.Refused('source')
        monkeypatch.setattr(module, '_preflight', preflight)
    else:
        original = module.Store.write
        def write(self, name, value):
            result = original(self, name, value)
            if name == 'report.json':
                raise module.Refused('control_changed')
            return result
        monkeypatch.setattr(module.Store, 'write', write)
    assert module.run(args) == 2
    value = json.loads(capsys.readouterr().out)
    assert value['observation_completed'] is False and value['stage'] == stage
    assert value['application_dispatch_count'] == 2
    assert value['project_observation']['code_running']['value'] is True
    assert json.loads((module.CONTROL / 'failure.json').read_bytes()) == value
    assert module.validate_failure_output(module.canonical(value), 2) == value
    if stage == 'report':
        assert json.loads((module.CONTROL / 'report.json').read_bytes())['observation_completed'] is True


def test_preflight_rejects_pytest_without_control_or_credentials(scope):
    with pytest.raises(module.Refused, match='context'):
        module._preflight(SimpleNamespace(expected_head='a' * 40, caller_sha256='b' * 64), float('inf'))
    assert not module.CONTROL.exists()


def test_profile_is_readonly_finite_scope():
    profile = module.profile_record()
    assert profile['endpoints'] == ['projects/read', 'backtests/list']
    assert profile['max_application_dispatches'] == 2 and profile['deadline_seconds'] == 60
    assert profile['before_measurement_available'] is False and profile['causal_diagnosis'] is False
    assert profile['actual_exit_zero_required_externally'] is True
    assert profile['a1_a2_a3_remain_spent'] is True
    assert len(profile['source_pins']) == 5
    assert all(profile[key] is False for key in module.FALSE_FLAGS)


def test_no_operational_code_on_import():
    assert 'research.analyst_revisions_v2_qc.newrule_comparison_submission' not in module.__dict__
    assert 'client' not in module.__dict__


@pytest.mark.parametrize('exit_code', [2, None, True, False, '0', -9])
def test_external_validator_requires_actual_integer_exit_zero(fake_run, capsys, exit_code):
    args, _ = fake_run
    assert module.run(args) == 0
    raw = capsys.readouterr().out.encode('ascii')
    with pytest.raises(module.Refused, match='bound'):
        module.validate_output(raw, exit_code, args)


@pytest.mark.parametrize('changed_key', ['sha256', 'byte_count'])
def test_external_report_pin_binds_reconstructed_canonical_bytes(fake_run, capsys, changed_key):
    args, _ = fake_run
    assert module.run(args) == 0
    value = json.loads(capsys.readouterr().out)
    if changed_key == 'sha256':
        value['report'][changed_key] = 'c' * 64
    else:
        value['report'][changed_key] += 1
    with pytest.raises(module.Refused, match='response_shape'):
        module.validate_output(module.canonical(value), 0, args)


@pytest.mark.parametrize('mutation', ['extra', 'flag', 'head', 'self', 'profile', 'project', 'report_size',
    'report_hash', 'stage', 'count', 'provider', 'endpoint', 'event', 'field_type', 'field_value',
    'field_presence', 'idle', 'backtest_count', 'status_sum', 'status_extra', 'zero', 'newline', 'duplicate'])
def test_external_validator_rejects_malformed_success(fake_run, capsys, mutation):
    args, _ = fake_run
    assert module.run(args) == 0
    raw = capsys.readouterr().out.encode('ascii')
    value = json.loads(raw)
    result = value['result']
    field = result['project_observation']['code_running']
    if mutation == 'extra': value['secret'] = 'not allowed'
    elif mutation == 'flag': value['formal_forward_ready'] = True
    elif mutation == 'head': value['expected_head'] = 'c' * 40
    elif mutation == 'self': value['caller_sha256'] = 'c' * 64
    elif mutation == 'profile': value['profile_sha256'] = 'c' * 64
    elif mutation == 'project': value['project_id'] = True
    elif mutation == 'report_size': value['report']['byte_count'] = True
    elif mutation == 'report_hash': value['report']['sha256'] = 'bad'
    elif mutation == 'stage': result['stage'] = 'launch'
    elif mutation == 'count': result['application_dispatch_count'] = True
    elif mutation == 'provider': result['provider_request_count'] = 0
    elif mutation == 'endpoint': result['last_endpoint'] = 'backtests/create'
    elif mutation == 'event': result['last_event'] = 'intent'
    elif mutation == 'field_type': field['json_type'] = 'secret'
    elif mutation == 'field_value': field['value'] = 1
    elif mutation == 'field_presence': field['present'] = False
    elif mutation == 'idle': result['project_observation']['idle_predicate_passed'] = True
    elif mutation == 'backtest_count': result['backtest_observation']['count'] = True
    elif mutation == 'status_sum': result['backtest_observation']['status_counts']['unknown'] = 1
    elif mutation == 'status_extra': result['backtest_observation']['status_counts']['private'] = 0
    elif mutation == 'zero': result['backtest_observation']['zero_prior_backtests'] = False
    changed = module.canonical(value)
    if mutation == 'newline': changed += b'\n'
    elif mutation == 'duplicate': changed = changed.replace(b'"schema":', b'"schema":"duplicate","schema":', 1)
    with pytest.raises(module.Refused):
        module.validate_output(changed, 0, args)


def test_git_child_environment_excludes_credentials(monkeypatch):
    monkeypatch.setattr(module.os, 'environ', {'PATH': '/usr/bin:/bin', 'LANG': 'C',
        'QC_USER_ID': 'synthetic-id', 'QC_API_TOKEN': 'synthetic-token'})
    def run(command, **kwargs):
        assert command == ['/usr/bin/git', 'status', '--porcelain']
        assert kwargs['cwd'] == module.ROOT
        assert kwargs['env'] == {'PATH': '/usr/bin:/bin', 'LANG': 'C'}
        assert kwargs['timeout'] <= 3
        return SimpleNamespace(returncode=0, stdout=b'', stderr=b'')
    monkeypatch.setattr(module.subprocess, 'run', run)
    assert module._git(['status', '--porcelain'], float('inf')) == b''


@pytest.mark.parametrize('result', [SimpleNamespace(returncode=1, stdout=b'', stderr=b''),
    SimpleNamespace(returncode=True, stdout=b'', stderr=b''),
    SimpleNamespace(returncode=0, stdout=b'', stderr=b'private'),
    SimpleNamespace(returncode=0, stdout='text', stderr=b''),
    SimpleNamespace(returncode=0, stdout=b'xx', stderr=b'')])
def test_git_refuses_ambiguous_or_unbounded_result(monkeypatch, result):
    monkeypatch.setattr(module.subprocess, 'run', lambda *_, **__: result)
    with pytest.raises(module.Refused, match='context'):
        module._git(['status', '--porcelain'], float('inf'), 1)


@pytest.fixture
def preflight_fixture(monkeypatch):
    from scripts import arv2_newrule_execution_environment as environment
    raw = b'synthetic-self-source'
    args = SimpleNamespace(expected_head='a' * 40, caller_sha256=module.sha(raw))
    monkeypatch.setattr(module, 'sys', SimpleNamespace(modules={}, platform='darwin',
        version_info=(3, 13), executable=str(module.PYTHON), path=[str(module.ROOT)]))
    monkeypatch.setattr(module, 'os', SimpleNamespace(**{**vars(os), 'environ': {}}))
    monkeypatch.setattr(environment, '_require_environment', lambda: None)
    sources = []
    def digest(path):
        sources.append(path)
        return args.caller_sha256 if path == module.SOURCE else module.SOURCE_PINS[path.relative_to(module.ROOT).as_posix()]
    monkeypatch.setattr(module, '_source_digest', digest)
    def git(command, deadline, limit=65536):
        if command == ['rev-parse', '--show-toplevel']: return str(module.ROOT).encode()
        if command == ['branch', '--show-current']: return module.BRANCH.encode()
        if command == ['rev-parse', 'HEAD']: return args.expected_head.encode()
        if command == ['status', '--porcelain']: return b''
        if command[:2] == ['cat-file', '-s']: return str(len(raw)).encode()
        if command[:2] == ['cat-file', 'blob']: return raw
        pytest.fail('unexpected git request')
    monkeypatch.setattr(module, '_git', git)
    return args, sources


def test_preflight_checks_all_selected_sources_and_self(preflight_fixture):
    args, sources = preflight_fixture
    module._preflight(args, float('inf'))
    assert set(sources) == {module.ROOT / name for name in module.SOURCE_PINS} | {module.SOURCE}


@pytest.mark.parametrize('path', list(module.SOURCE_PINS) + ['self'])
def test_each_source_pin_is_load_bearing(preflight_fixture, monkeypatch, path):
    args, _ = preflight_fixture
    original = module._source_digest
    bad = module.SOURCE if path == 'self' else module.ROOT / path
    monkeypatch.setattr(module, '_source_digest', lambda target: '0' * 64 if target == bad else original(target))
    with pytest.raises(module.Refused, match='source'):
        module._preflight(args, float('inf'))


@pytest.mark.parametrize('command', [('rev-parse', '--show-toplevel'), ('branch', '--show-current'),
    ('rev-parse', 'HEAD'), ('status', '--porcelain'), ('cat-file', '-s'), ('cat-file', 'blob')])
def test_git_context_and_head_blob_are_load_bearing(preflight_fixture, monkeypatch, command):
    args, _ = preflight_fixture
    original = module._git
    def git(values, deadline, limit=65536):
        return b'bad' if tuple(values[:2]) == command else original(values, deadline, limit)
    monkeypatch.setattr(module, '_git', git)
    with pytest.raises(module.Refused):
        module._preflight(args, float('inf'))


@pytest.mark.parametrize('key,value', [('expected_head', 'bad'), ('expected_head', None),
    ('caller_sha256', 'bad'), ('caller_sha256', 0)])
def test_preflight_argument_shapes(preflight_fixture, key, value):
    args, _ = preflight_fixture
    setattr(args, key, value)
    with pytest.raises(module.Refused, match='arguments'):
        module._preflight(args, float('inf'))


@pytest.mark.parametrize('attribute,value', [('platform', 'win32'), ('version_info', (3, 12)),
    ('executable', '/usr/bin/python3')])
def test_host_is_exact(preflight_fixture, attribute, value):
    args, _ = preflight_fixture
    setattr(module.sys, attribute, value)
    with pytest.raises(module.Refused, match='context'):
        module._preflight(args, float('inf'))


def test_alarm_fires_and_restores_original_handler():
    previous = module.signal.getsignal(module.signal.SIGALRM)
    with pytest.raises(module.Refused, match='deadline'):
        with module.alarm(module.time.monotonic() + 0.01):
            module.time.sleep(0.05)
    assert module.signal.getsignal(module.signal.SIGALRM) == previous
    assert module.signal.getitimer(module.signal.ITIMER_REAL) == (0.0, 0.0)


def test_already_expired_alarm_does_not_change_handler():
    previous = module.signal.getsignal(module.signal.SIGALRM)
    try:
        with pytest.raises(module.Refused, match='deadline'):
            with module.alarm(0):
                pytest.fail('entered expired alarm')
        assert module.signal.getsignal(module.signal.SIGALRM) == previous
    finally:
        module.signal.signal(module.signal.SIGALRM, previous)


def test_existing_alarm_is_not_replaced():
    previous = module.signal.getsignal(module.signal.SIGALRM)
    module.signal.setitimer(module.signal.ITIMER_REAL, 30)
    try:
        with pytest.raises(module.Refused, match='context'):
            with module.alarm(module.time.monotonic() + 1):
                pytest.fail('replaced existing timer')
        assert 0 < module.signal.getitimer(module.signal.ITIMER_REAL)[0] <= 30
        assert module.signal.getsignal(module.signal.SIGALRM) == previous
    finally:
        module.signal.setitimer(module.signal.ITIMER_REAL, 0)


def test_source_digest_actual_public_fixture(scope):
    source = scope / 'source.py'
    source.write_bytes(b'synthetic only\n')
    assert module._source_digest(source) == module.sha(b'synthetic only\n')


def test_source_digest_refuses_symlink(scope):
    target = scope / 'real.py'
    target.write_bytes(b'synthetic')
    source = scope / 'link.py'
    source.symlink_to(target)
    with pytest.raises(module.Refused, match='source'):
        module._source_digest(source)


def test_source_digest_refuses_changed_named_file(scope, monkeypatch):
    source = scope / 'source.py'
    source.write_bytes(b'synthetic only\n')
    original = module.os.read
    changed = []
    def read(fd, count):
        raw = original(fd, count)
        if not changed:
            changed.append(1)
            source.rename(scope / 'old.py')
            source.write_bytes(b'synthetic only\n')
        return raw
    monkeypatch.setattr(module.os, 'read', read)
    with pytest.raises(module.Refused, match='source'):
        module._source_digest(source)


def failure_envelope(state=None):
    return {'schema': module.SCHEMA, 'project_id': module.PROJECT,
        'observation_completed': False, **module.finite_failure(module.Refused('deadline'),
            module.new_state() if state is None else state)}


@pytest.mark.parametrize('stage', ['preflight', 'claim', 'credentials'])
def test_failure_validator_accepts_finite_predispatch(stage):
    value = failure_envelope({**module.new_state(), 'stage': stage})
    assert module.validate_failure_output(module.canonical(value), 2) == value


@pytest.mark.parametrize('event,count,have_observation', [('intent', 0, False), ('intent', 1, False),
    ('response_received', 1, False), ('response_received', 1, True), ('observation_saved', 1, True)])
def test_failure_validator_accepts_project_prefix(scope, event, count, have_observation):
    state = {**module.new_state(), 'stage': 'project', 'last_endpoint': 'projects/read',
        'last_event': event, 'application_dispatch_count': count,
        'project_observation': module.project_observation(project(True)) if have_observation else None}
    value = failure_envelope(state)
    assert module.validate_failure_output(module.canonical(value), 2) == value


@pytest.mark.parametrize('event,count,have_observation', [('intent', 1, False), ('intent', 2, False),
    ('response_received', 2, False), ('response_received', 2, True), ('observation_saved', 2, True)])
def test_failure_validator_accepts_backtest_prefix(scope, event, count, have_observation):
    state = {**module.new_state(), 'stage': 'backtests', 'last_endpoint': 'backtests/list',
        'last_event': event, 'application_dispatch_count': count,
        'project_observation': module.project_observation(project(False)),
        'backtest_observation': module.backtest_observation(backtests()) if have_observation else None}
    value = failure_envelope(state)
    assert module.validate_failure_output(module.canonical(value), 2) == value


@pytest.mark.parametrize('exit_code', [0, None, True, False, '2', -9])
def test_failure_validator_requires_actual_exit_two(exit_code):
    with pytest.raises(module.Refused, match='bound'):
        module.validate_failure_output(module.canonical(failure_envelope()), exit_code)


@pytest.mark.parametrize('field,value', [('schema', 'bad'), ('project_id', True),
    ('observation_completed', True), ('failure_code', 'private raw string'), ('provider_request_count', 0),
    ('attempt_consumption', 'retry'), ('stage', 'launch'), ('application_dispatch_count', True),
    ('application_dispatch_count', 3), ('last_endpoint', 'files/create'), ('last_event', 'private'),
    ('point_in_time_proven', True), ('extra', 'private'), ('project_observation', {}),
    ('backtest_observation', {}), ('last_endpoint', 'projects/read'), ('last_event', 'intent'),
    ('stage', 'report')])
def test_failure_validator_rejects_bad_shapes_or_incoherent_prefix(field, value):
    envelope = failure_envelope()
    envelope[field] = value
    with pytest.raises(module.Refused):
        module.validate_failure_output(module.canonical(envelope), 2)


def test_failure_validator_rejects_false_backtest_zero(scope):
    state = {**module.new_state(), 'stage': 'postflight', 'last_endpoint': 'backtests/list',
        'last_event': 'observation_saved', 'application_dispatch_count': 2,
        'project_observation': module.project_observation(project(False)),
        'backtest_observation': module.backtest_observation(backtests())}
    state['backtest_observation']['zero_prior_backtests'] = False
    with pytest.raises(module.Refused):
        module.validate_failure_output(module.canonical(failure_envelope(state)), 2)


@pytest.mark.parametrize('suffix', [b'\n', b' {}', b'raw private'])
def test_failure_validator_rejects_trailing_output(suffix):
    with pytest.raises(module.Refused):
        module.validate_failure_output(module.canonical(failure_envelope()) + suffix, 2)
