"""Public-source and synthetic packet tests; native denial required externally."""
import ast
import copy
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_newrule_quote_diagnostic_projection as m


SOURCE = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2/research/analyst_revisions_v2_qc')
PATCHER = SOURCE.parent.parent / 'scripts' / m.PATCHER_NAME


@pytest.fixture(scope='module')
def public():
    names = set(m.comparison.bridge.parent.SOURCE_PINS) | set(m.comparison.NEW_SOURCE_PINS) | {m.comparison.HOST_SOURCE_NAME}
    sources = {name: (SOURCE / name).read_bytes() for name in names}
    spec = m.comparison.public_specification(sources=sources,
        expected_host_source_pins={m.comparison.HOST_SOURCE_NAME: m.sha(sources[m.comparison.HOST_SOURCE_NAME])})
    pairs = tuple((item.project_path, item.source_bytes) for item in spec.cells[0].source_files)
    raw = PATCHER.read_bytes()
    return NS(pairs=pairs, patcher=raw, pin=m.sha(raw))


def build(value):
    return m.public_specification(value.pairs, patcher_source_bytes=value.patcher,
        expected_patcher_sha256=value.pin)


def test_source_changes_exactly_runtime_and_profile_literals_and_preserves_economics(public):
    value = build(public)
    record = value.to_record()
    old, new = dict(public.pairs), dict(value.source_pairs)
    assert {name for name in old if old[name] != new[name]} == {m.RUNTIME_NAME, 'main.py'}
    assert len(record['unchanged_cloud_files']) == 9
    assert 'accepted_risk_order_level_input_runtime.py' in record['unchanged_cloud_files']
    assert tuple(name for name, _ in value.source_pairs) == tuple(name for name, _ in public.pairs)
    old_profile = ast.literal_eval(m._driver(ast.parse(old['main.py']))['profile'].value)
    profile = json.loads(value.profile_bytes)
    assert m.comparison.bridge._economic_profile(profile) == m.comparison.bridge._economic_profile(old_profile)
    assert profile['source_pins'] == {**old_profile['source_pins'], m.RUNTIME_NAME: m.sha(new[m.RUNTIME_NAME]), m.PATCHER_NAME: public.pin}
    assert profile['profile_sha256'] != old_profile['profile_sha256']
    assert record['parent_projection_sha256'] == m.PARENT_PROJECTION
    assert record['runtime_source_pin_representation'] == 'normalized_cloud_ascii_python'
    assert m.comparison.bridge._main_shape(new['main.py']) == m.comparison.bridge._main_shape(old['main.py'])
    assert record['failure_codes'] == list(m.FAILURE_CODES)
    assert all(record[key] is False for key in m.FALSE_FLAGS)
    assert sum(len(raw) for _, raw in value.source_pairs) <= 448 * 1024
    assert all(len(raw) <= 64000 for _, raw in value.source_pairs)
    assert public.pairs == tuple(old.items())


def diagnostic_method(public):
    value = build(public)
    owner, node = m._method(ast.parse(dict(value.source_pairs)[m.RUNTIME_NAME]))
    context, = [item for item in owner.body if isinstance(item, ast.FunctionDef)
        and item.name == '_execution_price_context']
    tree = ast.fix_missing_locations(ast.Module(body=[node, context], type_ignores=[]))
    calls = []
    def number(value, *, positive=False):
        calls.append((value, positive))
        return value
    namespace = {'require': m.comparison.bridge.frozen.targets.require, 'instant': lambda value: value,
        'number': number}
    exec(compile(tree, 'synthetic diagnostic method', 'exec'), namespace)
    def method(driver, security):
        if not hasattr(driver, '_execution_price_context'):
            driver._execution_price_context = lambda *args: namespace['_execution_price_context'](driver, *args)
        return namespace['_current_execution_price'](driver, security)
    return method, calls


def test_success_returns_identical_security_price_through_original_number_call(public):
    method, calls = diagnostic_method(public)
    price = object()
    security = NS(price=price, get_last_data=lambda: NS(end_time=123, is_fill_forward=False))
    assert method(NS(_now=lambda: 123), security) is price
    assert calls == [(price, True)]


