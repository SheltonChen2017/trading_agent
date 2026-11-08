"""A15 exact injected lifecycle; no operational controls, credentials or QC."""
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r298_quote_execution_remote as m
from scripts import arv2_r298_quote_diagnostic_a14_remote as frozen


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


@pytest.fixture
def cloud(monkeypatch):
    old = {name: ('# exact A14 ' + name + '\n').encode('ascii') for name in m.previous.ready.SOURCE_NAMES}
    sources = {name: raw + (b'# new quote policy\n' if name in m.EDIT_NAMES else b'') for name, raw in old.items()}
    pairs = tuple(sorted(sources.items()))
    profile = {'schema': m.previous.frozen.runtime.SCHEMA, 'package_sha256': m.previous.ready.PACKAGE_SHA256,
        'universe_count': 6, 'ar_percent': 0, 'candidate_id': 'synthetic-new-quote-policy',
        'execution_policy': m.projection.POLICY}
    profile['profile_sha256'] = m.previous.frozen.runtime.targets.digest(profile)
    raw = b'{"synthetic":"new quote execution projection"}'
    monkeypatch.setattr(m, 'PROFILE_SHA256', profile['profile_sha256'])
    monkeypatch.setattr(m, 'PROJECTION_SHA256', m.sha(raw))
    monkeypatch.setattr(m, 'SOURCE_MANIFEST_SHA256', m.sha(m.canonical(m.QuoteDiagnostic._manifest(sources, m.PROJECTION_SHA256))))
    monkeypatch.setattr(m, 'OLD_SOURCE_MANIFEST_SHA256', m.sha(m.canonical(m.QuoteDiagnostic._manifest(old, m.OLD_PROJECTION_SHA256))))
    def receiver(record, supplied, *, expected_projection_sha256, expected_profile_sha256):
        assert record == raw and supplied == pairs
        assert expected_projection_sha256 == m.PROJECTION_SHA256 and expected_profile_sha256 == m.PROFILE_SHA256
        return {}, copy.deepcopy(profile), pairs
    monkeypatch.setattr(m.projection, 'validate_public_projection', receiver)
    owner = {'owner': True, 'uid': 123, 'publicId': 'synthetic', 'name': 'Synthetic', 'permission': 'write', 'liveControl': True}
    monkeypatch.setattr(m.previous.ready.access, 'OWNER_ROW_SHA256', m.sha(m.canonical(owner)))
    monkeypatch.setattr(m.previous.ready.access, 'ORGANIZATION_SHA256', m.sha(('a' * 32).encode('ascii')))
    project = {'projectId': m.PROJECT_ID, 'organizationId': 'a' * 32, 'ownerId': 123,
        'name': m.previous.ready.access.PROJECT_NAME, 'language': 'Py', 'owner': True,
        'codeRunning': False, 'collaborators': [copy.deepcopy(owner)]}
    manual = {'projectId': m.PROJECT_ID, 'backtestId': m.previous.ready.predecessor.MANUAL_BACKTEST_ID,
        'name': m.previous.ready.predecessor.MANUAL_BACKTEST_NAME, 'status': 'Completed.'}
    a12 = {'projectId': m.PROJECT_ID, 'backtestId': m.A12_ID, 'name': m.previous.BACKTEST_NAME,
        'status': 'Runtime Error', 'compileId': m.previous.COMPILE_ID}
    a14 = {'projectId': m.PROJECT_ID, 'backtestId': m.A14_ID, 'name': m.A14_NAME,
        'status': 'Runtime Error', 'compileId': m.A14_COMPILE_ID}
    s = NS(old=old, sources=sources, files=copy.deepcopy(old), profile=profile, project=project,
        dedicated={'collaborators': [copy.deepcopy(owner)], 'userPermissions': 'write', 'userLiveControl': True},
        manual=manual, a12=a12, a14=a14, own=None, calls=[], events=[], mutation=None, time=0.,
        compile_id='compile-a15-synthetic', compile_state='BuildSuccess', compile_error='',
        busy=False, create_state='In Queue...', detail_error=None, validation=[],
        stats={m.previous.frozen.runtime.META_STATISTIC: '{}', m.previous.frozen.runtime.MONTHLY_STATISTIC: '{}'})
    def journal(marker, event): s.events.append((marker, copy.deepcopy(event)))
    def request(endpoint, payload):
        assert s.events[-1][1] == {'event': 'intent', 'endpoint': endpoint, 'sha256': m.sha(m.canonical(payload))}
        s.calls.append((endpoint, copy.deepcopy(payload)))
        if endpoint == 'projects/read': value = {'projects': [copy.deepcopy(s.project)]}
        elif endpoint == 'projects/collaboration/read': value = copy.deepcopy(s.dedicated)
        elif endpoint == 'projects/collaboration/lock/acquire': value = {}
        elif endpoint == 'backtests/list':
            rows = copy.deepcopy([s.manual, s.a12, s.a14] + ([s.own] if s.own else []))
            value = {'projectId': m.PROJECT_ID, 'backtests': rows, 'count': len(rows)}
        elif endpoint == 'files/read':
            value = {'files': [{'projectId': m.PROJECT_ID, 'name': name, 'content': raw.decode('ascii')} for name, raw in s.files.items()]}
        elif endpoint == 'files/update': s.files[payload['name']] = payload['content'].encode('ascii'); value = {}
        elif endpoint == 'compile/create': value = {'projectId': m.PROJECT_ID, 'compileId': s.compile_id}
        elif endpoint == 'compile/read': value = {'projectId': m.PROJECT_ID, 'compileId': s.compile_id, 'state': s.compile_state, 'error': s.compile_error}
        elif endpoint == 'projects/nodes/read': value = {'nodes': {'backtest': [{'busy': s.busy, 'active': True}]}, 'autoSelectNode': False}
        elif endpoint == 'backtests/create':
            s.own = {'projectId': m.PROJECT_ID, 'backtestId': 'a15-synthetic-job', 'name': m.BACKTEST_NAME,
                'compileId': s.compile_id, 'status': s.create_state}
            value = {'backtest': copy.deepcopy(s.own)}
        elif endpoint == 'backtests/read':
            value = {'backtest': dict(copy.deepcopy(s.own), statistics=copy.deepcopy(s.stats))}
            if s.detail_error is not None: value['backtest']['error'] = s.detail_error
        else: pytest.fail('forbidden endpoint')
        value['success'] = True
        if s.mutation: s.mutation(endpoint, payload, value)
        return value
    def validator(selected, *, expected_profile):
        s.validation.append((copy.deepcopy(selected), copy.deepcopy(expected_profile)))
        return {'meta': {'bound': True}, 'monthly': {'bound': True}}
    monkeypatch.setattr(m.previous.frozen.runtime, 'validate_result_statistics', validator)
    s.request, s.journal = request, journal
    s.runner = m.QuoteDiagnostic(raw, pairs, request=request, journal=journal, clock=lambda: s.time)
    return s


