"""N synthetic lifecycle; native network/production-artifact denial required."""
import copy
import json
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r298_reference_feed_remote as m
from tests.analyst_revisions_v2 import test_r298_reference_feed_projection as public_tests


@pytest.fixture
def cloud(monkeypatch):
    names = ['main.py', m.RUNTIME_NAME] + ['module' + str(i) + '.py' for i in range(9)]
    sources = {name: ('# new ' + name + '\n').encode() for name in names}
    files = dict(sources)
    for name in m.EDIT_NAMES:
        files[name] = ('# old ' + name + '\n').encode()
    profile = {'profile_sha256': 'b' * 64, 'diagnostic_only': True}
    monkeypatch.setattr(m, 'PROJECTION_SHA256', 'a' * 64)
    monkeypatch.setattr(m, 'PROFILE_SHA256', 'b' * 64)
    monkeypatch.setattr(m, 'SOURCE_MANIFEST_SHA256', m.sha(m.canonical(m.QuoteDiagnostic._manifest(sources, m.PROJECTION_SHA256))))
    monkeypatch.setattr(m, 'OLD_SOURCE_MANIFEST_SHA256', m.sha(m.canonical(m.QuoteDiagnostic._manifest(files, m.OLD_PROJECTION_SHA256))))
    monkeypatch.setattr(m.projection, 'validate_public_projection', lambda *a, **k: ({}, profile, tuple(sources.items())))
    monkeypatch.setattr(m.projection, 'profile_digest', lambda p: 'b' * 64)
    monkeypatch.setattr(m.projection, 'validate_result_statistics', lambda stats, **kwargs: json.loads(stats[m.projection.META_STATISTIC]))
    monkeypatch.setattr(m.previous.ready.predecessor, '_manual_backtest', lambda row: row.get('backtestId') == 'manual')
    rows = [{'projectId': m.PROJECT_ID, 'backtestId': 'manual', 'name': 'manual', 'status': 'Completed.'}]
    for identity, name, compile_id in ((m.A12_ID, m.previous.BACKTEST_NAME, m.previous.COMPILE_ID),
        (m.A14_ID, m.A14_NAME, m.A14_COMPILE_ID), (m.A16_ID, m.A16_NAME, m.A16_COMPILE_ID),
        (m.A18_ID, m.A18_NAME, m.A18_COMPILE_ID), (m.A19_ID, m.A19_NAME, m.A19_COMPILE_ID)):
        rows.append({'projectId': m.PROJECT_ID, 'backtestId': identity, 'name': name,
            'compileId': compile_id, 'status': 'Runtime Error'})
    state = NS(calls=[], events=[], files=files, sources=sources, rows=rows, own=None,
        now=0, available=True, busy=False, compile_state='BuildSuccess', mutation=None,
        detail_mutation=None, create_status='In Queue...', meta={'diagnostic': 'synthetic'},
        compile_id='n-synthetic-compile', detail_error=None)
    def access(project, dedicated):
        if project['busy'] is not False:
            raise m.access.AccessRefused('idle')
        return {'synthetic_access': True}
    monkeypatch.setattr(m.access, 'verify_access', access)
    monkeypatch.setattr(m.previous.frozen, '_capacity', lambda value: {'available_count': int(state.available)})
    def request(endpoint, payload):
        state.calls.append((endpoint, copy.deepcopy(payload)))
        if state.mutation:
            state.mutation(endpoint, payload)
        if endpoint == 'projects/read': return {'success': True, 'busy': state.busy}
        if endpoint == 'projects/collaboration/read': return {'success': True}
        if endpoint == 'backtests/list': return {'success': True, 'backtests': copy.deepcopy(state.rows), 'count': len(state.rows)}
        if endpoint == 'files/read':
            return {'success': True, 'files': [{'projectId': m.PROJECT_ID, 'name': name, 'content': raw.decode()}
                for name, raw in state.files.items()]}
        if endpoint == 'files/update':
            state.files[payload['name']] = payload['content'].encode()
            return {'success': True}
        if endpoint == 'compile/create': return {'success': True, 'projectId': m.PROJECT_ID, 'compileId': state.compile_id}
        if endpoint == 'compile/read': return {'success': True, 'projectId': m.PROJECT_ID,
            'compileId': state.compile_id, 'state': state.compile_state}
        if endpoint == 'projects/nodes/read': return {'success': True}
        if endpoint == 'backtests/create':
            state.own = {'projectId': m.PROJECT_ID, 'backtestId': 'n-synthetic-job',
                'name': m.BACKTEST_NAME, 'compileId': state.compile_id, 'status': state.create_status}
            state.rows.append(state.own)
            return {'success': True, 'backtest': copy.deepcopy(state.own)}
        if endpoint == 'backtests/read':
            row = copy.deepcopy(state.own)
            row['error'] = state.detail_error
            row['statistics'] = {m.projection.META_STATISTIC: m.canonical(state.meta).decode().rstrip('\n'), 'PRIVATE PRICE': object()}
            row['charts'] = object()
            value = {'success': True, 'backtest': row}
            if state.detail_mutation: state.detail_mutation(value)
            return m.select_response(value, project_id=m.PROJECT_ID, backtest_id=state.own['backtestId'],
                backtest_name=m.BACKTEST_NAME, compile_id=state.compile_id,
                mode='completed' if state.own['status'] == 'Completed.' else 'error')
        raise AssertionError(endpoint)
    state.runner = m.QuoteDiagnostic(b'{}', tuple(sources.items()), request=request,
        journal=lambda marker, event: state.events.append((marker, event)), clock=lambda: state.now)
    return state


