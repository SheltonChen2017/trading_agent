"""Decode only supplied, exactly pinned original TICKERS capture bytes.

The public production wrapper has no alternate pins, source root, parser or
row filter. It reads no files and invokes no historical operational entry.
Fresh source security/one-use admission belongs to the separately frozen
caller. Every original CSV row remains private and immutable in the result.
"""
from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import PurePosixPath
import re
import time
from types import MappingProxyType
import zipfile

from scripts import capture_arv2_sharadar as capture
from scripts import arv2_r298_reference_ticker_evidence as evidence

SCHEMA = 'arv2-r298-original-full-ticker-catalog-v1'
ARTIFACT_NAME = 'arv2-sharadar-source-20260914T003329843989Z'
MANIFEST_SHA256 = '94251ffdf0529b118ff331b98c4a144d97bc734380d7e7333f94045e4aa6f09b'
ARCHIVE_NAME, ARCHIVE_BYTES = '01-tickers-years-full.zip', 4937076
ARCHIVE_SHA256 = 'a7b129f159631ee50f1eefd2be8d4215c1c7818880570c0ad0a79c76c25e51bf'
MEMBER_BYTES = 24939614
MEMBER_SHA256 = '562577ea331805c4d50229b783e37216c9422c09d921b17dc950cf267ecf7697'
HEADER_BYTES = 291
HEADER_SHA256 = 'c9186ed191f4e51d5142287016dc99e3f80ecebed49aa63c3fa1ecf09e5d26f7'
EXPECTED_ROWS, FIELD_COUNT = 74150, 28
MAX_MANIFEST_BYTES, MAX_BUFFER_BYTES = 128 * 1024, 64 * 1024 * 1024
MAX_ROWS, MAX_FIELD_CHARS = 250000, 65536
CAPTURE_SOURCE_SHA256 = '17e516b4cc721c7f97c4690f54dfcc9d2d11d8cebd413100f2e2ffa68e663ca2'
ROW_HASH_SOURCE_SHA256 = '7153d0d44db66d93ea4a0fb9921c58276e56ad8a46274841c99aa3abaf67712f'
FALSE_FLAGS = {'filesystem_access_performed': False, 'provider_contact': False,
    'credential_access': False, 'qc_contact': False, 'old_operation_invoked': False,
    'old_control_read': False, 'original_capture_reaccepted': False,
    'historical_security_continuity_proven': False, 'fresh_source_security_authenticated': False,
    'metadata_is_historical_availability': False, 'provider_route_admitted': False,
    'price_coverage_proven': False, 'strategy_price_admitted': False,
    'strategy_nav_admitted': False, 'strategy_result_accepted': False,
    'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False,
    'raw_rows_disclosed': False}
FINITE = frozenset(('deadline', 'input', 'manifest', 'archive_binding', 'member_binding',
    'member_content', 'header_binding', 'csv', 'row', 'row_census', 'row_ambiguous',
    'delisting_census', 'private_catalog', 'receipt', 'unknown'))
canonical = capture.canonical_json_bytes


