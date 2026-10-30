"""Synthetic AB orchestration and exact source guards; no private production inputs."""
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

from scripts import inspect_arv2_r298_route_dispositions as m

ARGS = NS(expected_head='a' * 40, caller_sha256='b' * 64)


def refused(code, function):
    with pytest.raises(m.Refused) as caught:
        function()
    assert m.finite(caught.value) == code


def source_receipt():
    return {'schema': m.SCHEMA + '-retained-AA-frame-current-source',
        'files': {name: {**pin, 'current_metadata_sha256': 'd' * 64,
            'current_security_sha256': 'e' * 64} for name, pin in m.SOURCE_PINS.items()},
        'fresh_current_security_authenticated': True, 'fixed_retained_bytes_authenticated': True,
        'historical_metadata_preservation_proven': False, 'continuous_security_proven': False}


def actual(output=b'', *, exit=0, bound=None, errors=b''):
    return {'actual_exit': exit, 'bound': bound, 'spawn_observed': True,
        'dispatched_at': '2026-10-27T00:00:00Z', 'completion_observed_at': '2026-10-27T00:00:01Z',
        'stdout_bytes': len(output), 'stdout_sha256': m.sha(output),
        'stderr_bytes': len(errors), 'stderr_sha256': m.sha(errors)}


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('old operation or actual private input called')
    monkeypatch.setattr(m.previous, 'run', deny)
    monkeypatch.setattr(m.previous, 'observe', deny)
    monkeypatch.setattr(m.previous, 'preflight', deny)
    monkeypatch.setattr(m.previous.worker, 'prepare', deny)
    monkeypatch.setattr(m.demand.loader, '_load_plain', deny)


