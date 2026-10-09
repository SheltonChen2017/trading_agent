"""Offline full-byte/row accounting of the exact owner-supplied Sharadar capture.

This is a custody/schema/coverage audit, not ingestion into a strategy. Numeric
fields are opaque strings. No price join, calculation, historical availability,
security mapping, licence authentication or outcome-look grant is inferred.
The caller must deny the whole process-tree network when using this module.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import zipfile
import zlib


CAPTURE = Path('/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__analyst_revisions_v2/artifacts/analyst_revisions_v2/sharadar_capture/arv2-sharadar-source-20260914T003329843989Z')
MANIFEST_SHA256 = '94251ffdf0529b118ff331b98c4a144d97bc734380d7e7333f94045e4aa6f09b'
DATASETS = ('tickers', 'actions', 'fundamentals')
FILES = ('01-tickers-years-full.zip', '02-actions-years-full.zip', '03-fundamentals-years-full.zip')
DIMENSIONS = ('ARQ', 'ART', 'ARY', 'MRQ', 'MRT', 'MRY')
MAX_ARCHIVE = 4 * 1024**3
MAX_MEMBER = 16 * 1024**3
MAX_ROWS = 100_000_000


class SuppliedSharadarAuditError(ValueError):
    """Refusals omit private rows, filenames from the manifest and OS details."""


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise SuppliedSharadarAuditError('REFUSED: ' + code)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _version(info) -> tuple:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _open_leaf(root: Path, name: str, limit: int):
    _require(root.is_absolute() and not root.is_symlink() and root.resolve() == root,
             'capture-path-redirected')
    path = root / name
    try:
        named = path.lstat()
        _require(stat.S_ISREG(named.st_mode) and named.st_nlink == 1
                 and 0 < named.st_size <= limit, 'capture-leaf-unsafe')
        # Reject named special files before open, and refuse a racing FIFO
        # substitution without ever blocking for an external writer.
        handle = os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb')
        opened = os.fstat(handle.fileno())
    except OSError:
        raise SuppliedSharadarAuditError('REFUSED: capture-leaf-unavailable') from None
    if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
            or not 0 < opened.st_size <= limit or _version(named) != _version(opened)):
        handle.close()
        raise SuppliedSharadarAuditError('REFUSED: capture-leaf-unsafe')
    return path, handle, _version(opened)


def _unchanged(path, handle, version) -> None:
    try:
        _require(path.resolve() == path and _version(path.lstat()) == version
                 and _version(os.fstat(handle.fileno())) == version,
                 'capture-changed-during-read')
    except OSError:
        raise SuppliedSharadarAuditError('REFUSED: capture-changed-during-read') from None


def _strict_json(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, 'duplicate-manifest-key')
            result[key] = value
        return result
    try:
        result = json.loads(raw, object_pairs_hook=pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise SuppliedSharadarAuditError('REFUSED: malformed-manifest') from None
    _require(type(result) is dict, 'manifest-not-object')
    return result


class _HashedRaw(io.RawIOBase):
    """Hash every uncompressed byte, including values excluded from analytics."""
    def __init__(self, source, limit: int):
        self.source, self.limit, self.count = source, limit, 0
        self.digest = hashlib.sha256()

    def readable(self):
        return True

    def readinto(self, buffer):
        raw = self.source.read(len(buffer))
        self.count += len(raw)
        _require(self.count <= self.limit, 'member-byte-limit')
        self.digest.update(raw)
        buffer[:len(raw)] = raw
        return len(raw)


def _date_text(raw: str) -> bool:
    try:
        return bool(raw) and date.fromisoformat(raw).isoformat() == raw
    except ValueError:
        return False


def _audit_capture(capture: Path, expected_manifest_sha256: str) -> dict:
    """Read exact supplied archives once, without extraction or any row export.

    The external digest is mandatory. Manifest-reported counts/hashes are
    checked against independently observed ZIP and CSV bytes, not copied as
    observations. Current-export/as-reported-date limitations remain explicit.
    """
    _require(type(expected_manifest_sha256) is str
             and re.fullmatch('[0-9a-f]{64}', expected_manifest_sha256) is not None,
             'manifest-anchor-invalid')
    path, handle, version = _open_leaf(capture, 'manifest.json', 1024**2)
    with handle:
        raw = handle.read(1024**2 + 1)
        _require(_sha(raw) == expected_manifest_sha256, 'manifest-anchor-mismatch')
        _unchanged(path, handle, version)
    manifest = _strict_json(raw)
    _require(manifest.get('schema') == 'arv2-sharadar-source-capture-artifact-v2'
             and manifest.get('api_key_persisted') is False
             and manifest.get('redirect_url_persisted') is False
             and manifest.get('fundamentals_downstream_admitted_dimension') == 'ART',
             'manifest-profile-differs')
    entries = manifest.get('archives')
    _require(type(entries) is list and len(entries) == 3
             and all(type(item) is dict for item in entries)
             and tuple(item.get('dataset') for item in entries) == DATASETS
             and tuple(item.get('archive_file') for item in entries) == FILES,
             'archive-inventory-differs')
    for key in ('total_row_count', 'total_archive_byte_count', 'total_uncompressed_byte_count'):
        _require(type(manifest.get(key)) is int and manifest[key] > 0, 'manifest-count-type')
    for entry in entries:
        for key in ('archive_byte_count', 'row_count', 'active_ticker_row_count',
                    'delisted_ticker_row_count', 'unknown_ticker_delisting_flag_row_count'):
            _require(type(entry.get(key)) is int and entry[key] >= 0, 'manifest-count-type')
        declared = entry.get('members')
        _require(type(declared) is list and len(declared) == 1 and type(declared[0]) is dict,
                 'member-inventory-differs')
        for key in ('row_count', 'uncompressed_byte_count', 'compressed_byte_count', 'crc32'):
            _require(type(declared[0].get(key)) is int and declared[0][key] >= 0, 'manifest-count-type')
        counts = entry.get('fundamental_dimension_counts')
        _require(type(counts) is list and all(type(item) is dict
                 and set(item) == {'dimension', 'row_count'} and type(item['dimension']) is str
                 and type(item['row_count']) is int and item['row_count'] >= 0 for item in counts),
                 'manifest-count-type')
    reports = []
    for dataset, name, entry in zip(DATASETS, FILES, entries, strict=True):
        path, handle, version = _open_leaf(capture, name, MAX_ARCHIVE)
        with handle:
            digest, count = hashlib.sha256(), 0
            while chunk := handle.read(1024**2):
                digest.update(chunk)
                count += len(chunk)
                _require(count <= min(MAX_ARCHIVE, version[2]), 'archive-byte-limit')
            _require(count == entry.get('archive_byte_count')
                     and digest.hexdigest() == entry.get('archive_sha256'),
                     'archive-byte-anchor-mismatch')
            handle.seek(0)
            try:
                with zipfile.ZipFile(handle) as envelope:
                    members = envelope.infolist()
                    declared = entry.get('members')
                    _require(len(members) == 1 and type(declared) is list and len(declared) == 1
                             and type(declared[0]) is dict, 'member-inventory-differs')
                    member, expected = members[0], declared[0]
                    _require(member.filename == dataset + '.csv' == expected.get('name')
                             and not member.flag_bits & 1
                             and member.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                             and 0 < member.file_size <= MAX_MEMBER
                             and member.file_size == expected.get('uncompressed_byte_count')
                             and member.compress_size == expected.get('compressed_byte_count')
                             and member.CRC == expected.get('crc32'), 'zip-envelope-differs')
                    with envelope.open(member) as source:
                        hashed = _HashedRaw(source, member.file_size)
                        with io.TextIOWrapper(io.BufferedReader(hashed), encoding='utf-8-sig', newline='') as text:
                            reader = csv.reader(text, strict=True)
                            columns = next(reader)
                            _require(columns == expected.get('columns') and len(columns) == len(set(columns))
                                     and all(re.fullmatch('[a-z][a-z0-9_]{0,63}', c) for c in columns),
                                     'csv-schema-differs')
                            indices = {column: position for position, column in enumerate(columns)}
                            required = {'tickers': {'table', 'isdelisted', 'secfilings'},
                                        'actions': {'date', 'action'},
                                        'fundamentals': {'dimension', 'date', 'reportperiod', 'lastupdated'}}[dataset]
                            _require(required <= indices.keys(), 'required-metadata-columns-missing')
                            rows, dimensions, flags, invalid_dates = 0, Counter(), Counter(), 0
                            date_min, date_max, art_scope_count = None, None, 0
                            for values in reader:
                                _require(rows < MAX_ROWS and len(values) == len(columns)
                                         and all('\x00' not in value for value in values), 'csv-row-shape-differs')
                                rows += 1
                                if dataset == 'tickers':
                                    flag = values[indices['isdelisted']]
                                    flags[flag if flag in ('N', 'Y') else 'unknown'] += 1
                                else:
                                    observed_date = values[indices['date']]
                                    valid = _date_text(observed_date)
                                    invalid_dates += not valid
                                    if valid:
                                        date_min = observed_date if date_min is None else min(date_min, observed_date)
                                        date_max = observed_date if date_max is None else max(date_max, observed_date)
                                    if dataset == 'fundamentals':
                                        dimension = values[indices['dimension']]
                                        _require(dimension in DIMENSIONS, 'unrecognized-fundamental-dimension')
                                        dimensions[dimension] += 1
                                        art_scope_count += dimension == 'ART' and valid and '2006-01-01' <= observed_date <= '2026-06-30'
                            observed_member_bytes, observed_member_sha = hashed.count, hashed.digest.hexdigest()
                    _require(observed_member_bytes == member.file_size
                             and observed_member_sha == expected.get('content_sha256')
                             and rows == expected.get('row_count') == entry.get('row_count'),
                             'csv-byte-or-row-anchor-mismatch')
                    if dataset == 'fundamentals':
                        _require([{'dimension': key, 'row_count': dimensions[key]} for key in sorted(dimensions)]
                                 == entry.get('fundamental_dimension_counts'), 'dimension-count-anchor-mismatch')
                    if dataset == 'tickers':
                        _require(flags['N'] == entry.get('active_ticker_row_count')
                                 and flags['Y'] == entry.get('delisted_ticker_row_count')
                                 and flags['unknown'] == entry.get('unknown_ticker_delisting_flag_row_count'),
                                 'delisting-count-anchor-mismatch')
                    report = {'dataset': dataset, 'archive_sha256': digest.hexdigest(), 'archive_bytes': count,
                              'member_sha256': observed_member_sha, 'member_bytes': observed_member_bytes,
                              'schema_sha256': _sha(json.dumps(columns, separators=(',', ':')).encode()),
                              'column_count': len(columns), 'rows': rows,
                              'dimension_counts': dict(sorted(dimensions.items())),
                              'current_delisting_flag_counts': dict(sorted(flags.items())),
                              'invalid_metadata_dates': invalid_dates, 'metadata_date_min': date_min,
                              'metadata_date_max': date_max, 'ART_rows_in_filing_scope_date_range': art_scope_count}
            except (zipfile.BadZipFile, csv.Error, UnicodeError, StopIteration, KeyError, OSError,
                    zlib.error, EOFError):
                raise SuppliedSharadarAuditError('REFUSED: bounded-archive-inspection-failed') from None
            _unchanged(path, handle, version)
            reports.append(report)
    _require(sum(r['rows'] for r in reports) == manifest.get('total_row_count')
             and sum(r['archive_bytes'] for r in reports) == manifest.get('total_archive_byte_count')
             and sum(r['member_bytes'] for r in reports) == manifest.get('total_uncompressed_byte_count'),
             'capture-total-anchor-mismatch')
    # Reopen the original anchor after all three long reads; concurrent changes
    # cannot produce an admitted audit against a stale supplied manifest.
    path, handle, version = _open_leaf(capture, 'manifest.json', 1024**2)
    with handle:
        _require(_sha(handle.read(1024**2 + 1)) == expected_manifest_sha256,
                 'manifest-changed-during-audit')
        _unchanged(path, handle, version)
    return {'schema': 'insider-supplied-sharadar-full-custody-audit-v1',
            'manifest_sha256': expected_manifest_sha256, 'archives': reports,
            'numeric_fields_treated_as_opaque_text': True, 'raw_rows_exported': 0,
            'fundamentals_candidate_dimension': 'ART', 'point_in_time_intraday_verified': False,
            'historical_identity_listing_verified': False, 'rights_authenticated': False,
            'source_authenticated': False, 'canonical_released': False,
            'provider_requests': 0, 'research_looks': 0, 'qc_jobs': 0, 'backtests': 0}


def audit_capture(capture: Path, expected_manifest_sha256: str) -> dict:
    """Public sanitized operational boundary; no OS/private content escapes."""
    try:
        return _audit_capture(capture, expected_manifest_sha256)
    except (OSError, zlib.error, EOFError):
        raise SuppliedSharadarAuditError('REFUSED: capture-read-operation-failed') from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        result = audit_capture(CAPTURE, args.manifest_sha256)
    except SuppliedSharadarAuditError as exc:
        print(json.dumps({'audit_refused': str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
