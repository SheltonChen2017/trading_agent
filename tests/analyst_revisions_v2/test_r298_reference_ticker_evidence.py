"""Synthetic original-composer parity; no private source or operational use."""
import copy
import hashlib
import json
import pickle
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r298_reference_ticker_evidence as m
from tests.analyst_revisions_v2 import test_r298_reference_identity_join as fixtures


@pytest.fixture(autouse=True)
def no_operations(monkeypatch):
    fixtures.no_operations.__wrapped__(monkeypatch)


@pytest.fixture(scope='module')
def axis():
    return fixtures.axis.__wrapped__()


def make_case(monkeypatch, axis, *, changes=None, first='1999-01-04', last='2022-10-20'):
    row = {'table': 'SF1', 'ticker': 'SYNTH', 'permaticker': '123456',
        'name': 'Synthetic caf\u00e9 issuer', 'exchange': 'NYSE', 'isdelisted': 'Y',
        'category': 'Domestic Common Stock Primary Class', 'figi': 'BBG000000001',
        'cusips': '012345678,123456789', 'currency': 'USD', 'sector': 'Technology',
        'industry': 'Synthetic industry', 'firstadded': '2000-01-01',
        'firstpricedate': first, 'lastpricedate': last, 'lastupdated': '2026-09-13', 'lastquarter': '',
        'scalemarketcap': '5 - Large', 'scalerevenue': '', 'relatedtickers': '',
        'famaindustry': '', 'famasector': '', 'siccode': '9999', 'sicsector': '',
        'sicindustry': '', 'location': 'U.S.A', 'secfilings': '', 'companysite': ''}
    if changes:
        row.update(changes)
    # This invokes the actual original pure row-to-candidate semantics while
    # replacing only its I/O iterator with one entirely synthetic supplied row.
    monkeypatch.setattr(m.composer, '_iter_sharadar_rows', lambda *_: iter([copy.deepcopy(row)]))
    candidates, refused, counts = m.composer._ticker_candidates(object())
    assert refused == {} and not any(counts.values())
    candidate = candidates[row['ticker']]
    binding = m.identity_join.figi.build_preliminary_qc_figi_binding(
        security_id=candidate.security_id, issuer_id=candidate.issuer_id,
        composite_figi=candidate.composite_figi, listing_id=candidate.listing_id,
        diagnostic_current_ticker=candidate.ticker, diagnostic_exchange_mic=candidate.exchange_id,
        candidate_first_session='2013-01-02', candidate_last_session='2026-10-13',
        source_snapshot_available_at='2026-09-14T00:33:29.843989Z',
        source_row_sha256=candidate.source_row_sha256,
        identity_evidence_sha256=candidate.identity_evidence_sha256,
        security_master_admission_sha256='c' * 64,
        admitted_mapping_inventory_sha256='d' * 64, admitted_mapping_count=1)
    context = fixtures.context_for([binding], axis)
    expected = {**context['witnesses'][0],
        'binding_row_sha256': binding['row_sha256'],
        'whole_binding_row_sha256': m.identity_join.legacy._sha(binding),
        **{key: binding[key] for key in ('source_row_sha256', 'identity_evidence_sha256',
            'security_master_admission_sha256', 'admitted_mapping_inventory_sha256')},
        **{key + '_sha256': m.identity_join._field(key, binding[key]) for key in (
            'composite_figi', 'issuer_id', 'listing_id', 'diagnostic_current_ticker',
            'diagnostic_exchange_mic', 'candidate_first_session', 'candidate_last_session',
            'source_snapshot_available_at')}}
    return NS(row=row, binding=binding, context=context, expected=expected, candidate=candidate)


@pytest.fixture
def case(monkeypatch, axis):
    return make_case(monkeypatch, axis)


def verify(case):
    return m.verify(case.row, case.binding, case.context, expected_match=case.expected)


def repin_binding(case):
    seed = dict(case.binding); seed.pop('row_sha256')
    case.binding['row_sha256'] = m.sha(m.identity_join.figi._canonical(seed))
    case.expected['binding_row_sha256'] = case.binding['row_sha256']
    case.expected['whole_binding_row_sha256'] = m.identity_join.legacy._sha(case.binding)
    for key in ('source_row_sha256', 'identity_evidence_sha256', 'security_master_admission_sha256',
            'admitted_mapping_inventory_sha256'):
        case.expected[key] = case.binding[key]
    for key in ('composite_figi', 'issuer_id', 'listing_id', 'diagnostic_current_ticker',
            'diagnostic_exchange_mic', 'candidate_first_session', 'candidate_last_session',
            'source_snapshot_available_at'):
        case.expected[key + '_sha256'] = m.identity_join._field(key, case.binding[key])


