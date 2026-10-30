"""Public-source and synthetic quote-aware policy checks; native denial required."""
import ast
import builtins
import copy
import dataclasses
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

import pytest

from scripts import arv2_newrule_quote_execution_projection as m


ROOT = Path('/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2')
NY = ZoneInfo('America/New_York')
NOW = datetime(2021, 2, 22, 9, 31, tzinfo=NY)
BASE_RUNTIME = m.comparison.bridge.frozen.runtime
NewruleError = m.comparison.bridge.frozen.targets.NewruleError


@pytest.fixture(scope='module')
def public():
    research = ROOT / 'research/analyst_revisions_v2_qc'
    comparison = m.comparison
    names = set(comparison.bridge.parent.SOURCE_PINS) | set(comparison.NEW_SOURCE_PINS) | {comparison.HOST_SOURCE_NAME}
    sources = {name: (research / name).read_bytes() for name in names}
    spec = comparison.public_specification(sources=sources,
        expected_host_source_pins={comparison.HOST_SOURCE_NAME: m.sha(sources[comparison.HOST_SOURCE_NAME])})
    pairs = tuple((item.project_path, item.source_bytes) for item in spec.cells[0].source_files)
    patcher = (ROOT / 'scripts' / m.PATCHER_NAME).read_bytes()
    pin = m.sha(patcher)
    projected = m.public_specification(pairs, patcher_source_bytes=patcher, expected_patcher_sha256=pin)
    return NS(pairs=pairs, patcher=patcher, pin=pin, projected=projected,
        old=dict(pairs), files=dict(projected.source_pairs), profile=json.loads(projected.profile_bytes))


def build(value):
    return m.public_specification(value.pairs, patcher_source_bytes=value.patcher,
        expected_patcher_sha256=value.pin)


def test_two_cloud_files_only_and_explicit_economic_revision(public):
    old, files = public.old, public.files
    record = public.projected.to_record()
    assert {name for name in old if old[name] != files[name]} == {m.RUNTIME_NAME, 'main.py'}
    assert len(record['unchanged_cloud_files']) == 9
    assert m.comparison.bridge.INPUT_NAME in record['unchanged_cloud_files']
    assert record['economic_revision'] is True and record['diagnostic_only'] is False
    assert record['policy'] == m.policy_record()
    assert all(record[name] is False for name in m.FALSE_FLAGS)
    assert all(len(raw) <= 64000 for raw in files.values())
    assert sum(len(raw) for raw in files.values()) <= 448 * 1024
    assert public.profile['candidate_id'].endswith('-quote-aware-v1')
    assert public.profile['execution_policy'] == m.POLICY
    assert public.profile['source_pins'][m.RUNTIME_NAME] == m.sha(files[m.RUNTIME_NAME])
    assert public.profile['source_pins'][m.PATCHER_NAME] == public.pin
    assert tuple(name for name, _ in public.projected.source_pairs) == tuple(name for name, _ in public.pairs)


def test_projected_make_profile_exactly_recomputes_host_profile_and_result_parser_unchanged(public):
    old_tree, tree = ast.parse(public.old[m.RUNTIME_NAME]), ast.parse(public.files[m.RUNTIME_NAME])
    before, after = m._node(old_tree, 'validate_result_statistics'), m._node(tree, 'validate_result_statistics')
    assert m._dump(before) == m._dump(after)
    namespace = dict(vars(BASE_RUNTIME))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[m._node(tree, 'make_profile')], type_ignores=[])),
        'synthetic projected make_profile', 'exec'), namespace)
    actual = namespace['make_profile'](m.comparison.bridge.frozen.october._sessions(),
        package_sha256=public.profile['package_sha256'], lineage_sha256=public.profile['lineage_sha256'],
        universe_count=6, ar_percent=0, source_pins=public.profile['source_pins'])
    assert actual == public.profile
    assert m.validate_result_statistics is BASE_RUNTIME.validate_result_statistics
    old_profile = ast.literal_eval(m._driver(ast.parse(public.old['main.py']))['profile'].value)
    excluded = {'candidate_id', 'profile_sha256', 'source_pins'} | set(m.policy_profile_fields())
    assert {key: value for key, value in actual.items() if key not in excluded} == {
        key: value for key, value in old_profile.items() if key not in excluded}