def launch(state):
    state.runner.prepare_once()
    assert state.runner.poll_compile(0)['state'] == 'BuildSuccess'
    return state.runner.launch_once()


def test_exact_scope_no_lock_or_strategy_result():
    assert m.ATTEMPT == 'N' and m.BACKTEST_NAME == 'ARV2 R298 RAW FEED PRESENCE R323 N'
    assert m.EDIT_NAMES == ('newrule_comparison_qc_runtime.py', 'main.py')
    assert not any('lock' in name or 'delete' in name for name in m.PAYLOAD_KEYS)
    assert m.STATUS_INTERVAL == 30 and m.STATUS_POLLS == 20
    assert m._binding()['diagnostic_only'] is True


def test_two_exact_updates_have_fresh_access_and_no_lock(cloud):
    launch(cloud)
    assert cloud.files == cloud.sources
    calls = [name for name, _ in cloud.calls]
    assert calls.count('files/update') == 2 and calls.count('compile/create') == calls.count('backtests/create') == 1
    for index, name in enumerate(calls):
        if name == 'files/update':
            assert calls[index-4:index] == ['projects/read', 'projects/collaboration/read', 'backtests/list', 'files/read']
    assert not any('lock' in name for name in calls)
    with pytest.raises(ValueError): cloud.runner.prepare_once()


@pytest.mark.parametrize('index', range(6))
def test_every_prior_row_is_required_before_any_write(cloud, index):
    cloud.rows[index]['name'] = 'changed'
    if index == 0: cloud.rows[index]['backtestId'] = 'not-manual'
    with pytest.raises(ValueError): cloud.runner.prepare_once()
    assert not any(endpoint == 'files/update' for endpoint, _ in cloud.calls)


def test_extra_job_not_filtered(cloud):
    cloud.rows.append({'projectId': m.PROJECT_ID, 'backtestId': 'unexpected', 'name': 'x', 'status': 'Runtime Error'})
    with pytest.raises(ValueError): cloud.runner.prepare_once()


