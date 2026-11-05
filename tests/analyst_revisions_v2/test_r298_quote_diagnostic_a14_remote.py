"""Additive A14 identity; public source and injected synthetic responses only."""
import ast
import json
from pathlib import Path

import pytest

from scripts import arv2_r298_quote_diagnostic_a14_remote as m
from scripts import arv2_r298_quote_diagnostic_remote as a13
from tests.analyst_revisions_v2 import test_r298_quote_diagnostic_remote as prior_tests


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
OLD_HELPER = ROOT / 'scripts/arv2_r298_quote_diagnostic_remote.py'
NEW_HELPER = ROOT / 'scripts/arv2_r298_quote_diagnostic_a14_remote.py'
OLD_HELPER_SHA256 = 'bed3653baeeeb5c1338127832ccd51af4587d957d733e18cdde33a11ef27c6e0'


def masked_tree(raw, *, schema, attempt, name):
    tree = ast.parse(raw)
    assert isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant)
    assert type(tree.body[0].value.value) is str
    tree.body[0].value = ast.Constant(value='permitted module documentation')
    seen = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in ('SCHEMA', 'BACKTEST_NAME'):
            expected = schema if target.id == 'SCHEMA' else name
            assert ast.literal_eval(node.value) == expected
            node.value = ast.Constant(value='permitted identity')
            seen.add(target.id)
        elif isinstance(target, ast.Tuple) and [part.id for part in target.elts] == ['PROJECT_ID', 'ATTEMPT']:
            assert ast.literal_eval(node.value) == (38364439, attempt)
            node.value.elts[1] = ast.Constant(value=0)
            seen.add('ATTEMPT')
    assert seen == {'SCHEMA', 'BACKTEST_NAME', 'ATTEMPT'}
    return ast.dump(tree, include_attributes=False)


def test_entire_helper_ast_equal_except_three_bound_identities_and_docstring():
    old = OLD_HELPER.read_bytes()
    assert m.sha(old) == OLD_HELPER_SHA256
    assert masked_tree(old, schema='arv2-r298-quote-diagnostic-v1', attempt=13,
        name='ARV2 R298 QUOTE DIAGNOSTIC R323 A13') == masked_tree(NEW_HELPER.read_bytes(),
        schema='arv2-r298-quote-diagnostic-a14-v1', attempt=14,
        name='ARV2 R298 QUOTE DIAGNOSTIC R323 A14')


def test_only_protocol_identity_changes_not_cloud_or_access_contract():
    old, new = a13.profile_record(), m.profile_record()
    assert {key for key in old if old[key] != new[key]} == {'schema', 'attempt', 'backtest_name'}
    assert m.PROJECTION_SHA256 == a13.PROJECTION_SHA256 == '1f366e402b3754e9f1f8ba89d08f250df771431b2ae98d19da953cfb722db293'
    assert m.PROFILE_SHA256 == a13.PROFILE_SHA256 == '1133de6d18fb8d8b5355fb906d5a2f38f97e1f97460b80bd1f4c9014e901ad70'
    assert m.SOURCE_MANIFEST_SHA256 == a13.SOURCE_MANIFEST_SHA256 == 'ed8bd6c988d6d9fc31586b9dd8df058e8235a79702f52d78a172c31a1e64b190'
    assert m.A12_ID == a13.A12_ID
    assert m.previous is a13.previous and m.projection is a13.projection
    assert m.CODE_SOURCE_ID == a13.CODE_SOURCE_ID
    assert m.PAYLOAD_KEYS == a13.PAYLOAD_KEYS and m.FALSE_FLAGS == a13.FALSE_FLAGS
    assert all(new[key] is False for key in m.FALSE_FLAGS)


@pytest.fixture
def cloud(monkeypatch):
    # Reuse only the original synthetic fixture; all public receiver/source
    # bindings are tested without monkeypatching separately below.
    monkeypatch.setattr(prior_tests, 'm', m)
    return prior_tests.cloud.__wrapped__(monkeypatch)


def test_genuine_public_projection_constructs_without_dispatch_or_admission():
    research = ROOT / 'research/analyst_revisions_v2_qc'
    comparison = m.projection.comparison
    names = set(comparison.bridge.parent.SOURCE_PINS) | set(comparison.NEW_SOURCE_PINS) | {comparison.HOST_SOURCE_NAME}
    sources = {name: (research / name).read_bytes() for name in names}
    spec = comparison.public_specification(sources=sources,
        expected_host_source_pins={comparison.HOST_SOURCE_NAME: m.sha(sources[comparison.HOST_SOURCE_NAME])})
    pairs = tuple((item.project_path, item.source_bytes) for item in spec.cells[0].source_files)
    patcher = (ROOT / 'scripts' / m.projection.PATCHER_NAME).read_bytes()
    projected = m.projection.public_specification(pairs, patcher_source_bytes=patcher,
        expected_patcher_sha256=m.sha(patcher))
    def forbidden(*args):
        pytest.fail('public constructor must not dispatch or journal')
    runner = m.QuoteDiagnostic(projected.record_bytes, projected.source_pairs,
        request=forbidden, journal=forbidden)
    assert runner.compile_receipt is runner.launch_receipt is runner.terminal_receipt is None
    assert runner._profile['profile_sha256'] == m.PROFILE_SHA256
    assert m.sha(projected.record_bytes) == m.PROJECTION_SHA256
    assert m.sha(m.canonical(m.QuoteDiagnostic._manifest(dict(projected.source_pairs),
        m.PROJECTION_SHA256))) == m.SOURCE_MANIFEST_SHA256


