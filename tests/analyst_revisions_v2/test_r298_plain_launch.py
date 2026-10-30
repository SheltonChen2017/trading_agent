"""Synthetic injected launch/result responses; no private corpus or QC client."""
import copy
import json
from types import SimpleNamespace

import pytest

from scripts import arv2_r298_plain_launch as m


@pytest.fixture
def cloud(monkeypatch):
    organization = 'a' * 32
    monkeypatch.setattr(m.ready.access, 'ORGANIZATION_SHA256', m.sha(organization.encode('ascii')))
    profile = {'schema': m.frozen.runtime.SCHEMA, 'package_sha256': m.ready.PACKAGE_SHA256,
               'universe_count': 6, 'ar_percent': 0, 'candidate_id': 'arv2-newrule-6-ar0-2026-v1'}
    profile['profile_sha256'] = m.frozen.runtime.targets.digest(profile)
    monkeypatch.setattr(m.ready, 'PROFILE_SHA256', profile['profile_sha256'])
    sources = {name: ('# synthetic exact ' + name + '\n').encode('ascii') for name in m.ready.SOURCE_NAMES}
    sources['main.py'] = ('driver = NewruleComparisonDriver(None, profile=' + repr(profile) + ')\n').encode('ascii')
    pairs = tuple(sorted(sources.items()))
    record = {'schema': 'arv2-r298-plain-projection-v1', 'candidate_id': 'R298',
        'package_sha256': m.ready.PACKAGE_SHA256, 'profile_sha256': profile['profile_sha256'],
        'activation_manifest_sha256': m.ready.ACTIVATION_SHA256,
        'source_files': [{'project_path': name, 'byte_count': len(raw), 'content_sha256': m.sha(raw)}
                         for name, raw in pairs]}
    raw = m.canonical(record)[:-1]
    monkeypatch.setattr(m.ready, 'PROJECTION_SHA256', m.sha(raw))
    manifest = {'project_id': m.PROJECT_ID, 'projection_sha256': m.ready.PROJECTION_SHA256,
        'files': [{'name': name, 'byte_count': len(value), 'sha256': m.sha(value)}
                  for name, value in sorted(sources.items())]}
    monkeypatch.setattr(m, 'SOURCE_MANIFEST_SHA256', m.sha(m.canonical(manifest)))
    owner = {'owner': True, 'uid': 123, 'publicId': 'synthetic', 'name': 'Synthetic',
             'permission': 'write', 'liveControl': True}
    extra = {'owner': False, 'uid': None, 'publicId': m.ready.CODE_SOURCE_ID,
             'name': m.ready.CODE_SOURCE_ID, 'permission': 'write', 'liveControl': True}
    monkeypatch.setattr(m.ready.access, 'OWNER_ROW_SHA256', m.sha(m.canonical(owner)))
    monkeypatch.setattr(m.ready.access, 'A5_ROW_SHA256', m.sha(m.canonical(extra)))
    manual = {'projectId': m.PROJECT_ID, 'backtestId': m.ready.predecessor.MANUAL_BACKTEST_ID,
              'name': m.ready.predecessor.MANUAL_BACKTEST_NAME, 'status': 'Completed.'}
    project = {'projectId': m.PROJECT_ID, 'organizationId': organization, 'ownerId': 123,
        'name': m.ready.access.PROJECT_NAME, 'language': 'Py', 'owner': True,
        'codeRunning': False, 'collaborators': [owner]}
    dedicated = {'collaborators': [owner], 'userPermissions': 'write', 'userLiveControl': True}
    s = SimpleNamespace(sources=sources, pairs=pairs, raw=raw, profile=profile, project=project,
        dedicated=dedicated, extra=extra, manual=manual, calls=[], events=[], time=0.,
        busy=False, mutation=None, create_state='In Queue...', own=None, compile_state='BuildSuccess',
        stats={m.frozen.runtime.META_STATISTIC: '{}', m.frozen.runtime.MONTHLY_STATISTIC: '{}'},
        validation=[], journal_failure=None)

    def journal(marker, event):
        if s.journal_failure == marker:
            raise RuntimeError('synthetic journal failure')
        s.events.append((marker, copy.deepcopy(event)))

    def request(endpoint, payload):
        assert s.events[-1][1] == {'event': 'intent', 'endpoint': endpoint, 'sha256': m.sha(m.canonical(payload))}
        s.calls.append((endpoint, copy.deepcopy(payload)))
        if endpoint == 'projects/read':
            value = {'projects': [copy.deepcopy(s.project)]}
        elif endpoint == 'projects/collaboration/read':
            value = copy.deepcopy(s.dedicated)
        elif endpoint == 'backtests/list':
            rows = [copy.deepcopy(s.manual)] + ([copy.deepcopy(s.own)] if s.own else [])
            value = {'projectId': m.PROJECT_ID, 'backtests': rows, 'count': len(rows)}
        elif endpoint == 'files/read':
            value = {'files': [{'projectId': m.PROJECT_ID, 'name': name, 'content': raw.decode('ascii')}
                               for name, raw in s.sources.items()]}
        elif endpoint == 'compile/read':
            value = {'projectId': m.PROJECT_ID, 'compileId': m.COMPILE_ID, 'state': s.compile_state}
        elif endpoint == 'projects/nodes/read':
            value = {'nodes': {'backtest': [{'busy': s.busy, 'active': True}]}, 'autoSelectNode': False}
        elif endpoint == 'backtests/create':
            s.own = {'projectId': m.PROJECT_ID, 'backtestId': '0123456789abcdef0123456789abcdef',
                     'name': m.BACKTEST_NAME, 'compileId': m.COMPILE_ID, 'status': s.create_state}
            value = {'backtest': copy.deepcopy(s.own)}
        elif endpoint == 'backtests/read':
            value = {'backtest': dict(copy.deepcopy(s.own), statistics=copy.deepcopy(s.stats))}
        else:
            pytest.fail('forbidden injected endpoint')
        value['success'] = True
        if s.mutation:
            s.mutation(endpoint, payload, value)
        return value

    def validator(stats, *, expected_profile):
        s.validation.append((copy.deepcopy(stats), copy.deepcopy(expected_profile)))
        return {'meta': {'bound': True}, 'monthly': {'bounded': True}}

    monkeypatch.setattr(m.frozen.runtime, 'validate_result_statistics', validator)
    s.request, s.journal = request, journal
    s.runner = m.PlainLaunch(raw, pairs, request=request, journal=journal, clock=lambda: s.time)
    return s