@pytest.fixture
def state(monkeypatch):
    state = NS(events=[], files={}, stores=0, evidence_calls=0, demand_calls=0, fail_stage=None,
        frame=b'synthetic-AA-frame-only', evidence_record={'rows': ['SYNTHETIC-EVIDENCE-PRIVATE']},
        demand_record={'rows': ['SYNTHETIC-DEMAND-PRIVATE']})
    expected = m.anchor.expected_summary()
    routing = expected['routing_summary']
    state.expected = expected
    e_raw, d_raw = m.evidence.canonical(state.evidence_record), m.demand.canonical(state.demand_record)
    state.evidence_summary = {'schema': 'synthetic-evidence-summary',
        'frame_pin': dict(m.SOURCE_PINS[m.SOURCE_NAMES[0]]),
        'routing_summary_sha256': m.sha(m.evidence.canonical(routing)),
        'binding_contract': routing['binding_contract'],
        'disposition_counts': routing['disposition_counts'], 'refusal_counts': routing['refusal_counts'],
        'private_evidence_byte_count': len(e_raw), 'private_evidence_sha256': m.sha(e_raw)}
    state.demand_summary = {'schema': 'synthetic-demand-summary',
        'source_frame_pin': dict(m.SOURCE_PINS[m.SOURCE_NAMES[0]]),
        'evidence_summary_sha256': m.sha(m.evidence.canonical(state.evidence_summary)),
        'route_evidence_private_sha256': state.evidence_summary['private_evidence_sha256'],
        'input_binding': expected['input_binding'],
        'private_frame_byte_count': len(d_raw), 'private_frame_sha256': m.sha(d_raw)}
    monkeypatch.setattr(m, 'aa_summary', lambda: copy.deepcopy(expected))
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
            if private:
                assert name in m.PRIVATE_NAMES and 'source_return' in state.events
            state.files[name] = bytes(raw)
            return {'byte_count': len(raw), 'sha256': m.sha(raw)}
    class MemoryGuard:
        def __init__(self, *, deadline): state.events.append('guard_construct')
        def __enter__(self):
            assert 'claim.json' in state.files and 'source-start.json' in state.files
            state.events.append('source_enter'); return self
        def __exit__(self, kind, *_):
            state.events.append('source_exit')
            if state.fail_stage == 'guard_return' and kind is None: raise m.Refused('source_changed')
            if kind is None: state.events.append('source_return')
        def read_once(self):
            state.events.append('source_read'); return {m.SOURCE_NAMES[0]: state.frame}
        def receipt(self):
            state.events.append('source_verify')
            if state.fail_stage == 'source_receipt': raise m.Refused('source_changed')
            return source_receipt()
    def inspect_frame(raw, *, expected_summary, deadline=None):
        state.evidence_calls += 1; state.events.append('evidence')
        assert state.evidence_calls == 1 and 'analysis-start.json' in state.files
        assert raw == state.frame and expected_summary == routing
        assert 'source_enter' in state.events and 'source_exit' not in state.events
        assert 0 < deadline - time.monotonic() <= m.PREPARE_SECONDS
        if state.fail_stage == 'evidence': raise m.evidence.Refused('frame_pin')
        return copy.deepcopy(state.evidence_summary), m.evidence.PrivateEvidence(state.evidence_record)
    def prepare(record, *, evidence_summary, deadline):
        state.demand_calls += 1; state.events.append('demand')
        assert state.demand_calls == 1 and state.evidence_calls == 1
        assert record == state.evidence_record and evidence_summary == state.evidence_summary
        assert 'source_exit' not in state.events and 0 < deadline - time.monotonic() <= m.PREPARE_SECONDS
        if state.fail_stage == 'demand': raise m.demand.Refused('catalog_binding')
        return copy.deepcopy(state.demand_summary), copy.deepcopy(state.demand_record)
    def validate_e(value):
        m.require(type(value) is dict and set(value) == set(state.evidence_summary)
            and value['schema'] == 'synthetic-evidence-summary', 'helper_binding')
        return copy.deepcopy(value)
    def validate_d(value):
        m.require(type(value) is dict and set(value) == set(state.demand_summary)
            and value['schema'] == 'synthetic-demand-summary', 'helper_binding')
        return copy.deepcopy(value)
    def validate_private(value, *, expected_summary):
        m.require(type(value) is dict and value == state.evidence_record, 'private_binding')
        return copy.deepcopy(value)
    def preflight(*args):
        state.events.append('postflight')
        if state.fail_stage == 'postflight': raise m.Refused('source_pin')
    monkeypatch.setattr(m, 'Store', MemoryStore); monkeypatch.setattr(m, 'SourceGuard', MemoryGuard)
    monkeypatch.setattr(m.evidence, 'inspect', inspect_frame)
    monkeypatch.setattr(m.evidence, 'validate_summary', validate_e)
    monkeypatch.setattr(m.evidence, 'validate_private_record', validate_private)
    monkeypatch.setattr(m.demand, 'prepare', prepare)
    monkeypatch.setattr(m.demand, 'validate_summary', validate_d)
    monkeypatch.setattr(m, 'preflight', preflight)
    def safe_environment():
        state.events.append('safe_environment')
        if state.fail_stage == 'post_guard_environment' and 'source_return' in state.events:
            raise m.environment.EnvironmentRefused('synthetic private logging refusal')
    monkeypatch.setattr(m.environment, 'require_safe_environment', safe_environment)
    return state


def run():
    return m.run(ARGS, time.monotonic() + 100)


def test_claim_starts_one_source_read_two_direct_helpers_and_guard_return_before_both_private_publications(state):
    outcome = run()
    assert set(outcome) == {'result', 'report'}
    ordered = ['write:claim.json', 'write:source-start.json', 'source_enter', 'source_read',
        'write:analysis-start.json', 'evidence', 'demand', 'source_exit', 'source_return',
        'write:' + m.PRIVATE_NAMES[0], 'write:' + m.PRIVATE_NAMES[1], 'postflight', 'write:report.json']
    assert [state.events.index(name) for name in ordered] == sorted(state.events.index(name) for name in ordered)
    assert state.evidence_calls == state.demand_calls == 1 and state.events.count('safe_environment') == 8
    assert state.files[m.PRIVATE_NAMES[0]] == m.evidence.canonical(state.evidence_record)
    assert state.files[m.PRIVATE_NAMES[1]] == m.demand.canonical(state.demand_record)
    assert b'SYNTHETIC-EVIDENCE-PRIVATE' not in m.canonical(outcome)
    assert b'SYNTHETIC-DEMAND-PRIVATE' not in m.canonical(outcome)
    value = {'binding': m.binding(ARGS), 'outcome': outcome}
    assert m.validate_output(m.canonical(value), 0, ARGS) == value
    assert all(outcome['result'][flag] is False for flag in m.FALSE_FLAGS)


