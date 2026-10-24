"""Synthetic prospective-controller proofs; no credentials or cloud access."""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.target_price_revisions_qc import operations_v2 as op

OFF = 'TPR-MATCHED-OFF-BASE-v1'
ON = 'TPR-MATCHED-ON-BASE-v1'


def manifest():
    now = datetime.now(timezone.utc)
    candidates, bundles = [], {}
    for candidate in sorted(op.CANDIDATES):
        arm = 'tpr_on' if '-ON-' in candidate else 'tpr_off' if '-OFF-' in candidate else 'etf_basket'
        config = {'schema': 'tpr-qc-matched-config-v1', 'study_id': op.STUDY,
            'freeze_sha256': op.FREEZE_HASH, 'candidate_id': candidate, 'arm': arm,
            'cost': 'adverse' if '-ADVERSE-' in candidate else 'baseline',
            'slippage': '0.0015' if '-ADVERSE-' in candidate else '0.001'}
        text = op.canonical(config).decode()
        files = {'main.py': '# synthetic ' + candidate + '\n',
            'proxy_core.py': '# synthetic immutable core\n', 'signal_packet.py': 'CONFIG_JSON = "{}"\n',
            'matched_config.py': 'CONFIG_JSON = ' + repr(text) + '\n'}
        bundles[candidate] = files
        candidates.append({'candidate_id': candidate, 'project_name': candidate + '-private',
            'config_sha256': op.digest(text.encode()),
            'source_hashes': {name: op.digest(raw.encode()) for name, raw in files.items()}})
    result = {'schema': 'tpr-qc-operations-manifest-v2', 'study_id': op.STUDY,
        'operation_id': 'TPR-MATCHED-ACCESS-FIXTURE-001', 'created_utc': (now - timedelta(seconds=1)).isoformat(),
        'expires_utc': (now + timedelta(hours=1)).isoformat(), 'baseline_git_head': op.BASELINE,
        'freeze_sha256': op.FREEZE_HASH, 'repository_source_hashes': {
            op.MODULE_PATH: op.digest(Path(op.__file__).read_bytes()), op.FREEZE_PATH: op.FREEZE_HASH},
        'input_hashes': {'signal-packet.json': op.PACKET_HASH}, 'packet_path': op.PACKET_PATH,
        'packet_sha256': op.PACKET_HASH, 'candidates': candidates, 'max_requests': 1000,
        'max_response_bytes': 16 * 1024 * 1024, 'request_timeout_seconds': 30,
        'max_attempts_per_candidate': 3, 'log_prefix': 'MATCHED_'}
    return result, bundles


class Cloud:
    def __init__(self):
        self.calls, self.projects = [], {}
        self.compile_state = 'BuildSuccess'
        self.order_count = 104
        self.order_duplicate = self.empty_order_page = False
        self.error = None
        self.fail_endpoint = None
        self.wrong_compile = self.wrong_backtest = False
        self.loading_endpoint = None

    def __call__(self, endpoint, raw, content_type):
        self.calls.append(endpoint)
        if endpoint == self.fail_endpoint:
            raise OSError('synthetic transport failure')
        if endpoint in ('authenticate', 'object/set'):
            return {'success': True}
        body = json.loads(raw)
        if endpoint == 'projects/create':
            project_id = 1000 + len(self.projects)
            self.projects[project_id] = {'main.py': '# untouched initial main\n', 'research.ipynb': '{}'}
            return {'success': True, 'projects': [{'projectId': project_id, 'name': body['name'],
                'owner': True, 'collaborators': [], 'isPublic': False, 'maxFileSize': 64000,
                'leanVersionId': 18171, 'organizationId': 'synthetic-org'}]}
        files = self.projects[body['projectId']]
        if endpoint == 'files/read':
            return {'success': True, 'files': [{'name': name, 'content': text} for name, text in files.items()]}
        if endpoint in ('files/create', 'files/update'):
            files[body['name']] = body['content']
            return {'success': True}
        if endpoint == 'compile/create':
            return {'success': True, 'compileId': 'compile-synthetic', 'state': 'InQueue'}
        if endpoint == 'compile/read':
            return {'success': True, 'compileId': 'foreign-compile' if self.wrong_compile else body['compileId'],
                'state': self.compile_state, 'logs': []}
        if endpoint == 'backtests/create':
            return {'success': True, 'backtest': {'backtestId': 'backtest-synthetic'}}
        if endpoint == 'backtests/read':
            return {'success': True, 'backtest': {'backtestId': 'foreign-backtest' if self.wrong_backtest else body['backtestId'],
                'completed': True, 'status': 'Completed', 'error': self.error,
                'statistics': {'Total Orders': str(self.order_count)},
                'charts': {'Strategy Equity': {'own_aggregate': True}, 'Benchmark': {'not_exported': True}}}}
        if endpoint == 'backtests/orders/read':
            if endpoint == self.loading_endpoint:
                return {'success': True, 'status': 'loading', 'message': 'Synthetic own orders are loading'}
            values = [{'id': index if not self.order_duplicate else 0, 'status': 3, 'quantity': 1,
                'type': 4, 'orderEvents': [{'status': 'filled', 'fillQuantity': 1}]} for index in
                range(body['start'], min(self.order_count, body['end']))]
            return {'success': True, 'length': self.order_count, 'orders': [] if self.empty_order_page else values}
        if endpoint == 'backtests/read/log':
            if endpoint == self.loading_endpoint:
                return {'success': True, 'status': 'loading', 'message': 'Synthetic own logs are loading'}
            values = ['2025-01-02 MATCHED_NAV {"nav":"100000"}', '2025-03-31 MATCHED_SUMMARY {}']
            return {'success': True, 'length': len(values), 'logs': values[body['start']:body['end']]}
        raise AssertionError('unexpected synthetic endpoint')


