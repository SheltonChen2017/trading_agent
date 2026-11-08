"""Qualified supplied-data EOD price locators; never strategy identity repair.

SF1 currency describes functional reporting, while stocks/funds currency
describes EOD prices. Original SF1 rows and all evidence hashes remain exact.
Current ticker/venue/category are observed price-table metadata, never updates
to original common-stock eligibility, QC identities or historical venues.
Full catalogs and every original CUSIP are checked before any private locator.
No filesystem, credential, provider/QC call or price observation exists here.
"""
from __future__ import annotations

from collections import Counter
import json

from scripts import arv2_r298_route_disposition_evidence as evidence
from scripts import arv2_r298_membership_price_demand as demand

routes = evidence.routes
SCHEMA = 'arv2-r298-qualified-price-lineage-routes-v1'
PRIVATE_SCHEMA = SCHEMA + '-private'
EXPECTED_STOCKS, EXPECTED_FUNDS = 6151, 8
FROZEN_SOURCE_PINS = {
    'scripts/arv2_r298_sharadar_all_routes_v2.py': '6fe5ec74c4e241fc554183d8ecbdc663c0e63e3f476deb180e37304b7c033ab1',
    'scripts/arv2_r298_route_disposition_evidence.py': '0c6604ba8cbbf5c42c4b4d1879ad5738a5843d70af776d171c2c947daa7a6a1b',
    'scripts/arv2_r298_membership_price_demand.py': '08a9aa94b8c771eb69ed5876a82f900f0716cff9c47e082d55490c211a2c9b40',
}
MAX_PRIVATE_BYTES, MAX_SUMMARY_BYTES = 64 * 1024 * 1024, 128 * 1024
FLAGS = frozenset(('original_reporting_currency_not_usd', 'current_ticker_differs',
    'current_exchange_differs', 'current_mic_differs', 'current_mic_unmapped',
    'current_category_differs', 'current_category_outside_old_common_vocabulary',
    'current_exchange_outside_old_listing_vocabulary', 'metadata_first_unparseable',
    'metadata_last_unparseable', 'metadata_updated_unparseable', 'metadata_interval_reversed',
    'metadata_first_after_window_start', 'metadata_last_before_window_end'))
REASONS = frozenset(('original_identity', 'identity_missing', 'identity_ambiguous',
    'price_table', 'price_ticker', 'price_currency', 'identity_shape', 'vocabulary',
    'original_vocabulary_not_retained', 'global_collision'))
FINITE = REASONS | frozenset(('deadline', 'aa_summary', 'aa_frame', 'demand_summary',
    'demand_frame', 'demand_binding', 'metadata_pin', 'metadata_catalog', 'private_bound',
    'private_record', 'summary', 'routes_incomplete', 'unknown'))
DEMAND_STOCK_FIELDS = frozenset(('binding_ordinal', 'security_id', 'binding_row_sha256', 'route_disposition',
    'route_reason', 'membership_interval_count', 'membership_rows_sha256', 'potential_for_both_cohorts_all_AR_arms',
    'eligible_decision_count', 'eligible_decisions_sha256', 'first_eligible_decision', 'last_eligible_decision',
    'required_price_start', 'required_price_end', 'binding_last_session_not_used_as_price_end',
    'zero_initial_runtime_condition_required_for_never_potential'))
DEMAND_FUND_FIELDS = frozenset(('fund_ordinal', 'ticker', 'route_disposition', 'route_reason',
    'six_universe', 'eight_universe', 'required_price_start', 'required_price_end'))
STOCK_FIELDS = frozenset(('binding_ordinal', 'binding', 'aa_disposition', 'aa_reason', 'potential',
    'conditional_never_potential', 'disposition', 'reason', 'route', 'observed_flags', 'query_window'))
FUND_FIELDS = frozenset(('fund_ordinal', 'ticker', 'disposition', 'reason', 'route', 'observed_flags', 'query_window'))
FALSE_FLAGS = {'provider_contact': False, 'qc_contact': False, 'price_acquired': False,
    'price_coverage_proven': False, 'price_input_admitted': False, 'strategy_continued': False,
    'original_identity_rewritten': False, 'current_display_is_historical_mapping': False,
    'point_in_time_proven': False, 'formal_identity_admitted': False,
    'formal_forward_ready': False, 'paper_or_live_ready': False}