def prepare(s):
    result = s.runner.prepare_once()
    assert s.runner.poll_compile(0)['state'] == 'BuildSuccess'
    return result


def launch(s):
    prepare(s)
    return s.runner.launch_once()


def test_fixed_new_identity_old_cloud_and_closed_scope():
    assert m.ATTEMPT == 15 and m.SCHEMA == 'arv2-r298-quote-execution-a15-v1'
    assert m.BACKTEST_NAME == 'ARV2 R298 QUOTE EXECUTION R323 A15'
    assert m.A14_ID == '45ffd36c48e59adfbb212cfd3324dfeb'
    assert m.A14_COMPILE_ID == 'c8398c515fb7425391986ac7b3d84429-79837ae21b59dee4b69ddb000301b67d'
    assert m.OLD_PROJECTION_SHA256 == frozen.PROJECTION_SHA256
    assert m.OLD_SOURCE_MANIFEST_SHA256 == frozen.SOURCE_MANIFEST_SHA256
    assert m.EDIT_NAMES == ('newrule_comparison_qc_runtime.py', 'main.py')
    assert m.PAYLOAD_KEYS == frozen.PAYLOAD_KEYS
    assert m._binding()['diagnostic_only'] is False and m._binding()['accepted_risk_only'] is True
    assert all(m._binding()[key] is False for key in m.FALSE_FLAGS)