def launched(s):
    value = s.runner.launch_once()
    assert value['state'] == 'launched'
    return value


def completed(s):
    launched(s)
    s.own['status'] = 'Completed.'
    return s.runner.poll_status(0)


def test_fixed_contract_values():
    assert m.PROJECT_ID == 38364439 and m.ATTEMPT == 12
    assert m.COMPILE_ID == '5bd25474163eb6cf13a005139d1c4998-2a348312a9ff411534083f2012d355b5'
    assert m.SOURCE_MANIFEST_SHA256 == '8dfc3d3e16c0f6b555c565d9cac5d4e86a2fe35d037f95538e2a7dfe70a7bfa9'
    assert (m.STATUS_INTERVAL, m.STATUS_POLLS) == (60, 240)
    assert (m.CAPACITY_INTERVAL, m.CAPACITY_POLLS) == (60, 3)
    assert set(m.PAYLOAD_KEYS) == {'projects/read', 'projects/collaboration/read', 'files/read',
        'compile/read', 'projects/nodes/read', 'backtests/list', 'backtests/create', 'backtests/read'}
    assert all(m.profile_record()[flag] is False for flag in m.FALSE_FLAGS)


def test_success_reads_exact_source_compile_capacity_then_one_launch(cloud):
    result = launched(cloud)
    assert [name for name, _ in cloud.calls] == ['projects/read', 'projects/collaboration/read',
        'backtests/list', 'files/read', 'compile/read', 'projects/nodes/read', 'backtests/create']
    receipt = result['launch_receipt']
    assert receipt['compile_id'] == m.COMPILE_ID and receipt['attempt'] == 12
    assert result['terminal_receipt'] is None
    assert [e['event'] for _, e in cloud.events].count('launch_receipt') == 1
    assert all(receipt[flag] is False for flag in m.FALSE_FLAGS)
    receipt['backtest_id'] = 'tampered'
    assert cloud.runner.launch_receipt['backtest_id'] != 'tampered'
    with pytest.raises(m.Refused, match='^launch_once$'):
        cloud.runner.launch_once()


@pytest.mark.parametrize('status', ['In Queue...', 'In Progress...', 'Completed.', 'Runtime Error'])
def test_create_accepts_real_pending_and_fast_terminal_states(cloud, status):
    cloud.create_state = status
    result = launched(cloud)
    assert (result['terminal_receipt'] is not None) is (status in m.TERMINAL)
    if status in m.TERMINAL:
        assert result['terminal_receipt']['status'] == status
        with pytest.raises(m.Refused, match='^status_once$'):
            cloud.runner.poll_status(0)


