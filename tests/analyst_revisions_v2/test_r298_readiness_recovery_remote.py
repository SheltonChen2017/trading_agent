"""Synthetic readiness helper; native network/artifact/Keychain denial required."""
import copy
import json
from types import SimpleNamespace

import pytest

from scripts import arv2_r298_readiness_recovery_remote as m
from scripts import arv2_r298_recovery_evidence as evidence
from scripts import arv2_newrule_execution_environment as environment


@pytest.fixture(autouse=True)
def operational_tripwire(monkeypatch):
    hits = []
    def refuse(*args, **kwargs):
        hits.append('operational')
        raise AssertionError('real operational seam forbidden')
    for module, names in ((m.post_mia, ('main', '_execute', '_recover', '_worker', '_child', '_workflow')),
        (m.post_mia.a3, ('main', '_execute', '_recover', '_worker', '_child', '_workflow', '_reconciliation')),
        (evidence, ('collect_documents',)), (m.post_mia.previous, ('_admission',)),
        (environment, ('guarded_client',))):
        for name in names: monkeypatch.setattr(module, name, refuse)
    yield
    assert hits == []


@pytest.fixture
def cloud(monkeypatch):
    organization = 'a' * 32
    pin = m._sha(organization.encode('ascii'))
    monkeypatch.setattr(m.frozen, 'ORGANIZATION_SHA256', pin)
    monkeypatch.setattr(m.access, 'ORGANIZATION_SHA256', pin)
    monkeypatch.setattr(m.diagnostic.projection, 'ORGANIZATION_SHA256', pin)
    sources = {name: ('# synthetic exact ' + name + '\n').encode('ascii') for name in m.SOURCE_NAMES}
    synthetic_inventory = {'project_id': m.PROJECT_ID, 'projection_sha256': m.PROJECTION_SHA256,
        'files': [{'name': name, 'byte_count': len(raw), 'sha256': m._sha(raw)}
            for name, raw in sorted(sources.items())]}
    monkeypatch.setattr(m, 'SOURCE_MANIFEST_SHA256', m._sha(m._strict_canonical(synthetic_inventory)))
    entries = tuple(SimpleNamespace(project_path=name, source_bytes=raw) for name, raw in sorted(sources.items()))
    manifest = [{'project_path': item.project_path, 'byte_count': len(item.source_bytes),
        'content_sha256': m._sha(item.source_bytes)} for item in entries]
    projection = SimpleNamespace(projection_sha256=m.PROJECTION_SHA256, source_files=entries,
        to_record=lambda: {'candidate_id': m.PROJECTION_CANDIDATE_ID, 'source_files': manifest})
    owner = {'owner': True, 'uid': 123, 'publicId': 'synthetic-owner', 'name': 'Synthetic Owner',
        'permission': 'write', 'liveControl': True}
    extra = {'owner': False, 'uid': None, 'publicId': m.CODE_SOURCE_ID, 'name': m.CODE_SOURCE_ID,
        'permission': 'write', 'liveControl': True, 'test-only-extra': 7}
    monkeypatch.setattr(m.access, 'OWNER_ROW_SHA256', m._sha(m._canonical(owner)))
    monkeypatch.setattr(m.access, 'A5_ROW_SHA256', m._sha(m._canonical(extra)))
    manual = {'projectId': m.PROJECT_ID, 'backtestId': m.MANUAL_BACKTEST_ID,
        'name': m.MANUAL_BACKTEST_NAME, 'status': 'Completed.'}
    state = SimpleNamespace(sources=sources, projection=projection, calls=[], events=[], observations=[],
        access_observations=[], owner=owner, extra=extra, manual=manual, pin=pin,
        files={'main.py': m.frozen.frozen.DEFAULT_MAIN.decode('ascii'),
            'accepted_risk_order_level_input_runtime.py': '#',
            **{name: sources[name].decode('ascii') for name in m.RETAINED_SOURCE_NAMES}},
        prior=[copy.deepcopy(manual)], compile_state='BuildSuccess', mutation=None, sink_failure=False)
    state.project = {'projectId': m.PROJECT_ID, 'organizationId': organization, 'ownerId': 123,
        'name': m.PROJECT_NAME, 'language': 'Py', 'owner': True,
        'codeRunning': False, 'collaborators': [copy.deepcopy(owner)]}
    state.dedicated = {'collaborators': [copy.deepcopy(owner)], 'userPermissions': 'write', 'userLiveControl': True}
    def journal(marker, event):
        assert not any(old == marker and before['event'] == event['event'] for old, before in state.events)
        state.events.append((marker, copy.deepcopy(event)))
    def request(endpoint, payload):
        assert state.events[-1][1] == {'event': 'intent', 'endpoint': endpoint,
            'sha256': m._sha(m._canonical(payload))}
        state.calls.append((endpoint, copy.deepcopy(payload)))
        if endpoint == 'projects/read': result = {'projects': [copy.deepcopy(state.project)]}
        elif endpoint == m.COLLABORATION_ENDPOINT: result = copy.deepcopy(state.dedicated)
        elif endpoint == m.LOCK_ENDPOINT: result = {'errors': []}
        elif endpoint == 'backtests/list':
            result = {'backtests': copy.deepcopy(state.prior), 'count': len(state.prior), 'projectId': m.PROJECT_ID}
        elif endpoint == 'files/read':
            result = {'files': [{'projectId': m.PROJECT_ID, 'name': name, 'content': raw}
                for name, raw in state.files.items()]}
        elif endpoint in ('files/create', 'files/update'):
            assert (payload['name'] in state.files) == (endpoint == 'files/update')
            state.files[payload['name']] = payload['content']
            result = {}
        elif endpoint == 'compile/create': result = {'projectId': m.PROJECT_ID, 'compileId': 'compile-a10'}
        elif endpoint == 'compile/read':
            result = {'projectId': m.PROJECT_ID, 'compileId': payload['compileId'], 'state': state.compile_state}
        else: pytest.fail('forbidden endpoint reached')
        result['success'] = True
        if state.mutation: state.mutation(endpoint, payload, result)
        return result
    def observe(marker, value):
        assert state.events[-1][0] == marker and state.events[-1][1]['event'] == 'observed'
        state.observations.append((marker, copy.deepcopy(value)))
    def access_observation(marker, value):
        assert marker == value['stage'] + '-access'
        assert state.events[-1][0] == value['stage'] + '-collaborators'
        state.access_observations.append((marker, copy.deepcopy(value)))
        if state.sink_failure: raise RuntimeError('private sink failure')
    state.request, state.journal, state.observe, state.access_observation = request, journal, observe, access_observation
    state.runner = m.ReadinessRecovery(projection, pin, request, journal, observe, access_observation)
    return state