@pytest.fixture
def environment(tmp_path):
    body, bundles = manifest()
    cloud = Cloud()
    controller = op.Operations(body, manifest_sha256=op.digest(op.canonical(body)),
        _fixture_root=tmp_path / 'private', _fixture_transport=cloud)
    controller.prepare_access()
    return controller, cloud, bundles


def ready(environment, candidate=OFF, *, launch=False):
    controller, cloud, bundles = environment
    controller.create_project(candidate)
    controller.upload_sources(candidate, bundles[candidate])
    attempt = controller.reserve_attempt(candidate)['attempt']
    controller.compile_candidate(candidate, attempt)
    controller.poll_compile(candidate, attempt)
    if launch:
        controller.launch_backtest(candidate, attempt)
        controller.poll_backtest(candidate, attempt)
    return controller, cloud, bundles, attempt


def rewrite(controller, name, update):
    """Synthetic corruption only; production controller never overwrites receipts."""
    body = controller._value(name)
    update(body)
    (controller.root / name).write_bytes(op.canonical(body))


@pytest.mark.parametrize('field,value', [
    ('study_id', 'foreign-study'), ('freeze_sha256', '0' * 64), ('baseline_git_head', '0' * 40),
    ('packet_path', 'artifacts/foreign.json'), ('packet_sha256', '0' * 64), ('max_requests', 1001),
    ('max_requests', True), ('request_timeout_seconds', 31), ('max_response_bytes', 16 * 1024 * 1024 + 1),
    ('max_attempts_per_candidate', 4), ('log_prefix', 'TPR_'), ('created_utc', '2026-01-01'),
])
def test_manifest_refuses_expanded_scope(field, value):
    body, _ = manifest()
    body[field] = value
    with pytest.raises(op.Refusal):
        op.validate_manifest(body, op.digest(op.canonical(body)))


def test_manifest_refuses_unknown_missing_and_duplicate_candidates():
    body, _ = manifest()
    for changed in ({**body, 'unknown': False}, {**body, 'candidates': body['candidates'][:-1]},
                    {**body, 'candidates': [body['candidates'][0]] * 6}):
        with pytest.raises(op.Refusal):
            op.validate_manifest(changed, op.digest(op.canonical(changed)))
    with pytest.raises(op.Refusal):
        op.validate_manifest(body, '0' * 64)


@pytest.mark.parametrize('path', ['../../CLAUDE.md', 'config.py',
    'research/analyst_revisions_v2/raw_candidate.py', 'research/target_price_revisions_development/raw_run.py'])
def test_only_exact_scoring_dependencies_can_expand_repository_inventory(path):
    body, _ = manifest()
    body['repository_source_hashes'][path] = '0' * 64
    with pytest.raises(op.Refusal, match='allowlist'):
        op.validate_manifest(body, op.digest(op.canonical(body)))


def test_two_exact_frozen_scorer_paths_are_allowed():
    body, _ = manifest()
    for name in ('raw_candidate.py', 'raw_revision.py'):
        body['repository_source_hashes']['research/target_price_revisions_development/' + name] = '0' * 64
    assert op.validate_manifest(body, op.digest(op.canonical(body)))[0] == body


def test_two_successive_requests_do_not_treat_terminal_receipts_as_reservations(environment):
    controller, cloud, _ = environment
    controller.authenticate()
    controller.authenticate()
    assert cloud.calls == ['authenticate', 'authenticate']
    assert controller._value('request.0002.terminal.json')['status'] == 'succeeded'


def test_fixture_operations_never_resolve_credentials_or_create_connection(environment, monkeypatch):
    controller, _, _ = environment
    monkeypatch.setattr(op.os.environ, 'get', lambda *args, **kwargs: pytest.fail('credential read'))
    monkeypatch.setattr(op.http.client, 'HTTPSConnection', lambda *args, **kwargs: pytest.fail('real network'))
    controller.authenticate()
    controller.create_project(OFF)


def test_request_budget_expires_before_transport(environment):
    controller, cloud, _ = environment
    controller.manifest['max_requests'] = 1
    # An altered in-memory manifest cannot silently reuse its access receipt.
    with pytest.raises(op.Refusal, match='binding'):
        controller.authenticate()
    assert not cloud.calls


def test_real_request_budget_is_consumed_across_terminal_slots(tmp_path):
    body, _ = manifest()
    body['max_requests'] = 1
    cloud = Cloud()
    controller = op.Operations(body, manifest_sha256=op.digest(op.canonical(body)),
        _fixture_root=tmp_path / 'private', _fixture_transport=cloud)
    controller.prepare_access()
    controller.authenticate()
    with pytest.raises(op.Refusal, match='budget exhausted'):
        controller.authenticate()
    assert cloud.calls == ['authenticate']