def test_create_runtime_error_retains_only_finite_failure_evidence(cloud):
    cloud.create_state = 'Runtime Error'
    def change(endpoint, payload, value):
        if endpoint == 'backtests/create':
            value['backtest']['error'] = 'TypeError: private rows and synthetic credential never retained'
    cloud.mutation = change
    result = launched(cloud)
    evidence = result['terminal_receipt']['failure_evidence']
    assert evidence['python_error_category'] == 'TypeError'
    assert evidence['raw_error_retained'] is False and evidence['cause_authenticated'] is False
    assert 'private rows' not in json.dumps(cloud.events)
    with pytest.raises(m.Refused, match='^not_completed$'):
        cloud.runner.read_once()


@pytest.mark.parametrize('marker', ['launch-receipt', 'launch-create'])
def test_launch_identity_survives_later_journal_failure(cloud, marker):
    def journal(name, event):
        if name == marker and (name != 'launch-create' or event['event'] == 'observed'):
            raise RuntimeError('synthetic fsync failure')
        cloud.events.append((name, copy.deepcopy(event)))
    cloud.runner._journal = journal
    with pytest.raises(RuntimeError):
        cloud.runner.launch_once()
    assert cloud.runner.launch_receipt['backtest_id'] == cloud.own['backtestId']
    with pytest.raises(m.Refused, match='^launch_once$'):
        cloud.runner.launch_once()


def test_busy_capacity_waits_and_never_creates_or_modifies_other_jobs(cloud):
    cloud.busy = True
    for index in range(3):
        cloud.time = index * 60
        assert cloud.runner.launch_once() == {'state': 'wait', 'observation': index + 1,
            'capacity': {'node_count': 1, 'busy_count': 1, 'selected_count': 1,
                         'auto_select': False, 'available_count': 0}}
    assert not any(endpoint == 'backtests/create' for endpoint, _ in cloud.calls)
    count = len(cloud.calls)
    cloud.time = 180
    with pytest.raises(m.Refused, match='^capacity_budget$'):
        cloud.runner.launch_once()
    assert len(cloud.calls) == count


def test_busy_then_available_uses_fresh_complete_checks(cloud):
    cloud.busy = True
    cloud.runner.launch_once()
    cloud.busy = False
    cloud.time = 59.9
    with pytest.raises(m.Refused, match='^wait$'):
        cloud.runner.launch_once()
    assert len(cloud.calls) == 6
    cloud.time = 60
    assert cloud.runner.launch_once()['state'] == 'launched'
    assert len(cloud.calls) == 13


@pytest.mark.parametrize('change', ['running', 'owner', 'public', 'unknown_extra', 'wrong_owner', 'dedicated_extra'])
def test_access_mismatch_stops_before_source_capacity_or_launch(cloud, change):
    if change == 'running': cloud.project['codeRunning'] = True
    if change == 'owner': cloud.project['owner'] = False
    if change == 'public': cloud.project['public'] = True
    if change == 'unknown_extra': cloud.project['collaborators'].append({'owner': False})
    if change == 'wrong_owner': cloud.dedicated['collaborators'][0]['uid'] += 1
    if change == 'dedicated_extra': cloud.dedicated['collaborators'].append(copy.deepcopy(cloud.extra))
    with pytest.raises(m.ready.access.AccessRefused):
        cloud.runner.launch_once()
    assert len(cloud.calls) == 2


def test_known_a5_general_row_is_accepted_without_permission_mutation(cloud):
    cloud.project['collaborators'].append(copy.deepcopy(cloud.extra))
    launched(cloud)
    assert all('lock' not in endpoint and 'update' not in endpoint for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'unknown', 'tamper', 'wrong_project', 'nonascii', 'subclass'])
def test_cloud_source_mismatch_stops_before_compile_capacity_launch(cloud, change):
    def mutate(endpoint, payload, value):
        if endpoint != 'files/read': return
        rows = value['files']
        if change == 'missing': rows.pop()
        if change == 'duplicate': rows[-1] = dict(rows[0])
        if change == 'unknown': rows[0]['name'] = 'unreviewed.py'
        if change == 'tamper': rows[0]['content'] += '# changed\n'
        if change == 'wrong_project': rows[0]['projectId'] = True
        if change == 'nonascii': rows[0]['content'] = '\u00e9'
        if change == 'subclass': rows[0]['content'] = 3
    cloud.mutation = mutate
    with pytest.raises(m.Refused): cloud.runner.launch_once()
    assert len(cloud.calls) == 4


