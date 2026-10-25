"""Synthetic A8 sequencing; native network/artifact/Keychain denial required."""
import copy
from types import SimpleNamespace

import pytest

from scripts import arv2_r298_diagnostic_recovery_remote as m
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
        for name in names:
            monkeypatch.setattr(module, name, refuse)
    yield
    assert hits == []


@pytest.fixture
def cloud(monkeypatch):
    organization = 'a' * 32
    pin = m._sha(organization.encode('ascii'))
    monkeypatch.setattr(m.frozen, 'ORGANIZATION_SHA256', pin)
    monkeypatch.setattr(m.access, 'ORGANIZATION_SHA256', pin)
    sources = {name: ('# synthetic exact ' + name + '\n').encode('ascii') for name in m.SOURCE_NAMES}
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
        owner=owner, extra=extra, manual=manual, pin=pin,
        files={'main.py': m.frozen.frozen.DEFAULT_MAIN.decode('ascii'),
            'accepted_risk_order_level_input_runtime.py': '#',
            **{name: sources[name].decode('ascii') for name in m.RETAINED_SOURCE_NAMES}},
        prior=[copy.deepcopy(manual)], busy=False, compile_state='BuildSuccess', mutation=None)
    state.project = {'projectId': m.PROJECT_ID, 'organizationId': organization, 'ownerId': 123,
        'name': m.PROJECT_NAME, 'language': 'Py', 'owner': True,
        'codeRunning': False, 'collaborators': [copy.deepcopy(owner), copy.deepcopy(extra)]}
    state.dedicated = {'collaborators': [copy.deepcopy(owner)], 'userPermissions': 'write', 'userLiveControl': True}
    def journal(marker, event):
        assert not any(old == marker and before['event'] == event['event'] for old, before in state.events)
        state.events.append((marker, copy.deepcopy(event)))
    def request(endpoint, payload):
        assert state.events[-1][1] == {'event': 'intent', 'endpoint': endpoint,
            'sha256': m._sha(m._canonical(payload))}
        state.calls.append((endpoint, copy.deepcopy(payload)))
        if endpoint == 'projects/read':
            result = {'projects': [copy.deepcopy(state.project)]}
        elif endpoint == m.COLLABORATION_ENDPOINT:
            result = copy.deepcopy(state.dedicated)
        elif endpoint == m.LOCK_ENDPOINT:
            result = {'errors': []}
        elif endpoint == 'backtests/list':
            result = {'backtests': copy.deepcopy(state.prior), 'count': len(state.prior), 'projectId': m.PROJECT_ID}
        elif endpoint == 'files/read':
            result = {'files': [{'projectId': m.PROJECT_ID, 'name': name, 'content': raw}
                for name, raw in state.files.items()]}
        elif endpoint in ('files/create', 'files/update'):
            assert (payload['name'] in state.files) == (endpoint == 'files/update')
            state.files[payload['name']] = payload['content']
            result = {}
        elif endpoint == 'compile/create':
            result = {'projectId': m.PROJECT_ID, 'compileId': 'compile-a8'}
        elif endpoint == 'compile/read':
            result = {'projectId': m.PROJECT_ID, 'compileId': payload['compileId'], 'state': state.compile_state}
        elif endpoint == 'projects/nodes/read':
            result = {'autoSelectNode': True, 'nodes': {'backtest': [{'active': False, 'busy': state.busy}]}}
        elif endpoint == 'backtests/create':
            row = {'projectId': m.PROJECT_ID, 'name': payload['backtestName'],
                'backtestId': 'run-a8', 'status': 'In Queue...'}
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
        state.observations.append((marker, copy.deepcopy(value)))
    state.request, state.journal, state.observe = request, journal, observe
    state.runner = m.OwnerRecovery(projection, pin, request, journal, observe)
    return state


def finish(cloud, polls=1):
    original = cloud.runner.inspect()
    completed = cloud.runner.complete(original)
    compiled = cloud.runner.compile_once(completed)
    for index in range(polls):
        cloud.runner.poll_compile(compiled['compile_id'], index)
    launched = cloud.runner.launch_once(compiled['compile_id'])
    return original, completed, compiled, launched


