"""Pure bulk-status compatibility including an opaque provider key field.

The retained current shape adds one opaque key to each advertised history.
Keys are checked only as bounded metadata and represented by hash/length;
they are never used as a URL, path, file selection or download capability.
No request, filesystem, credential lookup or source-admission authority.
"""
from __future__ import annotations

import json

from scripts import arv2_r298_sharadar_bulk_status as frozen

SCHEMA = 'arv2-r298-sharadar-bulk-status-v2'
FROZEN_BASE_SOURCE_SHA256 = 'c58567e66c9f1002612adfcc120f1aef9415fc5a3af7d7520c1cdf613c8daee9'
MAX_BODY, MAX_FILES, MAX_KEY_BYTES = frozen.MAX_BODY, 3, 256
TABLES, HISTORIES = frozen.TABLES, frozen.HISTORIES
HISTORY_LABELS = dict(frozen.HISTORY_LABELS)
FLAT_KEYS, ENVELOPE_KEYS, FILE_KEYS = frozen.FLAT_KEYS, frozen.ENVELOPE_KEYS, frozen.FILE_KEYS
KEYED_FILE_KEYS = FILE_KEYS | {'key'}
KEY_FIELDS = frozenset(('opaque_key_present', 'opaque_key_UTF8_bytes', 'opaque_key_sha256'))
NORMAL_KEYS = frozen.NORMAL_KEYS | KEY_FIELDS
SOURCE_KINDS = ('legacy_flat', 'history_files', 'history_files_keyed')
FALSE_FLAGS = {**frozen.FALSE_FLAGS, 'opaque_key_used_as_URL': False,
    'opaque_key_used_as_path': False, 'download_performed': False}
FINITE = frozen.FINITE | frozenset(('key', 'key_duplicate', 'mixed_file_schema', 'json_type'))
canonical, sha = frozen.canonical, frozen.sha


