"""A17 synthetic lifecycle and selected-response boundary; native denial required."""
import ast
import copy
import json
from pathlib import Path

import pytest

from scripts import arv2_r298_raw_reference_diagnostic_remote as m
from scripts import arv2_r298_quote_execution_a16_remote as frozen
from tests.analyst_revisions_v2 import test_r298_quote_execution_remote as base
from tests.analyst_revisions_v2 import test_raw_reference_diagnostic_projection as public_tests


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setattr(base, 'm', m)
    monkeypatch.setattr(m.projection, 'POLICY', m.projection.policy_record(), raising=False)
    state = base.cloud.__wrapped__(monkeypatch)
    original = state.request
    state.a16 = {'projectId': m.PROJECT_ID, 'backtestId': m.A16_ID, 'name': m.A16_NAME,
        'compileId': m.A16_COMPILE_ID, 'status': 'Runtime Error'}
    state.raw_mutation = None
    state.selected_mutation = None
    state.selections = []
    def request(endpoint, payload):
        value = original(endpoint, payload)
        if endpoint == 'backtests/list':
            value['backtests'].insert(3, copy.deepcopy(state.a16))
            value['count'] += 1
        if endpoint == 'backtests/read':
            if state.raw_mutation:
                state.raw_mutation(value)
            mode = 'error' if state.runner.terminal_receipt['status'] == 'Runtime Error' else 'completed'
            value = m.response_projection.select_response(value, project_id=m.PROJECT_ID,
                backtest_id=state.own['backtestId'], backtest_name=m.BACKTEST_NAME,
                compile_id=state.compile_id, mode=mode)
            state.selections.append(copy.deepcopy(value))
            if state.selected_mutation:
                state.selected_mutation(value)
        return value
    state.runner._request = request
    return state


def launch(state):
    return base.launch(state)


def test_exact_a17_identity_and_unchanged_quote_parent_scope():
    assert m.ATTEMPT == 17 and m.SCHEMA == 'arv2-r298-raw-reference-diagnostic-a17-v1'
    assert m.BACKTEST_NAME == 'ARV2 R298 RAW REFERENCE DIAGNOSTIC R323 A17'
    assert m.OLD_PROJECTION_SHA256 == frozen.PROJECTION_SHA256
    assert m.OLD_SOURCE_MANIFEST_SHA256 == frozen.SOURCE_MANIFEST_SHA256
    assert m.A16_ID == '65a1d6698d182b11f2f4b60b7e31267b'
    assert m.A16_COMPILE_ID == 'e92504b34a73aa018748ff8c59e1e00f-3eb607058a468d1e6924c729550834a0'
    assert m.EDIT_NAMES == ('newrule_legacy_primitives.py', 'main.py')
    assert m._binding()['diagnostic_only'] is True
    assert m.profile_record()['whole_backtest_response_authenticated'] is False
    assert m.profile_record()['backtest_read_wire_bound_unchanged'] == 16 * 1024 * 1024


def test_unrelated_operational_methods_ast_equal_to_frozen_a16():
    names = {'_access', 'prepare_once', '_files', '_compile_read', 'poll_compile', '_fresh',
        'launch_once', '_accept_created', '_set_terminal', 'poll_status', 'read_failure_once'}
    def methods(path):
        tree = ast.parse(path.read_bytes())
        owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'QuoteDiagnostic')
        return {node.name: ast.dump(node, include_attributes=False) for node in owner.body
            if isinstance(node, ast.FunctionDef) and node.name in names}
    assert methods(ROOT / 'scripts/arv2_r298_raw_reference_diagnostic_remote.py') == methods(
        ROOT / 'scripts/arv2_r298_quote_execution_a16_remote.py')


def test_actual_public_projection_is_received_with_exact_source_and_profile_pins():
    public = public_tests.public.__wrapped__()
    def forbidden(*args, **kwargs):
        pytest.fail('public constructor must not dispatch')
    runner = m.QuoteDiagnostic(public.projected.record_bytes, public.projected.source_pairs,
        request=forbidden, journal=forbidden)
    assert m.sha(public.projected.record_bytes) == m.PROJECTION_SHA256
    assert public.profile['profile_sha256'] == m.PROFILE_SHA256
    assert m.sha(m.canonical(m.QuoteDiagnostic._manifest(dict(public.projected.source_pairs),
        m.PROJECTION_SHA256))) == m.SOURCE_MANIFEST_SHA256
    assert runner.compile_receipt is runner.launch_receipt is runner.terminal_receipt is None