def test_preserved_protocol_methods_are_ast_identical_to_frozen_a14():
    names = {'_rpc', '_access', 'prepare_once', '_compile_read', 'poll_compile', '_fresh',
        'launch_once', '_accept_created', '_set_terminal', 'poll_status', 'read_once', 'read_failure_once'}
    def methods(path):
        tree = ast.parse(path.read_bytes())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'QuoteDiagnostic')
        return {node.name: ast.dump(node, include_attributes=False) for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name in names}
    assert m.sha((ROOT / 'scripts/arv2_r298_quote_diagnostic_a14_remote.py').read_bytes()) == '58cbc1b1f2fec140a5d4cd19660e6f2f61a94ab728a3da20ce011b7687f478f8'
    assert set(methods(ROOT / 'scripts/arv2_r298_quote_execution_remote.py')) == names
    assert methods(ROOT / 'scripts/arv2_r298_quote_execution_remote.py') == methods(ROOT / 'scripts/arv2_r298_quote_diagnostic_a14_remote.py')


def test_one_lifecycle_writes_two_exact_files_and_admits_only_new_profile(cloud):
    launch(cloud)
    assert cloud.files == cloud.sources
    assert [body['name'] for endpoint, body in cloud.calls if endpoint == 'files/update'] == list(m.EDIT_NAMES)
    assert sum(endpoint == 'compile/create' for endpoint, _ in cloud.calls) == 1
    assert sum(endpoint == 'backtests/create' for endpoint, _ in cloud.calls) == 1
    cloud.own['status'] = 'Completed.'; cloud.runner.poll_status(0)
    cloud.stats['PRIVATE EXTRA'] = 'never retained'
    result = cloud.runner.read_once()
    assert result['cell_completed'] is True and result['result_cell'] == 1 and result['family_comparable'] is False
    assert result['diagnostic_only'] is False and result['accepted_risk_only'] is True
    assert result['expected_profile'] == cloud.profile
    assert set(cloud.validation[0][0]) == {m.previous.frozen.runtime.META_STATISTIC, m.previous.frozen.runtime.MONTHLY_STATISTIC}
    assert 'PRIVATE' not in json.dumps(result)
    m.validate_result_receipt(result)
    count = len(cloud.calls)
    for call in (cloud.runner.prepare_once, cloud.runner.launch_once, cloud.runner.read_once, cloud.runner.read_failure_once):
        with pytest.raises(m.Refused): call()
    assert len(cloud.calls) == count


@pytest.mark.parametrize('change', ['a14_id', 'a14_name', 'a14_compile', 'a14_status', 'missing', 'a13_extra', 'count'])
def test_exact_manual_a12_a14_history_required_before_source_or_edit(cloud, change):
    def mutate(endpoint, payload, value):
        if endpoint != 'backtests/list': return
        row = value['backtests'][2]
        if change == 'a14_id': row['backtestId'] = 'other'
        elif change == 'a14_name': row['name'] = 'other'
        elif change == 'a14_compile': row['compileId'] = 'other'
        elif change == 'a14_status': row['status'] = 'Completed.'
        elif change == 'missing': value['backtests'].pop(); value['count'] -= 1
        elif change == 'count': value['count'] = True
        else: value['backtests'].append(dict(row, backtestId='a13-unexpected')); value['count'] += 1
    cloud.mutation = mutate
    with pytest.raises(ValueError): cloud.runner.prepare_once()
    assert [endpoint for endpoint, _ in cloud.calls] == ['projects/read', 'projects/collaboration/read', 'backtests/list']


