"""Bounded compression metadata fixture rendering; no real private payload reads."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

import pytest
from research.target_price_revisions_qc import extended_bundle_compressed as d

e = d.e
PUBLIC_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def deny_actual(monkeypatch):
    import http.client
    def deny(*_a, **_kw): raise AssertionError('actual network/private/credential/source subprocess forbidden')
    monkeypatch.setattr(http.client, 'HTTPSConnection', deny)
    monkeypatch.setattr(d.subprocess, 'run', deny)
    opening = d.compression._open_directory
    def guarded(path):
        assert not path.is_relative_to(d.LANE)
        return opening(path)
    monkeypatch.setattr(d.compression, '_open_directory', guarded)


def fixture(tmp_path):
    # These exact public code/hash descriptors are not licensed input rows.
    sources = {name: (PUBLIC_ROOT / name).read_bytes() for name in d.SOURCE_PATHS}
    hashes = {name: d._sha(raw) for name, raw in sources.items()}
    original = e.parse_json(sources[d.BUNDLE]); now = datetime.now(timezone.utc)
    rows = []
    for number, item in enumerate(original['inputs']):
        gz = f'{number + 1:064x}'; name = 'gzip.' + gz + '.json'
        rows.append({'plain_name': item['name'], 'logical_key': item['key'], 'plain_sha256': item['sha256'],
            'plain_bytes': item['bytes'], 'stored_name': name, 'stored_key': item['key'].rsplit('/', 1)[0] + '/' + name,
            'gzip_sha256': gz, 'gzip_bytes': 1})
    mapping = {'schema': 'tpr-ext26-gzip-input-map-v1', 'study_id': e.STUDY_ID, 'freeze_sha256': e.FREEZE_SHA256,
        'preparation_sha256': original['preparation_sha256'], 'bundle_sha256': d.BUNDLE_SHA256,
        'processing_operation_id': d.COMPRESSION_OPERATION, 'processing_plan_sha256': 'a' * 64,
        'encoding': 'gzip', 'gzip_level': 9, 'gzip_mtime': 0, 'payloads': rows}
    mapping_raw = e.canonical(mapping)
    receipt = {key: False for key in d.RECEIPT_KEYS}
    receipt.update(schema='tpr-ext26-compression-receipt-v1', study_id=e.STUDY_ID, freeze_sha256=e.FREEZE_SHA256,
        operation_id=d.COMPRESSION_OPERATION, plan_sha256='a' * 64, git_head='b' * 40,
        source_hashes={name: hashes[name] for name in d.compression.SOURCE_PATHS}, owner_instruction_sha256='c' * 64,
        bundle_sha256=d.BUNDLE_SHA256, preparation_sha256=original['preparation_sha256'], status='COMPLETED', scope_spent=True,
        failure=None, input_count=72, processed_count=72, original_bytes=d.compression.ORIGINAL_BYTES, gzip_bytes=72,
        ratio={'numerator': 72, 'denominator': d.compression.ORIGINAL_BYTES}, payloads=rows,
        original_read_bytes=2 * d.compression.ORIGINAL_BYTES, derived_read_bytes=72 + len(mapping_raw), stored_derived_bytes=72 + len(mapping_raw),
        mapping_name=d.MAPPING_NAME, mapping_sha256=d._sha(mapping_raw), mapping_bytes=len(mapping_raw), encoding='gzip',
        gzip_level=9, gzip_mtime=0, gzip_filename='', python_version='synthetic', zlib_compile_version='synthetic', zlib_runtime_version='synthetic',
        originals_retained_unchanged=True, decompressed_bytes_exact=True, cloud_uploads=0, cloud_deletes=0,
        quantconnect_attempts=0, development_looks=0, ended_utc=now.isoformat())
    receipt_raw = e.canonical(receipt)
    plan = d._plan(source_hashes=hashes, git_head='a' * 40, owner_instruction_sha256='b' * 64,
        created_utc=(now - timedelta(seconds=1)).isoformat(), expires_utc=(now + timedelta(hours=1)).isoformat(),
        read_operation_id='TPR-EXT26-COMPRESSED-BUNDLE-SYNTHETIC-001', expected_receipt_sha256=d._sha(receipt_raw),
        expected_mapping_sha256=d._sha(mapping_raw), mode='offline-fixture')
    root = tmp_path / 'private'; root.mkdir(mode=0o700)
    for name, raw in ((d.RECEIPT_NAME, receipt_raw), (d.MAPPING_NAME, mapping_raw)):
        (root / name).write_bytes(raw); (root / name).chmod(0o600)
    return plan, sources, root, now, receipt_raw, mapping_raw, original


def execute(f):
    return e.parse_json(d._execute(f[0], f[1], f[2], clock=lambda: f[3], guard=lambda *_: None))


def test_claim_before_exact_two_metadata_reads_originals_config_hashes_and_caps_unchanged(tmp_path, monkeypatch):
    f = fixture(tmp_path); read, seen = d.compression._read, []
    def observing(directory, name, **kw):
        assert (f[2] / (f[0]['read_operation_id'] + '.claim.spent.json')).exists()
        assert name in {d.RECEIPT_NAME, d.MAPPING_NAME}
        seen.append(name); return read(directory, name, **kw)
    monkeypatch.setattr(d.compression, '_read', observing)
    report = execute(f)
    assert report['status'] == 'COMPLETED' and report['scope_spent'] is True and seen == [d.RECEIPT_NAME, d.MAPPING_NAME]
    bundle = report['bundle']; assert bundle['inputs'] == f[6]['inputs'] and bundle['preparation_sha256'] == f[6]['preparation_sha256']
    for current, original in zip(bundle['candidates'], f[6]['candidates']):
        assert current['candidate_id'] == original['candidate_id'] and current['config_raw'] == original['config_raw']
        assert current['input_hashes'] == original['input_hashes'] and current['project_name'] == original['project_name']
        expected = 1 if e.CANDIDATES[current['candidate_id']] == 'tpr_on' else 2
        assert current['planned_attempt'].fraction() == expected
        assert d.old._literal(current['files']['main.py'], 'EXPECTED_ATTEMPT') == expected
        assert all(len(text.encode()) <= 60000 for text in current['files'].values())
        for name, old_text in original['files'].items():
            if name != 'main.py': assert current['files'][name] == old_text
    assert 'compressed_packet.py' in bundle['candidates'][0]['files']
    assert not any(name.startswith(('signal_packet', 'compressed_packet')) for name in bundle['candidates'][1]['files'])
    assert set(f[6]['repository_sources']) <= set(bundle['repository_sources']) and len(bundle['repository_sources']) <= 31
    assert report['read_bytes'].fraction() == len(f[4]) + len(f[5])
    with pytest.raises(FileExistsError): execute(f)


@pytest.mark.parametrize('kind', ['receipt_hash', 'mapping_hash', 'failed', 'partial', 'changed_plain', 'source', 'roundtrip_flag', 'old_input', 'ratio', 'physical_reads', 'future', 'extra'])
def test_refuses_any_unverified_or_changed_compression_proof(tmp_path, kind):
    f = fixture(tmp_path); receipt, mapping = e.parse_json(f[4]), e.parse_json(f[5])
    if kind == 'receipt_hash': f[0]['expected_receipt_sha256'] = 'c' * 64
    elif kind == 'mapping_hash': f[0]['expected_mapping_sha256'] = 'c' * 64
    elif kind == 'failed': receipt['status'] = 'FAILED_OR_UNCERTAIN'
    elif kind == 'partial': receipt['processed_count'] = e.JsonNumber('71')
    elif kind == 'changed_plain': receipt['payloads'][0]['plain_sha256'] = 'c' * 64
    elif kind == 'source': receipt['source_hashes'][d.PREFIX + 'extended_compression.py'] = 'c' * 64
    elif kind == 'roundtrip_flag': receipt['decompressed_bytes_exact'] = False
    elif kind == 'old_input': receipt['preparation_sha256'] = 'c' * 64
    elif kind == 'ratio': receipt['ratio']['numerator'] = e.JsonNumber('99')
    elif kind == 'physical_reads': receipt['original_read_bytes'] = e.JsonNumber('1')
    elif kind == 'future': receipt['ended_utc'] = (f[3] + timedelta(seconds=1)).isoformat()
    elif kind == 'extra': receipt['new_authority'] = True
    if kind not in {'receipt_hash', 'mapping_hash'}:
        raw = e.canonical(receipt); (f[2] / d.RECEIPT_NAME).write_bytes(raw); f[0]['expected_receipt_sha256'] = d._sha(raw)
    report = execute(f)
    assert report['status'] == 'FAILED_OR_UNCERTAIN' and report['scope_spent'] is True and report['bundle'] is None


def test_packet_split_is_closed_and_reconstructs_exact_bytes():
    raw = b'{"public_metadata":"' + b'a' * 90000 + b'"}'
    files = d._packets(raw)
    from research.target_price_revisions_qc import extended_operations_compressed as ops
    assert len(files) > 1 and ops._packet(files) == raw
    assert all(len(text.encode()) <= 60000 for text in files.values())


def test_metadata_custody_missing_or_oversized_refuses_after_claim(tmp_path):
    f = fixture(tmp_path); path = f[2] / d.MAPPING_NAME; path.chmod(0o644)
    report = execute(f)
    assert report['status'] == 'FAILED_OR_UNCERTAIN' and report['scope_spent'] is True


def test_wrong_import_location_refuses_before_private_claim(monkeypatch):
    monkeypatch.setattr(d.storage, '__file__', '/unrelated/extended_compressed_store.py')
    with pytest.raises(ValueError): d.run()
