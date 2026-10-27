"""Offline structural inventory of supplied bounded bulk-status JSON.

No credential is looked up or supplied here. A separate caller must bind the
exact previously checked capture and its provenance. This diagnostic does not
renew the earlier credential scan, accept a file schema, or admit price data.
Unknown key names and arbitrary values are represented only by lengths/hashes.
"""
from __future__ import annotations

from datetime import datetime
import json
import math
import re

from scripts import arv2_r298_sharadar_status_shape as frozen

SCHEMA = 'arv2-r298-sharadar-bulk-fields-v1'
FROZEN_JSON_SOURCE_SHA256 = '5ed5da0208aae8b18580b2a1569b5fab9df5fd49c3dee3ccf2bda208c1b5f5cb'
MAX_BODY, MAX_FILES = 8192, 3
TOP_FIELDS = ('table', 'files', 'error')
FILE_FIELDS = ('history', 'historyLabel', 'name', 'size', 'sizeLabel', 'modified',
    'available', 'key', 'table', 'years', 'canDownload', 'path', 'filename', 'lastModified')
HISTORIES, TABLES = ('5y', '10y', 'full'), ('stocks', 'funds')
HISTORY_LABELS = {'5y': '5 Years', '10y': '10 Years', 'full': 'Full History'}
NAMES = {table + '_' + history: table + {'5y': '-5Y', '10y': '-10Y', 'full': ''}[history]
    + '.csv.zip' for table in TABLES for history in HISTORIES}
TYPES = frozenset(('object', 'list', 'string', 'integer', 'number', 'boolean', 'null'))
MODIFIED_CLASSES = frozenset(('missing', 'not_string', 'empty', 'non_ASCII', 'too_long',
    'ISO_aware', 'ISO_naive', 'ISO_date_only', 'invalid_ISO', 'other_format'))
FALSE_FLAGS = {'provider_contact': False, 'qc_contact': False,
    'credential_absence_authenticated': False, 'credential_scan_reperformed': False,
    'raw_strings_disclosed': False, 'file_schema_accepted': False,
    'entitlement_proven': False, 'paid_tier_proven': False,
    'subscription_expiry_proven': False, 'source_identity_admitted': False,
    'price_input_admitted': False, 'common_price_package_admitted': False,
    'strategy_nav_admitted': False, 'strategy_result_accepted': False,
    'historical_completeness_proven': False, 'formal_identity_admitted': False,
    'point_in_time_proven': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False}
FINITE = frozenset(('body', 'json', 'json_duplicate', 'json_nonfinite', 'json_bound',
    'json_type', 'files', 'receipt', 'capture', 'unknown'))
canonical, sha = frozen.canonical, frozen.sha


