"""Supplied synthetic RAW history only; never an acquired or admitted source."""
from datetime import date
from decimal import Decimal
import json
import pickle
import time

import pytest

from scripts import arv2_r298_eodhd_history_schema as m


def bar(session='2020-12-31', **changes):
    values = {'date': json.dumps(session), 'open': '10', 'high': '12', 'low': '9',
        'close': '11', 'adjusted_close': '0.5', 'volume': '100'}
    values.update(changes)
    return '{' + ','.join(json.dumps(key) + ':' + value for key, value in values.items()) + '}'


def body(*rows): return ('[' + ','.join(rows) + ']').encode('utf-8')


@pytest.fixture
def synthetic_axis(monkeypatch):
    # A three-cell synthetic axis exercises the unchanged real _axis validator.
    # Only tests change its pinned constants; the production API offers no
    # override, permission boolean, partial-axis or calendar callback.
    values = ('2020-12-31', '2021-01-04', '2026-10-13')
    digest = m.digest(list(values))
    for module in (m, m.prices):
        monkeypatch.setattr(module, 'FULL_AXIS_COUNT', 3)
        monkeypatch.setattr(module, 'FULL_AXIS_SHA256', digest)
    monkeypatch.setattr(m, 'SESSION_COUNT', 3)
    monkeypatch.setattr(m.prices, 'PRICE_SESSION_COUNT', 3)
    return values


def inspect(raw, axis, **kwargs):
    return m.inspect(raw, full_session_axis=axis, expected_pin=m.pin(raw), **kwargs)


def refused(code, action):
    with pytest.raises(m.Refused) as caught: action()
    assert m.finite(caught.value) == code


def test_production_calendar_binding_and_financial_bounds_are_not_a_caller_selected_window():
    profile = m.profile_record()
    assert (m.FULL_AXIS_COUNT, m.SESSION_COUNT) == (3466, 1452)
    assert m.FULL_AXIS_SHA256 == '4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585'
    assert (m.FIRST, m.LAST) == ('2020-12-31', '2026-10-13')
    assert m.MAX_ROWS == (date(2026, 10, 13) - date(2020, 12, 31)).days + 1
    assert profile['maximum_raw_bytes'] == 1024 * 1024
    assert 'unchanged_raw_price_acquisition_axis' in profile['calendar_proof']
    assert all(profile[key] is False for key in m.FALSE_FLAGS)


def test_invalid_frozen_axis_refuses_before_any_body_decoder(monkeypatch):
    monkeypatch.setattr(m, '_decode', lambda *_: pytest.fail('body parsed before axis proof'))
    refused('axis', lambda: inspect(b'not-json', [m.FIRST] * 3466))


@pytest.mark.parametrize('change', ['missing', 'reorder', 'duplicate', 'changed_date'])
def test_exact_full_axis_order_count_and_digest_remain_mandatory(synthetic_axis, change):
    axis = list(synthetic_axis)
    if change == 'missing': axis.pop()
    elif change == 'reorder': axis.reverse()
    elif change == 'duplicate': axis[1] = axis[0]
    else: axis[1] = '2021-01-05'
    refused('axis', lambda: inspect(body(bar()), axis))


def test_exact_Decimal_RAW_close_is_retained_and_adjusted_value_never_substitutes(synthetic_axis):
    exact = '0.1000000000000000000000000000000000000001'
    raw = body(bar(close=exact, adjusted_close='99.99'), bar('2021-01-04'), bar('2026-10-13'))
    summary, private = inspect(raw, synthetic_axis)
    assert private.price('2020-12-31') == Decimal(exact)
    assert type(private.price('2020-12-31')) is Decimal
    assert private.private_rows()[0][2][4] == Decimal(exact)
    assert private.private_rows()[0][2][5] == Decimal('99.99')
    assert summary['valid_RAW_cell_count'] == 3 and summary['explicit_absent_cell_count'] == 0
    assert summary['normalization_complete'] is summary['all_required_cells_present'] is True
    assert summary['raw_pin'] == m.pin(raw)
    assert summary['adjusted_close_ignored_for_RAW_cells'] is True
    assert all(summary[key] is False for key in m.FALSE_FLAGS)
    assert m.validate_summary(summary, full_session_axis=synthetic_axis) == summary


def test_missing_expected_dates_are_explicit_absent_cells_and_never_zero_or_forward_fill(synthetic_axis):
    summary, private = inspect(body(bar()), synthetic_axis)
    assert summary['row_count'] == summary['valid_RAW_cell_count'] == 1
    assert summary['explicit_absent_cell_count'] == 2
    assert summary['normalization_complete'] is True and summary['all_required_cells_present'] is False
    assert private.cell('2021-01-04') == ('absent', None)
    refused('absent', lambda: private.price('2021-01-04'))
    assert private.private_cells() == (('2020-12-31', 'valid', '11'),
        ('2021-01-04', 'absent', None), ('2026-10-13', 'absent', None))


