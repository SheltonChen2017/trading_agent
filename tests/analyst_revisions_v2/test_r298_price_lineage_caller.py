"""Synthetic AC orchestration, four-leaf scope and public process-result binding."""
import copy
import inspect
import io
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS

import pytest

from scripts import prepare_arv2_r298_price_lineage as m

ARGS = NS(expected_head='a' * 40, caller_sha256='b' * 64)


def test_exact_local_alarm_failure_preserves_finite_deadline_cause():
    assert m.finite(m.admitted.helpers.Deadline()) == 'deadline'
    class ForeignDeadline(m.admitted.helpers.Deadline):
        pass
    assert m.finite(ForeignDeadline()) == 'unknown_exception'


def refused(code, function):
    with pytest.raises(m.Refused) as caught:
        function()
    assert m.finite(caught.value) == code


def source_receipt():
    return {'schema': m.data_guard.SCHEMA + '-receipt',
        'profile_sha256': m.sha(m.data_guard.canonical(m.data_guard.profile_record(m.FILE_PLAN))),
        'files': {role: {**pin, 'current_metadata_sha256': 'd' * 64, 'current_security_sha256': 'e' * 64}
            for role, pin in m.FILE_PLAN.items()}, 'fresh_current_security_authenticated': True,
        'fixed_bytes_authenticated': True, 'requires_normal_return_before_use': True,
        'historical_continuity_proven': False, 'continuous_integrity_proven': False}


def actual(output=b'', *, exit=0, bound=None, errors=b''):
    return {'actual_exit': exit, 'bound': bound, 'spawn_observed': True,
        'dispatched_at': '2026-10-27T00:00:00Z', 'completion_observed_at': '2026-10-27T00:00:01Z',
        'stdout_bytes': len(output), 'stdout_sha256': m.sha(output),
        'stderr_bytes': len(errors), 'stderr_sha256': m.sha(errors)}


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('old operation, original archive or genuine package load forbidden')
    for module in (m.previous, m.previous.previous):
        monkeypatch.setattr(module, 'run', deny)
        monkeypatch.setattr(module, 'observe', deny)
        monkeypatch.setattr(module, 'preflight', deny)
    monkeypatch.setattr(m.previous.demand, 'prepare', deny)
    monkeypatch.setattr(m.previous.demand.loader, '_load_plain', deny)


