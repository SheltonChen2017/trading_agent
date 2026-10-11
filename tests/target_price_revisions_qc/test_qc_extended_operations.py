"""Synthetic controller proofs: actual roots, credentials and HTTPS denied."""
from copy import deepcopy
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from research.target_price_revisions_qc import extended_evidence as e, extended_operations as o, extended_driver as d

ON, OFF = tuple(e.CANDIDATES)
INPUT = b'{"schema":"synthetic-input-only"}\n'


def calendar_raw():
    # This is a committed public date-only freeze, not private market data.
    raw = (Path(__file__).resolve().parents[2] / 'research/target_price_revisions_qc/extended_calendar.json').read_bytes()
    assert e.digest(raw) == o.CALENDAR_SHA256
    return raw


def chart_response(*, shape='array', nav='100000'):
    values = []
    for session in e.parse_json(calendar_raw())['valuation_sessions']:
        instant = datetime.fromisoformat(session + 'T16:01:00').replace(tzinfo=ZoneInfo('America/New_York'))
        point = [int(instant.timestamp()), e.JsonNumber(nav)]
        values.append({'x': point[0], 'y': point[1]} if shape == 'legacy' else point)
    return {'success': True, 'chart': {'name': 'EXT26 Account NAV', 'chartType': 0,
        'series': {'NAV': {'name': 'NAV', 'unit': '$', 'seriesType': 0, 'values': values}}}}


@pytest.fixture(autouse=True)
def actual_io_denied(monkeypatch):
    def denied(*args, **kwargs): raise AssertionError('actual credential/network/root access forbidden in synthetic test')
    monkeypatch.setattr(o, 'credential', denied)
    monkeypatch.setattr(o.http.client, 'HTTPSConnection', denied)
    original = o.Operations.guard
    def guard(self):
        assert self.fixture, 'actual operation root forbidden in synthetic test'
        return original(self)
    monkeypatch.setattr(o.Operations, 'guard', guard)


def manifest(attempt=1, operation='synthetic-operation-001'):
    clock = datetime.now(timezone.utc)
    inputs = [{'name': 'packet.json', 'sha256': e.digest(INPUT), 'bytes': len(INPUT),
        'key': 'tpr-ext26/inputs/' + e.STUDY_ID + '/' + 'a' * 64 + '/' + e.digest(INPUT) + '.json'}]
    rows = []
    for candidate, arm in e.CANDIDATES.items():
        config = {'schema': 'tpr-ext26-config-v1', 'study_id': e.STUDY_ID, 'candidate_id': candidate,
            'arm': arm, 'freeze_sha256': e.FREEZE_SHA256, 'input_hashes': {'packet.json': e.digest(INPUT), 'calendar.json': o.CALENDAR_SHA256, 'preparation.json': 'a' * 64}}
        text = e.canonical(config).decode()
        files = {'main.py': '# synthetic fresh algorithm\n', 'extended_config.py': 'CONFIG_JSON = ' + repr(text) + '\n',
                 'extended_core.py': '# synthetic new core\n',
                 'extended_loader.py': 'CALENDAR_JSON = ' + repr(calendar_raw().decode()) + '\n'}
        rows.append({'candidate_id': candidate, 'planned_attempt': attempt, 'project_name': candidate + '-private',
            'config_raw': text, 'files': files, 'input_hashes': config['input_hashes']})
    return {'schema': 'tpr-ext26-operations-manifest-v1', 'study_id': e.STUDY_ID, 'operation_id': operation,
        'created_utc': (clock - timedelta(seconds=1)).isoformat(), 'expires_utc': (clock + timedelta(hours=1)).isoformat(),
        'git_head': 'c' * 40, 'freeze_sha256': e.FREEZE_SHA256, 'preparation_sha256': 'a' * 64,
        'repository_source_hashes': {relative: 'd' * 64 for relative in ('research/target_price_revisions_qc/extended_operations.py',
            'research/target_price_revisions_qc/extended_driver.py', 'research/target_price_revisions_qc/extended_evidence.py')},
        'candidates': rows, 'inputs': inputs, 'max_requests': 4096, 'max_response_bytes': e.MAX_BYTES,
        'request_seconds': 30, 'max_orders': 50000, 'max_collections': 3}


