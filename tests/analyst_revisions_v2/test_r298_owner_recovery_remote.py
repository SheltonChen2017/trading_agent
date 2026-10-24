"""Synthetic owner-recovery checks; run with native network/artifact denial."""
import copy
from types import SimpleNamespace

import pytest

from scripts import arv2_r298_owner_recovery_remote as m
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
    sources = {name: ('# synthetic exact ' + name + '\n').encode('ascii') for name in m.SOURCE_NAMES}
    entries = tuple(SimpleNamespace(project_path=name, source_bytes=raw) for name, raw in sorted(sources.items()))
    manifest = [{'project_path': item.project_path, 'byte_count': len(item.source_bytes),
        'content_sha256': m._sha(item.source_bytes)} for item in entries]
    projection = SimpleNamespace(projection_sha256=m.PROJECTION_SHA256, source_files=entries,
        to_record=lambda: {'candidate_id': m.PROJECTION_CANDIDATE_ID, 'source_files': manifest})
    owner = {'owner': True, 'uid': 123, 'publicId': 'synthetic-owner', 'name': 'Synthetic Owner',
        'permission': 'write', 'liveControl': True}
    mia = {'owner': False, 'uid': None, 'publicId': 'synthetic-mia', 'name': 'Mia',
        'permission': 'write', 'liveControl': True}
    monkeypatch.setattr(m, 'MIA_ROW_SHA256', m._sha(m._canonical(mia)))
    manual = {'projectId': m.PROJECT_ID, 'backtestId': m.MANUAL_BACKTEST_ID,
        'name': m.MANUAL_BACKTEST_NAME, 'status': 'Completed.'}
    state = SimpleNamespace(sources=sources, projection=projection, calls=[], events=[], observations=[],
        owner=owner, mia=mia, manual=manual, pin=pin,
        files={'main.py': m.frozen.frozen.DEFAULT_MAIN.decode('ascii'),
            'accepted_risk_order_level_input_runtime.py': '#',
            **{name: sources[name].decode('ascii') for name in m.RETAINED_SOURCE_NAMES}},
        prior=[copy.deepcopy(manual)], busy=False, compile_state='BuildSuccess', mutation=None)
    state.project = {'projectId': m.PROJECT_ID, 'organizationId': organization, 'ownerId': 123,
        'name': m.PROJECT_NAME, 'language': 'Py', 'owner': True, 'public': False,
        'codeRunning': False, 'collaborators': [copy.deepcopy(owner), copy.deepcopy(mia)]}
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
            result = {'projectId': m.PROJECT_ID, 'compileId': 'compile-a4'}
        elif endpoint == 'compile/read':
            result = {'projectId': m.PROJECT_ID, 'compileId': payload['compileId'], 'state': state.compile_state}
        elif endpoint == 'projects/nodes/read':
            result = {'autoSelectNode': True, 'nodes': {'backtest': [{'active': False, 'busy': state.busy}]}}
        elif endpoint == 'backtests/create':
            row = {'projectId': m.PROJECT_ID, 'name': payload['backtestName'],
                'backtestId': 'run-a4', 'status': 'In Queue...'}
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


def test_fixed_contract_and_unmodified_pure_inheritance():
    assert m.PROJECT_ID == 38364439 and m.ATTEMPT == 4
    assert m.BACKTEST_NAME == 'ARV2 R298 NEWRULE SIX OFF 2021 OCT2026 A4 f67148cd'
    assert m.CODE_SOURCE_ID == 'Codex ARV2 R298 A4 20261024'
    assert m.MANUAL_BACKTEST_ID == 'bbd2202cc3000e8b1c14751bf088dd16'
    assert m.MANUAL_BACKTEST_NAME == 'Casual Yellow Kangaroo'
    assert m.MIA_ROW_SHA256 == '6e3fb9db0a3303a202fdebd062e91cd8a974ac564cab784dbccedc361477f44f'
    assert m.ENDPOINTS - m.frozen.ENDPOINTS == {m.COLLABORATION_ENDPOINT, m.LOCK_ENDPOINT}
    assert m.OwnerRecovery.complete is m.frozen.frozen.RemoteRecovery.complete
    assert m.OwnerRecovery.compile_once is m.frozen.frozen.RemoteRecovery.compile_once
    assert m.OwnerRecovery.launch_once is m.post_mia.PostMiaRecovery.launch_once
    assert m.OwnerRecovery._files is m.frozen.frozen.RemoteRecovery._files
    assert m.LOCK_ENDPOINT not in m.frozen.ENDPOINTS


