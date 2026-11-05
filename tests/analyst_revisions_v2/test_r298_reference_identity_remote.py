"""A19 exact prior history/new witness boundary; synthetic native-denied only."""
import ast
import copy
from pathlib import Path

import pytest

from scripts import arv2_r298_reference_identity_remote as m
from scripts import arv2_r298_raw_reference_diagnostic_a18_remote as frozen
from tests.analyst_revisions_v2 import test_r298_raw_reference_diagnostic_a18_remote as base
from tests.analyst_revisions_v2 import test_raw_reference_diagnostic_projection as public_base


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setattr(base, 'm', m)
    state = base.cloud.__wrapped__(monkeypatch)
    original = state.runner._request
    state.a18 = {'projectId': m.PROJECT_ID, 'backtestId': m.A18_ID, 'name': m.A18_NAME,
        'compileId': m.A18_COMPILE_ID, 'status': 'Runtime Error'}
    def request(endpoint, payload):
        value = original(endpoint, payload)
        if endpoint == 'backtests/list':
            value['backtests'].insert(4, copy.deepcopy(state.a18))
            value['count'] += 1
        return value
    state.runner._request = request
    return state


def test_exact_new_identity_old_diagnostic_cloud_and_false_flags():
    assert m.ATTEMPT == 19 and m.SCHEMA == 'arv2-r298-reference-identity-diagnostic-a19-v1'
    assert m.BACKTEST_NAME == 'ARV2 R298 REFERENCE IDENTITY DIAGNOSTIC R323 A19'
    assert m.A18_ID == '78ba7a236450cdeffea5efe07d087637'
    assert m.A18_COMPILE_ID == 'ed8233767e663d42a2ea3c9d5590d8f5-e3908e134c5314de5875830686db3b0b'
    assert m.OLD_PROJECTION_SHA256 == frozen.PROJECTION_SHA256
    assert m.OLD_SOURCE_MANIFEST_SHA256 == frozen.SOURCE_MANIFEST_SHA256
    assert m.EDIT_NAMES == ('newrule_legacy_primitives.py', 'main.py')
    assert m._binding()['diagnostic_only'] is True
    assert m.profile_record()['extra_history_probe_calls'] == 0
    assert m.profile_record()['private_identity_witness_only'] is True
    assert m.profile_record()['whole_backtest_response_authenticated'] is False


def test_all_unrelated_function_and_class_methods_remain_ast_identical():
    excluded_top = {'profile_record', 'validate_compile_receipt', 'validate_launch_receipt'}
    def selected(path):
        tree = ast.parse(path.read_bytes())
        values = {node.name: ast.dump(node, include_attributes=False) for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name not in excluded_top}
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'QuoteDiagnostic')
        values.update({'QuoteDiagnostic.' + node.name: ast.dump(node, include_attributes=False)
            for node in cls.body if isinstance(node, ast.FunctionDef) and node.name != '_history'})
        return values
    assert m.sha((ROOT / 'scripts/arv2_r298_raw_reference_diagnostic_a18_remote.py').read_bytes()) == (
        '8553ac2b4819cb13948e1c4358bb4cf1dfd26c46427eeaced0931643f04adc30')
    assert selected(ROOT / 'scripts/arv2_r298_reference_identity_remote.py') == selected(
        ROOT / 'scripts/arv2_r298_raw_reference_diagnostic_a18_remote.py')


def test_actual_public_witness_projection_constructor_never_dispatches():
    before = public_base.public.__wrapped__()
    patcher = (ROOT / 'scripts/arv2_newrule_reference_identity_projection.py').read_bytes()
    public = m.projection.public_specification(before.projected.source_pairs,
        patcher_source_bytes=patcher, expected_patcher_sha256=m.sha(patcher))
    def forbidden(*args, **kwargs):
        pytest.fail('pure public constructor dispatched')
    instance = m.QuoteDiagnostic(public.record_bytes, public.source_pairs,
        request=forbidden, journal=forbidden)
    assert public.projection_sha256 == m.PROJECTION_SHA256
    assert instance.compile_receipt is instance.launch_receipt is instance.terminal_receipt is None


def test_exact_lifecycle_adds_only_a19_to_five_prior_rows_and_zero_result_cells(cloud):
    base.fixtures.launch(cloud)
    assert cloud.files == cloud.sources
    assert sum(endpoint == 'compile/create' for endpoint, _ in cloud.calls) == 1
    assert sum(endpoint == 'backtests/create' for endpoint, _ in cloud.calls) == 1
    assert [payload['name'] for endpoint, payload in cloud.calls if endpoint == 'files/update'] == list(m.EDIT_NAMES)
    cloud.own['status'] = 'Completed.'
    cloud.runner.poll_status(0)
    result = cloud.runner.read_once()
    m.validate_result_receipt(result)
    assert result['attempt'] == 19 and result['result_cell'] == 0
    assert result['diagnostic_only'] is True and result['family_comparable'] is False
    for method in (cloud.runner.prepare_once, cloud.runner.launch_once,
        cloud.runner.read_once, cloud.runner.read_failure_once):
        with pytest.raises(ValueError): method()


@pytest.mark.parametrize('field,value', [('backtestId', 'wrong'), ('name', 'wrong'),
    ('compileId', 'wrong'), ('status', 'Completed.')])
def test_a18_exact_prior_binding_refuses_before_lock_or_write(cloud, field, value):
    cloud.a18[field] = value
    with pytest.raises(ValueError): cloud.runner.prepare_once()
    assert [endpoint for endpoint, _ in cloud.calls] == [
        'projects/read', 'projects/collaboration/read', 'backtests/list']


def test_no_invented_a17_history_is_ignored(cloud):
    base.test_no_invented_a17_history_is_filtered_or_accepted(cloud)


@pytest.mark.parametrize('field,value', [('uid', 999), ('name', 'Mia-other'),
    ('publicId', 'mia-ai'), ('permission', 'read'), ('owner', True), ('email', 'changed')])
def test_current_mia_row_drift_remains_prewrite_refusal(cloud, field, value):
    base.test_new_mia_representation_drift_refuses_before_history_lock_or_source_write(cloud, field, value)


def test_dedicated_mia_is_never_filtered(cloud):
    base.test_pinned_mia_is_never_removed_from_dedicated_collaborator_view(cloud)


@pytest.mark.parametrize('change', ['running', 'public', 'dedicated', 'extra'])
def test_access_contradictions_remain_strict(cloud, change):
    base.test_current_access_contradictions_still_refuse_before_any_lock_or_source_write(cloud, change)


@pytest.mark.parametrize('change', ['main', 'runtime', 'unknown_file', 'missing', 'duplicate', 'project', 'after_lock'])
def test_current_diagnostic_source_drift_refuses(cloud, change):
    base.test_existing_quote_source_drift_remains_a_refusal(cloud, change)


def test_capacity_wait_does_not_touch_other_jobs(cloud):
    base.test_capacity_wait_preserves_other_jobs_and_never_launches(cloud)


def test_compile_failure_never_launches_or_reads_error_detail(cloud):
    base.test_compile_failure_has_no_backtest_or_error_detail_read(cloud)


def test_finite_error_only_and_one_shared_read_budget(cloud):
    base.test_error_detail_selected_boundary_and_shared_read_budget_unchanged(cloud)


def test_independent_selected_pin_validation_remains(cloud):
    base.test_remote_still_revalidates_selected_response_pin(cloud)