def test_empty_history_is_a_valid_empty_representation_with_every_expected_cell_absent(synthetic_axis):
    summary, private = inspect(b'[]', synthetic_axis)
    assert summary['row_count'] == summary['on_axis_row_count'] == summary['off_axis_row_count'] == 0
    assert summary['explicit_absent_cell_count'] == 3 and not summary['all_required_cells_present']
    assert private.private_rows() == ()
    assert all(state == 'absent' and value is None for _, state, value in private.private_cells())


def test_in_window_off_axis_row_retains_ordinal_and_full_values_but_never_becomes_a_cell(synthetic_axis):
    raw = body(bar(), bar('2021-01-02', close='31.125', adjusted_close='1000'), bar('2021-01-04'))
    summary, private = inspect(raw, synthetic_axis)
    assert summary['row_count'] == 3 and summary['on_axis_row_count'] == 2
    assert summary['off_axis_row_count'] == 1 and summary['normalization_complete'] is False
    assert summary['explicit_absent_cell_count'] == 1
    assert private.private_rows()[1] == (1, 'off_axis', ('2021-01-02', Decimal('10'), Decimal('12'),
        Decimal('9'), Decimal('31.125'), Decimal('1000'), Decimal('100')))
    assert len(private.private_cells()) == 3
    refused('session', lambda: private.cell('2021-01-02'))
    refused('session', lambda: private.price('2021-01-02'))


@pytest.mark.parametrize('close,code', [('0', 'raw_close'), ('-1', 'raw_close'),
    ('null', 'raw_close'), ('true', 'raw_close'), ('"1.25"', 'raw_close'),
    ('NaN', 'number'), ('Infinity', 'number'), ('-Infinity', 'number'),
    ('1e129', 'number'), ('1e-129', 'number'), ('1e128', 'raw_close')])
def test_present_invalid_RAW_close_is_a_refusal_never_an_absent_cell(synthetic_axis, close, code):
    refused(code, lambda: inspect(body(bar(close=close)), synthetic_axis))


def test_positive_frozen_price_text_boundary_and_scientific_values_use_exact_Decimal(synthetic_axis):
    raw = body(bar(close='1e-126'), bar('2021-01-04', close='1e127'))
    _, private = inspect(raw, synthetic_axis)
    assert private.price('2020-12-31') == Decimal('1e-126')
    assert private.price('2021-01-04') == Decimal('1e127')
    assert len(private.private_cells()[0][2]) == len(private.private_cells()[1][2]) == 128


@pytest.mark.parametrize('field', ['open', 'high', 'low', 'adjusted_close'])
@pytest.mark.parametrize('value,code', [('null', 'auxiliary_price'), ('"1"', 'auxiliary_price'),
    ('-1', 'auxiliary_price'), ('NaN', 'number'), ('1e99999999', 'number')])
def test_unused_price_fields_still_require_bounded_finite_nonnegative_numeric_structure(synthetic_axis, field, value, code):
    refused(code, lambda: inspect(body(bar(**{field: value})), synthetic_axis))


def test_zero_unused_fields_are_retained_and_counted_without_changing_the_RAW_close(synthetic_axis):
    summary, private = inspect(body(bar(open='0', high='0.0', low='0', adjusted_close='0')), synthetic_axis)
    assert summary['auxiliary_zero_value_count'] == 4
    assert private.price('2020-12-31') == Decimal('11')
    assert private.private_rows()[0][2][1:4] == (Decimal('0'), Decimal('0.0'), Decimal('0'))


@pytest.mark.parametrize('volume,code', [('null', 'volume'), ('true', 'volume'), ('"2"', 'volume'),
    ('-1', 'volume'), ('1.5', 'volume'), ('NaN', 'number'), ('1e99999999', 'number')])
def test_volume_is_nonnegative_integral_exact_numeric_data(synthetic_axis, volume, code):
    refused(code, lambda: inspect(body(bar(volume=volume)), synthetic_axis))


@pytest.mark.parametrize('volume', ['0', '0.0', '12', '12.0', '1.2e2'])
def test_integral_volume_values_are_preserved_without_float_or_integer_coercion(synthetic_axis, volume):
    _, private = inspect(body(bar(volume=volume)), synthetic_axis)
    assert private.private_rows()[0][2][-1] == Decimal(volume)
    assert type(private.private_rows()[0][2][-1]) is Decimal