class Refused(ValueError):
    """Finite decoding refusal; never forward private data or exception text."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _budget(deadline):
    require(type(deadline) in (int, float) and math.isfinite(deadline)
        and time.monotonic() < deadline, 'deadline')


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


@dataclass(frozen=True)
class _ArchiveSpec:
    """Private bounded parser inputs, NOT a production admission alternative."""
    archive_bytes: int
    archive_sha256: str
    member_bytes: int
    member_sha256: str
    header_bytes: int
    header_sha256: str
    row_count: int


_PRODUCTION_SPEC = _ArchiveSpec(ARCHIVE_BYTES, ARCHIVE_SHA256, MEMBER_BYTES,
    MEMBER_SHA256, HEADER_BYTES, HEADER_SHA256, EXPECTED_ROWS)


class PrivateOriginalTickerCatalog:
    """Immutable private rows. Accessors are private-data operations, not receipts."""
    __slots__ = ('_columns', '_rows', '_digests', '_index', '_sealed')

    def __init__(self, columns, rows, digests):
        object.__setattr__(self, '_columns', tuple(columns))
        object.__setattr__(self, '_rows', tuple(tuple(row) for row in rows))
        object.__setattr__(self, '_digests', tuple(digests))
        index = {}
        for digest, row in zip(digests, self._rows, strict=True):
            index.setdefault(digest, []).append(row)
        object.__setattr__(self, '_index', MappingProxyType({
            digest: tuple(matches) for digest, matches in index.items()}))
        object.__setattr__(self, '_sealed', True)

    def __setattr__(self, name, value):
        raise TypeError('private original catalog is immutable')

    def __repr__(self):
        return '<PrivateOriginalTickerCatalog redacted; no source or operational authority>'

    def __reduce_ex__(self, protocol):
        raise TypeError('private original catalog must not be serialized')

    @property
    def columns(self):
        return self._columns

    @property
    def rows(self):
        return self._rows

    @property
    def row_count(self):
        return len(self._rows)

    def source_row(self, digest):
        require(_hash(digest) and digest in self._index, 'private_catalog')
        matches = self._index[digest]
        require(len(matches) == 1, 'row_ambiguous')
        return matches[0]

    def mapping_rows(self):
        """Explicit private tuple-of-dict copies for an in-memory all-route join."""
        return tuple(dict(zip(self._columns, row, strict=True)) for row in self._rows)


def profile_record():
    return {'schema': SCHEMA, 'purpose': 'supplied_fixed_original_full_TICKERS_catalog_only',
        'artifact_name': ARTIFACT_NAME, 'manifest_sha256': MANIFEST_SHA256,
        'manifest_maximum_bytes': MAX_MANIFEST_BYTES, 'marker_bytes': 65,
        'archive_name': ARCHIVE_NAME, 'archive_bytes': ARCHIVE_BYTES,
        'archive_sha256': ARCHIVE_SHA256, 'member_bytes': MEMBER_BYTES,
        'member_sha256': MEMBER_SHA256, 'header_bytes': HEADER_BYTES,
        'header_sha256': HEADER_SHA256, 'exact_rows': EXPECTED_ROWS,
        'exact_fields': FIELD_COUNT, 'maximum_CSV_field_chars': MAX_FIELD_CHARS,
        'source_hash_maximum_field_chars': evidence.MAX_FIELD_CHARS,
        'source_hash_maximum_row_bytes': evidence.MAX_ROW_BYTES,
        'capture_parser_source_sha256': CAPTURE_SOURCE_SHA256,
        'source_row_digest_source_sha256': ROW_HASH_SOURCE_SHA256,
        'capture_transport_required': capture.PRODUCTION_TRANSPORT,
        'source_row_hash_encoding': 'frozen_composer_UTF8_sorted_JSON_ensure_ascii_false_WITH_LF',
        'all_member_bytes_authenticated_before_CSV_or_source_row_hashing': True,
        'all_rows_preserved_without_witness_or_identity_filter': True,
        'duplicate_source_row_digests': 'retain_every_row_in_original_order_no_overwrite_or_drop',
        'direct_source_row_lookup': 'refuse_if_digest_has_multiple_original_rows',
        'delisting_census': 'unchanged_capture_Y_yes_1_true_N_no_0_false_blank_unknown',
        'CSV_global_field_limit_modified': False,
        'private_rows': 'immutable_tuple_values_with_redacted_container_no_serialization',
        'caller_must_hold_fresh_source_guard_through_normal_return': True,
        'synthetic_internal_helper_is_not_production_wrapper': True,
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}


def _checked_spec(spec):
    require(type(spec) is _ArchiveSpec
        and all(type(value) is int and 0 < value <= MAX_BUFFER_BYTES for value in (
            spec.archive_bytes, spec.member_bytes, spec.header_bytes))
        and type(spec.row_count) is int and 0 < spec.row_count <= MAX_ROWS
        and spec.header_bytes <= spec.member_bytes
        and all(_hash(value) for value in (spec.archive_sha256, spec.member_sha256, spec.header_sha256)),
        'input')
    return spec


def _declared_archive(manifest_raw):
    """Unchanged pure manifest parser; production pins are checked by its caller."""
    try:
        manifest, archives = capture._parse_manifest(manifest_raw, PurePosixPath(ARTIFACT_NAME))
    except (capture.SharadarCaptureError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise Refused('manifest') from None
    require(manifest['capture_transport'] == capture.PRODUCTION_TRANSPORT
        and len(archives) == len(capture.DATASET_ORDER), 'manifest')
    declared = archives[0]
    require(type(declared) is capture.SharadarArchiveBinding
        and declared.dataset is capture.SharadarDataset.TICKERS
        and declared.archive_file == ARCHIVE_NAME and len(declared.members) == 1, 'archive_binding')
    return declared


def _read_authenticated_member(archive_raw, declared, spec, deadline):
    """Bounded synthetic-test seam used only AFTER production's external gate."""
    _budget(deadline); _checked_spec(spec)
    require(type(archive_raw) is bytes and len(archive_raw) == spec.archive_bytes
        and sha(archive_raw) == spec.archive_sha256, 'archive_binding')
    require(type(declared) is capture.SharadarArchiveBinding
        and declared.dataset is capture.SharadarDataset.TICKERS and declared.archive_file == ARCHIVE_NAME
        and declared.archive_byte_count == spec.archive_bytes
        and declared.archive_sha256 == spec.archive_sha256 and len(declared.members) == 1, 'archive_binding')
    member = declared.members[0]
    require(type(member) is capture.SharadarMemberBinding
        and member.uncompressed_byte_count == spec.member_bytes
        and member.content_sha256 == spec.member_sha256
        and member.row_count == spec.row_count, 'member_binding')
    try:
        with zipfile.ZipFile(io.BytesIO(archive_raw), 'r') as zipped:
            infos = zipped.infolist()
            require(len(infos) == 1, 'member_binding')
            info = infos[0]
            capture._safe_zip_member(info)
            require(info.filename == member.name and info.compress_size == member.compressed_byte_count
                and info.file_size == spec.member_bytes and info.CRC == member.crc32
                and info.file_size <= max(1, info.compress_size) * capture.MAX_COMPRESSION_RATIO,
                'member_binding')
            with zipped.open(info) as handle:
                payload = handle.read(spec.member_bytes + 1)
            require(len(payload) == spec.member_bytes and sha(payload) == spec.member_sha256, 'member_content')
    except Refused:
        raise
    except (capture.SharadarCaptureError, ValueError, RuntimeError, zipfile.BadZipFile,
            zipfile.LargeZipFile, EOFError, OSError):
        raise Refused('member_content') from None
    _budget(deadline)
    return payload