def compile_candidate(cloud, polls=1):
    original = cloud.runner.inspect()
    completed = cloud.runner.complete(original)
    compiled = cloud.runner.compile_once(completed)
    for index in range(polls): cloud.runner.poll_compile(compiled['compile_id'], index)
    return original, completed, compiled


def test_contract_retains_frozen_source_policy_and_removes_launch():
    assert m.ATTEMPT == 10 and m.BACKTEST_NAME is None
    assert m.CODE_SOURCE_ID == m.previous.CODE_SOURCE_ID == 'Codex ARV2 R298 A5 20261024'
    assert m.ReadinessRecovery.complete is m.previous.HandoffRecovery.complete
    assert m.ReadinessRecovery.inspect is m.previous.HandoffRecovery.inspect
    assert m.ReadinessRecovery._files is m.previous.HandoffRecovery._files
    assert m.ReadinessRecovery.poll_compile is m.previous.HandoffRecovery.poll_compile
    assert m.access.OWNER_ROW_SHA256 == '707a30618e122e49fe6fa75364451b5b7c50e1019a68a89ffc0cd3ae3c8e0b78'
    assert m.access.A5_ROW_SHA256 == 'f9a933141393262edb66e3e8248ed75ebf4518668039e1a27af6734f26f58b9d'
    assert len(m.SOURCE_NAMES) == 11
    assert m.SOURCE_MANIFEST_SHA256 == '1d2b2d763045256ac0613b07bb8097b92feb7915ea5c4da8ba6d24fbe7b9a453'