class Cloud:
    def __init__(self):
        self.calls, self.files = [], {}
        self.state, self.fail, self.wrong_job, self.loading, self.order_count = 'BuildSuccess', None, False, False, 105

    def __call__(self, endpoint, raw, content_type):
        self.calls.append(endpoint)
        if self.fail == endpoint: raise OSError('synthetic transport failure')
        if endpoint in {'authenticate', 'object/set'}: return e.canonical({'success': True})
        body = e.parse_json(raw)
        if endpoint == 'projects/create':
            project = 101 + len(self.files); self.files[project] = {'main.py': '# fresh default\n', 'research.ipynb': '{}'}
            return e.canonical({'success': True, 'projects': [{'projectId': project, 'name': body['name'], 'owner': True,
                'isPublic': False, 'maxFileSize': 64000, 'leanVersionId': 18178, 'organizationId': 'synthetic-org', 'collaborators': []}]})
        project = o._int(body['projectId']); files = self.files[project]
        if endpoint == 'files/read': return e.canonical({'success': True, 'files': [{'name': name, 'content': text} for name, text in files.items()]})
        if endpoint in {'files/create', 'files/update'}:
            files[body['name']] = body['content']; return e.canonical({'success': True})
        if endpoint == 'compile/create': return e.canonical({'success': True, 'compileId': 'compile-synthetic', 'state': 'InQueue'})
        if endpoint == 'compile/read': return e.canonical({'success': True, 'compileId': body['compileId'], 'state': self.state})
        if endpoint == 'backtests/create': return e.canonical({'success': True, 'backtest': {'backtestId': 'job-synthetic', 'projectId': project}})
        if endpoint == 'backtests/read': return e.canonical({'success': True, 'backtest': {'backtestId': 'foreign-job' if self.wrong_job else body['backtestId'],
            'projectId': project, 'completed': True, 'progress': 1, 'status': 'Completed.', 'error': None,
            'statistics': {'Net Profit': '-5.0%'}, 'charts': {'Strategy Equity': {'series': {}}, 'Benchmark': {'must_not_export': True}}}})
        if endpoint == 'backtests/orders/read':
            if self.loading: return e.canonical({'success': True, 'status': 'Loading'})
            start, end = int(body['start'].lexeme), int(body['end'].lexeme)
            return e.canonical({'success': True, 'length': self.order_count, 'orders': [{'id': index + 1, 'status': 3}
                for index in range(start, min(end, self.order_count))]})
        if endpoint == 'backtests/chart/read':
            if body['name'] == 'EXT26 Account NAV': return e.canonical(chart_response())
            return e.canonical({'success': True, 'chart': {'name': body['name'], 'series': {}}})
        if endpoint == 'backtests/read/log':
            text = ast.literal_eval(ast.parse(files['extended_config.py']).body[0].value)
            config = e.parse_json(text.encode()); candidate = config['candidate_id']
            binding = {'candidate_id': candidate, 'attempt': 1, 'config_sha256': e.digest(text.encode()),
                'freeze_sha256': e.FREEZE_SHA256, 'project_id': project, 'job_id': body['backtestId'],
                'internally_meaningful_execution': True, 'strategy_accepted': False, 'canonical_admission': False}
            if body['query'] == 'EXT26_SUMMARY':
                summary = {**binding, 'study_id': e.STUDY_ID, 'arm': config['arm'], 'input_hashes': config['input_hashes'],
                    'calendar_sha256': config['input_hashes']['calendar.json'], 'coverage_complete': True,
                    'full_evidence_retrieval_verified': False, 'independent_sleeve_pnl_observed': False,
                    'last_valuation_session': '2026-10-09', 'engine_end_utc': '2026-10-09T20:00:00+00:00',
                    'reason_counts': {}, 'delisting_audit': {}}
                for key in ('decisions', 'refused_decisions', 'valuation_days', 'submitted_orders', 'fill_events',
                    'requested_shares', 'submitted_shares', 'filled_shares', 'position_ledger_mismatches', 'risk_breaches', 'name_soft_cap_breaches'):
                    summary[key] = 0
                summary.update(decisions=301, valuation_days=1486, submitted_orders=105, fill_events=105)
                for key in ('fees', 'max_cash_ledger_residual', 'max_nav_ledger_residual', 'max_name_exposure'):
                    summary[key] = {'numerator': '0', 'denominator': '1'}
                summary.update(clock_assertions=301, cap_snapshot_coverage={'available_decisions': 0, 'missing_decisions': 0,
                    'unobserved_decisions': 301}, per_sleeve_coverage={})
                for etf in ('SPY', 'QQQ', 'SOXX', 'XLV', 'REMX', 'XLE'):
                    sleeve = {'membership_available_decisions': 0, 'membership_missing_decisions': 0,
                        'membership_unobserved_decisions': 301, 'construction_observed_decisions': 0,
                        'construction_unobserved_decisions': 301, 'selected_any_decisions': 0, 'selected_zero_decisions': 0,
                        'cap_state_counts': {key: 0 for key in ('available', 'missing', 'unknown', 'invalid', 'nonpositive')},
                        'tpr_state_counts': {key: 0 for key in ('nonzero', 'zero', 'missing', 'unknown', 'invalid', 'not_used')}}
                    for key in ('cap_ranked_slots', 'executable_slots', 'selected_slots'):
                        sleeve[key] = {'observed_decisions': 0, 'sum': 0, 'min': None, 'max': None}
                    summary['per_sleeve_coverage'][etf] = sleeve
                summary['cash_exposure_aggregate'] = {'nav_observations': 1449, 'expected_nav_observations': 1449,
                    'missing_nav_observations': 0, 'dimensionless_mean_precision_digits': 50,
                    'dimensionless_mean_rounding': 'ROUND_HALF_EVEN', 'dimensionless_means_are_rounded': True}
                for key in ('cash_usd', 'cash_fraction', 'gross_exposure'):
                    summary['cash_exposure_aggregate'][key] = {'observations': 1449,
                        **{name: {'numerator': '0', 'denominator': '1'} for name in ('min', 'max', 'mean')}}
                    if key != 'cash_usd': summary['cash_exposure_aggregate'][key]['mean'] = '0'
                summary['matched_input_chains'] = {etf: {domain: {'sha256': 'f' * 64, 'observed_decisions': 0,
                    'unavailable_decisions': 301, 'expected_decisions': 301} for domain in ('membership', 'caps', 'selection', 'prior_marks')}
                    for etf in ('SPY', 'QQQ', 'SOXX', 'XLV', 'REMX', 'XLE')}
                aggregate = summary
            else:
                aggregate = {**binding, 'index_key': ('tpr-ext26/evidence/' + candidate + '/' + binding['config_sha256']
                    + '/attempt-1/' + str(project) + '/' + body['backtestId'] + '/index.json'), 'index_sha256': 'f' * 64,
                    'chunks': 1, 'records': 302, 'bytes': 1000, 'record_kind_counts': {'NAV': 301, 'SUMMARY': 1}}
            return e.canonical({'success': True, 'length': 1, 'logs': [body['query'] + ' ' + e.canonical(aggregate).decode()]})
        raise AssertionError('unexpected synthetic endpoint')


@pytest.fixture
def environment(tmp_path):
    body, cloud = manifest(), Cloud()
    controller = o.Operations(body, manifest_sha256=e.digest(e.canonical(body)), fixture_root=tmp_path / 'private', fixture_transport=cloud)
    controller.prepare()
    inputs = controller.root / 'fixture-inputs'; inputs.mkdir(mode=0o700)
    file = inputs / 'packet.json'; file.write_bytes(INPUT); file.chmod(0o600)
    return controller, cloud


