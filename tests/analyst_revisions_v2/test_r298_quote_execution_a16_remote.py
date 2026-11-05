"""A16 identity-only helper successor; no operations or private artifacts."""
import ast
import json
from pathlib import Path

import pytest

from scripts import arv2_r298_quote_execution_a16_remote as m
from scripts import arv2_r298_quote_execution_remote as previous
from tests.analyst_revisions_v2 import test_r298_quote_execution_remote as fixtures


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


def masked(raw, *, schema, attempt, name):
    tree = ast.parse(raw)
    assert isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant)
    tree.body[0].value = ast.Constant('permitted module documentation')
    seen = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1: continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in ('SCHEMA', 'BACKTEST_NAME'):
            assert ast.literal_eval(node.value) == (schema if target.id == 'SCHEMA' else name)
            node.value = ast.Constant('permitted identity'); seen.add(target.id)
        elif isinstance(target, ast.Tuple) and [part.id for part in target.elts] == ['PROJECT_ID', 'ATTEMPT']:
            assert ast.literal_eval(node.value) == (38364439, attempt)
            node.value.elts[1] = ast.Constant(0); seen.add('ATTEMPT')
    assert seen == {'SCHEMA', 'BACKTEST_NAME', 'ATTEMPT'}
    return ast.dump(tree, include_attributes=False)


def test_complete_helper_ast_identical_except_three_identities_and_docstring():
    old = (ROOT / 'scripts/arv2_r298_quote_execution_remote.py').read_bytes()
    new = (ROOT / 'scripts/arv2_r298_quote_execution_a16_remote.py').read_bytes()
    assert m.sha(old) == '5777c6cefd93a738817f2ef523ccbadee6763a9183cc6c14a96c43140f216893'
    assert masked(old, schema='arv2-r298-quote-execution-a15-v1', attempt=15,
        name='ARV2 R298 QUOTE EXECUTION R323 A15') == masked(new,
        schema='arv2-r298-quote-execution-a16-v1', attempt=16, name='ARV2 R298 QUOTE EXECUTION R323 A16')


def test_same_execution_policy_source_history_and_false_formal_flags():
    old, new = previous.profile_record(), m.profile_record()
    assert {key for key in old if old[key] != new[key]} == {'schema', 'attempt', 'backtest_name'}
    assert m.PROJECTION_SHA256 == previous.PROJECTION_SHA256 == '3735a7764f658ba867edb338615666844ceb8f81d7aebdc36d8b7b6495e67779'
    assert m.PROFILE_SHA256 == previous.PROFILE_SHA256 == 'cf6e4063796cd297b28aaa1620056a2a86e8bfe7f65a194de1e531f97dc64569'
    assert m.SOURCE_MANIFEST_SHA256 == previous.SOURCE_MANIFEST_SHA256 == 'b4ed1a5f3cb5da08bed86589b1d06fa8fa620b90a809b264b78661a723b3e907'
    assert m.OLD_PROJECTION_SHA256 == previous.OLD_PROJECTION_SHA256
    assert m.OLD_SOURCE_MANIFEST_SHA256 == previous.OLD_SOURCE_MANIFEST_SHA256
    assert m.A14_ID == previous.A14_ID and m.PAYLOAD_KEYS == previous.PAYLOAD_KEYS
    assert m.projection is previous.projection and m.previous is previous.previous
    assert new['diagnostic_only'] is False and new['accepted_risk_only'] is True
    assert all(new[key] is False for key in m.FALSE_FLAGS)


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setattr(fixtures, 'm', m)
    return fixtures.cloud.__wrapped__(monkeypatch)


def launch(cloud):
    receipt = cloud.runner.prepare_once()
    assert receipt['schema'] == m.SCHEMA and receipt['attempt'] == 16
    assert cloud.runner.poll_compile(0)['state'] == 'BuildSuccess'
    result = cloud.runner.launch_once()
    assert result['launch_receipt']['backtest_name'] == m.BACKTEST_NAME
    return result


def test_genuine_constructor_and_exact_new_profile_result_validator(monkeypatch):
    monkeypatch.setattr(fixtures, 'm', m)
    fixtures.test_genuine_public_projection_and_unchanged_parameterized_result_validator()