def test_complete_compile_readiness_bounded_without_capacity_or_launch(cloud):
    original, completed, compiled = compile_candidate(cloud, polls=20)
    ready = cloud.runner.ready_once(compiled)
    assert len(original['files']) == 4 and len(completed['files']) == 11
    assert len(cloud.calls) == 57 and len(cloud.calls) < 64
    assert ready['compile_id'] == 'compile-a10' and ready['state'] == 'compiled_exact_source_ready'
    assert ready['source_manifest_sha256'] == m._sha(m._canonical(completed))
    assert all(ready[key] is False for key in m.READY_FALSE)
    assert cloud.files == {name: raw.decode('ascii') for name, raw in cloud.sources.items()}
    assert [marker for marker, _ in cloud.access_observations] == [stage + '-access' for stage in m.OWNED_STAGES]
    assert not any(endpoint in ('projects/nodes/read', 'backtests/create', 'backtests/read') for endpoint, _ in cloud.calls)
    writes = [(endpoint, payload) for endpoint, payload in cloud.calls if endpoint in ('files/create', 'files/update')]
    assert len(writes) == len({payload['name'] for _, payload in writes}) == 9
    assert sum(endpoint == 'files/create' for endpoint, _ in writes) == 7
    assert sum(endpoint == 'files/update' for endpoint, _ in writes) == 2
    for index, (endpoint, _) in enumerate(cloud.calls):
        if endpoint in ('files/create', 'files/update'):
            assert cloud.calls[index - 1][0] == cloud.calls[index + 1][0] == 'files/read'


@pytest.mark.parametrize('endpoint', ['projects/nodes/read', 'backtests/create', 'backtests/read',
    'backtests/orders/read', 'backtests/chart/read', 'projects/create', 'files/delete',
    'projects/collaboration/delete', 'projects/collaboration/update'])
def test_forbidden_endpoints_refuse_before_intent(cloud, endpoint):
    with pytest.raises(m.RecoveryError, match='readiness_only'):
        cloud.runner._rpc('forbidden', endpoint, {'projectId': m.PROJECT_ID})
    assert cloud.calls == cloud.events == []


@pytest.mark.parametrize('method', ['launch_once', 'read_status'])
def test_launch_and_status_methods_never_dispatch(cloud, method):
    with pytest.raises(m.RecoveryError, match='readiness_only'):
        getattr(cloud.runner, method)('unused')
    assert cloud.calls == cloud.events == []


@pytest.mark.parametrize('marker', ['status-poll-000', 'launch-backtests', 'any-history', 'ready-backtests-other'])
def test_list_is_only_exact_manual_history_guard(cloud, marker):
    with pytest.raises(m.RecoveryError, match='readiness_only'):
        cloud.runner._rpc(marker, 'backtests/list', {'projectId': m.PROJECT_ID, 'includeStatistics': False})
    assert cloud.calls == cloud.events == []


@pytest.mark.parametrize('kind', ['owner_only', 'owner_and_exact_a5'])
def test_current_strict_owner_or_exact_a5_representation(cloud, kind):
    if kind == 'owner_and_exact_a5': cloud.project['collaborators'].append(copy.deepcopy(cloud.extra))
    cloud.runner.inspect()
    packet = cloud.access_observations[0][1]
    assert packet['project_observation']['collaborators']['count'] == (1 if kind == 'owner_only' else 2)
    assert packet['dedicated_observation']['collaborators']['count'] == 1
    assert packet['project_observation']['public']['json_type'] == 'absent'
    assert all(packet[key] is False for key in m.ACCESS_FALSE)
    raw = m._canonical(packet)
    assert b'Synthetic Owner' not in raw and b'synthetic-owner' not in raw
    assert m.CODE_SOURCE_ID.encode() not in raw
    m.validate_access_observation(packet)


@pytest.mark.parametrize('prefix', ['inspect', 'complete', 'compile', 'ready'])
@pytest.mark.parametrize('change', ['owner_hash', 'extra_hash', 'old_mia', 'third', 'live', 'busy', 'permission'])
def test_access_evidence_saved_before_unchanged_policy_refusal(cloud, prefix, change):
    cloud.project['collaborators'].append(copy.deepcopy(cloud.extra))
    if change == 'owner_hash':
        cloud.dedicated['collaborators'][0]['changed-private'] = True
        cloud.project['collaborators'][0]['changed-private'] = True
    elif change == 'extra_hash': cloud.project['collaborators'][1]['test-only-extra'] = 8
    elif change == 'old_mia': cloud.project['collaborators'][1]['name'] = 'Mia'
    elif change == 'third': cloud.project['collaborators'].append(copy.deepcopy(cloud.extra))
    elif change == 'live': cloud.dedicated['userLiveControl'] = False
    elif change == 'busy': cloud.project['codeRunning'] = True
    else: cloud.dedicated['userPermissions'] = 'read'
    with pytest.raises(m.RecoveryError, match='access_'): cloud.runner._owned(prefix)
    assert [endpoint for endpoint, _ in cloud.calls] == ['projects/read', m.COLLABORATION_ENDPOINT]
    assert len(cloud.access_observations) == 1
    packet = cloud.access_observations[0][1]
    m.validate_access_observation(packet)
    assert b'changed-private' not in m._canonical(packet)


