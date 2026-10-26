"""Pure original-TICKERS row cross-check, never price or routing authority.

The caller must authenticate the complete original CSV member and recompute a
genuine private catalog join before supplying one row.  This helper checks the
original composer's exact hashes and returns only redacted metadata evidence.
Its separate opaque private route must never be serialized or printed.
"""
from __future__ import annotations

from datetime import date
import hashlib
import re

from scripts import build_arv2_preopen_input as composer
from scripts import arv2_r298_reference_identity_join as identity_join


SCHEMA = 'arv2-r298-original-ticker-evidence-v1'
MAX_FIELDS, MAX_FIELD_CHARS, MAX_ROW_BYTES = 28, 8192, 65536
DATE_RELATIONS = ('before', 'at', 'after')
INTERVAL_RELATIONS = ('before', 'inside', 'after')
FALSE_FLAGS = {**identity_join.FALSE_FLAGS,
    'daily_price_coverage_proven': False, 'terminal_payoff_proven': False,
    'delisting_date_proven': False, 'original_capture_reaccepted': False,
    'candidate_interval_is_raw_price_interval': False,
    'current_snapshot_is_historical_availability': False,
    'raw_source_dates_disclosed': False, 'raw_provider_route_disclosed': False,
    'price_acquisition_performed': False, 'raw_response_disclosed': False}
FINITE = frozenset(('row_shape', 'row_bound', 'source_pin', 'metadata',
    'binding', 'match', 'context', 'identity', 'interval', 'changed', 'receipt'))
canonical, sha = identity_join.canonical, identity_join.sha


