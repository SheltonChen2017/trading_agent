"""Synthetic all-binding identities and routes; native-denied focused selection."""
import copy
import inspect
import json
import pickle

import pytest

from scripts import arv2_r298_sharadar_all_routes as m
from tests.analyst_revisions_v2 import test_r298_sharadar_eligibility_observation as fixture


def source(index, *, ticker=None, first='2000-01-03', last='2026-10-26', cusips=None):
    row = dict.fromkeys(m.ORIGINAL_FIELDS, '')
    row.update(table='SF1', ticker=ticker or 'SYN' + str(index), permaticker=str(1000 + index),
        name='Synthetic issuer caf\u00e9', exchange='NASDAQ', isdelisted='N',
        category='Domestic Common Stock', figi=f'BBG{index:09d}',
        cusips=cusips or f'{index:09d}', currency='USD', sector='Technology',
        industry='Synthetic', firstpricedate=first, lastpricedate=last, lastupdated='2026-10-26')
    return row


def binding(row, count, *, first='2013-01-02', last='2026-10-13'):
    c = m.original.composer
    evidence = {'permaticker': row['permaticker'], 'composite_figi': row['figi'],
        'source_table': 'SF1', 'ticker': row['ticker'], 'cusips': list(c._sharadar_cusips(row['cusips'])),
        'exchange': row['exchange'], 'exchange_mic': 'XNAS', 'firstpricedate': row['firstpricedate'],
        'lastpricedate': row['lastpricedate'] or None, 'source_row_sha256': m.original.source_row_digest(row),
        'availability_semantics': c.TICKERS_AVAILABILITY}
    pin = m.sha(c.canonical_json_bytes(evidence))
    return m.original.identity_join.figi.build_preliminary_qc_figi_binding(
        security_id='sharadar-composite-figi-' + row['figi'],
        issuer_id='sharadar-permaticker-' + row['permaticker'], composite_figi=row['figi'],
        listing_id='sharadar-listing-' + pin[:24], diagnostic_current_ticker=row['ticker'],
        diagnostic_exchange_mic='XNAS', candidate_first_session=first, candidate_last_session=last,
        source_snapshot_available_at='2026-09-14T00:33:29.843989Z',
        source_row_sha256=evidence['source_row_sha256'], identity_evidence_sha256=pin,
        security_master_admission_sha256='a' * 64, admitted_mapping_inventory_sha256='b' * 64,
        admitted_mapping_count=count)


def contract(bindings):
    return {'binding_count': len(bindings), 'binding_stream_sha256': m.sha(b''.join(
        m.original.identity_join.figi._canonical(row) for row in bindings)),
        'security_master_admission_sha256': 'a' * 64, 'admitted_mapping_inventory_sha256': 'b' * 64}


def case(count=2):
    originals = [source(index) for index in range(1, count + 1)]
    bindings = sorted([binding(row, count) for row in originals], key=lambda row: row['security_id'])
    stocks = [fixture.metadata(row['ticker'], index) for index, row in enumerate(originals, 1)]
    funds = [fixture.metadata(ticker, index, fund=True) for index, ticker in enumerate(m.current.ETF_TICKERS, 20)]
    return bindings, originals, stocks, funds


def join(data, **kwargs):
    return m.join(*data, binding_contract=kwargs.pop('binding_contract', contract(data[0])), **kwargs)


def refused(code, callback):
    with pytest.raises(m.Refused) as error:
        callback()
    assert m.finite(error.value) == code


