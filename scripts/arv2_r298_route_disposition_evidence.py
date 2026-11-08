"""Pure finite diagnostics of an externally authenticated AA private frame.

Only supplied bytes/metadata are inspected. The parent authenticates AA's real
exit and routing-summary provenance. A matching frame hash is not authority.
No files, credentials, provider/QC calls, price filters or membership admission.
Candidate rows are a SUBSET: global collision causes cannot be reconstructed.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
import json
import math
import re
import time

from scripts import arv2_r298_sharadar_all_routes_v2 as routes

SCHEMA = 'arv2-r298-route-disposition-evidence-v1'
PRIVATE_SCHEMA = 'arv2-r298-route-disposition-private-v1'
EXPECTED_STOCKS, EXPECTED_FUNDS = 6151, 8
MAX_FRAME_BYTES, MAX_PRIVATE_BYTES = routes.MAX_PRIVATE_BYTES, 64 * 1024 * 1024
MAX_SUMMARY_BYTES, MAX_JSON_DEPTH, MAX_JSON_NODES = 128 * 1024, 16, 4000000
MAX_JSON_SEPARATORS = 8000000
STATES = frozenset(('pass', 'fail', 'unknown'))
DISPOSITIONS = frozenset(('routed', 'refused', 'outside_window'))
ORIGINAL_FIELDS = ('source_present', 'source_row_hash', 'original_metadata', 'security_id',
    'permaticker_to_issuer_id', 'composite_figi', 'listing_id', 'diagnostic_current_ticker',
    'diagnostic_exchange_mic', 'identity_evidence_hash', 'original_currency_usd',
    'raw_first_le_candidate_first', 'candidate_last_le_raw_last_or_open', 'complete_cusip_vocabulary')
CURRENT_FIELDS = ('table_supported', 'permaticker_shape', 'ticker_shape', 'figi_shape',
    'cusip_vocabulary', 'exchange_supported', 'exchange_mic_shape', 'category_supported',
    'currency_usd', 'delisted_shape', 'firstpricedate_valid', 'lastpricedate_valid',
    'lastupdated_valid', 'price_interval_ordered', 'current_first_covers_required',
    'current_last_covers_required', 'ticker_matches_original', 'mic_matches_original',
    'original_tokens_retained')
MATCH_FIELDS = ('permaticker', 'figi', 'ticker', 'perma_and_figi', 'expected_table')
LOCAL_COLLISIONS = ('permaticker_other_rows', 'figi_other_rows', 'ticker_other_rows',
    'complete_token_overlap_rows', 'malformed_token_overlap_rows')
CATEGORIES = frozenset(('original_reconstruction_unavailable', 'original_identity_component_mismatch',
    'original_currency_not_usd', 'original_raw_candidate_interval_mismatch',
    'current_ticker_changed', 'current_exchange_mic_changed', 'current_table_mismatch', 'current_category_unsupported',
    'current_currency_not_usd', 'current_exchange_unsupported', 'current_identifier_or_vocabulary_shape',
    'current_metadata_date_invalid', 'current_first_after_required_geometry',
    'current_last_before_required_geometry', 'current_perma_figi_no_intersection',
    'current_same_perma_only', 'current_same_figi_only', 'current_same_ticker_only',
    'current_candidate_ambiguous', 'candidate_subset_empty', 'local_candidate_collision_seen',
    'global_collision_index_cause_unknown', 'recorded_outside_original_binding_window'))
FINITE = frozenset(('deadline', 'summary', 'frame_pin', 'json', 'json_bound', 'frame', 'binding',
    'source_row', 'stock_record', 'fund_record', 'disposition', 'route_record', 'count',
    'private_record', 'private_pin', 'unknown'))
STOCK_INPUT = frozenset(('binding_ordinal', 'binding', 'original_row', 'original_cusip_tokens',
    'required_first_date', 'required_last_date', 'current_candidate_rows', 'disposition', 'reason', 'route'))
FUND_INPUT = frozenset(('fund_ordinal', 'ticker', 'current_candidate_rows', 'disposition', 'reason', 'route'))
ROUTE_FIELDS = frozenset(('table', 'current_metadata_row', 'current_cusip_tokens', 'current_exchange_mic',
    'required_first_date', 'required_last_date', 'route_key', 'security_id', 'source_binding_sha256'))
STOCK_OUTPUT = frozenset(('binding_ordinal', 'binding', 'disposition', 'reason', 'required_first_date',
    'required_last_date', 'original_predicates', 'current_evidence'))
FUND_OUTPUT = frozenset(('fund_ordinal', 'ticker', 'disposition', 'reason', 'required_first_date',
    'required_last_date', 'current_evidence'))
ROUTING_KEYS = frozenset(('schema', 'scope', 'binding_contract', 'price_window', 'original_row_count',
    'original_rows_digest', 'metadata_rows_sha256', 'metadata_row_counts',
    'catalog_unknown_vocabulary_row_count', 'catalog_collision_group_counts',
    'disposition_counts', 'refusal_counts', 'private_payload_byte_count', 'private_payload_sha256'))
canonical, sha = routes.canonical, routes.sha


class Refused(ValueError):
    """A finite predicate, never a source value or exception rendering."""


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def _deadline(value):
    if value is not None:
        require(type(value) in (int, float) and math.isfinite(value) and time.monotonic() < value, 'deadline')


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _count(value, maximum=routes.MAX_CANDIDATE_ROWS):
    return type(value) is int and 0 <= value <= maximum


def _pin(value, maximum):
    return type(value) is dict and set(value) == {'byte_count', 'sha256'} and type(value['byte_count']) is int \
        and 0 < value['byte_count'] <= maximum and _hash(value['sha256'])


def _date(value):
    if type(value) is not str or len(value) != 10: return None
    try: parsed = date.fromisoformat(value)
    except ValueError: return None
    return value if parsed.isoformat() == value else None


def _state(value): return 'pass' if value else 'fail'


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'json')
        result[key] = value
    return result


def _decode(raw, deadline):
    # Bound nesting and delimiter-driven allocation before json.loads. The
    # exact externally pinned frame is still required before this is called.
    quoted, escaped, depth, separators = False, False, 0, 0
    for index, byte in enumerate(raw):
        if index % 65536 == 0: _deadline(deadline)
        if quoted:
            if escaped: escaped = False
            elif byte == 92: escaped = True
            elif byte == 34: quoted = False
            continue
        if byte == 34: quoted = True
        elif byte in (123, 91):
            depth += 1; require(depth <= MAX_JSON_DEPTH, 'json_bound')
        elif byte in (125, 93):
            depth -= 1; require(depth >= 0, 'json')
        elif byte in (44, 58):
            separators += 1; require(separators <= MAX_JSON_SEPARATORS, 'json_bound')
    require(not quoted and not escaped and depth == 0, 'json')
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused('json')))
        require(type(value) is dict and canonical(value) == raw, 'json')
    except (ValueError, UnicodeError, RecursionError): raise Refused('json') from None
    pending, nodes = [value], 0
    while pending:
        item = pending.pop(); nodes += 1
        require(nodes <= MAX_JSON_NODES and type(item) in (dict, list, str, int, bool, type(None)), 'json_bound')
        if type(item) is dict: pending.extend(item.values())
        elif type(item) is list: pending.extend(item)
    return value


def _routing_summary(value):
    require(type(value) is dict and set(value) == ROUTING_KEYS and value['schema'] == routes.SCHEMA
        and value['scope'] == 'supplied_current_route_crosscheck_not_admission'
        and value['price_window'] == [routes.PRICE_FIRST, routes.PRICE_LAST], 'summary')
    try: contract = routes._contract(value['binding_contract'])
    except (ValueError, TypeError): raise Refused('summary') from None
    require(contract['binding_count'] == EXPECTED_STOCKS and _pin({
        'byte_count': value['private_payload_byte_count'], 'sha256': value['private_payload_sha256']}, MAX_FRAME_BYTES), 'summary')
    for key in ('metadata_rows_sha256', 'metadata_row_counts', 'disposition_counts', 'refusal_counts'):
        require(type(value[key]) is dict and set(value[key]) == {'stocks', 'funds'}, 'summary')
    for table, count in (('stocks', EXPECTED_STOCKS), ('funds', EXPECTED_FUNDS)):
        require(_hash(value['metadata_rows_sha256'][table]) and _count(value['metadata_row_counts'][table], 200000), 'summary')
        dispositions, reasons = value['disposition_counts'][table], value['refusal_counts'][table]
        require(type(dispositions) is dict and set(dispositions) <= DISPOSITIONS
            and all(type(n) is int and n > 0 for n in dispositions.values())
            and sum(dispositions.values()) == count and type(reasons) is dict and set(reasons) <= routes.REASONS
            and all(type(n) is int and n > 0 for n in reasons.values())
            and sum(reasons.values()) == dispositions.get('refused', 0), 'summary')
    require(_count(value['original_row_count'], routes.MAX_ORIGINAL_ROWS) and value['original_row_count'] > 0
        and _hash(value['original_rows_digest']) and _count(value['catalog_unknown_vocabulary_row_count'], 200000)
        and type(value['catalog_collision_group_counts']) is dict
        and set(value['catalog_collision_group_counts']) == {'permaticker_collision_groups', 'figi_collision_groups',
            'ticker_collision_groups', 'complete_token_collision_groups', 'malformed_overlap_token_groups'}
        and all(_count(n, 200000) for n in value['catalog_collision_group_counts'].values()), 'summary')
    return contract


def _original(binding, source):
    states = dict.fromkeys(ORIGINAL_FIELDS, 'unknown')
    states['source_present'] = _state(source is not None)
    if source is None: return states, None
    require(type(source) is dict and routes.valid_original_columns(tuple(source)), 'source_row')
    try: source_pin = routes.original.source_row_digest(source)
    except (ValueError, TypeError): raise Refused('source_row') from None
    states['source_row_hash'] = _state(source_pin == binding['source_row_sha256'])
    require(states['source_row_hash'] == 'pass', 'source_row')
    try: values = routes.original._metadata(source)
    except (ValueError, TypeError):
        states['original_metadata'] = 'fail'; return states, None
    states['original_metadata'] = 'pass'
    table, ticker, perma, figi, exchange, mic, old_tokens, first, last = values
    evidence = {'permaticker': perma, 'composite_figi': figi, 'source_table': table, 'ticker': ticker,
        'cusips': list(old_tokens), 'exchange': exchange, 'exchange_mic': mic,
        'firstpricedate': first, 'lastpricedate': last, 'source_row_sha256': source_pin,
        'availability_semantics': routes.original.composer.TICKERS_AVAILABILITY}
    evidence_pin = sha(routes.original.composer.canonical_json_bytes(evidence))
    c = routes.original.composer
    comparisons = {'security_id': c._safe_component('sharadar-composite-figi', figi) == binding['security_id'],
        'permaticker_to_issuer_id': c._safe_component('sharadar-permaticker', perma) == binding['issuer_id'],
        'composite_figi': figi == binding['composite_figi'],
        'listing_id': 'sharadar-listing-' + evidence_pin[:24] == binding['listing_id'],
        'diagnostic_current_ticker': ticker == binding['diagnostic_current_ticker'],
        'diagnostic_exchange_mic': mic == binding['diagnostic_exchange_mic'],
        'identity_evidence_hash': evidence_pin == binding['identity_evidence_sha256'],
        'original_currency_usd': source['currency'] == 'USD',
        'raw_first_le_candidate_first': first <= binding['candidate_first_session'],
        'candidate_last_le_raw_last_or_open': last is None or binding['candidate_last_session'] <= last}
    states.update({key: _state(value) for key, value in comparisons.items()})
    try: original_tokens = routes.current.parse_vocabulary(source['cusips'])
    except routes.current.vocabulary.Refused: original_tokens = None
    states['complete_cusip_vocabulary'] = _state(bool(original_tokens))
    return states, {'permaticker': perma, 'figi': figi, 'ticker': ticker, 'mic': mic, 'tokens': original_tokens}


def _mic(row, table):
    value = routes.current.previous.composer._SHARADAR_EXCHANGE_TO_MIC.get(row['exchange'].upper())
    return {'NYSEARCA': 'ARCX', 'NYSE ARCA': 'ARCX', 'BATS': 'BATS'}.get(row['exchange'].upper(), value) \
        if table == 'funds' else value


def _current(candidates, *, table, original, ticker, first, last, deadline):
    require(type(candidates) is list and len(candidates) <= routes.MAX_CANDIDATE_ROWS_PER_ITEM, 'route_record')
    rows = []
    for row in candidates:
        _deadline(deadline)
        try: rows.append(routes.current._row(row))
        except (ValueError, TypeError): raise Refused('route_record') from None
    wanted = original or {'permaticker': None, 'figi': None, 'ticker': ticker, 'mic': None, 'tokens': None}
    matches = {'permaticker': None if wanted['permaticker'] is None else sum(row['permaticker'] == wanted['permaticker'] for row in rows),
        'figi': None if wanted['figi'] is None else sum(row['figi'] == wanted['figi'] for row in rows),
        'ticker': sum(row['ticker'] == ticker for row in rows),
        'perma_and_figi': None if wanted['permaticker'] is None or wanted['figi'] is None else sum(
            row['permaticker'] == wanted['permaticker'] and row['figi'] == wanted['figi'] for row in rows),
        'expected_table': sum(row['table'] in (table, 'SEP' if table == 'stocks' else 'SFP') for row in rows)}
    selected = [index for index, row in enumerate(rows) if
        (row['permaticker'] == wanted['permaticker'] and row['figi'] == wanted['figi']
            if table == 'stocks' else row['ticker'] == ticker and row['table'] in ('funds', 'SFP'))]
    states, collision = dict.fromkeys(CURRENT_FIELDS, 'unknown'), dict.fromkeys(LOCAL_COLLISIONS, None)
    if len(selected) == 1:
        own = selected[0]; row = rows[own]
        identity, composer = routes.current.previous.identities, routes.current.previous.composer
        tokens, vocabulary_state = routes.current._parsed(row['cusips'])
        mic = _mic(row, table)
        shape = {'table_supported': row['table'] in (table, 'SEP' if table == 'stocks' else 'SFP'),
            'permaticker_shape': identity._PERMANENT_ID.fullmatch(row['permaticker']) is not None,
            'ticker_shape': composer._TICKER.fullmatch(row['ticker']) is not None,
            'figi_shape': identity._FIGI.fullmatch(row['figi']) is not None,
            'cusip_vocabulary': vocabulary_state == 'parsed',
            'exchange_supported': row['exchange'] in (identity._STOCK_EXCHANGES if table == 'stocks' else identity._FUND_EXCHANGES),
            'exchange_mic_shape': type(mic) is str and re.fullmatch('[A-Z0-9]{4}', mic) is not None,
            'category_supported': row['category'].casefold() in (identity._COMMON_CATEGORIES if table == 'stocks' else {'etf'}),
            'currency_usd': row['currency'] == 'USD', 'delisted_shape': row['isdelisted'] in ('Y', 'N')}
        require(bool(routes.current._quality(row, table, tokens)) == all(shape.values()), 'route_record')
        states.update({key: _state(value) for key, value in shape.items()})
        start, end, updated = (_date(row[field]) for field in ('firstpricedate', 'lastpricedate', 'lastupdated'))
        states.update(firstpricedate_valid=_state(start is not None), lastpricedate_valid=_state(end is not None),
            lastupdated_valid=_state(updated is not None), ticker_matches_original=_state(row['ticker'] == ticker))
        if start is not None and end is not None: states['price_interval_ordered'] = _state(start <= end)
        if start is not None and first is not None: states['current_first_covers_required'] = _state(start <= first)
        if end is not None and last is not None: states['current_last_covers_required'] = _state(last <= end)
        if wanted['mic'] is not None: states['mic_matches_original'] = _state(mic == wanted['mic'])
        if wanted['tokens'] is not None and vocabulary_state == 'parsed':
            states['original_tokens_retained'] = _state(set(wanted['tokens']) <= set(tokens))
        for field in ('permaticker', 'figi', 'ticker'):
            collision[field + '_other_rows'] = sum(index != own and other[field] == row[field]
                for index, other in enumerate(rows))
        overlap, poisoned = 0, 0
        for index, other in enumerate(rows):
            if index == own: continue
            parsed, state = routes.current._parsed(other['cusips'])
            if state == 'parsed': overlap += bool(set(parsed) & set(tokens))
            else: poisoned += bool(set(identity._CUSIP_COLLISION_TOKEN.findall(other['cusips'].upper())) & set(tokens))
        collision.update(complete_token_overlap_rows=overlap, malformed_token_overlap_rows=poisoned)
    return {'candidate_count': len(rows), 'candidate_match_counts': matches, 'selected_candidate_count': len(selected),
        'selected_predicates': states, 'local_collision_observations': collision,
        'global_collision_cause': 'not_reconstructible_from_candidate_subset'}


def _disposition(row, *, fund=False):
    require(type(row['disposition']) is str and row['disposition'] in DISPOSITIONS, 'disposition')
    require((row['disposition'] == 'routed' and row['reason'] is None and type(row['route']) is dict
            and set(row['route']) == ROUTE_FIELDS)
        or (row['disposition'] == 'refused' and type(row['reason']) is str and row['reason'] in routes.REASONS and row['route'] is None)
        or (not fund and row['disposition'] == 'outside_window'
            and row['reason'] == 'original_candidate_interval_disjoint' and row['route'] is None), 'disposition')


def _facts(frame, contract, deadline):
    stocks, funds = frame['stocks'], frame['funds']
    require(type(stocks) is list and len(stocks) == EXPECTED_STOCKS
        and type(funds) is list and len(funds) == EXPECTED_FUNDS, 'count')
    try: bindings = routes._bindings([row['binding'] for row in stocks], contract)
    except (ValueError, TypeError, KeyError): raise Refused('binding') from None
    result_stocks, result_funds, candidate_total = [], [], 0
    for index, (row, binding) in enumerate(zip(stocks, bindings, strict=True)):
        _deadline(deadline)
        require(type(row) is dict and set(row) == STOCK_INPUT
            and type(row['binding_ordinal']) is int and row['binding_ordinal'] == index, 'stock_record')
        _disposition(row)
        states, original = _original(binding, row['original_row'])
        try:
            if row['original_row'] is not None: routes._original_identity(binding, row['original_row'])
            original_code = None
        except routes.Refused as error: original_code = routes.finite(error)
        if row['original_row'] is None:
            require(row['reason'] in ('original_row_missing', 'original_row_ambiguous'), 'stock_record')
        elif original_code is not None: require(row['reason'] == original_code, 'stock_record')
        else: require(row['reason'] not in ('original_metadata', 'original_identity', 'original_vocabulary'), 'stock_record')
        if original_code is None and row['original_row'] is not None:
            require(original is not None and row['original_cusip_tokens'] == list(original['tokens']), 'stock_record')
        else: require(row['original_cusip_tokens'] is None, 'stock_record')
        first, last = max(routes.PRICE_FIRST, binding['candidate_first_session']), min(routes.PRICE_LAST, binding['candidate_last_session'])
        if original_code is None and row['original_row'] is not None and first <= last:
            require(row['required_first_date'] == first and row['required_last_date'] == last
                and row['disposition'] != 'outside_window', 'stock_record')
        else:
            require(row['required_first_date'] is row['required_last_date'] is None, 'stock_record')
            if original_code is None and row['original_row'] is not None:
                require(row['disposition'] == 'outside_window' and first > last, 'stock_record')
        comparison = original or {'permaticker': None, 'figi': binding['composite_figi'],
            'ticker': binding['diagnostic_current_ticker'], 'mic': binding['diagnostic_exchange_mic'], 'tokens': None}
        current = _current(row['current_candidate_rows'], table='stocks', original=comparison,
            ticker=binding['diagnostic_current_ticker'], first=row['required_first_date'], last=row['required_last_date'], deadline=deadline)
        candidate_total += current['candidate_count']; require(candidate_total <= routes.MAX_CANDIDATE_ROWS, 'frame')
        if row['route'] is not None:
            route = row['route']
            require(route.get('security_id') == binding['security_id'] and route.get('route_key') == binding['security_id']
                and route.get('source_binding_sha256') == binding['row_sha256']
                and route.get('current_metadata_row') in row['current_candidate_rows']
                and route['table'] == 'stocks' and current['selected_candidate_count'] == 1
                and all(state == 'pass' for state in current['selected_predicates'].values())
                and route['required_first_date'] == row['required_first_date']
                and route['required_last_date'] == row['required_last_date'], 'route_record')
            require(route['current_cusip_tokens'] == list(routes.current.parse_vocabulary(route['current_metadata_row']['cusips']))
                and route['current_exchange_mic'] == _mic(route['current_metadata_row'], 'stocks'), 'route_record')
        result_stocks.append({'binding_ordinal': index, 'binding': binding, 'disposition': row['disposition'],
            'reason': row['reason'], 'required_first_date': row['required_first_date'],
            'required_last_date': row['required_last_date'], 'original_predicates': states, 'current_evidence': current})
    for index, row in enumerate(funds):
        _deadline(deadline)
        require(type(row) is dict and set(row) == FUND_INPUT and type(row['fund_ordinal']) is int
            and row['fund_ordinal'] == index and row['ticker'] == routes.current.ETF_TICKERS[index], 'fund_record')
        _disposition(row, fund=True)
        current = _current(row['current_candidate_rows'], table='funds', original=None, ticker=row['ticker'],
            first=routes.PRICE_FIRST, last=routes.PRICE_LAST, deadline=deadline)
        candidate_total += current['candidate_count']; require(candidate_total <= routes.MAX_CANDIDATE_ROWS, 'frame')
        if row['route'] is not None:
            require(row['route'].get('security_id') is None
                and row['route'].get('route_key') == 'own-etf-' + row['ticker']
                and row['route'].get('current_metadata_row') in row['current_candidate_rows']
                and row['route']['table'] == 'funds' and current['selected_candidate_count'] == 1
                and all(state == 'pass' for key, state in current['selected_predicates'].items()
                    if key not in ('mic_matches_original', 'original_tokens_retained'))
                and row['route']['source_binding_sha256'] is None
                and row['route']['required_first_date'] == routes.PRICE_FIRST
                and row['route']['required_last_date'] == routes.PRICE_LAST, 'route_record')
            require(row['route']['current_cusip_tokens'] == list(routes.current.parse_vocabulary(row['route']['current_metadata_row']['cusips']))
                and row['route']['current_exchange_mic'] == _mic(row['route']['current_metadata_row'], 'funds'), 'route_record')
        result_funds.append({'fund_ordinal': index, 'ticker': row['ticker'], 'disposition': row['disposition'],
            'reason': row['reason'], 'required_first_date': routes.PRICE_FIRST,
            'required_last_date': routes.PRICE_LAST, 'current_evidence': current})
    return result_stocks, result_funds


def _tallies(stocks, funds):
    dispositions, reasons, details, categories = {}, {}, {}, Counter()
    for table, rows in (('stocks', stocks), ('funds', funds)):
        dispositions[table] = dict(sorted(Counter(row['disposition'] for row in rows).items()))
        reasons[table] = dict(sorted(Counter(row['reason'] for row in rows if row['disposition'] == 'refused').items()))
        details[table] = {}
        for row in rows:
            if row['disposition'] == 'outside_window': categories['recorded_outside_original_binding_window'] += 1
            if row['disposition'] != 'refused': continue
            reason = row['reason']; original = row.get('original_predicates', {})
            current = row['current_evidence']; selected = current['selected_predicates']
            entry = details[table].setdefault(reason, {'original_failures': Counter(), 'original_unknowns': Counter(),
                'current_failures': Counter(), 'current_unknowns': Counter()})
            for group, predicates in (('original', original), ('current', selected)):
                for key, state in predicates.items():
                    if state != 'pass': entry[group + ('_failures' if state == 'fail' else '_unknowns')][key] += 1
            checks = {
                'original_reconstruction_unavailable': table == 'stocks' and original.get('original_metadata') != 'pass',
                'original_identity_component_mismatch': any(original.get(key) == 'fail' for key in ORIGINAL_FIELDS[3:10]),
                'original_currency_not_usd': original.get('original_currency_usd') == 'fail',
                'original_raw_candidate_interval_mismatch': any(original.get(key) == 'fail' for key in ORIGINAL_FIELDS[11:13]),
                'current_ticker_changed': selected['ticker_matches_original'] == 'fail',
                'current_exchange_mic_changed': selected['mic_matches_original'] == 'fail',
                'current_table_mismatch': selected['table_supported'] == 'fail',
                'current_category_unsupported': selected['category_supported'] == 'fail',
                'current_currency_not_usd': selected['currency_usd'] == 'fail',
                'current_exchange_unsupported': selected['exchange_supported'] == 'fail',
                'current_identifier_or_vocabulary_shape': any(selected[key] == 'fail' for key in
                    ('permaticker_shape', 'ticker_shape', 'figi_shape', 'cusip_vocabulary')),
                'current_metadata_date_invalid': any(selected[key] == 'fail' for key in
                    ('firstpricedate_valid', 'lastpricedate_valid', 'lastupdated_valid', 'price_interval_ordered')),
                'current_first_after_required_geometry': selected['current_first_covers_required'] == 'fail',
                'current_last_before_required_geometry': selected['current_last_covers_required'] == 'fail',
                'current_perma_figi_no_intersection': table == 'stocks' and current['candidate_match_counts']['perma_and_figi'] == 0,
                'current_same_perma_only': table == 'stocks' and current['candidate_match_counts']['permaticker'] is not None
                    and current['candidate_match_counts']['permaticker'] > 0
                    and current['candidate_match_counts']['perma_and_figi'] == 0,
                'current_same_figi_only': table == 'stocks' and current['candidate_match_counts']['figi'] is not None
                    and current['candidate_match_counts']['figi'] > 0
                    and current['candidate_match_counts']['perma_and_figi'] == 0,
                'current_same_ticker_only': table == 'stocks' and current['candidate_match_counts']['ticker'] > 0
                    and current['candidate_match_counts']['perma_and_figi'] == 0,
                'current_candidate_ambiguous': current['selected_candidate_count'] > 1,
                'candidate_subset_empty': current['candidate_count'] == 0,
                'local_candidate_collision_seen': any(value is not None and value > 0
                    for value in current['local_collision_observations'].values()),
                'global_collision_index_cause_unknown': reason == 'current_collision'}
            for key, value in checks.items():
                if value: categories[key] += 1
        details[table] = {reason: {group: dict(sorted(counts.items())) for group, counts in value.items()}
            for reason, value in sorted(details[table].items())}
    return dispositions, reasons, details, dict(sorted(categories.items()))


class PrivateEvidence:
    __slots__ = ('_raw',)
    def __init__(self, record):
        raw = canonical(record); require(0 < len(raw) <= MAX_PRIVATE_BYTES, 'private_record')
        object.__setattr__(self, '_raw', raw)
    def __setattr__(self, name, value): raise TypeError('private evidence is immutable')
    def __repr__(self): return '<PrivateEvidence redacted; supplied diagnostics only>'
    def __reduce_ex__(self, protocol): raise TypeError('private evidence needs an explicitly private export')
    def private_record(self): return json.loads(self._raw)


def inspect(raw_frame, *, expected_summary, deadline=None):
    """Inspect the exact supplied AA frame; expected_summary is routing_summary only."""
    _deadline(deadline); contract = _routing_summary(expected_summary)
    pin = {'byte_count': expected_summary['private_payload_byte_count'], 'sha256': expected_summary['private_payload_sha256']}
    require(type(raw_frame) is bytes and len(raw_frame) == pin['byte_count'] and sha(raw_frame) == pin['sha256'], 'frame_pin')
    frame = _decode(raw_frame, deadline)
    require(set(frame) == {'schema', 'binding_contract', 'price_window', 'stocks', 'funds'}
        and frame['schema'] == routes.PRIVATE_SCHEMA and frame['binding_contract'] == contract
        and frame['price_window'] == [routes.PRICE_FIRST, routes.PRICE_LAST], 'frame')
    stocks, funds = _facts(frame, contract, deadline)
    dispositions, reasons, details, categories = _tallies(stocks, funds)
    require(dispositions == expected_summary['disposition_counts'] and reasons == expected_summary['refusal_counts'], 'count')
    private = PrivateEvidence({'schema': PRIVATE_SCHEMA, 'frame_pin': pin,
        'routing_summary_sha256': sha(canonical(expected_summary)), 'binding_contract': contract, 'stocks': stocks, 'funds': funds})
    summary = {'schema': SCHEMA, 'scope': 'supplied_route_component_diagnostics_not_source_price_or_membership_admission',
        'frame_pin': pin, 'routing_summary_sha256': sha(canonical(expected_summary)), 'binding_contract': contract,
        'disposition_counts': dispositions, 'refusal_counts': reasons, 'per_reason_component_counts': details,
        'quality_category_counts': categories, 'private_evidence_byte_count': len(private._raw),
        'private_evidence_sha256': sha(private._raw)}
    _deadline(deadline)
    return validate_summary(summary), private


def validate_summary(value):
    keys = {'schema', 'scope', 'frame_pin', 'routing_summary_sha256', 'binding_contract',
        'disposition_counts', 'refusal_counts', 'per_reason_component_counts', 'quality_category_counts',
        'private_evidence_byte_count', 'private_evidence_sha256'}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
        and value['scope'] == 'supplied_route_component_diagnostics_not_source_price_or_membership_admission'
        and _pin(value['frame_pin'], MAX_FRAME_BYTES) and _hash(value['routing_summary_sha256'])
        and _pin({'byte_count': value['private_evidence_byte_count'], 'sha256': value['private_evidence_sha256']}, MAX_PRIVATE_BYTES), 'summary')
    try: contract = routes._contract(value['binding_contract'])
    except (ValueError, TypeError): raise Refused('summary') from None
    require(contract['binding_count'] == EXPECTED_STOCKS, 'summary')
    for key in ('disposition_counts', 'refusal_counts', 'per_reason_component_counts'):
        require(type(value[key]) is dict and set(value[key]) == {'stocks', 'funds'}, 'summary')
    for table, total in (('stocks', EXPECTED_STOCKS), ('funds', EXPECTED_FUNDS)):
        d, r, detail = (value[key][table] for key in ('disposition_counts', 'refusal_counts', 'per_reason_component_counts'))
        require(type(d) is dict and set(d) <= DISPOSITIONS and all(type(n) is int and n > 0 for n in d.values())
            and sum(d.values()) == total and type(r) is dict and set(r) <= routes.REASONS
            and all(type(n) is int and n > 0 for n in r.values()) and sum(r.values()) == d.get('refused', 0)
            and type(detail) is dict and set(detail) == set(r), 'summary')
        for reason, groups in detail.items():
            require(type(groups) is dict and set(groups) == {'original_failures', 'original_unknowns',
                'current_failures', 'current_unknowns'}, 'summary')
            for group, counts in groups.items():
                fields = ORIGINAL_FIELDS if group.startswith('original') else CURRENT_FIELDS
                require(type(counts) is dict and set(counts) <= set(fields)
                    and all(type(n) is int and 0 < n <= r[reason] for n in counts.values()), 'summary')
            for prefix, fields in (('original', ORIGINAL_FIELDS), ('current', CURRENT_FIELDS)):
                require(all(groups[prefix + '_failures'].get(field, 0)
                    + groups[prefix + '_unknowns'].get(field, 0) <= r[reason] for field in fields), 'summary')
    require(type(value['quality_category_counts']) is dict and set(value['quality_category_counts']) <= CATEGORIES
        and all(type(n) is int and 0 < n <= EXPECTED_STOCKS + EXPECTED_FUNDS
            for n in value['quality_category_counts'].values()) and len(canonical(value)) <= MAX_SUMMARY_BYTES, 'summary')
    require(value['quality_category_counts'].get('global_collision_index_cause_unknown', 0)
        == sum(value['refusal_counts'][table].get('current_collision', 0) for table in ('stocks', 'funds'))
        and value['quality_category_counts'].get('recorded_outside_original_binding_window', 0)
        == sum(value['disposition_counts'][table].get('outside_window', 0) for table in ('stocks', 'funds')), 'summary')
    return json.loads(canonical(value))


def _validate_current(value):
    require(type(value) is dict and set(value) == {'candidate_count', 'candidate_match_counts',
        'selected_candidate_count', 'selected_predicates', 'local_collision_observations', 'global_collision_cause'}
        and _count(value['candidate_count'], routes.MAX_CANDIDATE_ROWS_PER_ITEM)
        and _count(value['selected_candidate_count'], value['candidate_count'])
        and type(value['candidate_match_counts']) is dict and set(value['candidate_match_counts']) == set(MATCH_FIELDS)
        and all(n is None or _count(n, value['candidate_count']) for n in value['candidate_match_counts'].values())
        and type(value['selected_predicates']) is dict and set(value['selected_predicates']) == set(CURRENT_FIELDS)
        and all(type(state) is str and state in STATES for state in value['selected_predicates'].values())
        and type(value['local_collision_observations']) is dict and set(value['local_collision_observations']) == set(LOCAL_COLLISIONS)
        and all(n is None or _count(n, value['candidate_count']) for n in value['local_collision_observations'].values())
        and value['global_collision_cause'] == 'not_reconstructible_from_candidate_subset', 'private_record')


def validate_private_record(record, *, expected_summary):
    summary = validate_summary(expected_summary)
    require(type(record) is dict and set(record) == {'schema', 'frame_pin', 'routing_summary_sha256',
        'binding_contract', 'stocks', 'funds'} and record['schema'] == PRIVATE_SCHEMA
        and record['frame_pin'] == summary['frame_pin'] and record['routing_summary_sha256'] == summary['routing_summary_sha256']
        and record['binding_contract'] == summary['binding_contract']
        and type(record['stocks']) is list and len(record['stocks']) == EXPECTED_STOCKS
        and type(record['funds']) is list and len(record['funds']) == EXPECTED_FUNDS, 'private_record')
    try: routes._bindings([row['binding'] for row in record['stocks']], record['binding_contract'])
    except (ValueError, TypeError, KeyError): raise Refused('private_record') from None
    for table, rows, keys in (('stocks', record['stocks'], STOCK_OUTPUT), ('funds', record['funds'], FUND_OUTPUT)):
        for index, row in enumerate(rows):
            ordinal = 'binding_ordinal' if table == 'stocks' else 'fund_ordinal'
            require(type(row) is dict and set(row) == keys and type(row[ordinal]) is int and row[ordinal] == index
                and row['disposition'] in DISPOSITIONS
                and ((row['disposition'] == 'refused' and row['reason'] in routes.REASONS)
                    or (row['disposition'] == 'routed' and row['reason'] is None)
                    or (table == 'stocks' and row['disposition'] == 'outside_window'
                        and row['reason'] == 'original_candidate_interval_disjoint'))
                and all(value is None or _date(value) is not None for value in
                    (row['required_first_date'], row['required_last_date'])), 'private_record')
            if table == 'stocks':
                require(type(row['original_predicates']) is dict and set(row['original_predicates']) == set(ORIGINAL_FIELDS)
                    and all(type(state) is str and state in STATES for state in row['original_predicates'].values()), 'private_record')
            else: require(row['ticker'] == routes.current.ETF_TICKERS[index], 'private_record')
            _validate_current(row['current_evidence'])
    require(_tallies(record['stocks'], record['funds']) == (summary['disposition_counts'], summary['refusal_counts'],
        summary['per_reason_component_counts'], summary['quality_category_counts']), 'private_record')
    raw = canonical(record)
    require(len(raw) == summary['private_evidence_byte_count'] and sha(raw) == summary['private_evidence_sha256'], 'private_pin')
    return json.loads(raw)


def profile_record():
    return {'schema': SCHEMA, 'private_schema': PRIVATE_SCHEMA, 'expected_stock_count': EXPECTED_STOCKS,
        'expected_fund_count': EXPECTED_FUNDS, 'maximum_frame_bytes': MAX_FRAME_BYTES,
        'maximum_private_evidence_bytes': MAX_PRIVATE_BYTES, 'maximum_summary_bytes': MAX_SUMMARY_BYTES,
        'maximum_JSON_depth': MAX_JSON_DEPTH, 'maximum_JSON_nodes': MAX_JSON_NODES,
        'maximum_JSON_separators': MAX_JSON_SEPARATORS, 'original_component_fields': list(ORIGINAL_FIELDS),
        'current_component_fields': list(CURRENT_FIELDS), 'finite_quality_categories': sorted(CATEGORIES),
        'expected_summary': 'externally_authenticated_AA_routing_summary_v2_not_full_worker_summary',
        'header_source_and_actual_exit_authentication': 'parent_owned_before_supplied_frame_use',
        'global_collision_cause': 'not_reconstructible_from_candidate_subset',
        'binding_interval_diagnostics': 'original_geometry_not_runtime_membership_or_holding_lifetime',
        'result': 'metadata_diagnostics_no_price_selection_source_membership_rights_or_trading_admission'}