@pytest.mark.parametrize('change', ['main', 'runtime', 'unknown_file', 'missing', 'duplicate', 'project', 'after_lock'])
def test_initial_source_is_exact_a14_not_plain_a11_or_partial_recovery(cloud, change):
    if change in ('main', 'runtime'):
        cloud.files['main.py' if change == 'main' else m.RUNTIME_NAME] += b'# wrong source\n'
    def mutate(endpoint, payload, value):
        if endpoint == 'files/read':
            if change == 'unknown_file': value['files'][0]['name'] = 'unknown.py'
            if change == 'missing': value['files'].pop()
            if change == 'duplicate': value['files'][-1] = dict(value['files'][0])
            if change == 'project': value['files'][0]['projectId'] = True
        if endpoint == 'projects/collaboration/lock/acquire' and change == 'after_lock': cloud.files['main.py'] += b'# concurrent\n'
    cloud.mutation = mutate
    with pytest.raises(m.Refused): cloud.runner.prepare_once()
    assert not any(endpoint in ('files/update', 'compile/create', 'backtests/create') for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('change', ['running', 'public', 'dedicated', 'extra'])
def test_strict_access_unchanged_before_any_edit(cloud, change):
    if change == 'running': cloud.project['codeRunning'] = True
    elif change == 'public': cloud.project['public'] = True
    elif change == 'dedicated': cloud.dedicated['userPermissions'] = 'read'
    else: cloud.project['collaborators'].append({'owner': False})
    with pytest.raises(m.previous.ready.access.AccessRefused): cloud.runner.prepare_once()
    assert len(cloud.calls) == 2


@pytest.mark.parametrize('old', [m.previous.COMPILE_ID, m.A14_COMPILE_ID])
def test_compile_creation_cannot_reuse_old_identity(cloud, old):
    cloud.compile_id = old
    with pytest.raises(m.Refused): cloud.runner.prepare_once()
    with pytest.raises(m.Refused, match='^prepare_once$'): cloud.runner.prepare_once()
    assert not any(endpoint == 'backtests/create' for endpoint, _ in cloud.calls)


def test_compile_failure_terminal_blocks_every_launch(cloud):
    cloud.runner.prepare_once(); cloud.compile_state = 'BuildError'; cloud.compile_error = 'TypeError: PRIVATE SOURCE'
    assert cloud.runner.poll_compile(0)['state'] == 'BuildError'
    assert cloud.runner.terminal_receipt['failure_evidence']['python_error_category'] == 'TypeError'
    with pytest.raises(m.Refused, match='^launch_once$'): cloud.runner.launch_once()
    assert 'PRIVATE' not in json.dumps(cloud.runner.terminal_receipt)


def test_capacity_wait_does_not_cancel_or_launch_other_jobs(cloud):
    prepare(cloud); cloud.busy = True
    for index in range(3):
        cloud.time = index * 60
        assert cloud.runner.launch_once()['state'] == 'wait'
    cloud.time += 60
    with pytest.raises(m.Refused, match='^capacity_budget$'): cloud.runner.launch_once()
    assert not any(endpoint == 'backtests/create' for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('status', ['In Queue...', 'In Progress...', 'Completed.', 'Runtime Error'])
def test_create_accepts_exact_pending_and_fast_terminal_only(cloud, status):
    cloud.create_state = status
    result = launch(cloud)
    assert (result['terminal_receipt'] is not None) == (status in m.TERMINAL)
    assert result['launch_receipt']['attempt'] == 15
    with pytest.raises(m.Refused, match='^launch_once$'): cloud.runner.launch_once()


@pytest.mark.parametrize('change', ['a14', 'own_id', 'own_name', 'own_compile', 'extra'])
def test_status_requires_prior_three_plus_exact_own_job(cloud, change):
    launch(cloud)
    def mutate(endpoint, payload, value):
        if endpoint != 'backtests/list': return
        if change == 'a14': value['backtests'][2]['status'] = 'Completed.'
        elif change == 'own_id': value['backtests'][3]['backtestId'] = 'other'
        elif change == 'own_name': value['backtests'][3]['name'] = 'other'
        elif change == 'own_compile': value['backtests'][3]['compileId'] = 'other'
        else: value['backtests'].append(dict(value['backtests'][3])); value['count'] += 1
    cloud.mutation = mutate
    with pytest.raises(ValueError): cloud.runner.poll_status(0)


def test_runtime_error_detail_retains_only_new_finite_code_and_spends_single_read(cloud):
    launch(cloud); cloud.own['status'] = 'Runtime Error'; cloud.runner.poll_status(0)
    code = sorted(m.projection.FAILURE_CODES)[0]
    cloud.detail_error = 'Runtime Error: NewruleError: ' + code + '\nPRIVATE PRICE AND SYMBOL'
    cloud.stats['PRIVATE LICENSED ROWS'] = 'never retained'
    result = cloud.runner.read_failure_once()
    assert result['failure_evidence']['known_runtime_code'] == code
    assert result['failure_evidence']['diagnostic_context'] is None
    assert result['failure_evidence']['cause_authenticated'] is False
    assert cloud.validation == [] and 'PRIVATE' not in json.dumps(result)
    for call in (cloud.runner.read_failure_once, cloud.runner.read_once):
        with pytest.raises(m.Refused, match='^result_once$'): call()
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1


@pytest.mark.parametrize('prefix', ['NewruleError: ', 'RuntimeError: ', 'Runtime Error: '])
def test_all_exported_quote_fee_and_fill_codes_retained_without_raw_text(prefix):
    assert m.projection.FAILURE_CODES
    for code in m.projection.FAILURE_CODES:
        result = m.failure_evidence({'error': prefix + code + '\nPRIVATE SYMBOL AND PRICE'}, 'runtime_error')
        assert result['known_runtime_code'] == code and result['diagnostic_context'] is None
        assert result['known_runtime_code_sha256'] == m.sha(code.encode('ascii'))
        assert 'PRIVATE' not in json.dumps(result)
        m._validate_failure(result, 'runtime_error')


@pytest.mark.parametrize('text', ['PRIVATE arbitrary error', '\ud800', 'x' * (m.MAX_ERROR_BYTES + 1)])
def test_arbitrary_or_unbounded_error_is_unknown_not_retained(text):
    result = m.failure_evidence({'error': text}, 'runtime_error')
    assert result['known_runtime_code'] is result['diagnostic_context'] is None
    assert result['raw_error_retained'] is result['cause_authenticated'] is False


def test_single_error_read_preserves_known_list_code_when_detail_unknown(cloud):
    launch(cloud); cloud.own['status'] = 'Runtime Error'
    code = sorted(m.projection.FAILURE_CODES)[0]
    cloud.own['error'] = 'NewruleError: ' + code
    cloud.runner.poll_status(0)
    before = cloud.runner.terminal_receipt
    cloud.detail_error = 'PRIVATE arbitrary body'
    assert cloud.runner.read_failure_once() == before
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1


def test_error_read_conflict_preserves_old_terminal_and_spends_read(cloud):
    launch(cloud); cloud.own['status'] = 'Runtime Error'
    first, second = sorted(m.projection.FAILURE_CODES)[:2]
    cloud.own['error'] = 'NewruleError: ' + first
    cloud.runner.poll_status(0); before = cloud.runner.terminal_receipt
    cloud.detail_error = 'RuntimeError: ' + second
    with pytest.raises(m.Refused, match='^response$'): cloud.runner.read_failure_once()
    assert cloud.runner.terminal_receipt == before
    with pytest.raises(m.Refused, match='^result_once$'): cloud.runner.read_failure_once()


@pytest.mark.parametrize('change', ['id', 'name', 'compile', 'project', 'status', 'source'])
def test_error_only_read_reauthenticates_identity_and_source_without_statistics(cloud, change):
    launch(cloud); cloud.own['status'] = 'Runtime Error'; cloud.runner.poll_status(0)
    if change == 'source': cloud.files['main.py'] += b'# drift\n'
    def mutate(endpoint, payload, value):
        if endpoint != 'backtests/read': return
        key = {'id': 'backtestId', 'name': 'name', 'compile': 'compileId', 'project': 'projectId', 'status': 'status'}.get(change)
        if key: value['backtest'][key] = 'wrong'
    cloud.mutation = mutate
    with pytest.raises(ValueError): cloud.runner.read_failure_once()
    assert cloud.validation == []
    with pytest.raises(m.Refused, match='^result_once$'): cloud.runner.read_failure_once()


@pytest.mark.parametrize('endpoint', ['projects/create', 'files/create', 'files/delete', 'backtests/delete', 'projects/collaboration/delete', 'live/create'])
def test_forbidden_endpoints_never_dispatch(cloud, endpoint):
    with pytest.raises(m.Refused, match='^endpoint$'): cloud.runner._rpc('forged', endpoint, {'projectId': m.PROJECT_ID})
    assert cloud.calls == cloud.events == []


@pytest.mark.parametrize('field,bad', [('attempt', 14), ('attempt', True), ('schema', frozen.SCHEMA),
    ('profile_sha256', frozen.PROFILE_SHA256), ('diagnostic_only', True), ('accepted_risk_only', False), ('paper_or_live_ready', 0)])
def test_receipt_binding_cannot_reuse_old_policy_or_promote_flags(cloud, field, bad):
    receipt = cloud.runner.prepare_once(); receipt[field] = bad
    with pytest.raises(m.Refused): m.validate_compile_receipt(receipt)


def test_genuine_public_projection_and_unchanged_parameterized_result_validator():
    comparison = m.projection.comparison
    research = ROOT / 'research/analyst_revisions_v2_qc'
    names = set(comparison.bridge.parent.SOURCE_PINS) | set(comparison.NEW_SOURCE_PINS) | {comparison.HOST_SOURCE_NAME}
    sources = {name: (research / name).read_bytes() for name in names}
    spec = comparison.public_specification(sources=sources,
        expected_host_source_pins={comparison.HOST_SOURCE_NAME: m.sha(sources[comparison.HOST_SOURCE_NAME])})
    pairs = tuple((item.project_path, item.source_bytes) for item in spec.cells[0].source_files)
    patcher = (ROOT / 'scripts' / m.projection.PATCHER_NAME).read_bytes()
    projected = m.projection.public_specification(pairs, patcher_source_bytes=patcher, expected_patcher_sha256=m.sha(patcher))
    def forbidden(*_): pytest.fail('public constructor dispatched')
    runner = m.QuoteDiagnostic(projected.record_bytes, projected.source_pairs, request=forbidden, journal=forbidden)
    assert runner._profile['profile_sha256'] == m.PROFILE_SHA256
    assert m.sha(projected.record_bytes) == m.PROJECTION_SHA256
    assert m.sha(m.canonical(m.QuoteDiagnostic._manifest(dict(projected.source_pairs), m.PROJECTION_SHA256))) == m.SOURCE_MANIFEST_SHA256
    def validator(raw):
        tree = ast.parse(raw)
        return ast.dump(next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'validate_result_statistics'), include_attributes=False)
    assert validator(dict(projected.source_pairs)[m.RUNTIME_NAME]) == validator((research / m.RUNTIME_NAME).read_bytes())