def test_access_becoming_busy_before_second_edit_stops(cloud):
    def mutation(endpoint, payload):
        if endpoint == 'files/update' and payload['name'] == m.RUNTIME_NAME:
            cloud.busy = True
    cloud.mutation = mutation
    with pytest.raises(m.access.AccessRefused): cloud.runner.prepare_once()
    assert sum(endpoint == 'files/update' for endpoint, _ in cloud.calls) == 1
    assert not any(endpoint == 'compile/create' for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('kind', ['runtime', 'main', 'other', 'missing'])
def test_old_source_drift_refuses_prewrite(cloud, kind):
    name = m.RUNTIME_NAME if kind == 'runtime' else 'main.py' if kind == 'main' else 'module0.py'
    if kind == 'missing': cloud.files.pop(name)
    else: cloud.files[name] += b'# drift\n'
    with pytest.raises(ValueError): cloud.runner.prepare_once()
    assert not any(endpoint == 'files/update' for endpoint, _ in cloud.calls)


def test_compile_failure_terminal_has_no_job_or_result(cloud):
    cloud.runner.prepare_once()
    cloud.compile_state = 'BuildError'
    assert cloud.runner.poll_compile(0)['state'] == 'BuildError'
    m.validate_terminal_receipt(cloud.runner.terminal_receipt)
    with pytest.raises(ValueError): cloud.runner.launch_once()
    assert not any(endpoint.startswith('backtests/') and endpoint != 'backtests/list' for endpoint, _ in cloud.calls)


def test_capacity_wait_bounded_and_cooperative(cloud):
    cloud.runner.prepare_once(); cloud.runner.poll_compile(0)
    cloud.available = False
    for index in range(3):
        cloud.now = index * 60
        assert cloud.runner.launch_once()['state'] == 'wait'
    cloud.now += 60
    with pytest.raises(ValueError): cloud.runner.launch_once()
    assert not any(endpoint == 'backtests/create' for endpoint, _ in cloud.calls)


def test_normal_full_poll_budgets_fit160_dispatches(cloud):
    cloud.runner.prepare_once()
    for index in range(m.COMPILE_POLLS):
        cloud.now = index
        cloud.compile_state = 'BuildSuccess' if index == m.COMPILE_POLLS - 1 else 'Building'
        cloud.runner.poll_compile(index)
    for index in range(m.CAPACITY_POLLS):
        cloud.now += 60
        cloud.available = index == m.CAPACITY_POLLS - 1
        cloud.runner.launch_once()
    for index in range(m.STATUS_POLLS):
        cloud.now += m.STATUS_INTERVAL
        if index == m.STATUS_POLLS - 1: cloud.own['status'] = 'Completed.'
        cloud.runner.poll_status(index)
    cloud.runner.read_once()
    assert len(cloud.calls) == 136 < 160
    assert sum(endpoint == 'files/update' for endpoint, _ in cloud.calls) == 2
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1


@pytest.mark.parametrize('value', [True, -1, float('nan'), float('inf')])
def test_invalid_clock_stops_before_status_or_capacity(cloud, value):
    cloud.runner.prepare_once()
    cloud.now = value
    with pytest.raises(ValueError): cloud.runner.poll_compile(0)
    assert not any(endpoint == 'backtests/create' for endpoint, _ in cloud.calls)


def test_fast_terminal_and_only_metadata_aggregate_once(cloud):
    cloud.create_status = 'Completed.'
    launch(cloud)
    receipt = cloud.runner.read_once()
    assert receipt['metadata'] == cloud.meta and receipt['result_cell'] == 0
    assert receipt['observation_completed'] is True and receipt['family_comparable'] is False
    assert 'PRIVATE' not in json.dumps(receipt) and 'charts' not in json.dumps(cloud.events)
    for read in (cloud.runner.read_once, cloud.runner.read_failure_once):
        with pytest.raises(ValueError): read()
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1


def test_runtime_error_finite_only_no_context_or_metadata(cloud):
    launch(cloud); cloud.own['status'] = 'Runtime Error'; cloud.runner.poll_status(0)
    code = sorted(m.KNOWN_CODES)[0]
    cloud.detail_error = 'RuntimeError: ' + code + '\n private secret row'
    receipt = cloud.runner.read_failure_once()
    assert receipt['failure_evidence']['known_runtime_code'] == code
    assert receipt['failure_evidence']['diagnostic_context'] is None
    assert 'private' not in json.dumps(receipt) and 'statistics' not in json.dumps(receipt)


def test_busy_failure_read_preserves_terminal_without_contact(cloud):
    launch(cloud); cloud.own['status'] = 'Runtime Error'; cloud.runner.poll_status(0)
    terminal = cloud.runner.terminal_receipt
    cloud.busy = True
    with pytest.raises(m.access.AccessRefused): cloud.runner.read_failure_once()
    assert cloud.runner.terminal_receipt == terminal
    with pytest.raises(ValueError): cloud.runner.read_failure_once()
    assert not any(endpoint == 'backtests/read' for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('field,value', [('projectId', True), ('backtestId', 'wrong'), ('name', 'wrong'),
    ('compileId', 'wrong'), ('status', 'In Progress...')])
def test_selected_response_identity_mismatch_refuses_once(cloud, field, value):
    cloud.create_status = 'Completed.'; launch(cloud)
    cloud.detail_mutation = lambda result: result['backtest'].__setitem__(field, value)
    with pytest.raises(ValueError): cloud.runner.read_once()
    with pytest.raises(ValueError): cloud.runner.read_once()
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1


def test_selector_pin_and_extra_fields_independently_checked(cloud):
    row = {'projectId': m.PROJECT_ID, 'backtestId': 'new-job', 'name': m.BACKTEST_NAME,
        'compileId': 'new-compile', 'status': 'Completed.',
        'statistics': {m.projection.META_STATISTIC: '{}', 'SECRET': object()}, 'charts': object()}
    kwargs = dict(project_id=m.PROJECT_ID, backtest_id='new-job', backtest_name=m.BACKTEST_NAME,
        compile_id='new-compile', mode='completed')
    value = m.select_response({'success': True, 'backtest': row}, **kwargs)
    assert m.validate_selected(value, **kwargs) == value
    value['selection_pin']['sha256'] = '0' * 64
    with pytest.raises(ValueError): m.validate_selected(value, **kwargs)


def test_runtime_statistics_is_not_a_summary_channel_fallback():
    row = {'projectId': m.PROJECT_ID, 'backtestId': 'new-job', 'name': m.BACKTEST_NAME,
        'compileId': 'new-compile', 'status': 'Completed.', 'statistics': {},
        'runtimeStatistics': {m.projection.META_STATISTIC: '{}'}}
    with pytest.raises(ValueError):
        m.select_response({'success': True, 'backtest': row}, project_id=m.PROJECT_ID,
            backtest_id='new-job', backtest_name=m.BACKTEST_NAME, compile_id='new-compile', mode='completed')


def test_post_read_idle_retains_unaccepted_metadata_without_replay(cloud):
    cloud.create_status = 'Completed.'; launch(cloud)
    def after_read(value): cloud.busy = True
    cloud.detail_mutation = after_read
    with pytest.raises(m.access.AccessRefused): cloud.runner.read_once()
    observed = cloud.runner.result_observation
    assert observed['receipt']['metadata'] == cloud.meta
    assert observed['admissible_result'] is observed['post_checks_complete'] is observed['strategy_result_accepted'] is False
    m.validate_result_observation(observed)
    with pytest.raises(ValueError): cloud.runner.read_once()
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1
    observed['post_checks_complete'] = True
    with pytest.raises(ValueError): m.validate_result_observation(observed)


@pytest.mark.parametrize('field', ['selection_pin', 'admissible_result', 'strategy_result_accepted', 'extra'])
def test_partial_metadata_cannot_upgrade_authentication(cloud, field):
    cloud.create_status = 'Completed.'; launch(cloud); cloud.runner.read_once()
    value = cloud.runner.result_observation
    if field == 'selection_pin': value[field]['sha256'] = '0' * 64
    else: value[field] = True
    with pytest.raises(ValueError): m.validate_result_observation(value)


def test_genuine_public_projection_constructor_has_exact_pins_and_no_dispatch():
    public = public_tests.public.__wrapped__()
    def forbidden(*args, **kwargs): raise AssertionError('public constructor dispatched')
    instance = m.QuoteDiagnostic(public.projection.record_bytes, public.projection.source_pairs,
        request=forbidden, journal=forbidden)
    assert public.projection.projection_sha256 == m.PROJECTION_SHA256
    assert public.profile['profile_sha256'] == m.PROFILE_SHA256
    assert instance.compile_receipt is instance.launch_receipt is instance.terminal_receipt is None


def test_genuine_metadata_receipt_roundtrip_and_profile_tamper(monkeypatch):
    public = public_tests.public.__wrapped__()
    runtime = public_tests.runtime.__wrapped__()
    metadata = public_tests.receipt(runtime, public, monkeypatch)
    launch = {**m._binding(), 'compile_id': 'n-new-compile', 'backtest_id': 'n-new-job',
        'backtest_name': m.BACKTEST_NAME}
    receipt = {**launch, 'status': 'Completed.', 'observation_completed': True,
        'family_comparable': False, 'result_cell': 0, 'metadata': metadata, 'expected_profile': public.profile}
    assert m.validate_result_receipt(receipt) == receipt
    receipt['expected_profile']['policy']['observation_clock'] = 'invented'
    with pytest.raises(ValueError): m.validate_result_receipt(receipt)
