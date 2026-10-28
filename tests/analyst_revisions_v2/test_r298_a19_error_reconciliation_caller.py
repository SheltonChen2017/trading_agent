"""K read-only caller regressions; synthetic fixtures under native denial."""
import ast
import copy
import re
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import run_arv2_r298_a19_error_reconciliation as m
from scripts import run_arv2_r298_reference_identity_diagnostic as previous
from scripts import arv2_r298_a19_error_reconciliation as remote
from tests.analyst_revisions_v2 import test_r298_quote_diagnostic_caller as base
from tests.analyst_revisions_v2 import test_r298_reference_identity_diagnostic_caller as identity_tests
from tests.analyst_revisions_v2._post_merge_pins import current_pin

args, control = base.args, base.control


@pytest.fixture(autouse=True)
def synthetic_boundaries(monkeypatch):
    monkeypatch.setattr(base, 'm', m)
    monkeypatch.setattr(base, 'remote', m.job_source)
    monkeypatch.setattr(identity_tests, 'm', m)
    def forbidden(*_, **__): raise AssertionError('old operation invoked')
    for module, names in ((previous, ('run', 'observe', 'main', 'worker', 'join_worker', 'run_worker')),
        (m.admitted, ('main', '_execute', '_recover', '_worker', 'authenticate_storage')),
        (m.admitted.prep, ('main', 'construct')), (m.admission, ('admit',))):
        for name in names: monkeypatch.setattr(module, name, forbidden)


@pytest.fixture(scope='module')
def projected():
    return identity_tests.projected.__wrapped__()


packet = base.packet


def terminal():
    return {**m.job_source._binding(), 'compile_id': remote.COMPILE_ID,
        'backtest_id': remote.BACKTEST_ID, 'backtest_name': remote.BACKTEST_NAME,
        'status': 'Runtime Error', 'failure_evidence': m.job_source.failure_evidence({}, 'runtime_error')}


def receipt(error=None):
    return {**remote._binding(), 'terminal': terminal() if error is None else error,
        'fixed_source_checks_before': True, 'fixed_source_checks_after': True,
        'access_observation_index': 0, 'error_reads': 1, 'diagnostic_only': True,
        'result_cell': 0, **remote.FALSE_FLAGS}


def test_fixed_read_only_scope_new_control_and_source_closure():
    assert m.CONTROL.name == 'R323-20261025-K' and m.CONTROL != previous.CONTROL
    assert m.SCHEMA == 'arv2-r298-a19-error-reconciliation-v1'
    assert m.MAX_DISPATCHES == 24 and m.DEADLINE_SECONDS == 900
    assert m.MAX_FILES == 128 and m._remote().PAYLOAD_KEYS == m.READ_PAYLOAD_KEYS
    assert all('create' not in key and 'update' not in key and 'lock' not in key and 'nodes' not in key
        for key in m.READ_PAYLOAD_KEYS)
    record = m.profile_record()
    assert record['a19_control_read'] is False and record['a19_prior_error_read_dispatched'] is False
    assert record['new_jobs'] == record['new_compiles'] == record['new_source_writes'] == record['capacity_calls'] == 0
    assert record['private_join_workers'] == 1 and record['private_join_worker_index'] == 2
    assert record['actual_zero_is_error_observation_not_strategy_completion'] is True
    for name, pin in m.pins().items():
        assert re.fullmatch('[0-9a-f]{64}', pin) and m.sha((m.ROOT / name).read_bytes()) == current_pin(name, pin)
    assert 'assistant.dispatch_fence' not in sys.modules


def test_spent_J_and_every_predecessor_control_is_denied_without_reading_it():
    value = m.native_profile()
    assert str(previous.CONTROL) in value and 'R323-20261025-I' in value
    assert 'R323-20261025-H' in value and 'R323-20261025-G' in value
    assert '(deny network*)' in value and '/usr/bin/security' in value
    assert str(m.ROOT / 'artifacts') in m.native_profile(artifacts=True)


def test_immutable_store_and_worker_dispatch_core_match_frozen_A19_exactly():
    names = {'Store', 'preflight', 'remaining', 'validate_packet', 'worker', 'run_worker', '_join_intent',
        '_constructed_matches'}
    def selected(raw):
        return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(raw).body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names}
    assert selected(m.SOURCE.read_bytes()) == selected(previous.SOURCE.read_bytes())


