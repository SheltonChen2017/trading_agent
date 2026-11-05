"""FirstRate v3 accepts LF or CRLF per record without changing source bytes.

The caller binds source containers, member pins, identities and a genuine
calendar separately. Ticker filenames and matching hashes do not admit a
security, source, price convention or run. Original bytes and all parsed rows
remain in an opaque private value; only the exact REMX policy can create a
separately declared current-era view. No filesystem or service access exists.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import re

from scripts import arv2_r335_remx_identity as remx


SCHEMA = 'arv2-r335-firstrate-raw-daily-v3'
V2_SOURCE_PIN = {'byte_count': 15808, 'sha256':
    'a0c8d235036d37c95af47d1719c69405b0c2e979d92fcb32070ef42ac672cc5e'}
V1_SOURCE_PIN = {'byte_count': 14015, 'sha256':
    '53a136d12f5e2979cfbec6395e57923078a398316fb6bab0678fb50db79d3868'}
MAX_MEMBER_BYTES = 4 * 1024 * 1024
MAX_ROWS = 30000
MAX_LINE_BYTES = 640
MAX_NUMBER_BYTES = 128
MAX_REQUIRED_SESSIONS = 4000
FALSE_FLAGS = ('identity_admitted', 'source_admission_granted', 'price_input_admitted',
    'source_assignment_changed', 'source_or_processing_rights_granted',
    'point_in_time_proven', 'formal_forward_ready', 'paper_or_live_ready',
    'backtest_authority_granted')
FINITE = frozenset(('bytes', 'pin', 'member', 'encoding', 'line_ending', 'row_bound',
    'row_shape', 'session', 'timestamp', 'date_order', 'number', 'price', 'OHLC',
    'volume', 'series', 'calendar', 'reference_scope', 'partition', 'partition_once',
    'unknown'))


class Refused(ValueError):
    """Finite failure only, never an identifier, row, price or raw error."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def _flags():
    return {name: False for name in FALSE_FLAGS}


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _pin(raw):
    return {'byte_count': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def _checked_pin(value):
    require(type(value) is dict and set(value) == {'byte_count', 'sha256'}
        and type(value['byte_count']) is int and 0 < value['byte_count'] <= MAX_MEMBER_BYTES
        and _hash(value['sha256']), 'pin')
    return value


def _session(value, code='session'):
    require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) is not None, code)
    try:
        require(date.fromisoformat(value).isoformat() == value, code)
    except ValueError:
        raise Refused(code) from None
    return value


def _timestamp(value):
    require(type(value) is str and len(value) in (10, 19), 'timestamp')
    if len(value) == 19:
        require(value[10:] == ' 00:00:00', 'timestamp')
    return _session(value[:10])


def _number(value):
    require(type(value) is str and 0 < len(value) <= MAX_NUMBER_BYTES
        and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', value) is not None, 'number')
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise Refused('number') from None
    require(result.is_finite(), 'number')
    return result


def _member(member_name, ticker, code='member'):
    require(type(ticker) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,63}', ticker)
        and type(member_name) is str
        and member_name == ticker + '_full_1day_UNADJUSTED.txt', code)


@dataclass(frozen=True, slots=True, repr=False)
class DailyBar:
    session: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def __repr__(self):
        return '<DailyBar private supplied source row>'

    def __reduce_ex__(self, protocol):
        raise TypeError('private supplied source row cannot be pickled')


@dataclass(frozen=True, slots=True, repr=False)
class DailySeries:
    _ticker: str
    _member_name: str
    _raw: bytes
    _rows: tuple
    _offsets: tuple
    _active_start: int
    _partition_policy_sha256: str | None
    _partition_metadata: bytes | None

    def __repr__(self):
        return '<DailySeries private supplied source; no identity or price admission>'

    def __reduce_ex__(self, protocol):
        raise TypeError('private supplied source series cannot be pickled')