def test_contract_and_inherited_frozen_gates():
    assert m.ATTEMPT == 8 and m.PROJECT_ID == 38364439
    assert m.BACKTEST_NAME == 'ARV2 R298 NEWRULE SIX OFF 2021 OCT2026 A8 f67148cd'
    assert m.CODE_SOURCE_ID == m.previous.CODE_SOURCE_ID == 'Codex ARV2 R298 A5 20261024'
    assert m.OwnerRecovery._owned is m.previous.AccessRecovery._owned
    assert m.OwnerRecovery._files is m.previous.AccessRecovery._files
    assert m.OwnerRecovery.compile_once is m.previous.AccessRecovery.compile_once
    assert m.OwnerRecovery.poll_compile is m.previous.AccessRecovery.poll_compile
    assert m.OwnerRecovery.launch_once.__globals__ is m.__dict__
    assert m.OwnerRecovery.read_status.__globals__ is m.__dict__
    assert m.previous.ATTEMPT == 6 and ' A6 ' in m.previous.BACKTEST_NAME
    assert m.access.OWNER_ROW_SHA256 == '707a30618e122e49fe6fa75364451b5b7c50e1019a68a89ffc0cd3ae3c8e0b78'
    assert m.access.A5_ROW_SHA256 == 'f9a933141393262edb66e3e8248ed75ebf4518668039e1a27af6734f26f58b9d'


def test_complete_then_launch_and_status_stays_below_64_with_20_compile_polls(cloud):
    original, completed, compiled, launch = finish(cloud, polls=20)
    status = cloud.runner.read_status(launch, 0)
    assert len(original['files']) == 4 and len(completed['files']) == 11
    assert len(cloud.calls) == 60 and len(cloud.calls) < 64
    assert launch['backtest_name'] == m.BACKTEST_NAME and status['backtest_id'] == 'run-a8'
    assert cloud.files == {name: raw.decode('ascii') for name, raw in cloud.sources.items()}
    writes = [(endpoint, payload) for endpoint, payload in cloud.calls if endpoint in ('files/create', 'files/update')]
    assert len(writes) == len({payload['name'] for _, payload in writes}) == 9
    assert sum(endpoint == 'files/create' for endpoint, _ in writes) == 7
    assert sum(endpoint == 'files/update' for endpoint, _ in writes) == 2
    assert all(payload['content'].encode('ascii') == cloud.sources[payload['name']] for _, payload in writes)
    assert all(payload['codeSourceId'] == m.CODE_SOURCE_ID for endpoint, payload in cloud.calls
        if endpoint.startswith('files/') or endpoint == m.LOCK_ENDPOINT)
    assert sum(endpoint == 'backtests/create' for endpoint, _ in cloud.calls) == 1


def test_each_write_has_immediate_full_readback_and_next_write_uses_it(cloud):
    original = cloud.runner.inspect()
    cloud.runner.complete(original)
    calls = cloud.calls
    write_indexes = [i for i, (endpoint, _) in enumerate(calls) if endpoint in ('files/create', 'files/update')]
    for index in write_indexes:
        assert calls[index - 1][0] == calls[index + 1][0] == 'files/read'
    assert write_indexes == list(range(write_indexes[0], write_indexes[-1] + 1, 2))
    markers = [marker for marker, event in cloud.events if event['event'] == 'intent']
    assert markers.count('complete-before') == 1
    assert sum(marker.startswith('complete-after-') for marker in markers) == 9
    assert 'complete-final' not in markers


def test_already_complete_source_has_no_write_and_strict_final_read(cloud):
    cloud.files = {name: raw.decode('ascii') for name, raw in cloud.sources.items()}
    original = cloud.runner.inspect()
    assert cloud.runner.complete(original) == original
    assert not any(endpoint in ('files/create', 'files/update') for endpoint, _ in cloud.calls)
    assert any(marker == 'complete-final' for marker, _ in cloud.events)


@pytest.mark.parametrize('prefix', ['inspect', 'complete'])
@pytest.mark.parametrize('change', ['owner_hash', 'extra_hash', 'old_mia', 'third', 'live', 'busy', 'permission'])
def test_current_access_drift_refuses_before_source_mutation(cloud, prefix, change):
    original = cloud.runner.inspect() if prefix == 'complete' else None
    if change == 'owner_hash':
        cloud.dedicated['collaborators'][0]['new'] = True
        cloud.project['collaborators'][0]['new'] = True
    elif change == 'extra_hash': cloud.project['collaborators'][1]['test-only-extra'] = 8
    elif change == 'old_mia': cloud.project['collaborators'][1]['name'] = 'Mia'
    elif change == 'third': cloud.project['collaborators'].append(copy.deepcopy(cloud.extra))
    elif change == 'live': cloud.dedicated['userLiveControl'] = False
    elif change == 'busy': cloud.project['codeRunning'] = True
    else: cloud.dedicated['userPermissions'] = 'read'
    before = len(cloud.calls)
    with pytest.raises(m.RecoveryError):
        cloud.runner.inspect() if prefix == 'inspect' else cloud.runner.complete(original)
    assert [endpoint for endpoint, _ in cloud.calls[before:]] == ['projects/read', m.COLLABORATION_ENDPOINT]