def test_genuine_original_composer_parity_uses_utf8_with_lf_and_never_discloses_route(case):
    receipt, route = verify(case)
    m.validate_receipt(receipt)
    assert receipt['source_row_sha256'] == case.candidate.source_row_sha256
    assert m.source_row_digest(case.row) == case.candidate.source_row_sha256
    assert receipt['identity_evidence_sha256'] == case.candidate.identity_evidence_sha256
    assert m.composer.canonical_json_bytes(case.row).endswith(b'\n')
    assert b'caf\xc3\xa9' in m.composer.canonical_json_bytes(case.row)
    assert receipt['source_row_sha256'] != m.sha(m.canonical(case.row))
    assert route.permaticker == '123456' and route.ticker == 'SYNTH'
    assert route.composite_figi == 'BBG000000001' and route.exchange_mic == 'XNYS'
    assert receipt['delisted_metadata_state'] == 'Y' and receipt['delisted_metadata'] is True
    assert receipt['raw_last_price_vs_reference'] == 'before'
    assert receipt['reference_candidate_interval_relation'] == 'inside'
    assert receipt['decision_candidate_interval_relation'] == 'inside'
    assert all(receipt[key] is False for key in m.FALSE_FLAGS)
    raw = m.canonical(receipt)
    for value in ('SYNTH', '123456', 'BBG000000001', '1999-01-04', '2022-10-20',
            'Synthetic', '012345678', 'NYSE'):
        assert value.encode('ascii') not in raw
    assert 'SYNTH' not in repr(route) and '123456' not in str(route)
    assert not hasattr(route, '__dict__')
    with pytest.raises(TypeError): json.dumps(route)
    with pytest.raises(TypeError): pickle.dumps(route)
    with pytest.raises(TypeError): route.ticker = 'changed'


@pytest.mark.parametrize('last,reference,decision', [
    ('2022-10-20', 'before', 'before'), ('2022-10-21', 'at', 'before'),
    ('2022-10-24', 'after', 'at'), ('2022-10-25', 'after', 'after'),
    ('', 'unavailable', 'unavailable')])
def test_raw_price_date_relations_do_not_claim_bar_or_payoff_coverage(monkeypatch, axis, last, reference, decision):
    case = make_case(monkeypatch, axis, last=last)
    receipt, route = verify(case)
    assert receipt['raw_last_price_vs_reference'] == reference
    assert receipt['raw_last_price_vs_decision'] == decision
    assert receipt['daily_price_coverage_proven'] is False
    assert receipt['terminal_payoff_proven'] is False
    assert route.last_priced_date == (last or None)


@pytest.mark.parametrize('first,reference,decision', [
    ('2022-10-20', 'before', 'before'), ('2022-10-21', 'at', 'before'),
    ('2022-10-24', 'after', 'at'), ('2022-10-25', 'after', 'after')])
def test_first_price_relations_are_metadata_only(monkeypatch, axis, first, reference, decision):
    case = make_case(monkeypatch, axis, first=first, last='2026-10-13')
    receipt, _ = verify(case)
    assert receipt['raw_first_price_vs_reference'] == reference
    assert receipt['raw_first_price_vs_decision'] == decision


@pytest.mark.parametrize('value,state,boolean', [('Y', 'Y', True), ('N', 'N', False),
    ('y', 'unknown', None), ('true', 'unknown', None), ('1', 'unknown', None), ('', 'unknown', None)])
def test_delisted_is_only_strict_original_y_n_not_truthiness(monkeypatch, axis, value, state, boolean):
    case = make_case(monkeypatch, axis, changes={'isdelisted': value})
    receipt, _ = verify(case)
    assert receipt['delisted_metadata_state'] == state and receipt['delisted_metadata'] is boolean


def test_hashed_issuer_component_is_reconstructed_not_prefix_stripped(monkeypatch, axis):
    case = make_case(monkeypatch, axis, changes={'permaticker': 'synthetic / private value'})
    receipt, route = verify(case)
    assert case.binding['issuer_id'] != 'sharadar-permaticker-' + route.permaticker
    assert receipt['original_composer_identity_matched'] is True


def test_source_pin_compared_before_any_metadata_interpretation(case, monkeypatch):
    case.row['name'] += ' changed'
    monkeypatch.setattr(m, '_metadata', lambda *_: pytest.fail('parsed source before source pin'))
    with pytest.raises(m.Refused, match='^source_pin$'): verify(case)