def test_exact_nine_writes_four_owner_views_one_lock_and_61_max_dispatches(cloud):
    original, completed, compiled, launched = finish(cloud, polls=20)
    status = cloud.runner.read_status(launched, 0)
    assert len(original['files']) == 4 and len(completed['files']) == 11
    assert cloud.files == {name: raw.decode('ascii') for name, raw in cloud.sources.items()}
    assert sum(endpoint == 'files/create' for endpoint, _ in cloud.calls) == 7
    assert sum(endpoint == 'files/update' for endpoint, _ in cloud.calls) == 2
    assert sum(endpoint == m.COLLABORATION_ENDPOINT for endpoint, _ in cloud.calls) == 4
    assert sum(endpoint == m.LOCK_ENDPOINT for endpoint, _ in cloud.calls) == 1
    assert len(cloud.calls) == 61 and len(cloud.events) == 122
    assert status['backtest_name'] == m.BACKTEST_NAME and status['backtest_id'] == 'run-a4'
    assert [endpoint for endpoint, _ in cloud.calls[:5]] == ['projects/read',
        m.COLLABORATION_ENDPOINT, 'backtests/list', m.LOCK_ENDPOINT, 'files/read']
    for endpoint, payload in cloud.calls:
        if endpoint.startswith('files/') or endpoint == m.LOCK_ENDPOINT:
            assert payload['codeSourceId'] == m.CODE_SOURCE_ID
        assert not {'force', 'delete', 'permissions'} & set(payload)
    assert all(value == {'present': True, 'kind': 'boolean', 'boolean_value': False}
        for _, value in cloud.observations)


@pytest.mark.parametrize('mia_present,reverse', [(False, False), (True, False), (True, True)])
def test_only_owner_or_exact_pinned_mia_view_allowed(cloud, mia_present, reverse):
    rows = [copy.deepcopy(cloud.owner)] + ([copy.deepcopy(cloud.mia)] if mia_present else [])
    cloud.project['collaborators'] = list(reversed(rows)) if reverse else rows
    assert cloud.runner.inspect()['project_id'] == m.PROJECT_ID


@pytest.mark.parametrize('field,value,code', [
    ('projectId', True, 'owned_project_id'), ('projectId', 1, 'owned_project_id'),
    ('organizationId', 'b' * 32, 'owned_organization'), ('organizationId', 'A' * 32, 'owned_organization'),
    ('name', 'different', 'owned_name'), ('language', 'C#', 'owned_language'),
    ('owner', 1, 'owned_owner'), ('owner', False, 'owned_owner'),
    ('public', True, 'owned_private'), ('public', 0, 'owned_private'),
    ('codeRunning', True, 'owned_idle'), ('codeRunning', 0, 'owned_idle'),
    ('codeRunning', None, 'owned_idle'), ('ownerId', True, 'owned_owner_id'),
    ('ownerId', 0, 'owned_owner_id'), ('ownerId', -1, 'owned_owner_id'),
    ('ownerId', 2 ** 63, 'owned_owner_id'), ('ownerId', '123', 'owned_owner_id')])
def test_strict_project_gates_before_collaboration_lock_and_files(cloud, field, value, code):
    cloud.project[field] = value
    with pytest.raises(m.RecoveryError, match=code):
        cloud.runner.inspect()
    assert len(cloud.calls) == 1


@pytest.mark.parametrize('field', ['ownerId', 'owner', 'public', 'codeRunning', 'organizationId', 'name', 'language'])
def test_required_project_fields_cannot_be_missing(cloud, field):
    del cloud.project[field]
    with pytest.raises(m.RecoveryError):
        cloud.runner.inspect()
    assert len(cloud.calls) == 1


