"""A18 exact access-representation successor; synthetic/native-denied only."""
import ast
import copy
from pathlib import Path

import pytest

from scripts import arv2_r298_raw_reference_diagnostic_a18_remote as m
from scripts import arv2_r298_raw_reference_diagnostic_remote as previous
from tests.analyst_revisions_v2 import test_r298_raw_reference_diagnostic_remote as fixtures
from tests.analyst_revisions_v2 import test_r298_mia_access_representation as access_fixtures


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
OLD_SHA256 = '2ad47581084c0bc9f42673dccc94c11563cd5122c0c5a1b717c0a2c7d57d5470'


def test_entire_remote_ast_changes_only_identity_access_import_call_and_profile():
    old = (ROOT / 'scripts/arv2_r298_raw_reference_diagnostic_remote.py').read_bytes()
    new = (ROOT / 'scripts/arv2_r298_raw_reference_diagnostic_a18_remote.py').read_text()
    assert m.sha(old) == OLD_SHA256
    replacements = [
        ('Injected A18 RAW diagnostic after a separately pinned Mia access representation.',
            'Injected A17 failure-only RAW-reference diagnostic and selected result read.'),
        ('from scripts import arv2_r298_mia_access_representation as access\n', ''),
        ("SCHEMA = 'arv2-r298-raw-reference-diagnostic-a18-v1'",
            "SCHEMA = 'arv2-r298-raw-reference-diagnostic-a17-v1'"),
        ('PROJECT_ID, ATTEMPT = 38364439, 18', 'PROJECT_ID, ATTEMPT = 38364439, 17'),
        ("BACKTEST_NAME = 'ARV2 R298 RAW REFERENCE DIAGNOSTIC R323 A18'",
            "BACKTEST_NAME = 'ARV2 R298 RAW REFERENCE DIAGNOSTIC R323 A17'"),
        ("        'access_representation_schema': access.SCHEMA,\n"
            "        'access_representation_policy': access.profile_record(),\n", ''),
        ('        checked = access.verify_access(project, dedicated)',
            '        checked = previous.ready.access.verify_access(project, dedicated)'),
    ]
    for before, after in replacements:
        assert new.count(before) == 1
        new = new.replace(before, after)
    assert ast.dump(ast.parse(new), include_attributes=False) == ast.dump(ast.parse(old), include_attributes=False)


def test_scope_identity_cloud_profile_history_and_false_flags_stay_frozen():
    assert m.SCHEMA == 'arv2-r298-raw-reference-diagnostic-a18-v1' and m.ATTEMPT == 18
    assert m.BACKTEST_NAME == 'ARV2 R298 RAW REFERENCE DIAGNOSTIC R323 A18'
    for name in ('PROJECT_ID', 'PROJECTION_SHA256', 'PROFILE_SHA256', 'SOURCE_MANIFEST_SHA256',
        'OLD_PROJECTION_SHA256', 'OLD_SOURCE_MANIFEST_SHA256', 'CODE_SOURCE_ID',
        'A12_ID', 'A14_ID', 'A14_NAME', 'A14_COMPILE_ID', 'A16_ID', 'A16_NAME', 'A16_COMPILE_ID',
        'EDIT_NAMES', 'COMPILE_POLLS', 'CAPACITY_POLLS', 'STATUS_POLLS', 'PAYLOAD_KEYS', 'FINITE'):
        assert getattr(m, name) == getattr(previous, name)
    old, new = previous.profile_record(), m.profile_record()
    extras = {'access_representation_schema', 'access_representation_policy'}
    assert set(new) == set(old) | extras
    assert {key for key in old if old[key] != new[key]} == {'schema', 'attempt', 'backtest_name'}
    assert new['access_representation_schema'] == m.access.SCHEMA
    assert new['access_representation_policy'] == m.access.profile_record()
    assert m._binding()['diagnostic_only'] is True
    assert all(m._binding()[key] is False for key in m.FALSE_FLAGS)


def test_new_access_helper_is_direct_without_mutating_frozen_module_globals():
    assert m.access is not m.previous.ready.access
    tree = ast.parse((ROOT / 'scripts/arv2_r298_raw_reference_diagnostic_a18_remote.py').read_bytes())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'QuoteDiagnostic')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == '_access')
    calls = [ast.unparse(node.func) for node in ast.walk(method) if isinstance(node, ast.Call)]
    assert calls.count('access.verify_access') == 1
    assert 'previous.ready.access.verify_access' not in calls
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in ('setattr', 'exec', 'eval') for node in ast.walk(tree))


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setattr(fixtures, 'm', m)
    state = fixtures.cloud.__wrapped__(monkeypatch)
    supplied = access_fixtures.supplied.__wrapped__(monkeypatch)
    state.project = copy.deepcopy(supplied.project['projects'][0])
    state.dedicated = copy.deepcopy(supplied.dedicated)
    return state


def test_genuine_public_projection_constructor_preserves_all_pins_without_dispatch(monkeypatch):
    monkeypatch.setattr(fixtures, 'm', m)
    fixtures.test_actual_public_projection_is_received_with_exact_source_and_profile_pins()