def prepare(cloud):
    receipt = cloud.runner.prepare_once()
    assert receipt['attempt'] == 14 and receipt['schema'] == m.SCHEMA
    assert cloud.runner.poll_compile(0)['state'] == 'BuildSuccess'
    return receipt


def launch(cloud):
    prepare(cloud)
    result = cloud.runner.launch_once()
    assert result['state'] == 'launched'
    assert result['launch_receipt']['backtest_name'] == m.BACKTEST_NAME
    return result


def test_one_prepare_compile_launch_and_aggregate_flow_preserves_exact_source(cloud):
    launch(cloud)
    assert cloud.files == cloud.sources
    edits = [body for endpoint, body in cloud.calls if endpoint == 'files/update']
    assert [body['name'] for body in edits] == list(m.EDIT_NAMES)
    assert all(body['content'].encode('ascii') == cloud.sources[body['name']] for body in edits)
    assert sum(endpoint == 'compile/create' for endpoint, _ in cloud.calls) == 1
    assert sum(endpoint == 'backtests/create' for endpoint, _ in cloud.calls) == 1
    assert sum(endpoint == 'projects/collaboration/lock/acquire' for endpoint, _ in cloud.calls) == 1
    cloud.own['status'] = 'Completed.'
    assert cloud.runner.poll_status(0)['terminal'] is True
    cloud.stats['PRIVATE EXTRA STATISTIC'] = 'never forwarded'
    result = cloud.runner.read_once()
    m.validate_result_receipt(result)
    assert result['attempt'] == 14 and result['family_comparable'] is False
    assert result['profile_sha256'] == m.PROFILE_SHA256
    assert set(cloud.validation[0][0]) == {m.previous.frozen.runtime.META_STATISTIC,
        m.previous.frozen.runtime.MONTHLY_STATISTIC}
    assert 'PRIVATE EXTRA' not in json.dumps(result)
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1
    count = len(cloud.calls)
    for call, code in ((cloud.runner.prepare_once, 'prepare_once'),
            (cloud.runner.launch_once, 'launch_once'), (cloud.runner.read_once, 'result_once'),
            (cloud.runner.read_failure_once, 'result_once')):
        with pytest.raises(m.Refused, match='^' + code + '$'):
            call()
    assert len(cloud.calls) == count


@pytest.mark.parametrize('change,code', [('running', 'idle'), ('public', 'public_contradiction'),
    ('dedicated', 'dedicated_permissions'), ('extra', 'extra_row_shape')])
def test_strict_access_foreign_refusals_preserved_before_source_or_edits(cloud, change, code):
    if change == 'running': cloud.project['codeRunning'] = True
    if change == 'public': cloud.project['public'] = True
    if change == 'dedicated': cloud.dedicated['userPermissions'] = 'read'
    if change == 'extra': cloud.project['collaborators'].append({'owner': False})
    with pytest.raises(m.previous.ready.access.AccessRefused) as error:
        cloud.runner.prepare_once()
    assert m.finite(error.value) == code
    assert [endpoint for endpoint, _ in cloud.calls] == ['projects/read', 'projects/collaboration/read']
    count = len(cloud.calls)
    with pytest.raises(m.Refused, match='^prepare_once$'):
        cloud.runner.prepare_once()
    assert len(cloud.calls) == count


@pytest.mark.parametrize('change', ['a12', 'a13_job', 'old_source', 'drift_after_lock'])
def test_only_exact_manual_a12_history_and_old_source_permitted(cloud, change):
    if change == 'a12': cloud.a12['status'] = 'Completed.'
    if change == 'old_source': cloud.files['main.py'] += b'# nonmatching old source\n'
    def mutate(endpoint, payload, value):
        if change == 'a13_job' and endpoint == 'backtests/list':
            value['backtests'].append({'projectId': m.PROJECT_ID, 'backtestId': 'a13-unexpected',
                'name': a13.BACKTEST_NAME, 'status': 'Runtime Error'})
            value['count'] += 1
        if change == 'drift_after_lock' and endpoint == 'projects/collaboration/lock/acquire':
            cloud.files['main.py'] += b'# concurrent source drift\n'
    cloud.mutation = mutate
    with pytest.raises(ValueError):
        cloud.runner.prepare_once()
    assert not any(endpoint in ('files/update', 'compile/create', 'backtests/create') for endpoint, _ in cloud.calls)


