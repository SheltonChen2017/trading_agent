"""Pure bounded EODHD RAW-history representation; no source or price admission.

The caller supplies pinned bytes and the genuine full frozen session axis.
Every input row is retained privately. Only exact on-axis RAW close values
become cells; adjusted_close and auxiliary OHLC never substitute for a close.
No I/O, acquisition, credential, callback, QC or execution operation exists.
"""
from datetime import date
from decimal import Decimal, DecimalException
import hashlib
import json
import math
import re
import time
from types import MappingProxyType

from scripts import arv2_r298_raw_price_acquisition as prices

SCHEMA = 'arv2-r298-EODHD-RAW-history-schema-v1'
FIRST, LAST = prices.FIRST, prices.LAST
FULL_AXIS_COUNT, SESSION_COUNT = prices.FULL_AXIS_COUNT, prices.PRICE_SESSION_COUNT
FULL_AXIS_SHA256 = prices.FULL_AXIS_SHA256
MAX_RAW_BYTES, MAX_NUMBER_CHARS = 1024 * 1024, 128
MAX_ROWS = (date.fromisoformat(LAST) - date.fromisoformat(FIRST)).days + 1
FIELDS = ('date', 'open', 'high', 'low', 'close', 'adjusted_close', 'volume')
AUXILIARY_FIELDS = ('open', 'high', 'low', 'adjusted_close')
FALSE_FLAGS = {'source_admission_granted': False, 'identity_admitted': False,
    'price_input_admitted': False, 'complete_strategy_price_coverage_proven': False,
    'adjusted_price_substituted': False, 'executable_quote_substituted': False,
    'point_in_time_proven': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False, 'provider_contact': False, 'QC_contact': False,
    'credential_access': False, 'new_operation_or_read_granted': False}
FINITE = frozenset(('deadline', 'pin', 'axis', 'json', 'json_bound', 'number',
    'row_shape', 'date', 'date_window', 'duplicate_date', 'date_order',
    'raw_close', 'auxiliary_price', 'volume', 'summary', 'session', 'absent', 'unknown'))


class Refused(ValueError):
    """Finite predicates only; no body, row, date, price or exception rendering."""


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        allow_nan=False).encode('ascii')


def sha(raw): return hashlib.sha256(raw).hexdigest()
def digest(value): return sha(canonical(value))
def pin(raw): return {'byte_count': len(raw), 'sha256': sha(raw)}
def _hash(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _budget(deadline):
    if deadline is not None:
        require(type(deadline) in (int, float) and math.isfinite(deadline)
            and time.monotonic() < deadline, 'deadline')


def _sessions(full_axis):
    try: result = prices._axis(full_axis)
    except (ValueError, TypeError, KeyError, OverflowError): raise Refused('axis') from None
    require(len(full_axis) == FULL_AXIS_COUNT and prices.digest(list(full_axis)) == FULL_AXIS_SHA256
        and len(result) == SESSION_COUNT, 'axis')
    return tuple(result)


def _pin(value):
    return type(value) is dict and set(value) == {'byte_count', 'sha256'} \
        and type(value['byte_count']) is int and 0 < value['byte_count'] <= MAX_RAW_BYTES \
        and _hash(value['sha256'])


def _number(text):
    require(type(text) is str and 0 < len(text) <= MAX_NUMBER_CHARS, 'number')
    try: value = Decimal(text)
    except DecimalException: raise Refused('number') from None
    require(value.is_finite() and abs(value.adjusted()) <= MAX_NUMBER_CHARS
        and abs(value.as_tuple().exponent) <= MAX_NUMBER_CHARS, 'number')
    return value


def _decode(raw, deadline):
    # Two structural levels are sufficient for the fixed array-of-flat-records
    # schema. Bound nesting before the decoder allocates recursive containers.
    depth, quoted, escaped, separators = 0, False, False, 0
    for ordinal, byte in enumerate(raw):
        if ordinal % 65536 == 0: _budget(deadline)
        if quoted:
            if escaped: escaped = False
            elif byte == 92: escaped = True
            elif byte == 34: quoted = False
            continue
        if byte == 34: quoted = True
        elif byte in (91, 123):
            depth += 1; require(depth <= 2, 'json_bound')
        elif byte in (93, 125):
            depth -= 1; require(depth >= 0, 'json')
        elif byte in (44, 58):
            separators += 1; require(separators <= MAX_ROWS * 15, 'json_bound')
    require(not quoted and not escaped and depth == 0, 'json')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'json'); result[key] = value
        return result
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
            parse_float=_number, parse_int=_number,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('number')))
    except Refused: raise
    except (ValueError, UnicodeError, RecursionError, OverflowError): raise Refused('json') from None
    require(type(value) is list and len(value) <= MAX_ROWS, 'row_shape')
    return value


