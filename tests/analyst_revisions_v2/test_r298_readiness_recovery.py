"""Synthetic A10 readiness checks; native network/private artifact denial required."""
import ast
import copy
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
import pytest
from scripts import run_arv2_r298_readiness_recovery as m
from scripts import arv2_r298_recovery_evidence as evidence
from scripts import arv2_newrule_execution_environment as environment
REAL_OWNER_CLIENT = m.OwnerClient
PUBLIC_ROOT = m.ROOT

@pytest.fixture(autouse=True)
def operational_tripwire(monkeypatch):
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
    hits = []
    def refuse(*args, **kwargs):
        hits.append('operational')
        raise AssertionError('unreplaced private/operational seam')
    for module, names in ((m.a3, ('main', '_execute', '_recover', '_worker', '_child', '_workflow', '_reconciliation')),
        (m.a6, ('main', '_execute', '_recover', '_worker', '_child', '_workflow')),
        (evidence, ('collect_documents',)), (m.previous, ('_admission',)),
        (environment, ('guarded_client',)), (old, ('_client',))):
        for name in names:
            monkeypatch.setattr(module, name, refuse)
    yield
    assert hits == []


@pytest.fixture
def args():
    return SimpleNamespace(operation='recover', expected_head='a' * 40,
        caller_sha256='b' * 64, control_fd=None)


@pytest.fixture
def leaf(tmp_path, monkeypatch):
    root = tmp_path / 'root'
    (root / 'artifacts').mkdir(parents=True)
    monkeypatch.setattr(m, 'ROOT', root)
    monkeypatch.setattr(m, 'CONTROL', root / 'artifacts' / 'access-recovery' / 'fixed')
    return m.CONTROL


def test_store_own_path_inheritance_and_exclusive_claim(leaf):
    old = m.a3.CONTROL
    assert m.Store.read is m.a3.Store.read and m.Store.write is m.a3.Store.write
    assert m.Store.__init__ is not m.a3.Store.__init__ and m.Store.verify is not m.a3.Store.verify
    with m.Store(create=True) as store:
        pin = store.write('claim.json', {'a': 1})
        raw, value = store.read('claim.json')
        assert value == {'a': 1} and pin == {'byte_count': len(raw), 'sha256': m.sha(raw)}
        with m.Store(inherited=store.fd) as child:
            child.write('child.json', {})
        with pytest.raises(FileExistsError):
            store.write('claim.json', {})
        with pytest.raises(m.Refused):
            m.Store(inherited=1)
    with pytest.raises(m.Refused, match='claim'):
        m.Store(create=True)
    assert m.a3.CONTROL == old and (leaf / 'claim.json').read_bytes() == b'{"a":1}\n'


@pytest.mark.parametrize('mutation', ['mode', 'hardlink', 'symlink', 'noncanonical', 'duplicate', 'directory', 'replace_leaf'])
def test_own_store_refuses_tampering(leaf, mutation):
    with m.Store(create=True) as store:
        store.write('one.json', {'a': 1})
        path = leaf / 'one.json'
        if mutation == 'mode':
            path.chmod(0o644)
        elif mutation == 'hardlink':
            os.link(path, leaf / 'two.json')
        elif mutation == 'symlink':
            path.rename(leaf / 'two.json')
            path.symlink_to('two.json')
        elif mutation == 'noncanonical':
            path.write_bytes(b'{ "a": 1 }\n')
        elif mutation == 'duplicate':
            path.write_bytes(b'{"a":1,"a":2}\n')
        elif mutation == 'replace_leaf':
            leaf.rename(leaf.with_name('retained'))
            leaf.mkdir(mode=0o700)
        else:
            path.unlink()
            path.mkdir()
        with pytest.raises((m.Refused, m.previous.Refused, OSError)):
            store.read('one.json')


@pytest.mark.parametrize('name', ['../a.json', 'a/b.json', 'a', '', 'a.json\n'])
def test_own_store_names(leaf, name):
    with m.Store(create=True) as store:
        with pytest.raises(m.Refused):
            store.write(name, {})


@pytest.mark.parametrize('value,kind,boolean', [(False, 'boolean', False), (True, 'boolean', True),
    (None, 'null', None), (0, 'integer', None), (1, 'integer', None), (0.0, 'number', None),
    ('sensitive synthetic value', 'string', None), ([], 'array', None), ({'x': 'private'}, 'object', None)])
def test_typed_observation_never_coerces_or_emits_unexpected_value(value, kind, boolean):
    result = m.code_running_observation({'projects': [{'projectId': m.PROJECT, 'codeRunning': value}]})
    assert result == {'present': True, 'kind': kind, 'boolean_value': boolean}
    m._validate_code_running(result)
    assert 'sensitive' not in repr(result) and 'private' not in repr(result)


def test_missing_is_distinct_from_null_and_false():
    result = m.code_running_observation({'projects': [{'projectId': m.PROJECT}]})
    assert result == {'present': False, 'kind': 'missing', 'boolean_value': None}
    m._validate_code_running(result)


@pytest.mark.parametrize('value', [[], {}, {'present': False, 'kind': 'boolean', 'boolean_value': False},
    {'present': True, 'kind': 'boolean', 'boolean_value': 0},
    {'present': True, 'kind': 'null', 'boolean_value': False},
    {'present': True, 'kind': 'missing', 'boolean_value': None}])
def test_typed_observation_strict_schema(value):
    with pytest.raises(m.Refused):
        m._validate_code_running(value)


@pytest.mark.parametrize('rows', [None, [], [{}, {}], [False], [{'projectId': True}], [{'projectId': 1}]])
def test_typed_observation_requires_exact_project(rows):
    with pytest.raises(m.remote.RecoveryError):
        m.code_running_observation({'projects': rows})


