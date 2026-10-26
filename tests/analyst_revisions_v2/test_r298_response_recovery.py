"""Focused synthetic response-observed A7 checks; native remote/artifact denial is required."""
import ast
import copy
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import pytest

from scripts import run_arv2_r298_response_recovery as m
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


def test_profile_scoped_additional_attempt_not_renewed_ceiling():
    value = m.profile_record()
    assert value['attempt_id'] == 7 and value['additional_attempts'] == 1
    assert value['ordinary_attempt_ceiling'] == 3 and value['owner_additional_attempt_required']
    assert value['independent_review_or_exact_waiver_required'] and value['actual_parent_exit_zero_required']
    assert value['deadline_seconds'] == 600 and value['max_application_dispatches'] == 64
    assert value['compile_poll_limit'] == 20 and value['compile_interval_seconds'] == 10
    assert value['status_poll_limit'] == 1 and value['status_interval_seconds'] == 60
    assert value['max_output_bytes'] == value['max_failure_observation_bytes'] == 96 * 1024
    assert value['worker_max_output_bytes'] == 24 * 1024
    assert value['prelaunch_reserve_seconds'] == 90 and value['automatic_retry'] is False
    assert value['old_a2_a3_reconciliation_control_reads'] is False and value['a1_a2_a3_a4_a5_a6_remain_spent']
    assert value['fresh_family_and_d15_admission_reads'] is True
    assert value['shared_look'] == value['development_look'] == 1
    assert all(value[key] is False for key in m.FALSE_FLAGS)
    assert 'A7' in value['backtest_name'] and 'R319-20261024-A' in value['control']
    assert value['spent_predecessor_contract'] == 'arv2-r298-access-recovery-v1'
    assert value['external_manual_backtest_make_public_observation_required_before_freeze'] is True
    assert value['privacy_boundary'] == 'authenticated_pinned_owner_org_and_dedicated_collaborator_acl'
    assert value['privacy_basis'] == 'documented_private_default_plus_no_sharing_operations'
    assert value['project_public_field_required'] is False and value['missing_public_means_private'] is False
    assert value['historical_or_global_privacy_proven'] is False and value['sharing_operation_allowed'] is False
    assert value['immediate_terminal_create_receipt_retained'] is True
    assert value['immediate_terminal_create_status_poll'] is False
    assert value['access_policy'] == 'arv2-r298-collaborator-access-v1'
    assert value['reused_environment_label'] == 'same_observed_a5_code_source_id_not_attempt_identity'
    assert value['code_source_id'] == 'Codex ARV2 R298 A5 20261024'
    assert value['old_mia_row_accepted'] is False
    assert value['owner_row_sha256'] == m.remote.access.OWNER_ROW_SHA256
    assert value['extra_row_sha256'] == m.remote.access.A5_ROW_SHA256
    for selected in ('newrule_owner_recovery/R312-20261024-A',
        'newrule_privacy_recovery/R313-20261024-A', 'newrule_lock_access/R314-20261024-A',
        'newrule_access_recovery/R315-20261024-A', 'newrule_file_effect/R316-20261024-A'):
        assert any(selected in str(path) for path in m.OLD_CONTROLS)
    assert '(deny network*)' in m.SANDBOX
    assert all(f'(deny file-read* (subpath "{path}"))' in m.SANDBOX for path in m.OLD_CONTROLS)


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
    sources = {name: ('# synthetic exact ' + name + '\n').encode('ascii') for name in m.remote.SOURCE_NAMES}
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
            result = {'projectId': m.PROJECT, 'compileId': 'compile-a7'}
        elif endpoint == 'compile/read':
            result = {'projectId': m.PROJECT, 'compileId': payload['compileId'], 'state': state.compile_state}
        elif endpoint == 'projects/nodes/read':
            result = {'autoSelectNode': True, 'nodes': {'backtest': [{'active': False, 'busy': state.busy}]}}
        elif endpoint == 'backtests/create':
            row = {'projectId': m.PROJECT, 'name': payload['backtestName'], 'backtestId': 'run-a7', 'status': 'In Queue...'}
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
    state.runner = m.remote.OwnerRecovery(projection, pin, request, journal, observe)
    return state


