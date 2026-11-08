"""RAM-only observation of one supplied stock bulk-status response.

No request, filesystem or credential lookup occurs. Format/lexical evidence
does not authenticate a subscription cause, entitlement or usable price data.
Malformed encoding/JSON is observed without a body hash or secret-free claim.
"""
from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
import json
import math
import re

from scripts import arv2_r298_sharadar_eligibility_observation as frozen

SCHEMA = 'arv2-r298-sharadar-status-shape-v1'
FROZEN_SOURCE_SHA256 = 'c2c669b7e58bbb9ce118328225ddc8b8e7d96df1c1d7727309e42544279a197e'
MAX_BODY, MAX_DEPTH, MAX_NODES, MAX_KEYS = 8192, 12, 512, 64
EXPECTED_KEYS = ('table', 'name', 'size', 'sizeLabel', 'modified')
ERROR_KEYS = ('error', 'errors', 'message', 'detail', 'status', 'code', 'success')
KNOWN_KEYS = EXPECTED_KEYS + ERROR_KEYS
TYPES = frozenset(('object', 'list', 'string', 'integer', 'number', 'boolean', 'null'))
LEXICAL = ('subscription', 'expired', 'authentication', 'entitlement', 'rate_limit')
PREDICATES = ('body_valid_json', 'top_object', 'keys_exact', 'table_equals_stocks',
    'name_equals_stocks_zip', 'size_positive_nonbool_integer_lt_2pow63',
    'size_label_ASCII_nonempty_max64_without_low_controls',
    'modified_ASCII_nonempty_max40', 'modified_ISO_aware')
FINITE = frozenset(('body', 'credential', 'credential_echo', 'json_duplicate',
    'json_nonfinite', 'json_bound', 'json_type', 'receipt', 'legacy_consistency', 'unknown'))
FALSE_FLAGS = {'provider_contact': False, 'qc_contact': False, 'body_persisted': False,
    'credential_persisted': False, 'raw_strings_disclosed': False,
    'failure_cause_authenticated': False, 'subscription_expiry_proven': False,
    'paid_tier_proven': False, 'entitlement_proven': False, 'price_input_admitted': False,
    'strategy_nav_admitted': False, 'strategy_result_accepted': False,
    'formal_identity_admitted': False, 'point_in_time_proven': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False}
canonical, sha = frozen.canonical, frozen.sha


