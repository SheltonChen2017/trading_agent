"""Synthetic exact-capture census; no actual private/provider/QC access."""
import ast
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.target_price_revisions_qc import extended_sharadar_capture_census as m

NOW = datetime(2026, 10, 24, 20, tzinfo=timezone.utc)
INDEX_OP = 'TPR-EXT26-SHARADAR-CENSUS-INDEX-SYNTHETIC'
PAGES_OP = 'TPR-EXT26-SHARADAR-CENSUS-PAGES-SYNTHETIC'
PRIVATE = 'SYNTHETIC-ROW-DO-NOT-OUTPUT'


@pytest.fixture(autouse=True)
def forbid_real_effects(monkeypatch):
    import http.client
    import socket
    original_directory = m._directory
    def guarded(path, **kwargs):
        if Path(path).is_relative_to(m.LANE): pytest.fail('actual lane private access forbidden')
        return original_directory(path, **kwargs)
    def deny(*_args, **_kwargs): pytest.fail('provider/Git/private discovery forbidden')
    monkeypatch.setattr(m, '_directory', guarded)
    monkeypatch.setattr(m.subprocess, 'run', deny)
    monkeypatch.setattr(http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(socket, 'create_connection', deny)


def synthetic_pages():
    pages = []
    dates = ('1999-01-01', '2020-09-01', '2021-01-04', '2021-10-11', '2026-10-09')
    for number in range(1, 9):
        dataset = 'tickers' if number <= 3 else 'actions'
        count = 1007 if number == 3 else 9716 if number == 8 else 10000
        source = ({'ticker': PRIVATE, 'permaticker': '123', 'figi': None, 'category': 'Common Stock',
            'exchange': 'SYNTHETIC', 'isdelisted': 'N'} if dataset == 'tickers' else
            {'ticker': PRIVATE, 'date': dates[number - 4], 'action': 'split', 'contraticker': None})
        body = {'schema': 'tpr-ext26-sharadar-repair-page-v1', 'dataset': dataset,
            'rows': [{'source': source, 'refusals': []}] * count, 'source_rows': count,
            'row_refusals': 0, 'identical_duplicate_rows': 48 if number == 8 else 0,
            'conflicting_duplicate_rows': 0, 'ticker_python_lexical_descents': 351 if number == 3 else 0,
            'missing_optional_column': False, 'current_vintage_not_point_in_time': True}
        pages.append(m._canonical(body))
    return pages


@pytest.fixture(scope='module')
def capture():
    pages = synthetic_pages()
    entries = []
    for number, raw in enumerate(pages, 1):
        dataset = 'tickers' if number <= 3 else 'actions'
        prefix = f'request.{number:04}'
        entries.append({'request_index': number, 'provider': 'sharadar', 'dataset': dataset,
            'page': number - (1 if number <= 3 else 4), 'http_status': 200,
            'wire_file': prefix + '.wire.csv', 'wire_sha256': 'a' * 64, 'wire_bytes': 100,
            'received_bytes': 100, 'projection_file': prefix + '.projection.json',
            'projection_sha256': m._sha(raw), 'projection_bytes': len(raw),
            'response_complete': True, 'disposition': 'projected', 'fetch_utc': NOW.isoformat()})
    index = {'schema': 'tpr-ext26-sharadar-repair-index-v1', 'operation_id': m.CAPTURE,
        'study_id': m.STUDY, 'freeze_sha256': m.FREEZE, 'plan_sha256': 'b' * 64,
        'git_sha': 'c' * 40, 'source_hashes': {}, 'started_utc': NOW.isoformat(), 'ended_utc': NOW.isoformat(),
        'pages': entries, 'census': [{'provider': 'sharadar', 'dataset': dataset, 'pages': n,
            'source_rows': rows, 'response_bytes': size, 'terminated': True}
            for dataset, n, rows, size in (('tickers', 3, 21007, 946301), ('actions', 5, 49716, 1456441))],
        'failure': None, 'report': {'status': 'COMPLETED', 'capture_complete': True, 'scope_spent': True,
            'source_rows': 70723, 'row_refusals': 0, 'conflicting_duplicate_rows': 0,
            'identical_duplicate_rows': 48, 'response_bytes': 2402742},
        'original_capture_modified': False, 'point_in_time_data': False, 'current_vintage_identity': True,
        'action_history_no_lower_bound': True, 'ticker_python_collation_asserted': False,
        'terminated_pagination_not_transaction_snapshot': True, 'count_semantics': {}}
    return index, pages


@pytest.fixture
def bound(capture, monkeypatch):
    index, pages = capture
    raw = m._canonical(index)
    monkeypatch.setattr(m, 'INDEX_SHA256', m._sha(raw))
    monkeypatch.setattr(m, 'INDEX_BYTES', len(raw))
    inventory = m.index_inventory(raw)
    return raw, pages, inventory


def plan(stage='index', **changes):
    args = dict(operation_id=INDEX_OP if stage == 'index' else PAGES_OP, stage=stage,
        git_head='a' * 40, source_hashes={name: 'b' * 64 for name in m.SOURCE_PATHS},
        owner_instruction_sha256='c' * 64, created_utc=NOW.isoformat(),
        expires_utc=(NOW + timedelta(seconds=300)).isoformat(), mode='offline-fixture')
    args.update(changes)
    return m.make_plan(**args)


def execute(selected, source, output, **changes):
    return m.execute(selected, input_root=source, output_root=output,
        guard=changes.pop('guard', lambda head: None),
        source_identity=changes.pop('source_identity', lambda head: selected['source_hashes']),
        clock=changes.pop('clock', lambda: NOW), monotonic=changes.pop('monotonic', lambda: 10), **changes)


@pytest.fixture
def leaves(tmp_path, bound):
    source, output = tmp_path / 'synthetic_capture', tmp_path / 'synthetic_receipts'
    source.mkdir(mode=0o700); output.mkdir(mode=0o700)
    index, pages, inventory = bound
    for name, raw in [(m.INDEX_NAME, index), *[(d['name'], raw) for d, raw in zip(inventory['projections'], pages)]]:
        path = source / name; path.write_bytes(raw); path.chmod(0o600)
    return source, output, inventory


def saved(output, receipt):
    matches = list(output.glob(receipt['operation_id'] + '.attempt-*.result.json'))
    assert matches and json.loads(matches[-1].read_bytes()) == receipt
    assert PRIVATE not in matches[-1].read_text()
    assert all(receipt[name] is False for name in m._FALSE_FLAGS)
    assert receipt['qc_access'] is receipt['provider_access'] is receipt['inputs_changed'] is False
    assert receipt['outcome_reads'] == receipt['new_looks'] == receipt['quantconnect_attempts'] == 0


def test_index_contains_only_exact_eight_descriptors(bound):
    raw, _, inventory = bound
    assert inventory == m.index_inventory(raw)
    assert inventory['ticker_rows'] == 21007 and inventory['action_rows'] == 49716
    assert len(inventory['projections']) == 8
    assert PRIVATE not in m._canonical(inventory).decode()


@pytest.mark.parametrize('fault', ('hash', 'bytes', 'unknown_key', 'foreign_capture', 'page_path', 'dataset',
    'bool_page', 'missing_page', 'foreign_http', 'incomplete', 'row_count', 'boolean_count'))
def test_index_metadata_refuses_closed_shape_and_identity(capture, fault):
    body = deepcopy(capture[0])
    if fault == 'unknown_key': body['row'] = PRIVATE
    elif fault == 'foreign_capture': body['operation_id'] = 'other'
    elif fault == 'page_path': body['pages'][0]['projection_file'] = '../other.json'
    elif fault == 'dataset': body['pages'][0]['dataset'] = 'actions'
    elif fault == 'bool_page': body['pages'][0]['page'] = False
    elif fault == 'missing_page': body['pages'].pop()
    elif fault == 'foreign_http': body['pages'][0]['http_status'] = 403
    elif fault == 'incomplete': body['census'][1]['terminated'] = False
    elif fault == 'row_count': body['report']['source_rows'] = 70000
    elif fault == 'boolean_count': body['report']['row_refusals'] = False
    raw = m._canonical(body)
    with pytest.raises(m.CensusRefusal):
        m.index_inventory(raw, expected_sha256='f' * 64 if fault == 'hash' else m._sha(raw),
            expected_bytes=len(raw) + (fault == 'bytes'))


def test_all_page_hashes_precede_any_date_or_field_count(bound, monkeypatch):
    _, pages, inventory = bound
    pages = list(pages); pages[-1] += b' '
    monkeypatch.setattr(m, '_object', lambda *_: pytest.fail('parsed before all eight hash checks'))
    with pytest.raises(m.CensusRefusal): m.project_pages(pages, inventory)


def test_census_retains_early_actions_and_only_aggregate_current_master(bound):
    _, pages, inventory = bound
    result = m.project_pages(pages, inventory)
    assert result['early_actions_observed'] is True
    assert result['action_date_buckets']['early_window_before_2021_10_11'] == 20000
    assert result['action_date_buckets']['before_2021_10_11'] == 30000
    assert result['action_date_buckets']['before_warmup'] == 10000
    assert result['action_year_counts']['2020'] == 10000
    assert result['earliest_retained_action_date'] == '1999-01-01'
    assert result['latest_retained_action_date'] == '2026-10-09'
    assert result['ticker_rows'] + result['action_rows'] == 70723
    assert result['current_master_is_historical_identity_series'] is False
    assert result['current_subscription_proves_capture_entitlement'] is False
    assert result['full_as_published_history_proven'] is False
    assert PRIVATE not in m._canonical(result).decode()


def rebind_page(pages, inventory, number, mutate):
    pages, inventory = list(pages), deepcopy(inventory)
    body = json.loads(pages[number]); mutate(body)
    raw = pages[number] = m._canonical(body)
    inventory['projections'][number]['sha256'] = m._sha(raw)
    inventory['projections'][number]['bytes'] = len(raw)
    inventory['projection_bytes'] = sum(row['bytes'] for row in inventory['projections'])
    return pages, inventory


@pytest.mark.parametrize('fault', ('unknown_key', 'row_count', 'row_shape', 'field_shape', 'bool_count',
    'unknown_refusal', 'refusal_mismatch', 'wrong_schema', 'wrong_dataset', 'oversized_cell', 'chronology'))
def test_rebound_page_semantic_refusals(bound, fault):
    _, pages, inventory = bound
    def mutate(body):
        if fault == 'unknown_key': body['extra'] = PRIVATE
        elif fault == 'row_count': body['rows'].pop()
        elif fault == 'row_shape': body['rows'][0]['extra'] = PRIVATE
        elif fault == 'field_shape': body['rows'][0]['source']['extra'] = PRIVATE
        elif fault == 'bool_count': body['source_rows'] = True
        elif fault == 'unknown_refusal': body['rows'][0]['refusals'] = ['private-error']
        elif fault == 'refusal_mismatch': body['row_refusals'] = 1
        elif fault == 'wrong_schema': body['schema'] = 'other'
        elif fault == 'wrong_dataset': body['dataset'] = 'tickers'
        elif fault == 'oversized_cell': body['rows'][0]['source']['ticker'] = 'a' * 8193
        else: body['rows'][1]['source']['date'] = '1990-01-01'
    changed, manifest = rebind_page(pages, inventory, 3, mutate)
    with pytest.raises(m.CensusRefusal): m.project_pages(changed, manifest)


@pytest.mark.parametrize('value,bucket', ((None, 'missing_date'), ('', 'missing_date'),
    ('2021-02-30', 'invalid_date'), ('20210101', 'invalid_date')))
def test_unavailable_dates_retained_not_zeroed_or_invented(bound, value, bucket):
    _, pages, inventory = bound
    changed, manifest = rebind_page(pages, inventory, 3,
        lambda body: body['rows'][0]['source'].__setitem__('date', value))
    result = m.project_pages(changed, manifest)
    assert result['action_date_buckets'][bucket] == 1
    assert result['action_rows'] == 49716
    assert result['provider_completeness_proven'] is result['on_ready'] is False


def test_cross_page_ticker_descents_are_audit_counts_not_sorting_refusals(bound):
    _, pages, inventory = bound
    for number, ticker in ((0, 'ZZZ'), (1, 'MMM'), (2, 'AAA')):
        def change(body, ticker=ticker, number=number):
            for item in body['rows']: item['source']['ticker'] = ticker
            body['ticker_python_lexical_descents'] = 349 if number == 2 else 0
        pages, inventory = rebind_page(pages, inventory, number, change)
    result = m.project_pages(pages, inventory)
    assert result['ticker_python_lexical_descents'] == 351


def test_two_fresh_scopes_claim_before_inputs_and_leave_originals_unchanged(leaves, monkeypatch):
    source, output, inventory = leaves
    original = {path.name: path.read_bytes() for path in source.iterdir()}
    real_read = m._read; reads = []
    def read(fd, name, **kwargs):
        operation = INDEX_OP if name == m.INDEX_NAME else PAGES_OP
        assert (output / (operation + '.claim.spent.json')).exists()
        reads.append(name)
        return real_read(fd, name, **kwargs)
    monkeypatch.setattr(m, '_read', read)
    first = execute(plan(), source, output)
    assert first['status'] == 'COMPLETED_DIAGNOSTIC_ONLY' and reads == [m.INDEX_NAME]
    saved(output, first)
    second_plan = plan('pages', index_operation=INDEX_OP, inventory_sha256=first['output_sha256'])
    second = execute(second_plan, source, output)
    assert second['status'] == 'COMPLETED_DIAGNOSTIC_ONLY' and second['completed_input_reads'] == 9
    assert reads[1:] == [INDEX_OP + '.inventory.json', *[row['name'] for row in inventory['projections']]]
    assert (output / (PAGES_OP + '.census.json')).exists()
    assert original == {path.name: path.read_bytes() for path in source.iterdir()}
    saved(output, second)


@pytest.mark.parametrize('fault', ('hash', 'size', 'symlink', 'hardlink', 'mode', 'missing'))
def test_bad_index_file_keeps_spent_bodyfree_failure_without_search(leaves, fault):
    source, output, _ = leaves
    path = source / m.INDEX_NAME
    if fault == 'hash': path.write_bytes(b'x' * path.stat().st_size)
    elif fault == 'size': path.write_bytes(b'x')
    elif fault == 'symlink':
        original = source / 'unrelated'; path.rename(original); path.symlink_to(original)
    elif fault == 'hardlink': (source / 'unrelated').hardlink_to(path)
    elif fault == 'mode': path.chmod(0o644)
    else: path.unlink()
    result = execute(plan(), source, output)
    assert result['status'] == 'FAILED_OR_UNCERTAIN' and result['scope_spent']
    assert result['input_read_attempts'] == 1 and result['completed_input_reads'] == 0
    assert result['failed_input_read_bytes_unknown'] is True and result['output_sha256'] is None
    saved(output, result)


def test_replay_and_lock_contention_preserve_prior_receipts(leaves):
    source, output, _ = leaves
    first = execute(plan(), source, output)
    prior = {path.name: path.read_bytes() for path in output.iterdir()}
    second = execute(plan(), source, output)
    assert second['failure_stage'] == 'claim' and second['scope_spent']
    assert second['input_read_attempts'] == 0
    assert all((output / name).read_bytes() == raw for name, raw in prior.items())
    lock = output / (INDEX_OP + '.lock'); lock.write_bytes(b'foreign')
    third = execute(plan(), source, output)
    assert third['failure_stage'] == 'lock' and third['scope_spent'] is False
    assert lock.read_bytes() == b'foreign' and third['input_read_attempts'] == 0


def test_cancelled_read_retains_conservative_budget_and_no_retry(leaves, monkeypatch):
    source, output, _ = leaves
    monkeypatch.setattr(m, '_read', lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt(PRIVATE)))
    with pytest.raises(KeyboardInterrupt, match='preserve spent scope'):
        execute(plan(), source, output)
    raw = next(output.glob('*.result.json')).read_bytes(); result = json.loads(raw)
    assert result['status'] == 'CANCELLED' and result['input_read_attempts'] == 1
    assert result['reserved_input_bytes'] == m.INDEX_BYTES
    assert result['failed_input_read_bytes_unknown'] and PRIVATE not in raw.decode()


