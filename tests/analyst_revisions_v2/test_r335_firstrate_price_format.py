"""Synthetic FirstRate format; no USB, DATA, claims, provider or QC calls."""
import copy
from datetime import date
from decimal import Decimal
import hashlib
import inspect
import json

import pytest

from research.analyst_revisions_v2_qc import newrule_firstrate_price_format as m
from research.analyst_revisions_v2_qc import accepted_risk_october_order_package as calendar

REAL_DEMAND = m.SELECTED_DEMAND


def refused(code, operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    assert m.finite(caught.value) == code


def binding(index):
    figi = 'BBG' + str(index + 1).zfill(9)
    return m.figi.build_preliminary_qc_figi_binding(
        security_id='sharadar-composite-figi-' + figi,
        issuer_id='synthetic-issuer-' + str(index), composite_figi=figi,
        listing_id='synthetic-listing-' + str(index), diagnostic_current_ticker='T' + str(index),
        diagnostic_exchange_mic='XNYS', candidate_first_session='2013-01-02',
        candidate_last_session='2026-10-13', source_snapshot_available_at='2026-10-01T00:00:00.000000Z',
        source_row_sha256=m.digest({'synthetic_source': index}),
        identity_evidence_sha256=m.digest({'synthetic_identity': index}),
        security_master_admission_sha256=m.ADMISSION_SHA256,
        admitted_mapping_inventory_sha256='a' * 64, admitted_mapping_count=1)


@pytest.fixture
def case(monkeypatch):
    # Production accepts only6151/literalpins. This local fixture retains the
    # real binding validator, canonical+LF stream, full real calendar and all
    # five public dense/reference geometries, never a production input read.
    rows = tuple(sorted((binding(index) for index in range(7)), key=lambda row: row['security_id']))
    stream = hashlib.sha256()
    for row in rows:
        stream.update(m.canonical(row)); stream.update(b'\n')
    selected = tuple(sorted(rows[:5], key=m.digest))
    whole_pins = tuple(m.digest(row) for row in selected)
    monkeypatch.setattr(m, 'STOCK_COUNT', 7)
    monkeypatch.setattr(m, 'BINDING_STREAM_SHA256', stream.hexdigest())
    monkeypatch.setattr(m, 'SELECTED_WHOLE_BINDING_SHA256S', whole_pins)
    monkeypatch.setattr(m, 'SELECTED_DEMAND', tuple((whole, *source[1:])
        for whole, source in zip(whole_pins, REAL_DEMAND, strict=True)))
    axis = calendar._sessions(); prices = m.validate_axis(axis)
    positions = {session: index for index, session in enumerate(axis)}
    seen, decisions = set(), []
    for session in axis:
        if '2021-11-01' <= session <= '2026-10-12':
            week = date.fromisoformat(session).isocalendar()[:2]
            if week not in seen:
                seen.add(week); decisions.append(session)
    demand_rows, assignments, grid, identities = [], [], [], {}
    for ordinal, (original, expected) in enumerate(zip(selected, m.SELECTED_DEMAND, strict=True)):
        whole, first, count, dense_sha, refs_count, decisions_sha = expected
        required = [session for session in prices if first <= session]
        eligible = [session for session in decisions if axis[positions[session] - 1] >= first]
        references = [axis[positions[session] - 1] for session in eligible]
        assert len(required) == count and m.digest(required) == dense_sha
        assert len(eligible) == refs_count and m.digest(eligible) == decisions_sha
        demand_rows.append({'whole_binding_sha256': whole, 'first_required': first,
            'last_required': m.LAST, 'required_sessions': required,
            'required_sessions_sha256': dense_sha, 'potential_reference_sessions': references,
            'potential_reference_sessions_sha256': m.digest(references)})
        native = {'sid': 'SYNTHETIC-SID-' + str(ordinal), 'kind': 'equity',
            'market': 'usa', 'sid_date': '2013-01-02'}
        identities[whole] = native
        ticker = original['diagnostic_current_ticker']
        assignments.append({'ordinal': ordinal, 'security_id': original['security_id'],
            'whole_binding_sha256': whole, 'semantic_binding_sha256': original['row_sha256'],
            'original_identity_evidence_sha256': original['identity_evidence_sha256'],
            'native_identity': dict(native), 'source': {
                'archive_relative_path': m.STOCK_DIRECTORY + 'Tickers_T_Day_Unadjusted_Full_Dataset.zip',
                'container_pin': {'byte_count': 1000, 'sha256': 'b' * 64},
                'member_pin': {'byte_count': 500, 'sha256': m.digest({'synthetic_member': ordinal})},
                'member_name': ticker + '_full_1day_UNADJUSTED.txt', 'source_ticker': ticker,
                'ticker_era': {'name': 'Synthetic issuer ' + str(ordinal),
                    'first_date': m.FIRST, 'last_date': m.LAST,
                    'evidence_pin': {'byte_count': 90, 'sha256': m.digest({'synthetic_evidence': ordinal})}}}})
        grid.append([None if session < first else '123.45' for session in prices])
    demand = {'schema': m.SCHEMA + '-demand', 'source_policy_epoch_id': m.SOURCE_POLICY_EPOCH_ID,
        'binding_stream_sha256': m.BINDING_STREAM_SHA256, 'full_axis_sha256': m.FULL_AXIS_SHA256,
        'price_axis_sha256': m.PRICE_AXIS_SHA256, 'assignments': demand_rows, **m._flags()}
    demand_pin = m.pin(m.canonical(demand))
    evidence_pin = {'byte_count': 900, 'sha256': 'e' * 64}
    book = {'schema': m.SCHEMA, 'source_policy_epoch_id': m.SOURCE_POLICY_EPOCH_ID,
        'runtime_project_id': 123, 'format_profile_sha256': m.digest(m.profile_record()),
        'binding_stream_sha256': m.BINDING_STREAM_SHA256, 'full_axis_sha256': m.FULL_AXIS_SHA256,
        'price_axis_sha256': m.PRICE_AXIS_SHA256, 'price_sessions': list(prices), 'currency': 'USD',
        'price_convention_id': m.PRICE_CONVENTION_ID, 'demand_pin': demand_pin, 'demand': demand,
        'private_evidence_pin': copy.deepcopy(evidence_pin), 'assignments': assignments, 'prices': grid, **m._flags()}
    inputs = {'stock_bindings': rows, 'full_axis': axis, 'native_identities': identities,
        'expected_demand_pin': demand_pin, 'expected_evidence_pin': evidence_pin,
        'expected_runtime_project_id': 123}
    return book, inputs


def manifest(book, raw):
    return {'schema': m.SCHEMA + '-manifest', 'source_policy_epoch_id': m.SOURCE_POLICY_EPOCH_ID,
        'runtime_project_id': book['runtime_project_id'], 'format_profile_sha256': m.digest(m.profile_record()),
        'binding_stream_sha256': m.BINDING_STREAM_SHA256, 'full_axis_sha256': m.FULL_AXIS_SHA256,
        'price_axis_sha256': m.PRICE_AXIS_SHA256,
        'selected_whole_binding_sha256s': list(m.SELECTED_WHOLE_BINDING_SHA256S),
        'book_pin': m.pin(raw), 'demand_pin': book['demand_pin'],
        'private_evidence_pin': book['private_evidence_pin'], 'currency': 'USD',
        'price_convention_id': m.PRICE_CONVENTION_ID, **m._flags()}


def context(book_manifest, manifest_raw):
    return {'schema': m.SCHEMA + '-QC-context', 'source_policy_epoch_id': m.SOURCE_POLICY_EPOCH_ID,
        'runtime_project_id': book_manifest['runtime_project_id'], 'format_profile_sha256': m.digest(m.profile_record()),
        'object_key_prefix': str(book_manifest['runtime_project_id']) + '/arv2/r335-firstrate-five/'
            + m.sha(manifest_raw) + '/', 'manifest_pin': m.pin(manifest_raw),
        'book_pin': book_manifest['book_pin'], 'demand_pin': book_manifest['demand_pin'],
        'private_evidence_pin': book_manifest['private_evidence_pin'], **m._flags()}


def manifest_inputs(book, raw):
    return {'book_pin': m.pin(raw), 'demand_pin': book['demand_pin'],
        'evidence_pin': book['private_evidence_pin'], 'expected_runtime_project_id': 123}


def test_production_policy_has_exact_public_five_and_W5_axis():
    assert m.STOCK_COUNT == 6151 and m.SELECTED_COUNT == 5
    assert m.FULL_AXIS_COUNT == 3466 and m.PRICE_SESSION_COUNT == 1243
    assert m.MAX_BOOK_BYTES == 4 * 1024 * 1024 and m.MAX_CONTAINER_BYTES == 64 * 1024 * 1024
    from research.analyst_revisions_v2_qc import newrule_available_history_native_coverage as old
    assert [(row[0], row[1], row[4]) for row in m.SELECTED_DEMAND] == list(old.EXPECTED_DEMAND)
    assert [(row[2], row[3], row[5]) for row in m.SELECTED_DEMAND] == list(old.EXPECTED_GEOMETRY)
    assert len(m.validate_axis(calendar._sessions())) == 1243
    profile = m.profile_record()
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
    assert {'permanent_security_master_proven', 'point_in_time_proven', 'formal_forward_ready',
        'paper_or_live_ready', 'price_input_admitted', 'backtest_authority_granted'} <= set(m.FALSE_FLAGS)
    for function in (m.validate_book, m.validate_book_bytes, m.validate_manifest, m.validate_context, m.object_keys):
        assert inspect.signature(function).parameters['expected_runtime_project_id'].default is inspect.Parameter.empty


def test_book_manifest_context_chain_and_immutable_bytes(case):
    book, inputs = case
    raw = m.validate_book(book, **inputs)
    assert type(raw) is bytes and len(raw) <= m.MAX_BOOK_BYTES
    assert m.validate_book_bytes(raw, expected_pin=m.pin(raw), **inputs) == raw
    packet = manifest(book, raw)
    packet_raw = m.validate_manifest(packet, **manifest_inputs(book, raw))
    ctx = context(packet, packet_raw)
    assert type(m.validate_context(ctx, expected_runtime_project_id=123)) is bytes
    keys = m.object_keys(ctx, expected_runtime_project_id=123)
    assert keys == (ctx['object_key_prefix'] + 'manifest.json',
        ctx['object_key_prefix'] + 'book-' + m.sha(raw) + '.json')
    book['prices'][0][-1] = '999'
    inputs['native_identities'].clear()
    assert m.loads(raw, m.MAX_BOOK_BYTES)['prices'][0][-1] == '123.45'


def test_external_book_pin_precedes_decode(case, monkeypatch):
    _, inputs = case
    def forbidden(*args, **kwargs):
        raise AssertionError('decode happened before external pin')
    monkeypatch.setattr(m, 'loads', forbidden)
    refused('pin', lambda: m.validate_book_bytes(b'not-json',
        expected_pin={'byte_count': 8, 'sha256': 'a' * 64}, **inputs))


@pytest.mark.parametrize('change', ('count', 'order', 'semantic', 'stream', 'duplicate', 'non_tuple'))
def test_full_original_bindings_are_not_replaceable(case, change, monkeypatch):
    book, inputs = case
    rows = copy.deepcopy(inputs['stock_bindings'])
    if change == 'count': rows = rows[:-1]
    elif change == 'order': rows = tuple(reversed(rows))
    elif change == 'semantic': rows[0]['row_sha256'] = 'a' * 64
    elif change == 'stream': monkeypatch.setattr(m, 'BINDING_STREAM_SHA256', 'a' * 64)
    elif change == 'duplicate': rows = (rows[0], *rows[:-1])
    else: rows = list(rows)
    inputs['stock_bindings'] = rows
    refused('bindings', lambda: m.validate_book(book, **inputs))


@pytest.mark.parametrize('change', ('count', 'reversed', 'duplicate', 'date', 'list', 'hash'))
def test_full_calendar_pin_precedes_price_axis_use(case, change, monkeypatch):
    book, inputs = case
    axis = inputs['full_axis']
    if change == 'count': axis = axis[:-1]
    elif change == 'reversed': axis = tuple(reversed(axis))
    elif change == 'duplicate': axis = (axis[0], *axis[:-1])
    elif change == 'date': axis = ('not-date', *axis[1:])
    elif change == 'list': axis = list(axis)
    else: monkeypatch.setattr(m, 'FULL_AXIS_SHA256', 'a' * 64)
    inputs['full_axis'] = axis
    refused('axis', lambda: m.validate_book(book, **inputs))


@pytest.mark.parametrize('value', (None, True, 0, -1, 2147483648, 123.0, '123', 456))
@pytest.mark.parametrize('role', ('book', 'manifest', 'context', 'keys'))
def test_each_stage_requires_the_same_external_frozen_project(case, value, role):
    book, inputs = case
    raw = m.validate_book(book, **inputs); packet = manifest(book, raw)
    packet_raw = m.validate_manifest(packet, **manifest_inputs(book, raw))
    ctx = context(packet, packet_raw)
    if role == 'book':
        inputs['expected_runtime_project_id'] = value
        operation = lambda: m.validate_book(book, **inputs)
    elif role == 'manifest':
        args = manifest_inputs(book, raw); args['expected_runtime_project_id'] = value
        operation = lambda: m.validate_manifest(packet, **args)
    elif role == 'context':
        operation = lambda: m.validate_context(ctx, expected_runtime_project_id=value)
    else:
        operation = lambda: m.object_keys(ctx, expected_runtime_project_id=value)
    refused('project', operation)


@pytest.mark.parametrize('role', ('book', 'manifest', 'context'))
def test_cross_project_records_cannot_be_chained_with_matching_pins(case, role):
    book, inputs = case
    raw = m.validate_book(book, **inputs); packet = manifest(book, raw)
    packet_raw = m.validate_manifest(packet, **manifest_inputs(book, raw))
    ctx = context(packet, packet_raw)
    if role == 'book':
        book['runtime_project_id'] = 456
        operation = lambda: m.validate_book(book, **inputs)
    elif role == 'manifest':
        packet['runtime_project_id'] = 456
        operation = lambda: m.validate_manifest(packet, **manifest_inputs(book, raw))
    else:
        ctx['runtime_project_id'] = 456
        ctx['object_key_prefix'] = ctx['object_key_prefix'].replace('123/', '456/', 1)
        operation = lambda: m.validate_context(ctx, expected_runtime_project_id=123)
    refused('project', operation)


@pytest.mark.parametrize('change', ('missing', 'extra', 'flag', 'epoch', 'profile',
    'currency', 'convention', 'axis_hash', 'axis_order'))
def test_closed_book_rejects_forged_source_fields(case, change):
    book, inputs = case
    if change == 'missing': book.pop('price_sessions')
    elif change == 'extra': book['accepted'] = True
    elif change == 'flag': book['price_input_admitted'] = True
    elif change == 'epoch': book['source_policy_epoch_id'] = 'older-source-epoch'
    elif change == 'profile': book['format_profile_sha256'] = 'a' * 64
    elif change == 'currency': book['currency'] = 'CAD'
    elif change == 'convention': book['price_convention_id'] = 'adjusted'
    elif change == 'axis_hash': book['price_axis_sha256'] = 'a' * 64
    else: book['price_sessions'].reverse()
    refused('epoch' if change == 'epoch' else 'shape', lambda: m.validate_book(book, **inputs))


@pytest.mark.parametrize('change', ('whole', 'semantic', 'identity_evidence', 'security',
    'order', 'ordinal_bool', 'missing', 'extra', 'source_reused'))
def test_original_five_assignment_ownership_cannot_be_relabelled(case, change):
    book, inputs = case; row = book['assignments'][0]
    if change == 'whole': row['whole_binding_sha256'] = 'a' * 64
    elif change == 'semantic': row['semantic_binding_sha256'] = 'a' * 64
    elif change == 'identity_evidence': row['original_identity_evidence_sha256'] = 'a' * 64
    elif change == 'security': row['security_id'] = 'synthetic-other'
    elif change == 'order': book['assignments'].reverse()
    elif change == 'ordinal_bool': row['ordinal'] = False
    elif change == 'missing': row.pop('source')
    elif change == 'extra': row['fallback'] = True
    else: row['source'] = copy.deepcopy(book['assignments'][1]['source'])
    refused('provenance' if change == 'source_reused' else 'assignment', lambda: m.validate_book(book, **inputs))


@pytest.mark.parametrize('change', ('SID', 'kind', 'market', 'date', 'missing', 'extra', 'duplicate_external'))
def test_fresh_native_bridge_facts_are_exact(case, change):
    book, inputs = case; row = book['assignments'][0]['native_identity']
    if change == 'SID': row['sid'] = 'SYNTHETIC-OTHER-SID'
    elif change == 'kind': row['kind'] = 'option'
    elif change == 'market': row['market'] = 'canada'
    elif change == 'date': row['sid_date'] = '2013-02-30'
    elif change == 'missing': row.pop('sid_date')
    elif change == 'extra': row['display'] = 'T0'
    else:
        keys = list(inputs['native_identities'])
        inputs['native_identities'][keys[1]]['sid'] = inputs['native_identities'][keys[0]]['sid']
    refused('native_identity', lambda: m.validate_book(book, **inputs))


@pytest.mark.parametrize('change', ('ticker', 'member', 'archive', 'container', 'member_pin',
    'era_first', 'era_last', 'era_evidence', 'name', 'extra'))
def test_source_container_member_and_ticker_era_are_bound(case, change):
    book, inputs = case; source = book['assignments'][0]['source']
    if change == 'ticker': source['source_ticker'] = 'UNRELATED'
    elif change == 'member': source['member_name'] = '../../other.txt'
    elif change == 'archive': source['archive_relative_path'] = '/tmp/source.zip'
    elif change == 'container': source['container_pin']['byte_count'] = True
    elif change == 'member_pin': source['member_pin']['sha256'] = 'not-pin'
    elif change == 'era_first': source['ticker_era']['first_date'] = '2026-10-01'
    elif change == 'era_last': source['ticker_era']['last_date'] = '2025-01-01'
    elif change == 'era_evidence': source['ticker_era']['evidence_pin']['sha256'] = 'not-pin'
    elif change == 'name': source['ticker_era']['name'] = 'bad\nname'
    else: source['source_authentication_passed'] = True
    refused('pin' if change in ('container', 'member_pin', 'era_evidence') else 'provenance',
        lambda: m.validate_book(book, **inputs))


@pytest.mark.parametrize('change', ('first', 'last', 'count', 'order', 'hash', 'reference_date',
    'reference_hash', 'tuple', 'extra', 'external_pin'))
def test_demand_cannot_be_shortened_or_replaced(case, change):
    book, inputs = case; item = book['demand']['assignments'][0]
    if change == 'first': item['first_required'] = '2026-10-01'
    elif change == 'last': item['last_required'] = '2026-10-01'
    elif change == 'count': item['required_sessions'].pop()
    elif change == 'order': item['required_sessions'].reverse()
    elif change == 'hash': item['required_sessions_sha256'] = 'a' * 64
    elif change == 'reference_date': item['potential_reference_sessions'][0] = item['required_sessions'][1]
    elif change == 'reference_hash': item['potential_reference_sessions_sha256'] = 'a' * 64
    elif change == 'tuple': item['required_sessions'] = tuple(item['required_sessions'])
    elif change == 'extra': item['expiry_retires_holding'] = True
    else: inputs['expected_demand_pin'] = {'byte_count': 1, 'sha256': 'a' * 64}
    refused('pin' if change == 'external_pin' else 'demand', lambda: m.validate_book(book, **inputs))


def test_external_private_identity_and_convention_evidence_pin_is_mandatory(case):
    book, inputs = case
    book['private_evidence_pin']['sha256'] = 'a' * 64
    refused('pin', lambda: m.validate_book(book, **inputs))


@pytest.mark.parametrize('text', ('0', '0.0', '-1', 'NaN', 'Infinity', '1e2', '01',
    '1.00', ' 1', '1\n', 1, 1.0, True, Decimal('1')))
def test_marks_are_positive_canonical_decimal_text_only(case, text):
    book, inputs = case; book['prices'][0][-1] = text
    refused('price', lambda: m.validate_book(book, **inputs))


def test_absence_outside_demand_is_explicit_but_no_demanded_mark_can_be_missing(case):
    book, inputs = case
    assert book['prices'][0][0] is None
    m.validate_book(book, **inputs)
    book['prices'][0][-1] = None
    refused('missing_demanded_price', lambda: m.validate_book(book, **inputs))


@pytest.mark.parametrize('change', ('row_missing', 'row_extra', 'row_tuple', 'column_missing', 'column_extra'))
def test_complete_five_by_calendar_grid_no_row_drops(case, change):
    book, inputs = case
    if change == 'row_missing': book['prices'].pop()
    elif change == 'row_extra': book['prices'].append(list(book['prices'][0]))
    elif change == 'row_tuple': book['prices'][0] = tuple(book['prices'][0])
    elif change == 'column_missing': book['prices'][0].pop()
    else: book['prices'][0].append('1')
    refused('assignment' if change in ('row_missing', 'row_extra') else 'price',
        lambda: m.validate_book(book, **inputs))


@pytest.mark.parametrize('change', ('book', 'demand', 'evidence', 'selected', 'extra', 'flag'))
def test_closed_manifest_rejects_changed_pins_or_inventory(case, change):
    book, inputs = case
    raw = m.validate_book(book, **inputs); packet = manifest(book, raw)
    expected = manifest_inputs(book, raw)
    if change == 'book': packet['book_pin'] = {'byte_count': 1, 'sha256': 'a' * 64}
    elif change == 'demand': packet['demand_pin'] = {'byte_count': 1, 'sha256': 'a' * 64}
    elif change == 'evidence': packet['private_evidence_pin'] = {'byte_count': 1, 'sha256': 'a' * 64}
    elif change == 'selected': packet['selected_whole_binding_sha256s'].reverse()
    elif change == 'extra': packet['authorized'] = True
    else: packet['price_input_admitted'] = True
    code = 'pin' if change in ('book', 'demand', 'evidence') else 'shape' if change == 'flag' else 'manifest'
    refused(code, lambda: m.validate_manifest(packet, **expected))


@pytest.mark.parametrize('raw', (b'{"x":1,"x":2}', b' {"x":1}', b'{"x":NaN}',
    b'{"x":1}\n', b'{"x":1}tail', b'\xff', b'[]\n'))
def test_duplicate_noncanonical_nonfinite_or_trailing_json_refuses(raw):
    refused('json', lambda: m.loads(raw, 1024))


def test_canonical_never_coerces_non_JSON_types_or_dictionary_keys():
    class FakeString(str):
        pass
    for value in ({1: 'a'}, {'x': (1, 2)}, {'x': FakeString('x')}, {'x': float('nan')}):
        refused('json', lambda value=value: m.canonical(value))


def test_no_filesystem_or_callbacks_after_supplied_inputs(case, monkeypatch):
    from pathlib import Path
    def forbidden(*args, **kwargs):
        raise AssertionError('pure format attempted an operational read')
    monkeypatch.setattr(Path, 'read_bytes', forbidden); monkeypatch.setattr(Path, 'open', forbidden)
    book, inputs = case
    assert type(m.validate_book(book, **inputs)) is bytes