def test_sink_failure_blocks_policy_history_lock_or_write(cloud):
    cloud.sink_failure = True
    with pytest.raises(m.RecoveryError, match='access_observation_sink'): cloud.runner.inspect()
    assert len(cloud.access_observations) == 1
    assert [endpoint for endpoint, _ in cloud.calls] == ['projects/read', m.COLLABORATION_ENDPOINT]


def test_sink_non_none_return_refuses(cloud):
    cloud.runner._access_observation = lambda *_: True
    with pytest.raises(m.RecoveryError, match='access_observation_sink'): cloud.runner.inspect()
    assert len(cloud.calls) == 2


@pytest.mark.parametrize('change', ['new_run', 'missing', 'manual_name', 'manual_status', 'count', 'project'])
def test_manual_only_history_still_refuses_unexpected_runs(cloud, change):
    if change == 'new_run': cloud.prior.append(dict(cloud.manual, backtestId='unexpected'))
    elif change == 'missing': cloud.prior.clear()
    elif change == 'manual_name': cloud.prior[0]['name'] = 'different'
    elif change == 'manual_status': cloud.prior[0]['status'] = 'In Progress...'
    else:
        def mutation(endpoint, payload, response):
            if endpoint == 'backtests/list': response['count' if change == 'count' else 'projectId'] = 999
        cloud.mutation = mutation
    with pytest.raises(m.RecoveryError, match='prior_backtests'): cloud.runner.inspect()
    assert len(cloud.access_observations) == 1
    assert len(cloud.calls) == 3


@pytest.mark.parametrize('key,value', [('projectId', 99), ('success', False), ('errors', ['private-error'])])
def test_access_snapshot_rejects_response_contradictions(cloud, key, value):
    def mutation(endpoint, payload, response):
        if endpoint == m.COLLABORATION_ENDPOINT: response[key] = value
    cloud.mutation = mutation
    with pytest.raises(m.RecoveryError): cloud.runner.inspect()
    assert len(cloud.calls) == 2 and cloud.access_observations == []


def test_ready_requires_locally_created_compile_receipt_before_request(cloud):
    with pytest.raises(m.RecoveryError, match='readiness_compile_binding'): cloud.runner.ready_once({})
    assert cloud.calls == []
    with pytest.raises(m.RecoveryError, match='readiness_used'): cloud.runner.ready_once({})


@pytest.mark.parametrize('key,value', [('compile_id', 'forged'), ('source_manifest_sha256', '0' * 64),
    ('project_id', True), ('projection_sha256', '0' * 64)])
def test_ready_binds_full_created_compile_receipt(cloud, key, value):
    _, _, compiled = compile_candidate(cloud)
    compiled[key] = value
    count = len(cloud.calls)
    with pytest.raises(m.RecoveryError, match='readiness_compile_binding'): cloud.runner.ready_once(compiled)
    assert len(cloud.calls) == count


@pytest.mark.parametrize('state', ['InQueue', 'Building', 'BuildError', 'Completed.', None])
def test_ready_requires_fresh_build_success(cloud, state):
    _, _, compiled = compile_candidate(cloud)
    cloud.compile_state = state
    count = len(cloud.calls)
    with pytest.raises(m.RecoveryError): cloud.runner.ready_once(compiled)
    assert [endpoint for endpoint, _ in cloud.calls[count:]] == ['compile/read']