def _parse_authenticated_payload(payload, declared, spec, deadline):
    """Private generic bounded parsing helper; produces NO production receipt."""
    _budget(deadline); _checked_spec(spec)
    require(type(payload) is bytes and len(payload) == spec.member_bytes
        and sha(payload) == spec.member_sha256, 'member_content')
    first, separator, _ = payload.partition(b'\n')
    header_raw = first + separator
    require(separator == b'\n' and len(header_raw) == spec.header_bytes
        and sha(header_raw) == spec.header_sha256, 'header_binding')
    require(type(declared) is capture.SharadarArchiveBinding and len(declared.members) == 1, 'member_binding')
    member = declared.members[0]
    # Do not modify the process-wide CSV limit. A smaller host limit refuses;
    # the per-value and frozen hash-helper limits still enforce our own bounds.
    require(csv.field_size_limit() >= MAX_FIELD_CHARS, 'csv')
    rows, digests, census = [], [], Counter()
    try:
        reader = csv.reader(io.StringIO(payload.decode('utf-8-sig', errors='strict'), newline=''), strict=True)
        header = tuple(next(reader))
        require(len(header) == FIELD_COUNT and len(set(header)) == FIELD_COUNT
            and header == member.columns and all(type(name) is str and name for name in header)
            and capture.REQUIRED_FIELDS[capture.SharadarDataset.TICKERS].issubset(header), 'header_binding')
        indexes = {name: header.index(name) for name in ('table', 'ticker', 'permaticker', 'isdelisted')}
        for values in reader:
            _budget(deadline)
            require(len(rows) < spec.row_count and len(rows) < MAX_ROWS
                and len(values) == FIELD_COUNT
                and all(type(value) is str and len(value) <= MAX_FIELD_CHARS for value in values), 'row_census')
            require(all(values[indexes[name]] for name in ('table', 'ticker', 'permaticker')), 'row')
            state = values[indexes['isdelisted']].strip().casefold()
            if state in ('y', 'yes', '1', 'true'): census['delisted'] += 1
            elif state in ('n', 'no', '0', 'false'): census['active'] += 1
            elif state == '': census['unknown'] += 1
            else: raise Refused('delisting_census')
            row = dict(zip(header, values, strict=True))
            try:
                digest = evidence.source_row_digest(row)
            except (evidence.Refused, ValueError, TypeError, UnicodeError, RecursionError):
                raise Refused('row') from None
            digests.append(digest); rows.append(tuple(values))
        require(len(rows) == spec.row_count == member.row_count, 'row_census')
    except Refused:
        raise
    except (csv.Error, ValueError, UnicodeError, StopIteration):
        raise Refused('csv') from None
    _budget(deadline)
    counts = {key: census[key] for key in ('active', 'delisted', 'unknown')}
    require(counts == {'active': declared.active_ticker_row_count,
        'delisted': declared.delisted_ticker_row_count,
        'unknown': declared.unknown_ticker_delisting_flag_row_count}, 'delisting_census')
    return PrivateOriginalTickerCatalog(header, rows, digests), counts