@pytest.mark.parametrize('data,code', [(None, 'execution_price_missing'),
    (NS(end_time=122, is_fill_forward=False), 'execution_price_end_not_current'),
    (NS(end_time=124, is_fill_forward=False), 'execution_price_end_not_current'),
    (NS(end_time=123, is_fill_forward=True), 'execution_price_fill_forward'),
    (NS(end_time=123, is_fill_forward=0), 'execution_price_fill_forward'),
    (NS(end_time=123, is_fill_forward=None), 'execution_price_fill_forward')])
def test_three_original_predicates_refuse_with_finite_distinct_codes(public, data, code):
    method, calls = diagnostic_method(public)
    with pytest.raises(m.comparison.bridge.frozen.targets.NewruleError, match=code):
        method(NS(_now=lambda: 123), NS(price=object(), get_last_data=lambda: data))
    assert calls == []


def test_end_time_failure_still_short_circuits_fill_forward_access(public):
    method, calls = diagnostic_method(public)
    class Data:
        end_time = 122
        @property
        def is_fill_forward(self):
            pytest.fail('later predicate evaluated after earlier refusal')
    with pytest.raises(m.comparison.bridge.frozen.targets.NewruleError, match='execution_price_end_not_current'):
        method(NS(_now=lambda: 123), NS(get_last_data=lambda: Data()))
    assert calls == []


def test_context_is_never_collected_for_a_passing_price(public):
    method, calls = diagnostic_method(public)
    def forbidden(*args):
        pytest.fail('failure context observed on success path')
    driver = NS(_now=lambda: 123, _execution_price_context=forbidden)
    assert method(driver, NS(price=17, get_last_data=lambda: NS(end_time=123, is_fill_forward=False))) == 17
    assert calls == [(17, True)]


@pytest.mark.parametrize('trade,quote,wanted_trade,wanted_quote,wanted_price', [
    (None, None, 'missing', 'missing', 'unknown'),
    (NS(end_time=123, is_fill_forward=False, close=17), None, 'fresh_non_fill_forward', 'missing', 'equal'),
    (NS(end_time=123, is_fill_forward=False, close=18), None, 'fresh_non_fill_forward', 'missing', 'different'),
    (NS(end_time=123, is_fill_forward=True, close=17), None, 'fresh_fill_forward', 'missing', 'equal'),
    (NS(end_time=122, is_fill_forward=False, close=17), None, 'stale', 'missing', 'equal'),
    (NS(end_time=123, is_fill_forward=0, close=17), None, 'invalid', 'missing', 'equal'),
    (NS(), None, 'invalid', 'missing', 'unknown'),
    (None, NS(end_time=123, is_fill_forward=False), 'missing', 'fresh_non_fill_forward', 'unknown'),
    (None, NS(end_time=123, is_fill_forward=True), 'missing', 'fresh_fill_forward', 'unknown'),
    (None, NS(end_time=122, is_fill_forward=False), 'missing', 'stale', 'unknown'),
    (None, NS(), 'missing', 'invalid', 'unknown')])
def test_failure_context_distinguishes_generic_cache_from_current_slice_without_values(public,
        trade, quote, wanted_trade, wanted_quote, wanted_price):
    method, _ = diagnostic_method(public)
    data = type('QuoteBar', (), {'end_time': 122, 'is_fill_forward': False})()
    symbol = 'SYNTHETIC-SYMBOL-NEVER-RETAIN'
    driver = NS(_now=lambda: 123, _algorithm=NS(current_slice=NS(
        bars={} if trade is None else {symbol: trade}, quote_bars={} if quote is None else {symbol: quote})))
    with pytest.raises(m.comparison.bridge.frozen.targets.NewruleError) as error:
        method(driver, NS(symbol=symbol, price=17, get_last_data=lambda: data))
    text = error.value.args[0]
    assert text in m.CONTEXT_FAILURE_CODES
    assert symbol not in text and '17' not in text and '122' not in text and '123' not in text
    assert m.parse_failure_context(text) == {'schema': m.CONTEXT_SCHEMA,
        'predicate': 'execution_price_end_not_current', 'cache_class': 'quote_bar',
        'trade_bar': wanted_trade, 'quote_bar': wanted_quote, 'price_trade': wanted_price}