def test_claim_is_exclusive_and_retained(control):
    base.test_store_claim_is_exclusive_canonical_and_held_named(control)


@pytest.mark.parametrize('mutation', ['mode', 'new', 'replacement', 'inplace'])
def test_store_changes_refuse(control, mutation):
    base.test_store_detects_endpoint_change(control, mutation)


@pytest.mark.parametrize('bad', ['wrong-fd', 'wrong-index', 'bool-index', 'missing-intent', 'wrong-binding', 'credentials'])
def test_worker_scope_before_private_admission(control, args, monkeypatch, bad):
    base.test_worker_refuses_scope_before_private_admission(control, args, monkeypatch, bad)


@pytest.mark.parametrize('actual', [0, 2, True, None])
def test_initial_admission_requires_actual_zero_and_own_inherited_FD(control, args, packet, monkeypatch, actual):
    base.test_worker_dispatch_strips_credentials_binds_fd_and_requires_actual_zero(control, args, packet, monkeypatch, actual)


@pytest.mark.parametrize('change', ['extra', 'exit-bool', 'exit', 'report', 'storage', 'source',
    'source-order', 'projection', 'admission', 'tuple', 'opaque'])
def test_public_packet_tampering_refuses(packet, change):
    base.test_public_packet_tampering_refuses(packet, change)


@pytest.fixture
def workflow(control, args, monkeypatch):
    events = []
    public = {'projection_record': '{}', 'source_pairs': []}
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
    api = object.__new__(old.QuantConnectClient)
    api._base_url, api._transport, api._timeout = old.API_BASE, old.coverage._bounded_transport, 30
    def request(endpoint, payload):
        events.append(endpoint)
        if endpoint == 'backtests/read':
            return {'success': True, 'backtest': {'projectId': 38364439, 'backtestId': remote.BACKTEST_ID,
                'name': remote.BACKTEST_NAME, 'compileId': remote.COMPILE_ID, 'status': 'Runtime Error'}}
        return {'success': True}
    api.request = request
    class Runner:
        def __init__(self, record, pairs, *, request, journal):
            self.request, self.journal = request, journal
            self.terminal_receipt = None
            self.busy = 0
            self.post_fail = False
            self.mutate_endpoint = None
        def poll_idle(self, index):
            self.request('projects/read', {'projectId': 38364439})
            self.request('projects/collaboration/read', {'projectId': 38364439})
            return {'state': 'wait' if index < self.busy else 'ready'}
        def read_once(self):
            if self.mutate_endpoint:
                self.request(*self.mutate_endpoint)
                raise AssertionError('mutating request accepted')
            response = self.request('backtests/read', {'projectId': 38364439, 'backtestId': remote.BACKTEST_ID})
            m.response_selector.validate_selected(response, **m._read_binding({'stage': 'observe'},
                {'projectId': 38364439, 'backtestId': remote.BACKTEST_ID}))
            self.terminal_receipt = terminal()
            if self.post_fail: raise remote.Refused('files')
            return receipt(self.terminal_receipt)
    def worker(args, store, deadline, index):
        assert (control / 'claim.json').is_file()
        events.append('worker-' + str(index))
        return copy.deepcopy(public)
    monkeypatch.setattr(m, 'credential_shape', lambda: {})
    monkeypatch.setattr(old, '_client', lambda: api)
    monkeypatch.setattr(m, 'run_worker', worker)
    monkeypatch.setattr(remote, 'ErrorReconciliation', Runner)
    monkeypatch.setattr(m, 'run_join_worker', lambda *_: (_ for _ in ()).throw(m.Refused('join_scope')))
    monkeypatch.setattr(m, 'preflight', lambda *_: events.append('preflight'))
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: None)
    monkeypatch.setattr(m.time, 'sleep', lambda seconds: events.append(('sleep', seconds)))
    return NS(Runner=Runner, events=events, api=api)