def ready(environment, candidate=OFF, *, launch=False, terminal=False):
    controller, cloud = environment
    controller.create_project(candidate); controller.upload_sources(candidate)
    if candidate == ON: controller.upload_inputs(candidate)
    attempt = controller.reserve(candidate)['attempt']; controller.compile(candidate, attempt); controller.compile_status(candidate, attempt)
    if launch: controller.launch(candidate, attempt)
    if terminal: controller.status(candidate, attempt)
    return controller, cloud, attempt


@pytest.mark.parametrize('candidate', [ON, OFF])
def test_complete_fresh_synthetic_lifecycle_binds_sources_compile_attempt_and_orders(environment, candidate):
    controller, cloud, attempt = ready(environment, candidate, launch=True, terminal=True)
    result = controller.collect_orders(candidate, attempt)
    assert result['order_count'] == 105 and len(result['pages']) == 2
    assert result['strategy_accepted'] is False and result['new_looks'] == 0
    assert cloud.calls.count('backtests/create') == cloud.calls.count('compile/create') == 1
    if candidate == OFF: assert 'object/set' not in cloud.calls
    look = controller.value(candidate + '.attempt.1.look.json')
    assert look['consumed'] is False and look['fixture'] is True
    native = controller.collect_native(candidate, attempt)
    assert native['full_object_chunks_downloaded'] is native['independent_input_row_replay'] is False
    assert 'object/get' not in cloud.calls


@pytest.mark.parametrize('field,value', [('freeze_sha256', '0' * 64), ('study_id', 'old-study'), ('max_requests', 4097),
    ('request_seconds', True), ('max_orders', 50001), ('max_collections', 4), ('inputs', [])])
def test_manifest_scope_widening_or_boolean_bounds_refuse(field, value):
    body = manifest(); body[field] = value
    with pytest.raises(o.Refusal): o.validate_manifest(e.parse_json(e.canonical(body)))


@pytest.mark.parametrize('endpoint', ['object/get', 'live/create', 'projects/read', 'backtests/list', 'organizations/read'])
def test_unscoped_or_restricted_endpoints_refuse_before_transport(environment, endpoint):
    controller, cloud = environment
    project = controller.create_project(OFF)
    before = len(cloud.calls)
    with pytest.raises(o.Refusal): controller.request(endpoint, {'projectId': o._int(project['project_id'])}, candidate=OFF)
    assert len(cloud.calls) == before


@pytest.mark.parametrize('endpoint', ['projects/create', 'files/update', 'compile/create', 'backtests/create', 'object/set'])
def test_direct_effectful_transport_without_typed_stage_refuses(environment, endpoint):
    controller, cloud = environment
    with pytest.raises(o.Refusal): controller.request(endpoint, {})
    assert cloud.calls == []


def test_known_project_does_not_authorize_arbitrary_source_write(environment):
    controller, cloud = environment
    project = controller.create_project(OFF)
    before = len(cloud.calls)
    with pytest.raises(o.Refusal):
        controller.effect('files/update', {'projectId': o._int(project['project_id']), 'name': 'main.py', 'content': '# foreign\n'},
            OFF + '.source.' + controller.operation + '.main.py', OFF)
    assert len(cloud.calls) == before


def test_foreign_project_refuses_before_api(environment):
    controller, cloud = environment; controller.create_project(OFF)
    before = len(cloud.calls)
    with pytest.raises(o.Refusal): controller.request('files/read', {'projectId': 999}, candidate=OFF)
    assert len(cloud.calls) == before


def test_wrong_cloud_source_blocks_reservation_and_compile(environment):
    controller, cloud, attempt = ready(environment)
    project = o._int(controller.project(OFF)['project_id']); cloud.files[project]['main.py'] = '# changed\n'
    before = cloud.calls.count('backtests/create')
    with pytest.raises(o.Refusal): controller.launch(OFF, attempt)
    assert cloud.calls.count('backtests/create') == before


def test_unknown_compile_request_keeps_reserved_counter_and_blocks_successor(environment):
    controller, cloud = environment; controller.create_project(OFF); controller.upload_sources(OFF); controller.reserve(OFF)
    cloud.fail = 'compile/create'
    with pytest.raises(o.Refusal): controller.compile(OFF, 1)
    body = manifest(attempt=2, operation='synthetic-operation-002')
    successor = o.Operations(body, manifest_sha256=e.digest(e.canonical(body)), fixture_root=controller.root, fixture_transport=cloud)
    successor.prepare()
    with pytest.raises(o.Refusal): successor.reserve(OFF)
    assert cloud.calls.count('compile/create') == 1


def test_known_failed_compile_closes_consumed_slot_without_launch(environment):
    controller, cloud = environment; cloud.state = 'BuildError'
    controller.create_project(OFF); controller.upload_sources(OFF); controller.reserve(OFF); controller.compile(OFF, 1); controller.compile_status(OFF, 1)
    assert 'backtests/create' not in cloud.calls
    body = manifest(attempt=2, operation='synthetic-operation-002')
    successor = o.Operations(body, manifest_sha256=e.digest(e.canonical(body)), fixture_root=controller.root, fixture_transport=cloud)
    successor.prepare(); assert successor.reserve(OFF)['attempt'] == 2


def test_three_consumed_slots_survive_every_source_operation_identity(environment):
    controller, cloud = environment; cloud.state = 'BuildError'
    controller.create_project(OFF)
    for attempt in (1, 2, 3):
        if attempt != 1:
            body = manifest(attempt=attempt, operation='synthetic-operation-00' + str(attempt))
            controller = o.Operations(body, manifest_sha256=e.digest(e.canonical(body)), fixture_root=controller.root, fixture_transport=cloud)
            controller.prepare()
        controller.upload_sources(OFF); assert controller.reserve(OFF)['attempt'] == attempt
        controller.compile(OFF, attempt); controller.compile_status(OFF, attempt)
    body = manifest(attempt=3, operation='synthetic-operation-004')
    successor = o.Operations(body, manifest_sha256=e.digest(e.canonical(body)), fixture_root=controller.root, fixture_transport=cloud)
    successor.prepare()
    with pytest.raises(o.Refusal, match='three attempts consumed'): successor.reserve(OFF)
    assert cloud.calls.count('compile/create') == 3 and 'backtests/create' not in cloud.calls


