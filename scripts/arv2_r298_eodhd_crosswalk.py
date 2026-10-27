"""Pure qualified current EOD identifier crosswalk; never price admission.

The caller supplies all bytes/rows under its new source guard and separately
authenticates AW and the fresh genuine package. No I/O, provider, credential,
QC, callback, fallback or strategy operation is available here.
"""
from collections import Counter, defaultdict
import hashlib
import json
import math
import re
import time

from scripts import arv2_r298_raw_price_acquisition as prices
from scripts import arv2_r298_eodhd_catalog_schema as catalogs

SCHEMA = 'arv2-r298-EODHD-current-crosswalk-v1'
PRIVATE_SCHEMA, INVENTORY_SCHEMA = SCHEMA + '-private', SCHEMA + '-captured-inventories'
EXPECTED_STOCKS, EXPECTED_FUNDS = 6151, 8
AC_PIN = {'byte_count': 16344399, 'sha256': '4366e1e8a218fb21afc6ef3d88dfed9c2ab8b784a7718a405616850e1a4d6ddc'}
AP_PIN = {'byte_count': 2927971, 'sha256': '7703c8e29d7bef5928b0a776628759ff97715b003045c2c00df2b01e7b03f51e'}
MAX_ROWS, MAX_RECORD_BYTES, MAX_PRIVATE_BYTES = 200000, 64 * 1024 * 1024, 64 * 1024 * 1024
MAPPING_FIELDS = frozenset(('symbol', 'isin', 'figi', 'lei', 'cusip', 'cik'))
AP_ROLES = frozenset(('Sharadar_RAW_full_window', 'pending_native_original_identity_source',
    'conditional_never_potential_empty_initial_holdings_required'))
REASONS = frozenset(('source_locator_unavailable', 'source_figi_invalid', 'source_vocabulary_invalid',
    'source_owner_collision', 'no_identifier_match', 'figi_only_no_cusip_link',
    'mapping_fields_unknown', 'mapping_identifier_invalid', 'mapping_identifier_conflict',
    'mapping_symbol_ambiguous', 'catalog_symbol_missing', 'catalog_identity_ambiguous',
    'catalog_instrument_or_currency', 'isin_conflict', 'EOD_symbol_owner_collision'))
