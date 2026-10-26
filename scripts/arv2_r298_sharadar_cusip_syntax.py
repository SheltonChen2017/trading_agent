"""Offline syntax observation of two exact retained T metadata captures.

The new complete-vocabulary parser is prospective only.  Neither its accepted
tokens nor current-vintage metadata establish active/historical CUSIP identity.
This module performs no filesystem, credential, provider or QC operation.
"""
from __future__ import annotations

import re

from scripts import arv2_r298_sharadar_probe_metadata as previous


SCHEMA = 'arv2-r298-sharadar-cusip-syntax-v1'
T_SOURCE_SHA256 = '3122b8f2be402d1d74de7b0f0259835d5c317d6d30b00274a069607024b881ae'
T_RECEIPT_SHA256 = '84449eda55a1aad5b7139c1c2561457cf84c439c60204896ef912d798ae8c637'
CAPTURE_PINS = {
    'stocks-probe.csv': {'byte_count': 225, 'sha256': '0f0578e8f3067bfc40b3e32bcec8ad05d42087b3a4f1428a4d993cc9db7eb9bf'},
    'funds-probe.csv': {'byte_count': 899, 'sha256': '5e37400fd38313f4980f4947ef1e9aeafc52e4cf3566b64ee686bc91c9b9fdaa'},
}
CAPTURE_NAMES = previous.CAPTURE_NAMES
MAX_FIELD_BYTES, MAX_TOKENS, MAX_SEPARATOR_ORDINALS = 2048, 64, 32
REASONS = frozenset(('accepted', 'missing', 'field_type', 'field_bound', 'non_ascii',
    'control', 'empty_token', 'token_shape', 'token_count', 'duplicate'))
GRAMMARS = frozenset(('missing', 'single', 'comma', 'ascii_space', 'unknown'))
FINITE = REASONS | frozenset(('capture_shape', 'capture_pin', 't_projection', 'receipt', 'receipt_bound', 'unknown'))
FALSE_FLAGS = {**previous.FALSE_FLAGS, 'new_parser_admitted': False,
    'historical_active_identity_proven': False, 's_failure_cause_authenticated': False,
    't_failure_cause_authenticated': False, 'price_input_admitted': False,
    'provider_contact': False, 'qc_contact': False, 'strategy_result_admitted': False}
canonical, sha = previous.canonical, previous.sha


class Refused(ValueError):
    """A closed syntax/source diagnostic refusal, never raw source content."""


def require(condition, code):
    if not condition: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def profile_record():
    return {'schema': SCHEMA, 'purpose': 'offline_retained_public_probe_CUSIP_syntax_not_identity_admission',
        't_source_sha256': T_SOURCE_SHA256, 't_receipt_sha256': T_RECEIPT_SHA256,
        'capture_pins': {name: dict(CAPTURE_PINS[name]) for name in CAPTURE_NAMES},
        'fixed_probe_count': len(previous.PROBES), 'maximum_field_UTF8_bytes': MAX_FIELD_BYTES,
        'maximum_tokens': MAX_TOKENS, 'maximum_separator_ordinals': MAX_SEPARATOR_ORDINALS,
        'parser_grammar': 'nine_ASCII_alphanumeric_tokens_comma_with_ASCII_spaces_OR_ASCII_space_list',
        'outer_ASCII_spaces_allowed': True, 'ASCII_lowercase_normalized_to_uppercase': True,
        'ASCII_space_separators_may_be_one_or_more': True,
        'controls_and_nonASCII_refused': True, 'empty_tokens_and_duplicates_refused': True,
        'mixed_comma_and_space_token_lists_refused': True, 'all_input_consumed': True,
        'returned_vocabulary': 'sorted_complete_unique_tokens_never_first_match_or_findall',
        'separator_evidence': 'actual_nonalphanumeric_codepoint_ordinals_and_counts_only',
        'field_hash': 'canonical_ASCII_JSON_string_SHA256_not_raw_UTF8_SHA256',
        't_projection': 'pure_recomputed_full_T_receipt_hash_plus_exact_unique_nine_probe_census',
        'source_authentication': 'exact_supplied_capture_byte_count_and_SHA256_before_parsing',
        'caller_owns_native_FD_security_and_actual_exit_authentication': True,
        'old_parser_and_S_T_composer_sources_unchanged': True,
        'current_vintage_only': True, 'diagnostic_only': True,
        'historical_CUSIP_vocabulary_is_not_active_or_effective_interval_proof': True,
        **FALSE_FLAGS}


