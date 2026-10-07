"""Invented private captures only; never real rows or requests."""
import csv
import hashlib
import io
import json
import zipfile

import pytest

import research.insider_buying_supplied_sharadar_audit as audit


def capture(root, *, override=None, dimension='ART'):
    columns = [('table', 'isdelisted', 'secfilings'), ('date', 'action'),
               ('dimension', 'date', 'reportperiod', 'lastupdated', 'equity')]
    rows = [[('stocks', 'N', '')], [('2006-01-03', 'listing')],
            [(dimension, '2006-01-03', '2005-12-31', '2026-09-14', 'opaque-not-calculated')]]
    entries = []
    for dataset, name, fields, values in zip(audit.DATASETS, audit.FILES, columns, rows, strict=True):
        output = io.StringIO(newline='')
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(fields)
        writer.writerows(values)
        member = output.getvalue().encode()
        with zipfile.ZipFile(root / name, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(dataset + '.csv', member)
        with zipfile.ZipFile(root / name) as archive:
            info = archive.infolist()[0]
        raw = (root / name).read_bytes()
        entries.append({'dataset': dataset, 'archive_file': name, 'archive_byte_count': len(raw),
                        'archive_sha256': hashlib.sha256(raw).hexdigest(), 'row_count': 1,
                        'members': [{'name': dataset + '.csv', 'columns': list(fields), 'row_count': 1,
                                     'uncompressed_byte_count': len(member), 'compressed_byte_count': info.compress_size,
                                     'crc32': info.CRC, 'content_sha256': hashlib.sha256(member).hexdigest()}],
                        'active_ticker_row_count': 1 if dataset == 'tickers' else 0,
                        'delisted_ticker_row_count': 0, 'unknown_ticker_delisting_flag_row_count': 0,
                        'fundamental_dimension_counts': [{'dimension': dimension, 'row_count': 1}]
                        if dataset == 'fundamentals' else []})
    manifest = {'schema': 'arv2-sharadar-source-capture-artifact-v2', 'api_key_persisted': False,
                'redirect_url_persisted': False, 'fundamentals_downstream_admitted_dimension': 'ART',
                'archives': entries, 'total_row_count': 3,
                'total_archive_byte_count': sum(item['archive_byte_count'] for item in entries),
                'total_uncompressed_byte_count': sum(item['members'][0]['uncompressed_byte_count'] for item in entries)}
    if override:
        override(manifest)
    raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    (root / 'manifest.json').write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_full_independent_bytes_rows_metadata_without_financial_arithmetic(tmp_path):
    sha = capture(tmp_path)
    result = audit.audit_capture(tmp_path, sha)
    assert sum(item['rows'] for item in result['archives']) == 3
    assert result['archives'][2]['dimension_counts'] == {'ART': 1}
    assert result['archives'][2]['ART_rows_in_filing_scope_date_range'] == 1
    assert result['archives'][1]['metadata_date_min'] == '2006-01-03'
    assert 'opaque-not-calculated' not in json.dumps(result)
    for key in ('point_in_time_intraday_verified', 'historical_identity_listing_verified',
                'rights_authenticated', 'source_authenticated', 'canonical_released'):
        assert result[key] is False
    for key in ('raw_rows_exported', 'provider_requests', 'research_looks', 'qc_jobs', 'backtests'):
        assert result[key] == 0


@pytest.mark.parametrize('digest', ['a'*64, '', None, 'G'*64])
def test_external_manifest_anchor_required(tmp_path, digest):
    capture(tmp_path)
    with pytest.raises(audit.SuppliedSharadarAuditError, match='manifest-anchor'):
        audit.audit_capture(tmp_path, digest)


@pytest.mark.parametrize('key,value,match', [
    ('row_count', 2, 'csv-byte-or-row-anchor'),
    ('archive_sha256', 'b'*64, 'archive-byte-anchor'),
    ('fundamental_dimension_counts', [], 'dimension-count-anchor'),
])
def test_manifest_cannot_assert_unobserved_content(tmp_path, key, value, match):
    sha = capture(tmp_path, override=lambda m: m['archives'][2].update({key: value}))
    with pytest.raises(audit.SuppliedSharadarAuditError, match=match):
        audit.audit_capture(tmp_path, sha)


def test_actual_member_digest_checked(tmp_path):
    sha = capture(tmp_path, override=lambda m: m['archives'][2]['members'][0].update(content_sha256='b'*64))
    with pytest.raises(audit.SuppliedSharadarAuditError, match='csv-byte-or-row-anchor'):
        audit.audit_capture(tmp_path, sha)


def test_declared_totals_checked(tmp_path):
    sha = capture(tmp_path, override=lambda m: m.update(total_row_count=4))
    with pytest.raises(audit.SuppliedSharadarAuditError, match='capture-total-anchor'):
        audit.audit_capture(tmp_path, sha)


def test_boolean_count_is_not_a_measured_row_count(tmp_path):
    sha = capture(tmp_path, override=lambda m: m['archives'][2].update(row_count=True))
    with pytest.raises(audit.SuppliedSharadarAuditError, match='manifest-count-type'):
        audit.audit_capture(tmp_path, sha)


def test_unrecognized_dimension_refuses_without_echo(tmp_path):
    sha = capture(tmp_path, dimension='private-sensitive-value')
    with pytest.raises(audit.SuppliedSharadarAuditError, match='unrecognized-fundamental-dimension') as exc:
        audit.audit_capture(tmp_path, sha)
    assert 'private-sensitive-value' not in str(exc.value)


def test_manifest_schema_alias_or_path_injection_refused(tmp_path):
    sha = capture(tmp_path, override=lambda m: m['archives'][0].update(archive_file='../secret'))
    with pytest.raises(audit.SuppliedSharadarAuditError, match='archive-inventory'):
        audit.audit_capture(tmp_path, sha)


def test_symlink_capture_refused(tmp_path):
    real = tmp_path / 'actual'
    real.mkdir()
    sha = capture(real)
    link = tmp_path / 'linked'
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(audit.SuppliedSharadarAuditError, match='capture-path'):
        audit.audit_capture(link, sha)


def test_hardlinked_leaf_refused(tmp_path):
    sha = capture(tmp_path)
    import os
    os.link(tmp_path / audit.FILES[0], tmp_path / 'linked.zip')
    with pytest.raises(audit.SuppliedSharadarAuditError, match='capture-leaf-unsafe'):
        audit.audit_capture(tmp_path, sha)


def test_read_only_inspection_changes_no_input_bytes(tmp_path):
    sha = capture(tmp_path)
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in tmp_path.iterdir()}
    audit.audit_capture(tmp_path, sha)
    assert {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in tmp_path.iterdir()} == before


