"""Public-source and synthetic failure-only history probe checks."""
import ast
import builtins
import copy
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_newrule_raw_reference_diagnostic_projection as m
from tests.analyst_revisions_v2 import test_quote_execution_projection as qtests


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
REFERENCE = datetime(2022, 10, 21)
NOW = datetime(2022, 10, 24, 9, 20)


@pytest.fixture(scope='module')
def public():
    parent = qtests.public.__wrapped__()
    patcher = (ROOT / 'scripts' / m.PATCHER_NAME).read_bytes()
    value = m.public_specification(parent.projected.source_pairs,
        patcher_source_bytes=patcher, expected_patcher_sha256=m.sha(patcher))
    return NS(parent=parent, patcher=patcher, pin=m.sha(patcher), projected=value,
        old=dict(parent.projected.source_pairs), files=dict(value.source_pairs),
        profile=json.loads(value.profile_bytes))


def test_only_legacy_failure_branch_and_main_profile_change(public):
    value, old, files = public.projected, public.old, public.files
    assert {name for name in old if old[name] != files[name]} == {m.LEGACY_NAME, 'main.py'}
    assert files[m.quote.RUNTIME_NAME] == old[m.quote.RUNTIME_NAME]
    assert m.sha(files[m.quote.RUNTIME_NAME]) == m.PARENT_RUNTIME
    old_tree, tree = ast.parse(old[m.LEGACY_NAME]), ast.parse(files[m.LEGACY_NAME])
    before, after = m._legacy_method(old_tree), m._legacy_method(tree)
    old_branch, = [node for node in before.body if isinstance(node, ast.If)
        and m._dump(node.test) == m._dump(ast.parse('set(result) != set(security_ids)', mode='eval').body)]
    branch, = [node for node in after.body if isinstance(node, ast.If)
        and m._dump(node.test) == m._dump(old_branch.test)]
    branch.body = copy.deepcopy(old_branch.body)
    assert m._dump(tree) == m._dump(old_tree)
    main, old_main = ast.parse(files['main.py']), ast.parse(old['main.py'])
    m.quote._driver(main)['profile'].value = copy.deepcopy(m.quote._driver(old_main)['profile'].value)
    assert m._dump(main) == m._dump(old_main)
    record = value.to_record()
    assert record['diagnostic_only'] is True and record['policy'] == m.policy_record()
    assert all(record[name] is False for name in m.FALSE_FLAGS)
    assert public.profile['profile_sha256'] != m.PARENT_PROFILE
    assert len(record['unchanged_cloud_files']) == 9
    assert public.profile['source_pins'][m.LEGACY_NAME] == m.sha(files[m.LEGACY_NAME])
    assert m.PATCHER_NAME in public.profile['source_pins']
    assert all(len(raw) <= 64000 for raw in files.values())


def test_unchanged_cloud_make_profile_recomputes_diagnostic_profile(public):
    tree = ast.parse(public.files[m.quote.RUNTIME_NAME])
    namespace = dict(vars(m.comparison.bridge.frozen.runtime))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[m.quote._node(tree, 'make_profile')],
        type_ignores=[])), 'synthetic quote make_profile', 'exec'), namespace)
    assert namespace['make_profile'](m.comparison.bridge.frozen.october._sessions(),
        package_sha256=public.profile['package_sha256'], lineage_sha256=public.profile['lineage_sha256'],
        universe_count=6, ar_percent=0, source_pins=public.profile['source_pins']) == public.profile


def test_public_receiver_and_build_chain_interoperate_without_private_reads(public, monkeypatch):
    record, profile, pairs = m.validate_public_projection(public.projected.record_bytes,
        public.projected.source_pairs, expected_projection_sha256=public.projected.projection_sha256,
        expected_profile_sha256=public.profile['profile_sha256'])
    assert record == public.projected.to_record() and profile == public.profile
    assert pairs == public.projected.source_pairs
    packet, calls = object(), []
    def admitted(value, **kwargs):
        assert value is packet and kwargs == {'patcher_source_bytes': public.parent.patcher,
            'expected_patcher_sha256': public.parent.pin}
        calls.append(value)
        return public.parent.projected
    monkeypatch.setattr(m.quote, 'build_projection', admitted)
    result = m.build_projection(packet, patcher_source_bytes=public.patcher,
        expected_patcher_sha256=public.pin, quote_patcher_source_bytes=public.parent.patcher)
    assert result == public.projected and calls == [packet]