def _syntax(value):
    """Return private tokens and a finite analysis; no substring extraction."""
    result = {'grammar': 'unknown', 'reason': 'field_type', 'lexical_token_count': None,
        'duplicate_token_count': None, 'new_parse_count': 0, 'accepted': False}
    if type(value) is not str: return (), result
    if not value:
        result.update(grammar='missing', reason='missing'); return (), result
    if len(value) > MAX_FIELD_BYTES:
        result['reason'] = 'field_bound'; return (), result
    if not value.isascii():
        result['reason'] = 'non_ascii'; return (), result
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        result['reason'] = 'control'; return (), result
    text = value.strip(' ')
    if not text:
        result.update(grammar='missing', reason='missing'); return (), result
    if ',' in text:
        grammar, parts = 'comma', tuple(part.strip(' ') for part in text.split(','))
    elif ' ' in text:
        grammar, parts = 'ascii_space', tuple(part for part in text.split(' ') if part)
    else:
        grammar, parts = 'single', (text,)
    result['grammar'] = grammar
    if any(not part for part in parts):
        result['reason'] = 'empty_token'; return (), result
    if any(re.fullmatch('[A-Za-z0-9]{9}', part) is None for part in parts):
        result['reason'] = 'token_shape'; return (), result
    tokens = tuple(part.upper() for part in parts)
    result.update(lexical_token_count=len(tokens), duplicate_token_count=len(tokens) - len(set(tokens)))
    if len(tokens) > MAX_TOKENS:
        result['reason'] = 'token_count'; return (), result
    if result['duplicate_token_count']:
        result['reason'] = 'duplicate'; return (), result
    result.update(reason='accepted', new_parse_count=len(tokens), accepted=True)
    return tuple(sorted(tokens)), result


def parse_cusips(value):
    """Parse the whole prospective vocabulary, or refuse without raw values."""
    tokens, analysis = _syntax(value)
    require(analysis['accepted'], analysis['reason'])
    return tokens


def _field(value):
    require(type(value) is str, 't_projection')
    try: byte_count = len(value.encode('utf-8'))
    except UnicodeError: raise Refused('t_projection') from None
    require(byte_count <= MAX_FIELD_BYTES, 't_projection')
    separators = {}
    for character in value:
        if not ('0' <= character <= '9' or 'A' <= character <= 'Z' or 'a' <= character <= 'z'):
            ordinal = ord(character); separators[ordinal] = separators.get(ordinal, 0) + 1
    require(len(separators) <= MAX_SEPARATOR_ORDINALS, 't_projection')
    _, analysis = _syntax(value)
    return {'field_utf8_byte_count': byte_count, 'field_sha256': sha(canonical(value)),
        'separator_ordinals': [{'ordinal': ordinal, 'count': separators[ordinal]} for ordinal in sorted(separators)],
        'ASCII_lowercase_present': any('a' <= character <= 'z' for character in value),
        'legacy_parse_count': len(previous.composer._sharadar_cusips(value)), **analysis}


def _capture_bytes(captures):
    require(type(captures) is dict and len(captures) == len(CAPTURE_NAMES)
        and all(type(name) is str and name in CAPTURE_NAMES for name in captures), 'capture_shape')
    for name in CAPTURE_NAMES:
        raw, pin = captures[name], CAPTURE_PINS[name]
        require(type(raw) is bytes and len(raw) == pin['byte_count'] and sha(raw) == pin['sha256'], 'capture_pin')