@pytest.fixture
def cloud(monkeypatch):
    organization = 'a' * 32
    pin = m.sha(organization.encode('ascii'))
    monkeypatch.setattr(m.remote, 'ORGANIZATION_SHA256', pin)
    monkeypatch.setattr(m.remote.frozen, 'ORGANIZATION_SHA256', pin)
    monkeypatch.setattr(m.remote.access, 'ORGANIZATION_SHA256', pin)
    monkeypatch.setattr(m.remote.diagnostic.projection, 'ORGANIZATION_SHA256', pin)
    sources = {name: ('# synthetic exact ' + name + '\n').encode('ascii') for name in m.remote.SOURCE_NAMES}
    synthetic_inventory = {'project_id': m.PROJECT, 'projection_sha256': m.remote.PROJECTION_SHA256,
        'files': [{'name': name, 'byte_count': len(raw), 'sha256': m.sha(raw)}
            for name, raw in sorted(sources.items())]}
    monkeypatch.setattr(m.remote, 'SOURCE_MANIFEST_SHA256', m.sha(m.canonical(synthetic_inventory)))
    entries = tuple(SimpleNamespace(project_path=name, source_bytes=raw) for name, raw in sorted(sources.items()))
    manifest = [{'project_path': item.project_path, 'byte_count': len(item.source_bytes),
        'content_sha256': m.sha(item.source_bytes)} for item in entries]
    projection = SimpleNamespace(projection_sha256=m.remote.PROJECTION_SHA256, source_files=entries,
        to_record=lambda: {'candidate_id': m.remote.PROJECTION_CANDIDATE_ID, 'source_files': manifest})
    state = SimpleNamespace(sources=sources, projection=projection, calls=[], events=[], observations=[],
        files={'main.py': m.remote.frozen.frozen.DEFAULT_MAIN.decode('ascii'),
            'accepted_risk_order_level_input_runtime.py': '#',
            'accepted_risk_order_level_core.py': sources['accepted_risk_order_level_core.py'].decode('ascii'),
            'accepted_risk_order_level_forced_exit.py': sources['accepted_risk_order_level_forced_exit.py'].decode('ascii')},
        prior=[{'projectId': m.PROJECT, 'backtestId': m.remote.MANUAL_BACKTEST_ID,
            'name': m.remote.MANUAL_BACKTEST_NAME, 'status': 'Completed.'}], busy=False, compile_state='BuildSuccess', mutation=None)
    state.project = {'projectId': m.PROJECT, 'organizationId': organization,
        'name': m.remote.PROJECT_NAME, 'language': 'Py', 'owner': True,
        'codeRunning': False, 'ownerId': 123,
        'collaborators': [{'owner': True, 'uid': 123, 'publicId': 'synthetic-owner',
            'name': 'Synthetic Owner', 'permission': 'write', 'liveControl': True}]}
    state.dedicated = {'collaborators': copy.deepcopy(state.project['collaborators']),
        'userPermissions': 'write', 'userLiveControl': True}
    monkeypatch.setattr(m.remote.access, 'OWNER_ROW_SHA256',
        m.sha(m.canonical(state.dedicated['collaborators'][0])))
    extra = {'owner': False, 'uid': None, 'name': m.remote.CODE_SOURCE_ID,
        'publicId': m.remote.CODE_SOURCE_ID, 'permission': 'write', 'liveControl': True,
        'syntheticUnreported': 'exact synthetic metadata'}
    monkeypatch.setattr(m.remote.access, 'A5_ROW_SHA256', m.sha(m.canonical(extra)))
    state.project['collaborators'].append(extra)
    monkeypatch.setattr(m.remote.diagnostic, 'OWNER_ROW_SHA256', m.remote.access.OWNER_ROW_SHA256)
    monkeypatch.setattr(m.remote.diagnostic, 'A5_ROW_SHA256', m.remote.access.A5_ROW_SHA256)
    def journal(marker, event):
        assert not any(old == marker and before['event'] == event['event'] for old, before in state.events)
        state.events.append((marker, copy.deepcopy(event)))
    def request(endpoint, payload):
        assert state.events[-1][1] == {'event': 'intent', 'endpoint': endpoint, 'sha256': m.sha(m.canonical(payload))}
        state.calls.append((endpoint, copy.deepcopy(payload)))
        if endpoint == 'projects/read':
            result = {'projects': [copy.deepcopy(state.project)]}
        elif endpoint == 'projects/collaboration/read':
            result = copy.deepcopy(state.dedicated)
        elif endpoint == 'projects/collaboration/lock/acquire':
            result = {}
        elif endpoint == 'backtests/list':
            result = {'backtests': copy.deepcopy(state.prior), 'count': len(state.prior), 'projectId': m.PROJECT}
        elif endpoint == 'files/read':
            result = {'files': [{'projectId': m.PROJECT, 'name': name, 'content': raw} for name, raw in state.files.items()]}
        elif endpoint in ('files/create', 'files/update'):
            assert (payload['name'] in state.files) == (endpoint == 'files/update')
            state.files[payload['name']] = payload['content']
            result = {}
        elif endpoint == 'compile/create':
            result = {'projectId': m.PROJECT, 'compileId': 'compile-a10'}
        elif endpoint == 'compile/read':
            result = {'projectId': m.PROJECT, 'compileId': payload['compileId'], 'state': state.compile_state}
        elif endpoint == 'projects/nodes/read':
            result = {'autoSelectNode': True, 'nodes': {'backtest': [{'active': False, 'busy': state.busy}]}}
        elif endpoint == 'backtests/create':
            row = {'projectId': m.PROJECT, 'name': payload['backtestName'], 'backtestId': 'run-a10', 'status': 'In Queue...'}
            state.prior.append(copy.deepcopy(row))
            result = {'backtest': row}
        else:
            pytest.fail('unexpected endpoint')
        result['success'] = True
        if state.mutation:
            state.mutation(endpoint, payload, result)
        return result
    def observe(marker, value):
        assert state.events[-1][0] == marker and state.events[-1][1]['event'] == 'observed'
        assert state.calls[-1][0] == 'projects/read'
        state.observations.append((marker, copy.deepcopy(value)))
    state.request, state.journal, state.observe = request, journal, observe
    state.access_observations = []
    state.runner = m.remote.OwnerRecovery(projection, pin, request, journal, observe, lambda marker, packet: state.access_observations.append((marker, packet)))
    return state


@pytest.fixture
def workflow(monkeypatch, args, leaf, cloud):
    monkeypatch.setenv('QC_USER_ID', 'synthetic-user')
    monkeypatch.setenv('QC_API_TOKEN', 'synthetic-not-a-secret')
    state = SimpleNamespace(now=0, events=[], sleeps=[], child_error=None)
    monkeypatch.setattr(m.time, 'monotonic', lambda: state.now)
    def sleep(seconds):
        state.sleeps.append(seconds)
        state.now += seconds
    monkeypatch.setattr(m.time, 'sleep', sleep)
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: None)
    monkeypatch.setattr(m, 'OwnerClient', lambda sink: SimpleNamespace(request=cloud.request, boundary_code=None))
    monkeypatch.setattr(evidence, 'reconstruct_projection', lambda: cloud.projection)
    def child(supplied, store, deadline, operation):
        assert store.read('claim.json')[1] == m.claim(args)
        state.events.append(operation)
        store.write(operation + '-start.json', {})
        if state.child_error == operation:
            raise m.Refused('input_admission')
        return {'admission_authenticated': True, 'projection_sha256': m.remote.PROJECTION_SHA256}
    monkeypatch.setattr(m, '_child', child)
    # The pure cloud fixture expects its own journal, while this caller owns a
    # durable journal; retain the cloud model without that fixture assertion.
    original_request = cloud.request
    def request(endpoint, payload):
        cloud.events.append(('injected', {'event': 'intent', 'endpoint': endpoint,
            'sha256': m.sha(m.canonical(payload))}))
        return original_request(endpoint, payload)
    monkeypatch.setattr(m, 'OwnerClient', lambda sink: SimpleNamespace(request=request, boundary_code=None))
    monkeypatch.setattr(m, '_preflight', lambda *_: None)
    state.cloud = cloud
    return state


@pytest.mark.parametrize('operation', m.WORKERS)
def test_native_worker_fresh_claim_and_once_only_stage(args, leaf, monkeypatch, operation):
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: None)
    calls = []
    monkeypatch.setattr(m.previous, '_admission', lambda projected, deadline: calls.append(projected.projection_sha256))
    args.operation = operation
    with m.Store(create=True) as store:
        store.write('claim.json', m.claim(args))
        args.control_fd = store.fd
        result = m._worker(args, time.monotonic() + 20)
        assert result == {'admission_authenticated': True, 'projection_sha256': m.remote.PROJECTION_SHA256}
        with pytest.raises(FileExistsError):
            m._worker(args, time.monotonic() + 20)
    assert calls == [m.remote.PROJECTION_SHA256]


def test_worker_refuses_mismatched_claim_before_private_admission(args, leaf, monkeypatch):
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: None)
    args.operation = m.WORKERS[0]
    with m.Store(create=True) as store:
        store.write('claim.json', {})
        args.control_fd = store.fd
        with pytest.raises(m.Refused, match='claim'):
            m._worker(args, time.monotonic() + 10)


@pytest.fixture
def preflight(args, monkeypatch):
    raw = b'public synthetic caller\n'
    args.caller_sha256 = m.sha(raw)
    monkeypatch.setattr(m.v5, '_under_test', lambda: False)
    monkeypatch.setattr(m.sys, 'executable', str(m.frozen.PYTHON))
    monkeypatch.setattr(environment, '_require_environment', lambda: None)
    monkeypatch.setitem(m.NEW_PINS, 'scripts/arv2_r298_readiness_recovery_remote.py', '1' * 64)
    state = SimpleNamespace(command_error=None, source_error=None, calls=[])
    def git(command, deadline, *extra):
        state.calls.append(command)
        if state.command_error == command:
            return b'wrong\n'
        if command == ['rev-parse', '--show-toplevel']:
            return str(m.ROOT).encode() + b'\n'
        if command == ['branch', '--show-current']:
            return m.frozen.BRANCH.encode() + b'\n'
        if command == ['rev-parse', 'HEAD']:
            return args.expected_head.encode() + b'\n'
        if command == ['status', '--porcelain']:
            return b''
        if command[:2] == ['cat-file', '-s']:
            return str(len(raw)).encode() + b'\n'
        if command[:2] == ['cat-file', 'blob']:
            return raw
        pytest.fail('unexpected git command')
    def digest(path):
        if str(path) == state.source_error:
            return '0' * 64
        return args.caller_sha256 if path == m.SOURCE else m.selected_pins()[path.relative_to(m.ROOT).as_posix()]
    monkeypatch.setattr(m.v5, '_git', git)
    monkeypatch.setattr(m.helpers, '_source_digest', digest)
    return state