@pytest.mark.parametrize('field,value,code', [('table', 'SEP', 'metadata'),
    ('category', 'ETF', 'metadata'), ('exchange', 'OTC', 'metadata'),
    ('figi', '', 'metadata'), ('sector', '', 'metadata'), ('industry', '', 'metadata'),
    ('firstpricedate', '2022-1-04', 'metadata'), ('lastpricedate', '1998-12-31', 'interval')])
def test_even_rehashed_original_row_must_satisfy_exact_frozen_candidate_rules(case, field, value, code):
    case.row[field] = value
    case.binding['source_row_sha256'] = m.source_row_digest(case.row)
    repin_binding(case)
    with pytest.raises(m.Refused, match='^' + code + '$'): verify(case)


@pytest.mark.parametrize('where', ['source', 'expected_source', 'expected_whole', 'expected_identity',
    'binding_row', 'context_date', 'context_witness', 'match_holding'])
def test_no_substitution_of_another_row_binding_or_dated_witness(case, where):
    if where == 'source': case.row['ticker'] = 'OTHER'
    elif where == 'expected_source': case.expected['source_row_sha256'] = '0' * 64
    elif where == 'expected_whole': case.expected['whole_binding_row_sha256'] = '0' * 64
    elif where == 'expected_identity': case.expected['identity_sha256'] = '0' * 64
    elif where == 'binding_row': case.binding['diagnostic_current_ticker'] = 'OTHER'
    elif where == 'context_date': case.context['reference_session'] = '2022-10-20'
    elif where == 'context_witness': case.context['witnesses'][0]['identity_sha256'] = '0' * 64
    else: case.expected['holding'] = 'unheld_target'
    with pytest.raises(ValueError): verify(case)


@pytest.mark.parametrize('field,value', [('identity_evidence_sha256', '0' * 64),
    ('listing_id', 'different-listing'), ('issuer_id', 'different-issuer'),
    ('diagnostic_current_ticker', 'OTHER'), ('diagnostic_exchange_mic', 'XNAS'),
    ('composite_figi', 'BBG000000002')])
def test_self_rehashed_binding_still_must_match_original_composer(case, field, value):
    case.binding[field] = value
    repin_binding(case)
    code = 'binding' if field == 'composite_figi' else 'identity'
    with pytest.raises(m.Refused, match='^' + code + '$'): verify(case)


@pytest.mark.parametrize('row', [[], {'x': None}, {'x': 1}, {1: 'text'}, {'x': 'x' * 8193}])
def test_exact_string_row_shape_and_scalar_bounds_refuse_before_serialization(case, row):
    case.row = row
    with pytest.raises(m.Refused, match='^row_shape$'): verify(case)


def test_oversized_row_refuses_before_hash_comparison(case):
    case.row = {str(index): 'x' * 4096 for index in range(28)}
    with pytest.raises(m.Refused, match='^row_bound$'): verify(case)


def test_late_source_change_cannot_publish_receipt(case, monkeypatch):
    original = m._metadata
    def mutate(row):
        result = original(row)
        case.row['name'] += ' changed'
        return result
    monkeypatch.setattr(m, '_metadata', mutate)
    with pytest.raises(m.Refused, match='^changed$'): verify(case)


@pytest.mark.parametrize('field,value', [('delisted_metadata', 1), ('delisted_metadata_state', 'yes'),
    ('daily_price_coverage_proven', True), ('raw_last_price_vs_reference', 'inside'),
    ('raw_provider_route_disclosed', True), ('cusip_candidate_count', True),
    ('source_row_sha256', 'changed'), ('ticker', 'RAWPRIVATE')])
def test_closed_receipt_refuses_false_evidence_or_raw_extra_fields(case, field, value):
    receipt, _ = verify(case)
    receipt[field] = value
    with pytest.raises(ValueError): m.validate_receipt(receipt)


def test_unavailable_last_date_cannot_contradict_other_relation(case):
    receipt, _ = verify(case)
    receipt['raw_last_price_vs_reference'] = 'unavailable'
    with pytest.raises(m.Refused): m.validate_receipt(receipt)


def test_finite_errors_never_format_hostile_exception_or_private_text():
    class Hostile(m.Refused):
        def __str__(self): pytest.fail('formatted hostile error')
    assert m.finite(Hostile('metadata')) == 'unknown'
    assert m.finite(m.Refused('PRIVATE')) == 'unknown'
    assert all(m.finite(m.Refused(code)) == code for code in m.FINITE)
    profile = m.profile_record()
    assert profile['source_row_hash_compared_before_metadata_interpretation'] is True
    assert profile['receipt_is_operational_capability'] is False