def inspect_captures(captures):
    """Observe only exact retained T bytes; no old operational entry point."""
    _capture_bytes(captures)
    try:
        t_receipt = previous.validate_receipt(previous._receipt(captures))
        stocks, funds = (previous._rows(captures[name]) for name in CAPTURE_NAMES)
    except previous.Refused:
        raise Refused('t_projection') from None
    require(t_receipt['metadata_row_counts'] == {'stocks': 1, 'funds': 8}
        and sha(canonical(t_receipt)) == T_RECEIPT_SHA256
        and t_receipt['unexpected_ticker_row_counts'] == {'stocks': 0, 'funds': 0}
        and all(probe['candidate_count'] == 1 and probe['candidate_ambiguous'] is False
            for probe in t_receipt['probes']), 't_projection')
    observations = []
    for index, (table, ticker) in enumerate(previous.PROBES):
        rows = stocks if table == 'stocks' else funds
        candidates = [row for row in rows if row['ticker'] == ticker]
        require(len(candidates) == 1, 't_projection')
        field = _field(candidates[0]['cusips'])
        old = t_receipt['probes'][index]['fields']['cusips']
        require(field['field_sha256'] == old['value_sha256']
            and field['field_utf8_byte_count'] == old['utf8_byte_count'], 't_projection')
        observations.append({'probe_index': index, **field})
    return validate_receipt({'schema': SCHEMA, 'status': 'retained_CUSIP_syntax_observed',
        't_schema': previous.SCHEMA, 't_source_sha256': T_SOURCE_SHA256,
        't_receipt_sha256': sha(canonical(t_receipt)),
        'capture_pins': {name: dict(CAPTURE_PINS[name]) for name in CAPTURE_NAMES},
        'probe_count': len(previous.PROBES), 'probes': observations,
        'provider_application_dispatches': 0, 'qc_application_dispatches': 0,
        'current_vintage_only': True, 'diagnostic_only': True, **FALSE_FLAGS})


