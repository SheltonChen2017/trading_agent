"""N one-use caller; synthetic source/output/native-isolation checks only."""
import copy
import re
import sys
import time

import pytest

from scripts import run_arv2_r298_reference_feed as m
from scripts import arv2_r298_reference_feed_remote as remote
from tests.analyst_revisions_v2 import test_r298_quote_diagnostic_caller as base
from tests.analyst_revisions_v2 import test_r298_reference_feed_remote as remote_tests
from tests.analyst_revisions_v2._post_merge_pins import current_pin


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(base, 'm', m)
    monkeypatch.setattr(base, 'remote', remote)
    def forbidden(*a, **k): raise AssertionError('private or spent operational fallback')
    for module, names in ((m.prior, ('main', 'run', 'observe', 'worker', 'run_worker')),
        (m.access_context, ('main', 'run', 'observe')),
        (m.admitted, ('main', '_execute', '_recover', '_worker', 'authenticate_storage')),
        (m.admitted.prep, ('main', 'construct')), (m.admission, ('admit',))):
        for name in names: monkeypatch.setattr(module, name, forbidden)


args = base.args
control = base.control
cloud = remote_tests.cloud
@pytest.fixture
def workflow(control, args, monkeypatch):
    value = base.workflow.__wrapped__(control, args, monkeypatch)
    monkeypatch.setattr(value.Runner, 'result_observation', None, raising=False)
    return value


def test_exact_n_scope_and_frozen_dependencies():
    assert m.SCHEMA == remote.SCHEMA == 'arv2-r298-reference-feed-n-v1'
    assert m.CONTROL.name == 'R323-20261025-N'
    record = m.profile_record()
    assert record['attempt'] == 'N' and record['source_uploads'] == 2
    assert record['lock_mutations'] == record['strategy_results'] == record['result_cell'] == record['orders'] == 0
    assert record['new_compiles'] == record['max_launches'] == 1
    assert record['new_shared_look_if_launched'] == record['new_infrastructure_look_if_launched'] == 1
    assert record['historical_cause_authenticated'] is False
    assert m.MAX_DISPATCHES == 160 and m.MAX_FILES == 1024 and m.DEADLINE_SECONDS == 1200
    assert 'assistant.dispatch_fence' not in sys.modules


def test_all_selected_source_pins_current_public_and_literal():
    values = m.pins()
    assert len(values) > 100
    for name, pin in values.items():
        assert re.fullmatch('[a-f0-9]{64}', pin) and pin != '0' * 64
        assert m.sha((m.ROOT / name).read_bytes()) == current_pin(name, pin)
    assert m.PATCHER_SHA256 == values['scripts/arv2_r298_reference_feed_projection.py']


def test_native_scope_denies_every_spent_consumer_including_m():
    native = m.native_profile()
    for name in ('newrule_reference_identity/R323-20261025-J', 'newrule_reference_error/R323-20261025-K',
        'newrule_reference_error/R323-20261025-L', 'newrule_reference_ticker/R323-20261025-M'):
        assert name in native
    assert '(deny network*)' in native and 'Library/Keychains' in native


def test_store_is_exclusive_and_exact(control):
    base.test_store_claim_is_exclusive_canonical_and_held_named(control)


@pytest.mark.parametrize('name', ['../escape.json', '/tmp/x.json', 'bad_name.json', 'x.txt'])
def test_store_cannot_escape(control, name):
    base.test_store_rejects_other_paths(control, name)


@pytest.mark.parametrize('mutation', ['mode', 'new', 'replacement', 'inplace'])
def test_store_endpoint_drift(control, mutation):
    base.test_store_detects_endpoint_change(control, mutation)


def test_claim_precedes_native_admission_credentials_and_final_admission(control, args, workflow):
    base.test_workflow_claim_before_admission_before_credentials_and_final_recheck(control, args, workflow)


def test_compile_failure_never_launches(control, args, workflow, monkeypatch):
    base.test_compile_failure_has_no_capacity_launch_or_aggregate(control, args, workflow, monkeypatch)


def test_compile_budget_not_retry(control, args, workflow, monkeypatch):
    monkeypatch.setattr(workflow.Runner, 'poll_compile', lambda self, index: {**self.compile_receipt, 'state': 'Building'})
    result = m.run(args, time.monotonic() + 500)
    assert result['failure']['failure_code'] == 'compile_budget'
    assert workflow.events.count('prepare') == 1 and workflow.events.count(('sleep', 1)) == 60
    assert 'launch' not in workflow.events


def test_runtime_failure_has_one_detail_read(control, args, workflow, monkeypatch):
    base.test_runtime_failure_reads_only_error_detail_without_restart(control, args, workflow, monkeypatch)


def test_final_admission_change_refuses_report(control, args, workflow, monkeypatch):
    original = m.run_worker
    def drift(args, store, deadline, index):
        value = original(args, store, deadline, index)
        if index == 1: value['drift'] = True
        return value
    monkeypatch.setattr(m, 'run_worker', drift)
    outcome = m.run(args, time.monotonic() + 500)
    assert outcome['failure']['failure_code'] == 'admission_changed'
    assert not (control / 'report.json').exists()