def test_public_specification_has_no_filesystem_or_operational_calls(public, monkeypatch):
    def forbidden(*args, **kwargs): pytest.fail('pure specification crossed an operational boundary')
    monkeypatch.setattr(builtins, 'open', forbidden)
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    monkeypatch.setattr(m.admission, 'admit', forbidden)
    assert m.public_specification(public.parent.projected.source_pairs,
        patcher_source_bytes=public.patcher, expected_patcher_sha256=public.pin) == public.projected


@pytest.mark.parametrize('change', ['runtime', 'legacy', 'main', 'patcher', 'order', 'missing'])
def test_parent_source_or_patcher_drift_refuses(public, change):
    pairs, pin = list(public.parent.projected.source_pairs), public.pin
    name = {'runtime': m.quote.RUNTIME_NAME, 'legacy': m.LEGACY_NAME, 'main': 'main.py'}.get(change)
    if name:
        pairs = [(key, raw + b'# altered\n' if key == name else raw) for key, raw in pairs]
    if change == 'patcher': pin = '0' * 64
    if change == 'order': pairs.reverse()
    if change == 'missing': pairs.pop()
    with pytest.raises(m.Refused):
        m.public_specification(tuple(pairs), patcher_source_bytes=public.patcher, expected_patcher_sha256=pin)


class LegacyError(ValueError):
    pass


class Symbol:
    def __init__(self, sid, origin=datetime(2000, 1, 1)):
        self.sid, self.id = sid, NS(date=origin)


class Batch(dict):
    def __init__(self, items=(), *, when=None):
        super().__init__(items)
        self.time = when or REFERENCE.replace(hour=16)


class ProbeBar:
    def __init__(self, symbol, *, day=None, fill=False, end=None):
        self.symbol = symbol
        self.time = (day or REFERENCE).replace(hour=9, minute=30)
        self.end_time = end or (day or REFERENCE).replace(hour=16)
        self.is_fill_forward = fill

    @property
    def close(self):
        raise AssertionError('probe must never inspect a price')


def case(public, *, count=2, returned=0, probe=None, now=NOW, omit_final_refusal=False):
    tree = ast.parse(public.files[m.LEGACY_NAME])
    method = copy.deepcopy(m._legacy_method(tree))
    if omit_final_refusal:
        branch, = [node for node in method.body if isinstance(node, ast.If)
            and m._dump(node.test) == m._dump(ast.parse('set(result) != set(security_ids)', mode='eval').body)]
        assert isinstance(branch.body[-1], ast.Expr) and branch.body[-1].value.func.id == '_error'
        branch.body[-1] = ast.Pass()
    namespace = {'datetime': datetime, 'timedelta': timedelta, 'json': json,
        'MAXIMUM_REFERENCE_SECURITIES': 256, 'MAXIMUM_REFERENCE_HISTORY_CALLS': 400,
        'AcceptedRiskSixUniverseOrderQcRuntimeError': LegacyError,
        '_symbol_sid': lambda symbol, label: symbol.sid,
        '_decimal': lambda value, label, positive=False: Decimal(value)}
    def fail(message): raise LegacyError(message)
    namespace['_error'] = fail
    cls = ast.ClassDef(name='Driver', bases=[], keywords=[], body=[method], decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
        'synthetic reference method', 'exec'), namespace)
    symbols = {f'S{index:03d}': Symbol(f'SID{index:03d}') for index in range(count)}
    ids = tuple(sorted(symbols))
    first = [Batch([(symbols[key], NS(symbol=symbols[key], time=REFERENCE.replace(hour=9, minute=30),
        close=Decimal(100))) for key in ids[:returned]])] if returned else []
    c = NS(symbols=symbols, ids=ids, primary=first, probe=probe, calls=[], driver=namespace['Driver']())
    class History:
        def __getitem__(self, kind):
            assert kind is ProbeBar
            def query(*args, **kwargs):
                c.calls.append((args, kwargs))
                if len(c.calls) == 1: return c.primary
                if isinstance(c.probe, Exception): raise c.probe
                return [] if c.probe is None else c.probe
            return query
    d = c.driver
    d._algorithm = NS(history=History())
    d._trade_bar_type, d._daily_resolution, d._raw_normalization = ProbeBar, 'DAILY', 'RAW'
    d._reference_history_call_count = 0
    d._ensure_security = lambda identity: (symbols[identity], object())
    d._current_holding_census = lambda: {ids[-1]: 1}
    d._security_by_sid = {symbol.sid: identity for identity, symbol in symbols.items()}
    d._security_by_etf_sid = {}
    d._now = lambda: now
    return c