@pytest.fixture
def state(monkeypatch):
    expected = m.source_binding()
    state = NS(events=[], files={}, stores=0, prepares=0, fail_stage=None,
        buffers={role: ('synthetic-data-' + role).encode() for role in m.FILE_PLAN},
        private={'rows': ['SYNTHETIC-PRICE-LINEAGE-PRIVATE']}, expected=expected)
    raw = m.routes.canonical(state.private)
    state.summary = {'schema': 'synthetic-price-route-summary',
        'source_pins': {'aa_frame': m._file_pin('aa_frame'), 'demand_frame': m._file_pin('ab_demand'), **m.capture_pins()},
        'aa_routing_summary_sha256': m.sha(m.routes.canonical(expected['aa_routing_summary'])),
        'demand_summary_sha256': m.AB_DEMAND_SHA256,
        'binding_contract': expected['aa_routing_summary']['binding_contract'],
        'private_frame_byte_count': len(raw), 'private_frame_sha256': m.sha(raw)}
    monkeypatch.setattr(m, 'binding', lambda args: {'schema': m.SCHEMA,
        'expected_head': args.expected_head, 'caller_sha256': args.caller_sha256, 'profile_sha256': 'c' * 64})
    class MemoryStore:
        def __init__(self):
            state.stores += 1; m.require(state.stores == 1, 'claim_spent')
        def __enter__(self): return self
        def __exit__(self, *_): state.events.append('store_close')
        def verify(self): state.events.append('store_verify')
        def write(self, name, value): return self.write_bytes(name, m.canonical(value), private=False)
        def write_bytes(self, name, raw, *, private):
            m.require(name not in state.files, 'control_name')
            state.events.append('write:' + name)
            if state.fail_stage == name: raise m.Refused('control_write')
            if private: assert name == m.PRIVATE_NAME and 'source_return' in state.events
            state.files[name] = bytes(raw)
            return {'byte_count': len(raw), 'sha256': m.sha(raw)}
    class MemoryGuard:
        def __init__(self, plan, *, deadline):
            assert plan == m.FILE_PLAN
            state.events.append('guard_construct')
        def __enter__(self):
            assert 'claim.json' in state.files and 'source-start.json' in state.files
            state.events.append('source_enter'); return self
        def __exit__(self, kind, *_):
            state.events.append('source_exit')
            if state.fail_stage == 'guard_return' and kind is None: raise m.data_guard.Refused('named_changed')
            if kind is None: state.events.append('source_return')
        def read_all_once(self):
            state.events.append('source_read'); return dict(state.buffers)
        def receipt(self):
            state.events.append('source_verify')
            if state.fail_stage == 'source_receipt': raise m.data_guard.Refused('named_changed')
            return source_receipt()
    def prepare(*raws, aa_routing_summary, demand_summary, capture_pins, deadline=None):
        state.prepares += 1; state.events.append('prepare')
        assert state.prepares == 1 and 'analysis-start.json' in state.files
        assert raws == tuple(state.buffers[role] for role in ('aa_frame', 'ab_demand', 'stocks_metadata', 'funds_metadata'))
        assert aa_routing_summary == expected['aa_routing_summary'] and demand_summary == expected['demand_summary']
        assert capture_pins == m.capture_pins() and 0 < deadline - time.monotonic() <= m.PREPARE_SECONDS
        assert 'source_enter' in state.events and 'source_exit' not in state.events
        if state.fail_stage == 'prepare': raise m.routes.Refused('metadata_catalog')
        return copy.deepcopy(state.summary), m.routes.PrivatePriceRoutes(state.private)
    def validate_summary(value):
        m.require(type(value) is dict and set(value) == set(state.summary)
            and value['schema'] == 'synthetic-price-route-summary', 'helper_binding')
        return copy.deepcopy(value)
    def validate_private(value, *, expected_summary):
        m.require(type(value) is dict and value == state.private, 'private_binding')
        return copy.deepcopy(value)
    def preflight(*args):
        state.events.append('postflight')
        if state.fail_stage == 'postflight': raise m.Refused('source_pin')
    def safe_environment():
        state.events.append('safe_environment')
        if state.fail_stage == 'post_guard_environment' and 'source_return' in state.events:
            raise m.environment.EnvironmentRefused('synthetic private logging failure')
    monkeypatch.setattr(m, 'Store', MemoryStore)
    monkeypatch.setattr(m.data_guard, 'FixedDataGuard', MemoryGuard)
    monkeypatch.setattr(m.routes, 'prepare', prepare)
    monkeypatch.setattr(m.routes, 'validate_summary', validate_summary)
    monkeypatch.setattr(m.routes, 'validate_private_record', validate_private)
    monkeypatch.setattr(m, 'preflight', preflight)
    monkeypatch.setattr(m.environment, 'require_safe_environment', safe_environment)
    return state


def run():
    return m.run(ARGS, time.monotonic() + 100)


def test_claim_and_both_start_markers_precede_four_data_reads_single_prepare_and_guard_return_precedes_publication(state):
    outcome = run()
    assert set(outcome) == {'result', 'report'}
    ordered = ['write:claim.json', 'write:source-start.json', 'source_enter', 'source_read',
        'write:analysis-start.json', 'prepare', 'source_exit', 'source_return',
        'write:' + m.PRIVATE_NAME, 'postflight', 'write:report.json']
    assert [state.events.index(name) for name in ordered] == sorted(state.events.index(name) for name in ordered)
    assert state.prepares == 1 and state.events.count('safe_environment') == 6
    assert state.files[m.PRIVATE_NAME] == m.routes.canonical(state.private)
    assert b'SYNTHETIC-PRICE-LINEAGE-PRIVATE' not in m.canonical(outcome)
    value = {'binding': m.binding(ARGS), 'outcome': outcome}
    assert m.validate_output(m.canonical(value), 0, ARGS) == value
    assert all(outcome['result'][flag] is False for flag in m.FALSE_FLAGS)


@pytest.mark.parametrize('failure', ['source_receipt', 'prepare', 'guard_return', 'post_guard_environment',
    'price-lineage-private.json', 'postflight', 'report.json'])
def test_failure_is_consumed_without_retry_cleanup_or_early_publication(state, failure):
    state.fail_stage = failure
    outcome = run(); failed = outcome['failure']
    assert failed['claim_consumed'] is True and state.stores == 1 and state.prepares <= 1
    if failure in ('source_receipt', 'prepare', 'guard_return', 'post_guard_environment'):
        assert m.PRIVATE_NAME not in state.files
    value = {'binding': m.binding(ARGS), 'outcome': outcome}
    assert m.validate_output(m.canonical(value), 2, ARGS) == value
    refused('claim_spent', run)