@pytest.mark.parametrize('failure', ['source_receipt', 'evidence', 'demand', 'guard_return',
    'post_guard_environment', 'evidence-private.json', 'membership-demand-private.json', 'postflight', 'report.json'])
def test_failure_is_consumed_retained_and_never_replayed_or_published_before_normal_return(state, failure):
    state.fail_stage = failure
    outcome = run(); failed = outcome['failure']
    assert failed['claim_consumed'] is True and state.stores == 1
    assert state.evidence_calls <= 1 and state.demand_calls <= 1
    if failure in ('source_receipt', 'evidence', 'demand', 'guard_return', 'post_guard_environment'):
        assert not set(m.PRIVATE_NAMES) & set(state.files)
    if failure == 'membership-demand-private.json':
        assert m.PRIVATE_NAMES[0] in state.files and m.PRIVATE_NAMES[1] not in state.files
    value = {'binding': m.binding(ARGS), 'outcome': outcome}
    assert m.validate_output(m.canonical(value), 2, ARGS) == value
    refused('claim_spent', run)


@pytest.mark.parametrize('fault', ['evidence_hash', 'demand_hash', 'evidence_count', 'demand_count',
    'source_pin', 'routing_hash', 'dispositions', 'refusals', 'demand_source', 'evidence_link',
    'evidence_private_link', 'package_root', 'lineage_root', 'combined_bound'])
def test_helpers_and_both_private_products_bind_exact_prior_summary_and_each_other(state, monkeypatch, fault):
    if fault == 'evidence_hash': state.evidence_summary['private_evidence_sha256'] = 'f' * 64
    elif fault == 'demand_hash': state.demand_summary['private_frame_sha256'] = 'f' * 64
    elif fault == 'evidence_count': state.evidence_summary['private_evidence_byte_count'] += 1
    elif fault == 'demand_count': state.demand_summary['private_frame_byte_count'] += 1
    elif fault == 'source_pin': state.evidence_summary['frame_pin']['sha256'] = 'f' * 64
    elif fault == 'routing_hash': state.evidence_summary['routing_summary_sha256'] = 'f' * 64
    elif fault == 'dispositions': state.evidence_summary['disposition_counts'] = {}
    elif fault == 'refusals': state.evidence_summary['refusal_counts'] = {}
    elif fault == 'demand_source': state.demand_summary['source_frame_pin']['sha256'] = 'f' * 64
    elif fault == 'evidence_link': state.demand_summary['evidence_summary_sha256'] = 'f' * 64
    elif fault == 'evidence_private_link': state.demand_summary['route_evidence_private_sha256'] = 'f' * 64
    elif fault == 'package_root': state.demand_summary['input_binding'] = {
        **state.demand_summary['input_binding'], 'source_package_sha256': 'f' * 64}
    elif fault == 'lineage_root': state.demand_summary['input_binding'] = {
        **state.demand_summary['input_binding'], 'source_lineage_sha256': 'f' * 64}
    else: monkeypatch.setattr(m, 'MAX_PRIVATE', max(len(m.evidence.canonical(state.evidence_record)),
        len(m.demand.canonical(state.demand_record))))
    failed = run()['failure']
    assert failed['failure_code'] in ('private_binding', 'helper_binding')
    assert not set(m.PRIVATE_NAMES) & set(state.files)


@pytest.mark.parametrize('fault', ['frame', 'routing', 'bindings', 'dispositions', 'refusals'])
def test_first_summary_anchor_is_checked_independently_before_any_demand_call(state, fault):
    summary = copy.deepcopy(state.evidence_summary)
    if fault == 'frame': summary['frame_pin']['sha256'] = 'f' * 64
    elif fault == 'routing': summary['routing_summary_sha256'] = 'f' * 64
    elif fault == 'bindings': summary['binding_contract']['binding_stream_sha256'] = 'f' * 64
    elif fault == 'dispositions': summary['disposition_counts'] = {}
    else: summary['refusal_counts'] = {}
    refused('helper_binding', lambda: m._summaries(summary))
    assert state.demand_calls == 0