def observed(c):
    with pytest.raises(LegacyError) as error:
        c.driver._reference_prices('2022-10-21', c.ids)
    text = error.value.args[0]
    assert text.startswith(m.ORIGINAL_FAILURE + '\n')
    context = m.parse_failure_context(text)
    assert context is not None and m.validate_failure_context(context) == context
    assert 'SID' not in text and 'S000' not in text
    return context


def test_success_path_unchanged_one_query_and_exact_prices(public):
    c = case(public, count=2, returned=2)
    assert c.driver._reference_prices('2022-10-21', c.ids) == {'S000': Decimal(100), 'S001': Decimal(100)}
    assert len(c.calls) == c.driver._reference_history_call_count == 1


def test_omitting_final_refusal_is_detected_even_when_probe_finds_exact_reference(public):
    def assertion(omit=False):
        c = case(public, count=1, omit_final_refusal=omit)
        symbol = c.symbols['S000']
        c.probe = [Batch([(symbol, ProbeBar(symbol))])]
        try:
            c.driver._reference_prices('2022-10-21', c.ids)
        except LegacyError:
            return
        raise AssertionError('probe incorrectly repaired incomplete sizing census')
    assertion()
    with pytest.raises(AssertionError, match='incorrectly repaired'):
        assertion(True)


@pytest.mark.parametrize('kind', ['source', 'profile', 'record', 'flag', 'policy', 'runtime'])
def test_public_receiver_refuses_drift_and_false_acceptance_aliases(public, kind):
    raw, pairs, pin = public.projected.record_bytes, public.projected.source_pairs, public.profile['profile_sha256']
    if kind in ('source', 'runtime'):
        name = m.quote.RUNTIME_NAME if kind == 'runtime' else m.LEGACY_NAME
        pairs = tuple((key, value + b'# drift\n' if key == name else value) for key, value in pairs)
    if kind == 'profile': pin = '0' * 64
    if kind in ('record', 'flag', 'policy'):
        value = json.loads(raw)
        if kind == 'record': value['extra'] = 'not admitted'
        if kind == 'flag': value['family_comparable'] = 0
        if kind == 'policy': value['policy']['probe_prices_used'] = 0
        raw = m.canonical(value)
    with pytest.raises(m.Refused):
        m.validate_public_projection(raw, pairs, expected_projection_sha256=m.sha(raw),
            expected_profile_sha256=pin)


def test_failure_probe_only_missing_and_never_repairs_even_exact_reference_found(public):
    c = case(public, count=3, returned=2)
    missing = c.symbols['S002']
    c.probe = [Batch([(missing, ProbeBar(missing))])]
    context = observed(c)
    assert context['requested'] == 3 and context['returned'] == 2 and context['missing'] == 1
    assert context['missing_holdings'] == {'held': 1, 'unheld_target': 0, 'unknown': 0}
    assert context['probe']['status'] == 'complete' and context['probe']['identity_valid'] is True
    assert context['probe']['rows_by_offset']['exact_reference'] == 1
    assert context['probe_prices_used'] is False and context['sizing_repaired'] is False
    assert len(c.calls) == 2 and c.driver._reference_history_call_count == 1
    args, kwargs = c.calls[1]
    assert args == ([missing], REFERENCE - timedelta(days=5), REFERENCE + timedelta(days=2), 'DAILY')
    assert kwargs == {'fill_forward': False, 'extended_market_hours': False, 'data_normalization_mode': 'RAW'}