@pytest.mark.parametrize('change', ['extra_file', 'source_drift', 'retained_placeholder', 'duplicate'])
def test_unknown_initial_inventory_not_repaired(cloud, change):
    if change == 'extra_file': cloud.files['unknown.py'] = '#'
    elif change == 'source_drift': cloud.files['main.py'] = '# arbitrary changed code'
    elif change == 'retained_placeholder': cloud.files['accepted_risk_order_level_core.py'] = '#'
    else:
        def mutation(endpoint, payload, response):
            if endpoint == 'files/read': response['files'].append(copy.deepcopy(response['files'][0]))
        cloud.mutation = mutation
    with pytest.raises(m.RecoveryError): cloud.runner.inspect()
    assert not any(endpoint in ('files/create', 'files/update') for endpoint, _ in cloud.calls)
    assert cloud.runner._inspection_snapshot is None


def test_completion_requires_successful_inspect_before_any_dispatch(cloud):
    with pytest.raises(m.RecoveryError, match='completion_stage'): cloud.runner.complete({})
    assert cloud.calls == []
    with pytest.raises(m.RecoveryError, match='completion_used'): cloud.runner.complete({})


def test_original_inventory_is_bound_before_new_requests(cloud):
    original = cloud.runner.inspect()
    original['files'][0]['sha256'] = '0' * 64
    before = len(cloud.calls)
    with pytest.raises(m.RecoveryError, match='inventory_changed'): cloud.runner.complete(original)
    assert len(cloud.calls) == before


def test_remote_inventory_change_between_inspect_and_complete_refuses(cloud):
    original = cloud.runner.inspect()
    cloud.files['accepted_risk_order_level_input_runtime.py'] = '#\n'
    with pytest.raises(m.RecoveryError, match='inventory_changed'): cloud.runner.complete(original)
    assert not cloud.runner._written_targets


@pytest.mark.parametrize('change', ['target_unwritten', 'other_changed', 'new_file', 'missing_retained', 'success_false', 'request_raises'])
def test_first_write_or_immediate_readback_failure_never_reaches_next_write(cloud, change):
    original = cloud.runner.inspect()
    first = True
    def mutation(endpoint, payload, response):
        nonlocal first
        if endpoint in ('files/create', 'files/update') and first:
            first = False
            if change == 'target_unwritten': cloud.files[payload['name']] = '#'
            elif change == 'other_changed': cloud.files['main.py'] = '# arbitrary concurrent code'
            elif change == 'new_file': cloud.files['unknown.py'] = '#'
            elif change == 'missing_retained': del cloud.files['accepted_risk_order_level_core.py']
            elif change == 'success_false': response['success'] = False
            else: raise RuntimeError('SYNTHETIC PRIVATE ERROR')
    cloud.mutation = mutation
    with pytest.raises(m.RecoveryError): cloud.runner.complete(original)
    writes = [(endpoint, payload) for endpoint, payload in cloud.calls if endpoint in ('files/create', 'files/update')]
    assert len(writes) == 1 and len(cloud.runner._written_targets) == 1
    before = len(cloud.calls)
    with pytest.raises(m.RecoveryError, match='completion_used'): cloud.runner.complete(original)
    assert len(cloud.calls) == before
    assert cloud.runner._write_ready is None


def test_last_write_readback_requires_all_eleven_exact_files(cloud):
    original = cloud.runner.inspect()
    write_count = 0
    def mutation(endpoint, payload, response):
        nonlocal write_count
        if endpoint in ('files/create', 'files/update'):
            write_count += 1
            if write_count == 9: del cloud.files['accepted_risk_order_level_core.py']
    cloud.mutation = mutation
    with pytest.raises(m.RecoveryError, match='incomplete_cloud_source'):
        cloud.runner.complete(original)
    assert write_count == 9
    assert not any(endpoint.startswith('compile/') for endpoint, _ in cloud.calls)


