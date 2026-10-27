"""Synthetic bounded decoder seams; production pins are never overridden."""
import ast
import copy
import csv
from dataclasses import replace
import inspect
import io
import json
import pickle
import time
from types import SimpleNamespace as NS
import zipfile

import pytest

from scripts import arv2_r298_original_ticker_catalog as m


@pytest.fixture(autouse=True)
def no_old_operations(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('historical operational entry point')
    for name in ('capture_sharadar_history', 'load_sharadar_capture_artifact',
            '_visit_authenticated_sharadar_capture_rows_for_bridge'):
        monkeypatch.setattr(m.capture, name, denied)


def refused(code, callback):
    with pytest.raises(m.Refused) as caught:
        callback()
    assert m.finite(caught.value) == code


def make_fixture(*, rows=None, header=None, member_name='tickers.csv',
        compression=zipfile.ZIP_DEFLATED, payload=None, extra_member=False):
    header = header or ['table', 'ticker', 'permaticker', 'isdelisted', 'category', 'exchange',
        'sector', 'industry', 'figi', 'firstpricedate', 'lastpricedate'] + ['field' + str(i) for i in range(17)]
    if rows is None:
        rows = []
        for index, state in enumerate(('N', 'Y', '')):
            row = {name: 'private-' + str(index) for name in header}
            row.update(table='SF1', ticker='SYN' + str(index), permaticker=str(index + 1), isdelisted=state)
            rows.append(row)
    if payload is None:
        text = io.StringIO(newline='')
        writer = csv.writer(text, lineterminator='\n')
        writer.writerow(header)
        writer.writerows([[row.get(name, '') for name in header] for row in rows])
        payload = text.getvalue().encode('utf-8')
    raw_header = payload.partition(b'\n')[0] + b'\n'
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=compression) as zipped:
        zipped.writestr(member_name, payload)
        if extra_member:
            zipped.writestr('extra.csv', b'not requested\n')
    raw = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw), 'r') as zipped:
        info = zipped.infolist()[0]
    counts = {'active': 0, 'delisted': 0, 'unknown': 0}
    for row in rows:
        state = row.get('isdelisted', '').strip().casefold()
        name = 'active' if state in ('n', 'no', '0', 'false') else 'delisted' if state in ('y', 'yes', '1', 'true') else 'unknown'
        counts[name] += 1
    member = m.capture.SharadarMemberBinding(member_name, info.compress_size, len(payload), info.CRC,
        m.sha(payload), len(rows), tuple(header))
    archive = m.capture.SharadarArchiveBinding(m.capture.SharadarDataset.TICKERS,
        m.capture.ENDPOINT_PATHS[m.capture.SharadarDataset.TICKERS],
        m.sha(m.capture._request_query_bytes(m.capture.SharadarDataset.TICKERS)),
        m.ARCHIVE_NAME, len(raw), m.sha(raw), counts['active'], counts['delisted'], counts['unknown'],
        (), True, (member,))
    spec = m._ArchiveSpec(len(raw), m.sha(raw), len(payload), m.sha(payload),
        len(raw_header), m.sha(raw_header), len(rows))
    return NS(header=header, rows=rows, payload=payload, raw=raw, member=member,
        archive=archive, spec=spec, counts=counts)


@pytest.fixture
def fixture():
    return make_fixture()


def internal_decode(fixture):
    deadline = time.monotonic() + 10
    payload = m._read_authenticated_member(fixture.raw, fixture.archive, fixture.spec, deadline)
    return m._parse_authenticated_payload(payload, fixture.archive, fixture.spec, deadline)


def test_every_row_preserved_in_original_order_with_exact_frozen_source_hash(fixture):
    catalog, counts = internal_decode(fixture)
    assert type(catalog) is m.PrivateOriginalTickerCatalog
    assert catalog.columns == tuple(fixture.header) and catalog.row_count == 3
    assert catalog.rows == tuple(tuple(row[name] for name in fixture.header) for row in fixture.rows)
    assert counts == fixture.counts == {'active': 1, 'delisted': 1, 'unknown': 1}
    assert catalog.mapping_rows() == tuple(fixture.rows)
    for row in fixture.rows:
        digest = m.evidence.source_row_digest(row)
        assert catalog.source_row(digest) == tuple(row[name] for name in fixture.header)
        assert digest == m.sha(m.evidence.composer.canonical_json_bytes(row))
    assert len(catalog._index) == 3