canonical, sha = routes.canonical, routes.sha


class Refused(ValueError):
    """Finite predicates only; never a licensed locator or source value."""


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else 'unknown'


def _deadline(value):
    try: evidence._deadline(value)
    except evidence.Refused: raise Refused('deadline') from None


def _validate_demand_summary(value):
    try: return demand.validate_summary(value)
    except (ValueError, TypeError, KeyError): raise Refused('demand_summary') from None


def _frames(aa_raw, demand_raw, aa_summary, demand_summary, deadline):
    try:
        checked, _ = evidence.inspect(aa_raw, expected_summary=aa_summary, deadline=deadline)
        aa = evidence._decode(aa_raw, deadline)
    except evidence.Refused as error:
        raise Refused('deadline' if evidence.finite(error) == 'deadline' else 'aa_frame') from None
    summary = _validate_demand_summary(demand_summary)
    require(summary['source_frame_pin'] == checked['frame_pin']
        and summary['evidence_summary_sha256'] == sha(canonical(checked)), 'demand_binding')
    require(type(demand_raw) is bytes and len(demand_raw) == summary['private_frame_byte_count']
        and sha(demand_raw) == summary['private_frame_sha256'], 'demand_frame')
    try: planned = evidence._decode(demand_raw, deadline)
    except evidence.Refused: raise Refused('demand_frame') from None
    require(set(planned) == {'schema', 'source_frame_pin', 'evidence_summary_sha256', 'binding_contract', 'stocks', 'funds'}
        and planned['schema'] == demand.PRIVATE_SCHEMA and planned['source_frame_pin'] == checked['frame_pin']
        and planned['evidence_summary_sha256'] == summary['evidence_summary_sha256']
        and planned['binding_contract'] == aa['binding_contract']
        and type(planned['stocks']) is list and len(planned['stocks']) == EXPECTED_STOCKS
        and type(planned['funds']) is list and len(planned['funds']) == EXPECTED_FUNDS, 'demand_binding')
    for index, (item, source) in enumerate(zip(planned['stocks'], aa['stocks'], strict=True)):
        _deadline(deadline)
        require(type(item) is dict and set(item) == DEMAND_STOCK_FIELDS
            and type(item['binding_ordinal']) is int and item['binding_ordinal'] == index
            and item['security_id'] == source['binding']['security_id']
            and item['binding_row_sha256'] == source['binding']['row_sha256']
            and item['route_disposition'] == source['disposition'] and item['route_reason'] == source['reason']
            and type(item['potential_for_both_cohorts_all_AR_arms']) is bool
            and type(item['eligible_decision_count']) is int and item['eligible_decision_count'] >= 0
            and type(item['membership_interval_count']) is int and item['membership_interval_count'] >= 0
            and evidence._hash(item['membership_rows_sha256']) and evidence._hash(item['eligible_decisions_sha256'])
            and item['binding_last_session_not_used_as_price_end'] is True, 'demand_binding')
        potential = item['potential_for_both_cohorts_all_AR_arms']
        require(item['zero_initial_runtime_condition_required_for_never_potential'] is (not potential), 'demand_binding')
        if potential:
            require(item['eligible_decision_count'] > 0 and evidence._date(item['first_eligible_decision']) is not None
                and evidence._date(item['last_eligible_decision']) is not None
                and evidence._date(item['required_price_start']) is not None
                and routes.PRICE_FIRST <= item['required_price_start'] < item['first_eligible_decision']
                <= item['last_eligible_decision'] <= routes.PRICE_LAST
                and item['required_price_end'] == routes.PRICE_LAST, 'demand_binding')
        else:
            require(item['eligible_decision_count'] == 0 and all(item[key] is None for key in
                ('first_eligible_decision', 'last_eligible_decision', 'required_price_start', 'required_price_end')), 'demand_binding')
    for index, (item, source) in enumerate(zip(planned['funds'], aa['funds'], strict=True)):
        require(type(item) is dict and set(item) == DEMAND_FUND_FIELDS
            and type(item['fund_ordinal']) is int and item['fund_ordinal'] == index
            and item['ticker'] == source['ticker'] == routes.current.ETF_TICKERS[index]
            and item['route_disposition'] == source['disposition'] and item['route_reason'] == source['reason']
            and item['eight_universe'] is True and type(item['six_universe']) is bool
            and item['six_universe'] == (item['ticker'] in demand.runtime.targets.cohort(6))
            and item['required_price_start'] == routes.PRICE_FIRST
            and item['required_price_end'] == routes.PRICE_LAST, 'demand_binding')
    potential_count = sum(item['potential_for_both_cohorts_all_AR_arms'] for item in planned['stocks'])
    require(all(summary['cohorts'][str(count)]['potential_stock_count'] == potential_count
        and summary['cohorts'][str(count)]['never_potential_stock_count'] == EXPECTED_STOCKS - potential_count
        for count in (6, 8)), 'demand_binding')
    return aa, planned, summary