@pytest.mark.parametrize('kind,cache', [('TradeBar', 'trade_bar'), ('QuoteBar', 'quote_bar'), ('Unrecognized', 'other')])
def test_cache_class_never_exports_raw_unknown_typename(public, kind, cache):
    method, _ = diagnostic_method(public)
    data = type(kind, (), {'end_time': 122, 'is_fill_forward': False})()
    with pytest.raises(m.comparison.bridge.frozen.targets.NewruleError) as error:
        method(NS(_now=lambda: 123), NS(get_last_data=lambda: data))
    context = m.parse_failure_context(error.value.args[0])
    assert context['cache_class'] == cache
    assert 'Unrecognized' not in error.value.args[0]


def test_context_observation_errors_do_not_mask_original_predicate_or_export_exception(public):
    method, _ = diagnostic_method(public)
    class Broken:
        @property
        def symbol(self):
            raise RuntimeError('SYNTHETIC-RAW-PRIVATE-EXCEPTION')
        def get_last_data(self):
            return None
    with pytest.raises(m.comparison.bridge.frozen.targets.NewruleError) as error:
        method(NS(_now=lambda: 123), Broken())
    context = m.parse_failure_context(error.value.args[0])
    assert context == {'schema': m.CONTEXT_SCHEMA, 'predicate': 'execution_price_missing',
        'cache_class': 'missing', 'trade_bar': 'invalid', 'quote_bar': 'invalid', 'price_trade': 'unknown'}
    assert 'PRIVATE' not in error.value.args[0]


def test_full_finite_failure_inventory_and_wrapped_error_parser():
    assert len(m.CONTEXT_FAILURE_CODES) == 900
    for code in m.CONTEXT_FAILURE_CODES:
        value = m.parse_failure_context(code)
        assert value is not None and m.validate_failure_context(value) == value
    code = 'execution_price_end_not_current|cache=quote_bar|trade=fresh_non_fill_forward|quote=stale|price_trade=equal'
    assert m.parse_failure_context('Runtime Error: ' + code + '\n at _current_execution_price') == m.parse_failure_context(code)


@pytest.mark.parametrize('bad', [None, True, 0, '', '\u2603', 'x' * 4097,
    'execution_price_missing',
    'execution_price_missing|cache=other|trade=missing|quote=missing|price_trade=unknown|extra=raw',
    'execution_price_missing|cache=SECRET|trade=missing|quote=missing|price_trade=unknown',
    'execution_price_missing|cache=other|trade=missing|quote=missing|price_trade=unknownTrailing'])
def test_unknown_unbounded_or_partial_context_never_leaks_raw_text(bad):
    assert m.parse_failure_context(bad) is None


def test_repeated_context_is_ambiguous_and_rejected():
    code = next(iter(m.CONTEXT_FAILURE_CODES))
    assert m.parse_failure_context(code + '\n' + code) is None


@pytest.mark.parametrize('field,value', [('schema', 'wrong'), ('predicate', 'unknown'),
    ('cache_class', 'unknown'), ('trade_bar', 'unknown'), ('quote_bar', False), ('price_trade', None)])
def test_decoded_context_must_keep_exact_closed_types_and_fields(field, value):
    context = m.parse_failure_context(next(iter(m.CONTEXT_FAILURE_CODES)))
    context[field] = value
    with pytest.raises(m.Refused, match='failure_context'):
        m.validate_failure_context(context)


def test_only_existing_method_changes_in_complete_runtime_ast(public):
    value = build(public)
    before = ast.parse(dict(public.pairs)[m.RUNTIME_NAME])
    after = ast.parse(dict(value.source_pairs)[m.RUNTIME_NAME])
    owner, replacement = m._method(after)
    _, original = m._method(before)
    owner.body[owner.body.index(replacement)] = original
    owner.body = [node for node in owner.body
        if not (isinstance(node, ast.FunctionDef) and node.name == '_execution_price_context')]
    assert m._dump(after) == m._dump(before)
    runtime = dict(value.source_pairs)[m.RUNTIME_NAME]
    for code in m.FAILURE_CODES:
        assert runtime.count(('\'' + code + '\'').encode()) == 1
    assert b'execution_price_not_current_minute' not in runtime


