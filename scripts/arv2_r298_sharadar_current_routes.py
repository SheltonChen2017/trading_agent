"""Prospective complete-vocabulary current Sharadar probe routing.

Only caller-authenticated supplied rows are inspected. Complete vocabulary
parsing is shared by quality counts and selected routes. Current-vintage
shape/collision observations are not historical identity or price admission.
No filesystem, provider, credential, QC or legacy operational entry point.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import re

from scripts import arv2_r298_sharadar_cusip_syntax as vocabulary
from scripts import arv2_r298_sharadar_eligibility_observation as previous


SCHEMA = 'arv2-r298-sharadar-current-routes-v1'
PARSER_SHA256 = 'cab79cb04bbc0788b37138b74526fdd518b7d0e90ee7ceeca546227f91a7b72b'
FIELDS, ETF_TICKERS, REFERENCE_SESSION = previous.META_FIELDS, previous.ETF_TICKERS, previous.REFERENCE_SESSION
PROBES = (('stocks', 'QCOM'),) + tuple(('funds', ticker) for ticker in ETF_TICKERS)
TABLES = ('stocks', 'funds')
MAX_ROWS, MAX_FIELD_BYTES, MAX_CATALOG_BYTES = 100000, 2048, 32 * 1024 * 1024
FALSE_FLAGS = {**previous.FALSE_FLAGS, 'current_identity_admitted': False, 'historical_master_proven': False,
    'cusip_active_interval_proven': False, 'price_input_admitted': False, 'strategy_input_admitted': False,
    'provider_contact': False, 'qc_contact': False}
FINITE = frozenset(('row_shape', 'catalog_bound', 'table', 'metadata_csv', 'route_missing_or_ambiguous',
    'route_shape', 'route_collision', 'route_interval', 'receipt', 'unknown'))
canonical, sha = previous.canonical, previous.sha


class Refused(ValueError):
    """Finite current-routing refusal; never raw metadata values."""


def require(condition, code):
    if not condition: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def parse_vocabulary(value):
    """The complete prospective parser, not a historical-composer replacement."""
    return vocabulary.parse_cusips(value)


def _parsed(value):
    try: return parse_vocabulary(value), 'parsed'
    except vocabulary.Refused as error:
        return (), 'missing' if vocabulary.finite(error) == 'missing' else 'malformed'


def _row(row):
    require(type(row) is dict and len(row) == len(FIELDS)
        and all(type(key) is str and key in FIELDS for key in row), 'row_shape')
    result = {}
    for key in FIELDS:
        value = row[key]
        require(type(value) is str, 'row_shape')
        try: size = len(value.encode('utf-8'))
        except UnicodeError: raise Refused('row_shape') from None
        require(size <= MAX_FIELD_BYTES and value == value.strip()
            and not any(ord(char) < 32 or ord(char) == 127 for char in value), 'row_shape')
        result[key] = value
    return result


def _table(table):
    require(type(table) is str and table in TABLES, 'table')
    return table


def _quality(row, table, tokens):
    identity, composer = previous.identities, previous.composer
    exchanges = identity._STOCK_EXCHANGES if table == 'stocks' else identity._FUND_EXCHANGES
    categories = identity._COMMON_CATEGORIES if table == 'stocks' else {'etf'}
    mic = composer._SHARADAR_EXCHANGE_TO_MIC.get(row['exchange'].upper())
    if table == 'funds':
        mic = {'NYSEARCA': 'ARCX', 'NYSE ARCA': 'ARCX', 'BATS': 'BATS'}.get(row['exchange'].upper(), mic)
    return bool(row['table'] in (table, 'SEP' if table == 'stocks' else 'SFP')
        and identity._PERMANENT_ID.fullmatch(row['permaticker']) is not None
        and composer._TICKER.fullmatch(row['ticker']) is not None
        and identity._FIGI.fullmatch(row['figi']) is not None and tokens
        and row['exchange'] in exchanges and type(mic) is str and re.fullmatch('[A-Z0-9]{4}', mic)
        and row['category'].casefold() in categories and row['currency'] == 'USD'
        and row['isdelisted'] in ('Y', 'N'))


def route_quality(row, table):
    """Technical row shape; false is retained in catalog counts, not repaired."""
    table, row = _table(table), _row(row)
    tokens, _ = _parsed(row['cusips'])
    return _quality(row, table, tokens)


def metadata(raw, table, maximum):
    """Compatible pure CSV census for a separately versioned future observer."""
    table = _table(table)
    require(type(maximum) is int and 0 < maximum <= 16 * 1024 * 1024, 'catalog_bound')
    try: rows = previous._rows(raw, FIELDS, maximum, MAX_ROWS)
    except previous.Refused: raise Refused('metadata_csv') from None
    require(all(row['table'] in (table, 'SEP' if table == 'stocks' else 'SFP') for row in rows), 'table')
    permas = Counter(row['permaticker'] for row in rows if row['permaticker'])
    tickers = Counter(row['ticker'] for row in rows if row['ticker'])
    missing = {field: sum(not row[field] for row in rows)
        for field in ('permaticker', 'figi', 'cusips', 'exchange', 'category', 'currency')}
    malformed_dates = 0
    for row in rows:
        for field in ('firstpricedate', 'lastpricedate', 'lastupdated'):
            if row[field]:
                try: previous._date(row[field], 'metadata_interval')
                except previous.Refused: malformed_dates += 1
    summary = {'row_count': len(rows), 'duplicate_permaticker_count': sum(count > 1 for count in permas.values()),
        'duplicate_ticker_count': sum(count > 1 for count in tickers.values()), 'missing_field_counts': missing,
        'unsupported_or_incomplete_route_row_count': sum(not route_quality(row, table) for row in rows),
        'invalid_nonempty_date_field_count': malformed_dates}
    return rows, summary, permas, tickers


def _build(stocks, funds):
    rows_by_table, records = {}, {}
    indexes = {field: defaultdict(set) for field in ('permaticker', 'figi', 'ticker')}
    complete_tokens, refusal_tokens = defaultdict(set), defaultdict(set)
    totals, bytes_seen = {}, 0
    for table, supplied in zip(TABLES, (stocks, funds), strict=True):
        require(type(supplied) in (list, tuple) and len(supplied) < MAX_ROWS, 'catalog_bound')
        rows = []
        totals[table] = {'row_count': len(supplied), 'parsed_vocabulary_row_count': 0,
            'missing_vocabulary_row_count': 0, 'malformed_vocabulary_row_count': 0,
            'complete_vocabulary_token_count': 0}
        for index, supplied_row in enumerate(supplied):
            row = _row(supplied_row)
            require(row['table'] in (table, 'SEP' if table == 'stocks' else 'SFP'), 'table')
            bytes_seen += sum(len(value.encode('utf-8')) for value in row.values())
            require(bytes_seen <= MAX_CATALOG_BYTES, 'catalog_bound')
            row_id = (table, index)
            tokens, state = _parsed(row['cusips'])
            # Refusal-only extraction never supplies an admitted route vocabulary.
            poisoned = () if state == 'parsed' else tuple(sorted(set(
                previous.identities._CUSIP_COLLISION_TOKEN.findall(row['cusips'].upper()))))
            records[row_id] = {'row': row, 'tokens': tokens, 'state': state,
                'refusal_tokens': poisoned, 'quality': _quality(row, table, tokens)}
            totals[table][state + '_vocabulary_row_count'] += 1
            totals[table]['complete_vocabulary_token_count'] += len(tokens)
            for field, owners in indexes.items():
                if row[field]: owners[row[field]].add(row_id)
            for token in tokens: complete_tokens[token].add(row_id)
            for token in poisoned: refusal_tokens[token].add(row_id)
            rows.append(row)
        rows_by_table[table] = rows
    return rows_by_table, records, indexes, complete_tokens, refusal_tokens, totals


def _overlaps(owners, own):
    return set(owners) - {own}


def _probe(index, table, ticker, records, indexes, tokens, poisoned):
    candidates = sorted(row_id for row_id in indexes['ticker'].get(ticker, ()) if row_id[0] == table)
    result = {'probe_index': index, 'candidate_count': len(candidates), 'candidate_rows_sha256': sha(canonical(
        [records[row_id]['row'] for row_id in candidates])), 'vocabulary_status': 'not_unique',
        'complete_vocabulary_token_count': None, 'refusal_only_token_count': None,
        'shape_predicates_satisfied': None, 'permaticker_other_rows': None, 'figi_other_rows': None,
        'ticker_other_rows': None, 'same_table_complete_token_overlap_rows': None,
        'cross_table_complete_token_overlap_rows': None, 'malformed_field_overlap_rows': None}
    if len(candidates) == 1:
        own = candidates[0]; record = records[own]; row = record['row']
        complete_owners, poison_owners = set(), set()
        for token in record['tokens']:
            complete_owners |= _overlaps(tokens[token], own)
            poison_owners |= _overlaps(poisoned.get(token, ()), own)
        result.update(vocabulary_status=record['state'],
            complete_vocabulary_token_count=len(record['tokens']), refusal_only_token_count=len(record['refusal_tokens']),
            shape_predicates_satisfied=record['quality'],
            permaticker_other_rows=len(_overlaps(indexes['permaticker'].get(row['permaticker'], ()), own)),
            figi_other_rows=len(_overlaps(indexes['figi'].get(row['figi'], ()), own)),
            ticker_other_rows=len(_overlaps(indexes['ticker'].get(row['ticker'], ()), own)),
            same_table_complete_token_overlap_rows=sum(row_id[0] == table for row_id in complete_owners),
            cross_table_complete_token_overlap_rows=sum(row_id[0] != table for row_id in complete_owners),
            malformed_field_overlap_rows=len(poison_owners))
        if record['state'] != 'parsed':
            result.update(same_table_complete_token_overlap_rows=None,
                cross_table_complete_token_overlap_rows=None, malformed_field_overlap_rows=None)
    return result


def _receipt(built):
    rows, records, indexes, tokens, poisoned, totals = built
    unknown = sum(item['missing_vocabulary_row_count'] + item['malformed_vocabulary_row_count'] for item in totals.values())
    return {'schema': SCHEMA, 'status': 'current_probe_routing_predicates_observed',
        'parser_sha256': PARSER_SHA256, 'reference_session': REFERENCE_SESSION,
        'metadata_rows_sha256': {table: sha(canonical(rows[table])) for table in TABLES},
        'tables': totals, 'cusip_census_status': 'incomplete_unknown_vocabulary' if unknown else 'complete',
        'unknown_vocabulary_row_count': unknown,
        'permaticker_collision_groups': sum(len(owners) > 1 for owners in indexes['permaticker'].values()),
        'figi_collision_groups': sum(len(owners) > 1 for owners in indexes['figi'].values()),
        'ticker_collision_groups': sum(len(owners) > 1 for owners in indexes['ticker'].values()),
        'complete_token_collision_groups': sum(len(owners) > 1 for owners in tokens.values()),
        'malformed_overlap_token_groups': sum(bool(owners and tokens.get(token)) for token, owners in poisoned.items()),
        'probes': [_probe(index, table, ticker, records, indexes, tokens, poisoned)
            for index, (table, ticker) in enumerate(PROBES)],
        'current_vintage_only': True, 'diagnostic_only': True, **FALSE_FLAGS}


def catalog(stocks, funds):
    """Closed observations; unknown unrelated vocabularies remain explicitly unknown."""
    return validate_receipt(_receipt(_build(stocks, funds)))


def require_probe_routes(stocks, funds):
    """Return private row copies after all complete-token/refusal-token checks.

    This does not grant global identity admission: a malformed unrelated field
    remains unknown in catalog(). The separately scoped consumer must retain
    that receipt and all current-vintage qualifications.
    """
    built = _build(stocks, funds)
    rows, records, indexes, tokens, poisoned, _ = built
    selected = []
    for index, (table, ticker) in enumerate(PROBES):
        probe = _probe(index, table, ticker, records, indexes, tokens, poisoned)
        require(probe['candidate_count'] == 1, 'route_missing_or_ambiguous')
        require(probe['shape_predicates_satisfied'] is True and probe['vocabulary_status'] == 'parsed', 'route_shape')
        collision_fields = ('permaticker_other_rows', 'figi_other_rows', 'ticker_other_rows',
            'same_table_complete_token_overlap_rows', 'cross_table_complete_token_overlap_rows',
            'malformed_field_overlap_rows')
        require(all(probe[field] == 0 for field in collision_fields), 'route_collision')
        row = next(row for row in rows[table] if row['ticker'] == ticker)
        try:
            first, last = previous._date(row['firstpricedate'], 'metadata_interval'), previous._date(row['lastpricedate'], 'metadata_interval')
            require(first <= previous._date(REFERENCE_SESSION, 'probe_date') <= last, 'route_interval')
            previous._date(row['lastupdated'], 'metadata_interval')
        except previous.Refused: raise Refused('route_interval') from None
        selected.append(dict(row))
    return selected


def profile_record():
    return {'schema': SCHEMA, 'purpose': 'prospective_current_metadata_probe_routing_shape_and_collision_observation',
        'parser_sha256': PARSER_SHA256, 'maximum_rows_per_table_exclusive': MAX_ROWS,
        'maximum_field_UTF8_bytes': MAX_FIELD_BYTES, 'maximum_catalog_field_bytes': MAX_CATALOG_BYTES,
        'fields': list(FIELDS), 'fixed_probe_count': len(PROBES), 'reference_session': REFERENCE_SESSION,
        'quality_and_selection_share_complete_parser': True, 'all_complete_tokens_indexed': True,
        'collision_ownership': 'physical_rows_across_both_returned_tables_not_first_token_or_ticker_only',
        'malformed_field_shape_tokens': 'refusal_only_never_admission',
        'missing_or_malformed_unrelated_field': 'explicit_unknown_not_empty_or_global_no_collision',
        'selected_probe_requires_complete_vocabulary': True, 'required_route_collision_refused': True,
        'current_metadata_not_historical_effective_intervals': True, 'legacy_composer_and_evidence_unchanged': True,
        'caller_must_retain_catalog_unknown_status': True, 'raw_rows_and_token_values_private_only': True,
        'current_vintage_only': True, 'diagnostic_only': True, **FALSE_FLAGS}


def _hash(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate_receipt(value):
    fixed = {'schema': SCHEMA, 'status': 'current_probe_routing_predicates_observed',
        'parser_sha256': PARSER_SHA256, 'reference_session': REFERENCE_SESSION,
        'current_vintage_only': True, 'diagnostic_only': True, **FALSE_FLAGS}
    variables = {'metadata_rows_sha256', 'tables', 'cusip_census_status', 'unknown_vocabulary_row_count',
        'permaticker_collision_groups', 'figi_collision_groups', 'ticker_collision_groups',
        'complete_token_collision_groups', 'malformed_overlap_token_groups', 'probes'}
    require(type(value) is dict and len(value) == len(fixed) + len(variables)
        and all(type(key) is str and key in set(fixed) | variables for key in value)
        and all(key in value and type(value[key]) is type(item) and value[key] == item for key, item in fixed.items()), 'receipt')
    hashes, tables = value['metadata_rows_sha256'], value['tables']
    require(type(hashes) is dict and set(hashes) == set(TABLES) and all(_hash(pin) for pin in hashes.values())
        and type(tables) is dict and set(tables) == set(TABLES), 'receipt')
    counts = {}
    for table in TABLES:
        summary = tables[table]
        keys = {'row_count', 'parsed_vocabulary_row_count', 'missing_vocabulary_row_count',
            'malformed_vocabulary_row_count', 'complete_vocabulary_token_count'}
        require(type(summary) is dict and set(summary) == keys
            and all(type(summary[key]) is int and summary[key] >= 0 for key in keys)
            and summary['row_count'] < MAX_ROWS
            and summary['parsed_vocabulary_row_count'] + summary['missing_vocabulary_row_count']
                + summary['malformed_vocabulary_row_count'] == summary['row_count']
            and summary['parsed_vocabulary_row_count'] <= summary['complete_vocabulary_token_count']
                <= 64 * summary['parsed_vocabulary_row_count'], 'receipt')
        counts[table] = summary['row_count']
    total = sum(counts.values())
    unknown = sum(tables[table]['missing_vocabulary_row_count'] + tables[table]['malformed_vocabulary_row_count'] for table in TABLES)
    require(type(value['unknown_vocabulary_row_count']) is int and value['unknown_vocabulary_row_count'] == unknown
        and value['cusip_census_status'] == ('incomplete_unknown_vocabulary' if unknown else 'complete'), 'receipt')
    for key in ('permaticker_collision_groups', 'figi_collision_groups', 'ticker_collision_groups',
        'complete_token_collision_groups', 'malformed_overlap_token_groups'):
        require(type(value[key]) is int and 0 <= value[key] <= (64 * total if 'token' in key else total // 2), 'receipt')
    probes = value['probes']
    require(type(probes) is list and len(probes) == len(PROBES), 'receipt')
    count_fields = ('permaticker_other_rows', 'figi_other_rows', 'ticker_other_rows',
        'same_table_complete_token_overlap_rows', 'cross_table_complete_token_overlap_rows', 'malformed_field_overlap_rows')
    for index, probe in enumerate(probes):
        keys = {'probe_index', 'candidate_count', 'candidate_rows_sha256', 'vocabulary_status',
            'complete_vocabulary_token_count', 'refusal_only_token_count', 'shape_predicates_satisfied', *count_fields}
        table = PROBES[index][0]
        require(type(probe) is dict and set(probe) == keys and type(probe['probe_index']) is int
            and probe['probe_index'] == index and type(probe['candidate_count']) is int
            and 0 <= probe['candidate_count'] <= counts[table] and _hash(probe['candidate_rows_sha256']), 'receipt')
        if probe['candidate_count'] != 1:
            require(probe['vocabulary_status'] == 'not_unique'
                and all(probe[key] is None for key in ('complete_vocabulary_token_count',
                    'refusal_only_token_count', 'shape_predicates_satisfied', *count_fields)), 'receipt')
            if probe['candidate_count'] == 0: require(probe['candidate_rows_sha256'] == sha(canonical([])), 'receipt')
            continue
        state = probe['vocabulary_status']
        require(type(state) is str and state in ('parsed', 'missing', 'malformed')
            and type(probe['complete_vocabulary_token_count']) is int
            and type(probe['refusal_only_token_count']) is int
            and type(probe['shape_predicates_satisfied']) is bool, 'receipt')
        if state == 'parsed':
            require(1 <= probe['complete_vocabulary_token_count'] <= 64 and probe['refusal_only_token_count'] == 0
                and all(type(probe[key]) is int and 0 <= probe[key] <= max(total - 1, 0) for key in count_fields)
                and probe['same_table_complete_token_overlap_rows'] <= max(counts[table] - 1, 0)
                and probe['cross_table_complete_token_overlap_rows'] <= counts['funds' if table == 'stocks' else 'stocks']
                and probe['malformed_field_overlap_rows'] <= unknown, 'receipt')
        else:
            require(probe['complete_vocabulary_token_count'] == 0
                and 0 <= probe['refusal_only_token_count'] <= MAX_FIELD_BYTES
                and probe['shape_predicates_satisfied'] is False
                and all(probe[key] is None for key in count_fields[3:])
                and all(type(probe[key]) is int and 0 <= probe[key] <= max(total - 1, 0) for key in count_fields[:3]), 'receipt')
            if state == 'missing': require(probe['refusal_only_token_count'] == 0, 'receipt')
    require(len(canonical(value)) <= 65536, 'receipt')
    return json.loads(canonical(value))


def validate_catalog(receipt, stocks, funds):
    checked = validate_receipt(receipt)
    require(canonical(checked) == canonical(catalog(stocks, funds)), 'receipt')
    return checked