def test_preflight_clean_source_and_committed_self(args, preflight):
    m._preflight(args, time.monotonic() + 10)
    assert sum(command == ['status', '--porcelain'] for command in preflight.calls) == 2


@pytest.mark.parametrize('command', [['rev-parse', '--show-toplevel'], ['branch', '--show-current'],
    ['rev-parse', 'HEAD'], ['status', '--porcelain']])
def test_preflight_context_refuses(args, preflight, command):
    preflight.command_error = command
    with pytest.raises(m.Refused):
        m._preflight(args, time.monotonic() + 10)


@pytest.mark.parametrize('name', ['scripts/run_arv2_r298_final_recovery.py',
    'scripts/arv2_r298_final_recovery_remote.py', 'scripts/arv2_newrule_execution_environment.py',
    'scripts/run_arv2_r298_post_mia_recovery.py', 'scripts/run_arv2_r298_owner_recovery.py',
    'scripts/arv2_r298_owner_recovery_remote.py', 'scripts/run_arv2_r298_privacy_recovery.py',
    'scripts/arv2_r298_privacy_recovery_remote.py', 'scripts/run_arv2_r298_readiness_recovery.py',
    'scripts/arv2_r298_access_recovery_remote.py', 'scripts/arv2_r298_collaborator_access.py'])
def test_preflight_frozen_or_own_source_drift(args, preflight, name):
    preflight.source_error = str(m.ROOT / name)
    with pytest.raises(m.Refused, match='source'):
        m._preflight(args, time.monotonic() + 10)


@pytest.mark.parametrize('field,value', [('expected_head', 'bad'), ('caller_sha256', 'bad'),
    ('operation', 'evidence'), ('control_fd', 9)])
def test_preflight_rejects_wrong_binding_operation_or_descriptor(args, preflight, field, value):
    setattr(args, field, value)
    with pytest.raises(m.Refused):
        m._preflight(args, time.monotonic() + 10)


def test_worker_preflight_rejects_inherited_credentials(args, preflight, monkeypatch):
    args.operation, args.control_fd = m.WORKERS[0], 9
    monkeypatch.setenv('QC_API_TOKEN', 'synthetic-not-secret')
    with pytest.raises(m.Refused, match='context'):
        m._preflight(args, time.monotonic() + 10)


