"""Pure public-source and synthetic failure-only identity witness tests."""
import ast
import copy
from datetime import datetime
import json
from pathlib import Path

import pytest

from scripts import arv2_newrule_reference_identity_projection as m
from tests.analyst_revisions_v2 import test_raw_reference_diagnostic_projection as base


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')


@pytest.fixture(scope='module')
def public():
    previous = base.public.__wrapped__()
    patcher = (ROOT / 'scripts' / m.PATCHER_NAME).read_bytes()
    result = m.public_specification(previous.projected.source_pairs,
        patcher_source_bytes=patcher, expected_patcher_sha256=m.sha(patcher))
    return base.NS(parent=previous, projected=result, patcher=patcher, pin=m.sha(patcher),
        old=dict(previous.projected.source_pairs), files=dict(result.source_pairs),
        profile=json.loads(result.profile_bytes))


def case(public, **kwargs):
    value = base.case(public, **kwargs)
    namespace = value.driver._reference_prices.__func__.__globals__
    namespace['_sha'] = lambda item: m.sha(m.canonical(list(item) if type(item) is tuple else item))
    axis, decisions = m._axis()
    value.driver._session_axis = axis
    value.driver._session_positions = {session: index for index, session in enumerate(axis)}
    value.driver._decision_set = decisions
    value.driver._profile = {'session_axis_sha256': m.SESSION_AXIS_SHA256}
    return value


def observed(value):
    with pytest.raises(base.LegacyError) as error:
        value.driver._reference_prices('2022-10-21', value.ids)
    text = error.value.args[0]
    assert text.startswith(m.ORIGINAL_FAILURE + '\n' + m.MARKER)
    result = m.parse_failure_context(text)
    assert result is not None and m.validate_failure_context(result) == result
    assert 'SID' not in text and 'S000' not in text and '"close":' not in text
    return result


def complete_context():
    value = m.context_record(2, 1)
    value.update(calendar_status='valid', reference_session='2022-10-21',
        decision_session='2022-10-24', decision_time='09:20', session_axis_sha256=m.SESSION_AXIS_SHA256,
        witness_status='complete', witnesses=[{'identity_sha256': '1' * 64,
            'holding': 'unknown', 'kind': 'unknown', 'sid_date': 'unknown'}])
    return value


def test_exact_parent_manifest_and_only_failure_branch_main_profile_change(public):
    assert {name for name in public.old if public.old[name] != public.files[name]} == {m.LEGACY_NAME, 'main.py'}
    assert m.sha(public.old[m.LEGACY_NAME]) == m.PARENT_LEGACY
    assert public.files[m.quote.RUNTIME_NAME] == public.old[m.quote.RUNTIME_NAME]
    old = ast.parse(public.old[m.LEGACY_NAME]); new = ast.parse(public.files[m.LEGACY_NAME])
    method, old_method = m.parent._legacy_method(new), m.parent._legacy_method(old)
    branch, = [node for node in method.body if isinstance(node, ast.If)
        and ast.unparse(node.test) == 'set(result) != set(security_ids)']
    before, = [node for node in old_method.body if isinstance(node, ast.If)
        and ast.unparse(node.test) == 'set(result) != set(security_ids)']
    branch.body = copy.deepcopy(before.body)
    assert m.parent._dump(new) == m.parent._dump(old)
    assert not any(isinstance(node, ast.Attribute) and node.attr == 'history'
        for node in ast.walk(ast.parse(m.FAILURE_BODY)))
    assert m.policy_record()['extra_history_calls'] == 0
    assert m.policy_record()['prior_raw_probe_repeated'] is False
    assert all(public.projected.to_record()[key] is False for key in m.FALSE_FLAGS)


def test_genuine_public_receiver_and_profile_recompute_match(public):
    record, profile, pairs = m.validate_public_projection(public.projected.record_bytes,
        public.projected.source_pairs, expected_projection_sha256=public.projected.projection_sha256,
        expected_profile_sha256=public.profile['profile_sha256'])
    assert record == public.projected.to_record() and pairs == public.projected.source_pairs
    assert profile == public.profile and profile['profile_sha256'] != m.PARENT_PROFILE
    assert profile['source_pins'][m.parent.PATCHER_NAME] == m.PARENT_PATCHER
    assert profile['source_pins'][m.PATCHER_NAME] == public.pin
    assert m.quote._profile(m.comparison.bridge.frozen.october._sessions(), universe_count=6,
        ar_percent=0, source_pins=profile['source_pins']) == profile