def test_compile_terminal_polling_is_idempotent(environment):
    controller, cloud, attempt = ready(environment)
    calls = len(cloud.calls)
    assert controller.compile_status(OFF, attempt)['state'] == 'BuildSuccess'
    assert len(cloud.calls) == calls


def test_known_completed_job_can_be_collected_under_fresh_code_operation_without_reset(environment):
    controller, cloud, attempt = ready(environment, launch=True, terminal=True)
    body = manifest(operation='synthetic-operation-002'); body['git_head'] = 'e' * 40
    successor = o.Operations(body, manifest_sha256=e.digest(e.canonical(body)), fixture_root=controller.root, fixture_transport=cloud)
    successor.prepare()
    assert successor.collect_orders(OFF, attempt)['order_count'] == 105
    assert cloud.calls.count('compile/create') == cloud.calls.count('backtests/create') == 1


def test_persistent_request_budget_is_consumed_before_next_transport(environment):
    controller, cloud = environment
    body = manifest(); body['max_requests'] = 1
    # Use a separately hash-bound manifest, not mutate the already admitted one.
    body['operation_id'] = 'synthetic-limited'
    limited = o.Operations(body, manifest_sha256=e.digest(e.canonical(body)), fixture_root=controller.root, fixture_transport=cloud)
    limited.prepare(); limited.request('authenticate', {})
    with pytest.raises(o.Refusal, match='request budget'): limited.request('authenticate', {})
    assert cloud.calls == ['authenticate']


@pytest.mark.parametrize('bad', ['wrong-key', 'wrong-hash', 'wrong-size'])
def test_on_upload_receipt_requires_exact_key_hash_and_size(environment, bad):
    controller, cloud, attempt = ready(environment, ON)
    name = 'input.' + e.digest(INPUT) + '.completed.json'
    receipt = controller.value(name)
    if bad == 'wrong-key': receipt['key'] = 'foreign/key'
    if bad == 'wrong-hash': receipt['sha256'] = 'f' * 64
    if bad == 'wrong-size': receipt['bytes'] = 1
    (controller.root / name).write_bytes(e.canonical(receipt))
    with pytest.raises(o.Refusal): controller.launch(ON, attempt)
    assert 'backtests/create' not in cloud.calls


def test_input_read_and_wire_claims_precede_upload_and_off_never_reads(environment):
    controller, cloud = environment; controller.create_project(ON)
    observed = []
    original = controller.transport
    def transport(endpoint, raw, content_type):
        if endpoint == 'object/set':
            observed.append(((controller.root / ('input.' + e.digest(INPUT) + '.read.spent.json')).exists(),
                (controller.root / ('input.' + e.digest(INPUT) + '.upload.spent.json')).exists()))
        return original(endpoint, raw, content_type)
    controller.transport = transport
    controller.upload_inputs(ON)
    assert observed == [(True, True)]
    with pytest.raises(o.Refusal): controller.upload_inputs(OFF)


def test_terminal_status_cannot_close_on_boolean_progress_or_missing_error(environment):
    controller, cloud, attempt = ready(environment, launch=True)
    original = controller.transport
    def transport(endpoint, raw, content_type):
        response = e.parse_json(original(endpoint, raw, content_type))
        if endpoint == 'backtests/read': response['backtest']['progress'] = True
        return e.canonical(response)
    controller.transport = transport
    with pytest.raises(o.Refusal): controller.status(OFF, attempt)
    assert not (controller.root / (OFF + '.attempt.1.closure.json')).exists()


def test_no_matching_compact_summary_remains_explicit_native_diagnostic(environment):
    controller, cloud, attempt = ready(environment, launch=True, terminal=True)
    original = controller.transport
    def transport(endpoint, raw, content_type):
        return e.canonical({'success': True, 'logs': [], 'length': 0}) if endpoint == 'backtests/read/log' else original(endpoint, raw, content_type)
    controller.transport = transport
    result = controller.collect_native(OFF, attempt)
    assert result['classification'] == 'diagnostic_missing_evidence' and result['strategy_accepted'] is False


def test_input_keys_cannot_reuse_old_study_or_escape_preparation_prefix():
    body = manifest(); body['inputs'][0]['key'] = 'tpr-cap-tilt/old-study/packet.json'
    with pytest.raises(o.Refusal): o.validate_manifest(e.parse_json(e.canonical(body)))


def test_main_source_declared_planned_attempt_is_not_a_fourth_slot():
    body = manifest(); body['candidates'][0]['planned_attempt'] = 4
    with pytest.raises(o.Refusal): o.validate_manifest(e.parse_json(e.canonical(body)))


def test_unknown_extra_cloud_source_never_gets_overwritten(environment):
    controller, cloud = environment; project = controller.create_project(OFF)
    cloud.files[o._int(project['project_id'])]['unrelated.py'] = '# user-owned\n'
    before = len(cloud.calls)
    with pytest.raises(o.Refusal): controller.upload_sources(OFF)
    assert not any(endpoint in {'files/create', 'files/update'} for endpoint in cloud.calls[before:])


def test_declared_manifest_is_copied_before_caller_mutation(environment):
    controller, _ = environment
    body = manifest(); first = o.Operations(body, manifest_sha256=e.digest(e.canonical(body)), fixture_root=controller.root, fixture_transport=controller.transport)
    body['candidates'][0]['files']['main.py'] = '# attacker changed caller body\n'
    assert first.candidate(ON)['files']['main.py'] == '# synthetic fresh algorithm\n'


def test_future_controller_declares_no_restricted_export_or_operator_state_import():
    text = Path(o.__file__).read_text()
    assert 'object/get' not in text and 'assistant.' not in text and 'sqlite3' not in text