def test_runtime_other_methods_exact_and_main_expected_constructor_and_fee_changes(public):
    old_tree, tree = ast.parse(public.old[m.RUNTIME_NAME]), ast.parse(public.files[m.RUNTIME_NAME])
    old_owner, owner = m._owner(old_tree), m._owner(tree)
    allowed = {'__init__', '_current_execution_price', '_submit_market', 'on_after_open', 'on_order_event'}
    old_methods = {node.name: node for node in old_owner.body if isinstance(node, ast.FunctionDef)}
    methods = {node.name: node for node in owner.body if isinstance(node, ast.FunctionDef)}
    assert set(methods) - set(old_methods) == {'_quote_snapshot', 'fee_basis'}
    for name in old_methods.keys() - allowed:
        assert m._dump(old_methods[name]) == m._dump(methods[name])
    assert [arg.arg for arg in methods['__init__'].args.kwonlyargs].count('quote_bar_type') == 1
    keywords = m._driver(ast.parse(public.files['main.py']))
    assert m._dump(keywords['quote_bar_type'].value) == m._dump(ast.Name(id='QuoteBar', ctx=ast.Load()))
    assert m._dump(keywords['fee_model_factory'].value) == m._dump(ast.parse(
        'lambda: NewruleTenBpsFeeModel(self._driver)', mode='eval').body)
    for name in ('activation_manifest_key', 'activation_manifest_sha256', 'activation_manifest_byte_count'):
        assert m._dump(keywords[name]) == m._dump(m._driver(ast.parse(public.old['main.py']))[name])
    assert not any(isinstance(node, ast.Attribute) and node.attr in ('set_market_price', 'add_data', 'set_holdings')
        for node in ast.walk(tree))


def test_public_receiver_interoperates_and_fresh_record_is_not_authority(public):
    record, profile, pairs = m.validate_public_projection(public.projected.record_bytes,
        public.projected.source_pairs, expected_projection_sha256=public.projected.projection_sha256,
        expected_profile_sha256=public.profile['profile_sha256'])
    assert record == public.projected.to_record() and profile == public.profile
    assert pairs == public.projected.source_pairs
    record['backtest_created'] = True
    assert public.projected.to_record()['backtest_created'] is False
    with pytest.raises(dataclasses.FrozenInstanceError):
        public.projected.source_pairs = ()


def test_public_builder_has_no_filesystem_or_operational_boundary(public, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('pure builder crossed a filesystem or operational boundary')
    with monkeypatch.context() as patch:
        patch.setattr(builtins, 'open', forbidden)
        patch.setattr(Path, 'read_bytes', forbidden)
        patch.setattr(m.admission, 'admit', forbidden)
        result = build(public)
    assert result == public.projected


@pytest.mark.parametrize('kind', ['changed_source', 'reordered', 'missing', 'nonascii', 'patcher'])
def test_old_parent_and_patcher_bytes_are_bound(public, kind):
    pairs, pin = list(public.pairs), public.pin
    if kind == 'changed_source': pairs[0] = (pairs[0][0], pairs[0][1] + b'# altered\n')
    if kind == 'reordered': pairs.reverse()
    if kind == 'missing': pairs.pop()
    if kind == 'nonascii': pairs[0] = (pairs[0][0], b'\xff')
    if kind == 'patcher': pin = '0' * 64
    with pytest.raises(m.Refused):
        m.public_specification(tuple(pairs), patcher_source_bytes=public.patcher,
            expected_patcher_sha256=pin)


@pytest.mark.parametrize('kind', ['source', 'profile', 'record', 'pair_alias', 'policy', 'flags', 'policy_alias'])
def test_receiver_rejects_malformed_or_mismatched_supplied_output(public, kind):
    pairs, raw, profile_pin = public.projected.source_pairs, public.projected.record_bytes, public.profile['profile_sha256']
    if kind == 'source': pairs = tuple((name, value + b'# drift\n' if name == 'main.py' else value) for name, value in pairs)
    if kind == 'profile': profile_pin = '0' * 64
    if kind == 'pair_alias': pairs = list(pairs)
    if kind in ('record', 'policy', 'flags', 'policy_alias'):
        record = json.loads(raw)
        if kind == 'record': record['extra'] = True
        if kind == 'policy': record['policy']['engine_price_cache_modified'] = True
        if kind == 'policy_alias': record['policy']['engine_price_cache_modified'] = 0
        if kind == 'flags': record['family_comparable'] = 0
        raw = m.canonical(record)
    with pytest.raises(m.Refused):
        m.validate_public_projection(raw, pairs, expected_projection_sha256=m.sha(raw),
            expected_profile_sha256=profile_pin)


def harness_class(public, *, omit=None):
    tree = ast.parse(public.files[m.RUNTIME_NAME])
    names = {'_quote_snapshot', '_current_execution_price', 'fee_basis', '_submit_market',
        'on_after_open', 'on_order_event'}
    methods = [copy.deepcopy(node) for node in m._owner(tree).body
        if isinstance(node, ast.FunctionDef) and node.name in names]
    if omit:
        class Omit(ast.NodeTransformer):
            def visit_Expr(self, node):
                value = node.value
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == 'require' \
                        and value.args and isinstance(value.args[-1], ast.Constant) and value.args[-1].value == omit:
                    return ast.Pass()
                return self.generic_visit(node)
        methods = [Omit().visit(node) for node in methods]
    namespace = dict(vars(BASE_RUNTIME))
    namespace['legacy'] = NS(_symbol_sid=lambda symbol, label: symbol.sid)
    cls = ast.ClassDef(name='Harness', bases=[], keywords=[], body=methods, decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
        'synthetic projected driver methods', 'exec'), namespace)
    return namespace['Harness']