def decode_original_catalog(manifest_raw, marker_raw, archive_raw, *, deadline):
    """Fixed production wrapper: exact original bytes first, then all rows."""
    _budget(deadline)
    require(type(manifest_raw) is bytes and 0 < len(manifest_raw) <= MAX_MANIFEST_BYTES
        and sha(manifest_raw) == MANIFEST_SHA256
        and type(marker_raw) is bytes and marker_raw == (MANIFEST_SHA256 + '\n').encode('ascii')
        and type(archive_raw) is bytes and len(archive_raw) == ARCHIVE_BYTES
        and sha(archive_raw) == ARCHIVE_SHA256, 'archive_binding')
    declared = _declared_archive(manifest_raw)
    payload = _read_authenticated_member(archive_raw, declared, _PRODUCTION_SPEC, deadline)
    catalog, counts = _parse_authenticated_payload(payload, declared, _PRODUCTION_SPEC, deadline)
    receipt = {'schema': SCHEMA, 'status': 'fixed_original_full_TICKERS_bytes_decoded',
        'profile_sha256': sha(canonical(profile_record())), 'manifest_sha256': MANIFEST_SHA256,
        'archive_sha256': ARCHIVE_SHA256, 'archive_byte_count': ARCHIVE_BYTES,
        'member_sha256': MEMBER_SHA256, 'member_byte_count': MEMBER_BYTES,
        'header_sha256': HEADER_SHA256, 'header_byte_count': HEADER_BYTES,
        'csv_row_count': catalog.row_count, 'field_count': len(catalog.columns),
        'unique_source_row_count': len(catalog._index),
        'duplicate_source_row_count': catalog.row_count - len(catalog._index),
        'ordered_source_row_digests_sha256': sha(canonical(list(catalog._digests))),
        'delisting_flag_counts': counts, 'current_vintage_only': True,
        'result_cell': 0, **FALSE_FLAGS}
    validate_receipt(receipt)
    _budget(deadline)
    return receipt, catalog


def validate_receipt(value):
    fixed = {'schema': SCHEMA, 'status': 'fixed_original_full_TICKERS_bytes_decoded',
        'profile_sha256': sha(canonical(profile_record())), 'manifest_sha256': MANIFEST_SHA256,
        'archive_sha256': ARCHIVE_SHA256, 'archive_byte_count': ARCHIVE_BYTES,
        'member_sha256': MEMBER_SHA256, 'member_byte_count': MEMBER_BYTES,
        'header_sha256': HEADER_SHA256, 'header_byte_count': HEADER_BYTES,
        'csv_row_count': EXPECTED_ROWS, 'field_count': FIELD_COUNT,
        'current_vintage_only': True,
        'result_cell': 0, **FALSE_FLAGS}
    variable = {'ordered_source_row_digests_sha256', 'delisting_flag_counts',
        'unique_source_row_count', 'duplicate_source_row_count'}
    require(type(value) is dict and all(type(key) is str for key in value)
        and set(value) == set(fixed) | variable
        and all(type(value[key]) is type(expected) and value[key] == expected
            for key, expected in fixed.items()), 'receipt')
    counts = value['delisting_flag_counts']
    require(_hash(value['ordered_source_row_digests_sha256']) and type(counts) is dict
        and type(value['unique_source_row_count']) is int
        and 1 <= value['unique_source_row_count'] <= EXPECTED_ROWS
        and type(value['duplicate_source_row_count']) is int
        and value['duplicate_source_row_count'] == EXPECTED_ROWS - value['unique_source_row_count']
        and set(counts) == {'active', 'delisted', 'unknown'}
        and all(type(count) is int and 0 <= count <= EXPECTED_ROWS for count in counts.values())
        and sum(counts.values()) == EXPECTED_ROWS and counts['active'] > 0 and counts['delisted'] > 0,
        'receipt')
    return json.loads(canonical(value))