@pytest.mark.parametrize('fault', ['actual2', 'actual_bool', 'report_sha', 'guard', 'analysis',
    'source_receipt', 'flag', 'AA_summary', 'AA_fact', 'extra_private', 'private_hash', 'private_missing'])
def test_success_public_output_needs_actual_exit_exact_products_closed_summary_and_both_guard_returns(state, fault):
    value = {'binding': m.binding(ARGS), 'outcome': run()}
    exit = 0; result = value['outcome']['result']
    if fault == 'actual2': exit = 2
    elif fault == 'actual_bool': exit = False
    elif fault == 'report_sha': value['outcome']['report']['sha256'] = 'f' * 64
    elif fault == 'guard': result['source_guard_returned'] = False
    elif fault == 'analysis': result['analysis_returned'] = False
    elif fault == 'source_receipt': result['source_receipt'] = None
    elif fault == 'flag': result['point_in_time_proven'] = True
    elif fault == 'AA_summary': result['aa_summary_sha256'] = 'f' * 64
    elif fault == 'AA_fact': result['aa_observed_fact_sha256'] = 'f' * 64
    elif fault == 'extra_private': result['rows'] = ['never public']
    elif fault == 'private_hash': result['private_pins'][m.PRIVATE_NAMES[0]]['sha256'] = 'f' * 64
    else: del result['private_pins'][m.PRIVATE_NAMES[1]]
    with pytest.raises(m.Refused): m.validate_output(m.canonical(value), exit, ARGS)


def test_exact_public_AA_anchor_is_metadata_only_and_binds_prior_actual_zero():
    summary = m.aa_summary()
    assert summary['private_frame_byte_count'] == m.SOURCE_PINS[m.SOURCE_NAMES[0]]['byte_count']
    assert summary['private_frame_sha256'] == m.SOURCE_PINS[m.SOURCE_NAMES[0]]['sha256']
    assert summary['routing_summary']['disposition_counts']['stocks'] == {
        'routed': 5564, 'refused': 79, 'outside_window': 508}
    assert summary['original_schema']['legacy_known_name_set_equal'] is False


@pytest.mark.parametrize('fault', ['summary_hash', 'actual_exit', 'frame_pin', 'source_head',
    'stored_fact_pin', 'decoded_fact_observation'])
def test_changed_AA_public_anchor_refuses_before_any_private_data_read(monkeypatch, fault):
    if fault == 'summary_hash':
        value = m.anchor.expected_summary(); value['private_frame_sha256'] = 'f' * 64
        monkeypatch.setattr(m.anchor, 'expected_summary', lambda: value)
    elif fault == 'stored_fact_pin':
        value = m.anchor.profile_record(); value['observed_fact_sha256'] = 'f' * 64
        monkeypatch.setattr(m.anchor, 'profile_record', lambda: value)
    else:
        value = m.anchor.observed_fact()
        if fault == 'actual_exit': value['producer']['actual_exit'] = 2
        elif fault == 'frame_pin': value['private_file']['sha256'] = 'f' * 64
        elif fault == 'source_head': value['expected_head'] = 'f' * 40
        else:
            value['producer']['dispatched_at'] = '2026-10-27T00:00:00Z'
            value['validator']['dispatched_at'] = '2026-10-27T00:00:00Z'
        monkeypatch.setattr(m.anchor, 'observed_fact', lambda: value)
    refused('aa_binding', m.aa_summary)


def test_all_selected_public_source_pins_are_fixed_current_and_do_not_refresh():
    pins = m.pins()
    assert len(pins) == 171
    for name, pin in pins.items():
        assert m.sha((m.ROOT / name).read_bytes()) == pin
    assert pins['scripts/prepare_arv2_r298_all_routes_offline_v2.py'] == m.AA_CALLER_SHA256
    assert pins['scripts/arv2_r298_aa_source_binding.py'] == \
        'e881c694b516ad7d773ab6c3a8ef996873616862dc55ffda4e371733f6c6bd11'