def line_ending_evidence(raw):
    """Return lexical counts only; six fields do not prove a valid market row.

    This may explain a current source shape after a separately authorized read.
    It neither authenticates bytes nor diagnoses a historical failed invocation.
    No field, timestamp, ticker, price, row fingerprint or raw exception escapes.
    """
    require(type(raw) is bytes and 0 < len(raw) <= MAX_MEMBER_BYTES, 'bytes')
    lf, crlf = raw.count(b'\n'), raw.count(b'\r\n')
    bare = raw.count(b'\r') - crlf
    ends_lf, ends_crlf = raw.endswith(b'\n'), raw.endswith(b'\r\n')
    final = raw.rsplit(b'\n', 2)[-2] if ends_lf else raw.rsplit(b'\n', 1)[-1]
    if ends_crlf:
        final = final[:-1]
    field_count = final.count(b',') + 1
    complete = (0 < len(final) <= MAX_LINE_BYTES and field_count == 6
        and not final.startswith(b',') and not final.endswith(b',') and b',,' not in final)
    return {'schema': SCHEMA + '-line-ending-evidence', 'byte_count': len(raw),
        'LF_count': lf, 'CRLF_count': crlf, 'bare_CR_count': bare,
        'ends_LF': ends_lf, 'ends_CRLF': ends_crlf,
        'physical_record_count': lf + (0 if ends_lf else 1),
        'unterminated_final_record': not ends_lf,
        'complete_final_record': bool(complete), 'final_record_field_count': field_count,
        'line_endings_consistent': bare == 0 and (crlf == 0 or crlf == lf),
        'line_endings_supported': bare == 0}


def _rows(raw):
    evidence = line_ending_evidence(raw)
    require(evidence['line_endings_supported'], 'line_ending')
    try:
        raw.decode('ascii')
    except UnicodeDecodeError:
        raise Refused('encoding') from None
    lines = raw.split(b'\n')
    terminated = evidence['ends_LF']
    if terminated:
        require(lines[-1] == b'', 'line_ending')
        lines = lines[:-1]
    require(1 <= len(lines) <= MAX_ROWS, 'row_bound')
    bars, offsets, offset, previous, timestamp_width = [], [], 0, None, None
    for index, line in enumerate(lines):
        separated = index < len(lines) - 1 or terminated
        separator_bytes = 1 if separated else 0
        if separated and line.endswith(b'\r'):
            line = line[:-1]
            separator_bytes = 2
        require(0 < len(line) <= MAX_LINE_BYTES, 'row_bound')
        fields = line.decode('ascii').split(',')
        require(len(fields) == 6, 'row_shape')
        session = _timestamp(fields[0])
        if timestamp_width is None:
            timestamp_width = len(fields[0])
        require(len(fields[0]) == timestamp_width, 'timestamp')
        require(previous is None or previous < session, 'date_order')
        values = tuple(_number(field) for field in fields[1:])
        opening, high, low, close, volume = values
        require(all(value > 0 for value in values[:4]), 'price')
        require(low <= min(opening, close) <= max(opening, close) <= high, 'OHLC')
        require(volume >= 0 and volume == volume.to_integral_value(), 'volume')
        bars.append(DailyBar(session, opening, high, low, close, int(volume)))
        offsets.append(offset)
        offset += len(line) + separator_bytes
        previous = session
    require(offset == len(raw), 'row_bound')
    return tuple(bars), tuple((*offsets, offset))


def parse_daily(raw, *, expected_pin, member_name, expected_ticker):
    """Check the exact supplied member before decoding any source row.

    expected_ticker is the caller's explicit member alias (including a possible
    -DELISTED suffix), not an inferred security identity. Calendar trading-day
    eligibility and closing-price semantics are not inferred here.
    """
    require(type(raw) is bytes and 0 < len(raw) <= MAX_MEMBER_BYTES, 'bytes')
    _checked_pin(expected_pin)
    require(_pin(raw) == expected_pin, 'pin')
    _member(member_name, expected_ticker)
    bars, offsets = _rows(raw)
    return DailySeries(expected_ticker, member_name, raw, bars, offsets, 0, None, None)