@pytest.mark.parametrize('bad', [None, True, '', 'a' * 63, 'A' * 64, 'a' * 65])
def test_patcher_requires_explicit_exact_external_pin(public, bad):
    with pytest.raises(m.Refused, match='patcher_pin'):
        m.public_specification(public.pairs, patcher_source_bytes=public.patcher, expected_patcher_sha256=bad)


def test_patcher_bytes_cannot_change_under_frozen_pin(public):
    with pytest.raises(m.Refused, match='patcher_pin'):
        m.public_specification(public.pairs, patcher_source_bytes=public.patcher + b'\n', expected_patcher_sha256=public.pin)


@pytest.mark.parametrize('index', range(11))
def test_each_parent_source_remains_manifest_bound(public, index):
    pairs = list(public.pairs)
    name, raw = pairs[index]
    pairs[index] = name, raw + b'\n'
    with pytest.raises(m.Refused, match='parent_manifest'):
        build(NS(pairs=tuple(pairs), patcher=public.patcher, pin=public.pin))


@pytest.mark.parametrize('kind', ['list', 'reverse', 'missing', 'duplicate', 'mutable', 'bool-name'])
def test_source_topology_and_immutable_bytes_are_required(public, kind):
    pairs = public.pairs
    if kind == 'list': pairs = list(pairs)
    elif kind == 'reverse': pairs = tuple(reversed(pairs))
    elif kind == 'missing': pairs = pairs[:-1]
    elif kind == 'duplicate': pairs = pairs[:-1] + (pairs[0],)
    elif kind == 'mutable': pairs = ((pairs[0][0], bytearray(pairs[0][1])),) + pairs[1:]
    else: pairs = ((True, pairs[0][1]),) + pairs[1:]
    with pytest.raises(m.Refused):
        build(NS(pairs=pairs, patcher=public.patcher, pin=public.pin))


def test_known_runtime_hash_and_exact_original_method_anchor_required(public, monkeypatch):
    raw = dict(public.pairs)[m.RUNTIME_NAME]
    changed = raw.replace(b'execution_price_not_current_minute', b'other_guard', 1)
    with pytest.raises(m.Refused, match='runtime_pin'):
        m._runtime(changed)
    monkeypatch.setattr(m, 'PARENT_RUNTIME_CLOUD', m.sha(changed))
    with pytest.raises(m.Refused, match='runtime_anchor'):
        m._runtime(changed)


def test_public_projection_performs_no_filesystem_or_operational_admission(public, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('pure projection reached filesystem or operational admission')
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'read_bytes', forbidden)
        patch.setattr(m.admission, 'admit', forbidden)
        patch.setattr(m.admission, 'source_checks', forbidden)
        result = build(public)
    assert result.to_record()['diagnostic_only'] is True


def test_packet_is_authenticated_before_any_projection(public, monkeypatch):
    calls = []
    def reject(packet):
        calls.append('packet')
        raise m.admission.Refused('public_packet')
    monkeypatch.setattr(m.admission, 'validate_packet', reject)
    monkeypatch.setattr(m, 'public_specification', lambda *args, **kwargs: pytest.fail('projection before packet authentication'))
    with pytest.raises(m.admission.Refused, match='public_packet'):
        m.build_projection({'untrusted': True}, patcher_source_bytes=public.patcher, expected_patcher_sha256=public.pin)
    assert calls == ['packet']


def test_authenticated_packet_projection_must_match_fixed_parent_pin(public, monkeypatch):
    monkeypatch.setattr(m.admission, 'validate_packet', lambda packet: (b'{}', public.pairs))
    with pytest.raises(m.Refused, match='parent_projection'):
        m.build_projection({}, patcher_source_bytes=public.patcher, expected_patcher_sha256=public.pin)