def _date(value):
    require(type(value) is str and re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}', value) is not None, 'date')
    try: parsed = date.fromisoformat(value)
    except ValueError: raise Refused('date') from None
    require(parsed.isoformat() == value, 'date')
    return value


def _close(value):
    require(type(value) is Decimal and value.is_finite() and value > 0, 'raw_close')
    try: normalized = prices._price(str(value))
    except (ValueError, TypeError, DecimalException): raise Refused('raw_close') from None
    return normalized


def _inspect_bound(raw, sessions, expected_pin, deadline):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_RAW_BYTES
        and _pin(expected_pin) and pin(raw) == expected_pin, 'pin')
    rows = _decode(raw, deadline)
    axis, observed, seen, previous, private, cells = set(sessions), [], set(), None, [], {}
    off_axis, zero_auxiliary = [], 0
    for ordinal, row in enumerate(rows):
        _budget(deadline)
        require(type(row) is dict and set(row) == set(FIELDS), 'row_shape')
        session = _date(row['date'])
        require(FIRST <= session <= LAST, 'date_window')
        require(session not in seen, 'duplicate_date')
        require(previous is None or session > previous, 'date_order')
        previous = session; seen.add(session)
        close = _close(row['close'])
        for field in AUXILIARY_FIELDS:
            value = row[field]
            require(type(value) is Decimal and value.is_finite() and value >= 0, 'auxiliary_price')
            zero_auxiliary += value == 0
        volume = row['volume']
        require(type(volume) is Decimal and volume.is_finite() and volume >= 0
            and volume == volume.to_integral_value(), 'volume')
        aligned = session in axis
        observed.append(session)
        private.append((ordinal, 'on_axis' if aligned else 'off_axis', tuple(row[field] for field in FIELDS)))
        if aligned: cells[session] = close
        else: off_axis.append((ordinal, session))
    grid = tuple((session, 'valid', cells[session]) if session in cells else
        (session, 'absent', None) for session in sessions)
    absent = [session for session in sessions if session not in cells]
    summary = {'schema': SCHEMA, 'scope': 'one_supplied_body_technical_representation_not_source_or_price_admission',
        'raw_pin': dict(expected_pin), 'full_axis_count': FULL_AXIS_COUNT,
        'full_axis_sha256': FULL_AXIS_SHA256, 'expected_session_count': len(sessions),
        'expected_sessions_sha256': digest(list(sessions)), 'window_first': FIRST, 'window_last': LAST,
        'row_count': len(rows), 'on_axis_row_count': len(cells), 'off_axis_row_count': len(off_axis),
        'valid_RAW_cell_count': len(cells), 'explicit_absent_cell_count': len(absent),
        'observed_dates_sha256': digest(observed), 'absent_sessions_sha256': digest(absent),
        'off_axis_ordinals_and_dates_sha256': digest(off_axis), 'cell_stream_sha256': sha(b''.join(
            canonical(cell) + b'\n' for cell in grid)), 'auxiliary_zero_value_count': zero_auxiliary,
        'normalization_complete': not off_axis, 'all_required_cells_present': not absent,
        'every_supplied_row_retained': True, 'adjusted_close_ignored_for_RAW_cells': True, **FALSE_FLAGS}
    _validate_summary_bound(summary, sessions)
    return summary, PrivateRawHistory(raw, tuple(private), grid, digest(summary))


class PrivateRawHistory:
    """Supplied-data evidence only; never an authenticated source capability."""
    __slots__ = ('_raw', '_rows', '_grid', '_cells', 'byte_count', 'sha256', 'summary_sha256')
    def __init__(self, raw, rows, grid, summary_sha256):
        for name, value in (('_raw', raw), ('_rows', rows), ('_grid', grid),
                ('_cells', MappingProxyType({session: (state, value) for session, state, value in grid})),
                ('byte_count', len(raw)), ('sha256', sha(raw)), ('summary_sha256', summary_sha256)):
            object.__setattr__(self, name, value)
    def __setattr__(self, name, value): raise TypeError('private RAW history is immutable')
    def __repr__(self): return '<PrivateRawHistory supplied source values; redacted; no authority>'
    def __reduce_ex__(self, protocol): raise TypeError('private RAW history cannot be pickled')
    def private_rows(self):
        # Full seven-field values and original ordinal are retained; tuples
        # and Decimal values are immutable. This is no public serialization API.
        return self._rows
    def private_cells(self): return self._grid
    def cell(self, session):
        require(type(session) is str and session in self._cells, 'session')
        state, value = self._cells[session]
        return state, None if value is None else Decimal(value)
    def price(self, session):
        state, value = self.cell(session)
        require(state == 'valid', 'absent')
        return value