def test_cli_actual_nonzero_never_claims_success(args, monkeypatch, capsys):
    monkeypatch.setattr(m, '_preflight', lambda *_: None)
    monkeypatch.setattr(environment, '_bootstrap_cli_logging', lambda: None)
    def refuse(*_):
        raise m.Refused('deadline')
    monkeypatch.setattr(m, '_execute', refuse)
    exit_code = m.main(['recover', '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256])
    raw = capsys.readouterr().out.encode('ascii')
    assert exit_code == 2 and raw.endswith(b'\n\n')
    payload = m.parse(raw[:-1])
    assert payload['operation_completed'] is False and payload['failure_code'] == 'deadline'
    assert all(payload[key] is False for key in m.FALSE_FLAGS)
    assert m.validate_output(raw, exit_code, args) == payload


def test_dispatch_ceiling_stops_without_unjournalled_extra_request(args, workflow, monkeypatch):
    monkeypatch.setattr(m, 'MAX_DISPATCH', 5)
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    value = m.failure_observation(error.value)
    assert value['application_dispatch_count'] == 5 and len(workflow.cloud.calls) == 5
    assert value['last_event'] == 'intent'
    assert not any(endpoint in ('files/create', 'files/update', 'backtests/create') for endpoint, _ in workflow.cloud.calls)


def test_cli_success_and_alarm_scope(args, monkeypatch, capsys):
    from contextlib import contextmanager
    events = []
    @contextmanager
    def alarm(deadline):
        assert 590 < deadline - time.monotonic() <= 600
        events.append('alarm-enter')
        yield
        events.append('alarm-exit')
    monkeypatch.setattr(m.helpers, '_alarm', alarm)
    monkeypatch.setattr(m, '_preflight', lambda *_: events.append('preflight'))
    monkeypatch.setattr(environment, '_bootstrap_cli_logging', lambda: events.append('logging'))
    monkeypatch.setattr(m, '_execute', lambda *_: {'synthetic': True})
    assert m.main(['recover', '--expected-head', args.expected_head, '--caller-sha256', args.caller_sha256]) == 0
    raw = capsys.readouterr().out.encode('ascii')
    assert raw.endswith(b'\n\n')
    assert m.parse(raw[:-1])['operation_completed'] is True
    assert events == ['alarm-enter', 'preflight', 'logging', 'alarm-exit']


@pytest.mark.parametrize('kind', ['normal', 'nonzero', 'noise', 'stderr', 'trailing', 'oversize',
    'timeout', 'binding', 'false_flag', 'bad_result', 'wrong_operation'])
def test_real_synthetic_child_fd_bounded_channel_and_reap(args, leaf, monkeypatch, tmp_path, kind):
    operation = m.WORKERS[1]
    result = {'admission_authenticated': True, 'projection_sha256': m.remote.PROJECTION_SHA256}
    envelope = {'schema': m.SCHEMA, 'operation': operation, 'binding': m.binding(args),
        'result': copy.deepcopy(result), 'operation_completed': True, **m.FALSE_FLAGS}
    if kind == 'binding':
        envelope['binding']['project_id'] += 1
    elif kind == 'false_flag':
        envelope['strategy_result_accepted'] = True
    elif kind == 'bad_result':
        envelope['result']['unexpected'] = True
    elif kind == 'wrong_operation':
        envelope['operation'] = m.WORKERS[0]
    raw = m.canonical(envelope) + b'\n'
    if kind == 'noise':
        raw = b'noise' + raw
    elif kind == 'trailing':
        raw += b'x'
    elif kind == 'oversize':
        raw = b'x' * (m.WORKER_MAX_OUTPUT + 1)
    processes = []
    real_popen = subprocess.Popen
    synthetic_env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'en_US.UTF-8',
        'TMPDIR': str(tmp_path), 'TMP': str(tmp_path), 'TEMP': str(tmp_path),
        'XDG_CACHE_HOME': str(tmp_path), 'PYTHONPYCACHEPREFIX': str(tmp_path / 'cache'),
        'PYTHONDONTWRITEBYTECODE': '1', 'QC_USER_ID': 'synthetic-user', 'QC_API_TOKEN': 'synthetic-token'}
    monkeypatch.setattr(m.os, 'environ', synthetic_env)
    def launch(command, **kwargs):
        assert command[:3] == ['/usr/bin/sandbox-exec', '-p', m.SANDBOX]
        assert command[4:7] == ['-B', str(m.SOURCE), operation]
        assert str(m.a3.SOURCE) not in command and '--control-fd' in command
        assert not {'QC_USER_ID', 'QC_API_TOKEN'} & set(kwargs['env'])
        fd = kwargs['pass_fds'][0]
        # Pytest already supplies native denial. Nested sandbox-exec is not
        # supported on this Darwin host; only this tiny fixture replaces it.
        code = ('import os,socket,time\n'
            f'os.fstat({fd})\n'
            'try:\n socket.socket().bind(("127.0.0.1",0))\n'
            'except PermissionError:\n pass\n'
            'else:\n raise RuntimeError("native denial missing")\n'
            + ('time.sleep(30)\n' if kind == 'timeout' else '')
            + f'os.write(1,{raw!r})\n'
            + ('os.write(2,b"finite-noise")\n' if kind == 'stderr' else '')
            + ('raise SystemExit(2)\n' if kind == 'nonzero' else ''))
        process = real_popen([str(m.frozen.PYTHON), '-B', '-c', code], **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(m.subprocess, 'Popen', launch)
    with m.Store(create=True) as store:
        if kind == 'normal':
            assert m._child(args, store, time.monotonic() + 5, operation) == result
            assert store.read(operation + '-completed.json')[1]['result'] == result
        else:
            with pytest.raises((m.Refused, m.previous.Refused, ValueError)):
                m._child(args, store, time.monotonic() + (0.2 if kind == 'timeout' else 5), operation)
            assert not (leaf / (operation + '-completed.json')).exists()
    assert len(processes) == 1 and processes[0].poll() is not None
    assert processes[0].stdout.closed and processes[0].stderr.closed


def outer_success(args, result):
    report = m.canonical({**m.binding(args), 'result': result, 'operation_completed': True, **m.FALSE_FLAGS})
    return {'schema': m.SCHEMA, 'operation': 'recover', 'binding': m.binding(args),
        'operation_completed': True, **m.FALSE_FLAGS,
        'result': {'report': {'sha256': m.sha(report), 'byte_count': len(report)}, 'result': result}}


@pytest.fixture
def success(args, leaf, workflow):
    result = m._execute(args, 600)
    return outer_success(args, result['result'])


def test_readiness_end_to_end_stops_after_source_compile_and_final_admission(args, leaf, workflow):
    result = m._execute(args, 600)
    ready = result['result']
    assert ready['terminal'] == 'ready_for_backtest'
    assert ready['ready_receipt']['state'] == 'compiled_exact_source_ready'
    assert ready['ready_receipt']['attempt'] == 10
    assert all(ready['ready_receipt'][key] is False for key in m.remote.READY_FALSE)
    assert workflow.events == ['admission-initial-worker', 'admission-final-worker']
    assert workflow.sleeps == [10]
    calls = workflow.cloud.calls
    assert sum(endpoint == 'compile/create' for endpoint, _ in calls) == 1
    assert not any(endpoint in ('projects/nodes/read', 'backtests/create', 'backtests/read') for endpoint, _ in calls)
    writes = [payload['name'] for endpoint, payload in calls if endpoint in ('files/create', 'files/update')]
    assert len(writes) == len(set(writes)) == 9
    assert all(workflow.cloud.files[name] == raw.decode('ascii') for name, raw in workflow.cloud.sources.items())
    assert (leaf / 'ready-access.json').exists() and (leaf / 'ready-receipt.json').exists()
    assert ready['access_observation']['marker'] == 'ready-access'
    assert m.validate_output(m.canonical(outer_success(args, ready)) + b'\n', 0, args)['operation_completed'] is True


@pytest.mark.parametrize('operation', m.WORKERS)
def test_admission_failure_blocks_readiness_and_never_launches(args, workflow, operation):
    workflow.child_error = operation
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    failure = m.failure_observation(error.value)
    assert failure['code'] == 'input_admission'
    if operation == m.WORKERS[0]:
        assert workflow.cloud.calls == []
    else:
        assert failure['access_observation']['marker'] == 'ready-access'
    assert not any(endpoint in ('projects/nodes/read', 'backtests/create') for endpoint, _ in workflow.cloud.calls)


@pytest.mark.parametrize('compile_state,reason', [('BuildError', 'compile_failed'), ('Building', 'compile_budget')])
def test_compile_failure_or_budget_consumes_without_second_compile(args, workflow, compile_state, reason):
    workflow.cloud.compile_state = compile_state
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    failure = m.failure_observation(error.value)
    assert failure['code'] == reason
    assert sum(endpoint == 'compile/create' for endpoint, _ in workflow.cloud.calls) == 1
    assert sum(endpoint == 'compile/read' for endpoint, _ in workflow.cloud.calls) == (20 if compile_state == 'Building' else 1)
    assert workflow.events == ['admission-initial-worker']


@pytest.mark.parametrize('change,reason', [('name', 'access_extra_row_shape'), ('unreported', 'access_extra_row_pin')])
def test_current_extra_mismatch_retains_inline_facts_before_no_write(args, workflow, change, reason):
    row = workflow.cloud.project['collaborators'][1]
    row['name' if change == 'name' else 'another'] = 'Synthetic changed private value'
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    failure = m.failure_observation(error.value)
    assert failure['helper_code'] == reason and failure['application_dispatch_count'] == 2
    observed = failure['access_observation']
    assert observed['marker'] == 'inspect-access' and observed['journal_pin'] is not None
    m._validate_access(observed, args=args, published=True)
    assert b'Synthetic changed private value' not in m.canonical(failure)
    assert all(endpoint in ('projects/read', 'projects/collaboration/read') for endpoint, _ in workflow.cloud.calls)


def test_access_publication_failure_retains_safe_memory_snapshot(args, workflow, monkeypatch):
    original = m.Store.write
    def write(self, name, value):
        if name == 'inspect-access.json':
            raise m.Refused('control_changed')
        return original(self, name, value)
    monkeypatch.setattr(m.Store, 'write', write)
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    failure = m.failure_observation(error.value)
    assert failure['helper_code'] == 'access_observation_sink'
    assert failure['access_observation']['journal_pin'] is None
    assert failure['access_observation']['marker'] == 'inspect-access'
    assert len(workflow.cloud.calls) == 2


def test_next_history_intent_before_dispatch_preserves_prior_access_failure(args, workflow, monkeypatch):
    original = m.Store.write
    def write(self, name, value):
        result = original(self, name, value)
        if name == 'rpc-inspect-backtests-intent.json':
            workflow.now = 601
        return result
    monkeypatch.setattr(m.Store, 'write', write)
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    failure = m.failure_observation(error.value)
    assert failure['code'] == 'remote_refused' and failure['helper_code'] == 'request_ambiguous'
    assert failure['last_event'] == 'intent'
    assert failure['endpoint'] == 'backtests/list' and failure['application_dispatch_count'] == 2
    assert failure['access_observation']['marker'] == 'inspect-access'
    m._validate_access(failure['access_observation'], args=args, published=True)
    assert len(workflow.cloud.calls) == 2


@pytest.mark.parametrize('mutation', ['marker', 'count', 'pin', 'stage', 'raw', 'manifest', 'launch_flag', 'terminal'])
def test_readiness_and_inline_access_cannot_be_forged_with_new_report_pin(args, success, mutation):
    result = copy.deepcopy(success['result']['result'])
    if mutation == 'marker': result['access_observation']['marker'] = 'inspect-access'
    elif mutation == 'count': result['access_observation']['application_dispatch_count'] = 64
    elif mutation == 'pin': result['access_observation']['journal_pin']['sha256'] = '0' * 64
    elif mutation == 'stage': result['access_observation']['observation']['stage'] = 'inspect'
    elif mutation == 'raw': result['access_observation']['observation']['raw'] = 'private'
    elif mutation == 'manifest': result['ready_receipt']['source_manifest_sha256'] = '0' * 64
    elif mutation == 'launch_flag': result['ready_receipt']['backtest_created'] = True
    else: result['terminal'] = 'own_status_observed'
    with pytest.raises((m.Refused, m.remote.RecoveryError)):
        m.validate_output(m.canonical(outer_success(args, result)) + b'\n', 0, args)


@pytest.mark.parametrize('endpoint', ['projects/nodes/read', 'backtests/create', 'backtests/read',
    'backtests/orders/read', 'projects/collaboration/update', 'projects/update'])
def test_owner_client_has_no_capacity_launch_results_or_permission_capability(narrow_client, endpoint):
    _, _, events = narrow_client
    client = m.OwnerClient(lambda _: None)
    with pytest.raises(m.Refused, match='client'):
        client.request(endpoint, {'projectId': m.PROJECT})
    assert not any(type(event) is tuple for event in events)


def test_readiness_profile_and_worker_denial_are_narrow_and_new():
    profile = m.profile_record()
    assert profile['attempt_id'] == 10 and profile['max_backtest_creates'] == 0
    assert profile['capacity_backtest_status_or_result_allowed'] is False
    assert profile['a1_through_a9_remain_spent'] is True
    assert profile['worker_operations'] == ['admission-initial-worker', 'admission-final-worker']
    assert 'newrule_readiness_recovery/R321-20261024-B' in profile['control']
    assert '/Library/Keychains' in m.SANDBOX and '(deny network*)' in m.SANDBOX
    assert str(m.CONTROL) in m.SANDBOX and str(PUBLIC_ROOT / '.pytest_cache') in m.SANDBOX
    assert all(value is False for value in m.FALSE_FLAGS.values())


@pytest.mark.parametrize('mutation', ['unknown_extra', 'permission_read', 'live_false', 'public_true',
    'running_true', 'duplicate_owner', 'no_owner'])
def test_success_rejects_policy_contradiction_even_with_valid_diagnostic_and_all_new_pins(args, success, workflow, mutation):
    project = copy.deepcopy(workflow.cloud.project)
    dedicated = copy.deepcopy(workflow.cloud.dedicated)
    if mutation == 'unknown_extra': project['collaborators'][1]['name'] = 'Synthetic unknown'
    elif mutation == 'permission_read': dedicated['userPermissions'] = 'read'
    elif mutation == 'live_false': dedicated['userLiveControl'] = False
    elif mutation == 'public_true': project['public'] = True
    elif mutation == 'running_true': project['codeRunning'] = True
    elif mutation == 'duplicate_owner': project['collaborators'] = [project['collaborators'][0]] * 2
    else: project['collaborators'] = [project['collaborators'][1]]
    packet = m.remote.access_observation_record('ready', {'success': True, 'projects': [project]},
        {'success': True, **dedicated})
    result = copy.deepcopy(success['result']['result'])
    access = result['access_observation']
    access['observation'] = packet
    raw = m.canonical(m._access_record(args, access))
    access['journal_pin'] = {'sha256': m.sha(raw), 'byte_count': len(raw)}
    with pytest.raises(m.Refused):
        m.validate_output(m.canonical(outer_success(args, result)) + b'\n', 0, args)


def test_pure_output_success_authenticates_actual_result_report_and_exit(args, success):
    raw = m.canonical(success) + b'\n'
    assert m.validate_output(raw, 0, args) == success


@pytest.mark.parametrize('actual_exit', [2, -1, None, False, True, '0', 0.0])
def test_output_success_requires_actual_integer_zero(args, success, actual_exit):
    with pytest.raises((m.Refused, m.previous.Refused)):
        m.validate_output(m.canonical(success) + b'\n', actual_exit, args)


@pytest.mark.parametrize('mutation', ['trailing', 'single_lf', 'triple_lf', 'noncanonical', 'duplicate', 'oversize'])
def test_output_byte_framing_exact(args, success, mutation):
    raw = m.canonical(success) + b'\n'
    if mutation == 'trailing':
        raw += b'x'
    elif mutation == 'single_lf':
        raw = raw[:-1]
    elif mutation == 'triple_lf':
        raw += b'\n'
    elif mutation == 'noncanonical':
        raw = b' ' + raw
    elif mutation == 'duplicate':
        raw = b'{"schema":"duplicate",' + raw[1:]
    else:
        raw = b'x' * (m.MAX_OUTPUT + 1) + b'\n\n'
    with pytest.raises((m.Refused, m.previous.Refused, ValueError)):
        m.validate_output(raw, 0, args)


@pytest.mark.parametrize('mutation', ['schema', 'operation', 'binding', 'extra', 'flag', 'completed',
    'pin_digest', 'pin_bytes', 'pin_bool', 'pin_extra', 'wrapper_extra'])
def test_output_outer_bindings_and_report_hash(args, success, mutation):
    if mutation == 'schema':
        success['schema'] += '-wrong'
    elif mutation == 'operation':
        success['operation'] = m.WORKERS[0]
    elif mutation == 'binding':
        success['binding']['expected_head'] = 'f' * 40
    elif mutation == 'extra':
        success['private'] = 'do-not-print'
    elif mutation == 'flag':
        success['strategy_result_accepted'] = True
    elif mutation == 'completed':
        success['operation_completed'] = 1
    elif mutation == 'wrapper_extra':
        success['result']['extra'] = True
    else:
        pin = success['result']['report']
        if mutation == 'pin_digest':
            pin['sha256'] = 'e' * 64
        elif mutation == 'pin_bytes':
            pin['byte_count'] += 1
        elif mutation == 'pin_bool':
            pin['byte_count'] = True
        else:
            pin['extra'] = True
    with pytest.raises((m.Refused, m.previous.Refused)):
        m.validate_output(m.canonical(success) + b'\n', 0, args)


@pytest.fixture
def failure(args):
    state = {**m.a3._new_state(), 'last_stage': 'inspect', 'intent_marker': 'inspect-project',
        'endpoint': 'projects/read', 'last_event': 'observed', 'application_dispatch_count': 1,
        'code_running': {'present': True, 'kind': 'boolean', 'boolean_value': True}}
    observation = m._failure(m.remote.RecoveryError('access_idle'), state)
    return {'schema': m.SCHEMA, 'operation': 'recover', 'binding': m.binding(args),
        'operation_completed': False, 'failure_code': 'remote_refused', 'failure_observation': observation,
        'attempt_consumption': 'consumed_or_ambiguous_no_retry', **m.FALSE_FLAGS}


def test_output_failure_is_validated_failure_not_success(args, failure):
    raw = m.canonical(failure) + b'\n'
    assert m.validate_output(raw, 2, args) == failure
    with pytest.raises(m.Refused):
        m.validate_output(raw, 0, args)


@pytest.mark.parametrize('mutation', ['raw_code', 'raw_context', 'extra', 'binding', 'consumed', 'completed',
    'mismatched_code', 'count_bool', 'idle_bool_int'])
def test_output_failure_rejects_nonfinite_or_unbound_context(args, failure, mutation):
    if mutation == 'raw_code':
        failure['failure_code'] = 'private remote reason'
    elif mutation == 'raw_context':
        failure['failure_observation']['raw'] = 'private body'
    elif mutation == 'extra':
        failure['extra'] = True
    elif mutation == 'binding':
        failure['binding'] = None
    elif mutation == 'consumed':
        failure['attempt_consumption'] = 'retry'
    elif mutation == 'completed':
        failure['operation_completed'] = 0
    elif mutation == 'mismatched_code':
        failure['failure_code'] = 'deadline'
    elif mutation == 'count_bool':
        failure['failure_observation']['application_dispatch_count'] = True
    else:
        failure['failure_observation']['code_running']['boolean_value'] = 1
    with pytest.raises((m.Refused, m.previous.Refused)):
        m.validate_output(m.canonical(failure) + b'\n', 2, args)


@pytest.fixture
def narrow_client(monkeypatch):
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
        events.append((endpoint, copy.deepcopy(payload)))
        return {'success': True}
    monkeypatch.setattr(old.QuantConnectClient, 'request', request)
    return old, api, events


@pytest.mark.parametrize('endpoint,payload', [
    ('files/delete', {'projectId': m.PROJECT, 'name': 'main.py'}),
    ('projects/collaboration/delete', {'projectId': m.PROJECT}),
    ('projects/collaboration/create', {'projectId': m.PROJECT}),
    ('live/create', {'projectId': m.PROJECT}),
    ('backtests/read', {'projectId': m.PROJECT}),
    ('projects/read', {'projectId': True}),
    ('projects/read', {'projectId': m.PROJECT + 1}),
    ('projects/read', {'projectId': m.PROJECT, 'codeSourceId': 'extra'}),
    ('projects/read', {}),
    ('projects/read', []),
    (None, {'projectId': m.PROJECT}),
    ('files/read', {'projectId': m.PROJECT}),
    ('files/read', {'projectId': m.PROJECT, 'codeSourceId': 'wrong'}),
    ('files/read', {'projectId': m.PROJECT, 'codeSourceId': m.remote.CODE_SOURCE_ID, 'force': True}),
    ('projects/collaboration/lock/acquire', {'projectId': m.PROJECT}),
    ('projects/collaboration/lock/acquire', {'projectId': m.PROJECT, 'codeSourceId': 'other'}),
    ('files/update', {'projectId': m.PROJECT, 'codeSourceId': m.remote.CODE_SOURCE_ID,
        'name': '../main.py', 'content': '#'}),
    ('files/update', {'projectId': m.PROJECT, 'codeSourceId': m.remote.CODE_SOURCE_ID,
        'name': 'main.py', 'content': 'x' * 64001}),
    ('files/create', {'projectId': m.PROJECT, 'codeSourceId': m.remote.CODE_SOURCE_ID,
        'name': 'main.py', 'content': '\u2603'}),
    ('backtests/create', {'projectId': m.PROJECT, 'compileId': 'compiled', 'backtestName': 'other'}),
    ('backtests/list', {'projectId': m.PROJECT, 'includeStatistics': 0}),
    ('compile/read', {'projectId': m.PROJECT, 'compileId': '../bad'}),
])
def test_new_narrow_client_refuses_scope_before_dispatch(narrow_client, endpoint, payload):
    _, _, events = narrow_client
    client = m.OwnerClient(lambda _: None)
    with pytest.raises((m.Refused, m.remote.RecoveryError)):
        client.request(endpoint, payload)
    assert not any(type(event) is tuple for event in events)


@pytest.mark.parametrize('field,value', [('_base_url', 'https://example.invalid'),
    ('_transport', object()), ('_timeout', 31), ('_timeout', True), ('_timeout', '30')])
def test_new_client_binding_checked_before_each_request(narrow_client, field, value):
    _, api, events = narrow_client
    client = m.OwnerClient(lambda _: None)
    setattr(api, field, value)
    with pytest.raises(m.Refused, match='client'):
        client.request('projects/read', {'projectId': m.PROJECT})
    assert not any(type(event) is tuple for event in events)


def test_new_client_exact_type_and_constructor_guard(narrow_client, monkeypatch):
    old, api, events = narrow_client
    class Derived(old.QuantConnectClient):
        pass
    api.__class__ = Derived
    with pytest.raises(m.Refused, match='client'):
        m.OwnerClient(lambda _: None)
    assert not any(type(event) is tuple for event in events)


def test_new_client_environment_refusal_precedes_credentials(narrow_client, monkeypatch):
    _, _, events = narrow_client
    def refuse():
        raise RuntimeError('synthetic environment')
    monkeypatch.setattr(environment, 'require_safe_environment', refuse)
    with pytest.raises(RuntimeError):
        m.OwnerClient(lambda _: None)
    assert events == []


def test_direct_help_in_minimal_environment_no_operational_entry(tmp_path):
    env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'PYTHONDONTWRITEBYTECODE': '1',
        'TMPDIR': str(tmp_path), 'XDG_CACHE_HOME': str(tmp_path),
        'PYTHONPYCACHEPREFIX': str(tmp_path / 'pycache')}
    result = subprocess.run([str(m.frozen.PYTHON), '-B', str(m.SOURCE), '--help'],
        cwd=m.ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=5, check=False)
    assert result.returncode == 0 and result.stderr == b''
    assert b'--expected-head' in result.stdout and b'--caller-sha256' in result.stdout
    assert len(result.stdout) < 4096


@pytest.fixture
def response_workflow(workflow, monkeypatch):
    """Actual shared parser + fixed source, with fully synthetic native-denied transport."""
    import json
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
    from research.analyst_revisions_v2_qc.newrule_comparison_projection import normalize
    raw = (PUBLIC_ROOT / 'research/analyst_revisions_v2_qc' / m.boundary.TARGET_NAME).read_bytes()
    assert m.sha(raw) == 'a08098648d98a95736471113d48a3e1183f04969d2c2561b1a4f5d6bfc80d7ee'
    normalized = normalize(raw, m.boundary.TARGET_NAME)
    assert len(normalized) == 23055 and m.sha(normalized) == m.boundary.SOURCE_SHA256
    cloud = workflow.cloud
    cloud.sources[m.boundary.TARGET_NAME] = normalized
    entries = tuple(SimpleNamespace(project_path=name, source_bytes=raw)
        for name, raw in sorted(cloud.sources.items()))
    manifest = [{'project_path': item.project_path, 'byte_count': len(item.source_bytes),
        'content_sha256': m.sha(item.source_bytes)} for item in entries]
    cloud.projection = SimpleNamespace(projection_sha256=m.remote.PROJECTION_SHA256,
        source_files=entries, to_record=lambda: {
            'candidate_id': m.remote.PROJECTION_CANDIDATE_ID, 'source_files': manifest})
    state = SimpleNamespace(raw=b'{"success":true}', status=200,
        transport_error=False, target_calls=0, shared_replies=[], clients=[])

    def transport(url, body, headers, timeout):
        endpoint = url.removeprefix(old.API_BASE + '/')
        payload = json.loads(body)
        assert timeout == 30 and set(headers) == {'Authorization', 'Timestamp', 'Content-Type'}
        cloud.events.append(('injected', {'event': 'intent', 'endpoint': endpoint,
            'sha256': m.sha(m.canonical(payload))}))
        if endpoint == m.boundary.ENDPOINT and payload.get('name') == m.boundary.TARGET_NAME:
            state.target_calls += 1
            if state.transport_error:
                cloud.calls.append((endpoint, copy.deepcopy(payload)))
                raise RuntimeError('SYNTHETIC_PRIVATE_TRANSPORT_REASON')
            if state.raw == b'{"success":true}':
                cloud.request(endpoint, payload)
            else:
                cloud.calls.append((endpoint, copy.deepcopy(payload)))
            return state.status, state.raw
        return 200, m.canonical(cloud.request(endpoint, payload))

    monkeypatch.setattr(old.coverage, '_bounded_transport', transport)
    def client():
        api = old.QuantConnectClient(m.boundary.shared.QuantConnectCredentials(
            user_id='synthetic-user', api_token='synthetic-not-a-secret'),
            transport=transport, timeout=30, clock=lambda: 1234567890)
        state.clients.append(api)
        return api
    monkeypatch.setattr(old, '_client', client)
    monkeypatch.setattr(m, 'OwnerClient', REAL_OWNER_CLIENT)
    return state


def test_upstream_transport_error_stays_unknown_without_fabricated_response(args, response_workflow):
    response_workflow.transport_error = True
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    result = m.failure_observation(error.value)
    assert result['response_observation'] is None and result['http_status'] is None
    assert result['response_boundary_code'] == 'transport_refused'
    assert b'SYNTHETIC_PRIVATE_TRANSPORT_REASON' not in m.canonical(result)
    assert response_workflow.target_calls == 1


def synthetic_response(args):
    observation = {'project_id': m.PROJECT, 'endpoint': m.boundary.ENDPOINT,
        'target_name': m.boundary.TARGET_NAME, 'source_sha256': m.boundary.SOURCE_SHA256,
        'boundary_profile_sha256': m.sha(m.canonical(m.boundary.profile_record())),
        'intent_marker': 'complete-write-02', 'application_dispatch_count': 10,
        'evidence': m.response_evidence.project_response(200, b'{"success":true}'),
        'error_text': m.error_text.project_error_text(200, b'{"success":true}'),
        'journal_pin': None}
    raw = m.canonical(m._response_record(args, observation))
    observation['journal_pin'] = {'sha256': m.sha(raw), 'byte_count': len(raw)}
    return observation


def attach_response(failure, observation):
    outer = failure['failure_observation']
    outer.update(response_observation=observation, last_stage='complete',
        application_dispatch_count=observation['application_dispatch_count'],
        endpoint=m.boundary.ENDPOINT, intent_marker='complete-write-02', last_event='failure',
        http_status=observation['evidence']['http_status'])


@pytest.mark.parametrize('mutation', ['marker', 'later_count', 'parent_zero',
    'equal_endpoint', 'equal_marker', 'non_2xx', 'equal_status'])
def test_response_context_requires_coherent_parent_even_with_repinned_evidence(args, failure, mutation):
    observation = synthetic_response(args)
    attach_response(failure, observation)
    outer = failure['failure_observation']
    if mutation == 'marker':
        observation['intent_marker'] = 'complete-write-03'
    elif mutation == 'later_count':
        observation['application_dispatch_count'] += 1
    elif mutation == 'parent_zero':
        outer.update(application_dispatch_count=0, intent_marker=None, endpoint=None, last_event=None)
    elif mutation == 'equal_endpoint':
        outer['endpoint'] = 'projects/read'
    elif mutation == 'non_2xx':
        observation['evidence'] = m.response_evidence.project_response(404, b'{"success":false}')
        outer['http_status'] = 404
    elif mutation == 'equal_status':
        outer['http_status'] = 403
    else:
        outer['intent_marker'] = 'inspect-project'
    raw = m.canonical(m._response_record(args, observation))
    observation['journal_pin'] = {'sha256': m.sha(raw), 'byte_count': len(raw)}
    with pytest.raises(m.Refused):
        m.validate_output(m.canonical(failure) + b'\n', 2, args)


def test_success_response_context_cannot_follow_outer_dispatch_count(args, success):
    observation = synthetic_response(args)
    result = success['result']['result']
    observation['application_dispatch_count'] = result['application_dispatch_count'] + 1
    raw = m.canonical(m._response_record(args, observation))
    observation['journal_pin'] = {'sha256': m.sha(raw), 'byte_count': len(raw)}
    result['response_observation'] = observation
    with pytest.raises(m.Refused):
        m.validate_output(m.canonical(outer_success(args, result)) + b'\n', 0, args)


def test_response_survives_next_intent_without_another_dispatch(args, failure):
    observation = synthetic_response(args)
    attach_response(failure, observation)
    failure['failure_observation'].update(endpoint='files/read',
        intent_marker='complete-after-02', last_event='intent')
    assert m.validate_output(m.canonical(failure) + b'\n', 2, args) == failure


@pytest.mark.parametrize('kind', ['non_object', 'success_false', 'unpublished'])
def test_rejected_or_unpublished_response_cannot_precede_later_dispatch(args, failure, kind):
    observation = synthetic_response(args)
    attach_response(failure, observation)
    failure['failure_observation']['application_dispatch_count'] += 1
    if kind != 'unpublished':
        observation['evidence'] = m.response_evidence.project_response(200,
            b'[]' if kind == 'non_object' else b'{"success":false}')
        raw = m.canonical(m._response_record(args, observation))
        observation['journal_pin'] = {'sha256': m.sha(raw), 'byte_count': len(raw)}
    else:
        observation['journal_pin'] = None
    with pytest.raises(m.Refused):
        m.validate_output(m.canonical(failure) + b'\n', 2, args)


@pytest.mark.parametrize('mutation', ['schema', 'source', 'profile', 'endpoint', 'target',
    'project', 'count_bool', 'count_over', 'pin_hash', 'pin_size', 'missing_pin',
    'evidence_flag', 'raw_text', 'boundary_code', 'missing_response'])
def test_failure_response_envelope_rejects_unbound_or_nonfinite_evidence(args, failure, mutation):
    observation = synthetic_response(args)
    attach_response(failure, observation)
    if mutation == 'schema':
        observation['evidence']['schema'] = 'other'
    elif mutation == 'source':
        observation['source_sha256'] = 'f' * 64
    elif mutation == 'profile':
        observation['boundary_profile_sha256'] = 'f' * 64
    elif mutation == 'endpoint':
        observation['endpoint'] = 'files/create'
    elif mutation == 'target':
        observation['target_name'] = 'main.py'
    elif mutation == 'project':
        observation['project_id'] = True
    elif mutation.startswith('count'):
        observation['application_dispatch_count'] = True if mutation == 'count_bool' else 65
    elif mutation == 'pin_hash':
        observation['journal_pin']['sha256'] = 'f' * 64
    elif mutation == 'pin_size':
        observation['journal_pin']['byte_count'] += 1
    elif mutation == 'missing_pin':
        del observation['journal_pin']
    elif mutation == 'evidence_flag':
        observation['evidence']['remote_effect_known'] = True
    elif mutation == 'raw_text':
        observation['evidence']['raw'] = 'SYNTHETIC_PRIVATE_REASON'
    elif mutation == 'boundary_code':
        failure['failure_observation']['response_boundary_code'] = 'SYNTHETIC_PRIVATE_REASON'
    else:
        del failure['failure_observation']['response_observation']
    with pytest.raises((m.Refused, m.response_evidence.EvidenceError)):
        m.validate_output(m.canonical(failure) + b'\n', 2, args)


def test_large_finite_response_uses_new_parent_bound_not_worker_bound(args, failure):
    import json
    observation = synthetic_response(args)
    packet = {'success': False, **{key: ["Hash doesn't match."] * 32
        for key in ('errors', 'messages', 'Message')}}
    observation['evidence'] = m.response_evidence.project_response(200, json.dumps(packet).encode())
    observation['error_text'] = m.error_text.project_error_text(200, json.dumps(packet).encode())
    raw = m.canonical(m._response_record(args, observation))
    observation['journal_pin'] = {'sha256': m.sha(raw), 'byte_count': len(raw)}
    attach_response(failure, observation)
    failure['failure_observation']['response_boundary_code'] = 'shared_request_refused'
    envelope = m.canonical(failure) + b'\n'
    assert len(envelope) > 4096 and len(envelope) < m.MAX_OUTPUT == 120 * 1024
    assert m.WORKER_MAX_OUTPUT == 24 * 1024
    assert m.validate_output(envelope, 2, args) == failure


def test_maximum_retained_error_items_and_collaborator_rows_fit_combined_envelope(args, failure, cloud):
    import json
    failure['binding'] = m.binding(args)  # Synthetic cloud pins are fixture-local.
    project = copy.deepcopy(cloud.project)
    dedicated = copy.deepcopy(cloud.dedicated)
    rows = [{**copy.deepcopy(project['collaborators'][1]), 'name': 'Synthetic unknown ' + str(index)}
        for index in range(m.remote.diagnostic.projection.MAX_COLLABORATORS)]
    project['collaborators'] = rows
    dedicated['collaborators'] = copy.deepcopy(rows)
    packet = m.remote.access_observation_record('inspect', {'success': True, 'projects': [project]},
        {'success': True, **dedicated})
    access = {'marker': 'inspect-access', 'application_dispatch_count': 2,
        'observation': packet, 'journal_pin': None}
    access_raw = m.canonical(m._access_record(args, access))
    access['journal_pin'] = {'sha256': m.sha(access_raw), 'byte_count': len(access_raw)}
    response = synthetic_response(args)
    source = json.dumps({'success': False, **{name: ['synthetic item'] * m.response_evidence.MAX_ITEMS
        for name in ('errors', 'messages', 'Message')}}).encode()
    response['evidence'] = m.response_evidence.project_response(200, source)
    response['error_text'] = m.error_text.project_error_text(200, source)
    response_raw = m.canonical(m._response_record(args, response))
    response['journal_pin'] = {'sha256': m.sha(response_raw), 'byte_count': len(response_raw)}
    attach_response(failure, response)
    failure['failure_observation']['access_observation'] = access
    envelope = m.canonical(failure) + b'\n'
    assert len(envelope) > m.WORKER_MAX_OUTPUT
    assert len(envelope) < m.MAX_OUTPUT < 128 * 1024
    assert m.boundary.MAX_EVIDENCE_BYTES + m.remote.MAX_ACCESS_BYTES + 8 * 1024 <= m.MAX_OUTPUT
    assert m.validate_output(envelope, 2, args) == failure


@pytest.mark.parametrize('mutation', ['failed_response', 'null_pin'])
def test_success_cannot_claim_failed_or_unpublished_observation(args, success, mutation):
    observation = synthetic_response(args)
    if mutation == 'failed_response':
        observation['evidence'] = m.response_evidence.project_response(200, b'{"success":false}')
        raw = m.canonical(m._response_record(args, observation))
        observation['journal_pin'] = {'sha256': m.sha(raw), 'byte_count': len(raw)}
    else:
        observation['journal_pin'] = None
    result = success['result']['result']
    result['response_observation'] = observation
    value = outer_success(args, result)
    with pytest.raises(m.Refused):
        m.validate_output(m.canonical(value) + b'\n', 0, args)


@pytest.mark.parametrize('mutation', ['body', 'status', 'error_hash', 'error_bytes',
    'missing', 'extra', 'cause', 'retry', 'profile'])
def test_redacted_error_projection_cannot_be_unbound_even_with_republished_journal(args, failure, mutation):
    raw = b'{"success":false,"errors":["Cannot update file."]}'
    observation = synthetic_response(args)
    observation['evidence'] = m.response_evidence.project_response(200, raw)
    observation['error_text'] = m.error_text.project_error_text(200, raw,
        sensitive_values=('synthetic-user', 'synthetic-token'), source_text='# source fixture')
    diagnostic = observation['error_text']
    if mutation == 'body': diagnostic['body_sha256'] = 'f' * 64
    elif mutation == 'status': diagnostic['http_status'] = 201
    elif mutation == 'error_hash': diagnostic['error_string_sha256'] = 'f' * 64
    elif mutation == 'error_bytes': diagnostic['error_string_byte_count'] += 1
    elif mutation == 'missing': del observation['error_text']
    elif mutation == 'extra': diagnostic['raw'] = 'SYNTHETIC_SECRET'
    elif mutation == 'cause': diagnostic['cause_authenticated'] = True
    elif mutation == 'retry': diagnostic['retry_authority'] = True
    else: diagnostic['profile_sha256'] = 'f' * 64
    encoded = m.canonical(m._response_record(args, observation))
    observation['journal_pin'] = {'sha256': m.sha(encoded), 'byte_count': len(encoded)}
    attach_response(failure, observation)
    with pytest.raises((m.Refused, ValueError, RuntimeError)):
        m.validate_output(m.canonical(failure) + b'\n', 2, args)


def test_refused_diagnostic_retains_sanitized_error_and_stops_before_next_write(args, response_workflow):
    response_workflow.raw = b'{"success":false,"errors":["Cannot update file because the project is locked."]}'
    with pytest.raises(m.ObservedFailure) as caught:
        m._execute(args, 600)
    failure = m.failure_observation(caught.value)
    response = failure['response_observation']
    m._validate_response(response, args=args, published=True)
    assert response['evidence']['fields']['success']['boolean_value'] is False
    assert response['error_text']['error_string_sha256'] == response['evidence']['fields']['errors']['items'][0]['string_sha256']
    assert 'launch_receipt' not in failure and 'status_receipt' not in failure
    assert failure['last_stage'] == 'complete' and failure['application_dispatch_count'] == 10
    assert response_workflow.target_calls == 1
    assert failure['response_boundary_code'] == 'shared_request_refused'


@pytest.mark.parametrize('raw,wrong', [(b'{"success":true}', 'error_shape'),
    (b'{"success":false,"errors":[]}', 'response_shape'), (b'[]', 'error_shape')])
def test_noneligible_diagnostic_fallback_must_match_original_response_semantics(raw, wrong):
    diagnostic = m.error_text.project_error_text(200, raw)
    diagnostic['fallback_code'] = wrong
    m.error_text.validate_error_text(diagnostic)
    with pytest.raises(m.Refused):
        m._validate_error_binding(m.response_evidence.project_response(200, raw), diagnostic)


@pytest.mark.parametrize('missing', ['QC_USER_ID', 'QC_API_TOKEN'])
@pytest.mark.parametrize('value', [None, '', ' ', '\t\r\n'])
def test_nonempty_handoff_guard_precedes_control_claim_and_private_reads(args, monkeypatch, missing, value):
    events = []
    monkeypatch.setenv('QC_USER_ID', 'synthetic-user')
    monkeypatch.setenv('QC_API_TOKEN', 'synthetic-token')
    if value is None:
        monkeypatch.delenv(missing)
    else:
        monkeypatch.setenv(missing, value)
    monkeypatch.setattr(m, '_preflight', lambda *_: events.append('public-preflight'))
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: events.append('environment'))
    def forbidden(*_, **__):
        pytest.fail('missing credential handoff reached a control or private read')
    monkeypatch.setattr(m, 'Store', forbidden)
    monkeypatch.setattr(evidence, 'reconstruct_projection', forbidden)
    with pytest.raises(m.Refused, match='^credential_handoff$'):
        m._execute(args, 600)
    assert events == ['public-preflight', 'environment']


