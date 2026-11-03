"""Synthetic v2 final-record correction; no actual source or old operation read."""
from dataclasses import FrozenInstanceError, replace
import ast
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import pickle

import pytest

from scripts import arv2_r335_firstrate_prices_v2 as m


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


@pytest.mark.parametrize('ending', ('\n', '\r\n'))
@pytest.mark.parametrize('suffix', ('', ' 00:00:00'))
@pytest.mark.parametrize('terminated', (False, True))
def test_complete_final_record_is_retained_with_or_without_final_separator(ending, suffix, terminated):
    raw = source(suffix=suffix, ending=ending)
    if not terminated:
        raw = raw[:-len(ending)]
    value = parsed(raw)
    rows = m.private_rows(value)
    assert len(rows) == 2 and rows[-1].session == '2026-10-13'
    assert rows[-1].close == Decimal('12345.8') and rows[-1].volume == 1200
    assert m.private_original_bytes(value) is raw
    assert value._offsets[-1] == len(raw)
    summary = m.assess_coverage(value, ('2026-10-12', '2026-10-13'))
    assert summary['row_count'] == 2 and summary['present_required_count'] == 2
    assert summary['member_pin'] == pin(raw)
    evidence = m.line_ending_evidence(raw)
    assert evidence['physical_record_count'] == 2
    assert evidence['ends_LF'] is terminated
    assert evidence['ends_CRLF'] is (terminated and ending == '\r\n')
    assert evidence['unterminated_final_record'] is not terminated
    assert evidence['complete_final_record'] is True


def test_single_complete_unterminated_record_needs_no_separator():
    raw = b'2026-10-12,1,2,1,2,1200'
    value = parsed(raw)
    assert len(m.private_rows(value)) == 1
    assert value._offsets == (0, len(raw))
    evidence = m.line_ending_evidence(raw)
    assert evidence == {'schema': m.SCHEMA + '-line-ending-evidence', 'byte_count': len(raw),
        'LF_count': 0, 'CRLF_count': 0, 'bare_CR_count': 0, 'ends_LF': False,
        'ends_CRLF': False, 'physical_record_count': 1, 'unterminated_final_record': True,
        'complete_final_record': True, 'final_record_field_count': 6, 'line_endings_consistent': True}


@pytest.mark.parametrize('tail,code', (
    (b'2026-10-13,1,2,1,2', 'row_shape'),
    (b'2026-10-13,1,2,1,2,', 'number'),
    (b'2026-10-13,1,2,1,2,1.', 'number'),
    (b'2026-10-13,1,2,1,NaN,1', 'number'),
    (b'2026-10-13,1,2,1,2,1\r', 'line_ending'),
    (b'2026-10-13,1,2,1,2,1\n\n', 'row_bound'),
    (b'2026-10-13,1,2,1,2,1\r\n', 'line_ending'),
))
def test_optional_terminator_never_permits_a_truncated_invalid_or_mixed_final_record(tail, code):
    raw = b'2026-10-12,1,2,1,2,1\n' + tail
    refused(code, lambda: parsed(raw))


def test_torn_source_with_syntactically_valid_numeric_prefix_still_needs_original_whole_pin():
    original = b'2026-10-12,1,2,1,2,1200'
    torn = original[:-1]
    assert m.line_ending_evidence(torn)['complete_final_record'] is True
    refused('pin', lambda: m.parse_daily(torn, expected_pin=pin(original),
        member_name='SYNTHETIC_full_1day_UNADJUSTED.txt', expected_ticker='SYNTHETIC'))