def test_invalid_deflate_is_a_sanitized_refusal(tmp_path):
    capture(tmp_path)
    target = tmp_path / audit.FILES[2]
    raw = bytearray(target.read_bytes())
    import struct
    name_size, extra_size = struct.unpack_from('<HH', raw, 26)
    raw[30 + name_size + extra_size] = 255
    target.write_bytes(raw)
    manifest = json.loads((tmp_path / 'manifest.json').read_bytes())
    manifest['archives'][2]['archive_sha256'] = hashlib.sha256(raw).hexdigest()
    anchored = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    (tmp_path / 'manifest.json').write_bytes(anchored)
    with pytest.raises(audit.SuppliedSharadarAuditError, match='bounded-archive-inspection-failed'):
        audit.audit_capture(tmp_path, hashlib.sha256(anchored).hexdigest())


class _ReadFault:
    def __init__(self, handle, *, growth=False):
        self.handle, self.growth = handle, growth

    def __getattr__(self, name):
        return getattr(self.handle, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.handle.close()

    def read(self, size):
        if not self.growth:
            raise OSError('INVENTED_PRIVATE_OS_DETAIL')
        raw = self.handle.read(size)
        return raw + b'invented-growth' * 1000 if raw else raw


def test_operational_read_fault_is_a_sanitized_refusal(tmp_path, monkeypatch):
    sha = capture(tmp_path)
    original = audit._open_leaf
    def open_leaf(*args):
        path, handle, version = original(*args)
        return path, _ReadFault(handle), version
    monkeypatch.setattr(audit, '_open_leaf', open_leaf)
    with pytest.raises(audit.SuppliedSharadarAuditError) as exc:
        audit.audit_capture(tmp_path, sha)
    assert 'INVENTED_PRIVATE_OS_DETAIL' not in str(exc.value)


def test_growing_archive_stops_at_first_read_bound(tmp_path, monkeypatch):
    sha = capture(tmp_path)
    original = audit._open_leaf
    def open_leaf(*args):
        path, handle, version = original(*args)
        return path, _ReadFault(handle, growth=True) if path.name.endswith('.zip') else handle, version
    monkeypatch.setattr(audit, '_open_leaf', open_leaf)
    with pytest.raises(audit.SuppliedSharadarAuditError, match='archive-byte-limit'):
        audit.audit_capture(tmp_path, sha)


def test_fifo_is_refused_before_blocking_open(tmp_path):
    import os
    import threading
    fifo = tmp_path / audit.FILES[0]
    os.mkfifo(fifo)
    errors = []
    def read():
        try:
            audit._open_leaf(tmp_path, audit.FILES[0], audit.MAX_ARCHIVE)
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=read)
    thread.start()
    thread.join(0.2)
    blocked = thread.is_alive()
    if blocked:
        # Always release the deliberately blocked pre-fix reader before failing.
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        os.close(fd)
        thread.join(2)
    assert not thread.is_alive()
    assert not blocked, 'unsafe blocking open occurred before file-type validation'
    assert len(errors) == 1 and isinstance(errors[0], audit.SuppliedSharadarAuditError)