@pytest.mark.parametrize('value,kind', [(True, 'boolean'), (0, 'integer'), (None, 'null'), ('private-value', 'string')])
def test_typed_idle_failure_is_observed_before_refusal_without_raw_value(cloud, value, kind):
    cloud.project['codeRunning'] = value
    with pytest.raises(m.RecoveryError, match='owned_idle'):
        cloud.runner.inspect()
    assert cloud.observations == [('inspect-project', {'present': True, 'kind': kind,
        'boolean_value': value if type(value) is bool else None})]
    assert 'private-value' not in repr(cloud.observations)


@pytest.mark.parametrize('field,value', [('owner', 1), ('owner', False), ('uid', True), ('uid', 124),
    ('uid', '123'), ('permission', 'read'), ('permission', None), ('liveControl', 1), ('liveControl', False)])
def test_dedicated_owner_is_exact_typed_and_matches_owner_id(cloud, field, value):
    cloud.dedicated['collaborators'][0][field] = value
    with pytest.raises(m.RecoveryError, match='dedicated_owner'):
        cloud.runner.inspect()
    assert [endpoint for endpoint, _ in cloud.calls] == ['projects/read', m.COLLABORATION_ENDPOINT]


@pytest.mark.parametrize('rows', [None, [], [False], [{'owner': True}, {'owner': True}], [{}]])
def test_dedicated_exactly_one_complete_owner(cloud, rows):
    cloud.dedicated['collaborators'] = rows
    with pytest.raises(m.RecoveryError, match='dedicated_owner'):
        cloud.runner.inspect()


@pytest.mark.parametrize('field,value', [('userPermissions', None), ('userPermissions', 'read'),
    ('userPermissions', True), ('userLiveControl', None), ('userLiveControl', 1), ('userLiveControl', False)])
def test_dedicated_requester_requires_write_and_literal_live_control(cloud, field, value):
    cloud.dedicated[field] = value
    with pytest.raises(m.RecoveryError, match='dedicated_permissions'):
        cloud.runner.inspect()


@pytest.mark.parametrize('field,value', [('projectId', 1), ('projectId', True)])
def test_dedicated_optional_project_binding_not_coerced(cloud, field, value):
    cloud.dedicated[field] = value
    with pytest.raises(m.RecoveryError, match='dedicated_owner'):
        cloud.runner.inspect()


@pytest.mark.parametrize('change', ['absent', 'empty', 'third', 'duplicate', 'mismatch', 'nonobject'])
def test_project_owner_and_row_inventory_exact(cloud, change):
    if change == 'absent':
        cloud.project.pop('collaborators')
    elif change == 'empty':
        cloud.project['collaborators'] = []
    elif change == 'third':
        cloud.project['collaborators'].append(copy.deepcopy(cloud.owner))
    elif change == 'duplicate':
        cloud.project['collaborators'] = [copy.deepcopy(cloud.owner)] * 2
    elif change == 'mismatch':
        cloud.project['collaborators'][0]['name'] = 'Different Owner'
    else:
        cloud.project['collaborators'][1] = False
    with pytest.raises(m.RecoveryError):
        cloud.runner.inspect()
    assert len(cloud.calls) == 2


@pytest.mark.parametrize('field,value', [('name', 'mia'), ('name', None), ('owner', 0), ('owner', True),
    ('uid', 0), ('uid', 'null'), ('permission', 'read'), ('liveControl', 1), ('liveControl', False),
    ('publicId', ''), ('publicId', 'mia-ai'), ('publicId', 'é'), ('publicId', 'x' * 257)])
def test_mia_structural_guards_even_with_matching_test_pin(cloud, monkeypatch, field, value):
    row = cloud.project['collaborators'][1]
    row[field] = value
    monkeypatch.setattr(m, 'MIA_ROW_SHA256', m._sha(m._canonical(row)))
    with pytest.raises(m.RecoveryError, match='project_mia_pin'):
        cloud.runner.inspect()