class Ignored:
    def __repr__(self):
        raise AssertionError('ignored subtree formatted')


def test_large_ignored_completed_body_never_reaches_remote_canonicalization(cloud):
    launch(cloud)
    cloud.own['status'] = 'Completed.'
    cloud.runner.poll_status(0)
    def extras(value):
        value['backtest']['charts'] = 'X' * (2 * 1024 * 1024)
        value['backtest']['closedTrades'] = Ignored()
        value['backtest']['statistics']['SECRET EXTRA'] = Ignored()
    cloud.raw_mutation = extras
    result = cloud.runner.read_once()
    assert result['cell_completed'] is True and result['result_cell'] == 0
    assert result['diagnostic_only'] is True and result['family_comparable'] is False
    assert len(m.canonical(cloud.selections[0])) < m.MAX_RESPONSE_BYTES
    assert 'SECRET' not in json.dumps(result)
    assert not any('charts' in str(event) for _, event in cloud.events)
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1
    for method in (cloud.runner.read_once, cloud.runner.read_failure_once):
        with pytest.raises(ValueError):
            method()


def test_error_only_selection_keeps_finite_absence_not_raw_prices_or_statistics(cloud):
    launch(cloud)
    cloud.own['status'] = 'Runtime Error'
    cloud.runner.poll_status(0)
    cloud.detail_error = m.response_projection.RAW_REFERENCE_LITERAL
    cloud.raw_mutation = lambda value: value['backtest'].update(charts='X' * (2 * 1024 * 1024),
        statistics={'SECRET PRICE': 'private'})
    result = cloud.runner.read_failure_once()
    error = result['failure_evidence']
    assert error['known_runtime_code'] == 'raw_reference_census_incomplete'
    assert error['cause_authenticated'] is False and error['raw_error_retained'] is False
    assert cloud.validation == [] and 'SECRET' not in json.dumps(result)
    assert 'no stale-price' not in json.dumps(result)
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1


@pytest.mark.parametrize('field', ['backtestId', 'projectId', 'name', 'compileId', 'status'])
def test_wrong_received_identity_cannot_be_projected_or_admitted(cloud, field):
    launch(cloud)
    cloud.own['status'] = 'Runtime Error'
    cloud.runner.poll_status(0)
    cloud.raw_mutation = lambda value: value['backtest'].__setitem__(field, True if field == 'projectId' else 'wrong')
    with pytest.raises(ValueError):
        cloud.runner.read_failure_once()
    with pytest.raises(ValueError):
        cloud.runner.read_failure_once()
    assert sum(endpoint == 'backtests/read' for endpoint, _ in cloud.calls) == 1


def test_remote_independently_requires_selected_pin(cloud):
    launch(cloud)
    cloud.own['status'] = 'Runtime Error'
    cloud.runner.poll_status(0)
    cloud.selected_mutation = lambda value: value['selection_pin'].__setitem__('sha256', '0' * 64)
    with pytest.raises(ValueError):
        cloud.runner.read_failure_once()
    assert cloud.runner.terminal_receipt['failure_evidence']['known_runtime_code'] is None


@pytest.mark.parametrize('field,value', [('backtestId', 'wrong'), ('name', 'wrong'),
    ('compileId', 'wrong'), ('status', 'Completed.')])
def test_a16_prior_history_is_exact_before_any_lock_or_write(cloud, field, value):
    cloud.a16[field] = value
    with pytest.raises(ValueError):
        cloud.runner.prepare_once()
    assert [endpoint for endpoint, _ in cloud.calls] == ['projects/read', 'projects/collaboration/read', 'backtests/list']


@pytest.mark.parametrize('change', ['running', 'public', 'dedicated', 'extra'])
def test_strict_access_remains_before_mutation(cloud, change):
    base.test_strict_access_unchanged_before_any_edit(cloud, change)


@pytest.mark.parametrize('change', ['main', 'runtime', 'unknown_file', 'missing', 'duplicate', 'project', 'after_lock'])
def test_current_quote_source_refuses_any_drift(cloud, change):
    base.test_initial_source_is_exact_a14_not_plain_a11_or_partial_recovery(cloud, change)


def test_capacity_wait_and_compile_failure_remain_bounded(cloud):
    base.test_capacity_wait_does_not_cancel_or_launch_other_jobs(cloud)


def test_compile_error_has_no_launch_or_error_detail(cloud):
    base.test_compile_failure_terminal_blocks_every_launch(cloud)