@pytest.mark.parametrize('origin,bucket', [(datetime(2000, 1, 1), 'on_or_before_reference'),
    (datetime(2022, 10, 24), 'after_reference_through_decision'),
    (datetime(2023, 1, 1), 'after_decision'), (None, 'unknown')])
def test_missing_classification_is_aggregate_only_and_sid_date_not_listing_proof(public, origin, bucket):
    c = case(public, count=1)
    c.symbols['S000'].id.date = origin
    c.driver._security_by_etf_sid[c.symbols['S000'].sid] = 'synthetic'
    context = observed(c)
    assert context['missing_kind'] == {'own_etf': 1, 'stock': 0, 'unknown': 0}
    assert context['missing_sid_date'][bucket] == 1
    assert m.policy_record()['sid_date_is_independent_listing_proof'] is False


def test_held_and_unheld_and_unknown_memory_observations_are_not_new_queries(public):
    c = case(public, count=2)
    assert observed(c)['missing_holdings'] == {'held': 1, 'unheld_target': 1, 'unknown': 0}
    c = case(public, count=2)
    def unavailable(): raise ValueError('PRIVATE portfolio support detail')
    c.driver._current_holding_census = unavailable
    assert observed(c)['missing_holdings'] == {'held': 0, 'unheld_target': 0, 'unknown': 2}


def test_probe_dates_are_bucketed_without_prices_or_symbols(public):
    c = case(public, count=1)
    symbol = c.symbols['S000']
    days = [REFERENCE - timedelta(days=1), REFERENCE, REFERENCE + timedelta(days=1)]
    c.probe = [Batch([(symbol, ProbeBar(symbol, day=day))], when=day.replace(hour=16)) for day in days]
    context = observed(c)
    assert context['probe']['status'] == 'complete'
    assert context['probe']['rows_by_offset'] == {key: 1 for key in m.OFFSET_BUCKETS}


def test_probe_end_is_capped_at_current0920_and_no_future_close_admitted(public):
    reference = datetime(2022, 10, 21)
    now = datetime(2022, 10, 22, 9, 20)
    c = case(public, count=1, now=now)
    symbol = c.symbols['S000']
    c.probe = [Batch([(symbol, ProbeBar(symbol, day=now))], when=now.replace(hour=16))]
    context = observed(c)
    assert c.calls[1][0][2] == now
    assert context['probe']['status'] == 'time_invalid'
    assert context['probe']['rows_by_offset']['after_reference_before_cutoff'] == 0


@pytest.mark.parametrize('count,now,status', [(17, NOW, 'skipped_limit'),
    (1, NOW.replace(hour=9, minute=21), 'unknown_clock'),
    (1, datetime(2022, 10, 21, 9, 20), 'unknown_clock')])
def test_missing_or_clock_bounds_skip_probe_but_preserve_primary_refusal(public, count, now, status):
    c = case(public, count=count, now=now)
    context = observed(c)
    assert context['probe']['status'] == status and context['probe']['request_invoked'] is False
    assert len(c.calls) == 1


@pytest.mark.parametrize('change', ['lookup', 'noncallable', 'resolution', 'normalization'])
def test_pre_call_lookup_or_argument_failure_does_not_claim_probe_invocation(public, change):
    c = case(public, count=1)
    history = c.driver._algorithm.history
    if change in ('lookup', 'noncallable'):
        class Lookup:
            count = 0
            def __getitem__(self, kind):
                self.count += 1
                if self.count == 2:
                    if change == 'lookup': raise RuntimeError('PRIVATE overload lookup')
                    return None
                return history[kind]
        c.driver._algorithm.history = Lookup()
    else:
        attribute = '_daily_resolution' if change == 'resolution' else '_raw_normalization'
        original_type = type(c.driver)
        class Arguments(original_type):
            reads = 0
        def observed_property(self):
            self.reads += 1
            if self.reads == 2: raise RuntimeError('PRIVATE argument lookup')
            return 'DAILY' if change == 'resolution' else 'RAW'
        setattr(Arguments, attribute, property(observed_property))
        c.driver.__class__ = Arguments
    context = observed(c)
    probe = context['probe']
    assert probe['status'] == 'read_failed' and probe['requested'] == 0
    assert probe['request_invoked'] is False and probe['identity_valid'] is None
    assert probe['items'] == probe['batches'] == 0 and len(c.calls) == 1


