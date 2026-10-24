"""Synthetic four-file paired processing; actual private/API access is denied."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path

import pytest

from research.target_price_revisions_qc import extended_paired_results as p

e, N = p.e, p.e.JsonNumber
PUBLIC_ROOT = Path(__file__).resolve().parents[2]
CALENDAR = (PUBLIC_ROOT / (p.PREFIX + 'extended_calendar.json')).read_bytes()
BUNDLE = (PUBLIC_ROOT / p.BUNDLE).read_bytes()
CONFIGS = p._configurations(BUNDLE)
spec = importlib.util.spec_from_file_location('synthetic_paired_result_fixture', Path(__file__).with_name('test_qc_extended_result_driver.py'))
rf = importlib.util.module_from_spec(spec); spec.loader.exec_module(rf)


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def denied(*a, **kw): raise AssertionError('actual private, credentials, subprocess or network forbidden')
    monkeypatch.setattr(p.ops, 'credential', denied)
    monkeypatch.setattr(p.ops.http.client, 'HTTPSConnection', denied)
    monkeypatch.setattr(p.ops.Operations, '__init__', denied)
    monkeypatch.setattr(p.subprocess, 'run', denied)
    original = p.reader._open_directory
    def external(path):
        if path == p.LANE or path.is_relative_to(p.LANE): denied()
        return original(path)
    monkeypatch.setattr(p.reader, '_open_directory', external)


def setup(tmp_path, *, off_attempt=2):
    now = datetime.now(timezone.utc)
    sources = {name: b'# synthetic committed helper\n' for name in p.SOURCE_PATHS}
    sources[p.BUNDLE], sources[p.PREFIX + 'extended_calendar.json'] = BUNDLE, CALENDAR
    source_hashes = {name: p._sha(raw) for name, raw in sources.items()}
    fixture_data, base_arguments = rf.evidence_fixture('metrics')
    base_manifest = e.parse_json(fixture_data['execution_manifest'])
    original, _ = p.reader._metrics(base_arguments, base_manifest, 'synthetic-compile', fixture_data, CALENDAR)
    arms, data = {}, {}
    for arm in p.ARMS:
        config = CONFIGS[arm]; candidate = config['candidate_id']; attempt = 1 if arm == 'tpr_on' else off_attempt
        project, job = p.PROJECTS[arm], 'synthetic-' + arm + '-job'
        read_operation = 'TPR-EXT26-RESULT-V2-' + arm.replace('_', '-') + '-METRICS-001'
        operation = 'TPR-EXT26-QC-20261010-003'
        cloud_hashes = {key: 'd' * 64 for key in p.SHARED_MODULES | {'main.py', 'extended_config.py'}}
        cloud_hashes['main.py'] = ('a' if arm == 'tpr_on' else 'b') * 64
        series = e.parse_json(fixture_data['nav_series'])
        if arm == 'tpr_off':
            for row in series: row['nav'] = N('99999')
        nav = e.canonical(series)
        body = deepcopy(original)
        body.update(candidate_id=candidate, attempt=attempt, project_id=project, backtest_id=job,
            source_hashes=cloud_hashes, config_sha256=config['config_sha256'], input_hashes=config['input_hashes'])
        binding = body['metrics_binding']
        for key in ('candidate_id', 'project_id', 'backtest_id', 'source_hashes', 'config_sha256', 'input_hashes'): binding[key] = body[key]
        binding['series_sha256'] = p._sha(nav)
        body['nav_metrics'] = p.metrics.nav_metrics(nav, CALENDAR, expected_series_sha256=p._sha(nav))
        for census in (body['nav_census'], body['order_census']):
            census.update(candidate_id=candidate, attempt=attempt, project_id=project, backtest_id=job)
        body['nav_census']['normalized_series_sha256'] = p._sha(nav)
        summary = body['summary']
        summary.update(candidate_id=candidate, arm=arm, attempt=attempt, project_id=project, job_id=job,
            config_sha256=config['config_sha256'], input_hashes=config['input_hashes'], valuation_days=1449)
        index = body['evidence_index_receipt']
        index.update(candidate_id=candidate, attempt=attempt, project_id=project, job_id=job, config_sha256=config['config_sha256'])
        index['index_key'] = 'tpr-ext26/evidence/' + candidate + '/' + config['config_sha256'] + '/attempt-' + str(attempt) + '/' + str(project) + '/' + job + '/index.json'
        for key, field in (('summary_aggregate_sha256', 'summary'), ('index_aggregate_sha256', 'evidence_index_receipt')):
            body[key] = binding[key] = p._sha(e.canonical(body[field]))
        inventory = {key: {'sha256': p._sha(raw), 'bytes': len(raw)} for key, raw in fixture_data.items()}
        inventory['nav_series'] = {'sha256': p._sha(nav), 'bytes': len(nav)}
        look = {'schema': 'tpr-ext26-look-v2', 'at': (now - timedelta(minutes=1)).isoformat(), 'candidate_id': candidate,
            'attempt': attempt, 'manifest_sha256': inventory['operations_manifest']['sha256'],
            'execution_manifest_sha256': inventory['execution_manifest']['sha256'], 'config_sha256': config['config_sha256'],
            'source_hashes': cloud_hashes, 'input_hashes': config['input_hashes'], 'consumed': True, 'fixture': False,
            'old_looks': 17 if arm == 'tpr_off' else 16 + off_attempt,
            'baseline_observed_looks': 16, 'persistent_observed_looks_before': 1 if arm == 'tpr_off' else off_attempt,
            'observed_total_before': 17 if arm == 'tpr_off' else 16 + off_attempt, 'look_census_sha256': 'c' * 64}
        result = {'schema': 'tpr-ext26-result-reader-successor-receipt-v1', 'study_id': e.STUDY_ID,
            'read_operation_id': read_operation, 'candidate_id': candidate, 'attempt': attempt, 'project_id': project,
            'backtest_id': job, 'qc_operation_id': operation, 'action': 'metrics', 'status': 'COMPLETED', 'scope_spent': True,
            'plan_sha256': 'f' * 64, 'git_head': 'c' * 40, 'source_hashes': {name: source_hashes[name] for name in p.strict.SOURCE_PATHS},
            'owner_instruction_sha256': 'f' * 64, 'predecessor_reader_sha256': p.strict.READER_SHA256,
            'strict_inventory_source_sha256': p.strict.INVENTORY_SUCCESSOR_SHA256,
            'strict_read_policy': 'opened-descriptor-exact-expected-size-and-remaining-before-body-v1', 'read_inventory': inventory,
            'read_bytes': sum(row['bytes'] for row in inventory.values()), 'read_attempts': len(inventory),
            'failed_read_body_bytes_unknown': False,
            'read_bytes_semantics': 'retained custody-verified bytes; unsuccessful-read body bytes may be unknown',
            'body_budget_and_expected_size_enforced_before_read': True, 'terminal_status': 'Completed.', 'compile_id': body['compile_id'],
            'diagnostic': {'known_error_types': [], 'code_frames': [], 'private_error_text_returned': False, 'unknown_error_classification': True},
            'metrics': body, 'private_output_hashes': {'normalized-orders.0': body['order_census']['normalized_page_sha256'][0],
                'order-observations.0': body['order_census']['observation_page_sha256'][0]},
            'automatic_retry': False, 'old_receipts_renewed': False, 'new_looks': 0, 'quantconnect_attempts': 0,
            'full_cloud_journal_exported': False, 'independent_input_row_replay': False, 'canonical_admission': False, 'trading': False,
            'ended_utc': now.isoformat()}
        raw = e.canonical(result)
        arms[arm] = {'candidate_id': candidate, 'attempt': attempt, 'project_id': project, 'backtest_id': job,
            'read_operation_id': read_operation, 'qc_operation_id': operation, 'config_sha256': config['config_sha256'],
            'source_hashes': cloud_hashes, 'input_hashes': config['input_hashes'], 'result_sha256': p._sha(raw), 'result_bytes': len(raw),
            'nav_sha256': p._sha(nav), 'nav_bytes': len(nav), 'look_receipt_sha256': p._sha(e.canonical(look)), 'look': look,
            'collection_operations_manifest_sha256': inventory['operations_manifest']['sha256']}
        data[arm + '_result'], data[arm + '_nav'] = raw, nav
    plan = p._plan(source_hashes=source_hashes, git_head='c' * 40, owner_instruction_sha256='f' * 64,
        created_utc=(now - timedelta(seconds=1)).isoformat(), expires_utc=(now + timedelta(hours=24, seconds=-1)).isoformat(),
        processing_operation_id='TPR-EXT26-PAIRED-SYNTHETIC-001', arms=e.parse_json(e.canonical(arms)),
        expected_observed_looks=17 + off_attempt, mode='offline-fixture')
    root = tmp_path / 'synthetic-paired'; root.mkdir(mode=0o700)
    for role, descriptor in plan['files'].items():
        (root / descriptor['name']).write_bytes(data[role]); (root / descriptor['name']).chmod(0o600)
    return plan, sources, root, data, now


def execute(fixture, **changes):
    plan, sources, root, _, now = fixture
    return e.parse_json(p._execute(plan, sources, root, clock=changes.pop('clock', lambda: now), guard=changes.pop('guard', lambda *_: None), **changes))


def rebind(fixture, arm, modifier):
    plan, _, root, data, _ = fixture; role = arm + '_result'
    value = e.parse_json(data[role]); modifier(value); raw = e.canonical(value)
    data[role] = raw; (root / plan['files'][role]['name']).write_bytes(raw)
    plan['arms'][arm]['result_sha256'] = p._sha(raw); plan['arms'][arm]['result_bytes'] = N(str(len(raw)))
    plan['files'] = p._files(plan['arms'])


@pytest.mark.parametrize('off_attempt', [2, 3])
def test_exact_four_reads_pair1449_nav_preserves_null_costs_and_no_acceptance(tmp_path, off_attempt):
    fixture = setup(tmp_path, off_attempt=off_attempt); result = execute(fixture)
    assert result['status'] == 'COMPLETED', result
    assert result['scope_spent'] is True and len(result['read_inventory']) == 4
    assert result['read_bytes'].fraction() == sum(map(len, fixture[3].values()))
    paired = result['result']; assert paired['paired_metrics']['on']['observations'].fraction() == 1449
    assert paired['paired_metrics']['off']['observations'].fraction() == 1449
    assert paired['paired_metrics']['last_nav_difference_usd'] == {'numerator': '1', 'denominator': '1'}
    assert paired['arm_evidence']['tpr_on']['execution_metrics']['complete_reported_fees_usd'] is None
    assert paired['arm_evidence']['tpr_off']['execution_metrics']['complete_reported_gross_turnover_decimal'] is None
    assert paired['classification'] == 'diagnostic_paired_native_evidence'
    assert paired['strategy_accepted'] is paired['confirmatory_alpha'] is paired['quantconnect_ready'] is False
    assert result['new_looks'].fraction() == result['quantconnect_attempts'].fraction() == 0
    assert result['expected_observed_looks'].fraction() == 17 + off_attempt
    assert b'PRIVATE-TICKER' not in e.canonical(result) and b'normalized-orders.0' not in e.canonical(result)
    with pytest.raises(FileExistsError): execute(fixture)


@pytest.mark.parametrize('fault', ['job', 'project', 'terminal', 'scope', 'source', 'config', 'input', 'look', 'fees', 'extra',
    'future_clock', 'nav_clock', 'nav_census', 'order_collection', 'order_pages', 'order_outputs', 'order_extra'])
def test_rebound_receipt_hash_cannot_admit_foreign_or_unverified_evidence(tmp_path, fault):
    fixture = setup(tmp_path)
    def alter(result):
        if fault == 'job': result['backtest_id'] = 'foreign-job'
        elif fault == 'project': result['project_id'] = 42
        elif fault == 'terminal': result['terminal_status'] = 'Runtime Error'
        elif fault == 'scope': result['scope_spent'] = False
        elif fault == 'source': result['metrics']['source_hashes']['cap_tilt.py'] = '0' * 64
        elif fault == 'config': result['metrics']['config_sha256'] = '0' * 64
        elif fault == 'input': result['metrics']['input_hashes']['preparation.json'] = '0' * 64
        elif fault == 'look': result['read_inventory']['execution_manifest']['sha256'] = '0' * 64
        elif fault == 'fees': result['metrics']['execution_metrics']['complete_reported_fees_usd'] = {'numerator': '0', 'denominator': '1'}
        elif fault == 'extra': result['unrelated_licensed_rows'] = ['PRIVATE-TICKER']
        elif fault == 'future_clock': result['ended_utc'] = (fixture[4] + timedelta(seconds=1)).isoformat()
        elif fault == 'nav_clock': result['metrics']['nav_census']['observation_clock'] = '16:00:00 America/New_York'
        elif fault == 'nav_census': result['metrics']['nav_census']['observations'] = 1448
        elif fault == 'order_collection': result['metrics']['order_census']['collection_sha256'] = '0' * 64
        elif fault == 'order_pages': result['metrics']['order_census']['page_count'] = 2
        elif fault == 'order_outputs': result['private_output_hashes']['normalized-orders.0'] = '0' * 64
        else: result['metrics']['order_census']['licensed_rows'] = ['PRIVATE-TICKER']
    rebind(fixture, 'tpr_on', alter); result = execute(fixture)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['scope_spent'] is True and result['result'] is None
    assert b'PRIVATE-TICKER' not in e.canonical(result)


@pytest.mark.parametrize('fault', ['missing', 'hash', 'size', 'mode', 'symlink', 'hardlink', 'fifo'])
def test_exact_descriptor_failure_retains_claim_and_null_pair(tmp_path, fault):
    fixture = setup(tmp_path); plan, _, root, _, _ = fixture
    descriptor = plan['files']['tpr_on_result']; path = root / descriptor['name']
    if fault == 'missing': path.unlink()
    elif fault == 'hash': path.write_bytes(b'1' * len(path.read_bytes()))
    elif fault == 'size': path.write_bytes(b'0')
    elif fault == 'mode': path.chmod(0o644)
    elif fault == 'symlink': path.unlink(); path.symlink_to(root / 'absent')
    elif fault == 'hardlink': os.link(path, root / 'duplicate')
    else: path.unlink(); os.mkfifo(path, 0o600)
    result = execute(fixture)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['scope_spent'] is True and result['result'] is None
    assert (root / (plan['processing_operation_id'] + '.claim.spent.json')).exists()


@pytest.mark.parametrize('fault', ['path', 'operation', 'project', 'attempt', 'main_shared', 'construction_shared', 'look_count', 'look_hash', 'expiration', 'source'])
def test_plan_escapes_or_preclaim_source_changes_refuse_before_private_read(tmp_path, fault):
    fixture = setup(tmp_path); plan = fixture[0]
    if fault == 'path': plan['files']['tpr_on_result']['name'] = '../other.result.json'
    elif fault == 'operation': plan['arms']['tpr_on']['qc_operation_id'] = 'unrelated-operation'
    elif fault == 'project': plan['arms']['tpr_on']['project_id'] = N('42')
    elif fault == 'attempt': plan['arms']['tpr_on']['attempt'] = N('2')
    elif fault == 'main_shared': plan['arms']['tpr_off']['source_hashes']['cap_tilt.py'] = '0' * 64
    elif fault == 'construction_shared': plan['arms']['tpr_off']['source_hashes']['extended_construction.py'] = '0' * 64
    elif fault == 'look_count': plan['expected_observed_looks'] = 17
    elif fault == 'look_hash': plan['arms']['tpr_on']['look_receipt_sha256'] = '0' * 64
    elif fault == 'expiration': plan['expires_utc'] = (fixture[4] - timedelta(seconds=1)).isoformat()
    else: fixture[1][p.SOURCE_RELATIVE] += b'# modified\n'
    if fault in {'main_shared', 'construction_shared'}:
        # Coherently rebound per-job source/launch-look metadata reaches the
        # cross-arm policy equality gate rather than a local look mismatch.
        row = plan['arms']['tpr_off']; row['look']['source_hashes'] = deepcopy(row['source_hashes'])
        row['look_receipt_sha256'] = p._sha(e.canonical(row['look']))
    with pytest.raises((ValueError, KeyError)): execute(fixture)
    assert not (fixture[2] / (plan['processing_operation_id'] + '.claim.spent.json')).exists()


def test_private_stat_body_and_exact_four_filenames_follow_fresh_claim(tmp_path, monkeypatch):
    fixture = setup(tmp_path); original_read, original_stat = p.strict._read_bound, p.os.fstat
    observed = []; claim = fixture[2] / (fixture[0]['processing_operation_id'] + '.claim.spent.json')
    def counted(directory, name, expected, remaining):
        assert claim.exists(); observed.append(name)
        return original_read(directory, name, expected, remaining)
    def check(fd):
        result = original_stat(fd)
        import stat
        if stat.S_ISREG(result.st_mode): assert claim.exists()
        return result
    monkeypatch.setattr(p.strict, '_read_bound', counted); monkeypatch.setattr(p.os, 'fstat', check)
    assert execute(fixture)['status'] == 'COMPLETED'
    assert observed == [row['name'] for row in fixture[0]['files'].values()]


def test_new_collection_access_manifest_is_not_mislabelled_as_origin_launch_access(tmp_path):
    fixture = setup(tmp_path); row = fixture[0]['arms']['tpr_off']
    # Same immutable execution/job/source/config/input evidence, newly scoped
    # collection operation. The origin launch receipt remains independently
    # bound and is not renewed or relabelled as the later access manifest.
    original_collection = row['collection_operations_manifest_sha256']
    row['look']['manifest_sha256'] = '9' * 64
    row['look_receipt_sha256'] = p._sha(e.canonical(row['look']))
    assert original_collection != row['look']['manifest_sha256']
    result = execute(fixture)
    assert result['status'] == 'COMPLETED'
    assert result['launch_operations_manifest_sha256']['tpr_off'] == '9' * 64
    assert result['collection_operations_manifest_sha256']['tpr_off'] == original_collection
    assert result['new_looks'].fraction() == result['quantconnect_attempts'].fraction() == 0


@pytest.mark.parametrize('fault', ['collection', 'execution', 'unbound_origin'])
def test_distinct_access_does_not_weaken_collection_execution_or_original_look_binding(tmp_path, fault):
    fixture = setup(tmp_path); row = fixture[0]['arms']['tpr_off']
    if fault == 'collection': row['collection_operations_manifest_sha256'] = '9' * 64
    elif fault == 'execution':
        row['look']['execution_manifest_sha256'] = '9' * 64
        row['look_receipt_sha256'] = p._sha(e.canonical(row['look']))
    else:
        row['look']['manifest_sha256'] = '9' * 64
        with pytest.raises(ValueError): execute(fixture)
        assert not (fixture[2] / (fixture[0]['processing_operation_id'] + '.claim.spent.json')).exists()
        return
    result = execute(fixture)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['scope_spent'] is True and result['result'] is None


def test_wrong_missing_or_reordered_nav_does_not_fill_gaps(tmp_path):
    fixture = setup(tmp_path); plan, _, root, data, _ = fixture
    values = e.parse_json(data['tpr_on_nav']); values.pop(100); raw = e.canonical(values)
    row = plan['arms']['tpr_on']; row['nav_sha256'], row['nav_bytes'] = p._sha(raw), N(str(len(raw)))
    plan['files'] = p._files(plan['arms']); (root / plan['files']['tpr_on_nav']['name']).write_bytes(raw)
    result = execute(fixture)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['result'] is None


def test_matched_chain_inequality_is_visible_not_relabelled_as_alpha(tmp_path):
    fixture = setup(tmp_path)
    def change(value):
        body = value['metrics']; body['summary']['matched_input_chains']['REMX']['caps']['sha256'] = '0' * 64
        body['summary_aggregate_sha256'] = body['metrics_binding']['summary_aggregate_sha256'] = p._sha(e.canonical(body['summary']))
    rebind(fixture, 'tpr_off', change); result = execute(fixture)
    assert result['status'] == 'COMPLETED'
    assert result['result']['matched_input_chain_comparison']['matched_chain_receipts_equal'] is False
    assert 'matched_input_chain_receipts_differ' in result['result']['diagnostics']
    assert result['result']['strategy_accepted'] is False


def test_cli_hash_bound_arguments_sanitize_private_failure(monkeypatch, capsys):
    def fail(**arguments): raise ValueError('PRIVATE-TICKER SECRET-TOKEN')
    monkeypatch.setattr(p, 'run', fail)
    args = ['--processing-operation-id', 'TPR-EXT26-PAIRED-SYNTHETIC-001', '--owner-instruction-sha256', 'f' * 64,
        '--created-utc', '2026-10-11T00:00:00Z', '--expires-utc', '2026-10-12T00:00:00Z', '--arms-json', '{}',
        '--arms-sha256', p._sha(b'{}'), '--expected-observed-looks', '19']
    assert p.main(args) == 1
    raw = capsys.readouterr().out
    assert 'PRIVATE' not in raw and 'SECRET' not in raw
    assert set(e.parse_json(raw.encode())) == {'status', 'scope_spent', 'automatic_retry'}
