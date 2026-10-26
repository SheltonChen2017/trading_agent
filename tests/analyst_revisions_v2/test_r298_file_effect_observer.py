"""Synthetic fixed-three-read R316 runtime tests; no live account/provider use.

Invoke with native network, production artifact and Keychain denial. Every
fixture and subprocess support path stays inside this lane's .pytest_cache.
"""
from contextlib import contextmanager, nullcontext
import json
import os
from pathlib import Path
import signal
import subprocess
from types import SimpleNamespace

import pytest

from scripts import observe_arv2_r298_file_effect as module


@pytest.fixture(scope='module')
def source():
    return module.expected_source()


@pytest.fixture
def scope(monkeypatch, tmp_path):
    assert tmp_path.is_relative_to(module.ROOT / '.pytest_cache')
    monkeypatch.setattr(module, 'CONTROL', tmp_path / 'records' / 'once')
    monkeypatch.setattr(module.effect.access, 'ORGANIZATION_SHA256', module.sha(b'a' * 32))
    return tmp_path


def project():
    return {'success': True, 'projects': [{'projectId': module.PROJECT,
        'organizationId': 'a' * 32, 'name': module.effect.access.PROJECT_NAME,
        'language': 'Py', 'owner': True, 'ownerId': 12345,
        'public': False, 'codeRunning': False, 'collaborators': []}]}


def dedicated():
    return {'success': True, 'projectId': module.PROJECT, 'collaborators': [
        {'owner': True, 'uid': 12345, 'permission': 'write',
            'name': 'never retain private owner', 'email': 'secret@example.invalid'}],
        'userPermissions': 'write', 'userLiveControl': False}


def response(endpoint, payload, source):
    assert 'codeSourceId' not in payload
    if endpoint == module.ENDPOINTS[0]: return project()
    if endpoint == module.ENDPOINTS[1]: return dedicated()
    assert endpoint == 'files/read' and payload == {'projectId': module.PROJECT, 'name': module.TARGET}
    return {'success': True, 'files': [{'projectId': module.PROJECT, 'name': module.TARGET,
        'content': source.decode('ascii'), 'unexposed': 'never retain response metadata'}]}


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


def test_exact_three_reads_order_scope_and_environment(client_fixture):
    _, _, _, events = client_fixture
    client = module.ReadOnlyClient()
    assert repr(client) == '<ReadOnlyR298FileEffectClient>'
    for endpoint, payload in zip(module.ENDPOINTS, module.PAYLOADS):
        assert client.request(endpoint, dict(payload)) == {'success': True}
    assert [item for item in events if type(item) is tuple] == list(zip(module.ENDPOINTS, module.PAYLOADS))
    with pytest.raises(module.Refused, match='dispatch'):
        client.request('files/read', dict(module.PAYLOADS[2]))


@pytest.mark.parametrize('endpoint,payload', [
    ('files/read', {'projectId': module.PROJECT, 'name': module.TARGET}),
    ('projects/lock/acquire', {'projectId': module.PROJECT}),
    ('projects/read', {'projectId': True}), ('projects/read', {'projectId': module.PROJECT + 1}),
    ('projects/read', {'projectId': module.PROJECT, 'codeSourceId': 'anything'}),
    ('projects/read', {'projectId': module.PROJECT, 'name': module.TARGET}),
    ('projects/read', {}), ('projects/read', []), (None, {'projectId': module.PROJECT}),
])
def test_first_dispatch_allowlist_before_transport(client_fixture, endpoint, payload):
    _, _, _, events = client_fixture
    client = module.ReadOnlyClient()
    with pytest.raises(module.Refused, match='dispatch'): client.request(endpoint, payload)
    assert not any(type(item) is tuple for item in events)


@pytest.mark.parametrize('payload', [
    {'projectId': module.PROJECT}, {'projectId': module.PROJECT, 'name': 'main.py'},
    {'projectId': module.PROJECT, 'name': module.TARGET, 'codeSourceId': 'anything'},
    {'projectId': True, 'name': module.TARGET}, {'projectId': module.PROJECT, 'name': None},
])
def test_file_read_cannot_be_broadened(client_fixture, payload):
    _, _, _, events = client_fixture
    client = module.ReadOnlyClient()
    for endpoint, value in zip(module.ENDPOINTS[:2], module.PAYLOADS[:2]): client.request(endpoint, dict(value))
    with pytest.raises(module.Refused, match='dispatch'): client.request('files/read', payload)
    assert sum(type(item) is tuple for item in events) == 2