class QuoteBar:
    def __init__(self, symbol, *, start=None, end=None, fill=False, bid='90', ask='110'):
        self.symbol = symbol
        self.time, self.end_time = start or NOW - timedelta(minutes=1), end or NOW
        self.is_fill_forward = fill
        self.bid = NS(close=bid) if bid is not None else None
        self.ask = NS(close=ask) if ask is not None else None

    @property
    def period(self):
        raise AssertionError('must not guess Python.NET TimeSpan conversion')


class TypedCache:
    def __init__(self, value):
        self.value = value
        self.get_data = self

    def __getitem__(self, kind):
        assert kind is QuoteBar
        return lambda: self.value


def case(public, *, omit=None):
    symbol = NS(sid='synthetic-security')
    quote = QuoteBar(symbol)
    cached = QuoteBar(symbol)
    security = NS(symbol=symbol, price=Decimal('100'), bid_price=Decimal('90'), ask_price=Decimal('110'),
        cache=TypedCache(cached))
    driver = harness_class(public, omit=omit)()
    driver._now = lambda: NOW
    driver._quote_bar_type = QuoteBar
    driver._algorithm = NS(current_slice=NS(quote_bars={'synthetic-security': quote}))
    # Synthetic symbols are hashable strings for indexing, with stable SID
    # objects exposed via the mapping's explicit equality below.
    class Bars:
        def __contains__(self, key):
            return key.sid == symbol.sid and 'synthetic-security' in self.values
        def __getitem__(self, key):
            return self.values[key.sid]
    bars = Bars()
    bars.values = {'synthetic-security': quote}
    driver._algorithm.current_slice.quote_bars = bars
    driver._intent = None
    return NS(driver=driver, security=security, quote=quote, cached=cached, bars=bars, symbol=symbol)


def test_quote_ready_accepts_stale_engine_price_and_awkward_period_without_cache_mutation(public):
    c = case(public)
    stale = c.security.price
    assert c.driver._current_execution_price(c.security, 1) == Decimal('110')
    assert c.driver._current_execution_price(c.security, -1) == Decimal('90')
    assert c.security.price is stale and stale == 100


@pytest.mark.parametrize('quantity', [0, True, None, Decimal(1), 1.5])
def test_quantity_is_signed_nonzero_whole_integer(public, quantity):
    c = case(public)
    with pytest.raises(NewruleError, match='^quote_execution_quantity$'):
        c.driver._current_execution_price(c.security, quantity)


@pytest.mark.parametrize('change,code', [
    ('clock', 'quote_execution_clock'), ('missing', 'quote_execution_slice'),
    ('unsupported', 'quote_execution_type'), ('symbol', 'quote_execution_identity'),
    ('stale', 'quote_execution_period'), ('future', 'quote_execution_period'),
    ('period', 'quote_execution_period'), ('fill', 'quote_execution_fill_forward'),
    ('fill_alias', 'quote_execution_fill_forward'), ('one_side', 'quote_execution_sides'),
    ('zero', 'quote_execution_sides'), ('nan', 'quote_execution_sides'),
    ('crossed', 'quote_execution_spread'), ('cache_missing', 'quote_execution_cache'),
    ('cache_side', 'quote_execution_cache_binding'), ('cache_time', 'quote_execution_period'),
    ('security_side', 'quote_execution_security_sides')])