def _original(item):
    try: predicates, identity = evidence._original(item['binding'], item['original_row'])
    except (ValueError, TypeError, KeyError): raise Refused('original_identity') from None
    # The only changed old predicate is SF1's functional REPORTING currency.
    # Every constructor/evidence/raw-date consistency predicate is preserved.
    require(identity is not None and all(state == 'pass' for key, state in predicates.items()
        if key != 'original_currency_usd'), 'original_identity')
    return identity


def _price_route(built, original, *, table, source=None):
    _, records, indexes, tokens, poisoned, _ = built
    owners = set(indexes['permaticker'].get(original['permaticker'], ())) & set(indexes['figi'].get(original['figi'], ()))
    require(owners, 'identity_missing'); require(len(owners) == 1, 'identity_ambiguous')
    own = next(iter(owners)); record = records[own]; row = record['row']
    require(own[0] == table and row['table'] in (table, 'SEP' if table == 'stocks' else 'SFP'), 'price_table')
    identity, composer = routes.current.previous.identities, routes.current.previous.composer
    require(identity._PERMANENT_ID.fullmatch(row['permaticker']) is not None
        and identity._FIGI.fullmatch(row['figi']) is not None, 'identity_shape')
    require(composer._TICKER.fullmatch(row['ticker']) is not None, 'price_ticker')
    require(row['currency'] == 'USD', 'price_currency')
    require(record['state'] == 'parsed' and record['tokens'], 'vocabulary')
    require(all(indexes[field].get(row[field], set()) == {own} for field in ('permaticker', 'figi', 'ticker'))
        and all(tokens[token] == {own} and not poisoned.get(token) for token in record['tokens']), 'global_collision')
    require(set(original['tokens']) <= set(record['tokens']), 'original_vocabulary_not_retained')
    require(all(tokens.get(token) == {own} and not poisoned.get(token) for token in original['tokens']), 'global_collision')
    source = source or {}
    mic = evidence._mic(row, table)
    first, last, updated = (evidence._date(row[key]) for key in ('firstpricedate', 'lastpricedate', 'lastupdated'))
    flags = {'original_reporting_currency_not_usd': source.get('currency', 'USD') != 'USD',
        'current_ticker_differs': row['ticker'] != original['ticker'],
        'current_exchange_differs': 'exchange' in source and row['exchange'] != source['exchange'],
        'current_mic_differs': mic != original['mic'], 'current_mic_unmapped': mic is None,
        'current_category_differs': 'category' in source and row['category'] != source['category'],
        'current_category_outside_old_common_vocabulary': table == 'stocks' and row['category'].casefold() not in identity._COMMON_CATEGORIES,
        'current_exchange_outside_old_listing_vocabulary': row['exchange'] not in
            (identity._STOCK_EXCHANGES if table == 'stocks' else identity._FUND_EXCHANGES),
        'metadata_first_unparseable': first is None, 'metadata_last_unparseable': last is None,
        'metadata_updated_unparseable': updated is None,
        'metadata_interval_reversed': first is not None and last is not None and first > last,
        'metadata_first_after_window_start': first is not None and first > routes.PRICE_FIRST,
        'metadata_last_before_window_end': last is not None and last < routes.PRICE_LAST}
    return {'table': table, 'current_metadata_row': dict(row), 'current_cusip_tokens': list(record['tokens']),
        'current_exchange_mic': mic}, flags


