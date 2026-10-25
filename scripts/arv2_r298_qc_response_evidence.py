"""Pure bounded QC response projection; no transport or operational authority.

Invoke at a separately authorized response boundary, before a client discards
failure bodies. Only finite shapes, lengths, digests and two exact public text
patterns leave this module. Patterns do not authenticate causes. This cannot
recover A6's discarded reason or determine a write's effect.
"""
from __future__ import annotations

import hashlib
import json
import math
import re


SCHEMA = 'arv2-r298-qc-response-evidence-v1'
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_PARSE_BYTES = 64 * 1024
MAX_DEPTH = 32
MAX_NODES = 4096
MAX_ITEMS = 32
JSON_TYPES = ('null', 'boolean', 'number', 'string', 'array', 'object')
OUTCOMES = ('empty_body', 'parse_bound', 'invalid_utf8', 'invalid_json',
    'duplicate_keys', 'nonfinite_number', 'depth_bound', 'node_bound',
    'invalid_unicode', 'object', 'non_object')
FINITE_CODES = frozenset(('http_status', 'raw_type', 'raw_bound', 'evidence_shape'))
FIELDS = ('success', 'errors', 'messages', 'Message')
PATTERNS = {
    "Hash doesn't match.": 'hash_does_not_match_exact_literal',
    'UserID not valid': 'user_id_not_valid_exact_literal',
}
FALSE_FLAGS = ('remote_effect_known', 'response_provenance_authenticated',
    'provider_reason_is_root_cause', 'retry_authority')