@pytest.mark.parametrize('change', ['missing', 'additional', 'status', 'id', 'name', 'count_bool', 'project'])
def test_unknown_or_changed_manual_inventory_refuses(cloud, change):
    def mutate(endpoint, payload, value):
        if endpoint != 'backtests/list': return
        if change == 'missing': value['backtests'].clear()
        if change == 'additional': value['backtests'].append(dict(value['backtests'][0]))
        if change == 'status': value['backtests'][0]['status'] = 'In Progress...'
        if change == 'id': value['backtests'][0]['backtestId'] = 'unknown'
        if change == 'name': value['backtests'][0]['name'] = 'Other'
        if change == 'count_bool': value['count'] = True
        if change == 'project': value['backtests'][0]['projectId'] = True
    cloud.mutation = mutate
    with pytest.raises(ValueError):
        cloud.runner.launch_once()
    assert len(cloud.calls) == 3


@pytest.mark.parametrize('field,bad', [('state', 'BuildError'), ('compileId', 'other'), ('projectId', True)])
def test_old_compile_binding_requires_fresh_build_success(cloud, field, bad):
    def mutate(endpoint, payload, value):
        if endpoint == 'compile/read': value[field] = bad
    cloud.mutation = mutate
    with pytest.raises(m.Refused, match='^compile$'): cloud.runner.launch_once()
    assert len(cloud.calls) == 5


@pytest.mark.parametrize('field,bad', [('projectId', True), ('name', 'wrong'), ('compileId', 'other'),
    ('status', 'Completed'), ('backtestId', ''), ('backtestId', 'x' * 129),
    ('backtestId', m.ready.predecessor.MANUAL_BACKTEST_ID)])
def test_ambiguous_or_invalid_created_identity_consumes_create_without_retry(cloud, field, bad):
    def mutate(endpoint, payload, value):
        if endpoint == 'backtests/create': value['backtest'][field] = bad
    cloud.mutation = mutate
    with pytest.raises(m.Refused, match='^launch_receipt$'): cloud.runner.launch_once()
    assert (cloud.runner.launch_receipt is not None) is (field == 'status')
    with pytest.raises(m.Refused, match='^launch_once$'): cloud.runner.launch_once()
    assert sum(endpoint == 'backtests/create' for endpoint, _ in cloud.calls) == 1


def test_status_enforces_exact_two_rows_interval_sequential_index_and_budget(cloud):
    launched(cloud)
    assert cloud.runner.poll_status(0)['status'] == 'In Queue...'
    with pytest.raises(m.Refused, match='^status_budget$'): cloud.runner.poll_status(0)
    with pytest.raises(m.Refused, match='^wait$'): cloud.runner.poll_status(1)
    for index in range(1, 240):
        cloud.time = index * 60
        cloud.runner.poll_status(index)
    cloud.time += 60
    with pytest.raises(m.Refused, match='^status_budget$'): cloud.runner.poll_status(240)
    assert sum(endpoint == 'backtests/list' for endpoint, _ in cloud.calls) == 241


@pytest.mark.parametrize('change', ['unknown', 'missing_manual', 'duplicate_manual', 'name', 'status', 'project', 'compile'])
def test_status_census_cannot_adopt_unknown_or_wrong_job(cloud, change):
    launched(cloud)
    def mutate(endpoint, payload, value):
        if endpoint != 'backtests/list': return
        rows = value['backtests']
        if change == 'unknown': rows[1]['backtestId'] = 'new-unknown'
        if change == 'missing_manual': rows[0]['backtestId'] = 'wrong-manual'
        if change == 'duplicate_manual': rows[1] = dict(rows[0])
        if change == 'name': rows[1]['name'] = 'wrong'
        if change == 'status': rows[1]['status'] = 'Completed'
        if change == 'project': rows[1]['projectId'] = True
        if change == 'compile': rows[1]['compileId'] = 'unknown'
    cloud.mutation = mutate
    with pytest.raises(ValueError): cloud.runner.poll_status(0)