@pytest.mark.parametrize('field,value', [('_base_url', 'https://example.invalid'),
    ('_transport', object()), ('_timeout', True), ('_timeout', 31)])
def test_selected_transport_rechecked(client_fixture, field, value):
    _, _, api, events = client_fixture
    client = module.ReadOnlyClient()
    setattr(api, field, value)
    with pytest.raises(module.Refused, match='client'): client.request(*[module.ENDPOINTS[0], module.PAYLOADS[0]])
    assert not any(type(item) is tuple for item in events)


def test_client_exact_type_refuses_subclass(client_fixture):
    old, _, api, _ = client_fixture
    class Derived(old.QuantConnectClient): pass
    api.__class__ = Derived
    with pytest.raises(module.Refused, match='client'): module.ReadOnlyClient()


def test_environment_refuses_before_credential_constructor(client_fixture, monkeypatch):
    _, environment, _, events = client_fixture
    def fail(): raise RuntimeError('secret environment detail')
    monkeypatch.setattr(environment, 'require_safe_environment', fail)
    with pytest.raises(RuntimeError): module.ReadOnlyClient()
    assert events == []


def test_ambiguous_dispatch_is_not_retried(client_fixture, monkeypatch):
    old, _, _, events = client_fixture
    client = module.ReadOnlyClient()
    def fail(*_):
        events.append('ambiguous')
        raise RuntimeError('secret transport detail')
    monkeypatch.setattr(old.QuantConnectClient, 'request', fail)
    with pytest.raises(RuntimeError): client.request(module.ENDPOINTS[0], dict(module.PAYLOADS[0]))
    with pytest.raises(module.Refused, match='dispatch'): client.request(module.ENDPOINTS[0], dict(module.PAYLOADS[0]))
    assert events.count('ambiguous') == 1


@pytest.fixture
def fake_run(scope, source, monkeypatch):
    from scripts import arv2_newrule_execution_environment as environment
    calls = []
    monkeypatch.setattr(module, '_preflight', lambda *_: None)
    monkeypatch.setattr(module, 'alarm', lambda *_: nullcontext())
    monkeypatch.setattr(module, 'expected_source', lambda: source)
    monkeypatch.setattr(environment, '_bootstrap_cli_logging', lambda: None)
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: None)
    def client():
        assert (module.CONTROL / 'claim.json').is_file()
        calls.append('client')
        def request(endpoint, payload):
            stage = ('project', 'collaborators', 'files')[module.ENDPOINTS.index(endpoint)]
            assert (module.CONTROL / (stage + '-intent.json')).is_file()
            calls.append(endpoint)
            return response(endpoint, payload, source)
        return SimpleNamespace(request=request)
    monkeypatch.setattr(module, 'ReadOnlyClient', client)
    return SimpleNamespace(expected_head='a' * 40, caller_sha256='b' * 64), calls


def output(capsys, args, actual_exit):
    captured = capsys.readouterr()
    assert captured.err == ''
    return module.validate_output(captured.out.encode('ascii'), actual_exit, args)


def test_exact_durable_claim_six_journals_report_and_finite_output(fake_run, capsys):
    args, calls = fake_run
    assert module.run(args) == 0
    value = output(capsys, args, 0)
    assert calls == ['client', *module.ENDPOINTS]
    assert value['result']['application_dispatch_count'] == 3
    assert value['result']['provider_request_count'] is None
    assert value['result']['file_observation'] == {**module.EXPECTED_SOURCE, 'classification': 'desired_source'}
    assert all(value[key] is False for key in module.FALSE_FLAGS)
    assert all(value['result'][key] is False for key in module.effect.FALSE_FLAGS)
    assert set(path.name for path in module.CONTROL.iterdir()) == module.FILE_NAMES - {'failure.json'}
    for path in module.CONTROL.iterdir():
        raw = path.read_bytes()
        assert all(secret not in raw for secret in (
            b'never retain', b'secret@example.invalid', b'organizationId', b'QC_API_TOKEN'))
    raw = (module.CONTROL / 'report.json').read_bytes()
    assert value['report'] == {'sha256': module.sha(raw), 'byte_count': len(raw)}


def test_duplicate_claim_never_recontacts(fake_run, capsys):
    args, calls = fake_run
    assert module.run(args) == 0
    capsys.readouterr()
    assert module.run(args) == 2
    value = output(capsys, args, 2)
    assert value['failure_code'] == 'claim' and value['report'] is None
    assert calls == ['client', *module.ENDPOINTS]