def test_profile_native_scope_and_single_new_consumer_boundary(monkeypatch):
    monkeypatch.setattr(m.previous, 'pins', lambda: {'scripts/existing-' + str(i) + '.py': 'd' * 64 for i in range(167)})
    monkeypatch.setattr(m, 'NEW_PINS', {name: 'e' * 64 for name in m.NEW_PINS})
    profile = m.profile_record()
    assert len(profile['source_pins']) == 171 and profile['producer_seconds'] == 750
    assert profile['outer_seconds'] == 780 and profile['direct_analysis_seconds'] == 600
    assert profile['validator_seconds'] == 20 and profile['maximum_combined_private_bytes'] == 32 * 1024 * 1024
    assert profile['private_names'] == list(m.PRIVATE_NAMES)
    assert all(profile[flag] is False for flag in m.FALSE_FLAGS)
    producer, validator = m.native_profile(mode='producer'), m.native_profile(mode='validator')
    assert '(deny network*)' in producer and '(deny network*)' in validator
    assert '/usr/bin/security' in producer and 'Library/Keychains' in producer
    assert str(m.SOURCE_DIRECTORY / m.SOURCE_NAMES[0]) in producer
    assert str(m.SOURCE_DIRECTORY / 'report.json') not in producer
    assert '01-tickers-years-full.zip' not in producer and 'sharadar_capture' not in producer
    assert 'stocks-metadata.csv' not in producer and 'funds-metadata.csv' not in producer
    assert 'R323-20261025-A11' not in producer and 'R297-20261013-D2' not in producer
    assert str(m.SOURCE_DIRECTORY) not in validator and 'assistant.dispatch_fence' not in sys.modules

@pytest.mark.parametrize('fault', ['extra', 'missing', 'bytes_bool', 'wrong_sha', 'security_hash',
    'flags', 'extra_file', 'flag_type'])
def test_source_receipt_closed_pins_and_current_only_claims(fault):
    value = source_receipt()
    if fault == 'extra': value['rows'] = []
    elif fault == 'missing': del value['files'][m.SOURCE_NAMES[0]]
    elif fault == 'bytes_bool': value['files'][m.SOURCE_NAMES[0]]['byte_count'] = True
    elif fault == 'wrong_sha': value['files'][m.SOURCE_NAMES[0]]['sha256'] = 'f' * 64
    elif fault == 'security_hash': value['files'][m.SOURCE_NAMES[0]]['current_security_sha256'] = 'invalid'
    elif fault == 'flags': value['continuous_security_proven'] = True
    elif fault == 'flag_type': value['fresh_current_security_authenticated'] = 1
    else: value['files']['claim.json'] = value['files'][m.SOURCE_NAMES[0]]
    refused('source_receipt', lambda: m.validate_source_receipt(value))


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
    state.fail_stage = 'evidence'
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
    assert b'SYNTHETIC-EVIDENCE-PRIVATE' not in m.canonical(outer)
    assert len(calls) == 2


@pytest.mark.parametrize('fault', ['zero', 'placeholder', 'conflict', 'baseline_count'])
def test_unfrozen_or_conflicting_source_pin_map_refuses(fault, monkeypatch):
    baseline = {'scripts/existing-' + str(i) + '.py': 'd' * 64 for i in range(167)}
    monkeypatch.setattr(m.previous, 'pins', lambda: baseline)
    additions = {'scripts/new.py': 'e' * 64}
    if fault == 'zero': additions['scripts/new.py'] = '0' * 64
    elif fault == 'placeholder': additions['scripts/new.py'] = 'UNFROZEN'
    elif fault == 'conflict': additions['scripts/existing-1.py'] = 'f' * 64
    else: baseline.pop('scripts/existing-1.py')
    monkeypatch.setattr(m, 'NEW_PINS', additions)
    refused('source_pin', m.pins)


@pytest.fixture
def source_fixture(tmp_path, monkeypatch):
    root = tmp_path / 'synthetic-root'; root.mkdir(mode=0o755); root.chmod(0o755)
    source = root / 'artifacts/analyst_revisions_v2/newrule_all_routes_offline/R326-20261027-AA'
    for part in (source.parent.parent.parent, source.parent.parent, source.parent, source):
        part.mkdir(mode=0o700)
    pins = {}
    for name in m.SOURCE_NAMES:
        raw = ('synthetic-full-current-data-' + name).encode()
        path = source / name; path.write_bytes(raw); path.chmod(0o600)
        pins[name] = {'byte_count': len(raw), 'sha256': m.sha(raw)}
    monkeypatch.setattr(m, 'ROOT', root); monkeypatch.setattr(m, 'SOURCE_DIRECTORY', source)
    monkeypatch.setattr(m, 'SOURCE_PINS', pins); monkeypatch.chdir(root)
    return NS(root=root, source=source, pins=pins)