class PrivatePriceRoutes:
    __slots__ = ('_raw',)
    def __init__(self, value):
        raw = canonical(value); require(0 < len(raw) <= MAX_PRIVATE_BYTES, 'private_bound')
        object.__setattr__(self, '_raw', raw)
    def __setattr__(self, name, value): raise TypeError('private price routes are immutable')
    def __repr__(self): return '<PrivatePriceRoutes redacted; qualified supplied locators only>'
    def __reduce_ex__(self, protocol): raise TypeError('price routes require an explicitly private export')
    def private_record(self): return json.loads(self._raw)
    def query_routes(self):
        """PRIVATE inert data, never acquisition permission or price admission."""
        record = self.private_record()
        require(not any(item['disposition'] == 'refused' for item in record['stocks'] + record['funds']), 'routes_incomplete')
        return [dict(item['route'], query_window=list(item['query_window'])) for item in
            record['stocks'] + record['funds'] if item['query_window'] is not None]


def _counts(stocks, funds):
    dispositions, reasons, flags = {}, {}, {}
    for table, rows in (('stocks', stocks), ('funds', funds)):
        dispositions[table] = dict(sorted(Counter(item['disposition'] for item in rows).items()))
        reasons[table] = dict(sorted(Counter(item['reason'] for item in rows if item['reason'] is not None).items()))
        flags[table] = dict(sorted(Counter(key for item in rows for key, value in item['observed_flags'].items() if value).items()))
    return dispositions, reasons, flags


def prepare(aa_frame_raw, demand_raw, stocks_raw, funds_raw, *, aa_routing_summary,
            demand_summary, capture_pins, deadline=None):
    _deadline(deadline)
    aa, planned, checked_demand = _frames(aa_frame_raw, demand_raw, aa_routing_summary, demand_summary, deadline)
    require(type(capture_pins) is dict and set(capture_pins) == {'stocks', 'funds'}, 'metadata_pin')
    for table, raw in (('stocks', stocks_raw), ('funds', funds_raw)):
        require(evidence._pin(capture_pins[table], 16 * 1024 * 1024) and type(raw) is bytes
            and capture_pins[table] == {'byte_count': len(raw), 'sha256': sha(raw)}, 'metadata_pin')
    try:
        built = routes.current._build(routes.current.metadata(stocks_raw, 'stocks', 16 * 1024 * 1024)[0],
            routes.current.metadata(funds_raw, 'funds', 16 * 1024 * 1024)[0])
        catalog = routes.current.validate_receipt(routes.current._receipt(built))
    except (ValueError, TypeError, KeyError): raise Refused('metadata_catalog') from None
    require(catalog['metadata_rows_sha256'] == aa_routing_summary['metadata_rows_sha256'], 'metadata_pin')
    stocks, funds = [], []
    budget = 0
    for ordinal, (item, need) in enumerate(zip(aa['stocks'], planned['stocks'], strict=True)):
        _deadline(deadline); potential = need['potential_for_both_cohorts_all_AR_arms']
        result = {'binding_ordinal': ordinal, 'binding': dict(item['binding']),
            'aa_disposition': item['disposition'], 'aa_reason': item['reason'],
            'potential': potential, 'conditional_never_potential': not potential,
            'disposition': 'conditional_never_potential' if not potential else 'refused',
            'reason': None, 'route': None, 'observed_flags': dict.fromkeys(FLAGS, False), 'query_window': None}
        try:
            original = _original(item)
            route, flags = _price_route(built, original, table='stocks', source=item['original_row'])
            route.update(route_key=item['binding']['security_id'], security_id=item['binding']['security_id'],
                source_binding_sha256=item['binding']['row_sha256'])
            result.update(route=route, observed_flags=flags)
            if potential: result.update(disposition='routed', query_window=[routes.PRICE_FIRST, routes.PRICE_LAST])
        except Refused as error: result['reason'] = finite(error)
        budget += len(canonical(result)) + 1; require(budget + 4096 <= MAX_PRIVATE_BYTES, 'private_bound')
        stocks.append(result)
    for ordinal, item in enumerate(aa['funds']):
        _deadline(deadline)
        result = {'fund_ordinal': ordinal, 'ticker': item['ticker'], 'disposition': 'refused',
            'reason': None, 'route': None, 'observed_flags': dict.fromkeys(FLAGS, False), 'query_window': None}
        try:
            require(item['disposition'] == 'routed' and type(item['route']) is dict, 'original_identity')
            old = item['route']['current_metadata_row']
            original = {'permaticker': old['permaticker'], 'figi': old['figi'], 'ticker': old['ticker'],
                'mic': item['route']['current_exchange_mic'], 'tokens': tuple(item['route']['current_cusip_tokens'])}
            route, flags = _price_route(built, original, table='funds', source=old)
            route.update(route_key='own-etf-' + item['ticker'], security_id=None, source_binding_sha256=None)
            result.update(disposition='routed', route=route, observed_flags=flags,
                query_window=[routes.PRICE_FIRST, routes.PRICE_LAST])
        except Refused as error: result['reason'] = finite(error)
        budget += len(canonical(result)) + 1; require(budget + 4096 <= MAX_PRIVATE_BYTES, 'private_bound')
        funds.append(result)
    source_pins = {'aa_frame': {'byte_count': len(aa_frame_raw), 'sha256': sha(aa_frame_raw)},
        'demand_frame': {'byte_count': len(demand_raw), 'sha256': sha(demand_raw)}, **capture_pins}
    private = PrivatePriceRoutes({'schema': PRIVATE_SCHEMA, 'source_pins': source_pins,
        'binding_contract': aa['binding_contract'], 'stocks': stocks, 'funds': funds})
    dispositions, reasons, flags = _counts(stocks, funds)
    corrected = sum(item['potential'] and item['aa_disposition'] == 'refused' and item['disposition'] == 'routed' for item in stocks)
    summary = {'schema': SCHEMA, 'scope': 'qualified_current_vintage_price_locator_observation_not_coverage_admission',
        'source_pins': source_pins, 'aa_routing_summary_sha256': sha(canonical(aa_routing_summary)),
        'demand_summary_sha256': sha(canonical(checked_demand)), 'policy_sha256': sha(canonical(profile_record())),
        'binding_contract': aa['binding_contract'], 'price_window': [routes.PRICE_FIRST, routes.PRICE_LAST],
        'disposition_counts': dispositions, 'refusal_counts': reasons, 'observation_flag_counts': flags,
        'potential_stock_count': sum(item['potential'] for item in stocks),
        'conditional_never_potential_stock_count': sum(not item['potential'] for item in stocks),
        'old_predicate_only_route_correction_count': corrected,
        'current_catalog_unknown_vocabulary_row_count': catalog['unknown_vocabulary_row_count'],
        'private_frame_byte_count': len(private._raw), 'private_frame_sha256': sha(private._raw), **FALSE_FLAGS}
    _deadline(deadline)
    return validate_summary(summary), private