@pytest.mark.parametrize('stage', ['preflight', 'credentials', 'project', 'collaborators', 'files', 'postflight', 'report'])
def test_failure_and_late_positive_report_never_become_success(fake_run, source, capsys, monkeypatch, stage):
    args, _ = fake_run
    def fail(*_): raise RuntimeError('NEVER_ECHO_RAW_ERROR')
    if stage == 'preflight': monkeypatch.setattr(module, '_preflight', fail)
    elif stage == 'credentials': monkeypatch.setattr(module, 'ReadOnlyClient', fail)
    elif stage in ('project', 'collaborators', 'files'):
        def request(endpoint, payload):
            if endpoint == module.ENDPOINTS[('project', 'collaborators', 'files').index(stage)]: fail()
            return response(endpoint, payload, source)
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
    value = output(capsys, args, 2)
    assert b'NEVER_ECHO_RAW_ERROR' not in module.canonical(value)
    if stage in ('project', 'collaborators', 'files'):
        assert value['failure_code'] == 'remote_observation'
        assert value['result']['failure_code'] == 'request_ambiguous'
        assert value['result']['application_dispatch_count'] == ('project', 'collaborators', 'files').index(stage) + 1
    else:
        assert value['stage'] == stage and value['failure_code'] == 'unknown_exception'
    if stage in ('postflight', 'report'):
        assert value['result']['observation_complete'] is True
    if stage == 'report':
        assert value['report'] is None  # Eight files already exist; no ninth failure write.
        assert json.loads((module.CONTROL / 'report.json').read_bytes())['observation_completed'] is True
    with pytest.raises(module.Refused): module.validate_output(module.canonical(value), 0, args)


@pytest.mark.parametrize('name,count', [('project-intent.json', 0), ('collaborators-intent.json', 1), ('files-intent.json', 2)])
def test_journal_refusal_blocks_corresponding_dispatch(fake_run, capsys, monkeypatch, name, count):
    args, calls = fake_run
    original = module.Store.write
    def write(self, key, value):
        if key == name: raise OSError('PRIVATE_JOURNAL_ERROR')
        return original(self, key, value)
    monkeypatch.setattr(module.Store, 'write', write)
    assert module.run(args) == 2
    value = output(capsys, args, 2)
    assert value['result']['application_dispatch_count'] == count
    assert calls == ['client', *module.ENDPOINTS[:count]]
    assert b'PRIVATE_JOURNAL_ERROR' not in module.canonical(value)


def test_source_failure_precedes_claim_and_credentials(fake_run, capsys, monkeypatch):
    args, calls = fake_run
    def fail(): raise module.Refused('source')
    monkeypatch.setattr(module, 'expected_source', fail)
    assert module.run(args) == 2
    value = output(capsys, args, 2)
    assert value['failure_code'] == 'source' and calls == [] and not module.CONTROL.exists()


def test_alarm_encloses_preflight_contacts_and_persistence(fake_run, capsys, monkeypatch):
    args, _ = fake_run
    active, checked = [], []
    @contextmanager
    def bounded(deadline):
        assert 0 < deadline - module.time.monotonic() <= 90
        active.append(True)
        try:
            yield
        finally:
            active.clear()
    def preflight(*_):
        assert active == [True]
        checked.append('preflight')
    original = module.Store.write
    def write(self, name, value):
        assert active == [True]
        checked.append(name)
        return original(self, name, value)
    monkeypatch.setattr(module, 'alarm', bounded)
    monkeypatch.setattr(module, '_preflight', preflight)
    monkeypatch.setattr(module.Store, 'write', write)
    assert module.run(args) == 0
    output(capsys, args, 0)
    assert active == [] and checked.count('preflight') == 2
    assert len(checked) == 10 and checked[-1] == 'report.json'


@pytest.mark.parametrize('actual_exit', [None, True, False, '0', 1, -9])
def test_exact_actual_exit_required(fake_run, capsys, actual_exit):
    args, _ = fake_run
    assert module.run(args) == 0
    value = output(capsys, args, 0)
    with pytest.raises(module.Refused): module.validate_output(module.canonical(value), actual_exit, args)