def test_expired_access_refuses_before_transport(environment, monkeypatch):
    controller, cloud, _ = environment
    class Expired(datetime):
        @staticmethod
        def now(_tz):
            return datetime.fromisoformat(controller.manifest['expires_utc']) + timedelta(seconds=1)
    monkeypatch.setattr(op, 'datetime', Expired)
    with pytest.raises(op.Refusal, match='scope not active'):
        controller.authenticate()
    assert not cloud.calls


def production_transport_fixture(environment, monkeypatch, raw, *, status=200):
    controller, _, _ = environment
    controller.fixture = False
    monkeypatch.setattr(controller, '_access', lambda: {'fixture': True, 'git_head': op.BASELINE})
    monkeypatch.setattr(controller, '_root', lambda: controller.root)
    monkeypatch.setattr(op.os.environ, 'get', lambda key, default=None:
        {'QC_USER_ID': 'SYNTHETIC_UID', 'QC_API_TOKEN': 'SYNTHETIC_TOKEN'}.get(key, default))
    events = []
    @contextmanager
    def deadline(seconds):
        events.append(('deadline', seconds))
        try:
            yield
        finally:
            events.append(('deadline-restored', seconds))
    monkeypatch.setattr(op, '_wall_deadline', deadline)
    class Connection:
        def __init__(self, host, **kwargs):
            events.append(('connect', host, kwargs['timeout']))
        def request(self, method, path, **kwargs):
            events.append(('request', method, path))
        def getresponse(self):
            return SimpleNamespace(status=status, read=lambda maximum: raw[:maximum])
        def close(self):
            events.append(('closed',))
    monkeypatch.setattr(op.http.client, 'HTTPSConnection', Connection)
    return controller, events


def test_production_transport_redacts_userid_and_uses_wall_deadline(environment, monkeypatch):
    raw = op.canonical({'success': False, 'errors': ['failure for SYNTHETIC_UID']})
    controller, events = production_transport_fixture(environment, monkeypatch, raw, status=400)
    with pytest.raises(op.Refusal):
        controller.authenticate()
    receipt = controller._value('request.0001.terminal.json')
    assert receipt['status'] == 'api_refused'
    assert receipt['errors'] == ['failure for [redacted]']
    assert events[0] == ('deadline', 30)
    assert ('deadline-restored', 30) in events and events[-1] == ('closed',)


def test_production_token_echo_is_not_retained(environment, monkeypatch):
    raw = op.canonical({'success': True, 'foreign': 'SYNTHETIC_TOKEN'})
    controller, _ = production_transport_fixture(environment, monkeypatch, raw)
    with pytest.raises(op.Refusal):
        controller.authenticate()
    assert 'SYNTHETIC_TOKEN' not in controller.read_private('request.0001.terminal.json').decode()
    assert controller._value('request.0001.terminal.json')['status'] == 'failed_or_unknown'


def test_production_response_byte_bound_refuses_before_json_decode(environment, monkeypatch):
    controller, _ = production_transport_fixture(environment, monkeypatch, b'X' * 21)
    controller.manifest['max_response_bytes'] = 20
    with pytest.raises(op.Refusal):
        controller.authenticate()
    assert controller._value('request.0001.terminal.json')['status'] == 'failed_or_unknown'


def test_request_failure_keeps_slot_and_successor_does_not_reuse_it(environment):
    controller, cloud, _ = environment
    cloud.fail_endpoint = 'authenticate'
    with pytest.raises(op.Refusal, match='unknown'):
        controller.authenticate()
    assert controller._value('request.0001.terminal.json')['status'] == 'failed_or_unknown'
    cloud.fail_endpoint = None
    controller.authenticate()
    assert controller._value('request.0002.terminal.json')['status'] == 'succeeded'


@pytest.mark.parametrize('endpoint', ['projects/create', 'files/create', 'files/update',
    'compile/create', 'backtests/create', 'object/set'])
def test_direct_effectful_request_without_typed_stage_is_refused(environment, endpoint):
    controller, cloud, _ = environment
    controller.create_project(OFF)
    project = controller._project(OFF)
    before = len(cloud.calls)
    with pytest.raises(op.Refusal):
        controller._request(endpoint, {'projectId': project['project_id']}, project=project)
    assert len(cloud.calls) == before


def test_unregistered_project_and_out_of_scope_endpoint_refuse_without_transport(environment):
    controller, cloud, _ = environment
    with pytest.raises(op.Refusal):
        controller._request('backtests/read', {'projectId': 999})
    with pytest.raises(op.Refusal):
        controller._request('live/create', {})
    assert not cloud.calls


def test_forged_project_argument_cannot_access_an_unrelated_project(environment):
    controller, cloud, _ = environment
    controller.create_project(OFF)
    forged = {**controller._project(OFF), 'project_id': 987654}
    before = len(cloud.calls)
    with pytest.raises(op.Refusal, match='own fresh project'):
        controller._request('backtests/read', {'projectId': 987654}, project=forged)
    assert len(cloud.calls) == before