def test_written_target_consumed_even_if_intent_journal_refuses(cloud):
    original = cloud.runner.inspect()
    old_journal = cloud.runner._journal
    def refuse(marker, event):
        if marker.startswith('complete-write-'): raise RuntimeError('SYNTHETIC PRIVATE')
        return old_journal(marker, event)
    cloud.runner._journal = refuse
    with pytest.raises(m.RecoveryError, match='journal_failed'): cloud.runner.complete(original)
    assert len(cloud.runner._written_targets) == 1
    assert not any(endpoint in ('files/create', 'files/update') for endpoint, _ in cloud.calls)
    name = next(iter(cloud.runner._written_targets))
    with pytest.raises(m.RecoveryError, match='write_target_used'):
        cloud.runner._rpc('changed-marker', 'files/update', {'projectId': m.PROJECT_ID,
            'name': name, 'content': cloud.sources[name].decode('ascii')})


@pytest.mark.parametrize('endpoint', ['files/create', 'files/update'])
def test_direct_write_without_completion_stage_refuses(cloud, endpoint):
    cloud.runner.inspect()
    before = len(cloud.calls)
    name = 'accepted_risk_order_level_input_runtime.py'
    with pytest.raises(m.RecoveryError, match='completion_stage'):
        cloud.runner._rpc('not-completion', endpoint, {'projectId': m.PROJECT_ID,
            'name': name, 'content': cloud.sources[name].decode('ascii')})
    assert len(cloud.calls) == before


@pytest.mark.parametrize('field,value', [('name', 'unknown.py'), ('name', None), ('name', 1),
    ('content', '# wrong'), ('content', b'#'), ('content', 'é'), ('content', None)])
def test_exact_target_and_content_enforced_before_write(cloud, field, value):
    cloud.runner.inspect()
    payload = {'projectId': m.PROJECT_ID, 'name': 'accepted_risk_order_level_input_runtime.py',
        'content': cloud.sources['accepted_risk_order_level_input_runtime.py'].decode('ascii')}
    payload[field] = value
    before = len(cloud.calls)
    code = 'access_json_shape' if type(value) is bytes else 'write_binding'
    with pytest.raises(m.RecoveryError, match='^' + code + '$'):
        cloud.runner._rpc('not-completion', 'files/update', payload)
    assert len(cloud.calls) == before


@pytest.mark.parametrize('hidden', [(1,), {1: 'not-a-json-key'}, float('nan')])
def test_write_payload_strict_json_precedes_normalization(cloud, hidden):
    cloud.runner.inspect()
    payload = {'projectId': m.PROJECT_ID, 'name': 'accepted_risk_order_level_input_runtime.py',
        'content': cloud.sources['accepted_risk_order_level_input_runtime.py'].decode('ascii'),
        'hidden': hidden}
    before = len(cloud.calls)
    with pytest.raises(m.RecoveryError, match='access_json_shape'):
        cloud.runner._rpc('not-completion', 'files/update', payload)
    assert len(cloud.calls) == before and not cloud.runner._written_targets


def test_source_completion_does_not_mutate_supplied_projection_or_inventory(cloud):
    source_before = dict(cloud.sources)
    original = cloud.runner.inspect()
    snapshot = copy.deepcopy(original)
    cloud.runner.complete(original)
    assert original == snapshot and cloud.sources == source_before


def test_owner_only_or_pinned_a5_row_only_not_general_count_acceptance(cloud):
    cloud.project['collaborators'] = [copy.deepcopy(cloud.owner)]
    assert cloud.runner.inspect()['project_id'] == m.PROJECT_ID
    cloud.project['collaborators'].append({'owner': False, 'name': 'Mia'})
    with pytest.raises(m.RecoveryError, match='access_extra_row_shape'):
        cloud.runner.complete(m.json.loads(cloud.runner._inspection_snapshot))
    assert not cloud.runner._written_targets


@pytest.mark.parametrize('state', ['InQueue', 'Building', 'BuildError'])
def test_non_successful_compile_cannot_launch(cloud, state):
    original = cloud.runner.inspect()
    completed = cloud.runner.complete(original)
    compiled = cloud.runner.compile_once(completed)
    cloud.compile_state = state
    with pytest.raises(m.RecoveryError, match='compile_not_ready'):
        cloud.runner.launch_once(compiled['compile_id'])
    assert not any(endpoint == 'backtests/create' for endpoint, _ in cloud.calls)


