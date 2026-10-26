"""Synthetic-only inventory proofs; actual roots/credentials/transport denied."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path

import pytest
from research.target_price_revisions_qc import extended_result_inventory as d

reader, e, N = d.reader, d.e, d.e.JsonNumber
ACTUAL_LANE = d.LANE
spec = importlib.util.spec_from_file_location('synthetic_result_inventory_fixture', Path(__file__).with_name('test_qc_extended_result_driver.py'))
rf = importlib.util.module_from_spec(spec); spec.loader.exec_module(rf)


@pytest.fixture(autouse=True)
def forbidden_actual(monkeypatch):
    def denied(*_a, **_kw): raise AssertionError('actual private filesystem, credential, subprocess or network forbidden')
    monkeypatch.setattr(reader.ops, 'credential', denied)
    monkeypatch.setattr(reader.ops.http.client, 'HTTPSConnection', denied)
    monkeypatch.setattr(reader.ops.Operations, '__init__', denied)
    monkeypatch.setattr(d.subprocess, 'run', denied)
    original = reader._open_directory
    def external(path):
        if path == ACTUAL_LANE or path.is_relative_to(ACTUAL_LANE): denied()
        return original(path)
    monkeypatch.setattr(reader, '_open_directory', external)


def setup(tmp_path, *, action='diagnostics', compile_failure=False):
    data, arguments = rf.evidence_fixture(action, compile_failure=compile_failure)
    sources = rf.sources(); sources[d.SOURCE_RELATIVE] = b'# explicit synthetic inventory source\n'
    clock = datetime.now(timezone.utc)
    plan = d._plan(source_hashes={name: reader._sha(raw) for name, raw in sources.items()}, git_head='c' * 40,
        owner_instruction_sha256='f' * 64, created_utc=(clock - timedelta(seconds=1)).isoformat(),
        expires_utc=(clock + timedelta(hours=1)).isoformat(), read_operation_id='TPR-EXT26-INVENTORY-SYNTHETIC-001',
        mode='offline-fixture', **arguments)
    root = tmp_path / 'inventory-private'; root.mkdir(mode=0o700)
    for role, raw in data.items():
        (root / plan['files'][role]).write_bytes(raw); (root / plan['files'][role]).chmod(0o600)
    return plan, sources, root, data, clock


def execute(fixture, **kw):
    plan, sources, root, _, clock = fixture
    return e.parse_json(d._execute(plan, sources, root, clock=kw.pop('clock', lambda: clock), guard=kw.pop('guard', lambda *_: None), **kw))


def rewrite(fixture, role, body):
    raw = e.canonical(body)
    (fixture[2] / fixture[0]['files'][role]).write_bytes(raw); (fixture[2] / fixture[0]['files'][role]).chmod(0o600)
    fixture[3][role] = raw


@pytest.mark.parametrize('action,failure,count', [('diagnostics', False, 9), ('diagnostics', True, 5), ('metrics', False, 17)])
def test_complete_exact_inventory_can_feed_unchanged_reader(tmp_path, action, failure, count):
    fixture = setup(tmp_path, action=action, compile_failure=failure); result = execute(fixture)
    assert result['status'] == 'COMPLETED' and result['own_job_lineage_verified'] is True
    assert result['native_collection_lineage_verified'] is (action == 'metrics')
    assert len(result['inventory']) == count and result['read_bytes'].fraction() == sum(map(len, fixture[3].values()))
    assert result['read_attempts'].fraction() == count and result['failed_read_body_bytes_unknown'] is False
    inventory = e.canonical(result['inventory'])
    assert reader._sha(inventory) == result['inventory_sha256'] and len(inventory) == result['inventory_bytes'].fraction()
    assert result['inventory'] == result['read_inventory']
    old_arguments = {key: fixture[0][key] for key in ('git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc',
        'qc_operation_id', 'candidate_id', 'attempt', 'project_id', 'backtest_id', 'action', 'collection_sequence', 'order_pages', 'mode')}
    old_arguments.update(source_hashes={name: reader._sha(raw) for name, raw in rf.sources().items()},
        read_operation_id='TPR-EXT26-RESULT-SYNTHETIC-AFTER-INVENTORY', inventory=e.parse_json(inventory))
    reader._validate_plan(reader._plan(**old_arguments))
    assert result['accounting_metrics_computed'] is result['original_strategy_intent_verified'] is False
    output = e.canonical(result)
    for forbidden in (b'SECRET-TOKEN', b'PRIVATE-USER', b'PRIVATE-TICKER', b'order_id', b'nav_metrics', b'code_frames'): assert forbidden not in output


def test_off_reads_only_its_fixed_result_files_no_signal_input_resources(tmp_path, monkeypatch):
    off = next(candidate for candidate, arm in e.CANDIDATES.items() if arm == 'tpr_off')
    monkeypatch.setattr(rf.nf, 'CANDIDATE', off)
    fixture = setup(tmp_path, action='metrics'); result = execute(fixture)
    assert result['status'] == 'COMPLETED' and result['candidate_id'] == off
    assert result['signal_input_reads'].fraction() == result['provider_input_reads'].fraction() == 0
    assert set(fixture[0]['files']) == set(result['inventory'])
    assert not any('inputs/' in name or 'capture' in name or 'signal_packet' in name for name in fixture[0]['files'].values())


def test_claim_precedes_stat_hash_and_body_reads_and_second_use_refuses(tmp_path, monkeypatch):
    fixture = setup(tmp_path); plan, _, root, _, _ = fixture; original = d.os.stat
    def observing(path, *a, **kw):
        if 'dir_fd' in kw:
            assert (root / (plan['read_operation_id'] + '.claim.spent.json')).exists()
        return original(path, *a, **kw)
    monkeypatch.setattr(d.os, 'stat', observing)
    assert execute(fixture)['status'] == 'COMPLETED'
    with pytest.raises(FileExistsError): execute(fixture)


@pytest.mark.parametrize('field,value', [('private_root', '/other'), ('max_file_bytes', 999999999), ('network', True),
    ('new_looks', 1), ('order_pages', 500), ('files', {'operator': 'operator-state.db'}), ('source_hashes', {})])
def test_tampered_scope_refuses_before_claim(tmp_path, field, value):
    fixture = setup(tmp_path); fixture[0][field] = value
    with pytest.raises((ValueError, KeyError)): execute(fixture)
    assert not list(fixture[2].glob('*.claim.spent.json'))


def test_expired_scope_moved_head_and_source_tamper_refuse_before_claim(tmp_path):
    fixture = setup(tmp_path)
    with pytest.raises(ValueError): execute(fixture, clock=lambda: fixture[4] + timedelta(days=3))
    with pytest.raises(ValueError): execute(fixture, guard=lambda *_: d._fail())
    fixture[1][d.SOURCE_RELATIVE] += b'# mutated\n'
    with pytest.raises(ValueError): execute(fixture)
    assert not list(fixture[2].glob('*.claim.spent.json'))


@pytest.mark.parametrize('fault', ['missing', 'symlink', 'hardlink', 'mode', 'fifo', 'oversize', 'aggregate'])
def test_metadata_custody_and_joint_budget_failures_remain_spent_without_inventory(tmp_path, fault, monkeypatch):
    if fault == 'oversize': monkeypatch.setattr(d, 'MAX_FILE', 100)
    if fault == 'aggregate': monkeypatch.setattr(d, 'MAX_TOTAL', 100)
    fixture = setup(tmp_path); target = fixture[2] / fixture[0]['files']['operations_manifest']
    if fault == 'missing': target.unlink()
    elif fault == 'symlink': target.unlink(); target.symlink_to(fixture[2] / 'absent')
    elif fault == 'hardlink': os.link(target, fixture[2] / 'other')
    elif fault == 'mode': target.chmod(0o644)
    elif fault == 'fifo': target.unlink(); os.mkfifo(target, 0o600)
    result = execute(fixture)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['scope_spent'] is True
    assert result['inventory'] is None and result['inventory_sha256'] is None
    assert result['read_attempts'].fraction() == 1 and result['failed_read_body_bytes_unknown'] is True
    if fault in {'oversize', 'aggregate'}: assert result['read_bytes'].fraction() == 0


@pytest.mark.parametrize('fault', ['job', 'project', 'candidate', 'terminal_job', 'closure', 'source_readback'])
def test_independent_original_job_and_execution_lineage_not_caller_assertion(tmp_path, fault):
    fixture = setup(tmp_path)
    if fault == 'job': fixture[0]['backtest_id'] = 'foreign-job'
    elif fault == 'project': fixture[0]['project_id'] = 999
    elif fault == 'candidate':
        # Rebind the requested target without changing original retained bytes.
        fixture[0]['candidate_id'] = next(name for name, arm in e.CANDIDATES.items() if arm == 'tpr_off')
        fixture[0]['files'] = d._FIXED_NAMES(fixture[0]['candidate_id'], 1, fixture[0]['qc_operation_id'], 'diagnostics', True, 0, 0)
    elif fault == 'terminal_job':
        terminal = e.parse_json(fixture[3]['terminal']); terminal['response']['backtest']['backtestId'] = 'foreign-job'
        rewrite(fixture, 'terminal', terminal)
    elif fault == 'closure':
        closure = e.parse_json(fixture[3]['closure']); closure['outcome'] = 'unknown'; rewrite(fixture, 'closure', closure)
    else:
        readback = e.parse_json(fixture[3]['readback']); readback['response']['files'][0]['content'] += '# altered\n'; rewrite(fixture, 'readback', readback)
    result = execute(fixture)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['own_job_lineage_verified'] is False
    assert result['inventory'] is None


@pytest.mark.parametrize('fault', ['collection_job', 'collection_candidate', 'collection_pages', 'page_job', 'page_project',
    'page_scope', 'page_count', 'page_id', 'page_receipt', 'nav_job', 'summary_job', 'summary_unknown', 'incomplete_nav'])
def test_native_collection_and_compact_receipts_independently_bound(tmp_path, fault):
    fixture = setup(tmp_path, action='metrics')
    role = 'orders_collection' if fault.startswith('collection_') else 'nav_envelope' if fault in {'nav_job', 'incomplete_nav'} else 'summary_envelope' if fault.startswith('summary_') else 'orders_page_0'
    body = e.parse_json(fixture[3][role])
    if fault == 'collection_job': body['backtest_id'] = 'foreign-job'
    elif fault == 'collection_candidate': body['candidate_id'] = 'foreign-candidate'
    elif fault == 'collection_pages': body['pages'] = []
    elif fault in {'page_job', 'nav_job'}: body['request']['backtestId'] = 'foreign-job'
    elif fault == 'page_project': body['request']['projectId'] = N('999')
    elif fault == 'page_scope': body['request']['end'] = N('100')
    elif fault == 'page_count': body['response']['length'] = N('2')
    elif fault == 'page_id': body['response']['orders'][0]['id'] = True
    elif fault == 'page_receipt': body['returned_identity_checks']['absent_identifiers_inferred'] = True
    elif fault == 'summary_job': body['request']['backtestId'] = 'foreign-job'
    elif fault == 'summary_unknown': body['response']['success'] = False
    else: body['response']['chart']['series']['NAV']['values'].pop()
    rewrite(fixture, role, body)
    result = execute(fixture)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['inventory'] is None
    assert result['native_collection_lineage_verified'] is False


def test_exact_zero_order_collection_is_metadata_not_meaningful_execution(tmp_path):
    fixture = setup(tmp_path, action='metrics')
    envelopes, collection = rf.nf.order_fixture([])
    rewrite(fixture, 'orders_collection', collection)
    rewrite(fixture, 'orders_page_0', e.parse_json(envelopes[0]))
    result = execute(fixture)
    assert result['status'] == 'COMPLETED' and result['native_collection_lineage_verified'] is True
    assert result['accounting_metrics_computed'] is result['canonical_admission'] is False


def test_120_second_deadline_retains_spent_scope(tmp_path, monkeypatch):
    fixture = setup(tmp_path); sequence = iter([0, 0, 0, 121])
    monkeypatch.setattr(d.time, 'monotonic', lambda: next(sequence))
    result = execute(fixture)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['scope_spent'] is True


def test_real_root_cannot_be_fixture_target_and_import_rebinding_refuses(tmp_path, monkeypatch):
    fixture = setup(tmp_path)
    with pytest.raises(ValueError): d._execute(fixture[0], fixture[1], d.PRIVATE_ROOT, clock=lambda: fixture[4], guard=lambda *_: None)
    monkeypatch.setattr(reader, '_names', lambda *_: {})
    with pytest.raises(ValueError): d._verify_imports()


def test_cli_has_no_generic_path_or_fixture_callback_and_redacts_failures(monkeypatch, capsys):
    def denied(**_kw): raise RuntimeError('SECRET-TOKEN should not be printed')
    monkeypatch.setattr(d, 'run_inventory', denied)
    arguments = ['--read-operation-id', 'TPR-EXT26-INVENTORY-SYNTHETIC-001', '--qc-operation-id', 'synthetic-operation-001',
        '--candidate-id', rf.nf.CANDIDATE, '--attempt', '1', '--project-id', '123', '--backtest-id', 'none', '--action', 'diagnostics',
        '--owner-instruction-sha256', 'f' * 64, '--created-utc', '2026-10-10T00:00:00Z', '--expires-utc', '2026-10-11T00:00:00Z']
    assert d.main(arguments) == 1
    raw = capsys.readouterr().out.encode()
    assert b'SECRET' not in raw and set(e.parse_json(raw)) == {'status', 'scope_spent', 'automatic_retry'}