def test_readiness_refuses_each_unsafe_direction(public, change, code):
    c = case(public)
    if change == 'clock': c.driver._now = lambda: NOW + timedelta(seconds=1)
    if change == 'missing': c.bars.values.clear()
    if change == 'unsupported': c.bars.values[c.symbol.sid] = NS()
    if change == 'symbol': c.quote.symbol = NS(sid='wrong')
    if change == 'stale': c.quote.end_time -= timedelta(minutes=1)
    if change == 'future': c.quote.end_time += timedelta(minutes=1)
    if change == 'period': c.quote.time -= timedelta(minutes=1)
    if change == 'fill': c.quote.is_fill_forward = True
    if change == 'fill_alias': c.quote.is_fill_forward = 0
    if change == 'one_side': c.quote.ask = None
    if change == 'zero': c.quote.bid.close = 0
    if change == 'nan': c.quote.ask.close = Decimal('NaN')
    if change == 'crossed': c.quote.bid.close = '111'
    if change == 'cache_missing': c.security.cache.value = None
    if change == 'cache_side': c.cached.bid.close = '91'
    if change == 'cache_time': c.cached.end_time -= timedelta(minutes=1)
    if change == 'security_side': c.security.ask_price = Decimal('109')
    with pytest.raises(NewruleError, match='^' + code + '$'):
        c.driver._current_execution_price(c.security, 1)


def strategy(c, quantity=2):
    c.driver._intent = {'qc_sid': c.symbol.sid, 'tag': 'ARV2N-synthetic', 'quantity': quantity,
        'fee_basis_quote': '110' if quantity > 0 else '90', 'dispatched_at': NOW,
        'order_id': None, 'fill': None}
    order = NS(symbol=c.symbol, tag='ARV2N-synthetic', quantity=Decimal(quantity), absolute_quantity=abs(quantity))
    return NS(security=c.security, order=order)


@pytest.mark.parametrize('quantity,price', [(2, '110'), (-2, '90')])
def test_strategy_fee_basis_is_pure_repeatable_and_side_bound(public, quantity, price):
    c = case(public)
    parameters = strategy(c, quantity)
    before = copy.deepcopy(c.driver._intent)
    assert c.driver.fee_basis(parameters) == Decimal(price)
    assert c.driver.fee_basis(parameters) == Decimal(price)
    assert c.driver._intent == before
    c.driver._intent['fill'] = {'already_observed': True}
    assert c.driver.fee_basis(parameters) == Decimal(price)
    assert c.security.price == 100


def test_no_intent_forced_fee_keeps_original_security_price_without_clock_or_quote_read(public):
    c = case(public)
    c.driver._now = lambda: pytest.fail('forced fee must not require strategy dispatch clock')
    c.driver._quote_snapshot = lambda *args: pytest.fail('forced fee must not inspect strategy quote')
    assert c.driver.fee_basis(NS(security=c.security)) == Decimal('100')


@pytest.mark.parametrize('change,code', [('symbol', 'quote_execution_fee_order'),
    ('security', 'quote_execution_fee_order'), ('tag', 'quote_execution_fee_order'),
    ('quantity', 'quote_execution_fee_order'), ('dispatch', 'quote_execution_fee_intent'),
    ('quote', 'quote_execution_fee_intent')])
def test_strategy_fee_refuses_wrong_order_or_changed_frozen_basis(public, change, code):
    c = case(public)
    parameters = strategy(c)
    if change == 'symbol': parameters.order.symbol = NS(sid='wrong')
    if change == 'security': parameters.security = NS(symbol=NS(sid='wrong'))
    if change == 'tag': parameters.order.tag = 'wrong'
    if change == 'quantity': parameters.order.quantity = -2
    if change == 'dispatch': c.driver._intent['dispatched_at'] -= timedelta(minutes=1)
    if change == 'quote': c.driver._intent['fee_basis_quote'] = '109'
    with pytest.raises(NewruleError, match='^' + code + '$'):
        c.driver.fee_basis(parameters)


