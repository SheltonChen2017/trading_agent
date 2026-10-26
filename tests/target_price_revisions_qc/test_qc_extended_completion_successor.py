"""Synthetic actual completion boundary and public-only pure rendering proofs."""
from copy import deepcopy
from datetime import date, datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest
from research.target_price_revisions_qc import extended_completion_successor as candidate
from research.target_price_revisions_qc import extended_compressed_store as gzip_store
from tests.target_price_revisions_qc.test_qc_extended_runtime import runtime, aggregate_inputs
from tests.target_price_revisions_qc.test_qc_extended_compressed_store import Native

PUBLIC = Path('research/target_price_revisions_qc')


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    import http.client
    from research.target_price_revisions_qc import extended_operations as ops
    def deny(*_args, **_kw):
        raise AssertionError('actual private, credential, provider or QC operation forbidden')
    monkeypatch.setattr(ops, 'read_private', deny)
    monkeypatch.setattr(ops, 'credential', deny)
    monkeypatch.setattr(http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(ops.Operations, '__init__', deny)
    monkeypatch.setattr(ops.subprocess, 'run', deny)


def rendered():
    old = (PUBLIC / 'extended_source_bundle_compressed.json').read_bytes()
    helper = (PUBLIC / 'extended_completion_successor.py').read_bytes()
    return old, helper, candidate.render_completion_bundle(old,
        helper_raw=helper, expected_helper_sha256=hashlib.sha256(helper).hexdigest())


def load_helper(monkeypatch, *, mutant=False):
    module = ModuleType('extended_completion_successor')
    source = (PUBLIC / 'extended_completion_successor.py').read_text()
    if mutant:
        source = source.replace('cap_snapshots, list(records))', 'cap_snapshots, records)')
    exec(compile(source, 'extended_completion_successor.py', 'exec'), module.__dict__)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module


def finish_algorithm(runtime, monkeypatch, files, helper):
    deferred = ModuleType('extended_runtime_successor')
    exec(compile((PUBLIC / 'extended_runtime_successor.py').read_bytes(),
        'extended_runtime_successor.py', 'exec'), deferred.__dict__)
    monkeypatch.setitem(sys.modules, deferred.__name__, deferred)
    monkeypatch.setitem(sys.modules, 'extended_completion_successor', helper)
    monkeypatch.setitem(sys.modules, 'extended_compressed_store', gzip_store)
    module = ModuleType('synthetic_completion_main')
    exec(compile(files['main.py'], 'main.py', 'exec'), module.__dict__)
    algo = module.TargetPriceExtendedAlgorithm()
    # Fixed generated config literal; never execute unrelated cloud statements.
    import ast
    config_text = ast.literal_eval(ast.parse(files['extended_config.py']).body[0].value)
    algo._config = json.loads(config_text)
    algo.project_id, algo.algorithm_id = 123, 'synthetic-completion-job'
    algo._evidence = deferred.DeferredPrivateEvidence({
        'candidate_id': algo._config['candidate_id'], 'config_sha256': module.EXPECTED_CONFIG_SHA256,
        'freeze_sha256': runtime.core.FREEZE_SHA256, 'input_hashes': algo._config['input_hashes'],
        'attempt': module.EXPECTED_ATTEMPT}, lambda: (algo.project_id, algo.algorithm_id, True))
    coverage, membership, caps, records = aggregate_inputs(runtime)
    for raw in records:
        row = json.loads(raw)
        algo._evidence.append(row['kind'], row['payload'])
    algo._decision_coverage, algo._membership_coverage_by_day = coverage, membership
    algo._cap_snapshot_coverage_by_day = caps
    for name in ('_decision_count', '_refused_count', '_submitted', '_fill_events',
                 '_requested_shares', '_submitted_shares', '_filled_shares',
                 '_position_ledger_mismatches', '_risk_breaches', '_name_soft_cap_breaches'):
        setattr(algo, name, 0)
    for name in ('_fees', '_max_cash_residual', '_max_nav_residual', '_max_name_exposure'):
        setattr(algo, name, Fraction(0))
    algo._valuation_days = set(runtime.core.VALUATIONS[:2])
    algo._prior_close_day = date(2026, 10, 9)
    algo._attempted_days, algo._reasons, algo._clock_assertions = set(), {}, {}
    algo._warmup_finished_minute_validated = False
    algo._delisting_audit = module.cap_observer.empty_audit()
    algo.utc_time = datetime(2026, 10, 10, tzinfo=timezone.utc)
    algo._native_clock = lambda value, _zone: value
    algo.object_store, algo.logged = Native(), []
    algo.log = algo.logged.append
    return algo, records


def test_actual_end_method_red_old_tuple_boundary_green_successor_and_gzip_export(runtime, monkeypatch):
    old_raw, _, output = rendered(); old = json.loads(old_raw)
    helper = load_helper(monkeypatch)
    old_off = next(row for row in old['candidates'] if json.loads(row['config_raw'])['arm'] == 'tpr_off')
    fixed_off = next(row for row in output['candidates'] if json.loads(row['config_raw'])['arm'] == 'tpr_off')
    broken, original_records = finish_algorithm(runtime, monkeypatch, old_off['files'], helper)
    with pytest.raises(ValueError, match='bounded aggregate inputs required'):
        broken.on_end_of_algorithm()
    assert broken.logged == [] and broken.object_store.saves == [] and not broken._evidence.closed
    fixed, _ = finish_algorithm(runtime, monkeypatch, fixed_off['files'], helper)
    before = fixed._evidence.records
    fixed.on_end_of_algorithm()
    assert fixed._evidence.closed and len(fixed.logged) == 2
    assert fixed.logged[0].startswith('EXT26_SUMMARY ') and fixed.logged[1].startswith('EXT26_EVIDENCE_INDEX ')
    summary = json.loads(fixed.logged[0].split(' ', 1)[1])
    pointer = json.loads(fixed.logged[1].split(' ', 1)[1])
    assert summary['attempt'] == pointer['attempt'] == 3
    assert summary['internally_meaningful_execution'] is False and summary['coverage_complete'] is False
    assert summary['strategy_accepted'] is pointer['strategy_accepted'] is False
    assert pointer['records'] == len(original_records) + 1
    assert fixed._evidence.records[:len(before)] == before
    assert all(key.endswith('.json.gz') for key in fixed.object_store.saves)
    assert all('/123/synthetic-completion-job/' in key for key in fixed.object_store.saves)
    assert 'SECRET_LICENSED_SYMBOL' not in ''.join(fixed.logged)


def test_completion_fix_mutation_detected_in_memory(runtime, monkeypatch):
    _, _, output = rendered()
    off = next(row for row in output['candidates'] if json.loads(row['config_raw'])['arm'] == 'tpr_off')
    mutant = load_helper(monkeypatch, mutant=True)
    broken, _ = finish_algorithm(runtime, monkeypatch, off['files'], mutant)
    with pytest.raises(ValueError, match='bounded aggregate inputs required'):
        broken.on_end_of_algorithm()
    assert not broken.logged and not broken.object_store.saves and not broken._evidence.closed


def test_corrected_completion_export_failure_never_logs_success_or_closes(runtime, monkeypatch):
    _, _, output = rendered()
    off = next(row for row in output['candidates'] if json.loads(row['config_raw'])['arm'] == 'tpr_off')
    fixed, _ = finish_algorithm(runtime, monkeypatch, off['files'], load_helper(monkeypatch))
    fixed.object_store.save_bytes = lambda *_args: False
    with pytest.raises(ValueError):
        fixed.on_end_of_algorithm()
    assert not fixed.logged and not fixed._evidence.closed
    assert fixed._evidence.counts['SUMMARY'] == 1


def test_tuple_copy_exact_aggregate_parity_and_unmodified_original_journal(runtime):
    inputs = aggregate_inputs(runtime)
    old_records = tuple(inputs[-1]); before = deepcopy(old_records)
    observed = candidate.public_run_aggregates_snapshot(*inputs[:3], old_records)
    assert observed == runtime.core.public_run_aggregates(*inputs)
    assert old_records == before


@pytest.mark.parametrize('kind', ['list', 'iterator', 'record_count', 'record_bytes',
    'run_bytes', 'unknown_kind', 'duplicate_key', 'extra', 'float', 'nan', 'duplicate_nav', 'foreign_nav'])
def test_admission_keeps_original_schema_content_count_and_byte_bounds(runtime, monkeypatch, kind):
    records = tuple(aggregate_inputs(runtime)[-1])
    if kind == 'list': records = list(records)
    if kind == 'iterator': records = iter(records)
    if kind == 'record_count': monkeypatch.setattr(runtime.core, 'MAX_EVIDENCE_RECORDS', len(records) - 1)
    if kind == 'record_bytes': monkeypatch.setattr(runtime.core, 'MAX_RECORD_BYTES', 5)
    if kind == 'run_bytes': monkeypatch.setattr(runtime.core, 'MAX_EVIDENCE_BYTES', 5)
    if kind == 'unknown_kind': records = ('{"kind":"UNKNOWN","payload":{}}',)
    if kind == 'duplicate_key': records = ('{"kind":"ACTION","kind":"ACTION","payload":{}}',)
    if kind == 'extra': records = ('{"kind":"ACTION","payload":{},"extra":true}',)
    if kind == 'float': records = ('{"kind":"ACTION","payload":{"value":1.0}}',)
    if kind == 'nan': records = ('{"kind":"ACTION","payload":{"value":NaN}}',)
    if kind == 'duplicate_nav': records = (records[0], records[0])
    if kind == 'foreign_nav': records = (records[0].replace(runtime.core.VALUATIONS[0], '2050-01-01'),)
    with pytest.raises(ValueError):
        candidate.public_run_aggregates_snapshot({}, {}, {}, records)


def test_render_preserves_all_economics_inputs_old_cloud_modules_and_narrow_main_diff():
    raw, helper, observed = rendered(); old = json.loads(raw)
    assert observed['inputs'] == old['inputs'] and observed['preparation_sha256'] == old['preparation_sha256']
    assert len(observed['repository_sources']) == 30
    assert candidate.PREDECESSOR_BUNDLE in observed['repository_sources']
    for previous, current in zip(old['candidates'], observed['candidates']):
        assert set(current['files']) == set(previous['files']) | {candidate.HELPER}
        assert current['files'][candidate.HELPER].encode() == helper
        for name in set(previous['files']) - {'main.py'}:
            assert current['files'][name] == previous['files'][name]
        for name in ('candidate_id', 'project_name', 'config_raw', 'input_hashes'):
            assert current[name] == previous[name]
        restored = current['files']['main.py'].replace(candidate.NEW_IMPORT, candidate.OLD_IMPORT)
        restored = restored.replace(candidate.NEW_CALL, candidate.OLD_CALL)
        if current['planned_attempt'] == 3:
            restored = restored.replace('EXPECTED_ATTEMPT = 3\n', 'EXPECTED_ATTEMPT = 2\n')
        assert restored == previous['files']['main.py']
        assert len(current['files']['main.py'].encode()) <= 60000


@pytest.mark.parametrize('kind', ['predecessor', 'helper_hash', 'helper_quota'])
def test_render_refuses_alternate_unreviewed_input_or_helper_bytes(kind):
    old, helper, _ = rendered(); identity = hashlib.sha256(helper).hexdigest()
    if kind == 'predecessor': old += b' '
    if kind == 'helper_hash': identity = 'a' * 64
    if kind == 'helper_quota': helper = b'#' * 60001; identity = hashlib.sha256(helper).hexdigest()
    with pytest.raises(ValueError):
        candidate.render_completion_bundle(old, helper_raw=helper, expected_helper_sha256=identity)
