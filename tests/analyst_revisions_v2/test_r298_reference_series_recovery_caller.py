"""R recovery caller; synthetic source/output/native-isolation checks only."""
import copy
import ast
import os
import re
import sys
import time

import pytest

from scripts import run_arv2_r298_reference_series_recovery as m
from scripts import arv2_r298_reference_series_recovery_remote as remote
from tests.analyst_revisions_v2 import test_r298_quote_diagnostic_caller as base
from tests.analyst_revisions_v2 import test_r298_reference_series_recovery_remote as remote_tests


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(base, 'm', m)
    monkeypatch.setattr(base, 'remote', remote)
    # The old synthetic workflow's client seam lives behind this test-only
    # alias; the new production wrapper intentionally exports no client path.
    monkeypatch.setattr(remote, 'previous', remote.frozen.previous, raising=False)
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
    monkeypatch.setattr(value.Runner, 'partial_observation', None, raising=False)
    monkeypatch.setattr(value.Runner, 'expected_profile', {}, raising=False)
    return value


def test_exact_n_scope_and_frozen_dependencies():
    assert m.SCHEMA == 'arv2-r298-reference-series-recovery-r-v1' and remote.SCHEMA == 'arv2-r298-reference-series-phase-p-v1'
    assert m.CONTROL.name == 'R323-20261025-R'
    record = m.profile_record()
    assert record['attempt'] == 'R' and record['source_uploads'] == 2
    assert record['lock_mutations'] == record['strategy_results'] == record['result_cell'] == record['orders'] == 0
    assert record['new_compiles'] == record['max_launches'] == 1
    assert record['new_shared_look_if_launched'] == record['new_infrastructure_look_if_launched'] == 1
    assert record['historical_cause_authenticated'] is False
    assert record['scientific_experiment'] == 'P' and record['scientific_attempt'] == 2
    assert record['scientific_source_changed'] is False and record['maximum_scientific_attempts'] == 3
    assert record['q_observation_documentary_only'] is True and record['q_observation_is_access_authority'] is False
    assert record['strict_access_source_sha256'] == '57333e2d6932f3b75bb42bc59214ebda2ce9afdf65b9054b7edc7ee5cbd37d93'
    assert m.MAX_DISPATCHES == 160 and m.MAX_FILES == 1024 and m.DEADLINE_SECONDS == 1200
    assert 'assistant.dispatch_fence' not in sys.modules


def test_all_selected_source_pins_current_public_and_literal():
    values = m.pins()
    assert len(values) > 100
    for name, pin in values.items():
        assert re.fullmatch('[a-f0-9]{64}', pin) and pin != '0' * 64
        assert m.sha((m.ROOT / name).read_bytes()) == pin
    assert m.PATCHER_SHA256 == values['scripts/arv2_r298_reference_series_phase_projection.py']


def test_native_scope_denies_every_spent_consumer_including_m():
    native = m.native_profile()
    for name in ('newrule_reference_identity/R323-20261025-J', 'newrule_reference_error/R323-20261025-K',
        'newrule_reference_error/R323-20261025-L', 'newrule_reference_ticker/R323-20261025-M',
        'newrule_reference_feed/R323-20261025-N', 'newrule_sharadar_reference/R323-20261025-O',
        'newrule_reference_series_phase/R323-20261025-P', 'newrule_post_phase_access/R323-20261025-Q'):
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