def _series(series):
    require(type(series) is DailySeries and type(series._raw) is bytes
        and 0 < len(series._raw) <= MAX_MEMBER_BYTES and type(series._rows) is tuple
        and 1 <= len(series._rows) <= MAX_ROWS and type(series._offsets) is tuple
        and len(series._offsets) == len(series._rows) + 1
        and series._offsets[0] == 0 and series._offsets[-1] == len(series._raw)
        and type(series._active_start) is int and 0 <= series._active_start < len(series._rows), 'series')
    _member(series._member_name, series._ticker, 'series')
    require(all(type(offset) is int for offset in series._offsets)
        and all(type(bar) is DailyBar and type(bar.session) is str
            and type(bar.volume) is int and bar.volume >= 0
            and all(type(value) is Decimal and value.is_finite() and value > 0
                for value in (bar.open, bar.high, bar.low, bar.close))
            for bar in series._rows), 'series')
    # A public frozen dataclass can still be copied with dataclasses.replace.
    # Do not let a copied row tuple claim coverage absent from its source bytes.
    try:
        bars, offsets = _rows(series._raw)
        require((bars, offsets) == (series._rows, series._offsets), 'series')
    except Refused:
        raise Refused('series') from None
    if series._active_start:
        require(series._ticker == remx.TICKER and series._active_start == remx.OLD_ROWS
            and series._partition_policy_sha256 == remx.profile_sha256()
            and type(series._partition_metadata) is bytes, 'series')
        try:
            declaration = _remx_declaration(series,
                listing=remx.profile_record()['provider_listing'])
            require(series._partition_metadata == declaration.metadata_bytes, 'series')
        except Refused:
            raise Refused('series') from None
    else:
        require(series._partition_policy_sha256 is series._partition_metadata is None, 'series')
    return series


def _calendar(values, *, empty=False):
    require(type(values) is tuple and (empty or bool(values)) and len(values) <= MAX_REQUIRED_SESSIONS
        and all(type(value) is str for value in values)
        and values == tuple(sorted(set(values))), 'calendar')
    for value in values:
        _session(value, 'calendar')
    return values


def private_rows(series):
    """Explicit private-processing access; opaque rows must not be logged."""
    checked = _series(series)
    return checked._rows[checked._active_start:]


def private_original_bytes(series):
    """All original bytes, including any explicitly quarantined prefix."""
    return _series(series)._raw


def private_quarantined_bytes(series):
    checked = _series(series)
    return checked._raw[:checked._offsets[checked._active_start]]


def private_missing_sessions(series, required_sessions):
    required = _calendar(required_sessions)
    observed = {bar.session for bar in private_rows(series)}
    return tuple(value for value in required if value not in observed)


def assess_coverage(series, required_sessions, *, reference_sessions=()):
    """Count supplied date coverage; never infer identity or source admission."""
    checked = _series(series)
    required = _calendar(required_sessions)
    references = _calendar(reference_sessions, empty=True)
    require(set(references) <= set(required), 'reference_scope')
    observed = {bar.session for bar in private_rows(checked)}
    present = len(set(required) & observed)
    present_references = len(set(references) & observed)
    return {'schema': SCHEMA + '-coverage', 'member_pin': _pin(checked._raw),
        'row_count': len(checked._rows), 'selected_row_count': len(checked._rows) - checked._active_start,
        'quarantined_row_count': checked._active_start,
        'partition_policy_sha256': checked._partition_policy_sha256,
        'required_session_count': len(required), 'present_required_count': present,
        'missing_required_count': len(required) - present,
        'reference_session_count': len(references), 'present_reference_count': present_references,
        'missing_reference_count': len(references) - present_references,
        'observed_date_coverage_complete': present == len(required), **_flags()}


