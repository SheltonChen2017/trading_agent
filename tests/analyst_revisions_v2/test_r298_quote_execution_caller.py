"""A15 caller regressions and exact inherited-protocol parity, all synthetic."""
import ast
import copy
import inspect
import re
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_r298_quote_execution as m
from scripts import run_arv2_r298_quote_diagnostic as frozen
from scripts import run_arv2_r298_quote_diagnostic_a14 as a14
from scripts import arv2_r298_quote_execution_remote as remote
from tests.analyst_revisions_v2 import test_r298_quote_diagnostic_caller as inherited


@pytest.fixture(autouse=True)
def no_old_operational_entrypoints(monkeypatch):
    monkeypatch.setattr(inherited, 'm', m)
    monkeypatch.setattr(inherited, 'remote', remote)
    def refuse(*_, **__): raise AssertionError('old operational fallback')
    for module, names in ((frozen, ('main', 'run', 'observe', 'worker', 'run_worker')),
        (a14, ('main', 'run', 'observe', 'worker', 'run_worker')),
        (m.prior, ('main', 'run', 'observe', 'worker', 'run_worker')),
        (m.admitted, ('main', '_execute', '_recover', '_worker', 'authenticate_storage')),
        (m.admitted.prep, ('main', 'construct')), (m.admission, ('admit',))):
        for name in names: monkeypatch.setattr(module, name, refuse)


args = inherited.args
control = inherited.control
packet = inherited.packet
workflow = inherited.workflow


@pytest.fixture(scope='module')
def projected():
    public = inherited.projection_fixtures.public.__wrapped__()
    raw = m.ROOT.joinpath('scripts', m.projection.PATCHER_NAME).read_bytes()
    return m.projection.public_specification(public.pairs,
        patcher_source_bytes=raw, expected_patcher_sha256=m.sha(raw))


def test_new_immutable_identity_and_documentary_positive_observation_only():
    assert m.CONTROL.name == 'R323-20261025-E' and m.CONTROL not in (a14.CONTROL, frozen.CONTROL, m.prior.CONTROL)
    assert m.SCHEMA == 'arv2-r298-quote-execution-a15-v1'
    assert m.NEW_PINS['scripts/run_arv2_r298_quote_diagnostic.py'] == '770ce5b92fcd46e862a40a763b492d6561b55a82b4e244242a900eda71509257'
    assert m.NEW_PINS['scripts/arv2_r298_quote_diagnostic_remote.py'] == 'bed3653baeeeb5c1338127832ccd51af4587d957d733e18cdde33a11ef27c6e0'
    record = m.profile_record()
    assert record['attempt'] == 15 and record['max_launches'] == record['new_compiles'] == 1
    assert record['source_uploads'] == 2 and record['max_dispatches'] == 420 and m.MAX_FILES == 1024
    assert record['access_observation_actual_exit'] == 0 and record['access_observation_report_bytes'] == 3612
    assert record['access_observation_report_sha256'] == '625111ca3458ec173c0c9f1dfcbab70222a27bec23bd1b56342fc23488830a6f'
    assert record['access_observation_control_read'] is False and record['historical_a13_cause_known'] is False
    assert record['fresh_access_before_mutation'] is record['execution_semantics_changed'] is True
    assert record['diagnostic_not_family_cell'] is False
    assert record['a14_actual_exit'] == 2 and record['a14_report_bytes'] == 3256
    assert record['a14_report_sha256'] == 'c8d14b163bc214f78ed912271035deac88bbb9e6bd1cd7583d7d502151ffd5fe'
    assert record['a14_report_documentary_only'] is True and record['a14_control_read'] is False
    assert record['execution_price_basis'] == 'buy_ask_sell_bid_current_non_fill_forward_quote'
    assert record['fee_and_fill_price_basis_match_required'] is True
    assert record['execution_policy'] == 'arv2-newrule-quote-aware-execution-v1'
    assert record['execution_policy_record_sha256'] == m.sha(m.canonical(m.projection.policy_record()))
    assert record['accepted_risk_only'] is record['common_new_runtime_family_reconstruction_required'] is True
    assert record['family_comparable'] is False
    assert 'assistant.dispatch_fence' not in sys.modules