def test_private_result_is_immutable_redacted_and_nonserializable(fixture):
    catalog, _ = internal_decode(fixture)
    with pytest.raises(TypeError): catalog._rows = ()
    with pytest.raises(TypeError): catalog.rows[0][0] = 'changed'
    with pytest.raises(TypeError): catalog._index['f' * 64] = ()
    mappings = catalog.mapping_rows()
    mappings[0]['ticker'] = 'changed'
    assert catalog.mapping_rows()[0]['ticker'] == fixture.rows[0]['ticker']
    assert 'private-' not in repr(catalog) and 'SYN' not in repr(catalog)
    with pytest.raises(TypeError): pickle.dumps(catalog)
    with pytest.raises(TypeError): json.dumps(catalog)
    refused('private_catalog', lambda: catalog.source_row('f' * 64))


def test_unicode_and_embedded_CSV_newline_are_not_normalized_or_filtered(fixture):
    rows = copy.deepcopy(fixture.rows)
    rows[0]['sector'] = 'private é\nquoted, field'
    altered = make_fixture(rows=rows)
    catalog, counts = internal_decode(altered)
    assert catalog.mapping_rows() == tuple(rows) and counts == altered.counts
    assert catalog.source_row(m.evidence.source_row_digest(rows[0])) == tuple(rows[0][name] for name in altered.header)


@pytest.mark.parametrize('fault', ['archive_size', 'archive_sha', 'member_size', 'member_sha', 'row_count',
    'member_name', 'compressed_size', 'crc', 'archive_name', 'dataset', 'members'])
def test_archive_member_bindings_are_all_enforced(fixture, fault):
    spec, archive = fixture.spec, fixture.archive
    if fault == 'archive_size': spec = replace(spec, archive_bytes=spec.archive_bytes + 1)
    elif fault == 'archive_sha': spec = replace(spec, archive_sha256='f' * 64)
    elif fault == 'member_size': spec = replace(spec, member_bytes=spec.member_bytes + 1)
    elif fault == 'member_sha': spec = replace(spec, member_sha256='f' * 64)
    elif fault == 'row_count': spec = replace(spec, row_count=spec.row_count + 1)
    elif fault == 'archive_name': archive = replace(archive, archive_file='other.zip')
    elif fault == 'dataset': archive = replace(archive, dataset=m.capture.SharadarDataset.ACTIONS)
    elif fault == 'members': archive = replace(archive, members=(*archive.members, *archive.members))
    else:
        changes = {'member_name': {'name': 'wrong.csv'}, 'compressed_size': {'compressed_byte_count': 1},
            'crc': {'crc32': fixture.member.crc32 ^ 1}}[fault]
        archive = replace(archive, members=(replace(fixture.member, **changes),))
    with pytest.raises(m.Refused):
        m._read_authenticated_member(fixture.raw, archive, spec, time.monotonic() + 10)


@pytest.mark.parametrize('name', ['../tickers.csv', '/tickers.csv', 'a/tickers.csv', 'tickers.csv/', 'tickers.txt'])
def test_unchanged_safe_zip_policy_rejects_unsafe_names(name):
    fixture = make_fixture(member_name=name)
    with pytest.raises(m.Refused): internal_decode(fixture)


def test_extra_member_or_unreviewed_compression_is_not_skipped():
    with pytest.raises(m.Refused): internal_decode(make_fixture(extra_member=True))
    with pytest.raises(m.Refused): internal_decode(make_fixture(compression=zipfile.ZIP_BZIP2))


def test_member_content_authenticated_before_any_CSV_or_row_interpretation(fixture, monkeypatch):
    entered = []
    monkeypatch.setattr(m.csv, 'reader', lambda *a, **k: entered.append('CSV'))
    monkeypatch.setattr(m.evidence, 'source_row_digest', lambda *a: entered.append('ROW'))
    wrong = replace(fixture.spec, member_sha256='f' * 64)
    refused('member_binding', lambda: m._read_authenticated_member(fixture.raw, fixture.archive,
        wrong, time.monotonic() + 10))
    assert entered == []
    refused('member_content', lambda: m._parse_authenticated_payload(fixture.payload + b' ', fixture.archive,
        fixture.spec, time.monotonic() + 10))
    assert entered == []