@pytest.mark.parametrize('fault', ['source_aa', 'source_demand', 'source_stocks', 'source_funds',
    'aa_summary', 'demand_summary', 'binding_contract', 'private_hash', 'private_size', 'private_bound'])
def test_exact_four_sources_prior_summaries_binding_and_private_hash_are_required_before_publication(state, monkeypatch, fault):
    if fault.startswith('source_'):
        role = {'source_aa': 'aa_frame', 'source_demand': 'demand_frame',
            'source_stocks': 'stocks', 'source_funds': 'funds'}[fault]
        state.summary['source_pins'][role]['sha256'] = 'f' * 64
    elif fault == 'aa_summary': state.summary['aa_routing_summary_sha256'] = 'f' * 64
    elif fault == 'demand_summary': state.summary['demand_summary_sha256'] = 'f' * 64
    elif fault == 'binding_contract': state.summary['binding_contract'] = {}
    elif fault == 'private_hash': state.summary['private_frame_sha256'] = 'f' * 64
    elif fault == 'private_size': state.summary['private_frame_byte_count'] += 1
    else: monkeypatch.setattr(m, 'MAX_PRIVATE', 1)
    failed = run()['failure']
    assert failed['failure_code'] in ('private_binding', 'helper_binding')
    assert m.PRIVATE_NAME not in state.files


@pytest.mark.parametrize('fault', ['actual2', 'actual_bool', 'report_sha', 'guard', 'analysis',
    'source_receipt', 'flag', 'AB_demand', 'AB_fact', 'extra_private', 'private_hash', 'private_missing'])
def test_public_success_requires_actual_zero_closed_summary_both_guard_returns_and_output_pin(state, fault):
    value = {'binding': m.binding(ARGS), 'outcome': run()}
    exit = 0; result = value['outcome']['result']
    if fault == 'actual2': exit = 2
    elif fault == 'actual_bool': exit = False
    elif fault == 'report_sha': value['outcome']['report']['sha256'] = 'f' * 64
    elif fault == 'guard': result['source_guard_returned'] = False
    elif fault == 'analysis': result['analysis_returned'] = False
    elif fault == 'source_receipt': result['source_receipt'] = None
    elif fault == 'flag': result['point_in_time_proven'] = True
    elif fault == 'AB_demand': result['AB_demand_summary_sha256'] = 'f' * 64
    elif fault == 'AB_fact': result['AB_observed_fact_sha256'] = 'f' * 64
    elif fault == 'extra_private': result['rows'] = ['never public']
    elif fault == 'private_hash': result['private_pin']['sha256'] = 'f' * 64
    else: result['private_pin'] = None
    with pytest.raises(m.Refused): m.validate_output(m.canonical(value), exit, ARGS)


def test_public_prior_source_binding_authenticates_AA_and_AB_metadata_without_old_data_or_controls():
    expected = m.source_binding()
    assert expected['aa_routing_summary']['binding_contract']['binding_count'] == 6151
    assert expected['demand_summary']['private_frame_sha256'] == m._file_pin('ab_demand')['sha256']
    assert m.sha(m.routes.canonical(expected['demand_summary'])) == m.AB_DEMAND_SHA256


@pytest.mark.parametrize('fault', ['actual_exit', 'source_frame', 'source_head', 'evidence_summary', 'demand_summary',
    'observed_timestamps'])
def test_changed_public_AB_binding_refuses_before_any_new_private_source_open(monkeypatch, fault):
    if fault in ('evidence_summary', 'demand_summary'):
        fn = 'expected_' + fault
        value = getattr(m.anchor, fn)()
        if fault == 'evidence_summary': value['private_evidence_sha256'] = 'f' * 64
        else: value['private_frame_sha256'] = 'f' * 64
        monkeypatch.setattr(m.anchor, fn, lambda: value)
    else:
        value = m.anchor.observed_fact()
        if fault == 'actual_exit': value['producer']['actual_exit'] = 2
        elif fault == 'source_head': value['expected_head'] = 'f' * 40
        elif fault == 'source_frame': value['private_files']['membership-demand-private.json']['sha256'] = 'f' * 64
        else:
            value['producer']['dispatched_at'] = '2026-10-27T00:00:00Z'
            value['validator']['dispatched_at'] = '2026-10-27T00:00:00Z'
        monkeypatch.setattr(m.anchor, 'observed_fact', lambda: value)
    refused('source_binding', m.source_binding)