def test_selected_public_source_pins_are_literal_current_and_remote_bound():
    values = m.pins()
    assert set(m.NEW_PINS) <= set(values)
    assert len(values) > 100
    for name, pin in values.items():
        assert type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin) and pin != '0' * 64
        assert m.sha(m.ROOT.joinpath(name).read_bytes()) == pin
    assert m.PATCHER_SHA256 == m.NEW_PINS['scripts/arv2_newrule_quote_execution_projection.py']
    assert m._remote() is remote


def test_core_store_worker_admission_and_projection_are_ast_identical_to_frozen_a13():
    old = ast.parse(m.ROOT.joinpath('scripts/run_arv2_r298_quote_diagnostic.py').read_bytes())
    new = ast.parse(m.SOURCE.read_bytes())
    names = {'Store', 'remaining', 'validate_packet', 'worker', 'run_worker', 'preflight', 'pins'}
    def selected(tree):
        return {node.name: ast.dump(node, include_attributes=False) for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names}
    assert set(selected(old)) == names and selected(old) == selected(new)
    assert m.capture is m.prior.capture and m.credential_shape is m.prior.credential_shape


def test_native_denial_includes_a12_a13_spent_c_and_a14_without_reading_them():
    for artifacts in (False, True):
        value = m.native_profile(artifacts=artifacts)
        assert '(deny network*)' in value and '/usr/bin/security' in value
        assert str(frozen.CONTROL) in value and str(m.prior.CONTROL) in value
        assert str(a14.CONTROL) in value
        assert 'newrule_post_mia_access/R323-20261025-C' in value
        if artifacts: assert str(m.ROOT / 'artifacts') in value


def test_exclusive_claim_and_endpoint_metadata_retained(control):
    inherited.test_store_claim_is_exclusive_canonical_and_held_named(control)


@pytest.mark.parametrize('mutation', ['mode', 'new', 'replacement', 'inplace'])
def test_inherited_held_named_store_refuses_change(control, mutation):
    inherited.test_store_detects_endpoint_change(control, mutation)


def test_public_execution_projection_authenticated_without_old_operational_admission(packet):
    inherited.test_public_packet_binds_native_admission_and_diagnostic_projection(packet)


def test_old_a14_diagnostic_projection_cannot_be_accepted_as_new_execution(packet):
    old = inherited.projection_fixtures.build(inherited.projection_fixtures.public.__wrapped__())
    packet['projection_record'] = old.record_bytes.decode('ascii')
    packet['source_pairs'] = [[name, raw.decode('ascii')] for name, raw in old.source_pairs]
    with pytest.raises((m.Refused, m.projection.Refused)):
        m.validate_packet(packet)


@pytest.mark.parametrize('change', ['extra', 'exit-bool', 'exit', 'report', 'storage', 'source',
    'source-order', 'projection', 'admission', 'tuple', 'opaque'])
def test_public_execution_packet_rejects_tampered_binding_or_source(packet, change):
    inherited.test_public_packet_tampering_refuses(packet, change)


def test_native_worker_freshly_admits_original_packet_then_projects_new_sources(control, packet, projected, args, monkeypatch):
    inherited.test_native_worker_inherits_only_own_fd_and_authenticates_intent(
        control, packet, projected, args, monkeypatch)


@pytest.mark.parametrize('bad', ['wrong-fd', 'wrong-index', 'bool-index', 'missing-intent', 'wrong-binding', 'credentials'])
def test_inherited_worker_intent_before_any_private_source(control, args, monkeypatch, bad):
    inherited.test_worker_refuses_scope_before_private_admission(control, args, monkeypatch, bad)


@pytest.mark.parametrize('actual', [0, 2, True, None])
def test_inherited_native_worker_requires_actual_zero_once(control, args, packet, monkeypatch, actual):
    inherited.test_worker_dispatch_strips_credentials_binds_fd_and_requires_actual_zero(control, args, packet, monkeypatch, actual)