@pytest.mark.parametrize('failed', [False, True])
@pytest.mark.parametrize('changed', ['hash', 'length', 'missing', 'head', 'self', 'profile', 'project', 'flag', 'extra'])
def test_external_envelope_and_pin_are_load_bearing(fake_run, capsys, monkeypatch, failed, changed):
    args, _ = fake_run
    if failed:
        def fail(): raise module.Refused('client')
        monkeypatch.setattr(module, 'ReadOnlyClient', fail)
    code = 2 if failed else 0
    assert module.run(args) == code
    value = output(capsys, args, code)
    if changed == 'hash': value['report']['sha256'] = 'c' * 64
    elif changed == 'length': value['report']['byte_count'] += 1
    elif changed == 'missing': value.pop('report')
    elif changed == 'head': value['expected_head'] = 'c' * 40
    elif changed == 'self': value['caller_sha256'] = 'c' * 64
    elif changed == 'profile': value['profile_sha256'] = 'c' * 64
    elif changed == 'project': value['project_id'] = True
    elif changed == 'flag': value['a7_authorized'] = True
    else: value['secret'] = 'not allowed'
    with pytest.raises(module.Refused): module.validate_output(module.canonical(value), code, args)


@pytest.mark.parametrize('suffix', [b'\n', b' ', b'trailing'])
def test_canonical_framing(fake_run, capsys, suffix):
    args, _ = fake_run
    assert module.run(args) == 0
    value = output(capsys, args, 0)
    with pytest.raises(module.Refused): module.validate_output(module.canonical(value) + suffix, 0, args)


@pytest.mark.parametrize('change', ['count', 'stage', 'endpoint', 'provider', 'expected', 'readiness', 'observation'])
def test_inner_finite_record_not_just_its_pin_validated(fake_run, capsys, change):
    args, _ = fake_run
    assert module.run(args) == 0
    value = output(capsys, args, 0)
    result = value['result']
    if change == 'count': result['application_dispatch_count'] = True
    elif change == 'stage': result['stage'] = 'project'
    elif change == 'endpoint': result['last_endpoint'] = 'files/update'
    elif change == 'provider': result['provider_request_count'] = 0
    elif change == 'expected': result['expected_source']['sha256'] = 'c' * 64
    elif change == 'readiness': result['operational_retry_authority'] = True
    else: result['file_observation'] = None
    raw = module.canonical({key: item for key, item in value.items() if key != 'report'})
    value['report'] = {'sha256': module.sha(raw), 'byte_count': len(raw)}
    with pytest.raises((module.Refused, module.effect.EffectRefused)):
        module.validate_output(module.canonical(value), 0, args)


@pytest.mark.parametrize('mutation', ['bytes', 'mode', 'replace', 'directory', 'foreign'])
def test_store_held_named_integrity(scope, mutation):
    with module.Store() as store:
        store.write('claim.json', {'synthetic': True})
        target = module.CONTROL / 'claim.json'
        if mutation == 'bytes': target.write_bytes(b'bad')
        elif mutation == 'mode': target.chmod(0o644)
        elif mutation == 'replace':
            target.rename(module.CONTROL / 'moved.json')
            target.write_bytes(b'bad')
        elif mutation == 'directory':
            module.CONTROL.rename(module.CONTROL.with_name('moved'))
            module.CONTROL.mkdir(mode=0o700)
        else: (module.CONTROL / 'foreign').write_bytes(b'bad')
        with pytest.raises(module.Refused, match='control_changed'): store.verify()


def test_store_parent_symlink_refuses(scope):
    elsewhere = scope / 'elsewhere'
    elsewhere.mkdir()
    module.CONTROL.parent.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(OSError): module.Store()
    assert list(elsewhere.iterdir()) == []


@pytest.mark.parametrize('name', ['../bad.json', 'bad.txt', '', 'UPPER.json', 'other.json'])
def test_store_names_are_fixed(scope, name):
    with module.Store() as store:
        with pytest.raises(module.Refused): store.write(name, {})


def test_store_no_duplicate_and_eight_file_bound(scope):
    with module.Store() as store:
        for name in sorted(module.FILE_NAMES - {'failure.json'}): store.write(name, {})
        with pytest.raises(module.Refused): store.write('failure.json', {})
        with pytest.raises(module.Refused): store.write('claim.json', {})


def test_pytest_cannot_operate(scope):
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
        return args.caller_sha256 if path == module.SOURCE else module.selected_pins()[path.relative_to(module.ROOT).as_posix()]
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


def test_preflight_synthetic_context(preflight_fixture):
    module._preflight(preflight_fixture, float('inf'))


@pytest.mark.parametrize('path', list(module.selected_pins()) + ['self'])
def test_each_pin_load_bearing(preflight_fixture, monkeypatch, path):
    original = module._source_digest
    target = module.SOURCE if path == 'self' else module.ROOT / path
    monkeypatch.setattr(module, '_source_digest', lambda path: '0' * 64 if path == target else original(path))
    with pytest.raises(module.Refused, match='source'): module._preflight(preflight_fixture, float('inf'))