@pytest.mark.parametrize('change', ['missing', 'placeholder', 'unknown', 'source_drift'])
def test_ready_reauthenticates_all_exact_source_files(cloud, change):
    _, _, compiled = compile_candidate(cloud)
    if change == 'missing': del cloud.files['main.py']
    elif change == 'placeholder': cloud.files['main.py'] = '#'
    elif change == 'unknown': cloud.files['unknown.py'] = '#'
    else: cloud.files['main.py'] = '# different source'
    count = len(cloud.calls)
    with pytest.raises(m.RecoveryError): cloud.runner.ready_once(compiled)
    assert [endpoint for endpoint, _ in cloud.calls[count:]] == [
        'compile/read', 'projects/read', m.COLLABORATION_ENDPOINT, 'backtests/list', 'files/read']


def test_ready_manifest_bound_separately_from_file_count(cloud, monkeypatch):
    _, _, compiled = compile_candidate(cloud)
    original = cloud.runner._files
    def altered(marker, **kwargs):
        value = original(marker, **kwargs)
        value['files'][0]['sha256'] = '0' * 64
        return value
    monkeypatch.setattr(cloud.runner, '_files', altered)
    with pytest.raises(m.RecoveryError, match='readiness_manifest'): cloud.runner.ready_once(compiled)


def test_duplicate_compile_and_ready_never_dispatch_again(cloud):
    _, completed, compiled = compile_candidate(cloud)
    count = len(cloud.calls)
    with pytest.raises(m.RecoveryError, match='readiness_compile_binding'): cloud.runner.compile_once(completed)
    assert len(cloud.calls) == count
    cloud.runner.ready_once(compiled)
    count = len(cloud.calls)
    with pytest.raises(m.RecoveryError, match='readiness_used'): cloud.runner.ready_once(compiled)
    assert len(cloud.calls) == count


@pytest.mark.parametrize('mutation', ['schema', 'stage', 'project', 'raw', 'gate', 'hash',
    'comparison', 'policy_comparison', 'known_a5_hash'])
def test_access_finite_packet_forgery_refuses(cloud, mutation):
    cloud.runner.inspect()
    value = copy.deepcopy(cloud.access_observations[0][1])
    if mutation == 'schema': value['schema'] = 'old'
    elif mutation == 'stage': value['stage'] = 'launch'
    elif mutation == 'project': value['project_id'] = True
    elif mutation == 'raw': value['raw'] = 'private'
    elif mutation == 'gate': value['collaborator_policy_accepted'] = True
    elif mutation == 'hash': value['project_response_sha256'] = 'private'
    elif mutation == 'comparison': value['comparison']['project_count'] = 3
    elif mutation == 'policy_comparison': value['comparison_to_frozen_policy']['project_rows'][0]['equals_frozen_owner_row'] = True
    else:
        value['project_observation']['collaborators']['records'][0]['row_sha256'] = m.diagnostic.A5_ROW_SHA256
        value['dedicated_observation']['collaborators']['records'][0]['row_sha256'] = m.diagnostic.A5_ROW_SHA256
        result = m._access_result(value['project_observation'], value['dedicated_observation'])
        value['comparison'] = result['comparison']
        value['comparison_to_frozen_policy'] = m.diagnostic.policy_comparison(result)
    with pytest.raises(m.RecoveryError): m.validate_access_observation(value)


@pytest.mark.parametrize('key,value', [('schema', 'old'), ('project_id', True), ('attempt', 9),
    ('compile_id', 'bad id'), ('projection_sha256', '0' * 64), ('source_manifest_sha256', 'bad'),
    ('source_manifest_sha256', '0' * 64),
    ('state', 'running'), ('backtest_created', True), ('capacity_observed', True),
    ('launch_authorized', True), ('strategy_result_accepted', True)])
def test_readiness_receipt_has_no_launch_or_result_acceptance(cloud, key, value):
    _, _, compiled = compile_candidate(cloud)
    receipt = cloud.runner.ready_once(compiled)
    receipt[key] = value
    with pytest.raises(m.RecoveryError): m.validate_ready_receipt(receipt)


@pytest.mark.parametrize('code', ['readiness_only', 'readiness_used', 'readiness_compile_binding',
    'readiness_manifest', 'access_observation', 'access_observation_sink'])
def test_new_errors_finite(code):
    assert m.finite_error(m.RecoveryError(code)) == {'helper_code': code, 'predicate': None}
    assert m.finite_error(RuntimeError('private raw error')) == {'helper_code': 'unknown', 'predicate': None}