def test_main_fee_model_uses_driver_side_basis_not_stale_security_price(public):
    tree = ast.parse(public.files['main.py'])
    node = m._node(tree, 'NewruleTenBpsFeeModel', ast.ClassDef)
    namespace = {'FeeModel': object, 'Decimal': Decimal,
        'OrderFee': lambda cash: cash, 'CashAmount': lambda amount, currency: (amount, currency)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
        'synthetic projected fee class', 'exec'), namespace)
    c = case(public)
    parameters = strategy(c, 2)
    model = namespace['NewruleTenBpsFeeModel'](c.driver)
    assert model.get_order_fee(parameters) == (Decimal('0.220'), 'USD')
    assert model.get_order_fee(parameters) == (Decimal('0.220'), 'USD')
    c.driver._intent = None
    assert model.get_order_fee(parameters) == (Decimal('0.200'), 'USD')


def test_buy_budget_uses_ask_plus_fee_not_stale_price_or_midpoint(public):
    c = case(public)
    d = c.driver
    d._require_initialized = lambda: None
    d._decision_set = {NOW.date().isoformat()}
    d._preopen_clock_confirmations = set(d._decision_set)
    d._executed = set()
    d._split_records_by_session = {}
    d._plans = {NOW.date().isoformat(): {'holdings': {}, 'split_records': {}, 'quantities': {'ID': 2}, 'sha256': 'a' * 64}}
    d._algorithm.live_mode = False
    d._algorithm.transactions = NS(get_open_orders=lambda: ())
    holdings, cash, orders = {}, [Decimal(210)], []
    d._current_holding_census = lambda: dict(holdings)
    d._current_quantity = lambda identity: holdings.get(identity, 0)
    d._ensure_security = lambda identity: (c.symbol, c.security)
    d._portfolio_cash = lambda: cash[0]
    d._cash_underfill_count = 0
    def submit(identity, quantity, session):
        orders.append((identity, quantity))
        holdings[identity] = quantity
        cash[0] -= Decimal(quantity) * Decimal(110) * Decimal('1.001')
    d._submit_market = submit
    assert d.on_after_open() == 'a' * 64
    assert orders == [('ID', 1)] and cash[0] == Decimal('99.890')
    assert d._cash_underfill_count == 1 and d._executed == d._decision_set


@pytest.mark.parametrize('quantity,side,expected_cash', [(2, '110', '779.780'), (-2, '90', '1179.820')])
def test_submit_market_snapshots_side_and_reconciles_real_callback_fee_cash_holdings(public,
        quantity, side, expected_cash):
    c = case(public)
    d = c.driver
    session = NOW.date().isoformat()
    d._require_initialized = lambda: None
    d._status = lambda value: value
    d._order_ids, d._event_ids, d._fills = set(), set(), []
    d._plans = {session: {'sha256': 'a' * 64}}
    d._algorithm.live_mode = False
    holdings, cash, dispatched = [0 if quantity > 0 else 3], [Decimal(1000)], []
    d._ensure_security = lambda identity: (c.symbol, c.security)
    d._current_quantity = lambda identity: holdings[0]
    d._portfolio_cash = lambda: cash[0]
    engine = NS(id=7, tag=None, symbol=c.symbol, quantity=Decimal(quantity), absolute_quantity=abs(quantity))
    d._algorithm.transactions = NS(get_order_by_id=lambda order_id: engine)
    def market_order(symbol, signed_quantity, *, asynchronous, tag):
        assert symbol is c.symbol and signed_quantity == quantity and asynchronous is False
        engine.tag = tag
        snapshot = copy.deepcopy(d._intent)
        assert snapshot['fee_basis_quote'] == side and snapshot['quantity'] == quantity
        fee = d.fee_basis(NS(order=engine, security=c.security)) * abs(quantity) * Decimal('.001')
        assert d.fee_basis(NS(order=engine, security=c.security)) == Decimal(side)
        cash[0] -= Decimal(quantity) * Decimal(side) + fee
        holdings[0] += quantity
        event = NS(status='Filled', order_id=7, id=0, symbol=c.symbol, fill_quantity=quantity,
            fill_price=Decimal(side), order_fee=NS(value=NS(amount=fee, currency='USD')),
            utc_time=NOW.astimezone(timezone.utc))
        d.on_order_event(event)
        dispatched.append(snapshot)
        return NS(status='Filled', order_id=7)
    d._algorithm.market_order = market_order
    d._submit_market('synthetic-ID', quantity, session)
    assert d._intent is None and d._order_ids == {7} and len(d._fills) == 1
    assert cash[0] == Decimal(expected_cash) and holdings[0] == (2 if quantity > 0 else 1)
    assert d._fills[0]['fee_basis_quote'] == side and d._fills[0]['price'] == side
    assert c.security.price == Decimal(100) and len(dispatched) == 1