def test_claim_publication_uncertainty_cannot_refund_scope(leaves, monkeypatch):
    source, output, _ = leaves
    original = m._publish
    def publish(fd, name, raw):
        result = original(fd, name, raw)
        if name.endswith('.claim.spent.json'): raise OSError(PRIVATE)
        return result
    monkeypatch.setattr(m, '_publish', publish)
    result = execute(plan(), source, output)
    assert result['scope_spent'] and result['claim_attempted'] and result['input_read_attempts'] == 0
    assert (output / (INDEX_OP + '.claim.spent.json')).exists()
    saved(output, result)


def test_cleanup_interrupt_retains_completed_input_counts_and_durable_receipt(leaves, monkeypatch):
    source, output, _ = leaves
    original = m.os.unlink
    def unlink(name, **kwargs):
        if name.endswith('.lock'): raise KeyboardInterrupt(PRIVATE)
        return original(name, **kwargs)
    monkeypatch.setattr(m.os, 'unlink', unlink)
    with pytest.raises(KeyboardInterrupt, match='preserve spent scope'):
        execute(plan(), source, output)
    result = json.loads(next(output.glob('*.result.json')).read_bytes())
    assert result['status'] == 'CANCELLED' and result['failure_stage'] == 'cleanup'
    assert result['completed_input_reads'] == 1 and result['scope_spent']
    assert not result['lock_cleanup_complete']
    saved(output, result)