def test_mia_uid_must_be_present_and_null_even_if_matching_pin(cloud, monkeypatch):
    row = cloud.project['collaborators'][1]
    del row['uid']
    monkeypatch.setattr(m, 'MIA_ROW_SHA256', m._sha(m._canonical(row)))
    with pytest.raises(m.RecoveryError, match='project_mia_pin'):
        cloud.runner.inspect()


@pytest.mark.parametrize('field,value', [('publicId', 'another-ascii'), ('name', 'Mia'), ('newField', 1)])
def test_mia_canonical_pin_cannot_be_refreshed_implicitly(cloud, field, value):
    row = cloud.project['collaborators'][1]
    if field == 'name':
        row['syntheticExtra'] = 'changed'
    else:
        row[field] = value
    with pytest.raises(m.RecoveryError, match='project_mia_pin'):
        cloud.runner.inspect()


@pytest.mark.parametrize('change', ['none', 'extra', 'id', 'name', 'status', 'project', 'countbool', 'countwrong'])
def test_prelaunch_history_exact_manual_only_no_filtering(cloud, change):
    if change == 'none':
        cloud.prior = []
    elif change == 'extra':
        cloud.prior.append(copy.deepcopy(cloud.manual))
    elif change in ('id', 'name', 'status', 'project'):
        field = {'id': 'backtestId', 'name': 'name', 'status': 'status', 'project': 'projectId'}[change]
        cloud.prior[0][field] = 1 if change == 'project' else 'unexpected'
    else:
        def mutation(endpoint, payload, result):
            if endpoint == 'backtests/list':
                result['count'] = True if change == 'countbool' else 2
        cloud.mutation = mutation
    with pytest.raises(m.RecoveryError, match='prior_backtests'):
        cloud.runner.inspect()
    assert len(cloud.calls) == 3 and all(not endpoint.startswith('files/') for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('change', ['missing', 'stub', 'default'])
@pytest.mark.parametrize('name', sorted(m.RETAINED_SOURCE_NAMES))
def test_two_existing_exact_modules_are_mandatory_to_bound_nine_writes(cloud, name, change):
    if change == 'missing':
        del cloud.files[name]
    elif change == 'stub':
        cloud.files[name] = '#'
    else:
        cloud.files[name] = m.frozen.frozen.DEFAULT_MAIN.decode('ascii')
    with pytest.raises(m.RecoveryError, match='retained_source|unexpected_cloud_content'):
        cloud.runner.inspect()
    assert len(cloud.calls) == 5
    assert not any(endpoint in ('files/create', 'files/update') for endpoint, _ in cloud.calls)


def test_nine_other_files_absent_still_nine_writes_max(cloud):
    cloud.files = {name: cloud.sources[name].decode('ascii') for name in m.RETAINED_SOURCE_NAMES}
    original = cloud.runner.inspect()
    cloud.runner.complete(original)
    assert sum(endpoint == 'files/create' for endpoint, _ in cloud.calls) == 9


@pytest.mark.parametrize('response', [{'success': False}, {'success': 1}, {'success': True, 'errors': None},
    {'success': True, 'errors': {}}, {'success': True, 'errors': ['private-provider-error']}])
def test_lock_refusal_stops_before_files_and_cannot_reacquire(cloud, response):
    def mutation(endpoint, payload, result):
        if endpoint == m.LOCK_ENDPOINT:
            result.clear()
            result.update(response)
    cloud.mutation = mutation
    with pytest.raises(m.RecoveryError, match='response_refused|lock_refused'):
        cloud.runner.inspect()
    assert len(cloud.calls) == 4 and cloud.runner._lock_acquired is False
    with pytest.raises(m.RecoveryError):
        cloud.runner._rpc('different-lock', m.LOCK_ENDPOINT,
            {'projectId': m.PROJECT_ID, 'codeSourceId': m.CODE_SOURCE_ID})
    assert len(cloud.calls) == 4


def test_lock_absent_errors_accepted_and_repeated_inspect_refuses(cloud):
    def mutation(endpoint, payload, result):
        if endpoint == m.LOCK_ENDPOINT:
            result.pop('errors')
    cloud.mutation = mutation
    cloud.runner.inspect()
    with pytest.raises(m.RecoveryError, match='duplicate_or_endpoint'):
        cloud.runner.inspect()
    assert len(cloud.calls) == 5


@pytest.mark.parametrize('endpoint,payload', [('files/read', {'projectId': m.PROJECT_ID}),
    ('files/create', {'projectId': m.PROJECT_ID, 'name': 'main.py', 'content': 'x'}),
    (m.LOCK_ENDPOINT, {'projectId': m.PROJECT_ID, 'codeSourceId': m.CODE_SOURCE_ID})])
def test_no_files_or_acquire_before_owned_history_gate(cloud, endpoint, payload):
    with pytest.raises(m.RecoveryError, match='lock_required|lock_once'):
        cloud.runner._rpc('premature', endpoint, payload)
    assert cloud.calls == [] and cloud.events == []


@pytest.mark.parametrize('endpoint,payload', [('files/read', {'projectId': m.PROJECT_ID, 'force': True}),
    ('files/read', {'projectId': m.PROJECT_ID, 'codeSourceId': 'other'}),
    ('files/delete', {'projectId': m.PROJECT_ID, 'name': 'main.py'}),
    ('projects/update', {'projectId': m.PROJECT_ID, 'name': 'replacement'}),
    ('backtests/list', {'projectId': m.PROJECT_ID, 'includeStatistics': True}),
    ('projects/read', {'projectId': True}), ('projects/read', {'projectId': 1})])
def test_no_force_delete_unscoped_payload_or_statistics(cloud, endpoint, payload):
    cloud.runner.inspect()
    before = len(cloud.calls)
    with pytest.raises(m.RecoveryError):
        cloud.runner._rpc('forbidden', endpoint, payload)
    assert len(cloud.calls) == before


def test_durable_lock_intent_before_transport_and_ambiguous_consumption(cloud):
    original = cloud.runner._request
    def fail(endpoint, payload):
        if endpoint == m.LOCK_ENDPOINT:
            assert cloud.events[-1][1]['event'] == 'intent'
            raise OSError('private provider material')
        return original(endpoint, payload)
    cloud.runner._request = fail
    with pytest.raises(m.RecoveryError, match='request_ambiguous') as result:
        cloud.runner.inspect()
    assert 'private' not in str(result.value)
    assert 'inspect-lock' in cloud.runner._used and not cloud.runner._acquire_ready
    assert not cloud.runner._lock_acquired


def test_journal_refusal_prevents_transport_and_consumes_marker(cloud):
    def journal(marker, value):
        raise OSError('private log error')
    cloud.runner._journal = journal
    with pytest.raises(m.RecoveryError, match='journal_failed'):
        cloud.runner.inspect()
    assert cloud.calls == [] and 'inspect-project' in cloud.runner._used


def test_non_none_observation_callback_refuses_before_owner_checks(cloud):
    cloud.runner._observe = lambda *args: True
    with pytest.raises(m.RecoveryError, match='journal_result'):
        cloud.runner.inspect()
    assert len(cloud.calls) == 1


@pytest.mark.parametrize('change', ['idle', 'owner', 'newhistory', 'source'])
def test_fresh_stage_guards_stop_changed_context_before_writes(cloud, change):
    original = cloud.runner.inspect()
    if change == 'idle':
        cloud.project['codeRunning'] = True
    elif change == 'owner':
        cloud.dedicated['collaborators'][0]['uid'] = 999
    elif change == 'newhistory':
        cloud.prior.append(copy.deepcopy(cloud.manual))
    else:
        cloud.files['accepted_risk_order_level_input_runtime.py'] = '#\n'
    with pytest.raises(m.RecoveryError):
        cloud.runner.complete(original)
    assert not any(endpoint in ('files/create', 'files/update') for endpoint, _ in cloud.calls)


def test_entire_source_inventory_checked_before_each_write(cloud):
    original = cloud.runner.inspect()
    changed = False
    def mutation(endpoint, payload, result):
        nonlocal changed
        if endpoint in ('files/create', 'files/update') and not changed:
            changed = True
            cloud.files['accepted_risk_order_level_input_runtime.py'] = '#\n'
    cloud.mutation = mutation
    with pytest.raises(m.RecoveryError, match='inventory_changed'):
        cloud.runner.complete(original)
    assert sum(endpoint in ('files/create', 'files/update') for endpoint, _ in cloud.calls) == 1


def test_occupied_capacity_wait_has_no_launch_or_capacity_change(cloud):
    cloud.busy = True
    _, _, _, result = finish(cloud)
    assert result == {'project_id': m.PROJECT_ID, 'state': 'wait', 'available_count': 0}
    assert not any(endpoint == 'backtests/create' for endpoint, _ in cloud.calls)
    assert all('nodes/update' not in endpoint for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('status', ['In Queue...', 'In Progress...', 'Completed.', 'Runtime Error'])
def test_status_requires_exact_manual_and_a4_pair_without_order_assumption(cloud, status, reverse):
    _, _, _, launch = finish(cloud)
    cloud.prior[1]['status'] = status
    if reverse:
        cloud.prior.reverse()
    assert cloud.runner.read_status(launch, 0)['status'] == status


@pytest.mark.parametrize('change', ['extra', 'manual_missing', 'duplicate_own', 'manual_name', 'manual_status',
    'own_name', 'own_id', 'own_status', 'own_project', 'count', 'countbool'])
def test_status_refuses_extras_or_changed_manual_and_own_identity(cloud, change):
    _, _, _, launch = finish(cloud)
    if change == 'extra':
        cloud.prior.append(copy.deepcopy(cloud.manual))
    elif change == 'manual_missing':
        cloud.prior.pop(0)
    elif change == 'duplicate_own':
        cloud.prior[0] = copy.deepcopy(cloud.prior[1])
    elif change.startswith('manual_'):
        cloud.prior[0][change.removeprefix('manual_')] = 'changed'
    elif change.startswith('own_'):
        field = {'own_name': 'name', 'own_id': 'backtestId', 'own_status': 'status', 'own_project': 'projectId'}[change]
        cloud.prior[1][field] = 1 if field == 'projectId' else 'changed'
    else:
        def mutation(endpoint, payload, result):
            if endpoint == 'backtests/list':
                result['count'] = True if change == 'countbool' else 1
        cloud.mutation = mutation
    with pytest.raises(m.RecoveryError, match='status_inventory|backtest_status'):
        cloud.runner.read_status(launch, 0)


@pytest.mark.parametrize('value', [True, -1, 1, None, '0'])
def test_status_exactly_once_integer_zero(cloud, value):
    with pytest.raises(m.RecoveryError, match='status_poll_index'):
        cloud.runner.read_status({}, value)
    assert cloud.calls == []


def test_status_receipt_cannot_relabel_manual_as_own(cloud):
    _, _, _, launch = finish(cloud)
    launch['backtest_id'] = m.MANUAL_BACKTEST_ID
    before = len(cloud.calls)
    with pytest.raises(m.RecoveryError, match='launch_receipt'):
        cloud.runner.read_status(launch, 0)
    assert len(cloud.calls) == before


@pytest.mark.parametrize('code', sorted(m.FINITE_CODES))
def test_finite_helper_codes_never_raw_provider_values(code):
    assert m.finite_error(m.RecoveryError(code)) == {'helper_code': code,
        'predicate': m.OWNERSHIP_PREDICATES.get(code)}


@pytest.mark.parametrize('error', [ValueError('owned_idle'), m.RecoveryError('private token rows'),
    m.RecoveryError('owned_idle', 'private'), m.RecoveryError(None)])
def test_unknown_exception_shapes_are_safely_unknown(error):
    assert m.finite_error(error) == {'helper_code': 'unknown', 'predicate': None}


def test_response_hash_only_journal_never_emits_collaborator_rows(cloud):
    cloud.runner.inspect()
    raw = repr(cloud.events)
    for text in ('Synthetic Owner', 'synthetic-owner', 'synthetic-mia', 'Casual Yellow Kangaroo'):
        assert text not in raw
    assert all(set(event) == {'event', 'endpoint', 'sha256'} and len(event['sha256']) == 64
        for _, event in cloud.events)