def test_nonempty_handoff_presence_has_no_authentication_or_dispatch_side_effect(monkeypatch):
    monkeypatch.setenv('QC_USER_ID', ' synthetic-user ')
    monkeypatch.setenv('QC_API_TOKEN', ' synthetic-token ')
    assert m._require_credential_handoff() is None
    assert m.profile_record()['credential_presence_proves_authentication'] is False


def test_handoff_guard_does_not_coerce_hostile_or_nonstring_values(monkeypatch):
    class Hostile(str):
        def strip(self, *_):
            pytest.fail('hostile string was called')
    for value in (False, 1, object(), Hostile('synthetic-token')):
        monkeypatch.setattr(m.os, 'environ', {'QC_USER_ID': 'synthetic-user', 'QC_API_TOKEN': value})
        with pytest.raises(m.Refused, match='^credential_handoff$'):
            m._require_credential_handoff()


def test_valid_handoff_guard_is_after_public_preflight_before_store(args, monkeypatch):
    events = []
    original = m._require_credential_handoff
    monkeypatch.setenv('QC_USER_ID', 'synthetic-user')
    monkeypatch.setenv('QC_API_TOKEN', 'synthetic-token')
    monkeypatch.setattr(m, '_preflight', lambda *_: events.append('public-preflight'))
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: events.append('environment'))
    def guard():
        events.append('credential-shape')
        original()
    class SyntheticStop(Exception): pass
    def store(*, create=False, inherited=None):
        assert create is True and inherited is None
        events.append('store')
        raise SyntheticStop()
    monkeypatch.setattr(m, '_require_credential_handoff', guard)
    monkeypatch.setattr(m, 'Store', store)
    with pytest.raises(SyntheticStop):
        m._execute(args, 600)
    assert events == ['public-preflight', 'environment', 'credential-shape', 'store']