def test_packet_projection_matches_public_spec_after_actual_pure_receiver_validation(public, monkeypatch):
    # Construct only public synthetic metadata and rebind its test-only packet
    # pin. No actual readiness report or private artifact is loaded/replayed.
    ready = m.admission.a11.remote
    record = {'schema': 'arv2-r298-plain-projection-v1', 'candidate_id': 'R298',
        'package_sha256': ready.PACKAGE_SHA256, 'profile_sha256': ready.PROFILE_SHA256,
        'activation_manifest_sha256': ready.ACTIVATION_SHA256,
        'source_files': [{'project_path': name, 'byte_count': len(raw), 'content_sha256': m.sha(raw)}
            for name, raw in public.pairs]}
    raw = m.canonical(record)
    monkeypatch.setattr(ready, 'PROJECTION_SHA256', m.sha(raw))
    monkeypatch.setattr(m, 'PARENT_PROJECTION', m.sha(raw))
    manifest = {'project_id': 38364439, 'projection_sha256': m.sha(raw),
        'files': [{'name': name, 'byte_count': len(payload), 'sha256': m.sha(payload)} for name, payload in public.pairs]}
    monkeypatch.setattr(m, 'PARENT_MANIFEST', m.sha(m.canonical(manifest) + b'\n'))
    packet = {'admission_authenticated': True, 'projection_record': raw.decode('ascii'),
        'source_pairs': [[name, payload.decode('ascii')] for name, payload in public.pairs],
        'readiness_pin': m.admission.readiness_pin(), 'storage_receipt': m.admission.a11._storage_receipt()}
    result = m.build_projection(packet, patcher_source_bytes=public.patcher, expected_patcher_sha256=public.pin)
    assert result == build(public)


@pytest.mark.parametrize('field', ['projection_sha256', 'record_bytes', 'profile_bytes', 'source_pairs'])
def test_mutated_result_record_or_source_is_not_accepted(public, field):
    value = build(public)
    original = getattr(value, field)
    object.__setattr__(value, field, 'a' * 64 if field == 'projection_sha256' else () if field == 'source_pairs' else b'{}')
    try:
        with pytest.raises(m.Refused):
            value.to_record()
    finally:
        object.__setattr__(value, field, original)
    value.to_record()


def receiver(value, raw=None, pairs=None):
    return m.validate_public_projection(value.record_bytes if raw is None else raw,
        value.source_pairs if pairs is None else pairs,
        expected_projection_sha256=value.projection_sha256,
        expected_profile_sha256=json.loads(value.profile_bytes)['profile_sha256'])


def test_pure_receiver_checks_public_source_and_profile_binding(public):
    value = build(public)
    record, profile, pairs = receiver(value)
    assert record == value.to_record()
    assert profile == json.loads(value.profile_bytes) and pairs == value.source_pairs


def test_receiver_checks_external_hash_before_json_parser(public, monkeypatch):
    value = build(public)
    expected_profile = json.loads(value.profile_bytes)['profile_sha256']
    monkeypatch.setattr(m.json, 'loads', lambda *args, **kwargs: pytest.fail('parse before external hash'))
    with pytest.raises(m.Refused, match='projection_pin'):
        m.validate_public_projection(b'{}', value.source_pairs,
            expected_projection_sha256=value.projection_sha256, expected_profile_sha256=expected_profile)


@pytest.mark.parametrize('change', ['schema', 'parent', 'profile', 'codes', 'flag', 'source', 'runtime-pin'])
def test_receiver_refuses_semantic_corruption_even_under_synthetic_rebound_pin(public, change):
    value = build(public)
    record = value.to_record()
    pairs = value.source_pairs
    if change == 'schema': record['schema'] = 'wrong'
    elif change == 'parent': record['parent_projection_sha256'] = 'a' * 64
    elif change == 'profile': record['profile_sha256'] = 'b' * 64
    elif change == 'codes': record['failure_codes'].append('unknown')
    elif change == 'flag': record['backtest_created'] = 0
    elif change == 'source': pairs = pairs[:-1] + ((pairs[-1][0], pairs[-1][1] + b'\n'),)
    else: record['patcher_sha256'] = 'c' * 64
    raw = m.canonical(record)
    with pytest.raises(m.Refused, match='projection_packet'):
        m.validate_public_projection(raw, pairs, expected_projection_sha256=m.sha(raw),
            expected_profile_sha256=json.loads(value.profile_bytes)['profile_sha256'])