def _hash(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate_receipt(value):
    fixed = {'schema': SCHEMA, 'status': 'retained_CUSIP_syntax_observed',
        't_schema': previous.SCHEMA, 't_source_sha256': T_SOURCE_SHA256,
        'probe_count': len(previous.PROBES), 'provider_application_dispatches': 0,
        'qc_application_dispatches': 0, 'current_vintage_only': True, 'diagnostic_only': True, **FALSE_FLAGS}
    require(type(value) is dict and len(value) == len(fixed) + 3
        and all(type(key) is str and key in set(fixed) | {'t_receipt_sha256', 'capture_pins', 'probes'} for key in value)
        and all(key in value and type(value[key]) is type(item) and value[key] == item for key, item in fixed.items()), 'receipt')
    require(value['t_receipt_sha256'] == T_RECEIPT_SHA256 and type(value['t_receipt_sha256']) is str
        and type(value['capture_pins']) is dict
        and value['capture_pins'] == CAPTURE_PINS
        and all(type(pin) is dict and set(pin) == {'byte_count', 'sha256'}
            and type(pin['byte_count']) is int and type(pin['sha256']) is str for pin in value['capture_pins'].values()), 'receipt')
    probes = value['probes']
    require(type(probes) is list and len(probes) == len(previous.PROBES), 'receipt')
    keys = {'probe_index', 'field_utf8_byte_count', 'field_sha256', 'separator_ordinals',
        'ASCII_lowercase_present', 'legacy_parse_count', 'grammar', 'reason', 'lexical_token_count',
        'duplicate_token_count', 'new_parse_count', 'accepted'}
    for index, row in enumerate(probes):
        require(type(row) is dict and set(row) == keys and type(row['probe_index']) is int and row['probe_index'] == index
            and type(row['field_utf8_byte_count']) is int and 0 <= row['field_utf8_byte_count'] <= MAX_FIELD_BYTES
            and _hash(row['field_sha256']) and type(row['ASCII_lowercase_present']) is bool
            and type(row['legacy_parse_count']) is int and 0 <= row['legacy_parse_count'] <= 204
            and type(row['grammar']) is str and row['grammar'] in GRAMMARS
            and type(row['reason']) is str and row['reason'] in REASONS
            and type(row['accepted']) is bool and type(row['new_parse_count']) is int
            and 0 <= row['new_parse_count'] <= MAX_TOKENS, 'receipt')
        separators = row['separator_ordinals']
        require(type(separators) is list and len(separators) <= MAX_SEPARATOR_ORDINALS, 'receipt')
        last, separator_count = -1, 0
        for item in separators:
            require(type(item) is dict and set(item) == {'ordinal', 'count'} and type(item['ordinal']) is int
                and last < item['ordinal'] <= 0x10ffff and not 0xd800 <= item['ordinal'] <= 0xdfff
                and not (48 <= item['ordinal'] <= 57 or 65 <= item['ordinal'] <= 90 or 97 <= item['ordinal'] <= 122)
                and type(item['count']) is int and 0 < item['count'] <= MAX_FIELD_BYTES, 'receipt')
            last = item['ordinal']; separator_count += item['count']
        require(separator_count <= row['field_utf8_byte_count'], 'receipt')
        count, duplicate = row['lexical_token_count'], row['duplicate_token_count']
        require((count is None and duplicate is None) or (type(count) is int and 1 <= count <= 204
            and type(duplicate) is int and 0 <= duplicate < count), 'receipt')
        require(row['accepted'] is (row['reason'] == 'accepted'), 'receipt')
        if row['accepted']:
            require(type(count) is int and 1 <= count <= MAX_TOKENS and duplicate == 0
                and row['new_parse_count'] == count and row['grammar'] in ('single', 'comma', 'ascii_space')
                and all(item['ordinal'] in (32, 44) for item in separators)
                and row['field_utf8_byte_count'] == 9 * count + separator_count
                and (row['grammar'] == 'comma') is any(item['ordinal'] == 44 for item in separators)
                and (row['grammar'] != 'single' or count == 1)
                and (row['grammar'] != 'ascii_space' or (count >= 2 and separator_count >= count - 1))
                and (row['grammar'] != 'comma' or next(item['count'] for item in separators if item['ordinal'] == 44) == count - 1)
                and row['legacy_parse_count'] == (0 if row['grammar'] == 'ascii_space' else count), 'receipt')
        else:
            require(row['new_parse_count'] == 0, 'receipt')
            if row['reason'] in ('duplicate', 'token_count'):
                require(type(count) is int and (duplicate > 0 if row['reason'] == 'duplicate' else count > MAX_TOKENS), 'receipt')
            else: require(count is duplicate is None, 'receipt')
        empty = row['field_utf8_byte_count'] == 0
        require(empty is (row['field_sha256'] == sha(canonical(''))), 'receipt')
        if empty:
            require(row['reason'] == row['grammar'] == 'missing' and row['legacy_parse_count'] == 0
                and not separators and not row['ASCII_lowercase_present'], 'receipt')
    require(len(canonical(value)) <= 65536, 'receipt_bound')
    return {**fixed, 't_receipt_sha256': value['t_receipt_sha256'],
        'capture_pins': {name: dict(CAPTURE_PINS[name]) for name in CAPTURE_NAMES},
        'probes': [{**row, 'separator_ordinals': [dict(item) for item in row['separator_ordinals']]} for row in probes]}


def validate_capture(receipt, captures):
    checked = validate_receipt(receipt)
    require(canonical(checked) == canonical(inspect_captures(captures)), 'receipt')
    return checked


inspect = inspect_captures