def test_read_completed_filters_stats_uses_authenticated_new_profile_and_only_once(cloud):
    completed(cloud)
    cloud.stats['ignored statistic'] = 'private extra never forwarded'
    result = cloud.runner.read_once()
    assert result['cell_completed'] is True and result['family_comparable'] is False
    assert result['statistics'] == {'meta': {'bound': True}, 'monthly': {'bounded': True}}
    selected, profile = cloud.validation[0]
    assert set(selected) == {m.frozen.runtime.META_STATISTIC, m.frozen.runtime.MONTHLY_STATISTIC}
    assert profile == cloud.profile and profile['package_sha256'] == m.ready.PACKAGE_SHA256
    count = len(cloud.calls)
    with pytest.raises(m.Refused, match='^result_once$'): cloud.runner.read_once()
    assert len(cloud.calls) == count


@pytest.mark.parametrize('field,bad', [('projectId', True), ('name', 'wrong'),
    ('backtestId', 'unknown'), ('status', 'In Progress...'), ('compileId', 'wrong')])
def test_aggregate_read_requires_exact_completed_identity_and_no_retry(cloud, field, bad):
    completed(cloud)
    def mutate(endpoint, payload, value):
        if endpoint == 'backtests/read': value['backtest'][field] = bad
    cloud.mutation = mutate
    with pytest.raises(m.Refused, match='^result_identity$'): cloud.runner.read_once()
    assert cloud.validation == []
    with pytest.raises(m.Refused, match='^result_once$'): cloud.runner.read_once()