class Refused(ValueError):
    """Finite metadata refusal, never an opaque key or provider rendering."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def profile_record():
    return {'schema': SCHEMA, 'purpose': 'supplied_bulk_status_key_compatibility_not_price_admission',
        'frozen_base_source_sha256': FROZEN_BASE_SOURCE_SHA256,
        'frozen_base_profile_sha256': sha(canonical(frozen.profile_record())),
        'tables': list(TABLES), 'histories': list(HISTORIES),
        'maximum_body_bytes': MAX_BODY, 'maximum_files': MAX_FILES,
        'flat_keys': sorted(FLAT_KEYS), 'history_envelope_keys': sorted(ENVELOPE_KEYS),
        'history_file_keys': sorted(FILE_KEYS), 'keyed_history_file_keys': sorted(KEYED_FILE_KEYS),
        'mixed_keyed_unkeyed_file_records': 'refuse_inconsistent_envelope_version',
        'opaque_key': '1_to_256_visible_ASCII_bytes_no_normalization_hash_and_length_only',
        'opaque_key_semantics': 'not_interpreted_as_URI_path_object_route_or_capability',
        'opaque_key_relation_to_basename_or_history': 'not_invented_or_inferred',
        'duplicate_histories_names_or_present_keys': 'refuse',
        'flat_history': 'full', 'flat_availability': 'unknown_never_true',
        'every_file_validated': True, 'file_order': 'fixed_5y_10y_full_not_selection',
        'credential_scan': 'unchanged_v1_registered_raw_and_decoded_encodings_before_any_hash',
        'unpaired_Unicode_surrogates': 'refuse_before_retention_or_hash',
        'body_handling': 'supplied_exact_bytes_only_no_persistence_or_disclosure',
        'opaque_key_is_not_download_authority': True,
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}


def _base(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except frozen.Refused as error:
        code = frozen.finite(error)
        raise Refused(code if code in FINITE else 'unknown') from None


def _decode(raw, api_key):
    value = _base(frozen._decode, raw, api_key)
    # V1 already checks duplicates, depth/nodes, finite numbers, and registered
    # raw/decoded secret representations. Add strict Unicode encodability to
    # every decoded key/value before any metadata hash or optional retention.
    for text in frozen.frozen._strings(value):
        try:
            text.encode('utf-8', errors='strict')
        except UnicodeError:
            raise Refused('json_type') from None
    return value


def safe_body(raw, *, api_key):
    """Return exact bounded secret-checked JSON bytes, no semantic admission."""
    _decode(raw, api_key)
    return raw


def _key(value):
    require(type(value) is str and 0 < len(value) <= MAX_KEY_BYTES
        and value.isascii() and all(33 <= ord(char) < 127 for char in value), 'key')
    return {'opaque_key_present': True, 'opaque_key_UTF8_bytes': len(value),
        'opaque_key_sha256': sha(canonical(value))}


def _file(value, table, *, flat):
    require(type(value) is dict and set(value) in
        ((FLAT_KEYS,) if flat else (FILE_KEYS, KEYED_FILE_KEYS)), 'file')
    present = not flat and 'key' in value
    key = _key(value['key']) if present else {'opaque_key_present': False,
        'opaque_key_UTF8_bytes': None, 'opaque_key_sha256': None}
    base = {name: value[name] for name in (FLAT_KEYS if flat else FILE_KEYS)}
    return {**_base(frozen._file, base, table, flat=flat), **key}


def inspect_body(raw, *, api_key, table):
    """Validate all advertised metadata without choosing or acquiring a file."""
    value = _decode(raw, api_key)
    require(type(table) is str and table in TABLES, 'table')
    require(type(value) is dict and type(value.get('table')) is str
        and value['table'] == table, 'table')
    if set(value) == FLAT_KEYS:
        kind, files = 'legacy_flat', [_file(value, table, flat=True)]
    else:
        require(set(value) == ENVELOPE_KEYS and type(value['files']) is list
            and 0 < len(value['files']) <= MAX_FILES, 'shape')
        entries = value['files']
        require(all(type(item) is dict and set(item) in (FILE_KEYS, KEYED_FILE_KEYS)
            for item in entries), 'file')
        keyed = {'key' in item for item in entries}
        require(len(keyed) == 1, 'mixed_file_schema')
        kind = 'history_files_keyed' if True in keyed else 'history_files'
        if kind == 'history_files_keyed':
            require(all(type(item['key']) is str for item in entries), 'key')
            require(len({item['key'] for item in entries}) == len(entries), 'key_duplicate')
        files = [_file(item, table, flat=False) for item in entries]
    require(len({item['history'] for item in files}) == len(files)
        and len({item['name'] for item in files}) == len(files), 'history')
    files.sort(key=lambda item: HISTORIES.index(item['history']))
    return validate_receipt({'schema': SCHEMA,
        'status': 'supplied_bulk_status_v2_validated_not_price_admission',
        'table': table, 'source_kind': kind, 'body_byte_count': len(raw), 'body_sha256': sha(raw),
        'profile_sha256': sha(canonical(profile_record())), 'files': files,
        'files_sha256': sha(canonical(files)), 'credential_absence_authenticated': True,
        'availability_is_not_entitlement': True, 'opaque_key_is_not_download_authority': True,
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS})


def validate_receipt(value):
    """Check closed redacted structure; validate_capture additionally binds raw facts."""
    fixed = {'schema': SCHEMA, 'status': 'supplied_bulk_status_v2_validated_not_price_admission',
        'profile_sha256': sha(canonical(profile_record())),
        'credential_absence_authenticated': True, 'availability_is_not_entitlement': True,
        'opaque_key_is_not_download_authority': True,
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}
    variable = {'table', 'source_kind', 'body_byte_count', 'body_sha256', 'files', 'files_sha256'}
    require(type(value) is dict and set(value) == set(fixed) | variable
        and all(type(value[key]) is type(item) and value[key] == item for key, item in fixed.items()), 'receipt')
    require(type(value['table']) is str and value['table'] in TABLES
        and type(value['source_kind']) is str and value['source_kind'] in SOURCE_KINDS
        and type(value['body_byte_count']) is int and 0 < value['body_byte_count'] <= MAX_BODY
        and frozen._hash(value['body_sha256']) and frozen._hash(value['files_sha256'])
        and type(value['files']) is list and 0 < len(value['files']) <= MAX_FILES, 'receipt')
    files, table, kind = value['files'], value['table'], value['source_kind']
    histories, keys = [], []
    for item in files:
        require(type(item) is dict and set(item) == NORMAL_KEYS
            and type(item['history']) is str and item['history'] in HISTORIES, 'receipt')
        history = item['history']
        require(type(item['name']) is str and item['name'] == frozen._name(table, history)
            and type(item['size']) is int and 0 < item['size'] < 2**63
            and frozen._hash(item['size_label_sha256']) and frozen._hash(item['modified_sha256']), 'receipt')
        require((kind == 'legacy_flat' and item['available'] is None)
            or (kind != 'legacy_flat' and type(item['available']) is bool), 'receipt')
        require(type(item['opaque_key_present']) is bool
            and item['opaque_key_present'] is (kind == 'history_files_keyed'), 'receipt')
        if item['opaque_key_present']:
            require(type(item['opaque_key_UTF8_bytes']) is int
                and 0 < item['opaque_key_UTF8_bytes'] <= MAX_KEY_BYTES
                and frozen._hash(item['opaque_key_sha256']), 'receipt')
            keys.append(item['opaque_key_sha256'])
        else:
            require(item['opaque_key_UTF8_bytes'] is item['opaque_key_sha256'] is None, 'receipt')
        histories.append(history)
    require(len(histories) == len(set(histories)) and histories == sorted(histories, key=HISTORIES.index)
        and (kind != 'legacy_flat' or histories == ['full'])
        and len(keys) == len(set(keys)) and sha(canonical(files)) == value['files_sha256'], 'receipt')
    return json.loads(canonical(value))


def validate_capture(receipt, raw, *, api_key, table):
    expected = inspect_body(raw, api_key=api_key, table=table)
    checked = validate_receipt(receipt)
    require(canonical(checked) == canonical(expected), 'capture')
    return checked
