"""Fresh own-job fixture reads only; actual filesystem/account calls denied."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path

import pytest
from research.target_price_revisions_qc import extended_result_driver as d

e, N = d.e, d.e.JsonNumber
ACTUAL_LANE = d.LANE
CALENDAR = Path('research/target_price_revisions_qc/extended_calendar.json').read_bytes()
FREEZE = Path('research/target_price_revisions_qc/extended_study_freeze.json').read_bytes()


def helper(name):
    spec = importlib.util.spec_from_file_location('synthetic_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


nf, of = helper('test_qc_extended_native'), helper('test_qc_extended_operations')


@pytest.fixture(autouse=True)
def forbid_actual(monkeypatch):
    def denied(*_a, **_kw): raise AssertionError('actual credential/network/private/subprocess operation forbidden')
    monkeypatch.setattr(d.ops, 'credential', denied)
    monkeypatch.setattr(d.ops.http.client, 'HTTPSConnection', denied)
    monkeypatch.setattr(d.ops.Operations, '__init__', denied)
    monkeypatch.setattr(d.subprocess, 'run', denied)
    opening = d._open_directory
    def external(path):
        if path == ACTUAL_LANE or path.is_relative_to(ACTUAL_LANE): denied()
        return opening(path)
    monkeypatch.setattr(d, '_open_directory', external)


def sources():
    result = {name: b'# synthetic committed source fixture\n' for name in d.SOURCE_PATHS}
    result[d.PREFIX + 'extended_calendar.json'] = CALENDAR
    result[d.PREFIX + 'extended_study_freeze.json'] = FREEZE
    return result


def envelope(endpoint, request, response):
    return e.canonical({'schema': 'tpr-ext26-request-response-v1', 'endpoint': endpoint,
        'stage': e._STAGES[endpoint], 'request': request, 'response': response})


def evidence_fixture(action='diagnostics', *, compile_failure=False):
    candidate = nf.CANDIDATE; operation = 'synthetic-operation-001'; project, attempt, job = nf.PROJECT, 1, nf.JOB
    operation_manifest = of.manifest(operation=operation); selected = d.ops.validate_manifest(e.parse_json(e.canonical(operation_manifest)))[candidate]
    manifest = {'schema': 'tpr-ext26-execution-manifest-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
        'candidate_id': candidate, 'arm': e.CANDIDATES[candidate], 'project_id': project, 'baseline_git_head': 'b' * 40,
        'config_sha256': selected['config_sha256'], 'source_hashes': selected['source_hashes'],
        'input_hashes': selected['input_hashes'], 'max_attempts': 3}
    raw_manifest = e.canonical(manifest)
    reservation = {key: manifest[key] for key in ('study_id', 'candidate_id', 'project_id', 'config_sha256', 'freeze_sha256', 'source_hashes', 'input_hashes')}
    reservation.update(schema='tpr-ext26-attempt-reservation-v1', attempt=attempt, manifest_sha256=e.digest(raw_manifest), state='reserved')
    data = {'operations_manifest': e.canonical(operation_manifest), 'execution_manifest': raw_manifest, 'reservation': e.canonical(reservation)}
    data['compile_response'] = envelope('compile/read', {'projectId': project, 'compileId': 'synthetic-compile'},
        {'success': True, 'compileId': 'synthetic-compile', 'state': 'BuildError' if compile_failure else 'BuildSuccess',
         'errors': ['SyntaxError: SECRET-TOKEN PRIVATE-USER\nmain.py line 12'] if compile_failure else []})
    if not compile_failure:
        data['readback'] = envelope('files/read', {'projectId': project}, {'success': True,
            'files': [{'name': name, 'content': text} for name, text in selected['files'].items()]})
        data['compile_receipt'] = e.canonical({'schema': 'tpr-ext26-verified-compile-v1', 'manifest_sha256': e.digest(raw_manifest),
            'reservation_sha256': e.digest(data['reservation']), 'compile_response_sha256': e.digest(data['compile_response']),
            'source_readback_sha256': e.digest(data['readback']), 'project_id': project, 'compile_id': 'synthetic-compile'})
        data['launch'] = envelope('backtests/create', {'projectId': project, 'compileId': 'synthetic-compile',
            'backtestName': candidate + '-attempt-1'}, {'success': True, 'backtest': {'backtestId': job, 'projectId': project}})
        data['terminal'] = envelope('backtests/read', {'projectId': project, 'backtestId': job}, {'success': True,
            'backtest': {'backtestId': job, 'projectId': project, 'completed': True, 'status': 'Completed.', 'progress': 1, 'error': None}})
    data['closure'] = e.canonical({'schema': 'tpr-ext26-closed-attempt-v1', 'candidate_id': candidate, 'attempt': attempt,
        'manifest_sha256': e.digest(raw_manifest), 'reservation_sha256': e.digest(data['reservation']),
        'compile_response_sha256': e.digest(data['compile_response']), 'outcome': 'compile_failure' if compile_failure else 'backtest_terminal',
        'launch_sha256': None if compile_failure else e.digest(data['launch']), 'backtest_response_sha256': None if compile_failure else e.digest(data['terminal'])})
    if action == 'metrics':
        series, chart = nf.nav_fixture(); data.update(nav_series=e.canonical(series), nav_envelope=e.canonical(chart))
        pages, collection = nf.order_fixture([nf.order(events=False)])
        data.update(orders_collection=e.canonical(collection), orders_page_0=pages[0])
        cloud = of.Cloud(); cloud.files[project] = selected['files']
        for role, marker in (('summary', 'EXT26_SUMMARY'), ('index', 'EXT26_EVIDENCE_INDEX')):
            request = {'projectId': project, 'backtestId': job, 'start': 0, 'end': 100, 'query': marker}
            response = e.parse_json(cloud('backtests/read/log', e.canonical(request), 'application/json'))
            aggregate = d.ops.compact_aggregate(response['logs'][0], marker, manifest, attempt, job)
            data[role + '_aggregate'] = e.canonical(aggregate)
            data[role + '_envelope'] = e.canonical({'schema': 'tpr-ext26-native-read-envelope-v1', 'endpoint': 'backtests/read/log',
                'request': request, 'response': response, 'returned_identity_checks': d.ops._returned_identity(response, project, job)})
    return data, {'candidate_id': candidate, 'attempt': attempt, 'project_id': project, 'backtest_id': None if compile_failure else job,
        'action': action, 'qc_operation_id': operation, 'collection_sequence': 1 if action == 'metrics' else 0, 'order_pages': 1 if action == 'metrics' else 0}


def setup(tmp_path, *, action='diagnostics', compile_failure=False):
    data, arguments = evidence_fixture(action, compile_failure=compile_failure)
    scope = sources(); now = datetime.now(timezone.utc)
    plan = d._plan(source_hashes={name: d._sha(raw) for name, raw in scope.items()}, git_head='c' * 40,
        owner_instruction_sha256='f' * 64, created_utc=(now - timedelta(seconds=1)).isoformat(),
        expires_utc=(now + timedelta(hours=1)).isoformat(), read_operation_id='TPR-EXT26-RESULT-SYNTHETIC-001',
        inventory={role: {'sha256': d._sha(raw), 'bytes': len(raw)} for role, raw in data.items()}, mode='offline-fixture', **arguments)
    root = tmp_path / 'synthetic-private'; root.mkdir(mode=0o700)
    names = d._names(arguments['candidate_id'], 1, arguments['qc_operation_id'], action, not compile_failure,
                     arguments['collection_sequence'], arguments['order_pages'])
    for role, raw in data.items():
        (root / names[role]).write_bytes(raw); (root / names[role]).chmod(0o600)
    return plan, scope, root, data, now


def execute(fixture, **changes):
    plan, scope, root, _, now = fixture
    return e.parse_json(d._execute(plan, scope, root, clock=changes.pop('clock', lambda: now), guard=changes.pop('guard', lambda *_: None), **changes))


def test_completed_diagnostic_receipt_is_own_job_and_closed(tmp_path):
    fixture = setup(tmp_path); result = execute(fixture)
    assert result['status'] == 'COMPLETED' and result['scope_spent'] is True
    assert result['backtest_id'] == nf.JOB and result['terminal_status'] == 'Completed.'
    assert result['metrics'] is None and result['new_looks'].fraction() == 0
    assert len(result['read_inventory']) == 9


def test_compile_failure_is_consumed_without_invented_job_or_private_echo(tmp_path):
    fixture = setup(tmp_path, compile_failure=True); result = execute(fixture)
    assert result['status'] == 'COMPLETED' and result['backtest_id'] is None
    assert result['terminal_status'] == 'compile_failure'
    assert result['diagnostic']['known_error_types'] == ['SyntaxError']
    assert result['diagnostic']['code_frames'] == [{'file': 'main.py', 'line': N('12')}]
    assert b'SECRET' not in e.canonical(result) and b'PRIVATE-USER' not in e.canonical(result)


def test_metric_native_missing_observations_remain_null_and_rows_private(tmp_path):
    result = execute(setup(tmp_path, action='metrics'))
    assert result['status'] == 'COMPLETED'
    assert result['metrics']['nav_metrics']['observations'].fraction() == 1449
    assert result['metrics']['execution_metrics']['complete_reported_fees_usd'] is None
    assert result['metrics']['execution_metrics']['complete_reported_gross_turnover_decimal'] is None
    assert result['metrics']['order_census']['order_count'].fraction() == 1
    assert result['metrics']['strategy_accepted'] is False
    assert b'PRIVATE-TICKER' not in e.canonical(result) and b'order_id' not in e.canonical(result)
    assert len(result['private_output_hashes']) == 2


def test_claim_precedes_all_private_reads_and_second_run_refuses(tmp_path, monkeypatch):
    fixture = setup(tmp_path); plan, _, root, _, _ = fixture; read = d._read
    def observed(directory, name, **kw):
        assert (root / (plan['read_operation_id'] + '.claim.spent.json')).exists()
        return read(directory, name, **kw)
    monkeypatch.setattr(d, '_read', observed)
    assert execute(fixture)['status'] == 'COMPLETED'
    with pytest.raises(FileExistsError): execute(fixture)


@pytest.mark.parametrize('field,value', [('private_root', '/elsewhere'), ('max_total_bytes', 999999999),
    ('quantconnect_attempts', 1), ('network', True), ('source_hashes', {}), ('candidate_id', 'foreign')])
def test_tampered_plan_refuses_before_claim(tmp_path, field, value):
    fixture = setup(tmp_path); fixture[0][field] = value
    with pytest.raises((ValueError, KeyError)): execute(fixture)
    assert not list(fixture[2].glob('*.claim.spent.json'))


def test_expiry_and_moved_head_refuse_before_claim(tmp_path):
    fixture = setup(tmp_path)
    with pytest.raises(ValueError): execute(fixture, clock=lambda: fixture[4] + timedelta(days=3))
    with pytest.raises(ValueError): execute(fixture, guard=lambda *_: d._fail())
    assert not list(fixture[2].glob('*.claim.spent.json'))


@pytest.mark.parametrize('kind', ['hash', 'permission', 'symlink', 'hardlink', 'missing'])
def test_failed_private_read_keeps_spent_claim_and_closed_failure(tmp_path, kind):
    fixture = setup(tmp_path); plan, _, root, _, _ = fixture
    target = root / d._names(plan['candidate_id'], 1, plan['qc_operation_id'], 'diagnostics', True, 0, 0)['operations_manifest']
    if kind == 'hash': target.write_bytes(b'{"credential":"SECRET"}'); target.chmod(0o600)
    elif kind == 'permission': target.chmod(0o644)
    elif kind == 'symlink': target.unlink(); target.symlink_to(root / 'missing')
    elif kind == 'hardlink': os.link(target, root / 'other')
    else: target.unlink()
    result = execute(fixture)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['scope_spent'] is True
    assert result['metrics'] is None and result['diagnostic'] is None
    assert b'SECRET' not in e.canonical(result)


@pytest.mark.parametrize('role', ['terminal', 'closure', 'compile_response', 'readback'])
def test_rehashed_foreign_or_unknown_stage_not_accepted(tmp_path, role):
    fixture = setup(tmp_path); plan, _, root, data, _ = fixture
    body = e.parse_json(data[role])
    if role == 'terminal': body['response']['backtest']['backtestId'] = 'foreign-job'
    elif role == 'closure': body['outcome'] = 'unknown'
    elif role == 'compile_response': body['response']['compileId'] = 'foreign-compile'
    else: body['response']['files'][0]['content'] += '# foreign source\n'
    raw = e.canonical(body); plan['inventory'][role] = {'sha256': d._sha(raw), 'bytes': len(raw)}
    name = d._names(plan['candidate_id'], 1, plan['qc_operation_id'], 'diagnostics', True, 0, 0)[role]
    (root / name).write_bytes(raw); (root / name).chmod(0o600)
    assert execute(fixture)['status'] == 'FAILED_OR_UNCERTAIN'


def test_metrics_failure_does_not_turn_completed_zero_or_missing_data_into_success(tmp_path):
    fixture = setup(tmp_path, action='metrics'); fixture[0]['inventory']['nav_series']['sha256'] = '0' * 64
    result = execute(fixture)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['metrics'] is None


def test_actual_or_in_lane_fixture_root_cannot_open(monkeypatch, tmp_path):
    fixture = setup(tmp_path); plan, scope, _, _, now = fixture
    for root in (d.PRIVATE_ROOT, d.LANE / 'synthetic'):
        with pytest.raises(ValueError): d._execute(plan, scope, root, clock=lambda: now, guard=lambda *_: None)


def test_deadline_expires_without_refunding_claim(tmp_path, monkeypatch):
    fixture = setup(tmp_path); times = iter([0, 0, 0, 121])
    monkeypatch.setattr(d.time, 'monotonic', lambda: next(times))
    result = execute(fixture)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['read_bytes'].fraction() == 0


def test_closed_cli_refusal_does_not_print_inputs(monkeypatch, capsys):
    def denied(**_kw): raise AssertionError('SECRET-TOKEN should never be echoed')
    monkeypatch.setattr(d, 'run_result', denied)
    options = ['--read-operation-id', 'TPR-EXT26-RESULT-SYNTHETIC-001', '--qc-operation-id', 'synthetic', '--candidate-id', nf.CANDIDATE,
        '--project-id', '123', '--attempt', '1', '--backtest-id', 'none', '--owner-instruction-sha256', 'f' * 64,
        '--created-utc', '2026-10-10T00:00:00Z', '--expires-utc', '2026-10-11T00:00:00Z', '--inventory-json', '{}',
        '--inventory-sha256', d._sha(b'{}'), '--action', 'diagnostics']
    assert d.main(options) == 1
    output = capsys.readouterr().out
    assert 'SECRET' not in output and set(e.parse_json(output.encode())) == {'status', 'scope_spent', 'automatic_retry'}


def test_valid_stage_bytes_changed_without_inventory_rebinding_are_refused(tmp_path):
    fixture = setup(tmp_path); plan, _, root, data, _ = fixture
    body = e.parse_json(data['operations_manifest']); body['git_head'] = 'e' * 40
    name = d._names(plan['candidate_id'], 1, plan['qc_operation_id'], 'diagnostics', True, 0, 0)['operations_manifest']
    (root / name).write_bytes(e.canonical(body)); (root / name).chmod(0o600)
    result = execute(fixture)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and not result['read_inventory']


@pytest.mark.parametrize('change', ['extra_role', 'missing_role', 'excess_file', 'excess_total', 'path_role'])
def test_closed_inventory_cannot_expand_read_scope(tmp_path, change):
    fixture = setup(tmp_path); plan = fixture[0]
    if change == 'extra_role': plan['inventory']['unrelated'] = {'sha256': 'a' * 64, 'bytes': 1}
    elif change == 'missing_role': plan['inventory'].pop('closure')
    elif change == 'excess_file': plan['inventory']['closure']['bytes'] = d.MAX_FILE + 1
    elif change == 'excess_total':
        for value in plan['inventory'].values(): value['bytes'] = d.MAX_FILE
    else: plan['inventory']['../operator.db'] = plan['inventory'].pop('closure')
    with pytest.raises(ValueError): execute(fixture)
    assert not list(fixture[2].glob('*.claim.spent.json'))


def test_imported_function_replacement_refuses_before_any_private_open(monkeypatch):
    monkeypatch.setattr(d.native, 'normalize_nav', lambda *_a, **_kw: None)
    with pytest.raises(ValueError): d._verify_imports()


def test_source_closure_tamper_refuses_before_claim(tmp_path):
    fixture = setup(tmp_path); fixture[1][d.PREFIX + 'extended_native.py'] += b'# tampered\n'
    with pytest.raises(ValueError): execute(fixture)
    assert not list(fixture[2].glob('*.claim.spent.json'))


def discovery_setup(tmp_path, privacy='missing'):
    now = datetime.now(timezone.utc); scope = sources()
    plan = d._discovery_plan(source_hashes={name: d._sha(raw) for name, raw in scope.items()}, git_head='c' * 40,
        owner_instruction_sha256='f' * 64, created_utc=(now - timedelta(seconds=1)).isoformat(), expires_utc=(now + timedelta(hours=1)).isoformat(),
        read_operation_id='TPR-EXT26-PROJECT-DIAG-SYNTHETIC-001', qc_operation_id=d.DISCOVERY_QC_OPERATION, mode='offline-fixture')
    manifest = e.canonical(of.manifest(operation=d.DISCOVERY_QC_OPERATION)); manifest_sha = d._sha(manifest)
    payload_sha = d._sha(e.canonical({'name': d.DISCOVERY_CANDIDATE + '-private', 'language': 'Py'}))
    project = {'projectId': 123, 'name': d.DISCOVERY_CANDIDATE + '-private', 'owner': True, 'maxFileSize': 60000,
        'leanVersionId': 12345, 'organizationId': 'PRIVATE-ORGANIZATION',
        'collaborators': [{'owner': True, 'userId': 'PRIVATE-OWNER', 'email': 'PRIVATE-EMAIL'}], 'extra': 'PRIVATE-EXTRA'}
    if privacy != 'missing': project['isPublic'] = privacy
    projection = e.project_wire(e.canonical({'success': True, 'projects': [project]}), credential='')
    data = {'operations_manifest': manifest, 'request_projection': e.canonical(projection),
        'request_spent': e.canonical({'at': now.isoformat(), 'endpoint': 'projects/create', 'payload_sha256': payload_sha, 'manifest_sha256': manifest_sha}),
        'stage_spent': e.canonical({'at': now.isoformat(), 'payload_sha256': payload_sha, 'manifest_sha256': manifest_sha}),
        'stage_transport': e.canonical({'at': now.isoformat(), 'endpoint': 'projects/create'}),
        'request_terminal': e.canonical({'at': now.isoformat(), 'status': 'succeeded',
            'original_wire_sha256': projection['original_wire_sha256'], 'projection_sha256': projection['projection_sha256']})}
    root = tmp_path / 'discovery-private'; root.mkdir(mode=0o700)
    for role, raw in data.items():
        (root / d.DISCOVERY_FILES[role]).write_bytes(raw); (root / d.DISCOVERY_FILES[role]).chmod(0o600)
    return plan, scope, root, data, now


def discover(fixture):
    plan, scope, root, _, now = fixture
    return e.parse_json(d._discover(plan, scope, root, clock=lambda: now, guard=lambda *_: None))


@pytest.mark.parametrize('privacy', ['missing', False, True, 'unknown-type'])
def test_project_discovery_actual_field_presence_not_inferred_private(tmp_path, privacy):
    fixture = discovery_setup(tmp_path, privacy); result = discover(fixture)
    assert result['status'] == 'COMPLETED' and len(result['read_inventory']) == 6
    census = result['field_census']
    assert census['project_id']['value'].fraction() == 123 and census['intended_name_match'] is True
    assert census['is_public']['present'] is (privacy != 'missing')
    assert census['is_public']['value'] is (privacy if type(privacy) is bool else None)
    assert census['privacy_attested'] is False and result['project_creation_repeated'] is False
    raw_public = e.canonical(result)
    for private in (b'PRIVATE-ORGANIZATION', b'PRIVATE-OWNER', b'PRIVATE-EMAIL', b'PRIVATE-EXTRA'): assert private not in raw_public
    private_raw = (fixture[2] / result['project_admission_name']).read_bytes(); artifact = e.parse_json(private_raw)
    assert d._sha(private_raw) == result['project_admission_sha256']
    assert artifact['project']['organization_id'] == 'PRIVATE-ORGANIZATION' and artifact['admitted'] is False
    assert artifact['privacy']['documented_default_private'] is False
    assert artifact['field_census_sha256'] == d._sha(e.canonical(census))
    assert artifact['six_file_hashes'] == {role: row['sha256'] for role, row in result['read_inventory'].items()}


def test_project_discovery_fresh_claim_precedes_unknown_hash_reads_and_refuses_repeat(tmp_path, monkeypatch):
    fixture = discovery_setup(tmp_path); root, operation = fixture[2], fixture[0]['read_operation_id']; reading = d._read
    def observed(*args, **kw):
        assert (root / (operation + '.claim.spent.json')).exists()
        assert kw['private'] is True and 'expected' not in kw
        return reading(*args, **kw)
    monkeypatch.setattr(d, '_read', observed)
    assert discover(fixture)['status'] == 'COMPLETED'
    with pytest.raises(FileExistsError): discover(fixture)


@pytest.mark.parametrize('role,field', [('request_spent', 'payload_sha256'), ('stage_spent', 'manifest_sha256'),
    ('request_terminal', 'projection_sha256'), ('stage_transport', 'endpoint'), ('request_projection', 'projection_sha256')])
def test_project_discovery_lineage_refusal_keeps_claim_and_no_artifact(tmp_path, role, field):
    fixture = discovery_setup(tmp_path); data = fixture[3]
    body = e.parse_json(data[role]); body[field] = 'foreign/endpoint' if field == 'endpoint' else '0' * 64
    target = fixture[2] / d.DISCOVERY_FILES[role]; target.write_bytes(e.canonical(body)); target.chmod(0o600)
    result = discover(fixture)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['scope_spent'] is True
    assert result['field_census'] is None and result['project_admission_name'] is None
    assert not list(fixture[2].glob('*.project-admission.json'))


def test_project_discovery_cannot_expand_fixed_six_or_change_request_slot(tmp_path):
    fixture = discovery_setup(tmp_path); fixture[0]['files']['operator'] = 'operator-state.db'
    with pytest.raises(ValueError): discover(fixture)
    assert len(d.DISCOVERY_FILES) == 6 and not list(fixture[2].glob('*.claim.spent.json'))


def test_project_discovery_wrong_operation_or_expiry_refuses_before_claim(tmp_path):
    fixture = discovery_setup(tmp_path); fixture[0]['qc_operation_id'] = 'unrelated-operation'
    with pytest.raises(ValueError): discover(fixture)
    fixture[0]['qc_operation_id'] = d.DISCOVERY_QC_OPERATION
    fixture[0]['expires_utc'] = (fixture[4] - timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError): discover(fixture)
    assert not list(fixture[2].glob('*.claim.spent.json'))