def test_read_only_observation_can_actual_zero_but_never_a_strategy_result(control, args, workflow):
    outcome = m.run(args, time.monotonic() + 500)
    result = outcome['result']
    assert result['terminal'] == 'error_observed' and result['postcheck'] == {'passed': True, 'failure_code': None}
    assert result['result_cell'] == 0 and result['strategy_result_accepted'] is False
    assert result['diagnostic_join'] == {'status': 'unavailable', 'failure_code': 'join_scope'}
    assert workflow.events.index('worker-0') < workflow.events.index('backtests/read') < workflow.events.index('worker-1')
    value = m.canonical({'binding': m.binding(args), 'outcome': outcome})
    assert m.validate_output(value, 0, args)
    with pytest.raises(m.Refused): m.validate_output(value, 2, args)


def test_idle_wait_is_three_bounded_observations_then_unconditional_refusal(control, args, workflow, monkeypatch):
    original = workflow.Runner.__init__
    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs); self.busy = 3
    monkeypatch.setattr(workflow.Runner, '__init__', initialize)
    outcome = m.run(args, time.monotonic() + 500)
    assert outcome['failure']['failure_code'] == 'access_idle'
    assert workflow.events.count(('sleep', 60)) == 2 and 'backtests/read' not in workflow.events
    assert workflow.events.count('projects/read') == 3
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 2, args)


def test_helper_postcheck_failure_retains_selected_primary_error(control, args, workflow, monkeypatch):
    original = workflow.Runner.__init__
    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs); self.post_fail = True
    monkeypatch.setattr(workflow.Runner, '__init__', initialize)
    outcome = m.run(args, time.monotonic() + 500)
    failed = outcome['failure']
    assert failed['failure_code'] == 'launch_files' and failed['state']['error'] == terminal()
    assert failed['state']['observation'] is None and 'worker-1' not in workflow.events
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), 2, args)


def test_final_private_source_drift_retains_observation_but_requires_actual_two(control, args, workflow, monkeypatch):
    original = m.run_worker
    def worker(args, store, deadline, index):
        value = original(args, store, deadline, index)
        if index: value['changed'] = True
        return value
    monkeypatch.setattr(m, 'run_worker', worker)
    outcome = m.run(args, time.monotonic() + 500)
    result = outcome['result']
    assert result['observation']['terminal'] == terminal()
    assert result['postcheck'] == {'passed': False, 'failure_code': 'admission_changed'}
    raw = m.canonical({'binding': m.binding(args), 'outcome': outcome})
    assert m.validate_output(raw, 2, args)
    with pytest.raises(m.Refused): m.validate_output(raw, 0, args)


@pytest.mark.parametrize('endpoint,payload', [
    ('files/update', {'projectId': 38364439, 'name': 'main.py', 'content': 'bad'}),
    ('backtests/create', {'projectId': 38364439}),
    ('compile/create', {'projectId': 38364439}),
    ('projects/nodes/read', {'projectId': 38364439}),
    ('projects/collaboration/lock/acquire', {'projectId': 38364439}),
    ('compile/read', {'projectId': 38364439, 'compileId': 'wrong'}),
    ('files/read', {'projectId': 38364439, 'codeSourceId': 'wrong'}),
    ('backtests/list', {'projectId': 38364439, 'includeStatistics': True}),
    ('backtests/read', {'projectId': 38364439, 'backtestId': 'wrong'})])
def test_request_broker_rejects_mutation_or_other_identity_before_dispatch(control, args, workflow, monkeypatch, endpoint, payload):
    original = workflow.Runner.__init__
    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs); self.mutate_endpoint = (endpoint, payload)
    monkeypatch.setattr(workflow.Runner, '__init__', initialize)
    outcome = m.run(args, time.monotonic() + 500)
    assert outcome['failure']['failure_code'] in ('request_scope', 'response_scope')
    assert endpoint not in workflow.events


@pytest.mark.parametrize('code', sorted(remote.FINITE))
def test_exact_reconciliation_failure_categories_are_finite_and_native_validatable(args, code):
    value = m.finite(remote.Refused(code))
    assert value == 'launch_' + code and m._finite_code(value)
    assert m.validate_output(m.canonical({'binding': m.binding(args), 'preflight_failure': value}), 2, args)


@pytest.mark.parametrize('code', sorted(m.catalog_facts.FINITE))
def test_exact_catalog_facts_failure_categories_are_finite(args, code):
    assert m.finite(m.catalog_facts.Refused(code)) == 'facts_' + code
    assert m._finite_code('facts_' + code)