def test_profile_and_native_policy_have_only_fixed_four_DATA_sources_and_new_own_outputs(monkeypatch):
    monkeypatch.setattr(m.previous, 'pins', lambda: {'scripts/existing-' + str(i) + '.py': 'd' * 64 for i in range(171)})
    monkeypatch.setattr(m, 'NEW_PINS', {name: 'e' * 64 for name in m.NEW_PINS})
    profile = m.profile_record()
    assert len(profile['source_pins']) == 175
    assert profile['producer_seconds'] == 600 and profile['outer_seconds'] == 630
    assert profile['direct_prepare_seconds'] == 450 and profile['validator_seconds'] == 20
    assert len(profile['fixed_data_plan']) == 4
    assert all(profile[flag] is False for flag in m.FALSE_FLAGS)
    profile['fixed_data_plan']['aa_frame']['sha256'] = 'f' * 64
    assert m.FILE_PLAN['aa_frame']['sha256'] == '3776f03b4941d8e6d014dee19f5ee8a05080f214ab7f502d10738f00a689f561'
    producer, validator = m.native_profile(mode='producer'), m.native_profile(mode='validator')
    for row in m.FILE_PLAN.values():
        assert str(m.ROOT / row['relative_path']) in producer
    assert '(deny network*)' in producer and '/usr/bin/security' in producer and 'Library/Keychains' in producer
    assert '01-tickers-years-full.zip' not in producer and 'sharadar_capture' not in producer
    assert 'newrule_input' not in producer and 'source-lineage' not in producer
    assert str(m.ROOT / 'artifacts/analyst_revisions_v2/newrule_route_dispositions/R326-20261027-AB/report.json') not in producer
    assert 'membership-demand-private.json' not in validator and 'assistant.dispatch_fence' not in sys.modules


def test_actual_selected_public_source_closure_is_fixed_and_has_no_automatic_pin_refresh():
    pins = m.pins()
    assert len(pins) == 175
    for name, pin in pins.items():
        assert m.sha((m.ROOT / name).read_bytes()) == pin
    assert pins['scripts/inspect_arv2_r298_route_dispositions.py'] == m.AB_CALLER_SHA256
    assert pins['scripts/arv2_r298_ab_source_binding.py'] == \
        '817ea451899e61da3f3ee911cd5f8a11bb3dc6463dc1dfacebb5f71bd7ede1dd'

@pytest.mark.parametrize('fault', ['producer_nonzero', 'producer_bool', 'producer_timeout',
    'producer_noise', 'producer_binding', 'validator_nonzero', 'validator_bool', 'validator_noise', 'validator_binding'])
def test_no_data_observer_requires_exact_native_producer_and_separate_validator_actuals(state, monkeypatch, fault):
    value = {'binding': m.binding(ARGS), 'outcome': run()}
    raw = m.canonical(value)
    calls = []
    def capture(command, safe, timeout, **kwargs):
        calls.append((command, safe, timeout, kwargs))
        assert command[:2] == ['/usr/bin/sandbox-exec', '-p']
        assert '(deny network*)' in command[2] and '/usr/bin/security' in command[2]
        producer = len(calls) == 1
        errors = b'noise' if fault == ('producer_noise' if producer else 'validator_noise') else b''
        exit = (2 if fault == ('producer_nonzero' if producer else 'validator_nonzero') else
            False if fault == ('producer_bool' if producer else 'validator_bool') else 0)
        if fault == 'producer_nonzero' and not producer:
            # A real external validator refuses a success envelope paired
            # with observed producer exit2, rather than fabricating exit0.
            refused('output', lambda: m.validate_output(raw, 2, ARGS))
            exit = 2
        output = raw if not (fault == 'validator_binding' and not producer) else m.canonical({'wrong': 'metadata'})
        checked = actual(output, exit=exit, errors=errors,
            bound='deadline' if fault == 'producer_timeout' and producer else None)
        if fault == 'producer_binding' and producer: checked['stdout_sha256'] = 'f' * 64
        if not producer:
            assert kwargs['input_bytes'] == raw and timeout == m.VALIDATOR_SECONDS
        return output, errors, checked
    monkeypatch.setattr(m, 'capture', capture)
    outer, code = m.observe(ARGS)
    assert code == 2 and outer['output_authenticated'] is False
    assert len(calls) == (1 if fault.startswith('producer_') and fault != 'producer_nonzero' else 2)
    assert outer['failure_code'] in ('parent_failed', 'validator_failed')