def test_project_failure_cannot_be_recreated(environment):
    controller, cloud, _ = environment
    cloud.fail_endpoint = 'projects/create'
    with pytest.raises(op.Refusal):
        controller.create_project(OFF)
    assert controller._value(OFF + '.project-create.terminal.json')['status'] == 'failed_or_unknown'
    cloud.fail_endpoint = None
    with pytest.raises(op.Refusal, match='already exists'):
        controller.create_project(OFF)
    assert cloud.calls == ['projects/create']


@pytest.mark.parametrize('change', [lambda row: row.update(owner=False),
    lambda row: row.update(isPublic=True), lambda row: row.update(collaborators=[{'owner': False}]),
    lambda row: row.update(maxFileSize=59999), lambda row: row.update(projectId=True)])
def test_project_privacy_and_quota_are_actual_response_gates(environment, change):
    controller, cloud, _ = environment
    original = controller.transport
    def changed(endpoint, raw, content_type):
        result = original(endpoint, raw, content_type)
        if endpoint == 'projects/create':
            change(result['projects'][0])
        return result
    controller.transport = changed
    with pytest.raises(op.Refusal):
        controller.create_project(OFF)
    assert not (controller.root / (OFF + '.project.json')).exists()


def test_upload_rejects_changed_source_before_any_file_transport(environment):
    controller, cloud, bundles = environment
    controller.create_project(OFF)
    files = {**bundles[OFF], 'main.py': '# foreign strategy\n'}
    with pytest.raises(op.Refusal, match='frozen bundle'):
        controller.upload_sources(OFF, files)
    assert cloud.calls == ['projects/create']


def test_config_literal_hash_is_independent_of_wire_module_hash(environment):
    controller, cloud, bundles = environment
    changed = deepcopy(bundles[OFF])
    changed['matched_config.py'] += 'import os\n'
    body = deepcopy(controller.manifest)
    spec = next(row for row in body['candidates'] if row['candidate_id'] == OFF)
    spec['source_hashes']['matched_config.py'] = op.digest(changed['matched_config.py'].encode())
    controller = op.Operations(body, manifest_sha256=op.digest(op.canonical(body)),
        _fixture_root=controller.root.parent / 'second-private', _fixture_transport=cloud)
    controller.prepare_access()
    controller.create_project(OFF)
    with pytest.raises(op.Refusal, match='literal/hash'):
        controller.upload_sources(OFF, changed)
    assert cloud.calls == ['projects/create']


def test_caller_manifest_mutation_does_not_change_internal_source_contract(tmp_path):
    body, _ = manifest()
    controller = op.Operations(body, manifest_sha256=op.digest(op.canonical(body)),
        _fixture_root=tmp_path / 'private', _fixture_transport=Cloud())
    expected = deepcopy(controller.candidates)
    body['candidates'][0]['source_hashes']['main.py'] = '0' * 64
    body['max_requests'] = 9999
    assert controller.candidates == expected
    assert controller.manifest['max_requests'] == 1000


def test_cloud_readback_change_refuses_compile_before_consuming_launch(environment):
    controller, cloud, bundles = environment
    controller.create_project(OFF)
    controller.upload_sources(OFF, bundles[OFF])
    attempt = controller.reserve_attempt(OFF)['attempt']
    cloud.projects[controller._project(OFF)['project_id']]['main.py'] += '# concurrent change\n'
    with pytest.raises(op.Refusal, match='differs'):
        controller.compile_candidate(OFF, attempt)
    assert 'compile/create' not in cloud.calls
    assert not (controller.root / f'{OFF}.attempt.{attempt}.compile.spent.json').exists()


@pytest.mark.parametrize('file_change', ['main.py', 'research.ipynb'])
def test_launch_checks_sources_and_preserves_unrelated_notebook(environment, file_change):
    controller, cloud, _, attempt = ready(environment)
    cloud.projects[controller._project(OFF)['project_id']][file_change] += '\n'
    with pytest.raises(op.Refusal):
        controller.launch_backtest(OFF, attempt)
    assert 'backtests/create' not in cloud.calls


def test_launched_compile_is_insufficient_without_verified_buildsuccess(environment):
    controller, cloud, bundles = environment
    controller.create_project(OFF)
    controller.upload_sources(OFF, bundles[OFF])
    attempt = controller.reserve_attempt(OFF)['attempt']
    controller.compile_candidate(OFF, attempt)
    with pytest.raises(op.Refusal):
        controller.launch_backtest(OFF, attempt)
    assert 'backtests/create' not in cloud.calls


@pytest.mark.parametrize('state', ['InQueue', 'BuildError', 'Failed'])
def test_compile_terminal_or_queue_without_success_never_launches(environment, state):
    controller, cloud, bundles = environment
    controller.create_project(OFF)
    controller.upload_sources(OFF, bundles[OFF])
    attempt = controller.reserve_attempt(OFF)['attempt']
    controller.compile_candidate(OFF, attempt)
    cloud.compile_state = state
    assert controller.poll_compile(OFF, attempt)['state'] == state
    with pytest.raises(op.Refusal):
        controller.launch_backtest(OFF, attempt)
    assert 'backtests/create' not in cloud.calls


