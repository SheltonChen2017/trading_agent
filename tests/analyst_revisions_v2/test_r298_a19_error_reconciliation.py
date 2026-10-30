"""Synthetic exact-A19 read-only recovery; native isolation required."""
import copy
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r298_a19_error_reconciliation as m
from tests.analyst_revisions_v2 import test_reference_identity_projection as projection_tests
from tests.analyst_revisions_v2 import test_r298_mia_access_representation as access_tests


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


@pytest.fixture(scope='module')
def projected():
    return projection_tests.public.__wrapped__().projected


@pytest.fixture
def cloud(projected, monkeypatch):
    access = access_tests.supplied.__wrapped__(monkeypatch)
    j = m.job_source
    rows = [
        {'backtestId': j.previous.ready.predecessor.MANUAL_BACKTEST_ID,
            'name': j.previous.ready.predecessor.MANUAL_BACKTEST_NAME, 'status': 'Completed.'},
        {'backtestId': j.A12_ID, 'name': j.previous.BACKTEST_NAME, 'status': 'Runtime Error', 'compileId': j.previous.COMPILE_ID},
        {'backtestId': j.A14_ID, 'name': j.A14_NAME, 'status': 'Runtime Error', 'compileId': j.A14_COMPILE_ID},
        {'backtestId': j.A16_ID, 'name': j.A16_NAME, 'status': 'Runtime Error', 'compileId': j.A16_COMPILE_ID},
        {'backtestId': j.A18_ID, 'name': j.A18_NAME, 'status': 'Runtime Error', 'compileId': j.A18_COMPILE_ID},
        {'backtestId': m.BACKTEST_ID, 'name': m.BACKTEST_NAME, 'status': 'Runtime Error', 'compileId': m.COMPILE_ID}]
    for row in rows: row['projectId'] = m.PROJECT_ID
    s = NS(project=copy.deepcopy(access.project), dedicated=copy.deepcopy(access.dedicated),
        files=dict(projected.source_pairs), history=rows, time=0., calls=[], events=[],
        compile={'projectId': m.PROJECT_ID, 'compileId': m.COMPILE_ID, 'state': 'BuildSuccess'},
        mutation=None, after_read=None, context=projection_tests.complete_context())
    def journal(marker, event): s.events.append((marker, copy.deepcopy(event)))
    def request(endpoint, payload):
        assert s.events[-1][1] == {'event': 'intent', 'endpoint': endpoint, 'sha256': m.sha(m.canonical(payload))}
        s.calls.append((endpoint, copy.deepcopy(payload)))
        if endpoint == 'projects/read': value = copy.deepcopy(s.project)
        elif endpoint == 'projects/collaboration/read': value = copy.deepcopy(s.dedicated)
        elif endpoint == 'backtests/list': value = {'projectId': m.PROJECT_ID, 'backtests': copy.deepcopy(s.history), 'count': len(s.history)}
        elif endpoint == 'files/read': value = {'files': [{'projectId': m.PROJECT_ID, 'name': name, 'content': raw.decode('ascii')} for name, raw in s.files.items()]}
        elif endpoint == 'compile/read': value = copy.deepcopy(s.compile)
        elif endpoint == 'backtests/read':
            value = {'backtest': {**s.history[-1], 'error': m.job_source.projection.MARKER
                + m.job_source.projection.canonical(s.context).decode('ascii')}}
        else: pytest.fail('non-read-only endpoint')
        value['success'] = True
        if s.mutation: s.mutation(endpoint, payload, value)
        if endpoint == 'backtests/read':
            value = m.selector.select_response(value, project_id=m.PROJECT_ID,
                backtest_id=m.BACKTEST_ID, backtest_name=m.BACKTEST_NAME, compile_id=m.COMPILE_ID, mode='error')
            if s.after_read: s.after_read(s)
        return value
    s.runner = m.ErrorReconciliation(projected.record_bytes, projected.source_pairs,
        request=request, journal=journal, clock=lambda: s.time)
    return s


def ready(s):
    result = s.runner.poll_idle(0)
    assert result['state'] == 'ready'
    return result


def test_fixed_exact_identity_allowlist_and_no_mutation_or_capacity_api():
    assert m.BACKTEST_ID == 'b850c8193949015bc59c41d0e1434229'
    assert m.COMPILE_ID == '95f2715b63dde55edbac79da7e88d3aa-f8d3daabe131b918cd28aeaab059b9b9'
    assert m.BACKTEST_NAME == 'ARV2 R298 REFERENCE IDENTITY DIAGNOSTIC R323 A19'
    assert set(m.PAYLOAD_KEYS) == {'projects/read', 'projects/collaboration/read',
        'backtests/list', 'files/read', 'compile/read', 'backtests/read'}
    assert m.profile_record()['error_reads'] == 1 and m.profile_record()['source_mutations'] == 0
    assert m.profile_record()['old_a19_control_read'] is False