def _remx_declaration(checked, *, listing):
    require(checked._ticker == remx.TICKER and checked._member_name == remx.MEMBER_NAME
        and _pin(checked._raw) == {'byte_count': remx.MEMBER_BYTES, 'sha256': remx.MEMBER_SHA256}
        and len(checked._rows) == remx.TOTAL_ROWS and 0 < remx.OLD_ROWS < remx.TOTAL_ROWS, 'partition')
    old = checked._rows[:remx.OLD_ROWS]
    current = checked._rows[remx.OLD_ROWS:]
    metadata = {'raw_member_pin': _pin(checked._raw), 'ticker': remx.TICKER,
        'listing': listing, 'segments': [
            {'first_date': old[0].session, 'last_date': old[-1].session, 'row_count': len(old)},
            {'first_date': current[0].session, 'last_date': current[-1].session, 'row_count': len(current)}],
        'total_row_count': len(checked._rows)}
    try:
        return remx.validate_partition(metadata)
    except remx.Refused:
        raise Refused('partition') from None


def apply_remx_partition(series, *, listing):
    """Create only the exact declared REMX view; retain all original content."""
    checked = _series(series)
    require(checked._active_start == 0, 'partition_once')
    declaration = _remx_declaration(checked, listing=listing)
    return DailySeries(checked._ticker, checked._member_name, checked._raw, checked._rows,
        checked._offsets, remx.OLD_ROWS, declaration.policy_sha256, declaration.metadata_bytes)


def profile_record():
    return {'schema': SCHEMA, 'maximum_member_bytes': MAX_MEMBER_BYTES, 'maximum_rows': MAX_ROWS,
        'maximum_line_bytes': MAX_LINE_BYTES, 'maximum_number_bytes': MAX_NUMBER_BYTES,
        'maximum_required_sessions': MAX_REQUIRED_SESSIONS,
        'source_format': 'strict_ASCII_headerless_six_fields_DateTime_Open_High_Low_Close_Volume',
        'timestamp_forms': ['YYYY-MM-DD', 'YYYY-MM-DD 00:00:00'],
        'timestamp_forms_mixed_within_member': False,
        'line_endings': 'per_record_LF_or_CRLF_including_mixed_optional_complete_final_terminator_no_bare_CR_or_blank_rows',
        'v2_source_pin': dict(V2_SOURCE_PIN),
        'separator_handling': 'strip_only_one_CR_immediately_before_LF_original_bytes_and_actual_offsets_retained',
        'supported_and_uniform': 'bare_CR_zero_is_supported_uniformity_is_separate_observation_not_acceptance_gate',
        'v1_source_pin': dict(V1_SOURCE_PIN),
        'source_delta': 'per_record_LF_or_CRLF_and_supported_vs_uniform_evidence_only',
        'lexical_evidence_scope': 'field_completeness_and_separator_counts_not_OHLCV_date_identity_or_source_authentication',
        'prices': 'finite_positive_Decimal_OHLC_relations_no_adjustment',
        'volume': 'finite_nonnegative_integral_individual_shares',
        'source_pin_checked_before_decode': True,
        'row_order': 'strictly_ascending_unique_dates_no_sorting_deduplication_or_silent_row_drop',
        'opaque_input_recheck': 'supplied_bytes_reparsed_before_coverage_or_private_access_no_dataclass_replace_forgery',
        'calendar': 'caller_supplied_explicit_sorted_unique_sessions_not_authenticated_here',
        'source_choice': 'whole_binding_role_only_never_per_date_fallback_or_eligibility_selector',
        'member_alias': 'explicit_exact_flat_UNADJUSTED_daily_filename_not_security_identity',
        'raw_close_convention': 'requires_separate_external_validation_not_inferred_from_OHLCV',
        'private_data': 'opaque_repr_and_pickle_refusal_explicit_private_processing_access_only',
        'REMX_partition_policy_sha256': remx.profile_sha256(),
        'REMX_partition': 'exact_full_member_and_323row_prefix_quarantined_original_bytes_retained',
        'research_evidence': 'new_source_policy_current_vintage_only_no_original_R327_result_relabel',
        **_flags()}