def test_exact_nine_changes_and_all_twenty_polls_fit_dispatch_ceiling(cloud):
    runner = cloud.runner
    original = runner.inspect()
    complete = runner.complete(original)
    assert len(complete['files']) == 11 and cloud.files == {key: raw.decode('ascii') for key, raw in cloud.sources.items()}
    assert sum(endpoint == 'files/create' for endpoint, _ in cloud.calls) == 7
    assert sum(endpoint == 'files/update' for endpoint, _ in cloud.calls) == 2
    compiled = runner.compile_once(complete)
    for index in range(20):
        runner.poll_compile(compiled['compile_id'], index)
    launched = runner.launch_once(compiled['compile_id'])
    assert launched['backtest_name'] == m.BACKTEST_NAME and ' A7 ' in launched['backtest_name']
    assert runner.read_status(launched, 0)['status'] == 'In Queue...'
    assert len(cloud.calls) == 60 < m.MAX_DISPATCH
    assert len(cloud.observations) == 4 and all(value['boolean_value'] is False for _, value in cloud.observations)
    assert all(payload['projectId'] == m.PROJECT for _, payload in cloud.calls)
    assert not any(' A3 ' in str(payload) for _, payload in cloud.calls)
    assert sum(endpoint == 'backtests/create' for endpoint, _ in cloud.calls) == 1


@pytest.mark.parametrize('value', [True, None, 0, 'false', [], {}])
def test_non_false_is_durably_observed_before_guard_and_any_source_access(cloud, value):
    cloud.project['codeRunning'] = value
    with pytest.raises(m.remote.RecoveryError, match='access_idle'):
        cloud.runner.inspect()
    assert len(cloud.observations) == 1 and [endpoint for endpoint, _ in cloud.calls] == ['projects/read', 'projects/collaboration/read']


def test_missing_observed_before_unchanged_guard(cloud):
    del cloud.project['codeRunning']
    with pytest.raises(m.remote.RecoveryError, match='access_idle'):
        cloud.runner.inspect()
    assert cloud.observations[0][1]['kind'] == 'missing'


def test_observation_failure_blocks_source_and_guard_progress(cloud):
    def refuse(*_):
        raise m.Refused('journal')
    cloud.runner._observe = refuse
    with pytest.raises(m.Refused, match='journal'):
        cloud.runner.inspect()
    assert [endpoint for endpoint, _ in cloud.calls] == ['projects/read']


@pytest.mark.parametrize('field,value,code', [('owner', False, 'access_owner'),
    ('name', 'wrong', 'access_name'), ('language', 'C#', 'access_language'),
    ('collaborators', [{'owner': False}], 'access_owner_row_match')])