def test_unknown_launch_never_retries_or_refunds(environment):
    controller, cloud, attempt = ready(environment); cloud.fail = 'backtests/create'
    with pytest.raises(o.Refusal): controller.launch(OFF, attempt)
    body = manifest(attempt=2, operation='synthetic-operation-002')
    successor = o.Operations(body, manifest_sha256=e.digest(e.canonical(body)), fixture_root=controller.root, fixture_transport=cloud)
    successor.prepare()
    with pytest.raises(o.Refusal): successor.reserve(OFF)
    assert cloud.calls.count('backtests/create') == 1


def test_duplicate_launch_cannot_repeat_network(environment):
    controller, cloud, attempt = ready(environment, launch=True)
    with pytest.raises(o.Refusal): controller.launch(OFF, attempt)
    assert cloud.calls.count('backtests/create') == 1


def test_concurrent_or_crashed_claim_blocks_new_operation(environment):
    controller, cloud = environment
    controller.write('controller.lock', {'synthetic_owner': True})
    with pytest.raises(o.Refusal): controller.create_project(OFF)
    assert cloud.calls == []


def test_loading_order_page_is_retained_and_not_treated_as_zero(environment):
    controller, cloud, attempt = ready(environment, launch=True, terminal=True); cloud.loading = True
    with pytest.raises(o.Refusal): controller.collect_orders(OFF, attempt)
    paths = list(controller.root.glob('*.orders.00000.json'))
    assert len(paths) == 1 and controller.value(paths[0].name)['status'] == 'Loading'


def test_foreign_terminal_cannot_close_attempt(environment):
    controller, cloud, attempt = ready(environment, launch=True); cloud.wrong_job = True
    with pytest.raises(o.Refusal): controller.status(OFF, attempt)
    assert not (controller.root / (OFF + '.attempt.1.closure.json')).exists()


def test_own_wire_number_lexeme_remains_distinct_from_original_wire_hash(environment):
    controller, cloud = environment
    controller.transport = lambda *args: b'{"success":true,"value":0.123456789012345678901234567890}'
    value = controller.request('authenticate', {})
    assert value['value'].lexeme == '0.123456789012345678901234567890'
    receipt = controller.value('request.0001.projection.json')
    assert receipt['original_wire_sha256'] != receipt['projection_sha256']


def test_production_signing_branch_uses_only_explicit_synthetic_https_and_credentials(environment, monkeypatch):
    controller, _ = environment
    seen = {}
    class Response:
        status = 200
        def read(self, bound):
            seen['response_bound'] = bound
            return b'{"success":true,"value":0.123456789012345678901}'
    class Connection:
        def __init__(self, host, **kwargs): seen['host'] = host; seen.update(kwargs)
        def request(self, method, path, **kwargs): seen.update(method=method, path=path, **kwargs)
        def getresponse(self): return Response()
        def close(self): seen['closed'] = True
    # The fixture root remains private synthetic storage. Only the request route
    # toggles; every actual credential and network entry remains mocked here.
    monkeypatch.setattr(controller, 'guard', lambda: None)
    monkeypatch.setattr(controller, '_ensure_root', lambda: o._custody(controller.root.stat(), True))
    monkeypatch.setattr(o, 'credential', lambda: ('12345', 'SYNTHETIC_TOKEN_123'))
    monkeypatch.setattr(o.http.client, 'HTTPSConnection', Connection)
    controller.fixture = False
    value = controller.request('authenticate', {})
    assert value['value'].lexeme == '0.123456789012345678901'
    assert seen['host'] == 'www.quantconnect.com' and seen['path'] == '/api/v2/authenticate'
    assert seen['method'] == 'POST' and seen['closed'] is True
    assert seen['context'].keylog_filename is None and seen['context'].check_hostname is True
    assert seen['context'].verify_mode == o.ssl.CERT_REQUIRED and seen['timeout'] == 30
    assert 'SYNTHETIC_TOKEN_123' not in seen['headers']['Authorization']
    assert seen['response_bound'] == e.MAX_BYTES + 1


def test_terminal_collector_refuses_false_original_closure_hash(environment):
    controller, _, attempt = ready(environment, launch=True, terminal=True)
    _, rows = controller.history(OFF)
    row = dict(rows[0]); closure = e.parse_json(row['closure'])
    closure['manifest_sha256'] = '0' * 64
    row['closure'] = e.canonical(closure)
    with pytest.raises(o.Refusal): controller.validate_terminal(OFF, attempt, row)


def test_native_collection_gets_fresh_bound_account_without_replacing_terminal(environment):
    controller, cloud, attempt = ready(environment, launch=True, terminal=True)
    original = controller.read(OFF + '.attempt.1.terminal.json')
    before = cloud.calls.count('backtests/read')
    result = controller.collect_native(OFF, attempt)
    assert cloud.calls.count('backtests/read') == before + 1
    assert controller.read(OFF + '.attempt.1.terminal.json') == original
    assert result['classification'] == 'native_evidence_requires_accounting_audit'


def test_unhashable_private_input_key_fails_closed():
    body = manifest(); body['inputs'][0]['key'] = []
    with pytest.raises(o.Refusal): o.validate_manifest(e.parse_json(e.canonical(body)))


def test_private_read_refuses_symlink_and_widened_mode(environment):
    controller, _ = environment; controller.write('safe.json', {'safe': True})
    (controller.root / 'safe.json').chmod(0o644)
    with pytest.raises(o.Refusal): controller.read('safe.json')
    (controller.root / 'linked.json').symlink_to(controller.root / 'safe.json')
    with pytest.raises(o.Refusal): controller.read('linked.json')


def test_cli_create_omits_private_account_metadata(monkeypatch, capsys):
    class Fake:
        def create_project(self, candidate): return {'candidate_id': candidate, 'project_id': 123, 'owner': True,
            'lean_version_id': 18178, 'organization_id': 'PRIVATE_ACCOUNT'}
        def __getattr__(self, name): return lambda *args: {}
    monkeypatch.setattr(d, 'preflight', lambda: {'head': 'c' * 40, 'status': ''})
    monkeypatch.setattr(d, 'controller_for', lambda operation: Fake())
    d.main(['create', '--operation', 'synthetic-op', '--candidate', OFF])
    assert 'PRIVATE_ACCOUNT' not in capsys.readouterr().out