class Refused(ValueError):
    """Finite shape/security refusal; never source text."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def profile_record():
    return {'schema': SCHEMA, 'purpose': 'supplied_stock_status_shape_not_subscription_cause',
        'frozen_status_source_sha256': FROZEN_SOURCE_SHA256,
        'expected_table': 'stocks', 'maximum_body_bytes': MAX_BODY,
        'maximum_JSON_depth': MAX_DEPTH, 'maximum_JSON_nodes': MAX_NODES,
        'maximum_object_keys': MAX_KEYS, 'expected_keys': list(EXPECTED_KEYS),
        'fixed_error_key_inventory': list(ERROR_KEYS),
        'credential_scan': 'raw_encodings_then_every_decoded_JSON_key_and_string_before_any_hash',
        'duplicate_nonfinite_and_overbound_JSON': 'finite_refusal',
        'malformed_encoding_or_JSON': 'closed_format_only_no_hash_no_credential_absence_claim',
        'modified_formats': 'ISO_aware_naive_date_only_RFC_aware_naive_other',
        'size_string_numeric': 'lexical_only_never_coerced_into_integer_admission',
        'raw_body_retention': 'RAM_only_no_files',
        'lexical_flags_are_untrusted_word_presence_inferences_not_causes': True,
        'legacy_status_check': 'unchanged_pure_S_parser_after_safe_decoded_scan',
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}


def _type(value):
    return {dict: 'object', list: 'list', str: 'string', int: 'integer',
        float: 'number', bool: 'boolean', type(None): 'null'}.get(type(value))


def _pairs(items):
    require(len(items) <= MAX_KEYS, 'json_bound')
    result = {}
    for key, value in items:
        require(type(key) is str and key not in result, 'json_duplicate')
        result[key] = value
    return result


def _constant(_):
    raise Refused('json_nonfinite')


def _scan(value, key):
    pending, nodes = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        require(nodes <= MAX_NODES and depth <= MAX_DEPTH, 'json_bound')
        kind = type(item)
        require(_type(item) is not None, 'json_type')
        if kind is str:
            require(key not in item, 'credential_echo')
        elif kind is dict:
            require(len(item) <= MAX_KEYS, 'json_bound')
            pending.extend((child, depth + 1) for pair in item.items() for child in pair)
        elif kind is list:
            pending.extend((child, depth + 1) for child in item)
        elif kind is float:
            require(math.isfinite(item), 'json_nonfinite')


def _strings(value):
    pending, result = [value], []
    while pending:
        item = pending.pop()
        if type(item) is str:
            result.append(item)
        elif type(item) is dict:
            pending.extend(item.keys()); pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
    return result


def _summary(value):
    return {'type': _type(value), 'canonical_sha256': sha(canonical(value))}


def _size(value):
    kind = _type(value)
    result = {'type': kind, 'classification': kind, 'positive_integer_value': None,
        'decimal_string_digit_count': None}
    if type(value) is int:
        result['classification'] = ('positive_in_range' if 0 < value < 2**63 else
            'zero' if value == 0 else 'negative' if value < 0 else 'integer_out_of_range')
        if 0 < value < 2**63:
            result['positive_integer_value'] = value
    elif type(value) is float:
        result['classification'] = 'integral_number' if value.is_integer() else 'fractional_number'
    elif type(value) is str:
        decimal = value.isascii() and value.isdecimal() and bool(value)
        result['classification'] = 'unsigned_decimal_string' if decimal else 'other_string'
        if decimal:
            result['decimal_string_digit_count'] = len(value)
    return result


def _modified(value):
    result = {'type': _type(value), 'classification': 'not_string', 'ASCII': None,
        'nonempty_max40': None, 'timezone_aware': None}
    if type(value) is not str:
        return result
    result.update(ASCII=value.isascii(), nonempty_max40=0 < len(value) <= 40)
    if not value:
        result['classification'] = 'empty'; return result
    if not value.isascii():
        result['classification'] = 'non_ASCII'; return result
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        aware = parsed.tzinfo is not None and parsed.utcoffset() is not None
        result.update(classification='ISO_date_only' if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value)
            else 'ISO_aware' if aware else 'ISO_naive', timezone_aware=aware)
        return result
    except (ValueError, OverflowError):
        pass
    try:
        parsed = parsedate_to_datetime(value)
        aware = parsed.tzinfo is not None and parsed.utcoffset() is not None
        result.update(classification='RFC_aware' if aware else 'RFC_naive', timezone_aware=aware)
    except (ValueError, TypeError, OverflowError, IndexError):
        result['classification'] = 'unrecognized'
    return result


def _lexical(value):
    strings = _strings(value)
    patterns = {'subscription': r'\b(?:subscription|subscribed|plan)\b',
        'expired': r'\b(?:expired|expiry|expiration|expire)\b',
        'authentication': r'\b(?:authentication|authenticate|unauthenticated|unauthorized|api[_ -]?key|token)\b',
        'entitlement': r'\b(?:entitlement|entitled|permission|forbidden|access[_ -]?denied)\b',
        'rate_limit': r'\b(?:rate[_ -]?limit|too[_ -]?many|429)\b'}
    return {name: any(re.search(pattern, text, re.I) is not None for text in strings)
        for name, pattern in patterns.items()}


def _predicates(value):
    obj = type(value) is dict
    found = {key: False if obj else None for key in PREDICATES}
    found.update(body_valid_json=True, top_object=obj)
    if not obj:
        return found
    found['keys_exact'] = set(value) == set(EXPECTED_KEYS)
    found['table_equals_stocks'] = value.get('table') == 'stocks'
    found['name_equals_stocks_zip'] = value.get('name') == 'stocks.csv.zip'
    size, label, modified = (value.get(key) for key in ('size', 'sizeLabel', 'modified'))
    found['size_positive_nonbool_integer_lt_2pow63'] = type(size) is int and 0 < size < 2**63
    found['size_label_ASCII_nonempty_max64_without_low_controls'] = (type(label) is str
        and 0 < len(label) <= 64 and label.isascii() and not any(ord(char) < 32 for char in label))
    found['modified_ASCII_nonempty_max40'] = type(modified) is str and modified.isascii() and 0 < len(modified) <= 40
    shape = _modified(modified)
    found['modified_ISO_aware'] = shape['classification'] == 'ISO_aware'
    return found


def _receipt(byte_count, format_, value=None, raw=None):
    parsed = format_ == 'JSON'
    obj = parsed and type(value) is dict
    predicates = _predicates(value) if parsed else {key: False if key == 'body_valid_json' else None
        for key in PREDICATES}
    accepted = all(item is True for item in predicates.values())
    if parsed:
        try:
            frozen._status(raw, 'stocks')
            legacy = True
        except frozen.Refused:
            legacy = False
        require(legacy == accepted, 'legacy_consistency')
    known = {key: _summary(value[key]) if obj and key in value else None for key in KNOWN_KEYS}
    inference = _lexical({key: value[key] for key in ERROR_KEYS if key in value}) if obj else dict.fromkeys(LEXICAL, False)
    return validate_receipt({'schema': SCHEMA, 'status': 'supplied_stock_status_shape_observed',
        'body_byte_count': byte_count, 'body_sha256': sha(raw) if parsed else None,
        'body_format': format_, 'credential_absence_authenticated': parsed,
        'top_level_type': _type(value) if parsed else None,
        'object_key_count': len(value) if obj else None,
        'expected_key_presence': {key: key in value if obj else None for key in EXPECTED_KEYS},
        'unexpected_key_count': sum(key not in EXPECTED_KEYS for key in value) if obj else None,
        'known_fields': known,
        'size_shape': _size(value['size']) if obj and 'size' in value else None,
        'modified_shape': _modified(value['modified']) if obj and 'modified' in value else None,
        'contract_predicates': predicates, 'legacy_contract_accepted': accepted,
        'failed_predicates': sorted(key for key, item in predicates.items() if item is not True),
        'error_lexical_inferences': inference,
        'lexical_inferences_are_not_authenticated_causes': True,
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS})


def inspect_body(raw, *, api_key):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY, 'body')
    try:
        key = frozen.source._validated_api_key(api_key, synthetic=False)
    except Exception:
        raise Refused('credential') from None
    require(not any(token in raw for token in frozen._encodings(key)), 'credential_echo')
    try:
        text = raw.decode('utf-8-sig', errors='strict')
    except UnicodeError:
        return _receipt(len(raw), 'invalid_UTF8')
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except Refused:
        raise
    except RecursionError:
        raise Refused('json_bound') from None
    except (ValueError, UnicodeError):
        return _receipt(len(raw), 'malformed_JSON')
    _scan(value, key)  # No hash/receipt precedes the complete decoded scan.
    return _receipt(len(raw), 'JSON', value, raw)


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate_receipt(value):
    fixed = {'schema': SCHEMA, 'status': 'supplied_stock_status_shape_observed',
        'lexical_inferences_are_not_authenticated_causes': True, 'diagnostic_only': True,
        'result_cell': 0, **FALSE_FLAGS}
    variable = {'body_byte_count', 'body_sha256', 'body_format', 'credential_absence_authenticated',
        'top_level_type', 'object_key_count', 'expected_key_presence', 'unexpected_key_count',
        'known_fields', 'size_shape', 'modified_shape', 'contract_predicates',
        'legacy_contract_accepted', 'failed_predicates', 'error_lexical_inferences'}
    require(type(value) is dict and len(value) == len(fixed) + len(variable)
        and all(type(key) is str and key in set(fixed) | variable for key in value)
        and all(type(value[key]) is type(item) and value[key] == item for key, item in fixed.items()), 'receipt')
    require(type(value['body_byte_count']) is int and 0 < value['body_byte_count'] <= MAX_BODY
        and type(value['body_format']) is str and value['body_format'] in ('JSON', 'invalid_UTF8', 'malformed_JSON')
        and type(value['credential_absence_authenticated']) is bool
        and type(value['legacy_contract_accepted']) is bool, 'receipt')
    parsed = value['body_format'] == 'JSON'
    require(value['credential_absence_authenticated'] is parsed
        and (_hash(value['body_sha256']) if parsed else value['body_sha256'] is None)
        and (type(value['top_level_type']) is str and value['top_level_type'] in TYPES
            if parsed else value['top_level_type'] is None), 'receipt')
    obj = parsed and value['top_level_type'] == 'object'
    presence, known = value['expected_key_presence'], value['known_fields']
    require(type(presence) is dict and set(presence) == set(EXPECTED_KEYS)
        and all(type(item) is bool if obj else item is None for item in presence.values())
        and type(known) is dict and set(known) == set(KNOWN_KEYS), 'receipt')
    present_count = 0
    for key, item in known.items():
        if item is None:
            if key in presence: require(presence[key] in (False, None), 'receipt')
            continue
        require(obj and type(item) is dict and set(item) == {'type', 'canonical_sha256'}
            and type(item['type']) is str and item['type'] in TYPES and _hash(item['canonical_sha256']), 'receipt')
        present_count += 1
        if key in presence: require(presence[key] is True, 'receipt')
    if obj:
        require(type(value['object_key_count']) is int and present_count <= value['object_key_count'] <= MAX_KEYS
            and type(value['unexpected_key_count']) is int
            and value['unexpected_key_count'] == value['object_key_count'] - sum(presence.values()), 'receipt')
    else:
        require(value['object_key_count'] is value['unexpected_key_count'] is None
            and all(item is None for item in known.values()), 'receipt')
    for key in ('size_shape', 'modified_shape'):
        require((value[key] is None) is (known['size' if key == 'size_shape' else 'modified'] is None), 'receipt')
    if value['size_shape'] is not None:
        item = value['size_shape']
        require(type(item) is dict and set(item) == {'type', 'classification',
            'positive_integer_value', 'decimal_string_digit_count'} and item['type'] == known['size']['type']
            and type(item['classification']) is str and item['classification'] in TYPES | {
                'positive_in_range', 'zero', 'negative', 'integer_out_of_range', 'integral_number',
                'fractional_number', 'unsigned_decimal_string', 'other_string'}, 'receipt')
        positive, digits = item['positive_integer_value'], item['decimal_string_digit_count']
        allowed = {'integer': {'positive_in_range', 'zero', 'negative', 'integer_out_of_range'},
            'number': {'integral_number', 'fractional_number'},
            'string': {'unsigned_decimal_string', 'other_string'}}
        require(item['classification'] in allowed.get(item['type'], {item['type']}), 'receipt')
        require((type(positive) is int and 0 < positive < 2**63) if item['classification'] == 'positive_in_range'
            else positive is None, 'receipt')
        require((type(digits) is int and 1 <= digits <= MAX_BODY) if item['classification'] == 'unsigned_decimal_string'
            else digits is None, 'receipt')
    if value['modified_shape'] is not None:
        item = value['modified_shape']
        require(type(item) is dict and set(item) == {'type', 'classification', 'ASCII',
            'nonempty_max40', 'timezone_aware'} and item['type'] == known['modified']['type']
            and item['classification'] in ('not_string', 'empty', 'non_ASCII', 'ISO_date_only',
                'ISO_aware', 'ISO_naive', 'RFC_aware', 'RFC_naive', 'unrecognized'), 'receipt')
        string = item['type'] == 'string'
        require(all(type(item[key]) is bool if string else item[key] is None for key in ('ASCII', 'nonempty_max40'))
            and (type(item['timezone_aware']) is bool if item['classification'].startswith(('ISO_', 'RFC_'))
                else item['timezone_aware'] is None), 'receipt')
        require((item['classification'] != 'not_string') is string, 'receipt')
        if item['classification'] in ('ISO_aware', 'RFC_aware'):
            require(item['timezone_aware'] is True and item['ASCII'] is True, 'receipt')
        elif item['classification'] in ('ISO_naive', 'ISO_date_only', 'RFC_naive'):
            require(item['timezone_aware'] is False and item['ASCII'] is True, 'receipt')
        elif item['classification'] == 'non_ASCII':
            require(item['ASCII'] is False, 'receipt')
        elif item['classification'] == 'empty':
            require(item['ASCII'] is True and item['nonempty_max40'] is False, 'receipt')
    predicates = value['contract_predicates']
    require(type(predicates) is dict and set(predicates) == set(PREDICATES)
        and all(type(item) is bool or item is None for item in predicates.values())
        and predicates['body_valid_json'] is parsed
        and predicates['top_object'] is (obj if parsed else None)
        and value['legacy_contract_accepted'] is all(item is True for item in predicates.values())
        and value['failed_predicates'] == sorted(key for key, item in predicates.items() if item is not True), 'receipt')
    if obj:
        require(all(type(item) is bool for item in predicates.values())
            and predicates['keys_exact'] is (value['object_key_count'] == len(EXPECTED_KEYS)
                and value['unexpected_key_count'] == 0 and all(presence.values())), 'receipt')
        for field, expected, predicate in (('table', 'stocks', 'table_equals_stocks'),
                ('name', 'stocks.csv.zip', 'name_equals_stocks_zip')):
            matching = known[field] is not None and known[field]['type'] == 'string' \
                and known[field]['canonical_sha256'] == sha(canonical(expected))
            require(predicates[predicate] is matching, 'receipt')
        size, modified = value['size_shape'], value['modified_shape']
        positive = size is not None and size['type'] == 'integer' and size['classification'] == 'positive_in_range'
        require(predicates['size_positive_nonbool_integer_lt_2pow63'] is positive
            and (not positive or known['size']['canonical_sha256'] == sha(canonical(size['positive_integer_value'])))
            and predicates['modified_ISO_aware'] is (modified is not None and modified['classification'] == 'ISO_aware')
            and predicates['modified_ASCII_nonempty_max40'] is (modified is not None
                and modified['type'] == 'string' and modified['ASCII'] and modified['nonempty_max40']), 'receipt')
        if known['sizeLabel'] is None or known['sizeLabel']['type'] != 'string':
            require(predicates['size_label_ASCII_nonempty_max64_without_low_controls'] is False, 'receipt')
    else:
        require(all(predicates[key] is None for key in PREDICATES if key not in ('body_valid_json', 'top_object')), 'receipt')
    lexical = value['error_lexical_inferences']
    require(type(lexical) is dict and set(lexical) == set(LEXICAL)
        and all(type(item) is bool for item in lexical.values())
        and (obj or not any(lexical.values())), 'receipt')
    require(len(canonical(value)) <= 32768, 'receipt')
    return json.loads(canonical(value))


def validate_capture(receipt, raw, *, api_key):
    checked = validate_receipt(receipt)
    require(canonical(checked) == canonical(inspect_body(raw, api_key=api_key)), 'receipt')
    return checked