@pytest.mark.parametrize('rows,code', [
    ((bar(), bar()), 'duplicate_date'),
    ((bar('2021-01-02'), bar('2021-01-04'), bar('2021-01-02')), 'duplicate_date'),
    ((bar('2021-01-04'), bar()), 'date_order'),
    ((bar('2020-12-30'),), 'date_window'), ((bar('2026-10-14'),), 'date_window'),
    ((bar('2021-02-29'),), 'date'), ((bar('2021-1-04'),), 'date'),
    ((bar('２０２１-01-04'),), 'date')])
def test_date_order_duplicate_off_axis_and_window_errors_are_never_repaired(synthetic_axis, rows, code):
    refused(code, lambda: inspect(body(*rows), synthetic_axis))


@pytest.mark.parametrize('raw,code', [
    (b'{}', 'row_shape'), (b'[null]', 'row_shape'), (b'[[[]]]', 'json_bound'),
    (b'[', 'json'), (b'[] trailing', 'json'), (b'\xff', 'json'),
    (body(bar()).replace(b'"close":11', b'"close":11,"close":12'), 'json'),
    (body(bar()).replace(b'"close":11', b'"close":11,"\\u0063lose":12'), 'json'),
    (body(bar()).replace(b'"close":11', b'"extra":11'), 'row_shape'),
    (body(bar(close='1' * 129)), 'number')])
def test_strict_UTF8_JSON_shape_duplicates_and_numeric_bounds(synthetic_axis, raw, code):
    refused(code, lambda: inspect(raw, synthetic_axis))


def test_raw_pin_and_size_are_checked_before_any_JSON(synthetic_axis, monkeypatch):
    monkeypatch.setattr(m, '_decode', lambda *_: pytest.fail('JSON parsed before raw pin'))
    refused('pin', lambda: m.inspect(b'not-json', full_session_axis=synthetic_axis,
        expected_pin={'byte_count': 8, 'sha256': 'a' * 64}))
    refused('pin', lambda: m.inspect(b'x' * (m.MAX_RAW_BYTES + 1), full_session_axis=synthetic_axis,
        expected_pin={'byte_count': m.MAX_RAW_BYTES, 'sha256': 'a' * 64}))
    refused('pin', lambda: m.inspect(b'[]', full_session_axis=synthetic_axis,
        expected_pin={'byte_count': True, 'sha256': m.sha(b'[]')}))


def test_expired_budget_refuses_before_decoding_and_deadline_cannot_be_boolean(synthetic_axis):
    refused('deadline', lambda: inspect(body(bar()), synthetic_axis, deadline=time.monotonic() - 1))
    refused('deadline', lambda: inspect(body(bar()), synthetic_axis, deadline=True))


def test_row_count_and_predecoder_structure_are_bounded(synthetic_axis, monkeypatch):
    monkeypatch.setattr(m, 'MAX_ROWS', 2)
    refused('row_shape', lambda: inspect(body('{}', '{}', '{}'), synthetic_axis))
    refused('json_bound', lambda: inspect(b'[' * 4 + b']' * 4, synthetic_axis))


def test_private_rows_cells_and_summary_are_immutable_or_independent_and_metadata_only(synthetic_axis):
    summary, private = inspect(body(bar(close='19.8765432101')), synthetic_axis)
    assert '19.8765432101' not in repr(private) and '2020-12-31' not in repr(private)
    assert private.byte_count == summary['raw_pin']['byte_count'] and private.sha256 == summary['raw_pin']['sha256']
    assert private.summary_sha256 == m.digest(summary)
    with pytest.raises(TypeError): private.sha256 = 'a' * 64
    with pytest.raises(TypeError): private._cells['2020-12-31'] = ('valid', '999')
    with pytest.raises(TypeError): private.private_rows()[0][2][4] = Decimal('999')
    with pytest.raises(TypeError): pickle.dumps(private)
    public = m.canonical(summary)
    assert b'19.8765432101' not in public and b'close":' not in public
    cloned = m.validate_summary(summary, full_session_axis=synthetic_axis)
    cloned['raw_pin']['sha256'] = 'a' * 64
    assert summary['raw_pin']['sha256'] == private.sha256


@pytest.mark.parametrize('field,value', [('row_count', True), ('valid_RAW_cell_count', 2),
    ('normalization_complete', False), ('all_required_cells_present', True),
    ('off_axis_row_count', -1), ('price_input_admitted', True)])
def test_summary_rejects_contradictory_counts_and_readiness_claims(synthetic_axis, field, value):
    summary, _ = inspect(body(bar()), synthetic_axis)
    summary[field] = value
    refused('summary', lambda: m.validate_summary(summary, full_session_axis=synthetic_axis))


def test_summary_rejects_unknown_fields_and_raw_row_disclosure(synthetic_axis):
    summary, _ = inspect(body(bar()), synthetic_axis)
    summary['raw_rows'] = [{'close': 'PRIVATE'}]
    refused('summary', lambda: m.validate_summary(summary, full_session_axis=synthetic_axis))