class Refused(ValueError):
    """Finite diagnostic refusal, never a provider value."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def profile_record():
    return {'schema': SCHEMA, 'purpose': 'offline_supplied_bulk_fields_not_schema_or_price_admission',
        'frozen_JSON_source_sha256': FROZEN_JSON_SOURCE_SHA256,
        'maximum_body_bytes': MAX_BODY, 'maximum_files': MAX_FILES,
        'maximum_JSON_depth': frozen.MAX_DEPTH, 'maximum_JSON_nodes': frozen.MAX_NODES,
        'maximum_object_keys': frozen.MAX_KEYS, 'top_field_inventory': list(TOP_FIELDS),
        'file_field_inventory': list(FILE_FIELDS), 'history_enums': list(HISTORIES),
        'table_enums': list(TABLES), 'history_labels': dict(HISTORY_LABELS),
        'public_basenames': dict(NAMES),
        'unknown_names_and_arbitrary_values': 'canonical_hashes_and_lengths_only',
        'all_file_entries': 'inventory_without_schema_acceptance_or_first_entry_selection',
        'credential_provenance': 'external_exact_capture_pin_not_a_new_secret_scan',
        'timestamps': 'finite_ISO_classes_no_raw_time',
        'receipt_crosschecks': 'known_string_digest_lengths_and_unknown_key_digest_disjointness',
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}


def _type(value):
    return frozen._type(value)


def _scan(value):
    pending, nodes = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        require(nodes <= frozen.MAX_NODES and depth <= frozen.MAX_DEPTH, 'json_bound')
        kind = type(item)
        require(_type(item) is not None, 'json_type')
        if kind is str:
            try:
                item.encode('utf-8', errors='strict')
            except UnicodeError:
                raise Refused('json_type') from None
        elif kind is dict:
            require(len(item) <= frozen.MAX_KEYS, 'json_bound')
            pending.extend((child, depth + 1) for pair in item.items() for child in pair)
        elif kind is list:
            pending.extend((child, depth + 1) for child in item)
        elif kind is float:
            require(math.isfinite(item), 'json_nonfinite')


def _decode(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY, 'body')
    try:
        value = json.loads(raw.decode('utf-8-sig', errors='strict'),
            object_pairs_hook=frozen._pairs, parse_constant=frozen._constant)
    except frozen.Refused as error:
        code = frozen.finite(error)
        raise Refused(code if code in FINITE else 'json') from None
    except RecursionError:
        raise Refused('json_bound') from None
    except (ValueError, UnicodeError):
        raise Refused('json') from None
    _scan(value)
    return value


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _summary(value):
    return {'type': _type(value), 'canonical_sha256': sha(canonical(value)),
        'string_UTF8_bytes': len(value.encode('utf-8')) if type(value) is str else None}


def _unknown(value, fields):
    result = [{'canonical_sha256': sha(canonical(key)), 'string_UTF8_bytes': len(key.encode('utf-8'))}
        for key in value if key not in fields]
    result.sort(key=lambda item: item['canonical_sha256'])
    return result


def _enum(value, values):
    return value if type(value) is str and value in values else None


def _modified(value, present):
    if not present:
        return 'missing'
    if type(value) is not str:
        return 'not_string'
    if not value:
        return 'empty'
    if not value.isascii():
        return 'non_ASCII'
    if len(value) > 40:
        return 'too_long'
    date_only = re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) is not None
    naive = re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?', value) is not None
    aware = re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})', value) is not None
    if not (date_only or naive or aware):
        return 'other_format'
    if aware and not value.endswith('Z') and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        return 'invalid_ISO'
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, OverflowError):
        return 'invalid_ISO'
    if date_only:
        return 'ISO_date_only'
    return 'ISO_aware' if parsed.tzinfo is not None and parsed.utcoffset() is not None else 'ISO_naive'


def _inventory(value, fields):
    obj = type(value) is dict
    return {'type': _type(value), 'object_key_count': len(value) if obj else None,
        'keyset_sha256': sha(canonical(sorted(value))) if obj else None,
        'fields': {key: _summary(value[key]) if obj and key in value else None for key in fields},
        'unknown_keys': _unknown(value, fields) if obj else []}


def _file(value, index):
    obj = value if type(value) is dict else {}
    history, label, name, table = (obj.get(key) for key in ('history', 'historyLabel', 'name', 'table'))
    available, size = obj.get('available'), obj.get('size')
    return {'index': index, **_inventory(value, FILE_FIELDS),
        'history_enum': _enum(history, HISTORIES), 'table_enum': _enum(table, TABLES),
        'history_equals': {key: type(history) is str and history == key for key in HISTORIES},
        'history_label_equals': {key: type(label) is str and label == item for key, item in HISTORY_LABELS.items()},
        'name_equals': {key: type(name) is str and name == item for key, item in NAMES.items()},
        'available_boolean_value': available if type(available) is bool else None,
        'size_positive_integer': size if type(size) is int and 0 < size < 2**63 else None,
        'modified_classes': {key: _modified(obj.get(key), key in obj) for key in ('modified', 'lastModified')}}


def inspect_body(raw):
    """Inspect supplied strict JSON without any new credential/authenticity claim."""
    value = _decode(raw)
    obj = value if type(value) is dict else {}
    files = obj.get('files')
    require(type(files) is not list or len(files) <= MAX_FILES, 'files')
    return validate_receipt({'schema': SCHEMA, 'status': 'supplied_bulk_fields_observed',
        'profile_sha256': sha(canonical(profile_record())), 'body_byte_count': len(raw), 'body_sha256': sha(raw),
        'top': _inventory(value, TOP_FIELDS), 'table_enum': _enum(obj.get('table'), TABLES),
        'files_count': len(files) if type(files) is list else None,
        'files': [_file(item, index) for index, item in enumerate(files)] if type(files) is list else [],
        'inventory_is_not_schema_acceptance': True, 'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS})


def _validate_summary(value):
    require(type(value) is dict and set(value) == {'type', 'canonical_sha256', 'string_UTF8_bytes'}
        and type(value['type']) is str and value['type'] in TYPES and _hash(value['canonical_sha256']), 'receipt')
    require((type(value['string_UTF8_bytes']) is int and 0 <= value['string_UTF8_bytes'] <= MAX_BODY)
        if value['type'] == 'string' else value['string_UTF8_bytes'] is None, 'receipt')
    if value['type'] == 'string':
        digest, length = value['canonical_sha256'], value['string_UTF8_bytes']
        require((length == 0) is (digest == sha(canonical(''))), 'receipt')
        for text in (*HISTORIES, *TABLES, *HISTORY_LABELS.values(), *NAMES.values()):
            if digest == sha(canonical(text)):
                require(length == len(text.encode('utf-8')), 'receipt')
    if value['type'] in ('boolean', 'null'):
        options = (True, False) if value['type'] == 'boolean' else (None,)
        require(value['canonical_sha256'] in {sha(canonical(item)) for item in options}, 'receipt')


def _validate_inventory(value, fields):
    require(type(value) is dict and set(value) == {'type', 'object_key_count', 'keyset_sha256', 'fields', 'unknown_keys'}
        and type(value['type']) is str and value['type'] in TYPES
        and type(value['fields']) is dict and set(value['fields']) == set(fields)
        and type(value['unknown_keys']) is list and len(value['unknown_keys']) <= frozen.MAX_KEYS, 'receipt')
    obj = value['type'] == 'object'
    present = 0
    for item in value['fields'].values():
        if item is not None:
            require(obj, 'receipt')
            _validate_summary(item)
            present += 1
    unknown = value['unknown_keys']
    hashes = []
    known_hashes = {sha(canonical(name)) for name in fields}
    for item in unknown:
        require(obj and type(item) is dict and set(item) == {'canonical_sha256', 'string_UTF8_bytes'}
            and _hash(item['canonical_sha256']) and type(item['string_UTF8_bytes']) is int
            and 0 <= item['string_UTF8_bytes'] <= MAX_BODY
            and item['canonical_sha256'] not in known_hashes, 'receipt')
        hashes.append(item['canonical_sha256'])
    require(hashes == sorted(hashes) and len(hashes) == len(set(hashes)), 'receipt')
    if obj:
        require(type(value['object_key_count']) is int and value['object_key_count'] == present + len(unknown)
            and value['object_key_count'] <= frozen.MAX_KEYS and _hash(value['keyset_sha256']), 'receipt')
        if not unknown:
            require(value['keyset_sha256'] == sha(canonical(sorted(key for key, item in value['fields'].items()
                if item is not None))), 'receipt')
    else:
        require(value['object_key_count'] is value['keyset_sha256'] is None and not unknown, 'receipt')


def _matches(summary, value):
    return summary is not None and summary['type'] == 'string' and summary['canonical_sha256'] == sha(canonical(value))


def validate_receipt(value):
    """Check closed redacted structure; only validate_capture binds raw facts.

    Arbitrary string/collection hashes are intentionally opaque. This check
    cannot reconstruct their values or prove a timestamp classification from
    a digest; a separately authenticated caller must retain the exact-byte
    binding, and validate_capture recomputes every observation when supplied.
    """
    fixed = {'schema': SCHEMA, 'status': 'supplied_bulk_fields_observed',
        'profile_sha256': sha(canonical(profile_record())), 'inventory_is_not_schema_acceptance': True,
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}
    variable = {'body_byte_count', 'body_sha256', 'top', 'table_enum', 'files_count', 'files'}
    require(type(value) is dict and set(value) == set(fixed) | variable
        and all(type(value[key]) is type(item) and value[key] == item for key, item in fixed.items()), 'receipt')
    require(type(value['body_byte_count']) is int and 0 < value['body_byte_count'] <= MAX_BODY
        and _hash(value['body_sha256']) and type(value['files']) is list and len(value['files']) <= MAX_FILES, 'receipt')
    _validate_inventory(value['top'], TOP_FIELDS)
    top = value['top']['fields']
    table = next((item for item in TABLES if _matches(top['table'], item)), None)
    require(type(value['table_enum']) is type(table) and value['table_enum'] == table, 'receipt')
    is_list = top['files'] is not None and top['files']['type'] == 'list'
    require((type(value['files_count']) is int and value['files_count'] == len(value['files'])) if is_list
        else value['files_count'] is None and not value['files'], 'receipt')
    keys = {'index', 'type', 'object_key_count', 'keyset_sha256', 'fields', 'unknown_keys',
        'history_enum', 'table_enum', 'history_equals', 'history_label_equals', 'name_equals',
        'available_boolean_value', 'size_positive_integer', 'modified_classes'}
    for index, item in enumerate(value['files']):
        require(type(item) is dict and set(item) == keys and type(item['index']) is int and item['index'] == index, 'receipt')
        _validate_inventory({key: item[key] for key in ('type', 'object_key_count', 'keyset_sha256', 'fields', 'unknown_keys')}, FILE_FIELDS)
        fields = item['fields']
        for map_key, field, options in (('history_equals', 'history', dict.fromkeys(HISTORIES)),
                ('history_label_equals', 'historyLabel', HISTORY_LABELS), ('name_equals', 'name', NAMES)):
            expected = {key: _matches(fields[field], key if map_key == 'history_equals' else candidate)
                for key, candidate in options.items()}
            require(type(item[map_key]) is dict and set(item[map_key]) == set(expected)
                and all(type(item[map_key][key]) is bool and item[map_key][key] is result
                    for key, result in expected.items()), 'receipt')
        for field, options in (('history', HISTORIES), ('table', TABLES)):
            expected = next((candidate for candidate in options if _matches(fields[field], candidate)), None)
            require(type(item[field + '_enum']) is type(expected) and item[field + '_enum'] == expected, 'receipt')
        available = item['available_boolean_value']
        if fields['available'] is not None and fields['available']['type'] == 'boolean':
            require(type(available) is bool and fields['available']['canonical_sha256'] == sha(canonical(available)), 'receipt')
        else:
            require(available is None, 'receipt')
        size = item['size_positive_integer']
        require(size is None or (type(size) is int and 0 < size < 2**63 and fields['size'] is not None
            and fields['size']['type'] == 'integer' and fields['size']['canonical_sha256'] == sha(canonical(size))), 'receipt')
        classes = item['modified_classes']
        require(type(classes) is dict and set(classes) == {'modified', 'lastModified'}, 'receipt')
        for field, classification in classes.items():
            require(type(classification) is str and classification in MODIFIED_CLASSES, 'receipt')
            summary = fields[field]
            require((classification == 'missing') is (summary is None), 'receipt')
            if summary is not None:
                require((classification == 'not_string') is (summary['type'] != 'string'), 'receipt')
                if classification == 'empty':
                    require(summary['string_UTF8_bytes'] == 0, 'receipt')
    require(len(canonical(value)) <= 32768, 'receipt')
    return json.loads(canonical(value))


def validate_capture(receipt, raw):
    checked = validate_receipt(receipt)
    require(canonical(checked) == canonical(inspect_body(raw)), 'capture')
    return checked