@pytest.mark.parametrize('change', ['exit', 'pin', 'source', 'flags', 'extra', 'count', 'post', 'observation'])
def test_output_binding_refuses_false_readiness_or_corruption(control, args, workflow, change):
    outcome = m.run(args, time.monotonic() + 500)
    result = outcome['result']
    actual = 0
    if change == 'exit': actual = 2
    elif change == 'pin': outcome['report']['sha256'] = 'f' * 64
    elif change == 'source': result['observation']['source_manifest_sha256'] = 'f' * 64
    elif change == 'flags': result['paper_or_live_ready'] = True
    elif change == 'extra': result['raw_response'] = {}
    elif change == 'count': result['application_dispatch_count'] = True
    elif change == 'post': result['postcheck']['passed'] = False
    else: result['observation']['fixed_source_checks_after'] = False
    with pytest.raises((m.Refused, remote.Refused)):
        m.validate_output(m.canonical({'binding': m.binding(args), 'outcome': outcome}), actual, args)


@pytest.fixture
def joined(witness_terminal, monkeypatch):
    context = witness_terminal['failure_evidence']['diagnostic_context']
    join = identity_tests.synthetic_join_receipt.__wrapped__(witness_terminal, monkeypatch)
    for row in join['matches']:
        for field in m.catalog_facts.HASH_FIELDS:
            if field not in row: row[field] = 'a' * 64
    facts = {'context_sha256': m.identity_join.context_digest(context),
        'join_receipt_sha256': m.catalog_facts.join_receipt_digest(join),
        'witness_count': join['matched_count'],
        'facts': [{key: row[key] for key in m.catalog_facts.HASH_FIELDS} for row in join['matches']]}
    monkeypatch.setattr(m.catalog_facts, 'validate_receipt', lambda value: copy.deepcopy(value))
    return {'receipt': join, 'catalog_facts': facts}


@pytest.fixture
def witness_terminal():
    value = identity_tests.witness_terminal.__wrapped__()
    value.update(compile_id=remote.COMPILE_ID, backtest_id=remote.BACKTEST_ID, backtest_name=remote.BACKTEST_NAME)
    remote.validate_terminal_receipt(value)
    return value


def test_same_native_private_construct_supplies_join_and_facts_before_postauthentication(control, args,
        witness_terminal, joined, monkeypatch):
    events = []
    for key in ('QC_USER_ID', 'QC_API_TOKEN'): monkeypatch.delenv(key, raising=False)
    old_packet, plain, projected = {'synthetic': True}, object(), object()
    monkeypatch.setattr(m.admission, 'admit', lambda *_: events.append('admit') or old_packet)
    monkeypatch.setattr(m.admitted.prep, 'construct', lambda *_: events.append('construct') or (plain, projected))
    monkeypatch.setattr(m, '_constructed_matches', lambda *_: events.append('snapshot') or ('fixed',))
    def join(left, context, packet):
        assert left is plain and packet is old_packet
        events.append('join')
        return joined['receipt']
    def facts(left, context, packet, receipt):
        assert left is plain and packet is old_packet and receipt == joined['receipt']
        events.append('facts')
        return joined['catalog_facts']
    monkeypatch.setattr(m.identity_join, 'join', join)
    monkeypatch.setattr(m.catalog_facts, 'facts', facts)
    monkeypatch.setattr(m, 'preflight', lambda *_: events.append('preflight'))
    monkeypatch.setattr(m.environment, 'require_safe_environment', lambda: events.append('environment'))
    with m.Store() as store:
        args.control_fd, args.worker_index = store.fd, 2
        store.write('worker-2-intent.json', {'binding': m.binding(args), 'worker_index': 2, 'terminal': witness_terminal})
        assert m.join_worker(args, time.monotonic() + 100) == joined
        store.verify()
    assert events == ['admit', 'construct', 'snapshot', 'join', 'facts', 'construct', 'snapshot', 'admit', 'preflight', 'environment']


@pytest.mark.parametrize('field', ['context_sha256', 'join_receipt_sha256', 'witness_count', 'facts'])
def test_catalog_facts_receipt_must_bind_the_exact_join_context_and_witness(witness_terminal, joined, field):
    value = {'status': 'joined', **copy.deepcopy(joined)}
    if field == 'witness_count': value['catalog_facts'][field] += 1
    elif field == 'facts': value['catalog_facts'][field][0]['identity_sha256'] = 'f' * 64
    else: value['catalog_facts'][field] = 'f' * 64
    with pytest.raises(m.Refused, match='join_binding'): m.validate_join(value, witness_terminal)


