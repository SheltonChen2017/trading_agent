"""Pure supplied-byte bulk-status compatibility, never source admission.

Accept only the documented flat and history-files envelopes. Every advertised
file is checked; no arbitrary first-file choice or availability inference is
made. This module neither requests nor persists anything. Safe bytes may be
retained privately by a separately frozen caller, not disclosed by receipts.
"""
from __future__ import annotations

from datetime import datetime
import json
import re

from scripts import arv2_r298_sharadar_status_shape as frozen

SCHEMA = 'arv2-r298-sharadar-bulk-status-v1'
FROZEN_SECURITY_SOURCE_SHA256 = '5ed5da0208aae8b18580b2a1569b5fab9df5fd49c3dee3ccf2bda208c1b5f5cb'
MAX_BODY = 8192
TABLES = ('stocks', 'funds')
HISTORIES = ('5y', '10y', 'full')
HISTORY_LABELS = {'5y': '5 Years', '10y': '10 Years', 'full': 'Full History'}
FLAT_KEYS = frozenset(('table', 'name', 'size', 'sizeLabel', 'modified'))
ENVELOPE_KEYS = frozenset(('table', 'files'))
FILE_KEYS = frozenset(('history', 'historyLabel', 'name', 'size', 'sizeLabel', 'modified', 'available'))
NORMAL_KEYS = frozenset(('history', 'name', 'available', 'size', 'size_label_sha256', 'modified_sha256'))
FALSE_FLAGS = {'provider_contact': False, 'qc_contact': False,
    'credential_persisted': False, 'unvalidated_raw_strings_disclosed': False,
    'entitlement_proven': False, 'paid_tier_proven': False,
    'subscription_expiry_proven': False, 'source_identity_admitted': False,
    'price_input_admitted': False, 'common_price_package_admitted': False,
    'strategy_nav_admitted': False, 'strategy_result_accepted': False,
    'historical_completeness_proven': False, 'formal_identity_admitted': False,
    'point_in_time_proven': False, 'formal_forward_ready': False,
    'paper_or_live_ready': False}
FINITE = frozenset(('body', 'credential', 'credential_echo', 'json_duplicate',
    'json_nonfinite', 'json_bound', 'json_type', 'json', 'table', 'shape',
    'file', 'history', 'name', 'size', 'label', 'modified', 'available',
    'receipt', 'capture', 'unknown'))
canonical, sha = frozen.canonical, frozen.sha