def test_real_synthetic_source_guard_full_chain_both_held_files_one_read_and_normal_return(source_fixture):
    fixture = source_fixture
    with m.SourceGuard(deadline=time.monotonic() + 30) as guard:
        assert sum(row['leaf'] for row in guard.objects) == 1
        values = guard.read_once(); receipt = guard.receipt()
        assert set(values) == set(m.SOURCE_NAMES)
        assert all(m.sha(values[name]) == pin['sha256'] for name, pin in fixture.pins.items())
        refused('source_read_spent', guard.read_once)
        assert m.validate_source_receipt(receipt) == receipt
    assert guard.active is False and not guard.objects
    refused('source_state', guard.__enter__)


@pytest.mark.parametrize('change', ['content', 'mode', 'replace_name', 'extra_link', 'directory_mode'])
def test_real_synthetic_source_guard_detects_current_drift_without_repair(source_fixture, change):
    fixture = source_fixture
    with pytest.raises(m.Refused):
        with m.SourceGuard(deadline=time.monotonic() + 30) as guard:
            guard.read_once()
            path = fixture.source / m.SOURCE_NAMES[0]
            if change == 'content': path.write_bytes(b'changed')
            elif change == 'mode': path.chmod(0o644)
            elif change == 'extra_link': os.link(path, fixture.source / 'synthetic-extra-link')
            elif change == 'directory_mode': fixture.source.chmod(0o755)
            else:
                path.rename(fixture.source / 'synthetic-retained-old')
                path.write_bytes(b'changed'); path.chmod(0o600)
    assert guard.active is False and not guard.objects


def test_real_synthetic_source_guard_refuses_byte_pin_and_initial_symlink(source_fixture):
    fixture = source_fixture
    m.SOURCE_PINS[m.SOURCE_NAMES[0]]['sha256'] = 'f' * 64
    with m.SourceGuard(deadline=time.monotonic() + 30) as guard:
        refused('source_bytes', guard.read_once)
        refused('source_read_spent', guard.read_once)
    path = fixture.source / m.SOURCE_NAMES[0]
    path.rename(fixture.source / 'synthetic-retained-old')
    path.symlink_to(fixture.source / 'synthetic-retained-old')
    with pytest.raises(m.Refused):
        with m.SourceGuard(deadline=time.monotonic() + 30): pass


def test_real_new_control_store_is_exclusive_bounded_held_and_preserves_failure_leaf(tmp_path, monkeypatch):
    control = tmp_path / 'synthetic-AA-parent/synthetic-AA'
    monkeypatch.setattr(m, 'CONTROL', control)
    with m.Store() as store:
        pin = store.write('claim.json', {'synthetic': True})
        assert pin == {'byte_count': len(m.canonical({'synthetic': True})),
            'sha256': m.sha(m.canonical({'synthetic': True}))}
        private = b'synthetic-private-in-cache-only'
        private_pin = store.write_bytes(m.PRIVATE_NAMES[0], private, private=True)
        assert private_pin == {'byte_count': len(private), 'sha256': m.sha(private)}
        held = store.held[m.PRIVATE_NAMES[0]][0]
        assert store._read(held, len(private)) == private
        refused('control_name', lambda: store.write('claim.json', {}))
        refused('control_name', lambda: store.write_bytes('unexpected-private.csv', b'denied', private=True))
        refused('control_name', lambda: store.write('../elsewhere.json', {}))
        refused('control_bound', lambda: store.write_bytes('empty.json', b'', private=False))
        refused('claim_spent', m.Store)
        store.verify()
    assert control.is_dir() and {path.name for path in control.iterdir()} == {'claim.json', m.PRIVATE_NAMES[0]}
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


@pytest.mark.parametrize('deadline', [None, True, float('nan'), float('inf'), -1])
def test_invalid_deadline_refuses_before_source_or_claim_operations(deadline):
    refused('deadline', lambda: m.remaining(deadline))
    refused('deadline', lambda: m.SourceGuard(deadline=deadline))


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