def test_workflow_preserves_claim_and_fresh_final_admission(control, args, workflow):
    inherited.test_workflow_claim_before_admission_before_credentials_and_final_recheck(control, args, workflow)


def test_completed_runtime_with_changed_final_admission_is_failure_not_result(control, args, workflow, monkeypatch):
    original = m.run_worker
    def worker(args, store, deadline, index):
        value = original(args, store, deadline, index)
        if index: value['projection_record'] = '{"changed":true}'
        return value
    monkeypatch.setattr(m, 'run_worker', worker)
    outcome = m.run(args, time.monotonic() + 500)
    assert set(outcome) == {'failure'} and outcome['failure']['failure_code'] == 'admission_changed'
    assert outcome['failure']['state']['stage'] == 'final_admission'
    assert outcome['failure']['state']['terminal']['status'] == 'Completed.'
    assert 'read' in workflow.events and 'worker-1' in workflow.events
    assert not (control / 'report.json').exists()
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 2, args)


def test_compile_error_never_launches_or_reads_result(control, args, workflow, monkeypatch):
    inherited.test_compile_failure_has_no_capacity_launch_or_aggregate(control, args, workflow, monkeypatch)


def test_pending_compile_budget_never_prepares_or_dispatches_twice(control, args, workflow, monkeypatch):
    inherited.test_compile_budget_is_spent_without_repeated_prepare(control, args, workflow, monkeypatch)


def test_capacity_wait_never_becomes_performance_result(control, args, workflow, monkeypatch):
    inherited.test_capacity_wait_is_three_observations_no_job(control, args, workflow, monkeypatch)


def test_capacity_wait_reauthenticates_source_and_head_before_report(control, args, workflow, monkeypatch):
    monkeypatch.setattr(workflow.Runner, 'launch_once', lambda self: {'state': 'wait'})
    def refuse(*_): raise m.Refused('git_state')
    monkeypatch.setattr(m, 'preflight', refuse)
    outcome = m.run(args, time.monotonic() + 500)
    assert outcome['failure']['failure_code'] == 'git_state'
    assert not (control / 'report.json').exists()
    assert 'read' not in workflow.events and 'worker-1' not in workflow.events


def test_runtime_error_has_one_mutually_exclusive_error_read(control, args, workflow, monkeypatch):
    original = workflow.Runner.launch_once
    def create(self):
        value = original(self)
        self.terminal_receipt = inherited.terminal()
        return value
    def detail(self):
        workflow.events.append('failure-detail')
        self.terminal_receipt = {**self.launch_receipt, 'status': 'Runtime Error',
            'failure_evidence': remote.failure_evidence({'error': 'Runtime Error: '
                + m.projection.FAILURE_CODES[0]}, 'runtime_error')}
        return self.terminal_receipt
    monkeypatch.setattr(workflow.Runner, 'launch_once', create)
    monkeypatch.setattr(workflow.Runner, 'read_failure_once', detail)
    outcome = m.run(args, time.monotonic() + 500)
    evidence = outcome['result']['result']['failure_evidence']
    assert outcome['result']['terminal'] == 'runtime_error'
    assert evidence['known_runtime_code'] == m.projection.FAILURE_CODES[0]
    assert evidence['diagnostic_context'] is None
    assert evidence['raw_error_retained'] is evidence['cause_authenticated'] is False
    assert workflow.events.count('failure-detail') == 1 and 'read' not in workflow.events
    envelope = {'binding': m.binding(args), 'outcome': outcome}
    assert m.validate_output(m.canonical(envelope), 2, args) == envelope


def test_failure_after_compile_retains_identity(control, args, workflow, monkeypatch):
    def prepare(self):
        self.compile_receipt = inherited.compiled()
        raise m.Refused('control_write')
    monkeypatch.setattr(workflow.Runner, 'prepare_once', prepare)
    outcome = m.run(args, time.monotonic() + 500)
    assert outcome['failure']['failure_code'] == 'control_write'
    assert outcome['failure']['state']['compiled'] == inherited.compiled()
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 2, args)