def _validate_summary_bound(value, sessions):
    keys = {'schema', 'scope', 'raw_pin', 'full_axis_count', 'full_axis_sha256',
        'expected_session_count', 'expected_sessions_sha256', 'window_first', 'window_last',
        'row_count', 'on_axis_row_count', 'off_axis_row_count', 'valid_RAW_cell_count',
        'explicit_absent_cell_count', 'observed_dates_sha256', 'absent_sessions_sha256',
        'off_axis_ordinals_and_dates_sha256', 'cell_stream_sha256', 'auxiliary_zero_value_count',
        'normalization_complete', 'all_required_cells_present', 'every_supplied_row_retained',
        'adjusted_close_ignored_for_RAW_cells', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
        and value['scope'] == 'one_supplied_body_technical_representation_not_source_or_price_admission'
        and _pin(value['raw_pin']) and type(value['full_axis_count']) is int
        and value['full_axis_count'] == FULL_AXIS_COUNT and value['full_axis_sha256'] == FULL_AXIS_SHA256
        and type(value['expected_session_count']) is int and value['expected_session_count'] == len(sessions)
        and value['expected_sessions_sha256'] == digest(list(sessions))
        and value['window_first'] == FIRST and value['window_last'] == LAST
        and value['every_supplied_row_retained'] is value['adjusted_close_ignored_for_RAW_cells'] is True
        and all(value[key] is False for key in FALSE_FLAGS), 'summary')
    for name in ('row_count', 'on_axis_row_count', 'off_axis_row_count', 'valid_RAW_cell_count',
            'explicit_absent_cell_count', 'auxiliary_zero_value_count'):
        require(type(value[name]) is int and 0 <= value[name] <= MAX_ROWS * 4, 'summary')
    require(value['row_count'] <= MAX_ROWS
        and value['row_count'] == value['on_axis_row_count'] + value['off_axis_row_count']
        and value['on_axis_row_count'] == value['valid_RAW_cell_count']
        and value['on_axis_row_count'] + value['explicit_absent_cell_count'] == len(sessions)
        and value['auxiliary_zero_value_count'] <= len(AUXILIARY_FIELDS) * value['row_count']
        and type(value['normalization_complete']) is bool
        and value['normalization_complete'] is (value['off_axis_row_count'] == 0)
        and type(value['all_required_cells_present']) is bool
        and value['all_required_cells_present'] is (value['explicit_absent_cell_count'] == 0), 'summary')
    for name in ('observed_dates_sha256', 'absent_sessions_sha256',
            'off_axis_ordinals_and_dates_sha256', 'cell_stream_sha256'):
        require(_hash(value[name]), 'summary')
    if value['off_axis_row_count'] == 0:
        require(value['off_axis_ordinals_and_dates_sha256'] == digest([]), 'summary')
    if value['explicit_absent_cell_count'] == 0:
        require(value['absent_sessions_sha256'] == digest([]), 'summary')
    if value['row_count'] == 0: require(value['observed_dates_sha256'] == digest([]), 'summary')
    return json.loads(canonical(value))


def inspect(raw, *, full_session_axis, expected_pin, deadline=None):
    _budget(deadline)
    sessions = _sessions(full_session_axis)
    return _inspect_bound(raw, sessions, expected_pin, deadline)


def validate_summary(value, *, full_session_axis):
    return _validate_summary_bound(value, _sessions(full_session_axis))


def profile_record():
    return {'schema': SCHEMA, 'maximum_raw_bytes': MAX_RAW_BYTES,
        'maximum_row_count': MAX_ROWS, 'maximum_number_lexical_characters': MAX_NUMBER_CHARS,
        'fields': list(FIELDS), 'full_axis_count': FULL_AXIS_COUNT, 'full_axis_sha256': FULL_AXIS_SHA256,
        'expected_session_count': SESSION_COUNT, 'first': FIRST, 'last': LAST,
        'calendar_proof': 'unchanged_raw_price_acquisition_axis_requires_complete3466_fixed_digest_then_filters_exact1452',
        'raw_close': 'exact_Decimal_positive_frozen_price_text_max128_adjusted_exponent_abs128_normalized_length128',
        'auxiliary_prices': 'finite_nonnegative_exact_Decimal_zero_values_retained_and_counted_never_used',
        'volume': 'finite_nonnegative_integral_exact_Decimal',
        'off_axis': 'retain_original_ordinal_full_seven_values_no_cell_no_redating_normalization_incomplete',
        'missing': 'explicit_absent_only_when_expected_date_not_in_supplied_rows_never_invalid_close_as_absent',
        'row_order': 'strict_ASCII_ISO_dates_ascending_unique_within_fixed_window_no_sorting_or_dropping',
        'number_decoder': 'UTF8_strict_JSON_duplicate_keys_refused_Decimal_lexical128_adjusted_and_scale_exponent_abs128_no_float',
        'private_values': 'immutable_tuples_Decimal_redacted_repr_no_pickle_no_raw_serializer_no_source_authority',
        'raw_pin': 'externally_supplied_pin_compared_before_JSON_not_self_authentication_or_read_authority',
        **FALSE_FLAGS}