def test_observer_authenticates_failure_without_reclassifying_it_success(state, monkeypatch):
    state.fail_stage = 'prepare'
    raw = m.canonical({'binding': m.binding(ARGS), 'outcome': run()})
    calls = []
    def capture(command, safe, timeout, **kwargs):
        calls.append(command)
        return raw, b'', actual(raw, exit=2 if len(calls) == 1 else 0)
    monkeypatch.setattr(m, 'capture', capture)
    outer, code = m.observe(ARGS)
    assert code == 2 and outer['output_authenticated'] is True and outer['failure_code'] is None
    assert outer['output']['outcome']['failure']['claim_consumed'] is True and len(calls) == 2


def test_observer_public_only_success_broker_never_opens_private_output(state, monkeypatch):
    value = {'binding': m.binding(ARGS), 'outcome': run()}; raw = m.canonical(value)
    calls = []
    def capture(command, safe, timeout, **kwargs):
        calls.append(command)
        return raw, b'', actual(raw)
    monkeypatch.setattr(m, 'capture', capture)
    outer, code = m.observe(ARGS)
    assert code == 0 and outer['output_authenticated'] is True and outer['output'] == value
    assert b'SYNTHETIC-PRICE-LINEAGE-PRIVATE' not in m.canonical(outer)
    assert len(calls) == 2


@pytest.mark.parametrize('fault', ['zero', 'placeholder', 'conflict', 'baseline_count'])
def test_unfrozen_or_conflicting_source_pin_map_refuses(fault, monkeypatch):
    baseline = {'scripts/existing-' + str(i) + '.py': 'd' * 64 for i in range(171)}
    monkeypatch.setattr(m.previous, 'pins', lambda: baseline)
    additions = {'scripts/new.py': 'e' * 64}
    if fault == 'zero': additions['scripts/new.py'] = '0' * 64
    elif fault == 'placeholder': additions['scripts/new.py'] = 'UNFROZEN'
    elif fault == 'conflict': additions['scripts/existing-1.py'] = 'f' * 64
    else: baseline.pop('scripts/existing-1.py')
    monkeypatch.setattr(m, 'NEW_PINS', additions)
    refused('source_pin', m.pins)


def test_real_new_control_store_is_exclusive_bounded_held_and_preserves_failure_leaf(tmp_path, monkeypatch):
    control = tmp_path / 'synthetic-AA-parent/synthetic-AA'
    monkeypatch.setattr(m, 'CONTROL', control)
    with m.Store() as store:
        pin = store.write('claim.json', {'synthetic': True})
        assert pin == {'byte_count': len(m.canonical({'synthetic': True})),
            'sha256': m.sha(m.canonical({'synthetic': True}))}
        private = b'synthetic-private-in-cache-only'
        private_pin = store.write_bytes(m.PRIVATE_NAME, private, private=True)
        assert private_pin == {'byte_count': len(private), 'sha256': m.sha(private)}
        held = store.held[m.PRIVATE_NAME][0]
        assert store._read(held, len(private)) == private
        refused('control_name', lambda: store.write('claim.json', {}))
        refused('control_name', lambda: store.write_bytes('stocks-metadata.csv', b'denied', private=True))
        refused('control_name', lambda: store.write('../elsewhere.json', {}))
        refused('control_bound', lambda: store.write_bytes('empty.json', b'', private=False))
        refused('claim_spent', m.Store)
        store.verify()
    assert control.is_dir() and {path.name for path in control.iterdir()} == {'claim.json', m.PRIVATE_NAME}
    with pytest.raises(OSError): os.fstat(held)


@pytest.mark.parametrize('change', ['content', 'mode', 'name', 'extra_name'])
def test_real_owned_control_detects_external_drift_without_cleanup(tmp_path, monkeypatch, change):
    control = tmp_path / 'synthetic-AA-parent/synthetic-AA'
    monkeypatch.setattr(m, 'CONTROL', control)
    with m.Store() as store:
        store.write('claim.json', {'synthetic': True})
        path = control / 'claim.json'
        if change == 'content': path.write_bytes(b'changed')
        elif change == 'mode': path.chmod(0o644)
        elif change == 'extra_name': (control / 'synthetic-unexpected').write_bytes(b'extra')
        else:
            path.rename(control / 'synthetic-retained-old')
            path.write_bytes(b'changed'); path.chmod(0o600)
        refused('control_changed' if change in ('extra_name', 'name') else 'capture_changed', store.verify)
    assert control.is_dir()