def test_native_join_plus_facts_dispatch_is_once_actual_zero_and_no_credentials(control, args,
        witness_terminal, joined, monkeypatch):
    calls = []
    monkeypatch.setenv('QC_API_TOKEN', 'synthetic-only')
    def capture(command, env, timeout, **kwargs):
        calls.append(command)
        assert command[0] == '/usr/bin/sandbox-exec' and 'join-worker' in command
        assert command[-2:] == ['--worker-index', '2'] and kwargs['pass_fds'] == (store.fd,)
        assert not {'QC_USER_ID', 'QC_API_TOKEN'} & set(env) and timeout <= 120
        return m.canonical({'binding': m.binding(args), 'diagnostic_join': joined}), b'', {'actual_exit': 0, 'bound': None}
    monkeypatch.setattr(m, 'capture', capture)
    with m.Store() as store:
        assert m.run_join_worker(args, store, time.monotonic() + 100, witness_terminal) == {'status': 'joined', **joined}
        with pytest.raises(m.Refused): m.run_join_worker(args, store, time.monotonic() + 100, witness_terminal)
        store.verify()
    assert len(calls) == 1


def test_fixed_A19_read_binding_cannot_read_while_idle_or_change_job():
    with pytest.raises(m.Refused):
        m._read_binding({'stage': 'idle'}, {'projectId': 38364439, 'backtestId': remote.BACKTEST_ID})
    assert m._read_binding({'stage': 'observe'}, {'projectId': 38364439, 'backtestId': remote.BACKTEST_ID}) == {
        'project_id': 38364439, 'backtest_id': remote.BACKTEST_ID, 'backtest_name': remote.BACKTEST_NAME,
        'compile_id': remote.COMPILE_ID, 'mode': 'error'}


def test_error_selector_precedes_canonicalization_of_large_or_hostile_ignored_outcomes(control, args, workflow):
    class Opaque:
        def __iter__(self): raise AssertionError('ignored outcome iterated')
        def __str__(self): raise AssertionError('ignored outcome rendered')
    original = workflow.api.request
    def request(endpoint, payload):
        value = original(endpoint, payload)
        if endpoint == 'backtests/read':
            value.update(charts=Opaque(), trades='PRIVATE' * 200000, statistics=Opaque())
            value['backtest'].update(charts=Opaque(), statistics=Opaque())
        return value
    workflow.api.request = request
    outcome = m.run(args, time.monotonic() + 500)
    assert outcome['result']['observation']['terminal']['status'] == 'Runtime Error'
    raw = m.canonical({'binding': m.binding(args), 'outcome': outcome})
    assert b'PRIVATE' not in raw and len(raw) < 16384
    assert m.validate_output(raw, 0, args)


@pytest.mark.parametrize('changed', ['construct', 'admission'])
def test_join_plus_facts_never_survives_private_postcheck_drift(control, args, witness_terminal,
        joined, monkeypatch, changed):
    for key in ('QC_USER_ID', 'QC_API_TOKEN'): monkeypatch.delenv(key, raising=False)
    count = {'construct': 0, 'admission': 0}
    def admit(*_):
        count['admission'] += 1
        return {'same': 1 if changed != 'admission' or count['admission'] == 1 else 2}
    def snapshot(*_):
        count['construct'] += 1
        return 1 if changed != 'construct' or count['construct'] == 1 else 2
    monkeypatch.setattr(m.admission, 'admit', admit)
    monkeypatch.setattr(m.admitted.prep, 'construct', lambda *_: (object(), object()))
    monkeypatch.setattr(m, '_constructed_matches', snapshot)
    monkeypatch.setattr(m.identity_join, 'join', lambda *_: joined['receipt'])
    monkeypatch.setattr(m.catalog_facts, 'facts', lambda *_: joined['catalog_facts'])
    with m.Store() as store:
        args.control_fd, args.worker_index = store.fd, 2
        store.write('worker-2-intent.json', {'binding': m.binding(args), 'worker_index': 2, 'terminal': witness_terminal})
        with pytest.raises(m.Refused, match='admission_changed'): m.join_worker(args, time.monotonic() + 100)
