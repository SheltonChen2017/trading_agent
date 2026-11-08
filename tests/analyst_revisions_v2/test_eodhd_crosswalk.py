"""Synthetic V2 original+current vocabulary policy; no actual DATA or operations."""
import copy
import hashlib
import json
import pickle
import time

import pytest

from scripts import arv2_r298_eodhd_crosswalk as m


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def observation(rows):
    return {'row_count': len(rows), 'ordered_records_sha256': hashlib.sha256(
        b''.join(raw(row) + b'\n' for row in rows)).hexdigest()}


def figi(number):
    seed = 'BBG' + str(number).zfill(8)
    expanded = [int(char, 36) * (1 if index % 2 == 0 else 2) for index, char in enumerate(seed)]
    return seed + str((10 - sum(number // 10 + number % 10 for number in expanded) % 10) % 10)


def cusip(number):
    seed = str(number).zfill(8)
    expanded = [int(char) * (1 if index % 2 == 0 else 2) for index, char in enumerate(seed)]
    return seed + str((10 - sum(number // 10 + number % 10 for number in expanded) % 10) % 10)


def catalog(code, kind='Common Stock', isin=None):
    return {'Code': code, 'Name': 'Unicode display café 日本', 'Country': 'United States',
        'Exchange': 'NYSE', 'Currency': 'USD', 'Type': kind, 'Isin': isin}


def mapping(code, f, c, isin=None):
    return {'symbol': code + '.US', 'isin': isin, 'figi': f, 'lei': None, 'cusip': c, 'cik': None}


def inventory(active, delisted, mappings):
    active_raw, delisted_raw = raw(active), raw(delisted)
    return {'schema': m.INVENTORY_SCHEMA, 'aw_authentication_sha256': 'a' * 64,
        'active': {'body_pin': m.pin(active_raw), **observation(active)},
        'delisted': {'body_pin': m.pin(delisted_raw), **observation(delisted)},
        'mapping': observation(mappings)}


@pytest.fixture
def case():
    stocks, funds, active, mappings = [], [], [], []
    for index, role in enumerate(('Sharadar_RAW_full_window', 'Sharadar_RAW_full_window',
            'pending_native_original_identity_source', 'conditional_never_potential_empty_initial_holdings_required')):
        f, c = figi(index + 1), cusip(index + 100)
        binding = {'security_id': 'synthetic-security-' + str(index), 'composite_figi': f,
            'row_sha256': hashlib.sha256(('semantic-' + str(index)).encode()).hexdigest(),
            'candidate_first_session': '2020-12-31', 'candidate_last_session': '2026-10-13',
            'source_row_sha256': hashlib.sha256(('original-' + str(index)).encode()).hexdigest(),
            'identity_evidence_sha256': hashlib.sha256(('evidence-' + str(index)).encode()).hexdigest()}
        route = None if index == 2 else {'table': 'stocks',
            'current_metadata_row': {'ticker': 'SHARADAR-' + str(index), 'figi': f},
            'current_cusip_tokens': [c]}
        stocks.append({'binding_ordinal': index, 'binding': binding, 'potential': index != 3,
            'disposition': 'refused' if index == 2 else 'conditional_never_potential' if index == 3 else 'routed',
            'route': route, 'role': role})
        code = 'EOD-' + str(index)
        active.append(catalog(code)); mappings.append(mapping(code, f, c))
    for index, ticker in enumerate(('SPY', 'QQQ')):
        f, c = figi(index + 100), cusip(index + 1000)
        route = {'table': 'funds', 'current_metadata_row': {'ticker': ticker, 'figi': f},
            'current_cusip_tokens': [c], 'current_exchange_mic': 'ARCX'}
        funds.append({'fund_ordinal': index, 'ticker': ticker, 'disposition': 'routed', 'route': route})
        active.append(catalog(ticker, 'ETF')); mappings.append(mapping(ticker, f, c))
    originals = {row['binding']['source_row_sha256']: [cusip(index + 100)] for index, row in enumerate(stocks)}
    return {'originals': originals, 'frame': {'stocks': stocks, 'funds': funds,
                'binding_contract': {'binding_stream_sha256': m.prices.native.BINDING_STREAM_SHA256}},
        'active': active, 'delisted': [], 'mapping': mappings}


def plan_for(frame):
    assignments = []
    for row in frame['stocks']:
        route = row['route']
        role = row['role']
        assignments.append({'binding_ordinal': row['binding_ordinal'], 'security_id': row['binding']['security_id'],
            'whole_binding_sha256': m.digest(row['binding']), 'semantic_binding_sha256': row['binding']['row_sha256'],
            'role': role, 'table': 'stocks' if role == 'Sharadar_RAW_full_window' else None,
            'ticker': route['current_metadata_row']['ticker'] if role == 'Sharadar_RAW_full_window' else None,
            'refusal_reason': None})
    for row in frame['funds']:
        assignments.append({'fund_ordinal': row['fund_ordinal'], 'own_ETF': row['ticker'],
            'role': 'Sharadar_RAW_full_window', 'table': 'funds',
            'ticker': row['route']['current_metadata_row']['ticker'], 'route_sha256': m.digest(row['route'])})
    return {'schema': m.prices.PLAN_PRIVATE_SCHEMA, 'ac_summary_sha256': m.prices.AC_SUMMARY_SHA256,
        'ac_frame_pin': m.AC_PIN, 'native_specification_sha256': m.prices.NATIVE_SPECIFICATION_SHA256,
        'full_axis_sha256': m.prices.FULL_AXIS_SHA256, 'price_sessions': [], 'assignments': assignments, 'requests': []}


def aa_for(case):
    frame = case['frame']
    stocks = []
    for row in frame['stocks']:
        binding = row['binding']
        tokens = case['originals'][binding['source_row_sha256']]
        stocks.append({'binding_ordinal': row['binding_ordinal'], 'binding': copy.deepcopy(binding),
            'original_cusip_tokens': None,  # V2 must derive validated original_row, not trust this field.
            'original_row': {'currency': 'USD', 'figi': binding['composite_figi'], 'cusips': ','.join(tokens)}})
    return {'stocks': stocks, 'funds': copy.deepcopy(frame['funds']),
        'binding_contract': copy.deepcopy(frame.get('binding_contract', {}))}


def synthetic_original(item):
    row = item['original_row']
    return {'figi': row['figi'], 'tokens': tuple(row['cusips'].split(','))}


def run(case, monkeypatch, *, deadline=None):
    frame = case['frame']
    monkeypatch.setattr(m, 'EXPECTED_STOCKS', len(frame['stocks']))
    monkeypatch.setattr(m, 'EXPECTED_FUNDS', len(frame['funds']))
    monkeypatch.setattr(m.prices.ac, '_original', synthetic_original)
    source = {'AA': m.AA_PIN, 'AC': m.AC_PIN, 'AP_plan': m.AP_PIN,
        'genuine_binding_stream_sha256': m.prices.native.BINDING_STREAM_SHA256,
        'AW': inventory(case['active'], case['delisted'], case['mapping'])}
    return m._prepare_bound(aa_for(case), frame, plan_for(frame), case['active'], case['delisted'], case['mapping'], source, deadline)


def refused(code, operation):
    with pytest.raises(m.Refused) as caught: operation()
    assert m.finite(caught.value) == code


def test_strict_identity_conjunction_retains_every_stock_fund_native_and_conditional(case, monkeypatch):
    summary, private = run(case, monkeypatch)
    record = private.private_record()
    assert len(record['stocks']) == 4 and len(record['funds']) == 2
    assert summary['stock_count'] == 4 and summary['fund_count'] == 2
    assert summary['AP_stock_role_counts'] == {'Sharadar_RAW_full_window': 2,
        'pending_native_original_identity_source': 1, 'conditional_never_potential_empty_initial_holdings_required': 1}
    assert [row['binding'] for row in record['stocks']] == [row['binding'] for row in case['frame']['stocks']]
    assert record['stocks'][0]['route']['symbol'] == 'EOD-0.US'  # Not its Sharadar ticker.
    assert record['stocks'][2]['status'] == 'matched_current_crosswalk'
    assert record['stocks'][2]['route'] is not None
    assert record['stocks'][2]['validated_original_cusip_tokens'] == case['originals'][record['stocks'][2]['binding']['source_row_sha256']]
    assert record['stocks'][2]['qualified_current_cusip_tokens'] is None
    assert record['stocks'][3]['potential'] is False and record['stocks'][3]['route'] is not None
    assert summary['exact_FIGI_only_unresolved_count'] == 0
    assert summary['original_proof_counts'] == {'pass': 4, 'refused': 0, 'unavailable': 0}
    assert summary['all_original_rows_retained'] is summary['all_supplied_provider_rows_indexed'] is True
    assert all(summary[key] is False for key in m.FALSE_FLAGS)
    assert all(row['route']['query_window'] == [m.prices.FIRST, m.prices.LAST]
        for row in record['stocks'] + record['funds'] if row['route'] is not None)


def test_CUSIP_and_FIGI_checksums_are_exact_not_homoglyph_case_or_partial_aliases():
    assert m._cusip('037833100') and m._cusip('594918104')
    assert m._figi('BBG000B9XRY4') and m._isin('US0378331005')
    for value in ('037833101', '37833100', '0378331000', '０37833100', '03783310O', '037833100 '): assert not m._cusip(value)
    for value in ('bbg000b9xry4', 'BBG000B9XRY5', 'BBG000B9XRΥ4', 'BBG000B9XRY4 '): assert not m._figi(value)
    assert not m._isin('US0378331006')


@pytest.mark.parametrize('change,reason', [('figi_different', 'mapping_identifier_conflict'),
    ('figi_checksum', 'mapping_identifier_invalid'), ('cusip_checksum', 'mapping_identifier_invalid'),
    ('cusip_different', 'figi_only_no_cusip_link'), ('unknown_field', 'mapping_fields_unknown')])
def test_no_figi_hierarchy_alias_partial_CUSIP_or_unknown_mapping_field_route(case, monkeypatch, change, reason):
    row = case['mapping'][0]
    if change == 'figi_different': row['figi'] = figi(5000)
    elif change == 'figi_checksum': row['figi'] = row['figi'][:-1] + str((int(row['figi'][-1]) + 1) % 10)
    elif change == 'cusip_checksum': row['cusip'] = row['cusip'][:-1] + str((int(row['cusip'][-1]) + 1) % 10)
    elif change == 'cusip_different': row['cusip'] = cusip(8888)
    else: row['future_unknown'] = 'unrecognized'
    _, private = run(case, monkeypatch); result = private.private_record()['stocks'][0]
    assert result['status'] == 'unresolved' and result['route'] is None and result['reason'] == reason


def test_name_ticker_CIK_or_LEI_agreement_never_establishes_identity(case, monkeypatch):
    case['mapping'][0].update(figi=None, cusip=None, cik='same-company', lei='same-company')
    case['active'][0]['Name'] = case['frame']['stocks'][0]['route']['current_metadata_row']['ticker']
    _, private = run(case, monkeypatch)
    row = private.private_record()['stocks'][0]
    assert row['status'] == 'unresolved' and row['reason'] == 'no_identifier_match'


def test_complete_CUSIP_vocabulary_is_used_and_conflicting_first_token_is_not_ignored(case, monkeypatch):
    route = case['frame']['stocks'][0]['route']
    extra = cusip(9999)
    route['current_cusip_tokens'].insert(0, extra)
    _, private = run(case, monkeypatch)
    assert private.private_record()['stocks'][0]['route']['matched_cusip_tokens'] == [case['mapping'][0]['cusip']]
    case['mapping'].append(mapping('FOREIGN', figi(7000), extra)); case['active'].append(catalog('FOREIGN'))
    _, private = run(case, monkeypatch)
    assert private.private_record()['stocks'][0]['reason'] == 'mapping_identifier_conflict'


@pytest.mark.parametrize('change', ['bad_checksum', 'duplicate', 'homoglyph'])
def test_source_vocabulary_is_not_silently_trimmed_or_sanitized(case, monkeypatch, change):
    tokens = case['frame']['stocks'][0]['route']['current_cusip_tokens']
    if change == 'bad_checksum': tokens.append('037833101')
    elif change == 'duplicate': tokens.append(tokens[0])
    else: tokens.append('０37833100')
    if change == 'duplicate':
        refused('original_source', lambda: run(case, monkeypatch))
    else:
        _, private = run(case, monkeypatch)
        assert private.private_record()['stocks'][0]['reason'] == 'source_vocabulary_invalid'


def test_same_security_and_composite_repeated_intervals_are_one_owner_but_all_bindings_retained(case, monkeypatch):
    first = copy.deepcopy(case['frame']['stocks'][0]); first['binding_ordinal'] = 4
    first['binding']['candidate_first_session'] = '2022-01-01'
    first['binding']['row_sha256'] = 'f' * 64
    case['frame']['stocks'].append(first)
    summary, private = run(case, monkeypatch); rows = private.private_record()['stocks']
    assert rows[0]['route'] is not None and rows[4]['route'] is not None
    assert rows[0]['binding'] != rows[4]['binding']
    assert summary['repeated_source_owner_binding_count'] == 1 and len(rows) == 5


@pytest.mark.parametrize('change', ['different_ID_same_figi', 'same_ID_different_figi', 'CUSIP_owner', 'fund_overlap'])
def test_distinct_security_owners_cannot_be_merged_by_figi_CUSIP_or_shared_class(case, monkeypatch, change):
    a, b = case['frame']['stocks'][:2]
    if change == 'different_ID_same_figi': b['binding']['composite_figi'] = a['binding']['composite_figi']
    elif change == 'same_ID_different_figi': b['binding']['security_id'] = a['binding']['security_id']
    elif change == 'CUSIP_owner':
        b['route']['current_cusip_tokens'] = list(a['route']['current_cusip_tokens'])
        case['originals'][b['binding']['source_row_sha256']] = list(a['route']['current_cusip_tokens'])
    else:
        case['frame']['funds'][0]['route']['current_cusip_tokens'] = list(a['route']['current_cusip_tokens'])
    _, private = run(case, monkeypatch)
    assert private.private_record()['stocks'][0]['reason'] == 'source_owner_collision'


def test_all_duplicate_provider_rows_are_retained_and_agreeing_identity_owners_may_match(case, monkeypatch):
    case['mapping'].append(copy.deepcopy(case['mapping'][0]))
    case['active'].append(copy.deepcopy(case['active'][0]))
    case['delisted'].append(copy.deepcopy(case['active'][0]))
    summary, private = run(case, monkeypatch)
    stock = private.private_record()['stocks'][0]
    assert stock['route'] is not None and len(stock['mapping_indices']) == 2 and len(stock['catalog_references']) == 3
    assert summary['provider_row_counts']['mapping'] == 7
    assert summary['provider_duplicate_row_counts'] == {'active': 1, 'delisted': 0, 'mapping': 1}


def test_same_symbol_foreign_identifier_row_cannot_be_hidden_by_source_prefilter(case, monkeypatch):
    case['mapping'].append(mapping('EOD-0', figi(9000), cusip(9000)))
    _, private = run(case, monkeypatch)
    stock = private.private_record()['stocks'][0]
    assert stock['reason'] == 'mapping_identifier_conflict' and len(stock['mapping_indices']) == 2


@pytest.mark.parametrize('change,reason', [('currency', 'catalog_instrument_or_currency'),
    ('type', 'catalog_instrument_or_currency'), ('reused_code', 'catalog_identity_ambiguous'),
    ('isin_conflict', 'isin_conflict')])
def test_current_USD_instrument_and_ISIN_consistency_are_explicit(case, monkeypatch, change, reason):
    if change == 'currency': case['active'][0]['Currency'] = 'CAD'
    elif change == 'type': case['active'][0]['Type'] = 'UnknownStockType'
    elif change == 'reused_code':
        row = copy.deepcopy(case['active'][0]); row['Isin'] = 'US0378331005'; case['delisted'].append(row)
    else:
        case['active'][0]['Isin'] = 'US0378331005'; case['mapping'][0]['isin'] = 'US5949181045'
    _, private = run(case, monkeypatch)
    assert private.private_record()['stocks'][0]['reason'] == reason


def test_display_unicode_differences_are_observations_not_identity_aliases(case, monkeypatch):
    row = copy.deepcopy(case['active'][0]); row['Name'] = 'another display'; row['Country'] = 'display observation'
    row['Exchange'] = 'display venue'; case['delisted'].append(row)
    _, private = run(case, monkeypatch)
    assert private.private_record()['stocks'][0]['route'] is not None


def test_mapping_inventory_uses_actual_LF_and_preserves_unknown_fields_order_and_duplicates(case):
    active_raw, delisted_raw = raw(case['active']), raw(case['delisted'])
    expected = inventory(case['active'], case['delisted'], case['mapping'])
    a, d, rows = m._inventories(active_raw, delisted_raw, case['mapping'], expected, None)
    assert len(a) == 6 and not d and rows == case['mapping']
    wrong = copy.deepcopy(expected)
    wrong['mapping']['ordered_records_sha256'] = hashlib.sha256(
        b''.join(raw(row) + b'\\n' for row in case['mapping'])).hexdigest()
    refused('inventory', lambda: m._inventories(active_raw, delisted_raw, case['mapping'], wrong, None))
    stripped = copy.deepcopy(case['mapping']); stripped[0]['unknown'] = 'retained'
    captured = inventory(case['active'], case['delisted'], stripped)
    refused('inventory', lambda: m._inventories(active_raw, delisted_raw, case['mapping'], captured, None))
    refused('inventory', lambda: m._inventories(active_raw, delisted_raw, case['mapping'][::-1], expected, None))


def test_catalog_byte_pin_checked_before_JSON_and_inventory_counts_reject_bools(case, monkeypatch):
    expected = inventory(case['active'], case['delisted'], case['mapping'])
    monkeypatch.setattr(m.catalogs, 'checked_symbol_rows', lambda *args: pytest.fail('JSON before pin check'))
    refused('inventory', lambda: m._inventories(b'[]', raw(case['delisted']), case['mapping'], expected, None))
    expected['mapping']['row_count'] = True
    refused('inventory', lambda: m._inventory_metadata(expected))


def test_prepare_compares_supplied_full_bindings_and_plan_hashes_without_adding_a_permission_switch(case, monkeypatch):
    frame = case['frame']; monkeypatch.setattr(m, 'EXPECTED_STOCKS', 4); monkeypatch.setattr(m, 'EXPECTED_FUNDS', 2)
    ac_raw = raw(frame); monkeypatch.setattr(m, 'AC_PIN', m.pin(ac_raw))
    plan = plan_for(frame); ap_raw = raw(plan); monkeypatch.setattr(m, 'AP_PIN', m.pin(ap_raw))
    # Matching-engine fixtures stand in for already validated AC content; the
    # unchanged frozen AC validator remains mandatory in production prepare().
    monkeypatch.setattr(m.prices, '_source_ac', lambda supplied, summary: copy.deepcopy(frame))
    rows = [row['binding'] for row in frame['stocks']]
    aa = aa_for(case); aa_raw = raw(aa); monkeypatch.setattr(m, 'AA_PIN', m.pin(aa_raw))
    frame['source_pins'] = {'aa_frame': m.AA_PIN}
    ac_raw = raw(frame); monkeypatch.setattr(m, 'AC_PIN', m.pin(ac_raw)); plan['ac_frame_pin'] = m.AC_PIN
    ap_raw = raw(plan); monkeypatch.setattr(m, 'AP_PIN', m.pin(ap_raw))
    monkeypatch.setattr(m.evidence, 'inspect', lambda *args, **kwargs: ({}, None))
    monkeypatch.setattr(m.evidence, '_decode', lambda supplied, deadline: copy.deepcopy(aa))
    monkeypatch.setattr(m.prices.ac, '_original', synthetic_original)
    kwargs = {'expected_aa_routing_summary': {}, 'expected_ac_summary': {},
        'expected_aw_inventory': inventory(case['active'], case['delisted'], case['mapping'])}
    supplied = [rows, aa_raw, ac_raw, ap_raw, raw(case['active']), raw(case['delisted']), case['mapping']]
    for index in (1, 2, 3):
        changed_raw = list(supplied); changed_raw[index] += b'\n'
        refused('source_pin', lambda changed_raw=changed_raw: m.prepare(*changed_raw, **kwargs))
    summary, _ = m.prepare(*supplied, **kwargs)
    assert summary['stock_count'] == 4 and summary['crosswalk_admitted'] is False
    changed = copy.deepcopy(rows); changed[0]['candidate_last_session'] = '2021-01-01'
    refused('genuine_binding', lambda: m.prepare(changed, aa_raw, ac_raw, ap_raw, raw(case['active']), raw(case['delisted']), case['mapping'], **kwargs))
    broken_plan = copy.deepcopy(plan); broken_plan['assignments'][0]['whole_binding_sha256'] = 'a' * 64
    broken_raw = raw(broken_plan); monkeypatch.setattr(m, 'AP_PIN', m.pin(broken_raw))
    refused('plan', lambda: m.prepare(rows, aa_raw, ac_raw, broken_raw, raw(case['active']), raw(case['delisted']), case['mapping'], **kwargs))


def test_expired_deadline_stops_before_any_match_and_summary_is_closed(case, monkeypatch):
    refused('deadline', lambda: run(case, monkeypatch, deadline=time.monotonic() - 1))
    summary, _ = run(case, monkeypatch)
    bad = copy.deepcopy(summary); bad['raw_symbols'] = ['PRIVATE']
    refused('summary', lambda: m.validate_summary(bad))
    bad = copy.deepcopy(summary); bad['source_pins']['AW']['mapping']['row_count'] = True
    refused('inventory', lambda: m.validate_summary(bad))
    bad = copy.deepcopy(summary); bad['provider_row_counts']['active'] += 1
    refused('summary', lambda: m.validate_summary(bad))


def test_private_crosswalk_repr_pickle_and_mutability_do_not_disclose_or_grant(case, monkeypatch):
    summary, private = run(case, monkeypatch)
    assert 'EOD-' not in repr(private) and 'BBG' not in repr(private)
    with pytest.raises(TypeError): pickle.dumps(private)
    with pytest.raises(TypeError): private.sha256 = 'a' * 64
    first = private.private_record(); first['stocks'][0]['route'] = None
    assert private.private_record()['stocks'][0]['route'] is not None
    assert m.pin(m.canonical(private.private_record())) == summary['private_payload_pin']
    public = m.canonical(summary)
    assert b'EOD-0' not in public and b'BBG' not in public and 'café'.encode('utf-8') not in public


def test_production_scope_still_requires_all_originals_and_all_funds():
    assert m.EXPECTED_STOCKS == 6151 and m.EXPECTED_FUNDS == 8
    assert m.AA_PIN['byte_count'] == 19895631
    assert m.AC_PIN['byte_count'] == 16344399 and m.AP_PIN['byte_count'] == 2927971
    assert all(value is False for key, value in m.profile_record().items() if key in m.FALSE_FLAGS)


def test_full6151_and_eight_fund_partition_is_retained_with_native5_and_conditional510(monkeypatch):
    stocks, funds, active, mappings = [], [], [], []
    for index in range(6151):
        native = 5636 <= index < 5641
        conditional = index >= 5641
        role = ('pending_native_original_identity_source' if native else
            'conditional_never_potential_empty_initial_holdings_required' if conditional else 'Sharadar_RAW_full_window')
        f, c, code = figi(index + 10000), cusip(index + 10000), 'S' + str(index)
        binding = {'security_id': 'full-synthetic-' + str(index), 'composite_figi': f,
            'row_sha256': hashlib.sha256(str(index).encode()).hexdigest(),
            'candidate_first_session': '2020-12-31', 'candidate_last_session': '2026-10-13',
            'source_row_sha256': hashlib.sha256(('full-original-' + str(index)).encode()).hexdigest(),
            'identity_evidence_sha256': hashlib.sha256(('full-evidence-' + str(index)).encode()).hexdigest()}
        route = None if native else {'table': 'stocks', 'current_metadata_row': {'ticker': code, 'figi': f},
            'current_cusip_tokens': [c]}
        stocks.append({'binding_ordinal': index, 'binding': binding, 'potential': not conditional,
            'disposition': 'refused' if native else 'conditional_never_potential' if conditional else 'routed',
            'route': route, 'role': role})
        active.append(catalog(code)); mappings.append(mapping(code, f, c))
    for index, ticker in enumerate(('SPY','QQQ','SOXX','XLV','REMX','XLE','XLI','XLF')):
        f, c = figi(index + 50000), cusip(index + 50000)
        route = {'table': 'funds', 'current_metadata_row': {'ticker': ticker, 'figi': f},
            'current_cusip_tokens': [c], 'current_exchange_mic': 'ARCX'}
        funds.append({'fund_ordinal': index, 'ticker': ticker, 'disposition': 'routed', 'route': route})
        active.append(catalog(ticker, 'ETF')); mappings.append(mapping(ticker, f, c))
    originals = {row['binding']['source_row_sha256']: [cusip(index + 10000)] for index, row in enumerate(stocks)}
    full = {'originals': originals, 'frame': {'stocks': stocks, 'funds': funds}, 'active': active, 'delisted': [], 'mapping': mappings}
    summary, private = run(full, monkeypatch)
    record = private.private_record()
    assert summary['stock_count'] == len(record['stocks']) == 6151
    assert summary['fund_count'] == len(record['funds']) == 8
    assert summary['AP_stock_role_counts'] == {'Sharadar_RAW_full_window': 5636,
        'pending_native_original_identity_source': 5, 'conditional_never_potential_empty_initial_holdings_required': 510}
    assert summary['reason_counts']['stocks'] == {}
    assert summary['exact_FIGI_only_unresolved_count'] == 0
    assert summary['original_proof_counts'] == {'pass': 6151, 'refused': 0, 'unavailable': 0}
    assert summary['disposition_counts']['stocks'] == {'matched_current_crosswalk': 6151}
    assert sum(not row['potential'] for row in record['stocks']) == 510
    assert record['stocks'][-1]['binding'] == stocks[-1]['binding']
    assert record['funds'][-1]['ticker'] == 'XLF' and record['funds'][-1]['route'] is not None

def genuine_native_case(*, currency='USD'):
    original = m.evidence.routes.original
    composer = original.composer
    source = {'table': 'SF1', 'ticker': 'SYNTHETIC', 'permaticker': '1001',
        'figi': figi(5001), 'exchange': 'NYSE', 'category': 'Domestic Common Stock',
        'cusips': '037833100,594918104', 'currency': currency, 'sector': 'synthetic-sector',
        'industry': 'synthetic-industry', 'firstpricedate': '2020-01-02', 'lastpricedate': '2026-10-13',
        **{'unused_' + str(index): 'retained-' + str(index) for index in range(16)}}
    source_pin = original.source_row_digest(source)
    table, ticker, perma, f, exchange, mic, tokens, first, last = original._metadata(source)
    constructor_evidence = {'permaticker': perma, 'composite_figi': f, 'source_table': table,
        'ticker': ticker, 'cusips': list(tokens), 'exchange': exchange, 'exchange_mic': mic,
        'firstpricedate': first, 'lastpricedate': last, 'source_row_sha256': source_pin,
        'availability_semantics': composer.TICKERS_AVAILABILITY}
    evidence_pin = hashlib.sha256(composer.canonical_json_bytes(constructor_evidence)).hexdigest()
    binding = m.prices.native.figi.build_preliminary_qc_figi_binding(
        security_id=composer._safe_component('sharadar-composite-figi', f),
        issuer_id=composer._safe_component('sharadar-permaticker', perma), composite_figi=f,
        listing_id='sharadar-listing-' + evidence_pin[:24], diagnostic_current_ticker=ticker,
        diagnostic_exchange_mic=mic, candidate_first_session='2020-12-31',
        candidate_last_session='2026-10-13', source_snapshot_available_at='2026-10-13T23:00:00.000000Z',
        source_row_sha256=source_pin, identity_evidence_sha256=evidence_pin,
        security_master_admission_sha256=m.prices.native.ADMISSION_SHA256,
        admitted_mapping_inventory_sha256='f' * 64, admitted_mapping_count=1)
    row = {'binding_ordinal': 0, 'binding': binding, 'potential': True, 'disposition': 'refused',
        'route': None, 'role': 'pending_native_original_identity_source'}
    frame = {'stocks': [row], 'funds': [],
        'binding_contract': {'binding_stream_sha256': m.prices.native.BINDING_STREAM_SHA256}}
    aa = {'stocks': [{'binding_ordinal': 0, 'binding': copy.deepcopy(binding),
        'original_cusip_tokens': None, 'original_row': source}], 'funds': [],
        'binding_contract': copy.deepcopy(frame['binding_contract'])}
    return aa, frame, plan_for(frame)


@pytest.mark.parametrize('currency', ['USD', 'EUR'])
def test_genuine_original_constructor_derives_all_tokens_when_AA_token_field_is_none(currency, monkeypatch):
    aa, frame, plan = genuine_native_case(currency=currency)
    monkeypatch.setattr(m, 'EXPECTED_STOCKS', 1)
    monkeypatch.setattr(m, 'EXPECTED_FUNDS', 0)
    sources = m._sources(aa, frame, plan)
    stock = sources[0]
    assert stock['original_tokens'] == ['037833100', '594918104']
    assert stock['tokens'] == ['037833100', '594918104']
    assert stock['current_tokens'] is None
    assert stock['original_reporting_currency_not_usd'] is (currency != 'USD')
    assert stock['original_source_row_sha256'] == aa['stocks'][0]['binding']['source_row_sha256']
    assert stock['original_identity_evidence_sha256'] == aa['stocks'][0]['binding']['identity_evidence_sha256']


@pytest.mark.parametrize('field,value', [
    ('unused_15', 'changed-unused-column'), ('cusips', '037833100'),
    ('figi', figi(5002)), ('firstpricedate', '2020-02-02')])
def test_genuine_full_28_field_original_hash_is_checked_before_matching(field, value, monkeypatch):
    aa, frame, plan = genuine_native_case()
    monkeypatch.setattr(m, 'EXPECTED_STOCKS', 1)
    monkeypatch.setattr(m, 'EXPECTED_FUNDS', 0)
    aa['stocks'][0]['original_row'][field] = value
    assert_original_proof_refused(aa, frame, plan)


@pytest.mark.parametrize('field,value', [
    ('identity_evidence_sha256', 'a' * 64), ('listing_id', 'sharadar-listing-' + 'b' * 24),
    ('issuer_id', 'different-original-issuer'), ('composite_figi', figi(5002)),
    ('diagnostic_exchange_mic', 'XNAS'), ('candidate_last_session', '2026-10-14')])
def test_genuine_original_evidence_and_constructor_predicates_are_not_replaced_by_a_hash_claim(field, value, monkeypatch):
    aa, frame, plan = genuine_native_case()
    monkeypatch.setattr(m, 'EXPECTED_STOCKS', 1)
    monkeypatch.setattr(m, 'EXPECTED_FUNDS', 0)
    frame['stocks'][0]['binding'][field] = value
    aa['stocks'][0]['binding'][field] = value
    plan = plan_for(frame)
    assert_original_proof_refused(aa, frame, plan)


def test_union_is_uniform_deterministic_and_retains_separate_original_and_current_provenance(case, monkeypatch):
    extra = cusip(700001)
    case['frame']['stocks'][0]['route']['current_cusip_tokens'].insert(0, extra)
    case['mapping'].append(mapping('EOD-0', figi(1), extra))
    summary, private = run(case, monkeypatch)
    stocks = private.private_record()['stocks']
    assert stocks[0]['validated_original_cusip_tokens'] == [cusip(100)]
    assert stocks[0]['qualified_current_cusip_tokens'] == [extra, cusip(100)]
    assert stocks[0]['available_source_cusip_union'] == sorted([cusip(100), extra])
    assert stocks[2]['validated_original_cusip_tokens'] == [cusip(102)]
    assert stocks[2]['qualified_current_cusip_tokens'] is None
    assert stocks[2]['status'] == 'matched_current_crosswalk'
    assert summary['original_proof_counts'] == {'pass': 4, 'refused': 0, 'unavailable': 0}


def test_current_qualified_vocabulary_cannot_discard_an_authenticated_original_token(case, monkeypatch):
    case['frame']['stocks'][0]['route']['current_cusip_tokens'] = [cusip(800001)]
    refused('original_source', lambda: run(case, monkeypatch))


def test_AA_and_AC_fund_identifier_objects_must_match_exactly(case, monkeypatch):
    monkeypatch.setattr(m, 'EXPECTED_STOCKS', 4)
    monkeypatch.setattr(m, 'EXPECTED_FUNDS', 2)
    monkeypatch.setattr(m.prices.ac, '_original', synthetic_original)
    aa, frame = aa_for(case), case['frame']
    aa['funds'][-1]['route']['current_exchange_mic'] = 'XNAS'
    refused('original_source', lambda: m._sources(aa, frame, plan_for(frame)))


def test_v2_profile_adds_exact_AA_pin_without_an_operational_capability():
    profile = m.profile_record()
    assert profile['schema'].endswith('-v2') and profile['AA_pin'] == m.AA_PIN
    assert profile['original_token_provenance'].startswith('AA_original_row_revalidated')
    assert profile['fund_proof'].startswith('AA_AC_full')
    assert all(profile[key] is False for key in m.FALSE_FLAGS)

@pytest.mark.parametrize('field,value', [
    ('category', 'ETF'), ('table', 'SEP'), ('firstpricedate', '2026-10-14'),
    ('cusips', 'invalid-original-vocabulary')])
def test_repinning_a_synthetic_original_row_does_not_bypass_frozen_constructor_semantics(field, value, monkeypatch):
    aa, frame, plan = genuine_native_case()
    monkeypatch.setattr(m, 'EXPECTED_STOCKS', 1)
    monkeypatch.setattr(m, 'EXPECTED_FUNDS', 0)
    source = aa['stocks'][0]['original_row']
    source[field] = value
    new_pin = m.evidence.routes.original.source_row_digest(source)
    frame['stocks'][0]['binding']['source_row_sha256'] = new_pin
    aa['stocks'][0]['binding']['source_row_sha256'] = new_pin
    plan = plan_for(frame)
    assert_original_proof_refused(aa, frame, plan)

@pytest.mark.parametrize('kind', ['different_Code', 'different_class', 'different_currency'])
def test_all_catalog_ISIN_owners_are_checked_without_prefiltering_to_the_selected_symbol(case, monkeypatch, kind):
    valid_isin = 'US0378331005'
    case['mapping'][0]['isin'] = valid_isin
    case['active'][0]['Isin'] = valid_isin
    other = catalog('OTHER', isin=valid_isin)
    if kind == 'different_class': other.update(Code=case['active'][0]['Code'], Type='ETF')
    if kind == 'different_currency': other.update(Code=case['active'][0]['Code'], Currency='GBP')
    case['delisted'].append(other)
    _, private = run(case, monkeypatch)
    row = private.private_record()['stocks'][0]
    assert row['status'] == 'unresolved' and row['route'] is None
    assert row['reason'] in ('isin_conflict', 'catalog_identity_ambiguous')


def test_agreeing_global_ISIN_catalog_duplicates_are_preserved_without_inventing_new_owners(case, monkeypatch):
    valid_isin = 'US0378331005'
    case['mapping'][0]['isin'] = valid_isin
    case['active'][0]['Isin'] = valid_isin
    case['delisted'].append(copy.deepcopy(case['active'][0]))
    summary, private = run(case, monkeypatch)
    row = private.private_record()['stocks'][0]
    assert row['status'] == 'matched_current_crosswalk'
    assert len(row['catalog_references']) == 2
    assert summary['provider_row_counts']['delisted'] == 1


def test_nullable_or_opaque_catalog_display_never_becomes_identity_or_a_sanitized_alias(case, monkeypatch):
    case['active'][0].update(Name='line\n\x00\ud800', Country=None)
    _, private = run(case, monkeypatch)
    assert private.private_record()['stocks'][0]['status'] == 'matched_current_crosswalk'
    for key in ('Name', 'Country', 'Exchange'):
        assert key not in private.private_record()['stocks'][0]['route']
    public = m.canonical(run(case, monkeypatch)[0])
    assert b'line' not in public and b'\\ud800' not in public

def assert_original_proof_refused(aa, frame, plan):
    sources = m._sources(aa, frame, plan)
    assert len(sources) == 1 and sources[0]['original_proof'] == 'refused'
    assert sources[0]['original_tokens'] is None
    indexes = m._indexes([], [], [], sources, None)
    result = m._match(sources[0], indexes, None)
    assert result['status'] == 'unresolved' and result['route'] is None
    assert result['reason'] == 'original_source_refused'


def test_missing_original_row_remains_a_named_unresolved_binding_not_a_current_token_fallback(case, monkeypatch):
    frame = case['frame']
    monkeypatch.setattr(m, 'EXPECTED_STOCKS', 4)
    monkeypatch.setattr(m, 'EXPECTED_FUNDS', 2)
    monkeypatch.setattr(m.prices.ac, '_original', synthetic_original)
    aa = aa_for(case)
    aa['stocks'][0]['original_row'] = None
    source = {'AA': m.AA_PIN, 'AC': m.AC_PIN, 'AP_plan': m.AP_PIN,
        'genuine_binding_stream_sha256': m.prices.native.BINDING_STREAM_SHA256,
        'AW': inventory(case['active'], case['delisted'], case['mapping'])}
    summary, private = m._prepare_bound(aa, frame, plan_for(frame), case['active'], case['delisted'],
        case['mapping'], source, None)
    rows = private.private_record()['stocks']
    assert len(rows) == 4 and rows[0]['binding'] == frame['stocks'][0]['binding']
    assert rows[0]['reason'] == 'original_source_unavailable' and rows[0]['route'] is None
    assert rows[0]['validated_original_cusip_tokens'] is None
    assert rows[0]['qualified_current_cusip_tokens'] == frame['stocks'][0]['route']['current_cusip_tokens']
    assert summary['original_proof_counts'] == {'pass': 3, 'refused': 0, 'unavailable': 1}
    assert summary['disposition_counts']['stocks']['matched_current_crosswalk'] == 3
    for mutation in (True, -1, 4):
        changed = copy.deepcopy(summary)
        changed['original_proof_counts']['pass'] = mutation
        refused('summary', lambda: m.validate_summary(changed))