def test_genuine_public_constructor_dispatches_nothing_and_receives_exact_a19_source(projected):
    def forbidden(*args): pytest.fail('constructor dispatched')
    runner = m.ErrorReconciliation(projected.record_bytes, projected.source_pairs,
        request=forbidden, journal=forbidden)
    assert runner.terminal_receipt is None
    assert m.sha(projected.record_bytes) == m.PROJECTION_SHA256


def test_full_read_only_reconciliation_has_fresh_access_source_history_compile_both_sides(cloud):
    ready(cloud)
    result = cloud.runner.read_once()
    m.validate_receipt(result)
    assert result['terminal'] == cloud.runner.terminal_receipt
    assert result['terminal']['backtest_id'] == m.BACKTEST_ID
    assert result['terminal']['failure_evidence']['diagnostic_context'] == cloud.context
    assert result['diagnostic_only'] is True and result['result_cell'] == 0
    assert all(result[key] is False for key in m.FALSE_FLAGS)
    assert [endpoint for endpoint, _ in cloud.calls] == [
        'projects/read', 'projects/collaboration/read',
        'projects/read', 'projects/collaboration/read', 'backtests/list', 'files/read', 'compile/read',
        'backtests/read',
        'projects/read', 'projects/collaboration/read', 'backtests/list', 'files/read', 'compile/read']
    before = len(cloud.calls)
    for callback in (cloud.runner.read_once,
        lambda: cloud.runner._call('another-read', 'backtests/read', {'projectId': m.PROJECT_ID, 'backtestId': m.BACKTEST_ID}),
        lambda: cloud.runner.poll_idle(1)):
        with pytest.raises(m.Refused): callback()
    assert len(cloud.calls) == before


def test_busy_only_gets_three_observations_and_a_real_sixty_second_wait(cloud):
    cloud.project['projects'][0]['codeRunning'] = True
    assert cloud.runner.poll_idle(0)['state'] == 'wait'
    before = len(cloud.calls)
    with pytest.raises(m.Refused, match='^wait$'): cloud.runner.poll_idle(1)
    assert len(cloud.calls) == before
    cloud.time = 60.
    assert cloud.runner.poll_idle(1)['state'] == 'wait'
    cloud.time = 120.
    assert cloud.runner.poll_idle(2)['state'] == 'wait'
    with pytest.raises(m.Refused, match='^idle_budget$'): cloud.runner.poll_idle(3)
    with pytest.raises(m.Refused): cloud.runner.read_once()
    assert len(cloud.calls) == 6


def test_busy_then_idle_at_third_observation_still_authenticates_all_fresh_gates(cloud):
    cloud.project['projects'][0]['codeRunning'] = True
    cloud.runner.poll_idle(0); cloud.time = 60.; cloud.runner.poll_idle(1)
    cloud.time = 120.; cloud.project['projects'][0]['codeRunning'] = False
    assert cloud.runner.poll_idle(2)['state'] == 'ready'
    result = cloud.runner.read_once()
    assert result['access_observation_index'] == 2 and len(cloud.calls) == 17


@pytest.mark.parametrize('change', ['owner_id', 'uid', 'dedicated_permission', 'top_permission',
    'live', 'public', 'unknown_row', 'missing', 'null', 'one', 'string'])
def test_busy_cannot_hide_any_non_idle_refusal_or_accept_non_boolean_flag(cloud, change):
    project = cloud.project['projects'][0]
    project['codeRunning'] = True
    if change == 'owner_id': project.pop('ownerId')
    elif change == 'uid': cloud.dedicated['collaborators'][0].pop('uid')
    elif change == 'dedicated_permission': cloud.dedicated['collaborators'][0]['permission'] = 'read'
    elif change == 'top_permission': cloud.dedicated['userPermissions'] = 'read'
    elif change == 'live': cloud.dedicated['userLiveControl'] = False
    elif change == 'public': project['public'] = True
    elif change == 'unknown_row': project['collaborators'][2]['publicId'] = 'unknown'
    elif change == 'missing': project.pop('codeRunning')
    else: project['codeRunning'] = {'null': None, 'one': 1, 'string': 'true'}[change]
    with pytest.raises(ValueError): cloud.runner.poll_idle(0)
    assert len(cloud.calls) == 2
    assert not any(event['event'] == 'idle' for _, event in cloud.events)


@pytest.mark.parametrize('clock', [True, -1, float('nan'), float('inf'), 10**1000])
def test_bad_clock_refuses_before_any_contact(cloud, clock):
    cloud.time = clock
    with pytest.raises(m.Refused, match='^clock$'): cloud.runner.poll_idle(0)
    assert cloud.calls == []