def test_one_exact_source_compile_job_result_lifecycle_without_claiming_family_comparability(cloud):
    launch(cloud)
    assert cloud.files == cloud.sources
    assert [body['name'] for endpoint, body in cloud.calls if endpoint == 'files/update'] == list(m.EDIT_NAMES)
    assert sum(endpoint == 'compile/create' for endpoint, _ in cloud.calls) == 1
    assert sum(endpoint == 'backtests/create' for endpoint, _ in cloud.calls) == 1
    cloud.own['status'] = 'Completed.'; cloud.runner.poll_status(0)
    result = cloud.runner.read_once()
    assert result['attempt'] == 16 and result['family_comparable'] is False
    assert result['result_cell'] == 1 and result['accepted_risk_only'] is True
    m.validate_result_receipt(result)
    count = len(cloud.calls)
    for call in (cloud.runner.prepare_once, cloud.runner.launch_once, cloud.runner.read_once, cloud.runner.read_failure_once):
        with pytest.raises(m.Refused): call()
    assert len(cloud.calls) == count


@pytest.mark.parametrize('change', ['running', 'public', 'dedicated', 'extra'])
def test_current_strict_access_and_idleness_still_precede_mutation(cloud, change):
    if change == 'running': cloud.project['codeRunning'] = True
    elif change == 'public': cloud.project['public'] = True
    elif change == 'dedicated': cloud.dedicated['userPermissions'] = 'read'
    else: cloud.project['collaborators'].append({'owner': False})
    with pytest.raises(m.previous.ready.access.AccessRefused): cloud.runner.prepare_once()
    assert [endpoint for endpoint, _ in cloud.calls] == ['projects/read', 'projects/collaboration/read']


@pytest.mark.parametrize('change', ['unexpected_a15_job', 'a14_status', 'old_source', 'after_lock'])
def test_no_invented_a15_job_or_source_drift_can_renew_readiness(cloud, change):
    if change == 'a14_status': cloud.a14['status'] = 'Completed.'
    if change == 'old_source': cloud.files['main.py'] += b'# drift\n'
    def mutate(endpoint, payload, value):
        if change == 'unexpected_a15_job' and endpoint == 'backtests/list':
            value['backtests'].append(dict(cloud.a14, backtestId='a15-unknown', name=previous.BACKTEST_NAME))
            value['count'] += 1
        if change == 'after_lock' and endpoint == 'projects/collaboration/lock/acquire': cloud.files['main.py'] += b'# drift\n'
    cloud.mutation = mutate
    with pytest.raises(ValueError): cloud.runner.prepare_once()
    assert not any(endpoint in ('files/update', 'compile/create', 'backtests/create') for endpoint, _ in cloud.calls)


def test_failure_only_detail_read_retains_closed_code_not_raw_statistics(cloud):
    launch(cloud); cloud.own['status'] = 'Runtime Error'; cloud.runner.poll_status(0)
    code = sorted(m.projection.FAILURE_CODES)[0]
    cloud.detail_error = 'NewruleError: ' + code + '\nPRIVATE PRICE AND SYMBOL'
    cloud.stats['PRIVATE LICENSED ROWS'] = 'never forwarded'
    result = cloud.runner.read_failure_once()
    assert result['failure_evidence']['known_runtime_code'] == code
    assert result['failure_evidence']['diagnostic_context'] is None and cloud.validation == []
    assert 'PRIVATE' not in json.dumps(result)
    with pytest.raises(m.Refused, match='^result_once$'): cloud.runner.read_failure_once()
    with pytest.raises(m.Refused, match='^result_once$'): cloud.runner.read_once()
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1


@pytest.mark.parametrize('field,bad', [('attempt', 15), ('attempt', True), ('schema', previous.SCHEMA),
    ('accepted_risk_only', False), ('diagnostic_only', True), ('paper_or_live_ready', 0)])
def test_new_receipts_refuse_old_identity_or_flag_promotion(cloud, field, bad):
    receipt = cloud.runner.prepare_once(); receipt[field] = bad
    with pytest.raises(m.Refused): m.validate_compile_receipt(receipt)