PROFILE = {
    'schema': SCHEMA, 'max_response_bytes': MAX_RESPONSE_BYTES,
    'max_parse_bytes': MAX_PARSE_BYTES, 'max_depth': MAX_DEPTH,
    'max_nodes': MAX_NODES, 'max_items': MAX_ITEMS,
    'fields': list(FIELDS), 'observed_text_patterns': PATTERNS.copy(),
    'numeric_provider_values_emitted': False, 'unknown_text_emitted': False,
    'pattern_matching': 'exact_full_string', 'false_flags': list(FALSE_FLAGS),
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('ascii')


PROFILE_SHA256 = _sha(_encode(PROFILE))


class EvidenceError(ValueError):
    """A constant-safe local input/validation refusal, never response text."""

    def __init__(self, code):
        super().__init__(code if type(code) is str and code in FINITE_CODES
            else 'evidence_shape')


class _ParseRefused(ValueError):
    pass


def _require(value, code='evidence_shape'):
    if not value:
        raise EvidenceError(code)


def finite_error(error):
    if type(error) is EvidenceError:
        args = BaseException.args.__get__(error)
        if len(args) == 1 and type(args[0]) is str and args[0] in FINITE_CODES:
            return {'code': args[0]}
    return {'code': 'evidence_shape'}


def _kind(value):
    return {type(None): 'null', bool: 'boolean', int: 'number', float: 'number',
        str: 'string', list: 'array', dict: 'object'}[type(value)]


def _depth_scan(text):
    # Limit nesting before Python's recursive JSON decoder allocates it. Quotes
    # and escapes are counted lexically only; json.loads still validates syntax.
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > MAX_DEPTH:
                raise _ParseRefused('depth_bound')
        elif char in ']}':
            depth -= 1


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _ParseRefused('duplicate_keys')
        result[key] = value
    return result


def _constant(_value):
    raise _ParseRefused('nonfinite_number')


def _float(value):
    result = float(value)
    if not math.isfinite(result):
        raise _ParseRefused('nonfinite_number')
    return result


def _validate_tree(value):
    pending, visited = [(value, 0)], 0
    while pending:
        current, depth = pending.pop()
        visited += 1
        if visited > MAX_NODES:
            raise _ParseRefused('node_bound')
        if depth > MAX_DEPTH:
            raise _ParseRefused('depth_bound')
        kind = type(current)
        if kind is dict:
            if any(type(key) is not str for key in current):
                raise _ParseRefused('invalid_json')
            if len(current) * 2 > MAX_NODES - visited - len(pending):
                raise _ParseRefused('node_bound')
            pending.extend((item, depth + 1) for pair in current.items() for item in pair)
        elif kind is list:
            if len(current) > MAX_NODES - visited - len(pending):
                raise _ParseRefused('node_bound')
            pending.extend((item, depth + 1) for item in current)
        elif kind is str:
            try:
                current.encode('utf-8')
            except UnicodeEncodeError:
                raise _ParseRefused('invalid_unicode') from None
        elif kind is float:
            if not math.isfinite(current):
                raise _ParseRefused('nonfinite_number')
        elif kind not in (type(None), bool, int):
            raise _ParseRefused('invalid_json')


def _item(value):
    raw = value.encode('utf-8') if type(value) is str else None
    return {'json_type': _kind(value),
        'string_utf8_byte_count': len(raw) if raw is not None else None,
        'string_sha256': _sha(raw) if raw is not None else None,
        'observed_text_pattern': PATTERNS.get(value, 'unknown')
            if type(value) is str else None}


def _field(packet, key):
    present = key in packet
    value = packet.get(key)
    kind = _kind(value) if present else 'absent'
    if key == 'success':
        return {'present': present, 'json_type': kind,
            'boolean_value': value if type(value) is bool else None}
    selected = value[:MAX_ITEMS] if type(value) is list else [value] if present else []
    return {'present': present, 'json_type': kind,
        'count': len(value) if type(value) in (dict, list) else None,
        'items': [_item(item) for item in selected],
        'omitted_count': max(0, len(value) - MAX_ITEMS) if type(value) is list else 0}


def project_response(status, raw):
    """Project supplied bytes; their transport/provenance remains external.

    Bodies above the parse limit are hashed in full but NOT partially parsed.
    Invalid syntax/type/bounds never interpolate exception or provider text.
    A returned object is a fresh mutable snapshot, not a signed/authenticated
    record; any future caller must validate/snapshot before durable publication.
    """
    _require(type(status) is int and 100 <= status <= 599, 'http_status')
    _require(type(raw) is bytes, 'raw_type')
    _require(len(raw) <= MAX_RESPONSE_BYTES, 'raw_bound')
    result = {'schema': SCHEMA, 'profile_sha256': PROFILE_SHA256,
        'http_status': status, 'body_byte_count': len(raw), 'body_sha256': _sha(raw),
        'outcome': 'empty_body', 'root_type': None,
        'fields': dict.fromkeys(FIELDS), 'provider_request_count': None,
        **dict.fromkeys(FALSE_FLAGS, False)}
    if len(raw) > MAX_PARSE_BYTES:
        result['outcome'] = 'parse_bound'
    elif raw:
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            result['outcome'] = 'invalid_utf8'
        else:
            try:
                _depth_scan(text)
                # The 64KiB byte cap is the allocation bound before decoding;
                # the node budget is checked on the allocated bounded tree.
                packet = json.loads(text, object_pairs_hook=_pairs,
                    parse_constant=_constant, parse_float=_float)
                _validate_tree(packet)
            except _ParseRefused as error:
                result['outcome'] = error.args[0]
            except (json.JSONDecodeError, ValueError, RecursionError, OverflowError):
                result['outcome'] = 'invalid_json'
            else:
                result['root_type'] = _kind(packet)
                result['outcome'] = 'object' if type(packet) is dict else 'non_object'
                if type(packet) is dict:
                    result['fields'] = {key: _field(packet, key) for key in FIELDS}
    validate_evidence(result)
    return result


def _keys(value, keys):
    _require(type(value) is dict and set(value) == set(keys))


def _nat(value, maximum):
    return type(value) is int and 0 <= value <= maximum


def _digest(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _validate_item(value):
    _keys(value, ('json_type', 'string_utf8_byte_count', 'string_sha256',
        'observed_text_pattern'))
    kind = value['json_type']
    _require(type(kind) is str and kind in JSON_TYPES)
    if kind == 'string':
        size, digest, pattern = (value[key] for key in (
            'string_utf8_byte_count', 'string_sha256', 'observed_text_pattern'))
        _require(_nat(size, MAX_PARSE_BYTES) and _digest(digest))
        _require(type(pattern) is str and pattern in ('unknown', *PATTERNS.values()))
        for literal, label in PATTERNS.items():
            matches = size == len(literal.encode('utf-8')) and digest == _sha(literal.encode('utf-8'))
            _require((pattern == label) == matches)
        if size == 0:
            _require(digest == _sha(b''))
    else:
        _require(all(value[key] is None for key in (
            'string_utf8_byte_count', 'string_sha256', 'observed_text_pattern')))


def _validate_field(value, key):
    expected = ('present', 'json_type', 'boolean_value') if key == 'success' else (
        'present', 'json_type', 'count', 'items', 'omitted_count')
    _keys(value, expected)
    present, kind = value['present'], value['json_type']
    _require(type(present) is bool and type(kind) is str
        and kind in ('absent', *JSON_TYPES) and present == (kind != 'absent'))
    if key == 'success':
        _require(type(value['boolean_value']) is bool if kind == 'boolean'
            else value['boolean_value'] is None)
        return
    items, count, omitted = value['items'], value['count'], value['omitted_count']
    _require(type(items) is list and len(items) <= MAX_ITEMS
        and _nat(omitted, MAX_NODES))
    for item in items:
        _validate_item(item)
    if kind in ('array', 'object'):
        _require(_nat(count, MAX_NODES))
    else:
        _require(count is None)
    if kind == 'array':
        _require(len(items) == min(count, MAX_ITEMS) and omitted == max(0, count - MAX_ITEMS))
    else:
        _require(omitted == 0 and len(items) == (1 if present else 0))
        if items:
            _require(items[0]['json_type'] == kind)


def validate_evidence(value):
    """Validate only the finite projection's shape/coherence, not its truth."""
    try:
        _validate_tree(value)
    except _ParseRefused:
        raise EvidenceError('evidence_shape') from None
    _keys(value, ('schema', 'profile_sha256', 'http_status', 'body_byte_count',
        'body_sha256', 'outcome', 'root_type', 'fields', 'provider_request_count',
        *FALSE_FLAGS))
    _require(value['schema'] == SCHEMA and value['profile_sha256'] == PROFILE_SHA256)
    _require(type(value['http_status']) is int and 100 <= value['http_status'] <= 599)
    size, outcome, root = value['body_byte_count'], value['outcome'], value['root_type']
    _require(_nat(size, MAX_RESPONSE_BYTES) and _digest(value['body_sha256']))
    _require(type(outcome) is str and outcome in OUTCOMES)
    _require(value['provider_request_count'] is None
        and all(value[key] is False for key in FALSE_FLAGS))
    _keys(value['fields'], FIELDS)
    if outcome == 'empty_body':
        _require(size == 0 and value['body_sha256'] == _sha(b''))
    else:
        _require(size > 0)
    _require((outcome == 'parse_bound') == (size > MAX_PARSE_BYTES))
    if outcome in ('object', 'non_object'):
        _require(type(root) is str and root in JSON_TYPES
            and (outcome == 'object') == (root == 'object'))
    else:
        _require(root is None)
    if outcome == 'object':
        for key in FIELDS:
            _validate_field(value['fields'][key], key)
    else:
        _require(all(item is None for item in value['fields'].values()))