@pytest.mark.parametrize('fault', ('expired', 'future', 'head', 'source', 'nan', 'bool'))
def test_preflight_refuses_before_capture_observation(leaves, fault):
    source, output, _ = leaves
    kwargs = {}
    if fault == 'expired': kwargs['clock'] = lambda: NOW + timedelta(seconds=300)
    elif fault == 'future': kwargs['clock'] = lambda: NOW - timedelta(seconds=1)
    elif fault == 'head': kwargs['guard'] = lambda _: m._fail()
    elif fault == 'source': kwargs['source_identity'] = lambda _: {}
    elif fault == 'nan': kwargs['monotonic'] = lambda: float('nan')
    else: kwargs['monotonic'] = lambda: True
    with pytest.raises(m.CensusRefusal): execute(plan(), source, output, **kwargs)
    assert not list(output.iterdir())


@pytest.mark.parametrize('change', ({'stage': 'other'}, {'operation_id': 'other'}, {'git_head': 'x'},
    {'owner_instruction_sha256': 'x'}, {'source_hashes': {}}, {'mode': 'other'},
    {'expires_utc': NOW.isoformat()}, {'inventory_sha256': 'a' * 64}))
def test_closed_prospective_registration(change):
    with pytest.raises(m.CensusRefusal): plan(**change)