def test_build_chain_uses_explicit_frozen_quote_and_raw_patcher_bytes(public, monkeypatch):
    packet, calls = object(), []
    raw_patcher = public.parent.patcher
    quote_patcher = public.parent.parent.patcher
    def predecessor(value, **kwargs):
        assert value is packet
        assert kwargs == {'patcher_source_bytes': raw_patcher,
            'expected_patcher_sha256': m.PARENT_PATCHER, 'quote_patcher_source_bytes': quote_patcher}
        calls.append(value)
        return public.parent.projected
    monkeypatch.setattr(m.parent, 'build_projection', predecessor)
    assert m.build_projection(packet, patcher_source_bytes=public.patcher,
        expected_patcher_sha256=public.pin, quote_patcher_source_bytes=quote_patcher,
        raw_patcher_source_bytes=raw_patcher) == public.projected
    assert calls == [packet]


def test_success_path_has_exact_prices_and_only_original_history_query(public):
    value = case(public, count=2, returned=2, probe=AssertionError('extra query forbidden'))
    assert value.driver._reference_prices('2022-10-21', value.ids) == {'S000': base.Decimal(100), 'S001': base.Decimal(100)}
    assert len(value.calls) == 1


def test_omitting_original_refusal_is_detected_without_a_price_or_history_fallback(public):
    def must_refuse(omit):
        value = case(public, count=1, omit_final_refusal=omit)
        try:
            value.driver._reference_prices('2022-10-21', value.ids)
        except base.LegacyError:
            return
        raise AssertionError('identity diagnostic fell through into price sizing')
    must_refuse(False)
    with pytest.raises(AssertionError, match='fell through'):
        must_refuse(True)


def test_complete_witness_uses_exact_four_field_domain_and_actual_public_calendar(public):
    value = case(public, count=3, returned=2, probe=AssertionError('extra query forbidden'))
    result = observed(value)
    m.validate_complete_witness(result)
    assert result['reference_session'] == '2022-10-21' and result['decision_session'] == '2022-10-24'
    assert result['decision_time'] == '09:20' and result['session_axis_sha256'] == m.SESSION_AXIS_SHA256
    expected = m.sha(m.canonical({'schema': m.IDENTITY_SCHEMA, 'security_id': 'S002',
        'reference_session': '2022-10-21', 'decision_session': '2022-10-24'}))
    assert result['witnesses'] == [{'identity_sha256': expected, 'holding': 'held',
        'kind': 'stock', 'sid_date': 'on_or_before_reference'}]
    assert result['extra_history_call'] is False and result['probe_repeated'] is False
    assert len(value.calls) == value.driver._reference_history_call_count == 1
    assert result['sizing_repaired'] is False and result['probe_prices_used'] is False


def test_sixteen_witnesses_sorted_unique_and_all_aggregate_buckets_align(public):
    result = observed(case(public, count=16))
    assert len(result['witnesses']) == result['missing'] == 16
    assert [row['identity_sha256'] for row in result['witnesses']] == sorted(
        {row['identity_sha256'] for row in result['witnesses']})
    assert result['missing_holdings']['held'] == 1 and result['missing_kind']['stock'] == 16
    m.validate_complete_witness(result)


def test_more_than_sixteen_skips_all_witnesses_and_never_repeats_probe(public):
    value = case(public, count=17)
    result = observed(value)
    assert result['witness_status'] == 'skipped_limit' and result['witnesses'] == []
    assert len(value.calls) == 1
    with pytest.raises(m.Refused, match='^complete_witness$'): m.validate_complete_witness(result)


@pytest.mark.parametrize('change', ['clock', 'decision', 'reference', 'axis', 'profile', 'positions'])
def test_calendar_failures_never_create_witness_or_mask_original_refusal(public, change):
    value = case(public, count=1)
    if change == 'clock': value.driver._now = lambda: datetime(2022, 10, 24, 9, 21)
    elif change == 'decision': value.driver._decision_set = frozenset()
    elif change == 'reference': value.driver._session_positions['2022-10-24'] += 1
    elif change == 'axis': value.driver._session_axis = ()
    elif change == 'profile': value.driver._profile['session_axis_sha256'] = '0' * 64
    else: value.driver._session_positions = {}
    result = observed(value)
    assert result['calendar_status'] == result['witness_status'] == 'unavailable'
    assert all(result[key] is None for key in ('reference_session', 'decision_session', 'decision_time', 'session_axis_sha256'))
    assert result['witnesses'] == [] and len(value.calls) == 1