def test_inherited_other_ownership_gates_unchanged(cloud, field, value, code):
    cloud.project[field] = value
    with pytest.raises(m.remote.RecoveryError, match=code):
        cloud.runner.inspect()
    assert not any(endpoint.startswith('files/') for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('public', ['absent', False])
def test_supported_privacy_boundary_requires_positive_dedicated_acl(cloud, public):
    if public != 'absent':
        cloud.project['public'] = public
    cloud.runner.inspect()
    endpoints = [endpoint for endpoint, _ in cloud.calls]
    assert endpoints[:3] == ['projects/read', 'projects/collaboration/read', 'backtests/list']
    assert endpoints.index('projects/collaboration/read') < endpoints.index('files/read')


@pytest.mark.parametrize('public', [True, None, 0, 1, 'false', [], {}])
def test_unexpected_contradictory_public_field_still_refuses(cloud, public):
    cloud.project['public'] = public
    with pytest.raises(m.remote.RecoveryError, match='access_public_contradiction'):
        cloud.runner.inspect()
    assert [endpoint for endpoint, _ in cloud.calls] == ['projects/read', 'projects/collaboration/read']


def test_prior_run_refuses_before_source_access(cloud):
    cloud.prior = [{'backtestId': 'earlier'}]
    with pytest.raises(m.remote.RecoveryError, match='prior_backtests'):
        cloud.runner.inspect()
    assert not any(endpoint.startswith('files/') for endpoint, _ in cloud.calls)


def test_unexpected_cloud_bytes_never_overwritten(cloud):
    cloud.files['main.py'] = '# user work'
    with pytest.raises(m.remote.RecoveryError, match='unexpected_cloud_content'):
        cloud.runner.inspect()
    assert not any(endpoint in ('files/create', 'files/update') for endpoint, _ in cloud.calls)


def test_capacity_busy_no_launch_or_other_project_change(cloud):
    cloud.files = {name: raw.decode('ascii') for name, raw in cloud.sources.items()}
    cloud.busy = True
    cloud.runner.inspect()
    assert cloud.runner.launch_once('compile-a7')['state'] == 'wait'
    assert not any(endpoint == 'backtests/create' for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('status', ['In Queue...', 'In Progress...', 'Completed.', 'Runtime Error'])
def test_exact_own_status_only(cloud, status):
    cloud.files = {name: raw.decode('ascii') for name, raw in cloud.sources.items()}
    cloud.runner.inspect()
    launched = cloud.runner.launch_once('compile-a7')
    cloud.prior[-1]['status'] = status
    assert cloud.runner.read_status(launched, 0)['status'] == status
    with pytest.raises(m.remote.RecoveryError):
        cloud.runner.read_status(launched, 0)


def test_a3_receipt_rejected_without_request(cloud):
    receipt = {'project_id': m.PROJECT, 'compile_id': 'old-compile', 'backtest_id': 'old-run',
        'backtest_name': m.BACKTEST_NAME.replace(' A7 ', ' A3 '), 'projection_sha256': m.remote.PROJECTION_SHA256, 'status': 'In Queue...'}
    with pytest.raises(m.remote.RecoveryError, match='launch_receipt'):
        cloud.runner.read_status(receipt, 0)
    assert cloud.calls == []


def test_exact_inherited_gate_methods_and_genuine_projection():
    from scripts import arv2_r298_final_recovery_remote as frozen_remote
    for name in ('compile_once', 'poll_compile', '_files', '_event', '_compile_state'):
        assert getattr(m.remote.OwnerRecovery, name) is getattr(frozen_remote.FinalRecovery, name)
    projected = evidence.reconstruct_projection()
    def forbidden(*_):
        pytest.fail('pure construction dispatched')
    m.remote.OwnerRecovery(projected, m.remote.ORGANIZATION_SHA256, forbidden, forbidden, forbidden)
    assert projected.projection_sha256 == m.remote.PROJECTION_SHA256


def test_selected_source_pins_match_public_files():
    pins = m.selected_pins()
    assert len(pins) == 84
    from scripts import run_arv2_r298_privacy_recovery as spent_a5
    assert all(pins[name] == digest for name, digest in spent_a5.selected_pins().items())
    assert pins['scripts/arv2_r298_collaborator_access.py'] == '57333e2d6932f3b75bb42bc59214ebda2ce9afdf65b9054b7edc7ee5cbd37d93'
    assert pins['scripts/run_arv2_r298_privacy_recovery.py'] == '98ce1ee2a2d8a54523e383d9ca578575ad2c2510a171f2d772e2144de92d0e98'
    for name, digest in pins.items():
        assert m.sha((m.ROOT / name).read_bytes()) == digest


def test_no_old_operational_entrypoints_or_global_assignment():
    tree = ast.parse(m.SOURCE.read_text())
    forbidden = {'main', '_execute', '_recover', '_worker', '_child', '_workflow', '_reconciliation'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert not (isinstance(node.func.value, ast.Name) and node.func.value.id == 'a3' and node.func.attr in forbidden)
        if isinstance(node, ast.Assign):
            assert not any(isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                and target.value.id in ('a3', 'previous', 'remote', 'v5', 'frozen') for target in node.targets)


@pytest.fixture
def workflow(monkeypatch, args, leaf, cloud):
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


def test_actual_caller_workflow_with_synthetic_transport(args, leaf, workflow):
    result = m._execute(args, 600)
    assert result['result']['terminal'] == 'own_status_observed'
    assert result['result']['application_dispatch_count'] == 41
    assert result['result']['provider_request_count'] is None
    assert workflow.events == list(m.WORKERS) and workflow.sleeps == [10, 60]
    assert (leaf / 'report.json').exists() and (leaf / 'idle-inspect-project.json').exists()
    assert all(value is False for key, value in m.parse((leaf / 'report.json').read_bytes()).items() if key in m.FALSE_FLAGS)
    envelope = {'schema': m.SCHEMA, 'operation': 'recover', 'binding': m.binding(args),
        'result': result, 'operation_completed': True, **m.FALSE_FLAGS}
    assert m.validate_output(m.canonical(envelope) + b'\n', 0, args) == envelope


def test_distinct_a7_claim_launch_retains_exact_existing_a5_environment(args, leaf, workflow):
    result = m._execute(args, 600)
    claim = m.parse((leaf / 'claim.json').read_bytes())
    assert claim['schema'] == 'arv2-r298-response-recovery-v1' and claim['attempt_id'] == 7
    assert result['result']['launch']['backtest_name'] == m.remote.BACKTEST_NAME == m.BACKTEST_NAME
    assert ' A7 ' in result['result']['launch']['backtest_name']
    assert sum(endpoint == 'backtests/create' for endpoint, _ in workflow.cloud.calls) == 1
    assert all(payload['codeSourceId'] == 'Codex ARV2 R298 A5 20261024'
        for endpoint, payload in workflow.cloud.calls if endpoint.startswith('files/')
        or endpoint == 'projects/collaboration/lock/acquire')
    assert m.SOURCE.name == 'run_arv2_r298_response_recovery.py'
    assert m.profile_record()['a1_a2_a3_a4_a5_a6_remain_spent'] is True


@pytest.mark.parametrize('change,reason', [('historical_mia', 'access_extra_row_shape'),
    ('unreported_extra', 'access_extra_row_pin'), ('owner_extra', 'access_owner_row_pin')])
def test_caller_refuses_changed_pinned_access_before_lock_or_files(args, workflow, change, reason):
    if change == 'historical_mia':
        workflow.cloud.project['collaborators'][1]['name'] = 'Mia'
    elif change == 'unreported_extra':
        workflow.cloud.project['collaborators'][1]['syntheticUnreported'] = 'changed'
    else:
        workflow.cloud.dedicated['collaborators'][0]['syntheticUnreported'] = 'changed'
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    result = m.failure_observation(error.value)
    assert result['helper_code'] == reason and result['application_dispatch_count'] == 2
    assert result['launch_receipt'] is result['status_receipt'] is None
    assert [endpoint for endpoint, _ in workflow.cloud.calls] == ['projects/read', 'projects/collaboration/read']


@pytest.mark.parametrize('status', ['Completed.', 'Runtime Error'])
def test_immediate_terminal_create_retains_receipt_without_status_poll(args, leaf, workflow, status):
    def mutate(endpoint, payload, response):
        if endpoint == 'backtests/create':
            response['backtest']['status'] = status
    workflow.cloud.mutation = mutate
    if status == 'Completed.':
        result = m._execute(args, 600)
        assert result['result']['terminal'] == 'create_terminal_observed'
        assert result['result']['launch'] == result['result']['status']
        envelope = outer_success(args, result['result'])
        assert m.validate_output(m.canonical(envelope) + b'\n', 0, args) == envelope
        assert workflow.events == list(m.WORKERS)
    else:
        with pytest.raises(m.ObservedFailure) as error:
            m._execute(args, 600)
        observation = m.failure_observation(error.value)
        assert observation['code'] == 'runtime_failed'
        assert observation['launch_receipt']['status'] == 'Runtime Error'
        assert observation['launch_receipt']['backtest_id'] == 'run-a7'
        assert observation['status_receipt'] is None
        assert workflow.events == list(m.WORKERS[:2])
        value = {'schema': m.SCHEMA, 'operation': 'recover', 'binding': m.binding(args),
            'operation_completed': False, 'failure_code': observation['code'],
            'failure_observation': observation, 'attempt_consumption': 'consumed_or_ambiguous_no_retry',
            **m.FALSE_FLAGS}
        assert m.validate_output(m.canonical(value) + b'\n', 2, args) == value
        with pytest.raises(m.Refused):
            m.validate_output(m.canonical(value) + b'\n', 0, args)
    assert workflow.sleeps == [10]
    assert (leaf / 'launch-receipt.json').exists() and not (leaf / 'own-status.json').exists()
    assert sum(endpoint == 'backtests/create' for endpoint, _ in workflow.cloud.calls) == 1
    assert not any(name.startswith('rpc-own-status') for name in os.listdir(leaf))


@pytest.mark.parametrize('failed_file', ['launch-receipt.json', 'own-status.json', 'report.json'])
def test_known_launch_receipt_survives_later_publication_failure(args, workflow, monkeypatch, failed_file):
    original = m.Store.write
    def fail(self, name, value):
        if name == failed_file:
            raise m.Refused('control_changed')
        return original(self, name, value)
    monkeypatch.setattr(m.Store, 'write', fail)
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    observation = m.failure_observation(error.value)
    assert observation['launch_receipt']['backtest_id'] == 'run-a7'
    assert (observation['status_receipt'] is None) == (failed_file == 'launch-receipt.json')
    assert sum(endpoint == 'backtests/create' for endpoint, _ in workflow.cloud.calls) == 1


@pytest.mark.parametrize('operation', m.WORKERS)
def test_fresh_admission_failure_stops_at_exact_stage(args, workflow, operation):
    workflow.child_error = operation
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    result = m.failure_observation(error.value)
    assert result['code'] == 'input_admission'
    if operation == m.WORKERS[0]:
        assert workflow.cloud.calls == []
    elif operation == m.WORKERS[1]:
        assert not any(endpoint == 'backtests/create' for endpoint, _ in workflow.cloud.calls)
    else:
        assert sum(endpoint == 'backtests/create' for endpoint, _ in workflow.cloud.calls) == 1


def test_actual_failure_envelope_retains_typed_true_and_dispatch(args, leaf, workflow):
    workflow.cloud.project['codeRunning'] = True
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    result = m.failure_observation(error.value)
    assert result['helper_code'] == 'access_idle' and result['application_dispatch_count'] == 2
    assert result['code_running'] == {'present': True, 'kind': 'boolean', 'boolean_value': True}
    assert result['intent_marker'] == 'inspect-collaborators' and result['last_event'] == 'observed'
    assert (leaf / 'idle-inspect-project.json').exists() and (leaf / 'failure.json').exists()
    assert [endpoint for endpoint, _ in workflow.cloud.calls] == ['projects/read', 'projects/collaboration/read']


@pytest.mark.parametrize('stage', ['postflight', 'report'])
def test_late_failure_retains_context_even_with_failed_failure_write(args, workflow, monkeypatch, stage):
    calls = []
    def preflight(*_):
        calls.append(1)
        if stage == 'postflight' and len(calls) == 2:
            raise m.Refused('source')
    monkeypatch.setattr(m, '_preflight', preflight)
    write = m.Store.write
    def failing_write(self, name, value):
        if name == 'failure.json' or (stage == 'report' and name == 'report.json'):
            raise m.Refused('control_changed')
        return write(self, name, value)
    monkeypatch.setattr(m.Store, 'write', failing_write)
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    result = m.failure_observation(error.value)
    assert result['last_stage'] == 'report' and result['application_dispatch_count'] == 41
    assert result['code_running']['boolean_value'] is False and result['endpoint'] == 'backtests/list'


@pytest.mark.parametrize('condition,code', [('compile_error', 'compile_failed'), ('poll_budget', 'compile_budget'),
    ('prelaunch_reserve', 'deadline'), ('runtime_error', 'runtime_failed')])
def test_terminal_bounds_no_second_launch(args, workflow, monkeypatch, condition, code):
    if condition == 'compile_error':
        workflow.cloud.compile_state = 'BuildError'
    elif condition == 'poll_budget':
        workflow.cloud.compile_state = 'Building'
    elif condition == 'prelaunch_reserve':
        child = m._child
        def late_child(*values):
            result = child(*values)
            if values[-1] == 'admission-launch-worker':
                workflow.now = 510
            return result
        monkeypatch.setattr(m, '_child', late_child)
    else:
        def mutate(endpoint, payload, response):
            if endpoint == 'backtests/list' and len(response['backtests']) == 2:
                response['backtests'][-1]['status'] = 'Runtime Error'
        workflow.cloud.mutation = mutate
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    assert m.failure_observation(error.value)['code'] == code
    launches = sum(endpoint == 'backtests/create' for endpoint, _ in workflow.cloud.calls)
    assert launches == (1 if condition == 'runtime_error' else 0)
    if condition == 'poll_budget':
        assert workflow.sleeps == [10] * 20


def test_busy_capacity_reports_wait_without_status_or_retry(args, workflow):
    workflow.cloud.busy = True
    value = m._execute(args, 600)
    assert value['result']['terminal'] == 'capacity_wait'
    assert workflow.sleeps == [10] and workflow.events == list(m.WORKERS)
    assert not any(endpoint == 'backtests/create' for endpoint, _ in workflow.cloud.calls)


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
    'scripts/arv2_r298_privacy_recovery_remote.py', 'scripts/run_arv2_r298_response_recovery.py',
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
def success(args):
    receipt = {'project_id': m.PROJECT, 'compile_id': 'compiled', 'backtest_id': 'launched',
        'backtest_name': m.BACKTEST_NAME, 'status': 'In Queue...', 'projection_sha256': m.remote.PROJECTION_SHA256}
    result = {'terminal': 'own_status_observed', 'launch': receipt,
        'status': {**receipt, 'status': 'In Progress...'}, 'application_dispatch_count': 42,
        'provider_request_count': None, 'response_observation': None,
        'code_running': {'present': True, 'kind': 'boolean', 'boolean_value': False}}
    return outer_success(args, result)


def test_pure_output_success_authenticates_actual_result_report_and_exit(args, success):
    raw = m.canonical(success) + b'\n'
    assert m.validate_output(raw, 0, args) == success


def test_pure_output_accepts_only_finite_capacity_wait(args):
    result = {'terminal': 'capacity_wait', 'project_id': m.PROJECT, 'compile_id': 'compiled',
        'application_dispatch_count': 35, 'provider_request_count': None, 'response_observation': None,
        'code_running': {'present': True, 'kind': 'boolean', 'boolean_value': False}}
    value = outer_success(args, result)
    assert m.validate_output(m.canonical(value) + b'\n', 0, args) == value


@pytest.mark.parametrize('mutation', ['valid', 'runtime', 'queue', 'different_status', 'wrong_terminal', 'manual_id'])
def test_create_terminal_output_is_exact_completed_receipt_only(args, success, mutation):
    result = success['result']['result']
    result['terminal'] = 'create_terminal_observed'
    result['launch']['status'] = result['status']['status'] = 'Completed.'
    if mutation == 'runtime':
        result['launch']['status'] = result['status']['status'] = 'Runtime Error'
    elif mutation == 'queue':
        result['launch']['status'] = result['status']['status'] = 'In Queue...'
    elif mutation == 'different_status':
        result['status']['status'] = 'In Progress...'
    elif mutation == 'wrong_terminal':
        result['terminal'] = 'own_status_observed'
    elif mutation == 'manual_id':
        result['launch']['backtest_id'] = result['status']['backtest_id'] = m.remote.MANUAL_BACKTEST_ID
    value = outer_success(args, result)
    if mutation == 'valid':
        assert m.validate_output(m.canonical(value) + b'\n', 0, args) == value
    else:
        with pytest.raises((m.Refused, m.remote.RecoveryError)):
            m.validate_output(m.canonical(value) + b'\n', 0, args)


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


@pytest.mark.parametrize('mutation', ['terminal', 'extra', 'dispatch_bool', 'dispatch_zero', 'dispatch_over',
    'provider_count', 'code_running_true', 'code_running_missing', 'a3_name', 'project', 'compile_id',
    'launch_runtime_error', 'launch_extra', 'status_runtime_error', 'status_completed_spelling', 'status_run_id',
    'status_name', 'status_project', 'status_extra', 'projection', 'manual_id'])
def test_output_result_rejects_mutation_even_with_recomputed_report(args, success, mutation):
    result = success['result']['result']
    if mutation == 'terminal':
        result['terminal'] = 'unknown'
    elif mutation == 'extra':
        result['extra'] = True
    elif mutation.startswith('dispatch'):
        result['application_dispatch_count'] = {'dispatch_bool': True, 'dispatch_zero': 0, 'dispatch_over': 65}[mutation]
    elif mutation == 'provider_count':
        result['provider_request_count'] = 0
    elif mutation == 'code_running_true':
        result['code_running']['boolean_value'] = True
    elif mutation == 'code_running_missing':
        result['code_running'] = {'present': False, 'kind': 'missing', 'boolean_value': None}
    elif mutation == 'a3_name':
        result['launch']['backtest_name'] = m.BACKTEST_NAME.replace(' A7 ', ' A3 ')
    elif mutation == 'project':
        result['launch']['project_id'] += 1
    elif mutation == 'compile_id':
        result['launch']['compile_id'] = 'bad/compile'
    elif mutation == 'launch_runtime_error':
        result['launch']['status'] = 'Runtime Error'
    elif mutation == 'launch_extra':
        result['launch']['extra'] = True
    elif mutation == 'projection':
        result['launch']['projection_sha256'] = 'd' * 64
    elif mutation == 'manual_id':
        result['launch']['backtest_id'] = result['status']['backtest_id'] = m.remote.MANUAL_BACKTEST_ID
    elif mutation == 'status_runtime_error':
        result['status']['status'] = 'Runtime Error'
    elif mutation == 'status_completed_spelling':
        result['status']['status'] = 'Completed'
    elif mutation == 'status_run_id':
        result['status']['backtest_id'] = 'other-run'
    elif mutation == 'status_name':
        result['status']['backtest_name'] = 'other-name'
    elif mutation == 'status_project':
        result['status']['project_id'] = True
    else:
        result['status']['extra'] = True
    value = outer_success(args, result)
    with pytest.raises((m.Refused, m.previous.Refused, m.remote.RecoveryError)):
        m.validate_output(m.canonical(value) + b'\n', 0, args)


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


@pytest.mark.parametrize('mutation', ['valid', 'manual_id', 'wrong_name', 'wrong_project',
    'unknown_status', 'extra', 'unpaired_status', 'mismatched_status_identity', 'missing_field'])
def test_failure_receipts_retained_but_strictly_bound(args, failure, mutation):
    observation = failure['failure_observation']
    receipt = {'project_id': m.PROJECT, 'compile_id': 'compile-a7', 'backtest_id': 'run-a7',
        'backtest_name': m.BACKTEST_NAME, 'status': 'Runtime Error',
        'projection_sha256': m.remote.PROJECTION_SHA256}
    observation['launch_receipt'] = receipt
    if mutation == 'manual_id':
        receipt['backtest_id'] = m.remote.MANUAL_BACKTEST_ID
    elif mutation == 'wrong_name':
        receipt['backtest_name'] = m.BACKTEST_NAME.replace(' A7 ', ' A4 ')
    elif mutation == 'wrong_project':
        receipt['project_id'] = True
    elif mutation == 'unknown_status':
        receipt['status'] = 'private text'
    elif mutation == 'extra':
        receipt['extra'] = 'private text'
    elif mutation == 'unpaired_status':
        observation['status_receipt'] = receipt
        observation['launch_receipt'] = None
    elif mutation == 'mismatched_status_identity':
        observation['status_receipt'] = {**receipt, 'backtest_id': 'other-run'}
    elif mutation == 'missing_field':
        del observation['status_receipt']
    raw = m.canonical(failure) + b'\n'
    if mutation == 'valid':
        assert m.validate_output(raw, 2, args) == failure
    else:
        with pytest.raises((m.Refused, m.remote.RecoveryError)):
            m.validate_output(raw, 2, args)


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


def request_shapes():
    base = {'projectId': m.PROJECT}
    code = {**base, 'codeSourceId': m.remote.CODE_SOURCE_ID}
    return {
        'projects/read': base, 'projects/collaboration/read': base,
        'projects/collaboration/lock/acquire': code, 'projects/nodes/read': base,
        'files/read': code,
        'files/create': {**code, 'name': 'main.py', 'content': '# synthetic\n'},
        'files/update': {**code, 'name': 'main.py', 'content': '# synthetic\n'},
        'compile/create': base, 'compile/read': {**base, 'compileId': 'compile-a7'},
        'backtests/list': {**base, 'includeStatistics': False},
        'backtests/create': {**base, 'compileId': 'compile-a7', 'backtestName': m.BACKTEST_NAME},
    }


def test_new_narrow_client_exact_payloads_and_environment(narrow_client):
    _, _, events = narrow_client
    before = environment.ENDPOINTS
    client = m.OwnerClient(lambda _: None)
    assert events == ['environment', 'construct', 'environment']
    assert repr(client) == '<ResponseObservedR298Client>'
    assert set(request_shapes()) == m.remote.ENDPOINTS
    for endpoint, payload in request_shapes().items():
        assert client.request(endpoint, payload) == {'success': True}
    assert environment.ENDPOINTS is before
    assert 'projects/collaboration/lock/acquire' not in environment.ENDPOINTS
    assert sum(type(event) is tuple for event in events) == len(request_shapes())


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


@pytest.mark.parametrize('endpoint', ['projects/collaboration/read', 'projects/collaboration/lock/acquire'])
def test_new_endpoint_failure_context_is_finite_and_validated(args, endpoint):
    state = {**m.a3._new_state(), 'last_stage': 'inspect', 'intent_marker': 'inspect-lock',
        'endpoint': endpoint, 'last_event': 'failure', 'application_dispatch_count': 4,
        'category': 'http_failure', 'http_status': 403,
        'code_running': {'present': True, 'kind': 'boolean', 'boolean_value': False}}
    result = m._failure(m.remote.RecoveryError('request_ambiguous'), state)
    assert result['endpoint'] == endpoint and result['application_dispatch_count'] == 4
    assert result['http_status'] == 403 and result['provider_request_count'] is None
    value = {'schema': m.SCHEMA, 'operation': 'recover', 'binding': m.binding(args),
        'operation_completed': False, 'failure_code': result['code'], 'failure_observation': result,
        'attempt_consumption': 'consumed_or_ambiguous_no_retry', **m.FALSE_FLAGS}
    assert m.validate_output(m.canonical(value) + b'\n', 2, args) == value


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


def test_real_boundary_in_actual_caller_preserves_success_and_exact_journal_pin(args, leaf, workflow, response_workflow):
    result = m._execute(args, 600)
    observation = result['result']['response_observation']
    assert observation['endpoint'] == 'files/update' and observation['target_name'] == m.boundary.TARGET_NAME
    assert observation['evidence']['fields']['success']['boolean_value'] is True
    assert observation['evidence']['remote_effect_known'] is False
    raw = (leaf / 'input-runtime-response.json').read_bytes()
    assert observation['journal_pin'] == {'sha256': m.sha(raw), 'byte_count': len(raw)}
    assert m.parse(raw) == m._response_record(args, observation)
    assert response_workflow.target_calls == 1
    envelope = outer_success(args, result['result'])
    assert m.validate_output(m.canonical(envelope) + b'\n', 0, args) == envelope
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
    assert response_workflow.clients[0]._transport is old.coverage._bounded_transport


@pytest.mark.parametrize('raw,expected,boundary_code', [
    (b'{"success":false,"errors":["SYNTHETIC_PRIVATE_REASON"]}', 'object', 'shared_request_refused'),
    (b'{"errors":["SYNTHETIC_PRIVATE_REASON"]}', 'object', 'shared_request_refused'),
    (b'{"success":"true"}', 'object', 'shared_request_refused'),
    (b'{"success":false,"success":true}', 'duplicate_keys', 'response_not_object'),
    (b'bad', 'invalid_json', 'response_not_object'),
])
def test_real_boundary_failure_retained_and_no_further_write_readback_or_launch(
        args, leaf, workflow, response_workflow, raw, expected, boundary_code):
    response_workflow.raw = raw
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    result = m.failure_observation(error.value)
    observation = result['response_observation']
    assert observation['evidence']['outcome'] == expected
    assert result['response_boundary_code'] == boundary_code and result['http_status'] == 200
    assert result['helper_code'] == 'request_ambiguous'
    assert response_workflow.target_calls == 1
    assert workflow.cloud.calls[-1][0] == 'files/update'
    assert not any(endpoint == 'backtests/create' for endpoint, _ in workflow.cloud.calls)
    assert (leaf / 'input-runtime-response.json').exists()
    assert b'SYNTHETIC_PRIVATE_REASON' not in m.canonical(result)
    value = {'schema': m.SCHEMA, 'operation': 'recover', 'binding': m.binding(args),
        'operation_completed': False, 'failure_code': result['code'], 'failure_observation': result,
        'attempt_consumption': 'consumed_or_ambiguous_no_retry', **m.FALSE_FLAGS}
    assert m.validate_output(m.canonical(value) + b'\n', 2, args) == value


@pytest.mark.parametrize('failed_file', ['input-runtime-response.json', 'report.json', 'failure.json'])
def test_finite_response_survives_publication_failure_without_false_positive(
        args, workflow, response_workflow, monkeypatch, failed_file):
    if failed_file == 'failure.json':
        response_workflow.raw = b'{"success":false,"errors":["SYNTHETIC_PRIVATE_REASON"]}'
    original = m.Store.write
    def write(self, name, value):
        if name == failed_file:
            raise m.Refused('control_changed')
        return original(self, name, value)
    monkeypatch.setattr(m.Store, 'write', write)
    with pytest.raises(m.ObservedFailure) as error:
        m._execute(args, 600)
    result = m.failure_observation(error.value)
    observation = result['response_observation']
    assert observation is not None and observation['evidence']['http_status'] == 200
    assert (observation['journal_pin'] is None) == (failed_file == 'input-runtime-response.json')
    assert response_workflow.target_calls == 1
    assert b'SYNTHETIC_PRIVATE_REASON' not in m.canonical(result)


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
    raw = m.canonical(m._response_record(args, observation))
    observation['journal_pin'] = {'sha256': m.sha(raw), 'byte_count': len(raw)}
    attach_response(failure, observation)
    failure['failure_observation']['response_boundary_code'] = 'shared_request_refused'
    envelope = m.canonical(failure) + b'\n'
    assert len(envelope) > 4096 and len(envelope) < m.MAX_OUTPUT == 96 * 1024
    assert m.WORKER_MAX_OUTPUT == 24 * 1024
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