class Refused(ValueError):
    """Closed local predicate only, with no private source text."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    if type(error) is Refused:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE:
            return args[0]
    return 'unknown'


class PrivateTickerRoute:
    """Private display locators, not an operational or historical capability."""
    __slots__ = ('permaticker', 'ticker', 'composite_figi', 'exchange_mic',
        'first_priced_date', 'last_priced_date', '_sealed')

    def __init__(self, *, permaticker, ticker, composite_figi, exchange_mic,
                 first_priced_date, last_priced_date):
        for name, value in (('permaticker', permaticker), ('ticker', ticker),
                ('composite_figi', composite_figi), ('exchange_mic', exchange_mic),
                ('first_priced_date', first_priced_date), ('last_priced_date', last_priced_date)):
            object.__setattr__(self, name, value)
        object.__setattr__(self, '_sealed', True)

    def __setattr__(self, name, value):
        raise TypeError('private route is immutable')

    def __repr__(self):
        return '<PrivateTickerRoute redacted; no operational authority>'

    def __reduce_ex__(self, protocol):
        raise TypeError('private route must not be serialized')


def profile_record():
    return {'schema': SCHEMA, 'max_fields': MAX_FIELDS,
        'max_field_chars': MAX_FIELD_CHARS, 'max_row_bytes': MAX_ROW_BYTES,
        'original_hash_encoding': 'UTF8_sorted_JSON_ensure_ascii_false_WITH_LF',
        'binding_row_hash_encoding': 'canonical_ASCII_JSON_WITH_LF',
        'whole_binding_and_witness_hash_encoding': 'canonical_ASCII_JSON_without_LF',
        'field_hash_encoding': identity_join.FIELD_SCHEMA,
        'source_row_hash_compared_before_metadata_interpretation': True,
        'caller_authenticates_complete_original_csv_before_row_selection': True,
        'caller_recomputes_genuine_join_before_binding_selection': True,
        'original_composer_identity_reconstructed': True,
        'delisted_metadata_vocabulary': ['Y', 'N', 'unknown'],
        'clipped_candidate_dates_are_not_assumed_equal_to_raw_dates': True,
        'opaque_route_must_not_be_serialized_or_printed': True,
        'receipt_is_operational_capability': False, **FALSE_FLAGS}


def _hash(value, code='receipt'):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, code)
    return value


def _match(value):
    fields = {*identity_join.MATCH_HASHES, 'holding', 'kind', 'sid_date'}
    require(type(value) is dict and all(type(key) is str for key in value)
        and set(value) == fields, 'match')
    for key in identity_join.MATCH_HASHES:
        _hash(value[key], 'match')
    require(type(value['holding']) is str and value['holding'] in ('held', 'unheld_target', 'unknown')
        and type(value['kind']) is str and value['kind'] == 'stock'
        and type(value['sid_date']) is str and value['sid_date'] in (
            'on_or_before_reference', 'after_reference_through_decision', 'after_decision', 'unknown'), 'match')
    return dict(value)


def _source_bytes(row):
    require(type(row) is dict and len(row) == MAX_FIELDS
        and all(type(key) is str and 0 < len(key) <= 128 for key in row)
        and all(type(value) is str and len(value) <= MAX_FIELD_CHARS for value in row.values()), 'row_shape')
    try:
        raw = composer.canonical_json_bytes(row)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Refused('row_shape') from None
    require(0 < len(raw) <= MAX_ROW_BYTES, 'row_bound')
    return raw


def source_row_digest(row):
    """Hash one bounded full supplied CSV row without interpreting its fields."""
    return hashlib.sha256(_source_bytes(row)).hexdigest()


def _source(row, expected):
    raw = _source_bytes(row)
    require(hashlib.sha256(raw).hexdigest() == expected, 'source_pin')
    return dict(row), raw


def _binding(row, expected):
    require(type(row) is dict and all(type(key) is str for key in row)
        and set(row) == identity_join.figi._INPUT_FIELDS
        and all(value is None or type(value) in (str, int, bool) for value in row.values())
        and all(len(value) <= MAX_FIELD_CHARS for value in row.values() if type(value) is str), 'binding')
    try:
        checked = identity_join.figi._input_row(dict(row), expected['security_master_admission_sha256'])
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise Refused('binding') from None
    require(identity_join.legacy._sha(checked) == expected['whole_binding_row_sha256']
        and checked['row_sha256'] == expected['binding_row_sha256'], 'binding')
    return checked


def _date(value, code='interval'):
    require(type(value) is str and len(value) == 10, code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise Refused(code) from None
    require(parsed.isoformat() == value, code)
    return parsed


def _relation(value, other):
    return 'unavailable' if value is None else 'before' if value < other else 'after' if value > other else 'at'


def _interval(value, first, last):
    return 'before' if value < first else 'after' if value > last else 'inside'


def _metadata(row):
    """Exactly reproduce the frozen original composer's candidate semantics."""
    try:
        text = composer._text
        table, ticker = text(row.get('table'), 'table'), text(row.get('ticker'), 'ticker')
        require(table == composer._SHARADAR_FUNDAMENTALS_TABLE_ALIAS
            and composer._TICKER.fullmatch(ticker) is not None, 'metadata')
        perma, figi = text(row.get('permaticker'), 'permaticker'), text(row.get('figi'), 'figi')
        category, exchange = text(row.get('category'), 'category'), text(row.get('exchange'), 'exchange')
        require(category.casefold() in composer._ALLOWED_COMMON_STOCK_CATEGORIES, 'metadata')
        mic = composer._SHARADAR_EXCHANGE_TO_MIC.get(exchange.upper())
        require(mic is not None, 'metadata')
        # These two fields were also required to admit the original candidate.
        text(row.get('sector'), 'sector'); text(row.get('industry'), 'industry')
        cusips = composer._sharadar_cusips(row.get('cusips'))
        first = composer._date_text(row.get('firstpricedate'), 'firstpricedate')
        last_raw = text(row.get('lastpricedate'), 'lastpricedate', required=False)
        last = None if last_raw is None else composer._date_text(last_raw, 'lastpricedate')
        require(last is None or first <= last, 'interval')
    except Refused:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise Refused('metadata') from None
    return table, ticker, perma, figi, exchange, mic, cusips, first, last