def validate_summary(value):
    keys = {'schema', 'scope', 'source_pins', 'aa_routing_summary_sha256', 'demand_summary_sha256',
        'policy_sha256', 'binding_contract', 'price_window', 'disposition_counts', 'refusal_counts',
        'observation_flag_counts', 'potential_stock_count', 'conditional_never_potential_stock_count',
        'old_predicate_only_route_correction_count', 'current_catalog_unknown_vocabulary_row_count',
        'private_frame_byte_count', 'private_frame_sha256', *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value['schema'] == SCHEMA
        and value['scope'] == 'qualified_current_vintage_price_locator_observation_not_coverage_admission'
        and all(value[key] is False for key in FALSE_FLAGS) and value['price_window'] == [routes.PRICE_FIRST, routes.PRICE_LAST]
        and value['policy_sha256'] == sha(canonical(profile_record())), 'summary')
    try: contract = routes._contract(value['binding_contract'])
    except (ValueError, TypeError): raise Refused('summary') from None
    require(contract['binding_count'] == EXPECTED_STOCKS and type(value['source_pins']) is dict
        and set(value['source_pins']) == {'aa_frame', 'demand_frame', 'stocks', 'funds'}
        and all(evidence._pin(pin, routes.MAX_PRIVATE_BYTES if name in ('aa_frame', 'demand_frame')
            else 16 * 1024 * 1024) for name, pin in value['source_pins'].items())
        and all(evidence._hash(value[key]) for key in ('aa_routing_summary_sha256', 'demand_summary_sha256', 'private_frame_sha256'))
        and type(value['private_frame_byte_count']) is int and 0 < value['private_frame_byte_count'] <= MAX_PRIVATE_BYTES, 'summary')
    for field in ('potential_stock_count', 'conditional_never_potential_stock_count', 'old_predicate_only_route_correction_count'):
        require(evidence._count(value[field], EXPECTED_STOCKS), 'summary')
    require(value['potential_stock_count'] + value['conditional_never_potential_stock_count'] == EXPECTED_STOCKS
        and evidence._count(value['current_catalog_unknown_vocabulary_row_count'], 200000), 'summary')
    for field in ('disposition_counts', 'refusal_counts', 'observation_flag_counts'):
        require(type(value[field]) is dict and set(value[field]) == {'stocks', 'funds'}, 'summary')
    for table, total in (('stocks', EXPECTED_STOCKS), ('funds', EXPECTED_FUNDS)):
        d, r, f = (value[key][table] for key in ('disposition_counts', 'refusal_counts', 'observation_flag_counts'))
        require(type(d) is dict and set(d) <= {'routed', 'refused', 'conditional_never_potential'}
            and all(type(n) is int and n > 0 for n in d.values()) and sum(d.values()) == total
            and type(r) is dict and set(r) <= REASONS and all(type(n) is int and 0 < n <= total for n in r.values())
            and d.get('refused', 0) <= sum(r.values())
            <= d.get('refused', 0) + d.get('conditional_never_potential', 0)
            and type(f) is dict and set(f) <= FLAGS
            and all(type(n) is int and 0 < n <= total for n in f.values()), 'summary')
    require(value['disposition_counts']['stocks'].get('conditional_never_potential', 0)
        == value['conditional_never_potential_stock_count']
        and value['disposition_counts']['stocks'].get('routed', 0) + value['disposition_counts']['stocks'].get('refused', 0)
        == value['potential_stock_count'] and 'conditional_never_potential' not in value['disposition_counts']['funds']
        and value['old_predicate_only_route_correction_count'] <= value['disposition_counts']['stocks'].get('routed', 0)
        and len(canonical(value)) <= MAX_SUMMARY_BYTES, 'summary')
    return json.loads(canonical(value))