def test_foreign_compile_response_cannot_create_success_receipt(environment):
    controller, cloud, bundles = environment
    controller.create_project(OFF)
    controller.upload_sources(OFF, bundles[OFF])
    attempt = controller.reserve_attempt(OFF)['attempt']
    controller.compile_candidate(OFF, attempt)
    cloud.wrong_compile = True
    with pytest.raises(op.Refusal, match='identity'):
        controller.poll_compile(OFF, attempt)
    assert not (controller.root / f'{OFF}.attempt.{attempt}.compile.verified.json').exists()


@pytest.mark.parametrize('field,value', [('state', 'BuildError'), ('compile_id', 'foreign'),
    ('project_id', 99999), ('source_hashes', {}), ('manifest_sha256', '0' * 64),
    ('compile_response_sha256', '0' * 64), ('compile_response_file', '../foreign.json')])
def test_corrupt_verified_compile_receipt_cannot_launch(environment, field, value):
    controller, cloud, _, attempt = ready(environment)
    rewrite(controller, f'{OFF}.attempt.{attempt}.compile.verified.json', lambda row: row.update({field: value}))
    with pytest.raises(op.Refusal):
        controller.launch_backtest(OFF, attempt)
    assert 'backtests/create' not in cloud.calls


def test_compile_response_content_is_rehashed_before_launch(environment):
    controller, cloud, _, attempt = ready(environment)
    verified = controller._value(f'{OFF}.attempt.{attempt}.compile.verified.json')
    rewrite(controller, verified['compile_response_file'], lambda row: row.update(state='BuildError'))
    with pytest.raises(op.Refusal, match='BuildSuccess'):
        controller.launch_backtest(OFF, attempt)
    assert 'backtests/create' not in cloud.calls


def test_attempt_cap_survives_new_operation_identity(environment):
    controller, cloud, bundles = environment
    controller.create_project(OFF)
    controller.upload_sources(OFF, bundles[OFF])
    for expected in (1, 2, 3):
        assert controller.reserve_attempt(OFF)['attempt'] == expected
    before = len(cloud.calls)
    with pytest.raises(op.Refusal, match='three candidate attempts'):
        controller.reserve_attempt(OFF)
    body = deepcopy(controller.manifest)
    body['operation_id'] = 'TPR-MATCHED-ACCESS-FIXTURE-002'
    successor = op.Operations(body, manifest_sha256=op.digest(op.canonical(body)),
        _fixture_root=controller.root, _fixture_transport=cloud)
    successor.prepare_access()
    with pytest.raises(op.Refusal, match='three candidate attempts'):
        successor.reserve_attempt(OFF)
    assert len(cloud.calls) == before


def test_duplicate_compile_and_backtest_do_not_repeat_network(environment):
    controller, cloud, _, attempt = ready(environment, launch=True)
    before = len(cloud.calls)
    with pytest.raises(op.Refusal):
        controller.compile_candidate(OFF, attempt)
    with pytest.raises(op.Refusal):
        controller.launch_backtest(OFF, attempt)
    assert cloud.calls.count('compile/create') == cloud.calls.count('backtests/create') == 1
    assert len(cloud.calls) >= before  # Source readback is read-only; no duplicate effect.


def test_completed_backtest_poll_is_idempotent_and_excludes_benchmark_market_chart(environment):
    controller, cloud, _, attempt = ready(environment, launch=True)
    before = len(cloud.calls)
    assert controller.poll_backtest(OFF, attempt)['terminal'] is True
    assert len(cloud.calls) == before
    result = controller._value(f'{OFF}.attempt.{attempt}.backtest.result.json')
    assert set(result['charts']) == {'Strategy Equity'}


def test_foreign_backtest_result_is_never_saved_as_our_terminal(environment):
    controller, cloud, _, attempt = ready(environment)
    controller.launch_backtest(OFF, attempt)
    cloud.wrong_backtest = True
    with pytest.raises(op.Refusal, match='identity'):
        controller.poll_backtest(OFF, attempt)
    assert not (controller.root / f'{OFF}.attempt.{attempt}.backtest.result.json').exists()


def test_collect_all_order_pages_bind_exact_evidence_and_remain_pending_strategy_audit(environment):
    controller, cloud, bundles, attempt = ready(environment, launch=True)
    evidence = controller.collect_terminal(OFF, attempt)
    assert len(evidence['order_pages']) == 2
    assert [len(page['orders']) for page in evidence['order_pages']] == [99, 5]
    source = evidence['source_receipt']
    assert source['candidate_id'] == OFF and source['packet_sha256'] is None
    assert source['exact_cloud_readback'] is True and source['build_success'] is True
    assert source['source_hashes'] == {name: op.digest(text.encode()) for name, text in bundles[OFF].items()}
    assert source['evidence_hashes'] == {'result': op.digest(op.canonical(evidence['result_response'])),
        'logs': op.digest(op.canonical(evidence['logs_response'])),
        'order_pages': [op.digest(op.canonical(page)) for page in evidence['order_pages']]}
    assert evidence['completion']['strategy_accepted'] is False
    assert evidence['completion']['filled_order_count'] == 104
    assert (controller.root / (evidence['receipt_prefix'] + '.evidence-index.json')).exists()