def test_no_forbidden_imports_or_default_effects():
    tree = ast.parse(Path(m.__file__).read_text())
    roots = {node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    roots |= {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not roots & {'research', 'execution', 'dispatch', 'config', 'requests', 'http', 'socket', 'QuantConnect'}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in {'glob', 'rglob', 'iterdir', 'listdir', 'walk'} for node in ast.walk(tree))


@pytest.mark.parametrize('replaced', ('guard', 'source_identity', 'clock', 'monotonic', None))
def test_production_rejects_injected_callbacks_before_directory(monkeypatch, replaced):
    # Synthetic names stand in for fixed production bindings; no real guard,
    # directory, clock or source reader is called even by the clean control.
    selected = plan(mode='production')
    guard = lambda _head: None
    sources = lambda _head: selected['source_hashes']
    clock, tick = lambda: NOW, lambda: 10
    monkeypatch.setattr(m, '_guard', guard)
    monkeypatch.setattr(m, '_sources', sources)
    monkeypatch.setattr(m, '_now', clock, raising=False)
    monkeypatch.setattr(m, 'time', SimpleNamespace(monotonic=tick))
    class ReachedDirectory(Exception): pass
    def directory(*_args, **_kwargs):
        raise ReachedDirectory('synthetic production clean control')
    monkeypatch.setattr(m, '_directory', directory)
    arguments = {'guard': guard, 'source_identity': sources, 'clock': clock, 'monotonic': tick}
    if replaced == 'guard': arguments[replaced] = lambda _head: None
    elif replaced == 'source_identity': arguments[replaced] = lambda _head: selected['source_hashes']
    elif replaced == 'clock': arguments[replaced] = lambda: NOW
    elif replaced == 'monotonic': arguments[replaced] = lambda: 10
    with pytest.raises(ReachedDirectory if replaced is None else m.CensusRefusal):
        m.execute(selected, **arguments)


# TPR-CR30 regressions: the lane boundary is decided by identity, and a cleanup
# failure after a cancellation keeps the cancelled status.


def test_case_alias_of_the_lane_is_refused_by_identity_not_text(leaves, monkeypatch):
    import os
    _source, output, _ = leaves
    alias = Path(str(m.LANE).upper())
    if not alias.exists() or os.stat(alias).st_ino != os.stat(m.LANE).st_ino:
        pytest.skip('case-sensitive volume: no lane alias to test')
    lane_real = os.path.realpath(m.LANE)
    def guarded(path, **kwargs):
        if os.path.realpath(path).startswith(lane_real): pytest.fail('alias reached the real lane')
        return m._directory.__wrapped__(path, **kwargs) if hasattr(m._directory, '__wrapped__') else None
    monkeypatch.setattr(m, '_directory', guarded)
    with pytest.raises(m.CensusRefusal):
        execute(plan(), alias / 'artifacts' / 'synthetic-never-created', output)
    assert m._lane_identity(alias / 'artifacts', m.LANE) is True


def test_cleanup_failure_after_cancellation_keeps_the_cancelled_status(leaves, monkeypatch):
    source, output, _ = leaves
    monkeypatch.setattr(m, '_read', lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt(PRIVATE)))
    original = m.os.unlink
    def unlink(name, **kwargs):
        if name.endswith('.lock'): raise OSError(PRIVATE)
        return original(name, **kwargs)
    monkeypatch.setattr(m.os, 'unlink', unlink)
    with pytest.raises(KeyboardInterrupt, match='preserve spent scope'):
        execute(plan(), source, output)
    raw = next(output.glob('*.result.json')).read_bytes(); result = json.loads(raw)
    assert result['status'] == 'CANCELLED' and result['failure_stage'] == 'cleanup' and PRIVATE not in raw.decode()