def test_completed_history_regression_refuses_before_aggregate_contact(cloud):
    completed(cloud)
    cloud.own['status'] = 'In Progress...'
    with pytest.raises(m.Refused, match='^status$'): cloud.runner.read_once()
    assert not any(endpoint == 'backtests/read' for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('bad', [None, 1, '', 'x' * (m.frozen.runtime.MAX_STATISTIC_BYTES + 1), '\u00e9'])
def test_bad_custom_statistics_never_reaches_validator(cloud, bad):
    completed(cloud)
    cloud.stats[m.frozen.runtime.META_STATISTIC] = bad
    with pytest.raises(m.Refused, match='^result_statistics$'): cloud.runner.read_once()
    assert cloud.validation == []


def test_completed_alone_never_bypasses_result_validator(cloud, monkeypatch):
    completed(cloud)
    def validator(*args, **kwargs):
        raise ValueError('synthetic result binding refusal')
    monkeypatch.setattr(m.frozen.runtime, 'validate_result_statistics', validator)
    with pytest.raises(ValueError, match='synthetic result'): cloud.runner.read_once()
    assert not any(event['event'] == 'result_receipt' for _, event in cloud.events)


@pytest.mark.parametrize('endpoint', ['compile/create', 'files/update', 'files/create', 'projects/create',
    'projects/collaboration/lock/acquire', 'projects/collaboration/delete', 'backtests/delete', 'live/create'])
def test_forbidden_endpoints_refuse_before_any_intent(cloud, endpoint):
    with pytest.raises(m.Refused, match='^endpoint$'):
        cloud.runner._rpc('forged', endpoint, {'projectId': m.PROJECT_ID})
    assert cloud.events == cloud.calls == []


def test_direct_create_and_read_cannot_bypass_public_method_stages(cloud):
    with pytest.raises(m.Refused, match='^payload$'):
        cloud.runner._rpc('launch-create', 'backtests/create',
            {'projectId': m.PROJECT_ID, 'compileId': m.COMPILE_ID, 'backtestName': m.BACKTEST_NAME})
    with pytest.raises(m.Refused, match='^not_completed$'): cloud.runner.read_once()
    assert cloud.calls == []


@pytest.mark.parametrize('value', [True, -1, float('nan'), float('inf'), '3'])
def test_clock_invalid_values_refuse_before_contact(cloud, value):
    cloud.time = value
    with pytest.raises(m.Refused, match='^clock$'): cloud.runner.launch_once()
    assert cloud.calls == []


def test_clock_cannot_move_backwards(cloud):
    cloud.time = 100
    cloud.busy = True
    cloud.runner.launch_once()
    cloud.time = 99
    with pytest.raises(m.Refused, match='^clock$'): cloud.runner.launch_once()


def test_finite_diagnostics_never_stringify_arbitrary_exception():
    class Hostile(ValueError):
        def __str__(self): raise AssertionError('must not stringify')
    assert m.finite(Hostile('private')) == 'unknown'
    assert m.finite(m.Refused('source_hash')) == 'source_hash'
    assert m.finite(m.Refused('private unknown')) == 'unknown'


@pytest.mark.parametrize('change', ['extra_lf', 'changed_source', 'missing', 'list', 'order'])
def test_constructor_authenticates_packet_before_callbacks(cloud, change):
    raw, pairs = cloud.raw, list(cloud.pairs)
    if change == 'extra_lf': raw += b'\n'
    if change == 'changed_source': pairs[0] = (pairs[0][0], b'# bad\n')
    if change == 'missing': pairs.pop()
    if change == 'order': pairs.reverse()
    with pytest.raises(m.ready.Refused):
        m.PlainLaunch(raw, pairs if change == 'list' else tuple(pairs),
            request=cloud.request, journal=cloud.journal)
    assert cloud.calls == []


@pytest.mark.parametrize('field,bad', [('project_id', True), ('attempt', True), ('attempt', 11),
    ('compile_id', 'unknown'), ('projection_sha256', '0' * 64), ('profile_sha256', '0' * 64),
    ('source_manifest_sha256', '0' * 64), ('package_sha256', '0' * 64), ('backtest_name', 'other'),
    ('backtest_id', ''), ('backtest_id', m.ready.predecessor.MANUAL_BACKTEST_ID),
    ('paper_or_live_ready', True), ('formal_forward_ready', 0)])
def test_pure_launch_validator_rejects_identity_alias_and_false_flag_tampering(cloud, field, bad):
    value = launched(cloud)['launch_receipt']
    value[field] = bad
    with pytest.raises(m.Refused, match='^launch_receipt$'): m.validate_launch_receipt(value)


@pytest.mark.parametrize('change', ['unknown', 'missing', 'status', 'evidence_extra', 'evidence_code',
    'evidence_hash', 'evidence_raw', 'evidence_cause', 'evidence_category'])
def test_pure_terminal_validator_rejects_unknown_or_false_cause_fields(cloud, change):
    cloud.create_state = 'Runtime Error'
    terminal = launched(cloud)['terminal_receipt']
    if change == 'unknown': terminal['unknown'] = True
    if change == 'missing': terminal.pop('failure_evidence')
    if change == 'status': terminal['status'] = 'Completed'
    if change == 'evidence_extra': terminal['failure_evidence']['unknown'] = 'private'
    if change == 'evidence_code': terminal['failure_evidence']['known_runtime_code'] = 'invented_code'
    if change == 'evidence_hash': terminal['failure_evidence']['known_runtime_code_sha256'] = '0' * 64
    if change == 'evidence_raw': terminal['failure_evidence']['raw_error_retained'] = True
    if change == 'evidence_cause': terminal['failure_evidence']['cause_authenticated'] = True
    if change == 'evidence_category': terminal['failure_evidence']['python_error_category'] = 'Secret text'
    with pytest.raises(m.Refused): m.validate_terminal_receipt(terminal)


@pytest.mark.parametrize('change', ['unknown', 'result_bool', 'status', 'family', 'complete',
    'profile_hash', 'profile_package', 'profile_missing', 'meta_changed', 'statistics_missing'])
def test_pure_result_validator_rechecks_bound_profile_and_validated_statistics(cloud, change):
    completed(cloud)
    result = cloud.runner.read_once()
    if change == 'unknown': result['unknown'] = True
    if change == 'result_bool': result['result_cell'] = True
    if change == 'status': result['status'] = 'Runtime Error'
    if change == 'family': result['family_comparable'] = True
    if change == 'complete': result['cell_completed'] = 1
    if change == 'profile_hash': result['expected_profile']['profile_sha256'] = '0' * 64
    if change == 'profile_package': result['expected_profile']['package_sha256'] = '0' * 64
    if change == 'profile_missing': result.pop('expected_profile')
    if change == 'meta_changed': result['statistics']['meta']['bound'] = False
    if change == 'statistics_missing': result['statistics'].pop('meta')
    with pytest.raises(m.Refused): m.validate_result_receipt(result)


def test_pure_validators_are_detached_and_perform_no_transport(cloud):
    completed(cloud)
    result = cloud.runner.read_once()
    count = len(cloud.calls)
    launch = m.validate_launch_receipt(cloud.runner.launch_receipt)
    terminal = m.validate_terminal_receipt(cloud.runner.terminal_receipt)
    validated = m.validate_result_receipt(result)
    launch['backtest_id'] = 'changed'
    terminal['status'] = 'Runtime Error'
    validated['expected_profile']['ar_percent'] = 200
    assert result['expected_profile']['ar_percent'] == 0
    assert len(cloud.calls) == count