def test_one_exact_diagnostic_lifecycle_with_no_a17_job_or_result_cell(cloud):
    result = fixtures.launch(cloud)
    assert result['state'] == 'launched' and result['launch_receipt']['attempt'] == 18
    assert cloud.files == cloud.sources
    assert [body['name'] for endpoint, body in cloud.calls if endpoint == 'files/update'] == list(m.EDIT_NAMES)
    assert sum(endpoint == 'compile/create' for endpoint, _ in cloud.calls) == 1
    assert sum(endpoint == 'backtests/create' for endpoint, _ in cloud.calls) == 1
    assert cloud.own['name'] == m.BACKTEST_NAME
    cloud.own['status'] = 'Completed.'
    cloud.runner.poll_status(0)
    receipt = cloud.runner.read_once()
    assert receipt['attempt'] == 18 and receipt['result_cell'] == 0
    assert receipt['diagnostic_only'] is True and receipt['family_comparable'] is False
    m.validate_result_receipt(receipt)
    before = len(cloud.calls)
    for method in (cloud.runner.prepare_once, cloud.runner.launch_once,
        cloud.runner.read_once, cloud.runner.read_failure_once):
        with pytest.raises(ValueError): method()
    assert len(cloud.calls) == before


def test_every_fresh_stage_calls_new_access_verifier_and_journals_qualified_receipt(cloud, monkeypatch):
    original, observations = m.access.verify_access, []
    def verify(project, dedicated):
        checked = original(project, dedicated)
        observations.append(copy.deepcopy(checked))
        return checked
    monkeypatch.setattr(m.access, 'verify_access', verify)
    fixtures.launch(cloud)
    cloud.own['status'] = 'Runtime Error'
    cloud.runner.poll_status(0)
    cloud.detail_error = m.response_projection.RAW_REFERENCE_LITERAL
    cloud.runner.read_failure_once()
    access_events = [event['observation'] for _, event in cloud.events if event['event'] == 'access']
    assert observations == access_events and len(observations) >= 5
    assert all(row['schema'] == m.access.SCHEMA for row in observations)
    for row in observations:
        assert row['synthetic_entry_proven'] is False
        assert row['privacy_proven'] is False and row['edit_lock_proven'] is False
        assert row['operational_retry_authority'] is False


@pytest.mark.parametrize('field,value', [('uid', 999), ('name', 'Mia-other'),
    ('publicId', 'mia-ai'), ('permission', 'read'), ('owner', True), ('email', 'changed')])
def test_new_mia_representation_drift_refuses_before_history_lock_or_source_write(cloud, field, value):
    cloud.project['collaborators'][2][field] = value
    with pytest.raises(m.access.AccessRefused) as error: cloud.runner.prepare_once()
    assert m.access.finite_error(error.value)['code'] == 'general_row_pin'
    assert [endpoint for endpoint, _ in cloud.calls] == ['projects/read', 'projects/collaboration/read']


def test_pinned_mia_is_never_removed_from_dedicated_collaborator_view(cloud):
    cloud.dedicated['collaborators'].append(copy.deepcopy(cloud.project['collaborators'][2]))
    with pytest.raises(m.access.AccessRefused, match='^dedicated_owner$'):
        cloud.runner.prepare_once()
    assert [endpoint for endpoint, _ in cloud.calls] == ['projects/read', 'projects/collaboration/read']


@pytest.mark.parametrize('change', ['running', 'public', 'dedicated', 'extra'])
def test_current_access_contradictions_still_refuse_before_any_lock_or_source_write(cloud, change):
    fixtures.base.test_strict_access_unchanged_before_any_edit(cloud, change)


@pytest.mark.parametrize('field,value', [('backtestId', 'wrong'), ('name', 'wrong'),
    ('compileId', 'wrong'), ('status', 'Completed.')])
def test_current_a16_history_unchanged_before_lock(cloud, field, value):
    fixtures.test_a16_prior_history_is_exact_before_any_lock_or_write(cloud, field, value)


def test_no_invented_a17_history_is_filtered_or_accepted(cloud):
    def extra(endpoint, payload, value):
        if endpoint == 'backtests/list':
            value['backtests'].append({'projectId': m.PROJECT_ID, 'backtestId': 'invented-a17',
                'name': previous.BACKTEST_NAME, 'status': 'Runtime Error'})
            value['count'] += 1
    cloud.mutation = extra
    with pytest.raises(ValueError): cloud.runner.prepare_once()
    assert [endpoint for endpoint, _ in cloud.calls] == [
        'projects/read', 'projects/collaboration/read', 'backtests/list']


@pytest.mark.parametrize('change', ['main', 'runtime', 'unknown_file', 'missing', 'duplicate', 'project', 'after_lock'])
def test_existing_quote_source_drift_remains_a_refusal(cloud, change):
    fixtures.base.test_initial_source_is_exact_a14_not_plain_a11_or_partial_recovery(cloud, change)


def test_capacity_wait_preserves_other_jobs_and_never_launches(cloud):
    fixtures.base.test_capacity_wait_does_not_cancel_or_launch_other_jobs(cloud)


def test_compile_failure_has_no_backtest_or_error_detail_read(cloud):
    fixtures.base.test_compile_failure_terminal_blocks_every_launch(cloud)


def test_error_detail_selected_boundary_and_shared_read_budget_unchanged(cloud):
    fixtures.test_error_only_selection_keeps_finite_absence_not_raw_prices_or_statistics(cloud)


def test_remote_still_revalidates_selected_response_pin(cloud):
    fixtures.test_remote_independently_requires_selected_pin(cloud)