def test_cli_parent_and_validator_use_alarm_and_preflight_before_any_operation(monkeypatch):
    events, stdout = [], io.BytesIO()
    class Alarm:
        def __init__(self, deadline):
            assert 0 < deadline - time.monotonic() <= m.DEADLINE_SECONDS
            events.append('alarm_construct')
        def __enter__(self): events.append('alarm_enter')
        def __exit__(self, *_): events.append('alarm_exit')
    monkeypatch.setattr(m.admitted.helpers, '_alarm', Alarm)
    monkeypatch.setattr(m, 'preflight', lambda *args: events.append('preflight'))
    monkeypatch.setattr(m.environment, '_bootstrap_cli_logging', lambda: events.append('logging'))
    monkeypatch.setattr(m, 'binding', lambda args: {'synthetic': True})
    def run(args, deadline):
        events.append('run'); return {'failure': {'synthetic': True}}
    monkeypatch.setattr(m, 'run', run)
    monkeypatch.setattr(m.sys, 'stdout', NS(buffer=stdout))
    assert m.main(['run', '--expected-head', ARGS.expected_head, '--caller-sha256', ARGS.caller_sha256]) == 2
    assert events == ['alarm_construct', 'alarm_enter', 'preflight', 'logging', 'run', 'alarm_exit']
    assert json.loads(stdout.getvalue()) == {'binding': {'synthetic': True},
        'outcome': {'failure': {'synthetic': True}}}


@pytest.fixture
def public_preflight(monkeypatch):
    raw = m.SOURCE.read_bytes()
    args = NS(expected_head='a' * 40, caller_sha256=m.sha(raw))
    state = NS(raw=raw, args=args, calls=[], change=None)
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: False)
    monkeypatch.setattr(m.environment, '_require_environment', lambda: None)
    monkeypatch.setattr(m, 'pins', lambda: {m.SOURCE.relative_to(m.ROOT).as_posix():
        'f' * 64 if state.change == 'selected_pin' else m.sha(raw)})
    values = {('rev-parse', '--show-toplevel'): str(m.ROOT),
        ('branch', '--show-current'): m.admitted.frozen.BRANCH,
        ('rev-parse', 'HEAD'): args.expected_head, ('status', '--porcelain'): ''}
    def git(command, deadline, *args):
        state.calls.append(command)
        if command[0] == 'cat-file':
            return b'wrong committed source bytes' if state.change == 'committed_blob' else raw
        value = values[tuple(command)]
        if state.change == tuple(command): value = 'concurrent or mismatched synthetic state'
        return value.encode('ascii')
    monkeypatch.setattr(m.admitted.v5, '_git', git)
    return state


def test_preflight_binds_exact_host_clean_root_branch_head_source_and_committed_blob(public_preflight):
    fixture = public_preflight
    m.preflight(fixture.args, time.monotonic() + 30)
    assert fixture.calls[:4] == [['rev-parse', '--show-toplevel'], ['branch', '--show-current'],
        ['rev-parse', 'HEAD'], ['status', '--porcelain']]
    assert fixture.calls[-1] == ['cat-file', 'blob', fixture.args.expected_head + ':'
        + m.SOURCE.relative_to(m.ROOT).as_posix()]


@pytest.mark.parametrize('change', [('rev-parse', '--show-toplevel'), ('branch', '--show-current'),
    ('rev-parse', 'HEAD'), ('status', '--porcelain'), 'selected_pin', 'caller_pin', 'committed_blob'])
def test_preflight_concurrent_git_or_source_mismatch_refuses_without_refresh(public_preflight, change):
    fixture = public_preflight; fixture.change = change
    if change == 'caller_pin': fixture.args.caller_sha256 = 'f' * 64
    refused('git_state' if type(change) is tuple else 'source_pin',
        lambda: m.preflight(fixture.args, time.monotonic() + 30))


def test_preflight_test_host_and_invalid_args_refuse_before_git(public_preflight, monkeypatch):
    fixture = public_preflight
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: True)
    refused('host', lambda: m.preflight(fixture.args, time.monotonic() + 30))
    assert fixture.calls == []
    monkeypatch.setattr(m.admitted.v5, '_under_test', lambda: False)
    fixture.args.expected_head = 'not a frozen commit'
    refused('arguments', lambda: m.preflight(fixture.args, time.monotonic() + 30))
    assert fixture.calls == []
