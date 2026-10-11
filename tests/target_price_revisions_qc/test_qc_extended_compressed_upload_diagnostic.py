"""Synthetic op003 upload census; actual roots/network/credentials denied."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
import subprocess

import pytest
from research.target_price_revisions_qc import extended_compressed_upload_diagnostic as d

e = d.e


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    import http.client
    def deny(*_a, **_kw): raise AssertionError('actual private/network/credential/repository call forbidden')
    monkeypatch.setattr(http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(d.ops, 'credential', deny)
    monkeypatch.setattr(subprocess, 'run', deny)
    opening = d._open_directory
    def open_owned(path):
        assert not path.is_relative_to(d.LANE)
        return opening(path)
    monkeypatch.setattr(d, '_open_directory', open_owned)


def fixture(tmp_path, monkeypatch, *, split=False):
    now = datetime.now(timezone.utc); prefix = 'tpr-ext26/inputs/' + e.STUDY_ID + '/' + 'b' * 64 + '/'
    originals, payloads = [], []
    for index in range(72):
        plain, compressed = d._sha(('plain-' + str(index)).encode()), d._sha(('gzip-' + str(index)).encode())
        originals.append({'name': plain + '.json', 'sha256': plain, 'bytes': 100 + index, 'key': prefix + plain + '.json'})
        payloads.append({'plain_name': plain + '.json', 'plain_sha256': plain, 'plain_bytes': 100 + index,
            'logical_key': prefix + plain + '.json', 'gzip_sha256': compressed, 'gzip_bytes': 50 + index,
            'stored_name': 'gzip.' + compressed + '.json', 'stored_key': prefix + 'gzip.' + compressed + '.json'})
    mapping = {'schema': 'tpr-ext26-gzip-input-map-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
        'preparation_sha256': 'b' * 64, 'bundle_sha256': 'c' * 64, 'processing_operation_id': 'TPR-EXT26-COMPRESS-SYNTHETIC-001',
        'processing_plan_sha256': 'd' * 64, 'encoding': 'gzip', 'gzip_level': 9, 'gzip_mtime': 0, 'payloads': payloads}
    map_raw = e.canonical(mapping); text = map_raw.decode()
    if not split: files = {'compressed_packet.py': 'COMPRESSION_JSON = ' + repr(text) + '\n'}
    else:
        parts = [text[:len(text)//2], text[len(text)//2:]]
        files = {'compressed_packet_part' + str(index) + '.py': 'PART_JSON = ' + repr(part) + '\n' for index, part in enumerate(parts)}
        files['compressed_packet.py'] = 'from compressed_packet_part0 import PART_JSON as P0\nfrom compressed_packet_part1 import PART_JSON as P1\nCOMPRESSION_JSON = P0 + P1\n'
    candidates = [{'candidate_id': d.ON, 'files': files}]
    bundle = {'schema': 'tpr-ext26-source-bundle-v1', 'candidates': candidates, 'inputs': originals,
        'preparation_sha256': 'b' * 64, 'repository_sources': []}
    bundle_raw = e.canonical(bundle); monkeypatch.setattr(d, 'BUNDLE_SHA256', d._sha(bundle_raw))
    manifest = {'operation_id': d.QC_OPERATION, 'candidates': candidates, 'inputs': originals, 'preparation_sha256': 'b' * 64,
        'created_utc': (now - timedelta(seconds=10)).isoformat(), 'expires_utc': (now + timedelta(hours=1)).isoformat()}
    manifest_raw = e.canonical(manifest); monkeypatch.setattr(d, 'MANIFEST_SHA256', d._sha(manifest_raw))
    monkeypatch.setattr(d.ops, 'validate_manifest', lambda *_: None)
    sources = {name: b'# synthetic committed source\n' for name in d.SOURCE_PATHS}; sources[d.BUNDLE] = bundle_raw
    plan = d._plan(source_hashes={name: d._sha(raw) for name, raw in sources.items()}, git_head='a' * 40,
        owner_instruction_sha256='e' * 64, created_utc=(now - timedelta(seconds=1)).isoformat(),
        expires_utc=(now + timedelta(hours=1)).isoformat(), read_operation_id='TPR-EXT26-COMPRESSED-UPLOAD-DIAG-SYNTHETIC-001',
        expected_manifest_sha256=d.MANIFEST_SHA256, mode='offline-fixture')
    root = tmp_path / 'metadata'; root.mkdir(mode=0o700)
    def save(name, value):
        raw = value if type(value) is bytes else e.canonical(value)
        (root / name).write_bytes(raw); (root / name).chmod(0o600)
    save('manifest.' + d.QC_OPERATION + '.json', manifest_raw)
    at = now.isoformat()
    def stages(index, kind, *, number=None):
        row = payloads[index]; name = 'compressed-input.' + row['gzip_sha256']; wire_sha = d._sha(('wire-' + str(index)).encode())
        save(name + '.read.spent.json', {'at': at, 'name': row['stored_name'], 'gzip_sha256': row['gzip_sha256'],
            'mapping_sha256': d._sha(map_raw), 'manifest_sha256': d.MANIFEST_SHA256})
        if kind == 'read': return
        save(name + '.upload.spent.json', {'at': at, 'manifest_sha256': d.MANIFEST_SHA256, 'payload_sha256': wire_sha})
        if kind == 'upload': return
        save(name + '.upload.transport.json', {'at': at, 'endpoint': 'object/set'})
        if kind == 'transport': return
        request = 'request.' + f'{number:04d}'
        save(request + '.spent.json', {'at': at, 'endpoint': 'object/set', 'payload_sha256': wire_sha, 'manifest_sha256': d.MANIFEST_SHA256})
        if kind == 'no_terminal': return
        raw = e.canonical({'success': kind != 'failed', 'errors': [] if kind != 'failed' else ['PRIVATE-ROW-SENTINEL storage quota exceeded']})
        projection = e.project_wire(raw); save(request + '.projection.json', projection)
        if kind == 'failed': terminal = {'at': at, 'status': 'failed_or_unknown', 'automatic_retry': False}
        else: terminal = {'at': at, 'status': 'succeeded', 'original_wire_sha256': projection['original_wire_sha256'], 'projection_sha256': projection['projection_sha256']}
        save(request + '.terminal.json', terminal)
        if kind == 'completed': save(name + '.completed.json', {'schema': 'tpr-ext26-gzip-upload-v1', 'mapping_sha256': d._sha(map_raw),
            **{key: row[key] for key in ('plain_sha256', 'plain_bytes', 'logical_key', 'gzip_sha256', 'gzip_bytes', 'stored_key')}})
    return {'plan': plan, 'sources': sources, 'root': root, 'now': now, 'save': save, 'stages': stages,
        'payloads': payloads, 'mapping': mapping, 'bundle': bundle, 'map_raw': map_raw, 'manifest': manifest}


def execute(f):
    return e.parse_json(d._execute(f['plan'], f['sources'], f['root'], clock=lambda: f['now'], guard=lambda *_: None))


def test_local_read_claim_distinguished_from_failed_request_completed_and_unattempted(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); f['stages'](0, 'read'); f['stages'](1, 'failed', number=1); f['stages'](2, 'completed', number=2)
    result = execute(f)
    assert result['status'] == 'COMPLETED' and result['scope_spent'] is True
    assert result['census']['counts'] == {'input_read_claimed_no_upload': e.JsonNumber('1'), 'failed_or_unknown': e.JsonNumber('1'), 'completed': e.JsonNumber('1'), 'unattempted': e.JsonNumber('69')}
    assert result['census']['inputs'][1]['error_classification']['classes'] == ['quota']
    assert result['census']['all_uploads_completed'] is False
    assert b'PRIVATE-ROW-SENTINEL' not in e.canonical(result)
    assert result['new_looks'].fraction() == result['quantconnect_attempts'].fraction() == 0
    with pytest.raises(FileExistsError): execute(f)


@pytest.mark.parametrize('kind,expected', [('upload', 'upload_claimed_no_transport'), ('transport', 'transport_admitted_no_request'),
    ('no_terminal', 'request_terminal_unavailable'), ('succeeded', 'request_succeeded_no_completion')])
def test_intermediate_states_never_invent_completion(tmp_path, monkeypatch, kind, expected):
    f = fixture(tmp_path, monkeypatch); f['stages'](0, kind, number=1)
    result = execute(f)
    assert result['status'] == 'COMPLETED' and result['census']['inputs'][0]['status'] == expected
    assert result['census']['all_uploads_completed'] is False


def test_all72_matching_successful_requests_are_required(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    for index in range(72): f['stages'](index, 'completed', number=index + 1)
    answer = execute(f)
    assert answer['status'] == 'COMPLETED' and answer['census']['all_uploads_completed'] is True
    assert answer['census']['counts'] == {'completed': e.JsonNumber('72')}


def test_claim_precedes_every_existence_read_and_payloads_are_never_opened(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); f['stages'](0, 'read'); read = d._read; names = []
    def reading(directory, name, **kw):
        assert (f['root'] / (f['plan']['read_operation_id'] + '.claim.spent.json')).is_file()
        assert not name.startswith('gzip.') and name not in {row['plain_name'] for row in f['payloads']}
        names.append(name); return read(directory, name, **kw)
    monkeypatch.setattr(d, '_read', reading)
    assert execute(f)['status'] == 'COMPLETED'
    assert len([name for name in names if name.startswith('request.')]) == 128


def test_unrelated_off_old_operation_and_unknown_payload_responses_not_read(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); f['stages'](0, 'failed', number=3)
    for number, endpoint, manifest in ((1, 'backtests/read', d.MANIFEST_SHA256), (2, 'object/set', 'f' * 64)):
        request = 'request.' + f'{number:04d}'
        f['save'](request + '.spent.json', {'at': f['now'].isoformat(), 'endpoint': endpoint, 'payload_sha256': 'a' * 64, 'manifest_sha256': manifest})
        f['save'](request + '.projection.json', b'PRIVATE-OUTCOME-DO-NOT-READ')
    read = d._read; seen = []
    def reading(directory, name, **kw):
        assert name not in {'request.0001.projection.json', 'request.0002.projection.json', 'request.0001.terminal.json', 'request.0002.terminal.json'}
        seen.append(name); return read(directory, name, **kw)
    monkeypatch.setattr(d, '_read', reading); answer = execute(f)
    assert answer['status'] == 'COMPLETED' and answer['census']['unrelated_spent_request_count'].fraction() == 2
    assert 'request.0003.projection.json' in seen


@pytest.mark.parametrize('kind', ['foreign_manifest', 'wrong_mapping', 'wrong_payload', 'wrong_transport', 'wrong_completion', 'bad_clock', 'wrong_terminal', 'orphan_completed', 'duplicate_request'])
def test_unbound_metadata_refuses_with_consumed_scope(tmp_path, monkeypatch, kind):
    f = fixture(tmp_path, monkeypatch); f['stages'](0, 'completed', number=1); stage = 'compressed-input.' + f['payloads'][0]['gzip_sha256']
    def change(name, key, value):
        body = e.parse_json((f['root'] / name).read_bytes()); body[key] = value; f['save'](name, body)
    if kind == 'foreign_manifest': change(stage + '.read.spent.json', 'manifest_sha256', 'f' * 64)
    if kind == 'wrong_mapping': change(stage + '.read.spent.json', 'mapping_sha256', 'f' * 64)
    if kind == 'wrong_payload': change('request.0001.spent.json', 'payload_sha256', 'f' * 64)
    if kind == 'wrong_transport': change(stage + '.upload.transport.json', 'endpoint', 'backtests/read')
    if kind == 'wrong_completion': change(stage + '.completed.json', 'gzip_sha256', 'f' * 64)
    if kind == 'bad_clock': change(stage + '.read.spent.json', 'at', (f['now'] + timedelta(days=2)).isoformat())
    if kind == 'wrong_terminal': change('request.0001.terminal.json', 'original_wire_sha256', 'f' * 64)
    if kind == 'orphan_completed': (f['root'] / 'request.0001.spent.json').unlink()
    if kind == 'duplicate_request':
        f['save']('request.0002.spent.json', (f['root'] / 'request.0001.spent.json').read_bytes())
    answer = execute(f)
    assert answer['status'] == 'FAILED_OR_UNCERTAIN' and answer['scope_spent'] is True and answer['census'] is None


def test_split_packet_literal_without_execution_and_extra_code_refused(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch, split=True)
    assert execute(f)['status'] == 'COMPLETED'
    bad = deepcopy(f['bundle']); bad['candidates'][0]['files']['compressed_packet.py'] += 'raise RuntimeError("PRIVATE")\n'
    raw = e.canonical(bad); monkeypatch.setattr(d, 'BUNDLE_SHA256', d._sha(raw))
    with pytest.raises(ValueError): d._inventory(raw)


@pytest.mark.parametrize('kind', ['mode', 'symlink', 'hardlink', 'oversize', 'remaining'])
def test_fd_budget_and_custody_refuse_before_body(tmp_path, monkeypatch, kind):
    root = tmp_path / 'metadata'; root.mkdir(mode=0o700); path = root / 'value.json'; path.write_bytes(b'01234567890'); path.chmod(0o600)
    if kind == 'mode': path.chmod(0o644)
    if kind == 'hardlink': os.link(path, root / 'link')
    if kind == 'symlink':
        other = root / 'other'; other.write_bytes(path.read_bytes()); other.chmod(0o600); path.unlink(); path.symlink_to(other)
    maximum = 10 if kind in {'oversize', 'remaining'} else d.MAX_FILE
    reads = []; monkeypatch.setattr(d.os, 'read', lambda *_: reads.append(True) or b'')
    fd = d._open_directory(root)
    try:
        with pytest.raises((ValueError, OSError)): d._read(fd, path.name, maximum=maximum)
    finally: os.close(fd)
    assert reads == []


def test_fresh_clock_hash_bounds_and_cli_closed_failure(tmp_path, monkeypatch, capsys):
    f = fixture(tmp_path, monkeypatch); arguments = {key: f['plan'][key] for key in ('source_hashes', 'git_head', 'owner_instruction_sha256', 'created_utc', 'expires_utc', 'read_operation_id', 'expected_manifest_sha256', 'mode')}
    with pytest.raises(ValueError): d._plan(**{**arguments, 'expected_manifest_sha256': 'f' * 64})
    with pytest.raises(ValueError): d._plan(**{**arguments, 'expires_utc': (f['now'] + timedelta(hours=25)).isoformat()})
    def refused(**_kw): raise ValueError('PRIVATE-OUTCOME-DO-NOT-READ secret')
    monkeypatch.setattr(d, 'run', refused)
    assert d.main(['--read-operation-id', arguments['read_operation_id'], '--owner-instruction-sha256', 'a' * 64,
        '--created-utc', arguments['created_utc'], '--expires-utc', arguments['expires_utc'], '--expected-manifest-sha256', d.MANIFEST_SHA256]) == 1
    assert 'PRIVATE-OUTCOME-DO-NOT-READ' not in capsys.readouterr().out