@pytest.mark.parametrize('endpoint,stem', [('backtests/orders/read', 'orders'), ('backtests/read/log', 'logs')])
def test_loading_collection_retained_and_explicit_same_job_recollection_completes(environment, endpoint, stem):
    controller, cloud, _, attempt = ready(environment, launch=True)
    before = len(cloud.calls)
    cloud.loading_endpoint = endpoint
    first = controller.collect_terminal(OFF, attempt)
    assert first['completion']['classification'] == 'diagnostic_or_incomplete'
    first_prefix = f'{OFF}.attempt.{attempt}.collection.0001'
    wire = controller._value(first_prefix + '.' + stem + '.00000.wire.json')
    assert wire['status'] == 'loading'
    assert cloud.calls[before:].count(endpoint) == 1  # No implicit request retry.
    first_bytes = {path.name: controller.read_private(path.name)
                   for path in controller.root.glob(first_prefix + '.*')}
    cloud.loading_endpoint = None
    before_recollection = len(cloud.calls)
    second = controller.collect_terminal(OFF, attempt)
    assert first['collection_round'] == 1 and second['collection_round'] == 2
    assert first['receipt_prefix'] == first_prefix
    assert second['receipt_prefix'] == f'{OFF}.attempt.{attempt}.collection.0002'
    assert second['completion']['classification'] == 'completed_orders_require_strategy_accounting_audit'
    assert second['completion']['filled_order_count'] == 104
    assert [len(page['orders']) for page in second['order_pages']] == [99, 5]
    assert len({order['id'] for page in second['order_pages'] for order in page['orders']}) == 104
    assert second['logs_response']['length'] == 2
    assert all(controller.read_private(name) == raw for name, raw in first_bytes.items())
    assert set(cloud.calls[before_recollection:]) <= {'files/read', 'backtests/orders/read', 'backtests/read/log'}
    assert len(list(controller.root.glob(OFF + '.attempt.*.reserved.json'))) == 1
    assert cloud.calls.count('compile/create') == cloud.calls.count('backtests/create') == 1
    assert controller._value(second['receipt_prefix'] + '.spent.json')['new_development_looks'] == 0


def test_collection_round_reserved_before_every_read_and_no_mutation_transport(environment):
    controller, cloud, _, attempt = ready(environment, launch=True)
    def admitted_transport(endpoint, raw, content_type):
        assert endpoint in {'files/read', 'backtests/orders/read', 'backtests/read/log'}
        spent = controller._value(f'{OFF}.attempt.{attempt}.collection.0001.spent.json')
        assert spent['backtest_id'] == 'backtest-synthetic' and spent['read_only'] is True
        assert spent['new_compile_attempts'] == spent['new_backtest_launches'] == spent['new_development_looks'] == 0
        return cloud(endpoint, raw, content_type)
    controller.transport = admitted_transport
    assert controller.collect_terminal(OFF, attempt)['collection_round'] == 1


def test_five_collection_rounds_persist_across_controller_instances_and_refuse_before_api(environment):
    controller, cloud, _, attempt = ready(environment, launch=True)
    cloud.loading_endpoint = 'backtests/orders/read'
    for expected in range(1, 6):
        clone = op.Operations(deepcopy(controller.manifest), manifest_sha256=controller.manifest_sha256,
            _fixture_root=controller.root, _fixture_transport=cloud)
        assert clone.collect_terminal(OFF, attempt)['collection_round'] == expected
    before = len(cloud.calls)
    with pytest.raises(op.Refusal, match='five read-only collection rounds'):
        controller.collect_terminal(OFF, attempt)
    assert len(cloud.calls) == before
    assert len(list(controller.root.glob(f'{OFF}.attempt.{attempt}.collection.*.spent.json'))) == 5
    # A fresh operation identity cannot recycle the already-bound job or cap.
    successor = deepcopy(controller.manifest)
    successor['operation_id'] = 'TPR-MATCHED-ACCESS-FIXTURE-002'
    clone = op.Operations(successor, manifest_sha256=op.digest(op.canonical(successor)),
        _fixture_root=controller.root, _fixture_transport=cloud)
    clone.prepare_access()
    with pytest.raises(op.Refusal, match='attempt/code/input binding'):
        clone.collect_terminal(OFF, attempt)
    assert len(cloud.calls) == before
    assert len(list(controller.root.glob(f'{OFF}.attempt.{attempt}.collection.*.spent.json'))) == 5


def test_failed_collection_source_verification_has_numbered_error_and_can_explicitly_recover(environment):
    controller, cloud, bundles, attempt = ready(environment, launch=True)
    project_id = controller._project(OFF)['project_id']
    cloud.projects[project_id]['main.py'] = '# synthetic foreign modification\n'
    before = len(cloud.calls)
    with pytest.raises(op.Refusal, match='numbered collection compile/source verification'):
        controller.collect_terminal(OFF, attempt)
    prefix = f'{OFF}.attempt.{attempt}.collection.0001'
    assert cloud.calls[before:] == ['files/read']
    assert controller._value(prefix + '.error.json')['stage'] == 'compile_source_binding'
    assert controller._value(prefix + '.completion.json')['classification'] == 'diagnostic_or_incomplete'
    assert (controller.root / (prefix + '.evidence-index.json')).exists()
    assert not (controller.root / (prefix + '.source-receipt.json')).exists()  # No invented successful source binding.
    preserved = {path.name: controller.read_private(path.name) for path in controller.root.glob(prefix + '.*')}
    # Restore only the synthetic cloud fixture; production collect never edits cloud source.
    cloud.projects[project_id]['main.py'] = bundles[OFF]['main.py']
    assert controller.collect_terminal(OFF, attempt)['collection_round'] == 2
    assert all(controller.read_private(name) == raw for name, raw in preserved.items())
    assert cloud.calls.count('compile/create') == cloud.calls.count('backtests/create') == 1


