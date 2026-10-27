"""Synthetic finite AA-frame evidence; no retained data or operations."""
import copy
import json
import pickle
import time

import pytest

from scripts import arv2_r298_route_disposition_evidence as m
from tests.analyst_revisions_v2 import test_r298_sharadar_all_routes_v2 as fixture
from tests.analyst_revisions_v2 import test_r298_sharadar_eligibility_observation as metadata

PURE_JOIN = m.routes.join


@pytest.fixture(autouse=True)
def synthetic_scope_and_no_operation(monkeypatch):
    monkeypatch.setattr(m, 'EXPECTED_STOCKS', 2)
    def deny(*args, **kwargs): raise AssertionError('old operation or join used by analyzer')
    monkeypatch.setattr(m.routes, 'join', deny)
    monkeypatch.setattr(m.routes.original, 'verify', deny)
    monkeypatch.setattr(m.routes.original.identity_join, 'join', deny)
    for module in (m.routes.current.previous, m.routes.current.previous.previous):
        monkeypatch.setattr(module, 'observe', deny)
        monkeypatch.setattr(module, '_fetch', deny)


def make(data=None):
    data = fixture.case() if data is None else data
    summary, private = PURE_JOIN(*data, binding_contract=fixture.supplied.contract(data[0]))
    return m.canonical(private.private_record()), summary


def inspect(data=None):
    raw, expected = make(data)
    return m.inspect(raw, expected_summary=expected)


def repin(binding):
    seed = dict(binding); seed.pop('row_sha256')
    binding['row_sha256'] = m.sha(m.routes.original.identity_join.figi._canonical(seed))


def refused(code, call):
    with pytest.raises(m.Refused) as error: call()
    assert m.finite(error.value) == code


def self_pin(frame, expected):
    raw = m.canonical(frame)
    expected = copy.deepcopy(expected)
    expected.update(private_payload_byte_count=len(raw), private_payload_sha256=m.sha(raw))
    return raw, expected


def test_all_original_rows_are_preserved_in_order_and_summary_is_closed_hashes_and_finite_counts():
    raw, expected = make()
    summary, private = m.inspect(raw, expected_summary=expected)
    record = private.private_record()
    assert [row['binding'] for row in record['stocks']] == fixture.case()[0]
    assert summary['disposition_counts'] == {'stocks': {'routed': 2}, 'funds': {'routed': 8}}
    assert summary['refusal_counts'] == {'stocks': {}, 'funds': {}}
    assert summary['quality_category_counts'] == {}
    assert m.validate_summary(summary) == summary
    assert m.validate_private_record(record, expected_summary=summary) == record
    assert summary['frame_pin'] == {'byte_count': len(raw), 'sha256': m.sha(raw)}
    assert summary['routing_summary_sha256'] == m.sha(m.canonical(expected))
    assert summary['private_evidence_sha256'] == m.sha(m.canonical(record))
    serialized = m.canonical(summary)
    for value in ('SYN1', 'BBG000000001', 'NASDAQ', 'Synthetic', '000000001', '1001', 'SPY'):
        assert value.encode() not in serialized
    assert not any(key in serialized for key in (b'"ready":true', b'"admitted":true', b'authorized'))


@pytest.mark.parametrize('field,value,predicates', [
    ('issuer_id', 'sharadar-permaticker-other', ('permaticker_to_issuer_id',)),
    ('listing_id', 'sharadar-listing-other', ('listing_id',)),
    ('diagnostic_current_ticker', 'OTHER', ('diagnostic_current_ticker',)),
    ('diagnostic_exchange_mic', 'XNYS', ('diagnostic_exchange_mic',)),
    ('identity_evidence_sha256', 'c' * 64, ('identity_evidence_hash',)),
    ('composite_figi', 'BBGZZZZZZZZZ', ('composite_figi', 'security_id'))])
def test_original_identity_exact_reconstruction_components_are_reported_without_values(field, value, predicates):
    data = fixture.case()
    data[0][0][field] = value
    if field == 'composite_figi': data[0][0]['security_id'] = 'sharadar-composite-figi-' + value
    repin(data[0][0]); data[0].sort(key=lambda row: row['security_id'])
    summary, private = inspect(data)
    assert summary['refusal_counts']['stocks'] == {'original_identity': 1}
    failures = summary['per_reason_component_counts']['stocks']['original_identity']['original_failures']
    for predicate in predicates: assert failures[predicate] == 1
    assert summary['quality_category_counts']['original_identity_component_mismatch'] == 1
    assert value.encode() not in m.canonical(summary)


@pytest.mark.parametrize('kind,category,predicate', [
    ('currency', 'original_currency_not_usd', 'original_currency_usd'),
    ('first', 'original_raw_candidate_interval_mismatch', 'raw_first_le_candidate_first'),
    ('last', 'original_raw_candidate_interval_mismatch', 'candidate_last_le_raw_last_or_open')])