def validate_private_record(record, *, expected_summary):
    summary = validate_summary(expected_summary)
    require(type(record) is dict and set(record) == {'schema', 'source_pins', 'binding_contract', 'stocks', 'funds'}
        and record['schema'] == PRIVATE_SCHEMA and record['source_pins'] == summary['source_pins']
        and record['binding_contract'] == summary['binding_contract']
        and type(record['stocks']) is list and len(record['stocks']) == EXPECTED_STOCKS
        and type(record['funds']) is list and len(record['funds']) == EXPECTED_FUNDS, 'private_record')
    raw = canonical(record)
    require(len(raw) == summary['private_frame_byte_count'] and sha(raw) == summary['private_frame_sha256'], 'private_record')
    try: bindings = routes._bindings([item['binding'] for item in record['stocks']], record['binding_contract'])
    except (ValueError, TypeError, KeyError): raise Refused('private_record') from None
    route_keys = {'table', 'current_metadata_row', 'current_cusip_tokens', 'current_exchange_mic',
        'route_key', 'security_id', 'source_binding_sha256'}
    for table, rows, fields in (('stocks', record['stocks'], STOCK_FIELDS), ('funds', record['funds'], FUND_FIELDS)):
        for index, item in enumerate(rows):
            ordinal = 'binding_ordinal' if table == 'stocks' else 'fund_ordinal'
            require(type(item) is dict and set(item) == fields and type(item[ordinal]) is int and item[ordinal] == index
                and type(item['disposition']) is str and item['disposition'] in ('routed', 'refused', 'conditional_never_potential')
                and (item['reason'] is None or (type(item['reason']) is str and item['reason'] in REASONS))
                and type(item['observed_flags']) is dict and set(item['observed_flags']) == FLAGS
                and all(type(value) is bool for value in item['observed_flags'].values()), 'private_record')
            if table == 'stocks':
                require(type(item['potential']) is bool and item['conditional_never_potential'] is (not item['potential'])
                    and item['aa_disposition'] in evidence.DISPOSITIONS
                    and ((item['aa_disposition'] == 'routed' and item['aa_reason'] is None)
                        or (item['aa_disposition'] == 'refused' and item['aa_reason'] in routes.REASONS)
                        or (item['aa_disposition'] == 'outside_window'
                            and item['aa_reason'] == 'original_candidate_interval_disjoint'))
                    and ((item['potential'] and item['disposition'] != 'conditional_never_potential')
                        or (not item['potential'] and item['disposition'] == 'conditional_never_potential')), 'private_record')
            else:
                require(item['ticker'] == routes.current.ETF_TICKERS[index]
                    and item['disposition'] != 'conditional_never_potential', 'private_record')
            if item['disposition'] == 'routed':
                require(item['query_window'] == [routes.PRICE_FIRST, routes.PRICE_LAST]
                    and item['reason'] is None, 'private_record')
            else: require(item['query_window'] is None, 'private_record')
            if item['reason'] is not None:
                require(item['route'] is None and item['disposition'] != 'routed', 'private_record')
            else:
                route = item['route']
                require(type(route) is dict and set(route) == route_keys and route['table'] == table, 'private_record')
                try:
                    row = routes.current._row(route['current_metadata_row'])
                    tokens = routes.current.parse_vocabulary(row['cusips'])
                except (ValueError, TypeError): raise Refused('private_record') from None
                require(row['table'] in (table, 'SEP' if table == 'stocks' else 'SFP')
                    and row['currency'] == 'USD' and routes.current.previous.composer._TICKER.fullmatch(row['ticker']) is not None
                    and route['current_cusip_tokens'] == list(tokens)
                    and route['current_exchange_mic'] == evidence._mic(row, table), 'private_record')
                if table == 'stocks':
                    binding = bindings[index]
                    require(route['security_id'] == route['route_key'] == binding['security_id']
                        and route['source_binding_sha256'] == binding['row_sha256']
                        and row['figi'] == binding['composite_figi']
                        and routes.original.composer._safe_component('sharadar-permaticker', row['permaticker'])
                            == binding['issuer_id'], 'private_record')
                else:
                    require(route['route_key'] == 'own-etf-' + item['ticker']
                        and route['security_id'] is None and route['source_binding_sha256'] is None, 'private_record')
    d, r, f = _counts(record['stocks'], record['funds'])
    require((d, r, f) == (summary['disposition_counts'], summary['refusal_counts'], summary['observation_flag_counts'])
        and sum(item['potential'] for item in record['stocks']) == summary['potential_stock_count']
        and sum(item['potential'] and item['aa_disposition'] == 'refused' and item['disposition'] == 'routed'
            for item in record['stocks']) == summary['old_predicate_only_route_correction_count'], 'private_record')
    return json.loads(raw)