class Refused(ValueError):
    """Finite refusal, without provider strings or credentials."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def profile_record():
    return {'schema': SCHEMA, 'purpose': 'supplied_bulk_status_compatibility_not_price_admission',
        'frozen_security_source_sha256': FROZEN_SECURITY_SOURCE_SHA256,
        'tables': list(TABLES), 'histories': list(HISTORIES), 'maximum_body_bytes': MAX_BODY,
        'maximum_files': 3, 'maximum_JSON_depth': frozen.MAX_DEPTH,
        'maximum_JSON_nodes': frozen.MAX_NODES, 'maximum_object_keys': frozen.MAX_KEYS,
        'flat_keys': sorted(FLAT_KEYS), 'history_envelope_keys': sorted(ENVELOPE_KEYS),
        'history_file_keys': sorted(FILE_KEYS), 'history_labels': dict(HISTORY_LABELS),
        'flat_history': 'full', 'flat_availability': 'unknown_never_true',
        'every_file_validated': True, 'duplicate_histories_or_names': 'refuse',
        'file_order': 'fixed_5y_10y_full_not_first_entry_selection',
        'size': 'positive_nonbool_integer_less_than_2pow63',
        'size_label': 'printable_ASCII_trimmed_nonempty_max64_hash_only',
        'modified': 'ASCII_ISO_T_seconds_aware_nonempty_max40_hash_only',
        'credential_scan': 'raw_registered_encodings_and_all_decoded_JSON_keys_strings_before_hash',
        'unknown_fields_or_unsafe_JSON': 'refuse',
        'body_handling': 'supplied_bytes_only_no_persistence_or_disclosure',
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}


def _decode(raw, api_key):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY, 'body')
    try:
        key = frozen.frozen.source._validated_api_key(api_key, synthetic=False)
    except Exception:
        raise Refused('credential') from None
    encodings = frozen.frozen._encodings(key)
    require(not any(token in raw for token in encodings), 'credential_echo')
    try:
        value = json.loads(raw.decode('utf-8-sig', errors='strict'),
            object_pairs_hook=frozen._pairs, parse_constant=frozen._constant)
        frozen._scan(value, key)
    except frozen.Refused as error:
        code = frozen.finite(error)
        raise Refused(code if code in FINITE else 'json') from None
    except RecursionError:
        raise Refused('json_bound') from None
    except (ValueError, UnicodeError):
        raise Refused('json') from None
    # JSON escaping can hide a registered URL/JSON encoding from the raw scan.
    # Check every decoded key and string, including unknown envelope fields.
    needles = tuple(token.decode('ascii') for token in encodings)
    require(not any(needle in text for text in frozen._strings(value) for needle in needles),
        'credential_echo')
    return value


def safe_body(raw, *, api_key):
    """Strict bounded JSON plus complete registered secret scan, no schema claim.

    No hash is computed. A caller may persist the returned exact bytes only
    under its own private retention contract, even when later schema checks
    refuse them. Unknown schemas are deliberately not normalized here.
    """
    _decode(raw, api_key)
    return raw


def _name(table, history):
    suffix = {'5y': '-5Y', '10y': '-10Y', 'full': ''}[history]
    return table + suffix + '.csv.zip'


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _printable(value, maximum):
    return (type(value) is str and 0 < len(value) <= maximum
        and value.isascii() and all(32 <= ord(char) < 127 for char in value))


def _modified(value):
    require(_printable(value, 40) and re.fullmatch(
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})', value)
        is not None, 'modified')
    if not value.endswith('Z'):
        # fromisoformat normalizes out-of-range offset minutes (e.g. +01:99).
        # The supplied lexical offset itself must be a valid bounded ISO one.
        require(int(value[-5:-3]) <= 23 and int(value[-2:]) <= 59, 'modified')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(parsed.tzinfo is not None and parsed.utcoffset() is not None, 'modified')
    except (ValueError, OverflowError):
        raise Refused('modified') from None


def _file(value, table, *, flat):
    require(type(value) is dict and set(value) == (FLAT_KEYS if flat else FILE_KEYS), 'file')
    history = 'full' if flat else value['history']
    require(type(history) is str and history in HISTORIES, 'history')
    if not flat:
        require(type(value['historyLabel']) is str
            and value['historyLabel'] == HISTORY_LABELS[history], 'history')
        require(type(value['available']) is bool, 'available')
    require(type(value['name']) is str and value['name'] == _name(table, history), 'name')
    require(type(value['size']) is int and 0 < value['size'] < 2**63, 'size')
    require(_printable(value['sizeLabel'], 64)
        and value['sizeLabel'] == value['sizeLabel'].strip(), 'label')
    _modified(value['modified'])
    return {'history': history, 'name': _name(table, history),
        'available': None if flat else value['available'], 'size': value['size'],
        'size_label_sha256': sha(canonical(value['sizeLabel'])),
        'modified_sha256': sha(canonical(value['modified']))}


def inspect_body(raw, *, api_key, table):
    """Validate every supplied advertised file; never choose or acquire one."""
    value = _decode(raw, api_key)  # The complete secret scan precedes all hashes.
    require(type(table) is str and table in TABLES, 'table')
    require(type(value) is dict and type(value.get('table')) is str
        and value['table'] == table, 'table')
    if set(value) == FLAT_KEYS:
        kind, files = 'legacy_flat', [_file(value, table, flat=True)]
    else:
        require(set(value) == ENVELOPE_KEYS and type(value['files']) is list
            and 0 < len(value['files']) <= 3, 'shape')
        kind, files = 'history_files', [_file(item, table, flat=False) for item in value['files']]
    require(len({item['history'] for item in files}) == len(files)
        and len({item['name'] for item in files}) == len(files), 'history')
    files.sort(key=lambda item: HISTORIES.index(item['history']))
    return validate_receipt({'schema': SCHEMA,
        'status': 'supplied_bulk_status_validated_not_price_admission',
        'table': table, 'source_kind': kind, 'body_byte_count': len(raw), 'body_sha256': sha(raw),
        'profile_sha256': sha(canonical(profile_record())), 'files': files,
        'files_sha256': sha(canonical(files)), 'credential_absence_authenticated': True,
        'availability_is_not_entitlement': True, 'diagnostic_only': True,
        'result_cell': 0, **FALSE_FLAGS})


def validate_receipt(value):
    """Closed metadata schema; byte authentication additionally needs capture."""
    fixed = {'schema': SCHEMA, 'status': 'supplied_bulk_status_validated_not_price_admission',
        'profile_sha256': sha(canonical(profile_record())),
        'credential_absence_authenticated': True, 'availability_is_not_entitlement': True,
        'diagnostic_only': True, 'result_cell': 0, **FALSE_FLAGS}
    variable = {'table', 'source_kind', 'body_byte_count', 'body_sha256', 'files', 'files_sha256'}
    require(type(value) is dict and set(value) == set(fixed) | variable
        and all(type(value[key]) is type(item) and value[key] == item for key, item in fixed.items()),
        'receipt')
    require(type(value['table']) is str and value['table'] in TABLES
        and type(value['source_kind']) is str and value['source_kind'] in ('legacy_flat', 'history_files')
        and type(value['body_byte_count']) is int and 0 < value['body_byte_count'] <= MAX_BODY
        and _hash(value['body_sha256']) and _hash(value['files_sha256'])
        and type(value['files']) is list and 0 < len(value['files']) <= 3, 'receipt')
    files, table = value['files'], value['table']
    histories = []
    for item in files:
        require(type(item) is dict and set(item) == NORMAL_KEYS
            and type(item['history']) is str and item['history'] in HISTORIES, 'receipt')
        history = item['history']
        require(type(item['name']) is str and item['name'] == _name(table, history)
            and type(item['size']) is int and 0 < item['size'] < 2**63
            and _hash(item['size_label_sha256']) and _hash(item['modified_sha256']), 'receipt')
        require((value['source_kind'] == 'legacy_flat' and item['available'] is None)
            or (value['source_kind'] == 'history_files' and type(item['available']) is bool), 'receipt')
        histories.append(history)
    require(len(histories) == len(set(histories)) and histories == sorted(histories, key=HISTORIES.index)
        and (value['source_kind'] != 'legacy_flat' or histories == ['full'])
        and sha(canonical(files)) == value['files_sha256'], 'receipt')
    # Canonical round trip returns independent caller-owned nested structures.
    return json.loads(canonical(value))


def validate_capture(receipt, raw, *, api_key, table):
    expected = inspect_body(raw, api_key=api_key, table=table)
    checked = validate_receipt(receipt)
    require(canonical(checked) == canonical(expected), 'capture')
    return checked