def test_cli_missing_operation_is_not_implicitly_reused():
    with pytest.raises(SystemExit): d.main(['status', '--candidate', OFF, '--attempt', '1'])


def test_cli_refusal_is_closed_error_without_private_body_or_traceback(monkeypatch, capsys):
    monkeypatch.setattr(d, 'preflight', lambda: {'head': 'c' * 40, 'status': ''})
    def refused(*args): raise o.Refusal('PRIVATE LICENSED ROW OR CREDENTIAL ECHO')
    monkeypatch.setattr(d, 'controller_for', refused)
    assert d.main(['authenticate', '--operation', 'synthetic-op']) == 1
    result = capsys.readouterr()
    assert result.err == '' and result.out == '{"automatic_retry":false,"status":"refused_or_uncertain"}\n'


@pytest.mark.parametrize('field,value', [('job_id', 'foreign-job'), ('config_sha256', '0' * 64),
    ('strategy_accepted', True), ('input_hashes', {}), ('fees', {'numerator': '1', 'denominator': '0'}),
    ('fill_events', True)])
def test_compact_summary_bad_identity_cost_or_boolean_authority_refuses(environment, field, value):
    controller, cloud, attempt = ready(environment, launch=True, terminal=True)
    prefix, manifest_body = controller.attempt(OFF, attempt)
    raw = cloud('backtests/read/log', e.canonical({'projectId': o._int(manifest_body['project_id']),
        'backtestId': 'job-synthetic', 'query': 'EXT26_SUMMARY'}), 'application/json')
    body = e.parse_json(e.parse_json(raw)['logs'][0].split('EXT26_SUMMARY ', 1)[1].encode())
    body[field] = value
    with pytest.raises(o.Refusal): o.compact_aggregate('2026-10-09 16:00:00 EXT26_SUMMARY ' + e.canonical(body).decode(),
        'EXT26_SUMMARY', manifest_body, attempt, 'job-synthetic')


def test_compact_exact_rational_is_not_converted_to_float(environment):
    controller, cloud, attempt = ready(environment, launch=True, terminal=True)
    _, manifest_body = controller.attempt(OFF, attempt)
    raw = cloud('backtests/read/log', e.canonical({'projectId': o._int(manifest_body['project_id']),
        'backtestId': 'job-synthetic', 'query': 'EXT26_SUMMARY'}), 'application/json')
    body = e.parse_json(e.parse_json(raw)['logs'][0].split('EXT26_SUMMARY ', 1)[1].encode())
    exact = {'numerator': '123456789012345678901234567890', 'denominator': '100000000000000000000000000001'}
    body['fees'] = exact
    result = o.compact_aggregate('EXT26_SUMMARY ' + e.canonical(body).decode(), 'EXT26_SUMMARY', manifest_body, attempt, 'job-synthetic')
    assert result['fees'] == exact


@pytest.mark.parametrize('change', ['missing_nav', 'imputed_cash', 'negative_count', 'sleeve_census', 'slot_null', 'foreign_sleeve'])
def test_aggregate_coverage_missing_observations_cannot_be_imputed(environment, change):
    controller, cloud, attempt = ready(environment, launch=True, terminal=True)
    _, manifest_body = controller.attempt(OFF, attempt)
    raw = cloud('backtests/read/log', e.canonical({'projectId': o._int(manifest_body['project_id']),
        'backtestId': 'job-synthetic', 'query': 'EXT26_SUMMARY'}), 'application/json')
    body = e.parse_json(e.parse_json(raw)['logs'][0].split('EXT26_SUMMARY ', 1)[1].encode())
    if change == 'missing_nav': body['cash_exposure_aggregate']['missing_nav_observations'] = e.JsonNumber('1')
    elif change == 'imputed_cash':
        cash = body['cash_exposure_aggregate']; cash['nav_observations'] = e.JsonNumber('0'); cash['missing_nav_observations'] = e.JsonNumber('1449')
        for key in ('cash_usd', 'cash_fraction', 'gross_exposure'): cash[key]['observations'] = e.JsonNumber('0')
    elif change == 'negative_count': body['clock_assertions'] = e.JsonNumber('-1')
    elif change == 'sleeve_census': body['per_sleeve_coverage']['SPY']['membership_unobserved_decisions'] = e.JsonNumber('300')
    elif change == 'slot_null': body['per_sleeve_coverage']['SPY']['selected_slots']['min'] = e.JsonNumber('0')
    else: body['per_sleeve_coverage']['FOREIGN'] = body['per_sleeve_coverage'].pop('SPY')
    with pytest.raises(o.Refusal): o.compact_aggregate('EXT26_SUMMARY ' + e.canonical(body).decode(),
        'EXT26_SUMMARY', manifest_body, attempt, 'job-synthetic')


def test_input_hash_bound_is_distinct_from_evidence_response_bound():
    raw = b'synthetic-large-input-' + b'x' * (e.MAX_BYTES + 1)
    assert o._input_digest(raw) == o.hashlib.sha256(raw).hexdigest()
    assert o._request_digest(raw, 'object/set') == o._input_digest(raw)
    with pytest.raises(o.Refusal): o._request_digest(raw, 'files/update')
    with pytest.raises(o.Refusal): o._input_digest(b'x' * (o.MAX_INPUT_BYTES + 1))


def test_complete_chain_comparison_is_hash_receipt_equality_only(environment):
    controller, cloud, attempt = ready(environment, launch=True, terminal=True)
    _, manifest_body = controller.attempt(OFF, attempt)
    raw = cloud('backtests/read/log', e.canonical({'projectId': o._int(manifest_body['project_id']),
        'backtestId': 'job-synthetic', 'query': 'EXT26_SUMMARY'}), 'application/json')
    body = e.parse_json(e.parse_json(raw)['logs'][0].split('EXT26_SUMMARY ', 1)[1].encode())
    on, off = body['matched_input_chains'], deepcopy(body['matched_input_chains'])
    result = o.compare_matched_chain_receipts(on, off)
    assert result['matched_chain_receipts_equal'] is True and result['independent_input_row_replay'] is False
    off['SPY']['caps']['sha256'] = '0' * 64
    result = o.compare_matched_chain_receipts(on, off)
    assert result['matched_chain_receipts_equal'] is False and result['mismatches'] == [{'sleeve': 'SPY', 'domain': 'caps'}]
    off['SPY']['caps']['unavailable_decisions'] = e.JsonNumber('300')
    with pytest.raises(o.Refusal): o.compare_matched_chain_receipts(on, off)