FALSE_FLAGS = {'crosswalk_admitted': False, 'price_source_policy_admitted': False,
    'price_acquired': False, 'price_coverage_proven': False, 'strategy_continued': False,
    'source_fallback_selected': False, 'historical_intervals_proven': False,
    'permanent_security_master_proven': False, 'original_identity_rewritten': False,
    'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False}
FINITE = frozenset(('deadline', 'source_pin', 'source_json', 'source_frame', 'genuine_binding',
    'plan', 'inventory', 'catalog', 'mapping', 'bound', 'summary', 'private_record', 'unknown'))


class Refused(ValueError): pass


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
        require(type(deadline) in (int, float) and math.isfinite(deadline) and time.monotonic() < deadline, 'deadline')


def _figi(value):
    if type(value) is not str or re.fullmatch('[B-DF-HJ-NP-TV-Z]{2}G[B-DF-HJ-NP-TV-Z0-9]{8}[0-9]', value) is None:
        return False
    values = [int(char, 36) * (1 if index % 2 == 0 else 2) for index, char in enumerate(value[:11])]
    return int(value[-1]) == (10 - sum(number // 10 + number % 10 for number in values) % 10) % 10


def _cusip(value):
    if type(value) is not str or re.fullmatch('[A-Z0-9*@#]{8}[0-9]', value) is None: return False
    expanded = [int(char) if char.isdecimal() else ord(char) - 55 if char.isalpha()
        else {'*': 36, '@': 37, '#': 38}[char] for char in value[:8]]
    values = [number * (1 if index % 2 == 0 else 2) for index, number in enumerate(expanded)]
    return int(value[-1]) == (10 - sum(number // 10 + number % 10 for number in values) % 10) % 10


def _isin(value):
    if type(value) is not str or re.fullmatch('[A-Z]{2}[A-Z0-9]{9}[0-9]', value) is None: return False
    digits = ''.join(char if char.isdecimal() else str(ord(char) - 55) for char in value)
    values = [int(char) * (1 if index % 2 == 0 else 2) for index, char in enumerate(reversed(digits))]
    return sum(number // 10 + number % 10 for number in values) % 10 == 0


def _symbol(value):
    return type(value) is str and 3 < len(value) <= 68 and value.endswith('.US') \
        and re.fullmatch('[A-Za-z0-9^._-]+', value[:-3]) is not None


def _loads(raw, expected):
    require(type(raw) is bytes and pin(raw) == expected, 'source_pin')
    def pairs(items):
        value = {}
        for key, child in items:
            require(key not in value, 'source_json'); value[key] = child
        return value
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('source_json')))
        require(canonical(value) == raw, 'source_json'); return value
    except Refused: raise
    except (ValueError, UnicodeError, RecursionError, TypeError): raise Refused('source_json') from None


def _bounded(value, deadline, depth=0, nodes=None):
    _budget(deadline)
    if nodes is None: nodes = [0]
    nodes[0] += 1
    require(depth <= 6 and nodes[0] <= 10000, 'mapping')
    if value is None or type(value) in (bool, int): return
    if type(value) is float:
        require(math.isfinite(value), 'mapping'); return
    if type(value) is str:
        require(len(value) <= 4096, 'mapping'); return
    if type(value) is list:
        require(len(value) <= 4096, 'mapping')
        for item in value: _bounded(item, deadline, depth + 1, nodes)
        return
    require(type(value) is dict and len(value) <= 64
        and all(type(key) is str and 0 < len(key) <= 128 for key in value), 'mapping')
    for item in value.values(): _bounded(item, deadline, depth + 1, nodes)


def _observation(rows, deadline):
    require(type(rows) in (tuple, list) and len(rows) <= MAX_ROWS, 'inventory')
    stream, byte_count = hashlib.sha256(), 0
    for row in rows:
        _budget(deadline); require(type(row) is dict, 'inventory')
        raw = canonical(row) + b'\n'; byte_count += len(raw)
        require(byte_count <= MAX_RECORD_BYTES, 'bound'); stream.update(raw)
    return {'row_count': len(rows), 'ordered_records_sha256': stream.hexdigest()}


def _inventory_metadata(value):
    require(type(value) is dict and set(value) == {'schema', 'aw_authentication_sha256',
        'active', 'delisted', 'mapping'} and value['schema'] == INVENTORY_SCHEMA
        and _hash(value['aw_authentication_sha256']), 'inventory')
    for name in ('active', 'delisted', 'mapping'):
        record = value[name]
        fields = {'row_count', 'ordered_records_sha256'} | ({'body_pin'} if name != 'mapping' else set())
        require(type(record) is dict and set(record) == fields and type(record['row_count']) is int
            and 0 <= record['row_count'] <= MAX_ROWS and _hash(record['ordered_records_sha256']), 'inventory')
        if name != 'mapping':
            item = record['body_pin']
            require(type(item) is dict and set(item) == {'byte_count', 'sha256'}
                and type(item['byte_count']) is int and 0 < item['byte_count'] <= catalogs.MAX_RAW_BYTES
                and _hash(item['sha256']), 'inventory')
    return json.loads(canonical(value))


def _inventories(active_raw, delisted_raw, mapping_rows, expected, deadline):
    expected = _inventory_metadata(expected)
    for name, raw in (('active', active_raw), ('delisted', delisted_raw)):
        require(type(raw) is bytes and 0 < len(raw) <= catalogs.MAX_RAW_BYTES
            and pin(raw) == expected[name]['body_pin'], 'inventory')
    try:
        active, delisted = catalogs.checked_symbol_rows(active_raw), catalogs.checked_symbol_rows(delisted_raw)
    except Exception: raise Refused('catalog') from None
    for name, raw, rows in (('active', active_raw, active), ('delisted', delisted_raw, delisted)):
        record = expected[name]
        require(type(record) is dict and set(record) == {'body_pin', 'row_count', 'ordered_records_sha256'}
            and record['body_pin'] == pin(raw)
            and {key: record[key] for key in ('row_count', 'ordered_records_sha256')} == _observation(rows, deadline), 'inventory')
    require(type(mapping_rows) in (tuple, list) and len(mapping_rows) <= MAX_ROWS, 'mapping')
    for row in mapping_rows:
        require(type(row) is dict, 'mapping'); _bounded(row, deadline)
    require(type(expected['mapping']) is dict and set(expected['mapping']) == {'row_count', 'ordered_records_sha256'}
        and expected['mapping'] == _observation(mapping_rows, deadline), 'inventory')
    return list(active), list(delisted), json.loads(canonical(list(mapping_rows)))


def _source(binding_rows, ac_raw, plan_raw, expected_ac_summary, deadline):
    _budget(deadline)
    require(type(ac_raw) is bytes and pin(ac_raw) == AC_PIN, 'source_pin')
    try: frame = prices._source_ac(ac_raw, expected_ac_summary)
    except Exception: raise Refused('source_frame') from None
    require(type(binding_rows) in (tuple, list) and len(binding_rows) == EXPECTED_STOCKS
        and [item['binding'] for item in frame['stocks']] == list(binding_rows), 'genuine_binding')
    plan = _loads(plan_raw, AP_PIN)
    require(type(plan) is dict and set(plan) == {'schema', 'ac_summary_sha256', 'ac_frame_pin',
        'native_specification_sha256', 'full_axis_sha256', 'price_sessions', 'assignments', 'requests'}
        and plan['schema'] == prices.PLAN_PRIVATE_SCHEMA and plan['ac_frame_pin'] == AC_PIN
        and plan['ac_summary_sha256'] == prices.AC_SUMMARY_SHA256
        and plan['native_specification_sha256'] == prices.NATIVE_SPECIFICATION_SHA256
        and plan['full_axis_sha256'] == prices.FULL_AXIS_SHA256
        and type(plan['assignments']) is list and len(plan['assignments']) == EXPECTED_STOCKS + EXPECTED_FUNDS, 'plan')
    return frame, plan


def _sources(frame, plan):
    require(type(frame) is dict and type(frame['stocks']) is list and len(frame['stocks']) == EXPECTED_STOCKS
        and type(frame['funds']) is list and len(frame['funds']) == EXPECTED_FUNDS, 'source_frame')
    result = []
    for index, row in enumerate(frame['stocks']):
        binding, assignment = row['binding'], plan['assignments'][index]
        require(row['binding_ordinal'] == index and assignment['binding_ordinal'] == index
            and assignment['security_id'] == binding['security_id']
            and assignment['whole_binding_sha256'] == digest(binding)
            and assignment['semantic_binding_sha256'] == binding['row_sha256']
            and assignment['role'] in AP_ROLES, 'plan')
        role = assignment['role']
        require((role == 'conditional_never_potential_empty_initial_holdings_required') is (not row['potential']), 'plan')
        route = row['route']
        if role == 'Sharadar_RAW_full_window':
            require(type(route) is dict and row['disposition'] == 'routed'
                and assignment['ticker'] == route['current_metadata_row']['ticker']
                and assignment['table'] == 'stocks', 'plan')
        elif role == 'pending_native_original_identity_source':
            require(row['potential'] is True and row['disposition'] == 'refused' and route is None, 'plan')
        tokens = None if route is None else list(route['current_cusip_tokens'])
        result.append({'kind': 'stock', 'ordinal': index, 'binding': dict(binding), 'AP_role': role,
            'potential': row['potential'], 'figi': binding['composite_figi'], 'tokens': tokens,
            'owner': ('stock', binding['security_id'], binding['composite_figi'])})
    for index, row in enumerate(frame['funds']):
        assignment = plan['assignments'][EXPECTED_STOCKS + index]
        route = row['route']
        require(row['fund_ordinal'] == index and assignment['fund_ordinal'] == index
            and assignment['own_ETF'] == row['ticker'] and assignment['role'] == 'Sharadar_RAW_full_window'
            and row['disposition'] == 'routed' and type(route) is dict
            and assignment['route_sha256'] == digest(route) and assignment['table'] == 'funds'
            and assignment['ticker'] == route['current_metadata_row']['ticker'], 'plan')
        figi = route['current_metadata_row']['figi']
        result.append({'kind': 'fund', 'ordinal': index, 'ticker': row['ticker'], 'AP_role': assignment['role'],
            'potential': True, 'figi': figi, 'tokens': list(route['current_cusip_tokens']),
            'owner': ('fund', row['ticker'], figi)})
    return result


def _indexes(active, delisted, mapping_rows, sources, deadline):
    by_symbol, map_figi, map_cusip, map_symbol = defaultdict(list), defaultdict(set), defaultdict(set), defaultdict(set)
    for table, rows in (('active', active), ('delisted', delisted)):
        for index, row in enumerate(rows):
            _budget(deadline); by_symbol[row['Code'] + '.US'].append((table, index, row))
    records = []
    for index, row in enumerate(mapping_rows):
        _budget(deadline)
        symbol, figi, cusip = row.get('symbol'), row.get('figi'), row.get('cusip')
        valid_fields = set(row) == MAPPING_FIELDS and all(row[key] is None or type(row[key]) is str
            and len(row[key]) <= 4096 for key in MAPPING_FIELDS)
        records.append({'row': row, 'known_fields': valid_fields})
        if _figi(figi): map_figi[figi].add(index)
        if _cusip(cusip): map_cusip[cusip].add(index)
        if _symbol(symbol): map_symbol[symbol].add(index)
    source_figi, source_cusip, source_ids = defaultdict(set), defaultdict(set), defaultdict(set)
    for item in sources:
        _budget(deadline)
        source_figi[item['figi']].add(item['owner'])
        if item['kind'] == 'stock': source_ids[item['binding']['security_id']].add(item['figi'])
        for token in item['tokens'] or ():
            if _cusip(token): source_cusip[token].add(item['owner'])
    return {'catalog': by_symbol, 'map_figi': map_figi, 'map_cusip': map_cusip,
        'map_symbol': map_symbol, 'records': records, 'source_figi': source_figi,
        'source_cusip': source_cusip, 'source_ids': source_ids}


def _match(source, indexes, deadline):
    _budget(deadline)
    figi, tokens, owner = source['figi'], source['tokens'], source['owner']
    matches = set(indexes['map_figi'].get(figi, ()))
    figi_only = bool(matches)
    for token in tokens or (): matches.update(indexes['map_cusip'].get(token, ()))
    result = {'status': 'unresolved', 'reason': None, 'figi_only_observed': False,
        'mapping_indices': sorted(matches), 'catalog_references': [], 'route': None}
    def refused(reason):
        result['reason'] = reason; return result
    if not _figi(figi): return refused('source_figi_invalid')
    if not tokens:
        result['figi_only_observed'] = figi_only
        return refused('source_locator_unavailable')
    if type(tokens) is not list or len(tokens) != len(set(tokens)) or not all(_cusip(token) for token in tokens):
        return refused('source_vocabulary_invalid')
    if len(indexes['source_figi'][figi]) > 1 or any(len(indexes['source_cusip'][token]) > 1 for token in tokens) \
        or source['kind'] == 'stock' and len(indexes['source_ids'][source['binding']['security_id']]) > 1:
        return refused('source_owner_collision')
    if not matches: return refused('no_identifier_match')
    symbols = set()
    for index in tuple(matches):
        row = indexes['records'][index]['row']
        if _symbol(row.get('symbol')): symbols.add(row['symbol'])
    for symbol in symbols: matches.update(indexes['map_symbol'].get(symbol, ()))
    result['mapping_indices'] = sorted(matches)
    owners, matched_tokens, isins = set(), set(), set()
    for index in sorted(matches):
        _budget(deadline)
        item = indexes['records'][index]; row = item['row']
        if not item['known_fields']: return refused('mapping_fields_unknown')
        if not _symbol(row['symbol']) or not _figi(row['figi']) or not _cusip(row['cusip']):
            return refused('mapping_identifier_invalid')
        if row['figi'] != figi: return refused('mapping_identifier_conflict')
        if row['cusip'] not in tokens:
            result['figi_only_observed'] = figi_only
            return refused('figi_only_no_cusip_link')
        isin = row['isin']
        if isin not in (None, ''):
            if not _isin(isin): return refused('mapping_identifier_invalid')
            isins.add(isin)
        owners.add(row['symbol']); matched_tokens.add(row['cusip'])
    if len(owners) != 1: return refused('mapping_symbol_ambiguous')
    if len(isins) > 1: return refused('isin_conflict')
    symbol = next(iter(owners)); catalog_rows = indexes['catalog'].get(symbol, ())
    result['catalog_references'] = [{'table': table, 'ordinal': index} for table, index, _ in catalog_rows]
    if not catalog_rows: return refused('catalog_symbol_missing')
    identities = {(row['Code'], row['Type'], row['Currency'], row['Isin']) for _, _, row in catalog_rows}
    if len(identities) != 1: return refused('catalog_identity_ambiguous')
    code, instrument, currency, isin = next(iter(identities))
    if currency != 'USD' or instrument != ('Common Stock' if source['kind'] == 'stock' else 'ETF'):
        return refused('catalog_instrument_or_currency')
    if isin not in (None, '') and (not _isin(isin) or isins and isin not in isins): return refused('isin_conflict')
    result.update(status='matched_current_crosswalk', reason=None, route={
        'source_policy': 'EODHD_fixed_whole_window_candidate_not_admission',
        'symbol': symbol, 'original_composite_figi': figi, 'matched_cusip_tokens': sorted(matched_tokens),
        'currency': 'USD', 'instrument_type': instrument, 'query_window': [prices.FIRST, prices.LAST],
        'source_whole_binding_sha256': digest(source['binding']) if source['kind'] == 'stock' else None,
        'historical_intervals_proven': False})
    return result


def _prepare_bound(frame, plan, active, delisted, mapping_rows, source_meta, deadline):
    sources = _sources(frame, plan); indexes = _indexes(active, delisted, mapping_rows, sources, deadline)
    results, symbol_owners = [], defaultdict(set)
    for source in sources:
        _budget(deadline); result = _match(source, indexes, deadline); results.append(result)
        if result['route'] is not None: symbol_owners[result['route']['symbol']].add(source['owner'])
    for source, result in zip(sources, results, strict=True):
        if result['route'] is not None and len(symbol_owners[result['route']['symbol']]) > 1:
            result.update(status='unresolved', reason='EOD_symbol_owner_collision', route=None)
    stocks, funds, counts, reasons, prior_roles = [], [], {'stocks': Counter(), 'funds': Counter()}, {'stocks': Counter(), 'funds': Counter()}, Counter()
    output_bytes = 1024
    for source, result in zip(sources, results, strict=True):
        _budget(deadline)
        table = 'stocks' if source['kind'] == 'stock' else 'funds'
        item = {'AP_role': source['AP_role'], 'potential': source['potential'],
            'source_composite_figi': source['figi'], 'complete_source_cusip_tokens': source['tokens'], **result}
        if source['kind'] == 'stock':
            item['binding_ordinal'], item['binding'] = source['ordinal'], source['binding']
            prior_roles[source['AP_role']] += 1
        else:
            item['fund_ordinal'], item['ticker'] = source['ordinal'], source['ticker']
        output_bytes += len(canonical(item)) + 1
        require(output_bytes <= MAX_PRIVATE_BYTES, 'bound')
        (stocks if source['kind'] == 'stock' else funds).append(item)
        counts[table][result['status']] += 1
        if result['reason'] is not None: reasons[table][result['reason']] += 1
    private = {'schema': PRIVATE_SCHEMA, 'source_fingerprint': digest(source_meta), 'stocks': stocks, 'funds': funds}
    raw = canonical(private); require(len(raw) <= MAX_PRIVATE_BYTES, 'bound')
    def duplicates(rows): return len(rows) - len({digest(row) for row in rows})
    summary = {'schema': SCHEMA, 'scope': 'all_supplied_current_identifier_evidence_not_route_or_history_admission',
        'source_fingerprint': digest(source_meta), 'source_pins': source_meta,
        'stock_count': len(stocks), 'fund_count': len(funds),
        'distinct_source_owner_count': len({item['owner'] for item in sources}),
        'repeated_source_owner_binding_count': len(sources) - len({item['owner'] for item in sources}),
        'disposition_counts': {key: dict(sorted(value.items())) for key, value in counts.items()},
        'reason_counts': {key: dict(sorted(value.items())) for key, value in reasons.items()},
        'AP_stock_role_counts': dict(sorted(prior_roles.items())),
        'exact_FIGI_only_unresolved_count': sum(item['figi_only_observed'] and item['status'] == 'unresolved' for item in results),
        'provider_row_counts': {'active': len(active), 'delisted': len(delisted), 'mapping': len(mapping_rows)},
        'provider_duplicate_row_counts': {'active': duplicates(active), 'delisted': duplicates(delisted), 'mapping': duplicates(mapping_rows)},
        'private_payload_pin': pin(raw), 'all_original_rows_retained': True,
        'all_supplied_provider_rows_indexed': True, **FALSE_FLAGS}
    validate_summary(summary)
    return summary, PrivateCrosswalk(raw, digest(summary))


class PrivateCrosswalk:
    __slots__ = ('_raw', 'byte_count', 'sha256', 'summary_sha256')
    def __init__(self, raw, summary_sha256):
        object.__setattr__(self, '_raw', raw); object.__setattr__(self, 'byte_count', len(raw))
        object.__setattr__(self, 'sha256', sha(raw)); object.__setattr__(self, 'summary_sha256', summary_sha256)
    def __setattr__(self, name, value): raise TypeError('private crosswalk is immutable')
    def __repr__(self): return '<PrivateCrosswalk current identifier evidence; redacted; no authority>'
    def __reduce_ex__(self, protocol): raise TypeError('private crosswalk cannot be exported by pickle')
    def private_record(self):
        require(type(self._raw) is bytes and len(self._raw) == self.byte_count
            and sha(self._raw) == self.sha256, 'private_record')
        return json.loads(self._raw)


def validate_summary(value):
    keys = {'schema', 'scope', 'source_fingerprint', 'source_pins', 'stock_count', 'fund_count',
        'distinct_source_owner_count', 'repeated_source_owner_binding_count', 'disposition_counts',
        'reason_counts', 'AP_stock_role_counts', 'exact_FIGI_only_unresolved_count', 'provider_row_counts',
        'provider_duplicate_row_counts', 'private_payload_pin', 'all_original_rows_retained',
        'all_supplied_provider_rows_indexed', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
        and value['scope'] == 'all_supplied_current_identifier_evidence_not_route_or_history_admission'
        and value['stock_count'] == EXPECTED_STOCKS and type(value['stock_count']) is int
        and value['fund_count'] == EXPECTED_FUNDS and type(value['fund_count']) is int
        and value['all_original_rows_retained'] is value['all_supplied_provider_rows_indexed'] is True
        and all(value[key] is False for key in FALSE_FLAGS) and _hash(value['source_fingerprint'])
        and type(value['source_pins']) is dict, 'summary')
    source_meta = value['source_pins']
    require(set(source_meta) == {'AC', 'AP_plan', 'genuine_binding_stream_sha256', 'AW'}
        and source_meta['AC'] == AC_PIN and source_meta['AP_plan'] == AP_PIN
        and source_meta['genuine_binding_stream_sha256'] == prices.native.BINDING_STREAM_SHA256, 'summary')
    _inventory_metadata(source_meta['AW'])
    require(digest(source_meta) == value['source_fingerprint'], 'summary')
    for name in ('disposition_counts', 'reason_counts'):
        require(type(value[name]) is dict and set(value[name]) == {'stocks', 'funds'}, 'summary')
    total = EXPECTED_STOCKS + EXPECTED_FUNDS
    for key in ('distinct_source_owner_count', 'repeated_source_owner_binding_count', 'exact_FIGI_only_unresolved_count'):
        require(type(value[key]) is int and 0 <= value[key] <= total, 'summary')
    require(value['distinct_source_owner_count'] + value['repeated_source_owner_binding_count'] == total, 'summary')
    require(type(value['AP_stock_role_counts']) is dict and set(value['AP_stock_role_counts']) <= AP_ROLES
        and all(type(count) is int and count > 0 for count in value['AP_stock_role_counts'].values())
        and sum(value['AP_stock_role_counts'].values()) == EXPECTED_STOCKS, 'summary')
    for table, expected in (('stocks', EXPECTED_STOCKS), ('funds', EXPECTED_FUNDS)):
        counts, reasons = value['disposition_counts'][table], value['reason_counts'][table]
        require(type(counts) is dict and set(counts) <= {'matched_current_crosswalk', 'unresolved'}
            and all(type(count) is int and count > 0 for count in counts.values()) and sum(counts.values()) == expected
            and type(reasons) is dict and set(reasons) <= REASONS
            and all(type(count) is int and count > 0 for count in reasons.values())
            and sum(reasons.values()) == counts.get('unresolved', 0), 'summary')
    require(value['exact_FIGI_only_unresolved_count'] <= sum(
        value['disposition_counts'][table].get('unresolved', 0) for table in ('stocks', 'funds')), 'summary')
    require(value['provider_row_counts'] == {name: source_meta['AW'][name]['row_count']
        for name in ('active', 'delisted', 'mapping')}, 'summary')
    for key in ('provider_row_counts', 'provider_duplicate_row_counts'):
        require(type(value[key]) is dict and set(value[key]) == {'active', 'delisted', 'mapping'}
            and all(type(count) is int and 0 <= count <= MAX_ROWS for count in value[key].values()), 'summary')
    require(all(value['provider_duplicate_row_counts'][key] <= value['provider_row_counts'][key]
        for key in value['provider_row_counts']), 'summary')
    payload = value['private_payload_pin']
    require(type(payload) is dict and set(payload) == {'byte_count', 'sha256'}
        and type(payload['byte_count']) is int and 0 < payload['byte_count'] <= MAX_PRIVATE_BYTES
        and _hash(payload['sha256']), 'summary')
    return json.loads(canonical(value))


def prepare(binding_rows, ac_raw, ap_plan_raw, active_raw, delisted_raw, mapping_rows, *,
            expected_ac_summary, expected_aw_inventory, deadline=None):
    _budget(deadline)
    frame, plan = _source(binding_rows, ac_raw, ap_plan_raw, expected_ac_summary, deadline)
    active, delisted, mappings = _inventories(active_raw, delisted_raw, mapping_rows, expected_aw_inventory, deadline)
    source_meta = {'AC': dict(AC_PIN), 'AP_plan': dict(AP_PIN),
        'genuine_binding_stream_sha256': frame['binding_contract']['binding_stream_sha256'],
        'AW': json.loads(canonical(expected_aw_inventory))}
    return _prepare_bound(frame, plan, active, delisted, mappings, source_meta, deadline)


def profile_record():
    return {'schema': SCHEMA, 'AC_pin': dict(AC_PIN), 'AP_plan_pin': dict(AP_PIN),
        'stock_count': EXPECTED_STOCKS, 'fund_count': EXPECTED_FUNDS,
        'inventory_commitment': 'full_canonical_ASCII_sorted_JSON_row_plus_real_LF_preserve_order_duplicates_unknowns',
        'matching': 'unique_EOD_symbol_identity_exact_valid_compositeFIGI_and_at_least_one_exact_checksum_CUSIP9_link',
        'all_tokens': 'all_source_tokens_and_all_global_mapping_relationships_checked_no_first_token_or_row',
        'source_owner': 'same_validated_original_security_id_AND_compositeFIGI_repeated_intervals_share_owner_other_IDs_never_merge',
        'duplicate_provider_rows': 'preserved_classified_same_complete_identity_ownership_can_agree_no_arbitrary_first_row',
        'display': 'ticker_name_country_exchange_CIK_LEI_never_identity_or_alias_proof',
        'FIGI_only': 'diagnostic_unresolved_not_a_route',
        'current_catalog': 'USD_and_exact_Common_Stock_or_ETF_type_optional_ISIN_consistency_no_historical_interval_inference',
        'policy': 'prospective_fixed_EOD_whole_window_same_six_cells_not_implicit_Sharadar_native_fallback',
        'scope': 'all6151_original_bindings_plus8funds_including_native5_andconditional510_never_dropped',
        **FALSE_FLAGS}