def test_foreign_access_refusal_uses_new_closed_inventory():
    for code in m.access.FINITE_CODES:
        error = m.access.AccessRefused(code)
        assert m.finite(error) == 'access_' + code
        assert m._finite_code(m.finite(error))
    assert m.finite(RuntimeError('secret raw text')) == 'unknown_exception'


@pytest.mark.parametrize('actual', [False, None, 0])
def test_failed_output_never_accepted_without_actual_two(args, actual):
    value = {'binding': m.binding(args), 'preflight_failure': 'source_pin'}
    with pytest.raises(ValueError): m.validate_output(m.canonical(value), actual, args)


def test_failed_output_authenticates_finite_code_only(args):
    value = {'binding': m.binding(args), 'preflight_failure': 'source_pin'}
    assert m.validate_output(m.canonical(value), 2, args) == value
    value['preflight_failure'] = 'secret arbitrary data'
    with pytest.raises(ValueError): m.validate_output(m.canonical(value), 2, args)


def test_deadline_refuses_before_any_work():
    with pytest.raises(ValueError): m.remaining(time.monotonic() - 1)
    with pytest.raises(ValueError): m.remaining(float('nan'))


@pytest.mark.parametrize('kind', ['capacity_wait', 'compile_error', 'runtime_error'])
def test_exact_report_pin_and_actual_exit(args, kind):
    value = base.result_output(args, kind)
    actual = 2 if kind in ('compile_error', 'runtime_error') else 0
    assert m.validate_output(m.canonical(value), actual, args) == value
    bad = copy.deepcopy(value); bad['outcome']['report']['sha256'] = '0' * 64
    with pytest.raises(ValueError): m.validate_output(m.canonical(bad), actual, args)
    with pytest.raises(ValueError): m.validate_output(m.canonical(value), 2 - actual, args)


@pytest.mark.parametrize('field', ['backtestId', 'projectId'])
def test_read_binding_cannot_route_another_job(args, field):
    launch = base.launched()
    state = {'stage': 'result', 'launch': launch, 'terminal': base.terminal('Completed.')}
    payload = {'projectId': remote.PROJECT_ID, 'backtestId': launch['backtest_id']}
    assert m._read_binding(state, payload)['mode'] == 'completed'
    payload[field] = True if field == 'projectId' else 'other'
    with pytest.raises(ValueError): m._read_binding(state, payload)


def test_selected_metadata_no_whole_object_hash():
    class Secret:
        def __repr__(self): raise AssertionError('ignored value formatted')
    row = {'projectId': remote.PROJECT_ID, 'backtestId': 'new', 'compileId': 'new-compile',
        'name': remote.BACKTEST_NAME, 'status': 'Completed.', 'charts': Secret(),
        'statistics': {remote.projection.META_STATISTIC: '{}', 'Profit': Secret()}}
    selected = m.response_selector.select_response({'success': True, 'backtest': row},
        project_id=remote.PROJECT_ID, backtest_id='new', compile_id='new-compile',
        backtest_name=remote.BACKTEST_NAME, mode='completed')
    assert selected['whole_response_authenticated'] is False
    assert 'Profit' not in m.canonical(selected).decode()


def test_partial_validated_metadata_is_failure_only_and_exact_bound(args, cloud, monkeypatch):
    for name in ('PROJECTION_SHA256', 'PROFILE_SHA256', 'SOURCE_MANIFEST_SHA256'):
        monkeypatch.setattr(m, name, getattr(remote, name))
    cloud.create_status = 'Completed.'; remote_tests.launch(cloud)
    cloud.detail_mutation = lambda value: setattr(cloud, 'busy', True)
    with pytest.raises(remote.access.AccessRefused): cloud.runner.read_once()
    state = {'stage': 'result', 'dispatch_count': 1, 'response_count': 1,
        'last_endpoint': 'backtests/read', 'last_response_received': True,
        'compiled': cloud.runner.compile_receipt, 'launch': cloud.runner.launch_receipt,
        'terminal': cloud.runner.terminal_receipt, 'observation': cloud.runner.result_observation}
    failed = {'failure_code': 'access_idle', 'state': state, 'provider_request_count': None,
        'attempt_consumption': 'consumed_or_ambiguous_no_retry', **m.FALSE_FLAGS}
    envelope = {'binding': m.binding(args), 'outcome': {'failure': failed}}
    assert m.validate_output(m.canonical(envelope), 2, args) == envelope
    with pytest.raises(ValueError): m.validate_output(m.canonical(envelope), 0, args)
    bad = copy.deepcopy(envelope)
    bad['outcome']['failure']['state']['observation']['post_checks_complete'] = True
    with pytest.raises(ValueError): m.validate_output(m.canonical(bad), 2, args)