def rpc_fixture(monkeypatch, workflow, *, throws_on=None):
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
    api = object.__new__(old.QuantConnectClient)
    api._base_url, api._transport, api._timeout = old.API_BASE, old.coverage._bounded_transport, 30
    calls = []
    def request(endpoint, payload):
        calls.append(endpoint)
        if len(calls) == throws_on: raise RuntimeError('PRIVATE RESPONSE MESSAGE')
        return {'success': True}
    api.request = request
    monkeypatch.setattr(old, '_client', lambda: api)
    def prepare(self):
        self.request('projects/read', {'projectId': 38364439})
        self.request('projects/collaboration/read', {'projectId': 38364439})
        m.access.verify_access({}, {})
        raise AssertionError('expected strict refusal')
    monkeypatch.setattr(workflow.Runner, 'prepare_once', prepare)
    return calls


@pytest.mark.parametrize('code', sorted(m.access.FINITE_CODES))
def test_every_exact_access_refusal_preserved_after_two_successful_responses(control, args, workflow, monkeypatch, code):
    calls = rpc_fixture(monkeypatch, workflow)
    def refuse(*_): raise m.access.AccessRefused(code)
    monkeypatch.setattr(m.access, 'verify_access', refuse)
    outcome = m.run(args, time.monotonic() + 500)
    assert calls == ['projects/read', 'projects/collaboration/read']
    assert outcome['failure']['failure_code'] == 'access_' + code
    state = outcome['failure']['state']
    assert state['dispatch_count'] == state['response_count'] == 2
    assert state['last_endpoint'] == 'projects/collaboration/read' and state['last_response_received'] is True
    assert state['compiled'] is state['launch'] is state['terminal'] is None
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 2, args)


@pytest.mark.parametrize('where', [1, 2])
def test_rpc_exception_does_not_claim_successful_response_or_access_cause(control, args, workflow, monkeypatch, where):
    calls = rpc_fixture(monkeypatch, workflow, throws_on=where)
    outcome = m.run(args, time.monotonic() + 500)
    failed = outcome['failure']; state = failed['state']
    assert len(calls) == state['dispatch_count'] == where and state['response_count'] == where - 1
    assert state['last_response_received'] is False and failed['failure_code'] == 'unknown_exception'
    assert b'PRIVATE' not in m.canonical(outcome)
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 2, args)


def test_exact_foreign_classification_never_formats_args_or_subclasses():
    from research import quantconnect as qc
    class Hostile(m.access.AccessRefused):
        def __str__(self): raise AssertionError('rendered')
    class Value:
        def __str__(self): raise AssertionError('rendered')
    for args in ((), ('PRIVATE',), ('owner', 'PRIVATE'), (Value(),)):
        assert m.finite(m.access.AccessRefused(*args)) == 'access_unknown'
    assert m.finite(Hostile('owner')) == 'unknown_exception'
    assert m.finite(qc.QuantConnectError('PRIVATE')) == 'qc_client_refused'
    assert m.finite(qc.QuantConnectNotConfigured('PRIVATE')) == 'qc_not_configured'
    assert m.finite(m.environment.EnvironmentRefused('PRIVATE')) == 'execution_environment_refused'
    assert m.finite(m.Refused('private_words')) == 'refused'
    assert m.finite(m.projection.Refused('private_words')) == 'launch_unknown'


@pytest.mark.parametrize('code', sorted(m.projection.FINITE))
def test_new_projector_closed_refusals_survive_native_output_validation(args, code):
    known = m.finite(m.projection.Refused(code))
    assert known == 'launch_' + code and m._finite_code(known)
    value = {'binding': m.binding(args), 'preflight_failure': known}
    assert m.validate_output(m.canonical(value), 2, args) == value


@pytest.mark.parametrize('which,code', [('capacity', 'submission_capacity_shape'),
                                      ('history', 'recovery_prior_backtests')])