@pytest.mark.parametrize('kind,status', [('call', 'call_failed'), ('iterator', 'read_failed'),
    ('identity', 'identity_invalid'), ('payload', 'identity_invalid'), ('fill', 'fill_forward_invalid'),
    ('future', 'time_invalid')])
def test_probe_refusals_remain_finite_and_never_hide_original_missing_census(public, kind, status):
    c = case(public, count=1)
    symbol = c.symbols['S000']
    if kind == 'call': c.probe = ValueError('PRIVATE RAW SECRET')
    elif kind == 'iterator':
        class Broken:
            def __iter__(self): raise RuntimeError('PRIVATE ITERATOR')
        c.probe = Broken()
    else:
        key, bar = symbol, ProbeBar(symbol)
        if kind == 'identity': key = Symbol('wrong')
        if kind == 'payload': bar.symbol = Symbol('wrong')
        if kind == 'fill': bar.is_fill_forward = True
        if kind == 'future': bar.end_time = NOW + timedelta(days=1)
        c.probe = [Batch([(key, bar)])]
    context = observed(c)
    assert context['probe']['status'] == status
    assert 'PRIVATE' not in json.dumps(context)


@pytest.mark.parametrize('kind', ['batches', 'items'])
def test_reader_bounds_allow_only_one_unprocessed_sentinel(public, kind):
    c = case(public, count=1)
    symbol = c.symbols['S000']
    if kind == 'batches':
        c.probe = [Batch() for _ in range(9)]
    else:
        class Many:
            time = REFERENCE.replace(hour=16)
            def items(self):
                for unused in range(129): yield (symbol, ProbeBar(symbol))
        c.probe = [Many()]
    context = observed(c)
    assert context['probe']['status'] == 'bound_exceeded'
    assert context['probe']['batches'] <= 8 and context['probe']['items'] <= 128


@pytest.mark.parametrize('change', ['extra', 'bool_count', 'sum', 'status', 'bad_flag', 'probe_count',
    'prices', 'identity', 'offset', 'unknown_deep'])
def test_closed_context_rejects_forged_or_unbounded_metadata(change):
    value = m.context_record(2, 1)
    if change == 'extra': value['raw_symbol'] = 'SECRET'
    if change == 'bool_count': value['requested'] = True
    if change == 'sum': value['missing'] = 2
    if change == 'status': value['probe']['status'] = 'guessed cause'
    if change == 'bad_flag': value['cause_authenticated'] = 0
    if change == 'probe_count': value['probe']['items'] = 129
    if change == 'prices': value['probe_prices_used'] = True
    if change == 'identity': value['probe']['identity_valid'] = True
    if change == 'offset': value['probe']['rows_by_offset']['extra'] = 1
    if change == 'unknown_deep': value['probe'] = [object()] * 100000
    with pytest.raises(m.Refused, match='^failure_context$'): m.validate_failure_context(value)


def test_context_validation_does_not_render_or_serialize_unknown_hostile_values(monkeypatch):
    class Hostile:
        def __str__(self): pytest.fail('raw object rendered')
    value = m.context_record(1, 0)
    value['probe']['status'] = Hostile()
    def forbidden(*args, **kwargs): pytest.fail('invalid context reached serialization')
    monkeypatch.setattr(m, 'canonical', forbidden)
    with pytest.raises(m.Refused, match='^failure_context$'): m.validate_failure_context(value)


def test_parser_accepts_one_canonical_wrapped_context_and_rejects_ambiguity_or_raw_legacy():
    value = m.context_record(2, 1)
    token = m.FAILURE_CODES[0] + '|context=' + m.canonical(value).decode('ascii')
    assert m.parse_failure_context('Runtime Error: ' + token + '\n at frame') == value
    assert m.parse_failure_context(token + '\n' + token) is None
    assert m.parse_failure_context(m.ORIGINAL_FAILURE + '; context={"raw":"private"}') is None
    assert m.parse_failure_context(token + 'trailing') is None
    assert m.parse_failure_context(token.replace('"requested":2', '"requested":2,"requested":2')) is None
    assert m.parse_failure_context('x' * 8193) is None