def test_genuine_completed_metadata_still_requires_actual_parent_zero(args, monkeypatch):
    public = remote_tests.public_tests.public.__wrapped__()
    runtime = remote_tests.public_tests.runtime.__wrapped__()
    state = remote_tests.public_tests.initialized(runtime, public, monkeypatch)
    state.value.initialize()
    state.value.on_data(remote_tests.public_tests.clock(state))
    metadata = remote_tests.public_tests.bound_result(state)
    compiled = {**remote._binding(), 'compile_id': 'p-genuine-compile'}
    launch = {**compiled, 'backtest_id': 'p-genuine-job', 'backtest_name': remote.BACKTEST_NAME}
    receipt = {**launch, 'status': 'Completed.', 'observation_completed': True,
        'family_comparable': False, 'result_cell': 0, 'metadata': metadata,
        'expected_profile': public.profile}
    result = {'terminal': 'completed', 'application_dispatch_count': 47,
        'compiled': compiled, 'launch': launch, 'result': receipt, **m.FALSE_FLAGS}
    report = m.canonical({**m.binding(args), 'result': result})
    envelope = {'binding': m.binding(args), 'outcome': {'result': result,
        'report': {'byte_count': len(report), 'sha256': m.sha(report)}}}
    raw = m.canonical(envelope)
    assert m.validate_output(raw, 0, args) == envelope
    for actual in (2, False, None):
        with pytest.raises(ValueError):
            m.validate_output(raw, actual, args)


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
        'terminal': cloud.runner.terminal_receipt, 'observation': cloud.runner.result_observation,
        'partial_observation': None}
    failed = {'failure_code': 'access_idle', 'state': state, 'provider_request_count': None,
        'attempt_consumption': 'consumed_or_ambiguous_no_retry', **m.FALSE_FLAGS}
    envelope = {'binding': m.binding(args), 'outcome': {'failure': failed}}
    assert m.validate_output(m.canonical(envelope), 2, args) == envelope
    with pytest.raises(ValueError): m.validate_output(m.canonical(envelope), 0, args)
    bad = copy.deepcopy(envelope)
    bad['outcome']['failure']['state']['observation']['post_checks_complete'] = True
    with pytest.raises(ValueError): m.validate_output(m.canonical(bad), 2, args)


def test_runtime_error_partial_observation_never_success_or_other_job(args, cloud, monkeypatch):
    for name in ('PROJECTION_SHA256', 'PROFILE_SHA256', 'SOURCE_MANIFEST_SHA256'):
        monkeypatch.setattr(m, name, getattr(remote, name))
    remote_tests.launch(cloud); cloud.own['status'] = 'Runtime Error'; cloud.runner.poll_status(0)
    cloud.meta['diagnostic_complete'] = False
    cloud.runner.read_failure_once()
    result = {'terminal': 'runtime_error', 'application_dispatch_count': len(cloud.calls),
        'compiled': cloud.runner.compile_receipt, 'launch': cloud.runner.launch_receipt,
        'result': cloud.runner.terminal_receipt, 'partial_observation': cloud.runner.partial_observation,
        **m.FALSE_FLAGS}
    def envelope(result):
        report = m.canonical({**m.binding(args), 'result': result})
        return {'binding': m.binding(args), 'outcome': {'result': result,
            'report': {'byte_count': len(report), 'sha256': m.sha(report)}}}
    value = envelope(result)
    assert m.validate_output(m.canonical(value), 2, args) == value
    with pytest.raises(ValueError): m.validate_output(m.canonical(value), 0, args)
    bad = copy.deepcopy(result); bad['partial_observation']['admissible_result'] = True
    with pytest.raises(ValueError): m.validate_output(m.canonical(envelope(bad)), 2, args)


def synthetic_worker(monkeypatch, args):
    for key in ('QC_USER_ID', 'QC_API_TOKEN', 'SHARADAR_API_KEY', 'MASSIVE_API_KEY',
        'POLYGON_API_KEY', 'EODHD_API_TOKEN', 'FMP_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    packet = {'admission_authenticated': True, 'readiness_pin': {}, 'storage_receipt': {},
        'projection_record': '{}', 'source_pairs': []}
    monkeypatch.setattr(m.admission, 'admit', lambda deadline: {'readiness_pin': {}, 'storage_receipt': {}})
    monkeypatch.setattr(m.projection, 'build_projection', lambda *a, **k:
        type('Projected', (), {'record_bytes': b'{}', 'source_pairs': ()})())
    monkeypatch.setattr(m, 'validate_packet', lambda value: value)
    monkeypatch.setattr(m, 'preflight', lambda *a: None)
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    return packet