def test_occupied_capacity_waits_without_altering_other_work(cloud):
    cloud.busy = True
    _, _, _, result = finish(cloud)
    assert result == {'project_id': m.PROJECT_ID, 'state': 'wait', 'available_count': 0}
    assert not any(endpoint == 'backtests/create' for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('status', ['In Queue...', 'In Progress...', 'Completed.', 'Runtime Error'])
def test_launch_retains_exact_a8_and_finite_terminal_status(cloud, status):
    def mutation(endpoint, payload, response):
        if endpoint == 'backtests/create':
            response['backtest']['status'] = status
            cloud.prior[-1]['status'] = status
    cloud.mutation = mutation
    _, _, _, launch = finish(cloud)
    assert launch['status'] == status and launch['backtest_name'] == m.BACKTEST_NAME
    assert cloud.runner.read_status(launch, 0)['status'] == status


@pytest.mark.parametrize('step', ['create', 'receipt', 'status'])
@pytest.mark.parametrize('old_attempt', [2, 3, 4, 5, 6, 7])
def test_earlier_attempt_names_not_accepted_as_a8(cloud, step, old_attempt):
    old_name = f'{m.PROJECT_NAME} A{old_attempt} {m.PROJECTION_SHA256[:8]}'
    if step == 'create':
        def mutation(endpoint, payload, response):
            if endpoint == 'backtests/create': response['backtest']['name'] = old_name
        cloud.mutation = mutation
        with pytest.raises(m.RecoveryError, match='created_backtest'): finish(cloud)
    else:
        _, _, _, launch = finish(cloud)
        if step == 'receipt': launch['backtest_name'] = old_name
        else: cloud.prior[-1]['name'] = old_name
        before = len(cloud.calls)
        with pytest.raises(m.RecoveryError, match='launch_receipt|backtest_status'):
            cloud.runner.read_status(launch, 0)
        assert len(cloud.calls) == before + (step == 'status')


@pytest.mark.parametrize('value', [True, None, -1, 1, '0'])
def test_status_exactly_one_integer_zero(cloud, value):
    with pytest.raises(m.RecoveryError, match='status_poll_index'):
        cloud.runner.read_status({}, value)
    assert cloud.calls == []


def test_duplicate_completion_launch_and_status_are_consumed(cloud):
    original, _, compiled, launch = finish(cloud)
    before = len(cloud.calls)
    with pytest.raises(m.RecoveryError, match='completion_used'): cloud.runner.complete(original)
    with pytest.raises(m.RecoveryError, match='duplicate_or_endpoint'):
        cloud.runner.launch_once(compiled['compile_id'])
    assert len(cloud.calls) == before
    cloud.runner.read_status(launch, 0)
    before = len(cloud.calls)
    with pytest.raises(m.RecoveryError, match='duplicate_or_endpoint'):
        cloud.runner.read_status(launch, 0)
    assert len(cloud.calls) == before


def test_unexpected_prior_run_refuses_before_lock(cloud):
    cloud.prior.append({'projectId': m.PROJECT_ID, 'name': 'unknown',
        'backtestId': 'unknown-run', 'status': 'Completed.'})
    with pytest.raises(m.RecoveryError, match='prior_backtests'): cloud.runner.inspect()
    assert not any(endpoint == m.LOCK_ENDPOINT for endpoint, _ in cloud.calls)


def test_only_hashes_in_remote_journal(cloud):
    finish(cloud)
    raw = repr(cloud.events)
    for text in ('Synthetic Owner', 'synthetic-owner', '# synthetic', 'test-only-extra'):
        assert text not in raw
    assert all(set(event) == {'event', 'endpoint', 'sha256'} for _, event in cloud.events)


@pytest.mark.parametrize('code', sorted(m.FINITE_CODES))
def test_finite_helper_error(code):
    assert m.finite_error(m.RecoveryError(code)) == {'helper_code': code,
        'predicate': m.OWNERSHIP_PREDICATES.get(code)}


@pytest.mark.parametrize('error', [ValueError('private'), m.RecoveryError('private'),
    m.RecoveryError(None), m.RecoveryError('write_binding', 'private')])
def test_unknown_error_stays_unknown(error):
    assert m.finite_error(error) == {'helper_code': 'unknown', 'predicate': None}