def test_unknown_collection_request_outcome_is_consumed_without_implicit_retry(environment):
    controller, cloud, _, attempt = ready(environment, launch=True)
    cloud.fail_endpoint = 'backtests/orders/read'
    before = len(cloud.calls)
    evidence = controller.collect_terminal(OFF, attempt)
    assert cloud.calls[before:].count('backtests/orders/read') == 1
    assert evidence['completion']['classification'] == 'diagnostic_or_incomplete'
    assert controller._value(evidence['receipt_prefix'] + '.error.json')['stage'] == 'orders'
    terminals = [controller._value(path.name) for path in controller.root.glob('request.*.terminal.json')]
    assert sum(row['status'] == 'failed_or_unknown' for row in terminals) == 1
    cloud.fail_endpoint = None
    assert controller.collect_terminal(OFF, attempt)['completion']['filled_order_count'] == 104


@pytest.mark.parametrize('fault', ['duplicates', 'empty_page', 'zero_orders', 'runtime_error'])
def test_terminal_failures_and_zero_order_runs_remain_diagnostic(environment, fault):
    controller, cloud, _, attempt = ready(environment)
    if fault == 'duplicates':
        cloud.order_duplicate = True
    elif fault == 'empty_page':
        cloud.empty_order_page = True
    elif fault == 'zero_orders':
        cloud.order_count = 0
    else:
        cloud.error = 'synthetic runtime failure'
    controller.launch_backtest(OFF, attempt)
    controller.poll_backtest(OFF, attempt)
    evidence = controller.collect_terminal(OFF, attempt)
    assert evidence['completion']['classification'] == 'diagnostic_or_incomplete'
    assert evidence['completion']['strategy_accepted'] is False


@pytest.mark.parametrize('wrong_hash,wrong_key', [(True, False), (False, True), (True, True)],
    ids=['foreign-hash-only', 'misplaced-key-only', 'foreign-hash-and-key'])
def test_on_arm_cannot_launch_with_a_foreign_or_misplaced_packet_receipt(environment, wrong_hash, wrong_key):
    """TPR-CR22-008: a present upload receipt admits the TPR-on arm only when it
    names this study's exact packet hash under this study's own namespace; a
    foreign hash or another study's key must refuse before any launch call."""
    controller, cloud, _, attempt = ready(environment, candidate=ON)
    foreign = op.PACKET_HASH[::-1]
    assert foreign != op.PACKET_HASH
    packet_hash = foreign if wrong_hash else op.PACKET_HASH
    if wrong_key:
        key = (f'tpr-matched/{op.STUDY}/{foreign}.json' if wrong_hash else
               f'tpr-elsewhere/{op.STUDY}/{op.PACKET_HASH}.json')
    else:
        key = f'tpr-matched/{op.STUDY}/{op.PACKET_HASH}.json'
    controller.exclusive('packet-upload.completed.json',
        {'at': op.utc(), 'status': 'uploaded', 'packet_sha256': packet_hash, 'key': key})
    with pytest.raises(op.Refusal, match='admitted private packet'):
        controller.launch_backtest(ON, attempt)
    assert 'backtests/create' not in cloud.calls
    assert not (controller.root / f'{ON}.attempt.{attempt}.backtest.spent.json').exists()


def test_on_arm_exact_packet_receipt_reaches_the_launch(environment):
    """A valid ON control proves packet negatives do not pass through an earlier refusal."""
    controller, cloud, _, attempt = ready(environment, candidate=ON)
    controller.exclusive('packet-upload.completed.json', {'at': op.utc(),
        'status': 'uploaded', 'packet_sha256': op.PACKET_HASH,
        'key': f'tpr-matched/{op.STUDY}/{op.PACKET_HASH}.json'})
    launched = controller.launch_backtest(ON, attempt)
    assert launched['backtest_id'] == 'backtest-synthetic'
    assert cloud.calls.count('backtests/create') == 1
    spent = controller._value(f'{ON}.attempt.{attempt}.backtest.spent.json')
    assert spent['fixture'] is True and spent['development_look_consumed'] is False


def test_on_arm_cannot_launch_without_packet_but_neutral_can(environment):
    controller, cloud, _, attempt = ready(environment, candidate=ON)
    with pytest.raises(op.Refusal):
        controller.launch_backtest(ON, attempt)
    assert 'backtests/create' not in cloud.calls