@pytest.mark.parametrize('change', ['busy', 'unknown_row', 'files', 'compile', 'history'])
def test_failed_before_check_consumes_method_and_dispatches_no_result_or_retry(cloud, change):
    ready(cloud)
    if change == 'busy': cloud.project['projects'][0]['codeRunning'] = True
    elif change == 'unknown_row': cloud.project['projects'][0]['collaborators'][2]['name'] = 'other'
    elif change == 'files': cloud.files['main.py'] += b'# changed\n'
    elif change == 'compile': cloud.compile['state'] = 'Building'
    else: cloud.history[-1]['status'] = 'Completed.'
    with pytest.raises(ValueError): cloud.runner.read_once()
    before = len(cloud.calls)
    with pytest.raises(m.Refused, match='^read_once$'): cloud.runner.read_once()
    with pytest.raises(m.Refused, match='^read_once$'):
        cloud.runner._call('error-detail', 'backtests/read', {'projectId': m.PROJECT_ID, 'backtestId': m.BACKTEST_ID})
    assert len(cloud.calls) == before and cloud.runner.terminal_receipt is None
    assert not any(endpoint == 'backtests/read' for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('change', ['busy', 'unknown_row', 'files', 'compile', 'history'])
def test_postcheck_failure_retains_authenticated_primary_error_without_full_receipt(cloud, change):
    ready(cloud)
    def after(state):
        if change == 'busy': state.project['projects'][0]['codeRunning'] = True
        elif change == 'unknown_row': state.project['projects'][0]['collaborators'][2]['email'] = 'changed'
        elif change == 'files': state.files['main.py'] += b'# changed\n'
        elif change == 'compile': state.compile['state'] = 'BuildError'
        else: state.history[-1]['compileId'] = 'other'
    cloud.after_read = after
    with pytest.raises(ValueError): cloud.runner.read_once()
    terminal = cloud.runner.terminal_receipt
    assert terminal['failure_evidence']['diagnostic_context'] == cloud.context
    m.validate_terminal_receipt(terminal)
    assert terminal['status'] == 'Runtime Error' and terminal['backtest_id'] == m.BACKTEST_ID
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1
    assert not any(event['event'] == 'receipt' for _, event in cloud.events)
    before = len(cloud.calls)
    with pytest.raises(m.Refused): cloud.runner.read_once()
    assert len(cloud.calls) == before


@pytest.mark.parametrize('field,value', [('projectId', True), ('backtestId', 'other'),
    ('name', 'other'), ('compileId', 'other'), ('status', 'Completed.')])
def test_selected_result_is_exact_known_job_runtime_error_not_another_result(cloud, field, value):
    ready(cloud)
    def mutation(endpoint, payload, result):
        if endpoint == 'backtests/read': result['backtest'][field] = value
    cloud.mutation = mutation
    with pytest.raises(ValueError): cloud.runner.read_once()
    assert cloud.runner.terminal_receipt is None
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1


@pytest.mark.parametrize('field', ['backtestId', 'name', 'compileId', 'status'])
def test_every_known_a19_history_field_refuses_drift_before_detail(cloud, field):
    ready(cloud); cloud.history[-1][field] = 'other'
    with pytest.raises(ValueError): cloud.runner.read_once()
    assert not any(endpoint == 'backtests/read' for endpoint, _ in cloud.calls)


def test_no_extra_historical_row_is_filtered_or_treated_as_an_old_failed_attempt(cloud):
    ready(cloud)
    cloud.history.append(dict(cloud.history[-1], backtestId='invented-a17'))
    with pytest.raises(ValueError): cloud.runner.read_once()
    assert not any(endpoint == 'backtests/read' for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('endpoint', ['files/update', 'files/create', 'compile/create',
    'backtests/create', 'projects/nodes/read', 'projects/collaboration/lock/acquire'])
def test_mutation_and_capacity_endpoints_have_no_callable_route(cloud, endpoint):
    with pytest.raises(m.Refused, match='^endpoint$'):
        cloud.runner._call('forbidden', endpoint, {'projectId': m.PROJECT_ID})
    assert cloud.calls == []


@pytest.mark.parametrize('field', ['backtest_id', 'compile_id', 'backtest_name', 'projection_sha256',
    'fixed_source_checks_after', 'error_reads', 'diagnostic_only', 'result_cell'])
def test_closed_full_receipt_rejects_false_acceptance_or_identity_drift(cloud, field):
    ready(cloud); receipt = cloud.runner.read_once()
    receipt[field] = False if field in ('fixed_source_checks_after', 'diagnostic_only') else 'changed'
    with pytest.raises(ValueError): m.validate_receipt(receipt)