def test_original_currency_and_raw_date_bounds_are_distinct_from_identity_hash_failures(kind, category, predicate):
    data = fixture.case()
    if kind == 'currency': data[1][0]['currency'] = 'EUR'
    elif kind == 'first': data[1][0]['firstpricedate'] = '2020-01-02'
    else: data[1][0]['lastpricedate'] = '2025-12-31'
    data[0][0] = fixture.supplied.binding(data[1][0], 2)
    summary, private = inspect(data)
    assert summary['quality_category_counts'][category] == 1
    assert summary['per_reason_component_counts']['stocks']['original_identity']['original_failures'][predicate] == 1
    assert 'original_identity_component_mismatch' not in summary['quality_category_counts']


@pytest.mark.parametrize('field,value,category', [
    ('ticker', 'RENAMED', 'current_ticker_changed'), ('exchange', 'NYSE', 'current_exchange_mic_changed')])
def test_current_identity_changed_distinguishes_ticker_from_MIC(field, value, category):
    data = fixture.case(); data[2][0][field] = value
    summary, private = inspect(data)
    assert summary['refusal_counts']['stocks'] == {'current_identity_changed': 1}
    assert summary['quality_category_counts'][category] == 1
    assert value.encode() not in m.canonical(summary)


@pytest.mark.parametrize('field,value,component,category', [
    ('currency', 'EUR', 'currency_usd', 'current_currency_not_usd'),
    ('category', 'Preferred Stock', 'category_supported', 'current_category_unsupported'),
    ('exchange', 'UNKNOWN', 'exchange_supported', 'current_exchange_unsupported'),
    ('cusips', '000000001;INVALID', 'cusip_vocabulary', 'current_identifier_or_vocabulary_shape'),
    ('isdelisted', '?', 'delisted_shape', None)])
def test_current_shape_constituents_are_finite_and_agree_with_frozen_quality(field, value, component, category):
    data = fixture.case(); data[2][0][field] = value
    summary, private = inspect(data)
    assert summary['refusal_counts']['stocks'] == {'current_shape': 1}
    assert summary['per_reason_component_counts']['stocks']['current_shape']['current_failures'][component] == 1
    if category: assert summary['quality_category_counts'][category] == 1


@pytest.mark.parametrize('field,value,component,category', [
    ('firstpricedate', '2021-01-04', 'current_first_covers_required', 'current_first_after_required_geometry'),
    ('lastpricedate', '2026-10-12', 'current_last_covers_required', 'current_last_before_required_geometry'),
    ('lastupdated', 'bad', 'lastupdated_valid', 'current_metadata_date_invalid')])
def test_current_interval_endpoints_are_original_geometry_diagnostics_not_demand_or_price_filters(field, value, component, category):
    data = fixture.case(); data[2][0][field] = value
    summary, private = inspect(data)
    assert summary['refusal_counts']['stocks'] == {'current_interval': 1}
    assert summary['per_reason_component_counts']['stocks']['current_interval']['current_failures'][component] == 1
    assert summary['quality_category_counts'][category] == 1
    row = private.private_record()['stocks'][0]
    assert row['required_first_date'] == '2020-12-31' and row['required_last_date'] == '2026-10-13'


@pytest.mark.parametrize('kind,category', [('perma', 'current_same_figi_only'),
    ('figi', 'current_same_perma_only'), ('both', 'current_same_ticker_only'), ('absent', 'candidate_subset_empty')])
def test_missing_current_identity_reports_perma_FIGI_candidate_combinations(kind, category):
    data = fixture.case()
    if kind == 'absent': data[2].pop(0)
    else:
        if kind in ('perma', 'both'): data[2][0]['permaticker'] = '9999'
        if kind in ('figi', 'both'): data[2][0]['figi'] = 'BBG999999999'
    summary, private = inspect(data)
    assert summary['refusal_counts']['stocks'] == {'current_identity_missing': 1}
    assert summary['quality_category_counts'][category] == 1
    assert summary['quality_category_counts']['current_perma_figi_no_intersection'] == 1


@pytest.mark.parametrize('kind', ['unseen_token', 'local_perma'])
def test_collision_cause_is_never_invented_from_incomplete_candidate_subset(kind):
    data = fixture.case(); extra = metadata.metadata('OTHER', 99)
    if kind == 'unseen_token':
        data[2][0]['cusips'] += ' ABCDEF123'; extra['cusips'] += ' ABCDEF123'
    else: extra['permaticker'] = data[2][0]['permaticker']
    data[2].append(extra)
    summary, private = inspect(data)
    assert summary['refusal_counts']['stocks'] == {'current_collision': 1}
    assert summary['quality_category_counts']['global_collision_index_cause_unknown'] == 1
    if kind == 'unseen_token': assert 'local_candidate_collision_seen' not in summary['quality_category_counts']
    else: assert summary['quality_category_counts']['local_candidate_collision_seen'] == 1
    assert private.private_record()['stocks'][0]['current_evidence']['global_collision_cause'] == 'not_reconstructible_from_candidate_subset'


def test_outside_original_binding_window_preserves_every_binding_without_membership_exclusion():
    data = fixture.case()
    data[0][0] = fixture.supplied.binding(data[1][0], 2, last='2020-12-30')
    summary, private = inspect(data)
    assert summary['disposition_counts']['stocks'] == {'outside_window': 1, 'routed': 1}
    assert summary['quality_category_counts']['recorded_outside_original_binding_window'] == 1
    assert len(private.private_record()['stocks']) == 2
    assert private.private_record()['stocks'][0]['required_last_date'] is None