def test_final_decompression_digest_is_not_replaced_by_only_declared_digest(fixture):
    wrong = replace(fixture.spec, member_sha256='f' * 64)
    declared = replace(fixture.archive, members=(replace(fixture.member, content_sha256='f' * 64),))
    refused('member_content', lambda: m._read_authenticated_member(fixture.raw, declared,
        wrong, time.monotonic() + 10))


@pytest.mark.parametrize('fault', ['header_bytes', 'header_hash', 'columns', 'short_row', 'long_row',
    'blank_row', 'too_many', 'too_few', 'invalid_utf8', 'quoted_truncation', 'empty_identity', 'bad_delisted', 'census'])
def test_exact_header_CSV_shape_census_and_no_row_dropping(fixture, fault):
    value = fixture
    if fault == 'header_bytes': value = copy.copy(fixture); value.spec = replace(value.spec, header_bytes=value.spec.header_bytes + 1)
    elif fault == 'header_hash': value = copy.copy(fixture); value.spec = replace(value.spec, header_sha256='f' * 64)
    elif fault == 'columns': value = copy.copy(fixture); value.archive = replace(value.archive,
        members=(replace(value.member, columns=tuple(reversed(value.member.columns))),))
    elif fault == 'short_row': value = make_fixture(payload=fixture.payload.replace(b',private-0\n', b'\n', 1))
    elif fault == 'long_row': value = make_fixture(payload=fixture.payload.replace(b'private-0\n', b'private-0,extra\n', 1))
    elif fault == 'blank_row': value = make_fixture(payload=fixture.payload + b'\n')
    elif fault == 'too_many': value = copy.copy(fixture); value.spec = replace(value.spec, row_count=2)
    elif fault == 'too_few': value = copy.copy(fixture); value.spec = replace(value.spec, row_count=4)
    elif fault == 'invalid_utf8': value = make_fixture(payload=fixture.payload + b'\xff')
    elif fault == 'quoted_truncation': value = make_fixture(payload=fixture.payload + b'"unfinished')
    elif fault == 'empty_identity':
        rows = copy.deepcopy(fixture.rows); rows[1]['ticker'] = ''; value = make_fixture(rows=rows)
    elif fault == 'bad_delisted':
        rows = copy.deepcopy(fixture.rows); rows[1]['isdelisted'] = 'maybe'; value = make_fixture(rows=rows)
    else: value = copy.copy(fixture); value.archive = replace(value.archive, active_ticker_row_count=0)
    with pytest.raises(m.Refused):
        m._parse_authenticated_payload(value.payload, value.archive, value.spec, time.monotonic() + 10)


def test_duplicate_original_rows_preserved_without_global_admission_or_overwrite(fixture):
    duplicate = make_fixture(rows=[*fixture.rows, copy.deepcopy(fixture.rows[0])])
    catalog, counts = internal_decode(duplicate)
    assert catalog.mapping_rows() == tuple(duplicate.rows)
    assert catalog.rows[0] == catalog.rows[-1] and catalog.row_count == 4
    assert len(catalog._index) == 3 and len(catalog._digests) == 4
    digest = m.evidence.source_row_digest(fixture.rows[0])
    assert catalog._index[digest] == (catalog.rows[0], catalog.rows[-1])
    assert counts == {'active': 2, 'delisted': 1, 'unknown': 1}
    refused('row_ambiguous', lambda: catalog.source_row(digest))
    assert catalog.source_row(m.evidence.source_row_digest(fixture.rows[1])) == catalog.rows[1]


def test_frozen_hash_field_and_row_limits_are_preserved(fixture):
    rows = copy.deepcopy(fixture.rows)
    rows[0]['sector'] = 'x' * (m.evidence.MAX_FIELD_CHARS + 1)
    value = make_fixture(rows=rows, compression=zipfile.ZIP_STORED)
    refused('row', lambda: internal_decode(value))
    rows = copy.deepcopy(fixture.rows)
    for name in fixture.header[11:]: rows[0][name] = 'x' * 8000
    value = make_fixture(rows=rows, compression=zipfile.ZIP_STORED)
    refused('row', lambda: internal_decode(value))


def test_CSV_process_limit_is_never_modified(fixture, monkeypatch):
    calls = []
    def getter(*args):
        calls.append(args)
        assert args == ()
        return 131072
    monkeypatch.setattr(m.csv, 'field_size_limit', getter)
    assert internal_decode(fixture)[0].row_count == 3 and calls == [()]
    monkeypatch.setattr(m.csv, 'field_size_limit', lambda: 100)
    refused('csv', lambda: internal_decode(fixture))