def verify(row, joined_binding, context, *, expected_match):
    """Cross-check an authenticated supplied row; return evidence and private route.

    Neither a matching hash nor this pure call authenticates the supplied archive
    or proves a genuine join.  Those are the native caller's required gates.
    """
    expected = _match(expected_match)
    source, source_raw = _source(row, expected['source_row_sha256'])
    binding = _binding(joined_binding, expected)
    try:
        checked = identity_join.witness.validate_complete_witness(context)
        context_pin = identity_join.context_digest(checked)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise Refused('context') from None
    witnesses = [value for value in checked['witnesses'] if value['identity_sha256'] == expected['identity_sha256']]
    require(len(witnesses) == 1 and all(witnesses[0][key] == expected[key]
        for key in ('holding', 'kind', 'sid_date')), 'context')
    table, ticker, perma, figi, exchange, mic, cusips, first, last = _metadata(source)
    source_pin = hashlib.sha256(source_raw).hexdigest()
    identity = {'permaticker': perma, 'composite_figi': figi, 'source_table': table,
        'ticker': ticker, 'cusips': list(cusips), 'exchange': exchange, 'exchange_mic': mic,
        'firstpricedate': first, 'lastpricedate': last, 'source_row_sha256': source_pin,
        'availability_semantics': composer.TICKERS_AVAILABILITY}
    evidence_pin = hashlib.sha256(composer.canonical_json_bytes(identity)).hexdigest()
    reconstructed = {'security_id': composer._safe_component('sharadar-composite-figi', figi),
        'issuer_id': composer._safe_component('sharadar-permaticker', perma),
        'composite_figi': figi, 'listing_id': 'sharadar-listing-' + evidence_pin[:24],
        'diagnostic_current_ticker': ticker, 'diagnostic_exchange_mic': mic,
        'source_row_sha256': source_pin, 'identity_evidence_sha256': evidence_pin}
    require(all(type(binding[key]) is str and binding[key] == value
        for key, value in reconstructed.items()), 'identity')
    derived = {'identity_sha256': identity_join.legacy._sha({'schema': identity_join.WITNESS_SCHEMA,
            'security_id': binding['security_id'], 'reference_session': checked['reference_session'],
            'decision_session': checked['decision_session']}),
        'binding_row_sha256': binding['row_sha256'], 'whole_binding_row_sha256': identity_join.legacy._sha(binding),
        **{key: binding[key] for key in ('source_row_sha256', 'identity_evidence_sha256',
            'security_master_admission_sha256', 'admitted_mapping_inventory_sha256')},
        **{key + '_sha256': identity_join._field(key, binding[key]) for key in (
            'composite_figi', 'issuer_id', 'listing_id', 'diagnostic_current_ticker', 'diagnostic_exchange_mic',
            'candidate_first_session', 'candidate_last_session', 'source_snapshot_available_at')}}
    require(all(derived[key] == expected[key] for key in identity_join.MATCH_HASHES), 'match')
    reference, decision = _date(checked['reference_session']), _date(checked['decision_session'])
    first_date, last_date = _date(first), None if last is None else _date(last)
    candidate_first, candidate_last = _date(binding['candidate_first_session']), _date(binding['candidate_last_session'])
    require(candidate_first <= candidate_last, 'interval')
    delisted = source.get('isdelisted')
    state = delisted if delisted in ('Y', 'N') else 'unknown'
    result = {'schema': SCHEMA, 'status': 'original_ticker_metadata_crosschecked',
        'context_sha256': context_pin, **expected,
        'raw_first_price_date_sha256': identity_join._field('firstpricedate', first),
        'raw_last_price_date_sha256': identity_join._field('lastpricedate', last),
        'raw_first_price_vs_reference': _relation(first_date, reference),
        'raw_last_price_vs_reference': _relation(last_date, reference),
        'raw_first_price_vs_decision': _relation(first_date, decision),
        'raw_last_price_vs_decision': _relation(last_date, decision),
        'reference_candidate_interval_relation': _interval(reference, candidate_first, candidate_last),
        'decision_candidate_interval_relation': _interval(decision, candidate_first, candidate_last),
        'delisted_metadata_state': state,
        'delisted_metadata': True if state == 'Y' else False if state == 'N' else None,
        'cusip_candidate_count': len(cusips), 'original_composer_identity_matched': True,
        'candidate_intervals_are_clipped_input_geometry': True,
        'current_vintage_metadata_only': True, **FALSE_FLAGS}
    checked_result = validate_receipt(result)
    require(composer.canonical_json_bytes(row) == source_raw
        and identity_join.legacy._sha(joined_binding) == expected['whole_binding_row_sha256']
        and identity_join.context_digest(context) == context_pin
        and _match(expected_match) == expected, 'changed')
    route = PrivateTickerRoute(permaticker=perma, ticker=ticker, composite_figi=figi,
        exchange_mic=mic, first_priced_date=first, last_priced_date=last)
    return checked_result, route