@pytest.mark.parametrize('command', [('rev-parse', '--show-toplevel'), ('branch', '--show-current'),
    ('rev-parse', 'HEAD'), ('status', '--porcelain'), ('cat-file', '-s'), ('cat-file', 'blob')])
def test_git_context_load_bearing(preflight_fixture, monkeypatch, command):
    original = module._git
    monkeypatch.setattr(module, '_git', lambda values, deadline, limit=65536:
        b'bad' if tuple(values[:2]) == command else original(values, deadline, limit))
    with pytest.raises(module.Refused): module._preflight(preflight_fixture, float('inf'))


@pytest.mark.parametrize('key,value', [('platform', 'win32'), ('version_info', (3, 12)), ('executable', '/usr/bin/python3')])
def test_host_exact(preflight_fixture, key, value):
    setattr(module.sys, key, value)
    with pytest.raises(module.Refused, match='context'): module._preflight(preflight_fixture, float('inf'))


def test_native_alarm_expires_restores():
    previous = signal.getsignal(signal.SIGALRM)
    with pytest.raises(module.Refused, match='deadline'):
        with module.alarm(module.time.monotonic() + 0.01): module.time.sleep(0.05)
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_expected_source_exact_public_projection(source):
    assert {'byte_count': len(source), 'sha256': module.sha(source)} == module.EXPECTED_SOURCE
    assert module.EXPECTED_SOURCE['byte_count'] == 23055


@pytest.mark.parametrize('change', ['projection', 'missing', 'duplicate', 'bytes'])
def test_expected_projection_and_target_bytes_cannot_be_replaced(source, monkeypatch, change):
    from scripts import arv2_r298_recovery_evidence as evidence
    item = SimpleNamespace(project_path=module.TARGET, source_bytes=source)
    projection = SimpleNamespace(projection_sha256=module.PROJECTION_SHA256, source_files=[item])
    if change == 'projection': projection.projection_sha256 = 'a' * 64
    elif change == 'missing': projection.source_files = []
    elif change == 'duplicate': projection.source_files = [item, item]
    else: item.source_bytes = b'#'
    monkeypatch.setattr(evidence, 'reconstruct_projection', lambda: projection)
    with pytest.raises(module.Refused, match='source'): module.expected_source()


def test_pin_set_and_no_frozen_control_in_profile():
    pins = module.selected_pins()
    for relative, expected in pins.items(): assert module._source_digest(module.ROOT / relative) == expected
    assert set(module.a6.selected_pins()) <= set(pins)
    profile = module.profile_record()
    assert profile['max_application_dispatches'] == 3 and profile['deadline_seconds'] == 90
    assert profile['request_timeout_seconds'] == 30 and profile['automatic_retry'] is False
    assert profile['payloads'] == list(module.PAYLOADS)
    assert all(profile[key] is False for key in module.FALSE_FLAGS)
    assert str(module.CONTROL).endswith('/newrule_file_effect/R316-20261024-A')
    assert 'codeSourceId' not in module.canonical(profile).decode('ascii')
    assert all(profile[key] == 0 for key in ('shared_look', 'development_look', 'infrastructure_look'))


def test_imported_frozen_operational_entrypoints_not_called(monkeypatch, source):
    def fail(*_): pytest.fail('spent operational entrypoint reached')
    for name in ('Store', 'ReadOnlyClient', 'run'):
        monkeypatch.setattr(module.support, name, fail)
    monkeypatch.setattr(module.a6, 'main', fail)
    assert module.expected_source() == source
    assert module.selected_pins()


def test_invalid_binding_redaction():
    raw = module.canonical(module.binding(SimpleNamespace(expected_head='PRIVATE_HEAD', caller_sha256='PRIVATE_KEY')))
    assert b'PRIVATE_' not in raw


def test_direct_help_child_is_nonoperational(scope):
    result = subprocess.run([str(module.PYTHON), '-B', str(module.SOURCE), '--help'],
        cwd=module.ROOT, stdin=subprocess.DEVNULL, capture_output=True, timeout=5,
        env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'en_US.UTF-8',
            'TMPDIR': str(scope), 'XDG_CACHE_HOME': str(scope),
            'PYTHONPYCACHEPREFIX': str(scope / 'pycache'), 'PYTHONDONTWRITEBYTECODE': '1'})
    assert result.returncode == 0 and result.stderr == b'' and b'--expected-head' in result.stdout
    assert not module.CONTROL.exists()