def event_case(public, *, omit=None, fill_price='110'):
    c = case(public, omit=omit)
    strategy(c, 2)
    d = c.driver
    d._require_initialized = lambda: None
    d._status = lambda value: value
    d._event_ids = set()
    d._algorithm.live_mode = False
    engine = NS(id=7, tag=d._intent['tag'], quantity=Decimal(2))
    d._algorithm.transactions = NS(get_order_by_id=lambda order_id: engine)
    event = NS(status='Filled', order_id=7, id=0, symbol=c.symbol, fill_quantity=2,
        fill_price=Decimal(fill_price), order_fee=NS(value=NS(amount=Decimal('.220'), currency='USD')),
        utc_time=NOW.astimezone(timezone.utc))
    return c, event


@pytest.mark.parametrize('fill_price,accepted', [('110', True), ('110.00000009', True), ('110.00000011', False), ('100', False)])
def test_actual_fill_must_match_frozen_side_with_fixed_absolute_tolerance(public, fill_price, accepted):
    c, event = event_case(public, fill_price=fill_price)
    if accepted:
        c.driver.on_order_event(event)
        assert c.driver._intent['fill']['price'] == fill_price
    else:
        with pytest.raises(NewruleError, match='^quote_execution_fill_price$'):
            c.driver.on_order_event(event)
        assert c.driver._intent['fill'] is None


@pytest.mark.parametrize('guard', ['quote_execution_period', 'quote_execution_cache_binding',
    'quote_execution_fee_order', 'quote_execution_fee_intent', 'quote_execution_fill_price'])
def test_dangerous_guard_omissions_are_detected_in_memory(public, guard):
    def assertion(omit=None):
        if guard == 'quote_execution_fill_price':
            c, event = event_case(public, omit=omit, fill_price='100')
            call = lambda: c.driver.on_order_event(event)
        else:
            c = case(public, omit=omit)
            if guard == 'quote_execution_period':
                c.quote.time -= timedelta(minutes=1)
                c.cached.time -= timedelta(minutes=1)
                call = lambda: c.driver._current_execution_price(c.security, 1)
            elif guard == 'quote_execution_cache_binding':
                c.cached.bid.close = '91'
                call = lambda: c.driver._current_execution_price(c.security, 1)
            else:
                parameters = strategy(c)
                if guard == 'quote_execution_fee_order': parameters.order.tag = 'wrong'
                else: c.driver._intent['dispatched_at'] -= timedelta(minutes=1)
                call = lambda: c.driver.fee_basis(parameters)
        try:
            call()
        except NewruleError:
            return
        raise AssertionError('unsafe omission escaped the regression')
    assertion()
    with pytest.raises(AssertionError, match='unsafe omission'):
        assertion(guard)


def test_build_projection_requires_existing_admission_and_exact_parent_record(public, monkeypatch):
    calls = []
    packet = object()
    def admitted(value):
        assert value is packet
        calls.append(value)
        return b'wrong parent record', public.pairs
    monkeypatch.setattr(m.admission, 'validate_packet', admitted)
    with pytest.raises(m.Refused, match='^parent_projection$'):
        m.build_projection(packet, patcher_source_bytes=public.patcher, expected_patcher_sha256=public.pin)
    assert calls == [packet]


def test_no_structured_error_or_raw_context_is_admitted():
    assert len(set(m.FAILURE_CODES)) == len(m.FAILURE_CODES)
    assert all(code.startswith('quote_execution_') and len(code) <= 64 for code in m.FAILURE_CODES)
    for value in (None, 'secret symbol', {}, {'price': 123}, True):
        assert m.parse_failure_context(value) is None
        with pytest.raises(m.Refused, match='^failure_context$'):
            m.validate_failure_context(value)