@pytest.mark.parametrize('deadline', [None, True, float('nan'), float('inf'), -1])
def test_deadline_refuses_before_any_parsing(fixture, monkeypatch, deadline):
    monkeypatch.setattr(m.capture, '_parse_manifest', lambda *a: (_ for _ in ()).throw(AssertionError('not reached')))
    refused('deadline', lambda: m.decode_original_catalog(b'{}', b'bad', b'bad', deadline=deadline))
    refused('deadline', lambda: m._parse_authenticated_payload(fixture.payload, fixture.archive, fixture.spec, deadline))


@pytest.mark.parametrize('observations', [(0, 0, 0, 11), (0, 0, 0, 0, 11)])
def test_deadline_checked_for_every_row_and_after_full_parse(fixture, monkeypatch, observations):
    ticks = iter(observations)
    monkeypatch.setattr(m.time, 'monotonic', lambda: next(ticks))
    refused('deadline', lambda: m._parse_authenticated_payload(fixture.payload, fixture.archive, fixture.spec, 10))


def synthetic_manifest(fixture, *, transport=None):
    archives = [fixture.archive]
    for role in (m.capture.SharadarDataset.ACTIONS, m.capture.SharadarDataset.FUNDAMENTALS):
        fields = tuple(sorted(m.capture.REQUIRED_FIELDS[role]))
        member = m.capture.SharadarMemberBinding(role.value + '.csv', 1, 2, 0, 'b' * 64, 1, fields)
        archives.append(m.capture.SharadarArchiveBinding(role, m.capture.ENDPOINT_PATHS[role],
            m.sha(m.capture._request_query_bytes(role)), m.capture.ARCHIVE_FILENAMES[role],
            3, 'a' * 64, 0, 0, 0, (('ART', 1),) if role is m.capture.SharadarDataset.FUNDAMENTALS else (),
            True, (member,)))
    value = m.capture._manifest(m.ARTIFACT_NAME, '2026-09-14T00:33:29.843989Z',
        '2026-09-14T00:33:30.000000Z', transport or m.capture.PRODUCTION_TRANSPORT, tuple(archives))
    return value


def test_actual_unchanged_manifest_parser_used_on_synthetic_metadata_without_other_archives(fixture):
    value = synthetic_manifest(fixture)
    assert m._declared_archive(m.canonical(value)) == fixture.archive
    value = synthetic_manifest(fixture, transport=m.capture.TEST_TRANSPORT)
    refused('manifest', lambda: m._declared_archive(m.canonical(value)))
    value = synthetic_manifest(fixture)
    value['extra'] = 'unaccepted'
    refused('manifest', lambda: m._declared_archive(m.canonical(value)))


def test_production_wrapper_has_no_injected_pins_parser_or_census_and_refuses_synthetics(fixture, monkeypatch):
    def denied(*args, **kwargs): raise AssertionError('fixed external pins before parser')
    monkeypatch.setattr(m.capture, '_parse_manifest', denied)
    monkeypatch.setattr(m, '_read_authenticated_member', denied)
    refused('archive_binding', lambda: m.decode_original_catalog(b'{}\n',
        (m.MANIFEST_SHA256 + '\n').encode(), fixture.raw, deadline=time.monotonic() + 10))
    signature = inspect.signature(m.decode_original_catalog)
    assert tuple(signature.parameters) == ('manifest_raw', 'marker_raw', 'archive_raw', 'deadline')
    assert signature.parameters['deadline'].kind is inspect.Parameter.KEYWORD_ONLY
    assert m.EXPECTED_ROWS == 74150 and m.FIELD_COUNT == 28
    assert m.ARCHIVE_BYTES == 4937076 and m.MEMBER_BYTES == 24939614


def receipt():
    return {'schema': m.SCHEMA, 'status': 'fixed_original_full_TICKERS_bytes_decoded',
        'profile_sha256': m.sha(m.canonical(m.profile_record())), 'manifest_sha256': m.MANIFEST_SHA256,
        'archive_sha256': m.ARCHIVE_SHA256, 'archive_byte_count': m.ARCHIVE_BYTES,
        'member_sha256': m.MEMBER_SHA256, 'member_byte_count': m.MEMBER_BYTES,
        'header_sha256': m.HEADER_SHA256, 'header_byte_count': m.HEADER_BYTES,
        'csv_row_count': 74150, 'field_count': 28, 'unique_source_row_count': 74150,
        'duplicate_source_row_count': 0,
        'ordered_source_row_digests_sha256': 'a' * 64,
        'delisting_flag_counts': {'active': 40000, 'delisted': 30000, 'unknown': 4150},
        'current_vintage_only': True, 'result_cell': 0, **m.FALSE_FLAGS}