def test_rounded_dimensionless_mean_at_exact_boundary_has_explicit_half_ulp_tolerance(environment):
    controller, cloud, attempt = ready(environment, launch=True, terminal=True)
    _, manifest_body = controller.attempt(OFF, attempt)
    raw = cloud('backtests/read/log', e.canonical({'projectId': o._int(manifest_body['project_id']),
        'backtestId': 'job-synthetic', 'query': 'EXT26_SUMMARY'}), 'application/json')
    body = e.parse_json(e.parse_json(raw)['logs'][0].split('EXT26_SUMMARY ', 1)[1].encode())
    stats = body['cash_exposure_aggregate']['cash_fraction']
    stats['min'] = stats['max'] = {'numerator': '1', 'denominator': '3'}
    stats['mean'] = '0.' + '3' * 50
    o.compact_aggregate('EXT26_SUMMARY ' + e.canonical(body).decode(), 'EXT26_SUMMARY', manifest_body, attempt, 'job-synthetic')
    stats['mean'] = '0.1'
    with pytest.raises(o.Refusal): o.compact_aggregate('EXT26_SUMMARY ' + e.canonical(body).decode(),
        'EXT26_SUMMARY', manifest_body, attempt, 'job-synthetic')


@pytest.mark.parametrize('endpoint,location', [
    ('backtests/orders/read', 'top'), ('backtests/orders/read', 'order'),
    ('backtests/read', 'top'), ('backtests/read', 'backtest'),
    ('backtests/read/log', 'top'), ('backtests/chart/read', 'top'), ('backtests/chart/read', 'chart')])
@pytest.mark.parametrize('field,value', [('projectId', 999), ('backtestId', 'foreign-job'),
    ('projectId', True), ('backtestId', None)])
def test_foreign_returned_native_identifier_refuses_before_evidence_acceptance(environment, endpoint, location, field, value):
    controller, cloud, attempt = ready(environment, launch=True, terminal=True)
    original = controller.transport
    def transport(route, raw, content_type):
        body = e.parse_json(original(route, raw, content_type))
        if route == endpoint:
            target = body if location == 'top' else body['orders'][0] if location == 'order' else body[location]
            target[field] = value
        return e.canonical(body)
    controller.transport = transport
    with pytest.raises(o.Refusal):
        (controller.collect_orders if endpoint == 'backtests/orders/read' else controller.collect_native)(OFF, attempt)
    retained = [controller.value(path.name) for path in controller.root.glob('request.*.projection.json')]
    expected = e.parse_json(e.canonical({'value': value}))['value']
    def matching(item):
        body = item['projection']
        target = body if location == 'top' else body.get('orders', [{}])[0] if location == 'order' else body.get(location)
        return type(target) is dict and field in target and target[field] == expected
    assert any(matching(item) for item in retained)
    assert not (controller.root / (OFF + '.attempt.1.native.' + controller.operation + '.completed.json')).exists()
    assert cloud.calls.count('backtests/create') == 1


def test_absent_returned_identity_uses_explicit_envelope_not_fabricated_provider_fields(environment):
    controller, _, attempt = ready(environment, launch=True, terminal=True)
    orders = controller.collect_orders(OFF, attempt)
    checks = orders['pages'][0]['returned_identity_checks']
    assert checks['observed_project_id_fields'] == checks['observed_backtest_id_fields'] == 0
    assert checks['absent_identifiers_inferred'] is checks['provider_authenticity_independently_verified'] is False
    path = next(controller.root.glob('*.orders.00000.envelope.json'))
    envelope = controller.value(path.name)
    assert envelope['request']['backtestId'] == 'job-synthetic' and 'backtestId' not in envelope['response']
    assert e.digest(controller.read(path.name)) == orders['pages'][0]['request_response_envelope_sha256']


def test_fixed_native_chart_requests_claim_before_read_and_never_change_looks(environment):
    controller, cloud, attempt = ready(environment, launch=True, terminal=True)
    seen, original = [], controller.transport
    def transport(endpoint, raw, content_type):
        if endpoint == 'backtests/chart/read':
            payload = e.parse_json(raw)
            claim = next(controller.root.glob('*.chart.' + o.CHARTS[payload['name']] + '.spent.json'))
            assert controller.value(claim.name)['payload_sha256'] == e.digest(raw)
            seen.append(payload)
        return original(endpoint, raw, content_type)
    controller.transport = transport
    result = controller.collect_native(OFF, attempt)
    assert [row['name'] for row in seen] == list(o.CHARTS)
    for row in seen:
        assert o._int(row['count']) == 2000
        assert datetime.fromtimestamp(o._int(row['start']), timezone.utc).isoformat() == '2021-01-04T00:00:00+00:00'
        assert datetime.fromtimestamp(o._int(row['end']), timezone.utc).isoformat() == '2026-10-10T00:00:00+00:00'
        assert row['backtestId'] == 'job-synthetic'
    native = result['chart_inventories']['EXT26 Account NAV']
    assert native['daily_account_observations']['complete_daily_account_nav'] is True
    assert result['chart_inventories']['Strategy Equity']['complete_daily_account_nav'] is False
    assert result['has_account_chart'] is True and result['strategy_accepted'] is False
    assert result['new_looks'] == 0 and cloud.calls.count('backtests/create') == 1
    before = cloud.calls.count('backtests/chart/read')
    with pytest.raises(o.Refusal): controller.collect_native(OFF, attempt)
    assert cloud.calls.count('backtests/chart/read') == before