DATE_FIELDS = ('raw_first_price_vs_reference', 'raw_last_price_vs_reference',
    'raw_first_price_vs_decision', 'raw_last_price_vs_decision')
INTERVAL_FIELDS = ('reference_candidate_interval_relation', 'decision_candidate_interval_relation')


def validate_receipt(value):
    expected_fields = {'schema', 'status', 'context_sha256', *identity_join.MATCH_HASHES,
        'holding', 'kind', 'sid_date', 'raw_first_price_date_sha256', 'raw_last_price_date_sha256',
        *DATE_FIELDS, *INTERVAL_FIELDS, 'delisted_metadata_state', 'delisted_metadata',
        'cusip_candidate_count', 'original_composer_identity_matched',
        'candidate_intervals_are_clipped_input_geometry', 'current_vintage_metadata_only', *FALSE_FLAGS}
    require(type(value) is dict and all(type(key) is str for key in value)
        and set(value) == expected_fields, 'receipt')
    require(type(value['schema']) is str and value['schema'] == SCHEMA
        and type(value['status']) is str and value['status'] == 'original_ticker_metadata_crosschecked'
        and value['original_composer_identity_matched'] is True
        and value['candidate_intervals_are_clipped_input_geometry'] is True
        and value['current_vintage_metadata_only'] is True
        and all(value[key] is False for key in FALSE_FLAGS), 'receipt')
    for key in ('context_sha256', *identity_join.MATCH_HASHES,
            'raw_first_price_date_sha256', 'raw_last_price_date_sha256'):
        _hash(value[key])
    _match({key: value[key] for key in (*identity_join.MATCH_HASHES, 'holding', 'kind', 'sid_date')})
    require(all(type(value[key]) is str and value[key] in DATE_RELATIONS
        for key in ('raw_first_price_vs_reference', 'raw_first_price_vs_decision'))
        and all(type(value[key]) is str and value[key] in (*DATE_RELATIONS, 'unavailable')
            for key in ('raw_last_price_vs_reference', 'raw_last_price_vs_decision'))
        and (value['raw_last_price_vs_reference'] == 'unavailable')
            == (value['raw_last_price_vs_decision'] == 'unavailable')
        and all(type(value[key]) is str and value[key] in INTERVAL_RELATIONS for key in INTERVAL_FIELDS), 'receipt')
    state = value['delisted_metadata_state']
    require(type(state) is str and state in ('Y', 'N', 'unknown')
        and (value['delisted_metadata'] is (True if state == 'Y' else False if state == 'N' else None))
        and type(value['cusip_candidate_count']) is int and 0 <= value['cusip_candidate_count'] <= 1024,
        'receipt')
    return dict(value)


def receipt_digest(value):
    return sha(canonical(validate_receipt(value)))