@pytest.mark.parametrize('fault', ['extra', 'row_count', 'bool_count', 'field_count', 'unique', 'manifest',
    'archive', 'profile', 'digest', 'flag', 'flag_type', 'counts', 'count_type', 'active_zero', 'extra_count',
    'duplicate_negative', 'duplicate_bool', 'unique_bool', 'unique_zero', 'unique_excess'])
def test_public_receipt_is_closed_metadata_only_not_a_catalog_bypass(fault):
    value = receipt()
    if fault == 'extra': value['rows'] = [['private']]
    elif fault == 'row_count': value['csv_row_count'] -= 1
    elif fault == 'bool_count': value['archive_byte_count'] = True
    elif fault == 'field_count': value['field_count'] = 27
    elif fault == 'unique': value['unique_source_row_count'] -= 1
    elif fault == 'duplicate_negative': value['duplicate_source_row_count'] = -1
    elif fault == 'duplicate_bool': value['duplicate_source_row_count'] = False
    elif fault == 'unique_bool': value['unique_source_row_count'] = True
    elif fault == 'unique_zero': value['unique_source_row_count'] = 0
    elif fault == 'unique_excess': value['unique_source_row_count'] = 74151
    elif fault == 'manifest': value['manifest_sha256'] = 'f' * 64
    elif fault == 'archive': value['archive_sha256'] = 'f' * 64
    elif fault == 'profile': value['profile_sha256'] = 'f' * 64
    elif fault == 'digest': value['ordered_source_row_digests_sha256'] = 'invalid'
    elif fault == 'flag': value['raw_rows_disclosed'] = True
    elif fault == 'flag_type': value['filesystem_access_performed'] = 0
    elif fault == 'counts': value['delisting_flag_counts']['active'] += 1
    elif fault == 'count_type': value['delisting_flag_counts']['active'] = True
    elif fault == 'active_zero': value['delisting_flag_counts'] = {'active': 0, 'delisted': 70000, 'unknown': 4150}
    else: value['delisting_flag_counts']['other'] = 0
    refused('receipt', lambda: m.validate_receipt(value))


def test_receipt_deep_copy_and_profile_false_flags():
    value = receipt()
    checked = m.validate_receipt(value)
    checked['delisting_flag_counts']['active'] = 0
    assert value['delisting_flag_counts']['active'] == 40000
    assert all(m.profile_record()[flag] is False for flag in m.FALSE_FLAGS)
    assert m.profile_record()['exact_rows'] == 74150
    assert m.profile_record()['CSV_global_field_limit_modified'] is False


def test_receipt_preserves_explicit_duplicate_metadata_instead_of_fabricating_unique_catalog():
    value = receipt()
    value.update(unique_source_row_count=74149, duplicate_source_row_count=1)
    assert m.validate_receipt(value) == value
    assert 'retain_every_row' in m.profile_record()['duplicate_source_row_digests']


def test_pure_module_has_no_filesystem_or_old_operation_calls():
    tree = ast.parse(inspect.getsource(m))
    forbidden = {'original_row', 'consume', 'run', 'observe', 'main', 'preflight', 'read_bytes',
        'read_text', 'write_bytes', 'write_text', 'load_key', 'capture_sharadar_history',
        'load_sharadar_capture_artifact', '_visit_authenticated_sharadar_capture_rows_for_bridge'}
    calls = {node.func.attr for node in ast.walk(tree) if type(node) is ast.Call and type(node.func) is ast.Attribute}
    assert not calls & forbidden
    assert not any(type(node) is ast.Call and type(node.func) is ast.Name and node.func.id == 'open'
        for node in ast.walk(tree))
    assert m.finite(ValueError('private untrusted exception')) == 'unknown'
    assert m.finite(m.Refused('private untrusted exception')) == 'unknown'
    assert m.finite(m.Refused('row_ambiguous')) == 'row_ambiguous'