def test_collision_or_hash_failure_leaves_unknown_witness_and_original_refusal(public):
    value = case(public, count=2)
    namespace = value.driver._reference_prices.__func__.__globals__
    normal = namespace['_sha']
    namespace['_sha'] = lambda item: '0' * 64 if type(item) is dict else normal(item)
    result = observed(value)
    assert result['calendar_status'] == 'valid' and result['witness_status'] == 'unavailable'
    assert result['witnesses'] == []


@pytest.mark.parametrize('change', ['calendar', 'date', 'clock', 'hash', 'bool', 'count', 'unsorted',
    'duplicate', 'holding', 'kind', 'sid_date', 'extra_row', 'extra_context', 'raw_identity',
    'partial', 'skip_small', 'unknown_shape', 'prices', 'probe', 'cause'])
def test_context_refuses_malformed_or_unbound_witnesses_before_serializing_unknown_values(change):
    value = complete_context()
    if change == 'calendar': value['session_axis_sha256'] = '0' * 64
    elif change == 'date': value['reference_session'] = '2022-10-20'
    elif change == 'clock': value['decision_time'] = '09:21'
    elif change == 'hash': value['witnesses'][0]['identity_sha256'] = 'X' * 64
    elif change == 'bool': value['missing'] = True
    elif change == 'count': value['witnesses'] = []
    elif change in ('unsorted', 'duplicate'):
        value['requested'], value['missing'] = 3, 2
        for key in ('missing_holdings', 'missing_kind', 'missing_sid_date'): value[key]['unknown'] = 2
        value['witnesses'].append(copy.deepcopy(value['witnesses'][0]))
        if change == 'unsorted': value['witnesses'][0]['identity_sha256'] = '2' * 64
    elif change in ('holding', 'kind', 'sid_date'): value['witnesses'][0][change] = {'holding': 'held', 'kind': 'stock', 'sid_date': 'after_decision'}[change]
    elif change == 'extra_row': value['witnesses'][0]['unselected'] = object()
    elif change == 'extra_context': value['unselected'] = object()
    elif change == 'raw_identity': value['witnesses'][0]['security_id'] = 'private-not-retained'
    elif change == 'partial': value['witness_status'] = 'unavailable'
    elif change == 'skip_small': value['witness_status'], value['witnesses'] = 'skipped_limit', []
    elif change == 'unknown_shape': value['witnesses'] = [object()] * 100000
    elif change == 'prices': value['probe_prices_used'] = True
    elif change == 'probe': value['extra_history_call'] = True
    else: value['cause_authenticated'] = True
    with pytest.raises(m.Refused): m.validate_failure_context(value)


def test_context_parser_rejects_old_v1_duplicate_and_trailing_forms():
    context = complete_context()
    token = m.MARKER + m.canonical(context).decode('ascii')
    assert m.parse_failure_context('Runtime Error: ' + token + '\n at frame') == context
    assert m.parse_failure_context(token + '\n' + token) is None
    assert m.parse_failure_context(token + 'trailing') is None
    assert m.parse_failure_context(token.replace('"requested":2', '"requested":2,"requested":2')) is None
    old = m.parent.context_record(2, 1)
    assert m.parse_failure_context(m.parent.FAILURE_CODES[0] + '|context=' + m.canonical(old).decode('ascii')) is None


def test_public_calendar_requires_a_weekly_decision_not_only_two_adjacent_sessions():
    value = complete_context()
    value['reference_session'], value['decision_session'] = '2022-10-24', '2022-10-25'
    with pytest.raises(m.Refused, match='^failure_context$'): m.validate_failure_context(value)


def test_witness_key_type_refuses_without_rehashing_a_hostile_supplied_key():
    class Key:
        armed = False
        def __hash__(self):
            if self.armed: raise AssertionError('hostile key rehashed')
            return 1234
    key = Key()
    value = complete_context()
    value['witnesses'][0][key] = object()
    key.armed = True
    with pytest.raises(m.Refused, match='^failure_context$'): m.validate_failure_context(value)


@pytest.mark.parametrize('change', ['runtime', 'legacy', 'main', 'patcher', 'order'])
def test_source_pins_and_old_parent_manifest_refuse_drift(public, change):
    pairs, pin = list(public.parent.projected.source_pairs), public.pin
    if change == 'patcher': pin = '0' * 64
    elif change == 'order': pairs.reverse()
    else:
        name = {'runtime': m.quote.RUNTIME_NAME, 'legacy': m.LEGACY_NAME, 'main': 'main.py'}[change]
        pairs = [(key, raw + b'# altered\n' if key == name else raw) for key, raw in pairs]
    with pytest.raises(m.Refused): m.public_specification(tuple(pairs), patcher_source_bytes=public.patcher,
        expected_patcher_sha256=pin)
