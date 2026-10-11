"""Remaining71 synthetic native proof; no actual input, credential or cloud."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import os
import subprocess

import pytest
from research.target_price_revisions_qc import extended_input_remaining_successor as d
from tests.target_price_revisions_qc import test_qc_extended_input_probe_successor as first_tests

e = d.e


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    def deny(*_args, **_kw): raise AssertionError('actual private, credential, network or Git forbidden')
    monkeypatch.setattr(d.ops, 'credential', deny)
    monkeypatch.setattr(d.http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(subprocess, 'run', deny)
    monkeypatch.setattr(d, '_transport', deny)
    opening = d._open_directory
    def isolated(path):
        assert not path.is_relative_to(d.LANE)
        return opening(path)
    monkeypatch.setattr(d, '_open_directory', isolated)


def fixture(tmp_path, monkeypatch):
    f = first_tests.fixture(tmp_path, monkeypatch)
    first_result = d.first._execute(f['plan'], f['sources'], f['root'], f['inputs'],
        clock=lambda: f['now'], guard=lambda *_args: None, transport=f['transport'])
    result = e.parse_json(first_result)
    assert result['status'] == 'COMPLETED_FIRST_KEY_UPLOAD'
    monkeypatch.setattr(d, 'FIRST_OPERATION', f['plan']['operation_id'])
    monkeypatch.setattr(d, 'FIRST_PLAN_SHA256', result['plan_sha256'])
    monkeypatch.setattr(d, 'FIRST_RECEIPT_SHA256', d._sha(first_result))
    monkeypatch.setattr(d, 'FIRST_RECEIPT_BYTES', len(first_result))
    proof_raw = (f['root'] / (d.FIRST_OPERATION + '.native-hash-proof.json')).read_bytes()
    monkeypatch.setattr(d, 'FIRST_PROOF_SHA256', d._sha(proof_raw)); monkeypatch.setattr(d, 'FIRST_PROOF_BYTES', len(proof_raw))
    completion_raw = (f['root'] / ('compressed-input.' + f['first']['gzip_sha256'] + '.completed.json')).read_bytes()
    monkeypatch.setattr(d, 'FIRST_COMPLETION_SHA256', d._sha(completion_raw))
    monkeypatch.setattr(d.probe, 'ORGANIZATION_SHA256', d._sha(f['organization'].encode()))
    monkeypatch.setattr(d, 'ORGANIZATION_SHA256', d._sha(f['organization'].encode()))
    _, all_rows, _ = d.census._inventory(f['sources'][d.BUNDLE])
    rows = [row for row in all_rows if row['gzip_sha256'] != f['first']['gzip_sha256']]
    monkeypatch.setattr(d, 'TOTAL_ENCODED_BYTES', sum(e._integer(row['gzip_bytes']) for row in rows))
    monkeypatch.setattr(d, 'MAX_INPUT_FILE', max(e._integer(row['gzip_bytes']) for row in rows))
    _, _, synthetic_store, _ = first_tests.lifecycle.body()
    for row in rows: f['save'](row['stored_name'], synthetic_store.values[row['stored_key']], f['inputs'])
    sources = dict(f['sources']); sources[d.SOURCE_RELATIVE] = b'# synthetic committed remaining producer\n'
    plan = d._plan(source_hashes={name: d._sha(raw) for name, raw in sources.items()}, git_head='a' * 40,
        owner_instruction_sha256='b' * 64, created_utc=(f['now'] - timedelta(seconds=1)).isoformat(),
        expires_utc=(f['now'] + timedelta(hours=1)).isoformat(), operation_id='TPR-EXT26-INPUT-REMAINING-SYNTHETIC-001',
        bundle_raw=sources[d.BUNDLE], mode='offline-fixture')
    calls = []
    def transport(endpoint, raw, content_type):
        assert (f['root'] / (plan['operation_id'] + '.claim.spent.json')).is_file()
        number = len(calls) + 1
        assert (f['root'] / (plan['operation_id'] + '.request.' + str(number) + '.spent.json')).is_file()
        index, phase = (number - 1) // 3, (number - 1) % 3; row = rows[index]
        encoded = synthetic_store.values[row['stored_key']]
        calls.append((endpoint, row['gzip_sha256']))
        if phase == 1:
            assert endpoint == 'object/set'
            assert (f['root'] / (plan['operation_id'] + '.item-' + str(index) + '.input-read.spent.json')).is_file()
            expected, expected_content = d.first._multipart(f['organization'], row, encoded)
            assert raw == expected and content_type == expected_content
            return e.canonical({'success': True, 'errors': []}), 200
        assert endpoint == 'object/properties'
        assert e.parse_json(raw) == {'organizationId': f['organization'], 'key': row['stored_key']}
        if phase == 0: return e.canonical({'success': False, 'errors': ['key not found']}), 200
        return e.canonical({'success': True, 'errors': [], 'metadata': {'key': row['stored_key'],
            'size': len(encoded), 'md5': hashlib.md5(encoded).hexdigest()}}), 200
    return {**f, 'first_result': first_result, 'first_proof': proof_raw, 'first_completion': completion_raw,
        'sources': sources, 'plan': plan, 'rows': rows, 'native_store': synthetic_store,
        'calls': calls, 'transport': transport}


def execute(f, **kwargs):
    return e.parse_json(d._execute(f['plan'], f['sources'], f['root'], f['inputs'], clock=lambda: f['now'],
        guard=kwargs.pop('guard', lambda *_args: None), transport=kwargs.pop('transport', f['transport']), **kwargs))


def test_complete_exact71_roundtrips_claims_and_native_md5_without_first_body_reread(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    reading, seen = d.first._read_exact, []
    def observed(fd, name, **kwargs):
        assert (f['root'] / (f['plan']['operation_id'] + '.claim.spent.json')).is_file()
        assert name != f['first']['stored_name']
        seen.append(name); return reading(fd, name, **kwargs)
    monkeypatch.setattr(d.first, '_read_exact', observed)
    answer = execute(f)
    assert answer['status'] == 'COMPLETED_REMAINING71'
    assert answer['completed_count'].fraction() == 71 and answer['failed_count'].fraction() == answer['unattempted_count'].fraction() == 0
    assert answer['input_read_bytes'].fraction() == d.TOTAL_ENCODED_BYTES
    assert len(f['calls']) == 213 and sum(row[0] == 'object/set' for row in f['calls']) == 71
    assert answer['first_proof_verified'] is True
    assert len(list(f['root'].glob('compressed-input.*.completed.json'))) == 72
    assert (f['root'] / (d.FIRST_OPERATION + '.result.json')).read_bytes() == f['first_result']
    assert (f['root'] / (d.FIRST_OPERATION + '.native-hash-proof.json')).read_bytes() == f['first_proof']
    assert answer['new_looks'].fraction() == answer['quantconnect_attempts'].fraction() == 0
    assert answer['full_capacity_proved'] is answer['native_absence_attested'] is answer['native_content_sha256_verified'] is False
    assert f['organization'].encode() not in e.canonical(answer)
    assert f['rows'][0]['stored_key'].encode() not in e.canonical(answer)
    with pytest.raises(FileExistsError): execute(f)
    assert len(f['calls']) == 213


@pytest.mark.parametrize('failure_index', [0, 1, 35, 70])
def test_first_quota_failure_stops_preserves_completed_failed_unattempted(tmp_path, monkeypatch, failure_index):
    f = fixture(tmp_path, monkeypatch); normal = f['transport']
    def chosen(endpoint, raw, content_type):
        index, phase = len(f['calls']) // 3, len(f['calls']) % 3
        if index == failure_index and phase == 1:
            f['calls'].append((endpoint, f['rows'][index]['gzip_sha256']))
            return e.canonical({'success': False, 'errors': ['storage quota exceeded']}), 200
        return normal(endpoint, raw, content_type)
    answer = execute(f, transport=chosen)
    assert answer['status'] == 'FAILED_OR_UNCERTAIN'
    assert answer['completed_count'].fraction() == failure_index and answer['failed_count'].fraction() == 1
    assert answer['unattempted_count'].fraction() == 70 - failure_index
    assert len(f['calls']) == failure_index * 3 + 2
    assert len(list(f['root'].glob('compressed-input.*.completed.json'))) == failure_index + 1
    assert answer['automatic_retry'] is answer['old_claims_renewed'] is False


@pytest.mark.parametrize('kind', ['present_match', 'present_mismatch', 'unknown', 'http', 'foreign_key', 'post_md5', 'post_size', 'post_missing', 'transport'])
def test_native_conflict_uncertainty_or_postproof_error_never_invents_completion(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch); normal = f['transport']
    row, encoded = f['rows'][0], f['native_store'].values[f['rows'][0]['stored_key']]
    def chosen(endpoint, raw, content_type):
        phase = len(f['calls']) % 3
        if (phase == 0 and kind in {'present_match', 'present_mismatch', 'unknown', 'http', 'foreign_key'}
                or phase == 2 and kind in {'post_md5', 'post_size', 'post_missing'}):
            f['calls'].append((endpoint, row['gzip_sha256']))
            if kind in {'unknown', 'http', 'post_missing'}:
                return e.canonical({'success': False, 'errors': ['unrecognized']}), 403 if kind == 'http' else 200
            return e.canonical({'success': True, 'errors': [], 'metadata': {
                'key': 'FOREIGN' if kind == 'foreign_key' else row['stored_key'],
                'size': len(encoded) - 1 if kind == 'post_size' else len(encoded),
                'md5': 'a' * 32 if kind in {'present_mismatch', 'post_md5'} else hashlib.md5(encoded).hexdigest()}}), 200
        if phase == 1 and kind == 'transport':
            f['calls'].append((endpoint, row['gzip_sha256'])); raise OSError('SECRET-PRIVATE')
        return normal(endpoint, raw, content_type)
    answer = execute(f, transport=chosen)
    assert answer['status'] == 'FAILED_OR_UNCERTAIN' and answer['completed_count'].fraction() == 0
    assert answer['failed_count'].fraction() == 1 and answer['unattempted_count'].fraction() == 70
    assert len(list(f['root'].glob('compressed-input.*.completed.json'))) == 1
    assert b'SECRET-PRIVATE' not in e.canonical(answer)


@pytest.mark.parametrize('kind', ['receipt', 'proof', 'first_completion', 'project', 'old_read', 'prior_completion', 'gzip_hash', 'gzip_size'])
def test_first_lineage_existing_claim_or_input_corruption_refuses_before_api(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch); row = f['rows'][0]
    if kind == 'receipt': f['save'](d.FIRST_OPERATION + '.result.json', f['first_result'][:-1] + b' ')
    if kind == 'proof': f['save'](d.FIRST_OPERATION + '.native-hash-proof.json', f['first_proof'][:-1] + b' ')
    if kind == 'first_completion': f['save']('compressed-input.' + f['first']['gzip_sha256'] + '.completed.json', f['first_completion'][:-1] + b' ')
    if kind == 'project': f['project']['organization_id'] = 'FOREIGN'; f['save'](d.ON + '.project.json', f['project'])
    if kind == 'old_read': f['save']('compressed-input.' + row['gzip_sha256'] + '.read.spent.json', {'preserve': True})
    if kind == 'prior_completion': f['save']('compressed-input.' + row['gzip_sha256'] + '.completed.json', {'preserve': True})
    if kind == 'gzip_hash': f['save'](row['stored_name'], b'X' * e._integer(row['gzip_bytes']), f['inputs'])
    if kind == 'gzip_size': f['save'](row['stored_name'], b'X' * (e._integer(row['gzip_bytes']) + 1), f['inputs'])
    assert execute(f)['status'] == 'FAILED_OR_UNCERTAIN' and not f['calls']


@pytest.mark.parametrize('kind', ['expired', 'source', 'plan', 'duration', 'identity', 'runtime'])
def test_scope_bounds_load_bearing_before_private_or_later_effect(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch)
    if kind == 'expired': f['now'] += timedelta(hours=2)
    if kind == 'source': f['sources'][d.SOURCE_RELATIVE] += b'# changed'
    if kind == 'plan': f['plan']['max_requests'] = 214
    if kind == 'duration': f['plan']['expires_utc'] = (f['now'] + timedelta(hours=25)).isoformat()
    if kind == 'identity': f['plan']['operation_id'] = 'OLD-SPENT'
    if kind == 'runtime':
        monkeypatch.setattr(d, 'MAX_SECONDS', 0)
    monkeypatch.setattr(d, '_open_directory', lambda *_args: pytest.fail('invalid scope opened private'))
    with pytest.raises(d.Refusal): execute(f)


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'mode', 'input_directory'])
def test_row_custody_refuses_before_first_api(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch); path = f['inputs'] / f['rows'][0]['stored_name']
    if kind == 'symlink':
        old = f['inputs'] / 'old'; path.rename(old); path.symlink_to(old)
    if kind == 'hardlink': os.link(path, f['inputs'] / 'copy')
    if kind == 'mode': path.chmod(0o644)
    if kind == 'input_directory': f['inputs'].chmod(0o755)
    assert execute(f)['status'] == 'FAILED_OR_UNCERTAIN' and not f['calls']


@pytest.mark.parametrize('name', ['first', 'probe', 'storage', 'e', 'ops', 'census', 'old'])
def test_loaded_module_custody_refuses_before_git_private_source_or_network(monkeypatch, name):
    module = {'first': d.first, 'probe': d.probe, 'storage': d.storage, 'e': d.e,
        'ops': d.ops, 'census': d.census, 'old': d.probe.old}[name]
    monkeypatch.setattr(module, '__file__', '/foreign/module.py')
    for boundary in ('_guard', '_sources', '_open_directory', '_transport'):
        monkeypatch.setattr(d, boundary, lambda *_args, **_kw: pytest.fail('foreign module crossed custody'))
    with pytest.raises(d.Refusal): d.run()


def test_offline_fixture_refuses_real_operations_or_inputs(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    for path, inputs in ((d.PRIVATE_ROOT, f['inputs']), (f['root'], d.INPUT_ROOT)):
        with pytest.raises(d.Refusal):
            d._execute(f['plan'], f['sources'], path, inputs, clock=lambda: f['now'], guard=lambda *_args: None, transport=f['transport'])