@pytest.mark.parametrize('change', ['pin', 'count', 'order', 'binding', 'record_extra', 'route_extra',
    'reason', 'original_tokens', 'route_identity', 'fund_order', 'disposition_count'])
def test_external_frame_pin_full_binding_inventory_and_recorded_dispositions_cannot_be_forged(change):
    raw, expected = make(); frame = json.loads(raw)
    if change == 'pin': refused('frame_pin', lambda: m.inspect(raw + b' ', expected_summary=expected)); return
    if change == 'count': frame['stocks'].pop()
    elif change == 'order': frame['stocks'].reverse()
    elif change == 'binding': frame['stocks'][0]['binding']['row_sha256'] = 'f' * 64
    elif change == 'record_extra': frame['stocks'][0]['raw'] = 'PRIVATE'
    elif change == 'route_extra': frame['stocks'][0]['route']['authorized'] = True
    elif change == 'reason': frame['stocks'][0].update(disposition='refused', reason='current_shape', route=None)
    elif change == 'original_tokens': frame['stocks'][0]['original_cusip_tokens'] = []
    elif change == 'route_identity': frame['stocks'][0]['route']['security_id'] = 'other'
    elif change == 'fund_order': frame['funds'].reverse()
    else: expected['disposition_counts']['stocks'] = {'refused': 1, 'routed': 1}; expected['refusal_counts']['stocks'] = {'current_shape': 1}
    raw, expected = self_pin(frame, expected)
    with pytest.raises(m.Refused): m.inspect(raw, expected_summary=expected)


@pytest.mark.parametrize('bad', [b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b'{"x":1}\n'])
def test_exact_pinned_frame_still_requires_closed_canonical_JSON(bad):
    _, expected = make(); expected.update(private_payload_byte_count=len(bad), private_payload_sha256=m.sha(bad))
    with pytest.raises(m.Refused): m.inspect(bad, expected_summary=expected)


def test_private_facts_are_opaque_fresh_and_bound_to_the_closed_summary():
    summary, private = inspect(); record = private.private_record()
    assert m.validate_private_record(record, expected_summary=summary) == record
    record['stocks'][0]['binding']['security_id'] = 'changed'
    with pytest.raises(m.Refused): m.validate_private_record(record, expected_summary=summary)
    record = private.private_record(); record['stocks'][0]['current_evidence']['selected_predicates']['currency_usd'] = 'fail'
    with pytest.raises(m.Refused): m.validate_private_record(record, expected_summary=summary)
    assert 'SYN1' not in repr(private)
    with pytest.raises(TypeError): json.dumps(private)
    with pytest.raises(TypeError): pickle.dumps(private)
    with pytest.raises(TypeError): private._raw = b'changed'


@pytest.mark.parametrize('change', ['extra', 'category', 'count_bool', 'predicate', 'state_count', 'pin',
    'overlapping_states', 'invented_collision_count'])
def test_closed_public_summary_rejects_arbitrary_labels_flags_and_impossible_counts(change):
    data = fixture.case(); data[2][0]['currency'] = 'EUR'; summary, _ = inspect(data)
    if change == 'extra': summary['ready'] = True
    elif change == 'category': summary['quality_category_counts']['PRIVATE_TICKER'] = 1
    elif change == 'count_bool': summary['disposition_counts']['stocks']['routed'] = True
    elif change == 'predicate': summary['per_reason_component_counts']['stocks']['current_shape']['current_failures']['PRIVATE'] = 1
    elif change == 'state_count': summary['per_reason_component_counts']['stocks']['current_shape']['current_failures']['currency_usd'] = 2
    elif change == 'overlapping_states': summary['per_reason_component_counts']['stocks']['current_shape']['current_unknowns']['currency_usd'] = 1
    elif change == 'invented_collision_count': summary['quality_category_counts']['global_collision_index_cause_unknown'] = 1
    else: summary['frame_pin']['sha256'] = 'bad'
    refused('summary', lambda: m.validate_summary(summary))


def test_deadline_and_preparse_bounds_remain_explicit(monkeypatch):
    raw, expected = make()
    refused('deadline', lambda: m.inspect(raw, expected_summary=expected, deadline=time.monotonic() - 1))
    monkeypatch.setattr(m, 'MAX_JSON_DEPTH', 1)
    refused('json_bound', lambda: m.inspect(raw, expected_summary=expected))


def test_profile_exposes_fixed_scope_and_no_operational_or_membership_authority():
    profile = m.profile_record()
    assert profile['expected_summary'].startswith('externally_authenticated_AA_routing_summary')
    assert profile['global_collision_cause'] == 'not_reconstructible_from_candidate_subset'
    assert 'not_runtime_membership' in profile['binding_interval_diagnostics']
    assert not any(type(value) is bool for value in profile.values())
    class Child(m.Refused): pass
    assert m.finite(Child('frame')) == m.finite(ValueError('PRIVATE')) == 'unknown'