@pytest.mark.parametrize('operation', m.WORKERS)
def test_worker_never_runs_parent_credential_shape_guard(args, monkeypatch, operation):
    args.operation, args.control_fd = operation, 10
    monkeypatch.delenv('QC_USER_ID', raising=False)
    monkeypatch.delenv('QC_API_TOKEN', raising=False)
    monkeypatch.setattr(m, '_preflight', lambda *_: None)
    monkeypatch.setattr(environment, 'require_safe_environment', lambda: None)
    def forbidden(*_, **__): pytest.fail('worker called the parent credential guard')
    monkeypatch.setattr(m, '_require_credential_handoff', forbidden)
    monkeypatch.setattr(m, '_worker', lambda supplied, deadline: {'synthetic-worker': operation})
    assert m._execute(args, 600) == {'synthetic-worker': operation}


def test_handoff_failure_envelope_does_not_assert_an_unspent_attempt(args):
    value = {'schema': m.SCHEMA, 'operation': 'recover', 'binding': m.binding(args),
        'operation_completed': False, 'failure_code': 'credential_handoff',
        'failure_observation': None, 'attempt_consumption': 'consumed_or_ambiguous_no_retry',
        **m.FALSE_FLAGS}
    assert m.validate_output(m.canonical(value) + b'\n', 2, args) == value
    value['attempt_consumption'] = 'not_claimed_credential_handoff'
    with pytest.raises(m.Refused):
        m.validate_output(m.canonical(value) + b'\n', 2, args)