def test_real_own_worker_fd_start_and_parent_adoption_prevent_replay(control, args, monkeypatch):
    packet = synthetic_worker(monkeypatch, args)
    def capture(command, env, timeout, **kwargs):
        assert kwargs['pass_fds'] == (store.fd,) and timeout <= 120
        assert not {'QC_USER_ID', 'QC_API_TOKEN'} & set(env)
        args.control_fd, args.worker_index = store.fd, 0
        result = m.worker(args, time.monotonic() + 30)
        return m.canonical({'binding': m.binding(args), 'packet': result}), b'', {'actual_exit': 0, 'bound': None}
    monkeypatch.setattr(m, 'capture', capture)
    with m.Store() as store:
        store.write('claim.json', {**m.binding(args), 'attempt': 'R', 'old_attempts_spent': True})
        assert m.run_worker(args, store, time.monotonic() + 100, 0) == packet
        assert 'worker-0-started.json' in store.files
        store.verify()
        with pytest.raises(FileExistsError): m.worker(args, time.monotonic() + 30)
        with pytest.raises(ValueError): m.run_worker(args, store, time.monotonic() + 30, 0)


@pytest.mark.parametrize('which', ['missing_claim', 'claim_binding', 'claim_bool', 'intent_bool', 'intent_binding'])
def test_worker_authenticates_claim_and_typed_intent_before_private_reads(control, args, monkeypatch, which):
    synthetic_worker(monkeypatch, args)
    with m.Store() as store:
        if which != 'missing_claim':
            claim = {**m.binding(args), 'attempt': 'R', 'old_attempts_spent': True}
            if which == 'claim_binding': claim['expected_head'] = '0' * 40
            elif which == 'claim_bool': claim['old_attempts_spent'] = 1
            store.write('claim.json', claim)
        intent = {'binding': m.binding(args), 'worker_index': 0}
        if which == 'intent_bool': intent['worker_index'] = False
        elif which == 'intent_binding': intent['binding']['expected_head'] = '0' * 40
        store.write('worker-0-intent.json', intent)
        args.control_fd, args.worker_index = store.fd, 0
        monkeypatch.setattr(m.admission, 'admit', lambda *a: pytest.fail('private admission before claim/intent'))
        with pytest.raises((ValueError, FileNotFoundError)): m.worker(args, time.monotonic() + 30)
        assert not (control / 'worker-0-started.json').exists()


@pytest.mark.parametrize('actual', [0, 2, False, None])
def test_worker_actual_exit_and_exclusive_marker_both_required(control, args, monkeypatch, actual):
    packet = synthetic_worker(monkeypatch, args)
    monkeypatch.setattr(m, 'capture', lambda *a, **k: (m.canonical({'binding': m.binding(args), 'packet': packet}),
        b'', {'actual_exit': actual, 'bound': None}))
    with m.Store() as store:
        with pytest.raises(ValueError): m.run_worker(args, store, time.monotonic() + 30, 0)


def test_native_start_marker_cannot_extend_write_scope():
    profile = m.native_profile()
    assert '(require-not (subpath "' + str(m.CONTROL) + '"))' in profile
    assert '(require-not (subpath "' + str(m.CONTROL) + '"))' not in m.native_profile(artifacts=True)


def test_pin_union_refuses_conflict(monkeypatch):
    names = m.access_context.pins()
    name = next(iter(names))
    monkeypatch.setitem(m.NEW_PINS, name, '0' * 64)
    with pytest.raises(ValueError): m.pins()


def test_all_nonidentity_parent_protocol_methods_equal_frozen_P():
    from scripts import run_arv2_r298_reference_series_phase as frozen
    names = {'remaining', 'binding', 'preflight', 'Store', 'validate_packet', '_read_json', 'worker',
        'run_worker', '_read_binding', 'run', '_state', '_partial_matches_terminal', 'validate_output', 'observe', 'main'}
    def selected(raw, recovery=False):
        tree = ast.parse(raw)
        if recovery:
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and type(node.value) is str:
                    node.value = {'R': 'P', 'r323-r-worker-': 'r323-p-worker-',
                        'r323-r-observer-': 'r323-p-observer-'}.get(node.value, node.value)
        return {node.name: ast.dump(node, include_attributes=False) for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names}
    assert selected(m.SOURCE.read_bytes(), True) == selected(frozen.SOURCE.read_bytes())
    assert set(selected(m.SOURCE.read_bytes())) == names
