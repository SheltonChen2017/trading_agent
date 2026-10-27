"""Strict inert common-price sidecar format shared by host and QC readers.

Data validation grants no source, processing, trading or publication authority.
No I/O, credentials, callbacks or executable serializers are available here.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import time

SCHEMA = 'arv2-r326-common-price-sidecar-v1'
STOCK_COUNT, FUND_COUNT, VENDOR_COUNT, NATIVE_COUNT, CONDITIONAL_COUNT = 6151, 8, 5636, 5, 510
SESSION_COUNT, MONTH_COUNT = 1452, 71
OBSERVED_ROWS, ABSENT_CELLS = 5541040, 2654048
MAX_MONTH_BYTES, MAX_TOTAL_BYTES, MAX_CATALOG_BYTES = 32 * 1024 * 1024, 512 * 1024 * 1024, 4 * 1024 * 1024
MAX_MANIFEST_BYTES, MAX_PRICE_TEXT = 1024 * 1024, 128
FIRST, LAST = '2020-12-31', '2026-10-13'
OWN_FUNDS = ('SPY', 'QQQ', 'SOXX', 'XLV', 'REMX', 'XLE', 'XLI', 'XLF')
VENDOR = 'Sharadar_RAW_full_window'
NATIVE = 'pending_native_original_identity_source'
CONDITIONAL = 'conditional_never_potential_empty_initial_holdings_required'
AP_FACT_SHA256 = '4768862323d73344c48e239568c0dbce849e7441ac1ce7a609115932abe8c825'
AP_SOURCE_SHA256 = '6979b747ed1cf2bccce7144d8cbb1b4a8397373a586d2e736e0b3f8105350da1'
AP_AUTH_SHA256 = '93a82e5cbdd9c79b95de8e9289ebe7d2047b44a50dc1488816756c23fd509f51'
AP_DATA_PINS = {
    'plan': {'byte_count': 2927971, 'sha256': '7703c8e29d7bef5928b0a776628759ff97715b003045c2c00df2b01e7b03f51e'},
    'corpus': {'byte_count': 179185028, 'sha256': '024eeab3ee849e946b429f7c5d52586c58f017012e8593f81c832fa34cad7113'},
    'dispatch': {'byte_count': 161060, 'sha256': '6f875945c0fbb6b36b14f85d393016d3e2240071e0c9662f156a5dc7abdd3f25'},
    'captures': {'byte_count': 343437, 'sha256': '1c29fdbb57a7e64fe2191a279ea9e2e9bfc8a61aad8dae98d2e55340500f5ea5'}}
BINDING_SHA256 = '73ba4ac73c0485b2d274c31b5ec740a97a64de27a4f6dfbfb9cb63bc8e7cd15f'
FULL_AXIS_SHA256 = '4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585'
FALSE_FLAGS = {'source_admission_granted': False, 'QC_processing_rights_granted': False,
    'complete_price_coverage_proven': False, 'point_in_time_proven': False,
    'formal_identity_admitted': False, 'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('shape', 'bound', 'hash', 'json', 'price', 'catalog', 'assignment', 'axis',
    'month', 'manifest', 'grid', 'duplicate', 'missing', 'source', 'deadline', 'unknown'))


class Refused(ValueError): pass


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def sha(raw): return hashlib.sha256(raw).hexdigest()
def digest(value): return sha(canonical(value))
def pin(raw): return {'byte_count': len(raw), 'sha256': sha(raw)}
def hash_string(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate_pin(value, maximum):
    require(type(value) is dict and set(value) == {'byte_count', 'sha256'}
        and type(value['byte_count']) is int and 0 < value['byte_count'] <= maximum
        and hash_string(value['sha256']), 'hash')
    return value


def loads(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum, 'bound')
    def pairs(items):
        value = {}
        for key, child in items:
            require(key not in value, 'duplicate'); value[key] = child
        return value
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('json')))
        require(canonical(value) == raw, 'json'); return value
    except (ValueError, UnicodeError, RecursionError): raise Refused('json') from None


def price_text(value):
    require(type(value) is str and 0 < len(value) <= MAX_PRICE_TEXT
        and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', value), 'price')
    try: number = Decimal(value)
    except InvalidOperation: raise Refused('price') from None
    require(number.is_finite() and number > 0, 'price')
    normalized = format(number, 'f')
    if '.' in normalized: normalized = normalized.rstrip('0').rstrip('.')
    require(value == normalized, 'price'); return value


def months(sessions):
    require(type(sessions) is list and len(sessions) == SESSION_COUNT and sessions == sorted(set(sessions))
        and sessions[0] == FIRST and sessions[-1] == LAST, 'axis')
    result = []
    for index, session in enumerate(sessions):
        require(type(session) is str and re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}', session), 'axis')
        try: require(date.fromisoformat(session).isoformat() == session, 'axis')
        except ValueError: raise Refused('axis') from None
        label = session[:7]
        if not result or result[-1]['month'] != label:
            result.append({'month_ordinal': len(result), 'month': label, 'session_indexes': []})
        result[-1]['session_indexes'].append(index)
    require(len(result) == MONTH_COUNT and len(result) <= 72, 'month')
    return result


def validate_catalog(value):
    keys = {'schema', 'AP_fact_sha256', 'AP_source_sha256', 'AP_authentication_sha256',
        'source_data_pins', 'binding_stream_sha256', 'full_axis_sha256', 'price_sessions',
        'assignments', 'vendor_slots', 'months', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA + '-catalog'
        and value['AP_fact_sha256'] == AP_FACT_SHA256 and value['AP_source_sha256'] == AP_SOURCE_SHA256
        and value['AP_authentication_sha256'] == AP_AUTH_SHA256
        and value['binding_stream_sha256'] == BINDING_SHA256 and value['full_axis_sha256'] == FULL_AXIS_SHA256
        and all(value[key] is False for key in FALSE_FLAGS), 'catalog')
    require(value['source_data_pins'] == AP_DATA_PINS, 'source')
    for row in value['source_data_pins'].values(): validate_pin(row, 2 * 1024 * 1024 * 1024)
    require(value['months'] == months(value['price_sessions']), 'month')
    assignments = value['assignments']
    require(type(assignments) is list and len(assignments) == STOCK_COUNT + FUND_COUNT, 'assignment')
    seen_ids, seen_pins, tickers, counts = set(), set(), set(), {VENDOR: 0, NATIVE: 0, CONDITIONAL: 0}
    for index, row in enumerate(assignments):
        require(type(row) is dict, 'assignment')
        if index < STOCK_COUNT:
            require(set(row) == {'binding_ordinal', 'security_id', 'whole_binding_sha256', 'semantic_binding_sha256',
                'role', 'table', 'ticker', 'refusal_reason'} and type(row['binding_ordinal']) is int and row['binding_ordinal'] == index
                and type(row['security_id']) is str and row['security_id'] not in seen_ids
                and hash_string(row['whole_binding_sha256']) and row['whole_binding_sha256'] not in seen_pins
                and hash_string(row['semantic_binding_sha256']) and row['role'] in counts, 'assignment')
            seen_ids.add(row['security_id']); seen_pins.add(row['whole_binding_sha256']); counts[row['role']] += 1
            if row['role'] != VENDOR:
                require(row['table'] is row['ticker'] is None, 'assignment')
                continue
            require(row['table'] == 'stocks' and row['refusal_reason'] is None, 'assignment')
        else:
            require(set(row) == {'fund_ordinal', 'own_ETF', 'role', 'table', 'ticker', 'route_sha256'}
                and type(row['fund_ordinal']) is int and row['fund_ordinal'] == index - STOCK_COUNT and row['own_ETF'] == OWN_FUNDS[index - STOCK_COUNT]
                and row['role'] == VENDOR and row['table'] == 'funds' and hash_string(row['route_sha256']), 'assignment')
        require(type(row['ticker']) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,31}', row['ticker'])
            and row['ticker'] not in tickers, 'assignment'); tickers.add(row['ticker'])
    require(counts == {VENDOR: VENDOR_COUNT, NATIVE: NATIVE_COUNT, CONDITIONAL: CONDITIONAL_COUNT}, 'assignment')
    expected_slots = [index for index, row in enumerate(assignments) if row['role'] == VENDOR]
    require(value['vendor_slots'] == expected_slots and len(expected_slots) == VENDOR_COUNT + FUND_COUNT, 'assignment')
    require(len(canonical(value)) <= MAX_CATALOG_BYTES, 'bound'); return value


def validate_shard_summary(value):
    keys = {'month_ordinal', 'month', 'session_indexes', 'row_count', 'valid_count', 'absent_count', 'byte_count', 'sha256'}
    require(type(value) is dict and set(value) == keys and type(value['month_ordinal']) is int
        and 0 <= value['month_ordinal'] < MONTH_COUNT and type(value['month']) is str
        and re.fullmatch('[0-9]{4}-[0-9]{2}', value['month']) and type(value['session_indexes']) is list
        and 0 < len(value['session_indexes']) <= 31 and value['session_indexes'] == sorted(set(value['session_indexes']))
        and all(type(index) is int and 0 <= index < SESSION_COUNT for index in value['session_indexes'])
        and all(type(value[key]) is int and value[key] >= 0 for key in ('row_count', 'valid_count', 'absent_count'))
        and value['row_count'] == (VENDOR_COUNT + FUND_COUNT) * len(value['session_indexes'])
        and value['valid_count'] + value['absent_count'] == value['row_count'], 'month')
    validate_pin({'byte_count': value['byte_count'], 'sha256': value['sha256']}, MAX_MONTH_BYTES); return value


def validate_manifest(value):
    keys = {'schema', 'catalog_pin', 'AP_fact_sha256', 'AP_authentication_sha256', 'binding_stream_sha256',
        'full_axis_sha256', 'assignment_count', 'vendor_slot_count', 'session_count', 'months',
        'row_count', 'valid_count', 'absent_count', 'total_shard_bytes', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA + '-manifest'
        and value['AP_fact_sha256'] == AP_FACT_SHA256 and value['AP_authentication_sha256'] == AP_AUTH_SHA256
        and value['binding_stream_sha256'] == BINDING_SHA256 and value['full_axis_sha256'] == FULL_AXIS_SHA256
        and type(value['assignment_count']) is type(value['vendor_slot_count']) is type(value['session_count']) is int
        and value['assignment_count'] == STOCK_COUNT + FUND_COUNT and value['vendor_slot_count'] == VENDOR_COUNT + FUND_COUNT
        and value['session_count'] == SESSION_COUNT and all(value[key] is False for key in FALSE_FLAGS), 'manifest')
    validate_pin(value['catalog_pin'], MAX_CATALOG_BYTES)
    require(type(value['months']) is list and len(value['months']) == MONTH_COUNT, 'manifest')
    indexes, labels = [], []
    for index, row in enumerate(value['months']):
        validate_shard_summary(row); require(row['month_ordinal'] == index, 'manifest')
        indexes.extend(row['session_indexes']); labels.append(row['month'])
    require(indexes == list(range(SESSION_COUNT)) and labels == sorted(set(labels))
        and labels[0] == FIRST[:7] and labels[-1] == LAST[:7], 'manifest')
    for key in ('row_count', 'valid_count', 'absent_count'):
        require(type(value[key]) is int and value[key] == sum(row[key] for row in value['months']), 'manifest')
    require(value['row_count'] == (VENDOR_COUNT + FUND_COUNT) * SESSION_COUNT
        and value['valid_count'] == OBSERVED_ROWS and value['absent_count'] == ABSENT_CELLS
        and type(value['total_shard_bytes']) is int
        and value['total_shard_bytes'] == sum(row['byte_count'] for row in value['months']) <= MAX_TOTAL_BYTES
        and len(canonical(value)) <= MAX_MANIFEST_BYTES, 'bound'); return value


def validate_shard(raw, *, catalog, summary, deadline=None):
    """Authenticate one complete monthly grid; bounded tuple, never a global map."""
    validate_shard_summary(summary)
    require(type(raw) is bytes and pin(raw) == {'byte_count': summary['byte_count'], 'sha256': summary['sha256']}, 'hash')
    require(summary['month_ordinal'] < len(catalog['months'])
        and {key: summary[key] for key in ('month_ordinal', 'month', 'session_indexes')} == catalog['months'][summary['month_ordinal']], 'month')
    expected = ((slot, session) for slot in catalog['vendor_slots'] for session in summary['session_indexes'])
    values, valid, offset = [], 0, 0
    for slot, session in expected:
        if deadline is not None: require(type(deadline) in (int, float) and time.monotonic() < deadline, 'deadline')
        end = raw.find(b'\n', offset); require(end >= offset and end - offset <= MAX_PRICE_TEXT + 32, 'grid')
        row = loads(raw[offset:end], MAX_PRICE_TEXT + 32); offset = end + 1
        require(type(row) is list and len(row) == 3 and type(row[0]) is type(row[1]) is int
            and row[:2] == [slot, session], 'grid')
        if row[2] is not None: price_text(row[2]); valid += 1
        values.append(row[2])
    require(offset == len(raw) and valid == summary['valid_count']
        and len(values) - valid == summary['absent_count'], 'grid')
    if deadline is not None: require(time.monotonic() < deadline, 'deadline')
    return tuple(values)


def profile_record():
    return {'schema': SCHEMA, 'assignment_count': STOCK_COUNT + FUND_COUNT, 'vendor_slots': VENDOR_COUNT + FUND_COUNT,
        'session_count': SESSION_COUNT, 'months': MONTH_COUNT, 'month_bytes_maximum': MAX_MONTH_BYTES,
        'total_shard_bytes_maximum': MAX_TOTAL_BYTES, 'row_layout': '[source_slot,session_index,canonical_Decimal_text_or_null]',
        'source_choice': 'fixed_whole_binding_no_fallback_native_and_conditional_not_vendor_cells',
        'AP_fact_sha256': AP_FACT_SHA256, 'AP_authentication_sha256': AP_AUTH_SHA256, **FALSE_FLAGS}