@pytest.mark.parametrize('stage', ['before_prepare', 'compiled', 'pending', 'completed', 'compile_error'])
def test_failure_detail_requires_runtime_terminal_without_dispatch(cloud, stage):
    if stage == 'compiled': prepare(cloud)
    elif stage == 'pending': launch(cloud)
    elif stage == 'completed':
        launch(cloud)
        cloud.own['status'] = 'Completed.'
        cloud.runner.poll_status(0)
    elif stage == 'compile_error':
        cloud.runner.prepare_once()
        cloud.compile_state = 'BuildError'
        cloud.runner.poll_compile(0)
    count = len(cloud.calls)
    with pytest.raises(m.Refused, match='^status$'):
        cloud.runner.read_failure_once()
    assert len(cloud.calls) == count


CONTEXT = ('execution_price_end_not_current|cache=quote_bar'
    '|trade=fresh_non_fill_forward|quote=stale|price_trade=equal')


def failed(cloud, error=None):
    launch(cloud)
    cloud.own['status'] = 'Runtime Error'
    if error is not None: cloud.own['error'] = error
    return cloud.runner.poll_status(0)


def test_single_failure_read_retains_finite_context_no_raw_or_statistic(cloud):
    failed(cloud)
    cloud.detail_error = 'Runtime Error: NewruleError: ' + CONTEXT + '\nPRIVATE SYMBOL PRICE123'
    cloud.stats['PRIVATE LICENSED EXTRA'] = 'never forwarded'
    result = cloud.runner.read_failure_once()
    evidence = result['failure_evidence']
    assert evidence['known_runtime_code'] == 'execution_price_end_not_current'
    assert evidence['diagnostic_context'] == m.projection.parse_failure_context(CONTEXT)
    assert evidence['raw_error_retained'] is False and evidence['cause_authenticated'] is False
    assert cloud.validation == []
    assert 'PRIVATE' not in json.dumps(result) and 'PRICE123' not in json.dumps(cloud.events)
    m.validate_terminal_receipt(result)
    count = len(cloud.calls)
    for call in (cloud.runner.read_failure_once, cloud.runner.read_once):
        with pytest.raises(m.Refused, match='^result_once$'):
            call()
    assert len(cloud.calls) == count
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1


@pytest.mark.parametrize('detail', ['unknown private message',
    'NewruleError: execution_price_fill_forward',
    'execution_price_end_not_current|cache=trade_bar|trade=stale|quote=missing|price_trade=unknown'])
def test_failure_merge_preserves_known_or_refuses_conflict_without_second_read(cloud, detail):
    failed(cloud, 'NewruleError: ' + CONTEXT)
    before = cloud.runner.terminal_receipt
    cloud.detail_error = detail
    if detail.startswith('unknown'):
        assert cloud.runner.read_failure_once() == before
    else:
        with pytest.raises(m.Refused, match='^response$'):
            cloud.runner.read_failure_once()
        assert cloud.runner.terminal_receipt == before
    with pytest.raises(m.Refused, match='^result_once$'):
        cloud.runner.read_failure_once()
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1


@pytest.mark.parametrize('field,bad', [('attempt', 13), ('attempt', True),
    ('schema', 'arv2-r298-quote-diagnostic-v1'), ('profile_sha256', '0' * 64),
    ('paper_or_live_ready', 0)])
def test_receipts_cannot_reuse_a13_or_weaken_source_or_false_flags(cloud, field, bad):
    receipt = cloud.runner.prepare_once()
    receipt[field] = bad
    with pytest.raises(m.Refused, match='^compile_receipt$'):
        m.validate_compile_receipt(receipt)


@pytest.mark.parametrize('endpoint', ['projects/create', 'files/create', 'files/delete',
    'projects/collaboration/delete', 'backtests/delete', 'live/create'])
def test_forbidden_endpoints_never_dispatch(cloud, endpoint):
    with pytest.raises(m.Refused, match='^endpoint$'):
        cloud.runner._rpc('forged', endpoint, {'projectId': m.PROJECT_ID})
    assert cloud.calls == cloud.events == []


def test_compile_refusal_is_terminal_and_no_launch(cloud):
    cloud.runner.prepare_once()
    cloud.compile_state, cloud.compile_error = 'BuildError', 'TypeError: PRIVATE RAW CONTENT'
    cloud.runner.poll_compile(0)
    value = cloud.runner.terminal_receipt
    assert value['failure_evidence']['python_error_category'] == 'TypeError'
    assert 'PRIVATE' not in json.dumps(value)
    with pytest.raises(m.Refused, match='^launch_once$'):
        cloud.runner.launch_once()
    assert not any(endpoint == 'backtests/create' for endpoint, _ in cloud.calls)


def test_busy_capacity_uses_same_bounded_wait_without_cancel(cloud):
    prepare(cloud)
    cloud.busy = True
    for index in range(m.CAPACITY_POLLS):
        cloud.time = index * m.CAPACITY_INTERVAL
        assert cloud.runner.launch_once()['state'] == 'wait'
    cloud.time += m.CAPACITY_INTERVAL
    with pytest.raises(m.Refused, match='^capacity_budget$'):
        cloud.runner.launch_once()
    assert not any(endpoint == 'backtests/create' for endpoint, _ in cloud.calls)