@pytest.mark.parametrize('raw,wanted', (
    (b'one\rtwo', {'LF_count': 0, 'CRLF_count': 0, 'bare_CR_count': 1, 'line_endings_consistent': False}),
    (b'one\r\ntwo\nthree', {'LF_count': 2, 'CRLF_count': 1, 'bare_CR_count': 0, 'line_endings_consistent': False}),
    (b'one\r\ntwo\r\n', {'LF_count': 2, 'CRLF_count': 2, 'bare_CR_count': 0, 'line_endings_consistent': True}),
    (b'one\ntwo', {'LF_count': 1, 'CRLF_count': 0, 'bare_CR_count': 0, 'line_endings_consistent': True}),
))
def test_lexical_evidence_reports_observations_without_guessing_failure_cause(raw, wanted):
    observed = m.line_ending_evidence(raw)
    assert all(observed[key] == value for key, value in wanted.items())
    assert observed['complete_final_record'] is False
    assert set(observed) == {'schema', 'byte_count', 'LF_count', 'CRLF_count', 'bare_CR_count',
        'ends_LF', 'ends_CRLF', 'physical_record_count', 'unterminated_final_record',
        'complete_final_record', 'final_record_field_count', 'line_endings_consistent'}
    assert all(type(observed[key]) is bool for key in ('ends_LF', 'ends_CRLF',
        'unterminated_final_record', 'complete_final_record', 'line_endings_consistent'))
    assert not any(token in repr(observed) for token in ('one', 'two', 'three'))


def test_lexical_field_completeness_does_not_claim_numeric_validity_or_source_authentication():
    raw = b'2026-10-12,NaN,2,1,2,1'
    evidence = m.line_ending_evidence(raw)
    assert evidence['complete_final_record'] is True
    refused('number', lambda: parsed(raw))
    assert not any(key in evidence for key in ('ticker', 'price', 'row', 'source_pin', 'failure_cause'))


@pytest.mark.parametrize('raw', (b'', '', None, bytearray(b'x')))
def test_lexical_evidence_accepts_only_bounded_nonempty_supplied_bytes(raw):
    refused('bytes', lambda: m.line_ending_evidence(raw))


def _top(tree, name):
    values = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(values) == 1
    return values[0]


def _assign(tree, name):
    values = [node for node in tree.body if isinstance(node, ast.Assign)
        and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name]
    assert len(values) == 1
    return values[0]


def test_additive_v2_has_a_bounded_static_inverse_to_the_exact_spent_public_v1():
    # Read public source bytes only. Never import, execute or invoke v1.
    root = Path(__file__).resolve().parents[2]
    old = (root / 'scripts/arv2_r335_firstrate_prices.py').read_bytes()
    new = (root / 'scripts/arv2_r335_firstrate_prices_v2.py').read_bytes()
    assert len(old) == 14015 and hashlib.sha256(old).hexdigest() == (
        '53a136d12f5e2979cfbec6395e57923078a398316fb6bab0678fb50db79d3868')
    assert m.V1_SOURCE_PIN == pin(old)
    before, after = ast.parse(old), ast.parse(new)
    # Only the new lexical helper, schema/provenance constant, documentation,
    # row splitting/offset bookkeeping and profile declaration may differ.
    restored = ast.parse(new)
    restored.body = [node for node in restored.body if not (
        isinstance(node, ast.FunctionDef) and node.name == 'line_ending_evidence'
        or isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'V1_SOURCE_PIN')]
    restored.body[0] = before.body[0]
    restored.body[restored.body.index(_assign(restored, 'SCHEMA'))] = _assign(before, 'SCHEMA')
    for name in ('_rows', 'profile_record'):
        restored.body[restored.body.index(_top(restored, name))] = _top(before, name)
    assert ast.dump(restored, include_attributes=False) == ast.dump(before, include_attributes=False)
    # Within the row loop all field/date/number/ordering/row-preservation guards
    # remain identical. Only iteration and the last-record byte offset change.
    old_loop = next(node for node in _top(before, '_rows').body if isinstance(node, ast.For))
    new_loop = next(node for node in _top(after, '_rows').body if isinstance(node, ast.For))
    new_loop.target, new_loop.iter = old_loop.target, old_loop.iter
    old_offset = next(node for node in old_loop.body if isinstance(node, ast.AugAssign))
    offset = next(node for node in new_loop.body if isinstance(node, ast.AugAssign))
    new_loop.body[new_loop.body.index(offset)] = old_offset
    assert ast.dump(new_loop, include_attributes=False) == ast.dump(old_loop, include_attributes=False)
    assert ast.dump(next(node for node in _top(after, '_rows').body if isinstance(node, ast.Try)),
        include_attributes=False) == ast.dump(next(node for node in _top(before, '_rows').body
            if isinstance(node, ast.Try)), include_attributes=False)
    assert m.profile_record()['source_delta'].startswith('optional_complete_final_record_terminator')
    assert m.profile_record()['schema'] == 'arv2-r335-firstrate-raw-daily-v2'