def test_real_delegated_validator_refusals_are_retained_finitely(control, args, workflow, monkeypatch, which, code):
    assert m.submission is remote.previous.frozen
    assert m.recovery is remote.previous.ready.predecessor
    def prepare(self):
        if which == 'capacity': m.submission._capacity({})
        else: m.recovery._backtest_rows({}, 2, 'prior_backtests')
        pytest.fail('real helper accepted invalid response')
    monkeypatch.setattr(workflow.Runner, 'prepare_once', prepare)
    outcome = m.run(args, time.monotonic() + 500)
    assert outcome['failure']['failure_code'] == code
    assert outcome['failure']['state']['stage'] == 'prepare'
    assert outcome['failure']['state']['dispatch_count'] == 0
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 2, args)


def test_delegated_validator_unknown_args_and_subclasses_never_stringify():
    class Value:
        def __str__(self): raise AssertionError('rendered')
    class SubmissionChild(m.submission.NewruleSubmissionError):
        def __str__(self): raise AssertionError('rendered')
    class RecoveryChild(m.recovery.RecoveryError):
        def __str__(self): raise AssertionError('rendered')
    for args in ((), (Value(),), ('PRIVATE WORDS',), ('capacity_shape', 'PRIVATE')):
        assert m.finite(m.submission.NewruleSubmissionError(*args)) == 'submission_operation_refused'
        assert m.finite(m.recovery.RecoveryError(*args)) == 'recovery_unknown'
    assert m.finite(SubmissionChild('capacity_shape')) == 'unknown_exception'
    assert m.finite(RecoveryChild('prior_backtests')) == 'unknown_exception'
    assert not m._finite_code('submission_private_words') and not m._finite_code('recovery_private_words')


@pytest.mark.parametrize('name,actual', [('capacity_wait', 0), ('compile_error', 2), ('runtime_error', 2)])
def test_actual_exit_and_matching_report_pin_required(args, name, actual):
    inherited.test_output_authenticates_report_pin_and_actual_exit(args, name, actual)


@pytest.mark.parametrize('change', ['pin', 'binding', 'flags', 'count', 'compile', 'launch', 'terminal'])
def test_output_rejects_corrupt_result_or_a12_identity(args, change):
    inherited.test_output_cannot_promote_corrupt_result_metadata(args, change)


def failed_output(args):
    return {'binding': m.binding(args), 'outcome': {'failure': {'failure_code': 'access_idle',
        'state': {'stage': 'prepare', 'dispatch_count': 2, 'response_count': 2,
            'last_endpoint': 'projects/collaboration/read', 'last_response_received': True,
            'compiled': None, 'launch': None, 'terminal': None},
        'provider_request_count': None, 'attempt_consumption': 'consumed_or_ambiguous_no_retry', **m.FALSE_FLAGS}}}


@pytest.mark.parametrize('change', ['code', 'stage', 'bool-count', 'responses', 'endpoint', 'received', 'extra', 'exit', 'compiled'])
def test_output_closed_failure_state_distinguishes_attempt_and_response(args, change):
    value, actual = failed_output(args), 2
    failed = value['outcome']['failure']; state = failed['state']
    if change == 'code': failed['failure_code'] = 'private_words'
    elif change == 'stage': state['stage'] = 'arbitrary'
    elif change == 'bool-count': state['dispatch_count'] = True
    elif change == 'responses': state['response_count'] = 1
    elif change == 'endpoint': state['last_endpoint'] = 'arbitrary'
    elif change == 'received': state['last_response_received'] = 1
    elif change == 'extra': state['raw_response'] = {}
    elif change == 'compiled': state['compiled'] = {'raw': 'PRIVATE'}
    else: actual = 0
    with pytest.raises((m.Refused, remote.Refused)):
        m.validate_output(m.canonical(value), actual, args)


def test_preflight_failure_and_observer_setup_stay_finite(args, monkeypatch):
    inherited.test_output_preclaim_refusal_requires_actual_nonzero(args)
    monkeypatch.setattr(m, 'credential_shape', lambda: (_ for _ in ()).throw(m.Refused('host')))
    monkeypatch.setattr(m, 'capture', lambda *_args, **_kwargs: pytest.fail('must not spawn'))
    value, actual = m.observe(args)
    assert actual == 2 and value['failure_code'] == 'host'
    assert value['parent'] is value['validator'] is None and value['output_authenticated'] is False
