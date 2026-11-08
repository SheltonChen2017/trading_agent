"""Synthetic FirstRate rows only; USB, artifacts and contact are denied."""
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
import hashlib
import json
import pickle

import pytest

from scripts import arv2_r335_firstrate_prices as m


def pin(raw):
    return {'byte_count': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def source(dates=('2026-10-12', '2026-10-13'), *, suffix='', ending='\n'):
    return ''.join(day + suffix + ',12345.6789,12346,12345,12345.8,1200' + ending
        for day in dates).encode('ascii')


def parsed(raw=None, *, ticker='SYNTHETIC', **kwargs):
    raw = source() if raw is None else raw
    return m.parse_daily(raw, expected_pin=pin(raw),
        member_name=ticker + '_full_1day_UNADJUSTED.txt', expected_ticker=ticker, **kwargs)


def refused(code, action):
    with pytest.raises(m.Refused) as caught:
        action()
    assert m.finite(caught.value) == code


def test_raw_unadjusted_rows_remain_private_exact_and_decimal():
    raw = source()
    value = parsed(raw)
    assert m.private_original_bytes(value) == raw
    rows = m.private_rows(value)
    assert len(rows) == 2 and rows[0].session == '2026-10-12'
    assert rows[0].open == Decimal('12345.6789')
    assert rows[0].close == Decimal('12345.8') and rows[0].volume == 1200
    assert m.private_quarantined_bytes(value) == b''
    assert 'SYNTHETIC' not in repr(value) and '12345' not in repr(value)
    assert '12345' not in repr(rows)
    for item in (value, rows[0]):
        with pytest.raises(TypeError):
            pickle.dumps(item)
        with pytest.raises(TypeError):
            json.dumps(item)
    with pytest.raises(FrozenInstanceError):
        value._raw = b'changed'
    with pytest.raises(FrozenInstanceError):
        rows[0].close = Decimal('1')


def test_exact_hash_precedes_decode_and_expected_pin_shape_is_strict():
    raw = b'\xff\n'
    refused('pin', lambda: m.parse_daily(raw, expected_pin=pin(b'x\n'),
        member_name='SYNTHETIC_full_1day_UNADJUSTED.txt', expected_ticker='SYNTHETIC'))
    refused('encoding', lambda: parsed(raw))
    for value in ({'byte_count': True, 'sha256': 'a' * 64},
                  {'byte_count': 1, 'sha256': 'A' * 64},
                  {'byte_count': 1, 'sha256': 'a' * 64, 'extra': 'secret'},
                  {'byte_count': 0, 'sha256': 'a' * 64}):
        refused('pin', lambda value=value: m.parse_daily(b'x', expected_pin=value,
            member_name='SYNTHETIC_full_1day_UNADJUSTED.txt', expected_ticker='SYNTHETIC'))


@pytest.mark.parametrize('value', ('', 'wrong', '/REMX', '../REMX', 'reMx', 'A B', '.ABC', 'A' * 65))
def test_member_alias_does_not_accept_paths_or_unsupported_symbols(value):
    raw = source()
    refused('member', lambda: m.parse_daily(raw, expected_pin=pin(raw),
        expected_ticker=value, member_name=value + '_full_1day_UNADJUSTED.txt'))


def test_delisted_alias_is_explicit_and_never_a_security_admission():
    value = parsed(ticker='SYNTHETIC-DELISTED')
    summary = m.assess_coverage(value, ('2026-10-12', '2026-10-13'))
    assert summary['observed_date_coverage_complete'] is True
    assert all(summary[name] is False for name in m.FALSE_FLAGS)
    assert not any('ticker' in name or 'price' in name and name not in m.FALSE_FLAGS
        for name in summary)
    raw = source()
    refused('member', lambda: m.parse_daily(raw, expected_pin=pin(raw), expected_ticker='SYNTHETIC',
        member_name='SYNTHETIC-DELISTED_full_1day_UNADJUSTED.txt'))


@pytest.mark.parametrize('ending', ('\n', '\r\n'))
@pytest.mark.parametrize('suffix', ('', ' 00:00:00'))
def test_source_date_only_and_midnight_forms_are_explicit_and_consistent(ending, suffix):
    value = parsed(source(suffix=suffix, ending=ending))
    assert len(m.private_rows(value)) == 2


@pytest.mark.parametrize('raw,code', (
    (b'2026-10-12,1,2,1,2,1', 'line_ending'),
    (b'2026-10-12,1,2,1,2,1\r', 'line_ending'),
    (b'2026-10-12,1,2,1,2,1\r\n2026-10-13,1,2,1,2,1\n', 'line_ending'),
    (b'2026-10-12,1,2,1,2,1\n\n', 'row_bound'),
    (b'DateTime,Open,High,Low,Close,Volume\n', 'timestamp'),
    (b'2026-10-12,1,2,1,2\n', 'row_shape'),
    (b'2026-10-12,1,2,1,2,1,extra\n', 'row_shape'),
    (b'2026-10-12 09:30:00,1,2,1,2,1\n', 'timestamp'),
    (b'2026-10-12T00:00:00,1,2,1,2,1\n', 'timestamp'),
    (b'2026-02-30,1,2,1,2,1\n', 'session'),
    (b'2026-10-12,1,2,1,2,1\n2026-10-12,1,2,1,2,1\n', 'date_order'),
    (b'2026-10-13,1,2,1,2,1\n2026-10-12,1,2,1,2,1\n', 'date_order'),
    (b'2026-10-12,1,2,1,2,1\n2026-10-13 00:00:00,1,2,1,2,1\n', 'timestamp'),
))
def test_no_row_sorting_deduplication_header_or_malformed_row_skipping(raw, code):
    refused(code, lambda: parsed(raw))


@pytest.mark.parametrize('field,value,code', (
    (1, 'NaN', 'number'), (1, 'Infinity', 'number'), (1, '-1', 'number'),
    (1, '1e4', 'number'), (1, ' 1', 'number'), (1, '+1', 'number'),
    (1, '0', 'price'), (3, '0.0', 'price'), (4, '0', 'price'),
    (2, '0.5', 'OHLC'), (3, '1.5', 'OHLC'), (4, '3', 'OHLC'),
    (5, '-1', 'number'), (5, '0.5', 'volume'), (5, 'NaN', 'number'),
    (5, 'Infinity', 'number'), (1, '1' * 129, 'number'),
))
def test_invalid_prices_OHLC_and_volume_refuse(field, value, code):
    fields = ['2026-10-12', '1', '2', '1', '2', '1200']
    fields[field] = value
    refused(code, lambda: parsed((','.join(fields) + '\n').encode('ascii')))


@pytest.mark.parametrize('volume', ('0', '1200', '1200.0'))
def test_nonnegative_whole_volume_is_not_a_positive_trade_requirement(volume):
    raw = ('2026-10-12,1,2,1,2,' + volume + '\n').encode('ascii')
    assert m.private_rows(parsed(raw))[0].volume == int(Decimal(volume))


def test_coverage_counts_every_required_date_and_does_not_fill_missing_sessions():
    value = parsed()
    required = ('2026-10-09', '2026-10-12', '2026-10-13', '2026-10-14')
    references = ('2026-10-09', '2026-10-12')
    summary = m.assess_coverage(value, required, reference_sessions=references)
    assert (summary['required_session_count'], summary['present_required_count'],
        summary['missing_required_count']) == (4, 2, 2)
    assert (summary['reference_session_count'], summary['present_reference_count'],
        summary['missing_reference_count']) == (2, 1, 1)
    assert summary['observed_date_coverage_complete'] is False
    assert summary['member_pin'] == pin(source())
    assert m.private_missing_sessions(value, required) == ('2026-10-09', '2026-10-14')
    assert all(summary[name] is False for name in m.FALSE_FLAGS)
    assert '2026-10' not in repr(summary) and '12345' not in repr(summary)
    assert len(m.private_rows(value)) == summary['row_count'] == summary['selected_row_count'] == 2


@pytest.mark.parametrize('calendar', ([], (), ('2026-10-13', '2026-10-12'),
    ('2026-10-12', '2026-10-12'), (True,), ('2026-02-30',), ('2026-10-12 ',)))
def test_calendar_is_explicit_sorted_unique_and_cannot_be_inferred_or_repaired(calendar):
    refused('calendar', lambda: m.assess_coverage(parsed(), calendar))


def test_reference_dates_must_be_within_the_frozen_required_date_scope():
    refused('reference_scope', lambda: m.assess_coverage(parsed(), ('2026-10-12',),
        reference_sessions=('2026-10-13',)))
    refused('calendar', lambda: m.assess_coverage(parsed(), ('2026-10-12',), reference_sessions=[]))


@pytest.fixture
def synthetic_remx(monkeypatch):
    # Source bytes are synthetic, never a USB/member read. Patch only the
    # explicit policy pins/counts to exercise the otherwise exact partition.
    raw = source((m.remx.OLD_FIRST, m.remx.OLD_LAST, m.remx.PROVIDER_FIRST, m.remx.PROVIDER_LAST))
    for name, value in {'MEMBER_BYTES': len(raw), 'MEMBER_SHA256': pin(raw)['sha256'],
        'OLD_ROWS': 2, 'ETF_ROWS': 2, 'TOTAL_ROWS': 4}.items():
        monkeypatch.setattr(m.remx, name, value)
    listing = {'name': m.remx.PROVIDER_LISTING_NAME,
        'first_date': m.remx.PROVIDER_FIRST, 'last_date': m.remx.PROVIDER_LAST}
    return raw, parsed(raw, ticker='REMX'), listing


def test_exact_REMX_view_preserves_original_and_quarantined_bytes_separately(synthetic_remx):
    raw, original, listing = synthetic_remx
    current = m.apply_remx_partition(original, listing=listing)
    assert m.private_original_bytes(current) is m.private_original_bytes(original)
    assert m.private_original_bytes(current) == raw
    assert m.private_quarantined_bytes(current) == b''.join(raw.splitlines(keepends=True)[:2])
    assert len(m.private_rows(original)) == 4 and len(m.private_rows(current)) == 2
    assert current._rows is original._rows and current._offsets is original._offsets
    assert m.private_rows(current)[0].session == m.remx.PROVIDER_FIRST
    summary = m.assess_coverage(current, (m.remx.PROVIDER_FIRST, m.remx.PROVIDER_LAST))
    assert summary['quarantined_row_count'] == 2 and summary['selected_row_count'] == 2
    assert summary['row_count'] == 4 and summary['partition_policy_sha256'] == m.remx.profile_sha256()
    assert summary['observed_date_coverage_complete'] is True
    assert all(summary[name] is False for name in m.FALSE_FLAGS)
    refused('partition_once', lambda: m.apply_remx_partition(current, listing=listing))


@pytest.mark.parametrize('change', ('wrong_listing', 'missing_listing', 'wrong_alias', 'changed_member',
    'changed_prefix_count', 'wrong_boundary'))
def test_REMX_partition_cannot_be_used_as_an_arbitrary_row_filter(synthetic_remx, monkeypatch, change):
    raw, value, listing = synthetic_remx
    if change == 'wrong_listing': listing = {**listing, 'name': 'Synthetic changed issuer'}
    elif change == 'missing_listing': listing = {}
    elif change == 'wrong_alias': value = parsed(raw, ticker='SYNTHETIC')
    elif change == 'changed_member':
        raw = raw.replace(b'1200', b'1201')
        value = parsed(raw, ticker='REMX')
    elif change == 'changed_prefix_count': monkeypatch.setattr(m.remx, 'OLD_ROWS', 1)
    else:
        raw = raw.replace(m.remx.OLD_LAST.encode(), b'2006-06-29')
        monkeypatch.setattr(m.remx, 'MEMBER_SHA256', pin(raw)['sha256'])
        value = parsed(raw, ticker='REMX')
    refused('partition', lambda: m.apply_remx_partition(value, listing=listing))


def test_real_REMX_policy_pin_and_counts_are_not_refreshed_for_a_new_source():
    profile = m.profile_record()
    expected = m.remx.profile_record()
    assert expected['raw_member_pin'] == {'byte_count': 181222,
        'sha256': 'b8c54990689501ddc55183e6bb28c8eb7cd47a8817c04153480a6ef613b1de5e'}
    assert expected['quarantined_segment']['row_count'] == 323
    assert expected['ETF_segment']['row_count'] == 4016
    assert profile['REMX_partition_policy_sha256'] == m.remx.profile_sha256()
    assert all(profile[name] is False for name in m.FALSE_FLAGS)
    assert profile['source_pin_checked_before_decode'] is True
    assert profile['source_choice'].startswith('whole_binding_role_only')
    assert 'date' in profile['calendar'] or 'sessions' in profile['calendar']


@pytest.mark.parametrize('value', (None, {}, [], object()))
def test_coverage_rejects_unparsed_provider_shaped_objects(value):
    refused('series', lambda: m.assess_coverage(value, ('2026-10-12',)))


def test_source_bounds_and_unexpected_mutation_are_not_silent(monkeypatch):
    refused('bytes', lambda: parsed(b''))
    monkeypatch.setattr(m, 'MAX_MEMBER_BYTES', len(source()) - 1)
    refused('bytes', lambda: parsed())
    monkeypatch.undo()
    monkeypatch.setattr(m, 'MAX_ROWS', 1)
    refused('row_bound', lambda: parsed())
    monkeypatch.undo()
    monkeypatch.setattr(m, 'MAX_LINE_BYTES', 3)
    refused('row_bound', lambda: parsed())


def test_invalid_series_partition_state_refuses():
    value = parsed()
    changed = replace(value, _active_start=1)
    refused('series', lambda: m.assess_coverage(changed, ('2026-10-12',)))


@pytest.mark.parametrize('field', ('session', 'close', 'raw', 'offsets'))
def test_dataclass_replace_cannot_forge_rows_not_present_in_supplied_bytes(field):
    value = parsed()
    if field in ('session', 'close'):
        row = replace(value._rows[0], **({field: '2026-10-09'} if field == 'session'
            else {field: Decimal('99999')}))
        value = replace(value, _rows=(row, value._rows[1]))
    elif field == 'raw': value = replace(value, _raw=value._raw.replace(b'1200', b'1201'))
    else: value = replace(value, _offsets=(0, 1, len(value._raw)))
    refused('series', lambda: m.assess_coverage(value, ('2026-10-12',)))


def test_dataclass_replace_cannot_invent_a_REMX_quarantine_declaration(synthetic_remx):
    _, original, listing = synthetic_remx
    current = m.apply_remx_partition(original, listing=listing)
    forged = replace(current, _partition_metadata=b'{}')
    refused('series', lambda: m.assess_coverage(forged, (m.remx.PROVIDER_FIRST,)))


@pytest.mark.parametrize('change', ('bool_volume', 'decimal_volume', 'integer_price', 'NaN', 'sNaN',
    'bool_offset', 'alias_name_mismatch'))
def test_forged_equivalent_numeric_types_or_invalid_metadata_refuse(change):
    raw = b'2026-10-12,1,2,1,2,1\n'
    value = parsed(raw)
    bar = value._rows[0]
    if change == 'bool_volume': bar = replace(bar, volume=True)
    elif change == 'decimal_volume': bar = replace(bar, volume=Decimal('1'))
    elif change == 'integer_price': bar = replace(bar, open=1)
    elif change in ('NaN', 'sNaN'): bar = replace(bar, close=Decimal(change))
    elif change == 'bool_offset': value = replace(value, _offsets=(False, len(raw)))
    else: value = replace(value, _member_name='OTHER_full_1day_UNADJUSTED.txt')
    if change in ('bool_volume', 'decimal_volume', 'integer_price', 'NaN', 'sNaN'):
        value = replace(value, _rows=(bar,))
    refused('series', lambda: m.assess_coverage(value, ('2026-10-12',)))


def test_finite_unknown_errors_do_not_echo_supplied_content():
    assert m.finite(ValueError('synthetic secret')) == 'unknown'
    assert m.finite(m.Refused('synthetic secret')) == 'unknown'