@pytest.fixture(autouse=True)
def no_operations(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('frozen operation or witness-only selector used')
    for module in (m.current.previous, m.current.previous.previous):
        monkeypatch.setattr(module, 'observe', deny)
        monkeypatch.setattr(module, '_fetch', deny)
    monkeypatch.setattr(m.original, 'verify', deny)
    monkeypatch.setattr(m.original.identity_join, 'join', deny)
    monkeypatch.setattr(m.current, 'require_probe_routes', deny)


def test_every_binding_has_original_evidence_current_route_and_full_private_payload():
    data = case()
    summary, private = join(data)
    record = private.private_record()
    assert record['binding_contract'] == contract(data[0])
    assert [item['binding'] for item in record['stocks']] == data[0]
    assert [item['original_row'] for item in record['stocks']] == data[1]
    assert [item['current_candidate_rows'] for item in record['stocks']] == [[row] for row in data[2]]
    assert summary['disposition_counts'] == {'stocks': {'routed': 2}, 'funds': {'routed': 8}}
    assert summary['refusal_counts'] == {'stocks': {}, 'funds': {}}
    assert summary['private_payload_sha256'] == m.sha(m.canonical(record))
    assert len(private.price_routes()) == 10
    assert all(row['route_key'] == row['security_id'] for row in private.price_routes()[:2])
    assert all(row['security_id'] is row['source_binding_sha256'] is None
        and row['route_key'].startswith('own-etf-') for row in private.price_routes()[2:])
    assert all(row['required_first_date'] == '2020-12-31'
        and row['required_last_date'] == '2026-10-13' for row in private.price_routes())
    encoded = m.canonical(summary)
    for text in ('SYN1', 'BBG000000001', '1001', '000000001', 'NASDAQ', 'Synthetic', 'SPY'):
        assert text.encode() not in encoded
    assert summary['scope'] == 'supplied_current_route_crosscheck_not_admission'


def test_original_hashes_equal_actual_frozen_composer_semantics(monkeypatch):
    row = source(1, cusips='000000001, ABCDEF123')
    monkeypatch.setattr(m.original.composer, '_iter_sharadar_rows', lambda *_: iter([dict(row)]))
    candidates, refusals, counts = m.original.composer._ticker_candidates(object())
    assert refusals == {} and not any(counts.values())
    original_binding = binding(row, 1)
    assert original_binding['source_row_sha256'] == candidates[row['ticker']].source_row_sha256
    assert original_binding['identity_evidence_sha256'] == candidates[row['ticker']].identity_evidence_sha256
    stock = fixture.metadata(row['ticker'], 1); stock['cusips'] = row['cusips'] + ', ABCDEF124'
    summary, private = join(([original_binding], [row], [stock], case()[3]))
    assert summary['disposition_counts']['stocks'] == {'routed': 1}
    assert private.private_record()['stocks'][0]['original_cusip_tokens'] == ['000000001', 'ABCDEF123']


def test_bounded_supplied_CSV_and_rows_have_identical_result_without_response_authentication_claim():
    data = case()
    row_summary, row_private = join(data)
    csv_data = (data[0], data[1], fixture.csv_bytes(m.current.FIELDS, data[2]),
        fixture.csv_bytes(m.current.FIELDS, data[3]))
    csv_summary, csv_private = join(csv_data)
    assert csv_summary == row_summary and csv_private.private_record() == row_private.private_record()
    bad = (data[0], data[1], b'not_the_header\n', csv_data[3])
    refused('current_catalog', lambda: join(bad))


@pytest.mark.parametrize('original_text,current_text', [
    ('000000001,ABCDEF123', '000000001 ABCDEF123 ABCDEF124'),
    ('000000001 ABCDEF123', '000000001, ABCDEF123, ABCDEF124'),
    ('000000001 abcdef123', '000000001 ABCDEF123')])
def test_complete_vocabulary_is_separate_from_preserved_historical_hash_semantics(original_text, current_text):
    data = case(1)
    data[1][0]['cusips'] = original_text
    data[0][0] = binding(data[1][0], 1)
    data[2][0]['cusips'] = current_text
    summary, private = join(data)
    assert summary['disposition_counts']['stocks'] == {'routed': 1}
    assert private.private_record()['stocks'][0]['original_cusip_tokens'] == ['000000001', 'ABCDEF123']


@pytest.mark.parametrize('kind', ['missing', 'ambiguous', 'identity', 'currency', 'bad_vocabulary'])
def test_original_binding_never_disappears_on_source_mismatch(kind):
    data = case()
    if kind == 'missing': data[1].pop(0)
    elif kind == 'ambiguous': data[1].append(copy.deepcopy(data[1][0]))
    else:
        if kind == 'identity': data[0][0]['identity_evidence_sha256'] = 'c' * 64
        elif kind == 'currency': data[1][0]['currency'] = 'EUR'
        else: data[1][0]['cusips'] = '000000001;ABCDEF123'
        if kind != 'identity':
            data[0][0] = binding(data[1][0], 2)
        else:
            seed = dict(data[0][0]); seed.pop('row_sha256')
            data[0][0]['row_sha256'] = m.sha(m.original.identity_join.figi._canonical(seed))
    summary, private = join(data)
    record = private.private_record()
    assert len(record['stocks']) == 2 and len(record['funds']) == 8
    expected = {'missing': 'original_row_missing', 'ambiguous': 'original_row_ambiguous',
        'identity': 'original_identity', 'currency': 'original_identity', 'bad_vocabulary': 'original_vocabulary'}[kind]
    assert record['stocks'][0]['reason'] == expected
    assert summary['refusal_counts']['stocks'] == {expected: 1}
    refused('routes_incomplete', private.price_routes)


@pytest.mark.parametrize('kind', ['perma', 'figi', 'ticker', 'cross_perma', 'cross_figi', 'cross_ticker',
    'later_token_same', 'later_token_cross', 'malformed_poison'])
def test_collision_indexes_cover_both_tables_every_token_and_poison(kind):
    data = case()
    other = fixture.metadata('OTHER', 99, fund=kind.startswith('cross') or kind == 'later_token_cross')
    if kind in ('perma', 'figi', 'ticker', 'cross_perma', 'cross_figi', 'cross_ticker'):
        field = {'perma': 'permaticker', 'figi': 'figi', 'ticker': 'ticker'}[kind.removeprefix('cross_')]
        other[field] = data[2][0][field]
    elif kind == 'malformed_poison':
        other['cusips'] = '000000001;INVALID'
    else:
        data[2][0]['cusips'] += ' ABCDEF123'
        other['cusips'] += ' ABCDEF123'
    (data[3] if kind.startswith('cross') or kind == 'later_token_cross' else data[2]).append(other)
    summary, private = join(data)
    assert private.private_record()['stocks'][0]['reason'] == 'current_collision'
    assert summary['disposition_counts']['stocks'] == {'refused': 1, 'routed': 1}
    refused('routes_incomplete', private.price_routes)


@pytest.mark.parametrize('field,value,reason', [
    ('permaticker', '9999', 'current_identity_missing'), ('figi', 'BBG999999999', 'current_identity_missing'),
    ('ticker', 'RENAMED', 'current_identity_changed'), ('exchange', 'NYSE', 'current_identity_changed'),
    ('currency', 'EUR', 'current_shape'), ('category', 'Preferred Stock', 'current_shape'),
    ('cusips', '', 'current_shape'), ('cusips', '000000001;ABCDEF123', 'current_shape'),
    ('cusips', 'ABCDEF123', 'current_vocabulary_changed'),
    ('firstpricedate', '2021-01-04', 'current_interval'), ('lastpricedate', '2026-10-12', 'current_interval'),
    ('lastupdated', 'bad', 'current_interval'), ('isdelisted', '?', 'current_shape')])
def test_changed_route_is_refused_without_ticker_alias_currency_or_interval_fallback(field, value, reason):
    data = case(); data[2][0][field] = value
    _, private = join(data)
    assert private.private_record()['stocks'][0]['reason'] == reason
    refused('routes_incomplete', private.price_routes)


def test_current_interval_must_cover_original_required_interval_never_shrink_it():
    data = case(1)
    data[0][0] = binding(data[1][0], 1, first='2022-01-03', last='2025-12-31')
    data[2][0].update(firstpricedate='2022-01-04', lastpricedate='2025-12-30')
    _, private = join(data)
    stock = private.private_record()['stocks'][0]
    assert stock['required_first_date'] == '2022-01-03' and stock['required_last_date'] == '2025-12-31'
    assert stock['reason'] == 'current_interval' and stock['route'] is None
    assert stock['current_candidate_rows'] == data[2]


def test_disjoint_original_candidate_interval_remains_explicit_not_a_price_based_exclusion():
    data = case(1)
    data[0][0] = binding(data[1][0], 1, first='2013-01-02', last='2020-12-30')
    data[2].clear()  # No current price route is invented for a disjoint candidate.
    summary, private = join(data)
    stock = private.private_record()['stocks'][0]
    assert stock['binding'] == data[0][0] and stock['original_row'] == data[1][0]
    assert stock['disposition'] == 'outside_window' and stock['reason'] == 'original_candidate_interval_disjoint'
    assert stock['route'] is None and stock['required_first_date'] is stock['required_last_date'] is None
    assert summary['disposition_counts']['stocks'] == {'outside_window': 1}
    assert len(private.price_routes()) == 8


@pytest.mark.parametrize('kind', ['missing', 'ambiguous', 'wrong_currency', 'cross_token', 'interval'])
def test_eight_own_etfs_each_receive_a_route_or_named_refusal(kind):
    data = case()
    if kind == 'missing': data[3].pop(0)
    elif kind == 'ambiguous': data[3].append(dict(data[3][0]))
    elif kind == 'wrong_currency': data[3][0]['currency'] = 'EUR'
    elif kind == 'cross_token': data[2][0]['cusips'] += ' ' + data[3][0]['cusips']
    else: data[3][0]['firstpricedate'] = '2021-01-04'
    _, private = join(data)
    funds = private.private_record()['funds']
    assert len(funds) == 8 and funds[0]['disposition'] == 'refused'
    refused('routes_incomplete', private.price_routes)


def test_unrelated_unknown_vocabulary_is_retained_unknown_not_global_no_collision():
    data = case(); extra = fixture.metadata('OTHER', 99); extra['cusips'] = 'unknown'
    data[2].append(extra)
    summary, private = join(data)
    assert len(private.price_routes()) == 10
    assert summary['catalog_unknown_vocabulary_row_count'] == 1


def test_original_shared_issuer_is_not_rejected_as_a_corrupt_catalog_or_silently_dropped():
    data = case()
    data[1][1]['permaticker'] = data[1][0]['permaticker']
    data[2][1]['permaticker'] = data[2][0]['permaticker']
    data[0][1] = binding(data[1][1], 2)
    summary, private = join(data)
    assert len(private.private_record()['stocks']) == 2
    assert summary['refusal_counts']['stocks'] == {'current_collision': 2}
    refused('routes_incomplete', private.price_routes)


def test_dense_candidate_ownership_refuses_before_materializing_an_unbounded_copy_list(monkeypatch):
    data = case()
    extra = fixture.metadata(data[2][0]['ticker'], 99)
    data[2].append(extra)
    monkeypatch.setattr(m, 'MAX_CANDIDATE_ROWS_PER_ITEM', 1)
    refused('candidate_bound', lambda: join(data))


@pytest.mark.parametrize('field,limit', [('MAX_CANDIDATE_ROWS', 5), ('MAX_CANDIDATE_BYTES', 64)])
def test_aggregate_candidate_rows_and_canonical_bytes_cannot_amplify_across_bindings(monkeypatch, field, limit):
    monkeypatch.setattr(m, field, limit)
    refused('candidate_bound', lambda: join(case()))


def test_full_private_graph_budget_stops_during_join_without_building_every_binding_and_fund(monkeypatch):
    data = case()
    _, private = join(data)
    first = private.private_record()['stocks'][0]
    limit = m.PRIVATE_ENVELOPE_RESERVE + len(m.canonical(first)) + 100
    calls, candidate_rows = [], m._candidate_rows
    def counted(*args, **kwargs):
        calls.append('candidate item')
        return candidate_rows(*args, **kwargs)
    monkeypatch.setattr(m, '_candidate_rows', counted)
    monkeypatch.setattr(m, 'MAX_PRIVATE_BYTES', limit)
    refused('private_payload', lambda: join(data))
    assert len(calls) == 2 < len(data[0]) + len(data[3])


@pytest.mark.parametrize('kind', ['count', 'order', 'duplicate', 'stream', 'admission', 'inventory', 'rowhash', 'subset'])
def test_full_original_binding_count_order_inventory_and_stream_are_mandatory(kind):
    data = case(); expected = contract(data[0]); code = 'binding_inventory'
    if kind == 'count': expected['binding_count'] += 1
    elif kind == 'order': data[0].reverse()
    elif kind == 'duplicate': data[0][1] = dict(data[0][0])
    elif kind == 'stream': expected['binding_stream_sha256'] = 'c' * 64; code = 'binding_stream'
    elif kind == 'admission': expected['security_master_admission_sha256'] = 'c' * 64; code = 'binding'
    elif kind == 'inventory': expected['admitted_mapping_inventory_sha256'] = 'c' * 64
    elif kind == 'rowhash': data[0][0]['row_sha256'] = 'c' * 64; code = 'binding'
    else: data[0].pop(); expected = contract(data[0])
    refused(code, lambda: join(data, binding_contract=expected))


@pytest.mark.parametrize('kind', ['bool_count', 'extra', 'hash_subclass', 'missing', 'count_zero'])
def test_contract_is_closed_primitive_bounded_metadata(kind):
    class Text(str): pass
    data = case(); expected = contract(data[0])
    if kind == 'bool_count': expected['binding_count'] = True
    elif kind == 'extra': expected['authorized'] = True
    elif kind == 'hash_subclass': expected['binding_stream_sha256'] = Text(expected['binding_stream_sha256'])
    elif kind == 'missing': expected.pop('binding_stream_sha256')
    else: expected['binding_count'] = 0
    refused('contract', lambda: join(data, binding_contract=expected))


def test_bounded_source_shape_binding_bytes_catalog_and_private_result(monkeypatch):
    data = case(); bad = copy.deepcopy(data); bad[1][0]['extra'] = ''
    refused('original_rows', lambda: join(bad))
    bad = copy.deepcopy(data); bad[1][0]['name'] = '\ud800'
    refused('original_rows', lambda: join(bad))
    bad = copy.deepcopy(data); bad[2][0]['table'] = 'OTHER'
    refused('current_catalog', lambda: join(bad))
    for field, code in [('MAX_ORIGINAL_BYTES', 'original_bound'), ('MAX_BINDING_BYTES', 'binding_inventory'),
            ('MAX_PRIVATE_BYTES', 'private_payload')]:
        with monkeypatch.context() as patch:
            patch.setattr(m, field, 1)
            refused(code, lambda: join(data))


def test_private_exports_are_fresh_copies_opaque_by_default_and_do_not_claim_capability():
    summary, private = join(case())
    record = private.private_record(); record['stocks'][0]['binding']['security_id'] = 'changed'
    assert private.private_record()['stocks'][0]['binding']['security_id'] != 'changed'
    routes = private.price_routes(); routes[0]['current_metadata_row']['ticker'] = 'changed'
    assert private.price_routes()[0]['current_metadata_row']['ticker'] != 'changed'
    assert 'SYN1' not in repr(private) and 'authority' in repr(private)
    with pytest.raises(TypeError): json.dumps(private)
    with pytest.raises(TypeError): pickle.dumps(private)
    with pytest.raises(TypeError): private._raw = b'changed'
    assert set(summary) == {'schema', 'scope', 'binding_contract', 'price_window', 'original_row_count',
        'original_rows_digest', 'metadata_rows_sha256', 'metadata_row_counts',
        'catalog_unknown_vocabulary_row_count', 'catalog_collision_group_counts',
        'disposition_counts', 'refusal_counts', 'private_payload_byte_count', 'private_payload_sha256'}


def test_source_is_pure_profile_has_no_ready_or_authorized_switch_and_finite_errors_are_closed():
    source_text = inspect.getsource(m)
    for forbidden in ('open(', '.read_bytes(', '.observe(', '._fetch(', 'require_probe_routes(', 'identity_join.join('):
        assert forbidden not in source_text
    profile = m.profile_record()
    assert profile['complete_parser_sha256'] == 'cab79cb04bbc0788b37138b74526fdd518b7d0e90ee7ceeca546227f91a7b72b'
    assert profile['operational_stock_count_requires_separate_freeze'] == 6151
    assert 'never_current_metadata' in profile['required_interval']
    assert not any(type(value) is bool for value in profile.values())
    class Child(m.Refused): pass
    assert m.finite(m.Refused('current_collision')) == 'current_collision'
    assert m.finite(Child('current_collision')) == m.finite(ValueError('SECRET')) == 'unknown'