@pytest.mark.parametrize('change', ['count', 'start', 'end', 'name', 'no_claim'])
def test_chart_read_cannot_bypass_frozen_scope_or_claim(environment, change):
    controller, cloud, _ = ready(environment, launch=True, terminal=True)
    payload = {'projectId': 101, 'backtestId': 'job-synthetic', 'name': 'EXT26 Account NAV',
        'count': o.CHART_COUNT, 'start': o.CHART_START, 'end': o.CHART_END}
    if change in {'count', 'start', 'end'}: payload[change] += 1
    if change == 'name': payload['name'] = 'Unrelated Licensed Chart'
    before = len(cloud.calls)
    with pytest.raises(o.Refusal): controller.request('backtests/chart/read', payload, candidate=OFF)
    assert len(cloud.calls) == before


@pytest.mark.parametrize('shape', ['array', 'legacy'])
def test_exact_native_nav_series_preserves_numeric_tokens_and_proves_dst_close_sessions(shape):
    body = e.parse_json(e.canonical(chart_response(shape=shape, nav='100000.1234567890123456789012345678')))
    sessions = tuple(e.parse_json(calendar_raw())['valuation_sessions'])
    result, raw = o._account_nav_chart(body, sessions)
    assert result['complete_daily_account_nav'] is True and result['observations'] == 1449
    assert result['private_journal_replay_verified'] is False
    normalized = e.parse_json(raw)
    assert normalized[0]['session'] == '2021-01-04' and normalized[-1]['session'] == '2026-10-09'
    assert all(row['nav'].lexeme == '100000.1234567890123456789012345678' for row in normalized)
    assert e.digest(raw) == result['normalized_series_sha256']


@pytest.mark.parametrize('fault', ['loading', 'missing_chart', 'wrong_chart', 'missing_values', 'zero_observations',
    'downsample', 'duplicate_session', 'wrong_minute', 'outside_window', 'fractional_time', 'boolean_time',
    'missing_y', 'boolean_y', 'null_y', 'string_y', 'zero_y', 'negative_y', 'candle_series', 'unknown_unit', 'unknown_name'])
def test_missing_downsampled_or_wrong_clock_native_chart_stays_diagnostic(fault):
    body = e.parse_json(e.canonical(chart_response()))
    series = body['chart']['series']['NAV']; values = series['values']
    if fault == 'loading': body = {'success': True, 'status': 'loading', 'progress': e.JsonNumber('0')}
    elif fault == 'missing_chart': body = {'success': True}
    elif fault == 'wrong_chart': body['chart']['name'] = 'Strategy Equity'
    elif fault == 'missing_values': del series['values']
    elif fault == 'zero_observations': series['values'] = []
    elif fault == 'downsample': values.pop()
    elif fault == 'duplicate_session': values[1] = values[0]
    elif fault == 'wrong_minute': values[0][0] = e.JsonNumber(str(o._int(values[0][0]) - 60))
    elif fault == 'outside_window': values[-1][0] = e.JsonNumber(str(o.CHART_END))
    elif fault == 'fractional_time': values[0][0] = e.JsonNumber(values[0][0].lexeme + '.5')
    elif fault == 'boolean_time': values[0][0] = True
    elif fault == 'missing_y': values[0] = {'x': values[0][0]}
    elif fault == 'boolean_y': values[0][1] = True
    elif fault == 'null_y': values[0][1] = None
    elif fault == 'string_y': values[0][1] = '100000'
    elif fault == 'zero_y': values[0][1] = e.JsonNumber('0')
    elif fault == 'negative_y': values[0][1] = e.JsonNumber('-1')
    elif fault == 'candle_series': series['seriesType'] = e.JsonNumber('2')
    elif fault == 'unknown_unit': del series['unit']
    else: del series['name']
    sessions = tuple(e.parse_json(calendar_raw())['valuation_sessions'])
    result, raw = o._account_nav_chart(body, sessions)
    assert result['complete_daily_account_nav'] is False and raw is None
    assert result['classification'].startswith('diagnostic_')
    assert result['private_journal_replay_verified'] is False


def test_loading_chart_is_retained_once_without_extra_launch_or_implicit_read(environment):
    controller, cloud, attempt = ready(environment, launch=True, terminal=True)
    original = controller.transport
    def transport(endpoint, raw, content_type):
        return e.canonical({'success': True, 'status': 'loading', 'progress': 0}) if endpoint == 'backtests/chart/read' else original(endpoint, raw, content_type)
    controller.transport = transport
    result = controller.collect_native(OFF, attempt)
    observation = result['chart_inventories']['EXT26 Account NAV']['daily_account_observations']
    assert observation['classification'] == 'diagnostic_loading_chart' and observation['observations'] is None
    assert result['has_account_chart'] is False and result['classification'] == 'diagnostic_missing_evidence'
    assert cloud.calls.count('backtests/chart/read') == 0  # Replacement fixture returned, without network or retry.
    envelopes = list(controller.root.glob('*.chart.*.envelope.json'))
    assert len(envelopes) == 2
    assert all(controller.value(path.name)['response']['status'] == 'loading' for path in envelopes)
    assert not list(controller.root.glob('*.normalized-nav.json'))


@pytest.mark.parametrize('fault', ['missing_loader', 'hash', 'nonliteral', 'duplicate', 'changed_calendar'])
def test_rendered_calendar_cannot_be_substituted_before_native_read(environment, fault):
    controller, _, _ = ready(environment, launch=True, terminal=True)
    row = deepcopy(controller.candidate(OFF))
    if fault == 'missing_loader': del row['files']['extended_loader.py']
    elif fault == 'hash': row['input_hashes']['calendar.json'] = '0' * 64
    elif fault == 'nonliteral': row['files']['extended_loader.py'] = 'CALENDAR_JSON = str("not admitted")\n'
    elif fault == 'duplicate': row['files']['extended_loader.py'] += 'CALENDAR_JSON = "duplicate"\n'
    else: row['files']['extended_loader.py'] = 'CALENDAR_JSON = "changed"\n'
    with pytest.raises(o.Refusal): o._bundle_calendar(row)