def test_fresh_packet_read_and_upload_are_single_use_and_new_namespace(tmp_path, monkeypatch):
    raw = b'{"synthetic_packet":true}\n'
    monkeypatch.setattr(op, 'PACKET_HASH', op.digest(raw))
    body, _ = manifest()
    cloud = Cloud()
    controller = op.Operations(body, manifest_sha256=op.digest(op.canonical(body)),
        _fixture_root=tmp_path / 'private', _fixture_transport=cloud)
    controller.prepare_access()
    path = controller.root / 'fixture-packet.json'
    path.write_bytes(raw)
    path.chmod(0o600)
    assert controller.prepare_packet()['sha256'] == op.digest(raw)
    with pytest.raises(op.Refusal, match='already exists'):
        controller.prepare_packet()
    controller.create_project(ON)
    uploaded = controller.upload_packet(ON)
    assert uploaded['key'] == f'tpr-matched/{op.STUDY}/{op.digest(raw)}.json'
    with pytest.raises(op.Refusal, match='already exists'):
        controller.upload_packet(ON)
    assert cloud.calls.count('object/set') == 1


def test_redaction_removes_both_credentials_recursively_without_losing_other_metadata():
    result = op.redact({'errors': ['SYNTHETIC_UID SYNTHETIC_TOKEN'],
        'userId': 1234, 'api_token': 'SYNTHETIC_TOKEN', 'status': 'failed'},
        'SYNTHETIC_UID', 'SYNTHETIC_TOKEN')
    assert result == {'errors': ['[redacted] [redacted]'], 'userId': '[redacted]',
                      'api_token': '[redacted]', 'status': 'failed'}


def test_wall_deadline_refuses_existing_timer_and_restores_handler(monkeypatch):
    monkeypatch.setattr(op.signal, 'getitimer', lambda _: (1.0, 0.0))
    with pytest.raises(op.Refusal, match='existing wall timer'):
        with op._wall_deadline(30):
            pytest.fail('deadline admitted existing timer')
    monkeypatch.setattr(op.signal, 'getitimer', lambda _: (0.0, 0.0))
    changes = []
    monkeypatch.setattr(op.signal, 'getsignal', lambda _: 'prior-handler')
    monkeypatch.setattr(op.signal, 'signal', lambda *args: changes.append(('handler', args)))
    monkeypatch.setattr(op.signal, 'setitimer', lambda *args: changes.append(('timer', args)))
    with pytest.raises(op.Refusal, match='deadline exceeded'):
        with op._wall_deadline(30):
            changes[0][1][1](None, None)
    assert changes[-2] == ('timer', (op.signal.ITIMER_REAL, 0))
    assert changes[-1] == ('handler', (op.signal.SIGALRM, 'prior-handler'))


def test_production_guard_checks_actual_source_hash_without_operator_state(environment, monkeypatch):
    controller, _, _ = environment
    controller.fixture = False
    def git(args, **kwargs):
        if args[1:3] == ['merge-base', '--is-ancestor']:
            assert args[3:] == [op.BASELINE, op.BASELINE]
            return SimpleNamespace(returncode=0, stdout='')
        values = {('rev-parse', '--show-toplevel'): str(op.LANE), ('branch', '--show-current'): op.BRANCH,
                  ('rev-parse', 'HEAD'): op.BASELINE, ('status', '--short'): ' M synthetic.py'}
        return SimpleNamespace(stdout=values[tuple(args[1:])] + '\n')
    monkeypatch.setattr(op.subprocess, 'run', git)
    assert controller.guard()['dirty_status_sha256'] == op.digest(b' M synthetic.py')
    controller.manifest['repository_source_hashes'][op.MODULE_PATH] = '0' * 64
    with pytest.raises(op.Refusal, match='source changed'):
        controller.guard()


@pytest.mark.parametrize('ancestry', [0, 1, 128])
def test_committed_successor_baseline_requires_completed_review_ancestry(environment, monkeypatch, ancestry):
    controller, _, _ = environment
    head = '1' * 40
    controller.manifest['baseline_git_head'] = head
    controller.fixture = False
    calls = []
    def git(args, **kwargs):
        calls.append(args[1:])
        if args[1:3] == ['merge-base', '--is-ancestor']:
            assert args[3:] == [op.BASELINE, head]
            return SimpleNamespace(returncode=ancestry, stdout='')
        values = {('rev-parse', '--show-toplevel'): str(op.LANE), ('branch', '--show-current'): op.BRANCH,
                  ('rev-parse', 'HEAD'): head, ('status', '--short'): ''}
        return SimpleNamespace(stdout=values[tuple(args[1:])] + '\n')
    monkeypatch.setattr(op.subprocess, 'run', git)
    if ancestry == 0:
        assert controller.guard()['git_head'] == head
    else:
        with pytest.raises(op.Refusal, match='diverges'):
            controller.guard()
    assert ['merge-base', '--is-ancestor', op.BASELINE, head] in calls


def test_immutable_private_receipts_refuse_overwrite_and_widened_modes(environment):
    controller, _, _ = environment
    controller.exclusive('synthetic.json', {'value': 1})
    with pytest.raises(op.Refusal, match='already exists'):
        controller.exclusive('synthetic.json', {'value': 2})
    (controller.root / 'synthetic.json').chmod(0o644)
    with pytest.raises(op.Refusal, match='custody'):
        controller.read_private('synthetic.json')
