"""Pure all-binding original-evidence/current-route cross-check.

The caller authenticates the complete original catalog, original CSV and both
current metadata responses. This helper inspects only supplied bounded values;
it never reads a file, credential, provider or QC object. Its private payload
retains every binding, including refusals and disjoint candidate intervals.
The caller must authenticate the exact original 291-byte CSV header, its
SHA256 and ordered manifest columns before supplying rows. The bounded shape
predicate below knows only fields used by the frozen evidence reconstruction;
it never guesses the names of other original columns. All 28 names/values are
retained unchanged in the original source-row and identity evidence hashes.
Current routes and interval predicates are not source, price, rights, PIT or
historical identity admission, and are never an operational capability.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import re

from scripts import arv2_r298_sharadar_current_routes as current
from scripts import arv2_r298_reference_ticker_evidence as original


SCHEMA = 'arv2-r298-sharadar-all-routes-v2'
PRIVATE_SCHEMA = 'arv2-r298-sharadar-all-routes-private-v2'
PRICE_FIRST, PRICE_LAST = '2020-12-31', '2026-10-13'
MAX_BINDINGS, MAX_ORIGINAL_ROWS = 100000, 250000
MAX_ORIGINAL_BYTES, MAX_BINDING_BYTES = 64 * 1024 * 1024, 64 * 1024 * 1024
MAX_PRIVATE_BYTES = 128 * 1024 * 1024
MAX_CANDIDATE_ROWS_PER_ITEM, MAX_CANDIDATE_ROWS = 4096, 100000
MAX_CANDIDATE_BYTES = 128 * 1024 * 1024
PRIVATE_ENVELOPE_RESERVE = 4096
ORIGINAL_FIELD_COUNT, MAX_COLUMN_CHARS = 28, 128
# original._metadata reads these eleven fields; _original_identity additionally
# requires currency. original._source_bytes hashes every supplied field.
REQUIRED_ORIGINAL_FIELDS = frozenset(('table', 'ticker', 'permaticker', 'exchange',
    'category', 'figi', 'cusips', 'currency', 'sector', 'industry',
    'firstpricedate', 'lastpricedate'))
ORIGINAL_HEADER_BYTES = 291
ORIGINAL_HEADER_SHA256 = 'c9186ed191f4e51d5142287016dc99e3f80ecebed49aa63c3fa1ecf09e5d26f7'
FROZEN_V1_SHA256 = 'd3a7ab5fd486d548ec90d27532741cd8e0194863bd548baa53c0fd8c765bdd83'
CONTRACT_FIELDS = frozenset(('binding_count', 'binding_stream_sha256',
    'security_master_admission_sha256', 'admitted_mapping_inventory_sha256'))
REASONS = frozenset(('original_row_missing', 'original_row_ambiguous',
    'original_metadata', 'original_identity', 'original_vocabulary',
    'current_identity_missing', 'current_identity_ambiguous', 'current_identity_changed',
    'current_shape', 'current_collision', 'current_vocabulary_changed', 'current_interval'))
FINITE = REASONS | frozenset(('contract', 'binding', 'binding_inventory',
    'binding_stream', 'original_rows', 'original_bound', 'current_catalog',
    'private_payload', 'candidate_bound', 'routes_incomplete', 'unknown'))
canonical, sha = current.canonical, current.sha


class Refused(ValueError):
    """Closed predicates only; source values never occur in messages."""


def require(value, code):
    if not value:
        raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def valid_original_columns(columns):
    """Bounded shape only, never exact-header authentication or admission."""
    return (type(columns) in (tuple, list) and len(columns) == ORIGINAL_FIELD_COUNT
        and all(type(name) is str and 0 < len(name) <= MAX_COLUMN_CHARS
            and name.isascii() and all(32 <= ord(character) < 127 for character in name)
            for name in columns)
        and len(set(columns)) == ORIGINAL_FIELD_COUNT
        and REQUIRED_ORIGINAL_FIELDS <= set(columns))


def _contract(value):
    require(type(value) is dict and set(value) == CONTRACT_FIELDS
        and all(type(key) is str for key in value)
        and type(value['binding_count']) is int and 0 < value['binding_count'] <= MAX_BINDINGS
        and all(_hash(value[key]) for key in CONTRACT_FIELDS - {'binding_count'}), 'contract')
    return dict(value)


def _bindings(supplied, contract):
    require(type(supplied) in (tuple, list) and len(supplied) == contract['binding_count'], 'binding_inventory')
    figi = original.identity_join.figi
    result, digest, size = [], hashlib.sha256(), 0
    for supplied_row in supplied:
        require(type(supplied_row) is dict and set(supplied_row) == figi._INPUT_FIELDS
            and all(type(key) is str for key in supplied_row)
            and all(value is None or type(value) in (str, int, bool) for value in supplied_row.values())
            and all(len(value) <= original.MAX_FIELD_CHARS for value in supplied_row.values()
                if type(value) is str), 'binding')
        try:
            row = figi._input_row(supplied_row, contract['security_master_admission_sha256'])
            raw = figi._canonical(row)
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise Refused('binding') from None
        size += len(raw)
        require(size <= MAX_BINDING_BYTES, 'binding_inventory')
        require(row['admitted_mapping_count'] == len(supplied)
            and row['admitted_mapping_inventory_sha256'] == contract['admitted_mapping_inventory_sha256'],
            'binding_inventory')
        digest.update(raw)
        result.append(row)
    require(result == sorted(result, key=lambda row: row['security_id'])
        and all(len({row[field] for row in result}) == len(result) for field in
            ('security_id', 'composite_figi', 'row_sha256')), 'binding_inventory')
    require(digest.hexdigest() == contract['binding_stream_sha256'], 'binding_stream')
    return result


def _originals(supplied):
    require(type(supplied) in (tuple, list) and 0 < len(supplied) <= MAX_ORIGINAL_ROWS, 'original_rows')
    index, digest, size, columns = defaultdict(list), hashlib.sha256(), 0, None
    for supplied_row in supplied:
        require(type(supplied_row) is dict
            and valid_original_columns(tuple(supplied_row)), 'original_rows')
        if columns is None:
            columns = frozenset(supplied_row)
        require(frozenset(supplied_row) == columns, 'original_rows')
        try:
            raw = original._source_bytes(supplied_row)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise Refused('original_rows') from None
        size += len(raw)
        require(size <= MAX_ORIGINAL_BYTES, 'original_bound')
        index[sha(raw)].append(dict(supplied_row))
        digest.update(raw)
    return index, digest.hexdigest()


def _original_identity(binding, source):
    # Reproduce the historical evidence semantics, including its ORIGINAL
    # comma parser. The separate complete parser below controls new routing.
    try:
        table, ticker, perma, figi, exchange, mic, old_tokens, first, last = original._metadata(source)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise Refused('original_metadata') from None
    evidence = {'permaticker': perma, 'composite_figi': figi, 'source_table': table,
        'ticker': ticker, 'cusips': list(old_tokens), 'exchange': exchange, 'exchange_mic': mic,
        'firstpricedate': first, 'lastpricedate': last, 'source_row_sha256': binding['source_row_sha256'],
        'availability_semantics': original.composer.TICKERS_AVAILABILITY}
    evidence_pin = sha(original.composer.canonical_json_bytes(evidence))
    reconstructed = {'security_id': original.composer._safe_component('sharadar-composite-figi', figi),
        'issuer_id': original.composer._safe_component('sharadar-permaticker', perma),
        'composite_figi': figi, 'listing_id': 'sharadar-listing-' + evidence_pin[:24],
        'diagnostic_current_ticker': ticker, 'diagnostic_exchange_mic': mic,
        'identity_evidence_sha256': evidence_pin}
    require(all(binding[key] == value for key, value in reconstructed.items())
        and source['currency'] == 'USD'
        and first <= binding['candidate_first_session']
        and (last is None or binding['candidate_last_session'] <= last), 'original_identity')
    try:
        tokens = current.parse_vocabulary(source['cusips'])
    except current.vocabulary.Refused:
        raise Refused('original_vocabulary') from None
    require(tokens, 'original_vocabulary')
    return perma, figi, ticker, mic, tokens


def _interval(row, first, last):
    try:
        start = current.previous._date(row['firstpricedate'], 'metadata_interval')
        end = current.previous._date(row['lastpricedate'], 'metadata_interval')
        current.previous._date(row['lastupdated'], 'metadata_interval')
        require(start <= current.previous._date(first, 'metadata_interval')
            <= current.previous._date(last, 'metadata_interval') <= end, 'current_interval')
    except current.previous.Refused:
        raise Refused('current_interval') from None


def _current_route(built, *, table, perma=None, figi=None, ticker, mic=None,
                   original_tokens=None, first, last):
    _, records, indexes, tokens, poisoned, _ = built
    if table == 'stocks':
        by_perma = set(indexes['permaticker'].get(perma, ()))
        by_figi = set(indexes['figi'].get(figi, ()))
        candidates = by_perma & by_figi
        require(candidates, 'current_identity_missing')
        require(len(candidates) == 1, 'current_identity_ambiguous')
    else:
        candidates = {owner for owner in indexes['ticker'].get(ticker, ()) if owner[0] == 'funds'}
        require(candidates, 'current_identity_missing')
        require(len(candidates) == 1, 'current_identity_ambiguous')
    own = next(iter(candidates)); record = records[own]; row = record['row']
    require(own[0] == table and row['ticker'] == ticker, 'current_identity_changed')
    require(record['quality'] and record['state'] == 'parsed', 'current_shape')
    current_mic = current.previous.composer._SHARADAR_EXCHANGE_TO_MIC.get(row['exchange'].upper())
    if table == 'funds':
        current_mic = {'NYSEARCA': 'ARCX', 'NYSE ARCA': 'ARCX', 'BATS': 'BATS'}.get(row['exchange'].upper(), current_mic)
    require(mic is None or current_mic == mic, 'current_identity_changed')
    require(all(indexes[field].get(row[field], set()) == {own} for field in ('permaticker', 'figi', 'ticker')),
        'current_collision')
    require(all(tokens[token] == {own} and not poisoned.get(token) for token in record['tokens']),
        'current_collision')
    if original_tokens is not None:
        require(set(original_tokens) <= set(record['tokens']), 'current_vocabulary_changed')
        # Original tokens must not be owned or poisoned by ANY returned row,
        # including tokens omitted from this route's new current vocabulary.
        require(all(tokens.get(token) == {own} and not poisoned.get(token) for token in original_tokens),
            'current_collision')
    _interval(row, first, last)
    return {'table': table, 'current_metadata_row': dict(row),
        'current_cusip_tokens': list(record['tokens']), 'current_exchange_mic': current_mic,
        'required_first_date': first, 'required_last_date': last}


def _candidate_rows(built, budget, base_bytes, *, figi=None, ticker, perma=None):
    """PRIVATE diagnostic candidates, including disagreeing/colliding rows."""
    _, records, indexes, _, _, _ = built
    owners = set()
    for field, value in (('ticker', ticker), ('figi', figi), ('permaticker', perma)):
        if value is None:
            continue
        for owner in indexes[field].get(value, ()):
            owners.add(owner)
            require(len(owners) <= MAX_CANDIDATE_ROWS_PER_ITEM
                and budget['candidate_rows'] + len(owners) <= MAX_CANDIDATE_ROWS, 'candidate_bound')
    # Count/measure ALL diagnostic candidates before copying any of them.
    # The base item contains [] for this list, so each row plus one comma is
    # a conservative bound on its additional canonical representation.
    extra = 0
    require(budget['item_bytes'] + base_bytes + 1
        <= MAX_PRIVATE_BYTES - PRIVATE_ENVELOPE_RESERVE, 'private_payload')
    ordered = sorted(owners)
    for owner in ordered:
        size = len(canonical(records[owner]['row'])) + 1
        extra += size
        require(budget['candidate_bytes'] + extra <= MAX_CANDIDATE_BYTES, 'candidate_bound')
        require(budget['item_bytes'] + base_bytes + extra + 1
            <= MAX_PRIVATE_BYTES - PRIVATE_ENVELOPE_RESERVE, 'private_payload')
    budget['candidate_rows'] += len(ordered)
    budget['candidate_bytes'] += extra
    return [dict(records[owner]['row']) for owner in ordered]


def _finish_item(item, built, budget, *, figi=None, ticker, perma=None):
    """Bound the complete growing private graph before adding another item."""
    base = len(canonical(item))
    item['current_candidate_rows'] = _candidate_rows(built, budget, base,
        figi=figi, ticker=ticker, perma=perma)
    size = len(canonical(item)) + 1
    require(budget['item_bytes'] + size <= MAX_PRIVATE_BYTES - PRIVATE_ENVELOPE_RESERVE, 'private_payload')
    budget['item_bytes'] += size
    return item


def _metadata_rows(value, table):
    if type(value) is bytes:
        return current.metadata(value, table, 16 * 1024 * 1024)[0]
    return value


class PrivateRoutes:
    """Immutable supplied-data result; callers must keep explicit exports private."""
    __slots__ = ('_raw',)

    def __init__(self, record):
        raw = canonical(record)
        require(len(raw) <= MAX_PRIVATE_BYTES, 'private_payload')
        object.__setattr__(self, '_raw', raw)

    def __setattr__(self, name, value):
        raise TypeError('private routes are immutable')

    def __repr__(self):
        return '<PrivateRoutes redacted; supplied data only; no operational authority>'

    def __reduce_ex__(self, protocol):
        raise TypeError('private routes require an explicitly private export')

    def private_record(self):
        """Fresh PRIVATE copy. Never print, return through public IPC or log it."""
        return json.loads(self._raw)

    def price_routes(self):
        """PRIVATE routes or refusal; never converts missing routes to eligibility.

        Disjoint original candidate intervals remain in private_record(). A
        consumer must bind candidate eligibility/no-initial-stock semantics and
        independently extend required intervals for prior-session boundaries.
        These rows are inert data, not permission for acquisition or execution.
        """
        payload = self.private_record()
        require(not any(row['disposition'] == 'refused' for row in payload['stocks'] + payload['funds']),
            'routes_incomplete')
        return [dict(row['route']) for row in payload['stocks'] + payload['funds'] if row['disposition'] == 'routed']


def join(binding_rows, original_tickers_rows, stocks, funds, *, binding_contract):
    """Return a closed count/hash summary and a separate private full payload.

    binding_contract binds the genuine full ASCII-JSONL catalog supplied by the
    caller. Original source-row hashes and identity evidence are checked for
    every binding. Current response authentication remains the caller's job.
    """
    contract = _contract(binding_contract)
    bindings = _bindings(binding_rows, contract)
    original_index, original_rows_pin = _originals(original_tickers_rows)
    try:
        built = current._build(_metadata_rows(stocks, 'stocks'), _metadata_rows(funds, 'funds'))
        catalog = current.validate_receipt(current._receipt(built))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise Refused('current_catalog') from None
    private_stocks, private_funds = [], []
    budget = {'candidate_rows': 0, 'candidate_bytes': 0, 'item_bytes': 0}
    for ordinal, binding in enumerate(bindings):
        item = {'binding_ordinal': ordinal, 'binding': dict(binding), 'original_row': None,
            'original_cusip_tokens': None, 'required_first_date': None, 'required_last_date': None,
            'current_candidate_rows': [],
            'disposition': 'refused', 'reason': None, 'route': None}
        perma = None
        try:
            matches = original_index.get(binding['source_row_sha256'], ())
            require(matches, 'original_row_missing')
            require(len(matches) == 1, 'original_row_ambiguous')
            item['original_row'] = dict(matches[0])
            perma, figi, ticker, mic, original_tokens = _original_identity(binding, matches[0])
            item['original_cusip_tokens'] = list(original_tokens)
            first = max(PRICE_FIRST, binding['candidate_first_session'])
            last = min(PRICE_LAST, binding['candidate_last_session'])
            if first > last:
                item.update(disposition='outside_window', reason='original_candidate_interval_disjoint')
            else:
                item.update(required_first_date=first, required_last_date=last)
                route = _current_route(built, table='stocks', perma=perma, figi=figi,
                    ticker=ticker, mic=mic, original_tokens=original_tokens, first=first, last=last)
                route.update(route_key=binding['security_id'], security_id=binding['security_id'],
                    source_binding_sha256=binding['row_sha256'])
                item.update(disposition='routed', reason=None, route=route)
        except Refused as error:
            code = finite(error)
            require(code in REASONS, 'private_payload')
            item['reason'] = code
        private_stocks.append(_finish_item(item, built, budget, figi=binding['composite_figi'],
            ticker=binding['diagnostic_current_ticker'], perma=perma))
    for ordinal, ticker in enumerate(current.ETF_TICKERS):
        item = {'fund_ordinal': ordinal, 'ticker': ticker, 'current_candidate_rows': [],
            'disposition': 'refused', 'reason': None, 'route': None}
        try:
            route = _current_route(built, table='funds', ticker=ticker, first=PRICE_FIRST, last=PRICE_LAST)
            # This is a private price-route key, never an authenticated QC SID.
            route.update(route_key='own-etf-' + ticker, security_id=None, source_binding_sha256=None)
            item.update(disposition='routed', reason=None, route=route)
        except Refused as error:
            code = finite(error)
            require(code in REASONS, 'private_payload')
            item['reason'] = code
        private_funds.append(_finish_item(item, built, budget, ticker=ticker))
    payload = PrivateRoutes({'schema': PRIVATE_SCHEMA, 'binding_contract': contract,
        'price_window': [PRICE_FIRST, PRICE_LAST], 'stocks': private_stocks, 'funds': private_funds})
    counts = {table: dict(sorted(Counter(item['disposition'] for item in rows).items()))
        for table, rows in (('stocks', private_stocks), ('funds', private_funds))}
    refusals = {table: dict(sorted(Counter(item['reason'] for item in rows if item['disposition'] == 'refused').items()))
        for table, rows in (('stocks', private_stocks), ('funds', private_funds))}
    summary = {'schema': SCHEMA, 'scope': 'supplied_current_route_crosscheck_not_admission',
        'binding_contract': dict(contract), 'price_window': [PRICE_FIRST, PRICE_LAST],
        'original_row_count': len(original_tickers_rows), 'original_rows_digest': original_rows_pin,
        'metadata_rows_sha256': dict(catalog['metadata_rows_sha256']),
        'metadata_row_counts': {table: catalog['tables'][table]['row_count'] for table in current.TABLES},
        'catalog_unknown_vocabulary_row_count': catalog['unknown_vocabulary_row_count'],
        'catalog_collision_group_counts': {key: catalog[key] for key in (
            'permaticker_collision_groups', 'figi_collision_groups', 'ticker_collision_groups',
            'complete_token_collision_groups', 'malformed_overlap_token_groups')},
        'disposition_counts': counts, 'refusal_counts': refusals,
        'private_payload_byte_count': len(payload._raw), 'private_payload_sha256': sha(payload._raw)}
    return summary, payload


def profile_record():
    return {'schema': SCHEMA, 'private_schema': PRIVATE_SCHEMA,
        'purpose': 'all_supplied_original_bindings_and_eight_ETFs_current_route_crosscheck',
        'price_window': [PRICE_FIRST, PRICE_LAST], 'fixed_fund_count': len(current.ETF_TICKERS),
        'operational_stock_count_requires_separate_freeze': 6151,
        'maximum_binding_rows': MAX_BINDINGS, 'maximum_original_rows': MAX_ORIGINAL_ROWS,
        'maximum_original_canonical_bytes': MAX_ORIGINAL_BYTES, 'maximum_binding_bytes': MAX_BINDING_BYTES,
        'frozen_v1_source_sha256': FROZEN_V1_SHA256,
        'original_field_count': ORIGINAL_FIELD_COUNT,
        'maximum_original_column_characters': MAX_COLUMN_CHARS,
        'original_required_fields': sorted(REQUIRED_ORIGINAL_FIELDS),
        'original_column_policy': '28_unique_bounded_ASCII_names_required_evidence_subset_uniform_across_rows',
        'original_unknown_columns': 'names_and_values_retained_unchanged_in_full_source_hash_not_inferred_or_dropped',
        'caller_original_header_byte_count': ORIGINAL_HEADER_BYTES,
        'caller_original_header_sha256': ORIGINAL_HEADER_SHA256,
        'caller_header_manifest_gate': 'exact_decoder_authenticated_bytes_and_ordered_manifest_columns_before_helper',
        'maximum_private_payload_bytes': MAX_PRIVATE_BYTES,
        'maximum_candidate_rows_per_item': MAX_CANDIDATE_ROWS_PER_ITEM,
        'maximum_aggregate_candidate_rows': MAX_CANDIDATE_ROWS,
        'maximum_aggregate_candidate_canonical_bytes': MAX_CANDIDATE_BYTES,
        'private_envelope_byte_reserve': PRIVATE_ENVELOPE_RESERVE,
        'private_graph_budget': 'incremental_complete_item_canonical_bytes_plus_commas_before_append',
        'candidate_budget': 'count_and_measure_before_copy_never_truncate_or_drop_to_fit',
        'current_metadata_inputs': 'bounded_supplied_rows_or_exact_12field_CSV_bytes',
        'complete_parser_sha256': current.PARSER_SHA256,
        'binding_contract_fields': sorted(CONTRACT_FIELDS), 'named_route_refusals': sorted(REASONS),
        'original_evidence': 'frozen_original_composer_semantics_then_complete_vocabulary_for_new_routing',
        'required_interval': 'original_candidate_interval_intersect_fixed_window_never_current_metadata',
        'current_interval': 'must_cover_required_interval_no_shrinking_or_price_filter',
        'outside_window': 'retained_original_candidate_geometry_not_price_or_universe_eligibility_repair',
        'fund_route_keys': 'local_namespace_not_QC_SID_consumer_must_bind_exact_own_ETF_identity',
        'prior_session_boundary': 'separate_consumer_gate_not_inferred_from_candidate_interval',
        'collision_scope': 'all_current_rows_both_tables_all_tokens_and_refusal_only_poison_tokens',
        'unknown_unrelated_vocabulary': 'retained_unknown_not_global_absence_proof',
        'result': 'private_supplied_data_not_source_price_rights_PIT_QC_or_strategy_admission'}