def profile_record():
    return {'schema': SCHEMA, 'private_schema': PRIVATE_SCHEMA, 'stock_count': EXPECTED_STOCKS, 'fund_count': EXPECTED_FUNDS,
        'selected_frozen_component_pins': dict(FROZEN_SOURCE_PINS),
        'maximum_private_bytes': MAX_PRIVATE_BYTES, 'maximum_summary_bytes': MAX_SUMMARY_BYTES,
        'price_window': [routes.PRICE_FIRST, routes.PRICE_LAST], 'original_identity_policy':
            'all_frozen_original_constructor_evidence_and_rawdate_consistency_predicates_except_SF1_USD_test',
        'currency_field_roles': 'SF1_fundamentals_functional_reporting_vs_stocks_funds_EOD_price_currency_no_FX_conversion',
        'current_EOD_currency': 'USD_required', 'source_class': 'original_SF1_common_stock_proof_unchanged',
        'current_ticker': 'qualified_vendor_rewired_history_locator_same_perma_and_composite_FIGI_not_historical_QC_symbol',
        'current_venue_and_category': 'observations_not_replacements_for_original_strategy_eligibility_or_QC_identity',
        'metadata_dates': 'observed_first_last_price_observations_not_IPO_delisting_payoff_or_holding_bounds',
        'collisions': 'all_full_catalog_physical_rows_both_tables_perma_FIGI_ticker_all_CUSIPs_and_poison_tokens',
        'original_CUSIPs': 'complete_original_vocabulary_retained_in_current_vocabulary_no_first_token_alias',
        'potential_queries': 'full_frozen_window_not_clipped_to_metadata_binding_end_or_first_AB_demand',
        'never_potential': 'all_original_records_retained_conditional_on_frozen_zero_initial_runtime_no_unexpected_holdings',
        'unknown_or_mismatched_FIGI': 'closed_refusal_no_inferred_alias_or_provider_fallback',
        'source_documentation': ['https://sharadar.com/prices', 'https://sharadar.com/docs/faqs',
            'https://sharadar.com/docs/stocks', 'https://sharadar.com/docs/funds'],
        'observed_flags': sorted(FLAGS), 'refusal_codes': sorted(REASONS), **FALSE_FLAGS}
